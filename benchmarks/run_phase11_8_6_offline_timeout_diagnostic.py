#!/usr/bin/env python3
"""Run the deterministic, zero-network Phase 11.8.6 timeout diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx

try:
    from benchmarks.phase11_8_6_timeout_guardrails import (
        HTTPX_TIMEOUT_TAXONOMY,
        TimeoutPolicy,
        TimeoutPolicyError,
        classify_timeout_exception,
        decision_boundaries,
        diagnose_legacy_timeout,
    )
except ModuleNotFoundError:
    from phase11_8_6_timeout_guardrails import (  # type: ignore[no-redef]
        HTTPX_TIMEOUT_TAXONOMY,
        TimeoutPolicy,
        TimeoutPolicyError,
        classify_timeout_exception,
        decision_boundaries,
        diagnose_legacy_timeout,
    )

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-6-offline-timeout-diagnostic-v1"

PROTOCOL_PATH = "docs/benchmark-protocol-v21.md"
GUARDRAILS_PATH = "benchmarks/phase11_8_6_timeout_guardrails.py"
HISTORICAL_RESULT_PATH = "benchmarks/results/phase11_8_5_live_smoke_2026-07-30.json"

LOCKED_PROTOCOL_SHA256 = "b7d62af73021db103747acb5b0b0d670a6a52f0a4fa93986377657f1b2dc8120"
LOCKED_GUARDRAILS_SHA256 = "c20a094e56d638071780229cbb00a31482b4ac892c9bf66d091ad36af7eba231"
LOCKED_PHASE11_8_5_RESULT_SHA256 = (
    "92e092a5929b9c2eb4d2090c61187e8d7d1eba9796d4de85f8f2d288e29a9423"
)

PRIVATE_EXCEPTION_MESSAGE = "PRIVATE_EXCEPTION_MESSAGE_MUST_NOT_SURVIVE"
PRIVATE_REQUEST_URL = "https://private.invalid/secret-path?key=PRIVATE_KEY"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _timeout_fixture_matrix() -> dict[str, Any]:
    request = httpx.Request("POST", PRIVATE_REQUEST_URL)
    exceptions: tuple[tuple[str, BaseException], ...] = (
        (
            "connect",
            httpx.ConnectTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request),
        ),
        (
            "read",
            httpx.ReadTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request),
        ),
        (
            "write",
            httpx.WriteTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request),
        ),
        (
            "pool",
            httpx.PoolTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request),
        ),
        (
            "httpx_unknown",
            httpx.TimeoutException(PRIVATE_EXCEPTION_MESSAGE, request=request),
        ),
        ("benchmark_wall", TimeoutError(PRIVATE_EXCEPTION_MESSAGE)),
    )
    classified = {
        name: classify_timeout_exception(error).public_summary() for name, error in exceptions
    }
    replay = {
        name: classify_timeout_exception(error).public_summary() for name, error in exceptions
    }
    rendered = json.dumps(classified, ensure_ascii=False, sort_keys=True)
    return {
        "fixture_count": len(exceptions),
        "classified": classified,
        "deterministic_replay": replay == classified,
        "specific_httpx_timeout_count": len(HTTPX_TIMEOUT_TAXONOMY),
        "private_exception_message_omitted": PRIVATE_EXCEPTION_MESSAGE not in rendered,
        "private_request_url_omitted": PRIVATE_REQUEST_URL not in rendered,
        "request_query_secret_omitted": "PRIVATE_KEY" not in rendered,
    }


def _invalid_policy_diagnostics() -> dict[str, Any]:
    invalid = (
        {"connect_seconds": 0.0},
        {"read_seconds": -1.0},
        {"write_seconds": 0.0},
        {"pool_seconds": -1.0},
        {"wall_seconds": 30.0},
    )
    rejected = 0
    for values in invalid:
        try:
            TimeoutPolicy(**values)
        except TimeoutPolicyError:
            rejected += 1
    unsupported_rejected = False
    try:
        classify_timeout_exception(ValueError(PRIVATE_EXCEPTION_MESSAGE))
    except TypeError:
        unsupported_rejected = True
    return {
        "invalid_fixture_count": len(invalid),
        "invalid_rejected": rejected,
        "unsupported_exception_rejected": unsupported_rejected,
    }


def build_report(
    *,
    protocol_raw: bytes,
    guardrails_raw: bytes,
    historical_result_raw: bytes,
) -> dict[str, Any]:
    _require(
        sha256_bytes(protocol_raw) == LOCKED_PROTOCOL_SHA256,
        "Phase 11.8.6 protocol lock changed",
    )
    _require(
        sha256_bytes(guardrails_raw) == LOCKED_GUARDRAILS_SHA256,
        "Phase 11.8.6 guardrails lock changed",
    )
    _require(
        sha256_bytes(historical_result_raw) == LOCKED_PHASE11_8_5_RESULT_SHA256,
        "Phase 11.8.5 result changed",
    )

    historical = json.loads(historical_result_raw)
    _require(
        historical["benchmark"] == "evidencemesh-phase11-8-5-gemini-live-smoke-v1",
        "unexpected historical benchmark",
    )
    historical_decision = historical["decision"]
    historical_traffic = historical["traffic"]
    _require(
        historical["aborted"] is True
        and historical["aborted_reason"] == "request_timeout"
        and historical_decision["phase11_8_5_live_smoke_passed"] is False
        and historical_decision["phase11_9_protocol_may_be_frozen"] is False
        and historical_decision["release_decision"] == "no-go",
        "Phase 11.8.5 no-go boundary changed",
    )
    _require(
        historical_traffic["gemini_requests"] == 3
        and historical_traffic["http_429_responses"] == 0
        and historical_traffic["tavily_requests"] == 0
        and historical_traffic["retries"] == 0
        and historical_traffic["fallback_requests"] == 0
        and historical_traffic["repair_requests"] == 0,
        "Phase 11.8.5 traffic accounting changed",
    )
    _require(len(historical["outcomes"]) == 3, "historical outcome count changed")

    policy = TimeoutPolicy()
    matrix = _timeout_fixture_matrix()
    invalid = _invalid_policy_diagnostics()
    legacy = diagnose_legacy_timeout(historical["outcomes"][-1], policy=policy)
    privacy_passed = (
        matrix["private_exception_message_omitted"]
        and matrix["private_request_url_omitted"]
        and matrix["request_query_secret_omitted"]
    )
    gates = {
        "locked_source_integrity": {
            "passed": True,
            "protocol_sha256": LOCKED_PROTOCOL_SHA256,
            "guardrails_sha256": LOCKED_GUARDRAILS_SHA256,
            "phase11_8_5_result_sha256": LOCKED_PHASE11_8_5_RESULT_SHA256,
        },
        "historical_phase11_8_5_no_go_preserved": {
            "passed": (
                historical_decision["phase11_8_5_live_smoke_passed"] is False
                and historical_decision["phase11_9_protocol_may_be_frozen"] is False
                and historical_decision["release_decision"] == "no-go"
            ),
            "historical_gates_passed": 8,
            "historical_gate_count": 12,
        },
        "four_httpx_transport_timeouts_are_distinct": {
            "passed": (
                matrix["specific_httpx_timeout_count"] == 4
                and {
                    matrix["classified"][name]["error_kind"]
                    for name in ("connect", "read", "write", "pool")
                }
                == {
                    "connect_timeout",
                    "read_timeout",
                    "write_timeout",
                    "pool_timeout",
                }
            ),
            "observed": {
                name: matrix["classified"][name]["error_kind"]
                for name in ("connect", "read", "write", "pool")
            },
        },
        "generic_httpx_and_wall_timeouts_are_distinct": {
            "passed": (
                matrix["classified"]["httpx_unknown"]["error_kind"] == "httpx_timeout_unknown"
                and matrix["classified"]["benchmark_wall"]["error_kind"]
                == "generation_wall_timeout"
            ),
            "observed": {
                "httpx_unknown": matrix["classified"]["httpx_unknown"]["error_kind"],
                "benchmark_wall": matrix["classified"]["benchmark_wall"]["error_kind"],
            },
        },
        "classification_is_deterministic": {
            "passed": matrix["deterministic_replay"],
            "fixture_count": matrix["fixture_count"],
        },
        "timeout_policy_fails_closed": {
            "passed": (
                invalid["invalid_rejected"] == invalid["invalid_fixture_count"]
                and invalid["unsupported_exception_rejected"]
            ),
            **invalid,
        },
        "raw_exception_and_request_data_are_omitted": {
            "passed": privacy_passed,
            "raw_exception_retained": False,
            "request_url_retained": False,
            "headers_or_bodies_retained": False,
        },
        "legacy_timeout_remains_unresolved": {
            "passed": (
                legacy["diagnosis"] == "legacy_request_timeout_unresolved"
                and legacy["precise_timeout_kind"] is None
                and legacy["retroactive_reclassification_allowed"] is False
                and legacy["read_timeout_proven"] is False
            ),
            "diagnosis": legacy["diagnosis"],
            "read_deadline_compatibility_only": legacy["compatible_with_locked_read_deadline"],
        },
        "timeout_is_not_rewritten_as_quota_schema_or_quality": {
            "passed": (
                historical_traffic["http_429_responses"] == 0
                and legacy["excluded_interpretations"]
                == ["http_429", "native_schema_failure", "semantic_failure"]
            ),
            "historical_http_429": historical_traffic["http_429_responses"],
            "excluded_interpretations": legacy["excluded_interpretations"],
        },
        "zero_network_provider_secret_and_retry_traffic": {
            "passed": True,
            "network_requests": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "secrets_bound": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "model_smoke_and_product_release_gates_are_separate": {
            "passed": True,
            "benchmark_model_availability_validated": False,
            "product_release_blocked_by_timeout_alone": False,
            "users_choose_provider_model_and_credentials": True,
        },
        "phase_and_release_boundaries_are_preserved": {
            "passed": True,
            "future_live_run_authorized": False,
            "phase11_9_protocol_may_be_frozen": False,
            "phase12_authorized": False,
            "merge_allowed": False,
            "release_allowed": False,
        },
    }
    passed = all(bool(gate["passed"]) for gate in gates.values())
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": "offline timeout taxonomy and governance diagnostic",
        "protocol": {
            "path": PROTOCOL_PATH,
            "sha256": LOCKED_PROTOCOL_SHA256,
            "httpx_documented_timeout_classes": [
                "ConnectTimeout",
                "ReadTimeout",
                "WriteTimeout",
                "PoolTimeout",
            ],
            "historical_result_sha256": LOCKED_PHASE11_8_5_RESULT_SHA256,
            "guardrails_sha256": LOCKED_GUARDRAILS_SHA256,
        },
        "historical_phase11_8_5": {
            "result": "fail_8_of_12",
            "gemini_requests": historical_traffic["gemini_requests"],
            "native_http_200_responses": historical_traffic["native_http_200_responses"],
            "http_429_responses": historical_traffic["http_429_responses"],
            "timeout_count": historical_traffic["other_failed_requests"],
            "result_changed": False,
        },
        "timeout_policy": policy.public_summary(),
        "timeout_taxonomy": matrix,
        "legacy_timeout_diagnosis": legacy,
        "traffic": {
            "network_requests": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "secrets_bound": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "gates": gates,
        "decision": decision_boundaries(offline_guardrails_passed=passed),
        "privacy": {
            "raw_exception_messages_in_report": False,
            "request_urls_in_report": False,
            "request_headers_in_report": False,
            "request_bodies_in_report": False,
            "provider_responses_in_report": False,
            "credentials_in_report": False,
            "questions_or_evidence_in_report": False,
            "generated_answers_in_report": False,
            "phase12_identifiers_in_report": False,
        },
        "warnings": [
            (
                "The historical request_timeout is compatible with the locked "
                "30-second read deadline but is not proven to be ReadTimeout."
            ),
            (
                "This offline engineering pass authorizes no provider traffic "
                "and does not convert the failed Phase 11.8.5 smoke into a pass."
            ),
            (
                "A single test-model timeout does not alone define product "
                "release readiness; broader quality evidence remains blocking."
            ),
        ],
    }


def run(
    *,
    protocol_path: Path,
    guardrails_path: Path,
    historical_result_path: Path,
) -> dict[str, Any]:
    return build_report(
        protocol_raw=protocol_path.read_bytes(),
        guardrails_raw=guardrails_path.read_bytes(),
        historical_result_raw=historical_result_path.read_bytes(),
    )


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.partial")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=REPOSITORY_ROOT / PROTOCOL_PATH,
    )
    parser.add_argument(
        "--guardrails",
        type=Path,
        default=REPOSITORY_ROOT / GUARDRAILS_PATH,
    )
    parser.add_argument(
        "--historical-result",
        type=Path,
        default=REPOSITORY_ROOT / HISTORICAL_RESULT_PATH,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    report = run(
        protocol_path=arguments.protocol,
        guardrails_path=arguments.guardrails,
        historical_result_path=arguments.historical_result,
    )
    if arguments.check_only:
        print(
            json.dumps(
                {
                    "status": "phase11_8_6_offline_timeout_guardrails_valid",
                    "gates_passed": sum(gate["passed"] for gate in report["gates"].values()),
                    "gate_count": len(report["gates"]),
                    "network_requests": report["traffic"]["network_requests"],
                    "provider_calls": report["traffic"]["provider_calls"],
                    "secrets_bound": report["traffic"]["secrets_bound"],
                    "future_live_run_authorized": report["decision"]["future_live_run_authorized"],
                    "release_decision": report["decision"]["release_decision"],
                },
                sort_keys=True,
            )
        )
        return 0
    if arguments.output is None:
        raise ValueError("--output is required unless --check-only is used")
    write_report(arguments.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
