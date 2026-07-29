"""Canonical, content-free identities for retrieval benchmark targets."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from evidencemesh.urls import domain_matches

_ARXIV_VERSION = re.compile(r"v\d+$", re.IGNORECASE)
_TARGET_KINDS = frozenset({"arxiv", "domain", "github", "wikipedia"})


def validate_target_identity(identity: str) -> str:
    """Validate and normalize an authored benchmark identity."""

    compact = identity.strip()
    kind, separator, value = compact.partition(":")
    if not separator or kind not in _TARGET_KINDS or not value:
        raise ValueError(f"invalid target identity: {identity!r}")
    if kind == "domain":
        domain = value.casefold().rstrip(".")
        if (
            not domain
            or "://" in domain
            or "/" in domain
            or any(not label for label in domain.split("."))
        ):
            raise ValueError(f"invalid domain target identity: {identity!r}")
        return f"domain:{domain}"
    if kind == "github":
        owner, slash, repository = value.partition("/")
        if not slash or not owner or not repository or "/" in repository:
            raise ValueError(f"invalid GitHub target identity: {identity!r}")
        return f"github:{owner.casefold()}/{repository.removesuffix('.git').casefold()}"
    if kind == "arxiv":
        arxiv_id = _normalize_arxiv_id(value)
        if not arxiv_id:
            raise ValueError(f"invalid arXiv target identity: {identity!r}")
        return f"arxiv:{arxiv_id}"
    language, separator, slug = value.partition(":")
    if not separator or not language or not slug:
        raise ValueError(f"invalid Wikipedia target identity: {identity!r}")
    return f"wikipedia:{language.casefold()}:{_normalize_wikipedia_slug(slug)}"


def identities_for_url(url: str) -> set[str]:
    """Derive canonical benchmark identities from a result URL."""

    try:
        parsed = urlsplit(url)
    except ValueError:
        return set()
    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        return set()
    identities = {f"domain:{host}"}
    path = unquote(parsed.path)

    if host == "github.com":
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            identities.add(
                f"github:{parts[0].casefold()}/{parts[1].removesuffix('.git').casefold()}"
            )

    if host.endswith(".wikipedia.org"):
        language = host.removesuffix(".wikipedia.org")
        if language and path.startswith("/wiki/"):
            slug = _normalize_wikipedia_slug(path.removeprefix("/wiki/"))
            if slug:
                identities.add(f"wikipedia:{language}:{slug}")

    if host in {"arxiv.org", "export.arxiv.org"}:
        arxiv_id = _arxiv_id_from_path(path)
        if arxiv_id:
            identities.add(f"arxiv:{arxiv_id}")
    elif host == "doi.org":
        doi = path.lstrip("/").casefold()
        marker = "10.48550/arxiv."
        if doi.startswith(marker):
            arxiv_id = _normalize_arxiv_id(doi.removeprefix(marker))
            if arxiv_id:
                identities.add(f"arxiv:{arxiv_id}")
    return identities


def target_matches_url(targets: tuple[str, ...] | list[str], url: str) -> bool:
    """Return whether a URL resolves to one of the authored identities."""

    try:
        host = (urlsplit(url).hostname or "").casefold().rstrip(".")
    except ValueError:
        return False
    derived = identities_for_url(url)
    for target in targets:
        normalized = validate_target_identity(target)
        if normalized.startswith("domain:"):
            if host and domain_matches(host, [normalized.removeprefix("domain:")]):
                return True
        elif normalized in derived:
            return True
    return False


def _arxiv_id_from_path(path: str) -> str:
    candidate = path.lstrip("/")
    if candidate.startswith(("abs/", "pdf/")):
        candidate = candidate.split("/", 1)[1]
    if candidate.endswith(".pdf"):
        candidate = candidate.removesuffix(".pdf")
    return _normalize_arxiv_id(candidate)


def _normalize_arxiv_id(value: str) -> str:
    return _ARXIV_VERSION.sub("", value.strip().casefold().rstrip("/"))


def _normalize_wikipedia_slug(value: str) -> str:
    return value.strip().replace(" ", "_").casefold()
