from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import verify_alpha_a1_p3_real_host_offline as gate

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "alpha" / "alpha_a1_p3_real_host_offline_policy_v1.json"
PROTOCOL = ROOT / "docs" / "alpha-a1-p3-real-host-offline-gate-v1.md"
WORKFLOW = ROOT / ".github" / "workflows" / "alpha-a1-p3-real-host-offline.yml"
MANIFEST = ROOT / "alpha" / "a1-p3-gemini-cli" / "package.json"
LOCK = ROOT / "alpha" / "a1-p3-gemini-cli" / "package-lock.json"
REPLAY = ROOT / "alpha" / "a1-p3-gemini-cli" / "fake-responses.jsonl"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _health() -> dict[str, object]:
    return {
        "configuration_warnings": [],
        "deployment_profile": "community",
        "providers": [{"name": "wikipedia"}],
        "safety": {
            "dns_pinning": True,
            "nonstandard_ports_allowed": False,
            "private_networks_allowed": False,
            "robots_txt_respected": True,
        },
        "status": "ready",
        "version": "0.1.0",
    }


def _host_events() -> list[dict[str, object]]:
    tool_id = "mcp_evidencemesh_health__call-1"
    return [
        {"type": "init", "session_id": gate.SESSION_ID, "model": gate.MODEL_NAME},
        {"type": "message", "role": "user", "content": gate.PROMPT},
        {
            "type": "tool_use",
            "tool_name": gate.TOOL_NAME,
            "tool_id": tool_id,
            "parameters": {},
        },
        {
            "type": "tool_result",
            "tool_id": tool_id,
            "status": "success",
            "output": json.dumps(_health(), sort_keys=True),
        },
        {"type": "message", "role": "assistant", "content": gate.SENTINEL},
        {
            "type": "result",
            "status": "success",
            "stats": {
                "tool_calls": 1,
                "total_tokens": 4,
                "models": {
                    gate.MODEL_NAME: {
                        "total_tokens": 4,
                        "input_tokens": 2,
                        "output_tokens": 2,
                    }
                },
            },
        },
    ]


def _jsonl(values: list[dict[str, object]]) -> str:
    return "".join(json.dumps(value, sort_keys=True) + "\n" for value in values)


def test_policy_freezes_real_host_claim_and_honest_replay_boundary() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["schema_version"] == "evidencemesh.alpha-a1-p3-real-host-offline-policy.v1"
    assert policy["host"] == {
        "classification": "real open-source terminal AI agent and MCP host",
        "entry_sha256": gate.EXPECTED_GEMINI_ENTRY_SHA256,
        "license": "Apache-2.0",
        "model_label": gate.MODEL_NAME,
        "name": "Gemini CLI",
        "npm_integrity": gate.EXPECTED_GEMINI_INTEGRITY,
        "package": "@google/gemini-cli",
        "version": gate.EXPECTED_GEMINI_VERSION,
    }
    assert policy["claim"]["offline_replayed_agent_loop_validated"] is True
    assert policy["claim"]["live_gemini_model_validated"] is False
    assert policy["claim"]["production_authentication_validated"] is False
    assert policy["limitations"]["response_replay_is_a_real_model"] is False
    assert policy["limitations"]["external_model_semantics_validated"] is False
    assert not any(policy["authority"].values())


def test_policy_freezes_prerequisites_journey_and_budgets() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["entry_criteria"] == {
        "a1_p2_1_accepted_run_id": gate.P2_1_RUN_ID,
        "authorization_label": "alpha-a1-p3-authorized",
        "branch": gate.BRANCH,
        "exact_parent_commit": gate.PREREQUISITE_COMMIT,
        "exact_parent_tree": gate.PREREQUISITE_TREE,
        "pull_request": 1,
        "pull_request_draft": True,
        "same_repository_head": True,
    }
    assert policy["journey"]["mcp_request_sequence"] == [
        "initialize",
        "prompts/list",
        "tools/list",
        "resources/list",
        "tools/call health",
    ]
    assert policy["journey"]["only_exposed_tool"] == gate.TOOL_NAME
    assert policy["budgets"] == {
        "dependency_install_attempts": 1,
        "external_document_requests": 0,
        "external_model_requests": 0,
        "host_invocations": 1,
        "host_timeout_seconds": 60,
        "logical_mcp_requests_expected": 5,
        "logical_mcp_requests_maximum": 5,
        "maximum_p3_seconds": 240,
        "mcp_server_launches": 1,
        "mcp_sessions": 1,
        "mcp_tool_calls": 1,
        "provider_calls": 0,
        "retries": 0,
        "runtime_network_requests": 0,
        "search_calls": 0,
        "synthetic_model_turns": 2,
        "workflow_reruns": 0,
    }
    assert policy["publication"] == {
        "artifacts": 0,
        "distributions": 0,
        "releases": 0,
        "tags": 0,
    }


def test_harness_and_replay_are_exact_registry_only_inputs() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    replay = [json.loads(line) for line in REPLAY.read_text(encoding="utf-8").splitlines()]

    assert _sha256(MANIFEST) == gate.EXPECTED_PACKAGE_SHA256
    assert _sha256(LOCK) == gate.EXPECTED_LOCK_SHA256
    assert _sha256(REPLAY) == gate.EXPECTED_FAKE_RESPONSES_SHA256
    assert manifest["private"] is True
    assert manifest["engines"] == {
        "node": gate.EXPECTED_NODE_VERSION,
        "npm": gate.EXPECTED_NPM_VERSION,
    }
    assert manifest["dependencies"] == {"@google/gemini-cli": gate.EXPECTED_GEMINI_VERSION}
    assert "scripts" not in manifest
    assert lock["lockfileVersion"] == 3
    assert len(lock["packages"]) == gate.EXPECTED_LOCK_PACKAGE_COUNT
    gemini = lock["packages"]["node_modules/@google/gemini-cli"]
    assert gemini["version"] == gate.EXPECTED_GEMINI_VERSION
    assert gemini["resolved"] == gate.EXPECTED_GEMINI_TARBALL
    assert gemini["integrity"] == gate.EXPECTED_GEMINI_INTEGRITY
    for name, package in lock["packages"].items():
        if not name:
            continue
        assert package["resolved"].startswith("https://registry.npmjs.org/")
        assert package["integrity"].startswith("sha512-")
    assert len(replay) == 2
    assert [item["method"] for item in replay] == [
        "generateContentStream",
        "generateContentStream",
    ]
    assert replay[0]["response"][0]["candidates"][0]["content"]["parts"] == [
        {"functionCall": {"name": gate.TOOL_NAME, "args": {}}}
    ]
    assert replay[1]["response"][0]["candidates"][0]["content"]["parts"] == [
        {"text": gate.SENTINEL}
    ]


def test_verifier_freezes_one_parent_eight_addition_scope_and_immutables() -> None:
    assert gate.PREREQUISITE_COMMIT == "3cc75a33790be353a74641034a3c5210dfc7bc17"
    assert gate.PREREQUISITE_TREE == "21abc6024a08a5528710a5fd8e49630c8fca2c9d"
    assert len(gate.EXPECTED_CHANGED_PATHS) == 8
    assert {
        ".github/workflows/alpha-a1-p3-real-host-offline.yml",
        "alpha/a1-p3-gemini-cli/fake-responses.jsonl",
        "alpha/a1-p3-gemini-cli/package-lock.json",
        "alpha/a1-p3-gemini-cli/package.json",
        "alpha/alpha_a1_p3_real_host_offline_policy_v1.json",
        "docs/alpha-a1-p3-real-host-offline-gate-v1.md",
        "scripts/verify_alpha_a1_p3_real_host_offline.py",
        "tests/test_alpha_a1_p3_real_host_offline.py",
    } == gate.EXPECTED_CHANGED_PATHS
    assert gate.IMMUTABLE_SHA256[".github/workflows/ci.yml"] == (
        "1a7300b9126f865bc9252db9f4f62aeb84e1e35da6da288132984998c9af159e"
    )
    assert gate.IMMUTABLE_SHA256["examples/evidencemesh.mcp.json"] == (
        "81f631f82166f70d81712d7e9ab82cdb3dc20b8ba592d65ba59473faf5b4295e"
    )
    for relative, expected in gate.IMMUTABLE_SHA256.items():
        assert _sha256(ROOT / relative) == expected


def test_workflow_is_label_triggered_exact_head_one_shot_without_publication() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "types: [labeled]" in workflow
    assert "workflow_dispatch" not in workflow
    assert "github.event.label.name == 'alpha-a1-p3-authorized'" in workflow
    assert "github.event.pull_request.number == 1" in workflow
    assert "github.event.pull_request.draft == true" in workflow
    assert "github.event.pull_request.head.repo.full_name == 'VynoDePal/EvidenceMesh'" in workflow
    assert "ref: ${{ github.event.pull_request.head.sha }}" in workflow
    assert "fetch-depth: 2" in workflow
    assert 'node-version: "22.20.0"' in workflow
    assert 'cache: "npm"' not in workflow
    assert "verify_alpha_a1_p0_installability.py" in workflow
    assert "verify_alpha_a1_p3_real_host_offline.py" in workflow
    assert '--expected-head "$A1_EXPECTED_HEAD"' in workflow
    assert "upload-artifact" not in workflow
    assert "npm publish" not in workflow
    assert "gh release" not in workflow
    assert "cancel-in-progress: false" in workflow


def test_protocol_states_real_host_value_and_replay_limit_without_overclaim() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    assert "one named AI application host: Gemini CLI 0.53.1" in protocol
    assert "built-in strict `--fake-responses` engine" in protocol
    assert "it is not a real Gemini model" in protocol
    assert "does not establish live-model behavior" in protocol
    assert "exactly `initialize`, `prompts/list`, `tools/list`, `resources/list`" in protocol
    assert "zero external model requests" in protocol
    assert "not an operating-system network namespace" in protocol
    assert "does not authorize a merge, Phase 12, production deployment, or V1" in protocol


def test_host_event_validator_accepts_only_correlated_success() -> None:
    health, stats = gate._validate_host_events(_jsonl(_host_events()))

    assert health["status"] == "ready"
    assert stats["tool_calls"] == 1

    wrong_tool = copy.deepcopy(_host_events())
    wrong_tool[2]["tool_name"] = "mcp_evidencemesh_search_web"
    with pytest.raises(gate.GateError, match="another tool"):
        gate._validate_host_events(_jsonl(wrong_tool))

    failed = copy.deepcopy(_host_events())
    failed[3]["status"] = "error"
    with pytest.raises(gate.GateError, match="tool failure"):
        gate._validate_host_events(_jsonl(failed))


def test_request_trace_validator_is_exact_and_fail_closed(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    events: list[dict[str, object]] = [
        {"event": "server_start", "pid": 321},
        *[{"event": "request", "method": method} for method in gate.EXPECTED_MCP_REQUESTS],
        {"event": "notification", "method": "notifications/initialized"},
    ]
    trace.write_text(_jsonl(events), encoding="utf-8")

    receipt = gate._validate_request_trace(trace)
    assert receipt["logical_requests"] == 5
    assert receipt["server_launches"] == 1

    drifted = copy.deepcopy(events)
    drifted[3]["method"] = "resources/read"
    trace.write_text(_jsonl(drifted), encoding="utf-8")
    with pytest.raises(gate.GateError, match="request sequence"):
        gate._validate_request_trace(trace)


def test_python_guard_and_cli_arguments_lock_offline_fail_closed_controls() -> None:
    guard = gate.PYTHON_GUARD
    node_guard = gate.NODE_GUARD
    source = Path(gate.__file__).read_text(encoding="utf-8")

    assert (
        'expected = ["initialize", "prompts/list", "tools/list", "resources/list", "tools/call"]'
        in guard
    )
    assert 'params.get("name") != "health"' in guard
    assert "socket.socket.connect =" in guard
    assert "inherited forbidden environment names" in guard
    assert 'protocol !== "data:"' in node_guard
    assert 'return deny("fetch", target)' in node_guard
    assert "originalFetch(...args)" in node_guard
    assert '"--approval-mode",\n            "default"' in source
    assert '"--allowed-mcp-server-names",\n            NAMED_HOST' in source
    assert '"--fake-responses",' in source
    assert '"--output-format",\n            "stream-json"' in source
