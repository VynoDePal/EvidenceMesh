from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from scripts import smoke_official_mcp_client as smoke
from scripts import verify_alpha_a1_p1_mcp_first_run as gate

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "alpha" / "alpha_a1_p1_mcp_first_run_policy_v1.json"
TEMPLATE = ROOT / "examples" / "evidencemesh.mcp.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _template_payload() -> dict[str, object]:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def _p0_receipt() -> dict[str, object]:
    return {
        "schema_version": "evidencemesh.alpha-a1-p0-installability-receipt.v1",
        "candidate": {
            "branch": gate.BRANCH,
            "branch_head_observed": "a" * 40,
            "commit_sha": gate.SOURCE_COMMIT,
            "tree_sha": gate.SOURCE_TREE,
        },
        "installation": {
            "attempts": 1,
            "editable": False,
            "retries": 0,
            "version": "0.1.0",
        },
        "checks": gate.EXPECTED_P0_CHECKS,
        "runtime_traffic": {
            "document_requests": 0,
            "model_requests": 0,
            "provider_requests": 0,
            "python_socket_network_attempts": 0,
        },
        "environment": {
            "architecture": "x86_64",
            "operating_system": "Ubuntu 24.04.4 LTS",
            "python_version": "3.11.15",
            "readonly_home": True,
            "runtime_state_explicit": True,
        },
        "validation": {"errors": [], "passed": True},
    }


def test_policy_pins_entry_identities_and_zero_acquisition() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["schema_version"] == "evidencemesh.alpha-a1-p1-mcp-first-run-policy.v1"
    assert policy["prerequisite"] == {
        "branch": gate.BRANCH,
        "commit_sha": gate.PREREQUISITE_COMMIT,
        "gate": "Alpha A1-P0 installability",
        "receipt_required": True,
        "tree_sha": gate.PREREQUISITE_TREE,
        "trigger_head_exact_required": True,
    }
    assert policy["candidate"] == {
        "commit_sha": gate.SOURCE_COMMIT,
        "tree_sha": gate.SOURCE_TREE,
        "version": gate.EXPECTED_VERSION,
    }
    assert policy["descriptor"]["template_sha256"] == gate.DESCRIPTOR_TEMPLATE_SHA256
    assert policy["canonical_environment"]["mcp_python_sdk"] == smoke.EXPECTED_MCP_VERSION
    assert policy["budgets"] == {
        "additional_dependency_install_attempts": 0,
        "additional_public_clone_attempts": 0,
        "client_timeout_seconds": 30,
        "external_document_requests": 0,
        "local_prompt_gets": 1,
        "local_resource_reads": 1,
        "logical_mcp_requests_maximum": 7,
        "maximum_additional_seconds": 60,
        "mcp_server_launch_attempts": 1,
        "mcp_sessions": 1,
        "mcp_tool_calls": 1,
        "model_calls": 0,
        "provider_calls": 0,
        "read_timeout_seconds": 10,
        "retries": 0,
        "runtime_network_requests": 0,
        "search_calls": 0,
    }
    assert not any(policy["authority"].values())


def test_descriptor_template_and_readme_are_exact_and_honest() -> None:
    template_bytes = TEMPLATE.read_bytes()
    payload = json.loads(template_bytes)
    server = payload["mcpServers"]["evidencemesh"]

    assert hashlib.sha256(template_bytes).hexdigest() == gate.DESCRIPTOR_TEMPLATE_SHA256
    assert server["command"] == gate.COMMAND_PLACEHOLDER
    assert server["args"] == []
    assert set(server["env"]) == {*smoke.EXPECTED_USER_ENV, smoke.USER_PATH_ENV}
    assert server["env"][smoke.USER_PATH_ENV] == gate.CACHE_PLACEHOLDER
    assert {key: server["env"][key] for key in smoke.EXPECTED_USER_ENV} == smoke.EXPECTED_USER_ENV

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stdio = readme.split("### STDIO", maxsplit=1)[1].split("### Streamable HTTP", maxsplit=1)[0]
    fenced_json = stdio.split("```json", maxsplit=1)[1].split("```", maxsplit=1)[0]
    assert json.loads(fenced_json) == payload
    normalized_stdio = " ".join(stdio.split())
    assert "configuration schema is common but is not universal" in normalized_stdio
    assert "does not prove that Wikipedia is reachable" in normalized_stdio
    assert "did not test a GUI host, macOS or native Windows" in normalized_stdio
    quick_start = readme.split("## Quick start", maxsplit=1)[1].split("## MCP setup", maxsplit=1)[0]
    assert quick_start.index("cp examples/evidencemesh.mcp.json") < quick_start.index(
        "git checkout --detach"
    )
    assert 'chmod 0600 "$ALPHA_DESCRIPTOR"' in quick_start
    assert "printf '%s\\n' \"$ALPHA_DESCRIPTOR\"" in quick_start


def test_descriptor_loader_accepts_only_instantiated_absolute_paths(tmp_path: Path) -> None:
    command = tmp_path / "install" / "bin" / "evidencemesh-mcp"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    command.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    payload = _template_payload()
    server = payload["mcpServers"]["evidencemesh"]  # type: ignore[index]
    server["command"] = str(command)  # type: ignore[index]
    server["env"][smoke.USER_PATH_ENV] = str(state / "cache.sqlite3")  # type: ignore[index]
    descriptor = tmp_path / "descriptor.json"
    descriptor.write_text(json.dumps(payload), encoding="utf-8")

    env, cache = smoke._load_descriptor(descriptor, command)

    assert cache == state / "cache.sqlite3"
    assert set(env) == {*smoke.EXPECTED_USER_ENV, smoke.USER_PATH_ENV}
    server["env"]["UNEXPECTED_ENV"] = tmp_path.name  # type: ignore[index]
    descriptor.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(smoke.JourneyError, match="environment keys"):
        smoke._load_descriptor(descriptor, command)


def test_harness_overlay_is_explicit_and_disjoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index, key in enumerate(smoke.INSTRUMENTATION_ENV_KEYS):
        monkeypatch.setenv(key, f"value-{index}")

    overlay = smoke._instrumentation_overlay()

    assert set(overlay) == set(smoke.INSTRUMENTATION_ENV_KEYS)
    assert set(overlay).isdisjoint({*smoke.EXPECTED_USER_ENV, smoke.USER_PATH_ENV})


def test_health_validation_is_fail_closed() -> None:
    health = {
        "status": "ready",
        "version": "0.1.0",
        "deployment_profile": "community",
        "providers": [{"name": "wikipedia"}],
        "configuration_warnings": [],
        "safety": {"private_networks_allowed": False, "dns_pinning": True},
    }

    assert smoke._validate_health(health, "0.1.0")["providers"] == ["wikipedia"]
    health["providers"] = [{"name": "wikipedia"}, {}]
    with pytest.raises(smoke.JourneyError, match="row count"):
        smoke._validate_health(health, "0.1.0")
    health["providers"] = [{"name": "wikipedia"}]
    health["status"] = "degraded"
    with pytest.raises(smoke.JourneyError, match="not ready"):
        smoke._validate_health(health, "0.1.0")


def test_stderr_error_markers_cover_first_and_later_lines() -> None:
    assert smoke._stderr_error_markers("INFO startup\n") == []
    assert smoke._stderr_error_markers("ERROR failed\n") == ["ERROR_OR_CRITICAL_LINE"]
    assert smoke._stderr_error_markers("INFO startup\nCRITICAL failed\n") == [
        "ERROR_OR_CRITICAL_LINE"
    ]
    assert smoke._stderr_error_markers("[08/01/26 23:21:46] ERROR failed\n") == [
        "ERROR_OR_CRITICAL_LINE"
    ]
    assert "Traceback (most recent call last):" in smoke._stderr_error_markers(
        "Traceback (most recent call last):\n"
    )


def test_official_client_is_distinct_bounded_and_has_no_search_call() -> None:
    source = (ROOT / "scripts" / "smoke_official_mcp_client.py").read_text(encoding="utf-8")

    assert "from mcp import ClientSession, StdioServerParameters" in source
    assert "from mcp.client.stdio import stdio_client" in source
    assert "from fastmcp" not in source
    assert "fastmcp.Client" not in source
    assert "read_timeout_seconds=timedelta(seconds=READ_TIMEOUT_SECONDS)" in source
    assert "timeout=CLIENT_TIMEOUT_SECONDS" in source
    assert source.count("await session.") == 7
    assert 'await session.call_tool("health", {})' in source
    assert 'call_tool("search_web"' not in source
    assert smoke.LOGICAL_MCP_REQUESTS == 7
    assert smoke.MCP_TOOL_CALLS == 1


def test_p0_receipt_validation_separates_prerequisite_and_product() -> None:
    payload = _p0_receipt()

    assert gate._validate_p0_receipt(payload) == "a" * 40
    assert gate.PREREQUISITE_COMMIT != gate.SOURCE_COMMIT
    assert gate.PREREQUISITE_TREE != gate.SOURCE_TREE
    payload["candidate"]["commit_sha"] = gate.PREREQUISITE_COMMIT  # type: ignore[index]
    with pytest.raises(gate.GateError, match="product commit"):
        gate._validate_p0_receipt(payload)


def test_runtime_environment_is_sanitized_private_and_guarded(tmp_path: Path) -> None:
    root = tmp_path / "p1"
    root.mkdir(mode=0o700)
    venv = tmp_path / "source" / ".venv"

    env, home, network_log, armed_log = gate._runtime_environment(root, venv)

    assert stat.S_IMODE((root / "state").stat().st_mode) == 0o700
    assert stat.S_IMODE(home.stat().st_mode) == 0o555
    assert list(home.iterdir()) == []
    assert env["HOME"] == str(home.resolve())
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["EVIDENCEMESH_NETWORK_GUARD_LOG"] == str(network_log.resolve())
    assert env["EVIDENCEMESH_NETWORK_GUARD_ARMED_LOG"] == str(armed_log.resolve())
    assert stat.S_IMODE(network_log.stat().st_mode) == 0o600
    assert stat.S_IMODE(armed_log.stat().st_mode) == 0o600
    assert "GITHUB_TOKEN" not in env
    guard_source = (Path(env["PYTHONPATH"]) / "sitecustomize.py").read_text(encoding="utf-8")
    assert "socket.socket.connect = _connect" in guard_source
    assert "socket.socket.sendto = _sendto" in guard_source
    assert "socket.gethostbyname = _gethostbyname" in guard_source


def test_outer_gate_reuses_p0_and_freezes_public_change_scope() -> None:
    source = (ROOT / "scripts" / "verify_alpha_a1_p1_mcp_first_run.py").read_text(encoding="utf-8")

    assert gate.MAXIMUM_ADDITIONAL_SECONDS == 60
    assert '"clone"' not in source
    assert '"sync"' not in source
    assert "merge-base" in source
    assert "PREREQUISITE_COMMIT" in source
    assert {
        ".github/workflows/ci.yml",
        "README.md",
        "alpha/alpha_a1_p1_mcp_first_run_policy_v1.json",
        "docs/alpha-a1-p1-mcp-first-run-gate-v1.md",
        "examples/evidencemesh.mcp.json",
        "scripts/smoke_official_mcp_client.py",
        "scripts/verify_alpha_a1_p1_mcp_first_run.py",
        "tests/test_alpha_a1_p1_mcp_first_run.py",
    } == gate.EXPECTED_CHANGED_PATHS


def test_runtime_descriptor_immutability_check_fails_closed(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.json"
    descriptor.write_bytes(b"before")

    gate._require_file_unchanged(descriptor, b"before", "descriptor")
    descriptor.write_bytes(b"after")
    with pytest.raises(gate.GateError, match="changed during the journey"):
        gate._require_file_unchanged(descriptor, b"before", "descriptor")


def test_triggering_pr_head_must_match_public_clone_exactly() -> None:
    head = "a" * 40

    gate._validate_trigger_head(head, head)
    with pytest.raises(gate.GateError, match="differs from the triggering PR head"):
        gate._validate_trigger_head(head, "b" * 40)
    with pytest.raises(gate.GateError, match="not a full commit SHA"):
        gate._validate_trigger_head(head, "short")


def test_ci_chains_p1_after_p0_without_publication_or_second_install() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow.split("  alpha-a1-p0-installability:", maxsplit=1)[1].split(
        "\n  container:", maxsplit=1
    )[0]
    p1_step = job.split("- name: Verify official MCP SDK first-run journey", maxsplit=1)[1]

    assert "name: Alpha A1-P0 installability" in job
    assert "ref: ${{ github.event.pull_request.head.sha }}" in job
    assert job.index("verify_alpha_a1_p0_installability.py") < job.index(
        "verify_alpha_a1_p1_mcp_first_run.py"
    )
    assert job.count("verify_alpha_a1_p0_installability.py") == 1
    assert job.count("verify_alpha_a1_p1_mcp_first_run.py") == 1
    assert "A1_P0_OUTPUT" in p1_step
    assert "A1_EXPECTED_HEAD: ${{ github.event.pull_request.head.sha }}" in p1_step
    assert '--expected-head "$A1_EXPECTED_HEAD"' in p1_step
    assert "examples/evidencemesh.mcp.json" in p1_step
    assert "git clone" not in p1_step
    assert "uv sync" not in p1_step
    assert "upload-artifact" not in job
    assert "secrets." not in job
    assert "git tag" not in job


def test_protocol_documents_entry_stop_and_request_budget() -> None:
    protocol = (ROOT / "docs" / "alpha-a1-p1-mcp-first-run-gate-v1.md").read_text(encoding="utf-8")
    normalized_protocol = " ".join(protocol.split())

    assert "## Entry criteria" in protocol
    assert "## Budgets and stop criteria" in protocol
    assert "exactly seven logical MCP requests" in normalized_protocol
    assert "zero search" in normalized_protocol
    assert "zero retry" in normalized_protocol
    assert "does not claim a proven graceful server self-exit" in normalized_protocol
    assert "not an operating-system network namespace" in normalized_protocol
    assert "leaves PR #1 in draft" in normalized_protocol
