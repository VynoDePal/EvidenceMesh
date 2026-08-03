"""Verify the Alpha A1-P3 real AI host offline-replay interoperability gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import string
import subprocess
import time
from pathlib import Path
from typing import Any, cast

from scripts import verify_alpha_a1_p2_named_host as p2

BRANCH = "agent/evidencemesh-v0.1"
PREREQUISITE_COMMIT = "3cc75a33790be353a74641034a3c5210dfc7bc17"
PREREQUISITE_TREE = "21abc6024a08a5528710a5fd8e49630c8fca2c9d"
P2_COMMIT = "e33fb3bbfe5278ea30fe568847a1caf263de8c4d"
P2_TREE = "3564672ea1bd1ba6ec0edfd2c7a325d3f033b257"
P2_RUN_ID = 30743849354
P2_1_RUN_ID = 30744506608
SOURCE_COMMIT = "145f5f923825ffeaeb485bd680bc79410ab290d1"
SOURCE_TREE = "3b36c2d3970a5e3c325a2b20260daabf23d33a29"
EXPECTED_VERSION = "0.1.0"
EXPECTED_NODE_VERSION = "22.20.0"
EXPECTED_NPM_VERSION = "10.9.3"
EXPECTED_GEMINI_VERSION = "0.53.1"
EXPECTED_GEMINI_INTEGRITY = (
    "sha512-xBGdD/tl05gsTpD2oV1Bq0NCb4BBeTnjSbKxHtwOB7nt1QMaqWYJ9WsOEsQQhQ2P1v0"
    "UJth1F17SAXvdZ5mASw=="
)
EXPECTED_GEMINI_TARBALL = "https://registry.npmjs.org/@google/gemini-cli/-/gemini-cli-0.53.1.tgz"
EXPECTED_GEMINI_ENTRY_SHA256 = "a193db41b0b2c9e35a8c5aafcb2c810947ee41a311757bb4ee4d6b015bc3bfb5"
EXPECTED_PACKAGE_SHA256 = "59f5b8801b95333938d0ce17560ea583cfaf8388084a9bc620db637252926295"
EXPECTED_LOCK_SHA256 = "dc384de3fe3277f1cdaadf06dcc16268bb73aae0312f327119ba09fb8ea564b9"
EXPECTED_FAKE_RESPONSES_SHA256 = "ef07d0312717639ec5d53809b874fc4eee1e2f9f70d42133235d895752eb510b"
EXPECTED_LOCK_PACKAGE_COUNT = 13
EXPECTED_INSTALL_SCRIPT_PACKAGES = {
    "node_modules/@github/keytar",
    "node_modules/node-pty",
}
EXPECTED_CHANGED_PATHS = {
    ".github/workflows/alpha-a1-p3-real-host-offline.yml",
    "alpha/a1-p3-gemini-cli/fake-responses.jsonl",
    "alpha/a1-p3-gemini-cli/package-lock.json",
    "alpha/a1-p3-gemini-cli/package.json",
    "alpha/alpha_a1_p3_real_host_offline_policy_v1.json",
    "docs/alpha-a1-p3-real-host-offline-gate-v1.md",
    "scripts/verify_alpha_a1_p3_real_host_offline.py",
    "tests/test_alpha_a1_p3_real_host_offline.py",
}
IMMUTABLE_SHA256 = {
    ".github/workflows/ci.yml": (
        "1a7300b9126f865bc9252db9f4f62aeb84e1e35da6da288132984998c9af159e"
    ),
    "alpha/alpha_a1_p2_1_ci_determinism_policy_v1.json": (
        "19c05b282eb57a93b3f5e43a2ecc9f5515b76f2523e7b76a217ea8bb25c8a031"
    ),
    "alpha/alpha_a1_p2_named_host_policy_v1.json": (
        "ef7078b0ea15b232974eb38ed65f27c406618a15e6a53f4ba84cc9e61e51a487"
    ),
    "examples/evidencemesh.mcp.json": (
        "81f631f82166f70d81712d7e9ab82cdb3dc20b8ba592d65ba59473faf5b4295e"
    ),
    "pyproject.toml": ("eac6ae9e1d5b38f4262d33af137ce82ff019b41719c404a5c9b70a08a4f600a0"),
    "uv.lock": "5a47e1815cc2074698e1ab0cfec2932200bb013601d02246324513ffa5404898",
}
HARNESS_RELATIVE_PATH = Path("alpha/a1-p3-gemini-cli")
DESCRIPTOR_RELATIVE_PATH = Path("examples/evidencemesh.mcp.json")
COMMAND_PLACEHOLDER = "/absolute/path/to/EvidenceMesh/.venv/bin/evidencemesh-mcp"
CACHE_PLACEHOLDER = "/home/YOUR_USER/.cache/evidencemesh/cache.sqlite3"
NAMED_HOST = "evidencemesh"
MODEL_NAME = "gemini-3.1-flash-lite"
TOOL_NAME = "mcp_evidencemesh_health"
SERVER_TOOL_NAME = "health"
PROMPT = (
    "Call mcp_evidencemesh_health exactly once. Use no other tool. Return only status and version."
)
SENTINEL = "EVIDENCEMESH_A1_P3_COMPLETE"
EXPECTED_MCP_REQUESTS = [
    "initialize",
    "prompts/list",
    "tools/list",
    "resources/list",
    "tools/call",
]
EXPECTED_EVENT_TYPES = [
    "init",
    "message",
    "tool_use",
    "tool_result",
    "message",
    "result",
]
MAXIMUM_P3_SECONDS = 240
HOST_TIMEOUT_SECONDS = 60
PROCESS_TERMINATION_GRACE_SECONDS = 2
MAXIMUM_STDERR_BYTES = 16_384
SESSION_ID = "evidencemesh-a1-p3-offline"


class GateError(RuntimeError):
    """Raised when an A1-P3 fail-closed assertion does not hold."""


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


def _mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(message)
    return cast(dict[str, Any], value)


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label} is not valid UTF-8 JSON") from exc
    return _mapping(payload, f"{label} is not a JSON object")


def _validate_full_sha(value: str, label: str) -> None:
    _require(
        len(value) == 40 and all(character in string.hexdigits for character in value),
        f"{label} is not a full commit SHA",
    )


def _remaining_seconds(started_at: float) -> float:
    remaining = MAXIMUM_P3_SECONDS - (time.monotonic() - started_at)
    if remaining <= 0:
        raise GateError("Alpha A1-P3 exceeded its 240-second budget")
    return remaining


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    started_at: float,
    label: str,
    timeout_seconds: float | None = None,
) -> tuple[str, str, float]:
    before = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        timeout = _remaining_seconds(started_at)
        if timeout_seconds is not None:
            timeout = min(timeout, timeout_seconds)
        process = subprocess.Popen(  # noqa: S603 - executables are resolved first.
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
        if process is not None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=PROCESS_TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=PROCESS_TERMINATION_GRACE_SECONDS)
        raise GateError(f"{label} exceeded its budget") from exc
    _require(process is not None, f"{label} did not start")
    if process.returncode != 0:
        diagnostic = stderr[-5000:].strip()
        raise GateError(f"{label} failed with exit {process.returncode}: {diagnostic}")
    return stdout, stderr, time.monotonic() - before


def _resolve_executable(value: str, label: str) -> Path:
    candidate = Path(value)
    resolved = (
        candidate.expanduser().resolve()
        if candidate.parent != Path(".")
        else Path(shutil.which(value) or "")
    )
    _require(
        resolved.is_file() and os.access(resolved, os.X_OK),
        f"{label} is not executable: {value}",
    )
    return resolved


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": os.devnull,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
    }


def _validate_scope(
    repository_root: Path,
    expected_head: str,
    git_executable: Path,
    started_at: float,
) -> None:
    _validate_full_sha(expected_head, "trigger head")
    head, _, _ = _run(
        [str(git_executable), "rev-parse", "HEAD"],
        cwd=repository_root,
        env=_git_environment(),
        started_at=started_at,
        label="checkout HEAD",
    )
    _require(head.strip() == expected_head, "Checkout does not match the trigger head")
    parents, _, _ = _run(
        [str(git_executable), "rev-list", "--parents", "-n", "1", expected_head],
        cwd=repository_root,
        env=_git_environment(),
        started_at=started_at,
        label="A1-P3 parent inspection",
    )
    parent_tokens = parents.split()
    _require(len(parent_tokens) == 2, "A1-P3 commit must have exactly one parent")
    _require(parent_tokens[1] == PREREQUISITE_COMMIT, "A1-P3 parent checkpoint drifted")
    changed, _, _ = _run(
        [
            str(git_executable),
            "diff",
            "--name-status",
            "--no-renames",
            PREREQUISITE_COMMIT,
            expected_head,
        ],
        cwd=repository_root,
        env=_git_environment(),
        started_at=started_at,
        label="A1-P3 scope inspection",
    )
    observed: dict[str, str] = {}
    for line in changed.splitlines():
        status_value, separator, path = line.partition("\t")
        _require(bool(separator) and bool(path), "A1-P3 name-status output is malformed")
        observed[path] = status_value
    _require(set(observed) == EXPECTED_CHANGED_PATHS, "A1-P3 changed-path scope drifted")
    _require(set(observed.values()) == {"A"}, "A1-P3 scope must contain additions only")
    for relative, expected_hash in IMMUTABLE_SHA256.items():
        path = repository_root / relative
        _require(path.is_file(), f"Immutable prerequisite is missing: {relative}")
        _require(_sha256_file(path) == expected_hash, f"Immutable prerequisite drifted: {relative}")


def _validate_p0_receipt(path: Path, expected_head: str) -> dict[str, Any]:
    payload = _json_object(path, "A1-P0 receipt")
    try:
        observed_head = p2._validate_p0_receipt(payload)
    except p2.GateError as exc:
        raise GateError(str(exc)) from exc
    _require(observed_head == expected_head, "A1-P0 did not observe the A1-P3 trigger head")
    return payload


def _validate_harness(repository_root: Path) -> dict[str, Any]:
    harness = repository_root / HARNESS_RELATIVE_PATH
    package_path = harness / "package.json"
    lock_path = harness / "package-lock.json"
    fake_path = harness / "fake-responses.jsonl"
    package_bytes = package_path.read_bytes()
    lock_bytes = lock_path.read_bytes()
    fake_bytes = fake_path.read_bytes()
    _require(_sha256_bytes(package_bytes) == EXPECTED_PACKAGE_SHA256, "Gemini manifest drifted")
    _require(_sha256_bytes(lock_bytes) == EXPECTED_LOCK_SHA256, "Gemini lock drifted")
    _require(
        _sha256_bytes(fake_bytes) == EXPECTED_FAKE_RESPONSES_SHA256,
        "Offline response replay drifted",
    )
    manifest = _json_object(package_path, "Gemini harness manifest")
    lock = _json_object(lock_path, "Gemini harness lock")
    _require(manifest.get("private") is True, "Gemini harness is not private")
    _require(
        manifest.get("engines") == {"node": EXPECTED_NODE_VERSION, "npm": EXPECTED_NPM_VERSION},
        "Gemini harness engines drifted",
    )
    _require(
        manifest.get("dependencies") == {"@google/gemini-cli": EXPECTED_GEMINI_VERSION},
        "Gemini harness dependency drifted",
    )
    _require("scripts" not in manifest, "Gemini harness gained scripts")
    _require(lock.get("lockfileVersion") == 3, "Gemini lockfile version drifted")
    packages = _mapping(lock.get("packages"), "Gemini lock packages are missing")
    _require(len(packages) == EXPECTED_LOCK_PACKAGE_COUNT, "Gemini lock package count drifted")
    install_scripts: set[str] = set()
    for relative, value in packages.items():
        entry = _mapping(value, f"Gemini lock entry is malformed: {relative}")
        if relative:
            _require(
                str(entry.get("resolved", "")).startswith("https://registry.npmjs.org/"),
                f"Gemini lock registry drifted: {relative}",
            )
            _require(
                str(entry.get("integrity", "")).startswith("sha512-"),
                f"Gemini lock integrity drifted: {relative}",
            )
        if entry.get("hasInstallScript") is True:
            install_scripts.add(relative)
    _require(
        install_scripts == EXPECTED_INSTALL_SCRIPT_PACKAGES,
        "Gemini optional install-script inventory drifted",
    )
    gemini = _mapping(
        packages.get("node_modules/@google/gemini-cli"),
        "Gemini CLI lock entry is missing",
    )
    _require(gemini.get("version") == EXPECTED_GEMINI_VERSION, "Gemini version drifted")
    _require(gemini.get("resolved") == EXPECTED_GEMINI_TARBALL, "Gemini tarball drifted")
    _require(
        gemini.get("integrity") == EXPECTED_GEMINI_INTEGRITY,
        "Gemini registry integrity drifted",
    )
    fake_records: list[dict[str, Any]] = []
    for index, line in enumerate(fake_bytes.decode("utf-8").splitlines(), start=1):
        try:
            fake_records.append(_mapping(json.loads(line), f"Replay line {index} is not an object"))
        except json.JSONDecodeError as exc:
            raise GateError(f"Replay line {index} is invalid JSON") from exc
    _require(len(fake_records) == 2, "Replay must contain exactly two model turns")
    _require(
        [record.get("method") for record in fake_records]
        == ["generateContentStream", "generateContentStream"],
        "Replay methods drifted",
    )
    first_part = fake_records[0]["response"][0]["candidates"][0]["content"]["parts"][0]
    second_part = fake_records[1]["response"][0]["candidates"][0]["content"]["parts"][0]
    _require(
        first_part == {"functionCall": {"name": TOOL_NAME, "args": {}}},
        "Replay tool selection drifted",
    )
    _require(second_part == {"text": SENTINEL}, "Replay final response drifted")
    return {
        "fake_responses_sha256": EXPECTED_FAKE_RESPONSES_SHA256,
        "install_script_packages_omitted": sorted(install_scripts),
        "lock_package_count": len(packages),
        "lock_sha256": EXPECTED_LOCK_SHA256,
        "manifest_sha256": EXPECTED_PACKAGE_SHA256,
    }


PYTHON_GUARD = r'''"""Fail-closed A1-P3 Python network, request, and secret guard."""
import atexit
import json
import os
import re
import socket
import uuid

from mcp.server.lowlevel.server import Server
from mcp.server.session import ServerSession


armed = os.environ.get("EVIDENCEMESH_A1_P3_PYTHON_GUARD_ARMED_LOG")
network_marker = os.environ.get("EVIDENCEMESH_A1_P3_PYTHON_NETWORK_LOG")
request_trace = os.environ.get("EVIDENCEMESH_A1_P3_REQUEST_TRACE")
if not armed or not network_marker or not request_trace:
    raise RuntimeError("Alpha A1-P3 Python guard markers are missing")


def _append(event):
    with open(request_trace, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


forbidden = sorted(
    name
    for name in os.environ
    if re.search(r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", name, re.IGNORECASE)
    or name.upper().endswith("_PROXY")
    or name.upper() in {"ALL_PROXY", "NO_PROXY", "NODE_USE_ENV_PROXY"}
)
if forbidden:
    _append({"event": "denied", "reason": "environment", "names": forbidden})
    raise RuntimeError("Alpha A1-P3 server inherited forbidden environment names")
with open(armed, "a", encoding="utf-8") as handle:
    handle.write(f"{os.getpid()}\n")
_append({"event": "server_start", "pid": os.getpid()})


def _deny(operation, target=None):
    with open(network_marker, "a", encoding="utf-8") as handle:
        handle.write(f"{operation}:{target!r}\n")
    raise OSError("Alpha A1-P3 Python network is disabled")


socket.socket.connect = lambda _socket, address: _deny("socket.connect", address)
socket.socket.connect_ex = lambda _socket, address: _deny("socket.connect_ex", address)
socket.socket.sendto = lambda _socket, data, *args: _deny(
    "socket.sendto", args[-1] if args else None
)
socket.create_connection = lambda address, *args, **kwargs: _deny(
    "socket.create_connection", address
)
socket.getaddrinfo = lambda host, port, *args, **kwargs: _deny(
    "socket.getaddrinfo", (host, port)
)
socket.gethostbyname = lambda host: _deny("socket.gethostbyname", host)
socket.gethostbyname_ex = lambda host: _deny("socket.gethostbyname_ex", host)
socket.getnameinfo = lambda sockaddr, flags: _deny("socket.getnameinfo", sockaddr)


expected = ["initialize", "prompts/list", "tools/list", "resources/list", "tools/call"]
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
        if method in {"prompts/list", "tools/list", "resources/list"} and params != {}:
            _append({"event": "denied", "method": method, "reason": "params"})
            raise RuntimeError(f"Unexpected {method} parameters")
        if method == "tools/call":
            if not isinstance(params, dict):
                raise RuntimeError("Gemini tools/call parameters are malformed")
            if params.get("name") != "health" or params.get("arguments") != {}:
                _append({"event": "denied", "method": method, "reason": "tool"})
                raise RuntimeError("Gemini invoked a tool other than health")
            if set(params) != {"name", "arguments", "_meta"}:
                raise RuntimeError("Gemini tools/call parameter keys drifted")
            meta = params.get("_meta")
            token = meta.get("progressToken") if isinstance(meta, dict) else None
            try:
                uuid.UUID(str(token))
            except (ValueError, TypeError, AttributeError) as exc:
                raise RuntimeError("Gemini progress token drifted") from exc
        observed.append(method)
        _append({"event": "request", "method": method})
    elif method is not None:
        if method != "notifications/initialized" or initialized:
            _append({"event": "denied", "method": method})
            raise RuntimeError(f"Unexpected MCP notification before dispatch: {method!r}")
        initialized = True
        _append({"event": "notification", "method": method})
    return await original_handle_message(self, message, *args, **kwargs)


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


NODE_GUARD = (
    p2.NODE_NETWORK_GUARD.replace("A1_P2", "A1_P3")
    .replace("A1-P2", "A1-P3")
    .replace(
        'globalThis.fetch = async function (...args) { return deny("fetch", args[0]); };',
        r"""const originalFetch = globalThis.fetch;
globalThis.fetch = async function (...args) {
  const input = args[0];
  const target = input && typeof input === "object" && typeof input.url === "string"
    ? input.url
    : String(input);
  let protocol;
  try {
    protocol = new URL(target).protocol;
  } catch {
    return deny("fetch", target);
  }
  if (protocol !== "data:") {
    return deny("fetch", target);
  }
  return originalFetch(...args);
};""",
    )
)


def _private_file(path: Path, content: str = "") -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def _acquisition_environment(root: Path, node: Path) -> tuple[dict[str, str], Path]:
    home = root / "acquisition-home"
    cache = root / "npm-cache"
    home.mkdir(mode=0o700)
    cache.mkdir(mode=0o700)
    return (
        {
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "LOGNAME": "evidencemesh-a1-p3-acquisition",
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_CACHE": str(cache),
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
            "USER": "evidencemesh-a1-p3-acquisition",
        },
        cache,
    )


def _install_gemini(
    repository_root: Path,
    runtime_root: Path,
    node: Path,
    npm: Path,
    started_at: float,
) -> tuple[Path, dict[str, Any]]:
    harness_source = repository_root / HARNESS_RELATIVE_PATH
    harness = runtime_root / "gemini-harness"
    harness.mkdir(mode=0o700)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(harness_source / name, harness / name)
        (harness / name).chmod(0o600)
    package_snapshot = (harness / "package.json").read_bytes()
    lock_snapshot = (harness / "package-lock.json").read_bytes()
    acquisition_env, cache = _acquisition_environment(runtime_root, node)
    _, install_stderr, install_seconds = _run(
        [
            str(npm),
            "ci",
            "--ignore-scripts",
            "--omit=optional",
            "--no-audit",
            "--no-fund",
            "--fetch-retries=0",
        ],
        cwd=harness,
        env=acquisition_env,
        started_at=started_at,
        label="pinned Gemini CLI installation",
    )
    _require((harness / "package.json").read_bytes() == package_snapshot, "npm changed manifest")
    _require((harness / "package-lock.json").read_bytes() == lock_snapshot, "npm changed lock")
    package_root = harness / "node_modules" / "@google" / "gemini-cli"
    manifest = _json_object(package_root / "package.json", "installed Gemini manifest")
    _require(manifest.get("version") == EXPECTED_GEMINI_VERSION, "Installed Gemini drifted")
    _require(manifest.get("license") == "Apache-2.0", "Installed Gemini license drifted")
    _require(manifest.get("bin") == {"gemini": "bundle/gemini.js"}, "Gemini bin drifted")
    _require(manifest.get("engines") == {"node": ">=20"}, "Gemini engine floor drifted")
    launcher = package_root / "bundle" / "gemini.js"
    _require(_sha256_file(launcher) == EXPECTED_GEMINI_ENTRY_SHA256, "Gemini entry drifted")
    for omitted in ("@github", "@lydell", "node-pty", "nan", "node-addon-api"):
        _require(
            not (harness / "node_modules" / omitted).exists(),
            f"Optional package installed: {omitted}",
        )
    npm_ls, _, _ = _run(
        [str(npm), "ls", "--omit=optional", "--json"],
        cwd=harness,
        env=acquisition_env,
        started_at=started_at,
        label="installed Gemini dependency tree",
    )
    try:
        tree = _mapping(json.loads(npm_ls), "npm ls output is not an object")
    except json.JSONDecodeError as exc:
        raise GateError("npm ls output is malformed") from exc
    _require(not tree.get("problems"), "npm ls reported dependency problems")
    dependencies = _mapping(tree.get("dependencies"), "npm ls root dependencies are missing")
    _require(set(dependencies) == {"@google/gemini-cli"}, "Installed dependency scope drifted")
    _require(
        _mapping(dependencies["@google/gemini-cli"], "Gemini npm ls entry is malformed").get(
            "version"
        )
        == EXPECTED_GEMINI_VERSION,
        "npm ls Gemini version drifted",
    )
    shutil.rmtree(cache)
    _require(not cache.exists(), "npm acquisition cache survived into runtime")
    return launcher, {
        "attempts": 1,
        "entry_sha256": EXPECTED_GEMINI_ENTRY_SHA256,
        "ignore_scripts": True,
        "install_seconds": round(install_seconds, 3),
        "optional_dependencies_omitted": True,
        "retries": 0,
        "stderr_bytes": len(install_stderr.encode()),
    }


def _runtime_settings(
    repository_root: Path,
    runtime_root: Path,
    server_command: Path,
) -> dict[str, Any]:
    guards = runtime_root / "guards"
    guards.mkdir(mode=0o700)
    _private_file(guards / "sitecustomize.py", PYTHON_GUARD)
    _private_file(guards / "node-network-guard.cjs", NODE_GUARD)
    logs = {
        "node_armed": runtime_root / "node-guard-armed.log",
        "node_network": runtime_root / "node-network-attempts.log",
        "python_armed": runtime_root / "python-guard-armed.log",
        "python_network": runtime_root / "python-network-attempts.log",
        "request_trace": runtime_root / "mcp-request-trace.jsonl",
    }
    for path in logs.values():
        _private_file(path)
    state = runtime_root / "state"
    state.mkdir(mode=0o700)
    cache = state / "cache.sqlite3"
    _private_file(cache)
    server_home = runtime_root / "server-home"
    server_home.mkdir(mode=0o555)
    template_path = repository_root / DESCRIPTOR_RELATIVE_PATH
    template_bytes = template_path.read_bytes()
    _require(
        _sha256_bytes(template_bytes) == IMMUTABLE_SHA256[str(DESCRIPTOR_RELATIVE_PATH)],
        "A1-P1 descriptor drifted",
    )
    descriptor = _json_object(template_path, "A1-P1 descriptor")
    server = _mapping(
        _mapping(descriptor.get("mcpServers"), "Descriptor servers are missing").get(NAMED_HOST),
        "EvidenceMesh descriptor entry is missing",
    )
    _require(server.get("command") == COMMAND_PLACEHOLDER, "Command placeholder drifted")
    _require(server.get("args") == [], "Descriptor args drifted")
    server_env = _mapping(server.get("env"), "Descriptor environment is missing")
    _require(server_env.get("EVIDENCEMESH_CACHE_PATH") == CACHE_PLACEHOLDER, "Cache drifted")
    server["command"] = str(server_command.resolve())
    server_env["EVIDENCEMESH_CACHE_PATH"] = str(cache.resolve())
    server_env.update(
        {
            "EVIDENCEMESH_A1_P3_PYTHON_GUARD_ARMED_LOG": str(logs["python_armed"]),
            "EVIDENCEMESH_A1_P3_PYTHON_NETWORK_LOG": str(logs["python_network"]),
            "EVIDENCEMESH_A1_P3_REQUEST_TRACE": str(logs["request_trace"]),
            "HOME": str(server_home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(guards),
            "XDG_CACHE_HOME": str(server_home / ".cache"),
            "XDG_CONFIG_HOME": str(server_home / ".config"),
            "XDG_DATA_HOME": str(server_home / ".local" / "share"),
        }
    )
    server["includeTools"] = [SERVER_TOOL_NAME]
    server["timeout"] = 10_000
    server["trust"] = True
    blocked_environment = [
        "ALL_PROXY",
        "BUNDLE_HTTPS_PROXY",
        "BUNDLE_HTTP_PROXY",
        "BUNDLE_NO_PROXY",
        "DOCKER_HTTPS_PROXY",
        "DOCKER_HTTP_PROXY",
        "GEMINI_API_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GOOGLE_API_KEY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "NODE_USE_ENV_PROXY",
        "NPM_CONFIG_HTTPS_PROXY",
        "NPM_CONFIG_HTTP_PROXY",
        "NPM_CONFIG_NOPROXY",
        "NPM_CONFIG_PROXY",
        "ftp_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "npm_config_http_proxy",
        "npm_config_https_proxy",
        "npm_config_noproxy",
        "npm_config_proxy",
    ]
    settings = {
        "general": {
            "maxAttempts": 1,
            "plan": {"enabled": False, "modelRouting": False},
            "retryFetchErrors": False,
        },
        "mcp": {"allowed": [NAMED_HOST]},
        "mcpServers": descriptor["mcpServers"],
        "model": {"maxSessionTurns": 2, "skipNextSpeakerCheck": True},
        "privacy": {"usageStatisticsEnabled": False},
        "security": {
            "auth": {"selectedType": "gemini-api-key"},
            "environmentVariableRedaction": {
                "allowed": [],
                "blocked": blocked_environment,
                "enabled": True,
            },
        },
        "telemetry": {"enabled": False},
        "tools": {"core": [TOOL_NAME]},
    }
    gemini_home = runtime_root / "gemini-home"
    settings_dir = gemini_home / ".gemini"
    settings_dir.mkdir(parents=True, mode=0o700)
    settings_path = settings_dir / "settings.json"
    _private_file(settings_path, json.dumps(settings, indent=2, sort_keys=True) + "\n")
    workspace = runtime_root / "workspace"
    workspace.mkdir(mode=0o555)
    tmp = runtime_root / "tmp"
    tmp.mkdir(mode=0o700)
    return {
        "cache": cache,
        "gemini_home": gemini_home,
        "guards": guards,
        "logs": logs,
        "server_home": server_home,
        "settings": settings,
        "settings_path": settings_path,
        "state": state,
        "tmp": tmp,
        "workspace": workspace,
    }


def _runtime_environment(
    runtime: dict[str, Any], node: Path, installed_python: Path, expected_head: str
) -> dict[str, str]:
    gemini_home = cast(Path, runtime["gemini_home"])
    guards = cast(Path, runtime["guards"])
    logs = cast(dict[str, Path], runtime["logs"])
    tmp = cast(Path, runtime["tmp"])
    path_parts = [str(node.parent), str(installed_python.parent), os.defpath]
    git_path = shutil.which("git")
    if git_path:
        path_parts.insert(1, str(Path(git_path).resolve().parent))
    return {
        "CI": "true",
        "GEMINI_API_KEY": "offline-a1-p3-non-secret-sentinel",
        "GEMINI_CLI_HOME": str(gemini_home),
        "GEMINI_CLI_TRUST_WORKSPACE": "true",
        "GITHUB_SHA": expected_head,
        "HOME": str(gemini_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LOGNAME": "evidencemesh-a1-p3",
        "NODE_OPTIONS": f"--require={guards / 'node-network-guard.cjs'}",
        "NO_BROWSER": "1",
        "NO_COLOR": "1",
        "PATH": ":".join(path_parts),
        "SHELL": "/bin/sh",
        "TERM": "dumb",
        "TMPDIR": str(tmp),
        "USER": "evidencemesh-a1-p3",
        "XDG_CACHE_HOME": str(gemini_home / ".cache"),
        "XDG_CONFIG_HOME": str(gemini_home / ".config"),
        "XDG_DATA_HOME": str(gemini_home / ".local" / "share"),
        "EVIDENCEMESH_A1_P3_NODE_GUARD_ARMED_LOG": str(logs["node_armed"]),
        "EVIDENCEMESH_A1_P3_NODE_NETWORK_LOG": str(logs["node_network"]),
    }


def _json_lines(value: str, label: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, line in enumerate(value.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(_mapping(json.loads(line), f"{label} line {index} is not an object"))
        except json.JSONDecodeError as exc:
            raise GateError(f"{label} line {index} is malformed") from exc
    return events


def _validate_health(payload: Any) -> dict[str, Any]:
    health = _mapping(payload, "Gemini health output is not an object")
    _require(health.get("status") == "ready", "EvidenceMesh is not ready")
    _require(health.get("version") == EXPECTED_VERSION, "EvidenceMesh version drifted")
    _require(health.get("deployment_profile") == "community", "Deployment profile drifted")
    _require(health.get("configuration_warnings") == [], "Configuration warnings appeared")
    providers = health.get("providers")
    _require(isinstance(providers, list) and len(providers) == 1, "Provider inventory drifted")
    provider = _mapping(providers[0], "Provider receipt is malformed")
    _require(provider.get("name") == "wikipedia", "Configured provider drifted")
    safety = _mapping(health.get("safety"), "Safety receipt is missing")
    _require(safety.get("private_networks_allowed") is False, "Private networks became allowed")
    _require(safety.get("nonstandard_ports_allowed") is False, "Nonstandard ports became allowed")
    _require(safety.get("robots_txt_respected") is True, "robots.txt policy drifted")
    _require(safety.get("dns_pinning") is True, "DNS pinning drifted")
    return health


def _validate_host_events(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
    events = _json_lines(stdout, "Gemini stream JSON")
    _require([event.get("type") for event in events] == EXPECTED_EVENT_TYPES, "Host events drifted")
    init, user, tool_use, tool_result, assistant, result = events
    _require(init.get("model") == MODEL_NAME, "Gemini model label drifted")
    _require(init.get("session_id") == SESSION_ID, "Gemini session drifted")
    _require(user.get("role") == "user" and user.get("content") == PROMPT, "Prompt drifted")
    _require(tool_use.get("tool_name") == TOOL_NAME, "Gemini selected another tool")
    _require(tool_use.get("parameters") == {}, "Gemini tool parameters drifted")
    tool_id = tool_use.get("tool_id")
    _require(isinstance(tool_id, str) and bool(tool_id), "Gemini tool ID is missing")
    _require(tool_result.get("tool_id") == tool_id, "Gemini tool correlation drifted")
    _require(tool_result.get("status") == "success", "Gemini reported a tool failure")
    _require("error" not in tool_result, "Gemini tool result contains an error")
    try:
        health = _validate_health(json.loads(str(tool_result.get("output"))))
    except json.JSONDecodeError as exc:
        raise GateError("Gemini tool result is not JSON") from exc
    _require(
        assistant.get("role") == "assistant" and assistant.get("content") == SENTINEL,
        "Gemini final replay sentinel drifted",
    )
    _require(result.get("status") == "success", "Gemini host result did not pass")
    stats = _mapping(result.get("stats"), "Gemini stats are missing")
    _require(stats.get("tool_calls") == 1, "Gemini tool-call count drifted")
    _require(stats.get("total_tokens") == 4, "Gemini replay token total drifted")
    models = _mapping(stats.get("models"), "Gemini model stats are missing")
    _require(set(models) == {MODEL_NAME}, "Gemini used another model label")
    model_stats = _mapping(models[MODEL_NAME], "Gemini model stats are malformed")
    _require(
        {key: model_stats.get(key) for key in ("total_tokens", "input_tokens", "output_tokens")}
        == {"total_tokens": 4, "input_tokens": 2, "output_tokens": 2},
        "Gemini replay model statistics drifted",
    )
    return health, stats


def _validate_request_trace(path: Path) -> dict[str, Any]:
    events = _json_lines(path.read_text(encoding="utf-8"), "MCP request trace")
    _require(
        not [event for event in events if event.get("event") == "denied"], "Guard denied input"
    )
    starts = [event for event in events if event.get("event") == "server_start"]
    _require(len(starts) == 1, "EvidenceMesh server launch count drifted")
    methods = [str(event.get("method")) for event in events if event.get("event") == "request"]
    _require(methods == EXPECTED_MCP_REQUESTS, "Gemini MCP request sequence drifted")
    notifications = [
        str(event.get("method")) for event in events if event.get("event") == "notification"
    ]
    _require(notifications == ["notifications/initialized"], "MCP notification sequence drifted")
    server_pid = starts[0].get("pid")
    _require(isinstance(server_pid, int) and server_pid > 1, "EvidenceMesh server PID drifted")
    exits = [event for event in events if event.get("event") == "server_exit"]
    if exits:
        _require(len(exits) == 1, "EvidenceMesh server exit count drifted")
        _require(exits[0].get("request_sequence_complete") is True, "MCP exit was incomplete")
    return {
        "logical_requests": len(methods),
        "methods": methods,
        "notifications": notifications,
        "server_launches": 1,
        "server_pid": server_pid,
        "sessions": 1,
    }


def _validate_strace(path: Path) -> dict[str, Any]:
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateError("A1-P3 strace log is unreadable") from exc
    exec_paths = {Path(match).resolve() for match in re.findall(r'\bexecve\("([^"]+)"', value)}
    _require(bool(exec_paths), "A1-P3 strace did not record the host process tree")
    allowed_names = {"evidencemesh-mcp", "git", "node", "python", "python3", "python3.11", "rg"}
    unexpected = sorted(str(path) for path in exec_paths if path.name not in allowed_names)
    _require(not unexpected, f"A1-P3 executed an unexpected program: {unexpected}")
    try:
        return p2._validate_strace(path, exec_paths)
    except p2.GateError as exc:
        raise GateError(str(exc)) from exc


def _read_pid_set(path: Path, label: str) -> set[int]:
    values = path.read_text(encoding="utf-8").splitlines()
    try:
        result = {int(value) for value in values if value}
    except ValueError as exc:
        raise GateError(f"{label} contains a malformed PID") from exc
    _require(len(result) == 1, f"{label} arming count drifted")
    return result


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
    repository_root = Path(__file__).resolve().parents[1]
    _validate_scope(repository_root, expected_head, git_executable, started_at)
    _require(work_root.is_dir(), "A1-P0 work root is missing")
    _require(
        p0_receipt.resolve() == (work_root / "runtime" / "receipt.json").resolve(),
        "A1-P0 receipt path drifted",
    )
    _validate_p0_receipt(p0_receipt, expected_head)
    source = work_root / "source"
    _require(source.is_dir(), "A1-P0 source clone is missing")
    source_head, _, _ = _run(
        [str(git_executable), "rev-parse", f"refs/remotes/origin/{BRANCH}"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="A1-P0 public branch head",
    )
    _require(source_head.strip() == expected_head, "A1-P0 source did not observe the trigger head")
    installed_head, _, _ = _run(
        [str(git_executable), "rev-parse", "HEAD"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="A1-P0 installed source head",
    )
    _require(installed_head.strip() == SOURCE_COMMIT, "A1-P0 installed source commit drifted")
    source_status, _, _ = _run(
        [str(git_executable), "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="pre-gate source status",
    )
    _require(source_status == "", "A1-P0 source is dirty")
    node_version, _, _ = _run(
        [str(node_executable), "--version"],
        cwd=repository_root,
        env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": os.defpath},
        started_at=started_at,
        label="Node version",
    )
    _require(node_version.strip() == f"v{EXPECTED_NODE_VERSION}", "Canonical Node drifted")
    npm_version, _, _ = _run(
        [str(npm_executable), "--version"],
        cwd=repository_root,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": f"{node_executable.parent}:{os.defpath}",
        },
        started_at=started_at,
        label="npm version",
    )
    _require(npm_version.strip() == EXPECTED_NPM_VERSION, "Canonical npm drifted")
    supply_chain = _validate_harness(repository_root)
    runtime_root = work_root / "p3-runtime"
    _require(not runtime_root.exists(), "A1-P3 runtime root must not already exist")
    runtime_root.mkdir(mode=0o700)
    launcher, install_report = _install_gemini(
        repository_root, runtime_root, node_executable, npm_executable, started_at
    )
    installed_python = source / ".venv" / "bin" / "python"
    server_command = source / ".venv" / "bin" / "evidencemesh-mcp"
    _require(installed_python.is_file() and os.access(installed_python, os.X_OK), "Python missing")
    _require(server_command.is_file() and os.access(server_command, os.X_OK), "MCP command missing")
    runtime = _runtime_settings(repository_root, runtime_root, server_command)
    settings_path = cast(Path, runtime["settings_path"])
    settings_snapshot = settings_path.read_bytes()
    runtime_env = _runtime_environment(runtime, node_executable, installed_python, expected_head)
    fake_responses = repository_root / HARNESS_RELATIVE_PATH / "fake-responses.jsonl"
    strace_log = runtime_root / "gemini.strace.log"
    stdout, stderr, host_seconds = _run(
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
            "--prompt",
            PROMPT,
            "--model",
            MODEL_NAME,
            "--approval-mode",
            "default",
            "--allowed-mcp-server-names",
            NAMED_HOST,
            "--output-format",
            "stream-json",
            "--skip-trust",
            "--session-id",
            SESSION_ID,
            "--fake-responses",
            str(fake_responses),
        ],
        cwd=cast(Path, runtime["workspace"]),
        env=runtime_env,
        started_at=started_at,
        label="Gemini CLI real-host offline replay",
        timeout_seconds=HOST_TIMEOUT_SECONDS,
    )
    _require(len(stderr.encode()) <= MAXIMUM_STDERR_BYTES, "Gemini stderr exceeded its bound")
    lowered_stderr = stderr.lower()
    _require("traceback (most recent call last)" not in lowered_stderr, "Python traceback emitted")
    _require("error executing tool" not in lowered_stderr, "Gemini emitted a tool error")
    _require("mcp issues detected" not in lowered_stderr, "Gemini reported an MCP issue")
    health, host_stats = _validate_host_events(stdout)
    logs = cast(dict[str, Path], runtime["logs"])
    request_report = _validate_request_trace(logs["request_trace"])
    strace_report = _validate_strace(strace_log)
    for key in ("node_network", "python_network"):
        _require(logs[key].stat().st_size == 0, f"{key} recorded a network attempt")
    node_pids = _read_pid_set(logs["node_armed"], "Node guard")
    python_pids = _read_pid_set(logs["python_armed"], "Python guard")
    try:
        p2._require_processes_gone(
            node_pids | python_pids | {cast(int, request_report["server_pid"])}
        )
    except p2.GateError as exc:
        raise GateError(str(exc)) from exc
    _require(settings_path.read_bytes() == settings_snapshot, "Gemini changed locked settings")
    _require(stat.S_IMODE(settings_path.stat().st_mode) == 0o600, "Settings mode drifted")
    cache = cast(Path, runtime["cache"])
    _require(cache.is_file(), "EvidenceMesh cache is missing")
    _require(stat.S_IMODE(cache.stat().st_mode) == 0o600, "EvidenceMesh cache mode drifted")
    _require(set(cast(Path, runtime["state"]).iterdir()) == {cache}, "State inventory drifted")
    _require(list(cast(Path, runtime["workspace"]).iterdir()) == [], "Workspace was modified")
    _require(list(cast(Path, runtime["server_home"]).iterdir()) == [], "Server HOME was modified")
    source_status_after, _, _ = _run(
        [str(git_executable), "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="post-gate source status",
    )
    _require(source_status_after == "", "A1-P3 modified installed source")
    elapsed = time.monotonic() - started_at
    _require(elapsed <= MAXIMUM_P3_SECONDS, "A1-P3 exceeded its total budget")
    report: dict[str, Any] = {
        "schema_version": "evidencemesh.alpha-a1-p3-real-host-offline-receipt.v1",
        "candidate": {
            "branch": BRANCH,
            "product_commit_sha": SOURCE_COMMIT,
            "product_tree_sha": SOURCE_TREE,
            "trigger_head_sha": expected_head,
            "version": EXPECTED_VERSION,
        },
        "prerequisite": {
            "commit_sha": PREREQUISITE_COMMIT,
            "tree_sha": PREREQUISITE_TREE,
            "p2_commit_sha": P2_COMMIT,
            "p2_tree_sha": P2_TREE,
            "p2_run_id": P2_RUN_ID,
            "p2_1_run_id": P2_1_RUN_ID,
        },
        "host": {
            "agent_loop_executed": True,
            "classification": "real_ai_application_host_offline_replay",
            "entry_sha256": EXPECTED_GEMINI_ENTRY_SHA256,
            "license": "Apache-2.0",
            "model_label": MODEL_NAME,
            "name": "Gemini CLI",
            "npm_integrity": EXPECTED_GEMINI_INTEGRITY,
            "version": EXPECTED_GEMINI_VERSION,
        },
        "replay": {
            "external_model_requests": 0,
            "official_fake_response_engine": True,
            "synthetic_model_turns": 2,
            "live_model_provider_validated": False,
        },
        "mcp": request_report,
        "tool_call": {
            "calls": 1,
            "health": health,
            "host_name": TOOL_NAME,
            "server_name": SERVER_TOOL_NAME,
            "status": "success",
        },
        "runtime": {
            "host_seconds": round(host_seconds, 3),
            "network": strace_report,
            "node_api_guard_clear": True,
            "python_api_guard_clear": True,
            "secret_names_in_server_environment": 0,
        },
        "supply_chain": {**supply_chain, "installation": install_report},
        "budgets": {
            "dependency_install_attempts": 1,
            "external_document_requests": 0,
            "external_model_requests": 0,
            "host_invocations": 1,
            "host_timeout_seconds": HOST_TIMEOUT_SECONDS,
            "logical_mcp_requests": len(EXPECTED_MCP_REQUESTS),
            "logical_mcp_requests_maximum": 5,
            "mcp_server_launches": 1,
            "mcp_sessions": 1,
            "mcp_tool_calls": 1,
            "provider_calls": 0,
            "retries": 0,
            "runtime_network_requests": 0,
            "search_calls": 0,
            "synthetic_model_turns": 2,
        },
        "host_stats": host_stats,
        "validation": {"errors": [], "passed": True},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _private_file(output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--p0-receipt", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--git", default="git")
    parser.add_argument("--node", default="node")
    parser.add_argument("--npm", default="npm")
    parser.add_argument("--strace", default="strace")
    args = parser.parse_args()
    try:
        run_gate(
            work_root=args.work_root.resolve(),
            p0_receipt=args.p0_receipt.resolve(),
            expected_head=args.expected_head,
            output=args.output.resolve(),
            git_executable=_resolve_executable(args.git, "git"),
            node_executable=_resolve_executable(args.node, "node"),
            npm_executable=_resolve_executable(args.npm, "npm"),
            strace_executable=_resolve_executable(args.strace, "strace"),
        )
    except (GateError, OSError, UnicodeError, p2.GateError) as exc:
        print(f"Alpha A1-P3 FAIL: {exc}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
