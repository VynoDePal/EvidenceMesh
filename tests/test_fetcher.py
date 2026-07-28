from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from conftest import PermissiveGuard

from evidencemesh.config import Settings
from evidencemesh.errors import FetchError, UnsupportedContentError
from evidencemesh.fetcher import RobotsPolicy, WebFetcher


def fetch_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        enabled_providers=[],
        cache_path=tmp_path / "cache.sqlite3",
        respect_robots_txt=False,
        max_download_bytes=100_000,
        **overrides,
    )


@pytest.mark.asyncio
async def test_fetcher_extracts_html(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><title>Alpha</title><main>Useful alpha evidence.</main></html>",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    guard = PermissiveGuard()
    fetcher = WebFetcher(fetch_settings(tmp_path), client=client, guard=guard)
    document = await fetcher.fetch("https://example.com/a")
    assert document.title == "Alpha"
    assert "Useful alpha evidence" in document.text
    assert document.media_type == "text/html"
    assert guard.urls == ["https://example.com/a"]
    await client.aclose()


@pytest.mark.asyncio
async def test_fetcher_revalidates_redirect(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(
            200, content=b"final evidence", headers={"content-type": "text/plain"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    guard = PermissiveGuard()
    fetcher = WebFetcher(fetch_settings(tmp_path), client=client, guard=guard)
    document = await fetcher.fetch("https://example.com/start")
    assert document.canonical_url == "https://example.com/final"
    assert guard.urls == ["https://example.com/start", "https://example.com/final"]
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(404), "HTTP 404"),
        (
            httpx.Response(
                200,
                content=b"small",
                headers={"content-length": "100001", "content-type": "text/plain"},
            ),
            "byte limit",
        ),
        (httpx.Response(302), "no Location"),
    ],
)
async def test_fetcher_rejects_bad_responses(
    tmp_path: Path,
    response: httpx.Response,
    message: str,
) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response))
    fetcher = WebFetcher(
        fetch_settings(tmp_path),
        client=client,
        guard=PermissiveGuard(),
    )
    with pytest.raises(FetchError, match=message):
        await fetcher.fetch("https://example.com/a")
    await client.aclose()


@pytest.mark.asyncio
async def test_fetcher_enforces_streaming_limit(tmp_path: Path) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"x" * 100_001,
                headers={"content-type": "text/plain", "content-length": "invalid"},
            )
        )
    )
    fetcher = WebFetcher(
        fetch_settings(tmp_path),
        client=client,
        guard=PermissiveGuard(),
    )
    with pytest.raises(FetchError, match="byte limit"):
        await fetcher.fetch("https://example.com/a")
    await client.aclose()


@pytest.mark.asyncio
async def test_fetcher_rejects_unsupported_content(tmp_path: Path) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"image",
                headers={"content-type": "image/png"},
            )
        )
    )
    fetcher = WebFetcher(
        fetch_settings(tmp_path),
        client=client,
        guard=PermissiveGuard(),
    )
    with pytest.raises(UnsupportedContentError):
        await fetcher.fetch("https://example.com/image")
    await client.aclose()


@pytest.mark.asyncio
async def test_fetcher_wraps_network_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = WebFetcher(
        fetch_settings(tmp_path),
        client=client,
        guard=PermissiveGuard(),
    )
    with pytest.raises(FetchError, match="network"):
        await fetcher.fetch("https://example.com/a")
    await client.aclose()


@pytest.mark.asyncio
async def test_robots_policy_parses_and_caches_rules() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            content=b"User-agent: *\nDisallow: /private\n",
            headers={"content-type": "text/plain"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    policy = RobotsPolicy(client, PermissiveGuard(), "EvidenceMesh/0.1")
    assert await policy.allowed("https://example.com/public")
    assert not await policy.allowed("https://example.com/private/page")
    assert calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_robots_policy_fails_open_on_unavailable_file() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    policy = RobotsPolicy(client, PermissiveGuard(), "EvidenceMesh/0.1")
    assert await policy.allowed("https://example.com/a")
    await client.aclose()
