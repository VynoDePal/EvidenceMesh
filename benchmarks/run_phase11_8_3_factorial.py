#!/usr/bin/env python3
"""Run the locked Phase 11.8.3 observed-case 2x2 causal calibration.

One 20-result Tavily pool per already-observed Phase 11.7 case feeds four
factorial arms crossing equal/candidate projection with claims/direct response
contracts. Phase 12 remains sealed. Public output contains hashes and bounded
metrics, never questions, answers, evidence, prompts, credentials or reserve
identifiers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

try:
    from benchmarks import run_phase11_8_recovery as phase11_8
    from benchmarks.phase11_8_2_candidate import (
        DirectAnswerResponseError,
        balanced_baseline_project_blocks,
        build_direct_answer_prompt,
        candidate_project_blocks,
        parse_direct_answer,
        rendered_evidence_chars,
    )
except ModuleNotFoundError:
    import run_phase11_8_recovery as phase11_8  # type: ignore[no-redef]
    from phase11_8_2_candidate import (  # type: ignore[no-redef]
        DirectAnswerResponseError,
        balanced_baseline_project_blocks,
        build_direct_answer_prompt,
        candidate_project_blocks,
        parse_direct_answer,
        rendered_evidence_chars,
    )

from evidencemesh.citations import audit_citations

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-3-factorial-calibration-v1"
PROMPT_VERSION = "evidence-answer-phase11-8-3-factorial-v1"
LOCKED_PROTOCOL_SHA256 = "d139c1fed0d9c2bcfe7cdc02f1cda510802296ababbf360b6381c4db5e55239d"
LOCKED_MANIFEST_SHA256 = "da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e"
LOCKED_RESERVE_MANIFEST_SHA256 = "472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee"
LOCKED_PHASE11_8_RESULT_SHA256 = "0bd05884c6e6d019f22d18113ef449d1cf1c8158ac0e598d899ee1a93c4b687a"
LOCKED_PHASE11_8_2_RESULT_SHA256 = (
    "91e2ab81e95ca34ba8766f552db60018e44783fe9792857d30d2d9b1195c9bbd"
)
LOCKED_CANDIDATE_SHA256 = "0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e"

MODEL = "gemini-3.5-flash-lite"
MODELS = (MODEL,)
EQUAL_CLAIMS_ARM = "equal_claims"
CANDIDATE_CLAIMS_ARM = "candidate_claims"
EQUAL_DIRECT_ARM = "equal_direct"
CANDIDATE_DIRECT_ARM = "candidate_direct"
GENERATION_ARMS = (
    EQUAL_CLAIMS_ARM,
    CANDIDATE_CLAIMS_ARM,
    EQUAL_DIRECT_ARM,
    CANDIDATE_DIRECT_ARM,
)
CONTROL_ARM = EQUAL_CLAIMS_ARM
JOINT_CANDIDATE_ARM = CANDIDATE_DIRECT_ARM
EXPECTED_CASE_COUNT = phase11_8.PHASE11_7_CASE_COUNT
EXPECTED_RETRIEVAL_OPERATIONS = EXPECTED_CASE_COUNT
EXPECTED_TAVILY_REQUESTS = EXPECTED_CASE_COUNT
EXPECTED_GENERATION_REQUESTS = EXPECTED_CASE_COUNT * len(GENERATION_ARMS) * len(MODELS)
MINIMUM_PROMPT_ANSWER_COVERAGE = 20
MINIMUM_PROMPT_PAIRED_NET_GAIN = 2
MINIMUM_COMPLETIONS_PER_ARM = 23
MINIMUM_CONDITIONAL_SCHEMA_VALIDITY = 0.95
MINIMUM_JOINT_ANSWER_PAIRED_NET_GAIN = 2
MINIMUM_CITATION_PRESENCE = 0.95
MINIMUM_CITATION_ID_VALIDITY = 1.0
MINIMUM_CITATION_SUPPORT = 0.75


def projection_family(arm: str) -> str:
    if arm in {EQUAL_CLAIMS_ARM, EQUAL_DIRECT_ARM}:
        return "equal_cap"
    if arm in {CANDIDATE_CLAIMS_ARM, CANDIDATE_DIRECT_ARM}:
        return "rank_weighted_query_window_head_tail_v1"
    raise ValueError(f"unknown Phase 11.8.3 arm: {arm}")


def contract_family(arm: str) -> str:
    if arm in {EQUAL_CLAIMS_ARM, CANDIDATE_CLAIMS_ARM}:
        return "claims_json"
    if arm in {EQUAL_DIRECT_ARM, CANDIDATE_DIRECT_ARM}:
        return "direct_answer_json"
    raise ValueError(f"unknown Phase 11.8.3 arm: {arm}")


def project_blocks(
    row: phase11_8.BenchmarkRow,
    bundle: phase11_8.ArmBundle,
    *,
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
) -> tuple[phase11_8.EvidenceBlock, ...]:
    family = projection_family(bundle.arm)
    if family == "equal_cap":
        return balanced_baseline_project_blocks(
            bundle.blocks,
            evidence_budget_chars,
            max_block_chars,
        )
    return candidate_project_blocks(
        bundle.blocks,
        row.question,
        evidence_budget_chars,
        max_block_chars,
        min_block_chars=min_block_chars,
    )


def _claims_prompt(
    question: str,
    blocks: tuple[phase11_8.EvidenceBlock, ...],
) -> tuple[str, str]:
    allowed = ", ".join(f"[{block.citation_id}]" for block in blocks) or "None"
    rendered = phase11_8._render_prompt_blocks(blocks)
    user_prompt = (
        f"Question:\n{question}\n\n"
        f"Allowed citation identifiers:\n{allowed}\n\n"
        f"Evidence blocks:\n{rendered}\n\n"
        "Output this exact JSON shape with one concise claim preferred:\n"
        '{"claims":[{"text":"Concise factual claim.",'
        '"citation_ids":["S1"]}]}\n'
        "Use bare identifiers such as S1 in citation_ids. Every factual claim "
        "requires at least one supporting identifier. If support is insufficient, "
        f"use exactly {json.dumps(phase11_8.STRUCTURED_INSUFFICIENT_TEXT)} with an "
        "empty citation_ids list."
    )
    return phase11_8.STRUCTURED_SYSTEM_PROMPT, user_prompt


def build_prompt(
    row: phase11_8.BenchmarkRow,
    bundle: phase11_8.ArmBundle,
    *,
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
) -> tuple[str, str, tuple[phase11_8.EvidenceBlock, ...]]:
    included = project_blocks(
        row,
        bundle,
        evidence_budget_chars=evidence_budget_chars,
        max_block_chars=max_block_chars,
        min_block_chars=min_block_chars,
    )
    if contract_family(bundle.arm) == "claims_json":
        system_prompt, user_prompt = _claims_prompt(row.question, included)
    else:
        system_prompt, user_prompt = build_direct_answer_prompt(row.question, included)
    return system_prompt, user_prompt, included


def parse_contract_response(
    raw_answer: str,
    *,
    arm: str,
    allowed_ids: frozenset[str],
) -> tuple[str, int]:
    if contract_family(arm) == "claims_json":
        try:
            return phase11_8.parse_structured_answer(raw_answer)
        except phase11_8.StructuredResponseError as exc:
            raise DirectAnswerResponseError("response_schema_failure") from exc
    return parse_direct_answer(raw_answer, allowed_ids=allowed_ids), 1


def _sha256_file(path: Path) -> str:
    return phase11_8.sha256_bytes(path.read_bytes())


def validate_locked_sources(arguments: argparse.Namespace) -> dict[str, Any]:
    locked_paths = {
        "protocol": (arguments.protocol, LOCKED_PROTOCOL_SHA256),
        "manifest": (arguments.manifest, LOCKED_MANIFEST_SHA256),
        "reserve_manifest": (
            arguments.reserve_manifest,
            LOCKED_RESERVE_MANIFEST_SHA256,
        ),
        "phase11_8_result": (
            arguments.phase11_8_result,
            LOCKED_PHASE11_8_RESULT_SHA256,
        ),
        "phase11_8_2_result": (
            arguments.phase11_8_2_result,
            LOCKED_PHASE11_8_2_RESULT_SHA256,
        ),
        "candidate": (arguments.candidate, LOCKED_CANDIDATE_SHA256),
    }
    observed: dict[str, str] = {}
    for name, (path, expected) in locked_paths.items():
        actual = _sha256_file(path)
        if actual != expected:
            raise ValueError(f"Phase 11.8.3 {name} checksum changed")
        observed[name] = actual

    phase11_8_result = json.loads(arguments.phase11_8_result.read_bytes())
    phase11_8_2_result = json.loads(arguments.phase11_8_2_result.read_bytes())
    reserve = json.loads(arguments.reserve_manifest.read_bytes())
    if (
        phase11_8_result["decision"]["phase11_8_candidate_passed"] is not False
        or phase11_8_result["decision"]["release_decision"] != "no-go"
        or phase11_8_result["decision"]["phase12_executed"] is not False
    ):
        raise ValueError("historical Phase 11.8 no-go boundary changed")
    if (
        phase11_8_2_result["decision"]["offline_engineering_candidate_passed"] is not True
        or phase11_8_2_result["decision"]["real_case_quality_improvement_proven"] is not False
        or phase11_8_2_result["decision"]["phase11_8_3_live_calibration_authorized"] is not False
        or phase11_8_2_result["decision"]["release_decision"] != "no-go"
    ):
        raise ValueError("Phase 11.8.2 decision boundary changed")
    sealed_cases = reserve.get("sealed_cases")
    if (
        not isinstance(sealed_cases, list)
        or len(sealed_cases) != 96
        or any(set(case) != {"row_index", "case_id"} for case in sealed_cases)
    ):
        raise ValueError("Phase 12 sealed manifest shape changed")
    return {
        "status": "phase11_8_3_protocol_lock_valid",
        "hashes": observed,
        "historical_phase11_8_result": "fail_5_of_12",
        "historical_release_decision": "no-go",
        "phase12_sealed_case_count": len(sealed_cases),
        "network_requests": 0,
        "provider_calls": 0,
        "model_calls": 0,
        "live_authorized_by_protocol_publication": False,
    }


def validate_arguments(arguments: argparse.Namespace) -> None:
    if tuple(arguments.models) != MODELS:
        raise ValueError(f"Phase 11.8.3 requires the exact model order: {MODELS}")
    locked_values = {
        "provider_max_results": (arguments.provider_max_results, 20),
        "selection_limit": (arguments.selection_limit, 20),
        "max_per_domain": (arguments.max_per_domain, 3),
        "evidence_budget_chars": (arguments.evidence_budget_chars, 12_000),
        "max_block_chars": (arguments.max_block_chars, 1_500),
        "min_block_chars": (arguments.min_block_chars, 192),
        "max_output_tokens": (arguments.max_output_tokens, 2_048),
        "retrieval_wall_time_seconds": (
            arguments.retrieval_wall_time_seconds,
            30.0,
        ),
        "generation_wall_time_seconds": (
            arguments.generation_wall_time_seconds,
            60.0,
        ),
        "retrieval_pause_seconds": (arguments.retrieval_pause_seconds, 0.5),
        "model_pause_seconds": (arguments.model_pause_seconds, 2.0),
        "request_timeout_seconds": (arguments.request_timeout_seconds, 20.0),
    }
    changed = [
        f"{name}={actual!r} (expected {expected!r})"
        for name, (actual, expected) in locked_values.items()
        if actual != expected
    ]
    if changed:
        raise ValueError("Phase 11.8.3 locked arguments changed: " + ", ".join(changed))
    if arguments.gemini_api_key_env != "GEMINI_API_KEY":
        raise ValueError("Phase 11.8.3 requires GEMINI_API_KEY")
    if arguments.tavily_api_key_env != "TAVILY_API_KEY":
        raise ValueError("Phase 11.8.3 requires TAVILY_API_KEY")
    if not arguments.check_only and (arguments.dataset is None or arguments.output is None):
        raise ValueError("live execution requires --dataset and --output")


def public_retrieval_outcome(
    row: phase11_8.BenchmarkRow,
    bundle: phase11_8.ArmBundle,
    *,
    raw_pool_hash: str,
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
) -> dict[str, Any]:
    projections = tuple(
        project_blocks(
            row,
            bundle,
            evidence_budget_chars=evidence_budget_chars,
            max_block_chars=max_block_chars,
            min_block_chars=min_block_chars,
        )
        for _ in range(3)
    )
    included = projections[0]
    packet_hashes = {phase11_8.prompt_packet_sha256(blocks) for blocks in projections}
    candidate = projection_family(bundle.arm) != "equal_cap"
    rendered_chars = rendered_evidence_chars(included)
    return {
        "case_id": row.id,
        "arm": bundle.arm,
        "projection_family": projection_family(bundle.arm),
        "contract_family": contract_family(bundle.arm),
        "status": bundle.status,
        "available": bundle.available,
        "raw_result_count": bundle.raw_result_count,
        "fused_result_count": bundle.fused_result_count,
        "selected_result_count": bundle.selected_result_count,
        "prompt_result_count": len(included),
        "unique_domains": bundle.unique_domains,
        "selected_tavily_count": bundle.selected_tavily_count,
        "prompt_tavily_count": sum("tavily" in block.providers for block in included),
        "answer_key_in_selected_evidence": phase11_8.answer_covered(
            row.answers,
            (block.text for block in bundle.blocks),
        ),
        "answer_key_in_prompt_evidence": phase11_8.answer_covered(
            row.answers,
            (block.text for block in included),
        ),
        "raw_pool_sha256": raw_pool_hash,
        "selected_packet_sha256": phase11_8.prompt_packet_sha256(bundle.blocks),
        "prompt_packet_sha256": phase11_8.prompt_packet_sha256(included),
        "rendered_evidence_chars": rendered_chars,
        "exact_budget_compliant": rendered_chars <= evidence_budget_chars if candidate else None,
        "deterministic_three_replays": len(packet_hashes) == 1 if candidate else None,
        "retrieval_latency_ms": bundle.retrieval_latency_ms,
        "error_kind": bundle.error_kind,
    }


def aggregate_retrieval(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for arm in GENERATION_ARMS:
        rows = [outcome for outcome in outcomes if outcome["arm"] == arm]
        metrics[arm] = {
            "case_count": len(rows),
            "availability": phase11_8.ratio(
                sum(bool(outcome["available"]) for outcome in rows),
                len(rows),
            ),
            "answer_key_in_selected_evidence": phase11_8.ratio(
                sum(bool(outcome["answer_key_in_selected_evidence"]) for outcome in rows),
                len(rows),
            ),
            "answer_key_in_prompt_evidence": phase11_8.ratio(
                sum(bool(outcome["answer_key_in_prompt_evidence"]) for outcome in rows),
                len(rows),
            ),
            "mean_selected_result_count": round(
                statistics.fmean(int(outcome["selected_result_count"]) for outcome in rows),
                3,
            ),
            "mean_prompt_result_count": round(
                statistics.fmean(int(outcome["prompt_result_count"]) for outcome in rows),
                3,
            ),
        }
    return metrics


def packet_identity(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for outcome in outcomes:
        by_case.setdefault(str(outcome["case_id"]), {})[str(outcome["arm"])] = outcome
    counts = {
        "raw_pool_matching_cases": 0,
        "selected_packet_matching_cases": 0,
        "equal_contract_packet_matching_cases": 0,
        "candidate_contract_packet_matching_cases": 0,
        "candidate_deterministic_cases": 0,
        "candidate_budget_compliant_cases": 0,
    }
    for arms in by_case.values():
        if len(arms) != len(GENERATION_ARMS):
            continue
        if len({str(value["raw_pool_sha256"]) for value in arms.values()}) == 1:
            counts["raw_pool_matching_cases"] += 1
        if len({str(value["selected_packet_sha256"]) for value in arms.values()}) == 1:
            counts["selected_packet_matching_cases"] += 1
        if (
            arms[EQUAL_CLAIMS_ARM]["prompt_packet_sha256"]
            == arms[EQUAL_DIRECT_ARM]["prompt_packet_sha256"]
        ):
            counts["equal_contract_packet_matching_cases"] += 1
        if (
            arms[CANDIDATE_CLAIMS_ARM]["prompt_packet_sha256"]
            == arms[CANDIDATE_DIRECT_ARM]["prompt_packet_sha256"]
        ):
            counts["candidate_contract_packet_matching_cases"] += 1
        if all(
            bool(arms[arm]["deterministic_three_replays"])
            for arm in (CANDIDATE_CLAIMS_ARM, CANDIDATE_DIRECT_ARM)
        ):
            counts["candidate_deterministic_cases"] += 1
        if all(
            bool(arms[arm]["exact_budget_compliant"])
            for arm in (CANDIDATE_CLAIMS_ARM, CANDIDATE_DIRECT_ARM)
        ):
            counts["candidate_budget_compliant_cases"] += 1
    return {
        **counts,
        "denominator": len(by_case),
        "raw_and_selected_passed": (
            len(by_case) == EXPECTED_CASE_COUNT
            and counts["raw_pool_matching_cases"] == EXPECTED_CASE_COUNT
            and counts["selected_packet_matching_cases"] == EXPECTED_CASE_COUNT
        ),
        "projection_contract_identity_passed": all(
            counts[name] == EXPECTED_CASE_COUNT
            for name in (
                "equal_contract_packet_matching_cases",
                "candidate_contract_packet_matching_cases",
                "candidate_deterministic_cases",
                "candidate_budget_compliant_cases",
            )
        ),
    }


def paired_retrieval_metrics(
    outcomes: list[dict[str, Any]],
    *,
    field: str,
    candidate_arm: str,
    baseline_arm: str,
) -> dict[str, Any]:
    records = {(str(row["case_id"]), str(row["arm"])): row for row in outcomes}
    case_ids = sorted({case_id for case_id, _arm in records})
    return _paired_binary(
        [
            (
                bool(records[(case_id, candidate_arm)][field]),
                bool(records[(case_id, baseline_arm)][field]),
            )
            for case_id in case_ids
        ],
        field=field,
        candidate_arm=candidate_arm,
        baseline_arm=baseline_arm,
        eligible_pairs=len(case_ids),
    )


def _paired_binary(
    pairs: list[tuple[bool, bool]],
    *,
    field: str,
    candidate_arm: str,
    baseline_arm: str,
    eligible_pairs: int,
) -> dict[str, Any]:
    candidate_wins = sum(candidate and not baseline for candidate, baseline in pairs)
    baseline_wins = sum(baseline and not candidate for candidate, baseline in pairs)
    shared_hits = sum(candidate and baseline for candidate, baseline in pairs)
    shared_misses = sum(not candidate and not baseline for candidate, baseline in pairs)
    return {
        "field": field,
        "candidate_arm": candidate_arm,
        "baseline_arm": baseline_arm,
        "eligible_pairs": eligible_pairs,
        "candidate_wins": candidate_wins,
        "baseline_wins": baseline_wins,
        "shared_hits": shared_hits,
        "shared_misses": shared_misses,
        "net_gain": candidate_wins - baseline_wins,
    }


def _failed_generation_outcome(
    *,
    row: phase11_8.BenchmarkRow,
    bundle: phase11_8.ArmBundle,
    model: str,
    included: tuple[phase11_8.EvidenceBlock, ...],
    system_prompt: str,
    user_prompt: str,
    latency_ms: float,
    error_kind: str,
    native_request_completed: bool,
) -> dict[str, Any]:
    return {
        "case_id": row.id,
        "arm": bundle.arm,
        "projection_family": projection_family(bundle.arm),
        "contract_family": contract_family(bundle.arm),
        "model": model,
        "status": "failed",
        "native_request_completed": native_request_completed,
        "structured_schema_valid": False if native_request_completed else None,
        "structured_claim_count": 0,
        "answer_sha256": None,
        "answer_chars": 0,
        "answer_key_covered": False,
        "citation_count": 0,
        "invalid_citation_count": 0,
        "malformed_citation_count": 0,
        "citation_ids_valid": False,
        "citation_contract_passed": False,
        "citation_support_proxy": False,
        "prompt_evidence_count": len(included),
        "prompt_packet_sha256": phase11_8.prompt_packet_sha256(included),
        "prompt_sha256": phase11_8.canonical_json_sha256(
            {
                "system_instruction": system_prompt,
                "user_prompt": user_prompt,
            }
        ),
        "system_prompt_sha256": phase11_8.sha256_bytes(system_prompt.encode()),
        "response_model": None,
        "finish_reason": None,
        "usage": {},
        "generation_latency_ms": latency_ms,
        "error_kind": error_kind,
    }


async def generate_outcome(
    row: phase11_8.BenchmarkRow,
    bundle: phase11_8.ArmBundle,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
    max_output_tokens: int,
    wall_time_seconds: float,
) -> dict[str, Any]:
    system_prompt, user_prompt, included = build_prompt(
        row,
        bundle,
        evidence_budget_chars=evidence_budget_chars,
        max_block_chars=max_block_chars,
        min_block_chars=min_block_chars,
    )
    evidence_by_id = {block.citation_id: block.text for block in included}
    started = time.perf_counter()
    try:
        async with asyncio.timeout(wall_time_seconds):
            completion = await phase11_8.request_gemini_completion(
                client,
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
            )
    except TimeoutError:
        error_kind = "generation_wall_timeout"
    except phase11_8.ModelRequestError as exc:
        error_kind = exc.kind
    except Exception as exc:
        error_kind = phase11_8._safe_error(exc, "generation")
    else:
        try:
            answer, claim_count = parse_contract_response(
                completion.answer,
                arm=bundle.arm,
                allowed_ids=frozenset(evidence_by_id),
            )
        except DirectAnswerResponseError:
            latency_ms = round((time.perf_counter() - started) * 1_000, 3)
            return _failed_generation_outcome(
                row=row,
                bundle=bundle,
                model=model,
                included=included,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                latency_ms=latency_ms,
                error_kind="response_schema_failure",
                native_request_completed=True,
            )
        citation_audit = audit_citations(answer, evidence_by_id, citations_required=True)
        support_proxy = any(
            phase11_8.answer_covered(row.answers, (evidence_by_id[citation_id],))
            for citation_id in citation_audit.citation_ids
        )
        return {
            "case_id": row.id,
            "arm": bundle.arm,
            "projection_family": projection_family(bundle.arm),
            "contract_family": contract_family(bundle.arm),
            "model": model,
            "status": "completed",
            "native_request_completed": True,
            "structured_schema_valid": True,
            "structured_claim_count": claim_count,
            "answer_sha256": phase11_8.sha256_bytes(answer.encode()),
            "answer_chars": len(answer),
            "answer_key_covered": phase11_8.answer_covered(row.answers, (answer,)),
            "citation_count": len(citation_audit.citation_ids),
            "invalid_citation_count": len(citation_audit.invalid_ids),
            "malformed_citation_count": len(citation_audit.malformed_tokens),
            "citation_ids_valid": citation_audit.identifier_integrity_valid,
            "citation_contract_passed": citation_audit.valid,
            "citation_support_proxy": support_proxy,
            "prompt_evidence_count": len(included),
            "prompt_packet_sha256": phase11_8.prompt_packet_sha256(included),
            "prompt_sha256": phase11_8.canonical_json_sha256(
                {
                    "system_instruction": system_prompt,
                    "user_prompt": user_prompt,
                }
            ),
            "system_prompt_sha256": phase11_8.sha256_bytes(system_prompt.encode()),
            "response_model": completion.response_model,
            "finish_reason": completion.finish_reason,
            "usage": completion.usage,
            "generation_latency_ms": round((time.perf_counter() - started) * 1_000, 3),
            "error_kind": None,
        }
    latency_ms = round((time.perf_counter() - started) * 1_000, 3)
    return _failed_generation_outcome(
        row=row,
        bundle=bundle,
        model=model,
        included=included,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        latency_ms=latency_ms,
        error_kind=error_kind,
        native_request_completed=False,
    )


async def generate_all(
    rows: list[phase11_8.BenchmarkRow],
    bundles: dict[tuple[str, str], phase11_8.ArmBundle],
    *,
    api_key: str,
    models: tuple[str, ...],
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
    max_output_tokens: int,
    wall_time_seconds: float,
    pause_seconds: float,
    progress: bool,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    pacer = phase11_8.RequestPacer(pause_seconds)
    timeout = httpx.Timeout(
        connect=20.0,
        read=wall_time_seconds,
        write=30.0,
        pool=20.0,
    )
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": "EvidenceMesh benchmark/0.1"},
    ) as client:
        for case_index, row in enumerate(rows):
            for arm_index, arm in enumerate(phase11_8._rotated(GENERATION_ARMS, case_index)):
                for model in phase11_8._rotated(models, case_index + arm_index):
                    await pacer.wait()
                    outcome = await generate_outcome(
                        row,
                        bundles[(row.id, arm)],
                        client=client,
                        api_key=api_key,
                        model=model,
                        evidence_budget_chars=evidence_budget_chars,
                        max_block_chars=max_block_chars,
                        min_block_chars=min_block_chars,
                        max_output_tokens=max_output_tokens,
                        wall_time_seconds=wall_time_seconds,
                    )
                    outcomes.append(outcome)
                    if progress:
                        print(
                            f"[generation {row.id} {arm} {model}] "
                            f"{outcome['status']}; proxy={outcome['answer_key_covered']}; "
                            f"citations={outcome['citation_count']}",
                            file=sys.stderr,
                            flush=True,
                        )
    return outcomes


def aggregate_generation_rows(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = phase11_8.aggregate_phase11_7_generation_rows(outcomes)
    native = [outcome for outcome in outcomes if outcome["native_request_completed"]]
    metrics["native_request_completed"] = phase11_8.ratio(len(native), len(outcomes))
    metrics["structured_schema_valid_all_attempts"] = phase11_8.ratio(
        sum(bool(outcome["structured_schema_valid"]) for outcome in outcomes),
        len(outcomes),
    )
    metrics["structured_schema_valid_given_native_response"] = phase11_8.ratio(
        sum(bool(outcome["structured_schema_valid"]) for outcome in native),
        len(native),
    )
    return metrics


def aggregate_generation(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "aggregate": {
            arm: aggregate_generation_rows(
                [outcome for outcome in outcomes if outcome["arm"] == arm]
            )
            for arm in GENERATION_ARMS
        },
        "by_model": {
            model: {
                arm: aggregate_generation_rows(
                    [
                        outcome
                        for outcome in outcomes
                        if outcome["model"] == model and outcome["arm"] == arm
                    ]
                )
                for arm in GENERATION_ARMS
            }
            for model in MODELS
        },
    }


def paired_generation_metrics(
    outcomes: list[dict[str, Any]],
    *,
    field: str,
    candidate_arm: str,
    baseline_arm: str,
    completed_only: bool,
) -> dict[str, Any]:
    records = {(str(row["model"]), str(row["case_id"]), str(row["arm"])): row for row in outcomes}
    pairs: list[tuple[bool, bool]] = []
    for model in MODELS:
        case_ids = sorted(
            {case_id for record_model, case_id, _arm in records if record_model == model}
        )
        for case_id in case_ids:
            candidate = records[(model, case_id, candidate_arm)]
            baseline = records[(model, case_id, baseline_arm)]
            if completed_only and (
                candidate["status"] != "completed" or baseline["status"] != "completed"
            ):
                continue
            pairs.append((bool(candidate[field]), bool(baseline[field])))
    result = _paired_binary(
        pairs,
        field=field,
        candidate_arm=candidate_arm,
        baseline_arm=baseline_arm,
        eligible_pairs=len(pairs),
    )
    result["conditioning"] = "both_completed" if completed_only else "all_attempts"
    return result


def build_decision(
    retrieval_metrics: dict[str, Any],
    generation_metrics: dict[str, Any],
    prompt_paired: dict[str, Any],
    answer_pairs: dict[str, dict[str, Any]],
    support_paired: dict[str, Any],
    identity: dict[str, Any],
    *,
    retrieval_operations: int,
    generation_requests: int,
    tavily_requests: int,
) -> dict[str, Any]:
    aggregate = generation_metrics["aggregate"]
    equal_prompt_hits = int(
        retrieval_metrics[EQUAL_CLAIMS_ARM]["answer_key_in_prompt_evidence"]["numerator"]
    )
    candidate_prompt_hits = int(
        retrieval_metrics[CANDIDATE_CLAIMS_ARM]["answer_key_in_prompt_evidence"]["numerator"]
    )
    completions = {arm: int(aggregate[arm]["completed"]["numerator"]) for arm in GENERATION_ARMS}
    conditional_schema = {
        arm: aggregate[arm]["structured_schema_valid_given_native_response"]
        for arm in GENERATION_ARMS
    }
    joint = aggregate[JOINT_CANDIDATE_ARM]
    control = aggregate[CONTROL_ARM]
    joint_answer_hits = int(joint["answer_key_covered"]["numerator"])
    control_answer_hits = int(control["answer_key_covered"]["numerator"])
    citation_presence = joint["citation_presence"]["rate"]
    citation_id_validity = joint["citation_ids_valid"]["rate"]
    citation_support = joint["citation_support_proxy"]["rate"]
    gates = {
        "locked_inputs_and_exact_traffic": {
            "passed": (
                retrieval_operations == EXPECTED_RETRIEVAL_OPERATIONS
                and generation_requests == EXPECTED_GENERATION_REQUESTS
                and tavily_requests == EXPECTED_TAVILY_REQUESTS
            ),
            "retrieval_operations": retrieval_operations,
            "expected_retrieval_operations": EXPECTED_RETRIEVAL_OPERATIONS,
            "generation_requests": generation_requests,
            "expected_generation_requests": EXPECTED_GENERATION_REQUESTS,
            "tavily_requests": tavily_requests,
            "expected_tavily_requests": EXPECTED_TAVILY_REQUESTS,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "shared_raw_pool_and_selected_packet": {
            "passed": bool(identity["raw_and_selected_passed"]),
            "observed": identity,
        },
        "projection_contract_identity_determinism_and_budget": {
            "passed": bool(identity["projection_contract_identity_passed"]),
            "observed": identity,
        },
        "candidate_prompt_proxy_absolute_and_positive_gain": {
            "passed": (
                candidate_prompt_hits >= MINIMUM_PROMPT_ANSWER_COVERAGE
                and candidate_prompt_hits >= equal_prompt_hits
                and int(prompt_paired["net_gain"]) >= MINIMUM_PROMPT_PAIRED_NET_GAIN
            ),
            "equal_cap_hits": equal_prompt_hits,
            "candidate_hits": candidate_prompt_hits,
            "paired": prompt_paired,
            "minimum_candidate_hits": MINIMUM_PROMPT_ANSWER_COVERAGE,
            "minimum_paired_net_gain": MINIMUM_PROMPT_PAIRED_NET_GAIN,
        },
        "completion_at_least_23_of_24_per_arm": {
            "passed": all(value >= MINIMUM_COMPLETIONS_PER_ARM for value in completions.values()),
            "observed": completions,
            "required": MINIMUM_COMPLETIONS_PER_ARM,
            "denominator": EXPECTED_CASE_COUNT,
        },
        "conditional_schema_validity_at_least_95_percent_per_arm": {
            "passed": all(
                value["rate"] is not None
                and float(value["rate"]) >= MINIMUM_CONDITIONAL_SCHEMA_VALIDITY
                for value in conditional_schema.values()
            ),
            "observed": conditional_schema,
            "required_rate": MINIMUM_CONDITIONAL_SCHEMA_VALIDITY,
        },
        "joint_answer_positive_gain_vs_control": {
            "passed": (
                joint_answer_hits >= control_answer_hits
                and int(answer_pairs["joint_all"]["net_gain"])
                >= MINIMUM_JOINT_ANSWER_PAIRED_NET_GAIN
                and int(answer_pairs["joint_completed"]["net_gain"]) >= 0
            ),
            "control_hits": control_answer_hits,
            "joint_candidate_hits": joint_answer_hits,
            "all_attempts": answer_pairs["joint_all"],
            "both_completed": answer_pairs["joint_completed"],
            "minimum_all_attempt_paired_net_gain": MINIMUM_JOINT_ANSWER_PAIRED_NET_GAIN,
        },
        "projection_answer_no_regression_under_claims": {
            "passed": int(answer_pairs["projection_claims"]["net_gain"]) >= 0,
            "paired": answer_pairs["projection_claims"],
        },
        "projection_answer_no_regression_under_direct": {
            "passed": int(answer_pairs["projection_direct"]["net_gain"]) >= 0,
            "paired": answer_pairs["projection_direct"],
        },
        "direct_contract_answer_no_regression_on_equal_projection": {
            "passed": int(answer_pairs["contract_equal"]["net_gain"]) >= 0,
            "paired": answer_pairs["contract_equal"],
        },
        "direct_contract_answer_no_regression_on_candidate_projection": {
            "passed": int(answer_pairs["contract_candidate"]["net_gain"]) >= 0,
            "paired": answer_pairs["contract_candidate"],
        },
        "candidate_direct_citation_presence_at_least_95_percent": {
            "passed": (
                citation_presence is not None
                and float(citation_presence) >= MINIMUM_CITATION_PRESENCE
            ),
            "observed": joint["citation_presence"],
            "required_rate": MINIMUM_CITATION_PRESENCE,
        },
        "candidate_direct_citation_ids_100_percent_valid": {
            "passed": citation_id_validity == MINIMUM_CITATION_ID_VALIDITY,
            "observed": joint["citation_ids_valid"],
            "required_rate": MINIMUM_CITATION_ID_VALIDITY,
        },
        "candidate_direct_citation_support_floor_and_no_regression": {
            "passed": (
                citation_support is not None
                and float(citation_support) >= MINIMUM_CITATION_SUPPORT
                and int(support_paired["net_gain"]) >= 0
            ),
            "observed": joint["citation_support_proxy"],
            "required_rate": MINIMUM_CITATION_SUPPORT,
            "paired_vs_control_both_completed": support_paired,
        },
    }
    candidate_passed = all(bool(gate["passed"]) for gate in gates.values())
    return {
        "gates": gates,
        "phase11_8_3_candidate_passed": candidate_passed,
        "phase11_9_protocol_may_be_frozen": candidate_passed,
        "phase11_9_executed": False,
        "historical_phase11_8_result_changed": False,
        "quality_profile_promotion_allowed": False,
        "quality_profile_promoted": False,
        "community_profile_unchanged": True,
        "quality_profile_unchanged": True,
        "users_choose_provider_model_and_credentials": True,
        "phase12_authorized": False,
        "phase12_executed": False,
        "external_competitor_benchmark_allowed": False,
        "public_alpha_allowed": False,
        "superiority_claim_allowed": False,
        "merge_allowed": False,
        "release_allowed": False,
        "release_decision": "no-go",
        "reason": (
            "Phase 11.8.3 reuses observed calibration cases. A fourteen-gate pass "
            "may justify only a separately frozen fresh Phase 11.9 protocol."
        ),
    }


async def run(arguments: argparse.Namespace) -> dict[str, Any]:
    validate_arguments(arguments)
    lock_validation = validate_locked_sources(arguments)
    rows, manifest, dataset_metadata, reserve_metadata = phase11_8.load_phase11_7_rows(
        arguments.dataset,
        arguments.manifest,
        arguments.reserve_manifest,
        root=REPOSITORY_ROOT,
        expected_manifest_sha256=LOCKED_MANIFEST_SHA256,
        expected_reserve_manifest_sha256=LOCKED_RESERVE_MANIFEST_SHA256,
    )
    gemini_api_key = os.getenv(arguments.gemini_api_key_env)
    tavily_api_key = os.getenv(arguments.tavily_api_key_env)
    if not gemini_api_key:
        raise ValueError("Gemini API key is not configured")
    if not tavily_api_key:
        raise ValueError("Tavily API key is not configured")

    cache_root = Path(arguments.cache_root)
    await asyncio.to_thread(cache_root.mkdir, parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    (
        legacy_bundles,
        raw_hashes,
        diagnostics,
        retrieval_traffic,
        health,
    ) = await phase11_8.retrieve_all(
        rows,
        tavily_api_key=tavily_api_key,
        cache_root=cache_root,
        provider_max_results=arguments.provider_max_results,
        current_selection_limit=10,
        expanded_selection_limit=arguments.selection_limit,
        max_per_domain=arguments.max_per_domain,
        request_timeout_seconds=arguments.request_timeout_seconds,
        wall_time_seconds=arguments.retrieval_wall_time_seconds,
        pause_seconds=arguments.retrieval_pause_seconds,
        progress=arguments.progress,
    )
    bundles = {
        (row.id, arm): replace(
            legacy_bundles[(row.id, phase11_8.EXPANDED_ARM)],
            arm=arm,
        )
        for row in rows
        for arm in GENERATION_ARMS
    }
    retrieval_outcomes = [
        public_retrieval_outcome(
            row,
            bundles[(row.id, arm)],
            raw_pool_hash=raw_hashes[row.id],
            evidence_budget_chars=arguments.evidence_budget_chars,
            max_block_chars=arguments.max_block_chars,
            min_block_chars=arguments.min_block_chars,
        )
        for row in rows
        for arm in GENERATION_ARMS
    ]
    identity = packet_identity(retrieval_outcomes)
    generation_outcomes = await generate_all(
        rows,
        bundles,
        api_key=gemini_api_key,
        models=tuple(arguments.models),
        evidence_budget_chars=arguments.evidence_budget_chars,
        max_block_chars=arguments.max_block_chars,
        min_block_chars=arguments.min_block_chars,
        max_output_tokens=arguments.max_output_tokens,
        wall_time_seconds=arguments.generation_wall_time_seconds,
        pause_seconds=arguments.model_pause_seconds,
        progress=arguments.progress,
    )
    retrieval_metrics = aggregate_retrieval(retrieval_outcomes)
    generation_metrics = aggregate_generation(generation_outcomes)
    prompt_paired = paired_retrieval_metrics(
        retrieval_outcomes,
        field="answer_key_in_prompt_evidence",
        candidate_arm=CANDIDATE_CLAIMS_ARM,
        baseline_arm=EQUAL_CLAIMS_ARM,
    )
    comparisons = {
        "joint_all": (CANDIDATE_DIRECT_ARM, EQUAL_CLAIMS_ARM, False),
        "joint_completed": (CANDIDATE_DIRECT_ARM, EQUAL_CLAIMS_ARM, True),
        "projection_claims": (CANDIDATE_CLAIMS_ARM, EQUAL_CLAIMS_ARM, True),
        "projection_direct": (CANDIDATE_DIRECT_ARM, EQUAL_DIRECT_ARM, True),
        "contract_equal": (EQUAL_DIRECT_ARM, EQUAL_CLAIMS_ARM, True),
        "contract_candidate": (CANDIDATE_DIRECT_ARM, CANDIDATE_CLAIMS_ARM, True),
    }
    answer_pairs = {
        name: paired_generation_metrics(
            generation_outcomes,
            field="answer_key_covered",
            candidate_arm=candidate_arm,
            baseline_arm=baseline_arm,
            completed_only=completed_only,
        )
        for name, (candidate_arm, baseline_arm, completed_only) in comparisons.items()
    }
    support_paired = paired_generation_metrics(
        generation_outcomes,
        field="citation_support_proxy",
        candidate_arm=CANDIDATE_DIRECT_ARM,
        baseline_arm=EQUAL_CLAIMS_ARM,
        completed_only=True,
    )
    decision = build_decision(
        retrieval_metrics,
        generation_metrics,
        prompt_paired,
        answer_pairs,
        support_paired,
        identity,
        retrieval_operations=retrieval_traffic["case_retrieval_operations"],
        generation_requests=len(generation_outcomes),
        tavily_requests=retrieval_traffic["tavily_requests"],
    )
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": "observed 2x2 projection and response-contract causal calibration",
        "suite": {
            "manifest_sha256": LOCKED_MANIFEST_SHA256,
            "phase11_8_result_sha256": LOCKED_PHASE11_8_RESULT_SHA256,
            "phase11_8_2_result_sha256": LOCKED_PHASE11_8_2_RESULT_SHA256,
            "sample_count": len(rows),
            "case_ids": [row.id for row in rows],
            "topic_distribution": manifest["topic_distribution"],
            "answer_type_distribution": manifest["answer_type_distribution"],
            "purpose": "corrective calibration on the already-observed Phase 11.7 suite",
            "fresh_for_phase11_8_3": False,
            "phase12_cases_used": False,
        },
        "dataset": dataset_metadata,
        "phase12_reserve": reserve_metadata,
        "lock_validation": lock_validation,
        "protocol": {
            "path": str(arguments.protocol),
            "sha256": LOCKED_PROTOCOL_SHA256,
            "prompt_version": PROMPT_VERSION,
            "models": list(MODELS),
            "generation_arms": list(GENERATION_ARMS),
            "control_arm": CONTROL_ARM,
            "joint_candidate_arm": JOINT_CANDIDATE_ARM,
            "factorial_design": {
                arm: {
                    "projection": projection_family(arm),
                    "response_contract": contract_family(arm),
                }
                for arm in GENERATION_ARMS
            },
            "provider_bundle": ["tavily"],
            "one_raw_tavily_pool_per_case": True,
            "provider_request_repeated_per_arm": False,
            "selected_packet_shared_by_all_arms": True,
            "provider_max_results": arguments.provider_max_results,
            "selection_limit": arguments.selection_limit,
            "max_per_domain": arguments.max_per_domain,
            "evidence_prompt_budget_chars": arguments.evidence_budget_chars,
            "max_block_chars": arguments.max_block_chars,
            "candidate_min_block_chars": arguments.min_block_chars,
            "candidate_projection_replays": 3,
            "claims_parser": "locked Phase 11.8 strict raw JSON parser",
            "direct_parser": "locked Phase 11.8.2 strict raw JSON parser",
            "cache": False,
            "retry_policy": "none; no selective retry, fallback or repair",
            "expected_retrieval_operations": EXPECTED_RETRIEVAL_OPERATIONS,
            "expected_tavily_requests": EXPECTED_TAVILY_REQUESTS,
            "expected_generation_requests": EXPECTED_GENERATION_REQUESTS,
            "explicit_live_authorization_required": True,
            "manual_live_dispatch_supported": True,
            "same_repository_pr_label_authorization_supported": True,
            "live_authorization_label": "phase11.8.3-live-authorized",
            "protocol_publication_authorizes_live": False,
            "quality_profile_before_run": "unchanged mixed optional quality profile",
            "quality_profile_after_run": "unchanged regardless of result",
            "community_profile_unchanged": True,
            "users_choose_provider_model_and_credentials": True,
            "scoring": {
                "answer_key_covered": (
                    "normalized reference-answer substring in generated answer; proxy only"
                ),
                "answer_key_in_prompt_evidence": (
                    "normalized reference-answer substring in projected evidence; proxy only"
                ),
                "citation_support_proxy": (
                    "at least one cited block contains the normalized reference answer"
                ),
                "citation_identifier_integrity": (
                    "exact syntax and membership in the projected evidence packet"
                ),
                "structured_schema_valid": "strict JSON and exact local schema validation",
                "official_simpleqa_evaluation": "not run",
            },
        },
        "environment": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "commit_sha": phase11_8.commit_sha(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "network_region": arguments.network_region,
            "dependency_versions": {
                package: phase11_8.package_version(package)
                for package in ("fastmcp", "httpx", "pydantic")
            },
        },
        "traffic": {
            **retrieval_traffic,
            "expected_retrieval_operations": EXPECTED_RETRIEVAL_OPERATIONS,
            "generation_requests": len(generation_outcomes),
            "expected_generation_requests": EXPECTED_GENERATION_REQUESTS,
            "expected_tavily_requests": EXPECTED_TAVILY_REQUESTS,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "retrieval_health_after": health,
        "retrieval_diagnostics": diagnostics,
        "retrieval_metrics": retrieval_metrics,
        "packet_identity": identity,
        "retrieval_prompt_coverage_paired": prompt_paired,
        "generation_metrics": generation_metrics,
        "paired_answer_key_coverage": answer_pairs,
        "paired_citation_support": support_paired,
        "decision": decision,
        "retrieval_outcomes": retrieval_outcomes,
        "generation_outcomes": generation_outcomes,
        "privacy": {
            "questions_in_report": False,
            "reference_answers_in_report": False,
            "source_titles_or_urls_in_report": False,
            "source_snippets_or_evidence_in_report": False,
            "system_or_user_prompts_in_report": False,
            "generated_answers_in_report": False,
            "raw_structured_responses_in_report": False,
            "answer_hashes_in_report": True,
            "api_keys_in_report": False,
            "phase12_reserved_case_ids_in_report": False,
        },
        "warnings": [
            (
                "Phase 11.8.3 reuses observed calibration cases. A pass is not a "
                "fresh confirmation and cannot promote quality or authorize Phase 12."
            ),
            (
                "Substring and identifier metrics are transparent proxies, not official "
                "SimpleQA accuracy or semantic citation evaluation."
            ),
            (
                "Only Gemini 3.5 Flash Lite is tested to isolate the causal mechanism; "
                "cross-model robustness remains unproven."
            ),
            (
                "Live Tavily results and hosted model outputs are non-deterministic; "
                "selective retry is forbidden."
            ),
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    root = REPOSITORY_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=root / "benchmarks/data/phase11_7_fresh_confirmation_v1.json",
    )
    parser.add_argument(
        "--reserve-manifest",
        type=Path,
        default=root / "benchmarks/data/phase12_untouched_reserve_v1.json",
    )
    parser.add_argument(
        "--phase11-8-result",
        type=Path,
        default=root / "benchmarks/results/phase11_8_recovery_2026-07-29.json",
    )
    parser.add_argument(
        "--phase11-8-2-result",
        type=Path,
        default=(root / "benchmarks/results/phase11_8_2_offline_design_2026-07-30.json"),
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=root / "benchmarks/phase11_8_2_candidate.py",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=root / "docs/benchmark-protocol-v18.md",
    )
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--tavily-api-key-env", default="TAVILY_API_KEY")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(tempfile.gettempdir()) / "evidencemesh-phase11-8-3",
    )
    parser.add_argument("--provider-max-results", type=int, default=20)
    parser.add_argument("--selection-limit", type=int, default=20)
    parser.add_argument("--max-per-domain", type=int, default=3)
    parser.add_argument("--evidence-budget-chars", type=int, default=12_000)
    parser.add_argument("--max-block-chars", type=int, default=1_500)
    parser.add_argument("--min-block-chars", type=int, default=192)
    parser.add_argument("--max-output-tokens", type=int, default=2_048)
    parser.add_argument("--retrieval-wall-time-seconds", type=float, default=30.0)
    parser.add_argument("--generation-wall-time-seconds", type=float, default=60.0)
    parser.add_argument("--retrieval-pause-seconds", type=float, default=0.5)
    parser.add_argument("--model-pause-seconds", type=float, default=2.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=20.0)
    parser.add_argument(
        "--network-region",
        default=os.getenv("EVIDENCEMESH_BENCHMARK_REGION", "not reported"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    validate_arguments(arguments)
    if arguments.check_only:
        print(
            json.dumps(
                validate_locked_sources(arguments),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    report = asyncio.run(run(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
