from __future__ import annotations

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType
from evidencemesh.providers.base import (
    SearchProvider,
    bounded_json_request,
    parse_datetime,
    strip_markup,
)


class BraveProvider(SearchProvider):
    name = "brave"

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        vertical = "news" if request.profile is SearchProfile.NEWS else "web"
        endpoint = f"https://api.search.brave.com/res/v1/{vertical}/search"
        params: dict[str, str | int] = {
            "q": query,
            "count": min(max(request.limit * 3, 20), 50),
            "search_lang": request.language.split("-")[0],
            "safesearch": request.safe_search.value,
        }
        if request.time_range:
            params["freshness"] = {
                "day": "pd",
                "week": "pw",
                "month": "pm",
                "year": "py",
            }[request.time_range.value]
        try:
            payload = await bounded_json_request(
                self.client,
                "GET",
                endpoint,
                params=params,
                headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Brave request failed: {type(exc).__name__}") from exc
        items = payload.get(vertical, {}).get("results") or payload.get("results") or []
        return [
            ProviderResult(
                title=strip_markup(item.get("title")) or item["url"],
                url=item["url"],
                snippet=strip_markup(item.get("description")),
                provider=self.name,
                rank=rank,
                query=query,
                published_at=parse_datetime(item.get("page_age") or item.get("age")),
                source_type=SourceType(request.profile.value),
            )
            for rank, item in enumerate(items, start=1)
            if item.get("url")
        ]
