from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from evidencemesh.config import Settings
from evidencemesh.errors import ProviderError
from evidencemesh.models import (
    SafeSearch,
    SearchProfile,
    SearchRequest,
    TimeRange,
)
from evidencemesh.providers.base import bounded_json_request, parse_datetime, strip_markup
from evidencemesh.providers.brave import BraveProvider
from evidencemesh.providers.crossref import CrossrefProvider, _crossref_date
from evidencemesh.providers.ddgs import DDGSProvider
from evidencemesh.providers.exa import ExaProvider
from evidencemesh.providers.factory import build_providers
from evidencemesh.providers.firecrawl import FirecrawlProvider
from evidencemesh.providers.searxng import SearxngProvider
from evidencemesh.providers.tavily import TavilyProvider
from evidencemesh.providers.wikipedia import WikipediaProvider


def json_client(
    payload: dict[str, Any],
    captured: list[httpx.Request] | None = None,
    *,
    status: int = 200,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("value", "expected_year"),
    [
        ("2026-07-28T12:00:00Z", 2026),
        ("Tue, 28 Jul 2026 12:00:00 GMT", 2026),
        (0, None),
        ("not-a-date", None),
        (datetime.fromisoformat("2025-01-01"), 2025),
    ],
)
def test_parse_datetime(value: object, expected_year: int | None) -> None:
    parsed = parse_datetime(value)
    assert (parsed.year if parsed else None) == expected_year
    if parsed:
        assert parsed.tzinfo is not None


def test_strip_markup() -> None:
    assert strip_markup("<b>Alpha</b>&nbsp; beta") == "Alpha beta"
    assert strip_markup(None) == ""


@pytest.mark.asyncio
async def test_bounded_json_request_validates_size_and_shape() -> None:
    valid_client = json_client({"ok": True})
    assert await bounded_json_request(
        valid_client,
        "GET",
        "https://example.com",
        max_bytes=100,
    ) == {"ok": True}
    await valid_client.aclose()

    oversized = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b'{"payload":"too large"}',
                headers={"content-length": "1000"},
            )
        )
    )
    with pytest.raises(ValueError, match="byte limit"):
        await bounded_json_request(
            oversized,
            "GET",
            "https://example.com",
            max_bytes=20,
        )
    await oversized.aclose()

    list_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"[]"))
    )
    with pytest.raises(ValueError, match="JSON object"):
        await bounded_json_request(list_client, "GET", "https://example.com")
    await list_client.aclose()


@pytest.mark.asyncio
async def test_searxng_provider_maps_request_and_result() -> None:
    captured: list[httpx.Request] = []
    client = json_client(
        {
            "results": [
                {
                    "title": "<b>Alpha</b>",
                    "url": "https://example.com/a",
                    "content": "Useful <em>evidence</em>",
                    "publishedDate": "2026-07-01",
                    "engines": ["one", "two"],
                },
                {"title": "missing URL"},
                "invalid item",
            ]
        },
        captured,
    )
    provider = SearxngProvider("https://search.example/", client)
    results = await provider.search(
        "alpha",
        SearchRequest(
            query="alpha",
            profile=SearchProfile.NEWS,
            safe_search=SafeSearch.STRICT,
            time_range=TimeRange.WEEK,
        ),
    )
    assert len(results) == 1
    assert results[0].title == "Alpha"
    assert results[0].source_type.value == "news"
    assert results[0].metadata["engines"] == ["one", "two"]
    assert results[0].metadata["unresponsive_engines"] == []
    assert captured[0].url.params["categories"] == "news"
    assert captured[0].url.params["safesearch"] == "2"
    assert captured[0].url.params["time_range"] == "week"
    await client.aclose()


@pytest.mark.asyncio
async def test_searxng_provider_rejects_total_upstream_failure() -> None:
    client = json_client(
        {
            "results": [],
            "unresponsive_engines": [
                ["duckduckgo", "timeout"],
                ["brave", "rate limit"],
            ],
        }
    )
    provider = SearxngProvider("https://search.example", client)
    with pytest.raises(ProviderError, match="2 upstream engine"):
        await provider.search("alpha", SearchRequest(query="alpha"))
    await client.aclose()


@pytest.mark.asyncio
async def test_wikipedia_provider_builds_language_url() -> None:
    client = json_client(
        {
            "query": {
                "search": [
                    {
                        "title": "Recherche scientifique",
                        "snippet": "<span>Résumé</span>",
                        "pageid": 12,
                    }
                ]
            }
        }
    )
    provider = WikipediaProvider(
        "https://{language}.wikipedia.org/w/api.php",
        client,
    )
    result = (
        await provider.search(
            "recherche",
            SearchRequest(query="recherche", language="fr"),
        )
    )[0]
    assert result.url == "https://fr.wikipedia.org/wiki/Recherche_scientifique"
    assert result.metadata["pageid"] == 12
    await client.aclose()


def test_crossref_date_parsing() -> None:
    assert _crossref_date({"issued": {"date-parts": [[2024, 6, 2]]}}) == datetime(
        2024,
        6,
        2,
        tzinfo=UTC,
    )
    assert _crossref_date({"issued": {"date-parts": [["bad"]]}}) is None
    assert _crossref_date({}) is None


@pytest.mark.asyncio
async def test_crossref_provider_prefers_doi_and_abstract() -> None:
    captured: list[httpx.Request] = []
    client = json_client(
        {
            "message": {
                "items": [
                    {
                        "title": ["<b>Research</b> paper"],
                        "DOI": "10.1234/example",
                        "abstract": "<jats:p>Alpha evidence</jats:p>",
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                        "issued": {"date-parts": [[2025]]},
                        "type": "journal-article",
                    }
                ]
            }
        },
        captured,
    )
    provider = CrossrefProvider("https://api.crossref.test/works", client, "dev@example.com")
    result = (
        await provider.search(
            "alpha",
            SearchRequest(query="alpha", profile=SearchProfile.ACADEMIC),
        )
    )[0]
    assert result.url == "https://doi.org/10.1234/example"
    assert result.snippet == "Alpha evidence"
    assert captured[0].url.params["mailto"] == "dev@example.com"
    await client.aclose()


@pytest.mark.asyncio
async def test_brave_provider_uses_news_vertical_and_key() -> None:
    captured: list[httpx.Request] = []
    client = json_client(
        {
            "news": {
                "results": [
                    {
                        "title": "Alpha news",
                        "url": "https://news.example/a",
                        "description": "News evidence",
                        "age": "2026-07-01",
                    }
                ]
            }
        },
        captured,
    )
    provider = BraveProvider("secret", client)
    result = (
        await provider.search(
            "alpha",
            SearchRequest(
                query="alpha",
                profile=SearchProfile.NEWS,
                time_range=TimeRange.DAY,
            ),
        )
    )[0]
    assert result.source_type.value == "news"
    assert "/news/search" in captured[0].url.path
    assert captured[0].headers["x-subscription-token"] == "secret"
    assert captured[0].url.params["freshness"] == "pd"
    await client.aclose()


@pytest.mark.asyncio
async def test_tavily_provider_maps_score_and_filters() -> None:
    captured: list[httpx.Request] = []
    client = json_client(
        {
            "results": [
                {
                    "title": "Alpha",
                    "url": "https://example.com/a",
                    "content": "Evidence",
                    "score": 0.9,
                }
            ]
        },
        captured,
    )
    provider = TavilyProvider("key", client)
    result = (
        await provider.search(
            "alpha",
            SearchRequest(
                query="alpha",
                domains=["example.com"],
                exclude_domains=["other.example"],
            ),
        )
    )[0]
    body = json.loads(captured[0].content)
    assert body["include_domains"] == ["example.com"]
    assert body["exclude_domains"] == ["other.example"]
    assert result.provider_score == 0.9
    await client.aclose()


@pytest.mark.asyncio
async def test_exa_provider_maps_highlights_and_metadata() -> None:
    captured: list[httpx.Request] = []
    client = json_client(
        {
            "results": [
                {
                    "title": "Alpha",
                    "url": "https://example.com/a",
                    "highlights": ["One", "Two"],
                    "author": "Ada",
                    "id": "doc-1",
                    "score": 0.8,
                }
            ]
        },
        captured,
    )
    provider = ExaProvider("key", client)
    result = (
        await provider.search(
            "alpha",
            SearchRequest(query="alpha", domains=["example.com"]),
        )
    )[0]
    assert result.snippet == "One Two"
    assert result.metadata == {"author": "Ada", "id": "doc-1"}
    assert captured[0].headers["x-api-key"] == "key"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"data": {"web": [{"title": "Alpha", "url": "https://example.com/a"}]}},
        {"data": [{"title": "Alpha", "url": "https://example.com/a"}]},
    ],
)
async def test_firecrawl_provider_accepts_cloud_payload_shapes(
    payload: dict[str, Any],
) -> None:
    client = json_client(payload)
    results = await FirecrawlProvider("https://firecrawl.test", client, "key").search(
        "alpha",
        SearchRequest(query="alpha"),
    )
    assert results[0].url == "https://example.com/a"
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_http_error_is_wrapped() -> None:
    client = json_client({}, status=503)
    with pytest.raises(ProviderError, match="SearXNG"):
        await SearxngProvider("https://search.example", client).search(
            "alpha",
            SearchRequest(query="alpha"),
        )
    await client.aclose()


class FakeDDGS:
    last_call: tuple[str, dict[str, Any]] | None = None

    def __enter__(self) -> FakeDDGS:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def text(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        type(self).last_call = ("text", kwargs)
        return [{"title": "Alpha", "href": "https://example.com/a", "body": "Evidence"}]

    def news(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        type(self).last_call = ("news", kwargs)
        return [{"title": "News", "url": "https://news.example/a", "description": "Item"}]


@pytest.mark.asyncio
async def test_ddgs_provider_web_and_news(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("evidencemesh.providers.ddgs.DDGS", FakeDDGS)
    provider = DDGSProvider()
    web = await provider.search(
        "alpha",
        SearchRequest(
            query="alpha",
            time_range=TimeRange.MONTH,
            safe_search=SafeSearch.OFF,
        ),
    )
    assert web[0].url == "https://example.com/a"
    assert FakeDDGS.last_call == (
        "text",
        {
            "region": "wt-wt",
            "safesearch": "off",
            "timelimit": "m",
            "max_results": 30,
        },
    )
    news = await provider.search(
        "alpha",
        SearchRequest(query="alpha", profile=SearchProfile.NEWS),
    )
    assert news[0].source_type.value == "news"
    assert FakeDDGS.last_call is not None and FakeDDGS.last_call[0] == "news"


@pytest.mark.asyncio
async def test_provider_factory_keys_and_self_hosted_firecrawl(tmp_path: Path) -> None:
    settings = Settings(
        enabled_providers=[
            "searxng",
            "ddgs",
            "wikipedia",
            "crossref",
            "brave",
            "tavily",
            "exa",
            "firecrawl",
        ],
        brave_api_key="brave",
        tavily_api_key="tavily",
        exa_api_key="exa",
        firecrawl_url="http://127.0.0.1:3002",
        cache_path=tmp_path / "cache.sqlite3",
    )
    client = httpx.AsyncClient()
    providers, warnings = build_providers(settings, client)
    assert [provider.name for provider in providers] == settings.enabled_providers
    assert warnings == []
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_factory_warns_for_missing_optional_keys(tmp_path: Path) -> None:
    settings = Settings(
        enabled_providers=["brave", "tavily", "exa", "firecrawl"],
        cache_path=tmp_path / "cache.sqlite3",
    )
    client = httpx.AsyncClient()
    providers, warnings = build_providers(settings, client)
    assert providers == []
    assert len(warnings) == 4
    await client.aclose()
