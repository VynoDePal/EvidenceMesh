from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
DRAFT = ROOT / "docs/browsecomp-plus-upstream-clarification-request-draft-v1.md"
P1_RESULT = ROOT / "benchmarks/results/phase11_8_10b_p1_browsecomp_clarification_2026-08-01.json"
P1_RESULT_SHA256 = "90336e77544b5ba7a3c4ddf21cf9f535377a57c19c5756941f67ee2304d00016"
P1_RESULT_COMMIT = "aeb71a4a58c011de8182f603a9aaeba66a78cfe6"


def _draft() -> str:
    return DRAFT.read_text(encoding="utf-8")


def test_draft_is_bound_to_p1_and_explicitly_unsent() -> None:
    draft = _draft()

    assert draft.startswith("# DRAFT — LOCAL ONLY — UNSENT — DO NOT SEND\n")
    assert "`status: local-unsent-draft`" in draft
    assert "`send_authorized: false`" in draft
    assert "`response_ingestion_authorized: false`" in draft
    assert "`recipient_identity_resolved: false`" in draft
    assert f"`p1_result_sha256: {P1_RESULT_SHA256}`" in draft
    assert f"`p1_result_commit: {P1_RESULT_COMMIT}`" in draft
    assert hashlib.sha256(P1_RESULT.read_bytes()).hexdigest() == P1_RESULT_SHA256


def test_draft_preserves_zero_external_budget() -> None:
    draft = _draft()

    for field in (
        "external_requests_authorized",
        "external_retries_authorized",
        "publications_authorized",
    ):
        assert f"`{field}: 0`" in draft
    assert "require a separate explicit authorization and a new evidence budget" in draft


def test_draft_requests_only_the_two_authorized_clarifications() -> None:
    draft_text = _draft()
    draft = draft_text.lower()

    assert re.findall(r"^## .+$", draft_text, re.MULTILINE) == [
        "## 1. Component-level rights disposition",
        "## 2. Immutable effective evaluation closure",
    ]
    for required in (
        "acquisition of the component",
        "private local storage and processing",
        "aggregate metrics or scores only",
        "strict non-redistribution condition",
        "judge model repository, exact revision",
        "tokenizer repository, exact revision",
        "exact effective grader prompt",
        "every effective generation setting and override",
        "fully resolved runtime",
        "parser source identity and effective configuration",
        "scoring source identity and effective configuration",
        "machine-readable effective-run manifest",
    ):
        assert required in draft
    normalized = " ".join(draft.split())
    assert "for each published result, result row or result family" in normalized
    assert "stable result identifier and a one-to-one mapping" in normalized
    assert "binds the result identifier to all the elements above" in normalized


def test_draft_contains_no_contact_source_or_execution_mechanism() -> None:
    draft = _draft()
    lowered = draft.lower()

    for forbidden in (
        "http://",
        "https://",
        "mailto:",
        "curl ",
        "wget ",
        "github issue",
        "api key",
        "```python",
        "```bash",
        "```sh",
    ):
        assert forbidden not in lowered
    assert "@" not in draft
    assert not re.search(r"\[[^\]]+\]\([^)]+\)", draft)
    assert not re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", draft, re.I)


def test_draft_rejects_payloads_and_avoids_excessive_claims() -> None:
    draft = _draft().lower()
    normalized = " ".join(draft.split())

    assert "please do not provide benchmark payloads" in draft
    for excluded in (
        "corpus content",
        "examples",
        "queries",
        "answers",
        "qrels",
        "model weights",
        "secrets",
        "personal data",
        "newly executed score",
    ):
        assert excluded in draft
    for excessive_claim in (
        "the rights are granted",
        "the rights are denied",
        "the corpus is illegal",
        "the corpus is unlicensed",
        "will clear the gate",
        "is the official judge",
        "a future response will automatically admit the benchmark",
    ):
        assert excessive_claim not in draft
    for guardrail in (
        "in the bounded evidence set reviewed so far",
        "not legal advice or a legal conclusion",
        "does not assert that any permission exists or does not exist",
        "would not automatically admit the benchmark",
    ):
        assert guardrail in normalized
