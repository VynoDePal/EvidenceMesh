#!/usr/bin/env python3
"""Reproducible, retrieval-only live benchmark for EvidenceMesh profiles.

This runner deliberately does not ask a language model to answer or grade. It
measures whether ranked search results recover curated source URLs/domains and
whether their title/snippet contains the gold answer string.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import csv
import hashlib
import io
import json
import os
import platform
import random
import re
import statistics
import sys
import time
import unicodedata
from collections.abc import Iterable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from evidencemesh import EvidenceMesh, SearchRequest
from evidencemesh.config import Settings
from evidencemesh.models import SearchHit, SearchResponse
from evidencemesh.urls import (
    canonicalize_url,
    hostname_from_url,
    registrable_domain_hint,
)

SIMPLEQA_DATASET_URL = (
    "https://openaipublic.blob.core.windows.net/simple-evals/simple_qa_test_set.csv"
)
SIMPLEQA_DATASET_SHA256 = "feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032"
SIMPLEQA_REFERENCE_REPO_COMMIT = "652c89d0ca9df547706735883097e9537d40dc47"
SIMPLEQA_REFERENCE_FILE_BLOB = "0fc266800a87ace55ec192c9a91cafe92fef7b48"
MAX_DATASET_BYTES = 5_000_000
DEFAULT_PROFILES = (
    "federated=ddgs,wikipedia",
    "ddgs=ddgs",
    "wikipedia=wikipedia",
)


@dataclass(frozen=True, slots=True)
class BenchmarkRow:
    id: str
    question: str
    answers: tuple[str, ...]
    gold_urls: tuple[str, ...] = ()
    topic: str | None = None
    answer_type: str | None = None

    @property
    def gold_domains(self) -> tuple[str, ...]:
        domains = {
            registrable_domain_hint(hostname)
            for url in self.gold_urls
            if (hostname := hostname_from_url(url))
        }
        return tuple(sorted(domains))


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    providers: tuple[str, ...]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalise(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", value)).strip()


def answer_covered(answers: Iterable[str], texts: Iterable[str]) -> bool:
    haystack = normalise(" ".join(texts))
    return any(
        normalised_answer in haystack
        for answer in answers
        if (normalised_answer := normalise(answer))
    )


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def commit_sha() -> str | None:
    return os.getenv("EVIDENCEMESH_BENCHMARK_COMMIT") or os.getenv("GITHUB_SHA")


def stable_row_id(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]


def _clean_url(url: str) -> str:
    cleaned = url.rstrip(".,;]")
    while cleaned.endswith(")") and cleaned.count("(") < cleaned.count(")"):
        cleaned = cleaned[:-1]
    return canonicalize_url(cleaned)


def url_identity(url: str) -> str:
    """Return a canonical URL identity while treating HTTP/HTTPS as equivalent."""

    canonical = canonicalize_url(url)
    parsed = urlsplit(canonical)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return canonical
    return f"{parsed.netloc}{parsed.path}?{parsed.query}".rstrip("?")


def extract_source_urls(metadata: object) -> tuple[str, ...]:
    if isinstance(metadata, str):
        try:
            metadata = ast.literal_eval(metadata)
        except (SyntaxError, ValueError):
            return ()
    if not isinstance(metadata, dict):
        return ()
    raw_urls = metadata.get("urls")
    if not isinstance(raw_urls, list):
        return ()
    urls: list[str] = []
    for value in raw_urls:
        if not isinstance(value, str):
            continue
        for match in re.findall(r"https?://[^\s]+", value):
            cleaned = _clean_url(match)
            if hostname_from_url(cleaned):
                urls.append(cleaned)
    return tuple(dict.fromkeys(urls))


def parse_simpleqa(payload: bytes) -> list[BenchmarkRow]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("SimpleQA dataset is not valid UTF-8") from exc
    rows: list[BenchmarkRow] = []
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ["metadata", "problem", "answer"]:
        raise ValueError(f"unexpected SimpleQA columns: {reader.fieldnames}")
    for index, raw in enumerate(reader, start=2):
        question = (raw.get("problem") or "").strip()
        answer = (raw.get("answer") or "").strip()
        if not question or not answer:
            raise ValueError(f"SimpleQA CSV row {index} is missing a problem or answer")
        metadata_text = raw.get("metadata") or ""
        try:
            metadata = ast.literal_eval(metadata_text)
        except (SyntaxError, ValueError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        rows.append(
            BenchmarkRow(
                id=stable_row_id(question),
                question=question,
                answers=(answer,),
                gold_urls=extract_source_urls(metadata),
                topic=str(metadata["topic"]) if metadata.get("topic") else None,
                answer_type=(str(metadata["answer_type"]) if metadata.get("answer_type") else None),
            )
        )
    if len({row.id for row in rows}) != len(rows):
        raise ValueError("SimpleQA row IDs are not unique")
    return rows


def parse_jsonl(payload: bytes) -> list[BenchmarkRow]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("JSONL dataset is not valid UTF-8") from exc
    rows: list[BenchmarkRow] = []
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSONL row {index} is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"JSONL row {index} must be an object")
        question = raw.get("question")
        answer_value = raw.get("answer")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"JSONL row {index} has no non-empty string 'question'")
        if isinstance(answer_value, str):
            answers = (answer_value,)
        elif (
            isinstance(answer_value, list)
            and answer_value
            and all(isinstance(answer, str) and answer.strip() for answer in answer_value)
        ):
            answers = tuple(answer_value)
        else:
            raise ValueError(f"JSONL row {index} has no string or string-list 'answer'")
        gold_urls_value = raw.get("gold_urls", [])
        if not isinstance(gold_urls_value, list) or not all(
            isinstance(url, str) for url in gold_urls_value
        ):
            raise ValueError(f"JSONL row {index} has an invalid 'gold_urls' list")
        cleaned_urls = tuple(
            dict.fromkeys(
                cleaned for url in gold_urls_value if hostname_from_url(cleaned := _clean_url(url))
            )
        )
        row_id = raw.get("id")
        if row_id is not None and (not isinstance(row_id, str) or not row_id.strip()):
            raise ValueError(f"JSONL row {index} has an invalid 'id'")
        rows.append(
            BenchmarkRow(
                id=row_id.strip() if isinstance(row_id, str) else stable_row_id(question),
                question=question.strip(),
                answers=answers,
                gold_urls=cleaned_urls,
                topic=str(raw["topic"]) if raw.get("topic") else None,
                answer_type=str(raw["answer_type"]) if raw.get("answer_type") else None,
            )
        )
    if not rows:
        raise ValueError("dataset contains no benchmark rows")
    if len({row.id for row in rows}) != len(rows):
        raise ValueError("dataset row IDs must be unique")
    return rows


def download_simpleqa() -> bytes:
    chunks: list[bytes] = []
    received = 0
    with httpx.stream(
        "GET",
        SIMPLEQA_DATASET_URL,
        timeout=httpx.Timeout(60.0),
        follow_redirects=False,
        headers={"User-Agent": "EvidenceMesh benchmark/0.1"},
    ) as response:
        response.raise_for_status()
        declared_length = response.headers.get("content-length")
        if declared_length and int(declared_length) > MAX_DATASET_BYTES:
            raise ValueError("SimpleQA dataset exceeds the byte limit")
        for chunk in response.iter_bytes():
            received += len(chunk)
            if received > MAX_DATASET_BYTES:
                raise ValueError("SimpleQA dataset exceeds the byte limit")
            chunks.append(chunk)
    payload = b"".join(chunks)
    digest = sha256_bytes(payload)
    if digest != SIMPLEQA_DATASET_SHA256:
        raise ValueError(
            "SimpleQA dataset checksum changed; review and pin the new revision before running"
        )
    return payload


def select_sample(
    rows: list[BenchmarkRow],
    *,
    sample_size: int | None,
    seed: int,
) -> list[BenchmarkRow]:
    if sample_size is None:
        return list(rows)
    if sample_size < 1:
        raise ValueError("sample size must be at least 1")
    if sample_size > len(rows):
        raise ValueError("sample size exceeds the dataset size")
    # Reproduce the non-cryptographic sampler used by the reference evaluation.
    return random.Random(seed).sample(rows, sample_size)  # noqa: S311


def parse_profiles(values: list[str] | None) -> list[Profile]:
    profiles: list[Profile] = []
    for value in values or list(DEFAULT_PROFILES):
        name, separator, provider_csv = value.partition("=")
        providers = tuple(
            dict.fromkeys(
                provider.strip().lower() for provider in provider_csv.split(",") if provider.strip()
            )
        )
        if not separator or not name.strip() or not providers:
            raise ValueError("profiles must use NAME=provider,provider syntax")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name.strip().lower()):
            raise ValueError(f"invalid profile name: {name!r}")
        profiles.append(Profile(name=name.strip().lower(), providers=providers))
    if len({profile.name for profile in profiles}) != len(profiles):
        raise ValueError("profile names must be unique")
    return profiles


def first_answer_rank(answers: tuple[str, ...], hits: list[SearchHit]) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if answer_covered(answers, (hit.title, hit.snippet)):
            return rank
    return None


def first_gold_url_rank(gold_urls: tuple[str, ...], hits: list[SearchHit]) -> int | None:
    expected = {url_identity(url) for url in gold_urls}
    for rank, hit in enumerate(hits, start=1):
        if url_identity(hit.canonical_url) in expected:
            return rank
    return None


def first_gold_domain_rank(
    gold_domains: tuple[str, ...],
    hits: list[SearchHit],
) -> int | None:
    expected = set(gold_domains)
    for rank, hit in enumerate(hits, start=1):
        hostname = hostname_from_url(hit.canonical_url)
        if hostname and registrable_domain_hint(hostname) in expected:
            return rank
    return None


def result_record(hit: SearchHit) -> dict[str, Any]:
    return {
        "rank": int(hit.citation_id.removeprefix("S")),
        "url": hit.canonical_url,
        "domain": hit.domain,
        "providers": hit.providers,
        "text_sha256": sha256_bytes(f"{hit.title}\n{hit.snippet}".encode()),
    }


async def evaluate_one(
    engine: EvidenceMesh,
    row: BenchmarkRow,
    profile_name: str,
    *,
    max_results: int,
    language: str,
    fetch_content: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = await engine.search(
            SearchRequest(
                query=row.question,
                limit=max_results,
                language=language,
                fetch_content=fetch_content,
                use_cache=False,
            )
        )
        return outcome_from_response(
            row,
            profile_name,
            response,
            latency_ms=round((time.perf_counter() - started) * 1_000, 3),
        )
    except Exception as exc:
        return {
            "id": row.id,
            "profile": profile_name,
            "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
            "result_count": 0,
            "unique_domains": 0,
            "provider_call_count": 0,
            "provider_failure_count": 0,
            "answer_rank": None,
            "gold_url_rank": None,
            "gold_domain_rank": None,
            "has_gold_urls": bool(row.gold_urls),
            "results": [],
            "provider_failures": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def outcome_from_response(
    row: BenchmarkRow,
    profile_name: str,
    response: SearchResponse,
    *,
    latency_ms: float,
) -> dict[str, Any]:
    hits = response.results
    requested = response.metadata.providers_requested
    failures = response.metadata.provider_failures
    return {
        "id": row.id,
        "profile": profile_name,
        "latency_ms": latency_ms,
        "result_count": len(hits),
        "unique_domains": len({hit.domain for hit in hits}),
        "provider_call_count": len(requested),
        "provider_failure_count": len(failures),
        "answer_rank": first_answer_rank(row.answers, hits),
        "gold_url_rank": first_gold_url_rank(row.gold_urls, hits),
        "gold_domain_rank": first_gold_domain_rank(row.gold_domains, hits),
        "has_gold_urls": bool(row.gold_urls),
        "results": [result_record(hit) for hit in hits],
        "provider_failures": [
            {
                "provider": provider_query.partition(":")[0],
                "error": error,
            }
            for provider_query, error in sorted(failures.items())
        ],
        "error": None,
    }


def rate_metric(values: list[bool]) -> dict[str, Any]:
    denominator = len(values)
    numerator = sum(values)
    if denominator == 0:
        return {
            "numerator": 0,
            "denominator": 0,
            "rate": None,
            "wilson_95": None,
        }
    rate = numerator / denominator
    z = 1.959963984540054
    z_squared = z * z
    centre = (rate + z_squared / (2 * denominator)) / (1 + z_squared / denominator)
    margin = (
        z
        * ((rate * (1 - rate) / denominator + z_squared / (4 * denominator**2)) ** 0.5)
        / (1 + z_squared / denominator)
    )
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(rate, 6),
        "wilson_95": [round(max(0.0, centre - margin), 6), round(min(1.0, centre + margin), 6)],
    }


def aggregate_profile(
    outcomes: list[dict[str, Any]],
    *,
    max_results: int,
) -> dict[str, Any]:
    cutoffs = sorted({1, min(3, max_results), min(5, max_results), max_results})
    latencies = [float(outcome["latency_ms"]) for outcome in outcomes]
    gold_outcomes = [outcome for outcome in outcomes if outcome["has_gold_urls"]]
    provider_calls = sum(int(outcome["provider_call_count"]) for outcome in outcomes)
    provider_failures = sum(int(outcome["provider_failure_count"]) for outcome in outcomes)
    metrics: dict[str, Any] = {
        "sample_count": len(outcomes),
        "availability": rate_metric(
            [not outcome["error"] and int(outcome["result_count"]) > 0 for outcome in outcomes]
        ),
        "query_exception_rate": rate_metric([bool(outcome["error"]) for outcome in outcomes]),
        "partial_failure_rate": rate_metric(
            [int(outcome["provider_failure_count"]) > 0 for outcome in outcomes]
        ),
        "provider_call_failure_rate": (
            round(provider_failures / provider_calls, 6) if provider_calls else None
        ),
        "provider_calls": provider_calls,
        "provider_failures": provider_failures,
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
        "mean_result_count": (
            round(statistics.fmean(int(outcome["result_count"]) for outcome in outcomes), 6)
            if outcomes
            else 0.0
        ),
        "mean_unique_domains": (
            round(statistics.fmean(int(outcome["unique_domains"]) for outcome in outcomes), 6)
            if outcomes
            else 0.0
        ),
        "gold_url_mrr": (
            round(
                statistics.fmean(
                    1 / rank if (rank := outcome["gold_url_rank"]) is not None else 0.0
                    for outcome in gold_outcomes
                ),
                6,
            )
            if gold_outcomes
            else None
        ),
    }
    for cutoff in cutoffs:
        metrics[f"answer_coverage_at_{cutoff}"] = rate_metric(
            [
                outcome["answer_rank"] is not None and int(outcome["answer_rank"]) <= cutoff
                for outcome in outcomes
            ]
        )
        metrics[f"gold_url_hit_at_{cutoff}"] = rate_metric(
            [
                outcome["gold_url_rank"] is not None and int(outcome["gold_url_rank"]) <= cutoff
                for outcome in gold_outcomes
            ]
        )
        metrics[f"gold_domain_hit_at_{cutoff}"] = rate_metric(
            [
                outcome["gold_domain_rank"] is not None
                and int(outcome["gold_domain_rank"]) <= cutoff
                for outcome in gold_outcomes
            ]
        )
    return metrics


def paired_comparisons(
    profiles: list[Profile],
    outcomes: list[dict[str, Any]],
    *,
    max_results: int,
) -> list[dict[str, Any]]:
    if len(profiles) < 2:
        return []
    left = profiles[0].name
    indexed = {(outcome["profile"], outcome["id"]): outcome for outcome in outcomes}
    comparisons: list[dict[str, Any]] = []
    for right_profile in profiles[1:]:
        right = right_profile.name
        pairs = [
            (indexed[(left, row_id)], indexed[(right, row_id)])
            for row_id in sorted(
                {
                    outcome["id"]
                    for outcome in outcomes
                    if outcome["profile"] == left and (right, outcome["id"]) in indexed
                }
            )
        ]
        entry: dict[str, Any] = {
            "left": left,
            "right": right,
            "paired_sample_count": len(pairs),
        }
        for field in ("answer_rank", "gold_url_rank", "gold_domain_rank"):
            eligible_pairs = (
                [pair for pair in pairs if pair[0]["has_gold_urls"] and pair[1]["has_gold_urls"]]
                if field != "answer_rank"
                else pairs
            )
            left_hits = [
                pair[0][field] is not None and int(pair[0][field]) <= max_results
                for pair in eligible_pairs
            ]
            right_hits = [
                pair[1][field] is not None and int(pair[1][field]) <= max_results
                for pair in eligible_pairs
            ]
            paired_hits = list(zip(left_hits, right_hits, strict=True))
            wins = sum(left_hit and not right_hit for left_hit, right_hit in paired_hits)
            losses = sum(right_hit and not left_hit for left_hit, right_hit in paired_hits)
            denominator = len(eligible_pairs)
            entry[field.removesuffix("_rank")] = {
                "eligible_pairs": denominator,
                "left_only_hits": wins,
                "right_only_hits": losses,
                "paired_rate_delta": (
                    round((wins - losses) / denominator, 6) if denominator else None
                ),
            }
        comparisons.append(entry)
    return comparisons


def distribution(rows: list[BenchmarkRow], field: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for row in rows:
        value = getattr(row, field) or "unknown"
        values[value] = values.get(value, 0) + 1
    return dict(sorted(values.items()))


async def evaluate(
    rows: list[BenchmarkRow],
    profiles: list[Profile],
    *,
    dataset_metadata: dict[str, Any],
    seed: int,
    max_results: int,
    concurrency: int,
    request_timeout: float,
    language: str,
    fetch_content: bool,
    progress: bool,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    outcomes: list[dict[str, Any]] = []
    health: dict[str, Any] = {}
    semaphore = asyncio.Semaphore(concurrency)

    async with AsyncExitStack() as stack:
        engines: dict[str, EvidenceMesh] = {}
        for profile in profiles:
            settings = Settings.from_env(
                enabled_providers=list(profile.providers),
                cache_path=Path(":memory:"),
                request_timeout_seconds=request_timeout,
                max_concurrency=max(1, min(32, concurrency * len(profile.providers))),
            )
            engine = await stack.enter_async_context(EvidenceMesh(settings))
            engines[profile.name] = engine
            health[profile.name] = engine.health()

        async def run(row: BenchmarkRow, profile: Profile) -> dict[str, Any]:
            async with semaphore:
                outcome = await evaluate_one(
                    engines[profile.name],
                    row,
                    profile.name,
                    max_results=max_results,
                    language=language,
                    fetch_content=fetch_content,
                )
                if progress:
                    print(
                        (
                            f"[{profile.name}] {row.id}: "
                            f"{outcome['result_count']} results, "
                            f"{outcome['latency_ms']} ms"
                        ),
                        file=sys.stderr,
                        flush=True,
                    )
                return outcome

        tasks = [run(row, profile) for row in rows for profile in profiles]
        outcomes = list(await asyncio.gather(*tasks))

    sample_ids = [row.id for row in rows]
    report = {
        "schema_version": 2,
        "benchmark": "retrieval-only/simpleqa-source-recall-v1",
        "task_type": "retrieval_only",
        "dataset": dataset_metadata,
        "sample": {
            "count": len(rows),
            "seed": seed,
            "method": "python random.Random(seed).sample without replacement",
            "ids": sample_ids,
            "manifest_sha256": sha256_bytes("\n".join(sample_ids).encode("utf-8")),
            "rows_with_gold_urls": sum(bool(row.gold_urls) for row in rows),
            "topic_distribution": distribution(rows, "topic"),
            "answer_type_distribution": distribution(rows, "answer_type"),
        },
        "protocol": {
            "profiles": [
                {"name": profile.name, "providers": list(profile.providers)} for profile in profiles
            ],
            "profile_order": "interleaved question-major",
            "max_results": max_results,
            "language": language,
            "cache": False,
            "fetch_content": fetch_content,
            "global_query_concurrency": concurrency,
            "request_timeout_seconds": request_timeout,
        },
        "environment": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "commit_sha": commit_sha(),
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "health": health,
        "metrics": {
            profile.name: aggregate_profile(
                [outcome for outcome in outcomes if outcome["profile"] == profile.name],
                max_results=max_results,
            )
            for profile in profiles
        },
        "paired_comparisons": paired_comparisons(
            profiles,
            outcomes,
            max_results=max_results,
        ),
        "outcomes": outcomes,
        "warnings": [
            (
                "This benchmark measures retrieval only. It is not SimpleQA answer accuracy, "
                "factuality, citation correctness, or end-to-end deep-research quality."
            ),
            (
                "Answer coverage is exact normalised substring matching in titles/snippets; "
                "gold URL/domain metrics use the source metadata shipped with SimpleQA."
            ),
            (
                "Live-web results are dated and non-deterministic. Compare profiles only "
                "within the same interleaved run."
            ),
        ],
    }
    return report


def load_dataset(arguments: argparse.Namespace) -> tuple[list[BenchmarkRow], dict[str, Any]]:
    if arguments.simpleqa:
        payload = download_simpleqa()
        return (
            parse_simpleqa(payload),
            {
                "name": "SimpleQA test set",
                "source_url": SIMPLEQA_DATASET_URL,
                "sha256": sha256_bytes(payload),
                "reference_repository_commit": SIMPLEQA_REFERENCE_REPO_COMMIT,
                "reference_file_blob": SIMPLEQA_REFERENCE_FILE_BLOB,
                "license": "MIT (openai/simple-evals)",
            },
        )
    path = arguments.dataset
    if path is None:
        raise ValueError("choose --simpleqa or --dataset")
    payload = path.read_bytes()
    return (
        parse_jsonl(payload),
        {
            "name": path.name,
            "source": str(path),
            "sha256": sha256_bytes(payload),
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an interleaved, retrieval-only EvidenceMesh benchmark."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--simpleqa",
        action="store_true",
        help="download the checksum-pinned official SimpleQA test set",
    )
    source.add_argument("--dataset", type=Path, help="local JSONL dataset")
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--profile",
        action="append",
        help="repeatable NAME=provider,provider profile (defaults to zero-key trio)",
    )
    parser.add_argument("--max-results", type=int, default=10, choices=range(1, 51))
    parser.add_argument("--concurrency", type=int, default=3, choices=range(1, 17))
    parser.add_argument("--request-timeout", type=float, default=15.0)
    parser.add_argument("--language", default="en")
    parser.add_argument("--fetch-content", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        rows, dataset_metadata = load_dataset(arguments)
        sample = select_sample(rows, sample_size=arguments.sample_size, seed=arguments.seed)
        profiles = parse_profiles(arguments.profile)
        report = asyncio.run(
            evaluate(
                sample,
                profiles,
                dataset_metadata=dataset_metadata,
                seed=arguments.seed,
                max_results=arguments.max_results,
                concurrency=arguments.concurrency,
                request_timeout=arguments.request_timeout,
                language=arguments.language,
                fetch_content=arguments.fetch_content,
                progress=arguments.progress,
            )
        )
    except (OSError, ValueError, httpx.HTTPError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
