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


def reconstruct_abstract(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        positioned.extend(
            (position, word)
            for position in positions
            if isinstance(position, int) and position >= 0
        )
    positioned.sort()
    return " ".join(word for _, word in positioned)


class OpenAlexProvider(SearchProvider):
    name = "openalex"
    supported_profiles = frozenset({SearchProfile.ACADEMIC})
    source_type = SourceType.ACADEMIC
    query_budget = 2

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        client: httpx.AsyncClient,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.client = client

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        try:
            payload = await bounded_json_request(
                self.client,
                "GET",
                self.endpoint,
                params={
                    "api_key": self.api_key,
                    "search": query,
                    "per-page": min(max(request.limit * 2, 10), 50),
                },
            )
            items = payload.get("results", [])
            if not isinstance(items, list):
                raise ValueError("results is not a list")
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"OpenAlex request failed: {type(exc).__name__}") from exc

        results: list[ProviderResult] = []
        for rank, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            title = strip_markup(item.get("display_name") or item.get("title"))
            primary_location = item.get("primary_location")
            location_url = (
                primary_location.get("landing_page_url")
                if isinstance(primary_location, dict)
                else None
            )
            doi = item.get("doi")
            url = location_url or doi or item.get("id")
            if not isinstance(url, str) or not url:
                continue
            author_names: list[str] = []
            for authorship in item.get("authorships") or []:
                if not isinstance(authorship, dict):
                    continue
                author = authorship.get("author")
                if isinstance(author, dict) and isinstance(author.get("display_name"), str):
                    author_names.append(author["display_name"])
            abstract = reconstruct_abstract(item.get("abstract_inverted_index"))
            results.append(
                ProviderResult(
                    title=title or url,
                    url=url,
                    snippet=abstract or ", ".join(author_names[:10]),
                    provider=self.name,
                    rank=rank,
                    query=query,
                    published_at=parse_datetime(item.get("publication_date")),
                    source_type=SourceType.ACADEMIC,
                    metadata={
                        "authors": author_names[:20],
                        "cited_by_count": item.get("cited_by_count"),
                        "doi": doi,
                        "openalex_id": item.get("id"),
                        "type": item.get("type"),
                    },
                )
            )
        return results
