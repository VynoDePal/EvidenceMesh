from __future__ import annotations

from pathlib import Path

from benchmarks.run_phase11_2_independent_index import (
    ARMS,
    IndependentIndexCase,
    _arm_metrics,
    build_decision,
    load_suite,
    replay_arm,
)
from evidencemesh.models import ProviderResult


def make_result(*, provider: str, rank: int, domain: str) -> ProviderResult:
    return ProviderResult(
        title=f"{provider} independent evidence",
        url=f"https://{domain}/result-{rank}",
        snippet="Independent search documentation and evidence.",
        provider=provider,
        rank=rank,
        query="independent search documentation",
    )


def test_phase11_2_loads_locked_balanced_suite() -> None:
    root = Path(__file__).parents[1]
    cases, raw = load_suite(root / "benchmarks" / "data" / "independent_index_calibration_v1.json")
    assert len(cases) == 16
    assert len(raw) < 1_000_000
    assert sum(case.stratum == "broad_web" for case in cases) == 8
    assert sum(case.stratum == "long_tail" for case in cases) == 8
    assert all(case.target_domains for case in cases)


def test_phase11_2_replays_five_arms_without_network_or_reservation() -> None:
    case = IndependentIndexCase(
        id="synthetic",
        query="independent search documentation",
        target_domains=("mwmbl.example",),
        stratum="long_tail",
        topic="test",
    )
    raw_results = [
        make_result(provider="searxng", rank=1, domain="legacy.example"),
        make_result(provider="ddgs", rank=1, domain="ddgs.example"),
        make_result(provider="wikipedia", rank=1, domain="wikipedia.example"),
        make_result(provider="wiby", rank=1, domain="wiby.example"),
        make_result(provider="mwmbl", rank=1, domain="mwmbl.example"),
    ]
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
    assert outcomes["legacy_community"]["raw_mwmbl_result_count"] == 0
    assert outcomes["legacy_community"]["raw_wiby_result_count"] == 0
    assert outcomes["candidate_community"]["raw_mwmbl_result_count"] == 1
    assert outcomes["candidate_community"]["raw_wiby_result_count"] == 1
    assert outcomes["mwmbl_direct"]["raw_mwmbl_result_count"] == 1
    assert outcomes["mwmbl_direct"]["raw_wiby_result_count"] == 0
    assert outcomes["wiby_direct"]["raw_mwmbl_result_count"] == 0
    assert outcomes["independent_fused"]["raw_mwmbl_result_count"] == 1
    assert outcomes["independent_fused"]["raw_wiby_result_count"] == 1
    assert outcomes["mwmbl_direct"]["target_domain_hit"] is True
    assert all(outcome["ranking_reservation_policy"] == "none" for outcome in outcomes.values())
    assert all(outcome["ranking_reservation_requested"] == 0 for outcome in outcomes.values())


def test_phase11_2_separates_retrieval_pass_from_default_eligibility() -> None:
    outcomes: list[dict[str, object]] = []
    for arm in ARMS:
        for index in range(16):
            outcomes.append(
                {
                    "case_id": f"case-{index}",
                    "stratum": "broad_web" if index < 8 else "long_tail",
                    "arm": arm,
                    "available": True,
                    "target_domain_hit": True,
                    "selected_mwmbl_result_count": int(
                        arm
                        in {
                            "candidate_community",
                            "mwmbl_direct",
                            "independent_fused",
                        }
                    ),
                    "selected_wiby_result_count": int(
                        arm in {"candidate_community", "wiby_direct", "independent_fused"}
                    ),
                    "prompt_result_count": 1,
                }
            )
    metrics = _arm_metrics(outcomes)  # type: ignore[arg-type]
    decision = build_decision(
        outcomes,  # type: ignore[arg-type]
        metrics,
        provider_query_calls=80,
        mwmbl_requests=16,
        wiby_requests=16,
        mwmbl_raw_cases=16,
        mwmbl_raw_broad_cases=8,
        mwmbl_raw_long_tail_cases=8,
        mwmbl_licensed_cases=16,
    )
    assert decision["retrieval_candidate_passed"] is True
    assert decision["default_bundle_eligible"] is False
    assert decision["phase12_untouched_evaluation_allowed"] is False
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"


def test_phase11_2_workflow_locks_zero_paid_and_zero_model_traffic() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase11-2-independent-index.yml").read_text(
        encoding="utf-8"
    )
    assert "run_phase11_2_independent_index.py" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" not in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" not in workflow
    assert "TAVILY_API_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert 'report["traffic"]["provider_query_calls"] == 80' in workflow
    assert 'report["traffic"]["mwmbl_requests"] == 16' in workflow
    assert 'report["traffic"]["wiby_requests"] == 16' in workflow
    assert 'report["traffic"]["paid_provider_requests"] == 0' in workflow
    assert 'report["traffic"]["gemini_requests"] == 0' in workflow
    assert 'report["decision"]["default_bundle_eligible"] is False' in workflow
    assert 'report["decision"]["release_decision"] == "no-go"' in workflow
