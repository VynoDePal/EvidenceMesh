#!/usr/bin/env python3
"""Run the locked Phase 9 paired GitHub repository-recall benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

try:
    from benchmarks.run_live_retrieval import percentile, rate_metric
    from benchmarks.run_quality_calibration import package_version, sha256_bytes
    from benchmarks.target_identity import target_matches_url, validate_target_identity
except ModuleNotFoundError:
    from run_live_retrieval import percentile, rate_metric
    from run_quality_calibration import package_version, sha256_bytes
    from target_identity import target_matches_url, validate_target_identity
from evidencemesh.config import DeploymentProfile, Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType
from evidencemesh.providers.base import SearchProvider
from evidencemesh.providers.github import GitHubProvider, RepositoryQueryStrategy

LOCKED_SUITE_SHA256 = "0cfafa78e44662af47e51f26775593af0e3e9d6dbbc417d18178f1218f5ad61a"
LOCKED_MANIFEST_SHA256 = "7369c9a0f47e4dbf4f752885f32bdf28e44b0472a5129353e75f4da616d20e57"
MAX_INPUT_BYTES = 1_000_000
ARMS = ("baseline", "candidate")
DIFFICULTIES = ("low", "medium", "high")
QUERY_FORMS = ("entity_first", "intent_prefix")


@dataclass(frozen=True, slots=True)
class RepositoryCase:
    id: str
    query: str
    target_identities: tuple[str, ...]
    difficulty: str
    query_form: str


class RawResultRecorder:
    """Capture adapter-returned ranks without making an additional request."""

    def __init__(self) -> None:
        self.results: list[ProviderResult] = []

    def reset(self) -> None:
        self.results = []

    def record(self, results: list[ProviderResult]) -> None:
        self.results.extend(results)

    def target_rank(self, targets: tuple[str, ...]) -> int | None:
        ranks = [result.rank for result in self.results if target_matches_url(targets, result.url)]
        return min(ranks) if ranks else None


class RecordingProvider(SearchProvider):
    """Delegate exactly once and retain the adapter result list in memory."""

    def __init__(self, provider: SearchProvider, recorder: RawResultRecorder) -> None:
        self.provider = provider
        self.recorder = recorder
        self.name = provider.name
        self.supported_profiles = provider.supported_profiles
        self.source_type = provider.source_type
        self.query_budget = provider.query_budget
        self.minimum_cache_ttl_seconds = provider.minimum_cache_ttl_seconds

    def source_family(self, profile: SearchProfile) -> SourceType:
        return self.provider.source_family(profile)

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        results = await self.provider.search(query, request)
        self.recorder.record(results)
        return results


def load_suite(path: Path) -> tuple[list[RepositoryCase], dict[str, Any]]:
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("GitHub recall suite exceeds one megabyte")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("GitHub recall suite is not valid JSON") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("GitHub recall suite must be a non-empty JSON array")

    expected_keys = {
        "id",
        "query",
        "target_identities",
        "difficulty",
        "query_form",
    }
    cases: list[RepositoryCase] = []
    seen_ids: set[str] = set()
    seen_queries: set[str] = set()
    seen_targets: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("GitHub recall case fields do not match the locked schema")
        case_id = item["id"]
        query = item["query"]
        identities = item["target_identities"]
        difficulty = item["difficulty"]
        query_form = item["query_form"]
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError("case IDs must be unique non-empty strings")
        normalized_query = query.casefold().strip() if isinstance(query, str) else ""
        if not normalized_query or normalized_query in seen_queries:
            raise ValueError("queries must be unique non-empty strings")
        if difficulty not in DIFFICULTIES or query_form not in QUERY_FORMS:
            raise ValueError(f"case {case_id} has an invalid authored stratum")
        if (
            not isinstance(identities, list)
            or not identities
            or not all(isinstance(identity, str) for identity in identities)
        ):
            raise ValueError(f"case {case_id} has invalid target identities")
        normalized_targets = tuple(validate_target_identity(identity) for identity in identities)
        if any(not target.startswith("github:") for target in normalized_targets):
            raise ValueError(f"case {case_id} has a non-GitHub target")
        if len(set(normalized_targets)) != len(normalized_targets):
            raise ValueError(f"case {case_id} has duplicate target identities")
        if set(normalized_targets) & seen_targets:
            raise ValueError("target repositories must be unique")
        seen_ids.add(case_id)
        seen_queries.add(normalized_query)
        seen_targets.update(normalized_targets)
        cases.append(
            RepositoryCase(
                id=case_id.strip(),
                query=query.strip(),
                target_identities=normalized_targets,
                difficulty=difficulty,
                query_form=query_form,
            )
        )

    difficulty_distribution = {
        difficulty: sum(case.difficulty == difficulty for case in cases)
        for difficulty in DIFFICULTIES
    }
    query_form_distribution = {
        query_form: sum(case.query_form == query_form for case in cases)
        for query_form in QUERY_FORMS
    }
    if len(cases) != 24 or any(count != 8 for count in difficulty_distribution.values()):
        raise ValueError("locked GitHub recall calibration requires 24 cases, eight per difficulty")
    if any(count != 12 for count in query_form_distribution.values()):
        raise ValueError("locked GitHub recall calibration requires 12 cases per query form")
    ids = [case.id for case in cases]
    return cases, {
        "file": path.name,
        "sha256": sha256_bytes(raw),
        "count": len(cases),
        "ids": ids,
        "manifest_sha256": sha256_bytes("\n".join(ids).encode()),
        "difficulty_distribution": difficulty_distribution,
        "query_form_distribution": query_form_distribution,
        "target_identity_schema": 1,
    }


def validate_locked_inputs(suite_manifest: dict[str, Any]) -> None:
    if suite_manifest["sha256"] != LOCKED_SUITE_SHA256:
        raise ValueError("suite checksum does not match benchmark protocol v7")
    if suite_manifest["manifest_sha256"] != LOCKED_MANIFEST_SHA256:
        raise ValueError("suite manifest does not match benchmark protocol v7")


def validate_arguments(arguments: argparse.Namespace) -> None:
    if arguments.max_results != 10:
        raise ValueError("locked GitHub recall benchmark requires exactly 10 results")
    if not math.isclose(arguments.request_timeout, 20.0):
        raise ValueError("locked GitHub recall benchmark requires a 20 second timeout")
    if not math.isclose(arguments.pause_seconds, 6.5):
        raise ValueError("locked GitHub recall benchmark requires a 6.5 second pause")


def _final_target_rank(case: RepositoryCase, hits: list[Any]) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if target_matches_url(case.target_identities, hit.canonical_url):
            return rank
    return None


def _error_outcome(
    case: RepositoryCase,
    arm: str,
    *,
    latency_ms: float,
    error_type: str,
) -> dict[str, Any]:
    return {
        "case_id": case.id,
        "arm": arm,
        "difficulty": case.difficulty,
        "query_form": case.query_form,
        "request_succeeded": False,
        "available": False,
        "target_hit_at_10": False,
        "target_rank": None,
        "raw_target_seen": False,
        "raw_target_rank": None,
        "target_dropped_by_ranking": False,
        "latency_ms": round(latency_ms, 3),
        "result_count": 0,
        "provider_query_count": 0,
        "provider_failed": True,
        "cache_hits": 0,
        "error_type": error_type,
    }


async def run_arm_case(
    engine: EvidenceMesh,
    recorder: RawResultRecorder,
    case: RepositoryCase,
    arm: str,
    *,
    max_results: int,
) -> dict[str, Any]:
    recorder.reset()
    started = time.perf_counter()
    try:
        response = await engine.search(
            SearchRequest(
                query=case.query,
                limit=max_results,
                profile=SearchProfile.CODE,
                fetch_content=False,
                use_cache=False,
            )
        )
    except Exception as exc:
        return _error_outcome(
            case,
            arm,
            latency_ms=(time.perf_counter() - started) * 1_000,
            error_type=type(exc).__name__,
        )

    hits = response.results[:max_results]
    metadata = response.metadata
    target_rank = _final_target_rank(case, hits)
    raw_target_rank = recorder.target_rank(case.target_identities)
    return {
        "case_id": case.id,
        "arm": arm,
        "difficulty": case.difficulty,
        "query_form": case.query_form,
        "request_succeeded": "github" in metadata.providers_succeeded,
        "available": bool(hits),
        "target_hit_at_10": target_rank is not None,
        "target_rank": target_rank,
        "raw_target_seen": raw_target_rank is not None,
        "raw_target_rank": raw_target_rank,
        "target_dropped_by_ranking": raw_target_rank is not None and target_rank is None,
        "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
        "result_count": len(hits),
        "provider_query_count": metadata.provider_query_counts.get("github", 0),
        "provider_failed": bool(metadata.provider_failures),
        "cache_hits": metadata.cache_hits,
        "error_type": None,
    }


def aggregate(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(outcome["latency_ms"]) for outcome in outcomes]
    target_ranks = [
        int(outcome["target_rank"]) for outcome in outcomes if outcome["target_rank"] is not None
    ]
    raw_target_ranks = [
        int(outcome["raw_target_rank"])
        for outcome in outcomes
        if outcome["raw_target_rank"] is not None
    ]
    return {
        "request_success": rate_metric(
            [bool(outcome["request_succeeded"]) for outcome in outcomes]
        ),
        "availability": rate_metric([bool(outcome["available"]) for outcome in outcomes]),
        "target_hit_at_10": rate_metric(
            [bool(outcome["target_hit_at_10"]) for outcome in outcomes]
        ),
        "raw_target_seen": rate_metric([bool(outcome["raw_target_seen"]) for outcome in outcomes]),
        "target_dropped_by_ranking": rate_metric(
            [bool(outcome["target_dropped_by_ranking"]) for outcome in outcomes]
        ),
        "target_rank": {
            "observed": len(target_ranks),
            "mean": round(sum(target_ranks) / len(target_ranks), 3) if target_ranks else None,
            "p50": round(percentile(target_ranks, 0.50), 3) if target_ranks else None,
            "p95": round(percentile(target_ranks, 0.95), 3) if target_ranks else None,
            "at_1": sum(rank <= 1 for rank in target_ranks),
            "at_3": sum(rank <= 3 for rank in target_ranks),
            "at_5": sum(rank <= 5 for rank in target_ranks),
            "at_10": sum(rank <= 10 for rank in target_ranks),
        },
        "raw_target_rank": {
            "observed": len(raw_target_ranks),
            "at_10": sum(rank <= 10 for rank in raw_target_ranks),
            "at_20": sum(rank <= 20 for rank in raw_target_ranks),
        },
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "maximum": round(max(latencies, default=0.0), 3),
        },
        "result_count": {
            "total": sum(int(outcome["result_count"]) for outcome in outcomes),
            "mean": round(
                sum(int(outcome["result_count"]) for outcome in outcomes) / max(1, len(outcomes)),
                3,
            ),
        },
        "provider_query_count": sum(int(outcome["provider_query_count"]) for outcome in outcomes),
        "cache_hits": sum(int(outcome["cache_hits"]) for outcome in outcomes),
    }


def _paired_binary(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    baseline_by_id = {outcome["case_id"]: outcome for outcome in baseline}
    candidate_by_id = {outcome["case_id"]: outcome for outcome in candidate}
    if set(baseline_by_id) != set(candidate_by_id):
        raise ValueError("paired benchmark arms do not contain the same cases")
    candidate_wins = 0
    baseline_wins = 0
    both_true = 0
    both_false = 0
    for case_id in sorted(baseline_by_id):
        baseline_value = bool(baseline_by_id[case_id][field])
        candidate_value = bool(candidate_by_id[case_id][field])
        if candidate_value and not baseline_value:
            candidate_wins += 1
        elif baseline_value and not candidate_value:
            baseline_wins += 1
        elif baseline_value:
            both_true += 1
        else:
            both_false += 1
    discordant = candidate_wins + baseline_wins
    if discordant:
        lower_tail = sum(
            math.comb(discordant, index) for index in range(min(candidate_wins, baseline_wins) + 1)
        ) / (2**discordant)
        exact_p_value = min(1.0, 2 * lower_tail)
    else:
        exact_p_value = 1.0
    return {
        "candidate_wins": candidate_wins,
        "baseline_wins": baseline_wins,
        "both_true": both_true,
        "both_false": both_false,
        "net_gain": candidate_wins - baseline_wins,
        "discordant_pairs": discordant,
        "mcnemar_exact_two_sided_p": round(exact_p_value, 6),
    }


def paired_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = [outcome for outcome in outcomes if outcome["arm"] == "baseline"]
    candidate = [outcome for outcome in outcomes if outcome["arm"] == "candidate"]
    return {
        "target_hit_at_10": _paired_binary(
            baseline,
            candidate,
            "target_hit_at_10",
        ),
        "raw_target_seen": _paired_binary(
            baseline,
            candidate,
            "raw_target_seen",
        ),
    }


def gate_decision(
    outcomes: list[dict[str, Any]],
    arm_metrics: dict[str, dict[str, Any]],
    paired: dict[str, Any],
) -> dict[str, Any]:
    candidate_outcomes = [outcome for outcome in outcomes if outcome["arm"] == "candidate"]
    candidate = arm_metrics["candidate"]
    checks = {
        "candidate": {
            "request_success": candidate["request_success"]["numerator"] >= 23,
            "availability": candidate["availability"]["numerator"] >= 23,
            "raw_target_seen": candidate["raw_target_seen"]["numerator"] >= 20,
            "target_hit_at_10": candidate["target_hit_at_10"]["numerator"] >= 18,
            "p95_latency": candidate["latency_ms"]["p95"] <= 15_000,
            "one_query_per_case": all(
                outcome["provider_query_count"] == 1 for outcome in candidate_outcomes
            ),
            "zero_cache_hits": all(outcome["cache_hits"] == 0 for outcome in candidate_outcomes),
        },
        "paired": {
            "minimum_net_target_gain": paired["target_hit_at_10"]["net_gain"] >= 4,
            "no_target_regressions": paired["target_hit_at_10"]["baseline_wins"] == 0,
            "raw_recall_not_worse": (
                arm_metrics["candidate"]["raw_target_seen"]["numerator"]
                >= arm_metrics["baseline"]["raw_target_seen"]["numerator"]
            ),
        },
    }
    functional_gate_passed = all(passed for group in checks.values() for passed in group.values())
    return {
        "checks": checks,
        "functional_gate_passed": functional_gate_passed,
        "cross_network_gate": {
            "required": 2,
            "completed": 1,
            "status": "not_testable",
        },
        "stage_b_200_case_run_allowed": False,
        "release_ready": False,
        "release_decision": "no-go",
    }


async def run_paired_benchmark(
    cases: list[RepositoryCase],
    *,
    endpoint: str,
    cache_dir: Path,
    max_results: int,
    request_timeout: float,
    pause_seconds: float,
    progress: bool,
) -> list[dict[str, Any]]:
    await asyncio.to_thread(cache_dir.mkdir, parents=True, exist_ok=True)
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(request_timeout),
        headers={"User-Agent": "EvidenceMesh/0.1 Phase9 paired benchmark"},
        follow_redirects=False,
    )
    engines: dict[str, EvidenceMesh] = {}
    recorders: dict[str, RawResultRecorder] = {}
    strategies = {
        "baseline": RepositoryQueryStrategy.LEGACY,
        "candidate": RepositoryQueryStrategy.ENTITY_ANCHOR,
    }
    try:
        for arm in ARMS:
            settings = Settings(
                deployment_profile=DeploymentProfile.COMMUNITY,
                enabled_providers=["github"],
                github_search_url=endpoint,
                github_token=None,
                cache_path=cache_dir / f"{arm}.sqlite3",
                request_timeout_seconds=request_timeout,
                max_concurrency=1,
            )
            recorder = RawResultRecorder()
            provider = RecordingProvider(
                GitHubProvider(
                    endpoint,
                    client,
                    token=None,
                    query_strategy=strategies[arm],
                ),
                recorder,
            )
            recorders[arm] = recorder
            engines[arm] = EvidenceMesh(
                settings,
                providers=[provider],
                client=client,
            )

        outcomes: list[dict[str, Any]] = []
        completed_requests = 0
        total_requests = len(cases) * len(ARMS)
        for case_index, case in enumerate(cases):
            arm_order = ARMS if case_index % 2 == 0 else tuple(reversed(ARMS))
            for arm in arm_order:
                outcome = await run_arm_case(
                    engines[arm],
                    recorders[arm],
                    case,
                    arm,
                    max_results=max_results,
                )
                outcomes.append(outcome)
                completed_requests += 1
                if progress:
                    print(
                        f"[{completed_requests:02d}/{total_requests:02d}] "
                        f"{case.id} {arm}: success={outcome['request_succeeded']} "
                        f"target_rank={outcome['target_rank']} "
                        f"raw_rank={outcome['raw_target_rank']}",
                        file=sys.stderr,
                        flush=True,
                    )
                if completed_requests < total_requests:
                    await asyncio.sleep(pause_seconds)
        arm_index = {arm: index for index, arm in enumerate(ARMS)}
        return sorted(outcomes, key=lambda item: (item["case_id"], arm_index[item["arm"]]))
    finally:
        for engine in engines.values():
            await engine.aclose()
        await client.aclose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path("benchmarks/data/github_recall_v1.json"),
    )
    parser.add_argument(
        "--github-endpoint",
        default="https://api.github.com/search/repositories",
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--request-timeout", type=float, default=20.0)
    parser.add_argument("--pause-seconds", type=float, default=6.5)
    parser.add_argument("--network-region", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--progress", action="store_true")
    return parser


async def async_main(arguments: argparse.Namespace) -> dict[str, Any]:
    validate_arguments(arguments)
    cases, suite = load_suite(arguments.suite)
    validate_locked_inputs(suite)
    outcomes = await run_paired_benchmark(
        cases,
        endpoint=arguments.github_endpoint,
        cache_dir=arguments.cache_dir,
        max_results=arguments.max_results,
        request_timeout=arguments.request_timeout,
        pause_seconds=arguments.pause_seconds,
        progress=arguments.progress,
    )
    arm_metrics = {
        arm: aggregate([outcome for outcome in outcomes if outcome["arm"] == arm]) for arm in ARMS
    }
    by_difficulty = {
        arm: {
            difficulty: aggregate(
                [
                    outcome
                    for outcome in outcomes
                    if outcome["arm"] == arm and outcome["difficulty"] == difficulty
                ]
            )
            for difficulty in DIFFICULTIES
        }
        for arm in ARMS
    }
    paired = paired_metrics(outcomes)
    decision = gate_decision(outcomes, arm_metrics, paired)
    return {
        "schema_version": 1,
        "benchmark": "evidencemesh-github-recall-paired-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "commit_sha": os.getenv("EVIDENCEMESH_BENCHMARK_COMMIT", "unknown"),
            "network_region": arguments.network_region,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "evidencemesh": package_version("evidencemesh"),
            "httpx": package_version("httpx"),
        },
        "suite": suite,
        "provider_configuration": {
            "provider": "github",
            "endpoint": arguments.github_endpoint,
            "authentication": "anonymous",
            "api_version": "2022-11-28",
            "maximum_provider_results": 20,
            "arms": {
                "baseline": {
                    "query_strategy": RepositoryQueryStrategy.LEGACY.value,
                    "description": "Phase 8 intent trimming plus in:name,description",
                },
                "candidate": {
                    "query_strategy": RepositoryQueryStrategy.ENTITY_ANCHOR.value,
                    "description": ("repository entity anchor plus in:name,description,topics"),
                },
            },
        },
        "protocol": {
            "version": 7,
            "case_count": len(cases),
            "arm_count": len(ARMS),
            "request_count": len(cases) * len(ARMS),
            "requests_per_arm": len(cases),
            "maximum_queries_per_arm_case": 1,
            "interleaving": "alternating arm order by case",
            "max_results": arguments.max_results,
            "request_timeout_seconds": arguments.request_timeout,
            "pause_seconds": arguments.pause_seconds,
            "retry_policy": "none",
            "content_fetching": False,
            "cache": False,
            "tavily_requests": 0,
            "new_user_secrets": 0,
            "target_identity_schema": 1,
            "raw_target_rank_capture": "in-memory adapter wrapper; no additional requests",
        },
        "metrics": {
            "arms": arm_metrics,
            "by_difficulty": by_difficulty,
            "paired": paired,
        },
        "decision": decision,
        "outcomes": outcomes,
    }


def main() -> None:
    arguments = build_parser().parse_args()
    report = asyncio.run(async_main(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
