from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import httpx
import pytest

from benchmarks.run_searxng_calibration import (
    CalibrationCase,
    calibrate_request,
    config_manifest,
    domain_matches,
    engine_metrics,
    first_target_rank,
    load_suite,
    rank_eligible_engines,
    ranked_domains,
    scheduled_pairs,
    validate_arguments,
)


def calibration_case(case_id: str = "case-1") -> CalibrationCase:
    return CalibrationCase(
        id=case_id,
        query="Example documentation",
        target_domains=("docs.example.com",),
        topic="software",
    )


def outcome(
    engine: str,
    *,
    target: bool = True,
    available: bool = True,
    unresponsive: bool = False,
    latency_ms: float = 100.0,
) -> dict[str, object]:
    return {
        "id": "case",
        "engine": engine,
        "response_ok": True,
        "available": available,
        "result_count": 1 if available else 0,
        "unique_domains": 1 if available else 0,
        "target_domain_rank": 1 if target else None,
        "unresponsive_engines": [engine] if unresponsive else [],
        "latency_ms": latency_ms,
        "error_kind": None,
    }


def test_suite_loading_hashes_ids_and_rejects_empty_domains(tmp_path: Path) -> None:
    path = tmp_path / "suite.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "one",
                    "query": "Official example",
                    "target_domains": ["example.com"],
                    "topic": "test",
                }
            ]
        ),
        encoding="utf-8",
    )
    cases, manifest = load_suite(path)
    assert cases == [
        CalibrationCase(
            id="one",
            query="Official example",
            target_domains=("example.com",),
            topic="test",
        )
    ]
    assert manifest["count"] == 1
    assert len(manifest["sha256"]) == 64
    path.write_text(
        '[{"id":"one","query":"q","target_domains":[""],"topic":"test"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid target"):
        load_suite(path)


def test_domain_ranking_uses_safe_http_urls_and_subdomain_matching() -> None:
    payload = {
        "results": [
            {"url": "javascript:alert(1)"},
            {"url": "https://other.example/page"},
            {"url": "https://docs.example.com/guide"},
        ]
    }
    domains = ranked_domains(payload, max_results=10)
    assert domains == ["other.example", "docs.example.com"]
    assert first_target_rank(domains, ("example.com",)) == 2
    assert domain_matches("docs.example.com", "example.com")
    assert not domain_matches("notexample.com", "example.com")


def test_schedule_covers_every_pair_once_with_rotated_first_engine() -> None:
    cases = [calibration_case("one"), calibration_case("two")]
    pairs = scheduled_pairs(cases, ("a", "b", "c"))
    assert len(pairs) == 6
    assert len({(case.id, engine) for case, engine in pairs}) == 6
    assert [engine for case, engine in pairs if case.id == "one"] == ["a", "b", "c"]
    assert [engine for case, engine in pairs if case.id == "two"] == ["b", "c", "a"]


@pytest.mark.asyncio
async def test_calibration_request_records_target_and_unresponsive_engine() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["engines"] == "brave"
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://docs.example.com/guide"}],
                "unresponsive_engines": [["brave", "timeout"]],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await calibrate_request(
            client,
            base_url="https://search.example",
            case=calibration_case(),
            engine="brave",
            language="en",
            max_results=10,
        )
    assert result["response_ok"] is True
    assert result["target_domain_rank"] == 1
    assert result["unresponsive_engines"] == ["brave"]


def test_metrics_enforce_all_gates_and_rank_eligible_engines() -> None:
    engines = ("fast", "relevant", "unreliable")
    outcomes = []
    for _ in range(12):
        outcomes.extend(
            [
                outcome("fast", target=True, latency_ms=50),
                outcome("relevant", target=True, latency_ms=100),
                outcome("unreliable", target=False, available=False, unresponsive=True),
            ]
        )
    metrics = engine_metrics(outcomes, engines=engines, max_results=10)
    assert metrics["fast"]["eligible"] is True
    assert metrics["relevant"]["eligible"] is True
    assert metrics["unreliable"]["eligible"] is False
    assert set(metrics["unreliable"]["failed_gates"]) == {
        "availability_rate",
        "target_domain_hit_at_10",
        "unresponsive_rate",
    }
    assert rank_eligible_engines(metrics) == ["fast", "relevant"]


def test_locked_arguments_and_pinned_config_manifest(tmp_path: Path) -> None:
    arguments = Namespace(
        max_results=9,
        request_timeout=12.0,
        pause_seconds=0.25,
        engines=None,
        base_url="http://127.0.0.1:8889",
    )
    with pytest.raises(ValueError, match="exactly 10"):
        validate_arguments(arguments)

    config = tmp_path / "settings.yml"
    config.write_text("search: {}\n", encoding="utf-8")
    manifest = config_manifest(config, "image:tag@sha256:digest")
    assert len(manifest["config_sha256"]) == 64
    with pytest.raises(ValueError, match="immutable digest"):
        config_manifest(config, "image:latest")
