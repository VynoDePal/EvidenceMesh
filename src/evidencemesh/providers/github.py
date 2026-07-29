from __future__ import annotations

import re

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType
from evidencemesh.providers.base import (
    SearchProvider,
    bounded_json_request,
    parse_datetime,
    strip_markup,
)

_TRAILING_REPOSITORY_INTENT = re.compile(
    r"(?:\s+(?:official\s+)?(?:github\s+)?"
    r"(?:repository|repo|source\s+code|open[\s-]+source\s+project|project))+\s*[.!?]*$",
    re.IGNORECASE,
)
_GITHUB_IN_QUALIFIER = re.compile(r"(?:^|\s)in:(?:name|description|readme)\b", re.IGNORECASE)
_GITHUB_QUERY_LIMIT = 256
_REPOSITORY_FIELDS = " in:name,description"


def normalize_repository_query(query: str) -> str:
    """Turn natural-language repository intent into a bounded GitHub search query."""

    compact = " ".join(query.split()).strip()
    candidate = _TRAILING_REPOSITORY_INTENT.sub("", compact).strip()
    if candidate:
        compact = candidate
    suffix = "" if _GITHUB_IN_QUALIFIER.search(compact) else _REPOSITORY_FIELDS
    maximum_base_length = _GITHUB_QUERY_LIMIT - len(suffix)
    compact = compact[:maximum_base_length].rstrip()
    return f"{compact}{suffix}"


class GitHubProvider(SearchProvider):
    """Search public repositories; code-content search is deliberately out of scope."""

    name = "github"
    supported_profiles = frozenset({SearchProfile.CODE})
    source_type = SourceType.CODE
    query_budget = 1

    def __init__(
        self,
        endpoint: str,
        client: httpx.AsyncClient,
        token: str | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.client = client
        self.token = token

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            payload = await bounded_json_request(
                self.client,
                "GET",
                self.endpoint,
                params={
                    "q": normalize_repository_query(query),
                    "per_page": min(max(request.limit * 2, 10), 50),
                    "page": 1,
                },
                headers=headers,
            )
            items = payload.get("items", [])
            if not isinstance(items, list):
                raise ValueError("items is not a list")
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"GitHub request failed: {type(exc).__name__}") from exc

        results: list[ProviderResult] = []
        for rank, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            url = item.get("html_url")
            name = item.get("full_name") or item.get("name")
            if not isinstance(url, str) or not url or not isinstance(name, str) or not name:
                continue
            license_value = item.get("license")
            license_name = license_value.get("spdx_id") if isinstance(license_value, dict) else None
            results.append(
                ProviderResult(
                    title=name,
                    url=url,
                    snippet=strip_markup(item.get("description")),
                    provider=self.name,
                    rank=rank,
                    query=query,
                    published_at=parse_datetime(item.get("updated_at")),
                    source_type=SourceType.CODE,
                    provider_score=(
                        float(item["score"]) if isinstance(item.get("score"), int | float) else None
                    ),
                    metadata={
                        "default_branch": item.get("default_branch"),
                        "fork": bool(item.get("fork")),
                        "language": item.get("language"),
                        "license": license_name,
                        "stars": item.get("stargazers_count"),
                    },
                )
            )
        return results
