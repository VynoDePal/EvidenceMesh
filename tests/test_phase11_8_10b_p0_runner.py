from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.phase11_8_10b_p0_policy_lock import PolicyLockError, canonical_sha256
from benchmarks.run_phase11_8_10b_p0_policy_lock import (
    DEFAULT_SOURCE_LOCK_PATH,
    EXPECTED_AUTHORITY_PATHS,
    _validate_authority_source_records,
    run,
    validate_source_locks,
)

ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "benchmarks/run_phase11_8_10b_p0_policy_lock.py"
WORKFLOW = ROOT / ".github/workflows/phase11-8-10b-p0-policy-comparability-lock.yml"
COMMIT = "b" * 40


def test_source_lock_predecessor_and_runner_are_deterministic() -> None:
    source_lock = validate_source_locks()
    first = run(methodology_commit_sha=COMMIT)
    second = run(methodology_commit_sha=COMMIT)

    assert first == second
    assert first["source_lock"] == source_lock
    assert first["predecessor_verification"]["verified_file_count"] == 5
    assert first["predecessor_verification"]["quality_decision"] == "no_go"
    assert first["predecessor_verification"]["real_external_score"] is False
    assert first["predecessor_verification"]["external_evaluation_status"] == "not_run"
    assert first["governance"]["phase_11_8_10b_acquisition_authorized"] is False
    assert first["governance"]["phase_11_9_authorized"] is False
    assert first["governance"]["phase_12_authorized"] is False


def test_runner_rejects_invalid_methodology_commit() -> None:
    with pytest.raises(PolicyLockError, match="methodology_commit_sha"):
        run(methodology_commit_sha="main")


def test_source_lock_set_is_exact_ordered_and_excludes_results_and_itself() -> None:
    decoded = json.loads(DEFAULT_SOURCE_LOCK_PATH.read_text(encoding="utf-8"))
    records = decoded["authority_sources"]
    paths = [record["relative_path"] for record in records]

    assert tuple(paths) == EXPECTED_AUTHORITY_PATHS
    assert len(paths) == 12
    assert "benchmarks/data/phase11_8_10b_p0_source_locks_v1.json" not in paths
    assert not any(path.startswith("benchmarks/results/phase11_8_10b_p0") for path in paths)
    assert "CHANGELOG.md" not in paths
    assert not any(
        any(marker in path.lower() for marker in ("phase12", "phase_12", "phase-12"))
        for path in paths
    )
    for required in (
        ".github/workflows/phase11-8-10b-p0-policy-comparability-lock.yml",
        "benchmarks/data/phase11_8_10a_asset_locks_v1.json",
        "benchmarks/data/phase11_8_10a_object_inventory_v1.json",
        "benchmarks/data/phase11_8_10a_source_locks_v1.json",
        "benchmarks/data/phase11_8_10b_p0_policy_comparability_lock_v1.json",
        "benchmarks/phase11_8_10b_p0_policy_lock.py",
        "benchmarks/results/phase11_8_10a_asset_reconnaissance_2026-07-31.json",
        "benchmarks/run_phase11_8_10b_p0_policy_lock.py",
        "docs/benchmark-protocol-v26.md",
        "docs/benchmark-protocol-v27.md",
        "tests/test_phase11_8_10b_p0_policy_lock.py",
        "tests/test_phase11_8_10b_p0_runner.py",
    ):
        assert required in paths
    assert decoded["source_set_sha256"] == canonical_sha256(records)
    for record in records:
        assert (
            hashlib.sha256((ROOT / record["relative_path"]).read_bytes()).hexdigest()
            == record["sha256"]
        )


def test_source_lock_rejects_a_non_allowlisted_path_before_open() -> None:
    decoded = json.loads(DEFAULT_SOURCE_LOCK_PATH.read_text(encoding="utf-8"))
    records = list(decoded["authority_sources"])
    records[-1] = {"relative_path": ".env", "sha256": "a" * 64}

    with pytest.raises(PolicyLockError, match="path set drifted"):
        _validate_authority_source_records(records)


def test_runner_has_no_network_environment_process_or_dynamic_code_capability() -> None:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert imported_roots.isdisjoint(
        {
            "aiohttp",
            "asyncio",
            "base64",
            "boto3",
            "datasets",
            "google",
            "huggingface_hub",
            "httpx",
            "mistralai",
            "openai",
            "os",
            "requests",
            "socket",
            "subprocess",
            "tavily",
            "urllib",
        }
    )
    assert calls.isdisjoint(
        {
            "__import__",
            "b64decode",
            "compile",
            "decrypt",
            "eval",
            "exec",
            "getenv",
            "load_dataset",
            "popen",
            "system",
            "urlopen",
        }
    )


def test_workflow_has_no_secret_binding_benchmark_transfer_or_artifact_upload() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8").lower()
    for forbidden in (
        "secrets.",
        "curl ",
        "wget ",
        "huggingface-cli",
        "load_dataset",
        "upload-artifact",
        "download-artifact",
        "gemini",
        "tavily",
        "openai",
    ):
        assert forbidden not in workflow
    assert workflow.count("uv run python -m benchmarks.run_phase11_8_10b_p0_policy_lock") == 2
    assert "cmp /tmp/phase11_8_10b_p0_a.json /tmp/phase11_8_10b_p0_b.json" in workflow
    for predecessor_path in (
        "benchmarks/data/phase11_8_10a_asset_locks_v1.json",
        "benchmarks/data/phase11_8_10a_object_inventory_v1.json",
        "benchmarks/data/phase11_8_10a_source_locks_v1.json",
        "benchmarks/results/phase11_8_10a_asset_reconnaissance_2026-07-31.json",
    ):
        assert predecessor_path in workflow
