from __future__ import annotations

import json

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType
from evidencemesh.providers.base import (
    SearchProvider,
    bounded_bytes_request,
    strip_markup,
)

WIBY_ATTRIBUTION_URL = "https://wiby.me/"


class WibyProvider(SearchProvider):
    """Search Wiby's independently crawled small-web index."""

    name = "wiby"
    supported_profiles = frozenset({SearchProfile.WEB})
    source_type = SourceType.WEB
    query_budget = 1

    def __init__(self, endpoint: str, client: httpx.AsyncClient) -> None:
        self.endpoint = endpoint
        self.client = client

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        try:
            raw = await bounded_bytes_request(
                self.client,
                "GET",
                self.endpoint,
                params={"q": query},
            )
            payload = json.loads(raw)
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(f"Wiby request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, list):
            raise ProviderError("Wiby response must be a JSON array")

        results: list[ProviderResult] = []
        for item in payload[: max(request.limit * 3, 20)]:
            if not isinstance(item, dict):
                continue
            url = item.get("URL") or item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            title_value = item.get("Title") or item.get("title")
            description_value = item.get("Description") or item.get("description")
            snippet_value = item.get("Snippet") or item.get("snippet")
            title = strip_markup(title_value if isinstance(title_value, str) else None) or url
            description = strip_markup(
                description_value if isinstance(description_value, str) else None
            )
            snippet = description or strip_markup(
                snippet_value if isinstance(snippet_value, str) else None
            )
            results.append(
                ProviderResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    provider=self.name,
                    rank=len(results) + 1,
                    query=query,
                    source_type=SourceType.WEB,
                    metadata={
                        "attribution_url": WIBY_ATTRIBUTION_URL,
                        "index_kind": "independent_crawl",
                    },
                )
            )
        return results
