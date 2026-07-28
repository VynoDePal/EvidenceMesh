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
