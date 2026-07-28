from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from conftest import StaticFetcher, StaticProvider
from pydantic import ValidationError

from evidencemesh.benchmark import load_fixture, run_offline_benchmark
from evidencemesh.engine import EvidenceMesh
from evidencemesh.errors import FetchError, ProviderError
from evidencemesh.models import (
    FetchedDocument,
    FetchRequest,
    ProviderResult,
    ResearchRequest,
    SearchDepth,
    SearchProfile,
    SearchRequest,
)
from evidencemesh.query import build_query_plan


@pytest.mark.parametrize(
    ("depth", "expected"),
    [
        (SearchDepth.QUICK, 1),
        (SearchDepth.STANDARD, 4),
        (SearchDepth.DEEP, 7),
    ],
)
def test_query_plan_depth(depth: SearchDepth, expected: int) -> None:
    plan = build_query_plan(
        "  What   is EvidenceMesh? ",
        depth=depth,
        profile=SearchProfile.WEB,
        language="en",
    )
    assert len(plan) == expected
    assert plan[0] == "What is EvidenceMesh?"


@pytest.mark.parametrize(
    ("profile", "language", "expected_term"),
    [
        (SearchProfile.WEB, "fr", "source officielle"),
        (SearchProfile.ACADEMIC, "en", "research paper"),
        (SearchProfile.CODE, "en", "source code"),
        (SearchProfile.NEWS, "en", "latest update"),
        (SearchProfile.WEB, "de", "official source"),
    ],
)
def test_query_plan_profile_terms(
    profile: SearchProfile,
    language: str,
    expected_term: str,
) -> None:
    plan = build_query_plan(
        "alpha",
        depth=SearchDepth.STANDARD,
        profile=profile,
        language=language,
    )
    assert expected_term in plan[1]


def test_query_plan_honours_supplied_variants() -> None:
    assert build_query_plan(
        " alpha ",
        depth=SearchDepth.DEEP,
        profile=SearchProfile.WEB,
        language="en",
        supplied=[" beta ", "beta", ""],
    ) == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_search_returns_ranked_snippet_evidence_and_caches(
    settings,
    result: ProviderResult,
) -> None:
    provider = StaticProvider("alpha", [result])
    engine = EvidenceMesh(settings, providers=[provider])
    first = await engine.search(
        SearchRequest(query="EvidenceMesh", query_variants=["federated search"])
    )
    second = await engine.search(
        SearchRequest(query="EvidenceMesh", query_variants=["federated search"])
    )
    assert first.results[0].citation_id == "S1"
    assert first.evidence[0].quote.startswith("EvidenceMesh")
    assert first.metadata.queries_executed == ["EvidenceMesh", "federated search"]
    assert provider.calls == ["EvidenceMesh", "federated search"]
    assert second.metadata.cache_hits == 2
    await engine.aclose()
    await engine.aclose()


@pytest.mark.asyncio
async def test_search_isolates_provider_failures(settings, result: ProviderResult) -> None:
    good = StaticProvider("good", [result])
    bad = StaticProvider("bad", error=ProviderError("provider offline"))
    unexpected = StaticProvider("unexpected", error=RuntimeError("boom"))
    engine = EvidenceMesh(settings, providers=[good, bad, unexpected])
    response = await engine.search(SearchRequest(query="EvidenceMesh", use_cache=False))
    assert response.results
    assert len(response.metadata.provider_failures) == 2
    assert "partial results" in response.warnings[0]
    assert response.metadata.providers_succeeded == ["good"]
    await engine.aclose()


@pytest.mark.asyncio
async def test_search_opens_provider_circuit_after_repeated_failures(settings) -> None:
    protected_settings = settings.model_copy(
        update={
            "provider_failure_threshold": 2,
            "provider_recovery_seconds": 60.0,
        }
    )
    provider = StaticProvider("unstable", error=ProviderError("provider offline"))
    engine = EvidenceMesh(protected_settings, providers=[provider])

    first = await engine.search(SearchRequest(query="first failure", use_cache=False))
    second = await engine.search(SearchRequest(query="second failure", use_cache=False))
    third = await engine.search(SearchRequest(query="skipped call", use_cache=False))

    assert provider.calls == ["first failure", "second failure"]
    assert "provider offline" in first.metadata.provider_failures["unstable:first failure"]
    assert "provider offline" in second.metadata.provider_failures["unstable:second failure"]
    assert "circuit is open" in third.metadata.provider_failures["unstable:skipped call"]
    assert engine.health()["status"] == "degraded"
    assert engine.health()["providers"][0]["circuit"]["consecutive_failures"] == 2
    await engine.aclose()


class SlowProvider(StaticProvider):
    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        await asyncio.sleep(0.05)
        return []


@pytest.mark.asyncio
async def test_search_enforces_provider_total_deadline(settings) -> None:
    short_deadline = settings.model_copy(update={"request_timeout_seconds": 0.01})
    engine = EvidenceMesh(short_deadline, providers=[SlowProvider("slow")])
    response = await engine.search(SearchRequest(query="deadline test", use_cache=False))
    assert response.results == []
    assert "request deadline" in response.metadata.provider_failures["slow:deadline test"]
    assert "partial results" in response.warnings[0]
    await engine.aclose()


@pytest.mark.asyncio
async def test_provider_deadline_includes_concurrency_queue(settings) -> None:
    short_deadline = settings.model_copy(
        update={
            "max_concurrency": 1,
            "request_timeout_seconds": 0.08,
        }
    )
    engine = EvidenceMesh(short_deadline, providers=[SlowProvider("slow")])
    response = await engine.search(
        SearchRequest(
            query="first query",
            query_variants=["second query"],
            use_cache=False,
        )
    )
    assert len(response.metadata.provider_failures) == 1
    assert "slow:second query" in response.metadata.provider_failures
    await engine.aclose()


class AcademicOnlyProvider(StaticProvider):
    supported_profiles = frozenset({SearchProfile.ACADEMIC})


class BudgetedProvider(StaticProvider):
    query_budget = 1


@pytest.mark.asyncio
async def test_router_applies_query_budget_and_reports_source_family(
    settings,
    result: ProviderResult,
) -> None:
    provider = BudgetedProvider("budgeted", [result])
    engine = EvidenceMesh(settings, providers=[provider])
    response = await engine.search(
        SearchRequest(
            query="base query",
            query_variants=["variant one", "variant two"],
            use_cache=False,
        )
    )
    assert provider.calls == ["base query"]
    assert response.metadata.queries_executed == ["base query"]
    assert response.metadata.provider_query_counts == {"budgeted": 1}
    assert response.metadata.provider_source_families == {"budgeted": "web"}
    assert response.metadata.deployment_profile == "community"
    await engine.aclose()


class SlowFetcher(StaticFetcher):
    async def fetch(self, url: str, *, max_chars: int = 30_000) -> FetchedDocument:
        await asyncio.sleep(0.05)
        return await super().fetch(url, max_chars=max_chars)


@pytest.mark.asyncio
async def test_search_warns_when_no_provider_supports_profile(
    settings,
    result: ProviderResult,
) -> None:
    engine = EvidenceMesh(settings, providers=[AcademicOnlyProvider("academic", [result])])
    response = await engine.search(SearchRequest(query="EvidenceMesh", profile=SearchProfile.CODE))
    assert response.results == []
    assert "no configured provider supports" in response.warnings[0]
    await engine.aclose()


@pytest.mark.asyncio
async def test_search_fetches_content_and_propagates_risk_flags(
    settings,
    result: ProviderResult,
    document: FetchedDocument,
) -> None:
    flagged = document.model_copy(update={"risk_flags": ["possible_prompt_injection"]})
    fetcher = StaticFetcher({result.url: flagged})
    engine = EvidenceMesh(
        settings,
        providers=[StaticProvider("alpha", [result])],
        fetcher=fetcher,
    )
    response = await engine.search(SearchRequest(query="EvidenceMesh", fetch_content=True))
    assert response.evidence[0].content_sha256 == document.content_sha256
    assert response.results[0].risk_flags == ["possible_prompt_injection"]
    assert fetcher.guard.urls == [result.url]
    await engine.aclose()
    assert fetcher.closed


@pytest.mark.asyncio
async def test_search_falls_back_to_snippet_when_fetch_fails(
    settings,
    result: ProviderResult,
) -> None:
    engine = EvidenceMesh(
        settings,
        providers=[StaticProvider("alpha", [result])],
        fetcher=StaticFetcher({}),
    )
    response = await engine.search(SearchRequest(query="EvidenceMesh", fetch_content=True))
    assert response.evidence[0].quote == result.snippet
    assert "content fetch failed" in response.warnings[0]
    await engine.aclose()


@pytest.mark.asyncio
async def test_fetch_document_cache(
    settings,
    document: FetchedDocument,
) -> None:
    fetcher = StaticFetcher({document.url: document})
    engine = EvidenceMesh(settings, providers=[], fetcher=fetcher)
    first = await engine.fetch(document.url, max_chars=5_000)
    second = await engine.fetch(document.url, max_chars=5_000)
    assert first == second
    assert fetcher.calls == [document.url]
    await engine.aclose()


@pytest.mark.asyncio
async def test_fetch_deadline_includes_concurrency_queue(
    settings,
    document: FetchedDocument,
) -> None:
    second_url = "https://docs.example.org/second"
    second_document = document.model_copy(
        update={
            "url": second_url,
            "canonical_url": second_url,
        }
    )
    short_deadline = settings.model_copy(
        update={
            "fetch_timeout_seconds": 0.08,
            "max_concurrency": 1,
        }
    )
    engine = EvidenceMesh(
        short_deadline,
        providers=[],
        fetcher=SlowFetcher(
            {
                document.url: document,
                second_url: second_document,
            }
        ),
    )
    outcomes = await asyncio.gather(
        engine.fetch(FetchRequest(url=document.url, use_cache=False)),
        engine.fetch(FetchRequest(url=second_url, use_cache=False)),
        return_exceptions=True,
    )
    assert outcomes[0] == document
    assert isinstance(outcomes[1], FetchError)
    assert "total deadline" in str(outcomes[1])
    await engine.aclose()


@pytest.mark.asyncio
async def test_research_and_claim_review(
    settings,
    result: ProviderResult,
    document: FetchedDocument,
) -> None:
    fetcher = StaticFetcher({result.url: document})
    engine = EvidenceMesh(
        settings,
        providers=[StaticProvider("alpha", [result])],
        fetcher=fetcher,
    )
    packet = await engine.research(
        ResearchRequest(
            question="What does EvidenceMesh provide?",
            depth=SearchDepth.QUICK,
            max_sources=3,
        )
    )
    assert packet.coverage.total_queries == 1
    assert packet.coverage.extracted_sources == 1
    assert packet.synthesis_protocol
    review = await engine.verify_claim("EvidenceMesh provides evidence", max_sources=3)
    assert review.status == "insufficient_independent_evidence"
    assert "truth verdict" in review.review_protocol[0]
    await engine.aclose()


@pytest.mark.asyncio
async def test_batch_search_and_limit(settings, result: ProviderResult) -> None:
    engine = EvidenceMesh(settings, providers=[StaticProvider("alpha", [result])])
    response = await engine.batch_search(
        [SearchRequest(query="first query"), SearchRequest(query="second query")]
    )
    assert len(response.responses) == 2
    assert (await engine.batch_search([])).responses == []
    with pytest.raises(ValueError, match="at most 20"):
        await engine.batch_search([SearchRequest(query=f"query {index}") for index in range(21)])
    health = engine.health()
    assert health["status"] == "ready"
    assert health["safety"]["private_networks_allowed"] is False
    await engine.aclose()


def test_offline_benchmark_is_reproducible() -> None:
    fixture = load_fixture()
    first = run_offline_benchmark()
    second = run_offline_benchmark()
    assert len(fixture.cases) == 12
    assert first == second
    assert first.fused.hit_at_1 == 1.0
    assert first.fused.mrr_at_10 > first.baseline.mrr_at_10
    assert all(case.fused.duplicate_rate == 0.0 for case in first.cases)
    assert "do not establish" in first.interpretation


def test_benchmark_validates_custom_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "invalid.json"
    fixture.write_text('{"name":"missing fields"}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_fixture(fixture)
