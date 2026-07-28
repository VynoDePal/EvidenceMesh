from __future__ import annotations

from urllib.parse import quote

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType
from evidencemesh.providers.base import SearchProvider, bounded_json_request, strip_markup


class WikipediaProvider(SearchProvider):
    name = "wikipedia"
    supported_profiles = frozenset({SearchProfile.WEB, SearchProfile.ACADEMIC})

    def __init__(self, url_template: str, client: httpx.AsyncClient) -> None:
        self.url_template = url_template
        self.client = client

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        language = request.language.lower().split("-")[0]
        endpoint = self.url_template.format(language=language)
        params: dict[str, str | int] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": min(max(request.limit * 2, 10), 50),
            "utf8": "1",
            "format": "json",
            "origin": "*",
        }
        try:
            payload = await bounded_json_request(
                self.client,
                "GET",
                endpoint,
                params=params,
            )
            items = payload.get("query", {}).get("search", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Wikipedia request failed: {type(exc).__name__}") from exc
        results: list[ProviderResult] = []
        for rank, item in enumerate(items, start=1):
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            url = f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
            results.append(
                ProviderResult(
                    title=title,
                    url=url,
                    snippet=strip_markup(item.get("snippet")),
                    provider=self.name,
                    rank=rank,
                    query=query,
                    source_type=SourceType.REFERENCE,
                    metadata={
                        "pageid": item.get("pageid"),
                        "wordcount": item.get("wordcount"),
                    },
                )
            )
        return results
