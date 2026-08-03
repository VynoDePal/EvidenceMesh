"""Verify the A3-P0 unprivileged offline operator journey.

This driver intentionally uses only the Python standard library.  It treats
EvidenceMesh as a black-box installed command and never imports product
internals.  The calling workflow is responsible for placing the process in a
distinct network and mount namespace, switching to the unprivileged operator
UID, masking the source checkout, and tracing the complete process tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any, cast

SCHEMA_VERSION = "evidencemesh.alpha-a3-p0-operator-clean-room-receipt.v1"
PACKAGE_NAME = "evidencemesh"
DEFAULT_EXPECTED_VERSION = "0.1.0"
EXPECTED_UV_VERSION = "0.11.33"
EXPECTED_UV_TARGET = "x86_64-unknown-linux-gnu"
EXPECTED_ENTRY_POINTS = {
    "evidencemesh": "evidencemesh.cli:app",
    "evidencemesh-mcp": "evidencemesh.mcp_server:main",
}
EXPECTED_DESCRIPTOR_ENV = {
    "EVIDENCEMESH_ALLOW_NONSTANDARD_PORTS": "false",
    "EVIDENCEMESH_ALLOW_PRIVATE_NETWORKS": "false",
    "EVIDENCEMESH_DEPLOYMENT_PROFILE": "community",
    "EVIDENCEMESH_PROVIDERS": "wikipedia",
    "EVIDENCEMESH_RESPECT_ROBOTS_TXT": "true",
    "EVIDENCEMESH_TRANSPORT": "stdio",
    "FASTMCP_CHECK_FOR_UPDATES": "off",
    "FASTMCP_SHOW_SERVER_BANNER": "false",
    "PYTHONUNBUFFERED": "1",
}
DESCRIPTOR_CACHE_KEY = "EVIDENCEMESH_CACHE_PATH"
FORBIDDEN_ENV_TOKENS = (
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
    "KEY",
    "PASSWORD",
    "PROXY",
    "SECRET",
    "SESSION",
    "TOKEN",
)
FORBIDDEN_ENV_EXACT = frozenset({"SSH_AUTH_SOCK"})
OPERATOR_ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "PYTHONNOUSERSITE",
        "TMPDIR",
        "TZ",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    }
)
HANDOFF_REQUIREMENTS = "requirements.txt"
HANDOFF_MANIFEST = "SHA256SUMS"
HANDOFF_DESCRIPTOR = "evidencemesh.mcp.json"
HANDOFF_WHEELHOUSE = "wheelhouse"
HANDOFF_DRIVER = "verify_alpha_a3_p0_operator_clean_room.py"
HANDOFF_UV = "bin/uv"
TEMPLATE_COMMAND = "/absolute/path/to/EvidenceMesh/.venv/bin/evidencemesh-mcp"
TEMPLATE_CACHE = "/home/YOUR_USER/.cache/evidencemesh/cache.sqlite3"
EXPECTED_LOGICAL_MCP_REQUESTS = 4
EXPECTED_MCP_HEALTH_CALLS = 2
EXPECTED_MCP_SERVER_LAUNCHES = 2
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)(?:\s|;|$)")
HASH_OPTION = re.compile(r"--hash=sha256:([0-9a-f]{64})(?:\s|$)")
TRACE_SYSCALL = re.compile(
    r"(?:^|\s)(socketpair|socket|connect|connect_ex|bind|listen|accept4?|sendto|sendmsg|"
    r"recvfrom|recvmsg|getsockname|getpeername|shutdown)\("
)


class OperatorGateError(RuntimeError):
    """Raised when an A3-P0 fail-closed assertion does not hold."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OperatorGateError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OperatorGateError(f"{label} is not JSON") from exc
    _require(isinstance(payload, dict), f"{label} is not a JSON object")
    return cast(dict[str, Any], payload)


def _private_directory(path: Path, *, label: str, owner_uid: int) -> Path:
    _require(path.is_absolute(), f"{label} must be absolute")
    _require(path.exists() and path.is_dir(), f"{label} is missing")
    _require(not path.is_symlink(), f"{label} must not be a symlink")
    details = path.stat()
    _require(details.st_uid == owner_uid, f"{label} owner drifted")
    _require(stat.S_IMODE(details.st_mode) == 0o700, f"{label} must use mode 0700")
    return path.resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _forbidden_environment_names(environment: dict[str, str]) -> list[str]:
    return sorted(
        name
        for name in environment
        if name.upper() in FORBIDDEN_ENV_EXACT
        or any(token in name.upper() for token in FORBIDDEN_ENV_TOKENS)
    )


def _validate_environment(
    *,
    environment: dict[str, str],
    expected_uid: int,
    producer_uid: int,
    work_root: Path,
    home: Path,
    xdg_cache: Path,
    xdg_config: Path,
    xdg_data: Path,
    tmp: Path,
    cwd: Path,
) -> dict[str, int | bool]:
    _require(os.getuid() == expected_uid, "Operator UID drifted")
    _require(expected_uid != producer_uid, "Operator and producer UID must differ")
    _require(set(environment) == OPERATOR_ENV_ALLOWLIST, "Operator environment allowlist drifted")
    forbidden = _forbidden_environment_names(environment)
    _require(forbidden == [], "Operator environment contains a secret or proxy-shaped name")
    expected_paths = {
        "HOME": home,
        "XDG_CACHE_HOME": xdg_cache,
        "XDG_CONFIG_HOME": xdg_config,
        "XDG_DATA_HOME": xdg_data,
        "TMPDIR": tmp,
    }
    for name, expected in expected_paths.items():
        _require(environment.get(name) == str(expected), f"{name} does not match its private root")
    private_roots = [
        _private_directory(work_root, label="work root", owner_uid=expected_uid),
        _private_directory(home, label="HOME", owner_uid=expected_uid),
        _private_directory(xdg_cache, label="XDG cache", owner_uid=expected_uid),
        _private_directory(xdg_config, label="XDG config", owner_uid=expected_uid),
        _private_directory(xdg_data, label="XDG data", owner_uid=expected_uid),
        _private_directory(tmp, label="TMPDIR", owner_uid=expected_uid),
        _private_directory(cwd, label="operator cwd", owner_uid=expected_uid),
    ]
    _require(cwd.resolve() == work_root.resolve(), "Operator cwd must equal work root")
    _require(
        len(set(private_roots[:-1])) == len(private_roots[:-1]),
        "Private operator roots must be distinct",
    )
    return {
        "forbidden_environment_names": 0,
        "operator_uid_distinct": True,
        "private_directory_count": len(private_roots) - 1,
    }


def _namespace_identity(path: Path) -> str:
    try:
        value = os.readlink(path)
    except OSError as exc:
        raise OperatorGateError(f"Cannot inspect namespace: {path.name}") from exc
    _require(bool(value), f"Namespace identity is empty: {path.name}")
    return value


def _validate_containment(
    *,
    forbidden_workspace: Path,
    parent_net_namespace: str,
    parent_mount_namespace: str,
) -> dict[str, bool | str]:
    _require(forbidden_workspace.is_absolute(), "Forbidden workspace must be absolute")
    _require(
        not os.access(forbidden_workspace, os.R_OK | os.X_OK),
        "Operator can read or traverse the masked source workspace",
    )
    try:
        workspace_mode = stat.S_IMODE(forbidden_workspace.stat().st_mode)
    except OSError as exc:
        raise OperatorGateError("Masked workspace mode cannot be inspected") from exc
    _require(workspace_mode == 0, "Masked source workspace must use mode 0000")
    current_net = _namespace_identity(Path("/proc/self/ns/net"))
    current_mount = _namespace_identity(Path("/proc/self/ns/mnt"))
    _require(current_net != parent_net_namespace, "Network namespace was not isolated")
    _require(current_mount != parent_mount_namespace, "Mount namespace was not isolated")
    return {
        "mount_namespace_distinct": True,
        "network_namespace_distinct": True,
        "source_workspace_masked": True,
    }


def _manifest_relative_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    _require(raw == path.as_posix(), "Manifest path is not canonical POSIX")
    _require(not path.is_absolute(), "Manifest path is absolute")
    _require(path.parts != (), "Manifest path is empty")
    _require(".." not in path.parts and "." not in path.parts, "Manifest path escapes handoff")
    return path


def _parse_sha256sums(raw: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    lines = raw.splitlines()
    _require(lines != [], "SHA256SUMS is empty")
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        _require(match is not None, "SHA256SUMS row is malformed")
        digest, relative_raw = cast(re.Match[str], match).groups()
        relative = _manifest_relative_path(relative_raw).as_posix()
        _require(relative not in rows, "SHA256SUMS contains a duplicate path")
        rows[relative] = digest
    return rows


def _logical_requirements(raw: str) -> list[str]:
    logical: list[str] = []
    current = ""
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        continuation = line.endswith("\\")
        part = line[:-1].rstrip() if continuation else line
        current = f"{current} {part}".strip()
        if not continuation:
            logical.append(current)
            current = ""
    _require(current == "", "requirements.txt has an unterminated continuation")
    _require(logical != [], "requirements.txt is empty")
    return logical


def _validate_hashed_requirements(
    raw: str,
    *,
    expected_version: str,
    expected_wheel_sha256: str,
) -> dict[str, int | bool]:
    forbidden_options = (
        "--index-url",
        "--extra-index-url",
        "--find-links",
        "--trusted-host",
        "--constraint",
        "--requirement",
        "-c ",
        "-r ",
        "-e ",
        "--editable",
    )
    requirements = _logical_requirements(raw)
    package_names: list[str] = []
    evidence_hashes: tuple[str, ...] | None = None
    for row in requirements:
        lowered = row.lower()
        _require(
            not any(option in lowered for option in forbidden_options),
            "requirements.txt contains an external resolution option",
        )
        _require(" @ " not in row and "://" not in row, "requirements.txt contains a URL")
        match = REQUIREMENT_NAME.match(row)
        _require(match is not None, "Every requirement must be exactly pinned with ==")
        name, version = cast(re.Match[str], match).groups()
        normalised = name.lower().replace("_", "-")
        hashes = tuple(HASH_OPTION.findall(row))
        _require(hashes != (), f"Requirement has no SHA-256 hash: {normalised}")
        hash_tokens = re.findall(r"--hash=([^\s]+)", row)
        _require(len(hash_tokens) == len(hashes), "Requirement contains a non-SHA-256 hash")
        package_names.append(normalised)
        if normalised == PACKAGE_NAME:
            _require(version == expected_version, "EvidenceMesh requirement version drifted")
            evidence_hashes = hashes
    _require(package_names.count(PACKAGE_NAME) == 1, "EvidenceMesh requirement is not unique")
    _require(
        evidence_hashes is not None and expected_wheel_sha256 in evidence_hashes,
        "EvidenceMesh requirement is not bound to the canonical wheel",
    )
    return {
        "all_requirements_hash_pinned": True,
        "package_requirements": len(requirements),
        "project_requirement_unique": True,
    }


def _walk_handoff_files(
    root: Path, *, expected_owner_uid: int, expected_owner_gid: int
) -> dict[str, Path]:
    observed: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        _require(not path.is_symlink(), "Handoff contains a symbolic link")
        details = path.stat()
        _require(
            details.st_uid == expected_owner_uid and details.st_gid == expected_owner_gid,
            "Handoff member owner drifted",
        )
        _require(stat.S_IMODE(details.st_mode) & 0o222 == 0, "Handoff path is writable")
        if path.is_dir():
            continue
        _require(path.is_file(), "Handoff contains a non-regular path")
        _require(details.st_nlink == 1, "Handoff contains a hard-linked file")
        observed[relative] = path
    return observed


def _validate_handoff(
    root: Path,
    *,
    expected_version: str,
    expected_wheel_sha256: str,
    expected_wheel_size: int,
    expected_uv: Path,
    running_driver: Path | None = None,
    expected_owner_uid: int = 0,
    expected_owner_gid: int = 0,
) -> dict[str, Any]:
    _require(root.is_absolute(), "Handoff root must be absolute")
    _require(root.is_dir() and not root.is_symlink(), "Handoff root is missing or unsafe")
    _require(
        root.stat().st_uid == expected_owner_uid and root.stat().st_gid == expected_owner_gid,
        "Handoff root owner drifted",
    )
    _require(stat.S_IMODE(root.stat().st_mode) & 0o222 == 0, "Handoff root is writable")
    files = _walk_handoff_files(
        root,
        expected_owner_uid=expected_owner_uid,
        expected_owner_gid=expected_owner_gid,
    )
    manifest_path = root / HANDOFF_MANIFEST
    requirements_path = root / HANDOFF_REQUIREMENTS
    descriptor_path = root / HANDOFF_DESCRIPTOR
    wheelhouse = root / HANDOFF_WHEELHOUSE
    driver = root / HANDOFF_DRIVER
    uv = root / HANDOFF_UV
    _require(manifest_path.is_file(), "SHA256SUMS is missing")
    _require(requirements_path.is_file(), "requirements.txt is missing")
    _require(descriptor_path.is_file(), "MCP descriptor is missing")
    _require(driver.is_file(), "Operator driver is missing from handoff")
    _require(uv.is_file() and os.access(uv, os.X_OK), "Sealed uv executable is missing")
    _require(wheelhouse.is_dir(), "Wheelhouse is missing")
    top_level = {path.name for path in root.iterdir()}
    _require(
        top_level
        == {
            HANDOFF_DESCRIPTOR,
            HANDOFF_DRIVER,
            HANDOFF_MANIFEST,
            HANDOFF_REQUIREMENTS,
            "bin",
            HANDOFF_WHEELHOUSE,
        },
        "Handoff top-level inventory drifted",
    )
    _require({path.name for path in (root / "bin").iterdir()} == {"uv"}, "Handoff bin drifted")
    actual_driver = Path(__file__).resolve() if running_driver is None else running_driver.resolve()
    _require(actual_driver.samefile(driver), "Running driver is not the sealed handoff driver")
    _require(expected_uv.resolve().samefile(uv), "Selected uv is not the sealed handoff uv")
    wheel_paths = [path for relative, path in files.items() if relative.startswith("wheelhouse/")]
    _require(wheel_paths != [], "Wheelhouse is empty")
    _require(all(path.suffix == ".whl" for path in wheel_paths), "Wheelhouse is not wheels-only")
    _require(
        all(relative.count("/") == 1 for relative in files if relative.startswith("wheelhouse/")),
        "Wheelhouse contains a nested path",
    )
    project_names = [
        path.name.split("-", 1)[0].lower().replace("_", "-").replace(".", "-")
        for path in wheel_paths
    ]
    _require(len(project_names) == len(set(project_names)), "Wheelhouse project is duplicated")
    expected_manifest_paths = set(files) - {HANDOFF_MANIFEST}
    manifest = _parse_sha256sums(manifest_path.read_text(encoding="utf-8"))
    _require(set(manifest) == expected_manifest_paths, "SHA256SUMS inventory is not exact")
    for relative, digest in manifest.items():
        _require(_sha256_file(files[relative]) == digest, f"Handoff digest drifted: {relative}")
    project_wheels = [
        path
        for path in wheel_paths
        if path.name.lower().replace("_", "-").startswith(f"{PACKAGE_NAME}-{expected_version}-")
    ]
    _require(len(project_wheels) == 1, "Canonical EvidenceMesh wheel is not unique")
    project_wheel = project_wheels[0]
    _require(_sha256_file(project_wheel) == expected_wheel_sha256, "Canonical wheel hash drifted")
    _require(project_wheel.stat().st_size == expected_wheel_size, "Canonical wheel size drifted")
    requirements = _validate_hashed_requirements(
        requirements_path.read_text(encoding="utf-8"),
        expected_version=expected_version,
        expected_wheel_sha256=expected_wheel_sha256,
    )
    return {
        "descriptor": descriptor_path,
        "driver": driver,
        "manifest_entries": len(manifest),
        "project_wheel": project_wheel,
        "requirements": requirements_path,
        "requirements_report": requirements,
        "wheel_count": len(wheel_paths),
        "wheelhouse": wheelhouse,
    }


def _safe_runtime_environment(base: dict[str, str]) -> dict[str, str]:
    environment = dict(base)
    environment.update(
        {
            "NO_COLOR": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PIP_REQUIRE_VIRTUALENV": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "TZ": "UTC",
            "UV_HTTP_RETRIES": "0",
            "UV_NO_CACHE": "1",
            "UV_OFFLINE": "1",
        }
    )
    _require(_forbidden_environment_names(environment) == [], "Runtime environment became unsafe")
    return environment


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float,
    label: str,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 - exact commands are gate inputs.
            command,
            cwd=cwd,
            env=environment,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise OperatorGateError(f"{label} timed out") from exc
    _require(time.monotonic() - started <= timeout_seconds + 1.0, f"{label} exceeded timeout")
    if expect_success and completed.returncode != 0:
        raise OperatorGateError(f"{label} failed with exit code {completed.returncode}")
    return completed


def _validate_toolchain(
    *,
    uv: Path,
    python_base: Path,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float,
) -> dict[str, str]:
    uv_observation = _run(
        [str(uv), "--version"],
        cwd=cwd,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="sealed uv identity",
    )
    _require(
        uv_observation.stdout.strip() == f"uv {EXPECTED_UV_VERSION} ({EXPECTED_UV_TARGET})",
        "Sealed uv version drifted",
    )
    python_observation = _run(
        [
            str(python_base),
            "-I",
            "-c",
            "import json,sys; print(json.dumps(list(sys.version_info[:3])))",
        ],
        cwd=cwd,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="base Python identity",
    )
    version = json.loads(python_observation.stdout)
    _require(
        isinstance(version, list)
        and len(version) == 3
        and version[:2] == [3, 11]
        and all(isinstance(value, int) for value in version),
        "Base Python is not 3.11.x",
    )
    return {
        "python": ".".join(str(value) for value in version),
        "uv": EXPECTED_UV_VERSION,
    }


_ABSENCE_PROBE = r"""
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path

prefix = Path(os.environ["A3_PREFIX"]).resolve()
commands = [prefix / "bin" / "evidencemesh", prefix / "bin" / "evidencemesh-mcp"]
try:
    importlib.metadata.distribution("evidencemesh")
except importlib.metadata.PackageNotFoundError:
    metadata_present = False
else:
    metadata_present = True
entry_points = [
    item.name
    for item in importlib.metadata.entry_points(group="console_scripts")
    if item.name.startswith("evidencemesh")
]
print(json.dumps({
    "command_count": sum(path.exists() for path in commands),
    "entry_point_count": len(entry_points),
    "metadata_present": metadata_present,
    "module_present": importlib.util.find_spec("evidencemesh") is not None,
}))
"""


_IDENTITY_PROBE = r"""
import base64
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import sys
from io import StringIO
from pathlib import Path

prefix = Path(os.environ["A3_PREFIX"]).resolve()
expected_version = os.environ["A3_EXPECTED_VERSION"]
expected_entries = {
    "evidencemesh": "evidencemesh.cli:app",
    "evidencemesh-mcp": "evidencemesh.mcp_server:main",
}

def inside(path):
    try:
        path.resolve().relative_to(prefix)
    except ValueError:
        return False
    return True

distribution = importlib.metadata.distribution("evidencemesh")
assert distribution.version == expected_version
entries = {
    item.name: item.value
    for item in distribution.entry_points
    if item.group == "console_scripts" and item.name.startswith("evidencemesh")
}
assert entries == expected_entries
origins = {}
for module_name in ("evidencemesh", "evidencemesh.cli", "evidencemesh.mcp_server"):
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and isinstance(spec.origin, str)
    origin = Path(spec.origin).resolve()
    assert inside(origin) and origin.is_file()
    origins[module_name] = origin.name
record_text = distribution.read_text("RECORD")
assert record_text is not None
rows = list(csv.reader(StringIO(record_text)))
assert all(len(row) == 3 for row in rows)
paths = [row[0] for row in rows]
assert len(paths) == len(set(paths))
declared = distribution.files
assert declared is not None and set(paths) == {str(path) for path in declared}
hashed = 0
unhashed = 0
absolute_paths = []
for relative, digest, size in rows:
    installed = Path(distribution.locate_file(relative)).resolve()
    assert inside(installed) and installed.is_file() and not installed.is_symlink()
    absolute_paths.append(str(installed))
    if not digest:
        assert not size and relative.endswith(".dist-info/RECORD")
        unhashed += 1
        continue
    algorithm, separator, encoded = digest.partition("=")
    assert separator == "=" and algorithm == "sha256"
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", encoded)
    expected = base64.urlsafe_b64decode(encoded + "=")
    payload = installed.read_bytes()
    assert size.isdigit() and int(size) == len(payload)
    assert hashlib.sha256(payload).digest() == expected
    hashed += 1
assert hashed > 0 and unhashed == 1
for name in expected_entries:
    command = prefix / "bin" / name
    assert command.is_file() and os.access(command, os.X_OK) and inside(command)
assert sys.prefix != sys.base_prefix and Path(sys.prefix).resolve() == prefix
print(json.dumps({
    "entry_point_count": len(entries),
    "hashed_record_entries": hashed,
    "module_origin_count": len(origins),
    "record_absolute_paths": absolute_paths,
    "record_self_entries": unhashed,
    "version": distribution.version,
}))
"""


_MCP_SESSION_PROBE = r"""
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
import mcp.client.stdio as stdio_module
from mcp.types import Implementation

descriptor_path = Path(os.environ["A3_DESCRIPTOR"])
server_log = Path(os.environ["A3_SERVER_LOG"])
runtime_cwd = Path(os.environ["A3_RUNTIME_CWD"])
payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
server = payload["mcpServers"]["evidencemesh"]
private_environment_names = (
    "HOME",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "TMPDIR",
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONHASHSEED",
    "PYTHONNOUSERSITE",
)
descriptor_environment_names = {
    "EVIDENCEMESH_ALLOW_NONSTANDARD_PORTS",
    "EVIDENCEMESH_ALLOW_PRIVATE_NETWORKS",
    "EVIDENCEMESH_CACHE_PATH",
    "EVIDENCEMESH_DEPLOYMENT_PROFILE",
    "EVIDENCEMESH_PROVIDERS",
    "EVIDENCEMESH_RESPECT_ROBOTS_TXT",
    "EVIDENCEMESH_TRANSPORT",
    "FASTMCP_CHECK_FOR_UPDATES",
    "FASTMCP_SHOW_SERVER_BANNER",
    "PYTHONUNBUFFERED",
}
forbidden_environment_tokens = (
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
    "KEY",
    "PASSWORD",
    "PROXY",
    "SECRET",
    "SESSION",
    "TOKEN",
)

def build_server_environment(process_environment, descriptor_environment):
    assert isinstance(descriptor_environment, dict)
    assert set(descriptor_environment) == descriptor_environment_names
    assert all(
        isinstance(name, str) and isinstance(value, str)
        for name, value in descriptor_environment.items()
    )
    assert all(name in process_environment for name in private_environment_names)
    environment = {name: process_environment[name] for name in private_environment_names}
    environment.update(descriptor_environment)
    assert not any(name.startswith("A3_") for name in environment)
    assert "SSH_AUTH_SOCK" not in environment
    assert not any(
        token in name.upper()
        for name in environment
        for token in forbidden_environment_tokens
    )
    return environment

server_environment = build_server_environment(os.environ, server["env"])
created = []
fallback_calls = 0
original_create = stdio_module._create_platform_compatible_process

async def capture_create(*args, **kwargs):
    process = await original_create(*args, **kwargs)
    created.append(process)
    return process

async def forbid_fallback(*_args, **_kwargs):
    global fallback_calls
    fallback_calls += 1
    raise RuntimeError("MCP termination fallback was required")

stdio_module._create_platform_compatible_process = capture_create
stdio_module._terminate_process_tree = forbid_fallback

async def exercise():
    with server_log.open("w", encoding="utf-8") as errlog:
        parameters = StdioServerParameters(
            command=server["command"],
            args=server["args"],
            env=server_environment,
            cwd=runtime_cwd,
        )
        async with stdio_module.stdio_client(parameters, errlog=errlog) as streams:
            read_stream, write_stream = streams
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=10),
                client_info=Implementation(name="EvidenceMesh A3-P0 operator", version="1"),
            ) as session:
                initialization = await session.initialize()
                health_result = await session.call_tool("health", {})
                request_count = session._request_id
        return initialization, health_result, request_count

initialization, health_result, request_count = asyncio.run(asyncio.wait_for(exercise(), 30))
assert len(created) == 1
process = created[0]
pid = process.pid
children_path = Path(f"/proc/self/task/{os.getpid()}/children")
children = children_path.read_text(encoding="utf-8").split() if children_path.exists() else []
structured = health_result.structuredContent
assert isinstance(structured, dict)
print(json.dumps({
    "children_after_exit": len(children),
    "fallback_calls": fallback_calls,
    "health": structured,
    "logical_requests": request_count,
    "pid": pid,
    "pid_gone": not Path(f"/proc/{pid}").exists(),
    "protocol_version": str(initialization.protocolVersion),
    "returncode": process.returncode,
    "server_name": initialization.serverInfo.name,
    "server_version": initialization.serverInfo.version,
}))
"""


def _probe_absence(
    python: Path,
    *,
    prefix: Path,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float,
    label: str,
) -> dict[str, Any]:
    probe_environment = dict(environment)
    probe_environment["A3_PREFIX"] = str(prefix)
    observation = _run(
        [str(python), "-I", "-c", _ABSENCE_PROBE],
        cwd=cwd,
        environment=probe_environment,
        timeout_seconds=timeout_seconds,
        label=label,
    )
    payload = _json_object(observation.stdout, label)
    _require(
        payload
        == {
            "command_count": 0,
            "entry_point_count": 0,
            "metadata_present": False,
            "module_present": False,
        },
        f"{label} found EvidenceMesh",
    )
    return payload


def _validate_installed_identity(
    python: Path,
    *,
    prefix: Path,
    expected_version: str,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    probe_environment = dict(environment)
    probe_environment.update({"A3_EXPECTED_VERSION": expected_version, "A3_PREFIX": str(prefix)})
    observation = _run(
        [str(python), "-I", "-c", _IDENTITY_PROBE],
        cwd=cwd,
        environment=probe_environment,
        timeout_seconds=timeout_seconds,
        label="installed identity and RECORD probe",
    )
    payload = _json_object(observation.stdout, "installed identity probe")
    _require(payload.get("version") == expected_version, "Installed identity version drifted")
    _require(payload.get("entry_point_count") == 2, "Installed entry point count drifted")
    _require(payload.get("module_origin_count") == 3, "Installed module origin count drifted")
    _require(payload.get("record_self_entries") == 1, "Installed RECORD self row drifted")
    _require(
        isinstance(payload.get("hashed_record_entries"), int)
        and cast(int, payload["hashed_record_entries"]) > 0,
        "Installed RECORD has no verified hashed entry",
    )
    absolute_paths = payload.get("record_absolute_paths")
    _require(isinstance(absolute_paths, list) and absolute_paths, "Installed RECORD paths missing")
    _require(
        all(isinstance(path, str) and Path(path).is_absolute() for path in absolute_paths),
        "Installed RECORD path inventory is invalid",
    )
    return payload


def _require_record_paths_absent(paths: object, *, install_root: Path) -> int:
    _require(isinstance(paths, list) and paths, "Installed RECORD path inventory is absent")
    count = 0
    for raw in paths:
        _require(isinstance(raw, str), "Installed RECORD path is not a string")
        path = Path(raw)
        _require(path.is_absolute(), "Installed RECORD path is relative")
        _require(_is_within(path, install_root), "Installed RECORD path escaped install root")
        _require(not path.exists() and not path.is_symlink(), "Uninstall left a RECORD path")
        count += 1
    return count


def _validate_health(payload: dict[str, Any], *, expected_version: str) -> dict[str, Any]:
    providers = payload.get("providers")
    _require(isinstance(providers, list), "Health provider inventory is missing")
    names = [row.get("name") for row in providers if isinstance(row, dict)]
    safety = payload.get("safety")
    reliability = payload.get("reliability")
    _require(payload.get("status") == "ready", "Health is not ready")
    _require(payload.get("version") == expected_version, "Health version drifted")
    _require(payload.get("deployment_profile") == "community", "Health profile drifted")
    _require(names == ["wikipedia"], "Health provider isolation drifted")
    _require(payload.get("configuration_warnings") == [], "Health warning appeared")
    _require(isinstance(safety, dict), "Health safety inventory is missing")
    _require(safety.get("private_networks_allowed") is False, "Private networks became allowed")
    _require(safety.get("nonstandard_ports_allowed") is False, "Nonstandard ports became allowed")
    _require(safety.get("robots_txt_respected") is True, "robots.txt policy drifted")
    _require(safety.get("dns_pinning") is True, "DNS pinning is disabled")
    _require(isinstance(reliability, dict), "Health reliability inventory is missing")
    _require(
        reliability.get("closed_alpha_governor") == {"enabled": False},
        "A3-P0 unexpectedly activated a closed-alpha governor",
    )
    return {
        "configuration_warnings": 0,
        "deployment_profile": "community",
        "dns_pinning": True,
        "governor_enabled": False,
        "private_networks_allowed": False,
        "provider_count": 1,
        "status": "ready",
        "version": expected_version,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _require(not path.exists() and not path.is_symlink(), "Runtime descriptor already exists")
    temporary = path.with_name(f".{path.name}.partial")
    _require(not temporary.exists() and not temporary.is_symlink(), "Descriptor partial exists")
    descriptor_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor_fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor_fd, "wb") as handle:
            handle.write(descriptor_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        _require(stat.S_IMODE(temporary.stat().st_mode) == 0o600, "Descriptor mode drifted")
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _render_descriptor(
    template: Path,
    output: Path,
    *,
    expected_command: Path,
    expected_cache: Path,
) -> dict[str, Any]:
    payload = _json_object(template.read_text(encoding="utf-8"), "MCP descriptor template")
    _require(set(payload) == {"mcpServers"}, "Descriptor root keys drifted")
    servers = payload.get("mcpServers")
    _require(
        isinstance(servers, dict) and set(servers) == {PACKAGE_NAME}, "Descriptor server drifted"
    )
    server = servers[PACKAGE_NAME]
    _require(isinstance(server, dict), "Descriptor server is not an object")
    _require(set(server) == {"args", "command", "env"}, "Descriptor server keys drifted")
    command = server.get("command")
    _require(command == TEMPLATE_COMMAND, "Descriptor command template drifted")
    _require(
        expected_command.is_file() and os.access(expected_command, os.X_OK), "MCP launcher missing"
    )
    _require(server.get("args") == [], "Descriptor arguments drifted")
    descriptor_env = server.get("env")
    _require(isinstance(descriptor_env, dict), "Descriptor environment is missing")
    _require(
        all(
            isinstance(key, str) and isinstance(value, str) for key, value in descriptor_env.items()
        ),
        "Descriptor environment is not string-valued",
    )
    expected_template = {**EXPECTED_DESCRIPTOR_ENV, DESCRIPTOR_CACHE_KEY: TEMPLATE_CACHE}
    _require(descriptor_env == expected_template, "Descriptor environment template drifted")
    _require(
        _forbidden_environment_names(cast(dict[str, str], descriptor_env)) == [],
        "Descriptor leaks secret names",
    )
    _require(expected_cache.is_absolute(), "Descriptor cache path is relative")
    server["command"] = str(expected_command.resolve())
    descriptor_env[DESCRIPTOR_CACHE_KEY] = str(expected_cache.resolve())
    _atomic_json(output, payload)
    _require(output.is_file() and not output.is_symlink(), "Runtime descriptor is missing")
    _require(stat.S_IMODE(output.stat().st_mode) == 0o600, "Runtime descriptor mode drifted")
    rendered = _json_object(output.read_text(encoding="utf-8"), "Runtime MCP descriptor")
    expected_rendered = json.loads(json.dumps(payload))
    _require(rendered == expected_rendered, "Runtime descriptor bytes drifted")
    return {
        "environment_keys": len(descriptor_env),
        "mode": "0600",
        "template_fields_modified": 2,
        "validated": True,
    }


def _validate_mcp_session(
    payload: dict[str, Any],
    *,
    expected_version: str,
) -> dict[str, Any]:
    _require(payload.get("fallback_calls") == 0, "MCP termination fallback was used")
    _require(payload.get("logical_requests") == 2, "MCP request count drifted")
    _require(payload.get("returncode") == 0, "MCP server did not exit cleanly")
    _require(payload.get("pid_gone") is True, "MCP server PID survived shutdown")
    _require(payload.get("children_after_exit") == 0, "MCP client retained an orphan child")
    _require(payload.get("server_name") == "EvidenceMesh", "MCP server name drifted")
    _require(payload.get("server_version") == expected_version, "MCP server version drifted")
    _require(isinstance(payload.get("protocol_version"), str), "MCP protocol is missing")
    health = payload.get("health")
    _require(isinstance(health, dict), "MCP health is missing")
    validated_health = _validate_health(
        cast(dict[str, Any], health), expected_version=expected_version
    )
    pid = payload.get("pid")
    _require(isinstance(pid, int) and pid > 1, "MCP server PID is invalid")
    return {
        "health": validated_health,
        "logical_requests": 2,
        "natural_exit": True,
        "orphan_processes": 0,
        "pid": pid,
        "protocol_version": payload["protocol_version"],
    }


def _stderr_errors(value: str) -> list[str]:
    lower = value.lower()
    markers = ("traceback (most recent call last):", "exceptiongroup", "unhandled exception")
    errors = [marker for marker in markers if marker in lower]
    if re.search(r"(?im)^(?:\[[^\r\n]*\]\s+)?(?:error|critical)\b", value):
        errors.append("error_or_critical_line")
    return errors


def _run_mcp_session(
    python: Path,
    *,
    descriptor: Path,
    server_log: Path,
    runtime_cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float,
    expected_version: str,
    label: str,
) -> dict[str, Any]:
    probe_environment = dict(environment)
    probe_environment.update(
        {
            "A3_DESCRIPTOR": str(descriptor),
            "A3_RUNTIME_CWD": str(runtime_cwd),
            "A3_SERVER_LOG": str(server_log),
        }
    )
    observation = _run(
        [str(python), "-I", "-c", _MCP_SESSION_PROBE],
        cwd=runtime_cwd,
        environment=probe_environment,
        timeout_seconds=timeout_seconds,
        label=label,
    )
    _require(observation.stderr == "", f"{label} client wrote stderr")
    _require(server_log.is_file(), f"{label} server log is missing")
    server_stderr = server_log.read_text(encoding="utf-8")
    _require(len(server_stderr.encode("utf-8")) <= 16_384, f"{label} server log is too large")
    _require(_stderr_errors(server_stderr) == [], f"{label} server log contains an error")
    payload = _json_object(observation.stdout, label)
    return _validate_mcp_session(payload, expected_version=expected_version)


def _sqlite_receipt(path: Path, *, owner_uid: int) -> dict[str, int | bool | str]:
    _require(path.is_file() and not path.is_symlink(), "Operator cache database is missing")
    details = path.stat()
    _require(details.st_uid == owner_uid, "Operator cache owner drifted")
    _require(stat.S_IMODE(details.st_mode) == 0o600, "Operator cache must use mode 0600")
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as database:
            integrity_rows = database.execute("PRAGMA integrity_check").fetchall()
            table_count = int(
                database.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                ).fetchone()[0]
            )
    except sqlite3.Error as exc:
        raise OperatorGateError("Operator cache is not a readable SQLite database") from exc
    _require(integrity_rows == [("ok",)], "Operator cache integrity check failed")
    _require(table_count > 0, "Operator cache has no schema")
    return {
        "integrity": "ok",
        "mode_private": True,
        "sha256": _sha256_file(path),
        "table_count": table_count,
    }


def _parse_child_pids(raw: str) -> tuple[int, ...]:
    values: list[int] = []
    for token in raw.split():
        _require(token.isdigit() and int(token) > 1, "Child PID inventory is malformed")
        values.append(int(token))
    _require(len(values) == len(set(values)), "Child PID inventory contains duplicates")
    return tuple(values)


def _require_no_orphans(raw: str) -> None:
    _require(_parse_child_pids(raw) == (), "Operator driver retained a child process")


def _validate_network_trace(raw: str) -> dict[str, int | bool]:
    """Accept only explicitly local AF_UNIX IPC in a strace network trace."""

    local_calls = 0
    traced_calls = 0
    for line in raw.splitlines():
        match = TRACE_SYSCALL.search(line)
        if match is None:
            continue
        traced_calls += 1
        syscall = match.group(1)
        _require("AF_INET" not in line and "AF_INET6" not in line, "Internet socket observed")
        _require("sockaddr_in" not in line, "Internet socket address observed")
        if syscall in {"socket", "socketpair"}:
            _require("AF_UNIX" in line or "AF_LOCAL" in line, "Non-local socket observed")
        else:
            _require("AF_UNIX" in line or "AF_LOCAL" in line, "Non-local network syscall observed")
        local_calls += 1
    return {
        "external_network_calls": 0,
        "local_ipc_calls": local_calls,
        "trace_network_syscalls": traced_calls,
        "validated": True,
    }


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    _require(path.is_absolute(), "Receipt path must be absolute")
    _require(path.parent.is_dir(), "Receipt parent is missing")
    _require(not path.exists(), "Receipt path already exists")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def run_gate(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    expected_sha = args.expected_wheel_sha256.lower()
    _require(SHA256_HEX.fullmatch(expected_sha) is not None, "Expected wheel SHA-256 is invalid")
    _require(args.expected_wheel_size > 0, "Expected wheel size is invalid")
    _require(args.timeout_seconds > 0, "Timeout must be positive")
    operator_uid = args.expected_operator_uid
    previous_umask = os.umask(0o077)
    try:
        paths = {
            name: Path(getattr(args, name)).absolute()
            for name in (
                "handoff_root",
                "home",
                "xdg_cache",
                "xdg_config",
                "xdg_data",
                "tmp",
                "work_root",
                "state_root",
                "install_root",
                "forbidden_workspace",
                "receipt",
            )
        }
        cwd = Path.cwd().resolve()
        environment_report = _validate_environment(
            environment=dict(os.environ),
            expected_uid=operator_uid,
            producer_uid=args.producer_uid,
            work_root=paths["work_root"],
            home=paths["home"],
            xdg_cache=paths["xdg_cache"],
            xdg_config=paths["xdg_config"],
            xdg_data=paths["xdg_data"],
            tmp=paths["tmp"],
            cwd=cwd,
        )
        containment = _validate_containment(
            forbidden_workspace=paths["forbidden_workspace"],
            parent_net_namespace=args.parent_net_namespace,
            parent_mount_namespace=args.parent_mount_namespace,
        )
        _require(
            _is_within(paths["state_root"], paths["work_root"]), "State root escaped work root"
        )
        _require(
            _is_within(paths["install_root"], paths["work_root"]), "Install root escaped work root"
        )
        distinct_runtime_paths = [
            paths[name].resolve()
            for name in (
                "work_root",
                "home",
                "xdg_cache",
                "xdg_config",
                "xdg_data",
                "tmp",
                "state_root",
                "install_root",
            )
        ]
        _require(
            len(set(distinct_runtime_paths)) == len(distinct_runtime_paths),
            "Operator runtime paths must be distinct",
        )
        _require(not paths["state_root"].exists(), "State root must not pre-exist")
        _require(not paths["install_root"].exists(), "Install root must not pre-exist")
        paths["state_root"].mkdir(mode=0o700)
        logs = paths["work_root"] / "logs"
        logs.mkdir(mode=0o700)
        uv = Path(args.uv).resolve()
        python_base = Path(args.python_base).resolve()
        _require(uv.is_file() and os.access(uv, os.X_OK), "uv executable is unavailable")
        _require(
            python_base.is_file() and os.access(python_base, os.X_OK),
            "Base Python executable is unavailable",
        )
        handoff = _validate_handoff(
            paths["handoff_root"],
            expected_version=args.expected_version,
            expected_wheel_sha256=expected_sha,
            expected_wheel_size=args.expected_wheel_size,
            expected_uv=uv,
        )
        runtime_environment = _safe_runtime_environment(dict(os.environ))
        toolchain = _validate_toolchain(
            uv=uv,
            python_base=python_base,
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
        )
        command_count = 2

        _run(
            [
                str(uv),
                "venv",
                "--offline",
                "--no-config",
                "--no-python-downloads",
                "--python",
                str(python_base),
                str(paths["install_root"]),
            ],
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            label="offline empty virtual environment creation",
        )
        command_count += 1
        installed_python = paths["install_root"] / "bin" / "python"
        cli_command = paths["install_root"] / "bin" / "evidencemesh"
        mcp_command = paths["install_root"] / "bin" / "evidencemesh-mcp"
        _require(installed_python.is_file(), "Virtual environment Python is missing")
        preinstall = _probe_absence(
            installed_python,
            prefix=paths["install_root"],
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            label="pre-install absence probe",
        )
        command_count += 1

        install_command = [
            str(uv),
            "pip",
            "install",
            "--python",
            str(installed_python),
            "--require-hashes",
            "--offline",
            "--no-index",
            "--find-links",
            str(handoff["wheelhouse"]),
            "--no-cache",
            "--no-config",
            "-r",
            str(handoff["requirements"]),
        ]
        _require(
            "--no-deps" not in install_command, "Operator installation must resolve dependencies"
        )
        _run(
            install_command,
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            label="complete offline hashed installation",
        )
        command_count += 1
        _run(
            [
                str(uv),
                "pip",
                "check",
                "--python",
                str(installed_python),
                "--offline",
                "--no-config",
            ],
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            label="offline installed dependency check",
        )
        command_count += 1
        installation_identity = _validate_installed_identity(
            installed_python,
            prefix=paths["install_root"],
            expected_version=args.expected_version,
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
        )
        command_count += 1

        cache = paths["state_root"] / "cache.sqlite3"
        _require(not cache.exists() and not cache.is_symlink(), "Operator cache must not pre-exist")
        product_environment = dict(runtime_environment)
        product_environment.update(EXPECTED_DESCRIPTOR_ENV)
        product_environment[DESCRIPTOR_CACHE_KEY] = str(cache)
        providers_observation = _run(
            [str(cli_command), "providers"],
            cwd=cwd,
            environment=product_environment,
            timeout_seconds=args.timeout_seconds,
            label="installed CLI providers health",
        )
        command_count += 1
        cli_health = _validate_health(
            _json_object(providers_observation.stdout, "CLI providers health"),
            expected_version=args.expected_version,
        )
        _sqlite_receipt(cache, owner_uid=operator_uid)

        descriptor = paths["work_root"] / HANDOFF_DESCRIPTOR
        descriptor_report = _render_descriptor(
            cast(Path, handoff["descriptor"]),
            descriptor,
            expected_command=mcp_command,
            expected_cache=cache,
        )
        first_session = _run_mcp_session(
            installed_python,
            descriptor=descriptor,
            server_log=logs / "mcp-first.stderr.log",
            runtime_cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            expected_version=args.expected_version,
            label="first planned MCP health session",
        )
        command_count += 1
        _sqlite_receipt(cache, owner_uid=operator_uid)
        second_session = _run_mcp_session(
            installed_python,
            descriptor=descriptor,
            server_log=logs / "mcp-second.stderr.log",
            runtime_cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            expected_version=args.expected_version,
            label="second planned MCP restartability session",
        )
        command_count += 1
        second_cache = _sqlite_receipt(cache, owner_uid=operator_uid)
        _require(first_session["pid"] != second_session["pid"], "MCP sessions reused a PID")
        state_digest_before_uninstall = cast(str, second_cache["sha256"])
        record_absolute_paths = installation_identity.pop("record_absolute_paths")

        _run(
            [
                str(uv),
                "pip",
                "uninstall",
                "--python",
                str(installed_python),
                "--offline",
                "--no-cache",
                "--no-config",
                PACKAGE_NAME,
            ],
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            label="single offline EvidenceMesh uninstall",
        )
        command_count += 1
        _run(
            [
                str(uv),
                "pip",
                "check",
                "--python",
                str(installed_python),
                "--offline",
                "--no-config",
            ],
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            label="offline post-uninstall dependency check",
        )
        command_count += 1
        post_uninstall = _probe_absence(
            installed_python,
            prefix=paths["install_root"],
            cwd=cwd,
            environment=runtime_environment,
            timeout_seconds=args.timeout_seconds,
            label="post-uninstall fresh-process absence probe",
        )
        command_count += 1
        removed_record_paths = _require_record_paths_absent(
            record_absolute_paths,
            install_root=paths["install_root"],
        )
        state_after_uninstall = _sqlite_receipt(cache, owner_uid=operator_uid)
        _require(
            state_after_uninstall["sha256"] == state_digest_before_uninstall,
            "Uninstall mutated operator state",
        )
        children_path = Path(f"/proc/self/task/{os.getpid()}/children")
        children_raw = children_path.read_text(encoding="utf-8") if children_path.exists() else ""
        _require_no_orphans(children_raw)

        elapsed = time.monotonic() - started
        receipt: dict[str, Any] = {
            "budgets": {
                "cli_invocations": 1,
                "cli_health_invocations": 1,
                "driver_subprocess_invocations": command_count,
                "health_tool_calls": EXPECTED_MCP_HEALTH_CALLS,
                "installations": 1,
                "logical_mcp_requests": EXPECTED_LOGICAL_MCP_REQUESTS,
                "mcp_server_launches": EXPECTED_MCP_SERVER_LAUNCHES,
                "retries": 0,
                "uninstallations": 1,
            },
            "claim": {
                "a2_operator_recovery": False,
                "crash_recovery": False,
                "human_operator_validated": False,
                "public_distribution_available": False,
                "recovery": False,
                "restartability": True,
                "scope": "scripted_unprivileged_local_wheel_operator_journey",
            },
            "containment": {**containment, **environment_report},
            "descriptor": descriptor_report,
            "handoff": {
                "canonical_wheel_sha256": expected_sha,
                "canonical_wheel_size": args.expected_wheel_size,
                "manifest_entries": handoff["manifest_entries"],
                "owner_root": True,
                "read_only": True,
                "requirements": handoff["requirements_report"],
                "wheel_count": handoff["wheel_count"],
                "wheels_only": True,
            },
            "installation": {
                "complete_dependency_resolution": True,
                "identity": installation_identity,
                "no_deps_used": False,
                "offline": True,
                "pip_checks_passed": 2,
                "preinstall_absence": preinstall,
                "require_hashes": True,
                "source_imports_allowed": False,
            },
            "operator_checks": {
                "cli_health": cli_health,
                "first_mcp_session": {
                    key: value for key, value in first_session.items() if key != "pid"
                },
                "second_mcp_session": {
                    key: value for key, value in second_session.items() if key != "pid"
                },
                "sessions_used_distinct_processes": True,
                "state_sqlite_integrity": "ok",
            },
            "schema_version": SCHEMA_VERSION,
            "timing": {"elapsed_seconds": round(elapsed, 3)},
            "toolchain": toolchain,
            "trace_boundary": {
                "authoritative_validator": "outer_workflow_after_driver_exit",
                "driver_validates_process_tree_trace": False,
            },
            "traffic": {
                "dns_requests": 0,
                "external_document_requests": 0,
                "external_model_requests": 0,
                "external_network_requests": 0,
                "provider_requests": 0,
                "search_requests": 0,
            },
            "uninstall": {
                "fresh_process_absence": post_uninstall,
                "record_paths_absent": removed_record_paths,
                "state_preserved": True,
                "state_sha256": state_after_uninstall["sha256"],
            },
            "validation": {"errors": [], "passed": True},
        }
        _write_receipt(paths["receipt"], receipt)
        return receipt
    finally:
        os.umask(previous_umask)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--python-base", type=Path, required=True)
    parser.add_argument("--handoff-root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--xdg-cache", type=Path, required=True)
    parser.add_argument("--xdg-config", type=Path, required=True)
    parser.add_argument("--xdg-data", type=Path, required=True)
    parser.add_argument("--tmp", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--forbidden-workspace", type=Path, required=True)
    parser.add_argument("--expected-wheel-sha256", required=True)
    parser.add_argument("--expected-wheel-size", type=int, required=True)
    parser.add_argument("--expected-operator-uid", type=int, required=True)
    parser.add_argument("--producer-uid", type=int, required=True)
    parser.add_argument("--parent-net-namespace", required=True)
    parser.add_argument("--parent-mount-namespace", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-version", default=DEFAULT_EXPECTED_VERSION)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    run_gate(args)


if __name__ == "__main__":
    main()
