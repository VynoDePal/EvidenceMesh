from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import verify_alpha_a1_p3_2_optional_leaf_correction as gate

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "alpha" / "alpha_a1_p3_2_optional_leaf_correction_policy_v1.json"
PROTOCOL = ROOT / "docs" / "alpha-a1-p3-2-optional-leaf-correction-gate-v1.md"
WORKFLOW = ROOT / ".github" / "workflows" / "alpha-a1-p3-2-optional-leaf-correction.yml"
LOCK = ROOT / "alpha" / "a1-p3-gemini-cli" / "package-lock.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _harness(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(LOCK, tmp_path / "package-lock.json")
    source_lock = json.loads(LOCK.read_text(encoding="utf-8"))
    gemini_relative = "node_modules/@google/gemini-cli"
    modules = tmp_path / "node_modules"
    package_root = modules / "@google" / "gemini-cli"
    package_root.mkdir(parents=True)
    bin_root = modules / ".bin"
    bin_root.mkdir()
    (bin_root / "gemini").symlink_to("../@google/gemini-cli/bundle/gemini.js")
    (modules / ".package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {gemini_relative: source_lock["packages"][gemini_relative]},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_policy_freezes_exact_leaf_oracle_and_one_shot_budget() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["schema_version"] == (
        "evidencemesh.alpha-a1-p3-2-optional-leaf-correction-policy.v1"
    )
    assert policy["entry_criteria"]["exact_parent_commit"] == gate.FAILED_P3_1_COMMIT
    assert policy["entry_criteria"]["exact_parent_tree"] == gate.FAILED_P3_1_TREE
    assert policy["optional_dependency_oracle"]["exact_optional_leaf_count"] == 11
    assert policy["optional_dependency_oracle"]["exact_optional_leaves_must_be_absent"] is True
    budgets = policy["budgets"]
    assert budgets["corrective_commit_publications"] == 1
    assert budgets["corrective_workflow_runs"] == 1
    assert budgets["dependency_install_attempts"] == 1
    assert budgets["host_invocations"] == 1
    assert budgets["logical_mcp_requests_maximum"] == 5
    assert budgets["historical_run_reruns"] == 0
    assert budgets["retries"] == 0
    assert budgets["runtime_network_requests"] == 0
    assert not any(policy["authority"].values())


def test_corrective_and_cumulative_scope_are_exact() -> None:
    assert gate.BASE_COMMIT == "3cc75a33790be353a74641034a3c5210dfc7bc17"
    assert gate.FAILED_P3_COMMIT == "38eb63ade7024ab32963f894c719fa190fe9346a"
    assert gate.FAILED_P3_1_COMMIT == "06b57853332a89e8adf21317e85cc6f91deecacf"
    assert gate.CORRECTIVE_CHANGED_PATHS == {
        ".github/workflows/alpha-a1-p3-2-optional-leaf-correction.yml": "A",
        "alpha/alpha_a1_p3_2_optional_leaf_correction_policy_v1.json": "A",
        "docs/alpha-a1-p3-2-optional-leaf-correction-gate-v1.md": "A",
        "scripts/verify_alpha_a1_p3_2_optional_leaf_correction.py": "A",
        "tests/test_alpha_a1_p3_2_optional_leaf_correction.py": "A",
    }
    assert len(gate.CUMULATIVE_CHANGED_PATHS) == 18


def test_prior_p3_and_p3_1_inputs_remain_byte_identical() -> None:
    immutable = {
        **gate.p31.FAILED_CHECKPOINT_IMMUTABLE_SHA256,
        **gate.P3_1_CHECKPOINT_IMMUTABLE_SHA256,
    }
    for relative, expected in immutable.items():
        assert _sha256(ROOT / relative) == expected


def test_optional_oracle_accepts_absent_or_empty_scope_directories(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    first = gate._validate_optional_omission(harness)
    assert first["empty_scope_directories_tolerated"] == []
    assert len(first["optional_package_leaf_paths_checked"]) == 11

    for relative in gate.OPTIONAL_SCOPE_DIRECTORIES:
        (harness / relative).mkdir(parents=True)
    second = gate._validate_optional_omission(harness)
    assert second["empty_scope_directories_tolerated"] == sorted(gate.OPTIONAL_SCOPE_DIRECTORIES)


@pytest.mark.parametrize("relative", sorted(gate.EXPECTED_OPTIONAL_PACKAGE_PATHS))
def test_optional_oracle_rejects_every_exact_leaf(tmp_path: Path, relative: str) -> None:
    harness = _harness(tmp_path)
    leaf = harness / relative
    leaf.mkdir(parents=True)
    with pytest.raises(gate.p3.GateError, match=relative):
        gate._validate_optional_omission(harness)


def test_optional_oracle_rejects_scope_content_and_dangling_leaf(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    (harness / "node_modules" / "@github").mkdir()
    marker = harness / "node_modules" / "@github" / ".unexpected"
    marker.write_text("blocked", encoding="utf-8")
    with pytest.raises(gate.p3.GateError, match="contains installed content"):
        gate._validate_optional_omission(harness)

    marker.unlink()
    dangling = harness / "node_modules" / "@github" / "keytar"
    dangling.symlink_to("missing-target")
    with pytest.raises(gate.p3.GateError, match="node_modules/@github/keytar"):
        gate._validate_optional_omission(harness)


def test_optional_oracle_rejects_top_level_hidden_lock_and_bin_drift(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    unexpected = harness / "node_modules" / "unexpected"
    unexpected.mkdir()
    with pytest.raises(gate.p3.GateError, match="top-level inventory"):
        gate._validate_optional_omission(harness)

    unexpected.rmdir()
    hidden_lock_path = harness / "node_modules" / ".package-lock.json"
    hidden_lock = json.loads(hidden_lock_path.read_text(encoding="utf-8"))
    hidden_lock["packages"]["node_modules/unexpected"] = {}
    hidden_lock_path.write_text(json.dumps(hidden_lock), encoding="utf-8")
    with pytest.raises(gate.p3.GateError, match="hidden lock package inventory"):
        gate._validate_optional_omission(harness)

    harness = _harness(tmp_path / "second")
    link = harness / "node_modules" / ".bin" / "gemini"
    link.unlink()
    link.symlink_to("../wrong.js")
    with pytest.raises(gate.p3.GateError, match="bin target"):
        gate._validate_optional_omission(harness)


def test_workflow_uses_new_label_exact_module_and_no_publication() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Alpha A1-P3.2 optional-leaf correction" in workflow
    assert "types: [labeled]" in workflow
    assert "github.event.label.name == 'alpha-a1-p3-2-authorized'" in workflow
    assert "github.event.label.name == 'alpha-a1-p3-1-authorized'" not in workflow
    assert '"$python_path" -m scripts.verify_alpha_a1_p3_2_optional_leaf_correction' in workflow
    assert "fetch-depth: 4" in workflow
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
            "scripts.verify_alpha_a1_p3_2_optional_leaf_correction",
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
    assert "Alpha A1-P3.2 exact optional-leaf correction" in completed.stdout
    assert completed.stderr == ""


def test_scope_validator_locks_three_checkpoint_ancestors(monkeypatch) -> None:
    expected_head = "a" * 40
    direct = "\n".join(
        f"{status}\t{path}" for path, status in gate.CORRECTIVE_CHANGED_PATHS.items()
    )
    cumulative = "\n".join(f"A\t{path}" for path in gate.CUMULATIVE_CHANGED_PATHS)

    def fake_git(arguments, **_kwargs) -> str:
        table = {
            ("rev-parse", "HEAD"): expected_head,
            ("rev-list", "--parents", "-n", "1", expected_head): (
                f"{expected_head} {gate.FAILED_P3_1_COMMIT}"
            ),
            ("rev-list", "--parents", "-n", "1", gate.FAILED_P3_1_COMMIT): (
                f"{gate.FAILED_P3_1_COMMIT} {gate.FAILED_P3_COMMIT}"
            ),
            ("rev-list", "--parents", "-n", "1", gate.FAILED_P3_COMMIT): (
                f"{gate.FAILED_P3_COMMIT} {gate.BASE_COMMIT}"
            ),
            ("rev-parse", f"{gate.BASE_COMMIT}^{{tree}}"): gate.BASE_TREE,
            ("rev-parse", f"{gate.FAILED_P3_COMMIT}^{{tree}}"): gate.FAILED_P3_TREE,
            ("rev-parse", f"{gate.FAILED_P3_1_COMMIT}^{{tree}}"): gate.FAILED_P3_1_TREE,
            (
                "diff",
                "--name-status",
                "--no-renames",
                gate.FAILED_P3_1_COMMIT,
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


def test_scope_and_install_adapters_are_single_use_and_restored(
    monkeypatch, tmp_path: Path
) -> None:
    original_scope = gate.p3._validate_scope
    original_install = gate.p3._install_gemini
    monkeypatch.setattr(gate, "_validate_scope", lambda *_args: None)
    monkeypatch.setattr(
        gate,
        "_install_gemini_exact_leaf",
        lambda *_args: (tmp_path / "gemini.js", {"attempts": 1}),
    )

    def fake_run_gate(**kwargs):
        gate.p3._validate_scope(ROOT, "a" * 40, Path("/usr/bin/git"), 0.0)
        gate.p3._install_gemini(
            ROOT,
            tmp_path / "runtime",
            Path("/usr/bin/node"),
            Path("/usr/bin/npm"),
            0.0,
        )
        report = {"budgets": {}, "prerequisite": {}}
        kwargs["output"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output"].write_text("{}\n", encoding="utf-8")
        return report

    monkeypatch.setattr(gate.p3, "run_gate", fake_run_gate)
    report = gate.run_gate(
        work_root=tmp_path,
        p0_receipt=tmp_path / "receipt.json",
        expected_head="a" * 40,
        output=tmp_path / "p3-runtime" / "gate-receipt.json",
        git_executable=Path("/usr/bin/git"),
        node_executable=Path("/usr/bin/node"),
        npm_executable=Path("/usr/bin/npm"),
        strace_executable=Path("/usr/bin/strace"),
    )
    assert gate.p3._validate_scope is original_scope
    assert gate.p3._install_gemini is original_install
    assert report["correction"]["scope_adapter_calls"] == 1
    assert report["correction"]["install_adapter_calls"] == 1


def test_scope_and_install_adapters_are_restored_after_failure(monkeypatch, tmp_path: Path) -> None:
    original_scope = gate.p3._validate_scope
    original_install = gate.p3._install_gemini
    monkeypatch.setattr(gate, "_validate_scope", lambda *_args: None)
    monkeypatch.setattr(
        gate,
        "_install_gemini_exact_leaf",
        lambda *_args: (tmp_path / "gemini.js", {"attempts": 1}),
    )

    def failing_run_gate(**_kwargs):
        gate.p3._validate_scope(ROOT, "a" * 40, Path("/usr/bin/git"), 0.0)
        gate.p3._install_gemini(
            ROOT,
            tmp_path / "runtime",
            Path("/usr/bin/node"),
            Path("/usr/bin/npm"),
            0.0,
        )
        raise gate.p3.GateError("synthetic failure")

    monkeypatch.setattr(gate.p3, "run_gate", failing_run_gate)
    with pytest.raises(gate.p3.GateError, match="synthetic failure"):
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
    assert gate.p3._validate_scope is original_scope
    assert gate.p3._install_gemini is original_install


def test_protocol_preserves_failures_and_authority_boundary() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    assert "A1-P3 remains failed and non-evaluated" in protocol
    assert "A1-P3.1 remains failed" in protocol
    assert "does not establish whether the optional package leaf was installed" in protocol
    assert "eleven entries marked `optional`" in protocol
    assert "external model, provider, search, document" in protocol
    assert "authorizes neither merge, Phase 12" in protocol
