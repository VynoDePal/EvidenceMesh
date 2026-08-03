from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from benchmarks import run_phase11_8_8_offline_projection_lock as offline
from benchmarks import run_phase11_8_8_projection_calibration as live
from benchmarks.phase11_8_8_projection_candidate import (
    OMISSION_SEPARATOR,
    candidate_project_blocks_v2,
    rendered_evidence_chars,
)

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/benchmark-protocol-v23.md"
WORKFLOW = ROOT / ".github/workflows/phase11-8-8-offline-projection-lock.yml"
FIXTURE = ROOT / "benchmarks/data/phase11_8_8_offline_projection_fixtures_v1.json"
RESULT = ROOT / "benchmarks/results/phase11_8_8_offline_projection_lock_2026-07-30.json"
CANDIDATE = ROOT / "benchmarks/phase11_8_8_projection_candidate.py"
LIVE_RUNNER = ROOT / "benchmarks/run_phase11_8_8_projection_calibration.py"


@dataclass(frozen=True, slots=True)
class Block:
    citation_id: str
    title: str
    url: str
    text: str
    providers: tuple[str, ...] = ("tavily",)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ratio(numerator: int, denominator: int = 24) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 6) if denominator else None,
    }


def _passing_live_decision() -> dict[str, Any]:
    metrics = {
        arm: {
            "availability": _ratio(24),
            "answer_key_in_selected_evidence": _ratio(21),
            "answer_key_in_prompt_evidence": _ratio(21 if arm == live.V2_ARM else 18),
        }
        for arm in live.PROJECTION_ARMS
    }
    paired = {
        "candidate_wins": 3,
        "baseline_wins": 0,
        "shared_hits": 18,
        "shared_misses": 3,
        "net_gain": 3,
    }
    identity = {
        "shared_packet_identity_passed": True,
        "projection_invariants_passed": True,
    }
    traffic = {
        "case_retrieval_operations": 24,
        "provider_query_calls": 24,
        "tavily_requests": 24,
        "other_provider_requests": 0,
        "model_requests": 0,
        "gemini_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
    }
    return live.build_decision(
        metrics,
        paired,
        paired,
        {"numerator": 21, "denominator": 21, "rate": 1.0},
        identity,
        traffic,
        {"passed": True},
    )


def test_frozen_hashes_are_exact_and_have_no_placeholders() -> None:
    assert _sha256(PROTOCOL) == offline.LOCKED_PROTOCOL_SHA256
    assert _sha256(FIXTURE) == offline.LOCKED_FIXTURE_SHA256
    assert _sha256(CANDIDATE) == offline.LOCKED_CANDIDATE_V2_SHA256
    assert _sha256(LIVE_RUNNER) == offline.LOCKED_LIVE_RUNNER_SHA256
    assert "__PROTOCOL_SHA256__" not in PROTOCOL.read_text()
    assert "__CANDIDATE_V2_SHA256__" not in LIVE_RUNNER.read_text()


def test_committed_offline_report_reproduces_byte_for_byte(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    assert offline.main.__name__ == "main"
    rendered = (
        json.dumps(
            offline.run(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    output.write_text(rendered, encoding="utf-8")
    assert output.read_bytes() == RESULT.read_bytes()


def test_report_has_fourteen_passing_offline_gates_and_zero_traffic() -> None:
    report = json.loads(RESULT.read_bytes())
    assert report["benchmark"] == offline.BENCHMARK_NAME
    assert len(report["gates"]) == 14
    assert all(gate["passed"] for gate in report["gates"].values())
    assert report["traffic"] == {
        "network_requests": 0,
        "provider_calls": 0,
        "search_calls": 0,
        "model_calls": 0,
        "secrets_bound": 0,
        "tavily_requests": 0,
        "gemini_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
    }
    assert report["decision"]["offline_engineering_lock_passed"] is True
    assert report["decision"]["future_tavily_calibration_authorized"] is False
    assert report["decision"]["phase11_9_protocol_may_be_frozen"] is False
    assert report["decision"]["phase12_authorized"] is False
    assert report["decision"]["merge_allowed"] is False
    assert report["decision"]["release_allowed"] is False
    assert report["decision"]["release_decision"] == "no-go"


def test_synthetic_controls_and_candidate_are_reported_honestly() -> None:
    report = json.loads(RESULT.read_bytes())
    projection = report["projection"]
    assert projection["equal_cap_hits"] == 3
    assert projection["v1_hits"] == 7
    assert projection["v2_hits"] == 12
    assert projection["paired_v2_vs_equal_cap"]["baseline_wins"] == 0
    assert projection["paired_v2_vs_v1"]["baseline_wins"] == 0
    assert projection["historical_equal_cap_over_budget_cases"] == 4
    assert report["fixture_disclosure"]["predictive_quality_claim_allowed"] is False
    assert report["decision"]["real_case_quality_improvement_proven"] is False


def test_candidate_interface_is_answer_blind_and_standard_library_only() -> None:
    signature = inspect.signature(candidate_project_blocks_v2)
    assert list(signature.parameters) == [
        "blocks",
        "question",
        "budget_chars",
        "max_block_chars",
        "min_block_chars",
    ]
    source = CANDIDATE.read_text()
    tree = ast.parse(source)
    imports = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imports.discard("")
    assert imports <= {
        "__future__",
        "collections",
        "dataclasses",
        "itertools",
        "re",
        "typing",
    }
    forbidden = {
        "answer",
        "answers",
        "reference_answer",
        "expected_answer",
        "answer_hash",
        "sentinel",
        "case_id",
        "row_index",
    }
    assert forbidden.isdisjoint(signature.parameters)
    assert "open(" not in source
    assert "getenv(" not in source
    assert "httpx" not in source


def test_candidate_preserves_order_metadata_source_text_and_exact_budget() -> None:
    blocks = tuple(
        Block(
            citation_id=f"S{index}",
            title=("Project Selene language record" if index == 5 else f"Source {index}"),
            url=f"https://source-{index}.example/item",
            text=(
                ("neutral registry context. " * 25)
                + ("Project Selene uses LumaScript. " if index == 5 else "")
                + ("context " * 90)
            ),
        )
        for index in range(1, 9)
    )
    projected = candidate_project_blocks_v2(
        blocks,
        "Which language does Project Selene use?",
        2_000,
        500,
        min_block_chars=96,
    )
    assert rendered_evidence_chars(projected) <= 2_000
    assert all(len(block.text) <= 500 for block in projected)
    assert [block.citation_id for block in projected] == sorted(
        (block.citation_id for block in projected),
        key=lambda value: int(value[1:]),
    )
    source_by_id = {block.citation_id: block for block in blocks}
    assert all(
        (block.title, block.url, block.providers)
        == (
            source_by_id[block.citation_id].title,
            source_by_id[block.citation_id].url,
            source_by_id[block.citation_id].providers,
        )
        for block in projected
    )
    for block in projected:
        source = source_by_id[block.citation_id].text.strip()
        cursor = 0
        for segment in block.text.split(OMISSION_SEPARATOR):
            if not segment:
                continue
            position = source.find(segment, cursor)
            assert position >= 0
            cursor = position + len(segment)
    assert any("LumaScript" in block.text for block in projected)


def test_candidate_is_deterministic_and_rejects_invalid_boundaries() -> None:
    block = Block(
        citation_id="S1",
        title="Théâtre Élan",
        url="https://example.test/theatre",
        text=("architecture culturelle. " * 40) + "Designed by Anaïs Koffi.",
    )
    outputs = {
        tuple(
            (
                item.citation_id,
                item.title,
                item.url,
                item.text,
                item.providers,
            )
            for item in candidate_project_blocks_v2(
                (block,),
                "Who designed Théâtre Élan?",
                480,
                420,
                min_block_chars=96,
            )
        )
        for _ in range(10)
    }
    assert len(outputs) == 1
    with pytest.raises(ValueError, match="unique"):
        candidate_project_blocks_v2((block, block), "Question?", 500, 200)
    with pytest.raises(ValueError, match="budget_chars"):
        candidate_project_blocks_v2((block,), "Question?", 0, 200)
    with pytest.raises(ValueError, match="max_block_chars"):
        candidate_project_blocks_v2((block,), "Question?", 500, 0)
    assert (
        candidate_project_blocks_v2(
            (),
            "Question?",
            100,
            50,
            min_block_chars=50,
        )
        == ()
    )


def test_future_runner_defaults_to_check_only_and_validates_locks() -> None:
    arguments = live.build_parser().parse_args([])
    assert arguments.check_only is False
    assert arguments.authorize_live_run is False
    live.validate_arguments(arguments)
    validation = live.validate_locked_sources(arguments)
    assert validation["network_requests"] == 0
    assert validation["provider_calls"] == 0
    assert validation["model_calls"] == 0
    assert validation["secrets_bound"] == 0
    assert validation["protocol_publication_authorizes_live"] is False
    assert validation["phase11_9_protocol_may_be_frozen"] is False


@pytest.mark.asyncio
async def test_live_run_refuses_to_start_without_explicit_flag() -> None:
    arguments = live.build_parser().parse_args([])
    with pytest.raises(ValueError, match="explicit --authorize-live-run"):
        await live.run(arguments)


@pytest.mark.asyncio
async def test_future_retrieval_is_fail_fast_and_never_retries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    async def fake_retrieve(
        rows: list[live.phase11_8.BenchmarkRow],
        **_kwargs: object,
    ) -> tuple[
        dict[tuple[str, str], live.phase11_8.ArmBundle],
        dict[str, str],
        list[dict[str, Any]],
        dict[str, int],
        dict[str, Any],
    ]:
        nonlocal calls
        calls += 1
        return (
            {},
            {},
            [
                {
                    "case_id": rows[0].id,
                    "error_kind": "http_429",
                    "provider_failure_kind_counts": {},
                }
            ],
            {
                "case_retrieval_operations": 1,
                "provider_query_calls": 1,
                "tavily_requests": 1,
            },
            {},
        )

    monkeypatch.setattr(live.phase11_8, "retrieve_all", fake_retrieve)
    rows = [
        live.phase11_8.BenchmarkRow(
            id=f"case-{index}",
            question="Synthetic question?",
            answers=("Synthetic marker",),
        )
        for index in range(2)
    ]
    result = await live.retrieve_all_fail_fast(
        rows,
        tavily_api_key="fixture-key",
        cache_root=tmp_path,
        provider_max_results=20,
        selection_limit=20,
        max_per_domain=3,
        request_timeout_seconds=15.0,
        wall_time_seconds=30.0,
        pause_seconds=0.0,
        progress=False,
    )
    assert calls == 1
    assert result[-1] == "http_429"
    assert result[3]["tavily_requests"] == 1


def test_future_decision_separates_retrieval_ceiling_from_projection() -> None:
    passing = _passing_live_decision()
    assert passing["phase11_8_8_projection_candidate_passed"] is True
    assert passing["diagnostic_status"] == "projection_calibration_pass"
    assert passing["phase11_9_protocol_may_be_frozen"] is False
    assert passing["phase12_authorized"] is False
    assert passing["release_decision"] == "no-go"

    metrics = {
        arm: {
            "availability": _ratio(24),
            "answer_key_in_selected_evidence": _ratio(19),
            "answer_key_in_prompt_evidence": _ratio(19),
        }
        for arm in live.PROJECTION_ARMS
    }
    failed = live.build_decision(
        metrics,
        {"net_gain": 2},
        {"net_gain": 2},
        {"numerator": 19, "denominator": 19, "rate": 1.0},
        {
            "shared_packet_identity_passed": True,
            "projection_invariants_passed": True,
        },
        {
            "case_retrieval_operations": 24,
            "provider_query_calls": 24,
            "tavily_requests": 24,
            "other_provider_requests": 0,
            "model_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        {"passed": True},
    )
    assert failed["phase11_8_8_projection_candidate_passed"] is False
    assert failed["diagnostic_status"] == "retrieval_limited_inconclusive"


def test_offline_workflow_has_no_live_job_secret_or_provider_binding() -> None:
    workflow_text = WORKFLOW.read_text()
    parsed = yaml.safe_load(workflow_text)
    assert isinstance(parsed, dict)
    assert parsed["permissions"] == {"contents": "read"}
    assert set(parsed["jobs"]) == {"offline-projection-lock"}
    assert "authorize_live" not in workflow_text.casefold()
    assert "labeled" not in workflow_text.casefold()
    assert "secrets." not in workflow_text
    assert "TAVILY_API_KEY" not in workflow_text
    assert "GEMINI_API_KEY" not in workflow_text
    assert "curl " not in workflow_text
    assert "wget " not in workflow_text
    assert "--check-only" in workflow_text
    assert "persist-credentials: false" in workflow_text


def test_public_result_contains_no_fixture_questions_markers_or_text() -> None:
    fixture = json.loads(FIXTURE.read_bytes())
    report_text = RESULT.read_text()
    for case in fixture["cases"]:
        assert case["question"] not in report_text
        assert case["marker"] not in report_text
        for block in case["blocks"]:
            assert block["title"] not in report_text
            assert block["url"] not in report_text
            source_text = offline._materialize_text(block["text_parts"])
            if source_text.strip():
                assert source_text not in report_text


def test_protocol_freezes_future_ceiling_and_keeps_every_boundary_closed() -> None:
    protocol = PROTOCOL.read_text()
    assert "Tavily requests | 24 | 24" in protocol
    assert "Gemini requests | 0 | 0" in protocol
    assert "selected-packet proxy coverage is at least 20/24" in protocol
    assert "paired net gain of at least +2 against equal-cap" in protocol
    assert "paired net gain of at least +2 against v1" in protocol
    assert "does not authorize a" in protocol
    assert "live calibration" in protocol
    assert "Phase 11.9 or Phase 12" in protocol
    assert "merge" in protocol and "release" in protocol


def test_projected_block_metadata_helper_rejects_reordered_or_changed_data() -> None:
    source = (
        live.phase11_8.EvidenceBlock(
            citation_id="S1",
            title="One",
            url="https://one.example",
            text="one",
            providers=("tavily",),
        ),
        live.phase11_8.EvidenceBlock(
            citation_id="S2",
            title="Two",
            url="https://two.example",
            text="two",
            providers=("tavily",),
        ),
    )
    assert live.projection_metadata_preserved(source, source)
    assert not live.projection_metadata_preserved(source, tuple(reversed(source)))
    assert not live.projection_metadata_preserved(
        source,
        (replace(source[0], title="Changed"),),
    )
    assert live.projection_text_is_source_preserving(
        source,
        (replace(source[0], text=f"o{OMISSION_SEPARATOR}ne"),),
    )
    assert not live.projection_text_is_source_preserving(
        source,
        (replace(source[0], text="invented"),),
    )


def test_no_environment_secret_is_needed_for_check_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    arguments = live.build_parser().parse_args(["--check-only"])
    live.validate_arguments(arguments)
    validation = live.validate_locked_sources(arguments)
    assert validation["tavily_requests"] == 0
    assert validation["gemini_requests"] == 0
    asyncio.run(asyncio.sleep(0))
