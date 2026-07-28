"""Provider interface and parsing helpers."""

from __future__ import annotations

import html
import json
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType

_HTML_TAG = re.compile(r"<[^>]+>")
MAX_PROVIDER_RESPONSE_BYTES = 5_000_000


async def bounded_json_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_bytes: int = MAX_PROVIDER_RESPONSE_BYTES,
    **kwargs: Any,
) -> dict[str, Any]:
    """Read a provider JSON object while enforcing a decompressed byte limit."""

    payload = await bounded_bytes_request(
        client,
        method,
        url,
        max_bytes=max_bytes,
        **kwargs,
    )
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("provider response must be a JSON object")
    return parsed


async def bounded_bytes_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_bytes: int = MAX_PROVIDER_RESPONSE_BYTES,
    **kwargs: Any,
) -> bytes:
    """Read a provider response while enforcing a decompressed byte limit."""

    async with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        declared_length = response.headers.get("content-length")
        if declared_length:
            try:
                parsed_length = int(declared_length)
            except ValueError:
                parsed_length = None
            if parsed_length is not None and parsed_length > max_bytes:
                raise ValueError("provider response exceeds the byte limit")
        chunks: list[bytes] = []
        received = 0
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if received > max_bytes:
                raise ValueError("provider response exceeds the byte limit")
            chunks.append(chunk)
    return b"".join(chunks)


def strip_markup(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(_HTML_TAG.sub(" ", value))).strip()


def parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, UTC)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return None


class SearchProvider(ABC):
    name: str
    supported_profiles: frozenset[SearchProfile] = frozenset(SearchProfile)
    source_type: SourceType = SourceType.WEB
    query_budget: int | None = None
    minimum_cache_ttl_seconds: int = 0

    def supports(self, profile: SearchProfile) -> bool:
        return profile in self.supported_profiles

    def source_family(self, profile: SearchProfile) -> SourceType:
        if self.source_type is not SourceType.WEB:
            return self.source_type
        return SourceType(profile.value)

    @abstractmethod
    async def search(self, query: str, request: SearchRequest) -> list[ProviderResult]:
        """Return provider-native ranking translated to the shared model."""
