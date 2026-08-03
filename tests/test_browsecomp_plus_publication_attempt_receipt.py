from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
RECEIPT = ROOT / "docs/browsecomp-plus-publication-attempt-receipt-v1.md"
PREFLIGHT = ROOT / "docs/browsecomp-plus-contact-preflight-v1.md"
PAYLOAD = ROOT / "docs/browsecomp-plus-public-issue-payload-v1.json"
PREFLIGHT_COMMIT = "3eeedaff65700ecf969db0d427fdc13f9b521728"
PREFLIGHT_SHA256 = "538bc6f8cec30f784e47ac5fc01894f221cff6ed3534886274e922fa0856cbbf"
PAYLOAD_SHA256 = "2225c5f25641ecfef944ffb55bd34403753ef8a1c4c191db520857af3660e77c"


def _receipt() -> str:
    return RECEIPT.read_text(encoding="utf-8")


def _field_values(document: str, field: str) -> list[str]:
    return re.findall(rf"`{re.escape(field)}: ([^`]+)`", document)


def test_receipt_is_bound_to_preflight_and_exact_payload() -> None:
    receipt = _receipt()

    assert hashlib.sha256(PREFLIGHT.read_bytes()).hexdigest() == PREFLIGHT_SHA256
    assert hashlib.sha256(PAYLOAD.read_bytes()).hexdigest() == PAYLOAD_SHA256
    assert _field_values(receipt, "parent_preflight_commit") == [PREFLIGHT_COMMIT]
    assert _field_values(receipt, "parent_preflight_sha256") == [PREFLIGHT_SHA256]
    assert _field_values(receipt, "public_issue_payload_sha256") == [PAYLOAD_SHA256]


def test_receipt_records_one_failed_attempt_and_no_retry() -> None:
    receipt = _receipt()

    expected = {
        "issue_creation_attempts_authorized": "1",
        "issue_creation_attempts_performed": "1",
        "issue_creation_attempts_remaining": "0",
        "external_retries_authorized": "0",
        "external_retries_performed": "0",
        "publications_succeeded": "0",
        "write_receipt_observations": "1",
        "human_upstream_response_reads": "0",
        "issue_created": "false",
        "issue_number": "null",
        "issue_url": "null",
    }
    for field, value in expected.items():
        assert _field_values(receipt, field) == [value]


def test_receipt_records_exact_connector_failure() -> None:
    receipt = _receipt()

    expected = {
        "status": "issue-publication-failed-closed",
        "target_repository": "texttron/BrowseComp-Plus",
        "github_operation": "github_create_issue",
        "http_status": "403",
        "error_code": "FORBIDDEN",
        "error_message": "Resource not accessible by integration",
        "failure_class": "integration-write-permission-block",
    }
    for field, value in expected.items():
        assert _field_values(receipt, field) == [value]


def test_receipt_keeps_inferences_fail_closed() -> None:
    normalized = " ".join(_receipt().lower().split())

    for guardrail in (
        "does not prove that repository issues are disabled",
        "does not prove that repository issues are disabled, that the repository maintainers "
        "rejected the request",
        "adds no benchmark evidence",
        "no retry, alternate github tool, cli fallback, issue lookup, response read or channel "
        "switch was performed",
    ):
        assert guardrail in normalized


def test_receipt_machine_fields_are_unique() -> None:
    fields = re.findall(r"^- `([a-z0-9_]+): [^`]+`$", _receipt(), re.MULTILINE)

    assert len(fields) == len(set(fields))


def test_manual_handoff_is_bounded_and_requires_a_separate_go() -> None:
    receipt = _receipt()
    expected = {
        "proposed_manual_issue_attempts_maximum": "1",
        "proposed_manual_publications_maximum": "1",
        "proposed_manual_retries_maximum": "0",
        "proposed_manual_attachments_allowed": "false",
        "proposed_manual_human_response_reads_maximum": "0",
        "manual_publication_go_required": "true",
    }

    for field, value in expected.items():
        assert _field_values(receipt, field) == [value]
    assert "explicit user decision; it is not authorized or performed by this receipt" in receipt
