"""Verify the Alpha A1-P3.1 launcher correction and real-host offline gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts import verify_alpha_a1_p3_real_host_offline as p3

BASE_COMMIT = "3cc75a33790be353a74641034a3c5210dfc7bc17"
BASE_TREE = "21abc6024a08a5528710a5fd8e49630c8fca2c9d"
FAILED_COMMIT = "38eb63ade7024ab32963f894c719fa190fe9346a"
FAILED_TREE = "c21496bf690a8c2844a8957b7af12de72cf5b7ad"
FAILED_RUN_ID = 30745671040
FAILED_JOB_ID = 91490727817

CORRECTIVE_CHANGED_PATHS = {
    ".github/workflows/alpha-a1-p3-1-launcher-correction.yml": "A",
    "alpha/alpha_a1_p3_1_launcher_correction_policy_v1.json": "A",
    "docs/alpha-a1-p3-1-launcher-correction-gate-v1.md": "A",
    "scripts/verify_alpha_a1_p3_1_launcher_correction.py": "A",
    "tests/test_alpha_a1_p3_1_launcher_correction.py": "A",
}
CUMULATIVE_CHANGED_PATHS = p3.EXPECTED_CHANGED_PATHS | {
    ".github/workflows/alpha-a1-p3-1-launcher-correction.yml",
    "alpha/alpha_a1_p3_1_launcher_correction_policy_v1.json",
    "docs/alpha-a1-p3-1-launcher-correction-gate-v1.md",
    "scripts/verify_alpha_a1_p3_1_launcher_correction.py",
    "tests/test_alpha_a1_p3_1_launcher_correction.py",
}
FAILED_CHECKPOINT_IMMUTABLE_SHA256 = {
    ".github/workflows/alpha-a1-p3-real-host-offline.yml": (
        "9f6d8d04bb8e11e7bb3a8e621d4b243c462b2125117d5b597c10319f4ea0ef0d"
    ),
    "alpha/a1-p3-gemini-cli/fake-responses.jsonl": (
        "ef07d0312717639ec5d53809b874fc4eee1e2f9f70d42133235d895752eb510b"
    ),
    "alpha/a1-p3-gemini-cli/package-lock.json": (
        "dc384de3fe3277f1cdaadf06dcc16268bb73aae0312f327119ba09fb8ea564b9"
    ),
    "alpha/a1-p3-gemini-cli/package.json": (
        "59f5b8801b95333938d0ce17560ea583cfaf8388084a9bc620db637252926295"
    ),
    "alpha/alpha_a1_p3_real_host_offline_policy_v1.json": (
        "7c8202f6d78ff477e74f4b7f3e8cdf8b621ed3f61b956054cb9a2f39dfe6f5a2"
    ),
    "docs/alpha-a1-p3-real-host-offline-gate-v1.md": (
        "9444d55f6dff456114e218351ac0a1e94c16eab82c06ef631053a8e06855b1dc"
    ),
    "scripts/verify_alpha_a1_p3_real_host_offline.py": (
        "f407ee0f81ef205f2a1fd9f84f0f9ec06bddea6be7fe9c3ae6e1022a910faad5"
    ),
    "tests/test_alpha_a1_p3_real_host_offline.py": (
        "eb0b45f7d2d0a55d1e881ebee2380d53a83f7302c2d13d1c2b72ab17804e3b57"
    ),
}


def _git(
    arguments: list[str],
    *,
    repository_root: Path,
    git_executable: Path,
    started_at: float,
    label: str,
) -> str:
    stdout, _, _ = p3._run(
        [str(git_executable), *arguments],
        cwd=repository_root,
        env=p3._git_environment(),
        started_at=started_at,
        label=label,
    )
    return stdout.strip()


def _name_status(value: str, label: str) -> dict[str, str]:
    observed: dict[str, str] = {}
    for line in value.splitlines():
        status_value, separator, path = line.partition("\t")
        p3._require(bool(separator) and bool(path), f"{label} output is malformed")
        p3._require(path not in observed, f"{label} contains a duplicate path")
        observed[path] = status_value
    return observed


def _validate_scope(
    repository_root: Path,
    expected_head: str,
    git_executable: Path,
    started_at: float,
) -> None:
    p3._validate_full_sha(expected_head, "trigger head")
    head = _git(
        ["rev-parse", "HEAD"],
        repository_root=repository_root,
        git_executable=git_executable,
        started_at=started_at,
        label="A1-P3.1 checkout HEAD",
    )
    p3._require(head == expected_head, "Checkout does not match the A1-P3.1 trigger head")

    parent_tokens = _git(
        ["rev-list", "--parents", "-n", "1", expected_head],
        repository_root=repository_root,
        git_executable=git_executable,
        started_at=started_at,
        label="A1-P3.1 parent inspection",
    ).split()
    p3._require(len(parent_tokens) == 2, "A1-P3.1 commit must have exactly one parent")
    p3._require(parent_tokens[1] == FAILED_COMMIT, "A1-P3.1 parent checkpoint drifted")

    failed_parent_tokens = _git(
        ["rev-list", "--parents", "-n", "1", FAILED_COMMIT],
        repository_root=repository_root,
        git_executable=git_executable,
        started_at=started_at,
        label="failed A1-P3 parent inspection",
    ).split()
    p3._require(
        failed_parent_tokens == [FAILED_COMMIT, BASE_COMMIT],
        "Failed A1-P3 ancestry drifted",
    )
    p3._require(
        _git(
            ["rev-parse", f"{BASE_COMMIT}^{{tree}}"],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label="A1-P3.1 base tree",
        )
        == BASE_TREE,
        "A1-P3.1 base tree drifted",
    )
    p3._require(
        _git(
            ["rev-parse", f"{FAILED_COMMIT}^{{tree}}"],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label="failed A1-P3 tree",
        )
        == FAILED_TREE,
        "Failed A1-P3 tree drifted",
    )

    direct = _name_status(
        _git(
            ["diff", "--name-status", "--no-renames", FAILED_COMMIT, expected_head],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label="A1-P3.1 corrective scope",
        ),
        "A1-P3.1 corrective scope",
    )
    p3._require(direct == CORRECTIVE_CHANGED_PATHS, "A1-P3.1 corrective scope drifted")

    cumulative = _name_status(
        _git(
            ["diff", "--name-status", "--no-renames", BASE_COMMIT, expected_head],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label="A1-P3.1 cumulative scope",
        ),
        "A1-P3.1 cumulative scope",
    )
    p3._require(
        set(cumulative) == CUMULATIVE_CHANGED_PATHS,
        "A1-P3.1 cumulative changed-path scope drifted",
    )
    p3._require(
        set(cumulative.values()) == {"A"},
        "A1-P3.1 cumulative scope must contain additions only",
    )

    immutable = {**p3.IMMUTABLE_SHA256, **FAILED_CHECKPOINT_IMMUTABLE_SHA256}
    for relative, expected_hash in immutable.items():
        path = repository_root / relative
        p3._require(path.is_file(), f"A1-P3.1 immutable file is missing: {relative}")
        p3._require(
            p3._sha256_file(path) == expected_hash,
            f"A1-P3.1 immutable file drifted: {relative}",
        )


def run_gate(
    *,
    work_root: Path,
    p0_receipt: Path,
    expected_head: str,
    output: Path,
    git_executable: Path,
    node_executable: Path,
    npm_executable: Path,
    strace_executable: Path,
) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[1]
    p3._require(
        Path(p3.__file__).resolve()
        == repository_root / "scripts" / "verify_alpha_a1_p3_real_host_offline.py",
        "A1-P3.1 imported verifier provenance drifted",
    )
    base_output = output.parent / ".a1-p3-base-receipt.json"
    p3._require(not base_output.exists(), "A1-P3.1 temporary receipt already exists")
    original_scope_validator = p3._validate_scope
    scope_calls = 0

    def corrective_scope_validator(
        root: Path,
        head: str,
        git: Path,
        started_at: float,
    ) -> None:
        nonlocal scope_calls
        scope_calls += 1
        p3._require(scope_calls == 1, "A1-P3.1 scope adapter was called more than once")
        _validate_scope(root, head, git, started_at)

    p3._validate_scope = corrective_scope_validator
    try:
        report = p3.run_gate(
            work_root=work_root,
            p0_receipt=p0_receipt,
            expected_head=expected_head,
            output=base_output,
            git_executable=git_executable,
            node_executable=node_executable,
            npm_executable=npm_executable,
            strace_executable=strace_executable,
        )
    finally:
        p3._validate_scope = original_scope_validator
    p3._require(scope_calls == 1, "A1-P3.1 scope adapter call count drifted")
    p3._require(base_output.is_file(), "A1-P3.1 base receipt is missing")
    base_output.unlink()
    report["schema_version"] = "evidencemesh.alpha-a1-p3-1-launcher-correction-receipt.v1"
    report["correction"] = {
        "classification": "workflow_python_module_entrypoint",
        "corrective_parent_commit": FAILED_COMMIT,
        "failed_job_id": FAILED_JOB_ID,
        "failed_run_id": FAILED_RUN_ID,
        "historical_run_rerun": False,
        "module_entrypoint": "scripts.verify_alpha_a1_p3_1_launcher_correction",
        "original_gate_evaluated_host": False,
        "scope_adapter_calls": scope_calls,
    }
    report["budgets"].update(
        {
            "corrective_workflow_runs": 1,
            "historical_run_reruns": 0,
            "workflow_retries": 0,
        }
    )
    report["prerequisite"]["failed_a1_p3"] = {
        "commit_sha": FAILED_COMMIT,
        "conclusion": "failure",
        "job_id": FAILED_JOB_ID,
        "run_id": FAILED_RUN_ID,
        "tree_sha": FAILED_TREE,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    p3._private_file(output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--p0-receipt", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--git", default="git")
    parser.add_argument("--node", default="node")
    parser.add_argument("--npm", default="npm")
    parser.add_argument("--strace", default="strace")
    args = parser.parse_args()
    try:
        run_gate(
            work_root=args.work_root.resolve(),
            p0_receipt=args.p0_receipt.resolve(),
            expected_head=args.expected_head,
            output=args.output.resolve(),
            git_executable=p3._resolve_executable(args.git, "git"),
            node_executable=p3._resolve_executable(args.node, "node"),
            npm_executable=p3._resolve_executable(args.npm, "npm"),
            strace_executable=p3._resolve_executable(args.strace, "strace"),
        )
    except (p3.GateError, OSError, UnicodeError) as exc:
        print(f"Alpha A1-P3.1 FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
