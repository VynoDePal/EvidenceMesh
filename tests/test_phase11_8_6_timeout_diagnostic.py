from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from benchmarks.phase11_8_6_timeout_guardrails import (
    HTTPX_TIMEOUT_TAXONOMY,
    TimeoutPolicy,
    TimeoutPolicyError,
    classify_timeout_exception,
    decision_boundaries,
    diagnose_legacy_timeout,
)
from benchmarks.run_phase11_8_6_offline_timeout_diagnostic import (
    BENCHMARK_NAME,
    LOCKED_GUARDRAILS_SHA256,
    LOCKED_PHASE11_8_5_RESULT_SHA256,
    LOCKED_PROTOCOL_SHA256,
    run,
)

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/benchmark-protocol-v21.md"
GUARDRAILS = ROOT / "benchmarks/phase11_8_6_timeout_guardrails.py"
RUNNER = ROOT / "benchmarks/run_phase11_8_6_offline_timeout_diagnostic.py"
HISTORICAL = ROOT / "benchmarks/results/phase11_8_5_live_smoke_2026-07-30.json"
RESULT = ROOT / "benchmarks/results/phase11_8_6_offline_timeout_diagnostic_2026-07-30.json"
REPORT = ROOT / "benchmarks/results/phase11_8_6_offline_timeout_diagnostic_2026-07-30.md"
WORKFLOW = ROOT / ".github/workflows/phase11-8-6-timeout-diagnostic.yml"

PRIVATE_MESSAGE = "PRIVATE_TIMEOUT_MESSAGE"
PRIVATE_URL = "https://private.invalid/path?key=PRIVATE_VALUE"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _offline_report() -> dict[str, Any]:
    return run(
        protocol_path=PROTOCOL,
        guardrails_path=GUARDRAILS,
        historical_result_path=HISTORICAL,
    )


def _request() -> httpx.Request:
    return httpx.Request("POST", PRIVATE_URL)


def test_locked_sources_and_historical_no_go_are_unchanged() -> None:
    assert _sha256(PROTOCOL) == LOCKED_PROTOCOL_SHA256
    assert _sha256(GUARDRAILS) == LOCKED_GUARDRAILS_SHA256
    assert _sha256(HISTORICAL) == LOCKED_PHASE11_8_5_RESULT_SHA256

    historical = json.loads(HISTORICAL.read_bytes())
    assert historical["aborted_reason"] == "request_timeout"
    assert historical["decision"]["phase11_8_5_live_smoke_passed"] is False
    assert historical["decision"]["phase11_9_protocol_may_be_frozen"] is False
    assert historical["decision"]["release_decision"] == "no-go"


def test_timeout_policy_preserves_specific_transport_diagnosis() -> None:
    policy = TimeoutPolicy()
    assert policy.public_summary() == {
        "connect_seconds": 20.0,
        "read_seconds": 30.0,
        "write_seconds": 20.0,
        "pool_seconds": 20.0,
        "wall_seconds": 45.0,
    }
    assert policy.wall_seconds > max(
        policy.connect_seconds,
        policy.read_seconds,
        policy.write_seconds,
        policy.pool_seconds,
    )


@pytest.mark.parametrize(
    "values",
    [
        {"connect_seconds": 0.0},
        {"read_seconds": 0.0},
        {"write_seconds": -1.0},
        {"pool_seconds": -1.0},
        {"wall_seconds": 30.0},
    ],
)
def test_invalid_timeout_policy_fails_closed(values: dict[str, float]) -> None:
    with pytest.raises(TimeoutPolicyError):
        TimeoutPolicy(**values)


@pytest.mark.parametrize(
    ("error_type", "expected_kind", "expected_layer"),
    [
        (httpx.ConnectTimeout, "connect_timeout", "transport_connect"),
        (httpx.ReadTimeout, "read_timeout", "transport_read"),
        (httpx.WriteTimeout, "write_timeout", "transport_write"),
        (httpx.PoolTimeout, "pool_timeout", "connection_pool"),
    ],
)
def test_specific_httpx_timeouts_are_classified_without_raw_data(
    error_type: type[httpx.TimeoutException],
    expected_kind: str,
    expected_layer: str,
) -> None:
    diagnostic = classify_timeout_exception(
        error_type(PRIVATE_MESSAGE, request=_request())
    ).public_summary()
    assert diagnostic == {
        "error_kind": expected_kind,
        "layer": expected_layer,
        "provider_response_observed": False,
        "retry_allowed_in_scored_run": False,
        "raw_exception_retained": False,
        "request_url_retained": False,
    }
    rendered = json.dumps(diagnostic)
    assert PRIVATE_MESSAGE not in rendered
    assert PRIVATE_URL not in rendered
    assert "PRIVATE_VALUE" not in rendered


def test_generic_httpx_and_benchmark_wall_timeouts_remain_distinct() -> None:
    generic = classify_timeout_exception(
        httpx.TimeoutException(PRIVATE_MESSAGE, request=_request())
    )
    wall = classify_timeout_exception(TimeoutError(PRIVATE_MESSAGE))
    assert generic.error_kind == "httpx_timeout_unknown"
    assert generic.layer == "transport_unknown"
    assert wall.error_kind == "generation_wall_timeout"
    assert wall.layer == "benchmark_wall"
    with pytest.raises(TypeError):
        classify_timeout_exception(ValueError(PRIVATE_MESSAGE))


def test_taxonomy_contains_exactly_the_four_documented_httpx_subclasses() -> None:
    assert (
        (httpx.ConnectTimeout, "connect_timeout", "transport_connect"),
        (httpx.ReadTimeout, "read_timeout", "transport_read"),
        (httpx.WriteTimeout, "write_timeout", "transport_write"),
        (httpx.PoolTimeout, "pool_timeout", "connection_pool"),
    ) == HTTPX_TIMEOUT_TAXONOMY


def test_historical_timeout_is_not_retroactively_reclassified() -> None:
    historical = json.loads(HISTORICAL.read_bytes())
    diagnostic = diagnose_legacy_timeout(
        historical["outcomes"][-1],
        policy=TimeoutPolicy(),
    )
    assert diagnostic["diagnosis"] == "legacy_request_timeout_unresolved"
    assert diagnostic["precise_timeout_kind"] is None
    assert diagnostic["retroactive_reclassification_allowed"] is False
    assert diagnostic["compatible_with_locked_read_deadline"] is True
    assert diagnostic["read_timeout_proven"] is False
    assert diagnostic["excluded_interpretations"] == [
        "http_429",
        "native_schema_failure",
        "semantic_failure",
    ]


@pytest.mark.parametrize(
    "outcome",
    [
        {"error_kind": "other"},
        {
            "error_kind": "request_timeout",
            "native_http_200": True,
            "http_status": 200,
            "latency_ms": 30_000,
        },
        {
            "error_kind": "request_timeout",
            "native_http_200": False,
            "http_status": None,
            "latency_ms": -1,
        },
        {
            "error_kind": "request_timeout",
            "native_http_200": False,
            "http_status": None,
            "latency_ms": True,
        },
    ],
)
def test_invalid_historical_timeout_evidence_fails_closed(
    outcome: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        diagnose_legacy_timeout(outcome, policy=TimeoutPolicy())


def test_decision_boundary_separates_model_smoke_from_product_governance() -> None:
    decision = decision_boundaries(offline_guardrails_passed=True)
    assert decision["offline_timeout_guardrails_passed"] is True
    assert decision["phase11_8_5_live_smoke_passed"] is False
    assert decision["benchmark_model_availability_validated"] is False
    assert decision["future_live_run_authorized"] is False
    assert decision["product_release_blocked_by_phase11_8_5_timeout_alone"] is False
    assert decision["product_release_decision_uses_broader_quality_evidence"] is True
    assert decision["users_choose_provider_model_and_credentials"] is True
    assert decision["release_decision"] == "no-go"


def test_offline_report_passes_all_gates_without_authorizing_live_work() -> None:
    report = _offline_report()
    assert report["benchmark"] == BENCHMARK_NAME
    assert len(report["gates"]) == 12
    assert all(gate["passed"] for gate in report["gates"].values())
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
    assert report["historical_phase11_8_5"] == {
        "result": "fail_8_of_12",
        "gemini_requests": 3,
        "native_http_200_responses": 2,
        "http_429_responses": 0,
        "timeout_count": 1,
        "result_changed": False,
    }
    assert report["decision"]["future_live_run_authorized"] is False
    assert report["decision"]["phase11_9_protocol_may_be_frozen"] is False
    assert report["decision"]["phase12_authorized"] is False
    assert report["decision"]["merge_allowed"] is False
    assert report["decision"]["release_allowed"] is False


def test_public_report_omits_private_fixture_and_provider_content() -> None:
    rendered = json.dumps(_offline_report(), ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "PRIVATE_EXCEPTION_MESSAGE_MUST_NOT_SURVIVE",
        "PRIVATE_TIMEOUT_MESSAGE",
        "PRIVATE_KEY",
        "PRIVATE_VALUE",
        "private.invalid",
        "x-goog-api-key",
        "quotaMetric",
        "quotaId",
        "Naro City",
        "Project Amber began",
        "250 milliseconds",
    ):
        assert forbidden not in rendered
    assert all(value is False for value in _offline_report()["privacy"].values())


def test_offline_sources_create_no_client_transport_or_network_call() -> None:
    forbidden_calls = {
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
    for module in (
        __import__(
            "benchmarks.phase11_8_6_timeout_guardrails",
            fromlist=["phase11_8_6_timeout_guardrails"],
        ),
        __import__(
            "benchmarks.run_phase11_8_6_offline_timeout_diagnostic",
            fromlist=["run_phase11_8_6_offline_timeout_diagnostic"],
        ),
    ):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        assert calls.isdisjoint(forbidden_calls)


def test_workflow_is_read_only_secret_free_and_offline_only() -> None:
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


def test_committed_result_reproduces_and_report_discloses_boundaries() -> None:
    assert RESULT.is_file()
    assert REPORT.is_file()
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
    report = " ".join(REPORT.read_text(encoding="utf-8").split())
    for marker in (
        "12/12",
        "zero network or provider call",
        "legacy_request_timeout_unresolved",
        "does not, by itself, block product release",
        "Phase 11.9 and Phase 12 remain blocked",
        "release remains no-go",
    ):
        assert marker in report


def test_protocol_discloses_no_rerun_and_release_boundaries() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())
    for marker in (
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "legacy_request_timeout_unresolved",
        "no future live traffic",
        "Users retain provider, model and credential choice",
        "Phase 11.9 or Phase 12",
        "merge, release, public alpha",
    ):
        assert marker in protocol
