"""Exercise the installed EvidenceMesh wheel through a real MCP STDIO subprocess."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import evidencemesh

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
SMOKE_ID = "evidencemesh-installed-wheel-mcp-stdio-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _inside_prefix(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path(sys.prefix).resolve())
    except ValueError:
        return False
    return True


def _validation_errors(report: dict[str, Any], expected_version: str) -> list[str]:
    contract = report["contract"]
    initialization = report["initialization"]
    installation = report["installation"]
    errors = []
    if installation["package_version"] != expected_version:
        errors.append("installed_package_version")
    if installation["package_origin_within_isolated_prefix"] is not True:
        errors.append("package_origin")
    if installation["virtual_environment"] is not True:
        errors.append("virtual_environment")
    if initialization["server_name"] != "EvidenceMesh":
        errors.append("server_name")
    if initialization["server_version"] != expected_version:
        errors.append("server_version")
    if not initialization["protocol_version"]:
        errors.append("protocol_version")
    if contract["tools"] != EXPECTED_TOOLS:
        errors.append("tool_inventory")
    if contract["resources"] != EXPECTED_RESOURCES:
        errors.append("resource_inventory")
    if contract["prompts"] != EXPECTED_PROMPTS:
        errors.append("prompt_inventory")
    if contract["health_status"] != "ready":
        errors.append("health_status")
    if contract["configured_providers"] != ["wikipedia"]:
        errors.append("provider_isolation")
    if contract["configuration_warnings"] != []:
        errors.append("configuration_warnings")
    if contract["private_networks_allowed"] is not False:
        errors.append("private_network_policy")
    if contract["dns_pinning"] is not True:
        errors.append("dns_pinning")
    return errors


async def _exercise_mcp(
    *,
    command: str,
    server_env: dict[str, str],
    server_log: Path,
) -> dict[str, Any]:
    transport = StdioTransport(
        command=command,
        args=[],
        env=server_env,
        keep_alive=False,
        log_file=server_log,
    )

    async with Client(
        transport,
        name="EvidenceMesh installed-wheel verifier",
        timeout=15,
        init_timeout=15,
    ) as client:
        initialization = client.initialize_result
        if initialization is None:
            raise RuntimeError("MCP initialization did not return server information")
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()
        health = await client.call_tool("health", {})

    if not isinstance(health.data, dict):
        raise TypeError("The MCP health tool did not return a JSON object")
    return {
        "initialization": initialization,
        "tools": tools,
        "resources": resources,
        "prompts": prompts,
        "health": health.data,
    }


def run_smoke(
    command: Path,
    *,
    cache_path: Path,
    expected_version: str,
    output: Path,
    server_log: Path,
) -> dict[str, Any]:
    command = command.resolve()
    if not command.is_file() or not os.access(command, os.X_OK):
        raise ValueError("The MCP command must be an executable file")

    package_origin = Path(evidencemesh.__file__).resolve()
    server_log = server_log.resolve()
    server_log.parent.mkdir(parents=True, exist_ok=True)
    server_env = {
        "EVIDENCEMESH_CACHE_PATH": str(cache_path.resolve()),
        "EVIDENCEMESH_PROVIDERS": "wikipedia",
        "EVIDENCEMESH_TRANSPORT": "stdio",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONUNBUFFERED": "1",
    }
    observation = asyncio.run(
        _exercise_mcp(
            command=str(command),
            server_env=server_env,
            server_log=server_log,
        )
    )
    initialization = observation["initialization"]
    tools = observation["tools"]
    resources = observation["resources"]
    prompts = observation["prompts"]
    health = observation["health"]
    provider_rows = health.get("providers", [])
    if not isinstance(provider_rows, list):
        raise TypeError("The MCP health provider inventory is not a list")
    provider_names = [
        row.get("name")
        for row in provider_rows
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    ]
    safety = health.get("safety", {})
    if not isinstance(safety, dict):
        raise TypeError("The MCP health safety inventory is not a JSON object")

    report: dict[str, Any] = {
        "schema_version": 1,
        "smoke": SMOKE_ID,
        "scored": False,
        "installation": {
            "command_name": command.name,
            "command_sha256": _sha256(command),
            "package_version": importlib.metadata.version("evidencemesh"),
            "package_origin_within_isolated_prefix": _inside_prefix(package_origin),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "virtual_environment": sys.prefix != sys.base_prefix,
        },
        "initialization": {
            "protocol_version": initialization.protocolVersion,
            "server_name": initialization.serverInfo.name,
            "server_version": initialization.serverInfo.version,
        },
        "contract": {
            "tools": [tool.name for tool in tools],
            "resources": [str(resource.uri) for resource in resources],
            "prompts": [prompt.name for prompt in prompts],
            "health_status": health.get("status"),
            "configured_providers": provider_names,
            "configuration_warnings": health.get("configuration_warnings"),
            "private_networks_allowed": safety.get("private_networks_allowed"),
            "dns_pinning": safety.get("dns_pinning"),
        },
        "traffic": {
            "mcp_tool_calls": 1,
            "provider_search_calls": 0,
            "provider_http_requests": 0,
            "model_requests": 0,
        },
        "privacy": {
            "environment_values_in_report": False,
            "server_stderr_in_report": False,
            "secrets_required": False,
        },
    }
    errors = _validation_errors(report, expected_version)
    report["validation"] = {
        "errors": errors,
        "passed": not errors,
    }
    _write_json(output, report)
    if errors:
        raise RuntimeError(f"Installed-wheel MCP smoke failed: {', '.join(errors)}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", type=Path, required=True)
    parser.add_argument("--cache-path", type=Path, required=True)
    parser.add_argument("--expected-version", default="0.1.0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--server-log", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_smoke(
        args.command,
        cache_path=args.cache_path,
        expected_version=args.expected_version,
        output=args.output,
        server_log=args.server_log,
    )


if __name__ == "__main__":
    main()
