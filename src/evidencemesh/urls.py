"""URL canonicalisation and outbound request safety checks."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from evidencemesh.errors import UnsafeURLError

_TRACKING_PARAMETERS = {
    "_ga",
    "_gl",
    "dclid",
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref_src",
    "vero_conv",
    "vero_id",
    "yclid",
}


def _is_tracking_parameter(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_PARAMETERS


def canonicalize_url(url: str) -> str:
    """Return a stable URL for deduplication without making a network request."""

    raw = url.strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        return raw

    # DuckDuckGo frequently wraps the destination in a redirect URL.
    if (parsed.hostname or "").endswith("duckduckgo.com"):
        redirect_parameters = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if destination := redirect_parameters.get("uddg"):
            return canonicalize_url(destination)

    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        return raw
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return raw
    if host.startswith("www."):
        host = host[4:]

    try:
        port = parsed.port
    except ValueError:
        return raw
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = host if port is None or default_port else f"{host}:{port}"

    path = quote(parsed.path or "/", safe="/:@!$&'()*+,;=-._~%")
    if path != "/":
        path = path.rstrip("/")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_parameter(key)
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


def hostname_from_url(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def registrable_domain_hint(hostname: str) -> str:
    """Return a deterministic diversity key without a public-suffix dependency."""

    parts = hostname.lower().rstrip(".").split(".")
    if len(parts) <= 2:
        return hostname
    common_second_level = {"ac", "co", "com", "edu", "gov", "net", "org"}
    if len(parts[-1]) == 2 and parts[-2] in common_second_level and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def domain_matches(hostname: str, domains: Iterable[str]) -> bool:
    hostname = hostname.lower().rstrip(".")
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains)


def _address_is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped.is_global
    return address.is_global


class URLGuard:
    """Validate fetch targets before each outbound request and redirect."""

    def __init__(
        self,
        *,
        allow_private_networks: bool = False,
        allow_nonstandard_ports: bool = False,
    ) -> None:
        self.allow_private_networks = allow_private_networks
        self.allow_nonstandard_ports = allow_nonstandard_ports

    async def validate(self, url: str) -> str:
        parsed = urlsplit(url.strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            raise UnsafeURLError("only http and https URLs are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeURLError("URLs containing user information are not allowed")
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname:
            raise UnsafeURLError("URL has no hostname")
        if not self.allow_private_networks and (
            hostname == "localhost" or hostname.endswith((".localhost", ".local"))
        ):
            raise UnsafeURLError("local hostnames are blocked")
        try:
            port = parsed.port
        except ValueError as exc:
            raise UnsafeURLError("URL contains an invalid port") from exc
        if port is not None and port not in {80, 443} and not self.allow_nonstandard_ports:
            raise UnsafeURLError("non-standard ports are blocked")

        addresses = await self._resolve(hostname, port or (443 if parsed.scheme == "https" else 80))
        if not addresses:
            raise UnsafeURLError("hostname did not resolve")
        if not self.allow_private_networks:
            blocked = [str(address) for address in addresses if not _address_is_public(address)]
            if blocked:
                raise UnsafeURLError(f"hostname resolves to a non-public address: {blocked[0]}")
        return canonicalize_url(url)

    async def _resolve(
        self,
        hostname: str,
        port: int,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            return {ipaddress.ip_address(hostname)}
        except ValueError:
            pass

        def resolve() -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            return {ipaddress.ip_address(record[4][0]) for record in records}

        try:
            return await asyncio.to_thread(resolve)
        except socket.gaierror as exc:
            raise UnsafeURLError(f"hostname resolution failed: {hostname}") from exc
