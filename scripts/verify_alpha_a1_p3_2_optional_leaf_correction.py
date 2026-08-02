"""Verify the Alpha A1-P3.2 exact optional-leaf correction and host gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from scripts import verify_alpha_a1_p3_1_launcher_correction as p31
from scripts import verify_alpha_a1_p3_real_host_offline as p3

BASE_COMMIT = "3cc75a33790be353a74641034a3c5210dfc7bc17"
BASE_TREE = "21abc6024a08a5528710a5fd8e49630c8fca2c9d"
FAILED_P3_COMMIT = "38eb63ade7024ab32963f894c719fa190fe9346a"
FAILED_P3_TREE = "c21496bf690a8c2844a8957b7af12de72cf5b7ad"
FAILED_P3_RUN_ID = 30745671040
FAILED_P3_JOB_ID = 91490727817
FAILED_P3_1_COMMIT = "06b57853332a89e8adf21317e85cc6f91deecacf"
FAILED_P3_1_TREE = "c9f3b9bc7356753f751f9cd2dd32fab08c91d382"
FAILED_P3_1_RUN_ID = 30746105014
FAILED_P3_1_JOB_ID = 91491870812

CORRECTIVE_CHANGED_PATHS = {
    ".github/workflows/alpha-a1-p3-2-optional-leaf-correction.yml": "A",
    "alpha/alpha_a1_p3_2_optional_leaf_correction_policy_v1.json": "A",
    "docs/alpha-a1-p3-2-optional-leaf-correction-gate-v1.md": "A",
    "scripts/verify_alpha_a1_p3_2_optional_leaf_correction.py": "A",
    "tests/test_alpha_a1_p3_2_optional_leaf_correction.py": "A",
}
CUMULATIVE_CHANGED_PATHS = p31.CUMULATIVE_CHANGED_PATHS | set(CORRECTIVE_CHANGED_PATHS)

P3_1_CHECKPOINT_IMMUTABLE_SHA256 = {
    ".github/workflows/alpha-a1-p3-1-launcher-correction.yml": (
        "ae52378b5a61816fbfeb1524a714444a595007f9ff04c2c29ab9f7262525db7a"
    ),
    "alpha/alpha_a1_p3_1_launcher_correction_policy_v1.json": (
        "1831bac6535cc4cfd815acca2c7757a87552954977783a90fba0845a08bf6da6"
    ),
    "docs/alpha-a1-p3-1-launcher-correction-gate-v1.md": (
        "9e3a235977ecf23dba264081512ed300df17f7e8418c02badf48aec1cb500d2c"
    ),
    "scripts/verify_alpha_a1_p3_1_launcher_correction.py": (
        "593efe9aaaf3939b4b48cc72617897c844d77a5b7958cb08fabf406468f6ba48"
    ),
    "tests/test_alpha_a1_p3_1_launcher_correction.py": (
        "975a6605012724dadd5ce85cf69aed40c91afe347a8a739a899bd9d308a0e3e9"
    ),
}

EXPECTED_OPTIONAL_PACKAGE_PATHS = {
    "node_modules/@github/keytar",
    "node_modules/@lydell/node-pty",
    "node_modules/@lydell/node-pty-darwin-arm64",
    "node_modules/@lydell/node-pty-darwin-x64",
    "node_modules/@lydell/node-pty-linux-arm64",
    "node_modules/@lydell/node-pty-linux-x64",
    "node_modules/@lydell/node-pty-win32-arm64",
    "node_modules/@lydell/node-pty-win32-x64",
    "node_modules/nan",
    "node_modules/node-addon-api",
    "node_modules/node-pty",
}
OPTIONAL_SCOPE_DIRECTORIES = {
    "node_modules/@github",
    "node_modules/@lydell",
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
        label="A1-P3.2 checkout HEAD",
    )
    p3._require(head == expected_head, "Checkout does not match the A1-P3.2 trigger head")

    ancestry = (
        (expected_head, FAILED_P3_1_COMMIT, "A1-P3.2"),
        (FAILED_P3_1_COMMIT, FAILED_P3_COMMIT, "failed A1-P3.1"),
        (FAILED_P3_COMMIT, BASE_COMMIT, "failed A1-P3"),
    )
    for commit, parent, label in ancestry:
        tokens = _git(
            ["rev-list", "--parents", "-n", "1", commit],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label=f"{label} parent inspection",
        ).split()
        p3._require(tokens == [commit, parent], f"{label} ancestry drifted")

    trees = (
        (BASE_COMMIT, BASE_TREE, "A1-P3.2 base tree"),
        (FAILED_P3_COMMIT, FAILED_P3_TREE, "failed A1-P3 tree"),
        (FAILED_P3_1_COMMIT, FAILED_P3_1_TREE, "failed A1-P3.1 tree"),
    )
    for commit, expected_tree, label in trees:
        observed_tree = _git(
            ["rev-parse", f"{commit}^{{tree}}"],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label=label,
        )
        p3._require(observed_tree == expected_tree, f"{label} drifted")

    direct = _name_status(
        _git(
            [
                "diff",
                "--name-status",
                "--no-renames",
                FAILED_P3_1_COMMIT,
                expected_head,
            ],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label="A1-P3.2 direct scope inspection",
        ),
        "A1-P3.2 direct scope",
    )
    p3._require(direct == CORRECTIVE_CHANGED_PATHS, "A1-P3.2 direct changed-path scope drifted")

    cumulative = _name_status(
        _git(
            ["diff", "--name-status", "--no-renames", BASE_COMMIT, expected_head],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label="A1-P3.2 cumulative scope inspection",
        ),
        "A1-P3.2 cumulative scope",
    )
    p3._require(
        set(cumulative) == CUMULATIVE_CHANGED_PATHS,
        "A1-P3.2 cumulative changed-path scope drifted",
    )
    p3._require(set(cumulative.values()) == {"A"}, "A1-P3.2 cumulative scope is not additive")

    immutable = {
        **p3.IMMUTABLE_SHA256,
        **p31.FAILED_CHECKPOINT_IMMUTABLE_SHA256,
        **P3_1_CHECKPOINT_IMMUTABLE_SHA256,
    }
    for relative, expected_hash in immutable.items():
        path = repository_root / relative
        p3._require(path.is_file(), f"A1-P3.2 immutable file is missing: {relative}")
        p3._require(
            p3._sha256_file(path) == expected_hash,
            f"A1-P3.2 immutable file drifted: {relative}",
        )


def _validate_optional_omission(harness: Path) -> dict[str, Any]:
    lock = p3._json_object(harness / "package-lock.json", "Gemini harness lock")
    packages = p3._mapping(lock.get("packages"), "Gemini lock packages are missing")
    observed_optional = {
        relative
        for relative, value in packages.items()
        if p3._mapping(value, f"Gemini lock entry is malformed: {relative}").get("optional") is True
    }
    p3._require(
        observed_optional == EXPECTED_OPTIONAL_PACKAGE_PATHS,
        "Gemini optional package leaf inventory drifted",
    )

    for relative in sorted(observed_optional):
        path = harness / relative
        p3._require(
            not os.path.lexists(path),
            f"Optional package installed: {relative}",
        )

    modules = harness / "node_modules"
    p3._require(modules.is_dir() and not modules.is_symlink(), "node_modules root drifted")
    tolerated_empty_scopes: list[str] = []
    for relative in sorted(OPTIONAL_SCOPE_DIRECTORIES):
        scope = harness / relative
        p3._require(not scope.is_symlink(), f"Optional scope is a symlink: {relative}")
        if scope.exists():
            p3._require(scope.is_dir(), f"Optional scope is not a directory: {relative}")
            p3._require(
                not any(scope.iterdir()),
                f"Optional scope contains installed content: {relative}",
            )
            tolerated_empty_scopes.append(relative)

    expected_top_level = {".bin", ".package-lock.json", "@google"} | {
        Path(relative).name for relative in tolerated_empty_scopes
    }
    observed_top_level = {entry.name for entry in modules.iterdir()}
    p3._require(
        observed_top_level == expected_top_level,
        "Installed node_modules top-level inventory drifted",
    )

    google_scope = modules / "@google"
    p3._require(
        google_scope.is_dir() and not google_scope.is_symlink(),
        "Installed @google scope drifted",
    )
    p3._require(
        {entry.name for entry in google_scope.iterdir()} == {"gemini-cli"},
        "Installed @google scope inventory drifted",
    )
    package_root = google_scope / "gemini-cli"
    p3._require(
        package_root.is_dir() and not package_root.is_symlink(),
        "Installed Gemini package root drifted",
    )

    bin_root = modules / ".bin"
    p3._require(bin_root.is_dir() and not bin_root.is_symlink(), "Installed .bin drifted")
    p3._require(
        {entry.name for entry in bin_root.iterdir()} == {"gemini"},
        "Installed .bin inventory drifted",
    )
    gemini_link = bin_root / "gemini"
    p3._require(gemini_link.is_symlink(), "Installed Gemini bin is not a symlink")
    p3._require(
        os.readlink(gemini_link) == "../@google/gemini-cli/bundle/gemini.js",
        "Installed Gemini bin target drifted",
    )

    hidden_lock = p3._json_object(modules / ".package-lock.json", "installed hidden lock")
    p3._require(hidden_lock.get("lockfileVersion") == 3, "Installed hidden lock version drifted")
    hidden_packages = p3._mapping(
        hidden_lock.get("packages"), "Installed hidden lock packages are missing"
    )
    gemini_relative = "node_modules/@google/gemini-cli"
    p3._require(
        set(hidden_packages) == {gemini_relative},
        "Installed hidden lock package inventory drifted",
    )
    locked_gemini = p3._mapping(
        packages.get(gemini_relative), "Gemini source lock entry is missing"
    )
    installed_gemini = p3._mapping(
        hidden_packages.get(gemini_relative), "Gemini installed lock entry is missing"
    )
    p3._require(
        {key: installed_gemini.get(key) for key in ("version", "resolved", "integrity")}
        == {key: locked_gemini.get(key) for key in ("version", "resolved", "integrity")},
        "Installed hidden lock Gemini identity drifted",
    )

    return {
        "empty_scope_directories_tolerated": tolerated_empty_scopes,
        "installed_hidden_lock_packages": len(hidden_packages),
        "installed_top_level_entries": sorted(observed_top_level),
        "optional_package_leaf_paths_checked": sorted(observed_optional),
    }


def _install_gemini_exact_leaf(
    repository_root: Path,
    runtime_root: Path,
    node: Path,
    npm: Path,
    started_at: float,
) -> tuple[Path, dict[str, Any]]:
    harness_source = repository_root / p3.HARNESS_RELATIVE_PATH
    harness = runtime_root / "gemini-harness"
    harness.mkdir(mode=0o700)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(harness_source / name, harness / name)
        (harness / name).chmod(0o600)
    package_snapshot = (harness / "package.json").read_bytes()
    lock_snapshot = (harness / "package-lock.json").read_bytes()
    acquisition_env, cache = p3._acquisition_environment(runtime_root, node)
    _, install_stderr, install_seconds = p3._run(
        [
            str(npm),
            "ci",
            "--ignore-scripts",
            "--omit=optional",
            "--no-audit",
            "--no-fund",
            "--fetch-retries=0",
        ],
        cwd=harness,
        env=acquisition_env,
        started_at=started_at,
        label="pinned Gemini CLI installation",
    )
    p3._require((harness / "package.json").read_bytes() == package_snapshot, "npm changed manifest")
    p3._require((harness / "package-lock.json").read_bytes() == lock_snapshot, "npm changed lock")

    omission = _validate_optional_omission(harness)
    package_root = harness / "node_modules" / "@google" / "gemini-cli"
    manifest = p3._json_object(package_root / "package.json", "installed Gemini manifest")
    p3._require(manifest.get("version") == p3.EXPECTED_GEMINI_VERSION, "Installed Gemini drifted")
    p3._require(manifest.get("license") == "Apache-2.0", "Installed Gemini license drifted")
    p3._require(manifest.get("bin") == {"gemini": "bundle/gemini.js"}, "Gemini bin drifted")
    p3._require(manifest.get("engines") == {"node": ">=20"}, "Gemini engine floor drifted")
    launcher = package_root / "bundle" / "gemini.js"
    p3._require(
        p3._sha256_file(launcher) == p3.EXPECTED_GEMINI_ENTRY_SHA256,
        "Gemini entry drifted",
    )
    npm_ls, _, _ = p3._run(
        [str(npm), "ls", "--omit=optional", "--json"],
        cwd=harness,
        env=acquisition_env,
        started_at=started_at,
        label="installed Gemini dependency tree",
    )
    try:
        tree = p3._mapping(json.loads(npm_ls), "npm ls output is not an object")
    except json.JSONDecodeError as exc:
        raise p3.GateError("npm ls output is malformed") from exc
    p3._require(not tree.get("problems"), "npm ls reported dependency problems")
    dependencies = p3._mapping(tree.get("dependencies"), "npm ls root dependencies are missing")
    p3._require(set(dependencies) == {"@google/gemini-cli"}, "Installed dependency scope drifted")
    p3._require(
        p3._mapping(dependencies["@google/gemini-cli"], "Gemini npm ls entry is malformed").get(
            "version"
        )
        == p3.EXPECTED_GEMINI_VERSION,
        "npm ls Gemini version drifted",
    )
    shutil.rmtree(cache)
    p3._require(not cache.exists(), "npm acquisition cache survived into runtime")
    return launcher, {
        "attempts": 1,
        "entry_sha256": p3.EXPECTED_GEMINI_ENTRY_SHA256,
        "ignore_scripts": True,
        "install_seconds": round(install_seconds, 3),
        "optional_dependencies_omitted": True,
        **omission,
        "retries": 0,
        "stderr_bytes": len(install_stderr.encode()),
    }


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
        "A1-P3.2 imported P3 verifier provenance drifted",
    )
    p3._require(
        Path(p31.__file__).resolve()
        == repository_root / "scripts" / "verify_alpha_a1_p3_1_launcher_correction.py",
        "A1-P3.2 imported P3.1 verifier provenance drifted",
    )
    base_output = output.parent / ".a1-p3-base-receipt.json"
    p3._require(not base_output.exists(), "A1-P3.2 temporary receipt already exists")

    original_scope_validator = p3._validate_scope
    original_installer = p3._install_gemini
    scope_calls = 0
    install_calls = 0

    def corrective_scope_validator(
        repository_root: Path,
        expected_head: str,
        git_executable: Path,
        started_at: float,
    ) -> None:
        nonlocal scope_calls
        scope_calls += 1
        p3._require(scope_calls == 1, "A1-P3.2 scope adapter was called more than once")
        _validate_scope(repository_root, expected_head, git_executable, started_at)

    def corrective_installer(
        repository_root: Path,
        runtime_root: Path,
        node: Path,
        npm: Path,
        started_at: float,
    ) -> tuple[Path, dict[str, Any]]:
        nonlocal install_calls
        install_calls += 1
        p3._require(install_calls == 1, "A1-P3.2 install adapter was called more than once")
        return _install_gemini_exact_leaf(repository_root, runtime_root, node, npm, started_at)

    p3._validate_scope = corrective_scope_validator
    p3._install_gemini = corrective_installer
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
        p3._install_gemini = original_installer

    p3._require(scope_calls == 1, "A1-P3.2 scope adapter call count drifted")
    p3._require(install_calls == 1, "A1-P3.2 install adapter call count drifted")
    p3._require(base_output.is_file(), "A1-P3.2 base receipt is missing")
    base_output.unlink()

    report["schema_version"] = "evidencemesh.alpha-a1-p3-2-optional-leaf-correction-receipt.v1"
    report["correction"] = {
        "classification": "optional_dependency_assertion_granularity",
        "corrective_parent_commit": FAILED_P3_1_COMMIT,
        "failed_p3_1_job_id": FAILED_P3_1_JOB_ID,
        "failed_p3_1_run_id": FAILED_P3_1_RUN_ID,
        "historical_run_rerun": False,
        "install_adapter_calls": install_calls,
        "module_entrypoint": "scripts.verify_alpha_a1_p3_2_optional_leaf_correction",
        "optional_leaf_paths_checked": len(EXPECTED_OPTIONAL_PACKAGE_PATHS),
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
        "commit_sha": FAILED_P3_COMMIT,
        "conclusion": "failure",
        "job_id": FAILED_P3_JOB_ID,
        "run_id": FAILED_P3_RUN_ID,
        "tree_sha": FAILED_P3_TREE,
    }
    report["prerequisite"]["failed_a1_p3_1"] = {
        "commit_sha": FAILED_P3_1_COMMIT,
        "conclusion": "failure",
        "job_id": FAILED_P3_1_JOB_ID,
        "run_id": FAILED_P3_1_RUN_ID,
        "tree_sha": FAILED_P3_1_TREE,
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
        print(f"Alpha A1-P3.2 FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
