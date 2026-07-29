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


def test_phase10_workflow_locks_models_secrets_traffic_privacy_and_release_gate() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase10-end-to-end.yml").read_text(
        encoding="utf-8"
    )
    assert "run_end_to_end_phase10.py" in workflow
    assert "end_to_end_phase10_v1.json" in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "GEMINI_API_KEY: ${{ secrets.EVIDENCE_MESH_GEMINI_KEY }}" in workflow
    assert "TAVILY_API_KEY: ${{ secrets.EVIDENCE_MESH_TAVILY_KEY }}" in workflow
    assert "gemma-4-31b-it" in workflow
    assert "gemma-4-26b-a4b-it" in workflow
    assert "gemini-3.5-flash-lite" in workflow
    assert "--model-pause-seconds 2.0" in workflow
    assert "--max-output-tokens 2048" in workflow
    assert 'report["traffic"]["generation_requests"] == 144' in workflow
    assert 'report["traffic"]["tavily_requests"] == 24' in workflow
    assert 'report["traffic"]["retries"] == 0' in workflow
    assert 'report["privacy"]["generated_answers_in_report"] is False' in workflow
    assert 'report["decision"]["stage_b_allowed"] is False' in workflow
    assert 'report["decision"]["release_ready"] is False' in workflow
    assert 'report["decision"]["release_decision"] == "no-go"' in workflow
    assert 'echo "$GEMINI_API_KEY"' not in workflow
    assert 'echo "$TAVILY_API_KEY"' not in workflow
    assert "searxng/searxng:2026.7.26-b060c780d@sha256:" in workflow


def test_phase11_community_config_is_multi_engine_and_zero_key() -> None:
    root = Path(__file__).parents[1]
    settings = yaml.safe_load(
        (root / "docker" / "searxng" / "phase11-community-settings.yml").read_text(encoding="utf-8")
    )
    engines = settings["use_default_settings"]["engines"]["keep_only"]
    assert {
        "brave",
        "duckduckgo",
        "startpage",
        "wikipedia",
    } <= set(engines)
    assert settings["search"]["formats"] == ["html", "json"]
    assert len(engines) == len(set(engines))
    assert "secret_key" not in settings["server"]


def test_phase11_workflow_locks_shared_pool_traffic_and_no_model_calls() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase11-calibration.yml").read_text(
        encoding="utf-8"
    )
    assert "run_phase11_calibration.py" in workflow
    assert "phase11_calibration_v1.json" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert "--max-results 10" in workflow
    assert "--prompt-budget-chars 12000" in workflow
    assert 'report["traffic"]["provider_query_calls"] == 48' in workflow
    assert 'report["traffic"]["tavily_requests"] == 12' in workflow
    assert 'report["traffic"]["gemini_requests"] == 0' in workflow
    assert 'report["traffic"]["retries"] == 0' in workflow
    assert 'report["protocol"]["shared_raw_pool_per_case"] is True' in workflow
    assert 'report["decision"]["release_ready"] is False' in workflow
    assert 'report["decision"]["release_decision"] == "no-go"' in workflow
    assert 'echo "$TAVILY_API_KEY"' not in workflow
    assert "searxng/searxng:2026.7.26-b060c780d@sha256:" in workflow


def test_phase11_5_protocol_and_workflow_lock_quality_recovery_budget() -> None:
    root = Path(__file__).parents[1]
    protocol_path = root / "docs" / "benchmark-protocol-v13.md"
    workflow = (root / ".github" / "workflows" / "phase11-5-quality-recovery.yml").read_text(
        encoding="utf-8"
    )
    protocol = protocol_path.read_text(encoding="utf-8")

    assert hashlib.sha256(protocol_path.read_bytes()).hexdigest() == (
        "7fa9f6a0e40d2c7e18260de6468fa1b86770752f1b366985a2bedc5b070155b6"
    )
    assert "corrective calibration, not an untouched evaluation" in protocol
    assert "exactly 108 native Gemini" in protocol
    assert "community observability arm is explicitly excluded" in protocol
    assert "No Phase 12 question" in protocol
    assert "PR remains draft" in protocol

    assert "run_phase11_5_quality_recovery.py" in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "gemma-4-31b-it" in workflow
    assert "gemma-4-26b-a4b-it" in workflow
    assert "gemini-3.5-flash-lite" in workflow
    assert "--candidate-max-block-chars 900" in workflow
    assert "--model-pause-seconds 2.0" in workflow
    assert "--max-output-tokens 2048" in workflow
    assert 'traffic["case_retrieval_operations"] == 12' in workflow
    assert 'traffic["generation_requests"] == 108' in workflow
    assert 'traffic["tavily_requests"] == 12' in workflow
    assert 'traffic["retries"] == 0' in workflow
    assert 'traffic["repair_requests"] == 0' in workflow
    assert 'decision["phase12_executed"] is False' in workflow
    assert 'decision["public_alpha_allowed"] is False' in workflow
    assert 'decision["superiority_claim_allowed"] is False' in workflow
    assert 'decision["merge_allowed"] is False' in workflow
    assert 'decision["release_decision"] == "no-go"' in workflow
    assert 'echo "$GEMINI_API_KEY"' not in workflow
    assert 'echo "$TAVILY_API_KEY"' not in workflow
    assert "gh release create" not in workflow.lower()
    assert "pypi publish" not in workflow.lower()
    assert "searxng/searxng:2026.7.26-b060c780d@sha256:" in workflow


def test_phase11_6_protocol_and_workflow_lock_citation_isolation_budget() -> None:
    root = Path(__file__).parents[1]
    protocol_path = root / "docs" / "benchmark-protocol-v14.md"
    workflow = (
        root / ".github" / "workflows" / "phase11-6-tavily-citation-isolation.yml"
    ).read_text(encoding="utf-8")
    protocol = protocol_path.read_text(encoding="utf-8")

    assert hashlib.sha256(protocol_path.read_bytes()).hexdigest() == (
        "d72aa29b989d74cff09ca211e291b5d2d58d86d684fe6bca5f75a0dac429c4e8"
    )
    assert "disclosed causal calibration, not an untouched evaluation" in protocol
    assert "byte-identical selected evidence" in protocol
    assert "exactly 72 native Gemini" in protocol
    assert "`gemma-4-26b-a4b-it` is blocking" in protocol
    assert "`gemini-3.5-flash-lite` is explicitly included" in protocol
    assert "No Phase 12 question" in protocol
    assert "community profile remains unchanged and free" in protocol
    assert "pull request remains draft" in protocol

    assert "run_phase11_6_tavily_citation_isolation.py" in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "gemma-4-31b-it" in workflow
    assert "gemma-4-26b-a4b-it" in workflow
    assert "gemini-3.5-flash-lite" in workflow
    assert "--model-pause-seconds 2.0" in workflow
    assert "--max-output-tokens 2048" in workflow
    assert "--retrieval-wall-time-seconds 30" in workflow
    assert "--generation-wall-time-seconds 60" in workflow
    assert "timeout-minutes: 90" in workflow
    assert 'traffic["case_retrieval_operations"] == 12' in workflow
    assert 'traffic["generation_requests"] == 72' in workflow
    assert 'traffic["tavily_requests"] == 12' in workflow
    assert 'traffic["retries"] == 0' in workflow
    assert 'traffic["repair_requests"] == 0' in workflow
    assert 'decision["quality_profile_promoted"] is False' in workflow
    assert 'decision["phase12_executed"] is False' in workflow
    assert 'decision["public_alpha_allowed"] is False' in workflow
    assert 'decision["superiority_claim_allowed"] is False' in workflow
    assert 'decision["merge_allowed"] is False' in workflow
    assert 'decision["release_decision"] == "no-go"' in workflow
    assert 'echo "$GEMINI_API_KEY"' not in workflow
    assert 'echo "$TAVILY_API_KEY"' not in workflow
    assert "gh release create" not in workflow.lower()
    assert "pypi publish" not in workflow.lower()
    assert "run_phase12" not in workflow.lower()
    assert "phase12-" not in workflow.lower()


def test_phase11_7_protocol_workflow_and_sealed_reserve_lock_fresh_budget() -> None:
    root = Path(__file__).parents[1]
    protocol_path = root / "docs" / "benchmark-protocol-v15.md"
    workflow = (root / ".github" / "workflows" / "phase11-7-fresh-confirmation.yml").read_text(
        encoding="utf-8"
    )
    protocol = protocol_path.read_text(encoding="utf-8")
    fresh_path = root / "benchmarks" / "data" / "phase11_7_fresh_confirmation_v1.json"
    reserve_path = root / "benchmarks" / "data" / "phase12_untouched_reserve_v1.json"

    assert hashlib.sha256(protocol_path.read_bytes()).hexdigest() == (
        "a38cfdd9f8bb4ca9ebf39caac212e7868a773b62c874e1738bc8a5ff9ea1088e"
    )
    assert hashlib.sha256(fresh_path.read_bytes()).hexdigest() == (
        "da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e"
    )
    assert hashlib.sha256(reserve_path.read_bytes()).hexdigest() == (
        "472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee"
    )
    assert "fresh, pre-registered confirmation calibration" in protocol
    assert "case count: exactly 24" in protocol
    assert "case count: exactly 96" in protocol
    assert "exactly 96 native Gemini API generation" in protocol
    assert "`gemma-4-26b-a4b-it` is not called and is not blocking" in protocol
    assert "Users choose their provider bundle, model client and API keys" in protocol
    assert "pull request remains draft" in protocol

    assert "run_phase11_7_fresh_confirmation.py" in workflow
    assert "phase11_7_fresh_confirmation_v1.json" in workflow
    assert "phase12_untouched_reserve_v1.json" in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" in workflow
    assert "gemma-4-31b-it" in workflow
    assert "gemma-4-26b-a4b-it" not in workflow
    assert "gemini-3.5-flash-lite" in workflow
    assert "--model-pause-seconds 2.0" in workflow
    assert "--max-output-tokens 2048" in workflow
    assert "--retrieval-wall-time-seconds 30" in workflow
    assert "--generation-wall-time-seconds 60" in workflow
    assert "timeout-minutes: 120" in workflow
    assert 'traffic["case_retrieval_operations"] == 24' in workflow
    assert 'traffic["generation_requests"] == 96' in workflow
    assert 'traffic["tavily_requests"] == 24' in workflow
    assert 'traffic["retries"] == 0' in workflow
    assert 'traffic["repair_requests"] == 0' in workflow
    assert 'decision["quality_profile_promoted"] is False' in workflow
    assert 'decision["phase12_executed"] is False' in workflow
    assert 'decision["public_alpha_allowed"] is False' in workflow
    assert 'decision["superiority_claim_allowed"] is False' in workflow
    assert 'decision["merge_allowed"] is False' in workflow
    assert 'decision["release_decision"] == "no-go"' in workflow
    assert 'echo "$GEMINI_API_KEY"' not in workflow
    assert 'echo "$TAVILY_API_KEY"' not in workflow
    assert "gh release create" not in workflow.lower()
    assert "pypi publish" not in workflow.lower()
    assert "run_phase12" not in workflow.lower()


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


def test_committed_phase10_result_matches_locked_protocol() -> None:
    root = Path(__file__).parents[1]
    result_path = root / "benchmarks" / "results" / "end_to_end_phase10_2026-07-29.json"
    result_bytes = result_path.read_bytes()
    assert hashlib.sha256(result_bytes).hexdigest() == (
        "95259c697c7b511dec0075a7782f07023f7e5ee48f8b863363794ec44c8bf263"
    )
    report = json.loads(result_bytes)

    assert report["schema_version"] == 1
    assert report["benchmark"] == "evidencemesh-end-to-end-phase10-v1"
    assert report["environment"]["commit_sha"] == ("ae9a0191dd01a175da649fe0b12dfb0424f905f6")
    assert report["dataset"]["sha256"] == (
        "feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032"
    )
    assert report["suite"]["manifest_sha256"] == (
        "b38b89d316219be7dbd249f4365e0801330eb469ff6cc9b4fdaffebe6510134f"
    )
    assert report["suite"]["sample_count"] == 12

    protocol = report["protocol"]
    assert protocol["models"] == [
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it",
        "gemini-3.5-flash-lite",
    ]
    assert protocol["arms"] == [
        "closed_book",
        "tavily_direct",
        "community",
        "quality",
    ]
    assert protocol["cache"] is False
    assert protocol["retry_policy"] == "none; no selective retry"
    assert report["traffic"] == {
        "generation_requests": 144,
        "generation_requests_expected": 144,
        "maximum_tavily_credits": 24,
        "maximum_tavily_requests": 24,
        "recorded_tavily_provider_queries": 24,
        "retries": 0,
        "retrieval_case_arm_operations": 36,
        "tavily_requests": 24,
    }

    retrieval = report["retrieval_metrics"]
    assert retrieval["tavily_direct"]["availability"]["numerator"] == 12
    assert retrieval["tavily_direct"]["answer_key_in_evidence"]["numerator"] == 10
    assert retrieval["community"]["availability"]["numerator"] == 5
    assert retrieval["community"]["answer_key_in_evidence"]["numerator"] == 1
    assert retrieval["quality"]["availability"]["numerator"] == 12
    assert retrieval["quality"]["answer_key_in_evidence"]["numerator"] == 5

    generated = report["generation_metrics"]["aggregate"]
    assert generated["closed_book"]["answer_key_covered"]["numerator"] == 0
    assert generated["tavily_direct"]["answer_key_covered"]["numerator"] == 27
    assert generated["community"]["answer_key_covered"]["numerator"] == 6
    assert generated["quality"]["answer_key_covered"]["numerator"] == 13
    assert generated["quality"]["citation_presence"]["numerator"] == 14
    assert generated["quality"]["citation_ids_valid"] == {
        "denominator": 14,
        "numerator": 14,
        "rate": 1.0,
    }

    paired = report["paired_answer_key_coverage"]
    assert paired["quality_vs_community"]["overall"] == {
        "baseline_wins": 1,
        "candidate_wins": 8,
        "net_gain": 7,
        "shared_hits": 5,
        "shared_misses": 22,
    }
    assert paired["quality_vs_tavily_direct"]["overall"] == {
        "baseline_wins": 14,
        "candidate_wins": 0,
        "net_gain": -14,
        "shared_hits": 13,
        "shared_misses": 9,
    }

    decision = report["decision"]
    assert decision["functional_gate_passed"] is False
    assert decision["cross_network_gate"] == {
        "completed_independent_networks": 1,
        "required_independent_networks": 2,
        "status": "not_testable",
    }
    assert decision["external_competitor_replication"] == "deferred_by_user"
    assert decision["stage_b_allowed"] is False
    assert decision["release_ready"] is False
    assert decision["release_decision"] == "no-go"

    prompt_groups: dict[tuple[str, str], set[tuple[str, int]]] = {}
    for outcome in report["generation_outcomes"]:
        key = (outcome["case_id"], outcome["arm"])
        prompt_groups.setdefault(key, set()).add(
            (outcome["prompt_sha256"], outcome["prompt_evidence_count"])
        )
    assert len(prompt_groups) == 48
    assert all(len(values) == 1 for values in prompt_groups.values())

    private_fields = {
        "question",
        "answer",
        "reference_answer",
        "title",
        "snippet",
        "content",
        "url",
        "evidence",
        "generated_answer",
    }
    assert all(not private_fields & set(outcome) for outcome in report["retrieval_outcomes"])
    assert all(not private_fields & set(outcome) for outcome in report["generation_outcomes"])
    assert report["privacy"] == {
        "answer_hashes_in_report": True,
        "evidence_text_in_report": False,
        "generated_answers_in_report": False,
        "questions_in_report": False,
        "reference_answers_in_report": False,
        "source_titles_or_urls_in_report": False,
    }
