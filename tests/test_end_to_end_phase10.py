from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from benchmarks.run_end_to_end_phase10 import (
    ARMS,
    EXPECTED_GENERATION_REQUESTS,
    EXPECTED_RETRIEVAL_REQUESTS,
    MANIFEST_SHA256,
    MAXIMUM_TAVILY_REQUESTS,
    MODELS,
    EvidenceBlock,
    RetrievalBundle,
    aggregate_generation,
    build_prompt,
    gate_decision,
    gemini_endpoint,
    generate_all,
    generate_outcome,
    paired_answer_metrics,
    parse_gemini_completion,
    public_retrieval_outcome,
    request_gemini_completion,
    retrieval_packet_sha256,
    validate_arguments,
)
from benchmarks.run_live_retrieval import BenchmarkRow


def root() -> Path:
    return Path(__file__).parents[1]


def row(case_id: str = "case-1", answer: str = "42") -> BenchmarkRow:
    return BenchmarkRow(
        id=case_id,
        question="What is the answer?",
        answers=(answer,),
        topic="Other",
        answer_type="Number",
    )


def bundle(
    arm: str = "quality",
    *,
    text: str = "The answer is 42.",
) -> RetrievalBundle:
    blocks = (
        EvidenceBlock(
            citation_id="S1",
            title="Primary source",
            url="https://example.com/source",
            text=text,
            providers=("tavily",),
        ),
    )
    return RetrievalBundle(
        case_id="case-1",
        arm=arm,
        status="completed",
        blocks=() if arm == "closed_book" else blocks,
        source_count=0 if arm == "closed_book" else 1,
        unique_domains=0 if arm == "closed_book" else 1,
        queries_with_results=0 if arm == "closed_book" else 1,
        total_queries=0 if arm == "closed_book" else 1,
        provider_query_counts={} if arm == "closed_book" else {"tavily": 1},
        provider_failure_providers=(),
        warning_count=0,
        latency_ms=10.0,
        error_kind=None,
    )


def generation_outcome(
    case_id: str,
    model: str,
    arm: str,
    *,
    covered: bool,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "model": model,
        "arm": arm,
        "status": "completed",
        "answer_key_covered": covered,
        "citation_count": 1 if arm != "closed_book" else 0,
        "citation_ids_valid": True,
        "citation_support_proxy": covered and arm != "closed_book",
        "answer_chars": 10,
        "usage": {"totalTokenCount": 20},
        "generation_latency_ms": 100.0,
        "error_kind": None,
    }


def test_phase10_manifest_is_locked_private_and_novel() -> None:
    manifest_path = root() / "benchmarks/data/end_to_end_phase10_v1.json"
    payload = manifest_path.read_bytes()
    manifest = json.loads(payload)
    phase3 = json.loads(
        (root() / "benchmarks/results/simpleqa_retrieval_phase3_2026-07-28.json").read_text(
            encoding="utf-8"
        )
    )

    assert hashlib.sha256(payload).hexdigest() == MANIFEST_SHA256
    assert manifest["selection"]["seed"] == 11
    assert manifest["selection"]["case_count"] == 12
    assert len(manifest["case_ids"]) == len(set(manifest["case_ids"])) == 12
    assert not set(manifest["case_ids"]) & set(phase3["sample"]["ids"])
    assert all(value is False for value in manifest["privacy"].values())
    assert sum(manifest["topic_distribution"].values()) == 12
    assert sum(manifest["answer_type_distribution"].values()) == 12


def test_gemini_endpoint_uses_exact_model_id() -> None:
    assert gemini_endpoint("gemma-4-26b-a4b-it") == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent"
    )
    assert "?" not in gemini_endpoint("gemini-3.5-flash-lite")


def test_parse_gemini_completion_ignores_thought_parts() -> None:
    completion = parse_gemini_completion(
        {
            "modelVersion": "gemma-4-31b-it",
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"text": "private thought", "thought": True},
                            {"text": "Final answer [S1]"},
                        ]
                    },
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 20,
                "candidatesTokenCount": 5,
                "cachedContentTokenCount": False,
            },
        }
    )

    assert completion.answer == "Final answer [S1]"
    assert completion.response_model == "gemma-4-31b-it"
    assert completion.finish_reason == "STOP"
    assert completion.usage == {
        "promptTokenCount": 20,
        "candidatesTokenCount": 5,
    }


@pytest.mark.asyncio
@respx.mock
async def test_native_request_keeps_key_in_header_and_locks_thinking() -> None:
    route = respx.post(gemini_endpoint("gemini-3.5-flash-lite")).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "42"}]},
                    }
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        completion = await request_gemini_completion(
            client,
            api_key="test-secret",
            model="gemini-3.5-flash-lite",
            user_prompt="Question",
            max_output_tokens=2_048,
        )

    request = route.calls[0].request
    body = json.loads(request.content)
    assert completion.answer == "42"
    assert request.headers["x-goog-api-key"] == "test-secret"
    assert "test-secret" not in str(request.url)
    assert body["generationConfig"] == {
        "maxOutputTokens": 2_048,
        "thinkingConfig": {"thinkingLevel": "high"},
    }
    assert body["systemInstruction"]["parts"]


def test_prompt_budget_and_packet_hash_are_stable() -> None:
    first_prompt, first_blocks = build_prompt(
        row(),
        bundle(text="42 " * 1_000),
        evidence_budget_chars=250,
    )
    second_prompt, second_blocks = build_prompt(
        row(),
        bundle(text="42 " * 1_000),
        evidence_budget_chars=250,
    )

    assert first_prompt == second_prompt
    assert first_blocks == second_blocks
    assert len(first_blocks[0].text) < 250
    assert "[S1]" in first_prompt
    assert retrieval_packet_sha256(bundle()) == retrieval_packet_sha256(bundle())


@pytest.mark.asyncio
@respx.mock
async def test_generation_scores_answer_and_cited_evidence_without_persisting_text() -> None:
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
            max_output_tokens=2_048,
            wall_time_seconds=120.0,
        )

    assert outcome["status"] == "completed"
    assert outcome["answer_key_covered"] is True
    assert outcome["citation_ids_valid"] is True
    assert outcome["citation_support_proxy"] is True
    assert outcome["answer_sha256"] == hashlib.sha256(b"42 [S1]").hexdigest()
    assert "answer" not in outcome
    assert "evidence" not in outcome


@pytest.mark.asyncio
async def test_generation_reuses_one_bundle_across_models_and_arms(monkeypatch) -> None:
    seen: list[tuple[str, str, int]] = []

    async def fake_generate(
        selected_row: BenchmarkRow,
        selected_bundle: RetrievalBundle,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        seen.append(
            (
                selected_row.id,
                selected_bundle.arm,
                id(selected_bundle),
            )
        )
        return generation_outcome(
            selected_row.id,
            str(_kwargs["model"]),
            selected_bundle.arm,
            covered=True,
        )

    monkeypatch.setattr(
        "benchmarks.run_end_to_end_phase10.generate_outcome",
        fake_generate,
    )
    selected_row = row()
    bundles = {(selected_row.id, arm): bundle(arm) for arm in ARMS}
    outcomes = await generate_all(
        [selected_row],
        bundles,
        api_key="test-secret",
        models=MODELS,
        evidence_budget_chars=12_000,
        max_output_tokens=2_048,
        wall_time_seconds=120.0,
        pause_seconds=0.0,
        progress=False,
    )

    assert len(outcomes) == len(ARMS) * len(MODELS)
    for arm in ARMS:
        identities = {
            bundle_id for _case_id, selected_arm, bundle_id in seen if selected_arm == arm
        }
        assert identities == {id(bundles[(selected_row.id, arm)])}


def test_aggregate_generation_labels_proxy_and_citation_denominators() -> None:
    outcomes = [
        generation_outcome("case-1", MODELS[0], "quality", covered=True),
        generation_outcome("case-2", MODELS[0], "quality", covered=False),
    ]
    metrics = aggregate_generation(outcomes, citation_required=True)

    assert metrics["completed"] == {"numerator": 2, "denominator": 2, "rate": 1.0}
    assert metrics["answer_key_covered"] == {
        "numerator": 1,
        "denominator": 2,
        "rate": 0.5,
    }
    assert metrics["citation_presence"]["rate"] == 1.0
    assert metrics["citation_support_proxy"]["rate"] == 0.5


def test_paired_metrics_count_gains_regressions_and_ties() -> None:
    outcomes: list[dict[str, Any]] = []
    for model in MODELS:
        outcomes.extend(
            [
                generation_outcome("gain", model, "quality", covered=True),
                generation_outcome("gain", model, "community", covered=False),
                generation_outcome("regression", model, "quality", covered=False),
                generation_outcome("regression", model, "community", covered=True),
                generation_outcome("hit", model, "quality", covered=True),
                generation_outcome("hit", model, "community", covered=True),
                generation_outcome("miss", model, "quality", covered=False),
                generation_outcome("miss", model, "community", covered=False),
            ]
        )
    paired = paired_answer_metrics(
        outcomes,
        candidate_arm="quality",
        baseline_arm="community",
    )

    assert paired["overall"] == {
        "candidate_wins": 3,
        "baseline_wins": 3,
        "shared_hits": 3,
        "shared_misses": 3,
        "net_gain": 0,
    }
    assert paired["by_model"][MODELS[0]]["candidate_wins"] == 1


def test_gate_keeps_release_closed_even_when_functional_checks_pass() -> None:
    retrieval_metrics = {
        arm: {
            "availability": {"numerator": 12},
            "answer_key_in_evidence": {"numerator": 10 if arm == "quality" else 8},
        }
        for arm in ("tavily_direct", "community", "quality")
    }
    completed = {"numerator": 12}
    covered = {"numerator": 8}
    generation_metrics: dict[str, Any] = {
        model: {
            arm: {
                "completed": completed,
                "answer_key_covered": covered,
            }
            for arm in ARMS
        }
        for model in MODELS
    }
    generation_metrics["aggregate"] = {
        "quality": {
            "citation_presence": {"rate": 0.9},
            "citation_ids_valid": {"rate": 1.0},
            "citation_support_proxy": {"rate": 0.75},
        }
    }
    paired = {
        "quality_vs_community": {"overall": {"net_gain": 4, "baseline_wins": 2}},
        "quality_vs_closed_book": {"overall": {"net_gain": 5, "baseline_wins": 2}},
    }

    decision = gate_decision(
        retrieval_metrics,
        generation_metrics,
        paired,
        generation_request_count=EXPECTED_GENERATION_REQUESTS,
        retrieval_request_count=EXPECTED_RETRIEVAL_REQUESTS,
        tavily_request_count=MAXIMUM_TAVILY_REQUESTS,
    )

    assert decision["functional_gate_passed"] is True
    assert decision["cross_network_gate"]["status"] == "not_testable"
    assert decision["stage_b_allowed"] is False
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"


def test_public_retrieval_outcome_excludes_private_fields() -> None:
    outcome = public_retrieval_outcome(row(), bundle())
    forbidden = {
        "question",
        "answer",
        "reference_answer",
        "evidence",
        "title",
        "url",
        "content",
        "results",
    }
    assert not forbidden & set(outcome)
    assert outcome["answer_key_in_evidence"] is True
    assert outcome["evidence_packet_sha256"]


def test_locked_arguments_reject_model_or_budget_drift() -> None:
    arguments = argparse.Namespace(
        models=list(MODELS),
        max_sources=10,
        content_budget_chars=30_000,
        evidence_budget_chars=12_000,
        max_output_tokens=2_048,
        retrieval_wall_time_seconds=180.0,
        generation_wall_time_seconds=120.0,
        retrieval_pause_seconds=0.5,
        model_pause_seconds=2.0,
        request_timeout_seconds=20.0,
        gemini_api_key_env="GEMINI_API_KEY",
        tavily_api_key_env="TAVILY_API_KEY",
    )
    validate_arguments(arguments)

    arguments.models = list(reversed(MODELS))
    with pytest.raises(ValueError, match="exact locked model order"):
        validate_arguments(arguments)
    arguments.models = list(MODELS)
    arguments.max_output_tokens = 1_024
    with pytest.raises(ValueError, match="locked arguments changed"):
        validate_arguments(arguments)


def test_phase10_traffic_budget_is_explicit() -> None:
    assert EXPECTED_RETRIEVAL_REQUESTS == 36
    assert EXPECTED_GENERATION_REQUESTS == 144
    assert MAXIMUM_TAVILY_REQUESTS == 24
