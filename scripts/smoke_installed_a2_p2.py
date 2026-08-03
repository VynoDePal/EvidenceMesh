"""Exercise an installed EvidenceMesh A2 distribution without source imports.

The caller must invoke this script with the interpreter of the environment in
which the wheel or sdist was installed.  The generic RC4.1A installed smoke is
run first for the CLI/MCP and backwards-compatibility contract.  This module
then binds every A2 runtime file from the source archive, through RECORD, to
the installed bytes and exercises the additive v3 liveness path using only an
``httpx.MockTransport``.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import contextlib
import csv
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import shutil
import socket
import sqlite3
import stat
import sys
import tarfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, NoReturn, cast

import httpx

import evidencemesh
import evidencemesh.closed_alpha_feedback as feedback_module
from evidencemesh.alpha_liveness import (
    A2RetentionSupervisor,
    A2SQLiteAlphaControlPlane,
    A2SQLiteBudgetGovernor,
)
from evidencemesh.closed_alpha_feedback import (
    ClosedAlphaFeedbackContract,
    ClosedAlphaFeedbackIdentity,
    ClosedAlphaFeedbackStore,
)
from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError
from evidencemesh.governor import (
    AlphaControlState,
    ClosedAlphaAdmission,
    ClosedAlphaSession,
    DispatchIntent,
    SQLiteAlphaControlPlane,
)

SMOKE_ID = "evidencemesh-installed-alpha-a2-p2-v1"
PACKAGE_VERSION = "0.1.0"
BOOT_ID = b"01234567-89ab-cdef-0123-456789abcdef\n"
SESSION_SECRET = b"s" * 32
SUPERVISOR_SECRET = b"r" * 32
RECOVERY_SESSION_SECRET = b"x" * 32
RUNTIME_FILES = (
    "evidencemesh/__init__.py",
    "evidencemesh/alpha_liveness.py",
    "evidencemesh/closed_alpha_feedback.py",
    "evidencemesh/engine.py",
    "evidencemesh/fetcher.py",
)
EXPECTED_ENTRY_POINTS = {
    "evidencemesh": "evidencemesh.cli:app",
    "evidencemesh-mcp": "evidencemesh.mcp_server:main",
}
FORBIDDEN_ARCHIVE_PARTS = frozenset(
    {
        ".cache",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "dist",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside_prefix(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path(sys.prefix).resolve())
    except ValueError:
        return False
    return True


def _ensure_private_root(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)


def _safe_member_name(value: str) -> PurePosixPath:
    member = PurePosixPath(value)
    _require(not member.is_absolute(), "Archive member is absolute")
    _require(".." not in member.parts, "Archive member escapes its root")
    return member


def _require_clean_member_parts(member: PurePosixPath, *, skip_root: bool) -> None:
    inspected = member.parts[1:] if skip_root else member.parts
    _require(
        not any(part in FORBIDDEN_ARCHIVE_PARTS for part in inspected),
        "Archive contains a repository, environment, build, or cache path",
    )


def _validate_archive_inventory(archive: Path, *, label: str) -> dict[str, int | bool]:
    names: set[PurePosixPath] = set()
    regular_files = 0
    directories = 0
    if label == "wheel":
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                member = _safe_member_name(info.filename)
                _require(member not in names, "Wheel contains a duplicate member")
                names.add(member)
                _require_clean_member_parts(member, skip_root=False)
                unix_mode = info.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                _require(file_type != stat.S_IFLNK, "Wheel contains a symbolic link")
                _require(
                    file_type in {0, stat.S_IFREG, stat.S_IFDIR},
                    "Wheel contains a special member",
                )
                if info.is_dir():
                    directories += 1
                else:
                    regular_files += 1
    elif label == "sdist":
        roots: set[str] = set()
        with tarfile.open(archive, mode="r:gz") as bundle:
            for info in bundle.getmembers():
                member = _safe_member_name(info.name)
                _require(member not in names, "Sdist contains a duplicate member")
                names.add(member)
                _require(member.parts != (), "Sdist contains an empty member")
                roots.add(member.parts[0])
                _require_clean_member_parts(member, skip_root=True)
                _require(
                    not (info.issym() or info.islnk() or info.isdev() or info.isfifo()),
                    "Sdist contains a link or special member",
                )
                _require(info.isfile() or info.isdir(), "Sdist member type is unsupported")
                if info.isdir():
                    directories += 1
                else:
                    regular_files += 1
        _require(roots == {"evidencemesh-0.1.0"}, "Sdist root directory drifted")
    else:
        raise ValueError("label must be wheel or sdist")
    _require(regular_files > 0, "Distribution archive contains no regular file")
    return {
        "archive_member_paths_safe": True,
        "archive_members_unique": True,
        "directories": directories,
        "links_or_special_members": 0,
        "regular_files": regular_files,
    }


def _archive_runtime_bytes(archive: Path, *, label: str, relative_path: str) -> bytes:
    """Read exactly one regular A2 runtime member from a wheel or sdist."""

    relative = PurePosixPath(relative_path)
    if label == "wheel":
        with zipfile.ZipFile(archive) as bundle:
            matches = [
                info
                for info in bundle.infolist()
                if _safe_member_name(info.filename) == relative and not info.is_dir()
            ]
            _require(len(matches) == 1, f"Wheel runtime member is not unique: {relative_path}")
            return bundle.read(matches[0])
    if label != "sdist":
        raise ValueError("label must be wheel or sdist")
    with tarfile.open(archive, mode="r:gz") as bundle:
        matches = []
        for member in bundle.getmembers():
            name = _safe_member_name(member.name)
            if len(name.parts) >= 2 and PurePosixPath(*name.parts[1:]) == PurePosixPath(
                "src", relative
            ):
                matches.append(member)
        _require(len(matches) == 1, f"Sdist runtime member is not unique: {relative_path}")
        member = matches[0]
        _require(
            member.isfile() and not member.issym() and not member.islnk(),
            "Unsafe sdist member",
        )
        extracted = bundle.extractfile(member)
        _require(extracted is not None, "Sdist runtime member cannot be read")
        return extracted.read()


def _record_rows(distribution: importlib.metadata.Distribution) -> dict[str, tuple[str, str]]:
    record_text = distribution.read_text("RECORD")
    _require(record_text is not None, "Installed distribution has no RECORD")
    rows: dict[str, tuple[str, str]] = {}
    for row in csv.reader(StringIO(record_text)):
        _require(len(row) == 3, "Installed RECORD row is malformed")
        path, digest, size = row
        _require(path not in rows, "Installed RECORD contains a duplicate path")
        rows[path] = (digest, size)
    declared_files = distribution.files
    _require(declared_files is not None, "Installed distribution file inventory is absent")
    _require(
        set(rows) == {str(path) for path in declared_files},
        "Installed RECORD and distribution file inventory differ",
    )
    record_entries = [path for path in rows if path.endswith(".dist-info/RECORD")]
    _require(len(record_entries) == 1, "Installed distribution has no unique RECORD entry")
    _require(rows[record_entries[0]] == ("", ""), "RECORD self-entry must be unhashed")
    return rows


def _rehash_record(
    distribution: importlib.metadata.Distribution,
    rows: dict[str, tuple[str, str]],
) -> dict[str, int | bool]:
    hashed = 0
    unhashed = 0
    for relative_path, (digest, size) in rows.items():
        installed = Path(distribution.locate_file(relative_path)).resolve()
        _require(_inside_prefix(installed), "RECORD path escaped sys.prefix")
        _require(installed.is_file() and not installed.is_symlink(), "RECORD path is unsafe")
        if digest == "":
            unhashed += 1
            _require(size == "", "Unhashed RECORD row has a size")
            _require(relative_path.endswith(".dist-info/RECORD"), "Unexpected unhashed RECORD row")
            continue
        _require(size.isdigit(), "Hashed RECORD row has an invalid size")
        payload = installed.read_bytes()
        _require(len(payload) == int(size), "Installed RECORD file size drifted")
        _require(
            _record_sha256(digest) == hashlib.sha256(payload).digest(), "RECORD file hash drifted"
        )
        hashed += 1
    _require(hashed > 0 and unhashed == 1, "Installed RECORD hash coverage drifted")
    metadata_names = {"METADATA", "WHEEL", "entry_points.txt", "direct_url.json", "RECORD"}
    for name in metadata_names:
        matches = [path for path in rows if path.endswith(f".dist-info/{name}")]
        _require(len(matches) == 1, f"Installed metadata entry is not unique: {name}")
    return {
        "all_hashed_entries_reverified": True,
        "critical_metadata_entries": len(metadata_names),
        "hashed_entries": hashed,
        "record_self_unhashed_entries": unhashed,
    }


def _direct_url_binding(
    distribution: importlib.metadata.Distribution,
    archive: Path,
    expected_archive_sha256: str,
) -> dict[str, bool | str]:
    raw = distribution.read_text("direct_url.json")
    _require(raw is not None, "Installed distribution has no PEP 610 direct_url.json")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Installed PEP 610 direct_url.json is invalid") from exc
    _require(isinstance(payload, dict), "Installed PEP 610 record is not an object")
    expected_url = f"{archive.resolve().as_uri()}#sha256={expected_archive_sha256}"
    _require(payload.get("url") == expected_url, "PEP 610 hashed archive URL drifted")
    archive_info = payload.get("archive_info")
    _require(isinstance(archive_info, dict), "PEP 610 record is not archive-bound")
    _require("dir_info" not in payload and "vcs_info" not in payload, "PEP 610 source is mutable")
    declared: list[str] = []
    hashes = archive_info.get("hashes")
    if isinstance(hashes, dict) and isinstance(hashes.get("sha256"), str):
        declared.append(cast(str, hashes["sha256"]))
    legacy = archive_info.get("hash")
    if isinstance(legacy, str) and legacy.startswith("sha256="):
        declared.append(legacy.removeprefix("sha256="))
    _require(
        archive_info == {} or declared != [],
        "PEP 610 archive_info is neither empty nor SHA-256-bound",
    )
    if declared:
        _require(
            all(value == expected_archive_sha256 for value in declared),
            "PEP 610 archive_info SHA-256 drifted",
        )
    return {
        "archive_sha256_exact": True,
        "binding_scope": "url_and_sha256",
        "sha256_location": "url_fragment" if not declared else "url_fragment_and_archive_info",
        "url_exact": True,
    }


def _installed_module_origins() -> dict[str, str]:
    expected = {
        "evidencemesh": "__init__.py",
        "evidencemesh.alpha_liveness": "alpha_liveness.py",
        "evidencemesh.closed_alpha_feedback": "closed_alpha_feedback.py",
        "evidencemesh.engine": "engine.py",
        "evidencemesh.fetcher": "fetcher.py",
    }
    origins: dict[str, str] = {}
    for module_name, filename in expected.items():
        module = importlib.import_module(module_name)
        raw_origin = getattr(module, "__file__", None)
        _require(isinstance(raw_origin, str), f"Installed module origin is absent: {module_name}")
        origin = Path(raw_origin).resolve()
        _require(_inside_prefix(origin), f"Installed module escaped sys.prefix: {module_name}")
        _require(origin.name == filename, f"Installed module filename drifted: {module_name}")
        origins[module_name] = filename
    harness_directory = Path(__file__).resolve().parent
    repository_root = harness_directory.parent
    source_root = repository_root / "src"
    for entry in sys.path:
        if not entry:
            continue
        resolved = Path(entry).resolve()
        _require(
            resolved not in {harness_directory, repository_root, source_root},
            "sys.path exposes the harness or its source tree",
        )
        _require(resolved.name != "src", "sys.path exposes a source directory")
        if (resolved / "evidencemesh").is_dir():
            _require(_inside_prefix(resolved), "sys.path exposes a non-installed EvidenceMesh")
        _require(
            not any(part in {"export-one", "export-two"} for part in resolved.parts),
            "sys.path exposes a clean source export",
        )
    return origins


def _remove_harness_paths_from_sys_path() -> None:
    harness_directory = Path(__file__).resolve().parent
    retained: list[str] = []
    for entry in sys.path:
        if not entry:
            retained.append(entry)
            continue
        resolved = Path(entry).resolve()
        if resolved == harness_directory:
            continue
        retained.append(entry)
    sys.path[:] = retained


def _record_sha256(digest: str) -> bytes:
    algorithm, separator, encoded = digest.partition("=")
    _require(separator == "=" and algorithm == "sha256", "Runtime RECORD hash is not SHA-256")
    _require(
        re.fullmatch(r"[A-Za-z0-9_-]{43}", encoded) is not None,
        "Runtime RECORD hash is invalid",
    )
    try:
        return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("Runtime RECORD hash is invalid") from exc


def _validate_installed_identity_and_runtime_files(
    *,
    label: str,
    archive: Path,
    expected_archive_sha256: str,
    cli_command: Path,
    mcp_command: Path,
) -> dict[str, Any]:
    expected_name = (
        "evidencemesh-0.1.0-py3-none-any.whl" if label == "wheel" else "evidencemesh-0.1.0.tar.gz"
    )
    _require(archive.is_file(), "A2-P2 source archive is missing")
    _require(archive.name == expected_name, "A2-P2 source archive name drifted")
    _require(
        len(expected_archive_sha256) == 64
        and all(character in "0123456789abcdef" for character in expected_archive_sha256),
        "Expected archive SHA-256 is invalid",
    )
    _require(_sha256_file(archive) == expected_archive_sha256, "Source archive SHA-256 drifted")

    package_file = getattr(evidencemesh, "__file__", None)
    _require(isinstance(package_file, str), "Installed EvidenceMesh origin is absent")
    package_origin = Path(package_file).resolve()
    _require(_inside_prefix(package_origin), "EvidenceMesh was not imported from sys.prefix")
    _require(sys.prefix != sys.base_prefix, "A2-P2 smoke requires an isolated environment")

    commands = (cli_command.resolve(), mcp_command.resolve())
    for command in commands:
        _require(command.is_file() and os.access(command, os.X_OK), "Installed command is missing")
        _require(_inside_prefix(command), "Installed command is outside sys.prefix")

    distribution = importlib.metadata.distribution("evidencemesh")
    _require(distribution.version == PACKAGE_VERSION, "Installed package version drifted")
    entry_points = {
        item.name: item.value
        for item in distribution.entry_points
        if item.group == "console_scripts" and item.name.startswith("evidencemesh")
    }
    _require(entry_points == EXPECTED_ENTRY_POINTS, "Installed entry points drifted")
    rows = _record_rows(distribution)
    record_verification = _rehash_record(distribution, rows)
    direct_url = _direct_url_binding(distribution, archive, expected_archive_sha256)
    module_origins = _installed_module_origins()
    record_path = next(path for path in rows if path.endswith(".dist-info/RECORD"))
    dist_info = Path(distribution.locate_file(record_path)).resolve().parent
    _require(_inside_prefix(dist_info), "Installed dist-info escaped sys.prefix")
    _require(dist_info.name.endswith(".dist-info"), "Installed dist-info path drifted")

    runtime_hashes: dict[str, str] = {}
    for relative_path in RUNTIME_FILES:
        archive_payload = _archive_runtime_bytes(
            archive,
            label=label,
            relative_path=relative_path,
        )
        matches = [path for path in rows if path == relative_path]
        _require(len(matches) == 1, f"Runtime RECORD entry is not exact: {relative_path}")
        digest, size = rows[relative_path]
        installed_path = Path(distribution.locate_file(relative_path)).resolve()
        _require(_inside_prefix(installed_path), "Installed runtime file escaped sys.prefix")
        _require(
            installed_path.is_file() and not installed_path.is_symlink(),
            "Runtime file unsafe",
        )
        installed_payload = installed_path.read_bytes()
        _require(installed_payload == archive_payload, "Archive and installed runtime bytes differ")
        _require(
            _record_sha256(digest) == hashlib.sha256(installed_payload).digest(),
            "RECORD hash drifted",
        )
        _require(size == str(len(installed_payload)), "RECORD size drifted")
        runtime_hashes[relative_path] = _sha256_bytes(installed_payload)

    return {
        "archive_inventory": _validate_archive_inventory(archive, label=label),
        "archive_name": archive.name,
        "archive_sha256": expected_archive_sha256,
        "entry_points_exact": True,
        "module_origins": module_origins,
        "package_origin_within_prefix": True,
        "package_version": distribution.version,
        "pep610": direct_url,
        "dist_info_within_prefix": True,
        "record_inventory_exact": True,
        "record_verification": record_verification,
        "runtime_archive_record_install_exact": True,
        "runtime_file_count": len(RUNTIME_FILES),
        "runtime_sha256": runtime_hashes,
        "virtual_environment": True,
    }


def _load_rc4_smoke() -> ModuleType:
    """Load the sibling harness only when the composite smoke actually runs."""

    try:
        module = importlib.import_module("scripts.smoke_installed_rc4_1a")
    except ModuleNotFoundError:
        module = importlib.import_module("smoke_installed_rc4_1a")
    _remove_harness_paths_from_sys_path()
    return module


def _run_rc4_compatibility(
    *,
    root: Path,
    cli_command: Path,
    mcp_command: Path,
) -> dict[str, Any]:
    """Reuse only the installed CLI/MCP exercises, not RC4's older PEP 610 policy."""

    module = _load_rc4_smoke()
    private_directory = getattr(module, "_private_directory", None)
    exercise_cli = getattr(module, "_exercise_cli", None)
    exercise_mcp = getattr(module, "_exercise_mcp", None)
    _require(callable(private_directory), "RC4.1A private-directory helper is missing")
    _require(callable(exercise_cli), "RC4.1A CLI exercise is missing")
    _require(callable(exercise_mcp), "RC4.1A MCP exercise is missing")
    prepared_root = private_directory(root.resolve())
    cli_result = exercise_cli(prepared_root, cli_command.resolve())
    mcp_result = exercise_mcp(prepared_root, mcp_command.resolve())
    isolation_keys = (*cli_result.isolation_keys, *mcp_result.isolation_keys)
    ledgers = [key[0] for key in isolation_keys]
    sessions = [key[1] for key in isolation_keys]
    _require(len(set(ledgers)) == len(ledgers), "RC4.1A CLI/MCP reused a subprocess ledger")
    _require(len(set(sessions)) == len(sessions), "RC4.1A CLI/MCP reused a subprocess session")
    cli_report = cast(dict[str, Any], cli_result.report)
    mcp_report = cast(dict[str, Any], mcp_result.report)
    _require(cli_report["providers_command"]["health_status"] == "ready", "RC4 CLI failed")
    _require(mcp_report["health_status"] == "ready", "RC4 MCP failed")
    return {
        "cli_health_ready": True,
        "composite_passed": True,
        "distinct_subprocess_ledgers": True,
        "distinct_subprocess_sessions": True,
        "mcp_health_ready": True,
        "smoke": "evidencemesh-installed-alpha-rc4.1a-v1",
    }


class _HostClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def boottime(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    @staticmethod
    def boot_identity() -> bytes:
        return BOOT_ID


class _FeedbackClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 3, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _participant(index: int) -> str:
    return f"p-{index:016x}"


def _session(index: int) -> str:
    return f"s-{index:032x}"


def _admit_full_cohort(control: A2SQLiteAlphaControlPlane) -> None:
    for index in range(1, 7):
        control.admit(
            ClosedAlphaAdmission(
                participant_code=_participant(index),
                slot_id=f"C{index:02d}",
                profile="community",
                consent_version="closed-alpha-a0-consent-v1",
                consent_accepted=True,
                input_authority_attested=True,
                non_sensitive_use_attested=True,
            )
        )
    for offset in range(1, 3):
        control.admit(
            ClosedAlphaAdmission(
                participant_code=_participant(6 + offset),
                slot_id=f"Q{offset:02d}",
                profile="quality",
                consent_version="closed-alpha-a0-consent-v1",
                consent_accepted=True,
                input_authority_attested=True,
                non_sensitive_use_attested=True,
            )
        )


def _synthetic_installed_contract(archive_sha256: str, label: str) -> ClosedAlphaFeedbackContract:
    """Create a private smoke-only identity; it is not provenance evidence."""

    identity = object.__new__(ClosedAlphaFeedbackIdentity)
    values: dict[str, object] = {
        "candidate_sha": archive_sha256[:40],
        "candidate_tree": archive_sha256[24:64],
        "repository": "VynoDePal/EvidenceMesh",
        "record_sha256": archive_sha256,
        "archive_subject": (
            "dist/evidencemesh-0.1.0-py3-none-any.whl"
            if label == "wheel"
            else "dist/evidencemesh-0.1.0.tar.gz"
        ),
        "archive_sha256": archive_sha256,
        "_verification": feedback_module._IDENTITY_VERIFICATION,
    }
    for name, value in values.items():
        object.__setattr__(identity, name, value)
    return ClosedAlphaFeedbackContract(identity)


def _feedback_report(archive_sha256: str, collected_at: datetime) -> dict[str, object]:
    collected_on = collected_at.date()
    return {
        "schema_version": "evidencemesh.closed-alpha-a0.session.v1",
        "protocol_version": "closed-alpha-a0-v1",
        "candidate_sha": archive_sha256[:40],
        "participant_code": _participant(1),
        "session_code": _session(1),
        "slot_id": "C01",
        "profile": "community",
        "task": {"slot": 1, "kind": "prescribed", "category": "general_reference"},
        "retention": {
            "collected_on": collected_on.isoformat(),
            "delete_after": (collected_on + timedelta(days=14)).isoformat(),
        },
        "consent": {
            "version": "closed-alpha-a0-consent-v1",
            "confirmed": True,
            "authority_confirmed": True,
            "withdrawal_requested": False,
        },
        "outcome": {
            "status": "completed",
            "duration_seconds": 1,
            "useful": True,
            "blocking": False,
            "failure_kind": "none",
        },
        "traffic": {
            "provider_attempts": 1,
            "tavily_attempts": 0,
            "provider_errors": 0,
            "evidencemesh_model_attempts": 0,
            "automatic_retries": 0,
            "fallbacks": 0,
            "repairs": 0,
        },
        "grounding_counts": {
            "results": 1,
            "citations": 1,
            "resolvable_citations": 1,
            "supported_citations": 1,
        },
        "privacy": {
            "cache_disabled": True,
            "raw_runtime_objects_serialized": False,
            "sensitive_input_detected": False,
            "incident_detected": False,
        },
    }


@contextmanager
def _deny_real_network() -> Iterator[dict[str, int]]:
    attempts = {"socket_connect": 0, "dns_resolution": 0}
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo

    def deny_connect(_socket: socket.socket, _address: object) -> NoReturn:
        attempts["socket_connect"] += 1
        raise RuntimeError("A2-P2 real socket access is forbidden")

    def deny_connect_ex(_socket: socket.socket, _address: object) -> int:
        attempts["socket_connect"] += 1
        return 1

    def deny_create_connection(*_args: object, **_kwargs: object) -> NoReturn:
        attempts["socket_connect"] += 1
        raise RuntimeError("A2-P2 real socket access is forbidden")

    def deny_getaddrinfo(*_args: object, **_kwargs: object) -> NoReturn:
        attempts["dns_resolution"] += 1
        raise RuntimeError("A2-P2 DNS access is forbidden")

    socket.socket.connect = deny_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = deny_connect_ex  # type: ignore[method-assign]
    socket.create_connection = deny_create_connection
    socket.getaddrinfo = deny_getaddrinfo
    try:
        yield attempts
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = original_connect_ex  # type: ignore[method-assign]
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo


def _v2_refusal(root: Path, host: _HostClock) -> dict[str, Any]:
    ledger = root / "v2" / "control.sqlite3"
    SQLiteAlphaControlPlane.bootstrap(ledger, clock=host.boottime)
    before_payload = ledger.read_bytes()
    before_names = sorted(path.name for path in ledger.parent.iterdir())
    try:
        A2SQLiteAlphaControlPlane(
            ledger,
            boottime=host.boottime,
            boot_identity=host.boot_identity,
        )
    except BudgetConfigurationError:
        pass
    else:
        raise RuntimeError("A2 accepted a v2 ledger")
    _require(ledger.read_bytes() == before_payload, "A2 mutated the refused v2 ledger")
    _require(
        sorted(path.name for path in ledger.parent.iterdir()) == before_names,
        "A2 created files while refusing the v2 ledger",
    )
    return {"refused": True, "ledger_bytes_unchanged": True, "directory_entries_unchanged": True}


async def _autonomous_heartbeat(governor: A2SQLiteBudgetGovernor, host: _HostClock) -> int:
    stop = asyncio.Event()
    calls = 0

    async def wait(_seconds: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            host.advance(1.0)
        else:
            stop.set()

    await governor.run_session_heartbeat(stop, wait=wait)
    return calls - 1


async def _exercise_primary_v3(root: Path, archive_sha256: str, label: str) -> dict[str, Any]:
    _ensure_private_root(root)
    host = _HostClock()
    feedback_clock = _FeedbackClock()
    ledger = root / "v3" / "control.sqlite3"
    control = A2SQLiteAlphaControlPlane.bootstrap(
        ledger,
        boottime=host.boottime,
        boot_identity=host.boot_identity,
    )
    governor = A2SQLiteBudgetGovernor(
        ledger,
        ClosedAlphaSession(_participant(1), _session(1), "community"),
        boottime=host.boottime,
        boot_identity=host.boot_identity,
        owner_secret=SESSION_SECRET,
    )
    store = ClosedAlphaFeedbackStore(
        root / "feedback",
        _synthetic_installed_contract(archive_sha256, label),
        governor,
        clock=feedback_clock,
    )
    supervisor: A2RetentionSupervisor | None = None
    client: httpx.AsyncClient | None = None
    inner_calls = 0
    try:
        bound_epoch = control.bind_feedback_store(store, expected_control_epoch=1)
        _require(bound_epoch == 2, "A2 store binding epoch drifted")
        supervisor = A2RetentionSupervisor(control, store, owner_secret=SUPERVISOR_SECRET)
        lease = await supervisor.run_once()
        _require(lease.state == "active", "A2 supervisor did not acquire its lease")
        _admit_full_cohort(control)
        prepared_epoch = control.transition(
            AlphaControlState.PREPARED,
            expected_state=AlphaControlState.PAUSED,
            expected_epoch=bound_epoch,
        )
        _require(prepared_epoch == 3, "A2 prepared epoch drifted")
        _require(await governor.open_session() == 1, "A2 session did not open")
        heartbeat_count = await _autonomous_heartbeat(governor, host)
        _require(heartbeat_count == 1, "A2 autonomous heartbeat count drifted")
        permits = await governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
        _require(len(permits) == 1, "A2 did not reserve exactly one permit")

        def inner(request: httpx.Request) -> httpx.Response:
            nonlocal inner_calls
            inner_calls += 1
            return httpx.Response(200, json={"offline": True}, request=request)

        client = governor.make_client(httpx.MockTransport(inner))
        with governor.capture(permits[0]):
            response = await client.get("https://offline.invalid/a2-p2")
        _require(response.status_code == 200, "A2 MockTransport response drifted")
        _require(response.json() == {"offline": True}, "A2 MockTransport body drifted")
        _require(inner_calls == 1, "A2 transport delegated more than once")
        try:
            with governor.capture(permits[0]):
                await client.get("https://offline.invalid/replay")
        except BudgetExceededError:
            permit_replay_refused = True
        else:
            raise RuntimeError("A2 reused a consumed permit")
        await governor.aclose()
        closed_authority = governor.feedback_authority
        _require(closed_authority.session_code == _session(1), "A2 close authority drifted")
        feedback_path = root / "feedback" / f"{_session(1)}.json"
        publication = store.put(
            _feedback_report(archive_sha256, feedback_clock.now),
            authority=closed_authority,
        )
        _require(publication.created is True, "A2 feedback publication was not created")
        _require(feedback_path.is_file(), "A2 feedback publication is missing")
        await supervisor.aclose()
        _require(
            control.withdraw(_participant(1), expected_admission_epoch=1) == 2,
            "A2 withdrawal epoch drifted",
        )
        _require(store.withdraw(_participant(1)) == 1, "A2 withdrawal did not clean feedback")
        _require(not feedback_path.exists(), "A2 withdrawal left feedback behind")
        final = control.snapshot()
        _require(final["state"] == "paused", "A2 shutdown did not pause control")
        _require(final["supervisor_state"] == "revoked", "A2 shutdown did not revoke lease")
        return {
            "autonomous_session_heartbeats": heartbeat_count,
            "bootstrap_schema": "evidencemesh.closed-alpha-control-plane.v3",
            "closed_session_authority_created": True,
            "feedback_store_bound": True,
            "feedback_published_then_withdrawn": True,
            "mock_transport_delegations": inner_calls,
            "permit_replay_refused": permit_replay_refused,
            "prepared": True,
            "reserved_permits": 1,
            "shutdown_paused": True,
            "supervisor_revoked": True,
        }
    finally:
        if client is not None:
            with contextlib.suppress(BaseException):
                await client.aclose()
        with contextlib.suppress(BaseException):
            await governor.aclose()
        if supervisor is not None:
            with contextlib.suppress(BaseException):
                await supervisor.aclose()
        if not store.closed:
            store.close()


async def _exercise_recovery(root: Path, archive_sha256: str, label: str) -> dict[str, Any]:
    _ensure_private_root(root)
    host = _HostClock()
    feedback_clock = _FeedbackClock()
    ledger = root / "v3" / "control.sqlite3"
    control = A2SQLiteAlphaControlPlane.bootstrap(
        ledger,
        boottime=host.boottime,
        boot_identity=host.boot_identity,
    )
    governor = A2SQLiteBudgetGovernor(
        ledger,
        ClosedAlphaSession(_participant(1), _session(2), "community"),
        boottime=host.boottime,
        boot_identity=host.boot_identity,
        owner_secret=RECOVERY_SESSION_SECRET,
    )
    store = ClosedAlphaFeedbackStore(
        root / "feedback",
        _synthetic_installed_contract(archive_sha256, label),
        governor,
        clock=feedback_clock,
    )
    supervisor: A2RetentionSupervisor | None = None
    try:
        bound_epoch = control.bind_feedback_store(store, expected_control_epoch=1)
        supervisor = A2RetentionSupervisor(control, store, owner_secret=SUPERVISOR_SECRET)
        await supervisor.run_once()
        _admit_full_cohort(control)
        control.transition(
            AlphaControlState.PREPARED,
            expected_state=AlphaControlState.PAUSED,
            expected_epoch=bound_epoch,
        )
        await governor.open_session()
        await governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
        host.advance(300.0)
        try:
            await governor.aclose()
        except BudgetExceededError:
            pass
        else:
            raise RuntimeError("Expired A2 session closed without recovery containment")
        snapshot = control.snapshot()
        _require(snapshot["state"] == "paused", "Recovery did not pause A2 control")
        with sqlite3.connect(ledger) as database:
            session_status = database.execute(
                "SELECT status FROM sessions WHERE session_code = ?",
                (_session(2),),
            ).fetchone()
            attempt = database.execute(
                "SELECT dispatched, outcome FROM attempts WHERE session_code = ?",
                (_session(2),),
            ).fetchone()
        _require(session_status == ("recovery_required",), "Expired session was not quarantined")
        _require(attempt == (1, "denied_recovery"), "Reserved permit was not denied in recovery")
        recovery_epoch = snapshot["control_epoch"]
        _require(type(recovery_epoch) is int, "Recovery control epoch is invalid")
        control.resolve_recovery(_session(2), expected_control_epoch=cast(int, recovery_epoch))
        with sqlite3.connect(ledger) as database:
            resolved = database.execute(
                "SELECT status FROM sessions WHERE session_code = ?",
                (_session(2),),
            ).fetchone()
        _require(resolved == ("closed",), "Explicit A2 recovery did not close the session")
        return {
            "expired_close_refused": True,
            "reserved_permit_denied": True,
            "session_quarantined": True,
            "explicit_recovery_closed_session": True,
        }
    finally:
        with contextlib.suppress(BaseException):
            await governor.aclose()
        if supervisor is not None:
            with contextlib.suppress(BaseException):
                await supervisor.aclose()
        if not store.closed:
            store.close()


async def _exercise_a2(root: Path, archive_sha256: str, label: str) -> dict[str, Any]:
    _ensure_private_root(root)
    host = _HostClock()
    v2 = _v2_refusal(root, host)
    with _deny_real_network() as attempts:
        primary = await _exercise_primary_v3(root / "primary", archive_sha256, label)
        recovery = await _exercise_recovery(root / "recovery", archive_sha256, label)
    _require(attempts == {"socket_connect": 0, "dns_resolution": 0}, "Real network attempted")
    return {
        "network": {
            "dns_resolution_attempts": 0,
            "mock_transport_only": True,
            "real_socket_attempts": 0,
        },
        "primary": primary,
        "recovery": recovery,
        "v2_compatibility": v2,
    }


def run_smoke(
    *,
    label: str,
    cli_command: Path,
    mcp_command: Path,
    distribution: Path,
    expected_archive_sha256: str,
    work_root: Path,
    output: Path,
) -> dict[str, Any]:
    if label not in {"wheel", "sdist"}:
        raise ValueError("label must be wheel or sdist")
    resolved_root = work_root.resolve()
    resolved_output = output.resolve()
    _require(not resolved_root.exists(), "A2-P2 work root must not exist")
    _require(resolved_root.parent.is_dir(), "A2-P2 work-root parent is missing")
    _require(
        not resolved_output.is_relative_to(resolved_root),
        "A2-P2 output must be outside the ephemeral work root",
    )
    _require(not resolved_output.exists(), "A2-P2 output already exists")
    resolved_root.mkdir(mode=0o700)
    report: dict[str, Any] | None = None
    try:
        rc4_compatibility = _run_rc4_compatibility(
            root=resolved_root / "rc4-compatibility",
            cli_command=cli_command,
            mcp_command=mcp_command,
        )
        installation = _validate_installed_identity_and_runtime_files(
            label=label,
            archive=distribution.resolve(),
            expected_archive_sha256=expected_archive_sha256,
            cli_command=cli_command,
            mcp_command=mcp_command,
        )
        a2 = asyncio.run(_exercise_a2(resolved_root / "a2-runtime", expected_archive_sha256, label))
        report = {
            "a2_runtime": a2,
            "installation": installation,
            "label": label,
            "limitations": {
                "cross_platform_installability_validated": False,
                "live_provider_or_model_validated": False,
                "mock_transport_is_live_network_evidence": False,
                "synthetic_store_identity_is_public_provenance": False,
            },
            "rc4_1a_compatibility": rc4_compatibility,
            "schema_version": 1,
            "smoke": SMOKE_ID,
            "traffic": {
                "document_requests": 0,
                "model_requests": 0,
                "provider_requests": 0,
                "real_network_requests": 0,
                "retries": 0,
            },
            "validation": {"errors": [], "passed": True},
        }
    finally:
        if resolved_root.exists():
            shutil.rmtree(resolved_root)
        _require(not resolved_root.exists(), "A2-P2 ephemeral work root survived cleanup")
    _require(report is not None, "A2-P2 smoke did not produce a report")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=("wheel", "sdist"), required=True)
    parser.add_argument("--cli-command", type=Path, required=True)
    parser.add_argument("--mcp-command", type=Path, required=True)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    run_smoke(
        label=args.label,
        cli_command=args.cli_command,
        mcp_command=args.mcp_command,
        distribution=args.distribution,
        expected_archive_sha256=args.expected_archive_sha256,
        work_root=args.work_root,
        output=args.output,
    )


if __name__ == "__main__":
    main()
