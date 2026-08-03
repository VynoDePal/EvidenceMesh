from argparse import Namespace
from pathlib import Path

import pytest

from benchmarks.run_quality_calibration import (
    EXPECTED_TOPICS,
    aggregate,
    async_main,
    contribution_metrics,
    gate_decision,
    load_suite,
    locked_config_manifest,
    validate_arguments,
    validate_locked_inputs,
)


def root() -> Path:
    return Path(__file__).parents[1]


def passing_outcomes() -> list[dict[str, object]]:
    routes = {
        "web": (
            ["searxng", "wikipedia", "tavily"],
            ["tavily"],
            ["web"],
        ),
        "reference": (
            ["wikipedia"],
            ["wikipedia"],
            ["reference"],
        ),
        "academic": (
            ["wikipedia", "crossref", "arxiv"],
            ["crossref", "arxiv"],
            ["academic"],
        ),
        "code": (
            ["github"],
            ["github"],
            ["code"],
        ),
    }
    outcomes: list[dict[str, object]] = []
    for topic in EXPECTED_TOPICS:
        requested, contributed, families = routes[topic]
        for index in range(8):
            outcomes.append(
                {
                    "case_id": f"p7-{topic}-{index}",
                    "topic": topic,
                    "profile": topic,
                    "expected_family": topic,
                    "response_success": True,
                    "available": True,
                    "target_hit_at_10": True,
                    "expected_family_hit_at_10": True,
                    "provider_degradation": False,
                    "required_family_satisfied": True,
                    "required_family_status": "satisfied",
                    "latency_ms": 100.0 + index,
                    "result_count": 5,
                    "providers_requested": requested,
                    "providers_succeeded": requested,
                    "providers_failed": [],
                    "providers_contributed": contributed,
                    "provider_query_counts": dict.fromkeys(requested, 1),
                    "source_families_contributed": families,
                    "degraded_source_families": [],
                    "failed_source_families": [],
                    "cache_hits": 0,
                    "error_type": None,
                }
            )
    return outcomes


def decision_for(outcomes: list[dict[str, object]]) -> dict[str, object]:
    overall = aggregate(outcomes)
    by_topic = {
        topic: aggregate([outcome for outcome in outcomes if outcome["topic"] == topic])
        for topic in EXPECTED_TOPICS
    }
    providers, families = contribution_metrics(outcomes)
    return gate_decision(overall, by_topic, providers, families, outcomes)


def test_locked_quality_inputs_match_protocol_and_are_novel() -> None:
    cases, suite = load_suite(root() / "benchmarks/data/quality_calibration_v2.json")
    config = locked_config_manifest(
        root() / "docker/searxng/community-calibration-settings.yml",
        "searxng/searxng:tag@sha256:digest",
    )
    validate_locked_inputs(suite, config)
    assert len(cases) == 32
    assert suite["topic_distribution"] == {
        "academic": 8,
        "code": 8,
        "reference": 8,
        "web": 8,
    }
    old_cases, _ = __import__(
        "benchmarks.run_multisource_calibration",
        fromlist=["load_suite"],
    ).load_suite(root() / "benchmarks/data/multisource_calibration_v1.json")
    assert not {case.query.casefold() for case in cases} & {
        case.query.casefold() for case in old_cases
    }


def test_quality_gate_pass_still_blocks_release_without_second_network() -> None:
    decision = decision_for(passing_outcomes())
    assert decision["functional_gate_passed"] is True
    assert decision["cross_network_gate"]["status"] == "not_testable"
    assert decision["stage_b_200_case_run_allowed"] is False
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"


def test_quality_gate_detects_provider_degradation_and_topic_regression() -> None:
    outcomes = passing_outcomes()
    for outcome in outcomes[:9]:
        outcome["provider_degradation"] = True
    for outcome in outcomes[-3:]:
        outcome["target_hit_at_10"] = False
    decision = decision_for(outcomes)
    assert decision["checks"]["overall"]["provider_degradation_rate"] is False
    assert decision["checks"]["per_topic"]["web"]["target_hit_at_10"] is False
    assert decision["functional_gate_passed"] is False


def test_quality_gate_requires_tavily_contribution_and_budget() -> None:
    outcomes = passing_outcomes()
    for outcome in outcomes[-3:]:
        outcome["providers_contributed"] = ["searxng"]
    outcomes[-1]["provider_query_counts"]["tavily"] = 2
    decision = decision_for(outcomes)
    assert decision["checks"]["tavily"]["contributed_cases"] is False
    assert decision["checks"]["tavily"]["query_budget"] is False
    assert decision["functional_gate_passed"] is False


def test_quality_outcomes_exclude_queries_and_result_content() -> None:
    forbidden = {
        "query",
        "title",
        "snippet",
        "content",
        "url",
        "results",
        "target_domains",
        "target_url_prefixes",
    }
    assert all(not forbidden & set(outcome) for outcome in passing_outcomes())


def test_quality_locked_arguments() -> None:
    arguments = Namespace(
        max_results=10,
        request_timeout=20.0,
        pause_seconds=0.5,
    )
    validate_arguments(arguments)
    arguments.pause_seconds = 0.25
    with pytest.raises(ValueError, match=r"0\.5 second"):
        validate_arguments(arguments)


@pytest.mark.asyncio
async def test_quality_calibration_requires_tavily_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        await async_main(
            Namespace(
                max_results=10,
                request_timeout=20.0,
                pause_seconds=0.5,
            )
        )
