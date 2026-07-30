from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from benchmarks import run_phase11_8_8_live_projection_calibration as live

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "benchmarks/results/phase11_8_8_live_projection_calibration_2026-07-30.json"
EXPECTED_RESULT_BYTES = 13_984
EXPECTED_RESULT_SHA256 = "03e0ad7ef2d4859848c3b4d4d8bf9d25714b9d311741f15a91ec9b3311aca25f"

QUALITY_GATE_FAILURES = {
    "selected_proxy_coverage_at_least_20_of_24",
    "v2_proxy_coverage_at_least_20_of_24",
    "v2_selected_retention_at_least_95_percent",
    "v2_paired_net_gain_vs_equal_at_least_2",
    "v2_paired_net_gain_vs_v1_at_least_2",
}
FORBIDDEN_PUBLIC_KEYS = {
    "case_id",
    "case_ids",
    "row_index",
    "row_indexes",
    "question",
    "questions",
    "answer",
    "answers",
    "gold_url",
    "gold_urls",
    "title",
    "url",
    "snippet",
    "raw_results",
    "projection_outcomes",
    "outcomes",
    "raw_pool_sha256",
    "selected_packet_sha256",
    "prompt_packet_sha256",
}


def _load_result() -> tuple[bytes, dict[str, Any]]:
    raw = RESULT.read_bytes()
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    return raw, payload


def _schema_matches(value: object, schema: object) -> bool:
    if isinstance(schema, dict):
        return (
            isinstance(value, dict)
            and set(value) == set(schema)
            and all(_schema_matches(value[key], child) for key, child in schema.items())
        )
    if isinstance(schema, list):
        return (
            isinstance(value, list)
            and len(schema) == 1
            and all(_schema_matches(item, schema[0]) for item in value)
        )
    if isinstance(schema, tuple):
        return type(value) in schema
    if schema is list:
        return isinstance(value, list)
    if schema is dict:
        return isinstance(value, dict)
    return type(value) is schema


def _walk_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            keys.extend(_walk_keys(nested))
    return keys


def _walk_strings(value: object) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for nested in value.values():
            strings.extend(_walk_strings(nested))
    elif isinstance(value, list):
        for nested in value:
            strings.extend(_walk_strings(nested))
    return strings


def test_live_result_raw_hash_and_aggregate_only_schema_are_exact() -> None:
    raw, payload = _load_result()

    assert len(raw) == EXPECTED_RESULT_BYTES
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_RESULT_SHA256
    assert _schema_matches(payload, live.PUBLIC_SCHEMA)
    assert set(payload) == {
        "authorization",
        "benchmark",
        "dataset",
        "decision",
        "dependency_manifest_sha256",
        "privacy",
        "projection",
        "protocol",
        "retrieval",
        "run_status",
        "schema_version",
        "selection",
        "source_locks",
        "traffic",
        "warnings",
    }
    assert payload["schema_version"] == 1
    assert payload["run_status"] == "completed"
    assert payload["benchmark"] == ("evidencemesh-phase11-8-8-live-projection-calibration-v2")


def test_live_result_traffic_and_privacy_are_exact() -> None:
    _, payload = _load_result()

    assert payload["protocol"]["models"] == []
    assert payload["retrieval"] == {
        "attempted_cases": 24,
        "failure_kind": None,
        "http_status_counts": {"200": 24},
        "stopped_on_first_failure": False,
        "successful_cases": 24,
    }
    traffic = payload["traffic"]
    assert {
        "http_responses": traffic["http_responses"],
        "logical_operations_completed": traffic["logical_operations_completed"],
        "logical_operations_planned": traffic["logical_operations_planned"],
        "logical_operations_started": traffic["logical_operations_started"],
        "tavily_http_attempts_actual": traffic["tavily_http_attempts_actual"],
        "tavily_http_attempts_maximum": traffic["tavily_http_attempts_maximum"],
        "tavily_requests": traffic["tavily_requests"],
    } == {
        "http_responses": 24,
        "logical_operations_completed": 24,
        "logical_operations_planned": 24,
        "logical_operations_started": 24,
        "tavily_http_attempts_actual": 24,
        "tavily_http_attempts_maximum": 24,
        "tavily_requests": 24,
    }
    assert {
        field: traffic[field]
        for field in (
            "cache_reads",
            "cache_writes",
            "fallback_requests",
            "follow_up_document_fetches",
            "gemini_requests",
            "model_requests",
            "other_provider_requests",
            "repair_requests",
            "retries",
            "token_count_requests",
        )
    } == {
        "cache_reads": 0,
        "cache_writes": 0,
        "fallback_requests": 0,
        "follow_up_document_fetches": 0,
        "gemini_requests": 0,
        "model_requests": 0,
        "other_provider_requests": 0,
        "repair_requests": 0,
        "retries": 0,
        "token_count_requests": 0,
    }
    assert payload["privacy"] == {
        "absolute_paths_found": 0,
        "api_key_found": False,
        "case_ids_found": 0,
        "forbidden_keys_found": 0,
        "gold_urls_found": 0,
        "passed": True,
        "provider_content_values_found": 0,
        "questions_found": 0,
        "reference_answers_found": 0,
        "row_indexes_found": 0,
        "strict_allowlist_passed": True,
    }

    keys = set(_walk_keys(payload))
    strings = _walk_strings(payload)
    assert keys.isdisjoint(FORBIDDEN_PUBLIC_KEYS)
    assert not any(
        re.search(r"\b(?:case_id|row_index|question|snippet)\b", value, re.IGNORECASE)
        for value in strings
    )
    assert not any(re.search(r"\bhttps?://", value, re.IGNORECASE) for value in strings)
    assert not any(
        value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value) for value in strings
    )


def test_live_result_projection_quality_and_governance_are_exact() -> None:
    _, payload = _load_result()

    projection = payload["projection"]
    assert {
        "equal_cap_prompt_proxy_hits": projection["equal_cap_prompt_proxy_hits"],
        "selected_proxy_hits": projection["selected_proxy_hits"],
        "v1_prompt_proxy_hits": projection["v1_prompt_proxy_hits"],
        "v2_prompt_proxy_hits": projection["v2_prompt_proxy_hits"],
        "v2_retention_denominator": projection["v2_retention_denominator"],
        "v2_retention_numerator": projection["v2_retention_numerator"],
        "v2_retention_rate": projection["v2_retention_rate"],
        "v2_vs_equal_net_gain": projection["v2_vs_equal_net_gain"],
        "v2_vs_v1_net_gain": projection["v2_vs_v1_net_gain"],
    } == {
        "equal_cap_prompt_proxy_hits": 16,
        "selected_proxy_hits": 18,
        "v1_prompt_proxy_hits": 17,
        "v2_prompt_proxy_hits": 17,
        "v2_retention_denominator": 18,
        "v2_retention_numerator": 17,
        "v2_retention_rate": 0.944444,
        "v2_vs_equal_net_gain": 1,
        "v2_vs_v1_net_gain": 0,
    }

    decision = payload["decision"]
    gates = {gate["name"]: gate["passed"] for gate in decision["gates"]}
    assert list(gates) == list(live.GATE_NAMES)
    assert decision["gate_count"] == len(gates) == 13
    assert decision["passed_gate_count"] == sum(gates.values()) == 8
    assert {name for name, passed in gates.items() if not passed} == QUALITY_GATE_FAILURES
    assert all(gates[name] is False for name in QUALITY_GATE_FAILURES)
    assert decision["diagnostic_status"] == "retrieval_limited_inconclusive"
    assert {
        field: decision[field]
        for field in (
            "merge_allowed",
            "phase11_9_protocol_may_be_frozen",
            "phase12_authorized",
            "phase12_executed",
            "projection_candidate_passed",
            "quality_profile_promoted",
            "release_allowed",
            "superiority_claim_allowed",
        )
    } == {
        "merge_allowed": False,
        "phase11_9_protocol_may_be_frozen": False,
        "phase12_authorized": False,
        "phase12_executed": False,
        "projection_candidate_passed": False,
        "quality_profile_promoted": False,
        "release_allowed": False,
        "superiority_claim_allowed": False,
    }
    assert decision["release_decision"] == "no-go"
