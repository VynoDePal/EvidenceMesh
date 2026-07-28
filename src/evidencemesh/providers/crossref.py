from __future__ import annotations

from datetime import UTC, datetime

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType
from evidencemesh.providers.base import SearchProvider, bounded_json_request, strip_markup


def _crossref_date(item: dict[str, object]) -> datetime | None:
    for field in ("published-online", "published-print", "published", "issued", "created"):
        value = item.get(field)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
            continue
        try:
            year, *rest = [int(part) for part in parts[0]]
            month = rest[0] if rest else 1
            day = rest[1] if len(rest) > 1 else 1
            return datetime(year, month, day, tzinfo=UTC)
        except (TypeError, ValueError):
            continue
    return None


class CrossrefProvider(SearchProvider):
    name = "crossref"
    supported_profiles = frozenset({SearchProfile.ACADEMIC})

    def __init__(self, endpoint: str, client: httpx.AsyncClient, mailto: str | None = None) -> None:
        self.endpoint = endpoint
        self.client = client
        self.mailto = mailto

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        params: dict[str, str | int] = {
            "query.bibliographic": query,
            "rows": min(max(request.limit * 3, 20), 100),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        try:
            payload = await bounded_json_request(
                self.client,
                "GET",
                self.endpoint,
                params=params,
            )
            items = payload.get("message", {}).get("items", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Crossref request failed: {type(exc).__name__}") from exc
        results: list[ProviderResult] = []
        for rank, item in enumerate(items, start=1):
            titles = item.get("title") or []
            title = strip_markup(titles[0] if titles else "")
            doi = item.get("DOI")
            url = f"https://doi.org/{doi}" if doi else item.get("URL")
            if not url:
                continue
            author_names = []
            for author in item.get("author") or []:
                name = " ".join(
                    part for part in [author.get("given", ""), author.get("family", "")] if part
                )
                if name:
                    author_names.append(name)
            abstract = strip_markup(item.get("abstract"))
            snippet = abstract or ", ".join(author_names[:5])
            results.append(
                ProviderResult(
                    title=title or str(url),
                    url=str(url),
                    snippet=snippet,
                    provider=self.name,
                    rank=rank,
                    query=query,
                    published_at=_crossref_date(item),
                    source_type=SourceType.ACADEMIC,
                    metadata={
                        "doi": doi,
                        "type": item.get("type"),
                        "is_referenced_by_count": item.get("is-referenced-by-count"),
                    },
                )
            )
        return results
