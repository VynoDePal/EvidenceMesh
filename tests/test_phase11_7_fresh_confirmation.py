from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from benchmarks.phase11_7_dataset import (
    PHASE11_7_CASE_COUNT,
    PHASE11_7_SUITE,
    PHASE12_RESERVE_CASE_COUNT,
    PHASE12_RESERVE_SUITE,
    build_split_manifests,
    parse_selected_simpleqa,
)
from benchmarks.run_end_to_end_phase10 import paired_answer_metrics
from benchmarks.run_live_retrieval import BenchmarkRow, stable_row_id
from benchmarks.run_phase11_5_quality_recovery import ArmBundle, EvidenceBlock, gemini_endpoint
from benchmarks.run_phase11_7_fresh_confirmation import (
    BASELINE_ARM,
    CANDIDATE_ARM,
    GENERATION_ARMS,
    LOCKED_MANIFEST_SHA256,
    LOCKED_RESERVE_MANIFEST_SHA256,
    MODELS,
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
from evidencemesh.config import COMMUNITY_PROVIDERS, QUALITY_PROVIDERS, Settings


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
        for case_index in range(PHASE11_7_CASE_COUNT):
            for arm in GENERATION_ARMS:
                answer_hit_limit = 16 if arm == BASELINE_ARM else 18
                citation_limit = 12 if arm == BASELINE_ARM else 24
                support_limit = 10 if arm == BASELINE_ARM else 19
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
    for case_index in range(PHASE11_7_CASE_COUNT):
        case = row(
            f"case-{case_index + 1}",
            answer="42" if case_index < 20 else "missing",
        )
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
        retrieval_operations=24,
        generation_requests=96,
        tavily_requests=24,
    )


def test_fresh_and_reserved_manifests_are_locked_disjoint_and_private() -> None:
    root = Path(__file__).parents[1]
    fresh_path = root / "benchmarks/data/phase11_7_fresh_confirmation_v1.json"
    reserve_path = root / "benchmarks/data/phase12_untouched_reserve_v1.json"
    fresh_bytes = fresh_path.read_bytes()
    reserve_bytes = reserve_path.read_bytes()
    fresh = json.loads(fresh_bytes)
    reserve = json.loads(reserve_bytes)

    assert hashlib.sha256(fresh_bytes).hexdigest() == LOCKED_MANIFEST_SHA256
    assert hashlib.sha256(reserve_bytes).hexdigest() == LOCKED_RESERVE_MANIFEST_SHA256
    assert fresh["suite"] == PHASE11_7_SUITE
    assert reserve["suite"] == PHASE12_RESERVE_SUITE
    assert len(fresh["cases"]) == PHASE11_7_CASE_COUNT
    assert len(reserve["sealed_cases"]) == PHASE12_RESERVE_CASE_COUNT
    assert {entry["case_id"] for entry in fresh["cases"]}.isdisjoint(
        entry["case_id"] for entry in reserve["sealed_cases"]
    )
    assert {entry["row_index"] for entry in fresh["cases"]}.isdisjoint(
        entry["row_index"] for entry in reserve["sealed_cases"]
    )
    assert fresh["privacy"]["questions_committed"] is False
    assert fresh["privacy"]["reference_answers_committed"] is False
    assert reserve["seal"]["questions_committed"] is False
    assert reserve["seal"]["reference_answers_committed"] is False
    assert reserve["seal"]["topic_distribution_committed"] is False
    assert reserve["seal"]["phase11_7_loader_may_materialize_reserved_rows"] is False


def test_split_builder_is_deterministic_and_excludes_prior_ids() -> None:
    rows = [
        BenchmarkRow(
            id=stable_row_id(f"Question {index}?"),
            question=f"Question {index}?",
            answers=(str(index),),
            topic="Other",
            answer_type="Number",
        )
        for index in range(140)
    ]
    prior_ids = {rows[0].id, rows[1].id}
    first = build_split_manifests(rows, prior_case_ids=prior_ids, prior_sources=[])
    second = build_split_manifests(rows, prior_case_ids=prior_ids, prior_sources=[])

    assert first == second
    fresh, reserve = first
    fresh_ids = {entry["case_id"] for entry in fresh["cases"]}
    reserve_ids = {entry["case_id"] for entry in reserve["sealed_cases"]}
    assert not (fresh_ids | reserve_ids) & prior_ids
    assert fresh_ids.isdisjoint(reserve_ids)
    assert len(fresh_ids) == 24
    assert len(reserve_ids) == 96
    assert all(set(entry) == {"row_index", "case_id"} for entry in fresh["cases"])
    assert all(set(entry) == {"row_index", "case_id"} for entry in reserve["sealed_cases"])


def test_selected_parser_does_not_materialize_unselected_rows() -> None:
    selected_question = "Selected question?"
    payload = (
        f'metadata,problem,answer\n"{{}}","{selected_question}","42"\n"not valid metadata","",""\n'
    ).encode()
    selected_id = stable_row_id(selected_question)

    rows, row_count = parse_selected_simpleqa(payload, [(0, selected_id)])

    assert row_count == 2
    assert [item.id for item in rows] == [selected_id]
    assert rows[0].answers == ("42",)


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


def test_packet_identity_requires_all_24_selected_and_projected_pairs() -> None:
    outcomes = retrieval_outcomes()
    assert packet_identity(outcomes) == {
        "matching_cases": 24,
        "denominator": 24,
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

    assert decision["phase11_7_candidate_passed"] is True
    assert decision["quality_profile_promotion_allowed"] is True
    assert decision["quality_profile_promoted"] is False
    assert decision["phase12_untouched_evaluation_allowed"] is True
    assert decision["phase12_executed"] is False
    assert decision["gemma_4_26b_blocking"] is False
    assert decision["gemma_4_26b_tested"] is False
    assert decision["blocking_models"] == list(MODELS)
    assert all(gate["passed"] for gate in decision["gates"].values())


def test_completion_floor_is_blocking_for_each_locked_model() -> None:
    for model in MODELS:
        outcomes = generation_outcomes()
        failures = [
            outcome
            for outcome in outcomes
            if outcome["model"] == model and outcome["arm"] == CANDIDATE_ARM
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
        completion_gate = decision["gates"]["completion_at_least_23_of_24_per_model_arm"]
        assert completion_gate["observed"][f"{model}:tavily_strict"] == 22
        assert completion_gate["passed"] is False
        assert decision["phase11_7_candidate_passed"] is False


def test_flash_lite_per_model_regression_is_blocking() -> None:
    outcomes = generation_outcomes()
    flash_strict = [
        outcome
        for outcome in outcomes
        if outcome["model"] == "gemini-3.5-flash-lite" and outcome["arm"] == CANDIDATE_ARM
    ]
    for outcome in flash_strict[15:]:
        outcome["answer_key_covered"] = False

    decision = decision_for(outcomes)

    per_model = decision["gates"]["strict_answer_no_regression_for_any_model"]
    assert per_model["observed"]["gemini-3.5-flash-lite"] == {
        "baseline_hits": 16,
        "candidate_hits": 15,
        "paired_net_gain": -1,
    }
    assert per_model["passed"] is False
    assert decision["gemini_3_5_flash_lite_tested"] is True
    assert decision["phase11_7_candidate_passed"] is False


def test_locked_arguments_accept_exact_defaults_and_reject_changes(tmp_path: Path) -> None:
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


def test_result_boundary_is_absent_before_the_single_live_run() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks/results/phase11_7_fresh_confirmation_2026-07-29.json"
    report_path = root / "benchmarks/results/phase11_7_fresh_confirmation_2026-07-29.md"

    if not result_path.exists():
        assert not report_path.exists()
        assert (*COMMUNITY_PROVIDERS, "tavily") == QUALITY_PROVIDERS
        return

    result = json.loads(result_path.read_bytes())
    assert report_path.exists()
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == (
        "783fdaa60b351f975632b9cf23b57bab8766e39a8d81fabdead590962deea6de"
    )
    assert result["benchmark"] == PHASE11_7_SUITE
    assert result["traffic"]["case_retrieval_operations"] == 24
    assert result["traffic"]["tavily_requests"] == 24
    assert result["traffic"]["generation_requests"] == 96
    assert result["traffic"]["retries"] == 0
    assert result["traffic"]["repair_requests"] == 0
    assert result["phase12_reserve"]["case_count"] == 96
    assert result["phase12_reserve"]["questions_or_answers_materialized"] is False
    assert result["phase12_reserve"]["used_by_phase11_7"] is False
    assert sum(bool(gate["passed"]) for gate in result["decision"]["gates"].values()) == 7
    assert {name for name, gate in result["decision"]["gates"].items() if not gate["passed"]} == {
        "tavily_packet_available_and_answer_bearing",
        "strict_citation_presence_at_least_95_percent",
        "strict_citation_support_at_least_75_percent",
    }
    assert result["decision"]["phase11_7_candidate_passed"] is False
    assert result["decision"]["quality_profile_promotion_allowed"] is False
    assert result["decision"]["quality_profile_promoted"] is False
    assert result["decision"]["phase12_untouched_evaluation_allowed"] is False
    assert result["decision"]["phase12_executed"] is False
    assert result["decision"]["merge_allowed"] is False
    assert result["decision"]["release_decision"] == "no-go"
    assert (*COMMUNITY_PROVIDERS, "tavily") == QUALITY_PROVIDERS
    assert Settings().quality_primary_provider_share == 0.8
