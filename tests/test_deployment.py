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


def test_phase6_multisource_workflow_locks_inputs_traffic_and_release_gate() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase6-multisource.yml").read_text(
        encoding="utf-8"
    )
    settings = yaml.safe_load(
        (root / "docker" / "searxng" / "community-calibration-settings.yml").read_text(
            encoding="utf-8"
        )
    )
    assert "run_multisource_calibration.py" in workflow
    assert "--max-results 10" in workflow
    assert "--request-timeout 20" in workflow
    assert "--pause-seconds 0.5" in workflow
    assert 'request_count"] == 24' in workflow
    assert 'stage_b_200_case_run_allowed"] is False' in workflow
    assert 'release_ready"] is False' in workflow
    assert "searxng/searxng:2026.7.26-b060c780d@sha256:" in workflow
    assert settings["use_default_settings"]["engines"]["keep_only"] == ["duckduckgo"]
    assert settings["search"]["formats"] == ["html", "json"]
    assert "secret_key" not in settings["server"]
    assert '--env "SEARXNG_SECRET=$(openssl rand -hex 32)"' in workflow


def test_phase7_quality_workflow_locks_secret_budget_and_release_gate() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase7-quality.yml").read_text(encoding="utf-8")
    assert "run_quality_calibration.py" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "TAVILY_API_KEY: ${{ secrets.EVIDENCE_MESH_TAVILY_KEY }}" in workflow
    assert "--max-results 10" in workflow
    assert "--request-timeout 20" in workflow
    assert "--pause-seconds 0.5" in workflow
    assert 'request_count"] == 32' in workflow
    assert 'maximum_tavily_requests"] == 8' in workflow
    assert 'maximum_tavily_credits"] == 8' in workflow
    assert 'stage_b_200_case_run_allowed"] is False' in workflow
    assert 'release_ready"] is False' in workflow
    assert 'echo "$TAVILY_API_KEY"' not in workflow
    assert "searxng/searxng:2026.7.26-b060c780d@sha256:" in workflow


def test_phase8_workflow_locks_profile_caps_diagnostics_and_release_gate() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase8-quality.yml").read_text(encoding="utf-8")
    assert "run_quality_calibration_v2.py" in workflow
    assert "quality_calibration_v3.json" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "TAVILY_API_KEY: ${{ secrets.EVIDENCE_MESH_TAVILY_KEY }}" in workflow
    assert "--max-results 10" in workflow
    assert "--request-timeout 20" in workflow
    assert "--pause-seconds 0.5" in workflow
    assert 'request_count"] == 32' in workflow
    assert 'maximum_tavily_requests"] == 8' in workflow
    assert 'maximum_tavily_credits"] == 8' in workflow
    assert '"target_rank"' in workflow
    assert '"raw_target_provider_ranks"' in workflow
    assert '"target_identities"' in workflow
    assert 'stage_b_200_case_run_allowed"] is False' in workflow
    assert 'release_ready"] is False' in workflow
    assert 'echo "$TAVILY_API_KEY"' not in workflow
    assert "searxng/searxng:2026.7.26-b060c780d@sha256:" in workflow


def test_phase9_workflow_locks_paired_anonymous_github_budget() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase9-github-recall.yml").read_text(
        encoding="utf-8"
    )
    assert "run_github_recall_paired.py" in workflow
    assert "github_recall_v1.json" in workflow
    assert "--max-results 10" in workflow
    assert "--request-timeout 20" in workflow
    assert "--pause-seconds 6.5" in workflow
    assert 'request_count"] == 48' in workflow
    assert 'requests_per_arm"] == 24' in workflow
    assert 'maximum_queries_per_arm_case"] == 1' in workflow
    assert 'tavily_requests"] == 0' in workflow
    assert 'new_user_secrets"] == 0' in workflow
    assert '"authentication"]' in workflow
    assert '"anonymous"' in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" not in workflow
    assert "TAVILY_API_KEY" not in workflow
    assert 'stage_b_200_case_run_allowed"] is False' in workflow
    assert 'release_ready"] is False' in workflow


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


def test_committed_phase6_result_matches_locked_protocol() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "multisource_calibration_phase6_2026-07-28.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "9fe5671b41136165b2e2856c0c2d6bff54020067859dff22021e135f099f96c4"
    )
    report = json.loads(result_bytes)

    assert report["schema_version"] == 1
    assert report["benchmark"] == "evidencemesh-multisource-calibration-v1"
    assert report["environment"]["commit_sha"] == ("f79a7a919528e68096288498acf60c0babc80716")
    assert report["suite"]["sha256"] == (
        "e99e584cb115a3bb343d052b368e127acd924be7a6aabef98ae90c3c86acce34"
    )
    assert report["provider_configuration"]["searxng"]["sha256"] == (
        "26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645"
    )
    assert report["protocol"]["request_count"] == 24
    assert report["protocol"]["retry_policy"] == "none"
    assert len(report["outcomes"]) == 24

    overall = report["metrics"]["overall"]
    assert overall["availability"]["numerator"] == 24
    assert overall["target_domain_hit_at_10"]["numerator"] == 22
    assert overall["expected_family_hit_at_10"]["numerator"] == 22
    assert overall["partial_failure"]["numerator"] == 8
    assert report["metrics"]["providers"]["searxng"] == {
        "requested_cases": 12,
        "succeeded_cases": 4,
        "contributed_cases": 4,
    }
    decision = report["decision"]
    assert decision["functional_gate_passed"] is False
    assert decision["checks"]["partial_failure_rate"] is False
    assert decision["cross_network_gate"]["status"] == "not_testable"
    assert decision["stage_b_200_case_run_allowed"] is False
    assert decision["release_decision"] == "no-go"

    private_fields = {"query", "title", "snippet", "content", "url", "results"}
    assert all(not private_fields & set(outcome) for outcome in report["outcomes"])


def test_committed_phase7_result_matches_locked_protocol() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "quality_calibration_phase7_2026-07-29.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "4a692732200105b4b6c269647ba3e776ea3b977b70358b66aa24021596ac4104"
    )
    report = json.loads(result_bytes)

    assert report["schema_version"] == 2
    assert report["benchmark"] == "evidencemesh-quality-calibration-v2"
    assert report["environment"]["commit_sha"] == ("c837f5d51d89a8577408f34386ca55886c9b7358")
    assert report["suite"]["sha256"] == (
        "bfa1b033d31e509f622d35d7eb224498db9ba7a939fce3554b0a57c44417b869"
    )
    assert report["provider_configuration"]["searxng"]["sha256"] == (
        "26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645"
    )
    assert report["protocol"]["request_count"] == 32
    assert report["protocol"]["maximum_tavily_requests"] == 8
    assert report["protocol"]["retry_policy"] == "none"
    assert len(report["outcomes"]) == 32

    overall = report["metrics"]["overall"]
    assert overall["availability"]["numerator"] == 31
    assert overall["target_hit_at_10"]["numerator"] == 18
    assert overall["expected_family_hit_at_10"]["numerator"] == 31
    assert overall["provider_degradation"]["numerator"] == 1
    assert overall["required_family_unsatisfied"]["numerator"] == 1
    assert report["metrics"]["providers"]["tavily"] == {
        "requested_cases": 8,
        "succeeded_cases": 8,
        "contributed_cases": 8,
    }
    decision = report["decision"]
    assert decision["functional_gate_passed"] is False
    assert decision["checks"]["overall"]["target_hit_at_10"] is False
    assert decision["checks"]["tavily"] == {
        "requested_cases": True,
        "succeeded_cases": True,
        "contributed_cases": True,
        "query_budget": True,
    }
    assert decision["cross_network_gate"]["status"] == "not_testable"
    assert decision["stage_b_200_case_run_allowed"] is False
    assert decision["release_decision"] == "no-go"

    private_fields = {
        "query",
        "title",
        "snippet",
        "content",
        "url",
        "results",
        "target_domains",
        "target_url_prefixes",
    }
    assert all(not private_fields & set(outcome) for outcome in report["outcomes"])


def test_committed_phase8_result_matches_locked_protocol() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "quality_calibration_phase8_2026-07-29.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "d13598c873e0e7092542bf2f078132efa38fb42b3c67bac60ffe67d113ab563f"
    )
    report = json.loads(result_bytes)

    assert report["schema_version"] == 3
    assert report["benchmark"] == "evidencemesh-quality-calibration-v3"
    assert report["environment"]["commit_sha"] == ("0b029f3df4b85ffe83b64406f0f88b50eff634e4")
    assert report["suite"]["sha256"] == (
        "4a080230b0fe4590f1ef1af9087c7dbfaa05910bdcbd9c43a197cf87c5e44dc4"
    )
    assert report["protocol"]["version"] == 6
    assert report["protocol"]["request_count"] == 32
    assert report["protocol"]["maximum_tavily_requests"] == 8
    assert report["protocol"]["profile_default_max_per_domain"] == {
        "academic": 10,
        "code": 10,
        "news": 3,
        "reference": 10,
        "web": 3,
    }
    assert len(report["outcomes"]) == 32

    overall = report["metrics"]["overall"]
    assert overall["availability"]["numerator"] == 32
    assert overall["target_hit_at_10"]["numerator"] == 26
    assert overall["raw_target_seen"]["numerator"] == 27
    assert overall["target_dropped_by_ranking"]["numerator"] == 1
    assert overall["expected_family_hit_at_10"]["numerator"] == 32
    assert overall["provider_degradation"]["numerator"] == 4
    assert overall["required_family_unsatisfied"]["numerator"] == 0
    assert report["metrics"]["by_topic"]["code"]["target_hit_at_10"]["numerator"] == 4
    assert report["metrics"]["providers"]["tavily"] == {
        "requested_cases": 8,
        "succeeded_cases": 8,
        "contributed_cases": 8,
    }

    decision = report["decision"]
    assert all(decision["checks"]["overall"].values())
    assert decision["checks"]["per_topic"]["code"]["target_hit_at_10"] is False
    assert decision["functional_gate_passed"] is False
    assert decision["cross_network_gate"]["status"] == "not_testable"
    assert decision["stage_b_200_case_run_allowed"] is False
    assert decision["release_decision"] == "no-go"

    private_fields = {
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
    diagnostic_fields = {
        "target_rank",
        "raw_target_seen",
        "raw_target_provider_ranks",
        "target_dropped_by_ranking",
    }
    assert all(not private_fields & set(outcome) for outcome in report["outcomes"])
    assert all(diagnostic_fields <= set(outcome) for outcome in report["outcomes"])
    assert all(
        outcome["effective_max_per_domain"] == (3 if outcome["topic"] == "web" else 10)
        for outcome in report["outcomes"]
    )


def test_committed_phase9_result_matches_locked_protocol() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "github_recall_phase9_2026-07-29.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "17b6f266d6d828b8f013b460810143a1cb02f98c52fea28a1c3811af844e5aab"
    )
    report = json.loads(result_bytes)

    assert report["schema_version"] == 1
    assert report["benchmark"] == "evidencemesh-github-recall-paired-v1"
    assert report["environment"]["commit_sha"] == ("71bb02c8580bc2dff9dc651514ce0098d17eea22")
    assert report["suite"]["sha256"] == (
        "0cfafa78e44662af47e51f26775593af0e3e9d6dbbc417d18178f1218f5ad61a"
    )
    assert report["suite"]["manifest_sha256"] == (
        "7369c9a0f47e4dbf4f752885f32bdf28e44b0472a5129353e75f4da616d20e57"
    )
    assert report["suite"]["count"] == 24

    provider = report["provider_configuration"]
    assert provider["authentication"] == "anonymous"
    assert provider["arms"]["baseline"]["query_strategy"] == "legacy-v1"
    assert provider["arms"]["candidate"]["query_strategy"] == "entity-anchor-v2"

    protocol = report["protocol"]
    assert protocol["version"] == 7
    assert protocol["case_count"] == 24
    assert protocol["request_count"] == 48
    assert protocol["requests_per_arm"] == 24
    assert protocol["maximum_queries_per_arm_case"] == 1
    assert protocol["pause_seconds"] == 6.5
    assert protocol["retry_policy"] == "none"
    assert protocol["cache"] is False
    assert protocol["content_fetching"] is False
    assert protocol["tavily_requests"] == 0
    assert protocol["new_user_secrets"] == 0

    assert len(report["outcomes"]) == 48
    assert sum(outcome["arm"] == "baseline" for outcome in report["outcomes"]) == 24
    assert sum(outcome["arm"] == "candidate" for outcome in report["outcomes"]) == 24
    assert all(outcome["provider_query_count"] == 1 for outcome in report["outcomes"])
    assert all(outcome["cache_hits"] == 0 for outcome in report["outcomes"])

    baseline = report["metrics"]["arms"]["baseline"]
    assert baseline["request_success"]["numerator"] == 23
    assert baseline["availability"]["numerator"] == 8
    assert baseline["raw_target_seen"]["numerator"] == 4
    assert baseline["target_hit_at_10"]["numerator"] == 4

    candidate = report["metrics"]["arms"]["candidate"]
    assert candidate["request_success"]["numerator"] == 24
    assert candidate["availability"]["numerator"] == 24
    assert candidate["raw_target_seen"]["numerator"] == 24
    assert candidate["target_hit_at_10"]["numerator"] == 24
    assert candidate["target_rank"]["at_1"] == 21
    assert candidate["latency_ms"]["p95"] == 864.937

    paired = report["metrics"]["paired"]["target_hit_at_10"]
    assert paired == {
        "baseline_wins": 0,
        "both_false": 0,
        "both_true": 4,
        "candidate_wins": 20,
        "discordant_pairs": 20,
        "mcnemar_exact_two_sided_p": 0.000002,
        "net_gain": 20,
    }

    decision = report["decision"]
    assert all(decision["checks"]["candidate"].values())
    assert all(decision["checks"]["paired"].values())
    assert decision["functional_gate_passed"] is True
    assert decision["cross_network_gate"] == {
        "completed": 1,
        "required": 2,
        "status": "not_testable",
    }
    assert decision["stage_b_200_case_run_allowed"] is False
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"

    private_fields = {
        "query",
        "normalized_query",
        "target",
        "target_identity",
        "target_repository",
        "title",
        "snippet",
        "content",
        "url",
        "results",
    }
    diagnostic_fields = {
        "target_rank",
        "raw_target_rank",
        "raw_target_seen",
        "target_dropped_by_ranking",
    }
    assert all(not private_fields & set(outcome) for outcome in report["outcomes"])
    assert all(diagnostic_fields <= set(outcome) for outcome in report["outcomes"])
