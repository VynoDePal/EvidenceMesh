#!/usr/bin/env python3
"""Low-traffic, per-engine SearXNG reliability calibration.

The suite uses authored public queries, never SimpleQA questions. Each engine is
called exactly once per case with no retry. Public outcomes contain case IDs,
domains and telemetry, not query or result text.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

try:
    from benchmarks.run_live_retrieval import percentile, rate_metric, sha256_bytes
except ModuleNotFoundError:
    from run_live_retrieval import percentile, rate_metric, sha256_bytes
from evidencemesh.providers.base import bounded_json_request

DEFAULT_ENGINES = (
    "brave",
    "duckduckgo",
    "startpage",
    "qwant",
    "mojeek",
    "wiby",
    "mwmbl",
    "yep",
)
MAX_RESPONSE_BYTES = 5_000_000
MAX_CONFIG_BYTES = 1_000_000
SELECTION_GATES: dict[str, float] = {
    "minimum_response_success_rate": 0.90,
    "minimum_availability_rate": 0.80,
    "minimum_target_domain_hit_at_10": 0.50,
    "maximum_unresponsive_rate": 0.20,
    "maximum_p95_latency_ms": 10_000.0,
    "minimum_engine_isolation_rate": 1.0,
}


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    id: str
    query: str
    target_domains: tuple[str, ...]
    topic: str


def normalise_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    return domain[4:] if domain.startswith("www.") else domain


def domain_from_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return normalise_domain(parsed.hostname)


def domain_matches(candidate: str, target: str) -> bool:
    return candidate == target or candidate.endswith(f".{target}")


def load_suite(path: Path) -> tuple[list[CalibrationCase], dict[str, Any]]:
    raw = path.read_bytes()
    if len(raw) > MAX_CONFIG_BYTES:
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
        case_id = item.get("id")
        query = item.get("query")
        targets = item.get("target_domains")
        topic = item.get("topic")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError("calibration case IDs must be unique non-empty strings")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"case {case_id} has no query")
        if (
            not isinstance(targets, list)
            or not targets
            or not all(
                isinstance(target, str)
                and bool(target)
                and target == normalise_domain(target)
                and "/" not in target
                for target in targets
            )
        ):
            raise ValueError(f"case {case_id} has invalid target domains")
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError(f"case {case_id} has no topic")
        seen_ids.add(case_id)
        cases.append(
            CalibrationCase(
                id=case_id,
                query=query.strip(),
                target_domains=tuple(targets),
                topic=topic.strip(),
            )
        )
    ids = [case.id for case in cases]
    return cases, {
        "file": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "count": len(cases),
        "ids": ids,
        "manifest_sha256": sha256_bytes("\n".join(ids).encode("utf-8")),
        "topic_distribution": {
            topic: sum(case.topic == topic for case in cases)
            for topic in sorted({case.topic for case in cases})
        },
    }


def validate_base_url(value: str) -> str:
    try:
        parsed = httpx.URL(value)
    except httpx.InvalidURL as exc:
        raise ValueError("SearXNG base URL is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "SearXNG base URL must be HTTP(S), include a host, and omit credentials/query/fragment"
        )
    return str(parsed).rstrip("/")


def parse_unresponsive(payload: dict[str, Any]) -> list[str]:
    values = payload.get("unresponsive_engines", [])
    if not isinstance(values, list):
        return []
    return sorted(
        {
            value[0].strip()
            for value in values
            if isinstance(value, list) and value and isinstance(value[0], str) and value[0].strip()
        }
    )


def ranked_domains(payload: dict[str, Any], *, max_results: int) -> list[str]:
    values = payload.get("results", [])
    if not isinstance(values, list):
        raise ValueError("SearXNG response has an invalid results field")
    domains: list[str] = []
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("url"), str):
            continue
        if domain := domain_from_url(value["url"]):
            domains.append(domain)
        if len(domains) >= max_results:
            break
    return domains


def observed_result_engines(payload: dict[str, Any], *, max_results: int) -> list[str]:
    values = payload.get("results", [])
    if not isinstance(values, list):
        raise ValueError("SearXNG response has an invalid results field")
    observed: set[str] = set()
    accepted_results = 0
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("url"), str):
            continue
        if domain_from_url(value["url"]) is None:
            continue
        engine_values = value.get("engines", [])
        if isinstance(engine_values, list):
            observed.update(
                engine.strip()
                for engine in engine_values
                if isinstance(engine, str) and engine.strip()
            )
        elif isinstance(value.get("engine"), str) and value["engine"].strip():
            observed.add(value["engine"].strip())
        accepted_results += 1
        if accepted_results >= max_results:
            break
    return sorted(observed)


def first_target_rank(domains: list[str], targets: tuple[str, ...]) -> int | None:
    for rank, domain in enumerate(domains, start=1):
        if any(domain_matches(domain, target) for target in targets):
            return rank
    return None


async def calibrate_request(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    case: CalibrationCase,
    engine: str,
    language: str,
    max_results: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = await bounded_json_request(
            client,
            "GET",
            f"{base_url}/search",
            max_bytes=MAX_RESPONSE_BYTES,
            params={
                "q": case.query,
                "format": "json",
                "engines": engine,
                "language": language,
                "safesearch": 1,
            },
        )
        domains = ranked_domains(payload, max_results=max_results)
        observed_engines = observed_result_engines(payload, max_results=max_results)
        unexpected_engines = sorted(set(observed_engines) - {engine})
        unresponsive = parse_unresponsive(payload)
        error_kind = None
    except (httpx.HTTPError, ValueError) as exc:
        domains = []
        observed_engines = []
        unexpected_engines = []
        unresponsive = []
        error_kind = type(exc).__name__
    return {
        "id": case.id,
        "engine": engine,
        "response_ok": error_kind is None,
        "available": bool(domains),
        "result_count": len(domains),
        "unique_domains": len(set(domains)),
        "target_domain_rank": first_target_rank(domains, case.target_domains),
        "observed_result_engines": observed_engines,
        "unexpected_result_engines": unexpected_engines,
        "engine_isolation_ok": error_kind is None and not unexpected_engines,
        "unresponsive_engines": unresponsive,
        "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
        "error_kind": error_kind,
    }


def scheduled_pairs(
    cases: list[CalibrationCase], engines: tuple[str, ...]
) -> list[tuple[CalibrationCase, str]]:
    return [
        (case, engines[(case_index + offset) % len(engines)])
        for case_index, case in enumerate(cases)
        for offset in range(len(engines))
    ]


def engine_metrics(
    outcomes: list[dict[str, Any]], *, engines: tuple[str, ...], max_results: int
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for engine in engines:
        values = [outcome for outcome in outcomes if outcome["engine"] == engine]
        response_values = [bool(outcome["response_ok"]) for outcome in values]
        availability_values = [bool(outcome["available"]) for outcome in values]
        target_values = [
            outcome["target_domain_rank"] is not None
            and int(outcome["target_domain_rank"]) <= max_results
            for outcome in values
        ]
        unresponsive_values = [engine in set(outcome["unresponsive_engines"]) for outcome in values]
        isolation_values = [bool(outcome["engine_isolation_ok"]) for outcome in values]
        latencies = [float(outcome["latency_ms"]) for outcome in values]
        response_rate = rate_metric(response_values)
        availability_rate = rate_metric(availability_values)
        target_rate = rate_metric(target_values)
        unresponsive_rate = rate_metric(unresponsive_values)
        isolation_rate = rate_metric(isolation_values)
        p95 = percentile(latencies, 0.95)
        failed_gates: list[str] = []
        if (response_rate["rate"] or 0.0) < SELECTION_GATES["minimum_response_success_rate"]:
            failed_gates.append("response_success_rate")
        if (availability_rate["rate"] or 0.0) < SELECTION_GATES["minimum_availability_rate"]:
            failed_gates.append("availability_rate")
        if (target_rate["rate"] or 0.0) < SELECTION_GATES["minimum_target_domain_hit_at_10"]:
            failed_gates.append("target_domain_hit_at_10")
        if (unresponsive_rate["rate"] or 0.0) > SELECTION_GATES["maximum_unresponsive_rate"]:
            failed_gates.append("unresponsive_rate")
        if p95 > SELECTION_GATES["maximum_p95_latency_ms"]:
            failed_gates.append("p95_latency_ms")
        if (isolation_rate["rate"] or 0.0) < SELECTION_GATES["minimum_engine_isolation_rate"]:
            failed_gates.append("engine_isolation_rate")
        metrics[engine] = {
            "request_count": len(values),
            "response_success": response_rate,
            "availability": availability_rate,
            f"target_domain_hit_at_{max_results}": target_rate,
            "unresponsive": unresponsive_rate,
            "engine_isolation": isolation_rate,
            "mean_result_count": (
                round(statistics.fmean(int(value["result_count"]) for value in values), 3)
                if values
                else 0.0
            ),
            "mean_unique_domains": (
                round(statistics.fmean(int(value["unique_domains"]) for value in values), 3)
                if values
                else 0.0
            ),
            "latency_ms": {
                "p50": percentile(latencies, 0.50),
                "p95": p95,
            },
            "error_kinds": {
                kind: sum(value["error_kind"] == kind for value in values)
                for kind in sorted(
                    {
                        str(value["error_kind"])
                        for value in values
                        if value["error_kind"] is not None
                    }
                )
            },
            "eligible": not failed_gates,
            "failed_gates": failed_gates,
        }
    return metrics


def rank_eligible_engines(metrics: dict[str, dict[str, Any]]) -> list[str]:
    eligible = [engine for engine, values in metrics.items() if values["eligible"]]
    return sorted(
        eligible,
        key=lambda engine: (
            -float(metrics[engine]["target_domain_hit_at_10"]["rate"] or 0.0),
            -float(metrics[engine]["availability"]["rate"] or 0.0),
            float(metrics[engine]["unresponsive"]["rate"] or 0.0),
            float(metrics[engine]["latency_ms"]["p95"]),
            engine,
        ),
    )


def config_manifest(path: Path, image: str) -> dict[str, str]:
    raw = path.read_bytes()
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("SearXNG configuration exceeds one megabyte")
    if "@sha256:" not in image:
        raise ValueError("SearXNG image must include an immutable digest")
    return {
        "config_file": path.name,
        "config_sha256": hashlib.sha256(raw).hexdigest(),
        "image": image,
    }


async def run_calibration(
    cases: list[CalibrationCase],
    *,
    engines: tuple[str, ...],
    base_url: str,
    language: str,
    max_results: int,
    request_timeout: float,
    pause_seconds: float,
    progress: bool,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(request_timeout),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "EvidenceMesh-Calibration/1.0"},
    ) as client:
        pairs = scheduled_pairs(cases, engines)
        for index, (case, engine) in enumerate(pairs):
            outcome = await calibrate_request(
                client,
                base_url=base_url,
                case=case,
                engine=engine,
                language=language,
                max_results=max_results,
            )
            outcomes.append(outcome)
            if progress:
                print(
                    f"[{case.id}/{engine}] response={outcome['response_ok']} "
                    f"results={outcome['result_count']}",
                    file=sys.stderr,
                    flush=True,
                )
            if pause_seconds and index + 1 < len(pairs):
                await asyncio.sleep(pause_seconds)
    return outcomes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8889")
    parser.add_argument("--engine", action="append", dest="engines")
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--request-timeout", type=float, default=12.0)
    parser.add_argument("--pause-seconds", type=float, default=0.25)
    parser.add_argument("--provider-config", type=Path, required=True)
    parser.add_argument("--provider-image", required=True)
    parser.add_argument(
        "--network-region",
        default="not exposed by execution environment",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--progress", action="store_true")
    return parser


def validate_arguments(arguments: argparse.Namespace) -> tuple[str, tuple[str, ...]]:
    if arguments.max_results != 10:
        raise ValueError("the locked calibration protocol requires exactly 10 results")
    if not 1 <= arguments.request_timeout <= 60:
        raise ValueError("request timeout must be between 1 and 60 seconds")
    if not 0 <= arguments.pause_seconds <= 10:
        raise ValueError("pause must be between 0 and 10 seconds")
    engines = tuple(arguments.engines or DEFAULT_ENGINES)
    if not engines or len(set(engines)) != len(engines):
        raise ValueError("engines must be unique")
    if any(not engine.strip() or engine != engine.strip() for engine in engines):
        raise ValueError("engine names must be non-empty and trimmed")
    return validate_base_url(arguments.base_url), engines


def main() -> None:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        base_url, engines = validate_arguments(arguments)
        cases, suite = load_suite(arguments.suite)
        provider = config_manifest(arguments.provider_config, arguments.provider_image)
        started_at = datetime.now(UTC)
        outcomes = asyncio.run(
            run_calibration(
                cases,
                engines=engines,
                base_url=base_url,
                language=arguments.language,
                max_results=arguments.max_results,
                request_timeout=arguments.request_timeout,
                pause_seconds=arguments.pause_seconds,
                progress=arguments.progress,
            )
        )
        metrics = engine_metrics(outcomes, engines=engines, max_results=arguments.max_results)
        eligible = rank_eligible_engines(metrics)
        report = {
            "schema_version": 1,
            "benchmark": "searxng-engine-calibration-v1",
            "task_type": "provider_selection",
            "suite": suite,
            "protocol": {
                "engines": list(engines),
                "ordering": "query-major deterministic rotation",
                "request_count": len(cases) * len(engines),
                "request_timeout_seconds": arguments.request_timeout,
                "pause_seconds": arguments.pause_seconds,
                "language": arguments.language,
                "safe_search": 1,
                "max_results": arguments.max_results,
                "retry_policy": "none",
                "engine_selection": (
                    "engines parameter only; categories omitted because SearXNG unions "
                    "explicit engines with category engines"
                ),
                "selection_gates": SELECTION_GATES,
            },
            "provider": provider,
            "environment": {
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "commit_sha": os.getenv("EVIDENCEMESH_BENCHMARK_COMMIT") or os.getenv("GITHUB_SHA"),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "network_region": arguments.network_region,
            },
            "metrics": metrics,
            "selection": {
                "eligible_engines": eligible,
                "eligible_count": len(eligible),
                "full_200_case_run_allowed": len(eligible) >= 2,
                "promotion_limit": 3,
                "promoted_engines": eligible[:3] if len(eligible) >= 2 else [],
                "ranking": (
                    "target hit descending, availability descending, unresponsive rate "
                    "ascending, p95 ascending, engine name ascending"
                ),
            },
            "outcomes": outcomes,
            "warnings": [
                (
                    "This small authored suite selects reliable engine candidates; it is not "
                    "a general search-quality leaderboard."
                ),
                (
                    "A 200-case SimpleQA run is allowed only when at least two engines pass "
                    "every pre-registered gate."
                ),
                (
                    "Live engine behavior depends on date and network egress. Results do not "
                    "generalize to every SearXNG deployment."
                ),
            ],
        }
    except (OSError, ValueError, httpx.HTTPError) as exc:
        parser.error(str(exc))

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
