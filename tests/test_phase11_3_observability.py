from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.run_phase11_3_network_diagnostic import PROBES, _diagnosis, _sum_telemetry


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


def test_committed_phase11_3_result_matches_locked_diagnostic() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "phase11_3_network_diagnostic_2026-07-29.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "dba044f47aa3960fcc212c2b53cdea0470acfdc4b9816c2e6d709f71aea8d20f"
    )
    report = json.loads(result_bytes)

    assert report["diagnostic"] == "evidencemesh-phase11-3-network-observability-v1"
    assert report["scored"] is False
    assert report["environment"]["commit_sha"] == ("6a1925771048dcd0e66945ad6876512db88a8adb")
    assert report["protocol"]["sha256"] == (
        "d5d4b4e066e2010d3e420e91dfa4a11202eeb98d61174c5c7de965e7f7eff764"
    )

    traffic = report["traffic"]
    assert traffic["logical_calls"] == 4
    assert traffic["cache_hits"] == 0
    assert traffic["circuit_skips"] == 0
    assert traffic["adapter_invocations"] == 4
    assert traffic["http_attempts"] == 4
    assert traffic["http_responses"] == 3
    assert traffic["http_failures_without_response"] == 1
    assert traffic["http_status_counts"] == {"200": 3}
    assert traffic["failure_kind_counts"] == {"timeout": 1}
    assert traffic["paid_provider_requests"] == 0
    assert traffic["tavily_requests"] == 0
    assert traffic["gemini_requests"] == 0
    assert traffic["retries"] == 0

    assert [item["probe_id"] for item in report["observations"]] == [
        "probe-01",
        "probe-02",
        "probe-03",
        "probe-04",
    ]
    assert [item["result_count"] for item in report["observations"]] == [10, 0, 10, 10]
    assert report["diagnosis"] == {
        "classification": "public_endpoint_returned_results",
        "failure_cases": 1,
        "result_cases": 3,
    }
    assert report["decision"]["retrieval_candidate_evaluated"] is False
    assert report["decision"]["quality_claim_allowed"] is False
    assert report["decision"]["default_bundle_eligible"] is False
    assert report["decision"]["phase12_untouched_evaluation_allowed"] is False
    assert report["decision"]["release_ready"] is False
    assert report["decision"]["release_decision"] == "no-go"

    forbidden_keys = {
        "query",
        "question",
        "target_domains",
        "title",
        "url",
        "snippet",
        "content",
        "evidence",
        "exception_message",
        "headers",
    }

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {nested for item in value.values() for nested in keys(item)}
        if isinstance(value, list):
            return {nested for item in value for nested in keys(item)}
        return set()

    serialized = json.dumps(report, ensure_ascii=False)
    assert not forbidden_keys & keys(report)
    assert all(query not in serialized for _, query in PROBES)
