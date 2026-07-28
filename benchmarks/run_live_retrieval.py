#!/usr/bin/env python3
"""Dated live retrieval-coverage harness for local JSONL datasets."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import statistics
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidencemesh import EvidenceMesh, SearchRequest


def normalise(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", value)).strip()


def answer_covered(answers: list[str], texts: list[str]) -> bool:
    haystack = normalise(" ".join(texts))
    return any(normalise(answer) in haystack for answer in answers if normalise(answer))


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def commit_sha() -> str | None:
    return os.getenv("EVIDENCEMESH_BENCHMARK_COMMIT") or os.getenv("GITHUB_SHA")


def load_rows(path: Path, limit: int | None) -> list[dict[str, Any]]:
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if limit is not None:
        rows = rows[:limit]
    for index, row in enumerate(rows, start=1):
        if not isinstance(row.get("question"), str):
            raise ValueError(f"row {index} has no string 'question'")
        answer = row.get("answer")
        if not isinstance(answer, (str, list)):
            raise ValueError(f"row {index} has no string or list 'answer'")
    return rows


async def evaluate(
    dataset: Path,
    *,
    limit: int | None,
    max_results: int,
) -> dict[str, Any]:
    rows = load_rows(dataset, limit)
    started_at = datetime.now(UTC)
    outcomes: list[dict[str, Any]] = []
    async with EvidenceMesh() as engine:
        configuration = engine.health()
        for index, row in enumerate(rows, start=1):
            question = str(row["question"])
            answer_value = row["answer"]
            answers = (
                [str(answer) for answer in answer_value]
                if isinstance(answer_value, list)
                else [str(answer_value)]
            )
            started = time.perf_counter()
            try:
                response = await engine.search(
                    SearchRequest(
                        query=question,
                        limit=max_results,
                        fetch_content=True,
                        use_cache=False,
                    )
                )
                texts = [
                    text for result in response.results for text in (result.title, result.snippet)
                ]
                texts.extend(item.quote for item in response.evidence)
                outcomes.append(
                    {
                        "id": row.get("id", str(index)),
                        "covered": answer_covered(answers, texts),
                        "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
                        "result_count": len(response.results),
                        "failure_count": len(response.metadata.provider_failures),
                        "error": None,
                    }
                )
            except Exception as exc:
                outcomes.append(
                    {
                        "id": row.get("id", str(index)),
                        "covered": False,
                        "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
                        "result_count": 0,
                        "failure_count": 1,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    latencies = [float(outcome["latency_ms"]) for outcome in outcomes]
    return {
        "schema_version": 1,
        "metric": "retrieval_answer_coverage",
        "dataset": str(dataset),
        "sample_count": len(outcomes),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "commit_sha": commit_sha(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "configuration": configuration,
        "coverage": (
            statistics.fmean(bool(outcome["covered"]) for outcome in outcomes) if outcomes else 0.0
        ),
        "failure_rate": (
            statistics.fmean(bool(outcome["error"]) for outcome in outcomes) if outcomes else 0.0
        ),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
        "outcomes": outcomes,
        "warning": (
            "Answer-string coverage measures retrieval only. It is not factuality, "
            "citation quality or end-to-end research accuracy."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = asyncio.run(
        evaluate(
            arguments.dataset,
            limit=arguments.limit,
            max_results=arguments.max_results,
        )
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output:
        arguments.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
