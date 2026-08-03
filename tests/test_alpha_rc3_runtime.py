from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from conftest import PermissiveGuard

from evidencemesh.config import Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError
from evidencemesh.fetcher import WebFetcher
from evidencemesh.governor import ClosedAlphaSession, SQLiteBudgetGovernor
from evidencemesh.models import SearchRequest
from evidencemesh.providers.ddgs import DDGSProvider
from evidencemesh.providers.searxng import SearxngProvider
from evidencemesh.providers.tavily import TavilyProvider
from evidencemesh.providers.wikipedia import WikipediaProvider


def _settings(tmp_path: Path, *, robots: bool = False) -> Settings:
    return Settings(
        enabled_providers=[],
        cache_path=tmp_path / "cache.sqlite3",
        respect_robots_txt=robots,
        max_download_bytes=100_000,
    )


def _governor(tmp_path: Path, *, profile: str = "community") -> SQLiteBudgetGovernor:
    return SQLiteBudgetGovernor(
        tmp_path / "private" / "ledger.sqlite3",
        ClosedAlphaSession(
            participant_code="p-0000000000000001",
            session_code="s-00000000000000000000000000000001",
            profile=profile,
        ),
    )


@pytest.mark.asyncio
async def test_provider_plan_over_six_is_rejected_before_any_transport(tmp_path: Path) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": [], "query": {"search": []}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor = _governor(tmp_path, profile="quality")
    engine = EvidenceMesh(
        _settings(tmp_path),
        providers=[
            SearxngProvider("https://searx.invalid", client),
            WikipediaProvider("https://{language}.wikipedia.invalid/w/api.php", client),
            TavilyProvider("synthetic-not-a-secret", client),
        ],
        client=client,
        governor=governor,
    )
    try:
        with pytest.raises(BudgetExceededError):
            await engine.search(
                SearchRequest(
                    query="alpha evidence",
                    query_variants=["alpha official", "alpha docs", "alpha history"],
                    use_cache=False,
                )
            )
        assert calls == 0
        snapshot = await governor.snapshot()
        assert snapshot["global_attempts"] == 0
    finally:
        await engine.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_audited_provider_uses_one_permit_and_cache_true_fails_before_transport(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "query": {
                    "search": [
                        {
                            "title": "Alpha",
                            "snippet": "Offline evidence",
                            "pageid": 1,
                            "wordcount": 2,
                        }
                    ]
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor = _governor(tmp_path)
    engine = EvidenceMesh(
        _settings(tmp_path),
        providers=[WikipediaProvider("https://{language}.wikipedia.invalid/w/api.php", client)],
        client=client,
        governor=governor,
    )
    try:
        with pytest.raises(BudgetConfigurationError, match="use_cache=false"):
            await engine.search(SearchRequest(query="alpha evidence"))
        assert calls == 0

        response = await engine.search(SearchRequest(query="alpha evidence", use_cache=False))
        assert response.results[0].title == "Alpha"
        assert calls == 1
        snapshot = await governor.snapshot()
        assert snapshot["session_attempts"] == 1
        assert snapshot["dispatched_attempts"] == 1
    finally:
        await engine.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_ddgs_is_rejected_before_its_threaded_transport(tmp_path: Path) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    governor = _governor(tmp_path)
    try:
        with pytest.raises(BudgetConfigurationError, match="audited"):
            EvidenceMesh(
                _settings(tmp_path),
                providers=[DDGSProvider()],
                client=client,
                governor=governor,
            )
    finally:
        await governor.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_default_ddgs_configuration_is_rejected_before_client_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    governor = _governor(tmp_path)

    def forbidden_client(*_: object, **__: object) -> httpx.AsyncClient:
        raise AssertionError("HTTPX client must not be created for a rejected configuration")

    monkeypatch.setattr("evidencemesh.engine.httpx.AsyncClient", forbidden_client)
    try:
        with pytest.raises(BudgetConfigurationError, match="audited"):
            EvidenceMesh(
                Settings(
                    enabled_providers=["ddgs"],
                    cache_path=tmp_path / "cache.sqlite3",
                ),
                governor=governor,
            )
    finally:
        await governor.aclose()


@pytest.mark.asyncio
async def test_mutating_tavily_name_cannot_bypass_community_quota(tmp_path: Path) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor = _governor(tmp_path, profile="community")
    provider = TavilyProvider("synthetic-not-a-secret", client)
    engine = EvidenceMesh(
        _settings(tmp_path),
        providers=[provider],
        client=client,
        governor=governor,
    )
    provider.name = "wikipedia"
    try:
        with pytest.raises(BudgetExceededError, match="Tavily"):
            await engine.search(SearchRequest(query="alpha evidence", use_cache=False))
        assert calls == 0
        snapshot = await governor.snapshot()
        assert snapshot["session_tavily_attempts"] == 0
        assert snapshot["global_tavily_attempts"] == 0
    finally:
        await engine.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_robots_page_redirect_and_second_origin_each_consume_one_attempt(
    tmp_path: Path,
) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(f"{request.url.host}{request.url.path}")
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://b.invalid/final"})
        return httpx.Response(
            200,
            content=b"governed offline evidence",
            headers={"content-type": "text/plain"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor = _governor(tmp_path)
    fetcher = WebFetcher(
        _settings(tmp_path, robots=True),
        client=client,
        guard=PermissiveGuard(),
        governor=governor,
    )
    try:
        document = await fetcher.fetch("https://a.invalid/start")
        assert document.text == "governed offline evidence"
        assert paths == [
            "a.invalid/robots.txt",
            "a.invalid/start",
            "b.invalid/robots.txt",
            "b.invalid/final",
        ]
        snapshot = await governor.snapshot()
        assert snapshot["session_attempts"] == 4
        assert snapshot["dispatched_attempts"] == 4
    finally:
        await governor.aclose()
        await client.aclose()
