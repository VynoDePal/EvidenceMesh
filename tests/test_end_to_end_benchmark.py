from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from benchmarks.run_end_to_end import (
    PROMPT_VERSION,
    aggregate,
    build_messages,
    citation_numbers,
    completion_endpoint,
    evaluate,
    parse_completion,
)
from benchmarks.run_live_retrieval import BenchmarkRow
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import (
    CoverageReport,
    EvidenceItem,
    ResearchPacket,
    SearchDepth,
    SearchHit,
    SearchMetadata,
    SourceType,
)


def packet() -> ResearchPacket:
    hit = SearchHit(
        citation_id="S1",
        title="Primary source",
        url="https://example.com/source",
        canonical_url="https://example.com/source",
        snippet="Alpha is the supported answer.",
        domain="example.com",
        providers=["stub"],
        provider_ranks={"stub": 1},
        matched_queries=["What is supported?"],
        source_type=SourceType.WEB,
        fusion_score=1.0,
        relevance_score=1.0,
        source_signal_score=0.5,
        final_score=0.9,
    )
    evidence = EvidenceItem(
        citation_id="S1",
        title=hit.title,
        url=hit.url,
        canonical_url=hit.canonical_url,
        quote=hit.snippet,
        providers=hit.providers,
        retrieved_at=datetime.now(UTC),
        content_sha256="a" * 64,
        source_type=SourceType.WEB,
    )
    metadata = SearchMetadata(
        query="What is supported?",
        queries_executed=["What is supported?"],
        providers_requested=["stub"],
        providers_succeeded=["stub"],
        provider_failures={},
        raw_result_count=1,
        deduplicated_result_count=1,
        elapsed_ms=1,
        cache_hits=0,
        generated_at=datetime.now(UTC),
    )
    return ResearchPacket(
        question="What is supported?",
        subqueries=["What is supported?"],
        evidence=[evidence],
        sources=[hit],
        coverage=CoverageReport(
            unique_sources=1,
            unique_domains=1,
            queries_with_results=1,
            total_queries=1,
            extracted_sources=1,
            flagged_sources=0,
        ),
        synthesis_protocol=["Cite sources."],
        metadata=metadata,
    )


class StaticResearchEngine(EvidenceMesh):
    def __init__(self, result: ResearchPacket, settings) -> None:
        super().__init__(settings, providers=[])
        self.result = result

    async def research(self, request, **kwargs):
        return self.result


def test_completion_endpoint_and_parser() -> None:
    assert (
        completion_endpoint("http://127.0.0.1:11434/v1")
        == "http://127.0.0.1:11434/v1/chat/completions"
    )
    assert completion_endpoint("https://model.example/v1/chat/completions").endswith(
        "/chat/completions"
    )
    with pytest.raises(ValueError, match="omit credentials"):
        completion_endpoint("https://user:pass@model.example/v1")
    result = parse_completion(
        {
            "model": "local-model",
            "choices": [
                {
                    "message": {"content": "Alpha [S1]"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "other": "ignored"},
        }
    )
    assert result.answer == "Alpha [S1]"
    assert result.usage == {"prompt_tokens": 10}
    assert citation_numbers("Alpha [S1], again [S1], invalid [S0].") == ["S1"]


def test_build_messages_is_evidence_bounded() -> None:
    row = BenchmarkRow(id="q1", question="What is supported?", answers=("Alpha",))
    messages, evidence_ids = build_messages(
        row,
        packet(),
        evidence_budget_chars=1_000,
    )
    assert PROMPT_VERSION == "evidence-answer-v1"
    assert evidence_ids == ["S1"]
    assert "Alpha is the supported answer." in messages[1]["content"]
    assert "untrusted" in messages[0]["content"]


@pytest.mark.asyncio
async def test_end_to_end_report_separates_private_grading_data(settings) -> None:
    response_payload = {
        "model": "local-model",
        "choices": [
            {
                "message": {"content": "Alpha [S1]"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 4},
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))
    )
    engine = StaticResearchEngine(packet(), settings)
    engine.result.metadata.provider_failures = {"stub:What is supported?": "provider echoed Alpha"}
    row = BenchmarkRow(id="q1", question="What is supported?", answers=("Alpha",))
    report, private_records = await evaluate(
        [row],
        dataset_metadata={"name": "synthetic", "sha256": "b" * 64},
        seed=0,
        engine=engine,
        completion_client=client,
        endpoint="https://model.example/v1/chat/completions",
        api_key="secret",
        model="local-model",
        depth=SearchDepth.QUICK,
        language="en",
        max_sources=3,
        content_budget_chars=3_000,
        evidence_prompt_budget_chars=1_000,
        max_output_tokens=64,
        wall_time_seconds=5,
        case_concurrency=1,
        network_region="test",
        progress=False,
    )
    rendered = str(report)
    assert "What is supported?" not in rendered
    assert "Alpha [S1]" not in rendered
    assert "provider echoed Alpha" not in rendered
    assert "secret" not in rendered
    assert report["metrics"]["completed_count"] == 1
    assert report["metrics"]["answer_correctness"] is None
    assert report["outcomes"][0]["citation_ids_valid"] is True
    assert report["outcomes"][0]["provider_failure_providers"] == ["stub"]
    assert private_records[0]["problem"] == "What is supported?"
    assert private_records[0]["response"] == "Alpha [S1]"
    await client.aclose()
    await engine.aclose()


def test_aggregate_never_invents_correctness() -> None:
    metrics = aggregate(
        [
            {
                "status": "failed",
                "retrieval_latency_ms": 1,
                "generation_latency_ms": 0,
                "total_latency_ms": 2,
                "evidence_count": 0,
                "citation_ids": [],
                "citation_ids_valid": False,
                "answer_chars": 0,
                "usage": {},
                "error_kind": "case_timeout",
            }
        ]
    )
    assert metrics["completion_rate"] == 0
    assert metrics["answer_correctness"] is None
    assert metrics["error_kinds"] == {"case_timeout": 1}
