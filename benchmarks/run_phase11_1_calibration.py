#!/usr/bin/env python3
"""Run the locked Phase 11.1 feasibility and independent-index calibration."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import time
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from benchmarks.run_phase11_calibration import (
    EXPECTED_CASE_COUNT,
    LOCKED_SEARXNG_CONFIG_SHA256,
    CalibrationCase,
    RawResultRecorder,
    RecordingProvider,
    load_suite,
    package_version,
    percentile,
    ratio,
    sha256_bytes,
)
from evidencemesh.config import DeploymentProfile, Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import ProviderResult, SearchHit, SearchProfile, SearchRequest
from evidencemesh.ranking import rank_results_with_diagnostics
from evidencemesh.urls import domain_matches, hostname_from_url

BENCHMARK_NAME = "evidencemesh-phase11-1-feasibility-calibration-v1"
WIBY_ENDPOINT = "https://wiby.me/json/"
WIBY_ATTRIBUTION = "https://wiby.me/"
PHASE11_1_QUALITY_PROVIDERS: tuple[str, ...] = (
    "searxng",
    "ddgs",
    "wiby",
    "wikipedia",
    "crossref",
    "arxiv",
    "github",
    "tavily",
)
ARMS: tuple[str, ...] = (
    "tavily_direct",
    "wiby_direct",
    "community",
    "quality_legacy",
    "quality_safe_4_6",
    "quality_safe_6_4",
    "quality_safe_8_2",
)
ARM_SHARES: dict[str, float] = {
    "quality_safe_4_6": 0.4,
    "quality_safe_6_4": 0.6,
    "quality_safe_8_2": 0.8,
}


def _provider_counts(hits: Iterable[SearchHit]) -> dict[str, int]:
    return dict(sorted(Counter(provider for hit in hits for provider in hit.providers).items()))


def _prompt_projection(hits: list[SearchHit], budget_chars: int) -> list[SearchHit]:
    projected: list[SearchHit] = []
    remaining = budget_chars
    for hit in hits:
        if not hit.snippet or remaining <= 0:
            continue
        projected.append(hit)
        remaining -= min(len(hit.snippet), remaining)
    return projected


def _stage_losses(stage_counts: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    stages = ("raw", "fused", "eligible", "selected", "evidence", "prompt")
    losses: dict[str, dict[str, int]] = {}
    for left, right in pairwise(stages):
        left_counts = stage_counts.get(left, {})
        right_counts = stage_counts.get(right, {})
        providers = sorted(set(left_counts) | set(right_counts))
        losses[f"{left}_to_{right}"] = {
            provider: max(0, left_counts.get(provider, 0) - right_counts.get(provider, 0))
            for provider in providers
        }
    return losses


def _target_hit(case: CalibrationCase, hits: Iterable[SearchHit]) -> bool:
    return any(
        domain_matches(hostname_from_url(hit.canonical_url), case.target_domains) for hit in hits
    )


def _arm_results(raw_results: list[ProviderResult], arm: str) -> list[ProviderResult]:
    if arm == "tavily_direct":
        return [result for result in raw_results if result.provider == "tavily"]
    if arm == "wiby_direct":
        return [result for result in raw_results if result.provider == "wiby"]
    if arm == "community":
        return [result for result in raw_results if result.provider != "tavily"]
    return list(raw_results)


def replay_arm(
    case: CalibrationCase,
    raw_results: list[ProviderResult],
    *,
    arm: str,
    limit: int,
    max_per_domain: int,
    prompt_budget_chars: int,
) -> dict[str, Any]:
    selected_pool = _arm_results(raw_results, arm)
    share = ARM_SHARES.get(arm, 0.0)
    primary_provider = "tavily" if share else None
    hits, fused_count, diagnostics = rank_results_with_diagnostics(
        selected_pool,
        query=case.query,
        profile=SearchProfile.WEB,
        limit=limit,
        max_per_domain=max_per_domain,
        primary_provider=primary_provider,
        primary_provider_share=share,
    )
    evidence_hits = [hit for hit in hits if hit.snippet]
    prompt_hits = _prompt_projection(evidence_hits, prompt_budget_chars)
    stage_counts = {
        **diagnostics.provider_stage_counts,
        "evidence": _provider_counts(evidence_hits),
        "prompt": _provider_counts(prompt_hits),
    }
    return {
        "case_id": case.id,
        "arm": arm,
        "available": bool(prompt_hits),
        "target_domain_hit": _target_hit(case, prompt_hits),
        "fused_result_count": fused_count,
        "selected_result_count": len(hits),
        "evidence_result_count": len(evidence_hits),
        "prompt_result_count": len(prompt_hits),
        "raw_tavily_result_count": diagnostics.provider_stage_counts["raw"].get(
            "tavily",
            0,
        ),
        "eligible_tavily_result_count": diagnostics.provider_stage_counts["eligible"].get(
            "tavily",
            0,
        ),
        "selected_tavily_result_count": diagnostics.provider_stage_counts["selected"].get(
            "tavily",
            0,
        ),
        "raw_wiby_result_count": diagnostics.provider_stage_counts["raw"].get("wiby", 0),
        "selected_wiby_result_count": diagnostics.provider_stage_counts["selected"].get(
            "wiby",
            0,
        ),
        "ranking_reservation_policy": diagnostics.reservation_policy,
        "ranking_reservation_requested": diagnostics.reservation_requested,
        "ranking_reservation_eligible": diagnostics.reservation_eligible,
        "ranking_reservation_feasible": diagnostics.reservation_feasible,
        "ranking_reservation_target": diagnostics.reservation_target,
        "ranking_reservation_fulfilled": diagnostics.reservation_fulfilled,
        "ranking_reservation_shortfall_reason": diagnostics.reservation_shortfall_reason,
        "provider_stage_counts": stage_counts,
        "provider_stage_loss_counts": _stage_losses(stage_counts),
    }


def _paired(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, int]:
    left_by_case = {outcome["case_id"]: outcome for outcome in left}
    right_by_case = {outcome["case_id"]: outcome for outcome in right}
    wins = losses = ties = 0
    for case_id in sorted(left_by_case):
        left_hit = bool(left_by_case[case_id]["target_domain_hit"])
        right_hit = bool(right_by_case[case_id]["target_domain_hit"])
        wins += int(left_hit and not right_hit)
        losses += int(not left_hit and right_hit)
        ties += int(left_hit == right_hit)
    return {
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "net": wins - losses,
    }


def _arm_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for arm in ARMS:
        arm_outcomes = [outcome for outcome in outcomes if outcome["arm"] == arm]
        metrics[arm] = {
            "case_count": len(arm_outcomes),
            "availability": ratio(
                sum(bool(outcome["available"]) for outcome in arm_outcomes),
                len(arm_outcomes),
            ),
            "target_domain_hit_at_10": ratio(
                sum(bool(outcome["target_domain_hit"]) for outcome in arm_outcomes),
                len(arm_outcomes),
            ),
            "cases_with_selected_wiby": ratio(
                sum(outcome["selected_wiby_result_count"] > 0 for outcome in arm_outcomes),
                len(arm_outcomes),
            ),
            "mean_prompt_result_count": round(
                sum(outcome["prompt_result_count"] for outcome in arm_outcomes) / len(arm_outcomes),
                3,
            ),
            "mean_selected_tavily_result_count": round(
                sum(outcome["selected_tavily_result_count"] for outcome in arm_outcomes)
                / len(arm_outcomes),
                3,
            ),
            "mean_selected_wiby_result_count": round(
                sum(outcome["selected_wiby_result_count"] for outcome in arm_outcomes)
                / len(arm_outcomes),
                3,
            ),
        }
    return metrics


def build_decision(
    outcomes: list[dict[str, Any]],
    metrics: dict[str, Any],
    *,
    tavily_requests: int,
    wiby_requests: int,
    wiby_raw_cases: int,
    wiby_attributed_cases: int,
) -> dict[str, Any]:
    by_arm = {arm: [outcome for outcome in outcomes if outcome["arm"] == arm] for arm in ARMS}
    safe = by_arm["quality_safe_8_2"]
    safe_vs_direct = _paired(safe, by_arm["tavily_direct"])
    safe_vs_legacy = _paired(safe, by_arm["quality_legacy"])
    community_available = metrics["community"]["availability"]["numerator"]
    safe_target_hits = metrics["quality_safe_8_2"]["target_domain_hit_at_10"]["numerator"]
    legacy_target_hits = metrics["quality_legacy"]["target_domain_hit_at_10"]["numerator"]
    reservation_requested_total = sum(outcome["ranking_reservation_requested"] for outcome in safe)
    reservation_target_total = sum(outcome["ranking_reservation_target"] for outcome in safe)
    reservation_fulfilled_cases = sum(
        outcome["ranking_reservation_fulfilled"] == outcome["ranking_reservation_target"]
        for outcome in safe
    )
    reservation_target_at_least_six_cases = sum(
        outcome["ranking_reservation_target"] >= 6 for outcome in safe
    )
    community_wiby_selected_cases = metrics["community"]["cases_with_selected_wiby"]["numerator"]
    gates = {
        "community_availability_at_least_90_percent": {
            "passed": community_available >= 11,
            "observed": community_available,
            "required": 11,
            "denominator": EXPECTED_CASE_COUNT,
        },
        "safe_8_2_not_below_legacy_target_recall": {
            "passed": safe_target_hits >= legacy_target_hits,
            "safe_observed": safe_target_hits,
            "legacy_observed": legacy_target_hits,
        },
        "safe_8_2_at_most_one_loss_vs_tavily_direct": {
            "passed": safe_vs_direct["losses"] <= 1,
            "observed_losses": safe_vs_direct["losses"],
            "maximum": 1,
        },
        "domain_aware_reservation_is_strong_and_fulfilled": {
            "passed": (
                reservation_fulfilled_cases == EXPECTED_CASE_COUNT
                and reservation_target_at_least_six_cases == EXPECTED_CASE_COUNT
                and reservation_target_total >= 90
            ),
            "requested_total": reservation_requested_total,
            "target_total": reservation_target_total,
            "minimum_target_total": 90,
            "fulfilled_cases": reservation_fulfilled_cases,
            "target_at_least_six_cases": reservation_target_at_least_six_cases,
            "required_cases": EXPECTED_CASE_COUNT,
        },
        "wiby_independent_index_available": {
            "passed": wiby_raw_cases >= 6,
            "observed": wiby_raw_cases,
            "required": 6,
            "denominator": EXPECTED_CASE_COUNT,
        },
        "wiby_survives_community_ranking": {
            "passed": community_wiby_selected_cases >= 3,
            "observed": community_wiby_selected_cases,
            "required": 3,
            "denominator": EXPECTED_CASE_COUNT,
        },
        "wiby_attribution_complete": {
            "passed": (wiby_raw_cases > 0 and wiby_attributed_cases == wiby_raw_cases),
            "raw_result_cases": wiby_raw_cases,
            "attributed_cases": wiby_attributed_cases,
        },
        "paid_and_public_traffic_within_budget": {
            "passed": (
                tavily_requests <= EXPECTED_CASE_COUNT and wiby_requests <= EXPECTED_CASE_COUNT
            ),
            "tavily_requests": tavily_requests,
            "maximum_tavily_requests": EXPECTED_CASE_COUNT,
            "wiby_requests": wiby_requests,
            "maximum_wiby_requests": EXPECTED_CASE_COUNT,
        },
    }
    candidate_passed = all(gate["passed"] for gate in gates.values())
    return {
        "gates": gates,
        "paired_target_recall": {
            "quality_safe_8_2_vs_tavily_direct": safe_vs_direct,
            "quality_safe_8_2_vs_quality_legacy": safe_vs_legacy,
        },
        "phase11_1_candidate_passed": candidate_passed,
        "phase12_untouched_evaluation_allowed": candidate_passed,
        "stage_b_external_agents_allowed": False,
        "release_ready": False,
        "release_decision": "no-go",
        "reason": (
            "Phase 11.1 is an authored retrieval calibration without answer-model, "
            "external-agent, or second-network evaluation; release remains blocked."
        ),
    }


async def run(arguments: argparse.Namespace) -> dict[str, Any]:
    suite_path = Path(arguments.suite)
    config_path = Path(arguments.searxng_config)
    cases, suite_bytes = load_suite(suite_path)
    config_bytes = await asyncio.to_thread(config_path.read_bytes)
    if sha256_bytes(config_bytes) != LOCKED_SEARXNG_CONFIG_SHA256:
        raise ValueError("Phase 11.1 SearXNG config checksum does not match the lock")
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY is required for the Phase 11.1 calibration")

    cache_root = Path(arguments.cache_root)
    await asyncio.to_thread(cache_root.mkdir, parents=True, exist_ok=True)
    settings = Settings(
        deployment_profile=DeploymentProfile.QUALITY,
        enabled_providers=list(PHASE11_1_QUALITY_PROVIDERS),
        searxng_url=arguments.searxng_url,
        wiby_url=arguments.wiby_url,
        tavily_api_key=api_key,
        quality_primary_provider_share=0.0,
        cache_path=cache_root / "phase11-1.sqlite3",
        request_timeout_seconds=arguments.request_timeout_seconds,
        respect_robots_txt=False,
    )
    recorder = RawResultRecorder()
    engine = EvidenceMesh(settings)
    engine.providers = [RecordingProvider(provider, recorder) for provider in engine.providers]
    outcomes: list[dict[str, Any]] = []
    retrieval_diagnostics: list[dict[str, Any]] = []
    provider_query_calls = 0
    tavily_requests = 0
    wiby_requests = 0
    wiby_raw_cases = 0
    wiby_attributed_cases = 0
    latencies: list[float] = []
    started_at = datetime.now(UTC)
    try:
        for index, case in enumerate(cases, start=1):
            if index > 1 and arguments.pause_seconds:
                await asyncio.sleep(arguments.pause_seconds)
            recorder.reset()
            started = time.perf_counter()
            async with asyncio.timeout(arguments.wall_time_seconds):
                response = await engine.search(
                    SearchRequest(
                        query=case.query,
                        limit=arguments.max_results,
                        profile=SearchProfile.WEB,
                        fetch_content=False,
                        max_per_domain=arguments.max_per_domain,
                        use_cache=False,
                    )
                )
            elapsed_ms = round((time.perf_counter() - started) * 1_000, 3)
            latencies.append(elapsed_ms)
            query_counts = response.metadata.provider_query_counts
            provider_query_calls += sum(query_counts.values())
            tavily_requests += query_counts.get("tavily", 0)
            wiby_requests += query_counts.get("wiby", 0)
            raw_results = recorder.all_results()
            has_wiby_results = any(result.provider == "wiby" for result in raw_results)
            wiby_raw_cases += int(has_wiby_results)
            wiby_attributed_cases += int(
                has_wiby_results
                and response.metadata.provider_attributions.get("wiby") == WIBY_ATTRIBUTION
            )
            for arm in ARMS:
                outcomes.append(
                    replay_arm(
                        case,
                        raw_results,
                        arm=arm,
                        limit=arguments.max_results,
                        max_per_domain=arguments.max_per_domain,
                        prompt_budget_chars=arguments.prompt_budget_chars,
                    )
                )
            retrieval_diagnostics.append(
                {
                    "case_id": case.id,
                    "latency_ms": elapsed_ms,
                    "provider_query_counts": query_counts,
                    "wiby_returned_results": has_wiby_results,
                    "wiby_attribution_present": (
                        response.metadata.provider_attributions.get("wiby") == WIBY_ATTRIBUTION
                    ),
                    "provider_failure_providers": sorted(
                        {
                            key.partition(":")[0]
                            for key in response.metadata.provider_failures
                            if key.partition(":")[0]
                        }
                    ),
                    "provider_upstream_engine_query_counts": (
                        response.metadata.provider_upstream_engine_query_counts
                    ),
                    "provider_unresponsive_engine_query_counts": (
                        response.metadata.provider_unresponsive_engine_query_counts
                    ),
                    "provider_unavailable_engine_query_counts": (
                        response.metadata.provider_unavailable_engine_query_counts
                    ),
                    "provider_failure_kind_counts": (
                        response.metadata.provider_failure_kind_counts
                    ),
                }
            )
            if arguments.progress:
                print(
                    f"[{index}/{len(cases)}] {case.id}: {len(raw_results)} raw result(s)",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        await engine.aclose()

    metrics = _arm_metrics(outcomes)
    decision = build_decision(
        outcomes,
        metrics,
        tavily_requests=tavily_requests,
        wiby_requests=wiby_requests,
        wiby_raw_cases=wiby_raw_cases,
        wiby_attributed_cases=wiby_attributed_cases,
    )
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "suite": {
            "path": str(suite_path),
            "sha256": sha256_bytes(suite_bytes),
            "case_count": len(cases),
            "case_ids": [case.id for case in cases],
            "topic_distribution": dict(sorted(Counter(case.topic for case in cases).items())),
            "purpose": (
                "authored Phase 11 diagnostic suite reused for a corrective "
                "calibration; not an untouched final evaluation"
            ),
            "reused_from_phase11": True,
        },
        "protocol": {
            "arms": list(ARMS),
            "reservation_shares": ARM_SHARES,
            "reservation_contract": (
                "target=min(requested, diverse-feasible); fulfillment is judged "
                "against target while requested remains visible"
            ),
            "shared_raw_pool_per_case": True,
            "provider_calls_replayed": False,
            "cache": False,
            "retry_policy": "none",
            "max_results": arguments.max_results,
            "max_per_domain": arguments.max_per_domain,
            "prompt_projection_budget_chars": arguments.prompt_budget_chars,
            "searxng_config_sha256": sha256_bytes(config_bytes),
            "community_providers": [
                provider for provider in PHASE11_1_QUALITY_PROVIDERS if provider != "tavily"
            ],
            "quality_providers": list(PHASE11_1_QUALITY_PROVIDERS),
            "independent_provider": {
                "name": "wiby",
                "endpoint": WIBY_ENDPOINT,
                "attribution": WIBY_ATTRIBUTION,
                "query_budget_per_case": 1,
            },
            "gemini_requests": 0,
            "maximum_tavily_requests": EXPECTED_CASE_COUNT,
            "maximum_wiby_requests": EXPECTED_CASE_COUNT,
        },
        "environment": {
            "commit_sha": os.getenv("EVIDENCEMESH_BENCHMARK_COMMIT", "unknown"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "network_region": arguments.network_region,
            "dependency_versions": {
                "ddgs": package_version("ddgs"),
                "httpx": package_version("httpx"),
                "pydantic": package_version("pydantic"),
            },
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
        },
        "traffic": {
            "case_retrieval_operations": len(cases),
            "provider_query_calls": provider_query_calls,
            "tavily_requests": tavily_requests,
            "maximum_tavily_requests": EXPECTED_CASE_COUNT,
            "wiby_requests": wiby_requests,
            "maximum_wiby_requests": EXPECTED_CASE_COUNT,
            "gemini_requests": 0,
            "retries": 0,
        },
        "latency_ms": {
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
        },
        "retrieval_diagnostics": retrieval_diagnostics,
        "outcomes": outcomes,
        "metrics": metrics,
        "decision": decision,
        "privacy": {
            "queries_in_report": False,
            "target_domains_in_report": False,
            "source_titles_or_urls_in_report": False,
            "source_snippets_in_report": False,
            "provider_attribution_urls_in_report": True,
            "api_keys_in_report": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        default="benchmarks/data/phase11_calibration_v1.json",
    )
    parser.add_argument(
        "--searxng-config",
        default="docker/searxng/phase11-community-settings.yml",
    )
    parser.add_argument("--searxng-url", default="http://127.0.0.1:8895")
    parser.add_argument("--wiby-url", default=WIBY_ENDPOINT)
    parser.add_argument("--cache-root", default=".phase11-1-cache")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--max-per-domain", type=int, default=3)
    parser.add_argument("--prompt-budget-chars", type=int, default=12_000)
    parser.add_argument("--request-timeout-seconds", type=float, default=25.0)
    parser.add_argument("--wall-time-seconds", type=float, default=75.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--network-region", default="not reported")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    if arguments.max_results != 10:
        parser.error("the locked Phase 11.1 protocol requires --max-results 10")
    if arguments.max_per_domain != 3:
        parser.error("the locked Phase 11.1 protocol requires --max-per-domain 3")
    if arguments.prompt_budget_chars != 12_000:
        parser.error("the locked Phase 11.1 protocol requires --prompt-budget-chars 12000")
    if arguments.wiby_url != WIBY_ENDPOINT:
        parser.error(f"the locked Phase 11.1 protocol requires --wiby-url {WIBY_ENDPOINT}")
    return arguments


def main() -> None:
    arguments = parse_args()
    report = asyncio.run(run(arguments))
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
