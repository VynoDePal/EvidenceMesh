from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
POLICY = ROOT / "alpha/local_technical_alpha_v0_1_0_policy_v1.json"
PROTOCOL = ROOT / "docs/local-technical-alpha-v0.1.0-policy-v1.md"
MANUAL_RECEIPT = ROOT / "docs/browsecomp-plus-manual-issue-28-receipt-v1.md"
CONNECTOR_RECEIPT = ROOT / "docs/browsecomp-plus-publication-attempt-receipt-v1.md"
V27 = ROOT / "docs/benchmark-protocol-v27.md"
V28 = ROOT / "docs/benchmark-protocol-v28.md"

CONNECTOR_RECEIPT_SHA256 = "f8144511d2dd46d751cd7fa062f0db3be014f2ff2e6181b8a928cb0b93a003da"
V27_SHA256 = "8346b69b1b7261eaf94028d5f2ac2e40bc028b49db0ea68f4f779083680ab0c6"
V28_SHA256 = "e52fb157d32003b21c2af3497b2aa1b642dada68c480231380b4c6a751211e26"
PAYLOAD_SHA256 = "2225c5f25641ecfef944ffb55bd34403753ef8a1c4c191db520857af3660e77c"
COMMENT_SHA256 = "cffc9bc965bd8dbddffba75e804a3b45c89a3b03750164798fac4aa326045287"
ISSUE_URL = "https://github.com/texttron/BrowseComp-Plus/issues/28"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict[str, Any]:
    return json.loads(POLICY.read_bytes())


def _manual_receipt() -> str:
    return MANUAL_RECEIPT.read_text(encoding="utf-8")


def _field_values(document: str, field: str) -> list[str]:
    return re.findall(rf"`{re.escape(field)}: ([^`]+)`", document)


def _normalized(document: str) -> str:
    return " ".join(document.split())


def test_exact_local_alpha_identity_is_offline_and_unpublished() -> None:
    policy = _policy()
    candidate = policy["candidate"]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert policy["schema_version"] == "evidencemesh.local-technical-alpha-v0.1.0-policy.v1"
    assert candidate == {
        "commit_sha": "644064b5fa097bbf7055f3bf4335ea613afb6387",
        "current_head_claimed_as_candidate": False,
        "local_tag": "v0.1.0-alpha.local",
        "package_version": "0.1.0",
        "scope": "exact-tag-local-offline-only",
        "status": "validated_local_unpublished",
    }
    assert project["project"]["version"] == candidate["package_version"]
    assert '__version__ = "0.1.0"' in (ROOT / "src/evidencemesh/__init__.py").read_text(
        encoding="utf-8"
    )


def test_frozen_protocol_and_connector_receipt_bytes_are_bound_exactly() -> None:
    policy = _policy()
    basis = policy["basis"]

    assert _sha256(CONNECTOR_RECEIPT) == CONNECTOR_RECEIPT_SHA256
    assert _sha256(V27) == V27_SHA256
    assert _sha256(V28) == V28_SHA256
    assert basis["browsecomp_plus_connector_attempt_receipt"] == {
        "historical_result": "connector_write_failed_http_403",
        "path": "docs/browsecomp-plus-publication-attempt-receipt-v1.md",
        "sha256": CONNECTOR_RECEIPT_SHA256,
        "superseded": False,
    }
    connector = CONNECTOR_RECEIPT.read_text(encoding="utf-8")
    assert "`http_status: 403`" in connector
    assert "`issue_created: false`" in connector


def test_manual_issue_is_only_a_weak_user_browser_attestation() -> None:
    policy = _policy()
    publication = policy["manual_issue_publication"]
    receipt = _manual_receipt()

    assert publication == {
        "context_comment_sha256_user_attested": COMMENT_SHA256,
        "initial_payload_sha256_user_attested": PAYLOAD_SHA256,
        "issue_number": 28,
        "issue_url": ISSUE_URL,
        "local_github_write_receipt_available": False,
        "remote_content_cryptographically_verified": False,
        "source": "user_and_browser_attestations_in_conversation",
        "state": "manual_browser_user_attested",
    }
    assert _field_values(receipt, "state") == ["manual_browser_user_attested"]
    assert _field_values(receipt, "issue_url") == [ISSUE_URL]
    assert _field_values(receipt, "initial_payload_sha256_user_attested") == [PAYLOAD_SHA256]
    assert _field_values(receipt, "context_comment_sha256_user_attested") == [COMMENT_SHA256]
    assert _field_values(receipt, "remote_content_cryptographically_verified") == ["false"]
    assert "not cryptographic proof of the content currently served by GitHub" in _normalized(
        receipt
    )
    assert receipt.count("manual_browser_user_attested") == 1


def test_permanent_silence_and_every_unread_response_state_are_nonblocking() -> None:
    policy = _policy()
    independence = policy["response_independence"]

    assert independence["local_alpha_response_dependency"] == "none"
    assert independence["permanent_silence_preserves_local_alpha"] is True
    assert independence["automatic_polling_allowed"] is False
    assert independence["response_ingestion_requires_separate_explicit_go"] is True
    assert independence["local_alpha_decision_for_all_response_states"] == (
        "validated_local_unpublished"
    )
    assert set(independence["response_states_with_identical_local_alpha_decision"]) == {
        "no_response_observed",
        "response_exists_but_is_not_read_or_ingested",
        "permanent_silence",
    }
    assert "Permanent silence is permitted" in PROTOCOL.read_text(encoding="utf-8")


def test_external_candidates_phases_v1_and_release_remain_blocked() -> None:
    policy = _policy()
    admission = policy["external_benchmark_admission"]
    phases = policy["phase_boundaries"]
    authority = policy["authority"]

    assert admission["candidate_suites_admitted"] == 0
    assert admission["official_external_score_available"] is False
    assert admission["bright"] == {"admitted": False, "status": "blocked"}
    assert admission["browsecomp_plus"]["admitted"] is False
    assert admission["browsecomp_plus"]["status"] == "blocked"
    assert admission["browsecomp_plus"]["response_required_for_local_alpha"] is False
    assert phases["phase_11_9"] == {"authorized": False, "status": "blocked"}
    assert phases["phase_12"] == {
        "authorized": False,
        "executed": False,
        "seal_preserved": True,
        "status": "sealed_blocked",
    }
    assert phases["v1"] == {"readiness": False, "status": "no_go"}
    assert not any(phases["release"].values())
    assert authority["local_offline_technical_alpha_allowed"] is True
    for key, value in authority.items():
        if key != "local_offline_technical_alpha_allowed":
            assert value is False, key


def test_local_and_future_budgets_are_all_exact_integer_zero() -> None:
    budgets = _policy()["budgets"]

    assert set(budgets) == {"future_without_separate_explicit_go", "local_technical_alpha"}
    assert budgets["future_without_separate_explicit_go"] == budgets["local_technical_alpha"]
    for scope, values in budgets.items():
        assert values, scope
        for dimension, value in values.items():
            assert type(value) is int, (scope, dimension)
            assert value == 0, (scope, dimension)


def test_documents_preserve_publication_and_quality_boundaries() -> None:
    protocol = PROTOCOL.read_text(encoding="utf-8")
    receipt = _manual_receipt()
    normalized_protocol = _normalized(protocol)

    for marker in (
        "Phase 11.9 remains blocked",
        "Phase 12 remains sealed and blocked",
        "V1 readiness remains false",
        "public release remains false",
        "Every such local-alpha budget is zero",
    ):
        assert marker in normalized_protocol
    assert CONNECTOR_RECEIPT_SHA256 in protocol
    assert CONNECTOR_RECEIPT_SHA256 in receipt
    assert PAYLOAD_SHA256 in protocol and COMMENT_SHA256 in protocol
    assert "No human upstream response was read or ingested" in receipt
