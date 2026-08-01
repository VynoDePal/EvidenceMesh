"""Verify the Alpha A1-P1 first-run MCP journey after the A1-P0 gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import string
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

PREREQUISITE_COMMIT = "d34abe56b95c9daccf361eb86ff1c19421085f62"
PREREQUISITE_TREE = "c622cfe868a2bc77cd487ec17107eb225f882a4c"
SOURCE_COMMIT = "145f5f923825ffeaeb485bd680bc79410ab290d1"
SOURCE_TREE = "3b36c2d3970a5e3c325a2b20260daabf23d33a29"
BRANCH = "agent/evidencemesh-v0.1"
EXPECTED_VERSION = "0.1.0"
EXPECTED_MCP_VERSION = "1.29.0"
DESCRIPTOR_RELATIVE_PATH = Path("examples/evidencemesh.mcp.json")
DESCRIPTOR_TEMPLATE_SHA256 = "81f631f82166f70d81712d7e9ab82cdb3dc20b8ba592d65ba59473faf5b4295e"
COMMAND_PLACEHOLDER = "/absolute/path/to/EvidenceMesh/.venv/bin/evidencemesh-mcp"
CACHE_PLACEHOLDER = "/home/YOUR_USER/.cache/evidencemesh/cache.sqlite3"
MAXIMUM_ADDITIONAL_SECONDS = 60
EXPECTED_CHANGED_PATHS = {
    ".github/workflows/ci.yml",
    "README.md",
    "alpha/alpha_a1_p1_mcp_first_run_policy_v1.json",
    "docs/alpha-a1-p1-mcp-first-run-gate-v1.md",
    str(DESCRIPTOR_RELATIVE_PATH),
    "scripts/smoke_official_mcp_client.py",
    "scripts/verify_alpha_a1_p1_mcp_first_run.py",
    "tests/test_alpha_a1_p1_mcp_first_run.py",
}
EXPECTED_P0_CHECKS = {
    "cli_health": True,
    "installed_package": True,
    "mcp_stdio_health": True,
    "network_guard_clear": True,
    "offline_benchmark": True,
    "source_remained_clean": True,
}


class GateError(RuntimeError):
    """Raised when an A1-P1 fail-closed assertion does not hold."""


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


def _remaining_seconds(started_at: float) -> float:
    remaining = MAXIMUM_ADDITIONAL_SECONDS - (time.monotonic() - started_at)
    if remaining <= 0:
        raise GateError("Alpha A1-P1 exceeded its 60-second additional budget")
    return remaining


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    started_at: float,
    label: str,
) -> CommandObservation:
    before = time.monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 - exact executables are resolved first.
            argv,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=_remaining_seconds(started_at),
        )
    except subprocess.TimeoutExpired as exc:
        raise GateError(f"{label} exceeded the remaining additional budget") from exc
    elapsed = time.monotonic() - before
    if completed.returncode != 0:
        stderr = completed.stderr[-4000:].strip()
        raise GateError(f"{label} failed with exit {completed.returncode}: {stderr}")
    return CommandObservation(completed.stdout, completed.stderr, elapsed)


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


def _mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(message)
    return cast(dict[str, Any], value)


def _require_file_unchanged(path: Path, expected: bytes, label: str) -> None:
    _require(path.read_bytes() == expected, f"{label} changed during the journey")


def _validate_trigger_head(branch_head: str, expected_head: str) -> None:
    _require(
        len(expected_head) == 40
        and all(character in string.hexdigits for character in expected_head),
        "Triggering PR head is not a full commit SHA",
    )
    _require(branch_head == expected_head, "Public clone head differs from the triggering PR head")


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
    if not (
        isinstance(branch_head_value, str)
        and len(branch_head_value) == 40
        and all(character in string.hexdigits for character in branch_head_value)
    ):
        raise GateError("A1-P0 public branch head is missing")
    branch_head = branch_head_value
    installation = _mapping(
        payload.get("installation"),
        "A1-P0 installation receipt is missing",
    )
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
    environment = _mapping(
        payload.get("environment"),
        "A1-P0 environment receipt is missing",
    )
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
    _require(environment.get("runtime_state_explicit") is True, "A1-P0 state was implicit")
    return branch_head


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": os.devnull,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
    }


def _validate_public_head(
    *,
    source: Path,
    branch_head: str,
    git_executable: Path,
    started_at: float,
) -> None:
    env = _git_environment()
    prerequisite_tree = _run(
        [str(git_executable), "rev-parse", f"{PREREQUISITE_COMMIT}^{{tree}}"],
        cwd=source,
        env=env,
        started_at=started_at,
        label="A1-P0 prerequisite tree",
    ).stdout.strip()
    _require(prerequisite_tree == PREREQUISITE_TREE, "A1-P0 prerequisite tree drifted")
    _run(
        [str(git_executable), "merge-base", "--is-ancestor", PREREQUISITE_COMMIT, branch_head],
        cwd=source,
        env=env,
        started_at=started_at,
        label="A1-P0 prerequisite ancestry",
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
                label="A1-P1 public change scope",
            ).stdout.splitlines(),
        )
    )
    _require(changed == EXPECTED_CHANGED_PATHS, "A1-P1 public change scope drifted")


NETWORK_GUARD = '''"""Block Python network attempts and mark A1-P1 guard imports."""
import os
import socket


armed = os.environ.get("EVIDENCEMESH_NETWORK_GUARD_ARMED_LOG")
if armed:
    with open(armed, "a", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()}\\n")


def _deny(operation, target=None):
    marker = os.environ.get("EVIDENCEMESH_NETWORK_GUARD_LOG")
    if marker:
        with open(marker, "a", encoding="utf-8") as handle:
            handle.write(f"{operation}:{target!r}\\n")
    raise OSError("Alpha A1-P1 Python network is disabled")


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
'''


def _runtime_environment(p1_root: Path, venv: Path) -> tuple[dict[str, str], Path, Path, Path]:
    state = p1_root / "state"
    state.mkdir(mode=0o700)
    home = p1_root / "readonly-home"
    home.mkdir(mode=0o555)
    guard = p1_root / "network-guard"
    guard.mkdir(mode=0o700)
    (guard / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")
    network_log = p1_root / "blocked-network-attempts.log"
    armed_log = p1_root / "network-guard-armed.log"
    network_log.touch(mode=0o600)
    armed_log.touch(mode=0o600)
    env = {
        "EVIDENCEMESH_NETWORK_GUARD_ARMED_LOG": str(armed_log.resolve()),
        "EVIDENCEMESH_NETWORK_GUARD_LOG": str(network_log.resolve()),
        "HOME": str(home.resolve()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LOGNAME": "evidencemesh-a1-p1",
        "PATH": f"{venv / 'bin'}:{os.defpath}",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(guard.resolve()),
        "SHELL": "/bin/sh",
        "TERM": "dumb",
        "USER": "evidencemesh-a1-p1",
        "XDG_CACHE_HOME": str((home / ".cache").resolve()),
        "XDG_CONFIG_HOME": str((home / ".config").resolve()),
        "XDG_DATA_HOME": str((home / ".local/share").resolve()),
    }
    return env, home, network_log, armed_log


def _instantiate_descriptor(template: Path, output: Path, command: Path, cache: Path) -> bytes:
    payload = _json_object(template, "A1-P1 descriptor template")
    _require(_sha256_bytes(template.read_bytes()) == DESCRIPTOR_TEMPLATE_SHA256, "Template drifted")
    try:
        server = payload["mcpServers"]["evidencemesh"]
        _require(server["command"] == COMMAND_PLACEHOLDER, "Command placeholder drifted")
        _require(
            server["env"]["EVIDENCEMESH_CACHE_PATH"] == CACHE_PLACEHOLDER,
            "Cache placeholder drifted",
        )
        server["command"] = str(command.resolve())
        server["env"]["EVIDENCEMESH_CACHE_PATH"] = str(cache.resolve())
    except (KeyError, TypeError) as exc:
        raise GateError("Descriptor template shape drifted") from exc
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    _require(COMMAND_PLACEHOLDER.encode() not in raw, "Command placeholder survived")
    _require(CACHE_PLACEHOLDER.encode() not in raw, "Cache placeholder survived")
    output.write_bytes(raw)
    output.chmod(0o600)
    return raw


def _validate_journey_receipt(
    payload: dict[str, Any],
    *,
    expected_descriptor_sha256: str,
) -> None:
    _require(
        payload.get("schema_version") == "evidencemesh.alpha-a1-p1-mcp-first-run-receipt.v1",
        "A1-P1 journey receipt schema drifted",
    )
    _require(payload.get("validation") == {"errors": [], "passed": True}, "Journey did not pass")
    client = _mapping(payload.get("client"), "Journey client receipt is missing")
    _require(client.get("distribution") == "mcp", "Journey did not use the MCP SDK")
    _require(client.get("version") == EXPECTED_MCP_VERSION, "Journey MCP SDK drifted")
    _require(client.get("fastmcp_client_loaded") is False, "FastMCP client was loaded")
    configuration = _mapping(
        payload.get("configuration"),
        "Journey configuration receipt is missing",
    )
    _require(
        configuration.get("runtime_descriptor_sha256") == expected_descriptor_sha256,
        "Journey descriptor hash drifted",
    )
    _require(
        payload.get("initialization")
        == {
            "protocol_version": "2025-11-25",
            "server_name": "EvidenceMesh",
            "server_version": EXPECTED_VERSION,
        },
        "Journey initialization drifted",
    )
    _require(
        payload.get("traffic")
        == {
            "external_document_requests": 0,
            "local_prompt_gets": 1,
            "local_resource_reads": 1,
            "logical_mcp_requests": 7,
            "mcp_tool_calls": 1,
            "model_requests": 0,
            "provider_requests": 0,
            "search_calls": 0,
        },
        "Journey traffic budget drifted",
    )
    guard = _mapping(payload.get("guard"), "Journey guard receipt is missing")
    lifecycle = _mapping(payload.get("lifecycle"), "Journey lifecycle receipt is missing")
    _require(guard.get("blocked_attempts") == 0, "Network attempt observed")
    _require(guard.get("instrumented_python_processes") == 2, "Guard drifted")
    _require(lifecycle.get("session_context_exited") is True, "Session leaked")
    _require(lifecycle.get("stdio_context_exited") is True, "STDIO leaked")


def run_gate(
    *,
    work_root: Path,
    p0_receipt: Path,
    expected_head: str,
    descriptor_template: Path,
    output: Path,
    git_executable: Path,
) -> dict[str, Any]:
    started_at = time.monotonic()
    _require(work_root.is_dir(), "A1-P0 work root is missing")
    _require(
        p0_receipt.resolve() == (work_root / "runtime" / "receipt.json").resolve(),
        "P0 receipt path drifted",
    )
    p0_payload = _json_object(p0_receipt, "A1-P0 receipt")
    branch_head = _validate_p0_receipt(p0_payload)
    _validate_trigger_head(branch_head, expected_head)
    source = work_root / "source"
    _require(source.is_dir(), "A1-P0 source clone is missing")
    _validate_public_head(
        source=source,
        branch_head=branch_head,
        git_executable=git_executable,
        started_at=started_at,
    )

    repository_root = Path(__file__).resolve().parents[1]
    descriptor_template = descriptor_template.resolve()
    _require(
        descriptor_template == (repository_root / DESCRIPTOR_RELATIVE_PATH).resolve(),
        "Descriptor template path drifted",
    )
    template_bytes = descriptor_template.read_bytes()
    _require(
        _sha256_bytes(template_bytes) == DESCRIPTOR_TEMPLATE_SHA256, "Descriptor template drifted"
    )
    public_template = _run(
        [str(git_executable), "show", f"{branch_head}:{DESCRIPTOR_RELATIVE_PATH}"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="public descriptor template",
    ).stdout.encode()
    _require(public_template == template_bytes, "Workflow and public descriptor templates differ")

    p1_root = work_root / "p1-runtime"
    _require(not p1_root.exists(), "A1-P1 runtime root must not already exist")
    p1_root.mkdir(mode=0o700)
    runtime_env, readonly_home, network_log, armed_log = _runtime_environment(
        p1_root, source / ".venv"
    )
    state = p1_root / "state"
    installed_python = source / ".venv" / "bin" / "python"
    command = source / ".venv" / "bin" / "evidencemesh-mcp"
    _require(
        installed_python.is_file() and os.access(installed_python, os.X_OK), "P0 Python is missing"
    )
    _require(command.is_file() and os.access(command, os.X_OK), "P0 MCP command is missing")
    runtime_descriptor = p1_root / "evidencemesh.mcp.json"
    cache_path = state / "cache.sqlite3"
    runtime_descriptor_bytes = _instantiate_descriptor(
        descriptor_template,
        runtime_descriptor,
        command,
        cache_path,
    )

    smoke_script = repository_root / "scripts" / "smoke_official_mcp_client.py"
    public_smoke = _run(
        [str(git_executable), "show", f"{branch_head}:scripts/smoke_official_mcp_client.py"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="public official MCP client verifier",
    ).stdout.encode()
    _require(public_smoke == smoke_script.read_bytes(), "Workflow and public MCP verifiers differ")
    journey_output = p1_root / "journey.json"
    server_log = p1_root / "server.stderr.log"
    journey = _run(
        [
            str(installed_python),
            "-s",
            str(smoke_script),
            "--descriptor",
            str(runtime_descriptor),
            "--expected-command",
            str(command),
            "--expected-version",
            EXPECTED_VERSION,
            "--output",
            str(journey_output),
            "--server-log",
            str(server_log),
        ],
        cwd=state,
        env=runtime_env,
        started_at=started_at,
        label="official MCP SDK first-run journey",
    )
    journey_payload = _json_object(journey_output, "A1-P1 journey receipt")
    runtime_descriptor_sha256 = _sha256_bytes(runtime_descriptor_bytes)
    _validate_journey_receipt(
        journey_payload,
        expected_descriptor_sha256=runtime_descriptor_sha256,
    )
    _require_file_unchanged(
        runtime_descriptor,
        runtime_descriptor_bytes,
        "Runtime descriptor",
    )

    final_status = _run(
        [str(git_executable), "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        env=_git_environment(),
        started_at=started_at,
        label="post-journey candidate status",
    ).stdout
    _require(final_status == "", "A1-P1 modified the candidate source")
    _require(
        not network_log.exists() or network_log.stat().st_size == 0, "Network attempt observed"
    )
    _require(
        len(set(armed_log.read_text(encoding="utf-8").splitlines())) == 2, "Guard arming drifted"
    )
    _require(list(readonly_home.iterdir()) == [], "A1-P1 wrote inside read-only HOME")
    _require(stat.S_IMODE(readonly_home.stat().st_mode) == 0o555, "Read-only HOME mode drifted")
    _require(stat.S_IMODE(cache_path.stat().st_mode) == 0o600, "Cache mode drifted")
    _require(stat.S_IMODE(runtime_descriptor.stat().st_mode) == 0o600, "Descriptor mode drifted")

    elapsed_seconds = time.monotonic() - started_at
    _require(elapsed_seconds <= MAXIMUM_ADDITIONAL_SECONDS, "A1-P1 exceeded its budget")
    report: dict[str, Any] = {
        "schema_version": "evidencemesh.alpha-a1-p1-mcp-first-run-gate-receipt.v1",
        "prerequisite": {
            "branch": BRANCH,
            "branch_head_observed": branch_head,
            "commit_sha": PREREQUISITE_COMMIT,
            "tree_sha": PREREQUISITE_TREE,
            "p0_receipt_passed": True,
        },
        "candidate": {
            "commit_sha": SOURCE_COMMIT,
            "tree_sha": SOURCE_TREE,
            "version": EXPECTED_VERSION,
        },
        "configuration": {
            "runtime_descriptor_bytes": len(runtime_descriptor_bytes),
            "runtime_descriptor_sha256": runtime_descriptor_sha256,
            "template_sha256": DESCRIPTOR_TEMPLATE_SHA256,
            "user_descriptor_immutable_during_journey": True,
        },
        "environment": {
            "architecture": platform.machine(),
            "operating_system": "Ubuntu 24.04",
            "python": "3.11",
            "readonly_home": True,
        },
        "reuse": {
            "additional_dependency_install_attempts": 0,
            "additional_public_clone_attempts": 0,
            "p0_noneditable_installation_reused": True,
        },
        "journey": journey_payload,
        "checks": {
            "cache_private": True,
            "candidate_source_clean": True,
            "descriptor_loaded_from_disk": True,
            "official_mcp_sdk": True,
            "p0_identity_and_receipt": True,
            "python_network_guard_clear": True,
        },
        "budgets": {
            "additional_dependency_install_attempts": 0,
            "additional_elapsed_seconds": round(elapsed_seconds, 3),
            "additional_public_clone_attempts": 0,
            "client_timeout_seconds": 30,
            "logical_mcp_requests_maximum": 7,
            "maximum_additional_seconds": MAXIMUM_ADDITIONAL_SECONDS,
            "retries": 0,
            "runtime_network_requests_maximum": 0,
            "server_launch_attempts": 1,
        },
        "limitations": {
            "gui_host_validated": False,
            "live_provider_validated": False,
            "macos_validated": False,
            "mcp_host_configuration_schema_claimed_universal": False,
            "network_guard_scope": "python_socket_api",
            "operating_system_network_namespace_enforced": False,
            "quality_claim_authorized": False,
            "windows_validated": False,
        },
        "publication": {
            "artifact_uploaded": False,
            "distribution_published": False,
            "release_published": False,
            "tag_published": False,
        },
        "timings": {"journey_seconds": round(journey.elapsed_seconds, 3)},
        "validation": {"errors": [], "passed": True},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--p0-receipt", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--descriptor-template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--git", default="git")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_gate(
        work_root=args.work_root.resolve(),
        p0_receipt=args.p0_receipt.resolve(),
        expected_head=args.expected_head,
        descriptor_template=args.descriptor_template.resolve(),
        output=args.output.resolve(),
        git_executable=_resolve_executable(args.git, "git"),
    )
    json.dump(report, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
