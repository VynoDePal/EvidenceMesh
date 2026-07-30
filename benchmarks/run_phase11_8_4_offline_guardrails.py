#!/usr/bin/env python3
"""Run the deterministic, zero-network Phase 11.8.4 guardrail evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import pairwise
from pathlib import Path
from typing import Any

try:
    from benchmarks.phase11_8_2_candidate import (
        DirectAnswerResponseError,
        direct_answer_response_schema,
        parse_direct_answer,
    )
    from benchmarks.phase11_8_4_guardrails import (
        OBSERVED_PROJECT_POLICIES,
        BenchmarkQuotaContaminationError,
        DailyQuotaUnavailableError,
        ModelQuotaGovernor,
        QuotaConfigurationError,
        abort_scored_benchmark_on_429,
        audit_schedule,
        bounded_retry_delay,
        build_gemini_json_generation_request,
        gemini_direct_answer_schema,
        sanitize_gemini_429,
        validate_gemini_json_schema,
    )
except ModuleNotFoundError:
    from phase11_8_2_candidate import (  # type: ignore[no-redef]
        DirectAnswerResponseError,
        direct_answer_response_schema,
        parse_direct_answer,
    )
    from phase11_8_4_guardrails import (  # type: ignore[no-redef]
        OBSERVED_PROJECT_POLICIES,
        BenchmarkQuotaContaminationError,
        DailyQuotaUnavailableError,
        ModelQuotaGovernor,
        QuotaConfigurationError,
        abort_scored_benchmark_on_429,
        audit_schedule,
        bounded_retry_delay,
        build_gemini_json_generation_request,
        gemini_direct_answer_schema,
        sanitize_gemini_429,
        validate_gemini_json_schema,
    )

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-4-offline-guardrails-v1"
LOCKED_PROTOCOL_SHA256 = "ff3c034688dc87a320140b0e5815819603e9800fa14f5ea90cd5ff27b098cc58"
LOCKED_GUARDRAILS_SHA256 = "83a4341b93c49b3fc8c6a7f46da40c24f8bed19b516472229e3b280a3ebc763d"
LOCKED_PHASE11_8_3_RESULT_SHA256 = (
    "167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c"
)
LOCKED_PHASE11_8_2_CANDIDATE_SHA256 = (
    "0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e"
)
PROTOCOL_PATH = "docs/benchmark-protocol-v19.md"
GUARDRAILS_PATH = "benchmarks/phase11_8_4_guardrails.py"
HISTORICAL_RESULT_PATH = "benchmarks/results/phase11_8_3_factorial_2026-07-30.json"
CANDIDATE_PATH = "benchmarks/phase11_8_2_candidate.py"
FLASH_MODEL = "gemini-3.5-flash-lite"
GEMMA_MODEL = "gemma-4-26b-a4b-it"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256_bytes(encoded)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _quota_payload(quota_id: str, *, retry_delay: str | None = None) -> dict[str, Any]:
    details: list[dict[str, Any]] = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {
                    "quotaMetric": "generativelanguage.googleapis.com/generate_content",
                    "quotaId": quota_id,
                    "quotaDimensions": {
                        "model": FLASH_MODEL,
                        "location": "global",
                    },
                    "quotaValue": "fixture-only",
                }
            ],
        }
    ]
    if retry_delay is not None:
        details.append(
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": retry_delay,
            }
        )
    return {
        "error": {
            "code": 429,
            "message": "PRIVATE_PROVIDER_MESSAGE_MUST_NOT_SURVIVE",
            "status": "RESOURCE_EXHAUSTED",
            "details": details,
        }
    }


def _quota_diagnostics() -> dict[str, Any]:
    fixtures = {
        "rpm": _quota_payload(
            "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
            retry_delay="15s",
        ),
        "tpm": _quota_payload("GenerateContentInputTokensPerModelPerMinute-FreeTier"),
        "rpd": _quota_payload("GenerateRequestsPerDayPerProjectPerModel-FreeTier"),
        "unknown": _quota_payload("UnrecognizedProviderQuota"),
    }
    sanitized = {
        name: sanitize_gemini_429(
            429,
            payload,
            headers={"Retry-After": "12"} if name == "rpm" else None,
        )
        for name, payload in fixtures.items()
    }
    rendered = json.dumps(sanitized, ensure_ascii=False, sort_keys=True)
    abort_telemetry: dict[str, Any] | None = None
    try:
        abort_scored_benchmark_on_429(429, fixtures["rpm"])
    except BenchmarkQuotaContaminationError as exc:
        abort_telemetry = exc.telemetry
    return {
        "fixture_count": len(fixtures),
        "sanitized": sanitized,
        "dimensions_match": all(sanitized[name]["quota_dimension"] == name for name in fixtures),
        "raw_provider_message_omitted": (
            "PRIVATE_PROVIDER_MESSAGE_MUST_NOT_SURVIVE" not in rendered
        ),
        "raw_quota_identifiers_omitted": all(
            "quotaId" not in json.dumps(value, sort_keys=True)
            and "quotaMetric" not in json.dumps(value, sort_keys=True)
            for value in sanitized.values()
        ),
        "retry_after_uses_safe_maximum_hint": (sanitized["rpm"]["retry_after_seconds"] == 15.0),
        "scored_benchmark_aborted": abort_telemetry is not None,
        "abort_telemetry": abort_telemetry,
        "production_retry_examples_seconds": [
            bounded_retry_delay(attempt, positive_jitter_unit=0.5) for attempt in range(4)
        ],
        "benchmark_retry_count": 0,
    }


def _quota_schedules() -> dict[str, Any]:
    flash_policy = OBSERVED_PROJECT_POLICIES[FLASH_MODEL]
    flash = ModelQuotaGovernor(flash_policy, daily_requests_already_used=304)
    flash_reservations = flash.schedule([5_000] * 96)
    flash_audit = audit_schedule(flash_reservations, flash_policy)
    flash_deltas = [
        second.started_at - first.started_at for first, second in pairwise(flash_reservations)
    ]

    gemma_policy = OBSERVED_PROJECT_POLICIES[GEMMA_MODEL]
    gemma = ModelQuotaGovernor(gemma_policy)
    gemma_reservations = gemma.schedule([4_000] * 24)
    gemma_audit = audit_schedule(gemma_reservations, gemma_policy)
    rpm_only_interval = 60.0 / gemma_policy.effective_rpm
    first_gemma_interval = gemma_reservations[1].started_at - gemma_reservations[0].started_at

    daily_exhaustion_rejected = False
    exhausted = ModelQuotaGovernor(
        flash_policy,
        daily_requests_already_used=flash_policy.effective_rpd,
    )
    try:
        exhausted.schedule([1_000])
    except DailyQuotaUnavailableError:
        daily_exhaustion_rejected = True

    return {
        "policy_source": (
            "operator-observed active Google AI Studio project limits on "
            "2026-07-30; not universal defaults"
        ),
        "policies": {
            model: policy.public_summary()
            for model, policy in sorted(OBSERVED_PROJECT_POLICIES.items())
        },
        "flash_lite": {
            "estimated_input_tokens_per_request": 5_000,
            "planned_requests": 96,
            "initial_daily_requests": 304,
            "daily_requests_after_plan": flash.daily_requests,
            "minimum_start_interval_seconds": round(min(flash_deltas), 6),
            "audit": flash_audit,
        },
        "gemma_26b": {
            "estimated_input_tokens_per_request": 4_000,
            "planned_requests": 24,
            "rpm_only_interval_seconds": round(rpm_only_interval, 6),
            "first_scheduled_interval_seconds": round(first_gemma_interval, 6),
            "tpm_is_binding": first_gemma_interval > rpm_only_interval,
            "audit": gemma_audit,
        },
        "daily_exhaustion_rejected_before_request": daily_exhaustion_rejected,
    }


def _structured_output_diagnostics() -> dict[str, Any]:
    schema = gemini_direct_answer_schema()
    validate_gemini_json_schema(schema)
    legacy_unsupported_detected = False
    try:
        validate_gemini_json_schema(direct_answer_response_schema())
    except QuotaConfigurationError:
        legacy_unsupported_detected = True

    request = build_gemini_json_generation_request(
        system_prompt="SYNTHETIC_SYSTEM_PROMPT",
        user_prompt="SYNTHETIC_USER_PROMPT",
        max_output_tokens=2_048,
        schema=schema,
    )
    generation_config = request["generationConfig"]

    valid_accepted = False
    try:
        rendered = parse_direct_answer(
            '{"answer":"42","citation_ids":["S1"]}',
            allowed_ids=frozenset({"S1"}),
        )
        valid_accepted = rendered == "42 [S1]"
    except DirectAnswerResponseError:
        valid_accepted = False

    invalid = (
        '{"answer":"42","citation_ids":[]}',
        '{"answer":"42","citation_ids":["S2"]}',
        '{"answer":"42","citation_ids":["S1","S1"]}',
        '```json\n{"answer":"42","citation_ids":["S1"]}\n```',
    )
    invalid_rejected = 0
    for raw in invalid:
        try:
            parse_direct_answer(raw, allowed_ids=frozenset({"S1"}))
        except DirectAnswerResponseError:
            invalid_rejected += 1

    return {
        "model": FLASH_MODEL,
        "model_structured_output_documented": True,
        "schema_sha256": canonical_sha256(schema),
        "legacy_schema_contains_unsupported_keywords": legacy_unsupported_detected,
        "native_request_sha256": canonical_sha256(request),
        "request_contract": {
            "response_mime_type": generation_config["responseMimeType"],
            "response_json_schema_present": "responseJsonSchema" in generation_config,
            "maximum_output_tokens": generation_config["maxOutputTokens"],
            "thinking_level": generation_config["thinkingConfig"]["thinkingLevel"],
        },
        "strict_local_validation": {
            "valid_accepted": valid_accepted,
            "invalid_fixture_count": len(invalid),
            "invalid_rejected": invalid_rejected,
            "repair_requests": 0,
        },
    }


def build_report(
    *,
    protocol_raw: bytes,
    guardrails_raw: bytes,
    historical_result_raw: bytes,
    candidate_raw: bytes,
) -> dict[str, Any]:
    _require(
        sha256_bytes(protocol_raw) == LOCKED_PROTOCOL_SHA256,
        "Phase 11.8.4 protocol lock changed",
    )
    _require(
        sha256_bytes(guardrails_raw) == LOCKED_GUARDRAILS_SHA256,
        "Phase 11.8.4 guardrails lock changed",
    )
    _require(
        sha256_bytes(historical_result_raw) == LOCKED_PHASE11_8_3_RESULT_SHA256,
        "Phase 11.8.3 historical result changed",
    )
    _require(
        sha256_bytes(candidate_raw) == LOCKED_PHASE11_8_2_CANDIDATE_SHA256,
        "Phase 11.8.2 candidate changed",
    )
    historical = json.loads(historical_result_raw)
    historical_decision = historical["decision"]
    _require(
        historical_decision["phase11_8_3_candidate_passed"] is False
        and historical_decision["phase11_9_protocol_may_be_frozen"] is False
        and historical_decision["release_decision"] == "no-go",
        "Phase 11.8.3 decision boundary changed",
    )
    historical_429 = sum(
        metrics["error_kinds"].get("http_429", 0)
        for metrics in historical["generation_metrics"]["aggregate"].values()
    )
    _require(historical_429 == 22, "Phase 11.8.3 429 accounting changed")

    schedules = _quota_schedules()
    quota_diagnostics = _quota_diagnostics()
    structured = _structured_output_diagnostics()
    flash = schedules["flash_lite"]
    gemma = schedules["gemma_26b"]

    gates = {
        "locked_source_integrity": {
            "passed": True,
            "protocol_sha256": LOCKED_PROTOCOL_SHA256,
            "guardrails_sha256": LOCKED_GUARDRAILS_SHA256,
            "phase11_8_3_result_sha256": LOCKED_PHASE11_8_3_RESULT_SHA256,
            "phase11_8_2_candidate_sha256": LOCKED_PHASE11_8_2_CANDIDATE_SHA256,
        },
        "historical_phase11_8_3_no_go_preserved": {
            "passed": (
                historical_429 == 22
                and historical_decision["phase11_8_3_candidate_passed"] is False
                and historical_decision["phase11_9_protocol_may_be_frozen"] is False
            ),
            "historical_http_429": historical_429,
            "historical_gates_passed": 10,
            "historical_gate_count": 14,
        },
        "zero_network_provider_model_traffic": {
            "passed": True,
            "network_requests": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
        },
        "effective_quota_budgets_are_exact": {
            "passed": (
                schedules["policies"][FLASH_MODEL]["effective_budget"]
                == {"rpm": 12, "tpm": 200_000, "rpd": 400}
                and schedules["policies"][GEMMA_MODEL]["effective_budget"]
                == {"rpm": 24, "tpm": 12_800, "rpd": 11_520}
            )
        },
        "flash_schedule_within_rolling_rpm_and_tpm": {
            "passed": (
                flash["audit"]["within_rpm"] is True
                and flash["audit"]["within_tpm"] is True
                and flash["audit"]["request_count"] == 96
            ),
            "observed": flash["audit"],
        },
        "flash_start_interval_at_least_five_seconds": {
            "passed": flash["minimum_start_interval_seconds"] >= 5.0,
            "observed_seconds": flash["minimum_start_interval_seconds"],
            "required_seconds": 5.0,
        },
        "gemma_schedule_within_rolling_rpm_and_tpm": {
            "passed": (
                gemma["audit"]["within_rpm"] is True
                and gemma["audit"]["within_tpm"] is True
                and gemma["audit"]["request_count"] == 24
            ),
            "observed": gemma["audit"],
        },
        "gemma_fixture_is_tpm_bound": {
            "passed": gemma["tpm_is_binding"] is True,
            "rpm_only_interval_seconds": gemma["rpm_only_interval_seconds"],
            "scheduled_interval_seconds": gemma["first_scheduled_interval_seconds"],
        },
        "daily_exhaustion_fails_before_request": {
            "passed": schedules["daily_exhaustion_rejected_before_request"] is True
        },
        "quota_dimensions_are_bounded_and_correct": {
            "passed": (
                quota_diagnostics["dimensions_match"] is True
                and quota_diagnostics["retry_after_uses_safe_maximum_hint"] is True
            ),
            "observed": quota_diagnostics["sanitized"],
        },
        "quota_telemetry_omits_raw_provider_content": {
            "passed": (
                quota_diagnostics["raw_provider_message_omitted"] is True
                and quota_diagnostics["raw_quota_identifiers_omitted"] is True
            )
        },
        "scored_benchmark_aborts_on_429": {
            "passed": (
                quota_diagnostics["scored_benchmark_aborted"] is True
                and quota_diagnostics["benchmark_retry_count"] == 0
            ),
            "abort_telemetry": quota_diagnostics["abort_telemetry"],
        },
        "native_schema_and_request_use_supported_contract": {
            "passed": (
                structured["legacy_schema_contains_unsupported_keywords"] is True
                and structured["request_contract"]["response_mime_type"] == "application/json"
                and structured["request_contract"]["response_json_schema_present"] is True
            ),
            "schema_sha256": structured["schema_sha256"],
            "request_sha256": structured["native_request_sha256"],
        },
        "strict_local_semantic_validation_preserved": {
            "passed": (
                structured["strict_local_validation"]["valid_accepted"] is True
                and structured["strict_local_validation"]["invalid_rejected"]
                == structured["strict_local_validation"]["invalid_fixture_count"]
                and structured["strict_local_validation"]["repair_requests"] == 0
            ),
            "observed": structured["strict_local_validation"],
        },
        "authorization_and_release_boundaries_preserved": {
            "passed": (
                historical_decision["phase12_authorized"] is False
                and historical_decision["phase12_executed"] is False
                and historical_decision["merge_allowed"] is False
                and historical_decision["release_allowed"] is False
            ),
            "product_configuration_changed": False,
            "phase12_accessed": False,
            "live_smoke_authorized": False,
        },
    }
    offline_passed = all(bool(gate["passed"]) for gate in gates.values())
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": (
            "offline model-quota, HTTP 429 and native structured-output engineering guardrails"
        ),
        "source": {
            "phase11_8_3_result_path": HISTORICAL_RESULT_PATH,
            "phase11_8_3_result_sha256": LOCKED_PHASE11_8_3_RESULT_SHA256,
            "historical_result": "candidate_failed_10_of_14",
            "historical_http_429": historical_429,
            "historical_release_decision": "no-go",
        },
        "protocol": {
            "path": PROTOCOL_PATH,
            "sha256": LOCKED_PROTOCOL_SHA256,
            "guardrails_path": GUARDRAILS_PATH,
            "guardrails_sha256": LOCKED_GUARDRAILS_SHA256,
            "candidate_path": CANDIDATE_PATH,
            "candidate_sha256": LOCKED_PHASE11_8_2_CANDIDATE_SHA256,
            "active_limits_are_project_scoped": True,
            "observed_limits_are_universal_defaults": False,
            "safety_margin_percent": 20,
            "scored_benchmark_429_policy": "abort_unscored_without_retry",
            "ordinary_integration_429_policy": ("bounded exponential backoff with positive jitter"),
        },
        "quota_guardrails": schedules,
        "quota_error_diagnostics": quota_diagnostics,
        "structured_output": structured,
        "traffic": {
            "network_requests": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "gates": gates,
        "decision": {
            "offline_guardrails_passed": offline_passed,
            "historical_phase11_8_3_result_changed": False,
            "phase11_8_4_live_smoke_authorized": False,
            "phase11_9_protocol_may_be_frozen": False,
            "phase11_9_executed": False,
            "phase12_authorized": False,
            "phase12_executed": False,
            "quality_profile_promotion_allowed": False,
            "product_model_defaults_changed": False,
            "users_choose_provider_model_and_credentials": True,
            "external_competitor_benchmark_allowed": False,
            "public_alpha_allowed": False,
            "merge_allowed": False,
            "release_allowed": False,
            "superiority_claim_allowed": False,
            "release_decision": "no-go",
            "next_step": (
                "Review and separately authorize a small pre-registered live "
                "quota/schema smoke test; this offline pass authorizes no API traffic."
            ),
        },
        "privacy": {
            "questions_in_report": False,
            "reference_answers_in_report": False,
            "source_titles_or_urls_in_report": False,
            "source_snippets_or_evidence_in_report": False,
            "system_or_user_prompts_in_report": False,
            "generated_answers_in_report": False,
            "raw_provider_error_messages_in_report": False,
            "raw_quota_identifiers_in_report": False,
            "credentials_in_report": False,
            "phase12_reserved_identifiers_in_report": False,
        },
        "warnings": [
            (
                "The quota values are an operator-observed project snapshot, not "
                "guaranteed Gemini defaults. A future live protocol must review them."
            ),
            (
                "Native structured output constrains syntax only. The strict local "
                "parser remains necessary for evidence and citation semantics."
            ),
            (
                "The failed 17/24 Phase 11.8.3 projection gate is unaffected by these "
                "availability and response-contract guardrails."
            ),
        ],
    }


def run(
    *,
    protocol_path: Path,
    guardrails_path: Path,
    historical_result_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    return build_report(
        protocol_raw=protocol_path.read_bytes(),
        guardrails_raw=guardrails_path.read_bytes(),
        historical_result_raw=historical_result_path.read_bytes(),
        candidate_raw=candidate_path.read_bytes(),
    )


def main() -> int:
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
        "--phase11-8-3-result",
        type=Path,
        default=REPOSITORY_ROOT / HISTORICAL_RESULT_PATH,
    )
    parser.add_argument(
        "--phase11-8-2-candidate",
        type=Path,
        default=REPOSITORY_ROOT / CANDIDATE_PATH,
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run(
        protocol_path=arguments.protocol,
        guardrails_path=arguments.guardrails,
        historical_result_path=arguments.phase11_8_3_result,
        candidate_path=arguments.phase11_8_2_candidate,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
