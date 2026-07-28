from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evidencemesh.models import ProviderResult, SearchProfile, SourceType
from evidencemesh.ranking import (
    freshness_score,
    lexical_relevance,
    rank_results,
    source_signal,
    tokenize,
)


def make_result(
    *,
    title: str,
    url: str,
    provider: str,
    rank: int,
    query: str = "alpha evidence",
) -> ProviderResult:
    return ProviderResult(
        title=title,
        url=url,
        snippet=f"{title} contains alpha evidence and details.",
        provider=provider,
        rank=rank,
        query=query,
    )


def test_tokenize_and_lexical_relevance() -> None:
    assert tokenize("Alpha, bêta; a") == {"alpha", "bêta"}
    assert lexical_relevance("alpha beta", "Alpha beta", "other") >= 0.8
    assert lexical_relevance("", "Alpha", "Alpha") == 0.0


def test_source_signal_is_provenance_not_truth() -> None:
    government = source_signal(
        "https://example.gov/report",
        "Report",
        "Full report",
        SourceType.WEB,
    )
    clickbait = source_signal(
        "https://blog.example/post",
        "Shocking secret trick",
        "",
        SourceType.WEB,
    )
    assert government > clickbait


def test_freshness_only_affects_news() -> None:
    recent = datetime.now(UTC) - timedelta(days=1)
    old = datetime.now(UTC) - timedelta(days=365)
    assert freshness_score(recent, SearchProfile.NEWS) > freshness_score(
        old,
        SearchProfile.NEWS,
    )
    assert freshness_score(old, SearchProfile.WEB) == 0.5
    assert freshness_score(None, SearchProfile.NEWS) == 0.5


def test_consensus_ranks_above_single_provider_result() -> None:
    results = [
        make_result(title="Distractor", url="https://one.example/a", provider="searxng", rank=1),
        make_result(
            title="Correct evidence", url="https://docs.example/c", provider="searxng", rank=2
        ),
        make_result(
            title="Correct evidence", url="https://docs.example/c", provider="ddgs", rank=1
        ),
        make_result(
            title="Correct evidence", url="https://docs.example/c", provider="brave", rank=1
        ),
    ]
    hits, deduplicated = rank_results(
        results,
        query="alpha evidence",
        profile=SearchProfile.WEB,
        limit=10,
        max_per_domain=3,
    )
    assert hits[0].canonical_url == "https://docs.example/c"
    assert hits[0].providers == ["brave", "ddgs", "searxng"]
    assert deduplicated == 2
    assert [hit.citation_id for hit in hits] == ["S1", "S2"]


def test_tracking_and_title_duplicates_are_merged() -> None:
    results = [
        make_result(
            title="Same result",
            url="https://www.example.com/a?utm_source=x",
            provider="ddgs",
            rank=1,
        ),
        make_result(
            title="Same result",
            url="https://example.com/a",
            provider="searxng",
            rank=1,
        ),
        make_result(
            title="Same result",
            url="https://example.com/other",
            provider="brave",
            rank=2,
        ),
    ]
    hits, count = rank_results(
        results,
        query="same result",
        profile=SearchProfile.WEB,
        limit=10,
        max_per_domain=3,
    )
    assert count == 1
    assert len(hits) == 1


def test_domain_filters_and_diversity_cap() -> None:
    results = [
        make_result(title="One", url="https://a.example.com/1", provider="ddgs", rank=1),
        make_result(title="Two", url="https://b.example.com/2", provider="ddgs", rank=2),
        make_result(title="Three", url="https://other.org/3", provider="ddgs", rank=3),
    ]
    hits, _ = rank_results(
        results,
        query="alpha",
        profile=SearchProfile.WEB,
        limit=10,
        max_per_domain=1,
        exclude_domains=["other.org"],
    )
    assert len(hits) == 1
    assert hits[0].domain.endswith("example.com")
    included, _ = rank_results(
        results,
        query="alpha",
        profile=SearchProfile.WEB,
        limit=10,
        max_per_domain=3,
        domains=["other.org"],
    )
    assert [hit.domain for hit in included] == ["other.org"]


def test_empty_results() -> None:
    assert rank_results(
        [],
        query="anything",
        profile=SearchProfile.WEB,
        limit=10,
        max_per_domain=3,
    ) == ([], 0)
