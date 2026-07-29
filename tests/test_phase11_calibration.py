from __future__ import annotations

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
