from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import verify_alpha_a1_p3_1_launcher_correction as gate

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "alpha" / "alpha_a1_p3_1_launcher_correction_policy_v1.json"
PROTOCOL = ROOT / "docs" / "alpha-a1-p3-1-launcher-correction-gate-v1.md"
WORKFLOW = ROOT / ".github" / "workflows" / "alpha-a1-p3-1-launcher-correction.yml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_policy_preserves_failed_run_and_freezes_corrective_budget() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["schema_version"] == ("evidencemesh.alpha-a1-p3-1-launcher-correction-policy.v1")
    assert policy["historical_failure"] == {
        "commit_sha": gate.FAILED_COMMIT,
        "conclusion": "failure",
        "job_id": gate.FAILED_JOB_ID,
        "p0_mcp_stdio_health": True,
        "p0_installability_passed": True,
        "p3_host_invocations": 0,
        "p3_mcp_server_launches": 0,
        "p3_npm_install_attempts": 0,
        "reason": "ModuleNotFoundError: No module named 'scripts'",
        "run_id": gate.FAILED_RUN_ID,
        "tree_sha": gate.FAILED_TREE,
    }
    budgets = policy["budgets"]
    assert budgets["corrective_commit_publications"] == 1
    assert budgets["corrective_workflow_runs"] == 1
    assert budgets["historical_run_reruns"] == 0
    assert budgets["workflow_retries"] == 0
    assert budgets["external_model_requests"] == 0
    assert budgets["runtime_network_requests"] == 0
    assert not any(policy["authority"].values())


def test_corrective_and_cumulative_scope_are_exact() -> None:
    assert gate.BASE_COMMIT == "3cc75a33790be353a74641034a3c5210dfc7bc17"
    assert gate.BASE_TREE == "21abc6024a08a5528710a5fd8e49630c8fca2c9d"
    assert gate.FAILED_COMMIT == "38eb63ade7024ab32963f894c719fa190fe9346a"
    assert gate.FAILED_TREE == "c21496bf690a8c2844a8957b7af12de72cf5b7ad"
    assert gate.CORRECTIVE_CHANGED_PATHS == {
        ".github/workflows/alpha-a1-p3-1-launcher-correction.yml": "A",
        "alpha/alpha_a1_p3_1_launcher_correction_policy_v1.json": "A",
        "docs/alpha-a1-p3-1-launcher-correction-gate-v1.md": "A",
        "scripts/verify_alpha_a1_p3_1_launcher_correction.py": "A",
        "tests/test_alpha_a1_p3_1_launcher_correction.py": "A",
    }
    assert len(gate.CUMULATIVE_CHANGED_PATHS) == 13


def test_failed_checkpoint_inputs_remain_byte_identical() -> None:
    for relative, expected in gate.FAILED_CHECKPOINT_IMMUTABLE_SHA256.items():
        assert _sha256(ROOT / relative) == expected


def test_workflow_uses_new_one_shot_label_and_exact_module_entrypoint() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Alpha A1-P3.1 launcher correction" in workflow
    assert "types: [labeled]" in workflow
    assert "github.event.label.name == 'alpha-a1-p3-1-authorized'" in workflow
    assert "github.event.label.name == 'alpha-a1-p3-authorized'" not in workflow
    assert '"$python_path" -m scripts.verify_alpha_a1_p3_1_launcher_correction' in workflow
    assert "fetch-depth: 3" in workflow
    assert "upload-artifact" not in workflow
    assert "npm publish" not in workflow


def test_exact_module_entrypoint_imports_from_repository_root() -> None:
    environment = {
        "HOME": os.devnull,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "PYTHONNOUSERSITE": "1",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_alpha_a1_p3_1_launcher_correction",
            "--help",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0
    assert "Alpha A1-P3.1 launcher correction" in completed.stdout
    assert completed.stderr == ""


def test_name_status_parser_rejects_malformed_or_duplicate_paths() -> None:
    assert gate._name_status("M\ta\nA\tb", "scope") == {"a": "M", "b": "A"}
    with pytest.raises(gate.p3.GateError, match="malformed"):
        gate._name_status("missing-tab", "scope")
    with pytest.raises(gate.p3.GateError, match="duplicate"):
        gate._name_status("A\ta\nM\ta", "scope")


def test_scope_validator_locks_both_commits_trees_and_path_sets(monkeypatch) -> None:
    expected_head = "a" * 40
    direct = "\n".join(
        f"{status}\t{path}" for path, status in gate.CORRECTIVE_CHANGED_PATHS.items()
    )
    cumulative = "\n".join(f"A\t{path}" for path in gate.CUMULATIVE_CHANGED_PATHS)

    def fake_git(arguments, **_kwargs) -> str:
        table = {
            ("rev-parse", "HEAD"): expected_head,
            ("rev-list", "--parents", "-n", "1", expected_head): (
                f"{expected_head} {gate.FAILED_COMMIT}"
            ),
            ("rev-list", "--parents", "-n", "1", gate.FAILED_COMMIT): (
                f"{gate.FAILED_COMMIT} {gate.BASE_COMMIT}"
            ),
            ("rev-parse", f"{gate.BASE_COMMIT}^{{tree}}"): gate.BASE_TREE,
            ("rev-parse", f"{gate.FAILED_COMMIT}^{{tree}}"): gate.FAILED_TREE,
            (
                "diff",
                "--name-status",
                "--no-renames",
                gate.FAILED_COMMIT,
                expected_head,
            ): direct,
            (
                "diff",
                "--name-status",
                "--no-renames",
                gate.BASE_COMMIT,
                expected_head,
            ): cumulative,
        }
        return table[tuple(arguments)]

    monkeypatch.setattr(gate, "_git", fake_git)
    gate._validate_scope(ROOT, expected_head, Path("/usr/bin/git"), 0.0)


def test_scope_adapter_is_single_use_and_restored(monkeypatch, tmp_path: Path) -> None:
    original = gate.p3._validate_scope
    monkeypatch.setattr(gate, "_validate_scope", lambda *_args: None)

    def fake_run_gate(**kwargs):
        validator = gate.p3._validate_scope
        validator(ROOT, "a" * 40, Path("/usr/bin/git"), 0.0)
        validator(ROOT, "a" * 40, Path("/usr/bin/git"), 0.0)
        return kwargs

    monkeypatch.setattr(gate.p3, "run_gate", fake_run_gate)
    with pytest.raises(gate.p3.GateError, match="more than once"):
        gate.run_gate(
            work_root=tmp_path,
            p0_receipt=tmp_path / "receipt.json",
            expected_head="a" * 40,
            output=tmp_path / "p3-runtime" / "gate-receipt.json",
            git_executable=Path("/usr/bin/git"),
            node_executable=Path("/usr/bin/node"),
            npm_executable=Path("/usr/bin/npm"),
            strace_executable=Path("/usr/bin/strace"),
        )
    assert gate.p3._validate_scope is original


def test_protocol_states_non_evaluation_and_authority_boundary() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    assert "A1-P3 remains non-evaluated" in protocol
    assert "before installing Gemini CLI" in protocol
    assert "It is not a real Gemini model" in protocol
    assert "External model, provider, search, document" in protocol
    assert "authorizes neither merge, Phase 12" in protocol
