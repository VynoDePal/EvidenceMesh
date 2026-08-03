from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.run_phase11_calibration import (
    ARM_SHARES,
    ARMS,
    CalibrationCase,
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
        title=f"{provider} result {rank}",
        url=url,
        snippet="Official documentation and evidence.",
        provider=provider,
        rank=rank,
        query="official documentation",
    )


def test_phase11_suite_is_locked_and_authored_for_calibration() -> None:
    root = Path(__file__).parents[1]
    cases, raw = load_suite(root / "benchmarks" / "data" / "phase11_calibration_v1.json")
    assert len(cases) == 12
    assert len(raw) < 1_000_000
    assert len({case.id for case in cases}) == 12
    assert all(case.target_domains for case in cases)


def test_phase11_replays_reservations_from_one_raw_pool() -> None:
    case = CalibrationCase(
        id="synthetic",
        query="official documentation",
        target_domains=("tavily-1.net",),
        topic="test",
    )
    raw_results: list[ProviderResult] = []
    for rank in range(1, 11):
        community_url = f"https://community-{rank}.org/result"
        raw_results.extend(
            [
                make_result(
                    provider="searxng",
                    rank=rank,
                    url=community_url,
                ),
                make_result(
                    provider="ddgs",
                    rank=rank,
                    url=community_url,
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
    assert outcomes["community"]["raw_tavily_result_count"] == 0
    assert outcomes["tavily_direct"]["raw_tavily_result_count"] == 10
    assert outcomes["tavily_direct"]["target_domain_hit"] is True
    for arm, share in ARM_SHARES.items():
        expected = int(10 * share)
        assert outcomes[arm]["ranking_reservation_requested"] == expected
        assert outcomes[arm]["ranking_reservation_fulfilled"] == expected
        assert outcomes[arm]["selected_tavily_result_count"] >= expected
        assert set(outcomes[arm]["provider_stage_counts"]) == {
            "raw",
            "fused",
            "eligible",
            "selected",
            "evidence",
            "prompt",
        }


def test_committed_phase11_result_matches_frozen_protocol() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "phase11_calibration_2026-07-29.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "bafeacfad2d0b831910b6ce1470970b6bf7521e544d238cbf51cfdbdcb8305f7"
    )
    report = json.loads(result_bytes)

    assert report["benchmark"] == "evidencemesh-phase11-retrieval-calibration-v1"
    assert report["environment"]["commit_sha"] == ("4a1ed0a63ec5711fdc326d9d39073f10d972f6dc")
    assert report["suite"]["sha256"] == (
        "23f0a3c1c6d680b0ec6bdd0964a81f28b23e5778f4965632b03ed5dc4e78c5d7"
    )
    assert report["protocol"]["searxng_config_sha256"] == (
        "e33610cdd83c89a0fb85e687e632b179ed36057d948db102c7a6e2c33b456efb"
    )
    assert report["traffic"] == {
        "case_retrieval_operations": 12,
        "gemini_requests": 0,
        "maximum_tavily_requests": 12,
        "provider_query_calls": 48,
        "retries": 0,
        "tavily_requests": 12,
    }
    assert len(report["retrieval_diagnostics"]) == 12
    assert len(report["outcomes"]) == 72

    metrics = report["metrics"]
    assert metrics["community"]["availability"]["numerator"] == 12
    assert metrics["community"]["target_domain_hit_at_10"]["numerator"] == 12
    assert metrics["quality_safe_8_2"]["target_domain_hit_at_10"]["numerator"] == 12
    assert metrics["tavily_direct"]["target_domain_hit_at_10"]["numerator"] == 12

    reservation_gate = report["decision"]["gates"]["safe_8_2_reservation_fulfilled_when_evaluable"]
    assert reservation_gate == {
        "evaluable_cases": 12,
        "fulfilled_cases": 10,
        "minimum_evaluable_cases": 9,
        "passed": False,
    }
    assert report["decision"]["phase11_candidate_passed"] is False
    assert report["decision"]["phase12_untouched_evaluation_allowed"] is False
    assert report["decision"]["release_decision"] == "no-go"

    private_fields = {
        "query",
        "question",
        "target_domains",
        "title",
        "url",
        "snippet",
        "content",
        "evidence",
    }
    assert all(not private_fields & set(outcome) for outcome in report["outcomes"])
    assert all(
        set(outcome["provider_stage_counts"])
        == {"raw", "fused", "eligible", "selected", "evidence", "prompt"}
        for outcome in report["outcomes"]
    )
