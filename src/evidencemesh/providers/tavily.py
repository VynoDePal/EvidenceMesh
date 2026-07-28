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


class TavilyProvider(SearchProvider):
    name = "tavily"

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        body: dict[str, object] = {
            "query": query,
            "max_results": min(max(request.limit * 3, 20), 50),
            "search_depth": "basic",
            "topic": "news" if request.profile is SearchProfile.NEWS else "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_domains": request.domains,
            "exclude_domains": request.exclude_domains,
        }
        if request.time_range:
            body["time_range"] = request.time_range.value
        try:
            payload = await bounded_json_request(
                self.client,
                "POST",
                "https://api.tavily.com/search",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            items = payload.get("results", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Tavily request failed: {type(exc).__name__}") from exc
        return [
            ProviderResult(
                title=strip_markup(item.get("title")) or item["url"],
                url=item["url"],
                snippet=strip_markup(item.get("content")),
                provider=self.name,
                rank=rank,
                query=query,
                published_at=parse_datetime(item.get("published_date")),
                source_type=SourceType(request.profile.value),
                provider_score=item.get("score"),
            )
            for rank, item in enumerate(items, start=1)
            if item.get("url")
        ]
