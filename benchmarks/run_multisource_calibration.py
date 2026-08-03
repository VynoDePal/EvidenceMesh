#!/usr/bin/env python3
"""Run the locked Phase 6 low-traffic multi-source calibration."""

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
from evidencemesh.models import SearchProfile, SearchRequest
from evidencemesh.urls import domain_matches

LOCKED_SUITE_SHA256 = "e99e584cb115a3bb343d052b368e127acd924be7a6aabef98ae90c3c86acce34"
LOCKED_CONFIG_SHA256 = "26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645"
EXPECTED_TOPICS = ("academic", "code", "reference", "web")
EXPECTED_FAMILIES = frozenset({"academic", "code", "reference", "web"})
COMMUNITY_PROVIDERS = ("searxng", "wikipedia", "crossref", "arxiv", "github")
MAX_INPUT_BYTES = 1_000_000
GATES: dict[str, float | int] = {
    "minimum_availability_rate": 0.90,
    "minimum_target_domain_hit_at_10": 0.75,
    "minimum_expected_family_hit_at_10": 0.80,
    "maximum_partial_failure_rate": 0.25,
    "maximum_p95_latency_ms": 15_000.0,
    "minimum_contributing_providers": 4,
    "minimum_contributing_source_families": 4,
}


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    id: str
    query: str
    profile: SearchProfile
    expected_family: str
    target_domains: tuple[str, ...]
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
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("every calibration case must be an object")
        expected_keys = {
            "id",
            "query",
            "profile",
            "expected_family",
            "target_domains",
            "topic",
        }
        if set(item) != expected_keys:
            raise ValueError("calibration case fields do not match the locked schema")
        case_id = item["id"]
        query = item["query"]
        targets = item["target_domains"]
        expected_family = item["expected_family"]
        topic = item["topic"]
        try:
            profile = SearchProfile(item["profile"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"case {case_id!r} has an invalid profile") from exc
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError("calibration case IDs must be unique non-empty strings")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"case {case_id} has no query")
        if expected_family not in EXPECTED_FAMILIES:
            raise ValueError(f"case {case_id} has an invalid expected family")
        if topic not in EXPECTED_TOPICS:
            raise ValueError(f"case {case_id} has an invalid topic")
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
        seen_ids.add(case_id)
        cases.append(
            CalibrationCase(
                id=case_id,
                query=query.strip(),
                profile=profile,
                expected_family=expected_family,
                target_domains=tuple(targets),
                topic=topic,
            )
        )

    topic_distribution = {
        topic: sum(case.topic == topic for case in cases) for topic in EXPECTED_TOPICS
    }
    if len(cases) != 24 or any(count != 6 for count in topic_distribution.values()):
        raise ValueError("locked calibration requires 24 cases, six per topic")
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
        raise ValueError("suite checksum does not match benchmark protocol v4")
    if config_manifest["sha256"] != LOCKED_CONFIG_SHA256:
        raise ValueError("SearXNG checksum does not match benchmark protocol v4")


def validate_arguments(arguments: argparse.Namespace) -> None:
    if arguments.max_results != 10:
        raise ValueError("locked calibration requires exactly 10 results")
    if not math.isclose(arguments.request_timeout, 20.0):
        raise ValueError("locked calibration requires a 20 second request timeout")
    if not math.isclose(arguments.pause_seconds, 0.5):
        raise ValueError("locked calibration requires a 0.5 second pause")


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
    except Exception as exc:  # The report records type only and continues the suite.
        return {
            "case_id": case.id,
            "topic": case.topic,
            "profile": case.profile.value,
            "expected_family": case.expected_family,
            "target_domains": list(case.target_domains),
            "response_success": False,
            "available": False,
            "target_domain_hit_at_10": False,
            "expected_family_hit_at_10": False,
            "partial_failure": True,
            "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
            "result_count": 0,
            "providers_requested": [],
            "providers_succeeded": [],
            "providers_failed": [],
            "providers_contributed": [],
            "source_families_contributed": [],
            "cache_hits": 0,
            "error_type": type(exc).__name__,
        }

    hits = response.results[:max_results]
    providers_contributed = sorted({provider for hit in hits for provider in hit.providers})
    families_contributed = sorted({hit.source_type.value for hit in hits})
    failed_providers = sorted({key.split(":", 1)[0] for key in response.metadata.provider_failures})
    return {
        "case_id": case.id,
        "topic": case.topic,
        "profile": case.profile.value,
        "expected_family": case.expected_family,
        "target_domains": list(case.target_domains),
        "response_success": True,
        "available": bool(hits),
        "target_domain_hit_at_10": any(
            domain_matches(hit.domain, list(case.target_domains)) for hit in hits
        ),
        "expected_family_hit_at_10": any(
            hit.source_type.value == case.expected_family for hit in hits
        ),
        "partial_failure": bool(response.metadata.provider_failures),
        "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
        "result_count": len(hits),
        "providers_requested": response.metadata.providers_requested,
        "providers_succeeded": response.metadata.providers_succeeded,
        "providers_failed": failed_providers,
        "providers_contributed": providers_contributed,
        "source_families_contributed": families_contributed,
        "cache_hits": response.metadata.cache_hits,
        "error_type": None,
    }


def aggregate(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(outcome["latency_ms"]) for outcome in outcomes]
    metrics: dict[str, Any] = {
        "response_success": rate_metric(
            [bool(outcome["response_success"]) for outcome in outcomes]
        ),
        "availability": rate_metric([bool(outcome["available"]) for outcome in outcomes]),
        "target_domain_hit_at_10": rate_metric(
            [bool(outcome["target_domain_hit_at_10"]) for outcome in outcomes]
        ),
        "expected_family_hit_at_10": rate_metric(
            [bool(outcome["expected_family_hit_at_10"]) for outcome in outcomes]
        ),
        "partial_failure": rate_metric([bool(outcome["partial_failure"]) for outcome in outcomes]),
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
    return metrics


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
    providers: dict[str, dict[str, int]],
    families: dict[str, int],
) -> dict[str, Any]:
    contributing_provider_count = sum(
        metrics["contributed_cases"] > 0 for metrics in providers.values()
    )
    contributing_family_count = sum(count > 0 for count in families.values())
    checks = {
        "availability_rate": (
            overall["availability"]["rate"] >= GATES["minimum_availability_rate"]
        ),
        "target_domain_hit_at_10": (
            overall["target_domain_hit_at_10"]["rate"] >= GATES["minimum_target_domain_hit_at_10"]
        ),
        "expected_family_hit_at_10": (
            overall["expected_family_hit_at_10"]["rate"]
            >= GATES["minimum_expected_family_hit_at_10"]
        ),
        "partial_failure_rate": (
            overall["partial_failure"]["rate"] <= GATES["maximum_partial_failure_rate"]
        ),
        "p95_latency_ms": (overall["latency_ms"]["p95"] <= GATES["maximum_p95_latency_ms"]),
        "contributing_providers": (
            contributing_provider_count >= GATES["minimum_contributing_providers"]
        ),
        "contributing_source_families": (
            contributing_family_count >= GATES["minimum_contributing_source_families"]
        ),
    }
    functional_pass = all(checks.values())
    return {
        "thresholds": GATES,
        "checks": checks,
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
                    f"target={outcome['target_domain_hit_at_10']}",
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
        default=Path("benchmarks/data/multisource_calibration_v1.json"),
    )
    parser.add_argument(
        "--searxng-config",
        type=Path,
        default=Path("docker/searxng/community-calibration-settings.yml"),
    )
    parser.add_argument("--searxng-image", required=True)
    parser.add_argument("--searxng-url", default="http://127.0.0.1:8890")
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
    cases, suite_manifest = load_suite(arguments.suite)
    config_manifest = locked_config_manifest(
        arguments.searxng_config,
        arguments.searxng_image,
    )
    validate_locked_inputs(suite_manifest, config_manifest)
    settings = Settings(
        deployment_profile=DeploymentProfile.COMMUNITY,
        enabled_providers=list(COMMUNITY_PROVIDERS),
        searxng_url=arguments.searxng_url,
        cache_path=arguments.cache_path,
        request_timeout_seconds=arguments.request_timeout,
        max_concurrency=5,
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
    decision = gate_decision(overall, providers, families)
    return {
        "schema_version": 1,
        "benchmark": "evidencemesh-multisource-calibration-v1",
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
            "deployment_profile": DeploymentProfile.COMMUNITY.value,
            "providers": list(COMMUNITY_PROVIDERS),
            "searxng": config_manifest,
            "anonymous_github_repository_search": True,
            "openalex_enabled": False,
        },
        "protocol": {
            "version": 4,
            "max_results": arguments.max_results,
            "request_timeout_seconds": arguments.request_timeout,
            "pause_seconds": arguments.pause_seconds,
            "request_count": len(cases),
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
