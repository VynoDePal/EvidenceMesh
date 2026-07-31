from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks import run_phase11_8_10a_asset_preflight as preflight

ROOT = Path(__file__).parents[1]
RESULT = ROOT / "benchmarks/results/phase11_8_10a_asset_reconnaissance_2026-07-31.json"
METHODOLOGY_COMMIT_SHA = "619ce675ba28d1411658af52002828c544dafbd7"
RESULT_SHA256 = "3e0c2d7e99778d71f773a980a4212cd44fd8960fd1ee7d142350867345c9310d"


def _load_result() -> tuple[bytes, dict[str, Any]]:
    raw = RESULT.read_bytes()
    return raw, json.loads(raw)


def _walk(value: object) -> list[object]:
    values = [value]
    if isinstance(value, dict):
        for key, child in value.items():
            values.extend((key, *_walk(child)))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk(child))
    return values


def test_committed_result_is_exact_canonical_reproduction() -> None:
    raw, report = _load_result()
    expected = preflight.run(methodology_commit_sha=METHODOLOGY_COMMIT_SHA)
    expected_raw = (
        json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    )

    assert len(raw) == 4_337
    assert hashlib.sha256(raw).hexdigest() == RESULT_SHA256
    assert report == expected
    assert raw == expected_raw


def test_committed_result_preserves_policy_and_governance_boundaries() -> None:
    _raw, report = _load_result()

    assert report["outcome"] == "asset_integrity_lock_complete_policy_blocked"
    assert report["quality_decision"] == "no_go"
    assert report["gate_summary"] == {"failed": 0, "passed": 15, "total": 15}
    assert report["external_evaluation_status"] == "not_run"
    assert report["real_external_score"] is False
    assert set(report["traffic"].values()) == {0}
    assert report["readiness"] == {
        "acquisition_eligible": False,
        "benchmark_comparability_complete": False,
        "component_license_clearance_complete": False,
        "evaluation_eligible": False,
        "local_assets_admitted": False,
        "metadata_lock_complete": True,
        "next_phase_requires_separate_go": True,
        "object_inventory_complete": True,
    }
    assert not any(
        report["governance"][key]
        for key in (
            "default_promotion_allowed",
            "merge_allowed",
            "phase_11_8_10b_authorized",
            "phase_11_9_authorized",
            "release_allowed",
            "superiority_claim_allowed",
        )
    )
    assert report["governance"]["pull_request_must_remain_draft"] is True
    assert report["governance"]["phase12_accesses"] == 0


def test_committed_result_is_aggregate_only() -> None:
    _raw, report = _load_result()
    values = _walk(report)
    string_values = [value for value in values if isinstance(value, str)]

    assert not {"answer", "content", "document", "passage", "query", "text", "url"}.intersection(
        value for value in string_values
    )
    assert not any(value.startswith(("http://", "https://")) for value in string_values)
    assert not any("/workspace/" in value or "\\workspace\\" in value for value in string_values)
