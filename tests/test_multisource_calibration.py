from argparse import Namespace
from pathlib import Path

import pytest

from benchmarks.run_multisource_calibration import (
    EXPECTED_TOPICS,
    aggregate,
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
        "web": (["searxng", "wikipedia"], ["searxng"], ["web"]),
        "reference": (["searxng", "wikipedia"], ["wikipedia"], ["reference"]),
        "academic": (
            ["wikipedia", "crossref", "arxiv"],
            ["crossref", "arxiv"],
            ["academic"],
        ),
        "code": (["github"], ["github"], ["code"]),
    }
    outcomes: list[dict[str, object]] = []
    for topic in EXPECTED_TOPICS:
        requested, contributed, families = routes[topic]
        for index in range(6):
            outcomes.append(
                {
                    "case_id": f"{topic}-{index}",
                    "topic": topic,
                    "profile": "web" if topic == "reference" else topic,
                    "expected_family": topic,
                    "target_domains": ["example.org"],
                    "response_success": True,
                    "available": True,
                    "target_domain_hit_at_10": True,
                    "expected_family_hit_at_10": True,
                    "partial_failure": False,
                    "latency_ms": 100.0 + index,
                    "result_count": 5,
                    "providers_requested": requested,
                    "providers_succeeded": requested,
                    "providers_failed": [],
                    "providers_contributed": contributed,
                    "source_families_contributed": families,
                    "cache_hits": 0,
                    "error_type": None,
                }
            )
    return outcomes


def test_locked_multisource_inputs_match_protocol() -> None:
    cases, suite = load_suite(root() / "benchmarks/data/multisource_calibration_v1.json")
    config = locked_config_manifest(
        root() / "docker/searxng/community-calibration-settings.yml",
        "searxng/searxng:tag@sha256:digest",
    )
    validate_locked_inputs(suite, config)
    assert len(cases) == 24
    assert suite["topic_distribution"] == {
        "academic": 6,
        "code": 6,
        "reference": 6,
        "web": 6,
    }


def test_multisource_gate_pass_still_requires_second_network() -> None:
    outcomes = passing_outcomes()
    overall = aggregate(outcomes)
    providers, families = contribution_metrics(outcomes)
    decision = gate_decision(overall, providers, families)
    assert decision["functional_gate_passed"] is True
    assert decision["cross_network_gate"]["status"] == "not_testable"
    assert decision["stage_b_200_case_run_allowed"] is False
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"


def test_multisource_gate_detects_insufficient_availability() -> None:
    outcomes = passing_outcomes()
    for outcome in outcomes[:3]:
        outcome["available"] = False
    overall = aggregate(outcomes)
    providers, families = contribution_metrics(outcomes)
    decision = gate_decision(overall, providers, families)
    assert overall["availability"]["rate"] == 0.875
    assert decision["checks"]["availability_rate"] is False
    assert decision["functional_gate_passed"] is False


def test_multisource_outcomes_exclude_query_and_result_content() -> None:
    forbidden = {"query", "title", "snippet", "content", "url", "results"}
    assert all(not forbidden & set(outcome) for outcome in passing_outcomes())


def test_multisource_locked_arguments() -> None:
    arguments = Namespace(
        max_results=10,
        request_timeout=20.0,
        pause_seconds=0.5,
    )
    validate_arguments(arguments)
    arguments.max_results = 9
    with pytest.raises(ValueError, match="exactly 10"):
        validate_arguments(arguments)
