import hashlib
import json
from pathlib import Path

import yaml


def test_self_hosted_searxng_enables_json_search_api() -> None:
    settings_path = Path(__file__).parents[1] / "docker" / "searxng" / "settings.yml"
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))

    assert settings["search"]["formats"] == ["html", "json"]
    assert "formats" not in settings
    engines = settings["use_default_settings"]["engines"]["keep_only"]
    assert {"brave", "duckduckgo", "wikipedia"} <= set(engines)
    assert len(engines) == len(set(engines))


def test_phase4_workflow_locks_benchmark_scale_and_provenance() -> None:
    workflow_path = Path(__file__).parents[1] / ".github" / "workflows" / "phase4-benchmark.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    assert "--sample-size 200" in workflow
    assert "--provider-config searxng=docker/searxng/settings.yml" in workflow
    assert "searxng/searxng:2026.7.26-b060c780d@sha256:" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow


def test_phase5_calibration_locks_inputs_and_request_budget() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase5-calibration.yml").read_text(
        encoding="utf-8"
    )
    settings = yaml.safe_load(
        (root / "docker" / "searxng" / "calibration-settings.yml").read_text(encoding="utf-8")
    )
    assert "run_searxng_calibration.py" in workflow
    assert 'request_count"] == 96' in workflow
    assert "--pause-seconds 0.25" in workflow
    assert "--request-timeout 12" in workflow
    assert "searxng/searxng:2026.7.26-b060c780d@sha256:" in workflow
    assert settings["search"]["formats"] == ["html", "json"]
    assert len(settings["use_default_settings"]["engines"]["keep_only"]) == 8
    assert "secret_key" not in settings["server"]
    assert '--env "SEARXNG_SECRET=$(openssl rand -hex 32)"' in workflow
    assert "Generate an ephemeral SearXNG secret" not in workflow
    assert "$GITHUB_ENV" not in workflow


def test_committed_phase4_result_matches_locked_protocol() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "simpleqa_retrieval_phase4_2026-07-28.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "97742a6ceff0b9943ad9dfbb9a94fb36de36f05f38a7d82ea72dc34168f3a48b"
    )
    report = json.loads(result_bytes)
    config_bytes = (root / "docker" / "searxng" / "settings.yml").read_bytes()

    assert report["schema_version"] == 4
    assert report["environment"]["commit_sha"] == ("f78ce4bf53f1e167ea7a2b849e91f5543ba321e2")
    assert report["dataset"]["sha256"] == (
        "feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032"
    )
    assert report["sample"]["count"] == 200
    assert report["sample"]["manifest_sha256"] == (
        "d41ec6c806792f4dc0730b6dd1bad0fe30310a7d3ca0b703bcfcd5cd7f580333"
    )
    assert (
        report["protocol"]["provider_configuration"]["searxng"]["config_sha256"]
        == hashlib.sha256(config_bytes).hexdigest()
    )
    assert set(report["metrics"]) == {"federated", "searxng", "wikipedia"}
    assert len(report["outcomes"]) == 600
    private_fields = {"question", "answer", "reference_answer", "evidence"}
    assert all(not private_fields & set(outcome) for outcome in report["outcomes"])


def test_committed_phase5_result_matches_locked_protocol() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "searxng_calibration_phase5_2026-07-28.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "140f5c1804ab5b29ea2c83a0018364ddd0335a5d4221ea88ebe1bfb9be7bfd53"
    )
    report = json.loads(result_bytes)

    assert report["schema_version"] == 1
    assert report["environment"]["commit_sha"] == ("216e99fda3d7eecfb25e25e51d65395ec86539c6")
    assert report["suite"]["sha256"] == (
        "06a5d97980063999768127439f594090007dff7e793ad61567d248e134779dce"
    )
    assert report["provider"]["config_sha256"] == (
        "856ce08d2bf0c3512cb5a40f91aa54fde1860cad827bd8208fc09059c47d1584"
    )
    assert report["protocol"]["request_count"] == 96
    assert len(report["outcomes"]) == 96
    assert all(outcome["engine_isolation_ok"] for outcome in report["outcomes"])
    assert report["selection"] == {
        "eligible_engines": ["duckduckgo"],
        "eligible_count": 1,
        "full_200_case_run_allowed": False,
        "promotion_limit": 3,
        "promoted_engines": [],
        "ranking": (
            "target hit descending, availability descending, unresponsive rate "
            "ascending, p95 ascending, engine name ascending"
        ),
    }
    private_fields = {
        "question",
        "answer",
        "reference_answer",
        "evidence",
        "title",
        "snippet",
        "url",
        "content",
    }
    assert all(not private_fields & set(outcome) for outcome in report["outcomes"])
