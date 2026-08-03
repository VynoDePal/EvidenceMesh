from __future__ import annotations

import ast
import hashlib
import inspect
import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

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
    QuotaCeiling,
    QuotaConfigurationError,
    QuotaPolicy,
    ReservationTooEarlyError,
    abort_scored_benchmark_on_429,
    audit_schedule,
    bounded_retry_delay,
    build_gemini_json_generation_request,
    estimate_input_tokens,
    gemini_direct_answer_schema,
    sanitize_gemini_429,
    validate_gemini_json_schema,
)
from benchmarks.run_phase11_8_4_offline_guardrails import (
    BENCHMARK_NAME,
    LOCKED_GUARDRAILS_SHA256,
    LOCKED_PHASE11_8_2_CANDIDATE_SHA256,
    LOCKED_PHASE11_8_3_RESULT_SHA256,
    LOCKED_PROTOCOL_SHA256,
    run,
)

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/benchmark-protocol-v19.md"
GUARDRAILS = ROOT / "benchmarks/phase11_8_4_guardrails.py"
CANDIDATE = ROOT / "benchmarks/phase11_8_2_candidate.py"
HISTORICAL = ROOT / "benchmarks/results/phase11_8_3_factorial_2026-07-30.json"
RESULT = ROOT / "benchmarks/results/phase11_8_4_offline_guardrails_2026-07-30.json"
REPORT = ROOT / "benchmarks/results/phase11_8_4_offline_guardrails_2026-07-30.md"
WORKFLOW = ROOT / ".github/workflows/phase11-8-4-offline-guardrails.yml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _offline_report() -> dict[str, Any]:
    return run(
        protocol_path=PROTOCOL,
        guardrails_path=GUARDRAILS,
        historical_result_path=HISTORICAL,
        candidate_path=CANDIDATE,
    )


def _quota_payload(quota_id: str, retry_delay: str | None = None) -> dict[str, Any]:
    details: list[dict[str, Any]] = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {
                    "quotaMetric": "generativelanguage.googleapis.com/generate_content",
                    "quotaId": quota_id,
                    "quotaDimensions": {"model": "private-model-value"},
                    "quotaValue": "private-value",
                }
            ],
        }
    ]
    if retry_delay:
        details.append(
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": retry_delay,
            }
        )
    return {
        "error": {
            "code": 429,
            "message": "private response text",
            "details": details,
        }
    }


def test_all_locked_sources_match_and_historical_result_is_unchanged() -> None:
    assert _sha256(PROTOCOL) == LOCKED_PROTOCOL_SHA256
    assert _sha256(GUARDRAILS) == LOCKED_GUARDRAILS_SHA256
    assert _sha256(HISTORICAL) == LOCKED_PHASE11_8_3_RESULT_SHA256
    assert _sha256(CANDIDATE) == LOCKED_PHASE11_8_2_CANDIDATE_SHA256

    historical = json.loads(HISTORICAL.read_bytes())
    assert historical["decision"]["phase11_8_3_candidate_passed"] is False
    assert historical["decision"]["phase11_9_protocol_may_be_frozen"] is False
    assert historical["decision"]["release_decision"] == "no-go"


def test_observed_project_policies_apply_exact_twenty_percent_margin() -> None:
    flash = OBSERVED_PROJECT_POLICIES["gemini-3.5-flash-lite"]
    assert flash.ceiling == QuotaCeiling(rpm=15, tpm=250_000, rpd=500)
    assert (
        flash.effective_rpm,
        flash.effective_tpm,
        flash.effective_rpd,
    ) == (12, 200_000, 400)

    for model in ("gemma-4-26b-a4b-it", "gemma-4-31b-it"):
        policy = OBSERVED_PROJECT_POLICIES[model]
        assert policy.ceiling == QuotaCeiling(
            rpm=30,
            tpm=16_000,
            rpd=14_400,
        )
        assert (
            policy.effective_rpm,
            policy.effective_tpm,
            policy.effective_rpd,
        ) == (24, 12_800, 11_520)


@pytest.mark.parametrize(
    "ceiling",
    [
        {"rpm": 0, "tpm": 1, "rpd": 1},
        {"rpm": 1, "tpm": 0, "rpd": 1},
        {"rpm": 1, "tpm": 1, "rpd": 0},
    ],
)
def test_invalid_quota_ceilings_fail_closed(ceiling: dict[str, int]) -> None:
    with pytest.raises(QuotaConfigurationError):
        QuotaCeiling(**ceiling)


def test_invalid_safety_fraction_or_empty_model_fails_closed() -> None:
    ceiling = QuotaCeiling(rpm=15, tpm=250_000, rpd=500)
    with pytest.raises(QuotaConfigurationError):
        QuotaPolicy(model="", ceiling=ceiling)
    with pytest.raises(QuotaConfigurationError):
        QuotaPolicy(
            model="model",
            ceiling=ceiling,
            safety_numerator=6,
            safety_denominator=5,
        )


def test_token_estimate_is_deterministic_and_utf8_conservative() -> None:
    ascii_estimate = estimate_input_tokens(["a" * 300])
    unicode_estimate = estimate_input_tokens(["é" * 300])
    assert ascii_estimate == 164
    assert unicode_estimate == 264
    assert estimate_input_tokens(["same", "prompt"]) == estimate_input_tokens(["same", "prompt"])
    with pytest.raises(QuotaConfigurationError):
        estimate_input_tokens(["prompt"], bytes_per_token=0)


def test_flash_schedule_is_smoothed_and_within_rolling_budgets() -> None:
    policy = OBSERVED_PROJECT_POLICIES["gemini-3.5-flash-lite"]
    governor = ModelQuotaGovernor(
        policy,
        daily_requests_already_used=304,
    )
    reservations = governor.schedule([5_000] * 96)
    audit = audit_schedule(reservations, policy)
    deltas = [second.started_at - first.started_at for first, second in pairwise(reservations)]

    assert len(reservations) == 96
    assert min(deltas) == 5.0
    assert reservations[-1].started_at == 475.0
    assert audit["maximum_rolling_requests"] == 12
    assert audit["maximum_rolling_estimated_input_tokens"] == 60_000
    assert audit["within_rpm"] is True
    assert audit["within_tpm"] is True
    assert governor.daily_requests == 400


def test_gemma_schedule_is_tpm_bound_not_rpm_bound() -> None:
    policy = OBSERVED_PROJECT_POLICIES["gemma-4-26b-a4b-it"]
    governor = ModelQuotaGovernor(policy)
    reservations = governor.schedule([4_000] * 24)
    audit = audit_schedule(reservations, policy)
    first_interval = reservations[1].started_at - reservations[0].started_at

    assert first_interval == 18.75
    assert first_interval > 60 / policy.effective_rpm
    assert audit["maximum_rolling_requests"] == 3
    assert audit["maximum_rolling_estimated_input_tokens"] == 12_000
    assert audit["within_rpm"] is True
    assert audit["within_tpm"] is True


def test_oversized_tpm_daily_exhaustion_and_early_reservation_fail_closed() -> None:
    policy = OBSERVED_PROJECT_POLICIES["gemini-3.5-flash-lite"]
    governor = ModelQuotaGovernor(policy)
    governor.reserve(0.0, 1_000)
    with pytest.raises(ReservationTooEarlyError) as early:
        governor.reserve(1.0, 1_000)
    assert early.value.retry_after_seconds == 4.0
    with pytest.raises(QuotaConfigurationError):
        governor.schedule([policy.effective_tpm + 1])

    exhausted = ModelQuotaGovernor(
        policy,
        daily_requests_already_used=policy.effective_rpd,
    )
    with pytest.raises(DailyQuotaUnavailableError):
        exhausted.schedule([1_000])


@pytest.mark.asyncio
async def test_async_acquire_waits_for_the_computed_safe_start() -> None:
    policy = OBSERVED_PROJECT_POLICIES["gemini-3.5-flash-lite"]
    governor = ModelQuotaGovernor(policy)
    now = 0.0
    slept: list[float] = []

    def clock() -> float:
        return now

    async def sleep(delay: float) -> None:
        nonlocal now
        slept.append(delay)
        now += delay

    first = await governor.acquire(5_000, clock=clock, sleep=sleep)
    second = await governor.acquire(5_000, clock=clock, sleep=sleep)
    assert first.started_at == 0.0
    assert second.started_at == 5.0
    assert slept == [5.0]


@pytest.mark.parametrize(
    ("quota_id", "expected"),
    [
        ("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "rpm"),
        ("GenerateContentInputTokensPerModelPerMinute-FreeTier", "tpm"),
        ("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "rpd"),
        ("SpendPerTenMinutes", "spend"),
        ("UnrecognizedProviderQuota", "unknown"),
    ],
)
def test_429_sanitizer_classifies_only_bounded_dimensions(
    quota_id: str,
    expected: str,
) -> None:
    diagnostic = sanitize_gemini_429(
        429,
        _quota_payload(quota_id, retry_delay="15s"),
        headers={"Retry-After": "12"},
    )
    assert diagnostic == {
        "http_status": 429,
        "error_kind": "http_429",
        "quota_dimension": expected,
        "retry_after_seconds": 15.0,
    }
    rendered = json.dumps(diagnostic)
    assert "private response text" not in rendered
    assert "private-model-value" not in rendered
    assert quota_id not in rendered


def test_429_sanitizer_rejects_wrong_status_and_unbounded_retry_hint() -> None:
    with pytest.raises(ValueError):
        sanitize_gemini_429(503, {})
    diagnostic = sanitize_gemini_429(
        429,
        _quota_payload(
            "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
            retry_delay="999999999s",
        ),
        headers={"Retry-After": "not-a-number"},
    )
    assert diagnostic["retry_after_seconds"] is None


def test_scored_benchmark_aborts_on_429_without_retry() -> None:
    payload = _quota_payload("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
    with pytest.raises(BenchmarkQuotaContaminationError) as aborted:
        abort_scored_benchmark_on_429(429, payload)
    assert aborted.value.telemetry["quota_dimension"] == "rpm"
    assert "private response text" not in str(aborted.value)
    assert abort_scored_benchmark_on_429(503, {}) is None


def test_production_backoff_is_bounded_and_benchmark_policy_is_separate() -> None:
    delays = [bounded_retry_delay(attempt, positive_jitter_unit=0.5) for attempt in range(8)]
    assert delays[:4] == [1.1, 2.2, 4.4, 8.8]
    assert delays[-1] == 60.0
    assert all(first <= second for first, second in pairwise(delays))
    assert (
        bounded_retry_delay(
            0,
            retry_after_seconds=90.0,
            positive_jitter_unit=0.5,
        )
        == 90.0
    )
    with pytest.raises(ValueError):
        bounded_retry_delay(-1)
    with pytest.raises(ValueError):
        bounded_retry_delay(0, retry_after_seconds=-1.0)


def test_native_schema_uses_supported_subset_and_legacy_schema_is_detected() -> None:
    schema = gemini_direct_answer_schema()
    validate_gemini_json_schema(schema)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["propertyOrdering"] == ["answer", "citation_ids"]
    assert schema["required"] == ["answer", "citation_ids"]

    with pytest.raises(QuotaConfigurationError, match="unsupported"):
        validate_gemini_json_schema(direct_answer_response_schema())


def test_native_request_enables_json_schema_without_weakening_local_parser() -> None:
    request = build_gemini_json_generation_request(
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=2_048,
    )
    config = request["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == gemini_direct_answer_schema()
    assert config["maxOutputTokens"] == 2_048
    assert config["thinkingConfig"] == {"thinkingLevel": "high"}

    assert (
        parse_direct_answer(
            '{"answer":"42","citation_ids":["S1"]}',
            allowed_ids=frozenset({"S1"}),
        )
        == "42 [S1]"
    )
    for invalid in (
        '{"answer":"42","citation_ids":[]}',
        '{"answer":"42","citation_ids":["S2"]}',
        '{"answer":"42","citation_ids":["S1","S1"]}',
    ):
        with pytest.raises(DirectAnswerResponseError):
            parse_direct_answer(invalid, allowed_ids=frozenset({"S1"}))


def test_offline_report_passes_all_gates_without_authorizing_live_work() -> None:
    report = _offline_report()
    assert report["benchmark"] == BENCHMARK_NAME
    assert len(report["gates"]) == 15
    assert all(gate["passed"] for gate in report["gates"].values())
    assert report["traffic"] == {
        "network_requests": 0,
        "provider_calls": 0,
        "model_calls": 0,
        "tavily_requests": 0,
        "gemini_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
    }
    decision = report["decision"]
    assert decision["offline_guardrails_passed"] is True
    assert decision["historical_phase11_8_3_result_changed"] is False
    assert decision["phase11_8_4_live_smoke_authorized"] is False
    assert decision["phase11_9_protocol_may_be_frozen"] is False
    assert decision["phase12_authorized"] is False
    assert decision["phase12_executed"] is False
    assert decision["product_model_defaults_changed"] is False
    assert decision["merge_allowed"] is False
    assert decision["release_allowed"] is False
    assert decision["release_decision"] == "no-go"


def test_offline_sources_import_no_network_client_and_workflow_binds_no_secret() -> None:
    forbidden_imports = {
        "aiohttp",
        "google",
        "httpx",
        "requests",
        "socket",
        "tavily",
        "urllib",
    }
    imported: set[str] = set()
    for path in (
        GUARDRAILS,
        ROOT / "benchmarks/run_phase11_8_4_offline_guardrails.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", maxsplit=1)[0])
    assert imported.isdisjoint(forbidden_imports)

    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" not in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" not in workflow
    assert "${{ secrets." not in workflow
    assert "live-" not in workflow
    assert "authorize_live_run" not in workflow


def test_committed_result_reproduces_exactly_and_report_discloses_boundaries() -> None:
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

    report_text = REPORT.read_text(encoding="utf-8")
    for marker in (
        "15/15",
        "zero Gemini or Tavily calls",
        "The Phase 11.8.3 candidate remains failed",
        "Phase 12 remains sealed and blocked",
        "release remains no-go",
    ):
        assert marker in report_text


def test_public_report_contains_no_prompt_or_raw_quota_fixture_content() -> None:
    rendered = json.dumps(_offline_report(), ensure_ascii=False)
    for forbidden in (
        "SYNTHETIC_SYSTEM_PROMPT",
        "SYNTHETIC_USER_PROMPT",
        "PRIVATE_PROVIDER_MESSAGE_MUST_NOT_SURVIVE",
        "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
        "quotaMetric",
        "quotaId",
        "EVIDENCE_MESH_TAVILY_KEY",
        "EVIDENCE_MESH_GEMINI_KEY",
    ):
        assert forbidden not in rendered


def test_guardrail_module_performs_no_io_or_provider_call() -> None:
    source = inspect.getsource(
        __import__(
            "benchmarks.phase11_8_4_guardrails",
            fromlist=["phase11_8_4_guardrails"],
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
            "open",
            "read_bytes",
            "read_text",
            "write_bytes",
            "write_text",
            "request",
            "bounded_json_request",
            "request_gemini_completion",
            "urlopen",
            "connect",
            "send",
        }
    )
