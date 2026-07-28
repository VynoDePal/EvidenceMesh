"""Bounded, redirect-aware document fetching with robots.txt support."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from evidencemesh.config import Settings
from evidencemesh.errors import FetchError, UnsupportedContentError
from evidencemesh.extraction import content_sha256, extract_content
from evidencemesh.models import FetchedDocument
from evidencemesh.urls import URLGuard, canonicalize_url

_REDIRECTS = {301, 302, 303, 307, 308}


class RobotsPolicy:
    def __init__(
        self,
        client: httpx.AsyncClient,
        guard: URLGuard,
        user_agent: str,
        *,
        ttl_seconds: int = 3_600,
    ) -> None:
        self.client = client
        self.guard = guard
        self.user_agent = user_agent
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}

    async def allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = self._cache.get(origin)
        if cached and cached[0] > time.monotonic():
            cached_parser = cached[1]
            return True if cached_parser is None else cached_parser.can_fetch(self.user_agent, url)

        robots_url = f"{origin}/robots.txt"
        robots_parser: RobotFileParser | None = None
        try:
            await self.guard.validate(robots_url)
            response = await self.client.get(
                robots_url,
                headers={"User-Agent": self.user_agent, "Accept": "text/plain"},
                follow_redirects=False,
            )
            if response.status_code == 200 and len(response.content) <= 512_000:
                robots_parser = RobotFileParser()
                robots_parser.set_url(robots_url)
                robots_parser.parse(response.text.splitlines())
        except (httpx.HTTPError, FetchError):
            robots_parser = None
        self._cache[origin] = (time.monotonic() + self.ttl_seconds, robots_parser)
        return True if robots_parser is None else robots_parser.can_fetch(self.user_agent, url)


class WebFetcher:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        guard: URLGuard | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.fetch_timeout_seconds),
        )
        self.guard = guard or URLGuard(
            allow_private_networks=settings.allow_private_networks,
            allow_nonstandard_ports=settings.allow_nonstandard_ports,
        )
        self.robots = RobotsPolicy(self.client, self.guard, settings.user_agent)

    async def fetch(self, url: str, *, max_chars: int = 30_000) -> FetchedDocument:
        current = url.strip()
        for redirect_index in range(self.settings.max_redirects + 1):
            await self.guard.validate(current)
            if self.settings.respect_robots_txt and not await self.robots.allowed(current):
                raise FetchError("robots.txt does not permit this fetch")
            try:
                async with self.client.stream(
                    "GET",
                    current,
                    headers={
                        "User-Agent": self.settings.user_agent,
                        "Accept": (
                            "text/html,application/xhtml+xml,application/pdf,"
                            "text/plain;q=0.9,*/*;q=0.1"
                        ),
                    },
                    follow_redirects=False,
                ) as response:
                    if response.status_code in _REDIRECTS:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("redirect response has no Location header")
                        if redirect_index >= self.settings.max_redirects:
                            raise FetchError("maximum redirect count exceeded")
                        current = urljoin(current, location)
                        continue
                    if response.status_code < 200 or response.status_code >= 300:
                        raise FetchError(f"fetch failed with HTTP {response.status_code}")
                    declared_length = response.headers.get("content-length")
                    if declared_length:
                        try:
                            if int(declared_length) > self.settings.max_download_bytes:
                                raise FetchError("response exceeds the configured byte limit")
                        except ValueError:
                            # Invalid metadata is ignored; the streaming limit remains enforced.
                            pass
                    chunks: list[bytes] = []
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > self.settings.max_download_bytes:
                            raise FetchError("response exceeds the configured byte limit")
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
            except httpx.HTTPError as exc:
                raise FetchError(f"network fetch failed: {type(exc).__name__}") from exc

            try:
                title, text, flags, truncated = extract_content(
                    data,
                    media_type=response.headers.get("content-type", media_type),
                    url=current,
                    max_chars=max_chars,
                )
            except UnsupportedContentError:
                raise
            canonical = canonicalize_url(current)
            return FetchedDocument(
                url=current,
                canonical_url=canonical,
                title=title or canonical,
                media_type=media_type or "application/octet-stream",
                text=text,
                retrieved_at=datetime.now(UTC),
                content_sha256=content_sha256(text),
                content_chars=len(text),
                truncated=truncated,
                risk_flags=flags,
            )
        raise FetchError("maximum redirect count exceeded")

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()
