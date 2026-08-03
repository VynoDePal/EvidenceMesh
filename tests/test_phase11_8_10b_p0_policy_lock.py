from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.phase11_8_10b_p0_policy_lock import (
    DEFAULT_POLICY_PATH,
    PolicyLockError,
    build_policy_report,
    load_policy,
    validate_policy,
)

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "benchmarks/phase11_8_10b_p0_policy_lock.py"
COMMIT = "a" * 40


def _policy() -> dict[str, Any]:
    return json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))


def _candidate(policy: dict[str, Any], suite_id: str) -> dict[str, Any]:
    return next(item for item in policy["candidate_decisions"] if item["suite_id"] == suite_id)


def test_committed_policy_locks_the_recommended_fail_closed_decision() -> None:
    policy = load_policy()
    report = build_policy_report(policy, methodology_commit_sha=COMMIT)

    assert report["outcome"] == "policy_comparability_lock_complete_acquisition_blocked"
    assert report["engineering_lock"] == "pass"
    assert report["quality_decision"] == "no_go"
    assert report["real_external_score"] is False
    assert report["officially_comparable_score_available"] is False
    assert report["gate_summary"] == {"passed": 16, "failed": 0, "total": 16}
    assert report["selected_policy"] == {
        "option_id": "technical_alpha_isolated",
        "official_score_target": "officially-comparable-external-score",
        "one_authoritative_suite_may_suffice_later": True,
        "candidate_suites_admitted_now": 0,
        "asset_acquisition_before_clearance": False,
    }
    assert [item["status"] for item in report["candidate_decisions"]] == [
        "blocked",
        "blocked",
    ]
    assert report["research_budget"] == {
        "maximum_unique_public_metadata_documents": 15,
        "consulted_unique_public_metadata_documents": 10,
        "remaining_unique_public_metadata_documents": 5,
        "raw_transport_request_count_used_as_budget": False,
    }


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["phase_policy"].__setitem__(
                "internal-proxy-score_is_acceptable_substitute", True
            ),
            "proxy",
        ),
        (
            lambda value: value["phase_policy"].__setitem__("asset_acquisition_allowed", True),
            "asset_acquisition_allowed",
        ),
        (
            lambda value: value["phase_policy"].__setitem__("new_permission_allowed", True),
            "schema drifted",
        ),
        (
            lambda value: value["phase_policy"]["candidate_suites_admitted_now"].append("bright"),
            "admitted",
        ),
        (
            lambda value: value["research_budget"].__setitem__(
                "maximum_unique_public_metadata_documents", 16
            ),
            "ceiling",
        ),
        (
            lambda value: value["consulted_primary_documents"].append(
                copy.deepcopy(value["consulted_primary_documents"][0])
            ),
            "ten documents",
        ),
        (
            lambda value: value["consulted_primary_documents"][0].__setitem__(
                "url", "https://github.com/xlang-ai/BRIGHT/blob/main/README.md"
            ),
            "URL",
        ),
        (
            lambda value: value["consulted_primary_documents"][0].__setitem__(
                "payload_accessed", True
            ),
            "payload accessed",
        ),
        (
            lambda value: _candidate(value, "bright").__setitem__(
                "component_rights_clearance_complete", True
            ),
            "component rights",
        ),
        (
            lambda value: _candidate(value, "bright").__setitem__("comparability_complete", True),
            "comparability_complete",
        ),
        (
            lambda value: _candidate(value, "browsecomp_plus").__setitem__(
                "qwen_judge_identity_lock_complete", True
            ),
            "qwen_judge",
        ),
        (
            lambda value: _candidate(value, "browsecomp_plus").__setitem__(
                "official_population_mapping_complete", False
            ),
            "population mapping",
        ),
        (
            lambda value: value["inferences"].__setitem__(2, copy.deepcopy(value["inferences"][1])),
            "duplicate inference|order or id",
        ),
        (
            lambda value: value["facts"]["bright"][0].__setitem__(
                "source_ids", ["browsecomp_plus_code_license"]
            ),
            "fact sources|another suite",
        ),
        (
            lambda value: value["recommended_decision"].__setitem__("one_suite_selected_now", True),
            "too early",
        ),
        (
            lambda value: value["next_evidence_action"]["stop_criteria"].__setitem__(
                5, "continue even when one required gate remains unresolved"
            ),
            "stop criteria",
        ),
        (
            lambda value: value["next_evidence_action"].__setitem__(
                "maximum_provider_or_model_requests", 1
            ),
            "must remain zero",
        ),
    ],
)
def test_policy_mutations_fail_closed(mutator: Any, message: str) -> None:
    policy = _policy()
    mutator(policy)
    with pytest.raises(PolicyLockError, match=message):
        validate_policy(policy)


def test_report_is_aggregate_only_and_contains_no_public_source_urls() -> None:
    report = build_policy_report(load_policy(), methodology_commit_sha=COMMIT)
    serialized = json.dumps(report, sort_keys=True).lower()

    for forbidden in (
        "http://",
        "https://",
        "query_id",
        "canary",
        "answer",
        "passage",
        "evidence_mesh_gemini_key",
        "evidence_mesh_tavily_key",
        str(ROOT).lower(),
    ):
        assert forbidden not in serialized
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


def test_validator_has_no_network_process_environment_or_payload_capability() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert imported_roots.isdisjoint(
        {
            "aiohttp",
            "asyncio",
            "base64",
            "boto3",
            "datasets",
            "google",
            "huggingface_hub",
            "httpx",
            "mistralai",
            "openai",
            "os",
            "requests",
            "socket",
            "subprocess",
            "tavily",
            "urllib",
        }
    )
    assert calls.isdisjoint(
        {
            "__import__",
            "b64decode",
            "compile",
            "decrypt",
            "eval",
            "exec",
            "getenv",
            "load_dataset",
            "popen",
            "system",
            "urlopen",
        }
    )
