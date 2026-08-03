from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest
from conftest import StaticProvider

from benchmarks.run_github_recall_paired import (
    RawResultRecorder,
    RecordingProvider,
    RepositoryCase,
    aggregate,
    gate_decision,
    load_suite,
    paired_metrics,
    run_arm_case,
    validate_arguments,
    validate_locked_inputs,
)
from benchmarks.run_quality_calibration_v2 import load_suite as load_phase8_suite
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import ProviderResult, SearchProfile, SourceType


def root() -> Path:
    return Path(__file__).parents[1]


def test_phase9_suite_is_locked_balanced_and_novel() -> None:
    cases, manifest = load_suite(root() / "benchmarks/data/github_recall_v1.json")
    validate_locked_inputs(manifest)
    assert manifest["difficulty_distribution"] == {
        "low": 8,
        "medium": 8,
        "high": 8,
    }
    assert manifest["query_form_distribution"] == {
        "entity_first": 12,
        "intent_prefix": 12,
    }

    phase7 = json.loads(
        (root() / "benchmarks/data/quality_calibration_v2.json").read_text(encoding="utf-8")
    )
    phase7_targets = {
        prefix.removeprefix("https://github.com/").casefold()
        for item in phase7
        if item["topic"] == "code"
        for prefix in item["target_url_prefixes"]
    }
    phase8_targets = {
        identity.removeprefix("github:").casefold()
        for case in load_phase8_suite(root() / "benchmarks/data/quality_calibration_v3.json")[0]
        if case.topic == "code"
        for identity in case.target_identities
    }
    phase9_targets = {
        identity.removeprefix("github:").casefold()
        for case in cases
        for identity in case.target_identities
    }
    assert not phase9_targets & phase7_targets
    assert not phase9_targets & phase8_targets


@pytest.mark.asyncio
async def test_phase9_case_records_one_call_and_raw_rank(settings) -> None:
    names = [
        "amber",
        "birch",
        "cedar",
        "delta",
        "ember",
        "fjord",
        "garnet",
        "harbor",
        "indigo",
        "juniper",
    ]
    results = [
        ProviderResult(
            title=f"example/{name}",
            url=f"https://github.com/example/{name}",
            provider="github",
            rank=rank,
            query="repository",
            source_type=SourceType.CODE,
        )
        for rank, name in enumerate(names, start=1)
    ]
    provider = StaticProvider("github", results)
    recorder = RawResultRecorder()
    engine = EvidenceMesh(
        settings,
        providers=[RecordingProvider(provider, recorder)],
    )
    case = RepositoryCase(
        id="case",
        query="Repository number seven",
        target_identities=("github:example/garnet",),
        difficulty="medium",
        query_form="entity_first",
    )

    outcome = await run_arm_case(
        engine,
        recorder,
        case,
        "candidate",
        max_results=10,
    )

    assert provider.calls == ["Repository number seven"]
    assert outcome["request_succeeded"] is True
    assert outcome["provider_query_count"] == 1
    assert outcome["raw_target_rank"] == 7
    assert outcome["target_rank"] is not None
    assert outcome["cache_hits"] == 0
    await engine.aclose()


def _outcome(
    case_id: str,
    arm: str,
    *,
    target: bool,
    raw_target: bool,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "arm": arm,
        "difficulty": "low",
        "query_form": "entity_first",
        "request_succeeded": True,
        "available": True,
        "target_hit_at_10": target,
        "target_rank": 1 if target else None,
        "raw_target_seen": raw_target,
        "raw_target_rank": 1 if raw_target else None,
        "target_dropped_by_ranking": raw_target and not target,
        "latency_ms": 100.0,
        "result_count": 10,
        "provider_query_count": 1,
        "provider_failed": False,
        "cache_hits": 0,
        "error_type": None,
    }


def test_phase9_paired_metrics_and_gates() -> None:
    outcomes: list[dict[str, object]] = []
    for index in range(24):
        case_id = f"case-{index:02d}"
        baseline_target = index < 12
        candidate_target = index < 20
        outcomes.extend(
            [
                _outcome(
                    case_id,
                    "baseline",
                    target=baseline_target,
                    raw_target=baseline_target,
                ),
                _outcome(
                    case_id,
                    "candidate",
                    target=candidate_target,
                    raw_target=index < 22,
                ),
            ]
        )

    arms = {
        arm: aggregate([outcome for outcome in outcomes if outcome["arm"] == arm])
        for arm in ("baseline", "candidate")
    }
    paired = paired_metrics(outcomes)
    decision = gate_decision(outcomes, arms, paired)

    assert paired["target_hit_at_10"]["candidate_wins"] == 8
    assert paired["target_hit_at_10"]["baseline_wins"] == 0
    assert paired["target_hit_at_10"]["net_gain"] == 8
    assert decision["functional_gate_passed"] is True
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"


def test_phase9_public_outcomes_exclude_queries_and_targets() -> None:
    forbidden = {
        "query",
        "normalized_query",
        "title",
        "snippet",
        "content",
        "url",
        "results",
        "target_identities",
    }
    sample = _outcome("case", "candidate", target=True, raw_target=True)
    assert not forbidden & set(sample)


def test_phase9_locked_arguments() -> None:
    arguments = Namespace(
        max_results=10,
        request_timeout=20.0,
        pause_seconds=6.5,
    )
    validate_arguments(arguments)
    arguments.pause_seconds = 6.0
    with pytest.raises(ValueError, match=r"6\.5 second"):
        validate_arguments(arguments)


def test_phase9_suite_is_code_only() -> None:
    cases, _ = load_suite(root() / "benchmarks/data/github_recall_v1.json")
    assert all(
        identity.startswith("github:") for case in cases for identity in case.target_identities
    )
    assert SearchProfile.CODE.value == "code"
