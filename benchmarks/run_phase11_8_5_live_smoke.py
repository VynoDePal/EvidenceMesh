#!/usr/bin/env python3
"""Run the pre-registered Phase 11.8.5 Gemini live micro-smoke.

The live path makes at most eight sequential Gemini generateContent requests.
It makes no Tavily, search, token-count, retry, fallback or repair request.
Public output contains bounded diagnostics and hashes, never prompts, evidence,
answers, raw provider errors or credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

try:
    from benchmarks.phase11_8_2_candidate import (
        DIRECT_ANSWER_INSUFFICIENT_TEXT,
        DirectAnswerResponseError,
        build_direct_answer_prompt,
        parse_direct_answer,
    )
    from benchmarks.phase11_8_4_guardrails import (
        OBSERVED_PROJECT_POLICIES,
        ModelQuotaGovernor,
        audit_schedule,
        build_gemini_json_generation_request,
        estimate_input_tokens,
        gemini_direct_answer_schema,
        sanitize_gemini_429,
    )
    from benchmarks.run_end_to_end_phase10 import (
        ModelRequestError,
        parse_gemini_completion,
    )
except ModuleNotFoundError:
    from phase11_8_2_candidate import (  # type: ignore[no-redef]
        DIRECT_ANSWER_INSUFFICIENT_TEXT,
        DirectAnswerResponseError,
        build_direct_answer_prompt,
        parse_direct_answer,
    )
    from phase11_8_4_guardrails import (  # type: ignore[no-redef]
        OBSERVED_PROJECT_POLICIES,
        ModelQuotaGovernor,
        audit_schedule,
        build_gemini_json_generation_request,
        estimate_input_tokens,
        gemini_direct_answer_schema,
        sanitize_gemini_429,
    )
    from run_end_to_end_phase10 import (  # type: ignore[no-redef]
        ModelRequestError,
        parse_gemini_completion,
    )

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-5-gemini-live-smoke-v1"
MODEL = "gemini-3.5-flash-lite"
EXPECTED_CASES = 4
EXPECTED_REPETITIONS = 2
MAXIMUM_GEMINI_REQUESTS = EXPECTED_CASES * EXPECTED_REPETITIONS
MAX_RESPONSE_BYTES = 1_000_000
LIVE_AUTHORIZATION_LABEL = "phase11.8.5-live-authorized"

LOCKED_PROTOCOL_SHA256 = "6c41f28afbf1ae4d4d6c2efaf83d54610dc6fdbc98256aeff7cacef90956b001"
LOCKED_FIXTURE_SHA256 = "64096454a2884817148694b6086043a7fdbecb911b8db4456994a6dfadfc47af"
LOCKED_GUARDRAILS_SHA256 = "83a4341b93c49b3fc8c6a7f46da40c24f8bed19b516472229e3b280a3ebc763d"
LOCKED_PHASE11_8_4_RESULT_SHA256 = (
    "480e60d9f1d9807d9f7d0e21b23f812dbed2a4c978d27b08a8b810fe719d000d"
)
LOCKED_PHASE11_8_3_RESULT_SHA256 = (
    "167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c"
)
LOCKED_CANDIDATE_SHA256 = "0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e"

PROTOCOL_PATH = "docs/benchmark-protocol-v20.md"
FIXTURE_PATH = "benchmarks/data/phase11_8_5_live_smoke_v1.json"
GUARDRAILS_PATH = "benchmarks/phase11_8_4_guardrails.py"
PHASE11_8_4_RESULT_PATH = "benchmarks/results/phase11_8_4_offline_guardrails_2026-07-30.json"
PHASE11_8_3_RESULT_PATH = "benchmarks/results/phase11_8_3_factorial_2026-07-30.json"
CANDIDATE_PATH = "benchmarks/phase11_8_2_candidate.py"

USAGE_KEYS = (
    "promptTokenCount",
    "candidatesTokenCount",
    "totalTokenCount",
    "thoughtsTokenCount",
    "cachedContentTokenCount",
)


class SmokeFixtureError(ValueError):
    """The locked synthetic smoke fixture is malformed."""


class LiveSmokeRequestError(RuntimeError):
    """A bounded live request failure without raw provider content."""

    def __init__(
        self,
        kind: str,
        *,
        http_status: int | None = None,
        quota_telemetry: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(kind)
        self.kind = kind
        self.http_status = http_status
        self.quota_telemetry = quota_telemetry


@dataclass(frozen=True, slots=True)
class SmokeEvidence:
    citation_id: str
    title: str
    url: str
    text: str


@dataclass(frozen=True, slots=True)
class SmokeCase:
    case_id: str
    question: str
    expected_answer: str
    expected_citation_ids: tuple[str, ...]
    evidence: tuple[SmokeEvidence, ...]


@dataclass(frozen=True, slots=True)
class NativeCompletion:
    answer: str
    response_model: str | None
    finish_reason: str | None
    usage: dict[str, int]
    http_status: int


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SmokeFixtureError(f"{field} must be a non-empty string")
    return value


def load_cases(path: Path) -> tuple[SmokeCase, ...]:
    payload = json.loads(path.read_bytes())
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "suite", "cases"}
        or payload["schema_version"] != 1
        or payload["suite"] != "phase11_8_5_live_smoke_v1"
        or not isinstance(payload["cases"], list)
        or len(payload["cases"]) != EXPECTED_CASES
    ):
        raise SmokeFixtureError("unexpected Phase 11.8.5 fixture envelope")

    cases: list[SmokeCase] = []
    seen_case_ids: set[str] = set()
    for case_value in payload["cases"]:
        if not isinstance(case_value, dict) or set(case_value) != {
            "case_id",
            "question",
            "expected_answer",
            "expected_citation_ids",
            "evidence",
        }:
            raise SmokeFixtureError("unexpected smoke case fields")
        case_id = _require_nonempty_string(case_value["case_id"], "case_id")
        if case_id in seen_case_ids:
            raise SmokeFixtureError("case IDs must be unique")
        seen_case_ids.add(case_id)
        citation_values = case_value["expected_citation_ids"]
        evidence_values = case_value["evidence"]
        if (
            not isinstance(citation_values, list)
            or any(not isinstance(value, str) for value in citation_values)
            or len(citation_values) != len(set(citation_values))
            or not isinstance(evidence_values, list)
            or not evidence_values
        ):
            raise SmokeFixtureError("invalid citation or evidence collection")
        evidence: list[SmokeEvidence] = []
        evidence_ids: set[str] = set()
        for evidence_value in evidence_values:
            if not isinstance(evidence_value, dict) or set(evidence_value) != {
                "citation_id",
                "title",
                "url",
                "text",
            }:
                raise SmokeFixtureError("unexpected smoke evidence fields")
            evidence_item = SmokeEvidence(
                citation_id=_require_nonempty_string(
                    evidence_value["citation_id"],
                    "citation_id",
                ),
                title=_require_nonempty_string(evidence_value["title"], "title"),
                url=_require_nonempty_string(evidence_value["url"], "url"),
                text=_require_nonempty_string(evidence_value["text"], "text"),
            )
            if evidence_item.citation_id in evidence_ids:
                raise SmokeFixtureError("evidence citation IDs must be unique")
            evidence_ids.add(evidence_item.citation_id)
            evidence.append(evidence_item)
        expected_answer = _require_nonempty_string(
            case_value["expected_answer"],
            "expected_answer",
        )
        expected_ids = tuple(citation_values)
        if any(value not in evidence_ids for value in expected_ids):
            raise SmokeFixtureError("expected citation is outside the evidence packet")
        if (expected_answer == DIRECT_ANSWER_INSUFFICIENT_TEXT) != (not expected_ids):
            raise SmokeFixtureError("insufficient-evidence fixture semantics changed")
        cases.append(
            SmokeCase(
                case_id=case_id,
                question=_require_nonempty_string(case_value["question"], "question"),
                expected_answer=expected_answer,
                expected_citation_ids=expected_ids,
                evidence=tuple(evidence),
            )
        )
    return tuple(cases)


def _sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def validate_locked_sources(arguments: argparse.Namespace) -> dict[str, Any]:
    locked = {
        "protocol": (arguments.protocol, LOCKED_PROTOCOL_SHA256),
        "fixture": (arguments.fixture, LOCKED_FIXTURE_SHA256),
        "guardrails": (arguments.guardrails, LOCKED_GUARDRAILS_SHA256),
        "phase11_8_4_result": (
            arguments.phase11_8_4_result,
            LOCKED_PHASE11_8_4_RESULT_SHA256,
        ),
        "phase11_8_3_result": (
            arguments.phase11_8_3_result,
            LOCKED_PHASE11_8_3_RESULT_SHA256,
        ),
        "candidate": (arguments.candidate, LOCKED_CANDIDATE_SHA256),
    }
    observed: dict[str, str] = {}
    for name, (path, expected) in locked.items():
        actual = _sha256_file(path)
        if actual != expected:
            raise ValueError(f"Phase 11.8.5 {name} checksum changed")
        observed[name] = actual

    historical = json.loads(arguments.phase11_8_3_result.read_bytes())
    offline = json.loads(arguments.phase11_8_4_result.read_bytes())
    if (
        historical["decision"]["phase11_8_3_candidate_passed"] is not False
        or historical["decision"]["phase11_9_protocol_may_be_frozen"] is not False
        or historical["decision"]["phase12_executed"] is not False
        or historical["decision"]["release_decision"] != "no-go"
    ):
        raise ValueError("historical Phase 11.8.3 no-go boundary changed")
    if (
        offline["decision"]["offline_guardrails_passed"] is not True
        or offline["decision"]["phase11_8_4_live_smoke_authorized"] is not False
        or offline["decision"]["phase11_9_protocol_may_be_frozen"] is not False
        or offline["decision"]["phase12_executed"] is not False
        or offline["decision"]["release_decision"] != "no-go"
    ):
        raise ValueError("Phase 11.8.4 decision boundary changed")
    cases = load_cases(arguments.fixture)
    return {
        "status": "phase11_8_5_protocol_lock_valid",
        "hashes": observed,
        "case_count": len(cases),
        "maximum_gemini_requests": MAXIMUM_GEMINI_REQUESTS,
        "tavily_requests": 0,
        "model_calls": 0,
        "network_requests": 0,
        "protocol_publication_authorizes_live": False,
        "historical_phase11_8_3_result": "fail_10_of_14",
        "historical_release_decision": "no-go",
    }


def validate_arguments(arguments: argparse.Namespace) -> None:
    locked = {
        "model": (arguments.model, MODEL),
        "repetitions": (arguments.repetitions, EXPECTED_REPETITIONS),
        "max_requests": (arguments.max_requests, MAXIMUM_GEMINI_REQUESTS),
        "cold_start_seconds": (arguments.cold_start_seconds, 60.0),
        "initial_daily_requests": (arguments.initial_daily_requests, 392),
        "max_output_tokens": (arguments.max_output_tokens, 256),
        "thinking_level": (arguments.thinking_level, "minimal"),
        "request_timeout_seconds": (arguments.request_timeout_seconds, 30.0),
        "wall_time_seconds": (arguments.wall_time_seconds, 45.0),
        "api_key_env": (arguments.api_key_env, "GEMINI_API_KEY"),
    }
    changed = [
        f"{name}={actual!r} (expected {expected!r})"
        for name, (actual, expected) in locked.items()
        if actual != expected
    ]
    if changed:
        raise ValueError("Phase 11.8.5 locked arguments changed: " + ", ".join(changed))
    if not arguments.check_only and arguments.output is None:
        raise ValueError("live execution requires --output")


def ordered_attempts(
    cases: Sequence[SmokeCase],
    repetitions: int = EXPECTED_REPETITIONS,
) -> tuple[tuple[int, SmokeCase], ...]:
    attempts: list[tuple[int, SmokeCase]] = []
    for repetition in range(repetitions):
        selected = cases if repetition % 2 == 0 else tuple(reversed(cases))
        attempts.extend((repetition, case) for case in selected)
    return tuple(attempts)


def build_request(
    case: SmokeCase,
    *,
    repetition: int,
    max_output_tokens: int = 256,
    thinking_level: str = "minimal",
) -> tuple[dict[str, Any], str, str, int]:
    system_prompt, user_prompt = build_direct_answer_prompt(case.question, case.evidence)
    request = build_gemini_json_generation_request(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_output_tokens=max_output_tokens,
        thinking_level=thinking_level,
    )
    generation = request["generationConfig"]
    generation["seed"] = 11_850 + repetition
    schema_text = canonical_json_bytes(gemini_direct_answer_schema()).decode()
    estimated_tokens = estimate_input_tokens(
        (system_prompt, user_prompt, schema_text),
    )
    return request, system_prompt, user_prompt, estimated_tokens


def gemini_endpoint(model: str) -> str:
    encoded_model = quote(model, safe="-_.")
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent"
    )


async def _bounded_http_response(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    model: str,
    request: Mapping[str, Any],
) -> tuple[int, bytes, Mapping[str, str]]:
    async with client.stream(
        "POST",
        gemini_endpoint(model),
        headers={
            "x-goog-api-key": api_key,
            "content-type": "application/json",
        },
        json=request,
    ) as response:
        declared = response.headers.get("content-length")
        if declared:
            try:
                declared_bytes = int(declared)
            except ValueError:
                declared_bytes = None
            if declared_bytes is not None and declared_bytes > MAX_RESPONSE_BYTES:
                raise LiveSmokeRequestError(
                    "response_too_large",
                    http_status=response.status_code,
                )
        chunks: list[bytes] = []
        received = 0
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if received > MAX_RESPONSE_BYTES:
                raise LiveSmokeRequestError(
                    "response_too_large",
                    http_status=response.status_code,
                )
            chunks.append(chunk)
        safe_headers = {
            key: value for key, value in response.headers.items() if key.casefold() == "retry-after"
        }
        return response.status_code, b"".join(chunks), safe_headers


async def request_gemini_native(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    model: str,
    request: Mapping[str, Any],
) -> NativeCompletion:
    try:
        status_code, response_bytes, headers = await _bounded_http_response(
            client,
            api_key=api_key,
            model=model,
            request=request,
        )
    except httpx.TimeoutException as exc:
        raise LiveSmokeRequestError("request_timeout") from exc
    except httpx.HTTPError as exc:
        raise LiveSmokeRequestError("request_http_error") from exc

    if status_code != 429 and (status_code < 200 or status_code >= 300):
        raise LiveSmokeRequestError(
            f"http_{status_code}",
            http_status=status_code,
        )
    try:
        payload = json.loads(response_bytes)
    except json.JSONDecodeError as exc:
        if status_code == 429:
            payload = {}
        else:
            raise LiveSmokeRequestError(
                "invalid_json_response",
                http_status=status_code,
            ) from exc
    if not isinstance(payload, dict):
        payload = {}
        if status_code != 429:
            raise LiveSmokeRequestError(
                "invalid_json_response",
                http_status=status_code,
            )
    if status_code == 429:
        raise LiveSmokeRequestError(
            "http_429",
            http_status=429,
            quota_telemetry=sanitize_gemini_429(
                429,
                payload,
                headers=headers,
            ),
        )
    try:
        completion = parse_gemini_completion(payload)
    except ModelRequestError as exc:
        raise LiveSmokeRequestError(exc.kind, http_status=status_code) from exc
    usage = {
        key: value
        for key in USAGE_KEYS
        if isinstance((value := completion.usage.get(key)), int)
        and not isinstance(value, bool)
        and value >= 0
    }
    return NativeCompletion(
        answer=completion.answer,
        response_model=completion.response_model,
        finish_reason=completion.finish_reason,
        usage=usage,
        http_status=status_code,
    )


def evaluate_answer(
    case: SmokeCase,
    raw_answer: str,
) -> dict[str, Any]:
    answer_sha256 = sha256_bytes(raw_answer.encode())
    try:
        parsed_payload = json.loads(raw_answer)
        parse_direct_answer(
            raw_answer,
            allowed_ids=frozenset(item.citation_id for item in case.evidence),
        )
    except (json.JSONDecodeError, DirectAnswerResponseError):
        return {
            "schema_valid": False,
            "semantic_valid": False,
            "expected_answer_match": False,
            "expected_citations_match": False,
            "insufficient_semantics_valid": False,
            "answer_sha256": answer_sha256,
            "answer_chars": len(raw_answer),
            "citation_count": 0,
        }

    answer = parsed_payload["answer"].strip()
    citation_ids = tuple(parsed_payload["citation_ids"])
    expected_answer_match = answer == case.expected_answer
    expected_citations_match = citation_ids == case.expected_citation_ids
    insufficient_semantics_valid = (
        (answer == DIRECT_ANSWER_INSUFFICIENT_TEXT and not citation_ids)
        if case.expected_answer == DIRECT_ANSWER_INSUFFICIENT_TEXT
        else answer != DIRECT_ANSWER_INSUFFICIENT_TEXT and bool(citation_ids)
    )
    semantic_valid = (
        expected_answer_match and expected_citations_match and insufficient_semantics_valid
    )
    return {
        "schema_valid": True,
        "semantic_valid": semantic_valid,
        "expected_answer_match": expected_answer_match,
        "expected_citations_match": expected_citations_match,
        "insufficient_semantics_valid": insufficient_semantics_valid,
        "answer_sha256": answer_sha256,
        "answer_chars": len(answer),
        "citation_count": len(citation_ids),
    }


def _failed_outcome(
    *,
    case: SmokeCase,
    repetition: int,
    attempt_index: int,
    prompt_sha256: str,
    request_sha256: str,
    estimated_input_tokens: int,
    latency_ms: float,
    error: LiveSmokeRequestError,
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "repetition": repetition,
        "attempt_index": attempt_index,
        "model": MODEL,
        "status": "failed",
        "native_http_200": False,
        "schema_valid": None,
        "semantic_valid": None,
        "expected_answer_match": None,
        "expected_citations_match": None,
        "insufficient_semantics_valid": None,
        "prompt_sha256": prompt_sha256,
        "request_sha256": request_sha256,
        "answer_sha256": None,
        "answer_chars": 0,
        "citation_count": 0,
        "estimated_input_tokens": estimated_input_tokens,
        "usage": {},
        "response_model": None,
        "finish_reason": None,
        "http_status": error.http_status,
        "latency_ms": latency_ms,
        "error_kind": error.kind,
        "quota_telemetry": error.quota_telemetry,
    }


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _commit_sha() -> str | None:
    value = os.getenv("EVIDENCEMESH_BENCHMARK_COMMIT", "").strip()
    return value or None


def _ratio(numerator: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 6) if denominator else None,
    }


def build_decision(
    outcomes: Sequence[Mapping[str, Any]],
    *,
    lock_validation: Mapping[str, Any],
    quota: Mapping[str, Any],
    traffic: Mapping[str, int],
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    native = sum(bool(item["native_http_200"]) for item in outcomes)
    schema = sum(item["schema_valid"] is True for item in outcomes)
    semantic = sum(item["semantic_valid"] is True for item in outcomes)
    usage_present = sum(
        bool(item["usage"]) and "promptTokenCount" in item["usage"] for item in outcomes
    )
    gates = {
        "immutable_sources": {
            "passed": lock_validation["status"] == "phase11_8_5_protocol_lock_valid",
            "hashes": lock_validation["hashes"],
        },
        "exact_model_and_request_configuration": {
            "passed": (
                arguments.model == MODEL
                and arguments.max_output_tokens == 256
                and arguments.thinking_level == "minimal"
            ),
            "model": arguments.model,
            "max_output_tokens": arguments.max_output_tokens,
            "thinking_level": arguments.thinking_level,
            "sampling_parameters": ("provider defaults; temperature/top-p/top-k omitted"),
            "candidate_count": "omitted; provider default",
        },
        "traffic_ceiling_and_provider_isolation": {
            "passed": (
                traffic["gemini_requests"] <= MAXIMUM_GEMINI_REQUESTS
                and traffic["tavily_requests"] == 0
                and traffic["other_provider_requests"] == 0
                and traffic["token_count_requests"] == 0
            ),
            "observed": dict(traffic),
            "maximum_gemini_requests": MAXIMUM_GEMINI_REQUESTS,
        },
        "zero_retry_fallback_and_repair": {
            "passed": (
                traffic["retries"] == 0
                and traffic["fallback_requests"] == 0
                and traffic["repair_requests"] == 0
            ),
            "retries": traffic["retries"],
            "fallback_requests": traffic["fallback_requests"],
            "repair_requests": traffic["repair_requests"],
        },
        "cold_start_and_smoothed_start_pacing": {
            "passed": (
                arguments.cold_start_seconds == 60.0
                and (
                    quota["minimum_start_interval_seconds"] is None
                    or float(quota["minimum_start_interval_seconds"]) >= 5.0
                )
            ),
            "cold_start_seconds": arguments.cold_start_seconds,
            "minimum_start_interval_seconds": quota["minimum_start_interval_seconds"],
            "required_minimum_start_interval_seconds": 5.0,
        },
        "rolling_rpm_and_tpm_safety": {
            "passed": (
                quota["audit"]["within_rpm"] is True
                and quota["audit"]["within_tpm"] is True
                and int(quota["observed_prompt_tokens"]) <= int(quota["effective_tpm"])
                and int(quota["daily_requests_after"]) <= int(quota["effective_rpd"])
            ),
            "observed": dict(quota),
        },
        "no_http_429": {
            "passed": traffic["http_429_responses"] == 0,
            "observed": traffic["http_429_responses"],
        },
        "all_eight_native_completions": {
            "passed": native == MAXIMUM_GEMINI_REQUESTS,
            "observed": native,
            "required": MAXIMUM_GEMINI_REQUESTS,
        },
        "all_eight_strict_schema_valid": {
            "passed": schema == MAXIMUM_GEMINI_REQUESTS,
            "observed": schema,
            "required": MAXIMUM_GEMINI_REQUESTS,
        },
        "all_eight_fixture_semantics_valid": {
            "passed": semantic == MAXIMUM_GEMINI_REQUESTS,
            "observed": semantic,
            "required": MAXIMUM_GEMINI_REQUESTS,
        },
        "usage_metadata_present": {
            "passed": usage_present == MAXIMUM_GEMINI_REQUESTS,
            "observed": usage_present,
            "required": MAXIMUM_GEMINI_REQUESTS,
        },
        "privacy_and_historical_boundaries": {
            "passed": (
                lock_validation["historical_phase11_8_3_result"] == "fail_10_of_14"
                and lock_validation["historical_release_decision"] == "no-go"
            ),
            "questions_or_evidence_in_report": False,
            "generated_answers_in_report": False,
            "raw_provider_errors_in_report": False,
            "credentials_in_report": False,
            "historical_phase11_8_3_result": "unchanged_fail_10_of_14",
        },
    }
    passed = all(bool(gate["passed"]) for gate in gates.values())
    return {
        "gates": gates,
        "phase11_8_5_live_smoke_passed": passed,
        "historical_phase11_8_3_result_changed": False,
        "unchanged_phase11_8_3_rerun_authorized": False,
        "phase11_9_protocol_may_be_frozen": False,
        "phase11_9_executed": False,
        "projection_recovery_design_may_be_considered": passed,
        "product_model_defaults_changed": False,
        "quality_profile_promotion_allowed": False,
        "phase12_authorized": False,
        "phase12_executed": False,
        "external_competitor_benchmark_allowed": False,
        "public_alpha_allowed": False,
        "merge_allowed": False,
        "release_allowed": False,
        "superiority_claim_allowed": False,
        "release_decision": "no-go",
        "next_step": (
            "Review a separate projection-recovery design; do not rerun the "
            "unchanged Phase 11.8.3 factorial."
            if passed
            else "Diagnose the failed smoke gate without an opportunistic live rerun."
        ),
    }


async def execute_live(arguments: argparse.Namespace) -> dict[str, Any]:
    validate_arguments(arguments)
    lock_validation = validate_locked_sources(arguments)
    cases = load_cases(arguments.fixture)
    api_key = os.getenv(arguments.api_key_env)
    if not api_key:
        raise ValueError("Gemini API key is not configured")

    policy = OBSERVED_PROJECT_POLICIES[MODEL]
    governor = ModelQuotaGovernor(
        policy,
        daily_requests_already_used=arguments.initial_daily_requests,
    )
    attempts = ordered_attempts(cases, arguments.repetitions)
    if len(attempts) != arguments.max_requests:
        raise AssertionError("locked smoke attempt count changed")

    started_at = datetime.now(UTC)
    await asyncio.sleep(arguments.cold_start_seconds)
    outcomes: list[dict[str, Any]] = []
    aborted_reason: str | None = None
    timeout = httpx.Timeout(
        connect=20.0,
        read=arguments.request_timeout_seconds,
        write=20.0,
        pool=20.0,
    )
    transport = httpx.AsyncHTTPTransport(retries=0)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
        headers={"User-Agent": "EvidenceMesh Phase 11.8.5 live smoke/0.1"},
    ) as client:
        for attempt_index, (repetition, case) in enumerate(attempts, start=1):
            request, system_prompt, user_prompt, estimated_tokens = build_request(
                case,
                repetition=repetition,
                max_output_tokens=arguments.max_output_tokens,
                thinking_level=arguments.thinking_level,
            )
            await governor.acquire(estimated_tokens)
            prompt_sha256 = canonical_sha256(
                {
                    "system_instruction": system_prompt,
                    "user_prompt": user_prompt,
                }
            )
            request_sha256 = canonical_sha256(request)
            request_started = time.perf_counter()
            try:
                async with asyncio.timeout(arguments.wall_time_seconds):
                    completion = await request_gemini_native(
                        client,
                        api_key=api_key,
                        model=arguments.model,
                        request=request,
                    )
            except TimeoutError:
                error = LiveSmokeRequestError("generation_wall_timeout")
            except LiveSmokeRequestError as exc:
                error = exc
            else:
                evaluated = evaluate_answer(case, completion.answer)
                outcome = {
                    "case_id": case.case_id,
                    "repetition": repetition,
                    "attempt_index": attempt_index,
                    "model": arguments.model,
                    "status": (
                        "completed"
                        if evaluated["schema_valid"] and evaluated["semantic_valid"]
                        else "contract_failed"
                    ),
                    "native_http_200": True,
                    **evaluated,
                    "prompt_sha256": prompt_sha256,
                    "request_sha256": request_sha256,
                    "estimated_input_tokens": estimated_tokens,
                    "usage": completion.usage,
                    "response_model": completion.response_model,
                    "finish_reason": completion.finish_reason,
                    "http_status": completion.http_status,
                    "latency_ms": round(
                        (time.perf_counter() - request_started) * 1_000,
                        3,
                    ),
                    "error_kind": None,
                    "quota_telemetry": None,
                }
                outcomes.append(outcome)
                if arguments.progress:
                    print(
                        f"[{attempt_index}/{len(attempts)}] {case.case_id} "
                        f"schema={outcome['schema_valid']} "
                        f"semantic={outcome['semantic_valid']}",
                        file=sys.stderr,
                        flush=True,
                    )
                continue

            outcome = _failed_outcome(
                case=case,
                repetition=repetition,
                attempt_index=attempt_index,
                prompt_sha256=prompt_sha256,
                request_sha256=request_sha256,
                estimated_input_tokens=estimated_tokens,
                latency_ms=round((time.perf_counter() - request_started) * 1_000, 3),
                error=error,
            )
            outcomes.append(outcome)
            aborted_reason = error.kind
            if arguments.progress:
                print(
                    f"[{attempt_index}/{len(attempts)}] aborted={error.kind}",
                    file=sys.stderr,
                    flush=True,
                )
            break

    reservations = governor.reservations
    schedule_audit = audit_schedule(reservations, policy)
    intervals = [second.started_at - first.started_at for first, second in pairwise(reservations)]
    observed_prompt_tokens = sum(
        int(outcome["usage"].get("promptTokenCount", 0))
        for outcome in outcomes
        if isinstance(outcome["usage"], dict)
    )
    quota = {
        "model": MODEL,
        "observed_ceiling": policy.public_summary()["observed_ceiling"],
        "safety_fraction": policy.public_summary()["safety_fraction"],
        "effective_rpm": policy.effective_rpm,
        "effective_tpm": policy.effective_tpm,
        "effective_rpd": policy.effective_rpd,
        "cold_start_seconds": arguments.cold_start_seconds,
        "synthetic_initial_daily_reservation": arguments.initial_daily_requests,
        "daily_requests_after": governor.daily_requests,
        "minimum_start_interval_seconds": (round(min(intervals), 6) if intervals else None),
        "observed_prompt_tokens": observed_prompt_tokens,
        "audit": schedule_audit,
    }
    traffic = {
        "gemini_requests": len(outcomes),
        "maximum_gemini_requests": MAXIMUM_GEMINI_REQUESTS,
        "native_http_200_responses": sum(bool(outcome["native_http_200"]) for outcome in outcomes),
        "http_429_responses": sum(outcome["error_kind"] == "http_429" for outcome in outcomes),
        "other_failed_requests": sum(
            outcome["status"] == "failed" and outcome["error_kind"] != "http_429"
            for outcome in outcomes
        ),
        "tavily_requests": 0,
        "other_provider_requests": 0,
        "token_count_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
    }
    decision = build_decision(
        outcomes,
        lock_validation=lock_validation,
        quota=quota,
        traffic=traffic,
        arguments=arguments,
    )
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": "synthetic live quota and native structured-output micro-smoke",
        "suite": {
            "fixture_sha256": LOCKED_FIXTURE_SHA256,
            "case_count": len(cases),
            "repetitions": arguments.repetitions,
            "maximum_attempts": arguments.max_requests,
            "synthetic_public_fixtures": True,
            "simpleqa_cases_used": False,
            "phase11_7_cases_used": False,
            "phase12_cases_used": False,
        },
        "protocol": {
            "path": PROTOCOL_PATH,
            "sha256": LOCKED_PROTOCOL_SHA256,
            "model": arguments.model,
            "endpoint": "Gemini v1beta generateContent",
            "response_mime_type": "application/json",
            "response_json_schema": "Phase 11.8.4 supported subset",
            "strict_local_parser": "unchanged Phase 11.8.2 direct-answer parser",
            "max_output_tokens": arguments.max_output_tokens,
            "thinking_level": arguments.thinking_level,
            "sampling_parameters": ("provider defaults; temperature/top-p/top-k omitted"),
            "candidate_count": "omitted; provider default",
            "cold_start_seconds": arguments.cold_start_seconds,
            "retry_policy": "none",
            "live_authorization_label": LIVE_AUTHORIZATION_LABEL,
            "protocol_publication_authorizes_live": False,
        },
        "environment": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "commit_sha": _commit_sha(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "network_region": arguments.network_region,
            "dependency_versions": {
                "httpx": _package_version("httpx"),
            },
        },
        "lock_validation": lock_validation,
        "traffic": traffic,
        "quota": quota,
        "aggregate": {
            "native_completions": _ratio(
                traffic["native_http_200_responses"],
                MAXIMUM_GEMINI_REQUESTS,
            ),
            "strict_schema_valid": _ratio(
                sum(outcome["schema_valid"] is True for outcome in outcomes),
                MAXIMUM_GEMINI_REQUESTS,
            ),
            "fixture_semantics_valid": _ratio(
                sum(outcome["semantic_valid"] is True for outcome in outcomes),
                MAXIMUM_GEMINI_REQUESTS,
            ),
            "usage_metadata_present": _ratio(
                sum(
                    bool(outcome["usage"]) and "promptTokenCount" in outcome["usage"]
                    for outcome in outcomes
                ),
                MAXIMUM_GEMINI_REQUESTS,
            ),
        },
        "aborted": aborted_reason is not None,
        "aborted_reason": aborted_reason,
        "decision": decision,
        "outcomes": outcomes,
        "privacy": {
            "questions_in_report": False,
            "expected_answers_in_report": False,
            "evidence_in_report": False,
            "system_or_user_prompts_in_report": False,
            "generated_answers_in_report": False,
            "raw_provider_errors_in_report": False,
            "raw_quota_details_in_report": False,
            "api_keys_in_report": False,
            "phase12_identifiers_in_report": False,
        },
        "warnings": [
            (
                "This is an eight-request synthetic engineering smoke, not a "
                "retrieval or answer-quality benchmark."
            ),
            (
                "A pass does not repair the deterministic Phase 11.8.3 projection "
                "failure and does not authorize an unchanged factorial rerun."
            ),
            (
                "Observed project limits are calibration inputs and must be reviewed "
                "before any future live run."
            ),
        ],
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.partial")
    temporary.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument(
        "--protocol",
        type=Path,
        default=REPOSITORY_ROOT / PROTOCOL_PATH,
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=REPOSITORY_ROOT / FIXTURE_PATH,
    )
    parser.add_argument(
        "--guardrails",
        type=Path,
        default=REPOSITORY_ROOT / GUARDRAILS_PATH,
    )
    parser.add_argument(
        "--phase11-8-4-result",
        type=Path,
        default=REPOSITORY_ROOT / PHASE11_8_4_RESULT_PATH,
    )
    parser.add_argument(
        "--phase11-8-3-result",
        type=Path,
        default=REPOSITORY_ROOT / PHASE11_8_3_RESULT_PATH,
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=REPOSITORY_ROOT / CANDIDATE_PATH,
    )
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--repetitions", type=int, default=EXPECTED_REPETITIONS)
    parser.add_argument("--max-requests", type=int, default=MAXIMUM_GEMINI_REQUESTS)
    parser.add_argument("--cold-start-seconds", type=float, default=60.0)
    parser.add_argument("--initial-daily-requests", type=int, default=392)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument("--thinking-level", default="minimal")
    parser.add_argument("--request-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--wall-time-seconds", type=float, default=45.0)
    parser.add_argument("--api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--network-region", default="unspecified")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--progress", action="store_true")
    return parser


async def async_main(arguments: argparse.Namespace) -> int:
    validate_arguments(arguments)
    if arguments.check_only:
        validation = validate_locked_sources(arguments)
        print(json.dumps(validation, ensure_ascii=False, sort_keys=True))
        return 0
    report = await execute_live(arguments)
    if arguments.output is None:
        raise ValueError("live execution requires --output")
    write_report(arguments.output, report)
    return 0


def main() -> int:
    arguments = build_parser().parse_args()
    return asyncio.run(async_main(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
