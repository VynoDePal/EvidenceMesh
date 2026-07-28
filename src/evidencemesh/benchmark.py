"""Deterministic retrieval-ranking benchmark used as a regression gate."""

from __future__ import annotations

import math
from importlib import resources
from pathlib import Path
from statistics import fmean

from pydantic import Field

from evidencemesh.models import ProviderResult, SearchProfile, StrictModel
from evidencemesh.ranking import rank_results
from evidencemesh.urls import canonicalize_url, hostname_from_url


class FixtureResult(StrictModel):
    title: str
    url: str
    snippet: str = ""


class FixtureProvider(StrictModel):
    name: str
    results: list[FixtureResult]


class FixtureCase(StrictModel):
    id: str
    query: str
    profile: SearchProfile = SearchProfile.WEB
    relevant_urls: list[str] = Field(min_length=1)
    providers: list[FixtureProvider] = Field(min_length=2)


class BenchmarkFixture(StrictModel):
    name: str
    version: int
    description: str
    cases: list[FixtureCase] = Field(min_length=1)


class RankingMetrics(StrictModel):
    hit_at_1: float
    hit_at_5: float
    mrr_at_10: float
    ndcg_at_10: float
    duplicate_rate: float
    unique_domain_ratio: float


class CaseBenchmark(StrictModel):
    id: str
    baseline: RankingMetrics
    fused: RankingMetrics
    input_duplicate_rate: float
    baseline_ranking: list[str]
    fused_ranking: list[str]


class BenchmarkReport(StrictModel):
    benchmark: str
    fixture_version: int
    fixture_description: str
    case_count: int
    baseline: RankingMetrics
    fused: RankingMetrics
    delta: RankingMetrics
    cases: list[CaseBenchmark]
    interpretation: str


def _fixture_text(path: Path | None) -> str:
    if path is not None:
        return path.read_text(encoding="utf-8")
    fixture = resources.files("evidencemesh").joinpath("data/federation_v1.json")
    return fixture.read_text(encoding="utf-8")


def load_fixture(path: Path | None = None) -> BenchmarkFixture:
    """Load and validate a federation fixture."""

    return BenchmarkFixture.model_validate_json(_fixture_text(path))


def _deduplicate(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        canonical = canonicalize_url(url)
        if canonical not in seen:
            seen.add(canonical)
            unique.append(canonical)
    return unique


def _ranking_metrics(urls: list[str], relevant_urls: list[str]) -> RankingMetrics:
    canonical = [canonicalize_url(url) for url in urls]
    relevant = {canonicalize_url(url) for url in relevant_urls}
    first_rank = next(
        (rank for rank, url in enumerate(canonical[:10], start=1) if url in relevant),
        None,
    )
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, url in enumerate(canonical[:10], start=1)
        if url in relevant
    )
    ideal_count = min(len(relevant), 10)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    unique_urls = set(canonical)
    domains = {hostname_from_url(url) for url in canonical if hostname_from_url(url)}
    return RankingMetrics(
        hit_at_1=float(bool(canonical[:1] and canonical[0] in relevant)),
        hit_at_5=float(any(url in relevant for url in canonical[:5])),
        mrr_at_10=0.0 if first_rank is None else 1.0 / first_rank,
        ndcg_at_10=0.0 if ideal_dcg == 0 else dcg / ideal_dcg,
        duplicate_rate=0.0 if not canonical else 1.0 - (len(unique_urls) / len(canonical)),
        unique_domain_ratio=0.0 if not canonical else len(domains) / len(canonical),
    )


def _mean_metrics(metrics: list[RankingMetrics]) -> RankingMetrics:
    fields = RankingMetrics.model_fields
    values = {name: round(fmean(getattr(metric, name) for metric in metrics), 6) for name in fields}
    return RankingMetrics.model_validate(values)


def _delta(left: RankingMetrics, right: RankingMetrics) -> RankingMetrics:
    return RankingMetrics.model_validate(
        {
            name: round(getattr(right, name) - getattr(left, name), 6)
            for name in RankingMetrics.model_fields
        }
    )


def run_offline_benchmark(path: Path | None = None) -> BenchmarkReport:
    """Compare EvidenceMesh fusion with the first provider's native ordering."""

    fixture = load_fixture(path)
    cases: list[CaseBenchmark] = []
    for case in fixture.cases:
        raw_results: list[ProviderResult] = []
        raw_urls: list[str] = []
        for provider in case.providers:
            for rank, result in enumerate(provider.results, start=1):
                raw_urls.append(result.url)
                raw_results.append(
                    ProviderResult(
                        title=result.title,
                        url=result.url,
                        snippet=result.snippet,
                        provider=provider.name,
                        rank=rank,
                        query=case.query,
                    )
                )

        baseline_urls = _deduplicate([result.url for result in case.providers[0].results])[:10]
        fused_hits, _ = rank_results(
            raw_results,
            query=case.query,
            profile=case.profile,
            limit=10,
            max_per_domain=1,
        )
        fused_urls = [hit.canonical_url for hit in fused_hits]
        input_metrics = _ranking_metrics(raw_urls, case.relevant_urls)
        cases.append(
            CaseBenchmark(
                id=case.id,
                baseline=_ranking_metrics(baseline_urls, case.relevant_urls),
                fused=_ranking_metrics(fused_urls, case.relevant_urls),
                input_duplicate_rate=round(input_metrics.duplicate_rate, 6),
                baseline_ranking=baseline_urls,
                fused_ranking=fused_urls,
            )
        )

    baseline = _mean_metrics([case.baseline for case in cases])
    fused = _mean_metrics([case.fused for case in cases])
    return BenchmarkReport(
        benchmark=fixture.name,
        fixture_version=fixture.version,
        fixture_description=fixture.description,
        case_count=len(cases),
        baseline=baseline,
        fused=fused,
        delta=_delta(baseline, fused),
        cases=cases,
        interpretation=(
            "Synthetic deterministic regression benchmark only; these scores do not "
            "establish real-world superiority over live search systems."
        ),
    )
