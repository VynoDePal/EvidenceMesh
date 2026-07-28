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
                    "q": query,
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
