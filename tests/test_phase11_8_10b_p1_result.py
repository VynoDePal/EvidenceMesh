from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks import run_phase11_8_10b_p1_browsecomp_clarification as clarification

ROOT = Path(__file__).parents[1]
RESULT = ROOT / "benchmarks/results/phase11_8_10b_p1_browsecomp_clarification_2026-08-01.json"
RESULT_MARKDOWN = (
    ROOT / "benchmarks/results/phase11_8_10b_p1_browsecomp_clarification_2026-08-01.md"
)
METHODOLOGY_COMMIT_SHA = "1b871eed97039a356b35e7eea5b505b057047388"
RESULT_SHA256 = "90336e77544b5ba7a3c4ddf21cf9f535377a57c19c5756941f67ee2304d00016"


def _load_result() -> tuple[bytes, dict[str, Any]]:
    raw = RESULT.read_bytes()
    return raw, json.loads(raw)


def test_committed_result_is_exact_deterministic_reproduction() -> None:
    raw, report = _load_result()
    expected = clarification.run(methodology_commit_sha=METHODOLOGY_COMMIT_SHA)
    expected_raw = (
        json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    )

    assert len(raw) == 6_135
    assert hashlib.sha256(raw).hexdigest() == RESULT_SHA256
    assert report == expected
    assert raw == expected_raw


def test_committed_result_preserves_fail_closed_clarification() -> None:
    _raw, report = _load_result()

    assert report["outcome"] == "bounded_clarification_complete_admission_blocked"
    assert report["engineering_lock"] == "pass"
    assert report["clarification_decision"] == "no_go"
    assert report["candidate_id"] == "browsecomp_plus"
    assert report["candidate_admitted"] is False
    assert report["gate_summary"] == {"failed": 0, "passed": 18, "total": 18}
    assert report["research_budget"] == {
        "cumulative_documents": 15,
        "maximum_documents": 15,
        "new_documents": 5,
        "predecessor_documents": 10,
        "remaining_documents": 0,
        "source_ceiling_exhausted": True,
    }
    assert report["clarification_gates"]["component_rights"] == "blocked"
    assert report["clarification_gates"]["prompt_and_algorithm_source"] == "partial"
    assert report["clarification_gates"]["judge_and_runtime"] == "blocked"
    assert report["clarification_gates"]["end_to_end_comparability"] == "blocked"
    assert report["stop"]["criterion_triggered"] is True
    assert report["stop"]["additional_metadata_documents_allowed"] == 0
    assert report["source_lock"]["source_count"] == 14
    assert report["next_step"] == {
        "action_kind": "prepare-local-unsent-upstream-clarification-request",
        "external_contact_allowed": False,
        "maximum_external_requests": 0,
        "maximum_publications": 0,
        "maximum_retries": 0,
        "sending_requires_separate_explicit_go": True,
    }
    assert not any(
        report["governance"][key]
        for key in (
            "merge_allowed",
            "phase_11_8_10b_acquisition_authorized",
            "phase_11_9_authorized",
            "phase_12_authorized",
            "release_allowed",
            "superiority_claim_allowed",
            "upstream_contact_authorized",
        )
    )


def test_operation_counts_are_process_attestations_not_runtime_instrumentation() -> None:
    _raw, report = _load_result()
    attestation = report["operation_attestation"]

    assert attestation["measurement_mode"] == (
        "recorded-historical-assertion-plus-static-runner-capability-check"
    )
    assert attestation["historical_counts_are_process_attestations"] is True
    assert attestation["runtime_network_instrumentation_used"] is False
    assert attestation["new_public_metadata_documents_consulted"] == 5
    for key, value in attestation.items():
        if key not in {
            "historical_counts_are_process_attestations",
            "measurement_mode",
            "new_public_metadata_documents_consulted",
            "runtime_network_instrumentation_used",
        }:
            assert value == 0


def test_result_is_aggregate_only_and_markdown_records_the_same_verdict() -> None:
    raw, _report = _load_result()
    lowered = raw.decode("utf-8").lower()
    markdown = RESULT_MARKDOWN.read_text(encoding="utf-8")

    for forbidden in (
        "http://",
        "https://",
        "query_id",
        "canary",
        "answer",
        "passage",
        str(ROOT).lower(),
    ):
        assert forbidden not in lowered
    assert RESULT_SHA256 in markdown
    assert METHODOLOGY_COMMIT_SHA in markdown
    assert "18/18" in markdown
    assert "no_go" in markdown
    assert "0 requête externe, 0 retry, 0 publication" in markdown
