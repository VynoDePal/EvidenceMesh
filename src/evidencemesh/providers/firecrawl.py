from __future__ import annotations

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderResult, SearchRequest, SourceType
from evidencemesh.providers.base import (
    SearchProvider,
    bounded_json_request,
    parse_datetime,
    strip_markup,
)


class FirecrawlProvider(SearchProvider):
    name = "firecrawl"

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.api_key = api_key

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body: dict[str, object] = {
            "query": query,
            "limit": min(max(request.limit * 3, 20), 100),
        }
        try:
            payload = await bounded_json_request(
                self.client,
                "POST",
                f"{self.base_url}/v2/search",
                json=body,
                headers=headers,
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Firecrawl request failed: {type(exc).__name__}") from exc
        data = payload.get("data", {})
        items = (data.get("web") or data.get("news") or []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ProviderError("Firecrawl returned an unexpected search payload")
        return [
            ProviderResult(
                title=strip_markup(item.get("title")) or item["url"],
                url=item["url"],
                snippet=strip_markup(
                    item.get("description") or item.get("markdown") or item.get("content")
                ),
                provider=self.name,
                rank=rank,
                query=query,
                published_at=parse_datetime(
                    item.get("publishedDate") or item.get("published_date")
                ),
                source_type=SourceType(request.profile.value),
            )
            for rank, item in enumerate(items, start=1)
            if isinstance(item, dict) and item.get("url")
        ]
