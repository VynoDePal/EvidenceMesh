"""Verify the frozen EvidenceMesh Alpha A1-P0 public-source install path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_URL = "https://github.com/VynoDePal/EvidenceMesh.git"
BRANCH = "agent/evidencemesh-v0.1"
SOURCE_COMMIT = "145f5f923825ffeaeb485bd680bc79410ab290d1"
SOURCE_TREE = "3b36c2d3970a5e3c325a2b20260daabf23d33a29"
EXPECTED_VERSION = "0.1.0"
MAXIMUM_ELAPSED_SECONDS = 900
INSTALL_ATTEMPTS_MAX = 1
EXPECTED_ENTRY_POINTS = {
    "evidencemesh": "evidencemesh.cli:app",
    "evidencemesh-mcp": "evidencemesh.mcp_server:main",
}
EXPECTED_PACKAGE_DATA = {
    "data/federation_v1.json": ("4eb937323c2d12bb51ce5dfee5695de38a7e08569105238cd19316aa0ed130de"),
    "py.typed": "5aa7089e44073a5efd51ba6bdedc5ab11faf8e4a436318575e5c64533ba62cda",
}
EXPECTED_TOOLS = [
    "search_web",
    "deep_research",
    "fetch_url",
    "batch_search",
    "verify_claim",
    "health",
]


class GateError(RuntimeError):
    """Raised when an A1-P0 fail-closed assertion does not hold."""


@dataclass(frozen=True)
class CommandObservation:
    stdout: str
    stderr: str
    elapsed_seconds: float


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GateError(f"{label} did not emit valid JSON") from exc
    if not isinstance(payload, dict):
        raise GateError(f"{label} did not emit a JSON object")
    return payload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def _remaining_seconds(started_at: float) -> float:
    remaining = MAXIMUM_ELAPSED_SECONDS - (time.monotonic() - started_at)
    if remaining <= 0:
        raise GateError("Alpha A1-P0 exceeded its 900-second global budget")
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
        raise GateError(f"{label} exceeded the remaining global budget") from exc
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


def _base_environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", os.defpath),
    }


def _acquisition_environment(work_root: Path) -> dict[str, str]:
    home = work_root / "acquisition-home"
    home.mkdir(mode=0o700)
    env = _base_environment()
    env.update(
        {
            "GIT_ASKPASS": "",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(home),
            "UV_HTTP_RETRIES": "0",
            "UV_NO_CONFIG": "1",
            "UV_NO_PROGRESS": "1",
            "UV_NO_PYTHON_DOWNLOADS": "1",
            "XDG_CACHE_HOME": str(home / ".cache"),
        }
    )
    return env


NETWORK_GUARD = '''"""Fail closed on Python IPv4/IPv6 network attempts during A1-P0 runtime."""
import os
import socket


def _deny(operation, target=None):
    marker = os.environ.get("EVIDENCEMESH_NETWORK_GUARD_LOG")
    if marker:
        with open(marker, "a", encoding="utf-8") as handle:
            handle.write(f"{operation}:{target!r}\\n")
    raise OSError("Alpha A1-P0 runtime network is disabled")


def _connect(_socket, address):
    return _deny("socket.connect", address)


def _connect_ex(_socket, address):
    return _deny("socket.connect_ex", address)


def _create_connection(address, *args, **kwargs):
    return _deny("socket.create_connection", address)


def _getaddrinfo(host, port, *args, **kwargs):
    return _deny("socket.getaddrinfo", (host, port))


socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.create_connection = _create_connection
socket.getaddrinfo = _getaddrinfo
'''


PACKAGE_PROBE = r"""import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import evidencemesh

dist = importlib.metadata.distribution("evidencemesh")
package_root = Path(evidencemesh.__file__).resolve().parent
entry_points = {
    item.name: item.value
    for item in dist.entry_points
    if item.group == "console_scripts" and item.name.startswith("evidencemesh")
}
direct_url_entry = next(
    item for item in (dist.files or []) if str(item).endswith(".dist-info/direct_url.json")
)
direct_url_path = Path(dist.locate_file(direct_url_entry))
direct_url = json.loads(direct_url_path.read_text(encoding="utf-8"))
data_hashes = {}
for relative in ("data/federation_v1.json", "py.typed"):
    path = package_root / relative
    data_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
payload = {
    "base_prefix": sys.base_prefix,
    "data_hashes": data_hashes,
    "direct_url": direct_url,
    "direct_url_present": direct_url_path.is_file(),
    "entry_points": entry_points,
    "package_origin": str(package_root),
    "prefix": sys.prefix,
    "python_version": list(sys.version_info[:3]),
    "version": dist.version,
}
print(json.dumps(payload, sort_keys=True))
"""


def _runtime_environment(work_root: Path, venv: Path) -> tuple[dict[str, str], Path, Path]:
    runtime = work_root / "runtime"
    runtime.mkdir(mode=0o700)
    state = runtime / "state"
    state.mkdir(mode=0o700)
    home = runtime / "readonly-home"
    home.mkdir(mode=0o555)
    guard = runtime / "network-guard"
    guard.mkdir(mode=0o700)
    (guard / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")
    network_log = runtime / "blocked-network-attempts.log"
    env = _base_environment()
    env.update(
        {
            "EVIDENCEMESH_CACHE_PATH": str((state / "cache.sqlite3").resolve()),
            "EVIDENCEMESH_NETWORK_GUARD_LOG": str(network_log.resolve()),
            "EVIDENCEMESH_PROVIDERS": "wikipedia",
            "EVIDENCEMESH_TRANSPORT": "stdio",
            "FASTMCP_CHECK_FOR_UPDATES": "off",
            "FASTMCP_SHOW_SERVER_BANNER": "false",
            "HOME": str(home.resolve()),
            "PATH": f"{venv / 'bin'}:{os.defpath}",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(guard.resolve()),
            "XDG_CACHE_HOME": str((home / ".cache").resolve()),
            "XDG_CONFIG_HOME": str((home / ".config").resolve()),
            "XDG_DATA_HOME": str((home / ".local/share").resolve()),
        }
    )
    return env, home, network_log


def _validate_platform() -> dict[str, str]:
    os_release: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            os_release[key] = value.strip().strip('"')
    machine = platform.machine()
    _require(platform.system() == "Linux", "Canonical A1-P0 requires Linux")
    _require(os_release.get("ID") == "ubuntu", "Canonical A1-P0 requires Ubuntu")
    _require(os_release.get("VERSION_ID") == "24.04", "Canonical A1-P0 requires Ubuntu 24.04")
    _require(machine in {"x86_64", "amd64"}, "Canonical A1-P0 requires x86_64")
    return {
        "architecture": machine,
        "operating_system": os_release.get("PRETTY_NAME", "Ubuntu 24.04"),
    }


def _validate_package_probe(payload: dict[str, Any], source: Path, venv: Path) -> None:
    _require(payload.get("version") == EXPECTED_VERSION, "Installed version drifted")
    python_version = payload.get("python_version")
    _require(
        isinstance(python_version, list) and python_version[:2] == [3, 11],
        "Installed interpreter is not Python 3.11",
    )
    _require(payload.get("prefix") != payload.get("base_prefix"), "Install is not isolated")
    prefix = Path(str(payload.get("prefix"))).resolve()
    origin = Path(str(payload.get("package_origin"))).resolve()
    _require(prefix == venv.resolve(), "Installed prefix drifted")
    _require(origin.is_relative_to(prefix), "Package origin escaped the isolated prefix")
    _require(not origin.is_relative_to((source / "src").resolve()), "Package remained editable")
    _require(payload.get("entry_points") == EXPECTED_ENTRY_POINTS, "Console entry points drifted")
    _require(payload.get("data_hashes") == EXPECTED_PACKAGE_DATA, "Packaged data drifted")
    _require(payload.get("direct_url_present") is True, "PEP 610 provenance is missing")
    direct_url = payload.get("direct_url")
    _require(isinstance(direct_url, dict), "PEP 610 provenance is not an object")
    dir_info = direct_url.get("dir_info", {})
    _require(isinstance(dir_info, dict), "PEP 610 dir_info is not an object")
    _require(dir_info.get("editable", False) is False, "Install is editable")
    _require(
        direct_url.get("url") == source.resolve().as_uri(),
        "Install provenance does not bind the cloned source",
    )
    for executable in EXPECTED_ENTRY_POINTS:
        path = venv / "bin" / executable
        _require(path.is_file() and os.access(path, os.X_OK), f"Missing launcher: {executable}")


def _validate_providers(payload: dict[str, Any]) -> None:
    providers = payload.get("providers")
    names = [row.get("name") for row in providers] if isinstance(providers, list) else []
    safety = payload.get("safety")
    _require(payload.get("status") == "ready", "CLI health is not ready")
    _require(payload.get("version") == EXPECTED_VERSION, "CLI health version drifted")
    _require(names == ["wikipedia"], "CLI provider isolation drifted")
    _require(payload.get("configuration_warnings") == [], "CLI configuration has warnings")
    _require(isinstance(safety, dict), "CLI safety inventory is missing")
    _require(safety.get("private_networks_allowed") is False, "Private networks became allowed")
    _require(safety.get("dns_pinning") is True, "DNS pinning is disabled")


def _validate_benchmark(payload: dict[str, Any]) -> None:
    fused = payload.get("fused")
    _require(
        payload.get("benchmark") == "EvidenceMesh offline federation benchmark",
        "Offline benchmark identity drifted",
    )
    _require(payload.get("fixture_version") == 1, "Offline fixture version drifted")
    _require(payload.get("case_count") == 12, "Offline case count drifted")
    _require(isinstance(fused, dict), "Offline fused metrics are missing")
    _require(fused.get("hit_at_1") == 1.0, "Offline fused hit@1 regressed")
    _require(fused.get("hit_at_5") == 1.0, "Offline fused hit@5 regressed")
    _require(fused.get("mrr_at_10") == 1.0, "Offline fused MRR regressed")
    _require(fused.get("ndcg_at_10") == 1.0, "Offline fused NDCG regressed")
    _require(fused.get("duplicate_rate") == 0.0, "Offline duplicate rate regressed")


def _validate_mcp(payload: dict[str, Any]) -> None:
    _require(payload.get("validation") == {"errors": [], "passed": True}, "MCP smoke failed")
    contract = payload.get("contract")
    traffic = payload.get("traffic")
    _require(isinstance(contract, dict), "MCP contract is missing")
    _require(contract.get("tools") == EXPECTED_TOOLS, "MCP tool contract drifted")
    _require(contract.get("resources") == ["evidencemesh://research-guide"], "MCP resource drifted")
    _require(contract.get("prompts") == ["evidence_first_research"], "MCP prompt drifted")
    _require(contract.get("health_status") == "ready", "MCP health is not ready")
    _require(
        contract.get("configured_providers") == ["wikipedia"], "MCP provider isolation drifted"
    )
    _require(
        traffic
        == {
            "mcp_tool_calls": 1,
            "model_requests": 0,
            "provider_http_requests": 0,
            "provider_search_calls": 0,
        },
        "MCP traffic contract drifted",
    )


def run_gate(
    *,
    work_root: Path,
    output: Path,
    git_executable: Path,
    uv_executable: Path,
    python_executable: Path,
) -> dict[str, Any]:
    started_at = time.monotonic()
    _require(not work_root.exists(), "Work root must not already exist")
    _require(work_root.parent.is_dir(), "Work root parent must already exist")
    work_root.mkdir(mode=0o700)
    platform_report = _validate_platform()
    acquisition_env = _acquisition_environment(work_root)
    source = work_root / "source"

    clone = _run(
        [
            str(git_executable),
            "-c",
            "credential.helper=",
            "clone",
            "--branch",
            BRANCH,
            "--single-branch",
            "--no-tags",
            "--",
            REPOSITORY_URL,
            str(source),
        ],
        cwd=work_root,
        env=acquisition_env,
        started_at=started_at,
        label="public clone",
    )
    branch_head = _run(
        [str(git_executable), "rev-parse", "HEAD"],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="branch identity",
    ).stdout.strip()
    _run(
        [str(git_executable), "merge-base", "--is-ancestor", SOURCE_COMMIT, branch_head],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="candidate ancestry",
    )
    _run(
        [str(git_executable), "checkout", "--detach", SOURCE_COMMIT],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="candidate checkout",
    )
    observed_commit = _run(
        [str(git_executable), "rev-parse", "HEAD"],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="candidate commit",
    ).stdout.strip()
    observed_tree = _run(
        [str(git_executable), "rev-parse", "HEAD^{tree}"],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="candidate tree",
    ).stdout.strip()
    observed_remote = _run(
        [str(git_executable), "remote", "get-url", "origin"],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="candidate remote",
    ).stdout.strip()
    initial_status = _run(
        [str(git_executable), "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="candidate status",
    ).stdout
    _require(observed_commit == SOURCE_COMMIT, "Public candidate commit drifted")
    _require(observed_tree == SOURCE_TREE, "Public candidate tree drifted")
    _require(observed_remote == REPOSITORY_URL, "Public candidate remote drifted")
    _require(initial_status == "", "Public candidate is not clean")

    lock_sha256 = _sha256(source / "uv.lock")
    acquisition_env["UV_PROJECT_ENVIRONMENT"] = str((source / ".venv").resolve())
    install = _run(
        [
            str(uv_executable),
            "sync",
            "--locked",
            "--no-dev",
            "--no-editable",
            "--python",
            str(python_executable),
            "--no-config",
            "--no-python-downloads",
            "--no-cache",
        ],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="locked non-editable installation",
    )
    venv = source / ".venv"
    installed_python = venv / "bin" / "python"
    _require(installed_python.is_file(), "Installation did not create its Python runtime")

    runtime_env, readonly_home, network_log = _runtime_environment(work_root, venv)
    runtime_cwd = work_root / "runtime" / "state"
    package_observation = _run(
        [str(installed_python), "-s", "-c", PACKAGE_PROBE],
        cwd=runtime_cwd,
        env=runtime_env,
        started_at=started_at,
        label="installed package probe",
    )
    package_report = _json_object(package_observation.stdout, "installed package probe")
    _validate_package_probe(package_report, source, venv)

    cli = venv / "bin" / "evidencemesh"
    providers_observation = _run(
        [str(cli), "providers"],
        cwd=runtime_cwd,
        env=runtime_env,
        started_at=started_at,
        label="offline CLI health",
    )
    providers_report = _json_object(providers_observation.stdout, "offline CLI health")
    _validate_providers(providers_report)

    benchmark_observation = _run(
        [str(cli), "benchmark-offline"],
        cwd=runtime_cwd,
        env=runtime_env,
        started_at=started_at,
        label="offline benchmark",
    )
    benchmark_report = _json_object(benchmark_observation.stdout, "offline benchmark")
    _validate_benchmark(benchmark_report)

    repository_root = Path(__file__).resolve().parents[1]
    mcp_output = runtime_cwd / "mcp.json"
    mcp_observation = _run(
        [
            str(installed_python),
            "-s",
            str(repository_root / "scripts" / "smoke_installed_mcp.py"),
            "--command",
            str(venv / "bin" / "evidencemesh-mcp"),
            "--cache-path",
            str(runtime_cwd / "mcp-cache.sqlite3"),
            "--expected-version",
            EXPECTED_VERSION,
            "--output",
            str(mcp_output),
            "--server-log",
            str(runtime_cwd / "mcp-server.log"),
            "--inherit-runtime-guard",
        ],
        cwd=runtime_cwd,
        env=runtime_env,
        started_at=started_at,
        label="offline MCP STDIO smoke",
    )
    mcp_report = _json_object(mcp_output.read_text(encoding="utf-8"), "MCP smoke report")
    _validate_mcp(mcp_report)

    final_status = _run(
        [str(git_executable), "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        env=acquisition_env,
        started_at=started_at,
        label="post-install candidate status",
    ).stdout
    _require(final_status == "", "Installation modified tracked candidate files")
    _require(
        not network_log.exists() or network_log.stat().st_size == 0,
        "Runtime attempted network access",
    )
    _require(list(readonly_home.iterdir()) == [], "Runtime wrote inside the read-only HOME")
    _require(stat.S_IMODE(readonly_home.stat().st_mode) == 0o555, "Read-only HOME mode drifted")

    elapsed_seconds = time.monotonic() - started_at
    _require(elapsed_seconds <= MAXIMUM_ELAPSED_SECONDS, "Gate exceeded its global budget")
    report: dict[str, Any] = {
        "schema_version": "evidencemesh.alpha-a1-p0-installability-receipt.v1",
        "candidate": {
            "branch": BRANCH,
            "branch_head_observed": branch_head,
            "commit_sha": observed_commit,
            "repository_url": observed_remote,
            "tree_sha": observed_tree,
            "uv_lock_sha256": lock_sha256,
        },
        "environment": {
            **platform_report,
            "python_version": ".".join(str(item) for item in package_report["python_version"]),
            "readonly_home": True,
            "runtime_state_explicit": True,
        },
        "installation": {
            "attempts": INSTALL_ATTEMPTS_MAX,
            "command": "uv sync --locked --no-dev --no-editable",
            "dependency_acquisition_network_required": True,
            "editable": False,
            "elapsed_seconds": round(install.elapsed_seconds, 3),
            "retries": 0,
            "version": package_report["version"],
        },
        "checks": {
            "installed_package": True,
            "cli_health": True,
            "offline_benchmark": True,
            "mcp_stdio_health": True,
            "network_guard_clear": True,
            "source_remained_clean": True,
        },
        "runtime_traffic": {
            "document_requests": 0,
            "model_requests": 0,
            "python_socket_network_attempts": 0,
            "provider_requests": 0,
        },
        "budgets": {
            "dependency_install_attempts": 1,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "maximum_elapsed_seconds": MAXIMUM_ELAPSED_SECONDS,
            "public_clone_attempts": 1,
            "retries": 0,
            "runtime_network_requests_maximum": 0,
        },
        "limitations": {
            "live_provider_validated": False,
            "macos_validated": False,
            "network_guard_scope": "python_socket_api",
            "operating_system_network_namespace_enforced": False,
            "quality_claim_authorized": False,
            "reproducible_build_claim_authorized": False,
            "windows_validated": False,
        },
        "publication": {
            "artifact_uploaded": False,
            "distribution_published": False,
            "release_published": False,
            "tag_published": False,
        },
        "validation": {"errors": [], "passed": True},
        "timings": {
            "clone_seconds": round(clone.elapsed_seconds, 3),
            "mcp_seconds": round(mcp_observation.elapsed_seconds, 3),
            "package_probe_seconds": round(package_observation.elapsed_seconds, 3),
            "providers_seconds": round(providers_observation.elapsed_seconds, 3),
            "benchmark_seconds": round(benchmark_observation.elapsed_seconds, 3),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--git", default="git")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--python", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_gate(
        work_root=args.work_root.resolve(),
        output=args.output.resolve(),
        git_executable=_resolve_executable(args.git, "git"),
        uv_executable=_resolve_executable(args.uv, "uv"),
        python_executable=_resolve_executable(args.python, "Python 3.11"),
    )
    json.dump(report, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
