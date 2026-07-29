"""Run the privacy-safe, non-scored Phase 11.3 Mwmbl network diagnostic."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import sys
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from evidencemesh.config import DeploymentProfile, Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import SearchProfile, SearchRequest

DIAGNOSTIC_NAME = "evidencemesh-phase11-3-network-observability-v1"
MWMBL_ENDPOINT = "https://api.mwmbl.org/api/v2/search/"
PROBES = (
    ("probe-01", "open source search engine"),
    ("probe-02", "python async http client"),
    ("probe-03", "model context protocol"),
    ("probe-04", "web accessibility standards"),
)
EXPECTED_PROBE_COUNT = 4
PROTOCOL_PATH = Path("docs/benchmark-protocol-v12.md")
PROTOCOL_SHA256 = "d5d4b4e066e2010d3e420e91dfa4a11202eeb98d61174c5c7de965e7f7eff764"


def package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not-installed"


def _sum_telemetry(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    numeric_fields = (
        "logical_calls",
        "cache_hits",
        "circuit_skips",
        "adapter_invocations",
        "http_attempts",
        "http_responses",
        "http_failures_without_response",
    )
    totals = {
        field: sum(int(observation["network_telemetry"][field]) for observation in observations)
        for field in numeric_fields
    }
    status_counts: Counter[str] = Counter()
    failure_kind_counts: Counter[str] = Counter()
    adapter_latencies: list[float] = []
    http_latencies: list[float] = []
    for observation in observations:
        telemetry = observation["network_telemetry"]
        status_counts.update(telemetry["http_status_counts"])
        failure_kind_counts.update(observation["failure_kind_counts"])
        adapter_latencies.extend(telemetry["adapter_latency_ms"])
        http_latencies.extend(telemetry["http_attempt_latency_ms"])
    totals.update(
        {
            "http_status_counts": dict(sorted(status_counts.items())),
            "failure_kind_counts": dict(sorted(failure_kind_counts.items())),
            "adapter_latency_ms": adapter_latencies,
            "http_attempt_latency_ms": http_latencies,
            "unaccounted_before_adapter": max(
                0,
                totals["logical_calls"]
                - totals["cache_hits"]
                - totals["circuit_skips"]
                - totals["adapter_invocations"],
            ),
        }
    )
    return totals


def _diagnosis(traffic: dict[str, Any], result_cases: int) -> str:
    failure_kinds = set(traffic["failure_kind_counts"])
    if result_cases:
        return "public_endpoint_returned_results"
    if "invalid_schema" in failure_kinds:
        return "response_schema_failure"
    if "invalid_json" in failure_kinds:
        return "response_json_failure"
    if "http_status" in failure_kinds:
        return "http_status_failure"
    if "dns_error" in failure_kinds:
        return "dns_resolution_failure"
    if "connection_error" in failure_kinds:
        return "connection_failure"
    if "timeout" in failure_kinds:
        return "timeout_failure"
    if traffic["http_attempts"] == 0 and traffic["circuit_skips"]:
        return "circuit_open_without_new_network_attempt"
    return "inconclusive_provider_failure"


async def run(arguments: argparse.Namespace) -> dict[str, Any]:
    protocol_bytes = await asyncio.to_thread(PROTOCOL_PATH.read_bytes)
    protocol_sha256 = hashlib.sha256(protocol_bytes).hexdigest()
    if protocol_sha256 != PROTOCOL_SHA256:
        raise ValueError("Phase 11.3 protocol checksum does not match the lock")
    cache_root = Path(arguments.cache_root)
    await asyncio.to_thread(cache_root.mkdir, parents=True, exist_ok=True)
    settings = Settings(
        deployment_profile=DeploymentProfile.COMMUNITY,
        enabled_providers=["mwmbl"],
        mwmbl_url=arguments.mwmbl_url,
        cache_path=cache_root / "phase11-3.sqlite3",
        request_timeout_seconds=arguments.request_timeout_seconds,
        provider_failure_threshold=arguments.failure_threshold,
        provider_recovery_seconds=arguments.recovery_seconds,
        respect_robots_txt=False,
    )
    engine = EvidenceMesh(settings)
    observations: list[dict[str, Any]] = []
    started_at = datetime.now(UTC)
    try:
        for index, (probe_id, query) in enumerate(PROBES, start=1):
            if index > 1:
                await asyncio.sleep(arguments.pause_seconds)
            async with asyncio.timeout(arguments.wall_time_seconds):
                response = await engine.search(
                    SearchRequest(
                        query=query,
                        limit=arguments.max_results,
                        profile=SearchProfile.WEB,
                        fetch_content=False,
                        use_cache=False,
                    )
                )
            telemetry = response.metadata.provider_network_telemetry["mwmbl"]
            circuit = engine.health()["providers"][0]["circuit"]
            observations.append(
                {
                    "probe_id": probe_id,
                    "result_count": len(response.results),
                    "failure_kind_counts": (
                        response.metadata.provider_failure_kind_counts.get("mwmbl", {})
                    ),
                    "network_telemetry": telemetry.model_dump(mode="json"),
                    "circuit_after": {
                        "status": circuit["status"],
                        "consecutive_failures": circuit["consecutive_failures"],
                        "probe_in_flight": circuit["probe_in_flight"],
                    },
                }
            )
            if arguments.progress:
                print(
                    f"[{index}/{EXPECTED_PROBE_COUNT}] {probe_id}: "
                    f"{len(response.results)} result(s)",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        await engine.aclose()

    traffic = _sum_telemetry(observations)
    result_cases = sum(int(observation["result_count"] > 0) for observation in observations)
    return {
        "schema_version": 1,
        "diagnostic": DIAGNOSTIC_NAME,
        "scored": False,
        "protocol": {
            "document_path": str(PROTOCOL_PATH),
            "sha256": protocol_sha256,
            "fixed_public_probe_count": EXPECTED_PROBE_COUNT,
            "queries_disclosed_in_report": False,
            "targets_defined": False,
            "quality_metrics_computed": False,
            "cache": False,
            "retry_policy": "none",
            "max_results": arguments.max_results,
            "request_timeout_seconds": arguments.request_timeout_seconds,
            "wall_time_seconds": arguments.wall_time_seconds,
            "minimum_pause_seconds": 1.1,
            "failure_threshold": arguments.failure_threshold,
            "recovery_seconds": arguments.recovery_seconds,
            "provider": "mwmbl",
            "provider_default_enabled": False,
            "http_attempt_definition": (
                "shared httpx request dispatch; latency ends at response headers "
                "or transport exception"
            ),
        },
        "environment": {
            "commit_sha": os.getenv("EVIDENCEMESH_DIAGNOSTIC_COMMIT", "unknown"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "network_region": arguments.network_region,
            "dependency_versions": {
                "httpx": package_version("httpx"),
                "pydantic": package_version("pydantic"),
            },
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
        },
        "traffic": {
            **traffic,
            "maximum_logical_calls": EXPECTED_PROBE_COUNT,
            "maximum_adapter_invocations": EXPECTED_PROBE_COUNT,
            "maximum_http_attempts": EXPECTED_PROBE_COUNT,
            "paid_provider_requests": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
        },
        "observations": observations,
        "diagnosis": {
            "result_cases": result_cases,
            "failure_cases": EXPECTED_PROBE_COUNT - result_cases,
            "classification": _diagnosis(traffic, result_cases),
        },
        "decision": {
            "retrieval_candidate_evaluated": False,
            "quality_claim_allowed": False,
            "default_bundle_eligible": False,
            "phase12_untouched_evaluation_allowed": False,
            "release_ready": False,
            "release_decision": "no-go",
        },
        "privacy": {
            "queries_in_report": False,
            "target_domains_in_report": False,
            "source_titles_or_urls_in_report": False,
            "source_snippets_in_report": False,
            "response_bodies_in_report": False,
            "exception_messages_in_report": False,
            "credentials_in_report": False,
            "sanitized_failure_classes_in_report": True,
            "http_status_codes_in_report": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mwmbl-url", default=MWMBL_ENDPOINT)
    parser.add_argument("--cache-root", default=".phase11-3-cache")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--request-timeout-seconds", type=float, default=15.0)
    parser.add_argument("--wall-time-seconds", type=float, default=20.0)
    parser.add_argument("--pause-seconds", type=float, default=1.1)
    parser.add_argument("--failure-threshold", type=int, default=3)
    parser.add_argument("--recovery-seconds", type=float, default=300.0)
    parser.add_argument("--network-region", default="not reported")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    if arguments.mwmbl_url != MWMBL_ENDPOINT:
        parser.error(f"the locked Phase 11.3 protocol requires --mwmbl-url {MWMBL_ENDPOINT}")
    if arguments.max_results != 10:
        parser.error("the locked Phase 11.3 protocol requires --max-results 10")
    if arguments.request_timeout_seconds != 15.0:
        parser.error("the locked Phase 11.3 protocol requires --request-timeout-seconds 15")
    if arguments.wall_time_seconds != 20.0:
        parser.error("the locked Phase 11.3 protocol requires --wall-time-seconds 20")
    if arguments.pause_seconds < 1.1:
        parser.error("the locked Phase 11.3 protocol requires --pause-seconds >= 1.1")
    if arguments.failure_threshold != 3:
        parser.error("the locked Phase 11.3 protocol requires --failure-threshold 3")
    if arguments.recovery_seconds != 300.0:
        parser.error("the locked Phase 11.3 protocol requires --recovery-seconds 300")
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
