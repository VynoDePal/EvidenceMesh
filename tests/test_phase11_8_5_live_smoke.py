from __future__ import annotations

import ast
import hashlib
import inspect
import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
import pytest

from benchmarks.phase11_8_2_candidate import DIRECT_ANSWER_INSUFFICIENT_TEXT
from benchmarks.phase11_8_4_guardrails import (
    OBSERVED_PROJECT_POLICIES,
    ModelQuotaGovernor,
    audit_schedule,
    validate_gemini_json_schema,
)
from benchmarks.run_phase11_8_5_live_smoke import (
    BENCHMARK_NAME,
    CANDIDATE_PATH,
    EXPECTED_CASES,
    EXPECTED_REPETITIONS,
    FIXTURE_PATH,
    GUARDRAILS_PATH,
    LIVE_AUTHORIZATION_LABEL,
    LOCKED_CANDIDATE_SHA256,
    LOCKED_FIXTURE_SHA256,
    LOCKED_GUARDRAILS_SHA256,
    LOCKED_PHASE11_8_3_RESULT_SHA256,
    LOCKED_PHASE11_8_4_RESULT_SHA256,
    LOCKED_PROTOCOL_SHA256,
    MAXIMUM_GEMINI_REQUESTS,
    MODEL,
    PHASE11_8_3_RESULT_PATH,
    PHASE11_8_4_RESULT_PATH,
    PROTOCOL_PATH,
    LiveSmokeRequestError,
    SmokeFixtureError,
    async_main,
    build_decision,
    build_parser,
    build_request,
    evaluate_answer,
    gemini_endpoint,
    load_cases,
    ordered_attempts,
    request_gemini_native,
    validate_arguments,
    validate_locked_sources,
    write_report,
)

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / PROTOCOL_PATH
FIXTURE = ROOT / FIXTURE_PATH
GUARDRAILS = ROOT / GUARDRAILS_PATH
PHASE11_8_4_RESULT = ROOT / PHASE11_8_4_RESULT_PATH
PHASE11_8_3_RESULT = ROOT / PHASE11_8_3_RESULT_PATH
CANDIDATE = ROOT / CANDIDATE_PATH
RUNNER = ROOT / "benchmarks/run_phase11_8_5_live_smoke.py"
WORKFLOW = ROOT / ".github/workflows/phase11-8-5-live-smoke.yml"
RESULT = ROOT / "benchmarks/results/phase11_8_5_live_smoke_2026-07-30.json"
REPORT = ROOT / "benchmarks/results/phase11_8_5_live_smoke_2026-07-30.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _arguments(*values: str) -> Any:
    return build_parser().parse_args(list(values))


def _valid_native_payload(
    *,
    answer: str = "Naro City",
    citation_ids: list[str] | None = None,
) -> dict[str, Any]:
    if citation_ids is None:
        citation_ids = ["S1"]
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "answer": answer,
                                    "citation_ids": citation_ids,
                                }
                            )
                        }
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 20,
            "totalTokenCount": 120,
            "privateUnexpectedCounter": 999,
        },
        "modelVersion": "gemini-3.5-flash-lite-2026-07",
    }


def _passing_outcomes() -> list[dict[str, Any]]:
    return [
        {
            "native_http_200": True,
            "schema_valid": True,
            "semantic_valid": True,
            "usage": {"promptTokenCount": 100},
        }
        for _ in range(MAXIMUM_GEMINI_REQUESTS)
    ]


def _passing_traffic() -> dict[str, int]:
    return {
        "gemini_requests": 8,
        "maximum_gemini_requests": 8,
        "native_http_200_responses": 8,
        "http_429_responses": 0,
        "other_failed_requests": 0,
        "tavily_requests": 0,
        "other_provider_requests": 0,
        "token_count_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
    }


def _passing_quota() -> dict[str, Any]:
    return {
        "minimum_start_interval_seconds": 5.0,
        "observed_prompt_tokens": 800,
        "effective_tpm": 200_000,
        "effective_rpd": 400,
        "daily_requests_after": 400,
        "audit": {
            "within_rpm": True,
            "within_tpm": True,
        },
    }


def _lock_validation() -> dict[str, Any]:
    return {
        "status": "phase11_8_5_protocol_lock_valid",
        "hashes": {},
        "historical_phase11_8_3_result": "fail_10_of_14",
        "historical_release_decision": "no-go",
    }


def test_all_locked_sources_match() -> None:
    assert _sha256(PROTOCOL) == LOCKED_PROTOCOL_SHA256
    assert _sha256(FIXTURE) == LOCKED_FIXTURE_SHA256
    assert _sha256(GUARDRAILS) == LOCKED_GUARDRAILS_SHA256
    assert _sha256(PHASE11_8_4_RESULT) == LOCKED_PHASE11_8_4_RESULT_SHA256
    assert _sha256(PHASE11_8_3_RESULT) == LOCKED_PHASE11_8_3_RESULT_SHA256
    assert _sha256(CANDIDATE) == LOCKED_CANDIDATE_SHA256


def test_lock_validation_preserves_historical_no_go() -> None:
    validation = validate_locked_sources(_arguments("--check-only"))
    assert validation["status"] == "phase11_8_5_protocol_lock_valid"
    assert validation["case_count"] == EXPECTED_CASES
    assert validation["maximum_gemini_requests"] == MAXIMUM_GEMINI_REQUESTS
    assert validation["network_requests"] == 0
    assert validation["model_calls"] == 0
    assert validation["tavily_requests"] == 0
    assert validation["protocol_publication_authorizes_live"] is False
    assert validation["historical_phase11_8_3_result"] == "fail_10_of_14"
    assert validation["historical_release_decision"] == "no-go"


def test_fixture_has_four_public_synthetic_cases_with_strict_semantics() -> None:
    cases = load_cases(FIXTURE)
    assert len(cases) == EXPECTED_CASES
    assert len({case.case_id for case in cases}) == EXPECTED_CASES
    assert sum(case.expected_answer == DIRECT_ANSWER_INSUFFICIENT_TEXT for case in cases) == 1
    for case in cases:
        evidence_ids = {item.citation_id for item in case.evidence}
        assert set(case.expected_citation_ids) <= evidence_ids
        assert case.question
        assert case.evidence


def test_fixture_loader_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_bytes())
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]
    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SmokeFixtureError, match="unique"):
        load_cases(malformed)


def test_attempt_order_repeats_every_case_twice_and_reverses_second_pass() -> None:
    cases = load_cases(FIXTURE)
    attempts = ordered_attempts(cases)
    assert len(attempts) == MAXIMUM_GEMINI_REQUESTS
    assert [case.case_id for _, case in attempts[:4]] == [case.case_id for case in cases]
    assert [case.case_id for _, case in attempts[4:]] == [case.case_id for case in reversed(cases)]
    assert {repetition for repetition, _ in attempts} == {0, 1}
    assert all(
        sum(attempt_case.case_id == case.case_id for _, attempt_case in attempts)
        == EXPECTED_REPETITIONS
        for case in cases
    )


def test_request_uses_native_json_schema_and_locked_generation_controls() -> None:
    case = load_cases(FIXTURE)[0]
    request, system_prompt, user_prompt, estimated_tokens = build_request(
        case,
        repetition=0,
    )
    generation = request["generationConfig"]
    validate_gemini_json_schema(generation["responseJsonSchema"])
    assert generation["responseMimeType"] == "application/json"
    assert generation["maxOutputTokens"] == 256
    assert generation["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert "temperature" not in generation
    assert "topP" not in generation
    assert "topK" not in generation
    assert "candidateCount" not in generation
    assert generation["seed"] == 11_850
    assert system_prompt
    assert user_prompt
    assert estimated_tokens > 64


def test_repetition_changes_only_the_locked_seed() -> None:
    case = load_cases(FIXTURE)[0]
    first = build_request(case, repetition=0)[0]
    second = build_request(case, repetition=1)[0]
    first_seed = first["generationConfig"].pop("seed")
    second_seed = second["generationConfig"].pop("seed")
    assert first_seed == 11_850
    assert second_seed == 11_851
    assert first == second


def test_gemini_endpoint_uses_model_path_without_key_query_parameter() -> None:
    endpoint = gemini_endpoint(MODEL)
    assert endpoint == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.5-flash-lite:generateContent"
    )
    assert "key=" not in endpoint


@pytest.mark.asyncio
async def test_native_request_parses_success_and_whitelists_usage() -> None:
    observed_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request
        observed_request = request
        return httpx.Response(200, json=_valid_native_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        completion = await request_gemini_native(
            client,
            api_key="test-secret",
            model=MODEL,
            request={"contents": []},
        )
    assert observed_request is not None
    assert observed_request.headers["x-goog-api-key"] == "test-secret"
    assert "test-secret" not in str(observed_request.url)
    assert completion.http_status == 200
    assert completion.finish_reason == "STOP"
    assert completion.response_model == "gemini-3.5-flash-lite-2026-07"
    assert completion.usage == {
        "promptTokenCount": 100,
        "candidatesTokenCount": 20,
        "totalTokenCount": 120,
    }


@pytest.mark.asyncio
async def test_429_is_sanitized_without_raw_provider_message() -> None:
    private_message = "PRIVATE_PROVIDER_MESSAGE_MUST_NOT_SURVIVE"
    payload = {
        "error": {
            "code": 429,
            "message": private_message,
            "details": [
                {
                    "violations": [
                        {
                            "quotaId": ("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"),
                            "quotaMetric": "generate_content",
                        }
                    ]
                }
            ],
        }
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json=payload,
            headers={"Retry-After": "12"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveSmokeRequestError) as raised:
            await request_gemini_native(
                client,
                api_key="test-secret",
                model=MODEL,
                request={"contents": []},
            )
    error = raised.value
    assert error.kind == "http_429"
    assert error.http_status == 429
    assert error.quota_telemetry == {
        "http_status": 429,
        "error_kind": "http_429",
        "quota_dimension": "rpm",
        "retry_after_seconds": 12.0,
    }
    assert private_message not in str(error)
    assert private_message not in json.dumps(error.quota_telemetry)


@pytest.mark.asyncio
async def test_other_http_error_is_categorical_and_body_free() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="PRIVATE CAPACITY RESPONSE")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveSmokeRequestError) as raised:
            await request_gemini_native(
                client,
                api_key="test-secret",
                model=MODEL,
                request={"contents": []},
            )
    assert raised.value.kind == "http_503"
    assert raised.value.http_status == 503
    assert "PRIVATE CAPACITY RESPONSE" not in str(raised.value)


@pytest.mark.asyncio
async def test_response_declared_over_byte_limit_is_rejected_before_parsing() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"{}",
            headers={"Content-Length": "1000001"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveSmokeRequestError, match="response_too_large"):
            await request_gemini_native(
                client,
                api_key="test-secret",
                model=MODEL,
                request={"contents": []},
            )


@pytest.mark.asyncio
async def test_missing_native_candidate_is_bounded_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveSmokeRequestError) as raised:
            await request_gemini_native(
                client,
                api_key="test-secret",
                model=MODEL,
                request={"contents": []},
            )
    assert raised.value.kind == "response_no_candidate"
    assert raised.value.http_status == 200


def test_supported_answer_passes_strict_schema_and_fixture_semantics() -> None:
    case = load_cases(FIXTURE)[0]
    evaluated = evaluate_answer(
        case,
        '{"answer":"Naro City","citation_ids":["S1"]}',
    )
    assert evaluated["schema_valid"] is True
    assert evaluated["semantic_valid"] is True
    assert evaluated["expected_answer_match"] is True
    assert evaluated["expected_citations_match"] is True
    assert evaluated["insufficient_semantics_valid"] is True
    assert evaluated["citation_count"] == 1


def test_insufficient_answer_passes_exact_empty_citation_semantics() -> None:
    case = load_cases(FIXTURE)[-1]
    evaluated = evaluate_answer(
        case,
        '{"answer":"Insufficient evidence.","citation_ids":[]}',
    )
    assert evaluated["schema_valid"] is True
    assert evaluated["semantic_valid"] is True
    assert evaluated["citation_count"] == 0


@pytest.mark.parametrize(
    "raw_answer",
    [
        "not json",
        '{"answer":"Naro City"}',
        '{"answer":"Naro City","citation_ids":[]}',
        '{"answer":"Naro City","citation_ids":["S2"]}',
        '{"answer":"Naro City [S1]","citation_ids":["S1"]}',
    ],
)
def test_invalid_contract_is_never_semantically_valid(raw_answer: str) -> None:
    evaluated = evaluate_answer(load_cases(FIXTURE)[0], raw_answer)
    assert evaluated["semantic_valid"] is False


def test_wrong_but_well_formed_answer_is_schema_valid_and_semantically_invalid() -> None:
    evaluated = evaluate_answer(
        load_cases(FIXTURE)[0],
        '{"answer":"Wrong City","citation_ids":["S1"]}',
    )
    assert evaluated["schema_valid"] is True
    assert evaluated["semantic_valid"] is False
    assert evaluated["expected_answer_match"] is False


def test_all_eight_requests_fit_smoothed_rpm_tpm_and_rpd_budgets() -> None:
    cases = load_cases(FIXTURE)
    estimates = [
        build_request(case, repetition=repetition)[3]
        for repetition, case in ordered_attempts(cases)
    ]
    policy = OBSERVED_PROJECT_POLICIES[MODEL]
    governor = ModelQuotaGovernor(policy, daily_requests_already_used=392)
    reservations = governor.schedule(estimates)
    audit = audit_schedule(reservations, policy)
    intervals = [second.started_at - first.started_at for first, second in pairwise(reservations)]
    assert len(reservations) == MAXIMUM_GEMINI_REQUESTS
    assert min(intervals) == 5.0
    assert audit["within_rpm"] is True
    assert audit["within_tpm"] is True
    assert audit["maximum_rolling_requests"] == MAXIMUM_GEMINI_REQUESTS
    assert audit["maximum_rolling_estimated_input_tokens"] < policy.effective_tpm
    assert governor.daily_requests == policy.effective_rpd == 400


def test_passing_decision_still_blocks_factorial_rerun_phase11_9_and_release() -> None:
    decision = build_decision(
        _passing_outcomes(),
        lock_validation=_lock_validation(),
        quota=_passing_quota(),
        traffic=_passing_traffic(),
        arguments=_arguments(),
    )
    assert len(decision["gates"]) == 12
    assert all(gate["passed"] for gate in decision["gates"].values())
    assert decision["phase11_8_5_live_smoke_passed"] is True
    assert decision["historical_phase11_8_3_result_changed"] is False
    assert decision["unchanged_phase11_8_3_rerun_authorized"] is False
    assert decision["phase11_9_protocol_may_be_frozen"] is False
    assert decision["phase12_authorized"] is False
    assert decision["merge_allowed"] is False
    assert decision["release_allowed"] is False
    assert decision["release_decision"] == "no-go"


def test_429_fails_smoke_without_breaking_traffic_ceiling_gate() -> None:
    traffic = _passing_traffic()
    traffic["gemini_requests"] = 1
    traffic["native_http_200_responses"] = 0
    traffic["http_429_responses"] = 1
    decision = build_decision(
        [
            {
                "native_http_200": False,
                "schema_valid": None,
                "semantic_valid": None,
                "usage": {},
            }
        ],
        lock_validation=_lock_validation(),
        quota={
            **_passing_quota(),
            "daily_requests_after": 393,
        },
        traffic=traffic,
        arguments=_arguments(),
    )
    assert decision["phase11_8_5_live_smoke_passed"] is False
    assert decision["gates"]["traffic_ceiling_and_provider_isolation"]["passed"] is True
    assert decision["gates"]["no_http_429"]["passed"] is False
    assert decision["unchanged_phase11_8_3_rerun_authorized"] is False


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--model", "other-model"),
        ("--repetitions", "3"),
        ("--max-requests", "9"),
        ("--cold-start-seconds", "59"),
        ("--initial-daily-requests", "391"),
        ("--max-output-tokens", "512"),
        ("--thinking-level", "high"),
        ("--request-timeout-seconds", "31"),
        ("--wall-time-seconds", "46"),
        ("--api-key-env", "OTHER_KEY"),
    ],
)
def test_locked_live_arguments_fail_closed(flag: str, value: str) -> None:
    with pytest.raises(ValueError, match="locked arguments changed"):
        validate_arguments(_arguments("--check-only", flag, value))


@pytest.mark.asyncio
async def test_check_only_never_calls_live_request(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("provider request attempted during check-only")

    monkeypatch.setattr(
        "benchmarks.run_phase11_8_5_live_smoke.request_gemini_native",
        forbidden,
    )
    assert await async_main(_arguments("--check-only")) == 0


def test_report_writer_is_atomic_and_canonical_enough_for_artifact(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    report = {"benchmark": BENCHMARK_NAME, "value": "évidence"}
    write_report(output, report)
    assert json.loads(output.read_bytes()) == report
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert not output.with_suffix(".json.partial").exists()


def test_runner_does_not_import_tavily_or_use_provider_key_query_parameter() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", maxsplit=1)[0])
    assert "tavily" not in imported
    assert "TAVILY_API_KEY" not in source
    assert "?key=" not in source
    assert "retries=0" in source


def test_protocol_discloses_limits_and_preserves_blocking_boundaries() -> None:
    protocol = PROTOCOL.read_text(encoding="utf-8")
    for marker in (
        "eight maximum attempts",
        "60-second cold-start",
        "12 RPM",
        "200,000 estimated input TPM",
        "400 RPD",
        "Retries | 0",
        "Phase 11.9",
        "Phase 12",
        "release",
        "17/24",
        "phase11.8.5-live-authorized",
    ):
        assert marker in protocol


def test_workflow_separates_offline_and_live_paths_and_binds_only_gemini() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "lock-validation:" in workflow
    assert "live-smoke:" in workflow
    assert "needs: lock-validation" in workflow
    assert LIVE_AUTHORIZATION_LABEL in workflow
    assert "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    assert "secrets.EVIDENCE_MESH_GEMINI_KEY" in workflow
    assert "secrets.EVIDENCE_MESH_TAVILY_KEY" not in workflow
    assert "--cold-start-seconds 60" in workflow
    assert "--max-requests 8" in workflow
    assert "--initial-daily-requests 392" in workflow


def test_workflow_artifact_and_validation_preserve_no_go_on_smoke_failure() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "retention-days: 14" in workflow
    assert 'assert len(report["decision"]["gates"]) == 12' in workflow
    assert 'decision["unchanged_phase11_8_3_rerun_authorized"] is False' in workflow
    assert 'decision["phase11_9_protocol_may_be_frozen"] is False' in workflow
    assert 'decision["phase12_authorized"] is False' in workflow
    assert 'decision["release_decision"] == "no-go"' in workflow


def test_committed_live_result_is_an_audited_timeout_no_go() -> None:
    assert RESULT.is_file()
    assert REPORT.is_file()
    assert _sha256(RESULT) == ("92e092a5929b9c2eb4d2090c61187e8d7d1eba9796d4de85f8f2d288e29a9423")

    payload = json.loads(RESULT.read_bytes())
    decision = payload["decision"]
    gates = decision["gates"]
    failed_gates = {name for name, gate in gates.items() if gate["passed"] is False}

    assert payload["benchmark"] == BENCHMARK_NAME
    assert payload["environment"]["commit_sha"] == ("23be221715ba5870ee6a2fa0078356ec6ad3afc5")
    assert payload["aborted"] is True
    assert payload["aborted_reason"] == "request_timeout"
    assert payload["traffic"] == {
        "fallback_requests": 0,
        "gemini_requests": 3,
        "http_429_responses": 0,
        "maximum_gemini_requests": 8,
        "native_http_200_responses": 2,
        "other_failed_requests": 1,
        "other_provider_requests": 0,
        "repair_requests": 0,
        "retries": 0,
        "tavily_requests": 0,
        "token_count_requests": 0,
    }
    assert len(gates) == 12
    assert sum(gate["passed"] for gate in gates.values()) == 8
    assert failed_gates == {
        "all_eight_fixture_semantics_valid",
        "all_eight_native_completions",
        "all_eight_strict_schema_valid",
        "usage_metadata_present",
    }
    assert gates["no_http_429"]["observed"] == 0
    assert gates["rolling_rpm_and_tpm_safety"]["passed"] is True

    outcomes = payload["outcomes"]
    assert len(outcomes) == 3
    assert all(
        outcome["native_http_200"] is True
        and outcome["schema_valid"] is True
        and outcome["semantic_valid"] is True
        for outcome in outcomes[:2]
    )
    assert outcomes[2]["native_http_200"] is False
    assert outcomes[2]["http_status"] is None
    assert outcomes[2]["error_kind"] == "request_timeout"
    assert outcomes[2]["latency_ms"] == pytest.approx(30_022.938)

    assert decision["phase11_8_5_live_smoke_passed"] is False
    assert decision["projection_recovery_design_may_be_considered"] is False
    assert decision["unchanged_phase11_8_3_rerun_authorized"] is False
    assert decision["phase11_9_protocol_may_be_frozen"] is False
    assert decision["phase11_9_executed"] is False
    assert decision["phase12_authorized"] is False
    assert decision["phase12_executed"] is False
    assert decision["merge_allowed"] is False
    assert decision["release_allowed"] is False
    assert decision["superiority_claim_allowed"] is False
    assert decision["release_decision"] == "no-go"

    assert all(value is False for value in payload["privacy"].values())
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "According to the evidence, which city hosts",
        "The Solena Archive is located",
        "Naro City",
        "Project Amber began",
        "250 milliseconds",
        "A community orchard was planted",
        "x-goog-api-key",
        "quotaMetric",
        "quotaId",
    ):
        assert forbidden not in rendered

    report = REPORT.read_text(encoding="utf-8")
    for marker in (
        "live smoke failed (8/12 gates passed)",
        "GitHub Actions 30568779397",
        "8769965903",
        "92e092a5929b9c2eb4d2090c61187e8d7d1eba9796d4de85f8f2d288e29a9423",
        "e0237bd057ac3db44dc37c56e0b8a3ea6e6c4fdb23a045344239fbc06793d004",
        "Phase 11.9 and Phase 12 remain blocked",
        "No selective rerun was made",
    ):
        assert marker in report


def test_public_runner_source_never_logs_prompt_answer_or_key() -> None:
    source = inspect.getsource(
        __import__(
            "benchmarks.run_phase11_8_5_live_smoke",
            fromlist=["run_phase11_8_5_live_smoke"],
        )
    )
    assert "print(system_prompt" not in source
    assert "print(user_prompt" not in source
    assert "print(completion.answer" not in source
    assert "print(api_key" not in source
