from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.run_phase11_3_network_diagnostic import _diagnosis, _sum_telemetry


def observation(
    *,
    logical_calls: int = 1,
    adapter_invocations: int = 1,
    http_attempts: int = 1,
    http_responses: int = 0,
    circuit_skips: int = 0,
    failure_kind: str = "timeout",
) -> dict[str, object]:
    return {
        "failure_kind_counts": {failure_kind: 1} if failure_kind else {},
        "network_telemetry": {
            "logical_calls": logical_calls,
            "cache_hits": 0,
            "circuit_skips": circuit_skips,
            "adapter_invocations": adapter_invocations,
            "http_attempts": http_attempts,
            "http_responses": http_responses,
            "http_failures_without_response": http_attempts - http_responses,
            "http_status_counts": {"503": 1} if http_responses else {},
            "adapter_latency_ms": [10.0] * adapter_invocations,
            "http_attempt_latency_ms": [9.0] * http_attempts,
        },
    }


def test_phase11_3_aggregates_attempts_separately_from_circuit_skips() -> None:
    observations = [
        observation(),
        observation(),
        observation(),
        observation(
            adapter_invocations=0,
            http_attempts=0,
            circuit_skips=1,
            failure_kind="circuit_open",
        ),
    ]
    traffic = _sum_telemetry(observations)
    assert traffic["logical_calls"] == 4
    assert traffic["adapter_invocations"] == 3
    assert traffic["http_attempts"] == 3
    assert traffic["http_responses"] == 0
    assert traffic["http_failures_without_response"] == 3
    assert traffic["circuit_skips"] == 1
    assert traffic["unaccounted_before_adapter"] == 0
    assert traffic["failure_kind_counts"] == {
        "circuit_open": 1,
        "timeout": 3,
    }
    assert len(traffic["adapter_latency_ms"]) == 3
    assert len(traffic["http_attempt_latency_ms"]) == 3


@pytest.mark.parametrize(
    ("failure_kind", "expected"),
    [
        ("invalid_schema", "response_schema_failure"),
        ("invalid_json", "response_json_failure"),
        ("http_status", "http_status_failure"),
        ("dns_error", "dns_resolution_failure"),
        ("connection_error", "connection_failure"),
        ("timeout", "timeout_failure"),
    ],
)
def test_phase11_3_diagnosis_uses_bounded_failure_classes(
    failure_kind: str,
    expected: str,
) -> None:
    traffic = _sum_telemetry([observation(failure_kind=failure_kind)])
    assert _diagnosis(traffic, 0) == expected
    assert _diagnosis(traffic, 1) == "public_endpoint_returned_results"


def test_phase11_3_protocol_is_explicitly_non_scored_and_keeps_phase12_blocked() -> None:
    root = Path(__file__).parents[1]
    protocol = (root / "docs" / "benchmark-protocol-v12.md").read_text(encoding="utf-8")
    normalized = " ".join(protocol.split())
    assert "non-scored diagnostic" in protocol
    assert "maximum logical calls: 4" in protocol
    assert "Tavily calls: 0" in protocol
    assert "Gemini or other model calls: 0" in protocol
    assert "Phase 12" in protocol
    assert "CC BY-NC-SA 4.0" in protocol
    assert "no persistent, reproducibly populated index is available" in normalized


def test_phase11_3_workflow_locks_privacy_traffic_and_release_boundaries() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase11-3-network-observability.yml").read_text(
        encoding="utf-8"
    )
    assert "run_phase11_3_network_diagnostic.py" in workflow
    assert "--request-timeout-seconds 15" in workflow
    assert "--failure-threshold 3" in workflow
    assert "--recovery-seconds 300" in workflow
    assert "d5d4b4e066e2010d3e420e91dfa4a11202eeb98d61174c5c7de965e7f7eff764" in workflow
    assert 'traffic["logical_calls"] == 4' in workflow
    assert 'traffic["http_attempts"] <= 4' in workflow
    assert 'report["scored"] is False' in workflow
    assert 'report["decision"]["phase12_untouched_evaluation_allowed"] is False' in workflow
    assert 'report["decision"]["release_decision"] == "no-go"' in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" not in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" not in workflow
    assert "TAVILY_API_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
