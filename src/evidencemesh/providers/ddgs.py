from __future__ import annotations

import asyncio
from typing import Any

from ddgs import DDGS

from evidencemesh.errors import ProviderError
from evidencemesh.models import (
    ProviderResult,
    SafeSearch,
    SearchProfile,
    SearchRequest,
    SourceType,
)
from evidencemesh.providers.base import SearchProvider, parse_datetime, strip_markup


class DDGSProvider(SearchProvider):
    name = "ddgs"
    supported_profiles = frozenset({SearchProfile.WEB, SearchProfile.NEWS})
    query_budget = 1

    def _search_sync(self, query: str, request: SearchRequest) -> list[dict[str, Any]]:
        safe = {
            SafeSearch.OFF: "off",
            SafeSearch.MODERATE: "moderate",
            SafeSearch.STRICT: "on",
        }[request.safe_search]
        timelimit = (
            {
                "day": "d",
                "week": "w",
                "month": "m",
                "year": "y",
            }.get(request.time_range.value)
            if request.time_range
            else None
        )
        max_results = max(request.limit * 3, 20)
        with DDGS() as ddgs:
            if request.profile is SearchProfile.NEWS:
                return list(
                    ddgs.news(
                        query,
                        region="wt-wt",
                        safesearch=safe,
                        timelimit=timelimit,
                        max_results=max_results,
                    )
                )
            return list(
                ddgs.text(
                    query,
                    region="wt-wt",
                    safesearch=safe,
                    timelimit=timelimit,
                    max_results=max_results,
                )
            )

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        try:
            items = await asyncio.to_thread(self._search_sync, query, request)
        except Exception as exc:
            raise ProviderError(f"DDGS request failed: {type(exc).__name__}") from exc
        results: list[ProviderResult] = []
        for rank, item in enumerate(items, start=1):
            url = item.get("href") or item.get("url")
            if not url:
                continue
            results.append(
                ProviderResult(
                    title=strip_markup(item.get("title")) or url,
                    url=url,
                    snippet=strip_markup(item.get("body") or item.get("description")),
                    provider=self.name,
                    rank=rank,
                    query=query,
                    published_at=parse_datetime(item.get("date")),
                    source_type=SourceType(request.profile.value),
                    metadata={
                        "source": item.get("source"),
                    },
                )
            )
        return results
