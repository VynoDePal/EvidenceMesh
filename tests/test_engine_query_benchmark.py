from __future__ import annotations

from pathlib import Path

import pytest
from conftest import StaticFetcher, StaticProvider
from pydantic import ValidationError

from evidencemesh.benchmark import load_fixture, run_offline_benchmark
from evidencemesh.engine import EvidenceMesh
from evidencemesh.errors import ProviderError
from evidencemesh.models import (
    FetchedDocument,
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


class AcademicOnlyProvider(StaticProvider):
    supported_profiles = frozenset({SearchProfile.ACADEMIC})


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
