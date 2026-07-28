"""Deterministic query planning that does not require a second LLM."""

from __future__ import annotations

import re

from evidencemesh.models import SearchDepth, SearchProfile

_WHITESPACE = re.compile(r"\s+")


def _clean(query: str) -> str:
    return _WHITESPACE.sub(" ", query).strip()


def build_query_plan(
    question: str,
    *,
    depth: SearchDepth,
    profile: SearchProfile,
    language: str,
    supplied: list[str] | None = None,
) -> list[str]:
    """Create transparent query variants; users can override them explicitly."""

    base = _clean(question)
    if supplied:
        candidates = [base, *(_clean(query) for query in supplied)]
        return list(dict.fromkeys(query for query in candidates if query))

    target_count = {
        SearchDepth.QUICK: 1,
        SearchDepth.STANDARD: 4,
        SearchDepth.DEEP: 7,
    }[depth]
    language_code = language.lower().split("-")[0]
    terms = {
        "en": {
            "official": "official source",
            "evidence": "evidence data",
            "limits": "limitations criticism",
            "recent": "latest update",
            "academic": "research paper study",
            "code": "official documentation source code",
        },
        "fr": {
            "official": "source officielle",
            "evidence": "preuves données",
            "limits": "limites critiques",
            "recent": "mise à jour récente",
            "academic": "article scientifique étude",
            "code": "documentation officielle code source",
        },
    }.get(language_code)
    if terms is None:
        terms = {
            "official": "official source",
            "evidence": "evidence",
            "limits": "limitations",
            "recent": "latest",
            "academic": "research paper",
            "code": "official documentation",
        }

    candidates = [base]
    if profile is SearchProfile.ACADEMIC:
        candidates.append(f"{base} {terms['academic']}")
    elif profile is SearchProfile.CODE:
        candidates.append(f"{base} {terms['code']}")
    elif profile is SearchProfile.NEWS:
        candidates.append(f"{base} {terms['recent']}")
    else:
        candidates.append(f"{base} {terms['official']}")

    candidates.extend(
        [
            f"{base} {terms['evidence']}",
            f"{base} {terms['limits']}",
            f'"{base}"',
            f"{base} {terms['recent']}",
            f"{base} primary source",
        ]
    )
    return list(dict.fromkeys(_clean(query) for query in candidates))[:target_count]
