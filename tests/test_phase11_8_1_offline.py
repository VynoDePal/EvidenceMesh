from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from benchmarks.analyze_phase11_8_1_offline import (
    SOURCE_RESULT_SHA256,
    build_report,
    sha256_bytes,
)
from benchmarks.run_end_to_end_phase10 import EvidenceBlock
from benchmarks.run_phase11_5_quality_recovery import (
    _balanced_candidate_projection,
    _legacy_projection,
)
from benchmarks.run_phase11_8_recovery import (
    StructuredResponseError,
    parse_structured_answer,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RESULT = REPOSITORY_ROOT / "benchmarks" / "results" / "phase11_8_recovery_2026-07-29.json"
DIAGNOSTIC_RESULT = (
    REPOSITORY_ROOT / "benchmarks" / "results" / "phase11_8_1_offline_diagnostic_2026-07-30.json"
)
ANALYZER = REPOSITORY_ROOT / "benchmarks" / "analyze_phase11_8_1_offline.py"


def test_committed_diagnostic_is_exactly_reproducible() -> None:
    raw = SOURCE_RESULT.read_bytes()
    assert sha256_bytes(raw) == SOURCE_RESULT_SHA256

    source = json.loads(raw)
    recomputed = build_report(source, source_sha256=sha256_bytes(raw))
    committed = json.loads(DIAGNOSTIC_RESULT.read_bytes())

    assert recomputed == committed
    assert committed["historical_gate_classification"]["historical_passed"] == 5
    assert committed["historical_gate_classification"]["historical_failed"] == 7
    assert committed["decision"]["release_decision"] == "no-go"
    assert committed["decision"]["historical_phase11_8_result_changed"] is False


def test_diagnostic_separates_projection_from_retrieval_selection() -> None:
    raw = SOURCE_RESULT.read_bytes()
    report = build_report(json.loads(raw), source_sha256=sha256_bytes(raw))
    projection = report["projection_diagnostic"]

    assert projection["expanded_selected_answer_proxy_hits"] == 21
    assert projection["expanded_prompt_answer_proxy_hits"] == 18
    assert projection["selected_to_prompt_losses"] == 3
    assert projection["selected_to_prompt_gains"] == 0
    assert projection["expanded_vs_current_prompt_pairs"]["net_gain"] == -2


def test_diagnostic_separates_native_availability_from_schema_rejection() -> None:
    raw = SOURCE_RESULT.read_bytes()
    report = build_report(json.loads(raw), source_sha256=sha256_bytes(raw))
    availability = report["provider_model_availability"]
    schema = availability["structured_schema_accounting"]

    assert availability["errors_all_arms"] == {
        "generation_wall_timeout": 8,
        "http_503": 22,
        "response_schema_failure": 2,
    }
    assert availability["all_http_503_attributed_to_gemma_4_31b"] is True
    assert availability["completion_floor_deficit_total"] == 26
    assert schema == {
        "attempts": 48,
        "native_request_completed": 38,
        "schema_valid": 36,
        "unavailable_before_schema_validation": 10,
        "native_schema_rejections": 2,
        "schema_valid_given_native": {
            "numerator": 36,
            "denominator": 38,
            "rate": 0.947368,
        },
    }


def test_completed_pair_view_does_not_replace_historical_end_to_end_gate() -> None:
    raw = SOURCE_RESULT.read_bytes()
    report = build_report(json.loads(raw), source_sha256=sha256_bytes(raw))
    structured = report["structured_contract_diagnostic"]

    assert structured["answer_vs_expanded_all_attempts"]["net_gain"] == -4
    assert structured["answer_vs_expanded_completed_pairs"]["net_gain"] == -3
    assert structured["citation_support_vs_expanded_all_attempts"]["net_gain"] == 3
    assert structured["citation_support_vs_expanded_completed_pairs"]["net_gain"] == 4
    assert report["historical_gate_classification"]["historical_gates_unchanged"] is True


def test_balanced_projection_fixture_exposes_equal_truncation_boundary() -> None:
    sentinel = "ANSWER_KEY_SENTINEL"
    blocks = (
        EvidenceBlock(
            citation_id="S1",
            title="Primary",
            url="https://primary.example/a",
            text=("a" * 250) + sentinel + ("z" * 40),
            providers=("tavily",),
        ),
        EvidenceBlock(
            citation_id="S2",
            title="Secondary",
            url="https://secondary.example/b",
            text="b" * 400,
            providers=("tavily",),
        ),
    )

    legacy = _legacy_projection(blocks, 500)
    balanced = _balanced_candidate_projection(blocks, 500, 1_000)

    assert sentinel in "".join(block.text for block in blocks)
    assert sentinel in "".join(block.text for block in legacy)
    assert sentinel not in "".join(block.text for block in balanced)
    assert blocks[0].text.endswith("z" * 40)


def test_structured_parser_accepts_only_the_locked_exact_contract() -> None:
    rendered, claim_count = parse_structured_answer(
        '{"claims":[{"text":"Verified fact.","citation_ids":["S1","S2"]}]}'
    )
    assert rendered == "Verified fact. [S1] [S2]"
    assert claim_count == 1

    insufficient, insufficient_count = parse_structured_answer(
        '{"claims":[{"text":"Insufficient evidence.","citation_ids":[]}]}'
    )
    assert insufficient == "Insufficient evidence."
    assert insufficient_count == 1


@pytest.mark.parametrize(
    "raw_answer",
    [
        '{"claims":[]}',
        '{"claims":[{"text":"Fact [S1]","citation_ids":["S1"]}]}',
        '{"claims":[{"text":"Fact.","citation_ids":[]}]}',
        '{"claims":[{"text":"Fact.","citation_ids":["S1","S1"]}]}',
        '{"claims":[{"text":"Fact.","citation_ids":["[S1]"]}]}',
        '{"claims":[{"text":"Fact.","citation_ids":["S1"],"extra":true}]}',
        '{"claims":[{"text":"Fact.","citation_ids":["S1"]}],"extra":true}',
    ],
)
def test_structured_parser_rejects_adversarial_contracts(raw_answer: str) -> None:
    with pytest.raises(StructuredResponseError, match="response_schema_failure"):
        parse_structured_answer(raw_answer)


def test_analyzer_has_no_network_dependency_or_secret_input() -> None:
    module = ast.parse(ANALYZER.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])

    assert imported_roots.isdisjoint({"aiohttp", "httpx", "requests", "socket", "urllib"})
    source = ANALYZER.read_text(encoding="utf-8")
    assert "EVIDENCE_MESH_GEMINI_KEY" not in source
    assert "EVIDENCE_MESH_TAVILY_KEY" not in source

    raw = SOURCE_RESULT.read_bytes()
    report = build_report(json.loads(raw), source_sha256=sha256_bytes(raw))
    assert report["execution_boundary"] == {
        "network_access": False,
        "provider_or_model_calls": False,
        "tavily_requests": 0,
        "gemini_requests": 0,
        "phase12_accessed": False,
        "product_configuration_changed": False,
    }
