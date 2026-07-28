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


class ExaProvider(SearchProvider):
    name = "exa"

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        body: dict[str, object] = {
            "query": query,
            "numResults": min(max(request.limit * 3, 20), 100),
            "type": "auto",
            "contents": {"highlights": {"maxCharacters": 1_000}},
        }
        if request.domains:
            body["includeDomains"] = request.domains
        if request.exclude_domains:
            body["excludeDomains"] = request.exclude_domains
        try:
            payload = await bounded_json_request(
                self.client,
                "POST",
                "https://api.exa.ai/search",
                json=body,
                headers={"x-api-key": self.api_key},
            )
            items = payload.get("results", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Exa request failed: {type(exc).__name__}") from exc
        results: list[ProviderResult] = []
        for rank, item in enumerate(items, start=1):
            url = item.get("url")
            if not url:
                continue
            highlights = item.get("highlights") or []
            results.append(
                ProviderResult(
                    title=strip_markup(item.get("title")) or url,
                    url=url,
                    snippet=strip_markup(" ".join(highlights) or item.get("text")),
                    provider=self.name,
                    rank=rank,
                    query=query,
                    published_at=parse_datetime(item.get("publishedDate")),
                    source_type=SourceType(request.profile.value),
                    provider_score=item.get("score"),
                    metadata={"author": item.get("author"), "id": item.get("id")},
                )
            )
        return results
