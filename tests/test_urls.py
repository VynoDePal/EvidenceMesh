from __future__ import annotations

import ipaddress

import pytest

from evidencemesh.errors import UnsafeURLError
from evidencemesh.urls import (
    URLGuard,
    canonicalize_url,
    domain_matches,
    hostname_from_url,
    registrable_domain_hint,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "HTTPS://WWW.Example.COM:443/path/?utm_source=x&b=2&a=1#part",
            "https://example.com/path?a=1&b=2",
        ),
        ("http://example.com:80/", "http://example.com/"),
        ("https://example.com/a/", "https://example.com/a"),
        ("mailto:test@example.com", "mailto:test@example.com"),
    ],
)
def test_canonicalize_url(raw: str, expected: str) -> None:
    assert canonicalize_url(raw) == expected


def test_canonicalize_duckduckgo_redirect() -> None:
    wrapped = "https://duckduckgo.com/l/?uddg=https%3A%2F%2FExample.com%2Fa%3Futm_source%3Dx"
    assert canonicalize_url(wrapped) == "https://example.com/a"


def test_url_helpers() -> None:
    assert hostname_from_url("https://Sub.Example.co.uk/a") == "sub.example.co.uk"
    assert registrable_domain_hint("sub.example.co.uk") == "example.co.uk"
    assert registrable_domain_hint("docs.example.com") == "example.com"
    assert domain_matches("docs.example.com", ["example.com"])
    assert not domain_matches("notexample.com", ["example.com"])


class StubGuard(URLGuard):
    def __init__(self, addresses: set[str], **kwargs: bool) -> None:
        super().__init__(**kwargs)
        self.addresses = {ipaddress.ip_address(address) for address in addresses}

    async def _resolve(
        self,
        hostname: str,
        port: int,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        return self.addresses


@pytest.mark.asyncio
async def test_url_guard_accepts_public_https() -> None:
    guard = StubGuard({"93.184.216.34"})
    assert await guard.validate("https://www.example.com/a") == "https://example.com/a"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:password@example.com/",
        "http://localhost/",
        "http://name.local/",
        "http://example.com:8080/",
    ],
)
async def test_url_guard_rejects_unsafe_forms(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        await StubGuard({"93.184.216.34"}).validate(url)


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.1.1", "::1"])
async def test_url_guard_rejects_non_public_resolution(address: str) -> None:
    with pytest.raises(UnsafeURLError, match="non-public"):
        await StubGuard({address}).validate("https://example.com")


@pytest.mark.asyncio
async def test_url_guard_private_override() -> None:
    guard = StubGuard(
        {"127.0.0.1"},
        allow_private_networks=True,
        allow_nonstandard_ports=True,
    )
    assert await guard.validate("http://localhost:8080/a") == "http://localhost:8080/a"


@pytest.mark.asyncio
async def test_url_guard_rejects_empty_resolution() -> None:
    with pytest.raises(UnsafeURLError, match="did not resolve"):
        await StubGuard(set()).validate("https://example.com")
