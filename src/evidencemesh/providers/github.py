from __future__ import annotations

import re
from enum import StrEnum

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
_LEADING_REPOSITORY_INTENT = re.compile(
    r"^(?:(?:please\s+)?(?:find|locate|show)\s+(?:me\s+)?(?:the\s+)?|"
    r"(?:where\s+is|what\s+is)\s+(?:the\s+)?)?"
    r"(?:official\s+)?(?:github\s+)?"
    r"(?:(?:source\s+)?(?:repository|repo)|source\s+code)"
    r"\s+(?:for|of)\s+",
    re.IGNORECASE,
)
_GITHUB_QUALIFIER = re.compile(
    r"(?:^|\s)(?:archived|created|fork|forks|followers|good-first-issues|"
    r"help-wanted-issues|in|is|language|license|mirror|org|props|pushed|"
    r"repo|size|sponsor|stars|template|topic|topics|user|visibility):\S+",
    re.IGNORECASE,
)
_GITHUB_REPOSITORY_URL = re.compile(
    r"https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repository>[A-Za-z0-9_.-]+?)(?:\.git)?(?:[/?#].*)?$",
    re.IGNORECASE,
)
_OWNER_REPOSITORY = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repository>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)
_QUOTED_PHRASE = re.compile(r"[\"“](?P<phrase>[^\"”]{1,120})[\"”]")
_REPOSITORY_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+#-]*")
_GITHUB_QUERY_LIMIT = 256
_LEGACY_REPOSITORY_FIELDS = " in:name,description"
_ENTITY_REPOSITORY_FIELDS = " in:name,description,topics"
_LEADING_ARTICLES = frozenset({"a", "an", "the", "le", "la", "les", "un", "une"})
_ENTITY_BOUNDARIES = frozenset(
    {
        "api",
        "async",
        "automation",
        "backup",
        "browser",
        "build",
        "by",
        "client",
        "cli",
        "code",
        "command",
        "compiler",
        "cross-platform",
        "data",
        "database",
        "dependency",
        "editor",
        "extensible",
        "fast",
        "file",
        "finder",
        "formatter",
        "framework",
        "frontend",
        "from",
        "github",
        "go",
        "home",
        "http",
        "java",
        "javascript",
        "library",
        "linter",
        "management",
        "manager",
        "modal",
        "open",
        "orchestration",
        "package",
        "par",
        "php",
        "photo",
        "platform",
        "project",
        "python",
        "react",
        "repo",
        "repository",
        "runtime",
        "rust",
        "sdk",
        "self-hosted",
        "server",
        "sharing",
        "source",
        "terminal",
        "testing",
        "text",
        "tool",
        "toolkit",
        "typescript",
        "ui",
        "web",
        "workflow",
    }
)


class RepositoryQueryStrategy(StrEnum):
    """Versioned GitHub query strategies used by production and paired benchmarks."""

    LEGACY = "legacy-v1"
    ENTITY_ANCHOR = "entity-anchor-v2"


def _bounded_query(base: str, suffix: str = "") -> str:
    maximum_base_length = _GITHUB_QUERY_LIMIT - len(suffix)
    return f"{base[:maximum_base_length].rstrip()}{suffix}"


def _legacy_repository_query(query: str) -> str:
    compact = " ".join(query.split()).strip()
    candidate = _TRAILING_REPOSITORY_INTENT.sub("", compact).strip()
    if candidate:
        compact = candidate
    suffix = "" if _GITHUB_QUALIFIER.search(compact) else _LEGACY_REPOSITORY_FIELDS
    return _bounded_query(compact, suffix)


def _repository_reference(query: str) -> str | None:
    url_match = _GITHUB_REPOSITORY_URL.fullmatch(query)
    reference_match = _OWNER_REPOSITORY.fullmatch(query)
    match = url_match or reference_match
    if match is None:
        return None
    repository = match.group("repository").removesuffix(".git")
    return f"repo:{match.group('owner')}/{repository}"


def _repository_entity_anchor(query: str) -> str:
    compact = _LEADING_REPOSITORY_INTENT.sub("", query).strip()
    candidate = _TRAILING_REPOSITORY_INTENT.sub("", compact).strip(" ,.!?")
    if candidate:
        compact = candidate

    quoted = _QUOTED_PHRASE.search(compact)
    if quoted is not None:
        return quoted.group("phrase").strip()

    tokens = _REPOSITORY_TOKEN.findall(compact)
    while tokens and tokens[0].casefold() in _LEADING_ARTICLES:
        tokens.pop(0)
    if (
        len(tokens) >= 2
        and tokens[0][:1].isupper()
        and tokens[1].islower()
        and len(tokens[1]) <= 4
        and tokens[1].casefold() not in _ENTITY_BOUNDARIES
    ):
        tokens.pop(0)
    anchor: list[str] = []
    for token in tokens:
        folded = token.casefold()
        if anchor and (folded in _LEADING_ARTICLES or folded in _ENTITY_BOUNDARIES):
            break
        anchor.append(token)
        if len(anchor) == 4:
            break
    return " ".join(anchor) or compact


def normalize_repository_query(
    query: str,
    *,
    strategy: RepositoryQueryStrategy = RepositoryQueryStrategy.ENTITY_ANCHOR,
) -> str:
    """Turn natural-language repository intent into a bounded GitHub search query."""

    compact = " ".join(query.split()).strip()
    if strategy is RepositoryQueryStrategy.LEGACY:
        return _legacy_repository_query(compact)

    direct_reference = _repository_reference(compact)
    if direct_reference is not None:
        return _bounded_query(direct_reference)
    if _GITHUB_QUALIFIER.search(compact):
        return _bounded_query(compact)
    anchor = _repository_entity_anchor(compact)
    return _bounded_query(anchor, _ENTITY_REPOSITORY_FIELDS)


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
        query_strategy: RepositoryQueryStrategy = RepositoryQueryStrategy.ENTITY_ANCHOR,
    ) -> None:
        self.endpoint = endpoint
        self.client = client
        self.token = token
        self.query_strategy = RepositoryQueryStrategy(query_strategy)

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
                    "q": normalize_repository_query(query, strategy=self.query_strategy),
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
                        "query_strategy": self.query_strategy.value,
                        "stars": item.get("stargazers_count"),
                    },
                )
            )
        return results
