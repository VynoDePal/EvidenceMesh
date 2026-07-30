from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

import pytest
from benchmarks.phase11_8_2_candidate import (
    DIRECT_ANSWER_INSUFFICIENT_TEXT,
    DirectAnswerResponseError,
    build_direct_answer_prompt,
    candidate_project_blocks,
    direct_answer_response_schema,
    parse_direct_answer,
    rendered_evidence_chars,
)
from benchmarks.run_phase11_8_2_offline_design import (
    EXPECTED_INVALID_RESPONSES,
    EXPECTED_PROJECTION_CASES,
    EXPECTED_VALID_RESPONSES,
    LOCKED_CANDIDATE_SHA256,
    LOCKED_FIXTURE_SHA256,
    LOCKED_PHASE11_8_1_DIAGNOSTIC_SHA256,
    LOCKED_PHASE11_8_RESULT_SHA256,
    LOCKED_PROTOCOL_SHA256,
    OfflineBlock,
    _projection_outcomes,
    _structured_outcomes,
    balanced_baseline_project_blocks,
    build_report,
    run,
)

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/benchmark-protocol-v17.md"
FIXTURES = ROOT / "benchmarks/data/phase11_8_2_offline_fixtures_v1.json"
CANDIDATE = ROOT / "benchmarks/phase11_8_2_candidate.py"
RESULT = ROOT / "benchmarks/results/phase11_8_2_offline_design_2026-07-30.json"
PHASE11_8_RESULT = ROOT / "benchmarks/results/phase11_8_recovery_2026-07-29.json"
PHASE11_8_1_RESULT = ROOT / "benchmarks/results/phase11_8_1_offline_diagnostic_2026-07-30.json"
WORKFLOW = ROOT / ".github/workflows/phase11-8-2-offline-design.yml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixtures() -> dict[str, object]:
    return json.loads(FIXTURES.read_bytes())


def _offline_report() -> dict[str, object]:
    return build_report(
        protocol_raw=PROTOCOL.read_bytes(),
        fixture_raw=FIXTURES.read_bytes(),
        candidate_raw=CANDIDATE.read_bytes(),
        phase11_8_source_sha256=LOCKED_PHASE11_8_RESULT_SHA256,
        phase11_8_decision={
            "release_decision": "no-go",
            "phase11_8_candidate_passed": False,
            "phase12_executed": False,
        },
        phase11_8_1_source_sha256=LOCKED_PHASE11_8_1_DIAGNOSTIC_SHA256,
        phase11_8_1_decision={"historical_phase11_8_result_changed": False},
    )


def _block(
    citation_id: str,
    text: str,
    *,
    title: str = "Synthetic title",
    url: str = "https://example.test/source",
    providers: tuple[str, ...] = ("tavily",),
) -> OfflineBlock:
    return OfflineBlock(citation_id, title, url, text, providers)


def test_locked_sources_and_offline_artifacts_are_exact() -> None:
    assert _sha256(PROTOCOL) == LOCKED_PROTOCOL_SHA256
    assert _sha256(FIXTURES) == LOCKED_FIXTURE_SHA256
    assert _sha256(CANDIDATE) == LOCKED_CANDIDATE_SHA256
    assert _sha256(PHASE11_8_RESULT) == LOCKED_PHASE11_8_RESULT_SHA256
    assert _sha256(PHASE11_8_1_RESULT) == LOCKED_PHASE11_8_1_DIAGNOSTIC_SHA256


def test_committed_report_is_exact_runner_recomputation() -> None:
    expected = json.loads(RESULT.read_bytes())
    actual = run(
        protocol_path=PROTOCOL,
        fixture_path=FIXTURES,
        candidate_path=CANDIDATE,
        phase11_8_result_path=PHASE11_8_RESULT,
        phase11_8_1_diagnostic_path=PHASE11_8_1_RESULT,
    )
    assert actual == expected


def test_baseline_is_an_exact_clone_of_phase11_8_projection() -> None:
    from benchmarks.run_phase11_5_quality_recovery import (
        EvidenceBlock,
        _balanced_candidate_projection,
    )

    blocks = tuple(
        EvidenceBlock(
            citation_id=f"S{index}",
            title=f"Source {index}",
            url=f"https://source-{index}.example/item",
            text=f"Evidence {index}. " + ("context " * (20 + index)),
            providers=("tavily",) if index not in {3, 7} else ("community",),
        )
        for index in range(1, 10)
    )
    assert balanced_baseline_project_blocks(
        blocks,
        1_000,
        240,
    ) == _balanced_candidate_projection(blocks, 1_000, 240)


def test_authored_projection_cases_pass_only_engineering_invariants() -> None:
    fixtures = _fixtures()
    outcomes = _projection_outcomes(fixtures)
    assert len(outcomes) == EXPECTED_PROJECTION_CASES
    assert sum(row["baseline_retained_sentinel"] for row in outcomes) == 1
    assert sum(row["candidate_retained_sentinel"] for row in outcomes) == 12
    assert all(row["budget_compliant"] for row in outcomes)
    assert all(row["deterministic_three_replays"] for row in outcomes)
    assert all(row["metadata_preserved"] for row in outcomes)
    assert all(row["expected_source_in_candidate"] for row in outcomes)
    assert fixtures["authored_after_phase11_8"] is True
    assert fixtures["predictive_quality_claim_allowed"] is False


def test_candidate_projector_is_answer_blind_by_interface_and_source() -> None:
    parameters = set(inspect.signature(candidate_project_blocks).parameters)
    assert parameters == {
        "blocks",
        "question",
        "budget_chars",
        "max_block_chars",
        "min_block_chars",
    }
    tree = ast.parse(inspect.getsource(candidate_project_blocks))
    identifiers = {node.id.casefold() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert identifiers.isdisjoint({"answer", "sentinel", "reference_answer"})


def test_candidate_obeys_exact_rendered_budget_and_preserves_metadata() -> None:
    blocks = (
        _block("S1", "alpha " * 900, title="A" * 80),
        _block(
            "S2",
            ("background " * 250) + "Orion answer marker. " + ("tail " * 250),
            providers=("community",),
        ),
        _block("S3", "gamma " * 900),
    )
    projected = candidate_project_blocks(
        blocks,
        "Where is the Orion marker?",
        540,
        1_000,
        min_block_chars=64,
    )
    assert rendered_evidence_chars(projected) <= 540
    assert projected
    by_id = {block.citation_id: block for block in blocks}
    assert all(
        (block.title, block.url, block.providers)
        == (
            by_id[block.citation_id].title,
            by_id[block.citation_id].url,
            by_id[block.citation_id].providers,
        )
        for block in projected
    )


def test_candidate_handles_empty_and_header_only_budgets_deterministically() -> None:
    whitespace = _block("S1", "   ")
    long_header = _block(
        "S2",
        "useful evidence",
        title="T" * 300,
        url="https://example.test/" + "x" * 300,
    )
    assert (
        candidate_project_blocks(
            (whitespace,),
            "Question?",
            100,
            50,
            min_block_chars=20,
        )
        == ()
    )
    assert (
        candidate_project_blocks(
            (long_header,),
            "Question?",
            64,
            50,
            min_block_chars=20,
        )
        == ()
    )
    first = candidate_project_blocks(
        (long_header,),
        "Question?",
        800,
        50,
        min_block_chars=20,
    )
    second = candidate_project_blocks(
        (long_header,),
        "Question?",
        800,
        50,
        min_block_chars=20,
    )
    assert first == second
    assert rendered_evidence_chars(first) <= 800


@pytest.mark.parametrize(
    ("budget", "maximum", "minimum"),
    [
        (0, 100, 20),
        (-1, 100, 20),
        (100, 0, 20),
        (100, -1, 20),
        (100, 100, 0),
        (100, 20, 21),
    ],
)
def test_candidate_rejects_invalid_budget_configuration(
    budget: int,
    maximum: int,
    minimum: int,
) -> None:
    with pytest.raises(ValueError):
        candidate_project_blocks(
            (_block("S1", "evidence"),),
            "Question?",
            budget,
            maximum,
            min_block_chars=minimum,
        )


def test_candidate_rejects_duplicate_retained_citation_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        candidate_project_blocks(
            (_block("S1", "first"), _block("S1", "second")),
            "Question?",
            400,
            100,
            min_block_chars=20,
        )


def test_direct_answer_schema_is_minimal_and_closed() -> None:
    schema = direct_answer_response_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["answer", "citation_ids"]
    assert set(schema["properties"]) == {"answer", "citation_ids"}


def test_all_locked_direct_answer_contract_cases_are_categorical() -> None:
    structured = _structured_outcomes(_fixtures())
    assert structured["valid_accepted"] == EXPECTED_VALID_RESPONSES
    assert structured["invalid_rejected"] == EXPECTED_INVALID_RESPONSES
    assert all(row["rendered_matches"] for row in structured["valid_cases"])
    assert all(row["rejected"] for row in structured["invalid_cases"])


def test_direct_answer_contract_enforces_allowed_ids_and_insufficient_form() -> None:
    assert (
        parse_direct_answer(
            '{"answer":"42","citation_ids":["S1"]}',
            allowed_ids=frozenset({"S1"}),
        )
        == "42 [S1]"
    )
    assert (
        parse_direct_answer(
            json.dumps({"answer": DIRECT_ANSWER_INSUFFICIENT_TEXT, "citation_ids": []}),
            allowed_ids=frozenset({"S1"}),
        )
        == DIRECT_ANSWER_INSUFFICIENT_TEXT
    )
    with pytest.raises(DirectAnswerResponseError):
        parse_direct_answer(
            '{"answer":"42","citation_ids":["S2"]}',
            allowed_ids=frozenset({"S1"}),
        )


def test_direct_answer_prompt_exposes_only_packet_citation_ids() -> None:
    blocks = (_block("S1", "The supported value is 42."),)
    system_prompt, user_prompt = build_direct_answer_prompt("What is the value?", blocks)
    assert "claims" not in system_prompt
    assert "[S1]" in user_prompt
    assert "[S2]" not in user_prompt
    assert "Allowed citation identifiers" in user_prompt
    assert '"answer"' in user_prompt
    assert '"citation_ids"' in user_prompt


def test_candidate_and_runner_have_no_network_dependency_imports() -> None:
    forbidden = {
        "aiohttp",
        "google",
        "httpx",
        "requests",
        "socket",
        "tavily",
        "urllib",
    }
    imported: set[str] = set()
    for path in (CANDIDATE, ROOT / "benchmarks/run_phase11_8_2_offline_design.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", maxsplit=1)[0])
    assert imported.isdisjoint(forbidden)


def test_workflow_has_no_live_job_or_secret_binding() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" not in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" not in workflow
    assert "${{ secrets." not in workflow
    assert "phase11-8-3" not in workflow.casefold()


def test_report_preserves_no_go_and_all_authorization_boundaries() -> None:
    report = _offline_report()
    assert len(report["gates"]) == 12
    assert all(gate["passed"] for gate in report["gates"].values())
    decision = report["decision"]
    assert decision["offline_engineering_candidate_passed"] is True
    assert decision["real_case_quality_improvement_proven"] is False
    assert decision["historical_phase11_8_result_changed"] is False
    assert decision["phase11_8_3_live_calibration_authorized"] is False
    assert decision["phase11_9_authorized"] is False
    assert decision["phase12_executed"] is False
    assert decision["phase12_authorized"] is False
    assert decision["quality_profile_promotion_allowed"] is False
    assert decision["merge_allowed"] is False
    assert decision["release_allowed"] is False
    assert decision["superiority_claim_allowed"] is False
    assert decision["release_decision"] == "no-go"


def test_report_is_privacy_safe_and_contains_no_synthetic_payload() -> None:
    fixtures = _fixtures()
    rendered = json.dumps(_offline_report(), ensure_ascii=False)
    for case in fixtures["projection_cases"]:
        assert case["question"] not in rendered
        assert case["sentinel"] not in rendered
    assert "EVIDENCE_MESH_TAVILY_KEY" not in rendered
    assert "EVIDENCE_MESH_GEMINI_KEY" not in rendered
    assert '"network_requests": 0' in rendered
    assert '"provider_calls": 0' in rendered
    assert '"model_calls": 0' in rendered
