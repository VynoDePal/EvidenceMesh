from __future__ import annotations

import ast
import hashlib
import inspect
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import run_phase11_8_3_factorial as phase11_8_3

ROOT = Path(__file__).parents[1]
if not (ROOT / "pyproject.toml").is_file():
    ROOT = Path(__file__).parent
PROTOCOL = ROOT / "docs/benchmark-protocol-v18.md"
if not PROTOCOL.is_file():
    PROTOCOL = ROOT / "benchmark-protocol-v18.md"
WORKFLOW = ROOT / ".github/workflows/phase11-8-3-factorial-calibration.yml"
if not WORKFLOW.is_file():
    WORKFLOW = ROOT / "phase11-8-3-factorial-calibration.yml"


def _row(case_id: str = "case-1") -> phase11_8_3.phase11_8.BenchmarkRow:
    return phase11_8_3.phase11_8.BenchmarkRow(
        id=case_id,
        question="What is the answer marker?",
        answers=("42",),
        topic="Other",
        answer_type="Number",
    )


def _blocks(count: int = 20) -> tuple[phase11_8_3.phase11_8.EvidenceBlock, ...]:
    return tuple(
        phase11_8_3.phase11_8.EvidenceBlock(
            citation_id=f"S{index}",
            title=f"Source {index}",
            url=f"https://source-{index}.example/item",
            text=(
                ("The supported answer marker is 42. " if index == 16 else "")
                + f"Evidence block {index}. "
                + ("Context " * (80 + index))
            ),
            providers=("tavily",),
        )
        for index in range(1, count + 1)
    )


def _bundle(arm: str) -> phase11_8_3.phase11_8.ArmBundle:
    return phase11_8_3.phase11_8.ArmBundle(
        case_id="case-1",
        arm=arm,
        status="completed",
        blocks=_blocks(),
        raw_result_count=20,
        fused_result_count=20,
        selected_result_count=20,
        unique_domains=20,
        selected_tavily_count=20,
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


def _synthetic_retrieval_outcomes() -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for case_index in range(phase11_8_3.EXPECTED_CASE_COUNT):
        for arm in phase11_8_3.GENERATION_ARMS:
            candidate_projection = arm in {
                phase11_8_3.CANDIDATE_CLAIMS_ARM,
                phase11_8_3.CANDIDATE_DIRECT_ARM,
            }
            outcomes.append(
                {
                    "case_id": f"case-{case_index + 1}",
                    "arm": arm,
                    "status": "completed",
                    "available": True,
                    "raw_result_count": 20,
                    "fused_result_count": 20,
                    "selected_result_count": 20,
                    "prompt_result_count": 20,
                    "unique_domains": 8,
                    "selected_tavily_count": 20,
                    "prompt_tavily_count": 20,
                    "answer_key_in_selected_evidence": case_index < 20,
                    "answer_key_in_prompt_evidence": (
                        case_index < (20 if candidate_projection else 18)
                    ),
                    "raw_pool_sha256": f"raw-{case_index}",
                    "selected_packet_sha256": f"selected-{case_index}",
                    "prompt_packet_sha256": (
                        f"candidate-{case_index}" if candidate_projection else f"equal-{case_index}"
                    ),
                    "rendered_evidence_chars": 11_900,
                    "exact_budget_compliant": True if candidate_projection else None,
                    "deterministic_three_replays": True if candidate_projection else None,
                    "retrieval_latency_ms": 10.0,
                    "error_kind": None,
                }
            )
    return outcomes


def _synthetic_generation_outcomes() -> list[dict[str, Any]]:
    answer_limits = {
        phase11_8_3.EQUAL_CLAIMS_ARM: 18,
        phase11_8_3.CANDIDATE_CLAIMS_ARM: 19,
        phase11_8_3.EQUAL_DIRECT_ARM: 19,
        phase11_8_3.CANDIDATE_DIRECT_ARM: 21,
    }
    outcomes: list[dict[str, Any]] = []
    for case_index in range(phase11_8_3.EXPECTED_CASE_COUNT):
        for arm in phase11_8_3.GENERATION_ARMS:
            direct = phase11_8_3.contract_family(arm) == "direct_answer_json"
            outcomes.append(
                {
                    "case_id": f"case-{case_index + 1}",
                    "arm": arm,
                    "model": phase11_8_3.MODEL,
                    "status": "completed",
                    "native_request_completed": True,
                    "structured_schema_valid": True,
                    "structured_claim_count": 1,
                    "answer_key_covered": case_index < answer_limits[arm],
                    "citation_count": 1,
                    "citation_ids_valid": True,
                    "citation_contract_passed": True,
                    "citation_support_proxy": (
                        case_index
                        < (20 if arm == phase11_8_3.CANDIDATE_DIRECT_ARM else answer_limits[arm])
                    ),
                    "prompt_evidence_count": 20,
                    "generation_latency_ms": 10.0,
                    "usage": {},
                    "error_kind": None,
                    "contract_is_direct": direct,
                }
            )
    return outcomes


def _passing_decision() -> dict[str, Any]:
    retrieval = _synthetic_retrieval_outcomes()
    generation = _synthetic_generation_outcomes()
    retrieval_metrics = phase11_8_3.aggregate_retrieval(retrieval)
    generation_metrics = phase11_8_3.aggregate_generation(generation)
    prompt_paired = phase11_8_3.paired_retrieval_metrics(
        retrieval,
        field="answer_key_in_prompt_evidence",
        candidate_arm=phase11_8_3.CANDIDATE_CLAIMS_ARM,
        baseline_arm=phase11_8_3.EQUAL_CLAIMS_ARM,
    )
    comparisons = {
        "joint_all": (
            phase11_8_3.CANDIDATE_DIRECT_ARM,
            phase11_8_3.EQUAL_CLAIMS_ARM,
            False,
        ),
        "joint_completed": (
            phase11_8_3.CANDIDATE_DIRECT_ARM,
            phase11_8_3.EQUAL_CLAIMS_ARM,
            True,
        ),
        "projection_claims": (
            phase11_8_3.CANDIDATE_CLAIMS_ARM,
            phase11_8_3.EQUAL_CLAIMS_ARM,
            True,
        ),
        "projection_direct": (
            phase11_8_3.CANDIDATE_DIRECT_ARM,
            phase11_8_3.EQUAL_DIRECT_ARM,
            True,
        ),
        "contract_equal": (
            phase11_8_3.EQUAL_DIRECT_ARM,
            phase11_8_3.EQUAL_CLAIMS_ARM,
            True,
        ),
        "contract_candidate": (
            phase11_8_3.CANDIDATE_DIRECT_ARM,
            phase11_8_3.CANDIDATE_CLAIMS_ARM,
            True,
        ),
    }
    answer_pairs = {
        name: phase11_8_3.paired_generation_metrics(
            generation,
            field="answer_key_covered",
            candidate_arm=candidate_arm,
            baseline_arm=baseline_arm,
            completed_only=completed_only,
        )
        for name, (candidate_arm, baseline_arm, completed_only) in comparisons.items()
    }
    support_paired = phase11_8_3.paired_generation_metrics(
        generation,
        field="citation_support_proxy",
        candidate_arm=phase11_8_3.CANDIDATE_DIRECT_ARM,
        baseline_arm=phase11_8_3.EQUAL_CLAIMS_ARM,
        completed_only=True,
    )
    return phase11_8_3.build_decision(
        retrieval_metrics,
        generation_metrics,
        prompt_paired,
        answer_pairs,
        support_paired,
        phase11_8_3.packet_identity(retrieval),
        retrieval_operations=phase11_8_3.EXPECTED_RETRIEVAL_OPERATIONS,
        generation_requests=phase11_8_3.EXPECTED_GENERATION_REQUESTS,
        tavily_requests=phase11_8_3.EXPECTED_TAVILY_REQUESTS,
    )


def test_protocol_and_budget_locks_are_exact() -> None:
    assert hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() == (phase11_8_3.LOCKED_PROTOCOL_SHA256)
    assert phase11_8_3.MODELS == ("gemini-3.5-flash-lite",)
    assert phase11_8_3.EXPECTED_CASE_COUNT == 24
    assert phase11_8_3.EXPECTED_RETRIEVAL_OPERATIONS == 24
    assert phase11_8_3.EXPECTED_TAVILY_REQUESTS == 24
    assert phase11_8_3.EXPECTED_GENERATION_REQUESTS == 96


def test_factorial_arm_mapping_is_exact_and_closed() -> None:
    assert {
        arm: (
            phase11_8_3.projection_family(arm),
            phase11_8_3.contract_family(arm),
        )
        for arm in phase11_8_3.GENERATION_ARMS
    } == {
        "equal_claims": ("equal_cap", "claims_json"),
        "candidate_claims": ("rank_weighted_query_window_head_tail_v1", "claims_json"),
        "equal_direct": ("equal_cap", "direct_answer_json"),
        "candidate_direct": (
            "rank_weighted_query_window_head_tail_v1",
            "direct_answer_json",
        ),
    }
    with pytest.raises(ValueError):
        phase11_8_3.projection_family("unknown")
    with pytest.raises(ValueError):
        phase11_8_3.contract_family("unknown")


def test_equal_claims_is_an_exact_phase11_8_control_clone() -> None:
    row = _row()
    current_bundle = _bundle(phase11_8_3.EQUAL_CLAIMS_ARM)
    actual = phase11_8_3.build_prompt(
        row,
        current_bundle,
        evidence_budget_chars=12_000,
        max_block_chars=1_500,
        min_block_chars=192,
    )
    historical = phase11_8_3.phase11_8.build_prompt(
        row,
        replace(current_bundle, arm=phase11_8_3.phase11_8.CANDIDATE_ARM),
        evidence_budget_chars=12_000,
        expanded_max_block_chars=1_500,
    )
    assert actual == historical


def test_only_one_factor_changes_in_each_factorial_comparison() -> None:
    row = _row()
    prompts = {
        arm: phase11_8_3.build_prompt(
            row,
            _bundle(arm),
            evidence_budget_chars=12_000,
            max_block_chars=1_500,
            min_block_chars=192,
        )
        for arm in phase11_8_3.GENERATION_ARMS
    }
    assert prompts["equal_claims"][2] == prompts["equal_direct"][2]
    assert prompts["candidate_claims"][2] == prompts["candidate_direct"][2]
    assert prompts["equal_claims"][2] != prompts["candidate_claims"][2]
    assert prompts["equal_claims"][:2] != prompts["equal_direct"][:2]
    assert prompts["candidate_claims"][:2] != prompts["candidate_direct"][:2]


def test_candidate_projector_stays_answer_blind_and_budget_bounded() -> None:
    parameters = set(inspect.signature(phase11_8_3.candidate_project_blocks).parameters)
    assert parameters == {
        "blocks",
        "question",
        "budget_chars",
        "max_block_chars",
        "min_block_chars",
    }
    tree = ast.parse(inspect.getsource(phase11_8_3.candidate_project_blocks))
    identifiers = {node.id.casefold() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert identifiers.isdisjoint({"answer", "sentinel", "reference_answer"})
    projected = phase11_8_3.project_blocks(
        _row(),
        _bundle(phase11_8_3.CANDIDATE_DIRECT_ARM),
        evidence_budget_chars=2_000,
        max_block_chars=600,
        min_block_chars=96,
    )
    assert phase11_8_3.rendered_evidence_chars(projected) <= 2_000


def test_contract_parsers_are_strict_and_direct_ids_are_membership_checked() -> None:
    claims = '{"claims":[{"text":"42","citation_ids":["S1"]}]}'
    direct = '{"answer":"42","citation_ids":["S1"]}'
    assert phase11_8_3.parse_contract_response(
        claims,
        arm=phase11_8_3.EQUAL_CLAIMS_ARM,
        allowed_ids=frozenset({"S1"}),
    ) == ("42 [S1]", 1)
    assert phase11_8_3.parse_contract_response(
        direct,
        arm=phase11_8_3.CANDIDATE_DIRECT_ARM,
        allowed_ids=frozenset({"S1"}),
    ) == ("42 [S1]", 1)
    with pytest.raises(phase11_8_3.DirectAnswerResponseError):
        phase11_8_3.parse_contract_response(
            '{"answer":"42","citation_ids":["S2"]}',
            arm=phase11_8_3.CANDIDATE_DIRECT_ARM,
            allowed_ids=frozenset({"S1"}),
        )
    with pytest.raises(phase11_8_3.DirectAnswerResponseError):
        phase11_8_3.parse_contract_response(
            "```json\n" + direct + "\n```",
            arm=phase11_8_3.CANDIDATE_DIRECT_ARM,
            allowed_ids=frozenset({"S1"}),
        )


@pytest.mark.asyncio
async def test_generation_uses_one_native_request_and_publishes_only_safe_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_count = 0

    async def fake_completion(
        _client: object,
        **kwargs: Any,
    ) -> SimpleNamespace:
        nonlocal request_count
        request_count += 1
        assert kwargs["model"] == phase11_8_3.MODEL
        assert kwargs["max_output_tokens"] == 2_048
        return SimpleNamespace(
            answer='{"answer":"42","citation_ids":["S16"]}',
            response_model=phase11_8_3.MODEL,
            finish_reason="STOP",
            usage={"totalTokenCount": 10},
        )

    monkeypatch.setattr(
        phase11_8_3.phase11_8,
        "request_gemini_completion",
        fake_completion,
    )
    outcome = await phase11_8_3.generate_outcome(
        _row(),
        _bundle(phase11_8_3.CANDIDATE_DIRECT_ARM),
        client=object(),  # type: ignore[arg-type]
        api_key="test-key",
        model=phase11_8_3.MODEL,
        evidence_budget_chars=12_000,
        max_block_chars=1_500,
        min_block_chars=192,
        max_output_tokens=2_048,
        wall_time_seconds=1.0,
    )
    assert request_count == 1
    assert outcome["status"] == "completed"
    assert outcome["answer_key_covered"] is True
    assert outcome["citation_ids_valid"] is True
    assert outcome["citation_support_proxy"] is True
    assert "answer" not in outcome
    assert "system_prompt" not in outcome
    assert "user_prompt" not in outcome
    assert "raw_response" not in outcome


def test_packet_identity_proves_shared_provider_and_projection_packets() -> None:
    identity = phase11_8_3.packet_identity(_synthetic_retrieval_outcomes())
    assert identity["denominator"] == 24
    assert identity["raw_and_selected_passed"] is True
    assert identity["projection_contract_identity_passed"] is True
    assert identity["raw_pool_matching_cases"] == 24
    assert identity["selected_packet_matching_cases"] == 24


def test_all_fourteen_gates_pass_only_the_next_protocol_boundary() -> None:
    decision = _passing_decision()
    assert len(decision["gates"]) == 14
    assert all(gate["passed"] is True for gate in decision["gates"].values())
    assert decision["phase11_8_3_candidate_passed"] is True
    assert decision["phase11_9_protocol_may_be_frozen"] is True
    assert decision["phase11_9_executed"] is False
    assert decision["phase12_authorized"] is False
    assert decision["phase12_executed"] is False
    assert decision["quality_profile_promoted"] is False
    assert decision["superiority_claim_allowed"] is False
    assert decision["merge_allowed"] is False
    assert decision["release_allowed"] is False
    assert decision["release_decision"] == "no-go"


@pytest.mark.parametrize(
    ("gate", "traffic"),
    [
        (
            "locked_inputs_and_exact_traffic",
            {
                "retrieval_operations": 23,
                "generation_requests": 96,
                "tavily_requests": 24,
            },
        ),
        (
            "locked_inputs_and_exact_traffic",
            {
                "retrieval_operations": 24,
                "generation_requests": 95,
                "tavily_requests": 24,
            },
        ),
        (
            "locked_inputs_and_exact_traffic",
            {
                "retrieval_operations": 24,
                "generation_requests": 96,
                "tavily_requests": 25,
            },
        ),
    ],
)
def test_exact_traffic_gate_is_fail_closed(
    gate: str,
    traffic: dict[str, int],
) -> None:
    retrieval = _synthetic_retrieval_outcomes()
    generation = _synthetic_generation_outcomes()
    retrieval_metrics = phase11_8_3.aggregate_retrieval(retrieval)
    generation_metrics = phase11_8_3.aggregate_generation(generation)
    prompt_paired = phase11_8_3.paired_retrieval_metrics(
        retrieval,
        field="answer_key_in_prompt_evidence",
        candidate_arm=phase11_8_3.CANDIDATE_CLAIMS_ARM,
        baseline_arm=phase11_8_3.EQUAL_CLAIMS_ARM,
    )
    all_attempts = phase11_8_3.paired_generation_metrics(
        generation,
        field="answer_key_covered",
        candidate_arm=phase11_8_3.CANDIDATE_DIRECT_ARM,
        baseline_arm=phase11_8_3.EQUAL_CLAIMS_ARM,
        completed_only=False,
    )
    completed = {
        **all_attempts,
        "conditioning": "both_completed",
    }
    answer_pairs = dict.fromkeys(
        (
            "joint_completed",
            "projection_claims",
            "projection_direct",
            "contract_equal",
            "contract_candidate",
        ),
        completed,
    )
    answer_pairs["joint_all"] = all_attempts
    support_paired = phase11_8_3.paired_generation_metrics(
        generation,
        field="citation_support_proxy",
        candidate_arm=phase11_8_3.CANDIDATE_DIRECT_ARM,
        baseline_arm=phase11_8_3.EQUAL_CLAIMS_ARM,
        completed_only=True,
    )
    decision = phase11_8_3.build_decision(
        retrieval_metrics,
        generation_metrics,
        prompt_paired,
        answer_pairs,
        support_paired,
        phase11_8_3.packet_identity(retrieval),
        **traffic,
    )
    assert decision["gates"][gate]["passed"] is False
    assert decision["phase11_8_3_candidate_passed"] is False


def test_locked_arguments_refuse_model_budget_or_live_path_drift() -> None:
    parser = phase11_8_3.build_parser()
    check_only = parser.parse_args(["--check-only"])
    phase11_8_3.validate_arguments(check_only)
    changed_model = parser.parse_args(["--check-only", "--models", "other-model"])
    with pytest.raises(ValueError, match="exact model order"):
        phase11_8_3.validate_arguments(changed_model)
    changed_budget = parser.parse_args(["--check-only", "--evidence-budget-chars", "11999"])
    with pytest.raises(ValueError, match="locked arguments changed"):
        phase11_8_3.validate_arguments(changed_budget)
    live_without_paths = parser.parse_args([])
    with pytest.raises(ValueError, match="--dataset and --output"):
        phase11_8_3.validate_arguments(live_without_paths)


def test_workflow_is_offline_by_default_and_secrets_are_live_job_scoped() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "authorize_live_run" in workflow
    assert "default: false" in workflow
    assert "phase11.8.3-live-authorized" in workflow
    assert "pull_request.head.repo.full_name == github.repository" in workflow
    assert "python benchmarks/run_phase11_8_3_factorial.py --check-only" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" in workflow
    lock_job = workflow.split("lock-validation:", 1)[1].split("live-factorial-calibration:", 1)[0]
    assert "EVIDENCE_MESH_TAVILY_KEY" not in lock_job
    assert "EVIDENCE_MESH_GEMINI_KEY" not in lock_job
    assert "workflow_run:" not in workflow
    assert "schedule:" not in workflow
    assert 'traffic["retries"] == 0' in workflow
    assert 'traffic["fallback_requests"] == 0' in workflow
    assert 'traffic["repair_requests"] == 0' in workflow


def test_protocol_keeps_privacy_and_authorization_boundaries_explicit() -> None:
    protocol = PROTOCOL.read_text(encoding="utf-8")
    for forbidden_output in (
        "questions",
        "reference answers",
        "source titles",
        "URLs",
        "snippets",
        "generated text",
        "prompts",
        "credentials",
        "Phase 12 reserved identifiers",
    ):
        assert forbidden_output in protocol
    assert "Publishing this protocol must not add that label or dispatch the live job." in protocol
    assert "Phase 12 remains sealed and unexecuted" in protocol
    assert "merge, release, public-alpha and superiority claims remain blocked" in protocol


def test_source_has_no_retry_fallback_repair_or_response_publication() -> None:
    source = inspect.getsource(phase11_8_3)
    tree = ast.parse(source)
    function_calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert function_calls.isdisjoint({"sleep", "retry", "backoff"})
    report_keys = {
        key.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    assert "question" not in report_keys
    assert "reference_answer" not in report_keys
    assert "generated_answer" not in report_keys
    assert "raw_response" not in report_keys
