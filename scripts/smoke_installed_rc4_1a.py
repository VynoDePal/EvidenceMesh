"""Exercise an installed RC4.1A distribution without any external request."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.metadata
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import evidencemesh
from evidencemesh.governor import (
    AlphaControlState,
    ClosedAlphaAdmission,
    SQLiteAlphaControlPlane,
)

SMOKE_ID = "evidencemesh-installed-alpha-rc4.1a-v1"
PACKAGE_VERSION = "0.1.0"
CONSENT_VERSION = "closed-alpha-a0-consent-v1"
COMMUNITY_PROVIDERS = ["arxiv", "crossref", "github", "searxng", "wikipedia"]
EXPECTED_TOOLS = [
    "search_web",
    "deep_research",
    "fetch_url",
    "batch_search",
    "verify_claim",
    "health",
]
EXPECTED_RESOURCES = ["evidencemesh://research-guide"]
EXPECTED_PROMPTS = ["evidence_first_research"]
CRITICAL_PACKAGE_FILES = (
    "evidencemesh/__init__.py",
    "evidencemesh/cli.py",
    "evidencemesh/closed_alpha_feedback.py",
    "evidencemesh/config.py",
    "evidencemesh/governor.py",
    "evidencemesh/mcp_server.py",
)
EXPECTED_ENTRY_POINTS = {
    "evidencemesh": "evidencemesh.cli:app",
    "evidencemesh-mcp": "evidencemesh.mcp_server:main",
}
_NETWORK_GUARD_MARKER = "EVIDENCEMESH_SMOKE_NETWORK_GUARD_MARKER"
_NETWORK_GUARD_ARMED = b"evidencemesh.python-socket-guard.armed.v1\n"
_NETWORK_GUARD_BLOCKED = b"evidencemesh.python-socket-guard.blocked.v1\n"
_NETWORK_GUARD_SOURCE = f'''\
import os
import socket

_marker = os.environ.get("{_NETWORK_GUARD_MARKER}")
if not _marker:
    raise RuntimeError("EvidenceMesh smoke socket guard marker is missing")
_descriptor = os.open(
    _marker,
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
    0o600,
)
try:
    os.write(_descriptor, {_NETWORK_GUARD_ARMED!r})
finally:
    os.close(_descriptor)

def _record_block(operation):
    descriptor = os.open(
        _marker,
        os.O_WRONLY | os.O_TRUNC | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.write(descriptor, {_NETWORK_GUARD_BLOCKED!r} + operation.encode() + b"\\n")
    finally:
        os.close(descriptor)
    raise RuntimeError("EvidenceMesh installed smoke blocked Python socket access")

def _guard_socket_method(name):
    original = getattr(socket.socket, name)
    def guarded(instance, *args, **kwargs):
        if instance.family in (socket.AF_INET, socket.AF_INET6):
            return _record_block("socket.socket." + name)
        return original(instance, *args, **kwargs)
    setattr(socket.socket, name, guarded)

for _name in ("connect", "connect_ex", "sendto", "sendmsg"):
    if hasattr(socket.socket, _name):
        _guard_socket_method(_name)

def _guard_module_function(name):
    def guarded(*_args, **_kwargs):
        return _record_block("socket." + name)
    return guarded

for _name in (
    "create_connection",
    "getaddrinfo",
    "gethostbyaddr",
    "gethostbyname",
    "gethostbyname_ex",
    "getnameinfo",
):
    if hasattr(socket, _name):
        setattr(socket, _name, _guard_module_function(_name))
'''
_BINDING_PROBE_SOURCE = """\
import json
import os
from pathlib import Path

from evidencemesh.config import Settings
from evidencemesh.governor import SQLiteBudgetGovernor

governor = SQLiteBudgetGovernor.from_env()
if governor is None:
    raise RuntimeError("RC4 governor environment was not activated")
SQLiteBudgetGovernor.require_explicit_environment_match(governor)
settings = Settings.from_env()
expected_providers = os.environ["EVIDENCEMESH_PROVIDERS"].split(",")
identity_matches = (
    governor.ledger_path == Path(os.environ["EVIDENCEMESH_CLOSED_ALPHA_LEDGER"])
    and governor.session.participant_code
    == os.environ["EVIDENCEMESH_CLOSED_ALPHA_PARTICIPANT"]
    and governor.session.session_code == os.environ["EVIDENCEMESH_CLOSED_ALPHA_SESSION"]
    and governor.session.profile == os.environ["EVIDENCEMESH_CLOSED_ALPHA_PROFILE"]
)
settings_match = (
    settings.deployment_profile.value == os.environ["EVIDENCEMESH_DEPLOYMENT_PROFILE"]
    and settings.enabled_providers == expected_providers
    and settings.searxng_fallback_urls == []
)
governor.validate_provider_configuration(
    settings.enabled_providers,
    settings.searxng_fallback_urls,
    deployment_profile=settings.deployment_profile.value,
)
print(json.dumps({
    "governor_environment_match": identity_matches,
    "settings_environment_match": settings_match,
}, sort_keys=True))
"""


@dataclass(frozen=True, slots=True)
class _SubprocessFixture:
    purpose: str
    ledger: Path
    environment: dict[str, str]
    participant_code: str
    session_code: str


@dataclass(frozen=True, slots=True)
class _ExerciseResult:
    report: dict[str, Any]
    isolation_keys: tuple[tuple[Path, str], ...]


@dataclass(frozen=True, slots=True)
class _GuardedEnvironment:
    environment: dict[str, str]
    marker: Path


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    path.chmod(0o700)
    return path


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _guarded_environment(
    fixture: _SubprocessFixture,
    *,
    purpose: str,
) -> _GuardedEnvironment:
    marker = fixture.ledger.parent / f"{purpose}.python-socket-guard"
    _require(not marker.exists(), "Python socket guard marker was reused")
    environment = dict(fixture.environment)
    environment[_NETWORK_GUARD_MARKER] = str(marker)
    return _GuardedEnvironment(environment=environment, marker=marker)


def _verify_network_guard(marker: Path) -> dict[str, Any]:
    try:
        metadata = marker.lstat()
        content = marker.read_bytes()
    except OSError as exc:
        raise RuntimeError("Python socket guard did not start") from exc
    _require(stat.S_ISREG(metadata.st_mode), "Python socket guard marker is not a file")
    _require(_mode(marker) == 0o600, "Python socket guard marker is not private")
    _require(content == _NETWORK_GUARD_ARMED, "Python socket guard observed network access")
    return {
        "implementation": "sitecustomize_python_socket_guard_v1",
        "loaded": True,
        "network_access_observed": False,
        "scope": "python_socket_api_only_not_os_network_namespace",
    }


def _run_binding_probe(
    fixture: _SubprocessFixture,
    python_command: Path,
) -> dict[str, Any]:
    guarded = _guarded_environment(fixture, purpose="binding-probe")
    completed = subprocess.run(  # noqa: S603 - exact installed interpreter is validated.
        [str(python_command), "-c", _BINDING_PROBE_SOURCE],
        cwd=fixture.ledger.parent,
        env=guarded.environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    network_guard = _verify_network_guard(guarded.marker)
    if completed.returncode != 0:
        raise RuntimeError("Installed RC4.1A environment binding probe failed")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Installed RC4.1A environment binding probe is not JSON") from exc
    _require(
        result
        == {
            "governor_environment_match": True,
            "settings_environment_match": True,
        },
        "Installed RC4.1A environment binding probe drifted",
    )
    return {**result, "network_guard": network_guard}


def _run_guarded_product(
    fixture: _SubprocessFixture,
    command: list[str],
    *,
    purpose: str,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    guarded = _guarded_environment(fixture, purpose=purpose)
    completed = subprocess.run(  # noqa: S603 - exact installed executable is validated.
        command,
        cwd=fixture.ledger.parent.parent,
        env=guarded.environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed, _verify_network_guard(guarded.marker)


def _inside_prefix(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path(sys.prefix).resolve())
    except ValueError:
        return False
    return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _participant(index: int) -> str:
    return f"p-{index:016x}"


def _session(index: int) -> str:
    return f"s-{index:032x}"


def _admit_full_cohort(control: SQLiteAlphaControlPlane) -> None:
    for index in range(1, 7):
        control.admit(
            ClosedAlphaAdmission(
                participant_code=_participant(index),
                slot_id=f"C{index:02d}",
                profile="community",
                consent_version=CONSENT_VERSION,
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
                consent_version=CONSENT_VERSION,
                consent_accepted=True,
                input_authority_attested=True,
                non_sensitive_use_attested=True,
            )
        )


def _bootstrap_subprocess_environment(
    root: Path,
    *,
    identity_index: int,
    purpose: str,
) -> _SubprocessFixture:
    if identity_index not in range(1, 7):
        raise ValueError("RC4.1A smoke subprocess identity must select a community slot")
    ledger_root = _private_directory(root)
    ledger = ledger_root / "control.sqlite3"
    guard_module = ledger_root / "sitecustomize.py"
    guard_module.write_text(_NETWORK_GUARD_SOURCE, encoding="utf-8")
    guard_module.chmod(0o600)
    control = SQLiteAlphaControlPlane.bootstrap(ledger)
    _admit_full_cohort(control)
    epoch = control.transition(
        AlphaControlState.PREPARED,
        expected_state=AlphaControlState.PAUSED,
        expected_epoch=1,
    )
    snapshot = control.snapshot()
    _require(epoch == 2, "RC4.1A smoke control epoch drifted")
    _require(snapshot["state"] == "prepared", "RC4.1A smoke control is not prepared")
    _require(snapshot["admitted_participants"] == 8, "RC4.1A smoke cohort is incomplete")
    _require(snapshot["global_attempts"] == 0, "RC4.1A smoke ledger is not empty")

    participant_code = _participant(identity_index)
    session_code = _session(identity_index)
    environment = {
        "EVIDENCEMESH_ALLOW_PRIVATE_NETWORKS": "false",
        "EVIDENCEMESH_CACHE_PATH": str(ledger_root / "cache.sqlite3"),
        "EVIDENCEMESH_CLOSED_ALPHA_CONTROL_PLANE": "rc4",
        "EVIDENCEMESH_CLOSED_ALPHA_LEDGER": str(ledger),
        "EVIDENCEMESH_CLOSED_ALPHA_PARTICIPANT": participant_code,
        "EVIDENCEMESH_CLOSED_ALPHA_PROFILE": "community",
        "EVIDENCEMESH_CLOSED_ALPHA_SESSION": session_code,
        "EVIDENCEMESH_DEPLOYMENT_PROFILE": "community",
        "EVIDENCEMESH_PROVIDERS": ",".join(COMMUNITY_PROVIDERS),
        "EVIDENCEMESH_SEARXNG_FALLBACK_URLS": "",
        "EVIDENCEMESH_TRANSPORT": "stdio",
        "FASTMCP_CHECK_FOR_UPDATES": "off",
        "FASTMCP_SHOW_SERVER_BANNER": "false",
        "HOME": str(ledger_root),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(ledger_root),
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": str(ledger_root),
    }
    return _SubprocessFixture(
        purpose=purpose,
        ledger=ledger,
        environment=environment,
        participant_code=participant_code,
        session_code=session_code,
    )


def _control_plane_receipt(fixture: _SubprocessFixture) -> dict[str, Any]:
    snapshot = SQLiteAlphaControlPlane(fixture.ledger).snapshot()
    _require(snapshot["state"] == "prepared", "RC4.1A smoke state changed")
    _require(snapshot["control_epoch"] == 2, "RC4.1A smoke epoch changed")
    _require(snapshot["admitted_participants"] == 8, "RC4.1A smoke cohort changed")
    _require(snapshot["sessions"] == 0, "RC4.1A smoke unexpectedly opened a session")
    _require(snapshot["global_attempts"] == 0, "RC4.1A smoke dispatched an attempt")
    _require(
        snapshot["recovery_required_sessions"] == 0,
        "RC4.1A smoke created a recovery session",
    )
    _require(snapshot["privacy_fault"] is False, "RC4.1A smoke tripped a privacy fault")
    _require(_mode(fixture.ledger.parent) == 0o700, "RC4.1A ledger directory is not private")
    _require(_mode(fixture.ledger) == 0o600, "RC4.1A ledger file is not private")
    return {
        "purpose": fixture.purpose,
        "schema_version": snapshot["schema_version"],
        "state": snapshot["state"],
        "control_epoch": snapshot["control_epoch"],
        "admitted_participants": snapshot["admitted_participants"],
        "sessions": snapshot["sessions"],
        "global_attempts": snapshot["global_attempts"],
        "privacy_fault": snapshot["privacy_fault"],
        "ledger_directory_mode": "0700",
        "ledger_file_mode": "0600",
    }


def _validate_health(health: dict[str, Any], *, source: str) -> list[str]:
    _require(health.get("status") == "ready", f"{source} health is not ready")
    _require(health.get("version") == PACKAGE_VERSION, f"{source} version drifted")
    _require(
        health.get("deployment_profile") == "community",
        f"{source} deployment profile drifted",
    )
    rows = health.get("providers")
    if not isinstance(rows, list):
        raise RuntimeError(f"{source} provider inventory is not a list")
    providers = [row.get("name") for row in rows if isinstance(row, dict)]
    _require(providers == COMMUNITY_PROVIDERS, f"{source} provider bundle drifted")
    reliability = health.get("reliability")
    if not isinstance(reliability, dict):
        raise RuntimeError(f"{source} reliability object is missing")
    closed_alpha = reliability.get("closed_alpha_governor")
    _require(
        closed_alpha
        == {
            "enabled": True,
            "scope": "single_host_shared_sqlite",
            "distributed_global_guarantee": False,
        },
        f"{source} governor health drifted",
    )
    safety = health.get("safety")
    if not isinstance(safety, dict):
        raise RuntimeError(f"{source} safety object is missing")
    _require(safety.get("private_networks_allowed") is False, f"{source} private-network drift")
    _require(safety.get("dns_pinning") is True, f"{source} DNS pinning is disabled")
    return [str(provider) for provider in providers]


def _exercise_cli(root: Path, command: Path) -> _ExerciseResult:
    providers_fixture = _bootstrap_subprocess_environment(
        root / "cli-providers",
        identity_index=1,
        purpose="cli-providers",
    )
    providers_probe = _run_binding_probe(providers_fixture, Path(sys.executable).absolute())
    completed, providers_guard = _run_guarded_product(
        providers_fixture,
        [str(command), "providers"],
        purpose="cli-providers-product",
    )
    if completed.returncode != 0:
        raise RuntimeError("Installed RC4.1A CLI providers command failed")
    try:
        health = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Installed RC4.1A CLI providers output is not JSON") from exc
    _require(isinstance(health, dict), "Installed RC4.1A CLI health is not an object")
    providers = _validate_health(health, source="CLI")
    providers_control = _control_plane_receipt(providers_fixture)

    refusal_fixture = _bootstrap_subprocess_environment(
        root / "cli-http-refusal",
        identity_index=2,
        purpose="cli-http-refusal",
    )
    refusal_probe = _run_binding_probe(refusal_fixture, Path(sys.executable).absolute())
    refused, refusal_guard = _run_guarded_product(
        refusal_fixture,
        [str(command), "serve", "--transport", "http"],
        purpose="cli-http-refusal-product",
    )
    _require(refused.returncode != 0, "Installed RC4.1A CLI accepted HTTP transport")
    refusal_output = " ".join(f"{refused.stdout}\n{refused.stderr}".split())
    _require(
        "closed-alpha governor supports one-session-per-process STDIO only" in refusal_output,
        "Installed RC4.1A CLI HTTP refusal reason drifted",
    )
    refusal_control = _control_plane_receipt(refusal_fixture)
    _require(
        providers_fixture.ledger != refusal_fixture.ledger,
        "CLI smoke subprocesses reused one ledger",
    )
    _require(
        providers_fixture.session_code != refusal_fixture.session_code,
        "CLI smoke subprocesses reused one session",
    )
    return _ExerciseResult(
        report={
            "command_within_prefix": _inside_prefix(command),
            "configured_providers": providers,
            "providers_command": {
                "health_status": "ready",
                "binding_probe": providers_probe,
                "network_guard": providers_guard,
                "control_plane": providers_control,
            },
            "http_transport": {
                "refused": True,
                "binding_probe": refusal_probe,
                "network_guard": refusal_guard,
                "control_plane": refusal_control,
            },
            "distinct_subprocess_ledgers": True,
            "distinct_subprocess_sessions": True,
            "provider_requests": 0,
            "model_requests": 0,
            "document_fetches": 0,
        },
        isolation_keys=(
            (providers_fixture.ledger, providers_fixture.session_code),
            (refusal_fixture.ledger, refusal_fixture.session_code),
        ),
    )


async def _exercise_mcp_async(
    root: Path,
    command: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    transport = StdioTransport(
        command=str(command),
        args=[],
        env=environment,
        keep_alive=False,
        log_file=root / "mcp.server.log",
    )
    async with Client(
        transport,
        name="EvidenceMesh installed RC4.1A verifier",
        timeout=20,
        init_timeout=20,
    ) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()
        health = await client.call_tool("health", {})
    if not isinstance(health.data, dict):
        raise TypeError("Installed RC4.1A MCP health did not return an object")
    return {
        "health": health.data,
        "tools": [tool.name for tool in tools],
        "resources": [str(resource.uri) for resource in resources],
        "prompts": [prompt.name for prompt in prompts],
    }


def _exercise_mcp(root: Path, command: Path) -> _ExerciseResult:
    fixture = _bootstrap_subprocess_environment(
        root / "mcp-health",
        identity_index=3,
        purpose="mcp-health",
    )
    binding_probe = _run_binding_probe(fixture, Path(sys.executable).absolute())
    guarded = _guarded_environment(fixture, purpose="mcp-product")
    try:
        observation = asyncio.run(_exercise_mcp_async(root, command, guarded.environment))
    finally:
        network_guard = _verify_network_guard(guarded.marker)
    health = observation.get("health")
    tools = observation.get("tools")
    resources = observation.get("resources")
    prompts = observation.get("prompts")
    if not isinstance(health, dict):
        raise RuntimeError("Installed RC4.1A MCP health is not an object")
    _require(tools == EXPECTED_TOOLS, "Installed RC4.1A MCP tool inventory drifted")
    _require(
        resources == EXPECTED_RESOURCES,
        "Installed RC4.1A MCP resource inventory drifted",
    )
    _require(prompts == EXPECTED_PROMPTS, "Installed RC4.1A MCP prompt inventory drifted")
    providers = _validate_health(health, source="MCP")
    control = _control_plane_receipt(fixture)
    return _ExerciseResult(
        report={
            "command_within_prefix": _inside_prefix(command),
            "configured_providers": providers,
            "health_status": "ready",
            "tool_inventory": tools,
            "resource_inventory": resources,
            "prompt_inventory": prompts,
            "binding_probe": binding_probe,
            "network_guard": network_guard,
            "control_plane": control,
            "provider_requests": 0,
            "model_requests": 0,
            "document_fetches": 0,
        },
        isolation_keys=((fixture.ledger, fixture.session_code),),
    )


def _validate_installation_identity(
    installed_distribution: importlib.metadata.Distribution,
    package_origin: Path,
    commands: tuple[Path, Path],
) -> dict[str, Any]:
    installed_init = Path(
        str(installed_distribution.locate_file("evidencemesh/__init__.py"))
    ).resolve()
    _require(
        installed_init.is_file() and package_origin.samefile(installed_init),
        "Imported EvidenceMesh does not belong to its installed distribution",
    )
    entry_points = {
        entry_point.name: entry_point.value
        for entry_point in installed_distribution.entry_points
        if entry_point.group == "console_scripts" and entry_point.name in EXPECTED_ENTRY_POINTS
    }
    _require(entry_points == EXPECTED_ENTRY_POINTS, "Installed console entry points drifted")
    python_command = Path(sys.executable).absolute()
    _require(
        python_command.is_file() and python_command.parent.parent == Path(sys.prefix).absolute(),
        "Smoke interpreter is outside the environment prefix",
    )
    for (name, target), command in zip(EXPECTED_ENTRY_POINTS.items(), commands, strict=True):
        expected_launcher = python_command.parent / name
        _require(
            expected_launcher.is_file() and command.samefile(expected_launcher),
            f"Installed {name} launcher is not the exact environment launcher",
        )
        launcher = command.read_text(encoding="utf-8")
        first_line = launcher.splitlines()[0]
        _require(first_line.startswith("#!"), f"Installed {name} launcher has no shebang")
        _require(
            Path(first_line[2:]).absolute() == python_command,
            f"Installed {name} launcher uses another interpreter",
        )
        module, callable_name = target.split(":", maxsplit=1)
        _require(
            f"from {module} import {callable_name}" in launcher,
            f"Installed {name} launcher target drifted",
        )
    return {
        "distribution_module_samefile": True,
        "entry_points_exact": True,
        "launchers_exact": True,
    }


def _archive_file_bytes(archive: Path, *, label: str, relative_path: str) -> bytes:
    if label == "wheel":
        with zipfile.ZipFile(archive) as bundle:
            try:
                return bundle.read(relative_path)
            except KeyError as exc:
                raise RuntimeError(f"Wheel is missing critical file {relative_path}") from exc
    with tarfile.open(archive, mode="r:gz") as bundle:
        suffix = f"/src/{relative_path}"
        members = [member for member in bundle.getmembers() if member.name.endswith(suffix)]
        _require(
            len(members) == 1 and members[0].isfile(),
            f"sdist critical file {relative_path} drifted",
        )
        extracted = bundle.extractfile(members[0])
        if extracted is None:
            raise RuntimeError(f"Cannot read sdist critical file {relative_path}")
        return extracted.read()


def _critical_package_files(
    installed_distribution: importlib.metadata.Distribution,
    archive: Path,
    *,
    label: str,
) -> dict[str, Any]:
    files = installed_distribution.files
    if files is None:
        raise RuntimeError("Installed distribution has no RECORD file inventory")
    record_files = {str(package_path): package_path for package_path in files}
    for relative_path in CRITICAL_PACKAGE_FILES:
        package_path = record_files.get(relative_path)
        if package_path is None:
            raise RuntimeError(f"RECORD is missing critical file {relative_path}")
        record_hash = package_path.hash
        if record_hash is None or record_hash.mode != "sha256":
            raise RuntimeError(f"RECORD SHA-256 is missing for {relative_path}")
        try:
            record_digest = base64.urlsafe_b64decode(
                record_hash.value + "=" * (-len(record_hash.value) % 4)
            ).hex()
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"RECORD SHA-256 is invalid for {relative_path}") from exc
        installed_path = Path(str(installed_distribution.locate_file(package_path))).resolve()
        _require(installed_path.is_file(), f"Installed critical file {relative_path} is missing")
        installed_digest = _sha256_file(installed_path)
        archive_digest = hashlib.sha256(
            _archive_file_bytes(archive, label=label, relative_path=relative_path)
        ).hexdigest()
        _require(
            installed_digest == archive_digest == record_digest,
            f"Archive, installed file and RECORD differ for {relative_path}",
        )
    return {
        "archive_record_installed_match": True,
        "critical_file_count": len(CRITICAL_PACKAGE_FILES),
    }


def _declared_pep610_sha256(archive_info: dict[str, Any]) -> tuple[str, ...]:
    declared: list[str] = []
    legacy_hash = archive_info.get("hash")
    if legacy_hash is not None:
        _require(isinstance(legacy_hash, str), "PEP 610 archive hash is not text")
        algorithm, separator, digest = legacy_hash.partition("=")
        _require(separator == "=" and algorithm == "sha256", "PEP 610 archive hash drifted")
        declared.append(digest)
    hashes = archive_info.get("hashes")
    if hashes is not None:
        _require(isinstance(hashes, dict), "PEP 610 archive hashes are not an object")
        digest = hashes.get("sha256")
        _require(isinstance(digest, str), "PEP 610 archive SHA-256 is missing")
        declared.append(digest)
    _require(
        all(re.fullmatch(r"[0-9a-f]{64}", digest) is not None for digest in declared),
        "PEP 610 archive SHA-256 shape drifted",
    )
    return tuple(declared)


def _source_archive(
    installed_distribution: importlib.metadata.Distribution,
    distribution: Path,
    *,
    label: str,
    expected_sha256: str,
) -> dict[str, Any]:
    distribution = distribution.resolve()
    _require(distribution.is_file(), "Installed source archive is missing")
    _require(
        re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
        "Independent expected archive SHA-256 is invalid",
    )
    expected_name = (
        "evidencemesh-0.1.0-py3-none-any.whl" if label == "wheel" else "evidencemesh-0.1.0.tar.gz"
    )
    _require(distribution.name == expected_name, "Installed source archive name drifted")
    direct_url_text = installed_distribution.read_text("direct_url.json")
    if direct_url_text is None:
        raise RuntimeError("Installed distribution has no PEP 610 direct_url.json")
    direct_url = json.loads(direct_url_text)
    _require(isinstance(direct_url, dict), "PEP 610 direct_url.json is not an object")
    _require(
        direct_url.get("url") == distribution.as_uri(),
        "Installed distribution PEP 610 URL differs from the tested archive",
    )
    archive_info = direct_url.get("archive_info")
    _require(isinstance(archive_info, dict), "PEP 610 direct URL is not an archive reference")
    _require(
        "dir_info" not in direct_url and "vcs_info" not in direct_url,
        "Installed distribution unexpectedly came from a directory or VCS",
    )
    digest = _sha256_file(distribution)
    _require(
        digest == expected_sha256,
        "Installed archive differs from the independent expected SHA-256",
    )
    declared_digests = _declared_pep610_sha256(archive_info)
    _require(
        all(declared == digest for declared in declared_digests),
        "PEP 610 archive SHA-256 differs from the tested archive",
    )
    pep610_status = "matched" if declared_digests else "not_declared_by_installer"
    critical_files = _critical_package_files(
        installed_distribution,
        distribution,
        label=label,
    )
    return {
        "name": distribution.name,
        "sha256": digest,
        "size_bytes": distribution.stat().st_size,
        "critical_package_files": critical_files,
        "independent_sha256_after_install_matches": True,
        "install_to_smoke_toctou_excluded": False,
        "pep610": {
            "binding_scope": ("url_and_sha256" if declared_digests else "url_only"),
            "sha256_status": pep610_status,
            "url_matches": True,
        },
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
    if label not in {"sdist", "wheel"}:
        raise ValueError("label must be wheel or sdist")
    work_root = _private_directory(work_root.resolve())
    package_file = getattr(evidencemesh, "__file__", None)
    if not isinstance(package_file, str):
        raise RuntimeError("Installed EvidenceMesh package has no origin")
    package_origin = Path(package_file).resolve()
    _require(
        _inside_prefix(package_origin),
        "EvidenceMesh was not imported from the installed environment",
    )
    resolved_commands: list[Path] = []
    for command in (cli_command, mcp_command):
        resolved = command.resolve()
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise ValueError("Installed command is missing or not executable")
        _require(_inside_prefix(resolved), "Installed command is outside the environment prefix")
        resolved_commands.append(resolved)
    installed_distribution = importlib.metadata.distribution("evidencemesh")
    package_version = installed_distribution.version
    _require(package_version == PACKAGE_VERSION, "Installed EvidenceMesh version drifted")
    installation_identity = _validate_installation_identity(
        installed_distribution,
        package_origin,
        (resolved_commands[0], resolved_commands[1]),
    )

    archive = _source_archive(
        installed_distribution,
        distribution,
        label=label,
        expected_sha256=expected_archive_sha256,
    )
    cli = _exercise_cli(work_root, resolved_commands[0])
    mcp = _exercise_mcp(work_root, resolved_commands[1])
    isolation_keys = (*cli.isolation_keys, *mcp.isolation_keys)
    ledgers = [key[0] for key in isolation_keys]
    sessions = [key[1] for key in isolation_keys]
    _require(len(set(ledgers)) == len(ledgers), "RC4.1A smoke reused a subprocess ledger")
    _require(len(set(sessions)) == len(sessions), "RC4.1A smoke reused a subprocess session")

    report: dict[str, Any] = {
        "schema_version": 1,
        "smoke": SMOKE_ID,
        "label": label,
        "installation": {
            **installation_identity,
            "package_version": package_version,
            "package_origin_within_isolated_prefix": True,
            "virtual_environment": sys.prefix != sys.base_prefix,
        },
        "source_archive": archive,
        "control_plane": {
            "implementation": "SQLiteAlphaControlPlane",
            "profile": "community",
            "admitted_slots": {"community": 6, "quality": 2},
            "prepared_before_subprocess": True,
            "fixture_count": 3,
            "binding_probe_subprocess_count": 3,
            "product_subprocess_count": 3,
            "distinct_ledgers": True,
            "distinct_sessions": True,
        },
        "cli": cli.report,
        "mcp_stdio": mcp.report,
        "traffic": {
            "provider_requests": 0,
            "tavily_requests": 0,
            "model_requests": 0,
            "document_fetches": 0,
            "retries": 0,
            "fallbacks": 0,
            "repairs": 0,
        },
        "network_guard": {
            "implementation": "sitecustomize_python_socket_guard_v1",
            "dependency_update_checks_disabled": True,
            "binding_probe_markers_verified": 3,
            "product_markers_verified": 3,
            "network_access_observed": False,
            "os_network_namespace_enforced": False,
            "scope": "python_socket_api_only_not_os_network_namespace",
        },
        "validation": {"errors": [], "passed": True},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=("wheel", "sdist"), required=True)
    parser.add_argument("--cli-command", type=Path, required=True)
    parser.add_argument("--mcp-command", type=Path, required=True)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


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
