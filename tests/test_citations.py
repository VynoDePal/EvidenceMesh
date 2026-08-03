from __future__ import annotations

from evidencemesh import CitationAudit, audit_citations


def test_citation_audit_accepts_unique_available_identifiers() -> None:
    audit = audit_citations(
        "The first fact [S2]. The second fact [S1][S2].",
        ["S1", "S2"],
    )

    assert isinstance(audit, CitationAudit)
    assert audit.citation_ids == ("S2", "S1")
    assert audit.invalid_ids == ()
    assert audit.malformed_tokens == ()
    assert audit.has_citations is True
    assert audit.identifier_integrity_valid is True
    assert audit.valid is True


def test_citation_audit_rejects_unknown_and_malformed_identifiers() -> None:
    audit = audit_citations(
        "Known [S1], unknown [S3], zero [S0], padded [S01], lower [s1].",
        ["S1", "S2"],
    )

    assert audit.citation_ids == ("S1",)
    assert audit.invalid_ids == ("S3",)
    assert audit.malformed_tokens == ("[S0]", "[S01]", "[s1]")
    assert audit.identifier_integrity_valid is False
    assert audit.valid is False


def test_citation_audit_can_make_presence_optional() -> None:
    required = audit_citations("No citation.", ["S1"])
    optional = audit_citations("No citation.", ["S1"], citations_required=False)

    assert required.has_citations is False
    assert required.valid is False
    assert optional.valid is True
