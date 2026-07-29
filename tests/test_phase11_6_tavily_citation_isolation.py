from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from benchmarks.run_end_to_end_phase10 import MODELS, paired_answer_metrics
from benchmarks.run_live_retrieval import BenchmarkRow
from benchmarks.run_phase11_5_quality_recovery import ArmBundle, EvidenceBlock, gemini_endpoint
from benchmarks.run_phase11_6_tavily_citation_isolation import (
    BASELINE_ARM,
    CANDIDATE_ARM,
    GENERATION_ARMS,
    aggregate_generation,
    aggregate_retrieval,
    build_decision,
    build_parser,
    build_prompt,
    duplicate_tavily_bundle,
    generate_outcome,
    packet_identity,
    public_retrieval_outcome,
    validate_arguments,
)
from evidencemesh.config import COMMUNITY_PROVIDERS, QUALITY_PROVIDERS


def row(case_id: str = "case-1", answer: str = "42") -> BenchmarkRow:
    return BenchmarkRow(
        id=case_id,
        question="What is the answer?",
        answers=(answer,),
        topic="Other",
        answer_type="Number",
    )


def blocks() -> tuple[EvidenceBlock, ...]:
    return (
        EvidenceBlock(
            citation_id="S1",
            title="Source 1",
            url="https://one.example/source",
            text="The answer is 42.",
            providers=("tavily",),
        ),
        EvidenceBlock(
            citation_id="S2",
            title="Source 2",
            url="https://two.example/source",
            text="Independent context.",
            providers=("tavily",),
        ),
    )


def bundle(arm: str = BASELINE_ARM) -> ArmBundle:
    return ArmBundle(
        case_id="case-1",
        arm=arm,
        status="completed",
        blocks=blocks(),
        raw_result_count=2,
        fused_result_count=2,
        selected_result_count=2,
        unique_domains=2,
        selected_tavily_count=2,
        provider_stage_counts={},
        reservation_policy="none",
        reservation_requested=0,
        reservation_eligible=0,
        reservation_feasible=0,
        reservation_target=0,
        reservation_fulfilled=0,
        reservation_shortfall_reason=None,
        retrieval_latency_ms=10.0,
        error_kind=None,
    )


def generation_outcomes() -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for model in MODELS:
        for case_index in range(12):
            for arm in GENERATION_ARMS:
                answer_hit_limit = 8 if arm == BASELINE_ARM else 9
                citation_limit = 6 if arm == BASELINE_ARM else 12
                support_limit = 5 if arm == BASELINE_ARM else 9
                outcomes.append(
                    {
                        "case_id": f"case-{case_index + 1}",
                        "arm": arm,
                        "model": model,
                        "status": "completed",
                        "answer_key_covered": case_index < answer_hit_limit,
                        "citation_count": int(case_index < citation_limit),
                        "citation_ids_valid": True,
                        "citation_contract_passed": case_index < citation_limit,
                        "citation_support_proxy": case_index < support_limit,
                        "prompt_evidence_count": 2,
                        "generation_latency_ms": 10.0,
                        "usage": {},
                        "error_kind": None,
                    }
                )
    return outcomes


def retrieval_outcomes() -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for case_index in range(12):
        case = row(f"case-{case_index + 1}", answer="42" if case_index < 10 else "missing")
        for arm in GENERATION_ARMS:
            outcomes.append(
                public_retrieval_outcome(
                    case,
                    bundle(arm),
                    evidence_budget_chars=12_000,
                )
            )
    return outcomes


def decision_for(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    retrieved = retrieval_outcomes()
    generated = aggregate_generation(outcomes)
    paired = paired_answer_metrics(
        outcomes,
        candidate_arm=CANDIDATE_ARM,
        baseline_arm=BASELINE_ARM,
    )
    return build_decision(
        aggregate_retrieval(retrieved),
        generated,
        paired,
        packet_identity(retrieved),
        retrieval_operations=12,
        generation_requests=72,
        tavily_requests=12,
    )


def test_two_arms_share_byte_identical_evidence_and_only_prompts_differ() -> None:
    duplicated = duplicate_tavily_bundle(bundle())
    legacy_system, legacy_prompt, legacy_blocks = build_prompt(
        row(),
        duplicated[BASELINE_ARM],
        evidence_budget_chars=12_000,
    )
    strict_system, strict_prompt, strict_blocks = build_prompt(
        row(),
        duplicated[CANDIDATE_ARM],
        evidence_budget_chars=12_000,
    )

    assert duplicated[BASELINE_ARM].blocks == duplicated[CANDIDATE_ARM].blocks
    assert legacy_blocks == strict_blocks
    assert legacy_system != strict_system
    assert legacy_prompt != strict_prompt
    assert "Allowed citation identifiers" not in legacy_prompt
    assert "Allowed citation identifiers" in strict_prompt
    assert "[S1], [S2]" in strict_prompt


def test_packet_identity_requires_all_12_selected_and_projected_pairs() -> None:
    outcomes = retrieval_outcomes()
    assert packet_identity(outcomes) == {
        "matching_cases": 12,
        "denominator": 12,
        "passed": True,
    }

    outcomes[-1]["prompt_packet_sha256"] = "different"
    assert packet_identity(outcomes)["passed"] is False


@pytest.mark.asyncio
@respx.mock
async def test_strict_generation_audits_citations_without_private_text() -> None:
    respx.post(gemini_endpoint("gemini-3.5-flash-lite")).mock(
        return_value=httpx.Response(
            200,
            json={
                "modelVersion": "gemini-3.5-flash-lite",
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "42 [S1]"}]},
                    }
                ],
            },
        )
    )
    async with httpx.AsyncClient() as client:
        outcome = await generate_outcome(
            row(),
            bundle(CANDIDATE_ARM),
            client=client,
            api_key="test-secret",
            model="gemini-3.5-flash-lite",
            evidence_budget_chars=12_000,
            max_output_tokens=2_048,
            wall_time_seconds=60.0,
        )

    assert outcome["status"] == "completed"
    assert outcome["answer_key_covered"] is True
    assert outcome["citation_count"] == 1
    assert outcome["citation_ids_valid"] is True
    assert outcome["citation_contract_passed"] is True
    assert outcome["citation_support_proxy"] is True
    assert "answer" not in outcome
    assert "question" not in outcome
    assert "evidence" not in outcome
    assert "user_prompt" not in outcome


def test_all_pre_registered_gates_can_pass() -> None:
    decision = decision_for(generation_outcomes())

    assert decision["phase11_6_candidate_passed"] is True
    assert decision["quality_profile_promotion_allowed"] is True
    assert decision["quality_profile_promoted"] is False
    assert decision["phase12_untouched_evaluation_allowed"] is True
    assert decision["phase12_executed"] is False
    assert all(gate["passed"] for gate in decision["gates"].values())


def test_gemma_4_26b_completion_floor_is_blocking() -> None:
    outcomes = generation_outcomes()
    failures = [
        outcome
        for outcome in outcomes
        if outcome["model"] == "gemma-4-26b-a4b-it" and outcome["arm"] == CANDIDATE_ARM
    ][-2:]
    for outcome in failures:
        outcome["status"] = "failed"
        outcome["answer_key_covered"] = False
        outcome["citation_count"] = 0
        outcome["citation_ids_valid"] = False
        outcome["citation_contract_passed"] = False
        outcome["citation_support_proxy"] = False
        outcome["error_kind"] = "request_timeout"

    decision = decision_for(outcomes)

    completion_gate = decision["gates"]["completion_at_least_11_of_12_per_model_arm"]
    assert completion_gate["observed"]["gemma-4-26b-a4b-it:tavily_strict"] == 10
    assert completion_gate["gemma_4_26b_blocking"] is True
    assert completion_gate["passed"] is False
    assert decision["phase11_6_candidate_passed"] is False


def test_gemini_flash_lite_per_model_regression_is_blocking() -> None:
    outcomes = generation_outcomes()
    flash_strict = [
        outcome
        for outcome in outcomes
        if outcome["model"] == "gemini-3.5-flash-lite" and outcome["arm"] == CANDIDATE_ARM
    ]
    for outcome in flash_strict[7:]:
        outcome["answer_key_covered"] = False

    decision = decision_for(outcomes)

    per_model = decision["gates"]["strict_answer_no_regression_for_any_model"]
    assert per_model["observed"]["gemini-3.5-flash-lite"] == {
        "baseline_hits": 8,
        "candidate_hits": 7,
        "paired_net_gain": -1,
    }
    assert per_model["passed"] is False
    assert decision["gemini_3_5_flash_lite_tested"] is True
    assert decision["phase11_6_candidate_passed"] is False


def test_locked_arguments_accept_exact_defaults_and_reject_any_model_or_timeout_change(
    tmp_path: Path,
) -> None:
    parser = build_parser()
    arguments = parser.parse_args(
        [
            "--dataset",
            str(tmp_path / "dataset.csv"),
            "--output",
            str(tmp_path / "result.json"),
        ]
    )
    validate_arguments(arguments)

    changed_model = argparse.Namespace(**vars(arguments))
    changed_model.models = ["gemini-3.5-flash-lite"]
    with pytest.raises(ValueError, match="exact locked model order"):
        validate_arguments(changed_model)

    changed_timeout = argparse.Namespace(**vars(arguments))
    changed_timeout.generation_wall_time_seconds = 61.0
    with pytest.raises(ValueError, match="locked arguments changed"):
        validate_arguments(changed_timeout)


def test_committed_phase11_6_result_is_the_audited_blocking_no_go() -> None:
    root = Path(__file__).parents[1]
    result_path = (
        root / "benchmarks" / "results" / "phase11_6_tavily_citation_isolation_2026-07-29.json"
    )
    report_path = (
        root / "benchmarks" / "results" / "phase11_6_tavily_citation_isolation_2026-07-29.md"
    )
    result_bytes = result_path.read_bytes()
    result = json.loads(result_bytes)
    report = report_path.read_text(encoding="utf-8")

    assert hashlib.sha256(result_bytes).hexdigest() == (
        "86b9eda8ecb55822bb93501dbd1d1614c84c04444d1df62fbf6252e1202d22bd"
    )
    assert result["environment"]["commit_sha"] == ("5140b1d458e1846f6aa971e6707be7832c90b341")
    assert result["traffic"] == {
        "case_retrieval_operations": 12,
        "expected_generation_requests": 72,
        "expected_retrieval_operations": 12,
        "expected_tavily_requests": 12,
        "generation_requests": 72,
        "provider_query_calls": 12,
        "repair_requests": 0,
        "retries": 0,
        "tavily_requests": 12,
    }
    assert result["packet_identity"] == {
        "denominator": 12,
        "matching_cases": 12,
        "passed": True,
    }
    assert result["privacy"] == {
        "answer_hashes_in_report": True,
        "api_keys_in_report": False,
        "generated_answers_in_report": False,
        "questions_in_report": False,
        "reference_answers_in_report": False,
        "source_snippets_or_evidence_in_report": False,
        "source_titles_or_urls_in_report": False,
        "system_or_user_prompts_in_report": False,
    }

    gates = result["decision"]["gates"]
    assert len(gates) == 10
    assert sum(bool(gate["passed"]) for gate in gates.values()) == 9
    completion = gates["completion_at_least_11_of_12_per_model_arm"]
    assert completion["passed"] is False
    assert completion["gemma_4_26b_blocking"] is True
    assert completion["observed"]["gemma-4-26b-a4b-it:tavily_legacy"] == 10
    assert completion["observed"]["gemma-4-26b-a4b-it:tavily_strict"] == 10
    assert gates["strict_answer_no_overall_regression"]["candidate_hits"] == 25
    assert gates["strict_answer_no_overall_regression"]["baseline_hits"] == 25
    assert gates["strict_answer_no_overall_regression"]["passed"] is True
    assert gates["strict_answer_no_regression_for_any_model"]["passed"] is True
    assert gates["strict_citation_presence_at_least_90_percent"]["observed"]["numerator"] == 34
    assert gates["strict_citation_ids_100_percent_valid"]["observed"]["numerator"] == 34
    assert gates["strict_citation_support_at_least_70_percent"]["observed"]["numerator"] == 28

    decision = result["decision"]
    assert decision["phase11_6_candidate_passed"] is False
    assert decision["quality_profile_promotion_allowed"] is False
    assert decision["quality_profile_promoted"] is False
    assert decision["phase12_untouched_evaluation_allowed"] is False
    assert decision["phase12_executed"] is False
    assert decision["community_profile_unchanged"] is True
    assert decision["merge_allowed"] is False
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"
    assert decision["superiority_claim_allowed"] is False

    assert (*COMMUNITY_PROVIDERS, "tavily") == QUALITY_PROVIDERS
    assert "30487190189" in report
    assert "candidate failed; quality was not promoted" in report
    assert "25/36 vs 25/36" in report
