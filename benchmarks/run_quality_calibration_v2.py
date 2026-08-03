#!/usr/bin/env python3
"""Run the locked Phase 8 quality calibration with target-rank diagnostics."""

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

try:
    from benchmarks.run_live_retrieval import percentile, rate_metric
    from benchmarks.run_quality_calibration import (
        CALIBRATION_PROVIDERS,
        EXPECTED_FAMILIES,
        EXPECTED_TOPICS,
        contribution_metrics,
        gate_decision,
        locked_config_manifest,
        package_version,
        sha256_bytes,
    )
    from benchmarks.target_identity import target_matches_url, validate_target_identity
except ModuleNotFoundError:
    from run_live_retrieval import percentile, rate_metric
    from run_quality_calibration import (
        CALIBRATION_PROVIDERS,
        EXPECTED_FAMILIES,
        EXPECTED_TOPICS,
        contribution_metrics,
        gate_decision,
        locked_config_manifest,
        package_version,
        sha256_bytes,
    )
    from target_identity import target_matches_url, validate_target_identity
from evidencemesh.config import DeploymentProfile, Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import (
    ProviderResult,
    SearchProfile,
    SearchRequest,
    SourceFamilyStatus,
    SourceType,
)
from evidencemesh.providers.base import SearchProvider

LOCKED_SUITE_SHA256 = "4a080230b0fe4590f1ef1af9087c7dbfaa05910bdcbd9c43a197cf87c5e44dc4"
LOCKED_CONFIG_SHA256 = "26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645"
MAX_INPUT_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    id: str
    query: str
    profile: SearchProfile
    expected_family: str
    target_identities: tuple[str, ...]
    topic: str


class RawResultRecorder:
    """Case-scoped capture used only for aggregate-safe benchmark diagnostics."""

    def __init__(self) -> None:
        self._results: dict[str, list[ProviderResult]] = {}

    def reset(self) -> None:
        self._results = {}

    def record(self, provider: str, results: list[ProviderResult]) -> None:
        self._results.setdefault(provider, []).extend(results)

    def target_provider_ranks(self, targets: tuple[str, ...]) -> dict[str, int]:
        ranks: dict[str, int] = {}
        for provider, results in self._results.items():
            matching = [
                result.rank for result in results if target_matches_url(targets, result.url)
            ]
            if matching:
                ranks[provider] = min(matching)
        return dict(sorted(ranks.items()))


class RecordingProvider(SearchProvider):
    """Delegate exactly once while retaining provider-native ranks in memory."""

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
        self.recorder.record(self.name, results)
        return results


def load_suite(path: Path) -> tuple[list[CalibrationCase], dict[str, Any]]:
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("calibration suite exceeds one megabyte")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("calibration suite is not valid JSON") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("calibration suite must be a non-empty JSON array")

    cases: list[CalibrationCase] = []
    seen_ids: set[str] = set()
    seen_queries: set[str] = set()
    expected_keys = {
        "id",
        "query",
        "profile",
        "expected_family",
        "target_identities",
        "topic",
    }
    target_kind_by_topic = {
        "web": "domain:",
        "reference": "wikipedia:",
        "academic": "arxiv:",
        "code": "github:",
    }
    for item in payload:
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("calibration case fields do not match the locked schema")
        case_id = item["id"]
        query = item["query"]
        expected_family = item["expected_family"]
        topic = item["topic"]
        target_identities = item["target_identities"]
        try:
            profile = SearchProfile(item["profile"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"case {case_id!r} has an invalid profile") from exc
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError("calibration case IDs must be unique non-empty strings")
        normalized_query = query.casefold().strip() if isinstance(query, str) else ""
        if not normalized_query or normalized_query in seen_queries:
            raise ValueError("calibration queries must be unique non-empty strings")
        if expected_family not in EXPECTED_FAMILIES or topic not in EXPECTED_TOPICS:
            raise ValueError(f"case {case_id} has an invalid topic or expected family")
        if profile.value != expected_family or topic != expected_family:
            raise ValueError(f"case {case_id} must align profile, topic and required family")
        if (
            not isinstance(target_identities, list)
            or not target_identities
            or not all(isinstance(identity, str) for identity in target_identities)
        ):
            raise ValueError(f"case {case_id} has invalid target identities")
        try:
            normalized_targets = tuple(
                validate_target_identity(identity) for identity in target_identities
            )
        except ValueError as exc:
            raise ValueError(f"case {case_id} has invalid target identities") from exc
        expected_kind = target_kind_by_topic[topic]
        if any(not target.startswith(expected_kind) for target in normalized_targets):
            raise ValueError(f"case {case_id} has a target identity for the wrong topic")
        if len(set(normalized_targets)) != len(normalized_targets):
            raise ValueError(f"case {case_id} has duplicate target identities")
        seen_ids.add(case_id)
        seen_queries.add(normalized_query)
        cases.append(
            CalibrationCase(
                id=case_id.strip(),
                query=query.strip(),
                profile=profile,
                expected_family=expected_family,
                target_identities=normalized_targets,
                topic=topic,
            )
        )

    distribution = {topic: sum(case.topic == topic for case in cases) for topic in EXPECTED_TOPICS}
    if len(cases) != 32 or any(count != 8 for count in distribution.values()):
        raise ValueError("locked calibration requires 32 cases, eight per topic")
    ids = [case.id for case in cases]
    return cases, {
        "file": path.name,
        "sha256": sha256_bytes(raw),
        "count": len(cases),
        "ids": ids,
        "manifest_sha256": sha256_bytes("\n".join(ids).encode()),
        "topic_distribution": distribution,
        "target_identity_schema": 1,
    }


def validate_locked_inputs(
    suite_manifest: dict[str, Any],
    config_manifest: dict[str, str],
) -> None:
    if suite_manifest["sha256"] != LOCKED_SUITE_SHA256:
        raise ValueError("suite checksum does not match benchmark protocol v6")
    if config_manifest["sha256"] != LOCKED_CONFIG_SHA256:
        raise ValueError("SearXNG checksum does not match benchmark protocol v6")


def validate_arguments(arguments: argparse.Namespace) -> None:
    if arguments.max_results != 10:
        raise ValueError("locked calibration requires exactly 10 results")
    if not math.isclose(arguments.request_timeout, 20.0):
        raise ValueError("locked calibration requires a 20 second request timeout")
    if not math.isclose(arguments.pause_seconds, 0.5):
        raise ValueError("locked calibration requires a 0.5 second pause")


def _target_rank(case: CalibrationCase, hits: list[Any]) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if target_matches_url(case.target_identities, hit.canonical_url):
            return rank
    return None


def _error_outcome(
    case: CalibrationCase,
    *,
    latency_ms: float,
    max_results: int,
    error_type: str,
) -> dict[str, Any]:
    request = SearchRequest(query=case.query, limit=max_results, profile=case.profile)
    return {
        "case_id": case.id,
        "topic": case.topic,
        "profile": case.profile.value,
        "expected_family": case.expected_family,
        "response_success": False,
        "available": False,
        "target_hit_at_10": False,
        "target_rank": None,
        "raw_target_seen": False,
        "raw_target_provider_ranks": {},
        "target_dropped_by_ranking": False,
        "expected_family_hit_at_10": False,
        "provider_degradation": True,
        "required_family_satisfied": False,
        "required_family_status": "runner_error",
        "latency_ms": round(latency_ms, 3),
        "result_count": 0,
        "providers_requested": [],
        "providers_succeeded": [],
        "providers_failed": [],
        "providers_contributed": [],
        "provider_query_counts": {},
        "source_families_contributed": [],
        "degraded_source_families": [],
        "failed_source_families": [],
        "effective_max_per_domain": request.effective_max_per_domain,
        "max_per_domain_policy": request.max_per_domain_policy,
        "cache_hits": 0,
        "error_type": error_type,
    }


async def run_case(
    engine: EvidenceMesh,
    recorder: RawResultRecorder,
    case: CalibrationCase,
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
                profile=case.profile,
                fetch_content=False,
                use_cache=True,
            )
        )
    except Exception as exc:  # The public report records type only and continues.
        return _error_outcome(
            case,
            latency_ms=(time.perf_counter() - started) * 1_000,
            max_results=max_results,
            error_type=type(exc).__name__,
        )

    hits = response.results[:max_results]
    metadata = response.metadata
    target_rank = _target_rank(case, hits)
    raw_provider_ranks = recorder.target_provider_ranks(case.target_identities)
    raw_target_seen = bool(raw_provider_ranks)
    providers_contributed = sorted({provider for hit in hits for provider in hit.providers})
    families_contributed = sorted({hit.source_type.value for hit in hits})
    failed_providers = sorted({key.split(":", 1)[0] for key in metadata.provider_failures})
    required_status = metadata.required_source_family_status
    return {
        "case_id": case.id,
        "topic": case.topic,
        "profile": case.profile.value,
        "expected_family": case.expected_family,
        "response_success": True,
        "available": bool(hits),
        "target_hit_at_10": target_rank is not None,
        "target_rank": target_rank,
        "raw_target_seen": raw_target_seen,
        "raw_target_provider_ranks": raw_provider_ranks,
        "target_dropped_by_ranking": raw_target_seen and target_rank is None,
        "expected_family_hit_at_10": any(
            hit.source_type.value == case.expected_family for hit in hits
        ),
        "provider_degradation": bool(metadata.provider_failures),
        "required_family_satisfied": required_status is SourceFamilyStatus.SATISFIED,
        "required_family_status": required_status.value,
        "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
        "result_count": len(hits),
        "providers_requested": metadata.providers_requested,
        "providers_succeeded": metadata.providers_succeeded,
        "providers_failed": failed_providers,
        "providers_contributed": providers_contributed,
        "provider_query_counts": metadata.provider_query_counts,
        "source_families_contributed": families_contributed,
        "degraded_source_families": metadata.degraded_source_families,
        "failed_source_families": metadata.failed_source_families,
        "effective_max_per_domain": metadata.effective_max_per_domain,
        "max_per_domain_policy": metadata.max_per_domain_policy,
        "cache_hits": metadata.cache_hits,
        "error_type": None,
    }


def aggregate(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(outcome["latency_ms"]) for outcome in outcomes]
    target_ranks = [
        int(outcome["target_rank"]) for outcome in outcomes if outcome["target_rank"] is not None
    ]
    required_satisfied = [bool(outcome["required_family_satisfied"]) for outcome in outcomes]
    return {
        "response_success": rate_metric(
            [bool(outcome["response_success"]) for outcome in outcomes]
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
            "mean": (round(sum(target_ranks) / len(target_ranks), 3) if target_ranks else None),
            "p50": round(percentile(target_ranks, 0.50), 3) if target_ranks else None,
            "p95": round(percentile(target_ranks, 0.95), 3) if target_ranks else None,
            "at_1": sum(rank <= 1 for rank in target_ranks),
            "at_3": sum(rank <= 3 for rank in target_ranks),
            "at_5": sum(rank <= 5 for rank in target_ranks),
            "at_10": sum(rank <= 10 for rank in target_ranks),
        },
        "expected_family_hit_at_10": rate_metric(
            [bool(outcome["expected_family_hit_at_10"]) for outcome in outcomes]
        ),
        "provider_degradation": rate_metric(
            [bool(outcome["provider_degradation"]) for outcome in outcomes]
        ),
        "required_family_unsatisfied": rate_metric(
            [not satisfied for satisfied in required_satisfied]
        ),
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
    }


async def run_calibration(
    cases: list[CalibrationCase],
    settings: Settings,
    *,
    max_results: int,
    pause_seconds: float,
    progress: bool,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    recorder = RawResultRecorder()
    async with EvidenceMesh(settings) as engine:
        engine.providers = [RecordingProvider(provider, recorder) for provider in engine.providers]
        for index, case in enumerate(cases):
            outcome = await run_case(
                engine,
                recorder,
                case,
                max_results=max_results,
            )
            outcomes.append(outcome)
            if progress:
                print(
                    f"[{index + 1:02d}/{len(cases):02d}] {case.id}: "
                    f"available={outcome['available']} "
                    f"target_rank={outcome['target_rank']} "
                    f"raw_target={outcome['raw_target_seen']} "
                    f"required={outcome['required_family_status']}",
                    file=sys.stderr,
                    flush=True,
                )
            if index + 1 < len(cases):
                await asyncio.sleep(pause_seconds)
    return outcomes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path("benchmarks/data/quality_calibration_v3.json"),
    )
    parser.add_argument(
        "--searxng-config",
        type=Path,
        default=Path("docker/searxng/community-calibration-settings.yml"),
    )
    parser.add_argument("--searxng-image", required=True)
    parser.add_argument("--searxng-url", default="http://127.0.0.1:8891")
    parser.add_argument("--cache-path", type=Path, required=True)
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--request-timeout", type=float, default=20.0)
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    parser.add_argument("--network-region", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--progress", action="store_true")
    return parser


async def async_main(arguments: argparse.Namespace) -> dict[str, Any]:
    validate_arguments(arguments)
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        raise ValueError("TAVILY_API_KEY is required for the locked Phase 8 calibration")
    cases, suite_manifest = load_suite(arguments.suite)
    config_manifest = locked_config_manifest(
        arguments.searxng_config,
        arguments.searxng_image,
    )
    validate_locked_inputs(suite_manifest, config_manifest)
    settings = Settings(
        deployment_profile=DeploymentProfile.QUALITY,
        enabled_providers=list(CALIBRATION_PROVIDERS),
        searxng_url=arguments.searxng_url,
        tavily_api_key=tavily_api_key,
        cache_path=arguments.cache_path,
        request_timeout_seconds=arguments.request_timeout,
        max_concurrency=6,
        search_cache_ttl_seconds=86_400,
    )
    outcomes = await run_calibration(
        cases,
        settings,
        max_results=arguments.max_results,
        pause_seconds=arguments.pause_seconds,
        progress=arguments.progress,
    )
    overall = aggregate(outcomes)
    by_topic = {
        topic: aggregate([outcome for outcome in outcomes if outcome["topic"] == topic])
        for topic in EXPECTED_TOPICS
    }
    providers, families = contribution_metrics(outcomes)
    decision = gate_decision(overall, by_topic, providers, families, outcomes)
    return {
        "schema_version": 3,
        "benchmark": "evidencemesh-quality-calibration-v3",
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "commit_sha": os.getenv("EVIDENCEMESH_BENCHMARK_COMMIT") or os.getenv("GITHUB_SHA"),
            "network_region": arguments.network_region,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "packages": {
                "evidencemesh": package_version("evidencemesh"),
                "httpx": package_version("httpx"),
            },
        },
        "suite": suite_manifest,
        "provider_configuration": {
            "deployment_profile": DeploymentProfile.QUALITY.value,
            "providers": list(CALIBRATION_PROVIDERS),
            "searxng": config_manifest,
            "tavily": {
                "enabled": True,
                "authentication": "environment secret; value and fingerprint omitted",
                "search_depth": "basic",
                "query_budget": 1,
                "maximum_results": 10,
            },
            "github": {
                "authentication": "anonymous",
                "repository_query_normalization": "intent suffix removal plus in:name,description",
                "query_budget": 1,
            },
            "other_keyed_providers_enabled": False,
        },
        "protocol": {
            "version": 6,
            "max_results": arguments.max_results,
            "request_timeout_seconds": arguments.request_timeout,
            "pause_seconds": arguments.pause_seconds,
            "request_count": len(cases),
            "maximum_tavily_requests": 8,
            "maximum_tavily_credits": 8,
            "retry_policy": "none",
            "content_fetching": False,
            "query_variants": False,
            "profile_default_max_per_domain": {
                "web": 3,
                "news": 3,
                "reference": 10,
                "academic": 10,
                "code": 10,
            },
            "target_identity_schema": 1,
            "raw_target_rank_capture": "in-memory provider wrapper; no additional requests",
            "arxiv_minimum_interval_seconds": 3.0,
            "arxiv_minimum_cache_ttl_seconds": 86_400,
        },
        "metrics": {
            "overall": overall,
            "by_topic": by_topic,
            "providers": providers,
            "source_families": families,
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
