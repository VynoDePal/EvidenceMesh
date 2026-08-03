from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from evidencemesh.config import Settings
from evidencemesh.models import FetchedDocument, ProviderResult, SearchRequest
from evidencemesh.providers.base import SearchProvider


class StaticProvider(SearchProvider):
    def __init__(
        self,
        name: str,
        results: list[ProviderResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.results = results or []
        self.error = error
        self.calls: list[str] = []

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return [
            result.model_copy(update={"query": query, "provider": self.name})
            for result in self.results
        ]


class PermissiveGuard:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def validate(self, url: str) -> str:
        self.urls.append(url)
        return url


class StaticFetcher:
    def __init__(self, documents: dict[str, FetchedDocument]) -> None:
        self.documents = documents
        self.guard = PermissiveGuard()
        self.closed = False
        self.calls: list[str] = []

    async def fetch(self, url: str, *, max_chars: int = 30_000) -> FetchedDocument:
        self.calls.append(url)
        document = self.documents[url]
        if len(document.text) <= max_chars:
            return document
        text = document.text[:max_chars]
        return document.model_copy(
            update={
                "text": text,
                "content_chars": len(text),
                "truncated": True,
            }
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        enabled_providers=[],
        cache_path=tmp_path / "cache.sqlite3",
        respect_robots_txt=False,
    )


@pytest.fixture
def result() -> ProviderResult:
    return ProviderResult(
        title="Official EvidenceMesh documentation",
        url="https://docs.example.org/evidencemesh",
        snippet="EvidenceMesh federates search results and returns evidence.",
        provider="alpha",
        rank=1,
        query="EvidenceMesh",
    )


@pytest.fixture
def document() -> FetchedDocument:
    text = "EvidenceMesh provides structured evidence from multiple public sources."
    return FetchedDocument(
        url="https://docs.example.org/evidencemesh",
        canonical_url="https://docs.example.org/evidencemesh",
        title="EvidenceMesh documentation",
        media_type="text/html",
        text=text,
        retrieved_at=datetime.now(UTC),
        content_sha256="a" * 64,
        content_chars=len(text),
    )
