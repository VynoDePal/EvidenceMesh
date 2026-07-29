from __future__ import annotations

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType
from evidencemesh.providers.base import SearchProvider, bounded_json_request, strip_markup

MWMBL_RESULTS_LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"


class MwmblProvider(SearchProvider):
    """Search Mwmbl's independently crawled, community-maintained index."""

    name = "mwmbl"
    supported_profiles = frozenset({SearchProfile.WEB})
    source_type = SourceType.WEB
    query_budget = 1
    minimum_cache_ttl_seconds = 86_400

    def __init__(self, endpoint: str, client: httpx.AsyncClient) -> None:
        self.endpoint = endpoint
        self.client = client

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        try:
            payload = await bounded_json_request(
                self.client,
                "GET",
                self.endpoint,
                params={"q": query},
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Mwmbl request failed: {type(exc).__name__}") from exc

        items = payload.get("results")
        if not isinstance(items, list):
            raise ProviderError(
                "Mwmbl response must contain a results array",
                kind="invalid_schema",
            )

        results: list[ProviderResult] = []
        for item in items[: min(max(request.limit * 3, 20), 50)]:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            title_value = item.get("title")
            content_value = item.get("content")
            title = strip_markup(title_value if isinstance(title_value, str) else None) or url
            snippet = strip_markup(content_value if isinstance(content_value, str) else None)
            results.append(
                ProviderResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    provider=self.name,
                    rank=len(results) + 1,
                    query=query,
                    source_type=SourceType.WEB,
                    provider_score=item.get("score"),
                    metadata={
                        "index_kind": "independent_community_crawl",
                        "origin_engine": item.get("engine"),
                        "result_license_url": MWMBL_RESULTS_LICENSE_URL,
                    },
                )
            )
        return results
