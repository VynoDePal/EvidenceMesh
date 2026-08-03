from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.phase11_8_10b_p1_browsecomp_clarification import (
    DEFAULT_MANIFEST_PATH,
    ClarificationLockError,
    build_clarification_report,
    load_manifest,
    validate_manifest,
)

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "benchmarks/phase11_8_10b_p1_browsecomp_clarification.py"
COMMIT = "a" * 40


def _manifest() -> dict[str, Any]:
    return json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_committed_manifest_records_the_exhausted_budget_and_block() -> None:
    manifest = load_manifest()
    report = build_clarification_report(manifest, methodology_commit_sha=COMMIT)

    assert report["outcome"] == "bounded_clarification_complete_admission_blocked"
    assert report["engineering_lock"] == "pass"
    assert report["clarification_decision"] == "no_go"
    assert report["candidate_id"] == "browsecomp_plus"
    assert report["candidate_admitted"] is False
    assert report["gate_summary"] == {"passed": 18, "failed": 0, "total": 18}
    assert report["research_budget"] == {
        "predecessor_documents": 10,
        "new_documents": 5,
        "cumulative_documents": 15,
        "maximum_documents": 15,
        "remaining_documents": 0,
        "source_ceiling_exhausted": True,
    }
    assert report["clarification_gates"] == {
        "component_rights": "blocked",
        "prompt_and_algorithm_source": "partial",
        "qwen_candidate_revision_identified": True,
        "runner_binds_qwen_candidate_revision": False,
        "tokenizer_revision_locked": False,
        "resolved_runtime_dependency_lock_complete": False,
        "judge_and_runtime": "blocked",
        "end_to_end_comparability": "blocked",
    }
    assert report["stop"]["criterion_triggered"] is True
    assert report["stop"]["additional_metadata_documents_allowed"] == 0
    assert report["source_identity"]["moving_context_document_closed_no_gate"] is True
    assert report["source_identity"]["no_go_independent_of_moving_context_document"] is True


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value.__setitem__("new_permission", True),
            "top-level schema",
        ),
        (
            lambda value: value["phase_policy"].__setitem__("asset_acquisition_allowed", True),
            "phase_policy content",
        ),
        (
            lambda value: value["research_budget"].__setitem__(
                "additional_metadata_documents_allowed", 1
            ),
            "research_budget content",
        ),
        (
            lambda value: value["new_consulted_primary_documents"].append(
                copy.deepcopy(value["new_consulted_primary_documents"][0])
            ),
            "new_consulted_primary_documents content",
        ),
        (
            lambda value: value["new_consulted_primary_documents"][0].__setitem__(
                "payload_accessed", True
            ),
            "new_consulted_primary_documents content",
        ),
        (
            lambda value: value["clarification_gate_decisions"]["component_rights"].__setitem__(
                "clearance_complete", True
            ),
            "clarification_gate_decisions content",
        ),
        (
            lambda value: value["clarification_gate_decisions"]["judge_and_runtime"].__setitem__(
                "runner_binds_qwen_candidate_revision", True
            ),
            "clarification_gate_decisions content",
        ),
        (
            lambda value: value["aggregate_decision"].__setitem__(
                "stop_criterion_triggered", False
            ),
            "aggregate_decision content",
        ),
        (
            lambda value: value["single_recommended_next_step"].__setitem__(
                "external_contact_allowed", True
            ),
            "single_recommended_next_step content",
        ),
    ],
)
def test_manifest_mutations_fail_closed(mutator: Any, message: str) -> None:
    manifest = _manifest()
    mutator(manifest)
    with pytest.raises(ClarificationLockError, match=message):
        validate_manifest(manifest)


def test_report_is_aggregate_only_and_operation_counts_are_attested() -> None:
    report = build_clarification_report(load_manifest(), methodology_commit_sha=COMMIT)
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
        "recorded-historical-assertion-plus-static-runner-capability-check"
    )
    assert attestation["historical_counts_are_process_attestations"] is True
    assert attestation["runtime_network_instrumentation_used"] is False
    assert attestation["new_public_metadata_documents_consulted"] == 5
    for key, value in attestation.items():
        if key not in {
            "measurement_mode",
            "historical_counts_are_process_attestations",
            "runtime_network_instrumentation_used",
            "new_public_metadata_documents_consulted",
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
            "importlib",
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
