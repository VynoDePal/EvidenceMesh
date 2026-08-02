"""Verify the Alpha A1-P2 named-host developer-client interoperability gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import stat
import string
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

PREREQUISITE_COMMIT = "b967114a177eec00a7ff5f03bcf1169e04b2faac"
PREREQUISITE_TREE = "7477a10c89ae158a5f5ca197799b50088335d4d8"
SOURCE_COMMIT = "145f5f923825ffeaeb485bd680bc79410ab290d1"
SOURCE_TREE = "3b36c2d3970a5e3c325a2b20260daabf23d33a29"
BRANCH = "agent/evidencemesh-v0.1"
EXPECTED_VERSION = "0.1.0"
EXPECTED_NODE_VERSION = "22.20.0"
EXPECTED_NPM_VERSION = "10.9.3"
EXPECTED_INSPECTOR_VERSION = "2.0.0"
EXPECTED_INSPECTOR_INTEGRITY = (
    "sha512-uEoeEG7/+ZbrvccPF3EsgbfjcyJ3bWVJXT4pcZtpmDUhA0zdK4T4Tuj2oUphi2Huwl66"
    "LqVdo3Mx2PkS2SUHXA=="
)
EXPECTED_PACKAGE_SHA256 = "ec21ceac22f4897d454ffbf1cce610cafaf68fcfd700340300151fea68642071"
EXPECTED_LOCK_SHA256 = "b8c2d8cd2a8f16fcfd28dc7aedc3aae8e5baa6bf5bac508ee7b22bbd4343a33e"
EXPECTED_LOCK_PACKAGE_COUNT = 241
EXPECTED_INSTALL_SCRIPT_PACKAGES = {
    "node_modules/@modelcontextprotocol/inspector",
    "node_modules/fsevents",
}
EXPECTED_INSPECTOR_FILES = {
    "package.json": "d6be3029cd7b300575c4d54950dbcf372813055d9e14a555f5226a11ea6862d4",
    "clients/launcher/build/index.js": (
        "c114e7c78afcfa01523232ae9639c3e49919952db6b8901ec7c0f49267ce0c23"
    ),
    "clients/launcher/build/parse-launcher-argv.js": (
        "a417cf4d755b2c5ed3d08fa2ce0b7488fbfcbeb856794437990dd55c64139b73"
    ),
    "clients/cli/build/index.js": (
        "bce0edfa3a72dca4d3b1f81771172ded2e1294128539c353a51e11f05871a4b6"
    ),
}
EXPECTED_INSPECTOR_BIN = {"mcp-inspector": "./clients/launcher/build/index.js"}
HARNESS_RELATIVE_PATH = Path("alpha/a1-p2-inspector")
DESCRIPTOR_RELATIVE_PATH = Path("examples/evidencemesh.mcp.json")
DESCRIPTOR_TEMPLATE_SHA256 = "81f631f82166f70d81712d7e9ab82cdb3dc20b8ba592d65ba59473faf5b4295e"
COMMAND_PLACEHOLDER = "/absolute/path/to/EvidenceMesh/.venv/bin/evidencemesh-mcp"
CACHE_PLACEHOLDER = "/home/YOUR_USER/.cache/evidencemesh/cache.sqlite3"
EXPECTED_CHANGED_PATHS = {
    ".github/workflows/ci.yml",
    "README.md",
    "alpha/a1-p2-inspector/package-lock.json",
    "alpha/a1-p2-inspector/package.json",
    "alpha/alpha_a1_p2_named_host_policy_v1.json",
    "docs/alpha-a1-p2-named-host-interoperability-gate-v1.md",
    "scripts/verify_alpha_a1_p2_named_host.py",
    "tests/test_alpha_a1_p2_named_host.py",
}
EXPECTED_P0_CHECKS = {
    "cli_health": True,
    "installed_package": True,
    "mcp_stdio_health": True,
    "network_guard_clear": True,
    "offline_benchmark": True,
    "source_remained_clean": True,
}
EXPECTED_REQUEST_METHODS = [
    "initialize",
    "logging/setLevel",
    "tools/list",
    "tools/call",
]
NAMED_HOST = "evidencemesh"
MAXIMUM_ADDITIONAL_SECONDS = 90
HOST_TIMEOUT_SECONDS = 30
PROCESS_TERMINATION_GRACE_SECONDS = 2
LOGICAL_MCP_REQUESTS_MAXIMUM = 12
MAXIMUM_STDERR_BYTES = 16_384
SERVER_OVERRIDE_KEYS = {
    "EVIDENCEMESH_A1_P2_PYTHON_GUARD_ARMED_LOG",
    "EVIDENCEMESH_A1_P2_PYTHON_NETWORK_LOG",
    "EVIDENCEMESH_A1_P2_REQUEST_TRACE",
    "LANG",
    "LC_ALL",
    "PYTHONNOUSERSITE",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONPATH",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
}


class GateError(RuntimeError):
    """Raised when an A1-P2 fail-closed assertion does not hold."""


@dataclass(frozen=True)
class CommandObservation:
    stdout: str
    stderr: str
    elapsed_seconds: float


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remaining_seconds(started_at: float) -> float:
    remaining = MAXIMUM_ADDITIONAL_SECONDS - (time.monotonic() - started_at)
    if remaining <= 0:
        raise GateError("Alpha A1-P2 exceeded its 90-second additional budget")
    return remaining


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    started_at: float,
    label: str,
    timeout_seconds: float | None = None,
) -> CommandObservation:
    before = time.monotonic()
    try:
        timeout = _remaining_seconds(started_at)
        if timeout_seconds is not None:
            timeout = min(timeout, timeout_seconds)
        process = subprocess.Popen(  # noqa: S603 - exact executables are resolved first.
            argv,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=PROCESS_TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=PROCESS_TERMINATION_GRACE_SECONDS)
        raise GateError(f"{label} exceeded the remaining additional budget") from exc
    elapsed = time.monotonic() - before
    if process.returncode != 0:
        diagnostic = stderr[-4000:].strip()
        raise GateError(f"{label} failed with exit {process.returncode}: {diagnostic}")
    return CommandObservation(stdout, stderr, elapsed)


def _resolve_executable(value: str, label: str) -> Path:
    candidate = Path(value)
    resolved = (
        candidate.expanduser().resolve()
        if candidate.parent != Path(".")
        else Path(shutil.which(value) or "")
    )
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise GateError(f"{label} is not an executable file: {value}")
    return resolved


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label} is not valid UTF-8 JSON") from exc
    _require(isinstance(payload, dict), f"{label} is not a JSON object")
    return cast(dict[str, Any], payload)


def _json_stdout(value: str, label: str) -> dict[str, Any]:
    lines = [line for line in value.splitlines() if line.strip()]
    _require(len(lines) == 1, f"{label} did not emit exactly one JSON line")
    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise GateError(f"{label} did not emit valid JSON") from exc
    _require(isinstance(payload, dict), f"{label} did not emit a JSON object")
    return cast(dict[str, Any], payload)


def _mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(message)
    return cast(dict[str, Any], value)


def _validate_full_sha(value: str, label: str) -> None:
    _require(
        len(value) == 40 and all(character in string.hexdigits for character in value),
        f"{label} is not a full commit SHA",
    )


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": os.devnull,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
    }


def _validate_p0_receipt(payload: dict[str, Any]) -> str:
    _require(
        payload.get("schema_version") == "evidencemesh.alpha-a1-p0-installability-receipt.v1",
        "A1-P0 receipt schema drifted",
    )
    _require(payload.get("validation") == {"errors": [], "passed": True}, "A1-P0 did not pass")
    candidate = _mapping(payload.get("candidate"), "A1-P0 candidate receipt is missing")
    _require(candidate.get("branch") == BRANCH, "A1-P0 branch drifted")
    _require(candidate.get("commit_sha") == SOURCE_COMMIT, "A1-P0 product commit drifted")
    _require(candidate.get("tree_sha") == SOURCE_TREE, "A1-P0 product tree drifted")
    branch_head_value = candidate.get("branch_head_observed")
    _require(isinstance(branch_head_value, str), "A1-P0 public branch head is missing")
    branch_head = str(branch_head_value)
    _validate_full_sha(branch_head, "A1-P0 public branch head")
    installation = _mapping(payload.get("installation"), "A1-P0 installation is missing")
    _require(installation.get("attempts") == 1, "A1-P0 install attempt count drifted")
    _require(installation.get("retries") == 0, "A1-P0 retried installation")
    _require(installation.get("editable") is False, "A1-P0 installation became editable")
    _require(installation.get("version") == EXPECTED_VERSION, "A1-P0 version drifted")
    checks = _mapping(payload.get("checks"), "A1-P0 checks receipt is missing")
    _require(checks == EXPECTED_P0_CHECKS, "A1-P0 checks drifted")
    _require(
        payload.get("runtime_traffic")
        == {
            "document_requests": 0,
            "model_requests": 0,
            "provider_requests": 0,
            "python_socket_network_attempts": 0,
        },
        "A1-P0 runtime traffic drifted",
    )
    environment = _mapping(payload.get("environment"), "A1-P0 environment is missing")
    _require(
        environment.get("architecture") in {"x86_64", "amd64"},
        "A1-P0 architecture drifted",
    )
    _require(
        str(environment.get("operating_system", "")).startswith("Ubuntu 24.04"),
        "A1-P0 operating system drifted",
    )
    _require(
        str(environment.get("python_version", "")).startswith("3.11."),
        "A1-P0 Python version drifted",
    )
    _require(environment.get("readonly_home") is True, "A1-P0 HOME was not read-only")
    _require(
        environment.get("runtime_state_explicit") is True,
        "A1-P0 runtime state was implicit",
    )
    return branch_head


def _validate_platform() -> dict[str, str]:
    os_release: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            os_release[key] = value.strip().strip('"')
    machine = platform.machine()
    _require(platform.system() == "Linux", "Canonical A1-P2 requires Linux")
    _require(os_release.get("ID") == "ubuntu", "Canonical A1-P2 requires Ubuntu")
    _require(
        os_release.get("VERSION_ID") == "24.04",
        "Canonical A1-P2 requires Ubuntu 24.04",
    )
    _require(machine in {"x86_64", "amd64"}, "Canonical A1-P2 requires x86_64")
    return {
        "architecture": machine,
        "operating_system": os_release.get("PRETTY_NAME", "Ubuntu 24.04"),
    }


def _validate_public_head(
    *,
    source: Path,
    branch_head: str,
    expected_head: str,
    repository_root: Path,
    git_executable: Path,
    started_at: float,
) -> None:
    _validate_full_sha(expected_head, "Triggering PR head")
    _require(branch_head == expected_head, "Public clone head differs from triggering PR head")
    env = _git_environment()
    prerequisite_tree = _run(
        [str(git_executable), "rev-parse", f"{PREREQUISITE_COMMIT}^{{tree}}"],
        cwd=source,
        env=env,
        started_at=started_at,
        label="A1-P1 prerequisite tree",
    ).stdout.strip()
    _require(prerequisite_tree == PREREQUISITE_TREE, "A1-P1 prerequisite tree drifted")
    _run(
        [str(git_executable), "merge-base", "--is-ancestor", PREREQUISITE_COMMIT, branch_head],
        cwd=source,
        env=env,
        started_at=started_at,
        label="A1-P1 prerequisite ancestry",
    )
    changed = set(
        filter(
            None,
            _run(
                [
                    str(git_executable),
                    "diff",
                    "--name-only",
                    PREREQUISITE_COMMIT,
                    branch_head,
                    "--",
                ],
                cwd=source,
                env=env,
                started_at=started_at,
                label="A1-P2 public change scope",
            ).stdout.splitlines(),
        )
    )
    _require(changed == EXPECTED_CHANGED_PATHS, "A1-P2 public change scope drifted")
    for relative in sorted(EXPECTED_CHANGED_PATHS):
        local_path = repository_root / relative
        _require(local_path.is_file(), f"A1-P2 workflow file is missing: {relative}")
        public_bytes = _run(
            [str(git_executable), "show", f"{branch_head}:{relative}"],
            cwd=source,
            env=env,
            started_at=started_at,
            label=f"public A1-P2 file {relative}",
        ).stdout.encode()
        _require(
            public_bytes == local_path.read_bytes(),
            f"Workflow and public A1-P2 file differ: {relative}",
        )


def _expected_package_json() -> dict[str, Any]:
    return {
        "name": "evidencemesh-a1-p2-inspector",
        "version": "0.0.0",
        "private": True,
        "description": "Pinned MCP Inspector harness for the EvidenceMesh Alpha A1-P2 gate.",
        "engines": {"node": EXPECTED_NODE_VERSION, "npm": EXPECTED_NPM_VERSION},
        "dependencies": {"@modelcontextprotocol/inspector": EXPECTED_INSPECTOR_VERSION},
        "overrides": {"ink-select-input": "6.2.0"},
    }


def _validate_harness_files(package_path: Path, lock_path: Path) -> dict[str, Any]:
    package_bytes = package_path.read_bytes()
    lock_bytes = lock_path.read_bytes()
    _require(
        _sha256_bytes(package_bytes) == EXPECTED_PACKAGE_SHA256,
        "Inspector package manifest hash drifted",
    )
    _require(_sha256_bytes(lock_bytes) == EXPECTED_LOCK_SHA256, "Inspector lock hash drifted")
    package = _json_object(package_path, "Inspector package manifest")
    _require(package == _expected_package_json(), "Inspector package manifest drifted")
    lock = _json_object(lock_path, "Inspector package lock")
    _require(lock.get("lockfileVersion") == 3, "Inspector lockfile version drifted")
    _require(lock.get("requires") is True, "Inspector lock requires flag drifted")
    packages = _mapping(lock.get("packages"), "Inspector lock package inventory is missing")
    _require(len(packages) == EXPECTED_LOCK_PACKAGE_COUNT, "Inspector lock package count drifted")
    root = _mapping(packages.get(""), "Inspector lock root is missing")
    _require(
        root.get("dependencies") == {"@modelcontextprotocol/inspector": EXPECTED_INSPECTOR_VERSION},
        "Inspector lock root dependency drifted",
    )
    _require(
        root.get("engines") == {"node": EXPECTED_NODE_VERSION, "npm": EXPECTED_NPM_VERSION},
        "Inspector lock root engines drifted",
    )
    install_scripts: set[str] = set()
    for relative, raw_entry in packages.items():
        _require(isinstance(relative, str), "Inspector lock contains a non-string package path")
        entry = _mapping(raw_entry, f"Inspector lock entry is malformed: {relative}")
        if not relative:
            continue
        resolved = entry.get("resolved")
        integrity = entry.get("integrity")
        _require(
            isinstance(resolved, str)
            and resolved.startswith("https://registry.npmjs.org/")
            and "@" not in resolved.split("registry.npmjs.org/", maxsplit=1)[0],
            f"Inspector lock resolved URL is not the public HTTPS registry: {relative}",
        )
        _require(
            isinstance(integrity, str) and integrity.startswith("sha512-"),
            f"Inspector lock integrity is not SHA-512: {relative}",
        )
        if entry.get("hasInstallScript") is True:
            install_scripts.add(relative)
    _require(
        install_scripts == EXPECTED_INSTALL_SCRIPT_PACKAGES,
        "Inspector install-script inventory drifted",
    )
    inspector = _mapping(
        packages.get("node_modules/@modelcontextprotocol/inspector"),
        "Inspector lock entry is missing",
    )
    _require(inspector.get("version") == EXPECTED_INSPECTOR_VERSION, "Inspector version drifted")
    _require(
        inspector.get("integrity") == EXPECTED_INSPECTOR_INTEGRITY,
        "Inspector registry integrity drifted",
    )
    _require(
        inspector.get("engines") == {"node": ">=22.19.0"},
        "Inspector engine floor drifted",
    )
    return {
        "install_script_packages": sorted(install_scripts),
        "lock_package_count": len(packages),
        "lock_sha256": _sha256_bytes(lock_bytes),
        "package_sha256": _sha256_bytes(package_bytes),
    }


PYTHON_NETWORK_GUARD = '''"""Guard Python network and MCP requests before dispatch."""
import atexit
import json
import os
import socket

from mcp.server.lowlevel.server import Server
from mcp.server.session import ServerSession


armed = os.environ.get("EVIDENCEMESH_A1_P2_PYTHON_GUARD_ARMED_LOG")
network_marker = os.environ.get("EVIDENCEMESH_A1_P2_PYTHON_NETWORK_LOG")
request_trace = os.environ.get("EVIDENCEMESH_A1_P2_REQUEST_TRACE")
if not armed or not network_marker or not request_trace:
    raise RuntimeError("Alpha A1-P2 Python guard markers are missing")
with open(armed, "a", encoding="utf-8") as handle:
    handle.write(f"{os.getpid()}\\n")


def _append(event):
    with open(request_trace, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\\n")
        handle.flush()
        os.fsync(handle.fileno())


_append({"event": "server_start", "pid": os.getpid()})


def _deny(operation, target=None):
    with open(network_marker, "a", encoding="utf-8") as handle:
        handle.write(f"{operation}:{target!r}\\n")
    raise OSError("Alpha A1-P2 Python network is disabled")


def _connect(_socket, address):
    return _deny("socket.connect", address)


def _connect_ex(_socket, address):
    return _deny("socket.connect_ex", address)


def _sendto(_socket, data, *args):
    return _deny("socket.sendto", args[-1] if args else None)


def _create_connection(address, *args, **kwargs):
    return _deny("socket.create_connection", address)


def _getaddrinfo(host, port, *args, **kwargs):
    return _deny("socket.getaddrinfo", (host, port))


def _gethostbyname(host):
    return _deny("socket.gethostbyname", host)


def _gethostbyname_ex(host):
    return _deny("socket.gethostbyname_ex", host)


def _getnameinfo(sockaddr, flags):
    return _deny("socket.getnameinfo", sockaddr)


socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.socket.sendto = _sendto
socket.create_connection = _create_connection
socket.getaddrinfo = _getaddrinfo
socket.gethostbyname = _gethostbyname
socket.gethostbyname_ex = _gethostbyname_ex
socket.getnameinfo = _getnameinfo


expected = ["initialize", "logging/setLevel", "tools/list", "tools/call"]
observed = []
initialized = False
original_handle_message = Server._handle_message
original_received_request = ServerSession._received_request


def _root(message):
    request = getattr(message, "request", None)
    request_root = getattr(request, "root", None)
    if request_root is not None:
        return request_root, True
    notification_root = getattr(message, "root", None)
    if notification_root is not None:
        return notification_root, False
    return None, False


def _params(root):
    value = getattr(root, "params", None)
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return value


async def _guarded_received_request(self, responder):
    root = getattr(getattr(responder, "request", None), "root", None)
    method = getattr(root, "method", None) if root is not None else None
    if method == "initialize":
        if observed:
            _append({"event": "denied", "method": method})
            raise RuntimeError("Duplicate MCP initialize request before dispatch")
        observed.append(method)
        _append({"event": "request", "method": method})
    return await original_received_request(self, responder)


async def _guarded_handle_message(self, message, *args, **kwargs):
    global initialized
    root, is_request = _root(message)
    method = getattr(root, "method", None) if root is not None else None
    if is_request:
        index = len(observed)
        if index >= len(expected) or method != expected[index]:
            _append({"event": "denied", "method": method})
            raise RuntimeError(f"Unexpected MCP request before dispatch: {method!r}")
        params = _params(root)
        if method == "logging/setLevel" and params != {"level": "debug"}:
            _append({"event": "denied", "method": method, "reason": "params"})
            raise RuntimeError("Inspector logging level drifted")
        if method == "tools/list" and params != {}:
            _append({"event": "denied", "method": method, "reason": "params"})
            raise RuntimeError("Inspector tools/list parameters drifted")
        if method == "tools/call":
            if not isinstance(params, dict):
                raise RuntimeError("Inspector tools/call parameters are malformed")
            if params.get("name") != "health" or params.get("arguments") != {}:
                _append({"event": "denied", "method": method, "reason": "tool"})
                raise RuntimeError("Inspector invoked a tool other than health")
            if set(params) - {"name", "arguments", "_meta"}:
                raise RuntimeError("Inspector tools/call parameters drifted")
        observed.append(method)
        _append({"event": "request", "method": method})
    elif method is not None:
        if method != "notifications/initialized" or initialized:
            _append({"event": "denied", "method": method})
            raise RuntimeError(f"Unexpected MCP notification before dispatch: {method!r}")
        initialized = True
        _append({"event": "notification", "method": method})
    return await original_handle_message(self, message, *args, **kwargs)


if getattr(Server._handle_message, "_evidencemesh_a1_p2_guard", False):
    raise RuntimeError("Alpha A1-P2 request guard was installed twice")
if getattr(ServerSession._received_request, "_evidencemesh_a1_p2_guard", False):
    raise RuntimeError("Alpha A1-P2 initialization guard was installed twice")
_guarded_handle_message._evidencemesh_a1_p2_guard = True
_guarded_received_request._evidencemesh_a1_p2_guard = True
Server._handle_message = _guarded_handle_message
ServerSession._received_request = _guarded_received_request


def _at_exit():
    _append(
        {
            "event": "server_exit",
            "request_sequence_complete": observed == expected and initialized,
        }
    )


atexit.register(_at_exit)
'''


NODE_NETWORK_GUARD = r""""use strict";
const fs = require("node:fs");
const armed = process.env.EVIDENCEMESH_A1_P2_NODE_GUARD_ARMED_LOG;
const blocked = process.env.EVIDENCEMESH_A1_P2_NODE_NETWORK_LOG;
if (!armed || !blocked) {
  throw new Error("Alpha A1-P2 Node network guard markers are missing");
}
fs.appendFileSync(armed, `${process.pid}\n`, {encoding: "utf8"});
function deny(operation, target) {
  fs.appendFileSync(blocked, `${operation}:${String(target)}\n`, {encoding: "utf8"});
  throw new Error("Alpha A1-P2 Node network is disabled");
}
const net = require("node:net");
net.Socket.prototype.connect = function (...args) { return deny("net.Socket.connect", args[0]); };
net.connect = function (...args) { return deny("net.connect", args[0]); };
net.createConnection = function (...args) { return deny("net.createConnection", args[0]); };
const tls = require("node:tls");
tls.connect = function (...args) { return deny("tls.connect", args[0]); };
const http = require("node:http");
http.request = function (...args) { return deny("http.request", args[0]); };
http.get = function (...args) { return deny("http.get", args[0]); };
const https = require("node:https");
https.request = function (...args) { return deny("https.request", args[0]); };
https.get = function (...args) { return deny("https.get", args[0]); };
const dns = require("node:dns");
for (const name of ["lookup", "resolve", "resolve4", "resolve6", "reverse"]) {
  dns[name] = function (...args) { return deny(`dns.${name}`, args[0]); };
}
const dgram = require("node:dgram");
dgram.Socket.prototype.send = function (...args) { return deny("dgram.send", args.at(-1)); };
globalThis.fetch = async function (...args) { return deny("fetch", args[0]); };
"""


def _private_file(path: Path, content: str = "") -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def _server_environment_arguments(overrides: list[str]) -> list[str]:
    _require(bool(overrides), "Inspector server environment overrides are empty")
    keys: set[str] = set()
    arguments: list[str] = []
    for entry in overrides:
        key, separator, value = entry.partition("=")
        _require(
            bool(separator)
            and bool(key)
            and bool(value)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is not None
            and "\x00" not in value
            and "\n" not in value
            and "\r" not in value,
            f"Malformed Inspector server environment override: {entry!r}",
        )
        _require(key not in keys, f"Duplicate Inspector server environment override: {key}")
        keys.add(key)
        arguments.extend(["-e", entry])
    return arguments


def _instantiate_descriptor(
    template: Path,
    output: Path,
    command: Path,
    cache: Path,
) -> bytes:
    template_bytes = template.read_bytes()
    _require(
        _sha256_bytes(template_bytes) == DESCRIPTOR_TEMPLATE_SHA256,
        "A1-P1 descriptor template drifted",
    )
    payload = _json_object(template, "A1-P1 descriptor template")
    try:
        server = payload["mcpServers"][NAMED_HOST]
        _require(server["command"] == COMMAND_PLACEHOLDER, "Command placeholder drifted")
        _require(server["args"] == [], "Descriptor arguments drifted")
        _require(
            server["env"]["EVIDENCEMESH_CACHE_PATH"] == CACHE_PLACEHOLDER,
            "Cache placeholder drifted",
        )
        server["command"] = str(command.resolve())
        server["env"]["EVIDENCEMESH_CACHE_PATH"] = str(cache.resolve())
    except (KeyError, TypeError) as exc:
        raise GateError("A1-P1 descriptor template shape drifted") from exc
    _require(
        template_bytes.count(COMMAND_PLACEHOLDER.encode()) == 1,
        "Command placeholder occurrence count drifted",
    )
    _require(
        template_bytes.count(CACHE_PLACEHOLDER.encode()) == 1,
        "Cache placeholder occurrence count drifted",
    )
    raw = template_bytes.replace(COMMAND_PLACEHOLDER.encode(), str(command.resolve()).encode())
    raw = raw.replace(CACHE_PLACEHOLDER.encode(), str(cache.resolve()).encode())
    try:
        instantiated = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError("Two-substitution runtime descriptor is invalid") from exc
    _require(instantiated == payload, "Runtime descriptor changed beyond two substitutions")
    output.write_bytes(raw)
    output.chmod(0o600)
    return raw


def _acquisition_environment(root: Path, node: Path) -> tuple[dict[str, str], Path]:
    home = root / "acquisition-home"
    home.mkdir(mode=0o700)
    cache = root / "npm-cache"
    cache.mkdir(mode=0o700)
    env = {
        "HOME": str(home.resolve()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LOGNAME": "evidencemesh-a1-p2-acquisition",
        "NPM_CONFIG_AUDIT": "false",
        "NPM_CONFIG_CACHE": str(cache.resolve()),
        "NPM_CONFIG_ENGINE_STRICT": "true",
        "NPM_CONFIG_FETCH_RETRIES": "0",
        "NPM_CONFIG_FUND": "false",
        "NPM_CONFIG_IGNORE_SCRIPTS": "true",
        "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org/",
        "NPM_CONFIG_STRICT_SSL": "true",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        "NPM_CONFIG_USERCONFIG": os.devnull,
        "PATH": f"{node.parent}:{os.defpath}",
        "SHELL": "/bin/sh",
        "USER": "evidencemesh-a1-p2-acquisition",
        "XDG_CACHE_HOME": str((home / ".cache").resolve()),
        "XDG_CONFIG_HOME": str((home / ".config").resolve()),
    }
    return env, cache


def _prepare_runtime(
    root: Path,
    *,
    node: Path,
    installed_python: Path,
    server_command: Path,
    descriptor_template: Path,
) -> dict[str, Any]:
    state = root / "state"
    state.mkdir(mode=0o700)
    home = root / "readonly-home"
    home.mkdir(mode=0o555)
    guards = root / "guards"
    guards.mkdir(mode=0o700)
    python_guard = guards / "sitecustomize.py"
    node_guard = guards / "node-network-guard.cjs"
    _private_file(python_guard, PYTHON_NETWORK_GUARD)
    _private_file(node_guard, NODE_NETWORK_GUARD)
    paths = {
        "node_armed": root / "node-network-guard-armed.log",
        "node_network": root / "node-blocked-network-attempts.log",
        "python_armed": root / "python-network-guard-armed.log",
        "python_network": root / "python-blocked-network-attempts.log",
        "request_trace": root / "mcp-request-trace.jsonl",
    }
    for path in paths.values():
        _private_file(path)
    cache_path = state / "cache.sqlite3"
    _private_file(cache_path)
    _require(stat.S_IMODE(cache_path.stat().st_mode) == 0o600, "Cache preflight mode drifted")
    descriptor = root / "evidencemesh.inspector.json"
    descriptor_bytes = _instantiate_descriptor(
        descriptor_template,
        descriptor,
        server_command,
        cache_path,
    )
    server_environment = [
        f"PYTHONPATH={guards.resolve()}",
        f"EVIDENCEMESH_A1_P2_PYTHON_GUARD_ARMED_LOG={paths['python_armed']}",
        f"EVIDENCEMESH_A1_P2_PYTHON_NETWORK_LOG={paths['python_network']}",
        f"EVIDENCEMESH_A1_P2_REQUEST_TRACE={paths['request_trace']}",
        "PYTHONNOUSERSITE=1",
        "PYTHONDONTWRITEBYTECODE=1",
        f"XDG_CACHE_HOME={(home / '.cache').resolve()}",
        f"XDG_CONFIG_HOME={(home / '.config').resolve()}",
        f"XDG_DATA_HOME={(home / '.local/share').resolve()}",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
    ]
    _require(
        {entry.partition("=")[0] for entry in server_environment} == SERVER_OVERRIDE_KEYS,
        "Server override keys drifted",
    )
    runtime_env = {
        "EVIDENCEMESH_A1_P2_NODE_GUARD_ARMED_LOG": str(paths["node_armed"]),
        "EVIDENCEMESH_A1_P2_NODE_NETWORK_LOG": str(paths["node_network"]),
        "EVIDENCEMESH_A1_P2_PYTHON_GUARD_ARMED_LOG": str(paths["python_armed"]),
        "EVIDENCEMESH_A1_P2_PYTHON_NETWORK_LOG": str(paths["python_network"]),
        "EVIDENCEMESH_A1_P2_REQUEST_TRACE": str(paths["request_trace"]),
        "HOME": str(home.resolve()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LOGNAME": "evidencemesh-a1-p2",
        "NODE_OPTIONS": f"--require={node_guard.resolve()}",
        "NO_COLOR": "1",
        "PATH": f"{node.parent}:{installed_python.parent}:{os.defpath}",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(guards.resolve()),
        "SHELL": "/bin/sh",
        "TERM": "dumb",
        "USER": "evidencemesh-a1-p2",
        "XDG_CACHE_HOME": str((home / ".cache").resolve()),
        "XDG_CONFIG_HOME": str((home / ".config").resolve()),
        "XDG_DATA_HOME": str((home / ".local/share").resolve()),
    }
    return {
        "cache_path": cache_path,
        "descriptor": descriptor,
        "descriptor_bytes": descriptor_bytes,
        "environment": runtime_env,
        "home": home,
        "paths": paths,
        "state": state,
        "server_environment": server_environment,
    }


def _validate_installed_inspector(harness: Path) -> tuple[Path, dict[str, str]]:
    root = harness / "node_modules" / "@modelcontextprotocol" / "inspector"
    _require(root.is_dir(), "Pinned Inspector installation is missing")
    observed: dict[str, str] = {}
    for relative, expected_hash in EXPECTED_INSPECTOR_FILES.items():
        path = root / relative
        _require(path.is_file(), f"Installed Inspector file is missing: {relative}")
        observed_hash = _sha256_file(path)
        _require(observed_hash == expected_hash, f"Installed Inspector file drifted: {relative}")
        observed[relative] = observed_hash
    manifest = _json_object(root / "package.json", "Installed Inspector manifest")
    _require(manifest.get("version") == EXPECTED_INSPECTOR_VERSION, "Installed Inspector drifted")
    _require(
        manifest.get("bin") == EXPECTED_INSPECTOR_BIN,
        "Installed Inspector launcher drifted",
    )
    return root / "clients" / "launcher" / "build" / "index.js", observed


def _trace_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GateError(f"MCP request trace line {index} is malformed") from exc
        _require(isinstance(event, dict), f"MCP request trace line {index} is not an object")
        events.append(cast(dict[str, Any], event))
    return events


def _validate_request_trace(path: Path) -> dict[str, Any]:
    events = _trace_events(path)
    denied = [event for event in events if event.get("event") == "denied"]
    _require(not denied, "STDIO request guard denied an MCP message")
    methods = [str(event.get("method")) for event in events if event.get("event") == "request"]
    _require(methods == EXPECTED_REQUEST_METHODS, "Inspector MCP request sequence drifted")
    _require(len(methods) <= LOGICAL_MCP_REQUESTS_MAXIMUM, "Inspector exceeded MCP request budget")
    launches = [event for event in events if event.get("event") == "server_start"]
    exits = [event for event in events if event.get("event") == "server_exit"]
    _require(len(launches) == 1, "EvidenceMesh server launch count drifted")
    _require(len(exits) == 1, "EvidenceMesh server exit was not observed")
    _require(
        exits[0].get("request_sequence_complete") is True,
        "EvidenceMesh request sequence was incomplete at exit",
    )
    server_pid = launches[0].get("pid")
    _require(isinstance(server_pid, int) and server_pid > 1, "EvidenceMesh server PID is invalid")
    notifications = [
        event.get("method") for event in events if event.get("event") == "notification"
    ]
    _require(
        notifications == ["notifications/initialized"],
        "Inspector MCP notification sequence drifted",
    )
    return {
        "logical_requests": len(methods),
        "methods": methods,
        "notifications": notifications,
        "server_pid": server_pid,
        "server_launches": len(launches),
        "sessions": 1,
    }


_EXECVE = re.compile(r'\bexecve\("([^"]+)"')


def _validate_strace(path: Path, allowed_execs: set[Path]) -> dict[str, Any]:
    _require(path.is_file() and path.stat().st_size > 0, "strace audit is missing")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    forbidden_network_lines = [
        line
        for line in lines
        if any(family in line for family in ("AF_INET", "AF_INET6", "AF_PACKET"))
    ]
    _require(not forbidden_network_lines, "strace observed a non-local network syscall")
    exec_paths = [
        Path(match.group(1)).resolve() for line in lines if (match := _EXECVE.search(line))
    ]
    _require(bool(exec_paths), "strace did not record the Inspector process tree")
    unexpected = {path for path in exec_paths if path not in allowed_execs}
    _require(
        not unexpected, f"strace observed an unexpected executable: {sorted(map(str, unexpected))}"
    )
    return {
        "execve_count": len(exec_paths),
        "forbidden_network_syscalls": 0,
        "process_audit_lines": len(lines),
    }


def _require_processes_gone(pids: set[int]) -> None:
    _require(bool(pids), "No runtime process identity was recorded")
    surviving = sorted(pid for pid in pids if Path(f"/proc/{pid}").exists())
    _require(not surviving, f"A1-P2 left a runtime process alive: {surviving}")


def _validate_health(result: dict[str, Any]) -> dict[str, Any]:
    _require(result.get("isError") is False, "Inspector health call returned an MCP error")
    structured = result.get("structuredContent")
    _require(isinstance(structured, dict), "Inspector health structured content is missing")
    content = result.get("content")
    _require(isinstance(content, list) and len(content) == 1, "Health content count drifted")
    content_items = cast(list[Any], content)
    item = content_items[0]
    _require(
        isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str),
        "Health text content is malformed",
    )
    item_mapping = cast(dict[str, Any], item)
    try:
        text_payload = json.loads(str(item_mapping["text"]))
    except json.JSONDecodeError as exc:
        raise GateError("Health text content is not JSON") from exc
    _require(text_payload == structured, "Health text and structured content differ")
    health = cast(dict[str, Any], structured)
    providers = health.get("providers")
    _require(isinstance(providers, list) and len(providers) == 1, "Health providers drifted")
    provider_rows = cast(list[Any], providers)
    provider = provider_rows[0]
    _require(isinstance(provider, dict), "Health provider row is malformed")
    provider_mapping = cast(dict[str, Any], provider)
    safety = _mapping(health.get("safety"), "Health safety inventory is missing")
    _require(health.get("status") == "ready", "Health status is not ready")
    _require(health.get("version") == EXPECTED_VERSION, "Health version drifted")
    _require(health.get("deployment_profile") == "community", "Health profile drifted")
    _require(provider_mapping.get("name") == "wikipedia", "Health provider isolation drifted")
    _require(health.get("configuration_warnings") == [], "Health warnings are not empty")
    _require(safety.get("private_networks_allowed") is False, "Private networks became allowed")
    _require(safety.get("dns_pinning") is True, "DNS pinning is disabled")
    return {
        "configuration_warnings": [],
        "deployment_profile": "community",
        "dns_pinning": True,
        "private_networks_allowed": False,
        "providers": ["wikipedia"],
        "status": "ready",
        "version": EXPECTED_VERSION,
    }


def _validate_inspector_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    _require(set(payload) == {"result"}, "Inspector JSON envelope drifted")
    result = payload.get("result")
    _require(isinstance(result, dict), "Inspector JSON envelope result is missing")
    return cast(dict[str, Any], result)


def _stderr_error_markers(value: str) -> list[str]:
    markers: list[str] = []
    lowered = value.lower()
    if "traceback (most recent call last):" in lowered:
        markers.append("PYTHON_TRACEBACK")
    if re.search(r"(?im)^.*\b(?:error|critical)\b.*$", value):
        markers.append("ERROR_OR_CRITICAL_LINE")
    if re.search(r"unhandled\s*promise\s*rejection", value, re.IGNORECASE):
        markers.append("UNHANDLED_REJECTION")
    if re.search(r"unhandled\s+exception", value, re.IGNORECASE):
        markers.append("UNHANDLED_EXCEPTION")
    return markers


def run_gate(
    *,
    work_root: Path,
    p0_receipt: Path,
    expected_head: str,
    output: Path,
    git_executable: Path,
    node_executable: Path,
    npm_executable: Path,
    strace_executable: Path,
) -> dict[str, Any]:
    started_at = time.monotonic()
    platform_report = _validate_platform()
    _require(work_root.is_dir(), "A1-P0 work root is missing")
    _require(
        p0_receipt.resolve() == (work_root / "runtime" / "receipt.json").resolve(),
        "P0 receipt path drifted",
    )
    p0_payload = _json_object(p0_receipt, "A1-P0 receipt")
    branch_head = _validate_p0_receipt(p0_payload)
    source = work_root / "source"
    _require(source.is_dir(), "A1-P0 source clone is missing")
    repository_root = Path(__file__).resolve().parents[1]
    _validate_public_head(
        source=source,
        branch_head=branch_head,
        expected_head=expected_head,
        repository_root=repository_root,
        git_executable=git_executable,
        started_at=started_at,
    )

    p2_root = work_root / "p2-runtime"
    _require(not p2_root.exists(), "A1-P2 runtime root must not already exist")
    p2_root.mkdir(mode=0o700)
    initial_source_status = _run(
        [str(git_executable), "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="pre-journey candidate status",
    ).stdout
    _require(initial_source_status == "", "A1-P0 candidate source is not clean")

    node_version = _run(
        [str(node_executable), "--version"],
        cwd=p2_root,
        env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": os.defpath},
        started_at=started_at,
        label="Node version probe",
    ).stdout.strip()
    _require(node_version == f"v{EXPECTED_NODE_VERSION}", "Canonical Node version drifted")
    npm_version = _run(
        [str(npm_executable), "--version"],
        cwd=p2_root,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": f"{node_executable.parent}:{os.defpath}",
        },
        started_at=started_at,
        label="npm version probe",
    ).stdout.strip()
    _require(npm_version == EXPECTED_NPM_VERSION, "Canonical npm version drifted")

    public_harness = repository_root / HARNESS_RELATIVE_PATH
    package_path = public_harness / "package.json"
    lock_path = public_harness / "package-lock.json"
    supply_chain = _validate_harness_files(package_path, lock_path)
    harness = p2_root / "inspector-harness"
    harness.mkdir(mode=0o700)
    runtime_package = harness / "package.json"
    runtime_lock = harness / "package-lock.json"
    shutil.copyfile(package_path, runtime_package)
    shutil.copyfile(lock_path, runtime_lock)
    runtime_package.chmod(0o600)
    runtime_lock.chmod(0o600)
    package_snapshot = runtime_package.read_bytes()
    lock_snapshot = runtime_lock.read_bytes()
    acquisition_env, npm_cache = _acquisition_environment(p2_root, node_executable)
    install = _run(
        [
            str(npm_executable),
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--fetch-retries=0",
        ],
        cwd=harness,
        env=acquisition_env,
        started_at=started_at,
        label="pinned Inspector installation",
    )
    _require(runtime_package.read_bytes() == package_snapshot, "npm changed package.json")
    _require(runtime_lock.read_bytes() == lock_snapshot, "npm changed package-lock.json")
    launcher, inspector_file_hashes = _validate_installed_inspector(harness)
    npm_ls = _run(
        [str(npm_executable), "ls", "--all", "--json"],
        cwd=harness,
        env=acquisition_env,
        started_at=started_at,
        label="installed Inspector dependency tree",
    )
    try:
        npm_tree = json.loads(npm_ls.stdout)
    except json.JSONDecodeError as exc:
        raise GateError("npm ls did not emit valid JSON") from exc
    _require(isinstance(npm_tree, dict), "npm ls did not emit an object")
    _require(not npm_tree.get("problems"), "npm ls reported an invalid dependency tree")
    npm_dependencies = _mapping(npm_tree.get("dependencies"), "npm ls root is missing")
    installed_inspector = _mapping(
        npm_dependencies.get("@modelcontextprotocol/inspector"),
        "npm ls Inspector dependency is missing",
    )
    _require(
        installed_inspector.get("version") == EXPECTED_INSPECTOR_VERSION,
        "npm ls Inspector version drifted",
    )
    shutil.rmtree(npm_cache)
    _require(not npm_cache.exists(), "npm acquisition cache survived into runtime")

    installed_python = source / ".venv" / "bin" / "python"
    server_command = source / ".venv" / "bin" / "evidencemesh-mcp"
    _require(
        installed_python.is_file() and os.access(installed_python, os.X_OK),
        "P0 installed Python is missing",
    )
    _require(
        server_command.is_file() and os.access(server_command, os.X_OK),
        "P0 installed MCP command is missing",
    )
    runtime = _prepare_runtime(
        p2_root,
        node=node_executable,
        installed_python=installed_python,
        server_command=server_command,
        descriptor_template=repository_root / DESCRIPTOR_RELATIVE_PATH,
    )
    descriptor = cast(Path, runtime["descriptor"])
    descriptor_bytes = cast(bytes, runtime["descriptor_bytes"])
    runtime_env = cast(dict[str, str], runtime["environment"])
    runtime_paths = cast(dict[str, Path], runtime["paths"])
    state = cast(Path, runtime["state"])
    server_environment = cast(list[str], runtime["server_environment"])
    server_override_args = _server_environment_arguments(server_environment)
    strace_log = p2_root / "inspector.strace.log"
    inspector = _run(
        [
            str(strace_executable),
            "-f",
            "-qq",
            "-e",
            "trace=process,network",
            "-o",
            str(strace_log),
            str(node_executable),
            str(launcher),
            "--cli",
            "--config",
            str(descriptor),
            "--server",
            NAMED_HOST,
            *server_override_args,
            "--method",
            "tools/call",
            "--tool-name",
            "health",
            "--tool-args-json",
            "{}",
            "--format",
            "json",
            "--connect-timeout",
            "10000",
        ],
        cwd=state,
        env=runtime_env,
        started_at=started_at,
        label="MCP Inspector named-host journey",
        timeout_seconds=HOST_TIMEOUT_SECONDS,
    )
    _require(
        len(inspector.stderr.encode()) <= MAXIMUM_STDERR_BYTES,
        "Inspector stderr exceeded its bound",
    )
    _require(
        not _stderr_error_markers(inspector.stderr),
        "Inspector emitted an error marker on stderr",
    )
    inspector_payload = _json_stdout(inspector.stdout, "MCP Inspector")
    health = _validate_health(_validate_inspector_envelope(inspector_payload))
    request_report = _validate_request_trace(runtime_paths["request_trace"])
    allowed_execs = {
        node_executable.resolve(),
        installed_python.resolve(),
        server_command.resolve(),
    }
    strace_report = _validate_strace(strace_log, allowed_execs)

    _require(descriptor.read_bytes() == descriptor_bytes, "Runtime descriptor changed")
    _require(stat.S_IMODE(descriptor.stat().st_mode) == 0o600, "Descriptor mode drifted")
    for key in ("node_network", "python_network"):
        _require(runtime_paths[key].stat().st_size == 0, f"{key} recorded a network attempt")
    node_guard_pids = {
        int(value) for value in runtime_paths["node_armed"].read_text(encoding="utf-8").splitlines()
    }
    python_guard_pids = {
        int(value)
        for value in runtime_paths["python_armed"].read_text(encoding="utf-8").splitlines()
    }
    _require(len(node_guard_pids) == 1, "Node network guard arming count drifted")
    _require(len(python_guard_pids) == 1, "Python network guard arming count drifted")
    _require_processes_gone(
        node_guard_pids | python_guard_pids | {cast(int, request_report["server_pid"])}
    )
    readonly_home = cast(Path, runtime["home"])
    _require(list(readonly_home.iterdir()) == [], "A1-P2 wrote inside read-only HOME")
    _require(stat.S_IMODE(readonly_home.stat().st_mode) == 0o555, "Read-only HOME mode drifted")
    cache_path = cast(Path, runtime["cache_path"])
    _require(cache_path.is_file(), "EvidenceMesh cache was not created in explicit state")
    _require(stat.S_IMODE(cache_path.stat().st_mode) == 0o600, "EvidenceMesh cache mode drifted")
    _require(set(state.iterdir()) == {cache_path}, "A1-P2 runtime state inventory drifted")

    final_source_status = _run(
        [str(git_executable), "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="post-journey candidate status",
    ).stdout
    _require(final_source_status == "", "A1-P2 modified the candidate source")
    elapsed_seconds = time.monotonic() - started_at
    _require(elapsed_seconds <= MAXIMUM_ADDITIONAL_SECONDS, "A1-P2 exceeded its budget")

    report: dict[str, Any] = {
        "schema_version": "evidencemesh.alpha-a1-p2-named-host-gate-receipt.v1",
        "prerequisite": {
            "branch": BRANCH,
            "branch_head_observed": branch_head,
            "commit_sha": PREREQUISITE_COMMIT,
            "p0_receipt_passed": True,
            "tree_sha": PREREQUISITE_TREE,
            "trigger_head_exact": True,
        },
        "candidate": {
            "commit_sha": SOURCE_COMMIT,
            "tree_sha": SOURCE_TREE,
            "version": EXPECTED_VERSION,
        },
        "client": {
            "claim_scope": "developer_client_cli_only",
            "distribution": "@modelcontextprotocol/inspector",
            "named_host": NAMED_HOST,
            "node_version": EXPECTED_NODE_VERSION,
            "npm_version": EXPECTED_NPM_VERSION,
            "version": EXPECTED_INSPECTOR_VERSION,
        },
        "supply_chain": {
            **supply_chain,
            "dependency_acquisition_network_required": True,
            "inspector_integrity": EXPECTED_INSPECTOR_INTEGRITY,
            "installed_file_sha256": inspector_file_hashes,
            "install_scripts_executed": False,
            "registry": "https://registry.npmjs.org/",
        },
        "configuration": {
            "adapter_required": False,
            "descriptor_bytes": len(descriptor_bytes),
            "descriptor_immutable": True,
            "descriptor_mode": "0600",
            "descriptor_sha256": _sha256_bytes(descriptor_bytes),
            "descriptor_substitutions": ["command", "EVIDENCEMESH_CACHE_PATH"],
            "instrumentation": "server_pre_dispatch_hook",
            "named_hosts": [NAMED_HOST],
            "server_override_keys": [entry.partition("=")[0] for entry in server_environment],
            "template_sha256": DESCRIPTOR_TEMPLATE_SHA256,
        },
        "journey": {
            "health": health,
            "host_invocations": 1,
            "request_guard": request_report,
            "strace": strace_report,
        },
        "environment": {
            **platform_report,
            "readonly_home": True,
            "runtime_state_explicit": True,
        },
        "reuse": {
            "additional_public_clone_attempts": 0,
            "p0_noneditable_installation_reused": True,
        },
        "checks": {
            "candidate_source_clean": True,
            "descriptor_immutable": True,
            "exact_mcp_request_sequence": True,
            "named_host_health": True,
            "node_network_guard_clear": True,
            "no_orphan_processes": True,
            "p0_identity_and_receipt": True,
            "python_network_guard_clear": True,
            "strace_network_audit_clear": True,
        },
        "traffic": {
            "document_requests": 0,
            "logical_mcp_requests": len(EXPECTED_REQUEST_METHODS),
            "model_requests": 0,
            "provider_requests": 0,
            "runtime_network_requests": 0,
            "search_calls": 0,
            "tool_calls": 1,
        },
        "budgets": {
            "dependency_install_attempts": 1,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "host_invocations": 1,
            "host_timeout_seconds": HOST_TIMEOUT_SECONDS,
            "logical_mcp_requests_maximum": LOGICAL_MCP_REQUESTS_MAXIMUM,
            "maximum_additional_seconds": MAXIMUM_ADDITIONAL_SECONDS,
            "retries": 0,
            "runtime_network_requests_maximum": 0,
            "server_launch_attempts": 1,
            "sessions": 1,
        },
        "limitations": {
            "developer_client_only": True,
            "gui_host_validated": False,
            "live_provider_validated": False,
            "macos_validated": False,
            "mcp_host_configuration_schema_claimed_universal": False,
            "phase12_authorized": False,
            "quality_claim_authorized": False,
            "windows_validated": False,
        },
        "publication": {
            "artifact_uploaded": False,
            "distribution_published": False,
            "release_published": False,
            "tag_published": False,
        },
        "timings": {
            "inspector_seconds": round(inspector.elapsed_seconds, 3),
            "npm_ci_seconds": round(install.elapsed_seconds, 3),
            "npm_ls_seconds": round(npm_ls.elapsed_seconds, 3),
        },
        "validation": {"errors": [], "passed": True},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--p0-receipt", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--git", default="git")
    parser.add_argument("--node", default="node")
    parser.add_argument("--npm", default="npm")
    parser.add_argument("--strace", default="strace")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_gate(
        work_root=args.work_root.resolve(),
        p0_receipt=args.p0_receipt.resolve(),
        expected_head=args.expected_head,
        output=args.output.resolve(),
        git_executable=_resolve_executable(args.git, "git"),
        node_executable=_resolve_executable(args.node, "Node"),
        npm_executable=_resolve_executable(args.npm, "npm"),
        strace_executable=_resolve_executable(args.strace, "strace"),
    )
    json.dump(report, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
