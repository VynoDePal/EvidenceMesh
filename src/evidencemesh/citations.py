"""Deterministic validation for EvidenceMesh citation identifiers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_VALID_CITATION_ID = re.compile(r"S[1-9][0-9]*")
_CITATION_TOKEN = re.compile(r"\[([Ss][^\]\r\n]{0,31})\]")


@dataclass(frozen=True, slots=True)
class CitationAudit:
    """Integrity result for citations found in one generated answer.

    This contract validates identifier syntax and membership only. It does not
    claim that a cited source semantically supports the surrounding statement.
    """

    citation_ids: tuple[str, ...]
    invalid_ids: tuple[str, ...]
    malformed_tokens: tuple[str, ...]
    citations_required: bool

    @property
    def has_citations(self) -> bool:
        return bool(self.citation_ids or self.invalid_ids or self.malformed_tokens)

    @property
    def identifier_integrity_valid(self) -> bool:
        return not self.invalid_ids and not self.malformed_tokens

    @property
    def valid(self) -> bool:
        return self.identifier_integrity_valid and (
            self.has_citations or not self.citations_required
        )


def audit_citations(
    answer: str,
    available_ids: Iterable[str],
    *,
    citations_required: bool = True,
) -> CitationAudit:
    """Audit exact ``[S#]`` references without interpreting answer semantics."""

    allowed = {
        citation_id for citation_id in available_ids if _VALID_CITATION_ID.fullmatch(citation_id)
    }
    citation_ids: list[str] = []
    invalid_ids: list[str] = []
    malformed_tokens: list[str] = []

    for match in _CITATION_TOKEN.finditer(answer):
        value = match.group(1)
        token = match.group(0)
        if not _VALID_CITATION_ID.fullmatch(value):
            if token not in malformed_tokens:
                malformed_tokens.append(token)
            continue
        if value not in allowed:
            if value not in invalid_ids:
                invalid_ids.append(value)
            continue
        if value not in citation_ids:
            citation_ids.append(value)

    return CitationAudit(
        citation_ids=tuple(citation_ids),
        invalid_ids=tuple(invalid_ids),
        malformed_tokens=tuple(malformed_tokens),
        citations_required=citations_required,
    )
