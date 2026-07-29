"""Provider-neutral fusion, deduplication and source diversity."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from evidencemesh.models import ProviderResult, SearchHit, SearchProfile, SourceType
from evidencemesh.urls import (
    canonicalize_url,
    domain_matches,
    hostname_from_url,
    is_supported_http_url,
    registrable_domain_hint,
)

_TOKEN = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)
_CLICKBAIT = re.compile(
    r"\b(you won't believe|shocking|mind[- ]blowing|must see|secret trick)\b",
    re.IGNORECASE,
)
_PROVIDER_WEIGHTS = {
    "arxiv": 1.10,
    "brave": 1.05,
    "crossref": 1.10,
    "ddgs": 0.95,
    "exa": 1.05,
    "firecrawl": 1.00,
    "github": 1.05,
    "openalex": 1.10,
    "searxng": 1.00,
    "tavily": 1.05,
    "wiby": 0.95,
    "wikipedia": 1.00,
}


def _provider_weight(provider: str) -> float:
    """Resolve weights for named instances such as ``searxng-2``."""

    if provider.startswith("searxng-"):
        return _PROVIDER_WEIGHTS["searxng"]
    return _PROVIDER_WEIGHTS.get(provider, 1.0)


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text) if len(token) > 1}


def lexical_relevance(query: str, title: str, snippet: str) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    title_tokens = tokenize(title)
    snippet_tokens = tokenize(snippet)
    title_overlap = len(query_tokens & title_tokens) / len(query_tokens)
    snippet_overlap = len(query_tokens & snippet_tokens) / len(query_tokens)
    phrase_bonus = 0.15 if query.lower() in f"{title} {snippet}".lower() else 0.0
    return min(1.0, 0.65 * title_overlap + 0.35 * snippet_overlap + phrase_bonus)


def source_signal(url: str, title: str, snippet: str, source_type: SourceType) -> float:
    """Estimate provenance signals, never truth or factual correctness."""

    host = hostname_from_url(url)
    score = 0.50
    if host.endswith((".gov", ".gov.uk", ".gouv.fr", ".edu", ".ac.uk")):
        score += 0.20
    if source_type is SourceType.ACADEMIC:
        score += 0.12
    if source_type is SourceType.CODE and host in {"github.com", "gitlab.com"}:
        score += 0.10
    if host in {
        "arxiv.org",
        "crossref.org",
        "docs.python.org",
        "ietf.org",
        "modelcontextprotocol.io",
        "wikipedia.org",
    } or host.endswith(".wikipedia.org"):
        score += 0.10
    if not snippet.strip():
        score -= 0.08
    if _CLICKBAIT.search(title):
        score -= 0.18
    if len(url) > 220:
        score -= 0.05
    return max(0.0, min(1.0, score))


def freshness_score(published_at: datetime | None, profile: SearchProfile) -> float:
    if published_at is None or profile is not SearchProfile.NEWS:
        return 0.5
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age_days = max(0.0, (datetime.now(UTC) - published_at).total_seconds() / 86_400)
    return math.exp(-age_days / 45)


@dataclass
class _Aggregate:
    title: str
    url: str
    canonical_url: str
    snippet: str
    published_at: datetime | None
    source_type: SourceType
    providers: set[str] = field(default_factory=set)
    provider_ranks: dict[str, int] = field(default_factory=dict)
    matched_queries: set[str] = field(default_factory=set)
    rrf: float = 0.0


@dataclass(frozen=True, slots=True)
class RankingDiagnostics:
    """Provider lineage and reservation outcomes for one ranking operation."""

    provider_stage_counts: dict[str, dict[str, int]]
    reservation_policy: str
    reservation_requested: int
    reservation_eligible: int
    reservation_feasible: int
    reservation_target: int
    reservation_fulfilled: int
    reservation_shortfall_reason: str | None


_ScoredAggregate = tuple[float, _Aggregate, float, float, float]


def _provider_presence_counts(aggregates: Iterable[_Aggregate]) -> dict[str, int]:
    counts = Counter(provider for aggregate in aggregates for provider in aggregate.providers)
    return dict(sorted(counts.items()))


def _title_similarity(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def _merge_results(results: list[ProviderResult], rrf_k: int = 60) -> list[_Aggregate]:
    aggregates: dict[str, _Aggregate] = {}
    title_keys: dict[str, list[str]] = defaultdict(list)
    for result in results:
        if not is_supported_http_url(result.url):
            continue
        canonical = canonicalize_url(result.url)
        if not is_supported_http_url(canonical):
            continue
        host = hostname_from_url(canonical)
        if not host:
            continue
        key = canonical
        if key not in aggregates:
            diversity_key = registrable_domain_hint(host)
            for candidate_key in title_keys[diversity_key]:
                if _title_similarity(result.title, aggregates[candidate_key].title) >= 0.94:
                    key = candidate_key
                    break
        if key not in aggregates:
            aggregates[key] = _Aggregate(
                title=result.title.strip() or canonical,
                url=result.url,
                canonical_url=canonical,
                snippet=result.snippet.strip(),
                published_at=result.published_at,
                source_type=result.source_type,
            )
            title_keys[registrable_domain_hint(host)].append(key)

        aggregate = aggregates[key]
        aggregate.providers.add(result.provider)
        current_rank = aggregate.provider_ranks.get(result.provider)
        aggregate.provider_ranks[result.provider] = (
            min(current_rank, result.rank) if current_rank else result.rank
        )
        aggregate.matched_queries.add(result.query)
        weight = _provider_weight(result.provider)
        aggregate.rrf += weight / (rrf_k + result.rank)
        if len(result.snippet) > len(aggregate.snippet):
            aggregate.snippet = result.snippet.strip()
        if result.published_at and (
            aggregate.published_at is None or result.published_at > aggregate.published_at
        ):
            aggregate.published_at = result.published_at
    return list(aggregates.values())


def rank_results_with_diagnostics(
    results: list[ProviderResult],
    *,
    query: str,
    profile: SearchProfile,
    limit: int,
    max_per_domain: int,
    domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    primary_provider: str | None = None,
    primary_provider_share: float = 0.0,
) -> tuple[list[SearchHit], int, RankingDiagnostics]:
    raw_counts = dict(sorted(Counter(result.provider for result in results).items()))
    reservation_requested = 0
    reservation_eligible = 0
    reservation_feasible = 0
    reservation_target = 0
    reservation_fulfilled = 0
    reservation_policy = "none"
    if primary_provider and primary_provider_share > 0:
        bounded_share = min(1.0, primary_provider_share)
        reservation_requested = min(limit, max(1, int(limit * bounded_share)))
        reservation_policy = f"provider_share:{primary_provider}:{bounded_share:.3f}"
    aggregates = _merge_results(results)
    if not aggregates:
        return (
            [],
            0,
            RankingDiagnostics(
                provider_stage_counts={
                    "raw": raw_counts,
                    "fused": {},
                    "eligible": {},
                    "selected": {},
                },
                reservation_policy=reservation_policy,
                reservation_requested=reservation_requested,
                reservation_eligible=0,
                reservation_feasible=0,
                reservation_target=0,
                reservation_fulfilled=0,
                reservation_shortfall_reason=(
                    "insufficient_eligible_results" if reservation_requested else None
                ),
            ),
        )
    max_rrf = max(aggregate.rrf for aggregate in aggregates) or 1.0
    scored: list[_ScoredAggregate] = []
    for aggregate in aggregates:
        hostname = hostname_from_url(aggregate.canonical_url)
        if domains and not domain_matches(hostname, domains):
            continue
        if exclude_domains and domain_matches(hostname, exclude_domains):
            continue
        fusion = aggregate.rrf / max_rrf
        relevance = max(
            lexical_relevance(matched_query, aggregate.title, aggregate.snippet)
            for matched_query in aggregate.matched_queries
        )
        provenance = source_signal(
            aggregate.canonical_url,
            aggregate.title,
            aggregate.snippet,
            aggregate.source_type,
        )
        freshness = freshness_score(aggregate.published_at, profile)
        final = 0.55 * fusion + 0.25 * relevance + 0.15 * provenance + 0.05 * freshness
        scored.append((final, aggregate, fusion, relevance, provenance))
    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].canonical_url,
        )
    )

    selected: list[_ScoredAggregate] = []
    selected_urls: set[str] = set()
    domain_counts: dict[str, int] = defaultdict(int)

    if reservation_requested and primary_provider:
        primary_items = [item for item in scored if primary_provider in item[1].providers]
        reservation_eligible = len(primary_items)
        feasible_domain_counts: dict[str, int] = defaultdict(int)
        for item in primary_items:
            domain_key = registrable_domain_hint(hostname_from_url(item[1].canonical_url))
            if feasible_domain_counts[domain_key] >= max_per_domain:
                continue
            feasible_domain_counts[domain_key] += 1
            reservation_feasible += 1
            if reservation_feasible >= limit:
                break
        reservation_target = min(reservation_requested, reservation_feasible)

    reservation_shortfall_reason: str | None = None
    if reservation_requested and reservation_target < reservation_requested:
        insufficient = reservation_eligible < reservation_requested
        diversity_limited = reservation_feasible < min(
            reservation_requested,
            reservation_eligible,
        )
        if insufficient and diversity_limited:
            reservation_shortfall_reason = "insufficient_eligible_results_and_domain_diversity_cap"
        elif diversity_limited:
            reservation_shortfall_reason = "domain_diversity_cap"
        else:
            reservation_shortfall_reason = "insufficient_eligible_results"

    def select(item: _ScoredAggregate) -> bool:
        canonical_url = item[1].canonical_url
        if canonical_url in selected_urls:
            return False
        domain_key = registrable_domain_hint(hostname_from_url(item[1].canonical_url))
        if domain_counts[domain_key] >= max_per_domain:
            return False
        selected.append(item)
        selected_urls.add(canonical_url)
        domain_counts[domain_key] += 1
        return True

    if reservation_target and primary_provider:
        for item in scored:
            if primary_provider not in item[1].providers:
                continue
            reservation_fulfilled += int(select(item))
            if reservation_fulfilled >= reservation_target:
                break

    for item in scored:
        select(item)
        if len(selected) >= limit:
            break
    selected.sort(key=lambda item: (-item[0], item[1].canonical_url))

    hits = [
        SearchHit(
            citation_id=f"S{index}",
            title=aggregate.title,
            url=aggregate.url,
            canonical_url=aggregate.canonical_url,
            snippet=aggregate.snippet,
            domain=hostname_from_url(aggregate.canonical_url),
            providers=sorted(aggregate.providers),
            provider_ranks=dict(sorted(aggregate.provider_ranks.items())),
            matched_queries=sorted(aggregate.matched_queries),
            published_at=aggregate.published_at,
            source_type=aggregate.source_type,
            fusion_score=round(fusion, 6),
            relevance_score=round(relevance, 6),
            source_signal_score=round(provenance, 6),
            final_score=round(min(1.0, final), 6),
        )
        for index, (final, aggregate, fusion, relevance, provenance) in enumerate(
            selected,
            start=1,
        )
    ]
    diagnostics = RankingDiagnostics(
        provider_stage_counts={
            "raw": raw_counts,
            "fused": _provider_presence_counts(aggregates),
            "eligible": _provider_presence_counts(item[1] for item in scored),
            "selected": _provider_presence_counts(item[1] for item in selected),
        },
        reservation_policy=reservation_policy,
        reservation_requested=reservation_requested,
        reservation_eligible=reservation_eligible,
        reservation_feasible=reservation_feasible,
        reservation_target=reservation_target,
        reservation_fulfilled=reservation_fulfilled,
        reservation_shortfall_reason=reservation_shortfall_reason,
    )
    return hits, len(aggregates), diagnostics


def rank_results(
    results: list[ProviderResult],
    *,
    query: str,
    profile: SearchProfile,
    limit: int,
    max_per_domain: int,
    domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    primary_provider: str | None = None,
    primary_provider_share: float = 0.0,
) -> tuple[list[SearchHit], int]:
    """Rank results while preserving the original two-value public contract."""

    hits, deduplicated_count, _ = rank_results_with_diagnostics(
        results,
        query=query,
        profile=profile,
        limit=limit,
        max_per_domain=max_per_domain,
        domains=domains,
        exclude_domains=exclude_domains,
        primary_provider=primary_provider,
        primary_provider_share=primary_provider_share,
    )
    return hits, deduplicated_count
