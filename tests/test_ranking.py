from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evidencemesh.models import ProviderResult, SearchProfile, SourceType
from evidencemesh.ranking import (
    freshness_score,
    lexical_relevance,
    rank_results,
    rank_results_with_diagnostics,
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


def test_untrusted_non_http_and_malformed_urls_are_filtered() -> None:
    results = [
        make_result(title="Script", url="javascript:alert(1)", provider="hostile", rank=1),
        make_result(title="Local file", url="file:///etc/passwd", provider="hostile", rank=2),
        make_result(
            title="Credentials",
            url="https://user:pass@example.com/path",
            provider="hostile",
            rank=3,
        ),
        make_result(title="Malformed", url="http://[:::1", provider="hostile", rank=4),
        make_result(
            title="Wrapped credentials",
            url=("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fuser%3Apass%40example.com%2Fpath"),
            provider="hostile",
            rank=5,
        ),
        make_result(
            title="Private target",
            url="http://127.0.0.1/internal",
            provider="hostile",
            rank=6,
        ),
        make_result(title="Valid", url="https://example.org/evidence", provider="good", rank=1),
    ]
    hits, count = rank_results(
        results,
        query="alpha",
        profile=SearchProfile.WEB,
        limit=10,
        max_per_domain=3,
    )
    assert count == 1
    assert [hit.canonical_url for hit in hits] == ["https://example.org/evidence"]


def test_primary_provider_reservation_preserves_configured_share_and_lineage() -> None:
    results: list[ProviderResult] = []
    for rank in range(1, 11):
        url = f"https://community-{rank}.org/result"
        results.extend(
            [
                make_result(
                    title=f"Community consensus {rank}",
                    url=url,
                    provider="searxng",
                    rank=rank,
                ),
                make_result(
                    title=f"Community consensus {rank}",
                    url=url,
                    provider="ddgs",
                    rank=rank,
                ),
            ]
        )
        results.append(
            make_result(
                title=f"Tavily candidate {rank}",
                url=f"https://tavily-{rank}.net/result",
                provider="tavily",
                rank=rank,
            )
        )

    for share, expected in ((0.4, 4), (0.6, 6), (0.8, 8)):
        hits, fused_count, diagnostics = rank_results_with_diagnostics(
            results,
            query="alpha evidence",
            profile=SearchProfile.WEB,
            limit=10,
            max_per_domain=3,
            primary_provider="tavily",
            primary_provider_share=share,
        )
        assert fused_count == 20
        assert sum("tavily" in hit.providers for hit in hits) >= expected
        assert diagnostics.reservation_requested == expected
        assert diagnostics.reservation_eligible == 10
        assert diagnostics.reservation_feasible == 10
        assert diagnostics.reservation_target == expected
        assert diagnostics.reservation_fulfilled == expected
        assert diagnostics.reservation_shortfall_reason is None
        assert diagnostics.provider_stage_counts["raw"] == {
            "ddgs": 10,
            "searxng": 10,
            "tavily": 10,
        }
        assert diagnostics.provider_stage_counts["fused"] == {
            "ddgs": 10,
            "searxng": 10,
            "tavily": 10,
        }
        assert diagnostics.reservation_policy == f"provider_share:tavily:{share:.3f}"


def test_primary_provider_reservation_keeps_domain_diversity_cap() -> None:
    titles = ["Oak", "River", "Quartz", "Falcon", "Harbor"]
    results = [
        make_result(
            title=titles[rank - 1],
            url=f"https://same.example/result-{rank}",
            provider="tavily",
            rank=rank,
        )
        for rank in range(1, 6)
    ]
    results.extend(
        make_result(
            title=f"Community {rank}",
            url=f"https://community-{rank}.org/result",
            provider="searxng",
            rank=rank,
        )
        for rank in range(1, 6)
    )
    hits, _, diagnostics = rank_results_with_diagnostics(
        results,
        query="alpha evidence",
        profile=SearchProfile.WEB,
        limit=5,
        max_per_domain=1,
        primary_provider="tavily",
        primary_provider_share=0.8,
    )
    assert diagnostics.reservation_requested == 4
    assert diagnostics.reservation_eligible == 5
    assert diagnostics.reservation_feasible == 1
    assert diagnostics.reservation_target == 1
    assert diagnostics.reservation_fulfilled == 1
    assert diagnostics.reservation_shortfall_reason == "domain_diversity_cap"
    assert sum("tavily" in hit.providers for hit in hits) == 1


def test_primary_provider_reservation_remains_observable_with_no_results() -> None:
    hits, fused_count, diagnostics = rank_results_with_diagnostics(
        [],
        query="alpha evidence",
        profile=SearchProfile.WEB,
        limit=10,
        max_per_domain=3,
        primary_provider="tavily",
        primary_provider_share=0.8,
    )
    assert hits == []
    assert fused_count == 0
    assert diagnostics.reservation_policy == "provider_share:tavily:0.800"
    assert diagnostics.reservation_requested == 8
    assert diagnostics.reservation_eligible == 0
    assert diagnostics.reservation_feasible == 0
    assert diagnostics.reservation_target == 0
    assert diagnostics.reservation_fulfilled == 0
    assert diagnostics.reservation_shortfall_reason == "insufficient_eligible_results"


def test_primary_provider_reports_mixed_feasibility_shortfall() -> None:
    titles = ["Oak", "River", "Quartz"]
    results = [
        make_result(
            title=titles[rank - 1],
            url=f"https://same.example/result-{rank}",
            provider="tavily",
            rank=rank,
        )
        for rank in range(1, 4)
    ]
    _, _, diagnostics = rank_results_with_diagnostics(
        results,
        query="alpha evidence",
        profile=SearchProfile.WEB,
        limit=10,
        max_per_domain=2,
        primary_provider="tavily",
        primary_provider_share=0.8,
    )
    assert diagnostics.reservation_requested == 8
    assert diagnostics.reservation_eligible == 3
    assert diagnostics.reservation_feasible == 2
    assert diagnostics.reservation_target == 2
    assert diagnostics.reservation_fulfilled == 2
    assert (
        diagnostics.reservation_shortfall_reason
        == "insufficient_eligible_results_and_domain_diversity_cap"
    )
