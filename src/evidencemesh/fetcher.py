"""Bounded, redirect-aware document fetching with robots.txt support."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from evidencemesh.config import Settings
from evidencemesh.errors import FetchError, UnsupportedContentError
from evidencemesh.extraction import content_sha256, extract_content
from evidencemesh.governor import DispatchIntent, SQLiteBudgetGovernor
from evidencemesh.models import FetchedDocument
from evidencemesh.urls import (
    PinnedURLResolver,
    PinnedURLTarget,
    URLGuard,
    URLValidator,
    canonicalize_url,
)

_REDIRECTS = {301, 302, 303, 307, 308}
_ROBOTS_MAX_BYTES = 512_000


async def _request_targets(guard: URLValidator, url: str) -> list[PinnedURLTarget]:
    if isinstance(guard, PinnedURLResolver):
        return await guard.resolve_targets(url)
    await guard.validate(url)
    return [PinnedURLTarget(url=url, host_header=None, server_hostname=None)]


def _target_headers(target: PinnedURLTarget, base: dict[str, str]) -> dict[str, str]:
    headers = dict(base)
    if target.host_header is not None:
        headers["Host"] = target.host_header
        # Pinned IPs must not share a pooled TLS connection across hostnames.
        headers["Connection"] = "close"
    return headers


def _target_extensions(target: PinnedURLTarget) -> dict[str, str] | None:
    if target.server_hostname is None:
        return None
    return {"sni_hostname": target.server_hostname}


class RobotsPolicy:
    def __init__(
        self,
        client: httpx.AsyncClient,
        guard: URLValidator,
        user_agent: str,
        *,
        ttl_seconds: int = 3_600,
        governor: SQLiteBudgetGovernor | None = None,
    ) -> None:
        self.client = client
        self.guard = guard
        self.user_agent = user_agent
        self.ttl_seconds = ttl_seconds
        self.governor = governor
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def _dispatch(self) -> AsyncIterator[None]:
        if self.governor is None:
            yield
            return
        permit = (await self.governor.reserve_batch([DispatchIntent(kind="robots")]))[0]
        with self.governor.capture(permit):
            yield

    async def allowed(self, url: str) -> bool:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise FetchError("robots.txt target URL is invalid") from exc
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = self._cache.get(origin)
        if cached and cached[0] > time.monotonic():
            cached_parser = cached[1]
            return True if cached_parser is None else cached_parser.can_fetch(self.user_agent, url)

        lock = self._locks.setdefault(origin, asyncio.Lock())
        async with lock:
            cached = self._cache.get(origin)
            if cached and cached[0] > time.monotonic():
                cached_parser = cached[1]
                return (
                    True if cached_parser is None else cached_parser.can_fetch(self.user_agent, url)
                )

            robots_url = f"{origin}/robots.txt"
            robots_parser: RobotFileParser | None = None
            try:
                targets = await _request_targets(self.guard, robots_url)
                if self.governor is not None:
                    targets = targets[:1]
                for target in targets:
                    try:
                        async with (
                            self._dispatch(),
                            self.client.stream(
                                "GET",
                                target.url,
                                headers=_target_headers(
                                    target,
                                    {
                                        "User-Agent": self.user_agent,
                                        "Accept": "text/plain",
                                    },
                                ),
                                extensions=_target_extensions(target),
                                follow_redirects=False,
                            ) as response,
                        ):
                            if response.status_code != 200:
                                break
                            declared_length = response.headers.get("content-length")
                            if declared_length:
                                try:
                                    if int(declared_length) > _ROBOTS_MAX_BYTES:
                                        break
                                except ValueError:
                                    pass
                            chunks: list[bytes] = []
                            received = 0
                            oversized = False
                            async for chunk in response.aiter_bytes():
                                received += len(chunk)
                                if received > _ROBOTS_MAX_BYTES:
                                    oversized = True
                                    break
                                chunks.append(chunk)
                            if oversized:
                                break
                            robots_parser = RobotFileParser()
                            robots_parser.set_url(robots_url)
                            robots_parser.parse(
                                b"".join(chunks).decode("utf-8", errors="replace").splitlines()
                            )
                            break
                    except httpx.HTTPError:
                        continue
            except FetchError:
                robots_parser = None
            self._cache[origin] = (time.monotonic() + self.ttl_seconds, robots_parser)
            return True if robots_parser is None else robots_parser.can_fetch(self.user_agent, url)


class WebFetcher:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        guard: URLValidator | None = None,
        governor: SQLiteBudgetGovernor | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.fetch_timeout_seconds),
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=settings.max_concurrency,
                max_keepalive_connections=0,
            ),
            trust_env=False,
        )
        self.guard = guard or URLGuard(
            allow_private_networks=settings.allow_private_networks,
            allow_nonstandard_ports=settings.allow_nonstandard_ports,
            dns_timeout_seconds=settings.dns_timeout_seconds,
        )
        self.governor = governor
        if governor is not None:
            governor.attach_client(self.client)
        self.robots = RobotsPolicy(
            self.client,
            self.guard,
            settings.user_agent,
            governor=governor,
        )

    @asynccontextmanager
    async def _dispatch(self, kind: str) -> AsyncIterator[None]:
        if self.governor is None:
            yield
            return
        permit = (await self.governor.reserve_batch([DispatchIntent(kind=kind)]))[0]
        with self.governor.capture(permit):
            yield

    async def fetch(self, url: str, *, max_chars: int = 30_000) -> FetchedDocument:
        try:
            async with asyncio.timeout(self.settings.fetch_timeout_seconds):
                return await self._fetch(url, max_chars=max_chars)
        except TimeoutError as exc:
            raise FetchError("fetch exceeded the configured total deadline") from exc

    async def _fetch(self, url: str, *, max_chars: int) -> FetchedDocument:
        current = url.strip()
        for redirect_index in range(self.settings.max_redirects + 1):
            targets = await _request_targets(self.guard, current)
            if self.governor is not None:
                # A second resolved target is an automatic fallback. A0 permits none.
                targets = targets[:1]
            if self.settings.respect_robots_txt and not await self.robots.allowed(current):
                raise FetchError("robots.txt does not permit this fetch")
            redirect_target: str | None = None
            last_network_error: httpx.HTTPError | None = None
            for target in targets:
                try:
                    kind = "fetch" if redirect_index == 0 else "redirect"
                    async with (
                        self._dispatch(kind),
                        self.client.stream(
                            "GET",
                            target.url,
                            headers=_target_headers(
                                target,
                                {
                                    "User-Agent": self.settings.user_agent,
                                    "Accept": (
                                        "text/html,application/xhtml+xml,application/pdf,"
                                        "text/plain;q=0.9,*/*;q=0.1"
                                    ),
                                },
                            ),
                            extensions=_target_extensions(target),
                            follow_redirects=False,
                        ) as response,
                    ):
                        if response.status_code in _REDIRECTS:
                            location = response.headers.get("location")
                            if not location:
                                raise FetchError("redirect response has no Location header")
                            if len(location) > 8_192:
                                raise FetchError("redirect Location header is too long")
                            if redirect_index >= self.settings.max_redirects:
                                raise FetchError("maximum redirect count exceeded")
                            redirect_target = urljoin(current, location)
                            break
                        if response.status_code < 200 or response.status_code >= 300:
                            raise FetchError(f"fetch failed with HTTP {response.status_code}")
                        declared_length = response.headers.get("content-length")
                        if declared_length:
                            try:
                                if int(declared_length) > self.settings.max_download_bytes:
                                    raise FetchError("response exceeds the configured byte limit")
                            except ValueError:
                                # Invalid metadata is ignored; streaming remains bounded.
                                pass
                        chunks: list[bytes] = []
                        received = 0
                        async for chunk in response.aiter_bytes():
                            received += len(chunk)
                            if received > self.settings.max_download_bytes:
                                raise FetchError("response exceeds the configured byte limit")
                            chunks.append(chunk)
                        data = b"".join(chunks)
                        content_type = response.headers.get("content-type", "")
                        media_type = content_type.split(";", 1)[0].strip()
                except httpx.HTTPError as exc:
                    last_network_error = exc
                    continue

                try:
                    async with asyncio.timeout(self.settings.extraction_timeout_seconds):
                        title, text, flags, truncated = await asyncio.to_thread(
                            extract_content,
                            data,
                            media_type=content_type or media_type,
                            url=current,
                            max_chars=max_chars,
                            max_pdf_pages=self.settings.max_pdf_pages,
                        )
                except TimeoutError as exc:
                    raise FetchError("content extraction deadline exceeded") from exc
                except UnsupportedContentError:
                    raise
                except Exception as exc:
                    raise FetchError(f"content extraction failed: {type(exc).__name__}") from exc

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

            if redirect_target is not None:
                current = redirect_target
                continue
            if last_network_error is not None:
                raise FetchError(
                    f"network fetch failed: {type(last_network_error).__name__}"
                ) from last_network_error
            raise FetchError("network fetch failed before receiving a response")
        raise FetchError("maximum redirect count exceeded")

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()
