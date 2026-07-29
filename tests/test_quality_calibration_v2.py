from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
from conftest import StaticProvider

from benchmarks.run_multisource_calibration import load_suite as load_phase6_suite
from benchmarks.run_quality_calibration import load_suite as load_phase7_suite
from benchmarks.run_quality_calibration_v2 import (
    CalibrationCase,
    RawResultRecorder,
    RecordingProvider,
    aggregate,
    async_main,
    load_suite,
    locked_config_manifest,
    run_case,
    validate_arguments,
    validate_locked_inputs,
)
from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import ProviderResult, SearchProfile, SearchRequest, SourceType


def root() -> Path:
    return Path(__file__).parents[1]


def test_phase8_locked_inputs_are_valid_balanced_and_novel() -> None:
    cases, suite = load_suite(root() / "benchmarks/data/quality_calibration_v3.json")
    config = locked_config_manifest(
        root() / "docker/searxng/community-calibration-settings.yml",
        "searxng/searxng:tag@sha256:digest",
    )
    validate_locked_inputs(suite, config)
    assert suite["target_identity_schema"] == 1
    assert suite["topic_distribution"] == {
        "academic": 8,
        "code": 8,
        "reference": 8,
        "web": 8,
    }
    prior_queries = {
        case.query.casefold()
        for loader, path in (
            (load_phase6_suite, "benchmarks/data/multisource_calibration_v1.json"),
            (load_phase7_suite, "benchmarks/data/quality_calibration_v2.json"),
        )
        for case in loader(root() / path)[0]
    }
    assert not {case.query.casefold() for case in cases} & prior_queries


@pytest.mark.asyncio
async def test_recording_provider_delegates_once_and_captures_native_rank() -> None:
    result = ProviderResult(
        title="FastAPI",
        url="https://github.com/fastapi/fastapi",
        provider="stub",
        rank=4,
        query="FastAPI",
        source_type=SourceType.CODE,
    )
    provider = StaticProvider("stub", [result])
    recorder = RawResultRecorder()
    wrapper = RecordingProvider(provider, recorder)
    request = SearchRequest(query="FastAPI", profile=SearchProfile.CODE)

    assert await wrapper.search("FastAPI", request)
    assert provider.calls == ["FastAPI"]
    assert recorder.target_provider_ranks(("github:fastapi/fastapi",)) == {"stub": 4}


@pytest.mark.asyncio
async def test_phase8_case_records_raw_and_final_target_rank(settings) -> None:
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
            title=name,
            url=f"https://github.com/example/{name}",
            provider="github",
            rank=rank,
            query="software catalog",
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
    case = CalibrationCase(
        id="case",
        query="software catalog",
        profile=SearchProfile.CODE,
        expected_family="code",
        target_identities=("github:example/garnet",),
        topic="code",
    )

    outcome = await run_case(engine, recorder, case, max_results=10)

    assert outcome["result_count"] == 10
    assert outcome["effective_max_per_domain"] == 10
    assert outcome["max_per_domain_policy"] == "profile_default"
    assert outcome["raw_target_provider_ranks"] == {"github": 7}
    assert outcome["raw_target_seen"] is True
    assert outcome["target_hit_at_10"] is True
    assert outcome["target_rank"] is not None
    assert outcome["target_dropped_by_ranking"] is False
    await engine.aclose()


def test_phase8_aggregate_exposes_rank_diagnostics() -> None:
    outcomes = [
        {
            "response_success": True,
            "available": True,
            "target_hit_at_10": True,
            "target_rank": 2,
            "raw_target_seen": True,
            "target_dropped_by_ranking": False,
            "expected_family_hit_at_10": True,
            "provider_degradation": False,
            "required_family_satisfied": True,
            "latency_ms": 100.0,
            "result_count": 10,
        },
        {
            "response_success": True,
            "available": True,
            "target_hit_at_10": False,
            "target_rank": None,
            "raw_target_seen": True,
            "target_dropped_by_ranking": True,
            "expected_family_hit_at_10": True,
            "provider_degradation": False,
            "required_family_satisfied": True,
            "latency_ms": 200.0,
            "result_count": 10,
        },
    ]
    metrics = aggregate(outcomes)
    assert metrics["raw_target_seen"]["numerator"] == 2
    assert metrics["target_dropped_by_ranking"]["numerator"] == 1
    assert metrics["target_rank"]["observed"] == 1
    assert metrics["target_rank"]["at_3"] == 1


def test_phase8_outcomes_keep_target_values_private() -> None:
    forbidden = {
        "query",
        "title",
        "snippet",
        "content",
        "url",
        "results",
        "target_domains",
        "target_url_prefixes",
        "target_identities",
    }
    allowed_diagnostics = {
        "target_rank",
        "raw_target_seen",
        "raw_target_provider_ranks",
        "target_dropped_by_ranking",
    }
    assert not forbidden & allowed_diagnostics


def test_phase8_locked_arguments() -> None:
    arguments = Namespace(
        max_results=10,
        request_timeout=20.0,
        pause_seconds=0.5,
    )
    validate_arguments(arguments)
    arguments.max_results = 9
    with pytest.raises(ValueError, match="exactly 10"):
        validate_arguments(arguments)


@pytest.mark.asyncio
async def test_phase8_requires_tavily_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        await async_main(
            Namespace(
                max_results=10,
                request_timeout=20.0,
                pause_seconds=0.5,
            )
        )
