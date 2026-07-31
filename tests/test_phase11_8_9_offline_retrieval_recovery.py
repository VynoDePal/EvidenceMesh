from __future__ import annotations

import hashlib
import json
import os
import py_compile
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from benchmarks import run_phase11_8_9_offline_retrieval_recovery as offline

ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "benchmarks/run_phase11_8_9_offline_retrieval_recovery.py"
SOURCE_LOCKS = ROOT / "benchmarks/data/phase11_8_9_source_locks_v1.json"
FIXTURE = ROOT / "benchmarks/data/phase11_8_9_retrieval_fixtures_v1.json"
WORKFLOW = ROOT / ".github/workflows/phase11-8-9-offline-retrieval-recovery.yml"
LOCK_COMMIT_SHA = "1" * 40


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk(value: object) -> list[object]:
    values = [value]
    if isinstance(value, dict):
        for key, item in value.items():
            values.extend(_walk(key))
            values.extend(_walk(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_walk(item))
    return values


def _candidate_projection_for_direct_validation() -> tuple[object, str, object]:
    source_bytes, _manifest_raw, _locks, integrity = offline._load_source_locks(set())
    offline._bind_locked_runtime(
        source_bytes,
        str(integrity["computed_source_set_sha256"]),
    )
    fixture = json.loads(source_bytes[offline.RETRIEVAL_FIXTURE_PATH])
    case = fixture["cases"][2]
    query = case["query"]
    outcome = offline.select_candidate_v3(
        offline._raw_results(case),
        query,
        limit=case["limit"],
        max_per_domain=case["max_per_domain"],
    )
    return outcome, query, offline._project_candidate_v3(outcome, query)


def test_source_lock_manifest_is_complete_and_has_no_placeholders() -> None:
    manifest = json.loads(SOURCE_LOCKS.read_bytes())
    assert manifest["schema_version"] == "evidencemesh.phase11_8_9.source-locks.v1"
    authorities = manifest["authority_sources"]
    paths = [entry["relative_path"] for entry in authorities]
    assert len(paths) == len(set(paths))
    assert {
        "docs/benchmark-protocol-v25.md",
        "benchmarks/phase11_8_9_retrieval_candidate.py",
        "benchmarks/phase11_8_9_external_eval.py",
        "benchmarks/data/phase11_8_9_retrieval_fixtures_v1.json",
        "benchmarks/data/phase11_8_9_external_benchmarks_v1.json",
        "benchmarks/data/phase11_8_9_external_eval_fixtures_v1.json",
        "benchmarks/run_phase11_8_9_offline_retrieval_recovery.py",
        "tests/test_phase11_8_9_offline_retrieval_recovery.py",
        ".github/workflows/phase11-8-9-offline-retrieval-recovery.yml",
        "pyproject.toml",
        "uv.lock",
    }.issubset(paths)
    source_bytes: dict[str, bytes] = {}
    for entry in authorities:
        digest = entry["sha256"]
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
        assert _sha256(ROOT / entry["relative_path"]) == digest
        source_bytes[entry["relative_path"]] = (ROOT / entry["relative_path"]).read_bytes()
    assert manifest["source_set_sha256"] == offline.source_set_sha256(source_bytes)
    serialized = SOURCE_LOCKS.read_text()
    assert "__" not in serialized
    assert "PLACEHOLDER" not in serialized


def test_report_is_byte_deterministic_and_aggregate_only() -> None:
    first = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    second = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    assert offline.canonical_json_bytes(first) == offline.canonical_json_bytes(second)
    assert first["privacy"] == {
        "absolute_path_occurrences": 0,
        "forbidden_key_occurrences": 0,
        "passed": True,
        "web_url_occurrences": 0,
    }
    serialized = offline.canonical_json_bytes(first).decode()
    assert "https://" not in serialized
    assert "http://" not in serialized
    assert "/workspace/" not in serialized
    assert ("/" + "tmp/") not in serialized
    assert '"question"' not in serialized
    assert '"answer"' not in serialized
    assert '"snippet"' not in serialized
    assert '"url"' not in serialized
    assert '"query_id"' not in serialized
    assert '"document_id"' not in serialized
    assert '"per_query"' not in serialized


def test_report_has_exact_nineteen_gates_and_expected_conformance_outcome() -> None:
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    gates = report["gates"]
    assert len(gates) == 19
    assert [gate["number"] for gate in gates] == list(range(1, 20))
    assert report["decision"]["gate_count"] == 19
    assert report["decision"]["passed_gate_count"] == 12
    assert report["decision"]["offline_outcome"] == "engineering_conformance_only"
    assert report["decision"]["external_quality_passed"] is False
    assert all(gates[index - 1]["passed"] is False for index in range(10, 12))
    assert all(gates[index - 1]["passed"] is False for index in range(13, 18))
    assert all(
        gates[index - 1]["status"] == "not_evaluated" for index in (*range(10, 12), *range(13, 18))
    )
    assert all(gates[index - 1]["passed"] is True for index in sorted(offline.LOCAL_GATE_NUMBERS))


def test_historical_eight_of_thirteen_no_go_is_immutable() -> None:
    historical = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)["historical_boundary"]
    assert historical == {
        "classification": "development_diagnostic_only",
        "diagnostic_status": "retrieval_limited_inconclusive",
        "equal_cap_prompt_proxy_hits": 16,
        "gate_count": 13,
        "passed_gate_count": 8,
        "quality_gate_reuse_allowed": False,
        "release_decision": "no-go",
        "selected_proxy_hits": 18,
        "v1_prompt_proxy_hits": 17,
        "v2_prompt_proxy_hits": 17,
        "v2_retention_denominator": 18,
        "v2_retention_numerator": 17,
        "v2_retention_rate": 0.944444,
        "v2_vs_equal_net_gain": 1,
        "v2_vs_v1_net_gain": 0,
        "validation_passed": True,
    }


def test_local_fixture_is_conformance_only_and_matches_registered_oracles() -> None:
    fixture = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)["fixture_evaluation"]
    assert fixture["scope"] == "local_synthetic_engineering_conformance"
    assert fixture["real_external_score"] is False
    assert fixture["case_count"] == 5
    assert fixture["in_process_replays_per_arm"] == 2
    assert fixture["independent_process_replay_status"] == "required_workflow_cmp"
    assert fixture["control_expected_selection_match_cases"] == 5
    assert fixture["candidate_expected_selection_match_cases"] == 5
    assert fixture["lineage_invariant_cases"] == 5
    assert fixture["projection_invariant_cases"] == 5
    assert fixture["replay_invariant_cases"] == 5
    assert fixture["stage_invariant_cases"] == 5
    assert fixture["evaluator_only_fields_reached_candidate"] is False
    assert fixture["control_projector_v2_invocation_cases"] == 5
    registry = fixture["conformance_registry"]
    assert registry["registered_requirement_count"] == 43
    assert registry["requirements_with_structural_evidence"] == 43
    assert registry["registry_complete"] is True
    receipt = fixture["conformance_receipt"]
    assert receipt["status"] == "passed"
    assert receipt["collected"] == receipt["passed"]
    assert receipt["failures"] == receipt["errors"] == receipt["skipped"] == 0
    assert receipt["registered_test_count"] == receipt["registered_tests_covered"]
    assert fixture["conformance_receipt_covers_registry"] is True
    arms = fixture["arm_aggregates"]
    assert arms["pre_v3_pipeline_control"]["synthetic_utility_canonical_hits"] == 4
    assert arms["retrieval_candidate_v3"]["synthetic_utility_canonical_hits"] == 9
    assert arms["pre_v3_pipeline_control"]["selection_family"] == offline.BASELINE_FAMILY
    assert arms["pre_v3_pipeline_control"]["projection_family"] == offline.CONTROL_PROJECTION_FAMILY
    assert arms["retrieval_candidate_v3"]["selection_family"] == offline.CANDIDATE_FAMILY
    assert (
        arms["retrieval_candidate_v3"]["projection_family"] == offline.CANDIDATE_PROJECTION_FAMILY
    )
    assert (
        arms["retrieval_candidate_v3"]["funnel"]["selected"]
        <= arms["retrieval_candidate_v3"]["funnel"]["eligible"]
    )
    assert (
        arms["pre_v3_pipeline_control"]["funnel"]["selected"]
        <= arms["pre_v3_pipeline_control"]["funnel"]["eligible"]
    )


def test_control_really_invokes_locked_v2_projector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    calls = 0
    original = offline.candidate_project_blocks_v2

    def recording_projector(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(offline, "candidate_project_blocks_v2", recording_projector)
    fixture = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)["fixture_evaluation"]
    assert calls >= fixture["case_count"]
    assert fixture["control_projector_v2_invocation_cases"] == fixture["case_count"]


def test_duplicate_citation_or_empty_text_is_rejected_directly() -> None:
    outcome, query, projection = _candidate_projection_for_direct_validation()
    evidence = projection.evidence
    assert len(evidence) >= 2
    duplicate = replace(
        projection,
        evidence=(
            evidence[0],
            replace(evidence[1], citation_id=evidence[0].citation_id),
            *evidence[2:],
        ),
    )
    empty = replace(
        projection,
        evidence=(replace(evidence[0], text=""), *evidence[1:]),
    )
    assert offline._validate_projection(outcome, query, duplicate, candidate=True) is False
    assert offline._validate_projection(outcome, query, empty, candidate=True) is False


@pytest.mark.parametrize("mutation", ["duplicate", "empty"])
def test_projection_mutation_makes_gate_seven_fail(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    original = offline._project_candidate_v3

    def mutating_projector(outcome: object, query: str) -> object:
        projection = original(outcome, query)
        evidence = projection.evidence
        if not evidence:
            return projection
        if mutation == "duplicate" and len(evidence) >= 2:
            mutated = (
                evidence[0],
                replace(evidence[1], citation_id=evidence[0].citation_id),
                *evidence[2:],
            )
        else:
            mutated = (replace(evidence[0], text=""), *evidence[1:])
        return replace(projection, evidence=mutated)

    monkeypatch.setattr(offline, "_project_candidate_v3", mutating_projector)
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    assert report["gates"][6]["passed"] is False
    assert report["decision"]["offline_outcome"] == "invalid"


def test_external_assets_are_not_claimed_or_accessed() -> None:
    external = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)["external_evaluation"]
    assert external["status"] == "external_evaluation_not_run"
    assert external["complete_locked_assets_present"] is False
    assert external["asset_license_status"] == "unresolved"
    assert external["registry_suite_count"] == 2
    assert external["unresolved_asset_license_count"] == 2
    assert external["explicit_asset_license_entry_count"] == 2
    assert external["license_boundary_passed"] is True
    assert external["registry_validation_passed"] is True
    assert set(external["suite_statuses"]) == {"bright", "browsecomp_plus"}
    assert all(
        value
        == {
            "reason_category": "locked_assets_absent_or_inadmissible",
            "status": "not_evaluated",
        }
        for value in external["suite_statuses"].values()
    )
    adapter = external["synthetic_adapter_conformance"]
    assert adapter["real_external_score"] is False
    assert adapter["status"] == "passed"


def test_runner_binds_zero_traffic_and_keeps_governance_closed() -> None:
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    assert set(report["traffic"].values()) == {0}
    decision = report["decision"]
    assert decision["merge_allowed"] is False
    assert decision["phase11_9_authorized"] is False
    assert decision["phase12_authorized"] is False
    assert decision["product_defaults_change_allowed"] is False
    assert decision["pull_request_remains_draft_required"] is True
    assert decision["pull_request_state_verified_by_runner"] is False
    assert (
        decision["pull_request_state_verification_required"]
        == "externally_verified_by_github_process"
    )
    assert decision["release_allowed"] is False
    assert decision["release_decision"] == "no-go"
    assert decision["superiority_claim_allowed"] is False
    assert set(report["resource_diagnostics"].values()) == {
        "not_applicable_without_external_assets"
    }


class _PresenceOnlyEnvironment:
    def __init__(self, present: set[str]) -> None:
        self.present = present

    def __contains__(self, key: object) -> bool:
        return key in self.present

    def __getitem__(self, key: object) -> object:
        raise AssertionError(f"secret value was read for {type(key).__name__}")


def test_secret_presence_probe_counts_names_without_reading_values() -> None:
    environment = _PresenceOnlyEnvironment(set(offline.BOUND_SECRET_NAMES))
    assert offline._bound_secret_count(environment) == len(offline.BOUND_SECRET_NAMES)


@pytest.mark.parametrize("secret_name", offline.BOUND_SECRET_NAMES)
def test_bound_secret_presence_fails_gate_five_without_exposing_names_or_values(
    monkeypatch: pytest.MonkeyPatch,
    secret_name: str,
) -> None:
    sentinel_value = "sentinel-must-not-be-emitted"
    monkeypatch.setenv(secret_name, sentinel_value)
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    assert report["traffic"]["bound_secrets"] == 1
    assert report["gates"][4]["passed"] is False
    assert report["decision"]["offline_outcome"] == "invalid"
    serialized = offline.canonical_json_bytes(report).decode()
    assert secret_name not in serialized
    assert sentinel_value not in serialized


def test_arbitrary_commit_is_only_an_unverified_publication_reference() -> None:
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    reference = report["publication_reference"]
    assert reference == {
        "commit_sha": LOCK_COMMIT_SHA,
        "required_external_verification": "externally_verified_by_github_process",
        "runner_verified_commit_binding": False,
        "verification_status": "not_verified_by_runner",
    }
    assert report["source_integrity"]["source_set_byte_authority"] is True
    assert (
        report["source_integrity"]["computed_source_set_sha256"]
        == report["source_integrity"]["declared_source_set_sha256"]
    )


def test_gate_outcome_fails_closed_when_a_local_gate_fails() -> None:
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    gates = [dict(gate) for gate in report["gates"]]
    gates[4]["passed"] = False
    assert offline._derive_offline_outcome(gates, report["external_evaluation"]) == "invalid"


def test_gate_outcome_distinguishes_external_fail_and_pass() -> None:
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    external = {
        **report["external_evaluation"],
        "status": "evaluated",
        "suite_statuses": {
            suite: {"status": "evaluated"} for suite in offline.EXPECTED_EXTERNAL_SUITES
        },
    }
    failing = [dict(gate) for gate in report["gates"]]
    for number in offline.EXTERNAL_GATE_NUMBERS:
        failing[number - 1]["passed"] = number != 13
    assert offline._derive_offline_outcome(failing, external) == "external_fail"
    passing = [dict(gate) for gate in failing]
    for number in offline.EXTERNAL_GATE_NUMBERS:
        passing[number - 1]["passed"] = True
    assert offline._derive_offline_outcome(passing, external) == "offline_engineering_pass"


def test_runner_never_reads_a_phase12_path(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[str] = []
    original = Path.read_bytes

    def recording_read_bytes(path: Path) -> bytes:
        observed.append(str(path))
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", recording_read_bytes)
    offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    assert observed
    assert all("phase12" not in value.casefold() for value in observed)
    assert all("phase_12" not in value.casefold() for value in observed)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "../outside",
        "/absolute/path",
        "benchmarks/data/phase12_forbidden.json",
        "benchmarks/data/phase_12_forbidden.json",
    ],
)
def test_source_lock_paths_fail_closed(value: str) -> None:
    with pytest.raises(ValueError):
        offline._safe_relative_path(value)


def test_repository_reader_rejects_symlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    real = tmp_path / "real.txt"
    real.write_text("locked")
    link = tmp_path / "linked.txt"
    link.symlink_to(real)
    monkeypatch.setattr(offline, "REPOSITORY_ROOT", tmp_path)
    with pytest.raises(ValueError, match="repository_source_symlink_forbidden"):
        offline._read_repository_file("linked.txt")


def test_locked_module_executes_preflight_bytes_despite_source_and_pyc_swap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = "benchmarks/locked_probe.py"
    source_path = tmp_path / relative_path
    source_path.parent.mkdir(parents=True)
    source_path.write_text("VALUE = 'unlocked-pyc'\n")
    py_compile.compile(
        str(source_path),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    source_path.write_text("VALUE = 'unlocked-path'\n")
    locked_raw = b"VALUE = 'locked-preflight-bytes'\n"
    module_name = "_evidencemesh_exact_byte_probe"
    monkeypatch.setattr(offline, "REPOSITORY_ROOT", tmp_path)
    try:
        module = offline._load_exact_locked_module(
            module_name,
            relative_path,
            {relative_path: locked_raw},
        )
        assert module.VALUE == "locked-preflight-bytes"
        assert module.__file__ == str(source_path)
        assert module.__loader__ is None
        assert module.__package__ == ""
        assert module.__spec__ is None
        assert module.__cached__ is None
    finally:
        sys.modules.pop(module_name, None)


def test_isolated_pytest_prefix_ignores_cwd_pytest_shadow(tmp_path: Path) -> None:
    marker = tmp_path / "shadow-executed"
    (tmp_path / "pytest.py").write_text(
        "from pathlib import Path\n"
        "Path('shadow-executed').write_text('forged')\n"
        "raise SystemExit(91)\n"
    )
    completed = subprocess.run(  # noqa: S603 - fixed isolated interpreter probe
        [
            sys.executable,
            *offline.CONFORMANCE_PYTEST_PREFIX,
            "--version",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0
    assert not marker.exists()


def test_gate9_runs_only_from_materialized_locked_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_bytes, manifest_raw, _locks, integrity = offline._load_source_locks(set())
    fixture = json.loads(source_bytes[offline.RETRIEVAL_FIXTURE_PATH])
    test_source_bytes = (
        source_bytes["tests/test_phase11_8_9_retrieval_candidate.py"],
        source_bytes["tests/test_phase11_8_9_external_eval.py"],
        source_bytes["tests/test_phase11_8_9_offline_retrieval_recovery.py"],
    )
    _summary, registered_test_names = offline._validate_conformance_registry(
        fixture,
        test_source_bytes,
    )
    poison_root = tmp_path / "poison-repository"
    poison_root.mkdir()
    (poison_root / "pytest.py").write_text(
        "raise RuntimeError('repository pytest shadow executed')\n"
    )
    original_read_bytes = Path.read_bytes
    repository_test_paths = {
        (ROOT / relative_path).resolve()
        for relative_path in (
            "tests/test_phase11_8_9_retrieval_candidate.py",
            "tests/test_phase11_8_9_external_eval.py",
            "tests/test_phase11_8_9_offline_retrieval_recovery.py",
        )
    }

    def reject_repository_test_reread(path: Path) -> bytes:
        if path.resolve() in repository_test_paths:
            raise AssertionError("Gate 9 reread a repository test source")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_repository_test_reread)
    monkeypatch.setattr(offline, "REPOSITORY_ROOT", poison_root)
    offline._CONFORMANCE_RECEIPT_CACHE.clear()
    receipt = offline._run_conformance_receipt(
        str(integrity["computed_source_set_sha256"]),
        registered_test_names,
        source_bytes,
        manifest_raw,
    )
    assert receipt["status"] == "passed"
    assert receipt["passed"] == receipt["collected"]
    assert receipt["registered_tests_covered"] == len(registered_test_names)


def test_locked_modules_ignore_pythonpath_package_injection(tmp_path: Path) -> None:
    injected = tmp_path / "injected"
    package = injected / "benchmarks"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "raise RuntimeError('unlocked benchmarks package executed')\n"
    )
    output = tmp_path / "result.json"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(injected)
    for secret_name in offline.BOUND_SECRET_NAMES:
        environment.pop(secret_name, None)
    subprocess.run(  # noqa: S603 - fixed interpreter and repository runner
        [
            sys.executable,
            str(RUNNER),
            "--lock-commit-sha",
            LOCK_COMMIT_SHA,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
    )
    report = json.loads(output.read_bytes())
    assert report["source_capability_audit"]["locked_module_count"] == 3
    assert report["source_capability_audit"]["locked_module_origin_hash_passed"] is True


@pytest.mark.parametrize("value", ["", "abc", "f" * 39, "F" * 40, "g" * 40])
def test_invalid_lock_commit_sha_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="invalid_lock_commit_sha"):
        offline.run(lock_commit_sha=value)


def test_cli_requires_commit_and_emits_same_canonical_result(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    command = [
        sys.executable,
        str(RUNNER),
        "--lock-commit-sha",
        LOCK_COMMIT_SHA,
    ]
    subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned runner
        [*command, "--output", str(first)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned runner
        [*command, "--output", str(second)],
        cwd=ROOT,
        check=True,
    )
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_bytes()) == offline.run(lock_commit_sha=LOCK_COMMIT_SHA)


def test_workflow_is_read_only_local_and_secret_free() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    assert workflow["permissions"] == {"contents": "read"}
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) <= {"pull_request", "workflow_dispatch"}
    source = WORKFLOW.read_text().casefold()
    assert "persist-credentials: false" in source
    assert "phase11_8_9_offline_retrieval_recovery.py" in source
    assert "phase11_8_9_external_eval.py" in source
    assert "phase11_8_9_retrieval_candidate.py" in source
    assert "phase11_8_9_offline_retrieval_recovery_2026-07-31.json" in source
    assert "phase11_8_9_offline_retrieval_recovery_2026-07-31.md" in source
    assert "tests/test_phase11_8_9_result.py" in source
    assert "- changelog.md" in source
    assert source.count("uv run python -i") == 2
    manifest = json.loads(SOURCE_LOCKS.read_bytes())
    authority_paths = {entry["relative_path"] for entry in manifest["authority_sources"]}
    for relative_path in authority_paths | {offline.SOURCE_LOCK_MANIFEST_PATH}:
        assert f"- {relative_path.casefold()}" in source
    assert "upload-artifact" not in source
    assert "secrets." not in source
    assert "tavily_api_key" not in source
    assert "gemini_api_key" not in source
    assert "authorize" not in source
    assert "curl " not in source
    assert "wget " not in source
    assert "git push" not in source
    assert "pull-requests: write" not in source


def test_measured_local_gate_evidence_and_strict_public_schema_pass() -> None:
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    assert report["source_capability_audit"]["passed"] is True
    assert report["source_capability_audit"]["exact_byte_module_loader_audit_passed"] is True
    assert report["source_capability_audit"]["forbidden_capability_violation_count"] == 0
    assert report["path_access_audit"]["passed"] is True
    assert report["path_access_audit"]["phase12_path_access_count"] == 0
    assert report["public_schema"] == {
        "failed_contract_count": 0,
        "passed": True,
        "strict_contract_count": 18,
    }
    governance = report["governance"]
    assert governance["passed"] is True
    assert governance["exact_source_scope_passed"] is True
    assert governance["product_runtime_mutation_path_count"] == 0
    assert governance["product_default_mutation_path_count"] == 0
    assert governance["release_mutation_path_count"] == 0
    assert governance["pull_request_state_verified_by_runner"] is False


def test_final_payload_injection_fails_privacy_and_strict_schema() -> None:
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    mutated = {
        **report,
        "injected_final_section": {
            "url": "https://forbidden.example.test/private",
        },
    }
    audit = offline._audit_final_public_payload(mutated)
    assert audit["privacy"]["passed"] is False
    assert audit["public_schema"]["passed"] is False


def test_public_payload_has_no_per_case_or_identifier_values() -> None:
    report = offline.run(lock_commit_sha=LOCK_COMMIT_SHA)
    fixture = json.loads(FIXTURE.read_bytes())
    public_values = {value for value in _walk(report) if isinstance(value, str)}
    forbidden: set[str] = set()
    for case in fixture["cases"]:
        forbidden.add(case["id"])
        forbidden.add(case["query"])
        forbidden.update(case["utility_result_ids"])
        forbidden.update(case["expected_baseline_selected_ids"])
        forbidden.update(case["expected_candidate_selected_ids"])
        for raw in case["raw_results"]:
            forbidden.update(
                {
                    raw["result_id"],
                    raw["title"],
                    raw["url"],
                    raw["snippet"],
                    raw["query"],
                }
            )
    assert public_values.isdisjoint(forbidden)
