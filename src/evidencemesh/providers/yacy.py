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


class YaCyProvider(SearchProvider):
    """Search an operator-controlled YaCy index or YaCy peer network."""

    name = "yacy"
    supported_profiles = frozenset({SearchProfile.WEB})
    source_type = SourceType.WEB
    query_budget = 1
    minimum_cache_ttl_seconds = 3_600

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient,
        *,
        resource: str = "local",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/yacysearch.json"
        self.client = client
        self.resource = resource

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        params: dict[str, str | int] = {
            "query": query,
            "maximumRecords": min(max(request.limit * 3, 20), 50),
            "startRecord": 0,
            "resource": self.resource,
            "verify": "false",
            "contentdom": "text",
        }
        try:
            payload = await bounded_json_request(
                self.client,
                "GET",
                self.endpoint,
                params=params,
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"YaCy request failed: {type(exc).__name__}") from exc

        channels = payload.get("channels")
        if not isinstance(channels, list) or not channels or not isinstance(channels[0], dict):
            raise ProviderError("YaCy response must contain a channels array")
        items = channels[0].get("items")
        if not isinstance(items, list):
            raise ProviderError("YaCy response channel must contain an items array")

        results: list[ProviderResult] = []
        for item in items[: min(max(request.limit * 3, 20), 50)]:
            if not isinstance(item, dict):
                continue
            url = item.get("link") or item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            title_value = item.get("title")
            description_value = item.get("description")
            results.append(
                ProviderResult(
                    title=(
                        strip_markup(title_value if isinstance(title_value, str) else None) or url
                    ),
                    url=url,
                    snippet=strip_markup(
                        description_value if isinstance(description_value, str) else None
                    ),
                    provider=self.name,
                    rank=len(results) + 1,
                    query=query,
                    published_at=parse_datetime(item.get("pubDate")),
                    source_type=SourceType.WEB,
                    metadata={
                        "host": item.get("host"),
                        "index_kind": "independent_self_hosted",
                        "index_scope": self.resource,
                        "ranking": item.get("ranking"),
                    },
                )
            )
        return results
