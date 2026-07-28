"""Provider-neutral fusion, deduplication and source diversity."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from evidencemesh.models import ProviderResult, SearchHit, SearchProfile, SourceType
from evidencemesh.urls import (
    canonicalize_url,
    domain_matches,
    hostname_from_url,
    registrable_domain_hint,
)

_TOKEN = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)
_CLICKBAIT = re.compile(
    r"\b(you won't believe|shocking|mind[- ]blowing|must see|secret trick)\b",
    re.IGNORECASE,
)
_PROVIDER_WEIGHTS = {
    "brave": 1.05,
    "crossref": 1.10,
    "ddgs": 0.95,
    "exa": 1.05,
    "firecrawl": 1.00,
    "searxng": 1.00,
    "tavily": 1.05,
    "wikipedia": 1.00,
}


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


def _title_similarity(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def _merge_results(results: list[ProviderResult], rrf_k: int = 60) -> list[_Aggregate]:
    aggregates: dict[str, _Aggregate] = {}
    title_keys: dict[str, list[str]] = defaultdict(list)
    for result in results:
        canonical = canonicalize_url(result.url)
        host = hostname_from_url(canonical)
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
        weight = _PROVIDER_WEIGHTS.get(result.provider, 1.0)
        aggregate.rrf += weight / (rrf_k + result.rank)
        if len(result.snippet) > len(aggregate.snippet):
            aggregate.snippet = result.snippet.strip()
        if result.published_at and (
            aggregate.published_at is None or result.published_at > aggregate.published_at
        ):
            aggregate.published_at = result.published_at
    return list(aggregates.values())


def rank_results(
    results: list[ProviderResult],
    *,
    query: str,
    profile: SearchProfile,
    limit: int,
    max_per_domain: int,
    domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> tuple[list[SearchHit], int]:
    aggregates = _merge_results(results)
    if not aggregates:
        return [], 0
    max_rrf = max(aggregate.rrf for aggregate in aggregates) or 1.0
    scored: list[tuple[float, _Aggregate, float, float, float]] = []
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

    selected: list[tuple[float, _Aggregate, float, float, float]] = []
    domain_counts: dict[str, int] = defaultdict(int)
    for item in scored:
        domain_key = registrable_domain_hint(hostname_from_url(item[1].canonical_url))
        if domain_counts[domain_key] >= max_per_domain:
            continue
        selected.append(item)
        domain_counts[domain_key] += 1
        if len(selected) >= limit:
            break

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
    return hits, len(aggregates)
