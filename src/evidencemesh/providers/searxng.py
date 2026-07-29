from __future__ import annotations

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import (
    ProviderResult,
    SafeSearch,
    SearchProfile,
    SearchRequest,
    SourceType,
)
from evidencemesh.providers.base import (
    SearchProvider,
    bounded_json_request,
    parse_datetime,
    strip_markup,
)


class SearxngProvider(SearchProvider):
    name = "searxng"
    supported_profiles = frozenset({SearchProfile.WEB, SearchProfile.NEWS})

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient,
        *,
        name: str = "searxng",
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.client = client

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        categories = {
            SearchProfile.WEB: "general",
            SearchProfile.NEWS: "news",
            SearchProfile.ACADEMIC: "science",
            SearchProfile.CODE: "it",
        }
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "categories": categories[request.profile],
            "language": request.language,
            "safesearch": {
                SafeSearch.OFF: 0,
                SafeSearch.MODERATE: 1,
                SafeSearch.STRICT: 2,
            }[request.safe_search],
        }
        if request.time_range:
            params["time_range"] = request.time_range.value
        try:
            payload = await bounded_json_request(
                self.client,
                "GET",
                f"{self.base_url}/search",
                params=params,
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"SearXNG request failed: {type(exc).__name__}") from exc
        items = payload.get("results", [])
        if not isinstance(items, list):
            raise ProviderError("SearXNG response has an invalid results field")
        unresponsive_values = payload.get("unresponsive_engines", [])
        if not isinstance(unresponsive_values, list):
            unresponsive_values = []
        unresponsive_engines = sorted(
            {
                value[0].strip()
                for value in unresponsive_values
                if isinstance(value, list)
                and value
                and isinstance(value[0], str)
                and value[0].strip()
            }
        )
        if not items and unresponsive_values:
            raise ProviderError(
                "SearXNG returned no results while "
                f"{len(unresponsive_values)} upstream engine(s) were unavailable: "
                f"{', '.join(unresponsive_engines) or 'unknown'}",
                kind="upstream_unavailable",
                upstream_engines=tuple(unresponsive_engines),
            )
        source_type = SourceType(request.profile.value)
        results: list[ProviderResult] = []
        for rank, item in enumerate(items[: max(request.limit * 3, 20)], start=1):
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not url:
                continue
            engine_values = item.get("engines", [])
            engines = (
                sorted(
                    {
                        engine.strip()
                        for engine in engine_values
                        if isinstance(engine, str) and engine.strip()
                    }
                )
                if isinstance(engine_values, list)
                else []
            )
            results.append(
                ProviderResult(
                    title=strip_markup(item.get("title")) or url,
                    url=url,
                    snippet=strip_markup(item.get("content")),
                    provider=self.name,
                    rank=rank,
                    query=query,
                    published_at=parse_datetime(
                        item.get("publishedDate") or item.get("published_date")
                    ),
                    source_type=source_type,
                    metadata={
                        "engines": engines,
                        "unresponsive_engines": unresponsive_engines,
                    },
                )
            )
        return results
