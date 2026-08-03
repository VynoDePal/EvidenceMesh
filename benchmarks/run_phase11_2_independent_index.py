#!/usr/bin/env python3
"""Run the locked Phase 11.2 independent-index calibration."""

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
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

try:
    from benchmarks.run_phase11_calibration import (
        LOCKED_SEARXNG_CONFIG_SHA256,
        RawResultRecorder,
        RecordingProvider,
        package_version,
        percentile,
        ratio,
        sha256_bytes,
    )
except ModuleNotFoundError:
    from run_phase11_calibration import (  # type: ignore[no-redef]
        LOCKED_SEARXNG_CONFIG_SHA256,
        RawResultRecorder,
        RecordingProvider,
        package_version,
        percentile,
        ratio,
        sha256_bytes,
    )

from evidencemesh.config import DeploymentProfile, Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import ProviderResult, SearchHit, SearchProfile, SearchRequest
from evidencemesh.providers.mwmbl import MWMBL_RESULTS_LICENSE_URL
from evidencemesh.ranking import rank_results_with_diagnostics
from evidencemesh.urls import domain_matches, hostname_from_url

BENCHMARK_NAME = "evidencemesh-phase11-2-independent-index-calibration-v1"
LOCKED_SUITE_SHA256 = "670454d6c6bdb93a21bc1ea81f28003e08cac9d24c1663aba53fea50d3ac2423"
EXPECTED_CASE_COUNT = 16
MAX_INPUT_BYTES = 1_000_000
MWMBL_ENDPOINT = "https://api.mwmbl.org/api/v2/search/"
WIBY_ENDPOINT = "https://wiby.me/json/"
LIVE_PROVIDERS: tuple[str, ...] = (
    "searxng",
    "ddgs",
    "wikipedia",
    "wiby",
    "mwmbl",
)
ARMS: tuple[str, ...] = (
    "legacy_community",
    "candidate_community",
    "mwmbl_direct",
    "wiby_direct",
    "independent_fused",
)
STRATA: tuple[str, ...] = ("broad_web", "long_tail")


@dataclass(frozen=True, slots=True)
class IndependentIndexCase:
    id: str
    query: str
    target_domains: tuple[str, ...]
    stratum: str
    topic: str


def load_suite(path: Path) -> tuple[list[IndependentIndexCase], bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Phase 11.2 suite exceeds one megabyte")
    if sha256_bytes(raw) != LOCKED_SUITE_SHA256:
        raise ValueError("Phase 11.2 suite checksum does not match the locked revision")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Phase 11.2 suite is not valid JSON") from exc
    if not isinstance(payload, list) or len(payload) != EXPECTED_CASE_COUNT:
        raise ValueError(f"Phase 11.2 suite must contain exactly {EXPECTED_CASE_COUNT} cases")

    expected_fields = {"id", "query", "target_domains", "stratum", "topic"}
    cases: list[IndependentIndexCase] = []
    seen_ids: set[str] = set()
    seen_queries: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise ValueError("Phase 11.2 case fields do not match the locked schema")
        case_id = item["id"]
        query = item["query"]
        targets = item["target_domains"]
        stratum = item["stratum"]
        topic = item["topic"]
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("Phase 11.2 case IDs must be unique non-empty strings")
        normalized_query = query.casefold().strip() if isinstance(query, str) else ""
        if not normalized_query or normalized_query in seen_queries:
            raise ValueError("Phase 11.2 queries must be unique non-empty strings")
        if stratum not in STRATA:
            raise ValueError(f"Phase 11.2 case {case_id} has an invalid stratum")
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError(f"Phase 11.2 case {case_id} has an invalid topic")
        if (
            not isinstance(targets, list)
            or not targets
            or not all(isinstance(target, str) and target for target in targets)
        ):
            raise ValueError(f"Phase 11.2 case {case_id} has invalid target domains")
        normalized_targets = tuple(target.strip().lower().rstrip(".") for target in targets)
        if any("://" in target or "/" in target or "@" in target for target in normalized_targets):
            raise ValueError(f"Phase 11.2 case {case_id} has a non-hostname target")
        seen_ids.add(case_id)
        seen_queries.add(normalized_query)
        cases.append(
            IndependentIndexCase(
                id=case_id,
                query=query.strip(),
                target_domains=normalized_targets,
                stratum=stratum,
                topic=topic.strip(),
            )
        )
    if Counter(case.stratum for case in cases) != Counter({"broad_web": 8, "long_tail": 8}):
        raise ValueError("Phase 11.2 suite must contain eight cases in each stratum")
    return cases, raw


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


def _target_hit(case: IndependentIndexCase, hits: Iterable[SearchHit]) -> bool:
    return any(
        domain_matches(hostname_from_url(hit.canonical_url), case.target_domains) for hit in hits
    )


def _arm_results(raw_results: list[ProviderResult], arm: str) -> list[ProviderResult]:
    if arm == "legacy_community":
        allowed = {"searxng", "ddgs", "wikipedia"}
    elif arm == "mwmbl_direct":
        allowed = {"mwmbl"}
    elif arm == "wiby_direct":
        allowed = {"wiby"}
    elif arm == "independent_fused":
        allowed = {"mwmbl", "wiby"}
    else:
        allowed = set(LIVE_PROVIDERS)
    return [result for result in raw_results if result.provider in allowed]


def replay_arm(
    case: IndependentIndexCase,
    raw_results: list[ProviderResult],
    *,
    arm: str,
    limit: int,
    max_per_domain: int,
    prompt_budget_chars: int,
) -> dict[str, Any]:
    selected_pool = _arm_results(raw_results, arm)
    hits, fused_count, diagnostics = rank_results_with_diagnostics(
        selected_pool,
        query=case.query,
        profile=SearchProfile.WEB,
        limit=limit,
        max_per_domain=max_per_domain,
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
        "stratum": case.stratum,
        "arm": arm,
        "available": bool(prompt_hits),
        "target_domain_hit": _target_hit(case, prompt_hits),
        "fused_result_count": fused_count,
        "selected_result_count": len(hits),
        "evidence_result_count": len(evidence_hits),
        "prompt_result_count": len(prompt_hits),
        "raw_mwmbl_result_count": diagnostics.provider_stage_counts["raw"].get("mwmbl", 0),
        "selected_mwmbl_result_count": diagnostics.provider_stage_counts["selected"].get(
            "mwmbl",
            0,
        ),
        "raw_wiby_result_count": diagnostics.provider_stage_counts["raw"].get("wiby", 0),
        "selected_wiby_result_count": diagnostics.provider_stage_counts["selected"].get(
            "wiby",
            0,
        ),
        "ranking_reservation_policy": diagnostics.reservation_policy,
        "ranking_reservation_requested": diagnostics.reservation_requested,
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
    return {"wins": wins, "losses": losses, "ties": ties, "net": wins - losses}


def _aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(rows)
    return {
        "case_count": denominator,
        "availability": ratio(
            sum(bool(outcome["available"]) for outcome in rows),
            denominator,
        ),
        "target_domain_hit_at_10": ratio(
            sum(bool(outcome["target_domain_hit"]) for outcome in rows),
            denominator,
        ),
        "cases_with_selected_mwmbl": ratio(
            sum(outcome["selected_mwmbl_result_count"] > 0 for outcome in rows),
            denominator,
        ),
        "cases_with_selected_wiby": ratio(
            sum(outcome["selected_wiby_result_count"] > 0 for outcome in rows),
            denominator,
        ),
        "mean_prompt_result_count": (
            round(
                sum(outcome["prompt_result_count"] for outcome in rows) / denominator,
                3,
            )
            if denominator
            else None
        ),
    }


def _arm_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for arm in ARMS:
        arm_outcomes = [outcome for outcome in outcomes if outcome["arm"] == arm]
        metrics[arm] = {
            **_aggregate_metrics(arm_outcomes),
            "strata": {
                stratum: _aggregate_metrics(
                    [outcome for outcome in arm_outcomes if outcome["stratum"] == stratum]
                )
                for stratum in STRATA
            },
        }
    return metrics


def build_decision(
    outcomes: list[dict[str, Any]],
    metrics: dict[str, Any],
    *,
    provider_query_calls: int,
    mwmbl_requests: int,
    wiby_requests: int,
    mwmbl_raw_cases: int,
    mwmbl_raw_broad_cases: int,
    mwmbl_raw_long_tail_cases: int,
    mwmbl_licensed_cases: int,
) -> dict[str, Any]:
    by_arm = {arm: [outcome for outcome in outcomes if outcome["arm"] == arm] for arm in ARMS}
    paired = _paired(by_arm["candidate_community"], by_arm["legacy_community"])
    candidate_available = metrics["candidate_community"]["availability"]["numerator"]
    legacy_available = metrics["legacy_community"]["availability"]["numerator"]
    candidate_hits = metrics["candidate_community"]["target_domain_hit_at_10"]["numerator"]
    legacy_hits = metrics["legacy_community"]["target_domain_hit_at_10"]["numerator"]
    selected_mwmbl_cases = metrics["candidate_community"]["cases_with_selected_mwmbl"]["numerator"]
    mwmbl_broad_hits = metrics["mwmbl_direct"]["strata"]["broad_web"]["target_domain_hit_at_10"][
        "numerator"
    ]
    mwmbl_long_tail_hits = metrics["mwmbl_direct"]["strata"]["long_tail"][
        "target_domain_hit_at_10"
    ]["numerator"]
    independent_available = metrics["independent_fused"]["availability"]["numerator"]

    gates = {
        "candidate_availability": {
            "passed": candidate_available >= 15 and candidate_available >= legacy_available,
            "candidate_observed": candidate_available,
            "legacy_observed": legacy_available,
            "required": 15,
            "denominator": EXPECTED_CASE_COUNT,
        },
        "candidate_not_below_legacy_target_recall": {
            "passed": candidate_hits >= legacy_hits,
            "candidate_observed": candidate_hits,
            "legacy_observed": legacy_hits,
        },
        "candidate_at_most_one_paired_loss": {
            "passed": paired["losses"] <= 1,
            "observed_losses": paired["losses"],
            "maximum": 1,
        },
        "mwmbl_independent_index_available": {
            "passed": (
                mwmbl_raw_cases >= 12
                and mwmbl_raw_broad_cases >= 7
                and mwmbl_raw_long_tail_cases >= 6
            ),
            "observed": mwmbl_raw_cases,
            "required": 12,
            "broad_observed": mwmbl_raw_broad_cases,
            "broad_required": 7,
            "long_tail_observed": mwmbl_raw_long_tail_cases,
            "long_tail_required": 6,
        },
        "mwmbl_survives_candidate_ranking": {
            "passed": selected_mwmbl_cases >= 8,
            "observed": selected_mwmbl_cases,
            "required": 8,
            "denominator": EXPECTED_CASE_COUNT,
        },
        "mwmbl_direct_target_coverage": {
            "passed": mwmbl_broad_hits >= 4 and mwmbl_long_tail_hits >= 4,
            "broad_observed": mwmbl_broad_hits,
            "broad_required": 4,
            "long_tail_observed": mwmbl_long_tail_hits,
            "long_tail_required": 4,
        },
        "independent_fused_availability": {
            "passed": independent_available >= 12,
            "observed": independent_available,
            "required": 12,
            "denominator": EXPECTED_CASE_COUNT,
        },
        "mwmbl_result_license_notice_complete": {
            "passed": (mwmbl_raw_cases > 0 and mwmbl_licensed_cases == mwmbl_raw_cases),
            "raw_result_cases": mwmbl_raw_cases,
            "licensed_cases": mwmbl_licensed_cases,
            "license_url": MWMBL_RESULTS_LICENSE_URL,
        },
        "traffic_matches_locked_zero_paid_budget": {
            "passed": (
                provider_query_calls == EXPECTED_CASE_COUNT * len(LIVE_PROVIDERS)
                and mwmbl_requests == EXPECTED_CASE_COUNT
                and wiby_requests == EXPECTED_CASE_COUNT
            ),
            "provider_query_calls": provider_query_calls,
            "required_provider_query_calls": EXPECTED_CASE_COUNT * len(LIVE_PROVIDERS),
            "mwmbl_requests": mwmbl_requests,
            "required_mwmbl_requests": EXPECTED_CASE_COUNT,
            "wiby_requests": wiby_requests,
            "required_wiby_requests": EXPECTED_CASE_COUNT,
            "paid_provider_requests": 0,
            "model_requests": 0,
            "retries": 0,
        },
    }
    retrieval_candidate_passed = all(gate["passed"] for gate in gates.values())
    return {
        "gates": gates,
        "paired_target_recall": {
            "candidate_community_vs_legacy_community": paired,
        },
        "retrieval_candidate_passed": retrieval_candidate_passed,
        "default_bundle_eligible": False,
        "default_bundle_blockers": [
            "Mwmbl search-result licensing is not yet clear for unrestricted default use.",
            "YaCy broad-Web quality was not measured on a reproducible populated index.",
            "An untouched end-to-end answer-model evaluation has not been run.",
        ],
        "phase12_untouched_evaluation_allowed": False,
        "stage_b_external_agents_allowed": False,
        "release_ready": False,
        "release_decision": "no-go",
        "reason": (
            "Phase 11.2 is authored retrieval calibration. Default promotion and release "
            "remain blocked independently of retrieval performance."
        ),
    }


async def run(arguments: argparse.Namespace) -> dict[str, Any]:
    suite_path = Path(arguments.suite)
    config_path = Path(arguments.searxng_config)
    cases, suite_bytes = load_suite(suite_path)
    config_bytes = await asyncio.to_thread(config_path.read_bytes)
    if sha256_bytes(config_bytes) != LOCKED_SEARXNG_CONFIG_SHA256:
        raise ValueError("Phase 11.2 SearXNG config checksum does not match the lock")

    cache_root = Path(arguments.cache_root)
    await asyncio.to_thread(cache_root.mkdir, parents=True, exist_ok=True)
    settings = Settings(
        deployment_profile=DeploymentProfile.COMMUNITY,
        enabled_providers=list(LIVE_PROVIDERS),
        searxng_url=arguments.searxng_url,
        wiby_url=arguments.wiby_url,
        mwmbl_url=arguments.mwmbl_url,
        quality_primary_provider_share=0.0,
        cache_path=cache_root / "phase11-2.sqlite3",
        request_timeout_seconds=arguments.request_timeout_seconds,
        respect_robots_txt=False,
    )
    recorder = RawResultRecorder()
    engine = EvidenceMesh(settings)
    engine.providers = [RecordingProvider(provider, recorder) for provider in engine.providers]
    outcomes: list[dict[str, Any]] = []
    retrieval_diagnostics: list[dict[str, Any]] = []
    provider_query_calls = 0
    mwmbl_requests = 0
    wiby_requests = 0
    mwmbl_raw_cases = 0
    mwmbl_raw_broad_cases = 0
    mwmbl_raw_long_tail_cases = 0
    mwmbl_licensed_cases = 0
    latencies: list[float] = []
    started_at = datetime.now(UTC)
    try:
        for index, case in enumerate(cases, start=1):
            if index > 1:
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
            mwmbl_requests += query_counts.get("mwmbl", 0)
            wiby_requests += query_counts.get("wiby", 0)
            raw_results = recorder.all_results()
            has_mwmbl_results = any(result.provider == "mwmbl" for result in raw_results)
            has_mwmbl_license = (
                response.metadata.provider_result_licenses.get("mwmbl") == MWMBL_RESULTS_LICENSE_URL
            )
            mwmbl_raw_cases += int(has_mwmbl_results)
            mwmbl_raw_broad_cases += int(has_mwmbl_results and case.stratum == "broad_web")
            mwmbl_raw_long_tail_cases += int(has_mwmbl_results and case.stratum == "long_tail")
            mwmbl_licensed_cases += int(has_mwmbl_results and has_mwmbl_license)
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
                    "stratum": case.stratum,
                    "latency_ms": elapsed_ms,
                    "provider_query_counts": query_counts,
                    "mwmbl_returned_results": has_mwmbl_results,
                    "mwmbl_result_license_present": has_mwmbl_license,
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
        provider_query_calls=provider_query_calls,
        mwmbl_requests=mwmbl_requests,
        wiby_requests=wiby_requests,
        mwmbl_raw_cases=mwmbl_raw_cases,
        mwmbl_raw_broad_cases=mwmbl_raw_broad_cases,
        mwmbl_raw_long_tail_cases=mwmbl_raw_long_tail_cases,
        mwmbl_licensed_cases=mwmbl_licensed_cases,
    )
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "suite": {
            "path": str(suite_path),
            "sha256": sha256_bytes(suite_bytes),
            "case_count": len(cases),
            "case_ids": [case.id for case in cases],
            "stratum_distribution": dict(sorted(Counter(case.stratum for case in cases).items())),
            "topic_distribution": dict(sorted(Counter(case.topic for case in cases).items())),
            "purpose": (
                "authored Phase 11.2 independent-index calibration; not an untouched "
                "final evaluation"
            ),
            "exploratory_query_excluded": True,
        },
        "protocol": {
            "arms": list(ARMS),
            "shared_raw_pool_per_case": True,
            "provider_calls_replayed": False,
            "provider_specific_ranking_boost": False,
            "provider_reservation": False,
            "cache": False,
            "retry_policy": "none",
            "max_results": arguments.max_results,
            "max_per_domain": arguments.max_per_domain,
            "prompt_projection_budget_chars": arguments.prompt_budget_chars,
            "minimum_pause_seconds": 1.1,
            "searxng_config_sha256": sha256_bytes(config_bytes),
            "live_providers": list(LIVE_PROVIDERS),
            "independent_providers": ["mwmbl", "wiby"],
            "mwmbl": {
                "endpoint": MWMBL_ENDPOINT,
                "query_budget_per_case": 1,
                "result_license_url": MWMBL_RESULTS_LICENSE_URL,
                "default_enabled": False,
            },
            "yacy": {
                "adapter_contract_tested": True,
                "broad_index_benchmarked": False,
                "default_enabled": False,
            },
            "maximum_mwmbl_requests": EXPECTED_CASE_COUNT,
            "maximum_wiby_requests": EXPECTED_CASE_COUNT,
            "tavily_requests": 0,
            "gemini_requests": 0,
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
            "mwmbl_requests": mwmbl_requests,
            "maximum_mwmbl_requests": EXPECTED_CASE_COUNT,
            "wiby_requests": wiby_requests,
            "maximum_wiby_requests": EXPECTED_CASE_COUNT,
            "paid_provider_requests": 0,
            "tavily_requests": 0,
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
            "fixed_provider_and_license_urls_in_report": True,
            "api_keys_in_report": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        default="benchmarks/data/independent_index_calibration_v1.json",
    )
    parser.add_argument(
        "--searxng-config",
        default="docker/searxng/phase11-community-settings.yml",
    )
    parser.add_argument("--searxng-url", default="http://127.0.0.1:8896")
    parser.add_argument("--wiby-url", default=WIBY_ENDPOINT)
    parser.add_argument("--mwmbl-url", default=MWMBL_ENDPOINT)
    parser.add_argument("--cache-root", default=".phase11-2-cache")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--max-per-domain", type=int, default=3)
    parser.add_argument("--prompt-budget-chars", type=int, default=12_000)
    parser.add_argument("--request-timeout-seconds", type=float, default=25.0)
    parser.add_argument("--wall-time-seconds", type=float, default=75.0)
    parser.add_argument("--pause-seconds", type=float, default=1.1)
    parser.add_argument("--network-region", default="not reported")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    if arguments.max_results != 10:
        parser.error("the locked Phase 11.2 protocol requires --max-results 10")
    if arguments.max_per_domain != 3:
        parser.error("the locked Phase 11.2 protocol requires --max-per-domain 3")
    if arguments.prompt_budget_chars != 12_000:
        parser.error("the locked Phase 11.2 protocol requires --prompt-budget-chars 12000")
    if arguments.pause_seconds < 1.1:
        parser.error("the locked Phase 11.2 protocol requires --pause-seconds >= 1.1")
    if arguments.wiby_url != WIBY_ENDPOINT:
        parser.error(f"the locked Phase 11.2 protocol requires --wiby-url {WIBY_ENDPOINT}")
    if arguments.mwmbl_url != MWMBL_ENDPOINT:
        parser.error(f"the locked Phase 11.2 protocol requires --mwmbl-url {MWMBL_ENDPOINT}")
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
