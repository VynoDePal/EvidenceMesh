"""Deterministic provider routing with explicit per-source query budgets."""

from __future__ import annotations

from dataclasses import dataclass

from evidencemesh.models import SearchProfile, SourceType
from evidencemesh.providers.base import SearchProvider


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    provider: SearchProvider
    queries: tuple[str, ...]
    source_family: SourceType


def build_provider_routes(
    providers: list[SearchProvider],
    *,
    profile: SearchProfile,
    queries: list[str],
) -> list[ProviderRoute]:
    """Route only compatible sources and cap expensive or rate-limited verticals."""

    routes: list[ProviderRoute] = []
    for provider in providers:
        if not provider.supports(profile):
            continue
        budget = provider.query_budget
        routed_queries = queries if budget is None else queries[:budget]
        if not routed_queries:
            continue
        routes.append(
            ProviderRoute(
                provider=provider,
                queries=tuple(routed_queries),
                source_family=provider.source_family(profile),
            )
        )
    return routes
