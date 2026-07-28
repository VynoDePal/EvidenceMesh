"""Human- and automation-friendly command line interface."""

from __future__ import annotations

import asyncio
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from evidencemesh.benchmark import run_offline_benchmark
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import (
    ResearchRequest,
    SearchDepth,
    SearchProfile,
    SearchRequest,
)

app = typer.Typer(
    name="evidencemesh",
    help="Evidence-first search and deep-research infrastructure for AI agents.",
    no_args_is_help=True,
)
console = Console()
error_console = Console(stderr=True)


class OutputFormat(StrEnum):
    JSON = "json"
    TABLE = "table"


def _json(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _run(coroutine: Any) -> Any:
    try:
        return asyncio.run(coroutine)
    except KeyboardInterrupt:
        raise typer.Exit(130) from None
    except Exception as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


async def _search(request: SearchRequest) -> Any:
    async with EvidenceMesh() as engine:
        return await engine.search(request)


async def _research(request: ResearchRequest) -> Any:
    async with EvidenceMesh() as engine:
        return await engine.research(request)


def _search_table(response: Any) -> None:
    table = Table(title=f"EvidenceMesh — {response.metadata.query}")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Score", justify="right")
    table.add_column("Title")
    table.add_column("Domain", style="magenta")
    table.add_column("Providers")
    for hit in response.results:
        table.add_row(
            hit.citation_id,
            f"{hit.final_score:.3f}",
            hit.title,
            hit.domain,
            ", ".join(hit.providers),
        )
    console.print(table)
    for warning in response.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")


@app.command("search")
def search_command(
    query: str = typer.Argument(..., help="Search query."),
    limit: int = typer.Option(10, min=1, max=50),
    profile: SearchProfile = typer.Option(SearchProfile.WEB),
    language: str = typer.Option("en"),
    domain: list[str] | None = typer.Option(None, "--domain"),
    exclude_domain: list[str] | None = typer.Option(None, "--exclude-domain"),
    fetch_content: bool = typer.Option(False, "--fetch-content"),
    output: OutputFormat = typer.Option(OutputFormat.TABLE, "--output", "-o"),
) -> None:
    """Search multiple providers and fuse their rankings."""

    response = _run(
        _search(
            SearchRequest(
                query=query,
                limit=limit,
                profile=profile,
                language=language,
                domains=domain or [],
                exclude_domains=exclude_domain or [],
                fetch_content=fetch_content,
            )
        )
    )
    if output is OutputFormat.JSON:
        _json(response)
    else:
        _search_table(response)


@app.command("research")
def research_command(
    question: str = typer.Argument(..., help="Research question."),
    depth: SearchDepth = typer.Option(SearchDepth.STANDARD),
    profile: SearchProfile = typer.Option(SearchProfile.WEB),
    language: str = typer.Option("en"),
    max_sources: int = typer.Option(12, min=3, max=50),
    domain: list[str] | None = typer.Option(None, "--domain"),
    exclude_domain: list[str] | None = typer.Option(None, "--exclude-domain"),
) -> None:
    """Create a structured, citation-ready evidence packet."""

    packet = _run(
        _research(
            ResearchRequest(
                question=question,
                depth=depth,
                profile=profile,
                language=language,
                max_sources=max_sources,
                domains=domain or [],
                exclude_domains=exclude_domain or [],
            )
        )
    )
    _json(packet)


@app.command("fetch")
def fetch_command(
    url: str = typer.Argument(..., help="Public HTML, text or PDF URL."),
    max_chars: int = typer.Option(30_000, min=500, max=200_000),
) -> None:
    """Fetch and extract one URL through the outbound safety policy."""

    async def run() -> Any:
        async with EvidenceMesh() as engine:
            return await engine.fetch(url, max_chars=max_chars)

    _json(_run(run()))


@app.command("providers")
def providers_command() -> None:
    """Show configured providers and safety controls without network calls."""

    async def run() -> dict[str, Any]:
        async with EvidenceMesh() as engine:
            return engine.health()

    _json(_run(run()))


@app.command("cache-clear")
def cache_clear_command() -> None:
    """Clear locally cached search results and documents."""

    async def run() -> int:
        async with EvidenceMesh() as engine:
            return engine.cache.clear()

    count = _run(run())
    console.print(f"Removed {count} cache entr{'y' if count == 1 else 'ies'}.")


@app.command("benchmark-offline")
def benchmark_offline_command(
    fixture: Path | None = typer.Option(
        None,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional compatible JSON fixture.",
    ),
) -> None:
    """Run the deterministic fusion and deduplication regression benchmark."""

    _json(run_offline_benchmark(fixture))


@app.command("serve")
def serve_command(
    transport: str = typer.Option("stdio", help="stdio or http"),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000, min=1, max=65_535),
) -> None:
    """Run the FastMCP server."""

    from evidencemesh.mcp_server import mcp

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "http":
        mcp.run(transport="http", host=host, port=port)
    else:
        raise typer.BadParameter("transport must be 'stdio' or 'http'")


if __name__ == "__main__":
    app()
