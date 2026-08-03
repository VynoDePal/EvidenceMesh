from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.phase11_8_10a_asset_preflight import AssetLockError
from benchmarks.run_phase11_8_10a_asset_preflight import (
    DEFAULT_INVENTORY_PATH,
    DEFAULT_SOURCE_LOCK_PATH,
    run,
    validate_source_locks,
)

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/phase11-8-10a-external-asset-locks.yml"
RUNNER = ROOT / "benchmarks/run_phase11_8_10a_asset_preflight.py"
COMMIT = "b" * 40


def test_source_lock_and_runner_are_deterministic() -> None:
    source_lock = validate_source_locks()
    first = run(methodology_commit_sha=COMMIT)
    second = run(methodology_commit_sha=COMMIT)

    assert first == second
    assert first["source_lock"] == source_lock
    assert first["outcome"] == "asset_integrity_lock_complete_policy_blocked"
    assert first["inventory"]["object_count"] == 37
    assert first["inventory"]["total_content_bytes"] == 5_013_088_007
    assert first["inventory"]["payload_content_accessed"] is False
    assert first["governance"]["phase_11_8_10b_authorized"] is False
    assert first["governance"]["phase_11_9_authorized"] is False
    assert first["governance"]["phase12_accesses"] == 0


def test_runner_rejects_invalid_methodology_commit() -> None:
    with pytest.raises(AssetLockError, match="methodology_commit_sha"):
        run(methodology_commit_sha="main")


def test_committed_inventory_hash_is_bound_by_manifest() -> None:
    manifest = json.loads(
        (ROOT / "benchmarks/data/phase11_8_10a_asset_locks_v1.json").read_text(encoding="utf-8")
    )
    expected = manifest["metadata_importer_policy"]["committed_inventory"]["sha256"]
    assert hashlib.sha256(DEFAULT_INVENTORY_PATH.read_bytes()).hexdigest() == expected


def test_source_lock_set_is_explicit_and_excludes_results_and_itself() -> None:
    source_locks = json.loads(DEFAULT_SOURCE_LOCK_PATH.read_text(encoding="utf-8"))
    paths = [record["relative_path"] for record in source_locks["authority_sources"]]

    assert paths == sorted(paths)
    assert "benchmarks/data/phase11_8_10a_source_locks_v1.json" not in paths
    assert not any(path.startswith("benchmarks/results/phase11_8_10a") for path in paths)
    assert "CHANGELOG.md" not in paths
    assert not any(
        any(marker in path.lower() for marker in ("phase12", "phase_12", "phase-12"))
        for path in paths
    )
    for required in (
        ".github/workflows/phase11-8-10a-external-asset-locks.yml",
        "benchmarks/data/phase11_8_10a_asset_locks_v1.json",
        "benchmarks/data/phase11_8_10a_object_inventory_v1.json",
        "benchmarks/phase11_8_10a_asset_preflight.py",
        "benchmarks/run_phase11_8_10a_asset_preflight.py",
        "docs/benchmark-protocol-v26.md",
        "tests/test_phase11_8_10a_asset_preflight.py",
        "tests/test_phase11_8_10a_runner.py",
    ):
        assert required in paths


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
        {"__import__", "compile", "eval", "exec", "getenv", "popen", "system", "urlopen"}
    )


def test_workflow_has_no_secret_binding_asset_transfer_or_artifact_upload() -> None:
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
    assert workflow.count("uv run python -m benchmarks.run_phase11_8_10a_asset_preflight") == 2
    assert "cmp /tmp/phase11_8_10a_a.json /tmp/phase11_8_10a_b.json" in workflow
