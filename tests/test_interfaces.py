from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import typer
from conftest import StaticFetcher, StaticProvider
from fastmcp import Client
from typer.testing import CliRunner

from evidencemesh import cli, mcp_server
from evidencemesh.engine import EvidenceMesh
from evidencemesh.errors import BudgetConfigurationError
from evidencemesh.models import (
    BatchSearchResponse,
    ClaimReviewPacket,
    CoverageReport,
    EvidenceItem,
    FetchedDocument,
    ProviderResult,
    ResearchPacket,
    SearchHit,
    SearchMetadata,
    SearchRequest,
    SearchResponse,
    SourceType,
)


class FakeContext:
    def __init__(self, engine: EvidenceMesh) -> None:
        self.lifespan_context = {"engine": engine}
        self.messages: list[str] = []

    async def info(self, message: str) -> None:
        self.messages.append(message)


@pytest.mark.asyncio
async def test_mcp_tools_use_shared_engine(
    settings,
    result: ProviderResult,
    document: FetchedDocument,
) -> None:
    engine = EvidenceMesh(
        settings,
        providers=[StaticProvider("alpha", [result])],
        fetcher=StaticFetcher({result.url: document}),
    )
    context = FakeContext(engine)
    search = await mcp_server.search_web(
        "EvidenceMesh",
        limit=3,
        fetch_content=True,
        ctx=context,
    )
    research = await mcp_server.deep_research(
        "What does EvidenceMesh provide?",
        max_sources=3,
        ctx=context,
    )
    fetched = await mcp_server.fetch_url(result.url, ctx=context)
    batch = await mcp_server.batch_search(
        ["first query", "second query"],
        ctx=context,
    )
    review = await mcp_server.verify_claim(
        "EvidenceMesh provides evidence",
        max_sources=3,
        ctx=context,
    )
    health = await mcp_server.health(ctx=context)
    assert search["results"][0]["citation_id"] == "S1"
    assert research["synthesis_protocol"]
    assert fetched["title"] == document.title
    assert len(batch["responses"]) == 2
    assert review["status"] == "insufficient_independent_evidence"
    assert health["status"] == "ready"
    assert len(context.messages) == 2
    assert "EvidenceMesh" not in context.messages[0]
    with pytest.raises(ValueError, match="at most 20"):
        await mcp_server.batch_search(["query"] * 21, ctx=context)
    await engine.aclose()


def test_mcp_resource_and_prompt() -> None:
    guide = mcp_server.research_guide()
    prompt = mcp_server.evidence_first_research("What changed?")
    assert "untrusted data" in guide
    assert "immediately after every externally" in guide
    assert "deep_research" in prompt
    assert "never invent or renumber" in prompt
    assert "identifier validity" in prompt
    assert "What changed?" in prompt


@pytest.mark.asyncio
async def test_mcp_lifespan_closes_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EVIDENCEMESH_CACHE_PATH", str(tmp_path / "mcp-cache.sqlite3"))
    monkeypatch.setenv("EVIDENCEMESH_PROVIDERS", "wikipedia")
    async with mcp_server.app_lifespan(mcp_server.mcp) as state:
        assert state["engine"].health()["status"] == "ready"
        engine = state["engine"]
    assert engine._closed is True


@pytest.mark.asyncio
async def test_fastmcp_in_memory_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EVIDENCEMESH_CACHE_PATH", str(tmp_path / "client-cache.sqlite3"))
    monkeypatch.setenv("EVIDENCEMESH_PROVIDERS", "wikipedia")
    async with Client(mcp_server.mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()
        health = await client.call_tool("health", {})
    assert [tool.name for tool in tools] == [
        "search_web",
        "deep_research",
        "fetch_url",
        "batch_search",
        "verify_claim",
        "health",
    ]
    assert str(resources[0].uri) == "evidencemesh://research-guide"
    assert [prompt.name for prompt in prompts] == ["evidence_first_research"]
    assert health.data["status"] == "ready"


def sample_response() -> SearchResponse:
    hit = SearchHit(
        citation_id="S1",
        title="EvidenceMesh",
        url="https://example.com/a",
        canonical_url="https://example.com/a",
        snippet="Structured evidence",
        domain="example.com",
        providers=["alpha"],
        provider_ranks={"alpha": 1},
        matched_queries=["EvidenceMesh"],
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
        query="EvidenceMesh",
        queries_executed=["EvidenceMesh"],
        providers_requested=["alpha"],
        providers_succeeded=["alpha"],
        provider_failures={},
        raw_result_count=1,
        deduplicated_result_count=1,
        elapsed_ms=1,
        cache_hits=0,
        generated_at=datetime.now(UTC),
    )
    return SearchResponse(
        results=[hit],
        evidence=[evidence],
        metadata=metadata,
        warnings=["synthetic warning"],
    )


def sample_packet() -> ResearchPacket:
    response = sample_response()
    return ResearchPacket(
        question="What is EvidenceMesh?",
        subqueries=["What is EvidenceMesh?"],
        evidence=response.evidence,
        sources=response.results,
        coverage=CoverageReport(
            unique_sources=1,
            unique_domains=1,
            queries_with_results=1,
            total_queries=1,
            extracted_sources=1,
            flagged_sources=0,
        ),
        synthesis_protocol=["Cite sources."],
        metadata=response.metadata,
    )


@pytest.mark.parametrize("output", ["table", "json"])
def test_cli_search(
    monkeypatch: pytest.MonkeyPatch,
    output: str,
) -> None:
    async def fake_search(request: SearchRequest) -> SearchResponse:
        return sample_response()

    monkeypatch.setattr(cli, "_search", fake_search)
    result = CliRunner().invoke(
        cli.app,
        ["search", "EvidenceMesh", "--output", output],
    )
    assert result.exit_code == 0
    assert "EvidenceMesh" in result.stdout
    if output == "json":
        assert json.loads(result.stdout)["results"][0]["citation_id"] == "S1"


def test_cli_research_and_benchmark(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_research(request: Any) -> ResearchPacket:
        return sample_packet()

    monkeypatch.setattr(cli, "_research", fake_research)
    runner = CliRunner()
    research = runner.invoke(cli.app, ["research", "What is EvidenceMesh?"])
    benchmark = runner.invoke(cli.app, ["benchmark-offline"])
    assert research.exit_code == 0
    assert json.loads(research.stdout)["coverage"]["unique_sources"] == 1
    assert benchmark.exit_code == 0
    assert json.loads(benchmark.stdout)["case_count"] == 12


class FakeCache:
    def clear(self) -> int:
        return 2


class FakeCliEngine:
    cache = FakeCache()

    async def __aenter__(self) -> FakeCliEngine:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def fetch(
        self,
        url: str,
        *,
        max_chars: int,
        use_cache: bool = True,
    ) -> FetchedDocument:
        assert isinstance(use_cache, bool)
        return FetchedDocument(
            url=url,
            canonical_url=url,
            title="Fetched document",
            media_type="text/plain",
            text="Evidence",
            retrieved_at=datetime.now(UTC),
            content_sha256="b" * 64,
            content_chars=8,
        )

    def health(self) -> dict[str, Any]:
        return {"status": "ready", "providers": []}


def test_cli_fetch_providers_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "EvidenceMesh", FakeCliEngine)
    runner = CliRunner()
    fetched = runner.invoke(cli.app, ["fetch", "https://example.com/a"])
    providers = runner.invoke(cli.app, ["providers"])
    cleared = runner.invoke(cli.app, ["cache-clear"])
    assert fetched.exit_code == 0
    assert json.loads(fetched.stdout)["title"] == "Fetched document"
    assert providers.exit_code == 0
    assert '"status": "ready"' in providers.stdout
    assert cleared.exit_code == 0
    assert "Removed 2 cache entries" in cleared.stdout


def test_cli_run_handles_interrupt_and_error() -> None:
    async def interrupted() -> None:
        raise KeyboardInterrupt

    async def failed() -> None:
        raise RuntimeError("expected")

    with pytest.raises(typer.Exit) as interrupt:
        cli._run(interrupted())
    assert interrupt.value.exit_code == 130
    with pytest.raises(typer.Exit) as failure:
        cli._run(failed())
    assert failure.value.exit_code == 1
    assert cli._run(asyncio.sleep(0, result=7)) == 7


def test_cli_serve_and_mcp_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(mcp_server.mcp, "run", fake_run)
    runner = CliRunner()
    assert runner.invoke(cli.app, ["serve", "--transport", "stdio"]).exit_code == 0
    assert runner.invoke(cli.app, ["serve", "--transport", "http"]).exit_code == 0
    assert runner.invoke(cli.app, ["serve", "--transport", "invalid"]).exit_code != 0
    monkeypatch.setenv("EVIDENCEMESH_TRANSPORT", "http")
    monkeypatch.setenv("EVIDENCEMESH_PORT", "8123")
    mcp_server.main()
    monkeypatch.setenv("EVIDENCEMESH_TRANSPORT", "stdio")
    mcp_server.main()
    assert [call["transport"] for call in calls] == ["stdio", "http", "http", "stdio"]
    monkeypatch.setenv(
        "EVIDENCEMESH_CLOSED_ALPHA_LEDGER",
        str(tmp_path / "closed-alpha.sqlite3"),
    )
    blocked = runner.invoke(cli.app, ["serve", "--transport", "http"])
    assert blocked.exit_code != 0
    assert [call["transport"] for call in calls] == ["stdio", "http", "http", "stdio"]
    monkeypatch.setenv("EVIDENCEMESH_TRANSPORT", "http")
    with pytest.raises(BudgetConfigurationError, match="STDIO"):
        mcp_server.main()
    monkeypatch.delenv("EVIDENCEMESH_CLOSED_ALPHA_LEDGER")
    monkeypatch.setenv("EVIDENCEMESH_TRANSPORT", "invalid")
    with pytest.raises(ValueError, match="TRANSPORT"):
        mcp_server.main()


def test_interface_models_serialize() -> None:
    response = sample_response()
    batch = BatchSearchResponse(responses=[response])
    review = ClaimReviewPacket(
        claim="claim",
        evidence=response.evidence,
        sources=response.results,
        status="review",
        review_protocol=["Inspect evidence."],
    )
    assert batch.model_dump(mode="json")["responses"]
    assert review.model_dump(mode="json")["status"] == "review"
