"""Exercise an EvidenceMesh descriptor through the official Python MCP SDK."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import re
import stat
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation, TextContent, TextResourceContents
from pydantic import AnyUrl

EXPECTED_MCP_VERSION = "1.29.0"
EXPECTED_PROTOCOL_VERSION = "2025-11-25"
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
PROMPT_ARGUMENTS = {"question": "How should an EvidenceMesh client structure research?"}
EXPECTED_USER_ENV = {
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
USER_PATH_ENV = "EVIDENCEMESH_CACHE_PATH"
INSTRUMENTATION_ENV_KEYS = (
    "EVIDENCEMESH_NETWORK_GUARD_ARMED_LOG",
    "EVIDENCEMESH_NETWORK_GUARD_LOG",
    "HOME",
    "PATH",
    "PYTHONNOUSERSITE",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONPATH",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
)
LOGICAL_MCP_REQUESTS = 7
MCP_TOOL_CALLS = 1
LOCAL_RESOURCE_READS = 1
LOCAL_PROMPT_GETS = 1
READ_TIMEOUT_SECONDS = 10
CLIENT_TIMEOUT_SECONDS = 30
STDERR_BYTES_MAXIMUM = 16_384
SERVER_LOG_ERROR_MARKERS = (
    "Traceback (most recent call last):",
    "ExceptionGroup",
    "unhandled exception",
)
SERVER_LOG_LEVEL_ERROR = re.compile(r"(?im)^(?:\[[^\r\n]*\]\s+)?(?:ERROR|CRITICAL)\b")


class JourneyError(RuntimeError):
    """Raised when an A1-P1 first-run assertion does not hold."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise JourneyError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_descriptor(path: Path, expected_command: Path) -> tuple[dict[str, str], Path]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JourneyError("Descriptor is not valid UTF-8 JSON") from exc
    _require(isinstance(payload, dict), "Descriptor root must be an object")
    _require(set(payload) == {"mcpServers"}, "Descriptor root keys drifted")
    servers = payload["mcpServers"]
    _require(isinstance(servers, dict), "mcpServers must be an object")
    _require(set(servers) == {"evidencemesh"}, "Descriptor server key drifted")
    server = servers["evidencemesh"]
    _require(isinstance(server, dict), "EvidenceMesh descriptor must be an object")
    _require(set(server) == {"args", "command", "env"}, "Descriptor server keys drifted")

    command_value = server["command"]
    _require(isinstance(command_value, str), "Descriptor command must be a string")
    command = Path(command_value)
    _require(command.is_absolute(), "Descriptor command must be absolute")
    _require(command.resolve() == expected_command.resolve(), "Descriptor command drifted")
    _require(
        command.is_file() and os.access(command, os.X_OK), "Descriptor command is not executable"
    )
    _require(command.name == "evidencemesh-mcp", "Descriptor command name drifted")
    _require(server["args"] == [], "Descriptor arguments must be empty")

    user_env = server["env"]
    _require(isinstance(user_env, dict), "Descriptor env must be an object")
    expected_keys = {*EXPECTED_USER_ENV, USER_PATH_ENV}
    _require(set(user_env) == expected_keys, "Descriptor environment keys drifted")
    _require(
        all(isinstance(key, str) and isinstance(value, str) for key, value in user_env.items()),
        "Descriptor environment values must be strings",
    )
    for key, value in EXPECTED_USER_ENV.items():
        _require(user_env.get(key) == value, f"Descriptor value drifted: {key}")
    _require(set(user_env).isdisjoint(INSTRUMENTATION_ENV_KEYS), "Guard leaked into user config")
    _require(
        not any(token in key.upper() for key in user_env for token in ("TOKEN", "SECRET", "KEY")),
        "Descriptor contains a secret-shaped environment key",
    )
    cache_path = Path(user_env[USER_PATH_ENV])
    _require(cache_path.is_absolute(), "Descriptor cache path must be absolute")
    _require(cache_path.parent.is_dir(), "Descriptor cache parent is missing")
    _require(
        stat.S_IMODE(cache_path.parent.stat().st_mode) == 0o700,
        "Descriptor cache parent must use mode 0700",
    )
    _require(not cache_path.exists(), "Descriptor cache must not pre-exist")
    _require("YOUR_USER" not in str(cache_path), "Descriptor cache placeholder was not resolved")
    _require(
        "/absolute/path" not in command_value, "Descriptor command placeholder was not resolved"
    )
    return dict(user_env), cache_path


def _instrumentation_overlay() -> dict[str, str]:
    overlay: dict[str, str] = {}
    for key in INSTRUMENTATION_ENV_KEYS:
        value = os.environ.get(key)
        _require(bool(value), f"Missing harness instrumentation value: {key}")
        overlay[key] = str(value)
    return overlay


def _stderr_error_markers(value: str) -> list[str]:
    markers = [marker for marker in SERVER_LOG_ERROR_MARKERS if marker.lower() in value.lower()]
    if SERVER_LOG_LEVEL_ERROR.search(value):
        markers.append("ERROR_OR_CRITICAL_LINE")
    return markers


def _structured_health(result: Any) -> dict[str, Any]:
    _require(result.isError is False, "Health tool returned an MCP error")
    structured = result.structuredContent
    _require(isinstance(structured, dict), "Health structured content is missing")
    _require(len(result.content) == 1, "Health text content count drifted")
    text_item = result.content[0]
    _require(isinstance(text_item, TextContent), "Health content is not text")
    try:
        text_payload = json.loads(text_item.text)
    except json.JSONDecodeError as exc:
        raise JourneyError("Health text content is not JSON") from exc
    _require(text_payload == structured, "Health text and structured content differ")
    return dict(structured)


def _validate_health(health: dict[str, Any], expected_version: str) -> dict[str, Any]:
    providers = health.get("providers")
    if not isinstance(providers, list):
        raise JourneyError("Health provider inventory is missing")
    _require(len(providers) == 1, "Health provider row count drifted")
    provider = providers[0]
    if not isinstance(provider, dict) or not isinstance(provider.get("name"), str):
        raise JourneyError("Health provider row is malformed")
    provider_names = [provider["name"]]
    safety = health.get("safety")
    if not isinstance(safety, dict):
        raise JourneyError("Health safety inventory is missing")
    _require(health.get("status") == "ready", "Health status is not ready")
    _require(health.get("version") == expected_version, "Health version drifted")
    _require(health.get("deployment_profile") == "community", "Health profile drifted")
    _require(provider_names == ["wikipedia"], "Health provider isolation drifted")
    _require(health.get("configuration_warnings") == [], "Health warnings are not empty")
    _require(safety.get("private_networks_allowed") is False, "Private networks became allowed")
    _require(safety.get("dns_pinning") is True, "DNS pinning is disabled")
    return {
        "configuration_warnings": [],
        "deployment_profile": "community",
        "dns_pinning": True,
        "private_networks_allowed": False,
        "providers": provider_names,
        "status": "ready",
        "version": expected_version,
    }


async def _exercise(
    *,
    command: Path,
    server_env: dict[str, str],
    runtime_cwd: Path,
    server_log: Path,
) -> dict[str, Any]:
    session_context_exited = False
    stdio_context_exited = False
    with server_log.open("w", encoding="utf-8") as errlog:
        parameters = StdioServerParameters(
            command=str(command),
            args=[],
            env=server_env,
            cwd=runtime_cwd,
        )
        async with stdio_client(parameters, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=READ_TIMEOUT_SECONDS),
                client_info=Implementation(name="EvidenceMesh A1-P1 verifier", version="1"),
            ) as session:
                initialization = await session.initialize()
                tools_result = await session.list_tools()
                resources_result = await session.list_resources()
                prompts_result = await session.list_prompts()
                health_result = await session.call_tool("health", {})
                resource_result = await session.read_resource(AnyUrl(EXPECTED_RESOURCES[0]))
                prompt_result = await session.get_prompt(EXPECTED_PROMPTS[0], PROMPT_ARGUMENTS)
                request_count = session._request_id
            session_context_exited = True
        stdio_context_exited = True

    _require(request_count == LOGICAL_MCP_REQUESTS, "Logical MCP request budget drifted")
    _require(tools_result.nextCursor is None, "Tool pagination appeared")
    _require(resources_result.nextCursor is None, "Resource pagination appeared")
    _require(prompts_result.nextCursor is None, "Prompt pagination appeared")
    tools = [tool.name for tool in tools_result.tools]
    resources = [str(resource.uri) for resource in resources_result.resources]
    prompts = [prompt.name for prompt in prompts_result.prompts]
    _require(tools == EXPECTED_TOOLS, "Tool inventory drifted")
    _require(resources == EXPECTED_RESOURCES, "Resource inventory drifted")
    _require(prompts == EXPECTED_PROMPTS, "Prompt inventory drifted")

    health = _structured_health(health_result)
    _require(len(resource_result.contents) == 1, "Research guide content count drifted")
    guide = resource_result.contents[0]
    if not isinstance(guide, TextResourceContents):
        raise JourneyError("Research guide is not text")
    _require(str(guide.uri) == EXPECTED_RESOURCES[0], "Research guide URI drifted")
    guide_bytes = guide.text.encode("utf-8")
    _require(bool(guide_bytes), "Research guide is empty")
    _require(len(prompt_result.messages) == 1, "Prompt message count drifted")
    prompt_message = prompt_result.messages[0]
    _require(prompt_message.role == "user", "Prompt role drifted")
    if not isinstance(prompt_message.content, TextContent):
        raise JourneyError("Prompt content is not text")
    prompt_bytes = prompt_message.content.text.encode("utf-8")
    _require(bool(prompt_bytes), "Prompt is empty")

    return {
        "initialization": {
            "protocol_version": str(initialization.protocolVersion),
            "server_name": initialization.serverInfo.name,
            "server_version": initialization.serverInfo.version,
        },
        "contract": {
            "next_cursors_null": True,
            "prompts": prompts,
            "resources": resources,
            "tools": tools,
        },
        "health": health,
        "local_content": {
            "prompt_bytes": len(prompt_bytes),
            "prompt_sha256": _sha256_bytes(prompt_bytes),
            "resource_bytes": len(guide_bytes),
            "resource_sha256": _sha256_bytes(guide_bytes),
        },
        "lifecycle": {
            "server_exit_code_observed": False,
            "server_self_exit_before_sdk_termination_verified": False,
            "session_context_exited": session_context_exited,
            "stdio_context_exited": stdio_context_exited,
        },
    }


def run_journey(
    *,
    descriptor: Path,
    expected_command: Path,
    expected_version: str,
    output: Path,
    server_log: Path,
) -> dict[str, Any]:
    os.umask(0o077)
    user_env, cache_path = _load_descriptor(descriptor, expected_command)
    overlay = _instrumentation_overlay()
    _require(set(user_env).isdisjoint(overlay), "Instrumentation overlaps user configuration")
    mcp_version = importlib.metadata.version("mcp")
    _require(mcp_version == EXPECTED_MCP_VERSION, "Official MCP SDK version drifted")
    _require(
        not any(name.startswith("fastmcp.client") for name in sys.modules), "FastMCP client loaded"
    )

    server_log = server_log.resolve()
    server_log.parent.mkdir(parents=True, exist_ok=True)
    started = asyncio.get_event_loop_policy().new_event_loop()
    try:
        observation = started.run_until_complete(
            asyncio.wait_for(
                _exercise(
                    command=expected_command.resolve(),
                    server_env=user_env | overlay,
                    runtime_cwd=cache_path.parent,
                    server_log=server_log,
                ),
                timeout=CLIENT_TIMEOUT_SECONDS,
            )
        )
    finally:
        started.close()

    raw_log = server_log.read_bytes()
    _require(len(raw_log) <= STDERR_BYTES_MAXIMUM, "Server stderr exceeded its byte budget")
    try:
        decoded_log = raw_log.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JourneyError("Server stderr is not UTF-8") from exc
    markers = _stderr_error_markers(decoded_log)
    _require(not markers, "Server stderr contains an error marker")
    _require(cache_path.is_file(), "First run did not create the explicit cache")
    _require(stat.S_IMODE(cache_path.stat().st_mode) == 0o600, "Cache mode is not 0600")

    armed_log = Path(overlay["EVIDENCEMESH_NETWORK_GUARD_ARMED_LOG"])
    armed_rows = armed_log.read_text(encoding="utf-8").splitlines()
    _require(len(set(armed_rows)) == 2, "Network guard was not armed in both Python processes")
    network_log = Path(overlay["EVIDENCEMESH_NETWORK_GUARD_LOG"])
    _require(
        not network_log.exists() or network_log.stat().st_size == 0, "Network attempt observed"
    )

    initialization = observation["initialization"]
    _require(
        initialization
        == {
            "protocol_version": EXPECTED_PROTOCOL_VERSION,
            "server_name": "EvidenceMesh",
            "server_version": expected_version,
        },
        "MCP initialization identity drifted",
    )
    validated_health = _validate_health(observation["health"], expected_version)
    descriptor_bytes = descriptor.read_bytes()
    report: dict[str, Any] = {
        "schema_version": "evidencemesh.alpha-a1-p1-mcp-first-run-receipt.v1",
        "configuration": {
            "args": [],
            "bytes": len(descriptor_bytes),
            "configured_command": str(expected_command.resolve()),
            "runtime_descriptor_sha256": _sha256_bytes(descriptor_bytes),
            "secrets_present": False,
            "server_key": "evidencemesh",
            "user_env_keys": sorted(user_env),
        },
        "client": {
            "distribution": "mcp",
            "fastmcp_client_loaded": False,
            "session_api": "mcp.ClientSession",
            "transport_api": "mcp.client.stdio.stdio_client",
            "version": mcp_version,
        },
        "initialization": initialization,
        "contract": observation["contract"],
        "health": validated_health,
        "local_content": observation["local_content"],
        "lifecycle": observation["lifecycle"],
        "guard": {
            "blocked_attempts": 0,
            "claimed_as_user_configuration": False,
            "instrumented_python_processes": 2,
            "operating_system_network_namespace_enforced": False,
            "origin": "a1-p1-harness-overlay",
            "scope": "python_socket_api",
            "server_guard_import_observed": True,
        },
        "stderr": {
            "bytes": len(raw_log),
            "error_markers": [],
            "maximum_bytes": STDERR_BYTES_MAXIMUM,
            "sha256": _sha256_bytes(raw_log),
            "utf8": True,
        },
        "traffic": {
            "external_document_requests": 0,
            "local_prompt_gets": LOCAL_PROMPT_GETS,
            "local_resource_reads": LOCAL_RESOURCE_READS,
            "logical_mcp_requests": LOGICAL_MCP_REQUESTS,
            "mcp_tool_calls": MCP_TOOL_CALLS,
            "model_requests": 0,
            "provider_requests": 0,
            "search_calls": 0,
        },
        "budgets": {
            "client_timeout_seconds": CLIENT_TIMEOUT_SECONDS,
            "launch_attempts": 1,
            "logical_mcp_requests_maximum": LOGICAL_MCP_REQUESTS,
            "read_timeout_seconds": READ_TIMEOUT_SECONDS,
            "retries": 0,
        },
        "limitations": {
            "gui_host_validated": False,
            "live_provider_validated": False,
            "macos_validated": False,
            "mcp_host_configuration_schema_claimed_universal": False,
            "network_guard_scope": "python_socket_api",
            "operating_system_network_namespace_enforced": False,
            "quality_claim_authorized": False,
            "server_graceful_self_exit_verified": False,
            "windows_validated": False,
        },
        "validation": {"errors": [], "passed": True},
    }
    _write_json(output, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--expected-command", required=True, type=Path)
    parser.add_argument("--expected-version", default="0.1.0")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--server-log", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_journey(
        descriptor=args.descriptor.resolve(),
        expected_command=args.expected_command.resolve(),
        expected_version=args.expected_version,
        output=args.output.resolve(),
        server_log=args.server_log.resolve(),
    )
    json.dump(report, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
