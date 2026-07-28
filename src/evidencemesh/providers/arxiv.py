from __future__ import annotations

import asyncio
import time
import weakref
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx

from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType
from evidencemesh.providers.base import (
    SearchProvider,
    bounded_bytes_request,
    parse_datetime,
    strip_markup,
)

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


@dataclass(slots=True)
class _PacerState:
    lock: asyncio.Lock
    last_started: float | None = None


class _ProcessArxivPacer:
    """Serialize arXiv calls and keep request starts three seconds apart per event loop."""

    def __init__(self) -> None:
        self._states: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _PacerState] = (
            weakref.WeakKeyDictionary()
        )

    @asynccontextmanager
    async def slot(self, interval_seconds: float) -> AsyncIterator[None]:
        loop = asyncio.get_running_loop()
        state = self._states.get(loop)
        if state is None:
            state = _PacerState(lock=asyncio.Lock())
            self._states[loop] = state
        async with state.lock:
            if state.last_started is not None:
                remaining = interval_seconds - (time.monotonic() - state.last_started)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            state.last_started = time.monotonic()
            yield


_PACER = _ProcessArxivPacer()


def _entry_text(entry: ET.Element, tag: str) -> str:
    value = entry.findtext(f"{_ATOM}{tag}")
    return strip_markup(value)


class ArxivProvider(SearchProvider):
    name = "arxiv"
    supported_profiles = frozenset({SearchProfile.ACADEMIC})
    source_type = SourceType.ACADEMIC
    query_budget = 1
    minimum_cache_ttl_seconds = 86_400

    def __init__(
        self,
        endpoint: str,
        client: httpx.AsyncClient,
        *,
        minimum_interval_seconds: float = 3.0,
    ) -> None:
        self.endpoint = endpoint
        self.client = client
        self.minimum_interval_seconds = minimum_interval_seconds

    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        params: dict[str, str | int] = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(max(request.limit * 2, 10), 50),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        try:
            async with _PACER.slot(self.minimum_interval_seconds):
                payload = await bounded_bytes_request(
                    self.client,
                    "GET",
                    self.endpoint,
                    params=params,
                )
            upper_payload = payload.upper()
            if b"<!DOCTYPE" in upper_payload or b"<!ENTITY" in upper_payload:
                raise ValueError("arXiv XML contains a forbidden declaration")
            root = ET.fromstring(payload)  # noqa: S314 - declarations rejected above
        except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
            raise ProviderError(f"arXiv request failed: {type(exc).__name__}") from exc

        results: list[ProviderResult] = []
        for rank, entry in enumerate(root.findall(f"{_ATOM}entry"), start=1):
            title = _entry_text(entry, "title")
            url = ""
            for link in entry.findall(f"{_ATOM}link"):
                href = link.attrib.get("href", "").strip()
                if href and link.attrib.get("rel", "alternate") == "alternate":
                    url = href
                    break
            if not url:
                url = _entry_text(entry, "id")
            if url.startswith("http://arxiv.org/"):
                url = f"https://{url.removeprefix('http://')}"
            if not url:
                continue
            authors = [
                strip_markup(author.findtext(f"{_ATOM}name"))
                for author in entry.findall(f"{_ATOM}author")
            ]
            authors = [author for author in authors if author]
            categories = sorted(
                {
                    category.attrib["term"].strip()
                    for category in entry.findall(f"{_ATOM}category")
                    if category.attrib.get("term", "").strip()
                }
            )
            results.append(
                ProviderResult(
                    title=title or url,
                    url=url,
                    snippet=_entry_text(entry, "summary"),
                    provider=self.name,
                    rank=rank,
                    query=query,
                    published_at=parse_datetime(entry.findtext(f"{_ATOM}published")),
                    source_type=SourceType.ACADEMIC,
                    metadata={
                        "authors": authors[:20],
                        "categories": categories,
                        "doi": strip_markup(entry.findtext(f"{_ARXIV}doi")) or None,
                    },
                )
            )
        return results
