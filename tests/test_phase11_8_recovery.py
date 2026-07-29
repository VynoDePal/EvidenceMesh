from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from benchmarks.run_live_retrieval import BenchmarkRow
from benchmarks.run_phase11_5_quality_recovery import ArmBundle, EvidenceBlock, gemini_endpoint
from benchmarks.run_phase11_8_recovery import (
    BASELINE_ARM,
    BENCHMARK_NAME,
    CANDIDATE_ARM,
    CURRENT_ARM,
    EXPANDED_ARM,
    EXPECTED_CASE_COUNT,
    GENERATION_ARMS,
    LOCKED_MANIFEST_SHA256,
    LOCKED_PHASE11_7_RESULT_SHA256,
    LOCKED_PROTOCOL_SHA256,
    LOCKED_RESERVE_MANIFEST_SHA256,
    MODELS,
    STRUCTURED_INSUFFICIENT_TEXT,
    StructuredResponseError,
    aggregate_generation,
    aggregate_retrieval,
    build_decision,
    build_parser,
    build_prompt,
    generate_outcome,
    packet_identity,
    paired_generation_metrics,
    paired_retrieval_metrics,
    parse_structured_answer,
    project_blocks,
    public_retrieval_outcome,
    raw_pool_sha256,
    validate_arguments,
)
from evidencemesh.config import COMMUNITY_PROVIDERS, QUALITY_PROVIDERS, Settings
from evidencemesh.models import ProviderResult


def row(case_id: str = "case-1", answer: str = "42") -> BenchmarkRow:
    return BenchmarkRow(
        id=case_id,
        question="What is the answer?",
        answers=(answer,),
        topic="Other",
        answer_type="Number",
    )


def blocks(count: int = 20, *, answer_index: int = 14) -> tuple[EvidenceBlock, ...]:
    return tuple(
        EvidenceBlock(
            citation_id=f"S{index + 1}",
            title=f"Source {index + 1}",
            url=f"https://source-{index + 1}.example/item",
            text=(
                ("The answer is 42. " if index == answer_index else "")
                + f"Evidence block {index + 1}. "
                + ("Context " * 160)
            ),
            providers=("tavily",),
        )
        for index in range(count)
    )


def bundle(arm: str, *, block_count: int | None = None) -> ArmBundle:
    selected = block_count
    if selected is None:
        selected = 10 if arm == CURRENT_ARM else 20
    selected_blocks = blocks(selected)
    return ArmBundle(
        case_id="case-1",
        arm=arm,
        status="completed",
        blocks=selected_blocks,
        raw_result_count=20,
        fused_result_count=20,
        selected_result_count=selected,
        unique_domains=selected,
        selected_tavily_count=selected,
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


def synthetic_retrieval_outcomes() -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for case_index in range(EXPECTED_CASE_COUNT):
        for arm in GENERATION_ARMS:
            current = arm == CURRENT_ARM
            answer_bearing = case_index < (18 if current else 20)
            selected_count = 10 if current else 20
            prompt_count = 10 if current else 20
            outcomes.append(
                {
                    "case_id": f"case-{case_index + 1}",
                    "arm": arm,
                    "status": "completed",
                    "available": True,
                    "raw_result_count": 20,
                    "fused_result_count": 20,
                    "selected_result_count": selected_count,
                    "prompt_result_count": prompt_count,
                    "unique_domains": 8,
                    "selected_tavily_count": selected_count,
                    "prompt_tavily_count": prompt_count,
                    "answer_key_in_selected_evidence": answer_bearing,
                    "answer_key_in_prompt_evidence": answer_bearing,
                    "raw_pool_sha256": f"raw-{case_index}",
                    "selected_packet_sha256": (
                        f"current-selected-{case_index}"
                        if current
                        else f"expanded-selected-{case_index}"
                    ),
                    "prompt_packet_sha256": (
                        f"current-prompt-{case_index}"
                        if current
                        else f"expanded-prompt-{case_index}"
                    ),
                    "retrieval_latency_ms": 10.0,
                    "error_kind": None,
                }
            )
    return outcomes


def synthetic_generation_outcomes() -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for model in MODELS:
        for case_index in range(EXPECTED_CASE_COUNT):
            for arm in GENERATION_ARMS:
                answer_limit = 15 if arm == CURRENT_ARM else 16
                citation_limit = 20 if arm == EXPANDED_ARM else 24
                support_limit = 18 if arm == EXPANDED_ARM else 20
                if arm == CURRENT_ARM:
                    citation_limit = 22
                    support_limit = 16
                outcomes.append(
                    {
                        "case_id": f"case-{case_index + 1}",
                        "arm": arm,
                        "model": model,
                        "status": "completed",
                        "native_request_completed": True,
                        "structured_schema_valid": (True if arm == CANDIDATE_ARM else None),
                        "structured_claim_count": (1 if arm == CANDIDATE_ARM else 0),
                        "answer_key_covered": case_index < answer_limit,
                        "citation_count": int(case_index < citation_limit),
                        "citation_ids_valid": True,
                        "citation_contract_passed": case_index < citation_limit,
                        "citation_support_proxy": case_index < support_limit,
                        "prompt_evidence_count": 10 if arm == CURRENT_ARM else 20,
                        "generation_latency_ms": 10.0,
                        "usage": {},
                        "error_kind": None,
                    }
                )
    return outcomes


def decision_for(
    retrieval_outcomes: list[dict[str, Any]] | None = None,
    generation_outcomes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    retrieved = retrieval_outcomes or synthetic_retrieval_outcomes()
    generated_rows = generation_outcomes or synthetic_generation_outcomes()
    retrieval_metrics = aggregate_retrieval(retrieved)
    generation_metrics = aggregate_generation(generated_rows)
    retrieval_paired = paired_retrieval_metrics(
        retrieved,
        field="answer_key_in_prompt_evidence",
        candidate_arm=EXPANDED_ARM,
        baseline_arm=CURRENT_ARM,
    )
    answer_paired = paired_generation_metrics(
        generated_rows,
        field="answer_key_covered",
        candidate_arm=CANDIDATE_ARM,
        baseline_arm=CURRENT_ARM,
    )
    support_paired = paired_generation_metrics(
        generated_rows,
        field="citation_support_proxy",
        candidate_arm=CANDIDATE_ARM,
        baseline_arm=EXPANDED_ARM,
    )
    return build_decision(
        retrieval_metrics,
        generation_metrics,
        retrieval_paired,
        answer_paired,
        support_paired,
        packet_identity(retrieved),
        retrieval_operations=24,
        generation_requests=144,
        tavily_requests=24,
    )


def test_locked_inputs_and_observed_boundary() -> None:
    root = Path(__file__).parents[1]
    protocol = root / "docs/benchmark-protocol-v16.md"
    manifest = root / "benchmarks/data/phase11_7_fresh_confirmation_v1.json"
    phase11_7_result = root / "benchmarks/results/phase11_7_fresh_confirmation_2026-07-29.json"
    reserve = root / "benchmarks/data/phase12_untouched_reserve_v1.json"

    assert hashlib.sha256(protocol.read_bytes()).hexdigest() == LOCKED_PROTOCOL_SHA256
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == LOCKED_MANIFEST_SHA256
    assert (
        hashlib.sha256(phase11_7_result.read_bytes()).hexdigest() == LOCKED_PHASE11_7_RESULT_SHA256
    )
    assert hashlib.sha256(reserve.read_bytes()).hexdigest() == LOCKED_RESERVE_MANIFEST_SHA256
    result = json.loads(phase11_7_result.read_bytes())
    assert result["decision"]["phase11_7_candidate_passed"] is False
    assert result["decision"]["phase12_executed"] is False


def test_balanced_expansion_and_structured_arm_isolate_expected_variables() -> None:
    current_system, current_prompt, current_blocks = build_prompt(
        row(),
        bundle(CURRENT_ARM),
        evidence_budget_chars=12_000,
        expanded_max_block_chars=1_500,
    )
    expanded_system, expanded_prompt, expanded_blocks = build_prompt(
        row(),
        bundle(EXPANDED_ARM),
        evidence_budget_chars=12_000,
        expanded_max_block_chars=1_500,
    )
    structured_system, structured_prompt, structured_blocks = build_prompt(
        row(),
        bundle(CANDIDATE_ARM),
        evidence_budget_chars=12_000,
        expanded_max_block_chars=1_500,
    )

    assert 0 < len(current_blocks) <= 10
    assert len(expanded_blocks) == 20
    assert len(expanded_blocks) > len(current_blocks)
    assert expanded_blocks == structured_blocks
    assert current_system == expanded_system
    assert current_prompt != expanded_prompt
    assert expanded_system != structured_system
    assert expanded_prompt != structured_prompt
    assert '"claims"' in structured_prompt
    assert sum(len(block.text) for block in expanded_blocks) <= 20 * 1_500


def test_projection_never_reads_answers_and_is_deterministic() -> None:
    first = project_blocks(
        bundle(EXPANDED_ARM),
        evidence_budget_chars=12_000,
        expanded_max_block_chars=1_500,
    )
    second = project_blocks(
        bundle(EXPANDED_ARM),
        evidence_budget_chars=12_000,
        expanded_max_block_chars=1_500,
    )

    assert first == second
    assert [block.citation_id for block in first] == [f"S{index}" for index in range(1, 21)]


def test_structured_parser_accepts_exact_contract_and_renders_citations() -> None:
    rendered, claim_count = parse_structured_answer(
        json.dumps({"claims": [{"text": "The answer is 42.", "citation_ids": ["S1", "S2"]}]})
    )

    assert rendered == "The answer is 42. [S1] [S2]"
    assert claim_count == 1


def test_structured_parser_allows_only_exact_insufficiency_without_citation() -> None:
    rendered, claim_count = parse_structured_answer(
        json.dumps(
            {
                "claims": [
                    {
                        "text": STRUCTURED_INSUFFICIENT_TEXT,
                        "citation_ids": [],
                    }
                ]
            }
        )
    )

    assert rendered == STRUCTURED_INSUFFICIENT_TEXT
    assert claim_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        '```json\n{"claims":[]}\n```',
        '{"claims":[]}',
        '{"claims":[{"text":"42","citation_ids":[]}]}',
        '{"claims":[{"text":"42 [S1]","citation_ids":["S1"]}]}',
        '{"claims":[{"text":"42","citation_ids":["[S1]"]}]}',
        '{"claims":[{"text":"42","citation_ids":["S1","S1"]}]}',
        '{"claims":[{"text":"42","citation_ids":["S1"],"extra":true}]}',
        '{"claims":[{"text":"42","citation_ids":["S1"]}],"extra":true}',
    ],
)
def test_structured_parser_rejects_permissive_or_ambiguous_output(
    payload: str,
) -> None:
    with pytest.raises(StructuredResponseError, match="response_schema_failure"):
        parse_structured_answer(payload)


def test_packet_identity_requires_one_raw_pool_and_shared_expanded_packet() -> None:
    outcomes = synthetic_retrieval_outcomes()
    assert packet_identity(outcomes) == {
        "raw_pool_matching_cases": 24,
        "expanded_selected_and_prompt_matching_cases": 24,
        "denominator": 24,
        "passed": True,
    }

    outcomes[-1]["prompt_packet_sha256"] = "different"
    assert packet_identity(outcomes)["passed"] is False


def test_public_retrieval_outcome_contains_hashes_not_private_evidence() -> None:
    outcome = public_retrieval_outcome(
        row(),
        bundle(EXPANDED_ARM),
        raw_pool_hash="raw-hash",
        evidence_budget_chars=12_000,
        expanded_max_block_chars=1_500,
    )

    assert outcome["raw_pool_sha256"] == "raw-hash"
    assert outcome["selected_result_count"] == 20
    assert outcome["prompt_result_count"] == 20
    assert outcome["answer_key_in_prompt_evidence"] is True
    assert not {
        "question",
        "answer",
        "title",
        "url",
        "snippet",
        "evidence",
    } & set(outcome)


def test_raw_pool_hash_is_deterministic_and_content_sensitive() -> None:
    first = [
        ProviderResult(
            title="One",
            url="https://one.example/",
            snippet="Evidence",
            provider="tavily",
            rank=1,
            query="query",
        )
    ]
    second = [first[0].model_copy(update={"snippet": "Different"})]

    assert raw_pool_sha256(first) == raw_pool_sha256(first)
    assert raw_pool_sha256(first) != raw_pool_sha256(second)


@pytest.mark.asyncio
@respx.mock
async def test_structured_generation_parses_renders_and_audits_without_private_text() -> None:
    respx.post(gemini_endpoint("gemini-3.5-flash-lite")).mock(
        return_value=httpx.Response(
            200,
            json={
                "modelVersion": "gemini-3.5-flash-lite",
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "claims": [
                                                {
                                                    "text": "The answer is 42.",
                                                    "citation_ids": ["S15"],
                                                }
                                            ]
                                        }
                                    )
                                }
                            ]
                        },
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
            expanded_max_block_chars=1_500,
            max_output_tokens=2_048,
            wall_time_seconds=60.0,
        )

    assert outcome["status"] == "completed"
    assert outcome["native_request_completed"] is True
    assert outcome["structured_schema_valid"] is True
    assert outcome["structured_claim_count"] == 1
    assert outcome["answer_key_covered"] is True
    assert outcome["citation_count"] == 1
    assert outcome["citation_ids_valid"] is True
    assert outcome["citation_support_proxy"] is True
    assert not {
        "answer",
        "question",
        "evidence",
        "system_prompt",
        "user_prompt",
        "raw_response",
    } & set(outcome)


@pytest.mark.asyncio
@respx.mock
async def test_schema_failure_is_scored_without_retry_or_raw_text() -> None:
    route = respx.post(gemini_endpoint("gemini-3.5-flash-lite")).mock(
        return_value=httpx.Response(
            200,
            json={
                "modelVersion": "gemini-3.5-flash-lite",
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "42 [S15]"}]},
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
            expanded_max_block_chars=1_500,
            max_output_tokens=2_048,
            wall_time_seconds=60.0,
        )

    assert route.call_count == 1
    assert outcome["status"] == "failed"
    assert outcome["native_request_completed"] is True
    assert outcome["structured_schema_valid"] is False
    assert outcome["error_kind"] == "response_schema_failure"
    assert outcome["answer_sha256"] is None


def test_all_twelve_gates_can_pass_but_only_phase11_9_is_allowed() -> None:
    decision = decision_for()

    assert len(decision["gates"]) == 12
    assert all(gate["passed"] for gate in decision["gates"].values())
    assert decision["phase11_8_candidate_passed"] is True
    assert decision["phase11_9_fresh_confirmation_allowed"] is True
    assert decision["quality_profile_promotion_allowed"] is False
    assert decision["quality_profile_promoted"] is False
    assert decision["phase12_untouched_evaluation_allowed"] is False
    assert decision["phase12_executed"] is False
    assert decision["merge_allowed"] is False
    assert decision["release_decision"] == "no-go"


def test_retrieval_floor_and_structured_schema_are_independently_blocking() -> None:
    retrieved = synthetic_retrieval_outcomes()
    for outcome in retrieved:
        if outcome["arm"] != CURRENT_ARM and outcome["case_id"] == "case-20":
            outcome["answer_key_in_prompt_evidence"] = False
    retrieval_decision = decision_for(retrieval_outcomes=retrieved)
    assert (
        retrieval_decision["gates"]["expanded_retrieval_available_and_answer_bearing"]["passed"]
        is False
    )

    generated = synthetic_generation_outcomes()
    failures = [
        outcome
        for outcome in generated
        if outcome["model"] == MODELS[0] and outcome["arm"] == CANDIDATE_ARM
    ][-2:]
    for outcome in failures:
        outcome["status"] = "failed"
        outcome["structured_schema_valid"] = False
        outcome["answer_key_covered"] = False
        outcome["citation_count"] = 0
        outcome["citation_ids_valid"] = False
        outcome["citation_contract_passed"] = False
        outcome["citation_support_proxy"] = False
        outcome["error_kind"] = "response_schema_failure"
    schema_decision = decision_for(generation_outcomes=generated)
    assert (
        schema_decision["gates"]["structured_schema_valid_at_least_23_of_24_per_model"]["passed"]
        is False
    )
    assert schema_decision["phase11_8_candidate_passed"] is False


def test_paired_metrics_use_only_the_two_locked_models() -> None:
    paired = paired_generation_metrics(
        synthetic_generation_outcomes(),
        field="answer_key_covered",
        candidate_arm=CANDIDATE_ARM,
        baseline_arm=BASELINE_ARM,
    )

    assert set(paired["by_model"]) == set(MODELS)
    assert "gemma-4-26b-a4b-it" not in paired["by_model"]


def test_locked_arguments_accept_defaults_and_reject_budget_changes(
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

    changed_models = argparse.Namespace(**vars(arguments))
    changed_models.models = ["gemini-3.5-flash-lite"]
    with pytest.raises(ValueError, match="exact locked model order"):
        validate_arguments(changed_models)

    changed_results = argparse.Namespace(**vars(arguments))
    changed_results.provider_max_results = 19
    with pytest.raises(ValueError, match="locked arguments changed"):
        validate_arguments(changed_results)


def test_product_defaults_and_result_boundary_remain_unchanged() -> None:
    root = Path(__file__).parents[1]
    result = root / "benchmarks/results/phase11_8_recovery_2026-07-29.json"
    report = root / "benchmarks/results/phase11_8_recovery_2026-07-29.md"

    assert not result.exists()
    assert not report.exists()
    assert (*COMMUNITY_PROVIDERS, "tavily") == QUALITY_PROVIDERS
    assert Settings().quality_primary_provider_share == 0.8
    assert BENCHMARK_NAME == "evidencemesh-phase11-8-corrective-recovery-v1"
