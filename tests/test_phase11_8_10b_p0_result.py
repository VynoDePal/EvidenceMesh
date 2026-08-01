from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks import run_phase11_8_10b_p0_policy_lock as policy_lock

ROOT = Path(__file__).parents[1]
RESULT = ROOT / "benchmarks/results/phase11_8_10b_p0_policy_comparability_lock_2026-08-01.json"
RESULT_MARKDOWN = (
    ROOT / "benchmarks/results/phase11_8_10b_p0_policy_comparability_lock_2026-08-01.md"
)
METHODOLOGY_COMMIT_SHA = "56989d4674f99184b11f72d18c503c320c65c868"
RESULT_SHA256 = "7e4062e9270eb8dc681783b0aac2ff031ea53310bbd9982c61fea0e458fc3798"


def _load_result() -> tuple[bytes, dict[str, Any]]:
    raw = RESULT.read_bytes()
    return raw, json.loads(raw)


def test_committed_result_is_exact_deterministic_reproduction() -> None:
    raw, report = _load_result()
    expected = policy_lock.run(methodology_commit_sha=METHODOLOGY_COMMIT_SHA)
    expected_raw = (
        json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    )

    assert len(raw) == 6_339
    assert hashlib.sha256(raw).hexdigest() == RESULT_SHA256
    assert report == expected
    assert raw == expected_raw


def test_committed_result_preserves_fail_closed_policy() -> None:
    _raw, report = _load_result()

    assert report["outcome"] == "policy_comparability_lock_complete_acquisition_blocked"
    assert report["engineering_lock"] == "pass"
    assert report["quality_decision"] == "no_go"
    assert report["gate_summary"] == {"failed": 0, "passed": 16, "total": 16}
    assert report["real_external_score"] is False
    assert report["officially_comparable_score_available"] is False
    assert [item["status"] for item in report["candidate_decisions"]] == [
        "blocked",
        "blocked",
    ]
    assert report["selected_policy"]["candidate_suites_admitted_now"] == 0
    assert report["next_evidence_action"] == {
        "action_kind": "browsecomp-plus-immutable-metadata-clarification",
        "candidate_id": "browsecomp_plus",
        "entry_criteria_count": 5,
        "maximum_additional_unique_public_metadata_documents": 5,
        "maximum_benchmark_payload_requests": 0,
        "maximum_provider_or_model_requests": 0,
        "maximum_retries": 0,
        "requires_separate_go": True,
        "stop_criteria_count": 6,
        "success_criteria_count": 3,
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
        )
    )


def test_operation_counts_are_explicitly_attested_not_runtime_instrumented() -> None:
    _raw, report = _load_result()
    attestation = report["operation_attestation"]

    assert attestation["measurement_mode"] == (
        "bounded-process-attestation-and-static-capability-check"
    )
    assert attestation["runtime_network_instrumentation_used"] is False
    assert attestation["public_metadata_documents_consulted"] == 10
    for key, value in attestation.items():
        if key not in {
            "measurement_mode",
            "runtime_network_instrumentation_used",
            "public_metadata_documents_consulted",
        }:
            assert value == 0


def test_result_is_aggregate_only_and_markdown_records_the_same_verdict() -> None:
    raw, _report = _load_result()
    lowered = raw.decode("utf-8").lower()
    markdown = RESULT_MARKDOWN.read_text(encoding="utf-8")

    assert "http://" not in lowered
    assert "https://" not in lowered
    assert str(ROOT).lower() not in lowered
    assert RESULT_SHA256 in markdown
    assert METHODOLOGY_COMMIT_SHA in markdown
    assert "16/16" in markdown
    assert "no_go" in markdown
