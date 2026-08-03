from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from benchmarks.run_end_to_end_phase10 import MODELS
from benchmarks.run_live_retrieval import BenchmarkRow
from benchmarks.run_phase11_5_quality_recovery import (
    GENERATION_ARMS,
    ArmBundle,
    EvidenceBlock,
    build_decision,
    build_prompt,
    gemini_endpoint,
    generate_outcome,
    replay_arm,
    request_gemini_completion,
    validate_arguments,
)
from evidencemesh.models import ProviderResult, SourceType


def row(answer: str = "42") -> BenchmarkRow:
    return BenchmarkRow(
        id="case-1",
        question="What is the answer?",
        answers=(answer,),
        topic="Other",
        answer_type="Number",
    )


def blocks() -> tuple[EvidenceBlock, ...]:
    return tuple(
        EvidenceBlock(
            citation_id=f"S{index}",
            title=f"Source {index}",
            url=f"https://example{index}.com/source",
            text=("The answer is 42. " if index == 1 else "Other evidence. ") * 400,
            providers=("tavily",) if index <= 8 else ("wikipedia",),
        )
        for index in range(1, 11)
    )


def bundle(arm: str = "quality_candidate") -> ArmBundle:
    return ArmBundle(
        case_id="case-1",
        arm=arm,
        status="completed",
        blocks=blocks(),
        raw_result_count=15,
        fused_result_count=15,
        selected_result_count=10,
        unique_domains=10,
        selected_tavily_count=8,
        provider_stage_counts={},
        reservation_policy="provider_share:tavily:0.800",
        reservation_requested=8,
        reservation_eligible=10,
        reservation_feasible=10,
        reservation_target=8,
        reservation_fulfilled=8,
        reservation_shortfall_reason=None,
        retrieval_latency_ms=10.0,
        error_kind=None,
    )


def provider_results() -> list[ProviderResult]:
    results = [
        ProviderResult(
            title=f"Tavily result {index}",
            url=f"https://tavily{index}.example/result",
            snippet=f"What answer evidence {index}",
            provider="tavily",
            rank=index,
            query="What is the answer?",
            source_type=SourceType.WEB,
        )
        for index in range(1, 11)
    ]
    results.extend(
        ProviderResult(
            title=f"Community result {index}",
            url=f"https://community{index}.example/result",
            snippet=f"Additional answer evidence {index}",
            provider="wikipedia",
            rank=index,
            query="What is the answer?",
            source_type=SourceType.REFERENCE,
        )
        for index in range(1, 6)
    )
    return results


def test_candidate_projection_preserves_all_sources_and_legacy_can_starve_tail() -> None:
    _legacy_system, _legacy_prompt, legacy = build_prompt(
        row(),
        bundle("quality_current_8_2"),
        evidence_budget_chars=12_000,
        candidate_max_block_chars=900,
    )
    candidate_system, candidate_prompt, candidate = build_prompt(
        row(),
        bundle(),
        evidence_budget_chars=12_000,
        candidate_max_block_chars=900,
    )

    assert len(legacy) < 10
    assert len(candidate) == 10
    assert sum("tavily" in block.providers for block in candidate) == 8
    assert all(len(block.text) <= 900 for block in candidate)
    assert "[S10]" in candidate_prompt
    assert "Allowed citation identifiers" in candidate_prompt
    assert "Every externally verifiable factual statement" in candidate_system


def test_shared_pool_replay_keeps_8_2_reservation_and_community_non_tavily() -> None:
    raw = provider_results()
    current = replay_arm(
        "case-1",
        "What is the answer?",
        raw,
        arm="quality_current_8_2",
        limit=10,
        max_per_domain=3,
        retrieval_latency_ms=1.0,
    )
    candidate = replay_arm(
        "case-1",
        "What is the answer?",
        raw,
        arm="quality_candidate",
        limit=10,
        max_per_domain=3,
        retrieval_latency_ms=1.0,
    )
    community = replay_arm(
        "case-1",
        "What is the answer?",
        raw,
        arm="community_observability",
        limit=10,
        max_per_domain=3,
        retrieval_latency_ms=1.0,
    )

    assert current.blocks == candidate.blocks
    assert candidate.reservation_requested == 8
    assert candidate.reservation_target == 8
    assert candidate.reservation_fulfilled == 8
    assert candidate.selected_tavily_count == 8
    assert all("tavily" not in block.providers for block in community.blocks)


@pytest.mark.asyncio
@respx.mock
async def test_candidate_request_uses_exact_system_contract_and_header_key() -> None:
    route = respx.post(gemini_endpoint("gemini-3.5-flash-lite")).mock(
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
        completion = await request_gemini_completion(
            client,
            api_key="test-secret",
            model="gemini-3.5-flash-lite",
            system_prompt="Strict citation contract",
            user_prompt="Question",
            max_output_tokens=2_048,
        )

    request = route.calls[0].request
    payload = json.loads(request.content)
    assert completion.answer == "42 [S1]"
    assert request.headers["x-goog-api-key"] == "test-secret"
    assert "test-secret" not in str(request.url)
    assert payload["systemInstruction"]["parts"] == [{"text": "Strict citation contract"}]
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"}


@pytest.mark.asyncio
@respx.mock
async def test_generation_audits_support_without_persisting_private_text() -> None:
    respx.post(gemini_endpoint("gemma-4-31b-it")).mock(
        return_value=httpx.Response(
            200,
            json={
                "modelVersion": "gemma-4-31b-it",
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
            bundle(),
            client=client,
            api_key="test-secret",
            model="gemma-4-31b-it",
            evidence_budget_chars=12_000,
            candidate_max_block_chars=900,
            max_output_tokens=2_048,
            wall_time_seconds=120.0,
        )

    assert outcome["status"] == "completed"
    assert outcome["answer_key_covered"] is True
    assert outcome["citation_count"] == 1
    assert outcome["citation_ids_valid"] is True
    assert outcome["citation_contract_passed"] is True
    assert outcome["citation_support_proxy"] is True
    assert "answer" not in outcome
    assert "evidence" not in outcome


def _metric(value: int, denominator: int) -> dict[str, int | float]:
    return {
        "numerator": value,
        "denominator": denominator,
        "rate": value / denominator,
    }


def passing_generation_metrics() -> dict[str, Any]:
    aggregate = {
        arm: {
            "answer_key_covered": _metric(30, 36),
            "citation_presence": _metric(36, 36),
            "citation_ids_valid": _metric(36, 36),
            "citation_support_proxy": _metric(30, 36),
        }
        for arm in GENERATION_ARMS
    }
    by_model = {
        model: {
            arm: {
                "completed": _metric(12, 12),
            }
            for arm in GENERATION_ARMS
        }
        for model in MODELS
    }
    return {"aggregate": aggregate, "by_model": by_model}


def test_decision_only_unblocks_phase12_when_every_quality_gate_passes() -> None:
    retrieval = {
        "tavily_direct": {
            "answer_key_in_prompt_evidence": _metric(10, 12),
        },
        "quality_candidate": {
            "answer_key_in_prompt_evidence": _metric(10, 12),
        },
    }
    paired = {
        "quality_candidate_vs_tavily_direct": {
            "overall": {
                "candidate_wins": 1,
                "baseline_wins": 1,
                "shared_hits": 29,
                "shared_misses": 5,
                "net_gain": 0,
            }
        },
        "quality_candidate_vs_quality_current_8_2": {
            "overall": {
                "candidate_wins": 2,
                "baseline_wins": 1,
                "shared_hits": 28,
                "shared_misses": 5,
                "net_gain": 1,
            }
        },
    }

    decision = build_decision(
        retrieval,
        passing_generation_metrics(),
        paired,
        retrieval_operations=12,
        generation_requests=108,
        tavily_requests=12,
    )

    assert decision["phase11_5_candidate_passed"] is True
    assert decision["phase12_untouched_evaluation_allowed"] is True
    assert decision["phase12_executed"] is False
    assert decision["community_observability_blocking"] is False
    assert decision["public_alpha_allowed"] is False
    assert decision["release_decision"] == "no-go"


def test_locked_argument_validation_rejects_extra_model_calls(tmp_path: Path) -> None:
    arguments = argparse.Namespace(
        models=list(MODELS),
        max_results=10,
        max_per_domain=3,
        evidence_budget_chars=12_000,
        candidate_max_block_chars=900,
        max_output_tokens=2_048,
        retrieval_wall_time_seconds=90.0,
        generation_wall_time_seconds=120.0,
        retrieval_pause_seconds=0.5,
        model_pause_seconds=2.0,
        request_timeout_seconds=20.0,
        gemini_api_key_env="GEMINI_API_KEY",
        tavily_api_key_env="TAVILY_API_KEY",
        output=tmp_path / "result.json",
    )
    validate_arguments(arguments)
    arguments.models = [*MODELS, "unexpected"]

    with pytest.raises(ValueError, match="exact locked model order"):
        validate_arguments(arguments)


def test_committed_phase11_5_result_is_the_audited_no_go() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "phase11_5_quality_recovery_2026-07-29.json"
    report_path = root / "benchmarks" / "results" / "phase11_5_quality_recovery_2026-07-29.md"
    result = json.loads(result_path.read_bytes())
    report = report_path.read_text(encoding="utf-8")

    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == (
        "7c9716cd970c3f955934ccf218ecbd835b261f1cf885c2b749217452b90af29c"
    )
    assert result["environment"]["commit_sha"] == ("c496186b64a07db035f96898cb0c9ec45e573833")
    assert result["traffic"] == {
        "case_retrieval_operations": 12,
        "expected_generation_requests": 108,
        "expected_retrieval_operations": 12,
        "generation_requests": 108,
        "maximum_tavily_requests": 12,
        "provider_query_calls": 48,
        "repair_requests": 0,
        "retries": 0,
        "tavily_requests": 12,
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
    assert sum(gate["passed"] for gate in gates.values()) == 6
    assert gates["completion_at_least_11_of_12_per_model_arm"]["passed"] is False
    assert gates["candidate_no_net_answer_regression_vs_tavily_direct"]["paired"]["net_gain"] == -3
    assert gates["candidate_no_net_answer_regression_vs_tavily_direct"]["passed"] is False
    assert gates["candidate_no_net_answer_regression_vs_current_8_2"]["passed"] is True
    assert gates["candidate_citation_presence_at_least_90_percent"]["passed"] is True
    assert gates["candidate_citation_ids_100_percent_valid"]["passed"] is True
    assert gates["candidate_citation_support_at_least_70_percent"]["passed"] is True

    decision = result["decision"]
    assert decision["phase11_5_candidate_passed"] is False
    assert decision["phase12_untouched_evaluation_allowed"] is False
    assert decision["phase12_executed"] is False
    assert decision["merge_allowed"] is False
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"
    assert decision["superiority_claim_allowed"] is False

    assert "30482256579" in report
    assert "candidate failed; Phase 12 remains blocked" in report
    assert "25/36 vs 28/36" in report
