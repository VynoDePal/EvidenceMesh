"""Fail-closed BrowseComp-Plus metadata clarification for Phase 11.8.10B-P1.

This module validates committed public-metadata conclusions only. It cannot
download, inspect, decrypt, evaluate, judge, score, contact an upstream party,
read secrets, spawn a process, inspect the environment, or use a network.
"""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

MANIFEST_SCHEMA = "evidencemesh.phase11_8_10b_p1.browsecomp-clarification.v1"
RESULT_SCHEMA = "evidencemesh.phase11_8_10b_p1.browsecomp-clarification-result.v1"
DEFAULT_MANIFEST_PATH = (
    Path(__file__).parent / "data/phase11_8_10b_p1_browsecomp_clarification_v1.json"
)
MAX_MANIFEST_BYTES = 256 * 1024
EXPECTED_PREDECESSOR_FILES = {
    "policy_manifest": (
        "benchmarks/data/phase11_8_10b_p0_policy_comparability_lock_v1.json",
        "09e9dfb6475ccf40ffa4d844684ac7036c0255f35e2ad7c6fdeb5e0fe1027082",
    ),
    "protocol": (
        "docs/benchmark-protocol-v27.md",
        "8346b69b1b7261eaf94028d5f2ac2e40bc028b49db0ea68f4f779083680ab0c6",
    ),
    "result": (
        "benchmarks/results/phase11_8_10b_p0_policy_comparability_lock_2026-08-01.json",
        "7e4062e9270eb8dc681783b0aac2ff031ea53310bbd9982c61fea0e458fc3798",
    ),
    "source_lock": (
        "benchmarks/data/phase11_8_10b_p0_source_locks_v1.json",
        "045b28d1da12ee11f2ca9083d6ea8648de8827f9e80c396f12d8bb6e8ccf93ff",
    ),
}
EXPECTED_SECTION_SHA256 = {
    "predecessor_lock": "c8d05cf323f8c6ca480861898fb7013baa958077f9522a807131c34b12a4703a",
    "phase_policy": "ec7deab7beaed92fb6638d8cbc6c31bda5a4a718dd3e584b73b370426dc6b113",
    "research_budget": "33fdca9e12fc46184a49458e86be47d250f5525c157cc75d831b379896356884",
    "new_consulted_primary_documents": (
        "977146af911130a8096e32be37de92e399623d43ca6ab654852f814a1acd5de8"
    ),
    "facts": "e8b2170a54ad6a145af523796e45f280c10790b96a1e5fd3870fadeaa11ebea5",
    "inferences": "f70816dd9809767858230589a566139a3b12c35621b9cd8f16b3492c9f377840",
    "clarification_gate_decisions": (
        "3366120bafb35b57a58e2978e4fcc75175a0eaacffa68ab2683557fea76fa25c"
    ),
    "aggregate_decision": "9fe682aa9f85cdd9a982cb45c1747c0069cef374914e090817ebda5bd7cb9b7c",
    "single_recommended_next_step": (
        "cc0a02da3dfed6f3a2facd2ebd1dfd080eb225adbbf222b08baf8b2a9fbbab05"
    ),
}
EXPECTED_SOURCE_IDS = (
    "browsecomp_plus_evaluation_runner",
    "browsecomp_plus_project_dependencies",
    "browsecomp_plus_paper_v1",
    "openai_browsecomp_official_page",
    "qwen3_32b_candidate_model_card",
)
EXPECTED_SOURCE_URLS = (
    "https://github.com/texttron/BrowseComp-Plus/blob/"
    "046949032b0328319cc9a02663a759ec601d9402/"
    "scripts_evaluation/evaluate_run.py",
    "https://github.com/texttron/BrowseComp-Plus/blob/"
    "046949032b0328319cc9a02663a759ec601d9402/pyproject.toml",
    "https://arxiv.org/abs/2508.06600v1",
    "https://openai.com/index/browsecomp/",
    "https://huggingface.co/Qwen/Qwen3-32B/blob/9216db5781bf21249d130ec9da846c4624c16137/README.md",
)
EXPECTED_QWEN_REVISION = "9216db5781bf21249d130ec9da846c4624c16137"


class ClarificationLockError(ValueError):
    """Raised when the bounded clarification ceases to be fail-closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ClarificationLockError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return cast(dict[str, Any], value)


def _array(value: object, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label} must be an array")
    return cast(list[Any], value)


def _lower_hex(value: object, length: int, label: str) -> str:
    _require(isinstance(value, str), f"{label} must be a string")
    text = cast(str, value)
    _require(len(text) == length, f"{label} must be {length} lowercase hex characters")
    _require(all(character in "0123456789abcdef" for character in text), f"{label} is not hex")
    return text


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    _require(path == DEFAULT_MANIFEST_PATH, "manifest path is frozen")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ClarificationLockError("cannot stat clarification manifest") from exc
    _require(stat.S_ISREG(metadata.st_mode), "manifest must be a regular file")
    _require(not path.is_symlink(), "manifest must not be a symlink")
    _require(metadata.st_size <= MAX_MANIFEST_BYTES, "manifest is too large")
    try:
        decoded = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClarificationLockError("manifest is not valid UTF-8 JSON") from exc
    manifest = _object(decoded, "manifest")
    validate_manifest(manifest)
    return manifest


def _validate_predecessor(manifest: Mapping[str, Any]) -> None:
    predecessor = _object(manifest.get("predecessor_lock"), "predecessor_lock")
    _require(predecessor.get("phase") == "11.8.10B-P0", "predecessor phase drifted")
    _require(
        predecessor.get("methodology_commit") == "56989d4674f99184b11f72d18c503c320c65c868",
        "predecessor methodology commit drifted",
    )
    _require(
        predecessor.get("methodology_tree") == "5db66c294420c901e63ad7c276ba430a0f50ac33",
        "predecessor methodology tree drifted",
    )
    _require(
        predecessor.get("result_commit") == "f05498eb59dae75b02d176f2c0d6a53d4246df0f",
        "predecessor result commit drifted",
    )
    _require(
        predecessor.get("result_tree") == "7c7f366d3aef562aec387443d9432a27d5c5488b",
        "predecessor result tree drifted",
    )
    for record_id, (expected_path, expected_hash) in EXPECTED_PREDECESSOR_FILES.items():
        record = _object(predecessor.get(record_id), f"predecessor.{record_id}")
        _require(record.get("path") == expected_path, f"predecessor {record_id} path drifted")
        _require(
            record.get("sha256") == expected_hash,
            f"predecessor {record_id} hash drifted",
        )
    result = _object(predecessor.get("result"), "predecessor.result")
    _require(result.get("engineering_gates_passed") == 16, "P0 passed gate count drifted")
    _require(result.get("engineering_gates_total") == 16, "P0 total gate count drifted")
    _require(result.get("quality_decision") == "no_go", "P0 no-go drifted")
    _require(result.get("candidate_suites_admitted") == 0, "P0 candidate count drifted")
    _require(
        result.get("remaining_unique_public_metadata_documents") == 5,
        "P0 remaining source budget drifted",
    )


def _validate_phase_policy(manifest: Mapping[str, Any]) -> None:
    policy = _object(manifest.get("phase_policy"), "phase_policy")
    _require(policy.get("mode") == "metadata-only-local-fail-closed", "mode drifted")
    _require(policy.get("candidate_id") == "browsecomp_plus", "candidate drifted")
    _require(policy.get("bright_decision_frozen_from_p0") is True, "BRIGHT decision changed")
    _require(
        policy.get("official_score_target")
        == "browsecomp-plus-fixed-corpus-officially-comparable-score",
        "official score target drifted",
    )
    _require(
        policy.get("internal_proxy_score_is_acceptable_substitute") is False,
        "internal proxy was enabled",
    )
    forbidden = (
        "asset_acquisition_allowed",
        "asset_payload_download_allowed",
        "asset_payload_open_or_parse_allowed",
        "distribution_allowed",
        "evaluation_allowed",
        "judge_requests_allowed",
        "model_requests_allowed",
        "phase_11_9_allowed",
        "phase_12_allowed",
        "provider_requests_allowed",
        "publication_allowed",
        "query_decryption_allowed",
        "retrieval_requests_allowed",
        "scoring_requests_allowed",
        "secret_access_allowed",
        "v1_quality_claim_allowed",
    )
    for key in forbidden:
        _require(policy.get(key) is False, f"{key} must remain false")
    _require(
        policy.get("next_external_action_requires_separate_go") is True,
        "separate GO boundary drifted",
    )


def _validate_budget_and_sources(manifest: Mapping[str, Any]) -> None:
    budget = _object(manifest.get("research_budget"), "research_budget")
    _require(budget.get("maximum_unique_public_metadata_documents") == 15, "ceiling drifted")
    _require(
        budget.get("predecessor_consulted_unique_public_metadata_documents") == 10,
        "predecessor document count drifted",
    )
    _require(budget.get("p1_new_unique_public_metadata_documents") == 5, "P1 count drifted")
    _require(
        budget.get("cumulative_consulted_unique_public_metadata_documents") == 15,
        "cumulative count drifted",
    )
    _require(budget.get("remaining_unique_public_metadata_documents") == 0, "budget remains")
    _require(budget.get("source_ceiling_exhausted") is True, "ceiling not exhausted")
    _require(budget.get("additional_metadata_documents_allowed") == 0, "extra source enabled")
    _require(
        budget.get("historical_operation_counts_are_process_attestations") is True,
        "historical operation attestation qualifier drifted",
    )
    for key in (
        "benchmark_payload_requests",
        "benchmark_provider_model_or_judge_retries",
        "decryption_requests",
        "judge_requests",
        "model_requests",
        "provider_requests",
        "publication_requests",
        "retrieval_requests",
        "scoring_requests",
        "secret_requests",
    ):
        _require(budget.get(key) == 0, f"{key} must remain zero")

    sources = _array(manifest.get("new_consulted_primary_documents"), "sources")
    _require(len(sources) == 5, "exactly five new sources are required")
    observed_ids: list[str] = []
    observed_urls: list[str] = []
    for source in sources:
        record = _object(source, "source")
        source_id = record.get("source_id")
        url = record.get("url")
        _require(isinstance(source_id, str), "source id must be a string")
        _require(isinstance(url, str), "source URL must be a string")
        observed_ids.append(source_id)
        observed_urls.append(url)
        _require(record.get("payload_accessed") is False, f"payload accessed: {source_id}")
        _require(
            record.get("local_content_digest_verified") is False,
            f"local content digest overstated: {source_id}",
        )
    _require(tuple(observed_ids) == EXPECTED_SOURCE_IDS, "source id set or order drifted")
    _require(tuple(observed_urls) == EXPECTED_SOURCE_URLS, "source URL set or order drifted")


def _validate_gate_decisions(manifest: Mapping[str, Any]) -> None:
    decisions = _object(
        manifest.get("clarification_gate_decisions"), "clarification_gate_decisions"
    )
    rights = _object(decisions.get("component_rights"), "component_rights")
    _require(rights.get("status") == "blocked", "rights status drifted")
    _require(rights.get("clearance_complete") is False, "rights were not cleared")
    prompt = _object(decisions.get("prompt_and_algorithm_source"), "prompt_and_algorithm")
    _require(prompt.get("status") == "partial", "source lock must remain partial")
    _require(prompt.get("prompt_source_identity_locked") is True, "prompt source lost")
    _require(prompt.get("parser_source_identity_locked") is True, "parser source lost")
    _require(
        prompt.get("aggregation_algorithm_source_identity_locked") is True,
        "algorithm source lost",
    )
    _require(
        prompt.get("effective_execution_configuration_locked") is False,
        "effective execution was not locked",
    )
    judge = _object(decisions.get("judge_and_runtime"), "judge_and_runtime")
    _require(judge.get("status") == "blocked", "judge status drifted")
    _require(judge.get("qwen_candidate_revision") == EXPECTED_QWEN_REVISION, "Qwen SHA drifted")
    _require(judge.get("qwen_candidate_revision_identified") is True, "Qwen candidate lost")
    _require(judge.get("runner_binds_qwen_candidate_revision") is False, "Qwen bind overstated")
    _require(judge.get("tokenizer_revision_locked") is False, "tokenizer bind overstated")
    _require(
        judge.get("resolved_runtime_dependency_lock_complete") is False,
        "runtime closure overstated",
    )
    _require(judge.get("end_to_end_closure_complete") is False, "end-to-end closure overstated")


def _validate_aggregate_and_next_step(manifest: Mapping[str, Any]) -> None:
    aggregate = _object(manifest.get("aggregate_decision"), "aggregate_decision")
    _require(aggregate.get("engineering_lock_may_pass") is True, "engineering lock disabled")
    _require(aggregate.get("clarification_decision") == "no_go", "no-go drifted")
    _require(aggregate.get("candidate_id") == "browsecomp_plus", "aggregate candidate drifted")
    _require(aggregate.get("candidate_admitted") is False, "candidate admitted")
    _require(aggregate.get("stop_criterion_triggered") is True, "stop was not triggered")
    _require(
        aggregate.get("moving_context_document_closed_no_gate") is True,
        "moving context source was promoted to gate evidence",
    )
    _require(
        aggregate.get("no_go_independent_of_moving_context_document") is True,
        "no-go became dependent on moving context",
    )
    _require(
        aggregate.get("prompt_and_algorithm_source_lock") == "partial",
        "partial source lock drifted",
    )
    for key in (
        "asset_acquisition_allowed",
        "component_rights_clearance_complete",
        "end_to_end_comparability_complete",
        "evaluation_allowed",
        "judge_runtime_closure_complete",
        "officially_comparable_score_available",
        "publication_allowed",
        "real_external_score",
        "v1_readiness",
    ):
        _require(aggregate.get(key) is False, f"aggregate {key} must remain false")
    _require(aggregate.get("phase_11_9_status") == "blocked", "Phase 11.9 drifted")
    _require(aggregate.get("phase_12_status") == "blocked", "Phase 12 drifted")

    next_step = _object(
        manifest.get("single_recommended_next_step"), "single_recommended_next_step"
    )
    _require(
        next_step.get("action_kind") == "prepare-local-unsent-upstream-clarification-request",
        "next step drifted",
    )
    _require(next_step.get("decision") == "recommended", "next-step decision drifted")
    _require(next_step.get("external_contact_allowed") is False, "external contact enabled")
    _require(
        next_step.get("sending_requires_separate_explicit_go") is True,
        "send boundary drifted",
    )
    for key in ("maximum_external_requests", "maximum_publications", "maximum_retries"):
        _require(next_step.get(key) == 0, f"{key} must remain zero")


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the exact five-source decision without contacting a source."""

    expected_top_level = {
        "aggregate_decision",
        "captured_on",
        "clarification_gate_decisions",
        "facts",
        "inferences",
        "new_consulted_primary_documents",
        "phase_policy",
        "predecessor_lock",
        "purpose",
        "research_budget",
        "schema_version",
        "single_recommended_next_step",
    }
    _require(set(manifest) == expected_top_level, "manifest top-level schema drifted")
    _require(manifest.get("schema_version") == MANIFEST_SCHEMA, "manifest schema drifted")
    _require(
        manifest.get("purpose")
        == "bounded-metadata-only-browsecomp-plus-rights-and-judge-runtime-clarification",
        "purpose drifted",
    )
    _require(manifest.get("captured_on") == "2026-08-01", "capture date drifted")
    for section, expected_hash in EXPECTED_SECTION_SHA256.items():
        _require(
            canonical_sha256(manifest.get(section)) == expected_hash,
            f"{section} content drifted",
        )
    _validate_predecessor(manifest)
    _validate_phase_policy(manifest)
    _validate_budget_and_sources(manifest)
    _validate_gate_decisions(manifest)
    _validate_aggregate_and_next_step(manifest)


def build_clarification_report(
    manifest: Mapping[str, Any], *, methodology_commit_sha: str
) -> dict[str, Any]:
    """Return the deterministic aggregate-only P1 report."""

    validate_manifest(manifest)
    _lower_hex(methodology_commit_sha, 40, "methodology_commit_sha")
    gate_ids = (
        "p0_methodology_and_result_authorities_exact",
        "p0_result_reproduced_16_of_16_no_go",
        "browsecomp_plus_only_clarification_scope",
        "exact_five_new_primary_metadata_documents",
        "cumulative_fifteen_document_ceiling_exhausted",
        "source_identity_strengths_and_limits_explicit",
        "zero_benchmark_payload_access",
        "component_rights_absence_recorded_without_legal_inference",
        "component_rights_gate_fail_closed",
        "evaluation_runner_prompt_parser_and_algorithm_source_locked",
        "effective_prompt_and_algorithm_lock_classified_partial",
        "qwen_candidate_revision_identified",
        "runner_to_qwen_and_tokenizer_binding_absent",
        "resolved_runtime_dependency_closure_absent",
        "end_to_end_comparability_gate_fail_closed",
        "p0_stop_criterion_triggered",
        "zero_live_judge_score_secret_retry_or_publication_operations",
        "phase11_8_10b_acquisition_phase11_9_phase12_and_v1_blocked",
    )
    return {
        "schema_version": RESULT_SCHEMA,
        "phase": "11.8.10B-P1",
        "generated_on": "2026-08-01",
        "mode": "metadata-only-local-fail-closed",
        "methodology_commit_sha": methodology_commit_sha,
        "manifest_canonical_sha256": canonical_sha256(manifest),
        "outcome": "bounded_clarification_complete_admission_blocked",
        "engineering_lock": "pass",
        "clarification_decision": "no_go",
        "candidate_id": "browsecomp_plus",
        "candidate_admitted": False,
        "real_external_score": False,
        "officially_comparable_score_available": False,
        "gate_summary": {"passed": len(gate_ids), "failed": 0, "total": len(gate_ids)},
        "gates": [
            {"gate": index, "gate_id": gate_id, "passed": True}
            for index, gate_id in enumerate(gate_ids, start=1)
        ],
        "research_budget": {
            "predecessor_documents": 10,
            "new_documents": 5,
            "cumulative_documents": 15,
            "maximum_documents": 15,
            "remaining_documents": 0,
            "source_ceiling_exhausted": True,
        },
        "source_identity": {
            "git_blob_locked_documents": 2,
            "versioned_arxiv_records": 1,
            "immutable_revision_and_path_documents": 1,
            "moving_context_only_documents": 1,
            "external_document_content_digests_verified_locally": 0,
            "moving_context_document_closed_no_gate": True,
            "no_go_independent_of_moving_context_document": True,
        },
        "clarification_gates": {
            "component_rights": "blocked",
            "prompt_and_algorithm_source": "partial",
            "qwen_candidate_revision_identified": True,
            "runner_binds_qwen_candidate_revision": False,
            "tokenizer_revision_locked": False,
            "resolved_runtime_dependency_lock_complete": False,
            "judge_and_runtime": "blocked",
            "end_to_end_comparability": "blocked",
        },
        "stop": {
            "criterion_triggered": True,
            "reason_ids": [
                "fifteen_document_source_ceiling_exhausted",
                "component_rights_gate_remains_blocked",
                "judge_and_runtime_gate_remains_blocked",
            ],
            "additional_metadata_documents_allowed": 0,
        },
        "operation_attestation": {
            "measurement_mode": (
                "recorded-historical-assertion-plus-static-runner-capability-check"
            ),
            "historical_counts_are_process_attestations": True,
            "runtime_network_instrumentation_used": False,
            "new_public_metadata_documents_consulted": 5,
            "benchmark_payload_downloads": 0,
            "benchmark_payload_bytes_opened": 0,
            "queries_decrypted": 0,
            "provider_requests": 0,
            "model_requests": 0,
            "judge_requests": 0,
            "retrieval_requests": 0,
            "scores_computed": 0,
            "secret_requests": 0,
            "retries": 0,
            "publication_requests": 0,
        },
        "next_step": {
            "action_kind": "prepare-local-unsent-upstream-clarification-request",
            "external_contact_allowed": False,
            "sending_requires_separate_explicit_go": True,
            "maximum_external_requests": 0,
            "maximum_retries": 0,
            "maximum_publications": 0,
        },
        "readiness": {
            "component_rights_clearance_complete": False,
            "judge_runtime_closure_complete": False,
            "end_to_end_comparability_complete": False,
            "asset_acquisition_allowed": False,
            "evaluation_allowed": False,
            "publication_allowed": False,
            "v1_ready": False,
        },
        "governance": {
            "upstream_contact_authorized": False,
            "phase_11_8_10b_acquisition_authorized": False,
            "phase_11_9_authorized": False,
            "phase_12_authorized": False,
            "merge_allowed": False,
            "release_allowed": False,
            "superiority_claim_allowed": False,
            "pull_request_must_remain_draft": True,
            "distributions_must_remain_unpublished": True,
        },
    }
