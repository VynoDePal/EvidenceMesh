from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks import run_phase11_8_9_offline_retrieval_recovery as offline

ROOT = Path(__file__).parents[1]
RESULT = ROOT / "benchmarks/results/phase11_8_9_offline_retrieval_recovery_2026-07-31.json"
LOCK_COMMIT_SHA = "63e1b95d06173c27d1b7c10ab2b0e486fe5abebd"
RESULT_SHA256 = "cb3f4bd4e2862d4ef170d2c41d17cd7991090f5e933d480d3c76ccab7a197720"


def _report() -> tuple[bytes, dict[str, object]]:
    raw = RESULT.read_bytes()
    return raw, json.loads(raw)


def test_committed_result_is_exact_canonical_reproduction() -> None:
    raw, report = _report()
    assert len(raw) == 14_600
    assert hashlib.sha256(raw).hexdigest() == RESULT_SHA256
    assert report == offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    assert raw == offline.canonical_json_bytes(report)


def test_committed_result_preserves_external_and_governance_boundaries() -> None:
    _raw, report = _report()
    decision = report["decision"]
    assert decision == {
        "external_quality_passed": False,
        "gate_count": 19,
        "merge_allowed": False,
        "offline_outcome": "engineering_conformance_only",
        "passed_gate_count": 12,
        "phase11_9_authorized": False,
        "phase12_authorized": False,
        "product_defaults_change_allowed": False,
        "pull_request_remains_draft_required": True,
        "pull_request_state_verification_required": ("externally_verified_by_github_process"),
        "pull_request_state_verified_by_runner": False,
        "release_allowed": False,
        "release_decision": "no-go",
        "superiority_claim_allowed": False,
    }
    assert set(report["traffic"].values()) == {0}
    assert report["privacy"]["passed"] is True
    assert report["public_schema"] == {
        "failed_contract_count": 0,
        "passed": True,
        "strict_contract_count": 18,
    }

    gates = report["gates"]
    assert len(gates) == 19
    assert all(gates[index - 1]["passed"] is True for index in offline.LOCAL_GATE_NUMBERS)
    external_gate_numbers = (10, 11, 13, 14, 15, 16, 17)
    assert all(gates[index - 1]["passed"] is False for index in external_gate_numbers)
    assert all(gates[index - 1]["status"] == "not_evaluated" for index in external_gate_numbers)

    external = report["external_evaluation"]
    assert external["status"] == "external_evaluation_not_run"
    assert external["complete_locked_assets_present"] is False
    assert external["synthetic_adapter_conformance"]["real_external_score"] is False
    assert all(suite["status"] == "not_evaluated" for suite in external["suite_statuses"].values())

    fixture = report["fixture_evaluation"]
    assert fixture["real_external_score"] is False
    assert fixture["conformance_receipt"] == {
        "collected": 53,
        "errors": 0,
        "failures": 0,
        "passed": 53,
        "registered_test_count": 22,
        "registered_tests_covered": 22,
        "skipped": 0,
        "source_set_sha256": ("d5bf3470536f0a9cb9a527fab7a57480863b7157e23609c73d2e40b50358a125"),
        "status": "passed",
    }
    assert fixture["conformance_registry"]["registered_requirement_count"] == 43
    assert fixture["conformance_registry"]["requirements_with_structural_evidence"] == 43
