from __future__ import annotations

from pathlib import Path

from benchmarks.run_phase11_1_calibration import (
    ARMS,
    CalibrationCase,
    build_decision,
    load_suite,
    replay_arm,
)
from evidencemesh.models import ProviderResult


def make_result(
    *,
    provider: str,
    rank: int,
    url: str,
) -> ProviderResult:
    return ProviderResult(
        title=f"{provider} evidence {rank}",
        url=url,
        snippet="Official documentation and evidence.",
        provider=provider,
        rank=rank,
        query="official documentation",
    )


def test_phase11_1_explicitly_reuses_locked_authored_suite() -> None:
    root = Path(__file__).parents[1]
    cases, raw = load_suite(root / "benchmarks" / "data" / "phase11_calibration_v1.json")
    assert len(cases) == 12
    assert len(raw) < 1_000_000
    assert all(case.target_domains for case in cases)


def test_phase11_1_replays_wiby_and_tavily_from_one_raw_pool() -> None:
    case = CalibrationCase(
        id="synthetic",
        query="official documentation",
        target_domains=("tavily-1.net",),
        topic="test",
    )
    raw_results: list[ProviderResult] = []
    for rank in range(1, 11):
        raw_results.extend(
            [
                make_result(
                    provider="searxng",
                    rank=rank,
                    url=f"https://community-{rank}.org/result",
                ),
                make_result(
                    provider="wiby",
                    rank=rank,
                    url=f"https://wiby-{rank}.org/result",
                ),
                make_result(
                    provider="tavily",
                    rank=rank,
                    url=f"https://tavily-{rank}.net/result",
                ),
            ]
        )

    outcomes = {
        arm: replay_arm(
            case,
            raw_results,
            arm=arm,
            limit=10,
            max_per_domain=3,
            prompt_budget_chars=12_000,
        )
        for arm in ARMS
    }
    assert outcomes["wiby_direct"]["raw_wiby_result_count"] == 10
    assert outcomes["wiby_direct"]["raw_tavily_result_count"] == 0
    assert outcomes["tavily_direct"]["raw_wiby_result_count"] == 0
    assert outcomes["community"]["raw_tavily_result_count"] == 0
    assert outcomes["quality_safe_8_2"]["ranking_reservation_requested"] == 8
    assert outcomes["quality_safe_8_2"]["ranking_reservation_feasible"] == 10
    assert outcomes["quality_safe_8_2"]["ranking_reservation_target"] == 8
    assert outcomes["quality_safe_8_2"]["ranking_reservation_fulfilled"] == 8


def test_phase11_1_reservation_target_respects_domain_feasibility() -> None:
    case = CalibrationCase(
        id="domain-cap",
        query="official documentation",
        target_domains=("primary-one.example",),
        topic="test",
    )
    titles = ["Oak", "River", "Quartz", "Falcon", "Harbor", "Meadow", "Comet", "Cedar"]
    raw_results = [
        ProviderResult(
            title=titles[rank - 1],
            snippet="Official documentation and evidence.",
            provider="tavily",
            rank=rank,
            query="official documentation",
            url=(
                f"https://primary-one.example/result-{rank}"
                if rank <= 4
                else f"https://primary-two.example/result-{rank}"
            ),
        )
        for rank in range(1, 9)
    ]
    outcome = replay_arm(
        case,
        raw_results,
        arm="quality_safe_8_2",
        limit=10,
        max_per_domain=3,
        prompt_budget_chars=12_000,
    )
    assert outcome["ranking_reservation_requested"] == 8
    assert outcome["ranking_reservation_eligible"] == 8
    assert outcome["ranking_reservation_feasible"] == 6
    assert outcome["ranking_reservation_target"] == 6
    assert outcome["ranking_reservation_fulfilled"] == 6
    assert outcome["ranking_reservation_shortfall_reason"] == "domain_diversity_cap"


def test_phase11_1_decision_requires_every_frozen_gate() -> None:
    outcomes: list[dict[str, object]] = []
    for arm in ARMS:
        for index in range(12):
            outcome: dict[str, object] = {
                "case_id": f"case-{index}",
                "arm": arm,
                "target_domain_hit": True,
            }
            if arm == "quality_safe_8_2":
                outcome.update(
                    {
                        "ranking_reservation_requested": 8,
                        "ranking_reservation_target": 8 if index < 9 else 6,
                        "ranking_reservation_fulfilled": 8 if index < 9 else 6,
                    }
                )
            outcomes.append(outcome)
    metrics = {
        "community": {
            "availability": {"numerator": 12},
            "cases_with_selected_wiby": {"numerator": 12},
        },
        "quality_safe_8_2": {
            "target_domain_hit_at_10": {"numerator": 12},
        },
        "quality_legacy": {
            "target_domain_hit_at_10": {"numerator": 12},
        },
    }
    decision = build_decision(
        outcomes,  # type: ignore[arg-type]
        metrics,
        tavily_requests=12,
        wiby_requests=12,
        wiby_raw_cases=12,
        wiby_attributed_cases=12,
    )
    assert decision["phase11_1_candidate_passed"] is True
    assert decision["phase12_untouched_evaluation_allowed"] is True
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"


def test_phase11_1_workflow_locks_traffic_privacy_and_no_model_calls() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase11-1-calibration.yml").read_text(
        encoding="utf-8"
    )
    assert "run_phase11_1_calibration.py" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert 'report["traffic"]["provider_query_calls"] == 60' in workflow
    assert 'report["traffic"]["tavily_requests"] == 12' in workflow
    assert 'report["traffic"]["wiby_requests"] == 12' in workflow
    assert 'report["traffic"]["gemini_requests"] == 0' in workflow
    assert 'report["decision"]["release_ready"] is False' in workflow
    assert 'report["decision"]["release_decision"] == "no-go"' in workflow
