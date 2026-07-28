"""URL canonicalisation and outbound request safety checks."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import SplitResult, parse_qsl, quote, urlencode, urlsplit, urlunsplit

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
_NAT64_WELL_KNOWN = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL_USE = ipaddress.ip_network("64:ff9b:1::/48")
_LEGACY_IPV4_LITERAL = re.compile(r"(?:0[xX][0-9A-Fa-f]+|[0-9.]+)")


def _is_tracking_parameter(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_PARAMETERS


def _split_url(url: str) -> SplitResult | None:
    try:
        return urlsplit(url)
    except ValueError:
        return None


def _normalise_hostname(hostname: str) -> str:
    hostname = hostname.lower().rstrip(".")
    try:
        return ipaddress.ip_address(hostname).compressed
    except ValueError:
        return hostname.encode("idna").decode("ascii")


def _netloc_host(hostname: str) -> str:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname
    if isinstance(address, ipaddress.IPv6Address):
        return f"[{address.compressed}]"
    return address.compressed


def _literal_address(
    hostname: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Recognise standard and legacy numeric IP spellings without DNS."""

    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass
    if not _LEGACY_IPV4_LITERAL.fullmatch(hostname):
        return None
    try:
        return ipaddress.IPv4Address(socket.inet_aton(hostname))
    except OSError:
        return None


def canonicalize_url(url: str) -> str:
    """Return a stable URL for deduplication without making a network request."""

    raw = url.strip()
    parsed = _split_url(raw)
    if parsed is None:
        return raw
    if parsed.scheme.lower() not in {"http", "https"}:
        return raw
    if parsed.username is not None or parsed.password is not None:
        return raw

    # DuckDuckGo frequently wraps the destination in a redirect URL.
    try:
        parsed_hostname = parsed.hostname or ""
    except ValueError:
        return raw
    lowered_hostname = parsed_hostname.lower().rstrip(".")
    if lowered_hostname == "duckduckgo.com" or lowered_hostname.endswith(".duckduckgo.com"):
        redirect_parameters = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if destination := redirect_parameters.get("uddg"):
            return canonicalize_url(destination)

    if not parsed_hostname:
        return raw
    try:
        host = _normalise_hostname(parsed_hostname)
    except (UnicodeError, ValueError):
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
    rendered_host = _netloc_host(host)
    netloc = rendered_host if port is None or default_port else f"{rendered_host}:{port}"

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
    parsed = _split_url(url)
    if parsed is None:
        return ""
    try:
        hostname = parsed.hostname
    except ValueError:
        return ""
    if not hostname:
        return ""
    try:
        return _normalise_hostname(hostname)
    except (UnicodeError, ValueError):
        return ""


def is_supported_http_url(url: str) -> bool:
    """Return whether an untrusted result URL is safe to expose as an HTTP citation."""

    raw = url.strip()
    if not raw or any(ord(character) < 32 or ord(character) == 127 for character in raw):
        return False
    parsed = _split_url(raw)
    if parsed is None or parsed.scheme.lower() not in {"http", "https"}:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    try:
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    if not hostname:
        return False
    try:
        normalised_hostname = _normalise_hostname(hostname)
    except (UnicodeError, ValueError):
        return False
    if normalised_hostname == "localhost" or normalised_hostname.endswith((".localhost", ".local")):
        return False
    address = _literal_address(normalised_hostname)
    return address is None or _address_is_public(address)


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
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return address.ipv4_mapped.is_global
        if address in _NAT64_LOCAL_USE:
            return False
        if address in _NAT64_WELL_KNOWN:
            embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
            return embedded.is_global
    return address.is_global


@dataclass(frozen=True, slots=True)
class PinnedURLTarget:
    """A request target whose connection address came from the validated DNS answer."""

    url: str
    host_header: str | None
    server_hostname: str | None


@runtime_checkable
class URLValidator(Protocol):
    async def validate(self, url: str) -> str: ...


@runtime_checkable
class PinnedURLResolver(URLValidator, Protocol):
    async def resolve_targets(self, url: str) -> list[PinnedURLTarget]: ...


class URLGuard:
    """Validate fetch targets before each outbound request and redirect."""

    def __init__(
        self,
        *,
        allow_private_networks: bool = False,
        allow_nonstandard_ports: bool = False,
        dns_timeout_seconds: float = 5.0,
    ) -> None:
        self.allow_private_networks = allow_private_networks
        self.allow_nonstandard_ports = allow_nonstandard_ports
        self.dns_timeout_seconds = dns_timeout_seconds

    def _parse(self, url: str) -> tuple[str, SplitResult, str, int]:
        raw = url.strip()
        if not raw or any(ord(character) < 32 or ord(character) == 127 for character in raw):
            raise UnsafeURLError("URL contains control characters")
        parsed = _split_url(raw)
        if parsed is None:
            raise UnsafeURLError("URL could not be parsed")
        if parsed.scheme.lower() not in {"http", "https"}:
            raise UnsafeURLError("only http and https URLs are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeURLError("URLs containing user information are not allowed")
        try:
            parsed_hostname = parsed.hostname
        except ValueError as exc:
            raise UnsafeURLError("URL contains an invalid hostname") from exc
        if not parsed_hostname:
            raise UnsafeURLError("URL has no hostname")
        try:
            hostname = _normalise_hostname(parsed_hostname)
        except (UnicodeError, ValueError) as exc:
            raise UnsafeURLError("URL contains an invalid hostname") from exc
        if not hostname:
            raise UnsafeURLError("URL has no hostname")
        if "%" in hostname:
            raise UnsafeURLError("scoped IP addresses are not allowed")
        if not self.allow_private_networks and (
            hostname == "localhost" or hostname.endswith((".localhost", ".local"))
        ):
            raise UnsafeURLError("local hostnames are blocked")
        try:
            port = parsed.port
        except ValueError as exc:
            raise UnsafeURLError("URL contains an invalid port") from exc
        if port == 0:
            raise UnsafeURLError("port zero is not allowed")
        if port is not None and port not in {80, 443} and not self.allow_nonstandard_ports:
            raise UnsafeURLError("non-standard ports are blocked")
        connection_port = (
            port if port is not None else (443 if parsed.scheme.lower() == "https" else 80)
        )
        return raw, parsed, hostname, connection_port

    async def _validated_addresses(
        self,
        hostname: str,
        port: int,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        addresses = await self._resolve(hostname, port)
        if not addresses:
            raise UnsafeURLError("hostname did not resolve")
        if not self.allow_private_networks:
            blocked = [str(address) for address in addresses if not _address_is_public(address)]
            if blocked:
                raise UnsafeURLError(f"hostname resolves to a non-public address: {blocked[0]}")
        return addresses

    async def validate(self, url: str) -> str:
        raw, _, hostname, port = self._parse(url)
        await self._validated_addresses(hostname, port)
        return canonicalize_url(raw)

    async def resolve_targets(self, url: str) -> list[PinnedURLTarget]:
        """Resolve once, validate every answer, then connect to those exact addresses."""

        _, parsed, hostname, port = self._parse(url)
        addresses = await self._validated_addresses(hostname, port)
        scheme = parsed.scheme.lower()
        default_port = 443 if scheme == "https" else 80
        original_host = _netloc_host(hostname)
        host_header = original_host if port == default_port else f"{original_host}:{port}"
        targets: list[PinnedURLTarget] = []
        for address in sorted(
            addresses,
            key=lambda item: (isinstance(item, ipaddress.IPv6Address), item.compressed),
        ):
            pinned_host = _netloc_host(address.compressed)
            pinned_netloc = pinned_host if port == default_port else f"{pinned_host}:{port}"
            pinned_url = urlunsplit(
                (
                    scheme,
                    pinned_netloc,
                    parsed.path or "/",
                    parsed.query,
                    "",
                )
            )
            targets.append(
                PinnedURLTarget(
                    url=pinned_url,
                    host_header=host_header,
                    server_hostname=hostname,
                )
            )
        if not targets:  # Kept defensive if a custom resolver violates the contract.
            raise UnsafeURLError(f"hostname did not resolve: {hostname}")
        return targets

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
            return {ipaddress.ip_address(str(record[4][0]).split("%", 1)[0]) for record in records}

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(resolve),
                timeout=self.dns_timeout_seconds,
            )
        except TimeoutError as exc:
            raise UnsafeURLError(f"hostname resolution timed out: {hostname}") from exc
        except (OSError, UnicodeError, ValueError) as exc:
            raise UnsafeURLError(f"hostname resolution failed: {hostname}") from exc
