#!/usr/bin/env python3
"""Recompute a privacy-safe causal diagnostic from the locked Phase 11.8 result.

This module is deliberately standard-library-only and performs no network I/O.
It does not change the historical Phase 11.8 gates or authorize another live run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BENCHMARK_NAME = "evidencemesh-phase11-8-1-offline-causal-diagnostic-v1"
SOURCE_BENCHMARK_NAME = "evidencemesh-phase11-8-corrective-recovery-v1"
SOURCE_RESULT_SHA256 = "0bd05884c6e6d019f22d18113ef449d1cf1c8158ac0e598d899ee1a93c4b687a"
SOURCE_RESULT_PATH = "benchmarks/results/phase11_8_recovery_2026-07-29.json"
CURRENT_ARM = "current_strict"
EXPANDED_ARM = "expanded_strict"
STRUCTURED_ARM = "expanded_structured"
MODELS = ("gemma-4-31b-it", "gemini-3.5-flash-lite")
EXPECTED_TRAFFIC = {
    "case_retrieval_operations": 24,
    "generation_requests": 144,
    "tavily_requests": 24,
    "retries": 0,
    "fallback_requests": 0,
    "repair_requests": 0,
}


class DiagnosticInputError(ValueError):
    """Raised when the locked source result does not satisfy diagnostic invariants."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DiagnosticInputError(message)


def _paired(
    outcomes: list[dict[str, Any]],
    *,
    field: str,
    candidate_arm: str,
    baseline_arm: str,
    completed_only: bool,
) -> dict[str, int | str | bool]:
    records = {(str(row["model"]), str(row["case_id"]), str(row["arm"])): row for row in outcomes}
    case_ids = sorted({str(row["case_id"]) for row in outcomes})
    candidate_wins = 0
    baseline_wins = 0
    shared_hits = 0
    shared_misses = 0
    excluded = 0
    for model in MODELS:
        for case_id in case_ids:
            candidate = records[(model, case_id, candidate_arm)]
            baseline = records[(model, case_id, baseline_arm)]
            if completed_only and (
                candidate["status"] != "completed" or baseline["status"] != "completed"
            ):
                excluded += 1
                continue
            candidate_hit = bool(candidate[field])
            baseline_hit = bool(baseline[field])
            if candidate_hit and not baseline_hit:
                candidate_wins += 1
            elif baseline_hit and not candidate_hit:
                baseline_wins += 1
            elif candidate_hit:
                shared_hits += 1
            else:
                shared_misses += 1
    eligible = candidate_wins + baseline_wins + shared_hits + shared_misses
    return {
        "field": field,
        "candidate_arm": candidate_arm,
        "baseline_arm": baseline_arm,
        "completed_pairs_only": completed_only,
        "eligible_pairs": eligible,
        "excluded_pairs": excluded,
        "candidate_wins": candidate_wins,
        "baseline_wins": baseline_wins,
        "shared_hits": shared_hits,
        "shared_misses": shared_misses,
        "net_gain": candidate_wins - baseline_wins,
    }


def _availability(generation: list[dict[str, Any]]) -> dict[str, Any]:
    by_model_arm: dict[str, dict[str, Any]] = {}
    all_errors: Counter[str] = Counter()
    http_503_by_model: Counter[str] = Counter()
    for model in MODELS:
        for arm in (CURRENT_ARM, EXPANDED_ARM, STRUCTURED_ARM):
            rows = [row for row in generation if row["model"] == model and row["arm"] == arm]
            errors = Counter(
                str(row["error_kind"]) for row in rows if row["error_kind"] is not None
            )
            all_errors.update(errors)
            http_503_by_model[model] += errors["http_503"]
            completed = sum(row["status"] == "completed" for row in rows)
            native = sum(bool(row["native_request_completed"]) for row in rows)
            by_model_arm[f"{model}:{arm}"] = {
                "attempts": len(rows),
                "completed": completed,
                "native_request_completed": native,
                "completion_floor": 23,
                "completion_floor_deficit": max(0, 23 - completed),
                "errors": dict(sorted(errors.items())),
            }

    structured = [row for row in generation if row["arm"] == STRUCTURED_ARM]
    native_structured = sum(bool(row["native_request_completed"]) for row in structured)
    schema_valid = sum(bool(row["structured_schema_valid"]) for row in structured)
    schema_rejections = sum(row["error_kind"] == "response_schema_failure" for row in structured)
    unavailable_before_schema = len(structured) - native_structured
    _require(
        len(structured) - schema_valid == unavailable_before_schema + schema_rejections,
        "structured schema failure accounting does not reconcile",
    )

    return {
        "by_model_arm": by_model_arm,
        "errors_all_arms": dict(sorted(all_errors.items())),
        "http_503_by_model": dict(sorted(http_503_by_model.items())),
        "all_http_503_attributed_to_gemma_4_31b": (
            http_503_by_model["gemma-4-31b-it"] == all_errors["http_503"]
            and http_503_by_model["gemini-3.5-flash-lite"] == 0
        ),
        "completion_floor_deficit_total": sum(
            int(cell["completion_floor_deficit"]) for cell in by_model_arm.values()
        ),
        "structured_schema_accounting": {
            "attempts": len(structured),
            "native_request_completed": native_structured,
            "schema_valid": schema_valid,
            "unavailable_before_schema_validation": unavailable_before_schema,
            "native_schema_rejections": schema_rejections,
            "schema_valid_given_native": {
                "numerator": schema_valid,
                "denominator": native_structured,
                "rate": round(schema_valid / native_structured, 6),
            },
        },
    }


def _projection(retrieval: list[dict[str, Any]]) -> dict[str, Any]:
    records = {(str(row["case_id"]), str(row["arm"])): row for row in retrieval}
    case_ids = sorted({str(row["case_id"]) for row in retrieval})
    selected_hits = 0
    prompt_hits = 0
    selected_to_prompt_losses = 0
    selected_to_prompt_gains = 0
    current_prompt_hits = 0
    expanded_wins = 0
    current_wins = 0
    shared_hits = 0
    shared_misses = 0
    for case_id in case_ids:
        current = records[(case_id, CURRENT_ARM)]
        expanded = records[(case_id, EXPANDED_ARM)]
        selected_hit = bool(expanded["answer_key_in_selected_evidence"])
        prompt_hit = bool(expanded["answer_key_in_prompt_evidence"])
        current_hit = bool(current["answer_key_in_prompt_evidence"])
        selected_hits += selected_hit
        prompt_hits += prompt_hit
        selected_to_prompt_losses += selected_hit and not prompt_hit
        selected_to_prompt_gains += prompt_hit and not selected_hit
        current_prompt_hits += current_hit
        if prompt_hit and not current_hit:
            expanded_wins += 1
        elif current_hit and not prompt_hit:
            current_wins += 1
        elif prompt_hit:
            shared_hits += 1
        else:
            shared_misses += 1
    return {
        "cases": len(case_ids),
        "expanded_selected_answer_proxy_hits": selected_hits,
        "expanded_prompt_answer_proxy_hits": prompt_hits,
        "selected_to_prompt_losses": selected_to_prompt_losses,
        "selected_to_prompt_gains": selected_to_prompt_gains,
        "current_prompt_answer_proxy_hits": current_prompt_hits,
        "expanded_vs_current_prompt_pairs": {
            "expanded_wins": expanded_wins,
            "current_wins": current_wins,
            "shared_hits": shared_hits,
            "shared_misses": shared_misses,
            "net_gain": expanded_wins - current_wins,
        },
        "stage_attribution": (
            "The answer proxy was present after expanded selection and absent after "
            "projection in three cases. Projection is therefore directly implicated; "
            "the privacy-safe result cannot reveal which truncation boundary removed it."
        ),
    }


def _gate_classification(gates: dict[str, Any]) -> dict[str, Any]:
    layers = {
        "protocol_integrity": ("experimental_integrity", False),
        "shared_raw_pool_and_expanded_packet_identity": (
            "experimental_integrity",
            False,
        ),
        "expanded_retrieval_available_and_answer_bearing": (
            "evidence_projection_quality",
            False,
        ),
        "expanded_prompt_answer_coverage_no_regression": (
            "evidence_projection_quality",
            False,
        ),
        "completion_at_least_23_of_24_per_model_arm": (
            "provider_model_availability",
            False,
        ),
        "structured_schema_valid_at_least_23_of_24_per_model": (
            "mixed_availability_and_schema_contract",
            True,
        ),
        "structured_answer_no_overall_regression": (
            "end_to_end_answer_quality",
            True,
        ),
        "structured_answer_no_regression_for_any_model": (
            "end_to_end_answer_quality",
            True,
        ),
        "structured_citation_presence_at_least_95_percent_and_no_regression": (
            "citation_contract_quality",
            False,
        ),
        "structured_citation_ids_100_percent_valid": (
            "citation_contract_quality",
            False,
        ),
        "structured_citation_support_at_least_75_percent": (
            "citation_semantic_proxy",
            False,
        ),
        "structured_citation_support_no_regression": (
            "citation_semantic_proxy",
            False,
        ),
    }
    _require(set(gates) == set(layers), "historical gate inventory changed")
    classified = {
        name: {
            "historical_passed": bool(gates[name]["passed"]),
            "primary_layer": layers[name][0],
            "availability_confounded": layers[name][1],
        }
        for name in sorted(gates)
    }
    return {
        "historical_gate_count": len(gates),
        "historical_passed": sum(bool(gate["passed"]) for gate in gates.values()),
        "historical_failed": sum(not bool(gate["passed"]) for gate in gates.values()),
        "historical_gates_unchanged": True,
        "by_gate": classified,
    }


def build_report(source: dict[str, Any], *, source_sha256: str) -> dict[str, Any]:
    """Build a deterministic diagnostic from the committed privacy-safe result."""

    _require(source_sha256 == SOURCE_RESULT_SHA256, "unexpected Phase 11.8 source SHA-256")
    _require(source.get("benchmark") == SOURCE_BENCHMARK_NAME, "unexpected source benchmark")
    _require(source.get("decision", {}).get("release_decision") == "no-go", "source is not no-go")
    _require(
        source.get("decision", {}).get("phase11_8_candidate_passed") is False,
        "source candidate decision changed",
    )
    for field, expected in EXPECTED_TRAFFIC.items():
        _require(source.get("traffic", {}).get(field) == expected, f"unexpected traffic: {field}")
    _require(len(source.get("retrieval_outcomes", [])) == 72, "expected 72 retrieval outcomes")
    _require(len(source.get("generation_outcomes", [])) == 144, "expected 144 generations")
    _require(source.get("packet_identity", {}).get("passed") is True, "packet identity failed")

    retrieval = list(source["retrieval_outcomes"])
    generation = list(source["generation_outcomes"])
    projection = _projection(retrieval)
    availability = _availability(generation)
    gate_classification = _gate_classification(source["decision"]["gates"])
    answer_structured_vs_current = _paired(
        generation,
        field="answer_key_covered",
        candidate_arm=STRUCTURED_ARM,
        baseline_arm=CURRENT_ARM,
        completed_only=False,
    )
    answer_structured_vs_current_completed = _paired(
        generation,
        field="answer_key_covered",
        candidate_arm=STRUCTURED_ARM,
        baseline_arm=CURRENT_ARM,
        completed_only=True,
    )
    answer_structured_vs_expanded = _paired(
        generation,
        field="answer_key_covered",
        candidate_arm=STRUCTURED_ARM,
        baseline_arm=EXPANDED_ARM,
        completed_only=False,
    )
    answer_structured_vs_expanded_completed = _paired(
        generation,
        field="answer_key_covered",
        candidate_arm=STRUCTURED_ARM,
        baseline_arm=EXPANDED_ARM,
        completed_only=True,
    )
    support_structured_vs_expanded = _paired(
        generation,
        field="citation_support_proxy",
        candidate_arm=STRUCTURED_ARM,
        baseline_arm=EXPANDED_ARM,
        completed_only=False,
    )
    support_structured_vs_expanded_completed = _paired(
        generation,
        field="citation_support_proxy",
        candidate_arm=STRUCTURED_ARM,
        baseline_arm=EXPANDED_ARM,
        completed_only=True,
    )
    structured_metrics = source["generation_metrics"]["aggregate"][STRUCTURED_ARM]

    return {
        "benchmark": BENCHMARK_NAME,
        "schema_version": 1,
        "task_type": "offline_causal_diagnostic",
        "source": {
            "path": SOURCE_RESULT_PATH,
            "sha256": source_sha256,
            "benchmark": source["benchmark"],
            "historical_result": "fail",
            "historical_release_decision": "no-go",
        },
        "execution_boundary": {
            "network_access": False,
            "provider_or_model_calls": False,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "phase12_accessed": False,
            "product_configuration_changed": False,
        },
        "historical_gate_classification": gate_classification,
        "projection_diagnostic": projection,
        "provider_model_availability": availability,
        "structured_contract_diagnostic": {
            "expanded_packet_identity_cases": source["packet_identity"][
                "expanded_selected_and_prompt_matching_cases"
            ],
            "expanded_packet_identity_denominator": source["packet_identity"]["denominator"],
            "answer_vs_current_all_attempts": answer_structured_vs_current,
            "answer_vs_current_completed_pairs": answer_structured_vs_current_completed,
            "answer_vs_expanded_all_attempts": answer_structured_vs_expanded,
            "answer_vs_expanded_completed_pairs": answer_structured_vs_expanded_completed,
            "citation_support_vs_expanded_all_attempts": support_structured_vs_expanded,
            "citation_support_vs_expanded_completed_pairs": (
                support_structured_vs_expanded_completed
            ),
            "structured_citation_presence": structured_metrics["citation_presence"],
            "structured_citation_id_validity": structured_metrics["citation_ids_valid"],
            "structured_citation_support": structured_metrics["citation_support_proxy"],
            "interpretation": (
                "With byte-identical expanded evidence, the structured arm improved "
                "citation discipline and support on comparable completions but reduced "
                "the answer-key proxy. Hosted-model non-determinism prevents a stronger "
                "content-level causal claim from this single run."
            ),
        },
        "causal_findings": [
            {
                "id": "projection-stage-loss",
                "strength": "confirmed_stage_attribution",
                "finding": (
                    "Three expanded cases lost the answer proxy between selected evidence "
                    "and projected prompt evidence."
                ),
            },
            {
                "id": "provider-model-availability",
                "strength": "confirmed_accounting",
                "finding": (
                    "All 22 HTTP 503 failures came from gemma-4-31b-it; eight additional "
                    "wall timeouts affected the run."
                ),
            },
            {
                "id": "schema-gate-decomposition",
                "strength": "confirmed_accounting",
                "finding": (
                    "Of 12 structured attempts counted as not schema-valid, ten never "
                    "reached native schema validation and two were native schema rejects."
                ),
            },
            {
                "id": "structured-contract-tradeoff",
                "strength": "controlled_association",
                "finding": (
                    "The structured contract improved citation metrics but regressed the "
                    "answer-key proxy against the identical-evidence expanded strict arm."
                ),
            },
            {
                "id": "content-root-cause-limit",
                "strength": "not_observable",
                "finding": (
                    "Questions, evidence, prompts and answers are absent by design, so the "
                    "exact content-level truncation and answer failures cannot be replayed."
                ),
            },
        ],
        "ranked_corrective_hypotheses": [
            {
                "rank": 1,
                "target": "evidence_projection",
                "hypothesis": (
                    "Equal per-block truncation diluted or cut answer-bearing spans in "
                    "three cases despite successful expanded selection."
                ),
                "status": "mechanism_plausible_stage_loss_confirmed_content_unavailable",
                "next_test": (
                    "Use synthetic boundary fixtures now; require a separately authorized "
                    "privacy-preserving content replay before any product change."
                ),
            },
            {
                "rank": 2,
                "target": "provider_model_availability",
                "hypothesis": (
                    "Gemma 4 31B endpoint availability, not retrieval quality, dominated "
                    "the completion deficit."
                ),
                "status": "confirmed_for_observed_http_503_failures",
                "next_test": (
                    "Pre-register availability gates separately per user-selected model; "
                    "do not change EvidenceMesh model defaults because none are imposed."
                ),
            },
            {
                "rank": 3,
                "target": "structured_answer_contract",
                "hypothesis": (
                    "The one-claim structured instruction over-optimized citation form at "
                    "the expense of preserving answer-key wording."
                ),
                "status": "controlled_association_not_content_verified",
                "next_test": (
                    "Compare pre-registered structured contracts on shared evidence with "
                    "paired semantic and answer-key scoring."
                ),
            },
        ],
        "future_protocol_taxonomy_proposal": {
            "status": "proposal_only_not_applied_to_phase11_8",
            "layers": [
                {
                    "name": "experimental_integrity",
                    "measures": ["traffic", "packet identity", "privacy"],
                },
                {
                    "name": "provider_model_availability",
                    "measures": ["native response completion by model and arm"],
                },
                {
                    "name": "response_contract_validity",
                    "measures": ["schema validity conditional on native completion"],
                },
                {
                    "name": "completion_conditioned_product_quality",
                    "measures": ["paired answer and citation quality when both arms complete"],
                },
                {
                    "name": "end_to_end_user_quality",
                    "measures": ["all-attempt answer and citation outcomes"],
                },
            ],
            "rule": (
                "Future protocols should pre-register both conditioned and end-to-end "
                "views. A provider outage must remain blocking when required, but it must "
                "not be mislabeled as a retrieval, schema-format or answer-quality defect."
            ),
        },
        "decision": {
            "diagnostic_only": True,
            "historical_phase11_8_result_changed": False,
            "phase11_8_candidate_passed": False,
            "phase11_9_authorized": False,
            "phase12_executed": False,
            "phase12_authorized": False,
            "quality_profile_promotion_allowed": False,
            "merge_allowed": False,
            "release_allowed": False,
            "superiority_claim_allowed": False,
            "release_decision": "no-go",
        },
        "privacy": {
            "questions_in_output": False,
            "reference_answers_in_output": False,
            "source_content_in_output": False,
            "prompts_in_output": False,
            "generated_answers_in_output": False,
            "credentials_in_output": False,
            "phase12_identifiers_in_output": False,
        },
    }


def _read_input(path: str) -> tuple[bytes, str]:
    if path == "-":
        raw = sys.stdin.buffer.read()
        return raw, "stdin"
    source_path = Path(path)
    return source_path.read_bytes(), str(source_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=SOURCE_RESULT_PATH)
    parser.add_argument("--output")
    args = parser.parse_args()
    raw, input_label = _read_input(args.input)
    try:
        source = json.loads(raw)
        report = build_report(source, source_sha256=sha256_bytes(raw))
    except (DiagnosticInputError, json.JSONDecodeError) as exc:
        parser.error(f"{input_label}: {exc}")
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
