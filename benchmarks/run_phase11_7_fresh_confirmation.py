#!/usr/bin/env python3
"""Run the locked Phase 11.7 fresh Tavily confirmation calibration.

The 24 cases are selected deterministically after excluding every prior
SimpleQA case. Each case makes one Tavily request. The resulting selected and
projected packet is shared byte-for-byte by a legacy-prompt arm and a
strict-citation arm. A separate 96-case Phase 12 reserve stays sealed.
Questions, reference answers, evidence, URLs, prompts, reserved identifiers and
generated answers are excluded from the public report.
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
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

try:
    from benchmarks.phase11_7_dataset import (
        PHASE11_7_CASE_COUNT,
        load_phase11_7_rows,
    )
    from benchmarks.run_end_to_end_phase10 import (
        EvidenceBlock,
        ModelRequestError,
        RequestPacer,
        canonical_json_sha256,
        paired_answer_metrics,
        ratio,
    )
    from benchmarks.run_live_retrieval import (
        BenchmarkRow,
        answer_covered,
        commit_sha,
        package_version,
        percentile,
        sha256_bytes,
    )
    from benchmarks.run_phase11_5_quality_recovery import (
        CANDIDATE_SYSTEM_PROMPT,
        LEGACY_SYSTEM_PROMPT,
        ArmBundle,
        _legacy_projection,
        _render_prompt_blocks,
        _rotated,
        _safe_error,
        replay_arm,
        request_gemini_completion,
    )
    from benchmarks.run_phase11_calibration import RawResultRecorder, RecordingProvider
except ModuleNotFoundError:
    from phase11_7_dataset import (  # type: ignore[no-redef]
        PHASE11_7_CASE_COUNT,
        load_phase11_7_rows,
    )
    from run_end_to_end_phase10 import (  # type: ignore[no-redef]
        EvidenceBlock,
        ModelRequestError,
        RequestPacer,
        canonical_json_sha256,
        paired_answer_metrics,
        ratio,
    )
    from run_live_retrieval import (  # type: ignore[no-redef]
        BenchmarkRow,
        answer_covered,
        commit_sha,
        package_version,
        percentile,
        sha256_bytes,
    )
    from run_phase11_5_quality_recovery import (  # type: ignore[no-redef]
        CANDIDATE_SYSTEM_PROMPT,
        LEGACY_SYSTEM_PROMPT,
        ArmBundle,
        _legacy_projection,
        _render_prompt_blocks,
        _rotated,
        _safe_error,
        replay_arm,
        request_gemini_completion,
    )
    from run_phase11_calibration import (  # type: ignore[no-redef]
        RawResultRecorder,
        RecordingProvider,
    )

from evidencemesh.citations import audit_citations
from evidencemesh.config import DeploymentProfile, Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest
from evidencemesh.providers.base import SearchProvider

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-7-fresh-confirmation-v1"
PROMPT_VERSION = "evidence-answer-phase11-7-v1"
LOCKED_PROTOCOL_SHA256 = "a38cfdd9f8bb4ca9ebf39caac212e7868a773b62c874e1738bc8a5ff9ea1088e"
LOCKED_MANIFEST_SHA256 = "da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e"
LOCKED_RESERVE_MANIFEST_SHA256 = "472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee"
MODELS = (
    "gemma-4-31b-it",
    "gemini-3.5-flash-lite",
)
EXPECTED_CASE_COUNT = PHASE11_7_CASE_COUNT
GENERATION_ARMS = ("tavily_legacy", "tavily_strict")
BASELINE_ARM = "tavily_legacy"
CANDIDATE_ARM = "tavily_strict"
EXPECTED_RETRIEVAL_OPERATIONS = EXPECTED_CASE_COUNT
EXPECTED_GENERATION_REQUESTS = EXPECTED_CASE_COUNT * len(GENERATION_ARMS) * len(MODELS)
EXPECTED_TAVILY_REQUESTS = EXPECTED_CASE_COUNT
MINIMUM_COMPLETIONS_PER_MODEL_ARM = 23
MINIMUM_PROMPT_ANSWER_COVERAGE = 20
MINIMUM_CITATION_PRESENCE = 0.95
MINIMUM_CITATION_ID_VALIDITY = 1.0
MINIMUM_CITATION_SUPPORT = 0.75
MINIMUM_CITATION_PRESENCE_LIFT = 0.20


class CountingRecordingProvider(RecordingProvider):
    """Record provider invocations even when the delegated request fails."""

    def __init__(self, provider: SearchProvider, recorder: RawResultRecorder) -> None:
        super().__init__(provider, recorder)
        self.query_calls = 0

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        self.query_calls += 1
        return await super().search(query, request)


def prompt_packet_sha256(blocks: tuple[EvidenceBlock, ...]) -> str:
    return canonical_json_sha256(
        [
            {
                "citation_id": block.citation_id,
                "title": block.title,
                "url": block.url,
                "text": block.text,
                "providers": block.providers,
            }
            for block in blocks
        ]
    )


def build_prompt(
    row: BenchmarkRow,
    bundle: ArmBundle,
    *,
    evidence_budget_chars: int,
) -> tuple[str, str, tuple[EvidenceBlock, ...]]:
    included = _legacy_projection(bundle.blocks, evidence_budget_chars)
    rendered = _render_prompt_blocks(included)
    if bundle.arm == CANDIDATE_ARM:
        allowed_ids = ", ".join(f"[{block.citation_id}]" for block in included)
        user_prompt = (
            f"Question:\n{row.question}\n\n"
            f"Allowed citation identifiers:\n{allowed_ids or 'None'}\n\n"
            f"Evidence blocks:\n{rendered}\n\n"
            "Output contract: answer the question directly; cite every factual statement "
            "immediately; use only the allowed identifiers; do not add a bibliography."
        )
        return CANDIDATE_SYSTEM_PROMPT, user_prompt, included
    if bundle.arm != BASELINE_ARM:
        raise ValueError(f"unknown Phase 11.7 generation arm: {bundle.arm}")
    user_prompt = (
        f"Question:\n{row.question}\n\n"
        f"Evidence blocks:\n{rendered}\n\n"
        "Return only the concise answer. Keep supporting [S#] citations inline "
        "when evidence blocks are present."
    )
    return LEGACY_SYSTEM_PROMPT, user_prompt, included


def duplicate_tavily_bundle(base: ArmBundle) -> dict[str, ArmBundle]:
    return {arm: replace(base, arm=arm) for arm in GENERATION_ARMS}


async def retrieve_all(
    rows: list[BenchmarkRow],
    *,
    tavily_api_key: str,
    cache_root: Path,
    max_results: int,
    max_per_domain: int,
    request_timeout_seconds: float,
    wall_time_seconds: float,
    pause_seconds: float,
    progress: bool,
) -> tuple[
    dict[tuple[str, str], ArmBundle],
    list[dict[str, Any]],
    dict[str, int],
    dict[str, Any],
]:
    settings = Settings(
        deployment_profile=DeploymentProfile.QUALITY,
        enabled_providers=["tavily"],
        tavily_api_key=tavily_api_key,
        quality_primary_provider="tavily",
        quality_primary_provider_share=1.0,
        cache_path=cache_root / "phase11-7.sqlite3",
        request_timeout_seconds=request_timeout_seconds,
        respect_robots_txt=False,
    )
    recorder = RawResultRecorder()
    engine = EvidenceMesh(settings)
    counting_providers = [
        CountingRecordingProvider(provider, recorder) for provider in engine.providers
    ]
    engine.providers = counting_providers
    bundles: dict[tuple[str, str], ArmBundle] = {}
    diagnostics: list[dict[str, Any]] = []
    traffic = {
        "case_retrieval_operations": 0,
        "provider_query_calls": 0,
        "tavily_requests": 0,
    }
    pacer = RequestPacer(pause_seconds)
    try:
        for index, row in enumerate(rows, start=1):
            await pacer.wait()
            recorder.reset()
            calls_before = sum(provider.query_calls for provider in counting_providers)
            started = time.perf_counter()
            response = None
            error_kind = None
            try:
                async with asyncio.timeout(wall_time_seconds):
                    response = await engine.search(
                        SearchRequest(
                            query=row.question,
                            limit=max_results,
                            profile=SearchProfile.WEB,
                            fetch_content=False,
                            max_per_domain=max_per_domain,
                            use_cache=False,
                        )
                    )
            except Exception as exc:
                error_kind = _safe_error(exc, "retrieval")
            elapsed_ms = round((time.perf_counter() - started) * 1_000, 3)
            raw_results = recorder.all_results()
            query_count = (
                sum(provider.query_calls for provider in counting_providers) - calls_before
            )
            query_counts = {"tavily": query_count} if query_count else {}
            traffic["case_retrieval_operations"] += 1
            traffic["provider_query_calls"] += sum(query_counts.values())
            traffic["tavily_requests"] += query_counts.get("tavily", 0)

            base = replay_arm(
                row.id,
                row.question,
                raw_results,
                arm="tavily_direct",
                limit=max_results,
                max_per_domain=max_per_domain,
                retrieval_latency_ms=elapsed_ms,
                error_kind=error_kind,
            )
            for arm, bundle in duplicate_tavily_bundle(base).items():
                bundles[(row.id, arm)] = bundle

            diagnostics.append(
                {
                    "case_id": row.id,
                    "status": "completed" if response is not None else "failed",
                    "raw_result_count": len(raw_results),
                    "selected_result_count": len(base.blocks),
                    "latency_ms": elapsed_ms,
                    "provider_query_counts": dict(sorted(query_counts.items())),
                    "provider_failure_kind_counts": (
                        response.metadata.provider_failure_kind_counts
                        if response is not None
                        else {}
                    ),
                    "error_kind": error_kind,
                }
            )
            if progress:
                print(
                    f"[retrieval {index}/{len(rows)}] {row.id}: "
                    f"{len(raw_results)} raw Tavily result(s)",
                    file=sys.stderr,
                    flush=True,
                )
        return bundles, diagnostics, traffic, engine.health()
    finally:
        await engine.aclose()


def public_retrieval_outcome(
    row: BenchmarkRow,
    bundle: ArmBundle,
    *,
    evidence_budget_chars: int,
) -> dict[str, Any]:
    _system, _user, included = build_prompt(
        row,
        bundle,
        evidence_budget_chars=evidence_budget_chars,
    )
    return {
        "case_id": row.id,
        "arm": bundle.arm,
        "status": bundle.status,
        "available": bundle.available,
        "raw_result_count": bundle.raw_result_count,
        "selected_result_count": bundle.selected_result_count,
        "prompt_result_count": len(included),
        "unique_domains": bundle.unique_domains,
        "selected_tavily_count": bundle.selected_tavily_count,
        "prompt_tavily_count": sum("tavily" in block.providers for block in included),
        "answer_key_in_selected_evidence": answer_covered(
            row.answers,
            (block.text for block in bundle.blocks),
        ),
        "answer_key_in_prompt_evidence": answer_covered(
            row.answers,
            (block.text for block in included),
        ),
        "selected_packet_sha256": prompt_packet_sha256(bundle.blocks),
        "prompt_packet_sha256": prompt_packet_sha256(included),
        "retrieval_latency_ms": bundle.retrieval_latency_ms,
        "error_kind": bundle.error_kind,
    }


def aggregate_retrieval(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for arm in GENERATION_ARMS:
        rows = [outcome for outcome in outcomes if outcome["arm"] == arm]
        metrics[arm] = {
            "case_count": len(rows),
            "availability": ratio(
                sum(bool(outcome["available"]) for outcome in rows),
                len(rows),
            ),
            "answer_key_in_selected_evidence": ratio(
                sum(bool(outcome["answer_key_in_selected_evidence"]) for outcome in rows),
                len(rows),
            ),
            "answer_key_in_prompt_evidence": ratio(
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
            "latency_ms": {
                "p50": percentile(
                    [float(outcome["retrieval_latency_ms"]) for outcome in rows],
                    0.50,
                ),
                "p95": percentile(
                    [float(outcome["retrieval_latency_ms"]) for outcome in rows],
                    0.95,
                ),
            },
        }
    return metrics


def packet_identity(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for outcome in outcomes:
        by_case.setdefault(str(outcome["case_id"]), {})[str(outcome["arm"])] = outcome
    matching_cases = 0
    for arms in by_case.values():
        baseline = arms[BASELINE_ARM]
        candidate = arms[CANDIDATE_ARM]
        if (
            baseline["selected_packet_sha256"] == candidate["selected_packet_sha256"]
            and baseline["prompt_packet_sha256"] == candidate["prompt_packet_sha256"]
            and baseline["prompt_result_count"] == candidate["prompt_result_count"]
        ):
            matching_cases += 1
    return {
        "matching_cases": matching_cases,
        "denominator": len(by_case),
        "passed": matching_cases == EXPECTED_CASE_COUNT == len(by_case),
    }


async def generate_outcome(
    row: BenchmarkRow,
    bundle: ArmBundle,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    evidence_budget_chars: int,
    max_output_tokens: int,
    wall_time_seconds: float,
) -> dict[str, Any]:
    system_prompt, user_prompt, included = build_prompt(
        row,
        bundle,
        evidence_budget_chars=evidence_budget_chars,
    )
    evidence_by_id = {block.citation_id: block.text for block in included}
    started = time.perf_counter()
    try:
        async with asyncio.timeout(wall_time_seconds):
            completion = await request_gemini_completion(
                client,
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
            )
    except TimeoutError:
        error_kind = "generation_wall_timeout"
    except ModelRequestError as exc:
        error_kind = exc.kind
    except Exception as exc:
        error_kind = _safe_error(exc, "generation")
    else:
        citation_audit = audit_citations(
            completion.answer,
            evidence_by_id,
            citations_required=True,
        )
        support_proxy = any(
            answer_covered(row.answers, (evidence_by_id[citation_id],))
            for citation_id in citation_audit.citation_ids
        )
        return {
            "case_id": row.id,
            "arm": bundle.arm,
            "model": model,
            "status": "completed",
            "answer_sha256": sha256_bytes(completion.answer.encode("utf-8")),
            "answer_chars": len(completion.answer),
            "answer_key_covered": answer_covered(row.answers, (completion.answer,)),
            "citation_count": len(citation_audit.citation_ids),
            "invalid_citation_count": len(citation_audit.invalid_ids),
            "malformed_citation_count": len(citation_audit.malformed_tokens),
            "citation_ids_valid": citation_audit.identifier_integrity_valid,
            "citation_contract_passed": citation_audit.valid,
            "citation_support_proxy": support_proxy,
            "prompt_evidence_count": len(included),
            "prompt_packet_sha256": prompt_packet_sha256(included),
            "prompt_sha256": canonical_json_sha256(
                {
                    "system_instruction": system_prompt,
                    "user_prompt": user_prompt,
                }
            ),
            "system_prompt_sha256": sha256_bytes(system_prompt.encode("utf-8")),
            "response_model": completion.response_model,
            "finish_reason": completion.finish_reason,
            "usage": completion.usage,
            "generation_latency_ms": round((time.perf_counter() - started) * 1_000, 3),
            "error_kind": None,
        }
    return {
        "case_id": row.id,
        "arm": bundle.arm,
        "model": model,
        "status": "failed",
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
        "prompt_packet_sha256": prompt_packet_sha256(included),
        "prompt_sha256": canonical_json_sha256(
            {
                "system_instruction": system_prompt,
                "user_prompt": user_prompt,
            }
        ),
        "system_prompt_sha256": sha256_bytes(system_prompt.encode("utf-8")),
        "response_model": None,
        "finish_reason": None,
        "usage": {},
        "generation_latency_ms": round((time.perf_counter() - started) * 1_000, 3),
        "error_kind": error_kind,
    }


async def generate_all(
    rows: list[BenchmarkRow],
    bundles: dict[tuple[str, str], ArmBundle],
    *,
    api_key: str,
    models: tuple[str, ...],
    evidence_budget_chars: int,
    max_output_tokens: int,
    wall_time_seconds: float,
    pause_seconds: float,
    progress: bool,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    pacer = RequestPacer(pause_seconds)
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
            for arm_index, arm in enumerate(_rotated(GENERATION_ARMS, case_index)):
                for model in _rotated(models, case_index + arm_index):
                    await pacer.wait()
                    outcome = await generate_outcome(
                        row,
                        bundles[(row.id, arm)],
                        client=client,
                        api_key=api_key,
                        model=model,
                        evidence_budget_chars=evidence_budget_chars,
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
    completed = [outcome for outcome in outcomes if outcome["status"] == "completed"]
    with_citations = [outcome for outcome in completed if int(outcome["citation_count"]) > 0]
    usage: dict[str, int] = {}
    for outcome in completed:
        for key, value in outcome["usage"].items():
            usage[key] = usage.get(key, 0) + int(value)
    return {
        "case_count": len(outcomes),
        "completed": ratio(len(completed), len(outcomes)),
        "answer_key_covered": ratio(
            sum(bool(outcome["answer_key_covered"]) for outcome in completed),
            len(outcomes),
        ),
        "citation_presence": ratio(len(with_citations), len(completed)),
        "citation_ids_valid": ratio(
            sum(bool(outcome["citation_ids_valid"]) for outcome in with_citations),
            len(with_citations),
        ),
        "citation_contract_passed": ratio(
            sum(bool(outcome["citation_contract_passed"]) for outcome in completed),
            len(completed),
        ),
        "citation_support_proxy": ratio(
            sum(bool(outcome["citation_support_proxy"]) for outcome in completed),
            len(completed),
        ),
        "mean_prompt_evidence_count": (
            round(
                statistics.fmean(int(outcome["prompt_evidence_count"]) for outcome in completed),
                3,
            )
            if completed
            else 0.0
        ),
        "latency_ms": {
            "p50": percentile(
                [float(outcome["generation_latency_ms"]) for outcome in outcomes],
                0.50,
            ),
            "p95": percentile(
                [float(outcome["generation_latency_ms"]) for outcome in outcomes],
                0.95,
            ),
        },
        "usage_totals": dict(sorted(usage.items())),
        "error_kinds": dict(
            sorted(
                Counter(
                    str(outcome["error_kind"])
                    for outcome in outcomes
                    if outcome["error_kind"] is not None
                ).items()
            )
        ),
    }


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


def build_decision(
    retrieval_metrics: dict[str, Any],
    generation_metrics: dict[str, Any],
    paired: dict[str, Any],
    identity: dict[str, Any],
    *,
    retrieval_operations: int,
    generation_requests: int,
    tavily_requests: int,
) -> dict[str, Any]:
    baseline = generation_metrics["aggregate"][BASELINE_ARM]
    candidate = generation_metrics["aggregate"][CANDIDATE_ARM]
    completion_by_model_arm = {
        f"{model}:{arm}": int(generation_metrics["by_model"][model][arm]["completed"]["numerator"])
        for model in MODELS
        for arm in GENERATION_ARMS
    }
    by_model_non_regression = {
        model: {
            "baseline_hits": generation_metrics["by_model"][model][BASELINE_ARM][
                "answer_key_covered"
            ]["numerator"],
            "candidate_hits": generation_metrics["by_model"][model][CANDIDATE_ARM][
                "answer_key_covered"
            ]["numerator"],
            "paired_net_gain": paired["by_model"][model]["net_gain"],
        }
        for model in MODELS
    }
    baseline_presence = float(baseline["citation_presence"]["rate"] or 0.0)
    candidate_presence = float(candidate["citation_presence"]["rate"] or 0.0)
    presence_lift = round(candidate_presence - baseline_presence, 6)
    retrieval = retrieval_metrics[CANDIDATE_ARM]
    gates = {
        "protocol_integrity": {
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
            "repair_requests": 0,
        },
        "identical_tavily_prompt_packets": identity,
        "tavily_packet_available_and_answer_bearing": {
            "passed": (
                int(retrieval["availability"]["numerator"]) == EXPECTED_CASE_COUNT
                and int(retrieval["answer_key_in_prompt_evidence"]["numerator"])
                >= MINIMUM_PROMPT_ANSWER_COVERAGE
            ),
            "availability": retrieval["availability"],
            "answer_key_in_prompt_evidence": retrieval["answer_key_in_prompt_evidence"],
            "minimum_answer_coverage": MINIMUM_PROMPT_ANSWER_COVERAGE,
        },
        "completion_at_least_23_of_24_per_model_arm": {
            "passed": all(
                value >= MINIMUM_COMPLETIONS_PER_MODEL_ARM
                for value in completion_by_model_arm.values()
            ),
            "observed": completion_by_model_arm,
            "required": MINIMUM_COMPLETIONS_PER_MODEL_ARM,
            "denominator": EXPECTED_CASE_COUNT,
            "blocking_models": list(MODELS),
        },
        "strict_answer_no_overall_regression": {
            "passed": (
                int(candidate["answer_key_covered"]["numerator"])
                >= int(baseline["answer_key_covered"]["numerator"])
                and int(paired["overall"]["net_gain"]) >= 0
            ),
            "baseline_hits": baseline["answer_key_covered"]["numerator"],
            "candidate_hits": candidate["answer_key_covered"]["numerator"],
            "paired": paired["overall"],
        },
        "strict_answer_no_regression_for_any_model": {
            "passed": all(
                int(values["candidate_hits"]) >= int(values["baseline_hits"])
                and int(values["paired_net_gain"]) >= 0
                for values in by_model_non_regression.values()
            ),
            "observed": by_model_non_regression,
        },
        "strict_citation_presence_at_least_95_percent": {
            "passed": candidate_presence >= MINIMUM_CITATION_PRESENCE,
            "observed": candidate["citation_presence"],
            "required_rate": MINIMUM_CITATION_PRESENCE,
        },
        "strict_citation_presence_lift_at_least_20_points": {
            "passed": presence_lift >= MINIMUM_CITATION_PRESENCE_LIFT,
            "baseline_rate": baseline_presence,
            "candidate_rate": candidate_presence,
            "observed_lift": presence_lift,
            "required_lift": MINIMUM_CITATION_PRESENCE_LIFT,
        },
        "strict_citation_ids_100_percent_valid": {
            "passed": candidate["citation_ids_valid"]["rate"] == MINIMUM_CITATION_ID_VALIDITY,
            "observed": candidate["citation_ids_valid"],
            "required_rate": MINIMUM_CITATION_ID_VALIDITY,
        },
        "strict_citation_support_at_least_75_percent": {
            "passed": (
                candidate["citation_support_proxy"]["rate"] is not None
                and float(candidate["citation_support_proxy"]["rate"]) >= MINIMUM_CITATION_SUPPORT
            ),
            "observed": candidate["citation_support_proxy"],
            "required_rate": MINIMUM_CITATION_SUPPORT,
        },
    }
    candidate_passed = all(bool(gate["passed"]) for gate in gates.values())
    return {
        "gates": gates,
        "phase11_7_candidate_passed": candidate_passed,
        "quality_profile_promotion_allowed": candidate_passed,
        "quality_profile_promoted": False,
        "phase12_untouched_evaluation_allowed": candidate_passed,
        "phase12_executed": False,
        "gemma_4_26b_blocking": False,
        "gemma_4_26b_tested": False,
        "blocking_models": list(MODELS),
        "gemini_3_5_flash_lite_tested": True,
        "community_profile_unchanged": True,
        "external_competitor_benchmark_allowed": False,
        "public_alpha_allowed": False,
        "superiority_claim_allowed": False,
        "merge_allowed": False,
        "release_ready": False,
        "release_decision": "no-go",
        "reason": (
            "Phase 11.7 is a fresh pre-registered confirmation calibration. A pass "
            "permits a separately committed Tavily-only quality profile and can "
            "unblock, but never execute, the sealed Phase 12 reserve."
        ),
    }


def validate_arguments(arguments: argparse.Namespace) -> None:
    if tuple(arguments.models) != MODELS:
        raise ValueError(f"Phase 11.7 requires the exact locked model order: {MODELS}")
    locked_values = {
        "max_results": (arguments.max_results, 10),
        "max_per_domain": (arguments.max_per_domain, 3),
        "evidence_budget_chars": (arguments.evidence_budget_chars, 12_000),
        "max_output_tokens": (arguments.max_output_tokens, 2_048),
        "retrieval_wall_time_seconds": (arguments.retrieval_wall_time_seconds, 30.0),
        "generation_wall_time_seconds": (arguments.generation_wall_time_seconds, 60.0),
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
        raise ValueError("Phase 11.7 locked arguments changed: " + ", ".join(changed))
    if arguments.gemini_api_key_env != "GEMINI_API_KEY":
        raise ValueError("Phase 11.7 requires GEMINI_API_KEY as the runtime environment name")
    if arguments.tavily_api_key_env != "TAVILY_API_KEY":
        raise ValueError("Phase 11.7 requires TAVILY_API_KEY as the runtime environment name")


async def run(arguments: argparse.Namespace) -> dict[str, Any]:
    validate_arguments(arguments)
    protocol_bytes = await asyncio.to_thread(arguments.protocol.read_bytes)
    if sha256_bytes(protocol_bytes) != LOCKED_PROTOCOL_SHA256:
        raise ValueError("Phase 11.7 protocol checksum does not match the frozen lock")
    rows, manifest, dataset_metadata, reserve_metadata = load_phase11_7_rows(
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
    bundles, retrieval_diagnostics, retrieval_traffic, health = await retrieve_all(
        rows,
        tavily_api_key=tavily_api_key,
        cache_root=cache_root,
        max_results=arguments.max_results,
        max_per_domain=arguments.max_per_domain,
        request_timeout_seconds=arguments.request_timeout_seconds,
        wall_time_seconds=arguments.retrieval_wall_time_seconds,
        pause_seconds=arguments.retrieval_pause_seconds,
        progress=arguments.progress,
    )
    retrieval_outcomes = [
        public_retrieval_outcome(
            row,
            bundles[(row.id, arm)],
            evidence_budget_chars=arguments.evidence_budget_chars,
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
        max_output_tokens=arguments.max_output_tokens,
        wall_time_seconds=arguments.generation_wall_time_seconds,
        pause_seconds=arguments.model_pause_seconds,
        progress=arguments.progress,
    )
    retrieval_metrics = aggregate_retrieval(retrieval_outcomes)
    generation_metrics = aggregate_generation(generation_outcomes)
    paired = paired_answer_metrics(
        generation_outcomes,
        candidate_arm=CANDIDATE_ARM,
        baseline_arm=BASELINE_ARM,
    )
    decision = build_decision(
        retrieval_metrics,
        generation_metrics,
        paired,
        identity,
        retrieval_operations=retrieval_traffic["case_retrieval_operations"],
        generation_requests=len(generation_outcomes),
        tavily_requests=retrieval_traffic["tavily_requests"],
    )
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": "fresh Tavily-only citation-contract confirmation calibration",
        "suite": {
            "manifest_sha256": LOCKED_MANIFEST_SHA256,
            "sample_count": len(rows),
            "case_ids": [row.id for row in rows],
            "topic_distribution": manifest["topic_distribution"],
            "answer_type_distribution": manifest["answer_type_distribution"],
            "purpose": (
                "fresh pre-registered confirmation calibration after excluding every "
                "previously observed SimpleQA case"
            ),
            "phase12_cases_used": False,
        },
        "dataset": dataset_metadata,
        "phase12_reserve": reserve_metadata,
        "protocol": {
            "path": str(arguments.protocol),
            "sha256": LOCKED_PROTOCOL_SHA256,
            "prompt_version": PROMPT_VERSION,
            "models": list(MODELS),
            "generation_arms": list(GENERATION_ARMS),
            "baseline_arm": BASELINE_ARM,
            "candidate_arm": CANDIDATE_ARM,
            "provider_bundle": ["tavily"],
            "shared_tavily_packet_per_case": True,
            "provider_request_repeated_per_arm": False,
            "identical_selected_and_prompt_packets_required": True,
            "quality_profile_before_run": "community providers plus Tavily 8/2 reservation",
            "quality_profile_candidate": "Tavily only with strict packet-local citations",
            "community_profile_unchanged": True,
            "gemma_4_26b_blocking": False,
            "gemma_4_26b_tested": False,
            "gemini_3_5_flash_lite_tested": True,
            "users_choose_provider_model_and_credentials": True,
            "max_results": arguments.max_results,
            "max_per_domain": arguments.max_per_domain,
            "evidence_prompt_budget_chars": arguments.evidence_budget_chars,
            "projection": "identical Phase 10 sequential projection for both arms",
            "candidate_citation_contract": (
                "every factual statement cites an allowed exact ID immediately; "
                "deterministic identifier validation; no repair pass"
            ),
            "legacy_system_prompt_sha256": sha256_bytes(LEGACY_SYSTEM_PROMPT.encode("utf-8")),
            "candidate_system_prompt_sha256": sha256_bytes(CANDIDATE_SYSTEM_PROMPT.encode("utf-8")),
            "cache": False,
            "retry_policy": "none; no selective retry, fallback or repair",
            "expected_retrieval_operations": EXPECTED_RETRIEVAL_OPERATIONS,
            "expected_tavily_requests": EXPECTED_TAVILY_REQUESTS,
            "expected_generation_requests": EXPECTED_GENERATION_REQUESTS,
            "generation_wall_time_seconds": arguments.generation_wall_time_seconds,
            "whole_job_timeout_minutes": 120,
            "scoring": {
                "answer_key_covered": (
                    "normalized reference-answer substring in generated answer; proxy only"
                ),
                "answer_key_in_prompt_evidence": (
                    "normalized reference-answer substring in projected evidence; proxy only"
                ),
                "citation_support_proxy": (
                    "at least one cited projected block contains the normalized reference answer"
                ),
                "citation_identifier_integrity": (
                    "exact [S#] syntax and membership in the projected evidence packet"
                ),
                "official_simpleqa_evaluation": "not run",
            },
        },
        "environment": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "commit_sha": commit_sha(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "network_region": arguments.network_region,
            "dependency_versions": {
                package: package_version(package) for package in ("fastmcp", "httpx", "pydantic")
            },
        },
        "traffic": {
            **retrieval_traffic,
            "expected_retrieval_operations": EXPECTED_RETRIEVAL_OPERATIONS,
            "generation_requests": len(generation_outcomes),
            "expected_generation_requests": EXPECTED_GENERATION_REQUESTS,
            "expected_tavily_requests": EXPECTED_TAVILY_REQUESTS,
            "retries": 0,
            "repair_requests": 0,
        },
        "retrieval_health_after": health,
        "retrieval_diagnostics": retrieval_diagnostics,
        "retrieval_metrics": retrieval_metrics,
        "packet_identity": identity,
        "generation_metrics": generation_metrics,
        "paired_answer_key_coverage": paired,
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
            "answer_hashes_in_report": True,
            "api_keys_in_report": False,
            "phase12_reserved_case_ids_in_report": False,
        },
        "warnings": [
            (
                "The strict substring metrics are transparent proxies, not official "
                "SimpleQA accuracy or semantic citation evaluation."
            ),
            (
                "The suite was fresh when frozen but becomes observed by this calibration. "
                "Only the sealed Phase 12 reserve can support a later untouched evaluation."
            ),
            (
                "Live Tavily results and hosted model outputs are dated and "
                "non-deterministic; no selective retry is permitted."
            ),
            (
                "Tavily and Gemini are optional API-backed benchmark components. "
                "The zero-key community profile remains available and unchanged."
            ),
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    root = REPOSITORY_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
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
        "--protocol",
        type=Path,
        default=root / "docs/benchmark-protocol-v15.md",
    )
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--tavily-api-key-env", default="TAVILY_API_KEY")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(tempfile.gettempdir()) / "evidencemesh-phase11-7",
    )
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--max-per-domain", type=int, default=3)
    parser.add_argument("--evidence-budget-chars", type=int, default=12_000)
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    report = asyncio.run(run(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
