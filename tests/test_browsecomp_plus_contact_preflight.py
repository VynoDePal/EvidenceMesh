from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
PREFLIGHT = ROOT / "docs/browsecomp-plus-contact-preflight-v1.md"
DRAFT = ROOT / "docs/browsecomp-plus-upstream-clarification-request-draft-v1.md"
DRAFT_SHA256 = "300704435689f64647728ca4dcd7300a078eed3fae8d70f6ed94521d6120766d"
DRAFT_COMMIT = "e155feefa4081bce1746e58b04f631811dbb02b4"
PAYLOAD = ROOT / "docs/browsecomp-plus-public-issue-payload-v1.json"
PAYLOAD_SHA256 = "2225c5f25641ecfef944ffb55bd34403753ef8a1c4c191db520857af3660e77c"


def _preflight() -> str:
    return PREFLIGHT.read_text(encoding="utf-8")


def _field_values(document: str, field: str) -> list[str]:
    return re.findall(rf"`{re.escape(field)}: ([^`]+)`", document)


def test_all_machine_fields_are_unique() -> None:
    fields = re.findall(r"^- `([a-z0-9_]+): [^`]+`$", _preflight(), re.MULTILINE)

    assert len(fields) == len(set(fields))


def test_preflight_is_bound_to_the_sealed_unsent_draft() -> None:
    preflight = _preflight()

    assert hashlib.sha256(DRAFT.read_bytes()).hexdigest() == DRAFT_SHA256
    assert f"`parent_draft_commit: {DRAFT_COMMIT}`" in preflight
    assert f"`parent_draft_sha256: {DRAFT_SHA256}`" in preflight
    assert _field_values(preflight, "status") == ["contact-preflight-complete-send-blocked"]
    assert _field_values(preflight, "send_authorized") == ["false"]


def test_preflight_consumes_exactly_two_reads_and_performs_no_write() -> None:
    preflight = _preflight()

    assert re.findall(r"^### Read .+$", preflight, re.MULTILINE) == [
        "### Read 1 of 2 — repository metadata",
        "### Read 2 of 2 — issue-channel existence",
    ]
    assert re.findall(r"GitHub connector operation: `([^`]+)`\.", preflight) == [
        "github_get_repo",
        "github_search_issues",
    ]
    for field, value in (
        ("external_metadata_reads_authorized", 2),
        ("external_metadata_reads_performed", 2),
        ("external_metadata_reads_remaining", 0),
        ("messages_sent", 0),
        ("external_retries_performed", 0),
        ("publications_performed", 0),
        ("human_upstream_responses_read", 0),
        ("write_receipts_observed", 0),
    ):
        assert _field_values(preflight, field) == [str(value)]


def test_preflight_qualifies_measurement_and_mutable_observations() -> None:
    preflight = _preflight()
    normalized = " ".join(preflight.lower().split())

    assert _field_values(preflight, "measurement_mode") == [
        "bounded-process-attestation-plus-connector-response-record"
    ]
    assert _field_values(preflight, "runtime_network_instrumentation_used") == ["false"]
    assert _field_values(preflight, "captured_on") == ["2026-08-01"]
    assert _field_values(preflight, "connector_response_identity_recorded") == ["false"]
    assert normalized.count("connector returned no stable response identity") == 2


def test_preflight_records_only_bounded_contact_metadata() -> None:
    normalized = " ".join(_preflight().lower().split())

    for required in (
        "requested repository: `texttron/browsecomp-plus`",
        "owner: `texttron`, github owner type `organization`, numeric id `89861074`",
        "visibility: `public`",
        "archived: `false`",
        "default branch: `main`",
        "issue `22`, titled `leaderboard for retrieval only metrics.`",
        "issue body was not adopted as benchmark evidence and is not reproduced",
    ):
        assert required in normalized
    assert "benchmark payload" not in normalized.split("## read ledger", maxsplit=1)[0]


def test_preflight_does_not_overstate_channel_or_rights_authority() -> None:
    preflight = _preflight().lower()
    normalized = " ".join(preflight.split())

    for field in (
        "`new_issue_creation_currently_confirmed: false`",
        "`component_rights_authority_resolved: false`",
        "`personal_recipient_identity_resolved: false`",
    ):
        assert preflight.count(field) == 1
    for guardrail in (
        "not a presumed legal authority",
        "does not prove that new issue creation remains enabled",
        "no inference is made that the maintainers own all required rights",
        "a github issue would be a public publication",
    ):
        assert guardrail in normalized


def test_next_action_is_one_public_attempt_but_is_not_authorized() -> None:
    preflight = _preflight()

    for field, value in (
        ("proposed_issue_creation_attempts_maximum", "1"),
        ("proposed_publications_maximum", "1"),
        ("proposed_external_retries_maximum", "0"),
        ("proposed_human_upstream_response_reads_maximum", "0"),
        ("proposed_write_receipt_observations_maximum", "1"),
        ("proposed_attachments_allowed", "false"),
        ("explicit_publication_go_required", "true"),
    ):
        assert _field_values(preflight, field) == [value]
    assert "not currently authorized" in preflight
    assert "stop without\nretrying or switching channels" in preflight


def test_public_issue_payload_is_exact_separate_and_safe_to_review() -> None:
    raw = PAYLOAD.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == PAYLOAD_SHA256
    assert _field_values(_preflight(), "public_issue_payload_sha256") == [PAYLOAD_SHA256]
    assert set(payload) == {"body", "title"}
    assert payload["title"] == (
        "Clarification request: component rights and immutable evaluation configuration"
    )
    body = payload["body"]
    assert re.findall(r"^## .+$", body, re.MULTILINE) == [
        "## 1. Component-level rights disposition",
        "## 2. Immutable effective evaluation closure",
    ]
    for internal_control in (
        "DRAFT — LOCAL ONLY",
        "DO NOT SEND",
        "send_authorized",
        "p1_result_sha256",
        "Local stop note",
        DRAFT_COMMIT,
        DRAFT_SHA256,
    ):
        assert internal_control not in body
    assert "http://" not in body.lower()
    assert "https://" not in body.lower()
    assert "@" not in body


def test_preflight_contains_no_personal_contact_or_send_mechanism() -> None:
    preflight = _preflight()
    lowered = preflight.lower()

    for forbidden in (
        "http://",
        "https://",
        "mailto:",
        "curl ",
        "wget ",
        "```python",
        "```bash",
        "api key",
    ):
        assert forbidden not in lowered
    assert "@" not in preflight
    assert not re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", preflight, re.I)
