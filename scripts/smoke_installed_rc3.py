"""Exercise an installed RC3 package without any external network request."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import evidencemesh
from evidencemesh.config import Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.governor import ClosedAlphaSession, SQLiteBudgetGovernor
from evidencemesh.models import SearchRequest
from evidencemesh.providers.wikipedia import WikipediaProvider

SMOKE_ID = "evidencemesh-installed-alpha-rc3-v1"
EXPECTED_TOOLS = [
    "search_web",
    "deep_research",
    "fetch_url",
    "batch_search",
    "verify_claim",
    "health",
]


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    path.chmod(0o700)
    return path


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


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


def _strict_environment(
    root: Path,
    *,
    participant_suffix: str,
    session_suffix: str,
) -> tuple[dict[str, str], Path]:
    ledger_root = _private_directory(root)
    ledger = ledger_root / "ledger.sqlite3"
    environment = {
        "EVIDENCEMESH_CACHE_PATH": str(ledger_root / "cache.sqlite3"),
        "EVIDENCEMESH_CLOSED_ALPHA_LEDGER": str(ledger),
        "EVIDENCEMESH_CLOSED_ALPHA_PARTICIPANT": f"p-{participant_suffix:0>16}",
        "EVIDENCEMESH_CLOSED_ALPHA_PROFILE": "community",
        "EVIDENCEMESH_CLOSED_ALPHA_SESSION": f"s-{session_suffix:0>32}",
        "EVIDENCEMESH_PROVIDERS": "wikipedia",
        "EVIDENCEMESH_TRANSPORT": "stdio",
        "HOME": str(ledger_root),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": str(ledger_root),
    }
    return environment, ledger


async def _exercise_sdk(root: Path) -> dict[str, Any]:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "query": {
                    "search": [
                        {
                            "title": "RC3",
                            "snippet": "Governed synthetic evidence",
                            "pageid": 1,
                            "wordcount": 3,
                        }
                    ]
                }
            },
        )

    ledger_root = _private_directory(root / "sdk")
    ledger = ledger_root / "ledger.sqlite3"
    governor = SQLiteBudgetGovernor(
        ledger,
        ClosedAlphaSession(
            participant_code="p-0000000000000001",
            session_code="s-00000000000000000000000000000001",
            profile="community",
        ),
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    engine = EvidenceMesh(
        Settings(enabled_providers=[], cache_path=ledger_root / "cache.sqlite3"),
        providers=[
            WikipediaProvider(
                "https://{language}.wikipedia.invalid/w/api.php",
                client,
            )
        ],
        client=client,
        governor=governor,
    )
    try:
        response = await engine.search(SearchRequest(query="rc3", use_cache=False))
        snapshot = await governor.snapshot()
        health = engine.health()
    finally:
        await engine.aclose()
        await client.aclose()

    _require(response.results[0].title == "RC3", "SDK response contract failed")
    _require(calls == 1, "SDK MockTransport count drifted")
    _require(snapshot["session_attempts"] == 1, "SDK session attempts drifted")
    _require(snapshot["global_attempts"] == 1, "SDK global attempts drifted")
    _require(snapshot["dispatched_attempts"] == 1, "SDK dispatch count drifted")
    closed_alpha = health["reliability"]["closed_alpha_governor"]
    _require(
        closed_alpha
        == {
            "enabled": True,
            "scope": "single_host_shared_sqlite",
            "distributed_global_guarantee": False,
        },
        "SDK governor health drifted",
    )
    _require(_mode(ledger_root) == 0o700, "SDK ledger directory is not private")
    _require(_mode(ledger) == 0o600, "SDK ledger file is not private")
    return {
        "mock_transport_calls": calls,
        "session_attempts": snapshot["session_attempts"],
        "global_attempts": snapshot["global_attempts"],
        "dispatched_attempts": snapshot["dispatched_attempts"],
        "governor_enabled": True,
        "scope": closed_alpha["scope"],
        "ledger_directory_mode": "0700",
        "ledger_file_mode": "0600",
    }


def _exercise_cli(root: Path, command: Path) -> dict[str, Any]:
    environment, ledger = _strict_environment(
        root / "cli",
        participant_suffix="2",
        session_suffix="2",
    )
    completed = subprocess.run(  # noqa: S603 - exact installed executable is validated.
        [str(command), "providers"],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError("Installed CLI health failed")
    health = json.loads(completed.stdout)
    closed_alpha = health["reliability"]["closed_alpha_governor"]
    providers = [row["name"] for row in health["providers"]]
    _require(closed_alpha["enabled"] is True, "CLI governor is disabled")
    _require(
        closed_alpha["scope"] == "single_host_shared_sqlite",
        "CLI governor scope drifted",
    )
    _require(
        closed_alpha["distributed_global_guarantee"] is False,
        "CLI incorrectly claims distributed enforcement",
    )
    _require(providers == ["wikipedia"], "CLI provider isolation drifted")
    _require(_mode(ledger.parent) == 0o700, "CLI ledger directory is not private")
    _require(_mode(ledger) == 0o600, "CLI ledger file is not private")

    refused = subprocess.run(  # noqa: S603 - exact installed executable is validated.
        [str(command), "serve", "--transport", "http"],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    _require(refused.returncode != 0, "CLI HTTP transport was not refused")
    refusal_output = " ".join(f"{refused.stdout}\n{refused.stderr}".split())
    _require(
        "closed-alpha governor supports one-session-per-process STDIO only" in refusal_output,
        "CLI HTTP refusal reason drifted",
    )
    return {
        "command_within_prefix": _inside_prefix(command),
        "configured_providers": providers,
        "governor_enabled": True,
        "scope": closed_alpha["scope"],
        "http_transport_refused": True,
        "provider_requests": 0,
    }


def _source_archive(distribution: Path, *, label: str) -> dict[str, Any]:
    distribution = distribution.resolve()
    _require(distribution.is_file(), "Installed source archive is missing")
    expected_name = (
        "evidencemesh-0.1.0-py3-none-any.whl" if label == "wheel" else "evidencemesh-0.1.0.tar.gz"
    )
    _require(distribution.name == expected_name, "Installed source archive name drifted")
    direct_url_text = importlib.metadata.distribution("evidencemesh").read_text("direct_url.json")
    _require(direct_url_text is not None, "Installed distribution has no direct_url.json")
    direct_url = json.loads(direct_url_text)
    _require(isinstance(direct_url, dict), "direct_url.json is not an object")
    _require(
        direct_url.get("url") == distribution.as_uri(),
        "Installed distribution direct URL differs from the tested archive",
    )
    _require(
        isinstance(direct_url.get("archive_info"), dict),
        "Installed distribution direct URL is not an archive reference",
    )
    _require(
        "dir_info" not in direct_url and "vcs_info" not in direct_url,
        "Installed distribution unexpectedly came from a directory or VCS",
    )
    return {
        "name": distribution.name,
        "sha256": _sha256_file(distribution),
        "size_bytes": distribution.stat().st_size,
        "direct_url_matches": True,
    }


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
        name="EvidenceMesh installed RC3 verifier",
        timeout=15,
        init_timeout=15,
    ) as client:
        tools = await client.list_tools()
        health = await client.call_tool("health", {})
    if not isinstance(health.data, dict):
        raise TypeError("MCP health did not return an object")
    return {
        "health": health.data,
        "tools": [tool.name for tool in tools],
    }


def _exercise_mcp(root: Path, command: Path) -> dict[str, Any]:
    environment, ledger = _strict_environment(
        root / "mcp",
        participant_suffix="3",
        session_suffix="3",
    )
    observation = asyncio.run(_exercise_mcp_async(root, command, environment))
    health = observation["health"]
    closed_alpha = health["reliability"]["closed_alpha_governor"]
    providers = [row["name"] for row in health["providers"]]
    _require(observation["tools"] == EXPECTED_TOOLS, "MCP tool inventory drifted")
    _require(closed_alpha["enabled"] is True, "MCP governor is disabled")
    _require(
        closed_alpha["scope"] == "single_host_shared_sqlite",
        "MCP governor scope drifted",
    )
    _require(
        closed_alpha["distributed_global_guarantee"] is False,
        "MCP incorrectly claims distributed enforcement",
    )
    _require(providers == ["wikipedia"], "MCP provider isolation drifted")
    _require(_mode(ledger.parent) == 0o700, "MCP ledger directory is not private")
    _require(_mode(ledger) == 0o600, "MCP ledger file is not private")
    return {
        "command_within_prefix": _inside_prefix(command),
        "configured_providers": providers,
        "governor_enabled": True,
        "scope": closed_alpha["scope"],
        "tool_inventory": observation["tools"],
        "provider_requests": 0,
    }


def run_smoke(
    *,
    label: str,
    cli_command: Path,
    mcp_command: Path,
    distribution: Path,
    work_root: Path,
    output: Path,
) -> dict[str, Any]:
    work_root = _private_directory(work_root.resolve())
    package_origin = Path(evidencemesh.__file__).resolve()
    if not _inside_prefix(package_origin):
        raise RuntimeError("EvidenceMesh was not imported from the installed environment")
    if label not in {"sdist", "wheel"}:
        raise ValueError("label must be wheel or sdist")
    for command in (cli_command, mcp_command):
        if not command.resolve().is_file() or not os.access(command.resolve(), os.X_OK):
            raise ValueError("Installed command is missing or not executable")

    report: dict[str, Any] = {
        "schema_version": 1,
        "smoke": SMOKE_ID,
        "label": label,
        "installation": {
            "package_version": importlib.metadata.version("evidencemesh"),
            "package_origin_within_isolated_prefix": True,
            "virtual_environment": sys.prefix != sys.base_prefix,
        },
        "source_archive": _source_archive(distribution, label=label),
        "sdk": asyncio.run(_exercise_sdk(work_root)),
        "cli": _exercise_cli(work_root, cli_command.resolve()),
        "mcp_stdio": _exercise_mcp(work_root, mcp_command.resolve()),
        "traffic": {
            "provider_requests": 0,
            "tavily_requests": 0,
            "model_requests": 0,
            "document_fetches": 0,
            "retries": 0,
            "fallbacks": 0,
            "repairs": 0,
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
        work_root=args.work_root,
        output=args.output,
    )


if __name__ == "__main__":
    main()
