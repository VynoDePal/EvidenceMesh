from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

from benchmarks.run_phase11_8_7_offline_runtime_timeout_hardening import (
    BENCHMARK_NAME,
    LOCKED_CONFIG_SHA256,
    LOCKED_ENGINE_SHA256,
    LOCKED_PHASE11_8_6_RESULT_SHA256,
    LOCKED_PROTOCOL_SHA256,
    LOCKED_TELEMETRY_SHA256,
    run,
)

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/benchmark-protocol-v22.md"
CONFIG = ROOT / "src/evidencemesh/config.py"
ENGINE = ROOT / "src/evidencemesh/engine.py"
TELEMETRY = ROOT / "src/evidencemesh/telemetry.py"
RUNNER = ROOT / "benchmarks/run_phase11_8_7_offline_runtime_timeout_hardening.py"
HISTORICAL = ROOT / "benchmarks/results/phase11_8_6_offline_timeout_diagnostic_2026-07-30.json"
RESULT = ROOT / "benchmarks/results/phase11_8_7_offline_runtime_timeout_hardening_2026-07-30.json"
REPORT = ROOT / "benchmarks/results/phase11_8_7_offline_runtime_timeout_hardening_2026-07-30.md"
WORKFLOW = ROOT / ".github/workflows/phase11-8-7-runtime-timeout-hardening.yml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _offline_report() -> dict[str, Any]:
    return run(
        protocol_path=PROTOCOL,
        config_path=CONFIG,
        engine_path=ENGINE,
        telemetry_path=TELEMETRY,
        historical_result_path=HISTORICAL,
    )


def test_locked_runtime_sources_and_historical_result_are_unchanged() -> None:
    assert _sha256(PROTOCOL) == LOCKED_PROTOCOL_SHA256
    assert _sha256(CONFIG) == LOCKED_CONFIG_SHA256
    assert _sha256(ENGINE) == LOCKED_ENGINE_SHA256
    assert _sha256(TELEMETRY) == LOCKED_TELEMETRY_SHA256
    assert _sha256(HISTORICAL) == LOCKED_PHASE11_8_6_RESULT_SHA256


def test_offline_report_passes_all_gates_with_exact_timeout_policy() -> None:
    report = _offline_report()
    assert report["benchmark"] == BENCHMARK_NAME
    assert len(report["gates"]) == 12
    assert all(gate["passed"] for gate in report["gates"].values())
    assert report["timeout_policy"] == {
        "connect_seconds": 5.0,
        "read_seconds": 12.0,
        "write_seconds": 10.0,
        "pool_seconds": 5.0,
        "wall_seconds": 15.0,
    }
    assert {key: value["kind"] for key, value in report["timeout_taxonomy"].items()} == {
        "connect": "connect_timeout",
        "read": "read_timeout",
        "write": "write_timeout",
        "pool": "pool_timeout",
        "httpx_unknown": "httpx_timeout_unknown",
        "provider_wall": "provider_wall_timeout",
    }


def test_offline_report_has_zero_traffic_and_preserves_boundaries() -> None:
    report = _offline_report()
    assert report["traffic"] == {
        "network_requests": 0,
        "provider_calls": 0,
        "model_calls": 0,
        "secrets_bound": 0,
        "tavily_requests": 0,
        "gemini_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
    }
    decision = report["decision"]
    assert decision["phase11_8_7_runtime_timeout_hardening_passed"] is True
    assert decision["historical_phase11_8_6_result_changed"] is False
    assert decision["future_live_run_authorized"] is False
    assert decision["phase11_9_protocol_may_be_frozen"] is False
    assert decision["phase12_authorized"] is False
    assert decision["product_provider_or_model_defaults_changed"] is False
    assert decision["users_choose_provider_model_and_credentials"] is True
    assert decision["merge_allowed"] is False
    assert decision["release_allowed"] is False
    assert decision["release_decision"] == "no-go"


def test_public_report_omits_private_fixture_and_provider_content() -> None:
    report = _offline_report()
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "PRIVATE_RUNTIME_TIMEOUT_MESSAGE_MUST_NOT_SURVIVE",
        "PRIVATE_RUNTIME_KEY",
        "private.invalid",
        "x-goog-api-key",
        "quotaMetric",
        "quotaId",
        "Naro City",
        "Project Amber began",
        "250 milliseconds",
    ):
        assert forbidden not in rendered
    assert all(value is False for value in report["privacy"].values())


def test_runner_creates_no_http_client_transport_or_network_call() -> None:
    source = inspect.getsource(
        __import__(
            "benchmarks.run_phase11_8_7_offline_runtime_timeout_hardening",
            fromlist=["run_phase11_8_7_offline_runtime_timeout_hardening"],
        )
    )
    tree = ast.parse(source)
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert calls.isdisjoint(
        {
            "AsyncClient",
            "Client",
            "HTTPTransport",
            "AsyncHTTPTransport",
            "post",
            "request",
            "send",
            "stream",
            "urlopen",
            "connect",
        }
    )


def test_workflow_is_read_only_secret_free_and_reproduces_result() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b" in workflow
    assert "${{ secrets." not in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" not in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" not in workflow
    assert "authorize_live_run" not in workflow
    assert "live-authorized" not in workflow
    assert "cmp \\" in workflow


def test_committed_result_reproduces_byte_for_byte() -> None:
    expected = (
        json.dumps(
            _offline_report(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    assert RESULT.read_text(encoding="utf-8") == expected


def test_protocol_and_report_disclose_limits() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())
    report = " ".join(REPORT.read_text(encoding="utf-8").split())
    for marker in (
        "5/12/10/5/15-second",
        "caller supplies a client",
        "sends no network, provider, search or model request",
        "legacy_request_timeout_unresolved",
        "Users retain provider, model and credential choice",
        "Phase 11.9 or Phase 12",
        "marking the draft pull request ready",
    ):
        assert marker in protocol
    for marker in (
        "12/12 offline engineering gates",
        "zero network, provider or model calls",
        "legacy_request_timeout_unresolved",
        "Phase 11.9 and Phase 12 remain blocked",
        "release and superiority claims remain no-go",
    ):
        assert marker in report
