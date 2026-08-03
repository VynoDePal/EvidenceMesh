#!/usr/bin/env python3
"""Run the locked Phase 7 Tavily quality-profile calibration."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

try:
    from benchmarks.run_live_retrieval import percentile, rate_metric
except ModuleNotFoundError:
    from run_live_retrieval import percentile, rate_metric
from evidencemesh.config import DeploymentProfile, Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import SearchProfile, SearchRequest, SourceFamilyStatus
from evidencemesh.urls import domain_matches

LOCKED_SUITE_SHA256 = "bfa1b033d31e509f622d35d7eb224498db9ba7a939fce3554b0a57c44417b869"
LOCKED_CONFIG_SHA256 = "26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645"
EXPECTED_TOPICS = ("academic", "code", "reference", "web")
EXPECTED_FAMILIES = frozenset(EXPECTED_TOPICS)
CALIBRATION_PROVIDERS = (
    "searxng",
    "wikipedia",
    "crossref",
    "arxiv",
    "github",
    "tavily",
)
MAX_INPUT_BYTES = 1_000_000
OVERALL_GATES: dict[str, float | int] = {
    "minimum_availability_rate": 0.90,
    "minimum_target_hit_at_10": 0.80,
    "minimum_expected_family_hit_at_10": 0.90,
    "maximum_provider_degradation_rate": 0.25,
    "maximum_required_family_unsatisfied_rate": 0.10,
    "maximum_p95_latency_ms": 15_000.0,
    "minimum_contributing_providers": 5,
    "minimum_contributing_source_families": 4,
}
TOPIC_GATES: dict[str, float] = {
    "minimum_availability_rate": 0.875,
    "minimum_target_hit_at_10": 0.75,
    "minimum_expected_family_hit_at_10": 0.875,
    "maximum_required_family_unsatisfied_rate": 0.125,
}
TAVILY_GATES: dict[str, int] = {
    "required_cases": 8,
    "minimum_succeeded_cases": 7,
    "minimum_contributed_cases": 6,
    "maximum_queries_per_case": 1,
}


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    id: str
    query: str
    profile: SearchProfile
    expected_family: str
    target_domains: tuple[str, ...]
    target_url_prefixes: tuple[str, ...]
    topic: str


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


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
        "target_domains",
        "target_url_prefixes",
        "topic",
    }
    for item in payload:
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("calibration case fields do not match the locked schema")
        case_id = item["id"]
        query = item["query"]
        expected_family = item["expected_family"]
        topic = item["topic"]
        targets = item["target_domains"]
        prefixes = item["target_url_prefixes"]
        try:
            profile = SearchProfile(item["profile"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"case {case_id!r} has an invalid profile") from exc
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError("calibration case IDs must be unique non-empty strings")
        if (
            not isinstance(query, str)
            or not query.strip()
            or query.casefold().strip() in seen_queries
        ):
            raise ValueError("calibration queries must be unique non-empty strings")
        if expected_family not in EXPECTED_FAMILIES or topic not in EXPECTED_TOPICS:
            raise ValueError(f"case {case_id} has an invalid topic or expected family")
        if profile.value != expected_family or topic != expected_family:
            raise ValueError(f"case {case_id} must align profile, topic and required family")
        if (
            not isinstance(targets, list)
            or not targets
            or not all(
                isinstance(target, str)
                and target
                and target == target.strip().lower().rstrip(".")
                and "://" not in target
                and "/" not in target
                for target in targets
            )
        ):
            raise ValueError(f"case {case_id} has invalid target domains")
        if not isinstance(prefixes, list) or not all(
            isinstance(prefix, str) and prefix.startswith("https://") and len(prefix) <= 500
            for prefix in prefixes
        ):
            raise ValueError(f"case {case_id} has invalid target URL prefixes")
        if topic in {"academic", "code", "reference"} and not prefixes:
            raise ValueError(f"case {case_id} requires an exact target URL prefix")
        seen_ids.add(case_id)
        seen_queries.add(query.casefold().strip())
        cases.append(
            CalibrationCase(
                id=case_id,
                query=query.strip(),
                profile=profile,
                expected_family=expected_family,
                target_domains=tuple(targets),
                target_url_prefixes=tuple(prefixes),
                topic=topic,
            )
        )

    topic_distribution = {
        topic: sum(case.topic == topic for case in cases) for topic in EXPECTED_TOPICS
    }
    if len(cases) != 32 or any(count != 8 for count in topic_distribution.values()):
        raise ValueError("locked calibration requires 32 cases, eight per topic")
    ids = [case.id for case in cases]
    return cases, {
        "file": path.name,
        "sha256": sha256_bytes(raw),
        "count": len(cases),
        "ids": ids,
        "manifest_sha256": sha256_bytes("\n".join(ids).encode()),
        "topic_distribution": topic_distribution,
    }


def locked_config_manifest(path: Path, image: str) -> dict[str, str]:
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("SearXNG configuration exceeds one megabyte")
    if "@sha256:" not in image:
        raise ValueError("SearXNG image must include an immutable digest")
    return {
        "file": path.name,
        "sha256": sha256_bytes(raw),
        "image": image,
    }


def validate_locked_inputs(
    suite_manifest: dict[str, Any],
    config_manifest: dict[str, str],
) -> None:
    if suite_manifest["sha256"] != LOCKED_SUITE_SHA256:
        raise ValueError("suite checksum does not match benchmark protocol v5")
    if config_manifest["sha256"] != LOCKED_CONFIG_SHA256:
        raise ValueError("SearXNG checksum does not match benchmark protocol v5")


def validate_arguments(arguments: argparse.Namespace) -> None:
    if arguments.max_results != 10:
        raise ValueError("locked calibration requires exactly 10 results")
    if not math.isclose(arguments.request_timeout, 20.0):
        raise ValueError("locked calibration requires a 20 second request timeout")
    if not math.isclose(arguments.pause_seconds, 0.5):
        raise ValueError("locked calibration requires a 0.5 second pause")


def _target_hit(case: CalibrationCase, hits: list[Any]) -> bool:
    if case.target_url_prefixes:
        prefixes = tuple(prefix.casefold().rstrip("/") for prefix in case.target_url_prefixes)
        return any(
            hit.canonical_url.casefold().rstrip("/").startswith(prefix)
            for hit in hits
            for prefix in prefixes
        )
    return any(domain_matches(hit.domain, list(case.target_domains)) for hit in hits)


async def run_case(
    engine: EvidenceMesh,
    case: CalibrationCase,
    *,
    max_results: int,
) -> dict[str, Any]:
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
        return {
            "case_id": case.id,
            "topic": case.topic,
            "profile": case.profile.value,
            "expected_family": case.expected_family,
            "response_success": False,
            "available": False,
            "target_hit_at_10": False,
            "expected_family_hit_at_10": False,
            "provider_degradation": True,
            "required_family_satisfied": False,
            "required_family_status": "runner_error",
            "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
            "result_count": 0,
            "providers_requested": [],
            "providers_succeeded": [],
            "providers_failed": [],
            "providers_contributed": [],
            "provider_query_counts": {},
            "source_families_contributed": [],
            "degraded_source_families": [],
            "failed_source_families": [],
            "cache_hits": 0,
            "error_type": type(exc).__name__,
        }

    hits = response.results[:max_results]
    metadata = response.metadata
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
        "target_hit_at_10": _target_hit(case, hits),
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
        "cache_hits": metadata.cache_hits,
        "error_type": None,
    }


def aggregate(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(outcome["latency_ms"]) for outcome in outcomes]
    required_satisfied = [bool(outcome["required_family_satisfied"]) for outcome in outcomes]
    return {
        "response_success": rate_metric(
            [bool(outcome["response_success"]) for outcome in outcomes]
        ),
        "availability": rate_metric([bool(outcome["available"]) for outcome in outcomes]),
        "target_hit_at_10": rate_metric(
            [bool(outcome["target_hit_at_10"]) for outcome in outcomes]
        ),
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


def contribution_metrics(
    outcomes: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    provider_names = sorted(
        {
            provider
            for outcome in outcomes
            for field in (
                "providers_requested",
                "providers_succeeded",
                "providers_contributed",
            )
            for provider in outcome[field]
        }
    )
    providers = {
        provider: {
            "requested_cases": sum(
                provider in outcome["providers_requested"] for outcome in outcomes
            ),
            "succeeded_cases": sum(
                provider in outcome["providers_succeeded"] for outcome in outcomes
            ),
            "contributed_cases": sum(
                provider in outcome["providers_contributed"] for outcome in outcomes
            ),
        }
        for provider in provider_names
    }
    families = {
        family: sum(family in outcome["source_families_contributed"] for outcome in outcomes)
        for family in sorted(EXPECTED_FAMILIES)
    }
    return providers, families


def gate_decision(
    overall: dict[str, Any],
    by_topic: dict[str, dict[str, Any]],
    providers: dict[str, dict[str, int]],
    families: dict[str, int],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    contributing_provider_count = sum(
        metrics["contributed_cases"] > 0 for metrics in providers.values()
    )
    contributing_family_count = sum(count > 0 for count in families.values())
    overall_checks = {
        "availability_rate": (
            overall["availability"]["rate"] >= OVERALL_GATES["minimum_availability_rate"]
        ),
        "target_hit_at_10": (
            overall["target_hit_at_10"]["rate"] >= OVERALL_GATES["minimum_target_hit_at_10"]
        ),
        "expected_family_hit_at_10": (
            overall["expected_family_hit_at_10"]["rate"]
            >= OVERALL_GATES["minimum_expected_family_hit_at_10"]
        ),
        "provider_degradation_rate": (
            overall["provider_degradation"]["rate"]
            <= OVERALL_GATES["maximum_provider_degradation_rate"]
        ),
        "required_family_unsatisfied_rate": (
            overall["required_family_unsatisfied"]["rate"]
            <= OVERALL_GATES["maximum_required_family_unsatisfied_rate"]
        ),
        "p95_latency_ms": (overall["latency_ms"]["p95"] <= OVERALL_GATES["maximum_p95_latency_ms"]),
        "contributing_providers": (
            contributing_provider_count >= OVERALL_GATES["minimum_contributing_providers"]
        ),
        "contributing_source_families": (
            contributing_family_count >= OVERALL_GATES["minimum_contributing_source_families"]
        ),
    }
    topic_checks = {
        topic: {
            "availability_rate": (
                metrics["availability"]["rate"] >= TOPIC_GATES["minimum_availability_rate"]
            ),
            "target_hit_at_10": (
                metrics["target_hit_at_10"]["rate"] >= TOPIC_GATES["minimum_target_hit_at_10"]
            ),
            "expected_family_hit_at_10": (
                metrics["expected_family_hit_at_10"]["rate"]
                >= TOPIC_GATES["minimum_expected_family_hit_at_10"]
            ),
            "required_family_unsatisfied_rate": (
                metrics["required_family_unsatisfied"]["rate"]
                <= TOPIC_GATES["maximum_required_family_unsatisfied_rate"]
            ),
        }
        for topic, metrics in by_topic.items()
    }
    tavily = providers.get(
        "tavily",
        {"requested_cases": 0, "succeeded_cases": 0, "contributed_cases": 0},
    )
    tavily_query_budget_ok = all(
        int(outcome["provider_query_counts"].get("tavily", 0))
        <= TAVILY_GATES["maximum_queries_per_case"]
        for outcome in outcomes
    )
    tavily_checks = {
        "requested_cases": tavily["requested_cases"] == TAVILY_GATES["required_cases"],
        "succeeded_cases": (tavily["succeeded_cases"] >= TAVILY_GATES["minimum_succeeded_cases"]),
        "contributed_cases": (
            tavily["contributed_cases"] >= TAVILY_GATES["minimum_contributed_cases"]
        ),
        "query_budget": tavily_query_budget_ok,
    }
    functional_pass = (
        all(overall_checks.values())
        and all(all(checks.values()) for checks in topic_checks.values())
        and all(tavily_checks.values())
    )
    return {
        "thresholds": {
            "overall": OVERALL_GATES,
            "per_topic": TOPIC_GATES,
            "tavily": TAVILY_GATES,
        },
        "checks": {
            "overall": overall_checks,
            "per_topic": topic_checks,
            "tavily": tavily_checks,
        },
        "contributing_provider_count": contributing_provider_count,
        "contributing_source_family_count": contributing_family_count,
        "functional_gate_passed": functional_pass,
        "cross_network_gate": {
            "required_independent_networks": 2,
            "observed_independent_networks": 1,
            "status": "not_testable",
            "passed": False,
        },
        "independent_network_replication_required": True,
        "stage_b_200_case_run_allowed": False,
        "release_ready": False,
        "release_decision": "no-go",
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
    async with EvidenceMesh(settings) as engine:
        for index, case in enumerate(cases):
            outcome = await run_case(engine, case, max_results=max_results)
            outcomes.append(outcome)
            if progress:
                print(
                    f"[{index + 1:02d}/{len(cases):02d}] {case.id}: "
                    f"available={outcome['available']} "
                    f"target={outcome['target_hit_at_10']} "
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
        default=Path("benchmarks/data/quality_calibration_v2.json"),
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
        raise ValueError("TAVILY_API_KEY is required for the locked Phase 7 calibration")
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
        "schema_version": 2,
        "benchmark": "evidencemesh-quality-calibration-v2",
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
            "anonymous_github_repository_search": True,
            "other_keyed_providers_enabled": False,
        },
        "protocol": {
            "version": 5,
            "max_results": arguments.max_results,
            "request_timeout_seconds": arguments.request_timeout,
            "pause_seconds": arguments.pause_seconds,
            "request_count": len(cases),
            "maximum_tavily_requests": 8,
            "maximum_tavily_credits": 8,
            "retry_policy": "none",
            "content_fetching": False,
            "query_variants": False,
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
