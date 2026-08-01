from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.phase11_8_10b_p1_browsecomp_clarification import (
    canonical_sha256,
)
from benchmarks.run_phase11_8_10b_p1_browsecomp_clarification import (
    DEFAULT_SOURCE_LOCK_PATH,
    EXPECTED_AUTHORITY_PATHS,
    ClarificationLockError,
    _validate_authority_source_records,
    run,
    validate_source_locks,
)

ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "benchmarks/run_phase11_8_10b_p1_browsecomp_clarification.py"
WORKFLOW = ROOT / ".github/workflows/phase11-8-10b-p1-browsecomp-clarification.yml"
COMMIT = "b" * 40


def test_source_lock_predecessor_and_runner_are_deterministic() -> None:
    source_lock = validate_source_locks()
    first = run(methodology_commit_sha=COMMIT)
    second = run(methodology_commit_sha=COMMIT)

    assert first == second
    assert first["source_lock"] == source_lock
    assert first["predecessor_verification"]["verified_file_count"] == 4
    assert first["predecessor_verification"]["result_reproduced"] is True
    assert first["predecessor_verification"]["gate_summary"] == {
        "failed": 0,
        "passed": 16,
        "total": 16,
    }
    assert first["predecessor_verification"]["quality_decision"] == "no_go"
    assert first["predecessor_verification"]["candidate_suites_admitted"] == 0
    assert first["predecessor_verification"]["remaining_metadata_documents"] == 5


def test_runner_rejects_invalid_methodology_commit() -> None:
    with pytest.raises(ClarificationLockError, match="methodology_commit_sha"):
        run(methodology_commit_sha="main")


def test_source_lock_is_an_exact_allowlist() -> None:
    decoded = json.loads(DEFAULT_SOURCE_LOCK_PATH.read_text(encoding="utf-8"))
    records = decoded["authority_sources"]
    paths = tuple(record["relative_path"] for record in records)

    assert paths == EXPECTED_AUTHORITY_PATHS
    assert len(paths) == 14
    assert "benchmarks/__init__.py" in paths
    assert "benchmarks/data/phase11_8_10b_p1_source_locks_v1.json" not in paths
    assert not any(path.startswith("benchmarks/results/phase11_8_10b_p1") for path in paths)
    assert "CHANGELOG.md" not in paths
    assert decoded["source_set_sha256"] == canonical_sha256(records)
    for record in records:
        assert (
            hashlib.sha256((ROOT / record["relative_path"]).read_bytes()).hexdigest()
            == record["sha256"]
        )


def test_source_lock_rejects_non_allowlisted_path_before_open() -> None:
    decoded = json.loads(DEFAULT_SOURCE_LOCK_PATH.read_text(encoding="utf-8"))
    records = list(decoded["authority_sources"])
    records[-1] = {"relative_path": ".env", "sha256": "a" * 64}

    with pytest.raises(ClarificationLockError, match="path set drifted"):
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
            "importlib",
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


def test_runner_imports_no_repository_benchmark_module_before_source_lock() -> None:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    top_level_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.add(node.module)

    assert not any(
        module == "benchmarks" or module.startswith("benchmarks.") for module in top_level_imports
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
    assert "python -m benchmarks" not in workflow
    assert (
        workflow.count("uv run python benchmarks/run_phase11_8_10b_p1_browsecomp_clarification.py")
        == 2
    )
    assert "cmp /tmp/phase11_8_10b_p1_a.json /tmp/phase11_8_10b_p1_b.json" in workflow
