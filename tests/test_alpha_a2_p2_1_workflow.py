from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/alpha-a2-p2-1-fixture-root-correction-offline-gate-v1.md"
POLICY = ROOT / "alpha/alpha-a2-p2-1-fixture-root-correction-policy-v1.json"
WORKFLOW = ROOT / ".github/workflows/alpha-a2-p2-1-fixture-root-correction-offline.yml"
CORRECTED_TEST = ROOT / "tests/test_smoke_installed_a2_p2.py"

PARENT_SHA = "18340f972bbc907912d1fcfa9fe5a2385751cc97"
PARENT_TREE = "06e745383904c37ca277c8f57c45db9ed96df6b4"
FAILED_RUN_ID = 30841501822
FAILED_JOB_ID = 91779399419
PROTOCOL_SHA256 = "9c189f7ba5792f3aa28a70d0664bb05b68972a7d68adf6574c4d3085bc96c0c9"
POLICY_SHA256 = "c1f14a4c57a65f49d2a8f365f4dea1c1f8bb88904077711c09e12372ab3f4e45"
CORRECTED_TEST_SHA256 = "05eef013f16d2017a36a091e403d6ca8c79f61f1fe5eec58554f0f0f8d6904c3"

ADDITIONS = [
    ".github/workflows/alpha-a2-p2-1-fixture-root-correction-offline.yml",
    "alpha/alpha-a2-p2-1-fixture-root-correction-policy-v1.json",
    "docs/alpha-a2-p2-1-fixture-root-correction-offline-gate-v1.md",
    "tests/test_alpha_a2_p2_1_workflow.py",
]
MODIFICATIONS = ["tests/test_smoke_installed_a2_p2.py"]
ALLOWED_PATHS = [*ADDITIONS, *MODIFICATIONS]
IMMUTABLE_P2_SHA256 = {
    ".github/workflows/alpha-a2-p2-installed-distribution-offline.yml": (
        "1c66dcf6bdcf7164e100df3dfa3639caca207669ee1bdda634e16c0aed32ca2c"
    ),
    "alpha/alpha-a2-p2-installed-distribution-offline-policy-v1.json": (
        "6356e5da4dc9ddb5db6cc643a894cc6dd404687297aa86c2005c1963303936f8"
    ),
    "docs/alpha-a2-p2-installed-distribution-offline-gate-v1.md": (
        "2b64d1364b5c90894e109d016afa85ef466e9b4f285b2f2c86985b3ad7189cd1"
    ),
    "scripts/smoke_installed_a2_p2.py": (
        "66aaf1815233e3f9e04b5a898e1b70d5b486ed1b3eae01489f42873a99578309"
    ),
    "tests/test_alpha_a2_p2_workflow.py": (
        "8b26b5de758fcfc5bcd18d1609ffe6d495a660a877a5dba605436f3b8ff12fda"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(POLICY.read_bytes()))


def test_policy_locks_exact_parent_protocol_and_immutable_failed_evidence() -> None:
    policy = _policy()

    assert _sha256(PROTOCOL) == PROTOCOL_SHA256
    assert _sha256(POLICY) == POLICY_SHA256
    assert policy["entry"] == {
        "branch": "agent/evidencemesh-v0.1",
        "direct_child_required": True,
        "exact_parent_commit_sha": PARENT_SHA,
        "exact_parent_tree_sha": PARENT_TREE,
        "merge_commit_allowed": False,
        "pull_request": 1,
        "pull_request_must_remain_draft": True,
        "repository": "VynoDePal/EvidenceMesh",
    }
    assert policy["protocol"] == {
        "path": "docs/alpha-a2-p2-1-fixture-root-correction-offline-gate-v1.md",
        "sha256": PROTOCOL_SHA256,
    }
    assert policy["historical_failure"] == {
        "conclusion": "failure",
        "exception": "FileExistsError",
        "failed_before_build": True,
        "immutable": True,
        "job_id": FAILED_JOB_ID,
        "product_runtime_defect_observed": False,
        "run_attempt": 1,
        "run_id": FAILED_RUN_ID,
        "stage": "full_suite_two_test_fixture_failures",
    }


def test_policy_freezes_exact_scope_budgets_correction_and_claim_boundary() -> None:
    policy = _policy()

    assert policy["schema_version"] == (
        "evidencemesh.alpha-a2-p2.1-fixture-root-correction-offline-policy.v1"
    )
    assert policy["scope"] == {
        "allowed_additions": ADDITIONS,
        "allowed_modifications": MODIFICATIONS,
        "runtime_and_packaging_immutable_paths": ["src", "pyproject.toml", "uv.lock"],
    }
    assert policy["budgets"] == {
        "branch_fast_forward_updates_maximum": 1,
        "build_invocations_maximum": 2,
        "candidate_commits_maximum": 1,
        "candidate_distribution_installations_maximum": 2,
        "changed_files_exact": 5,
        "distribution_publications": 0,
        "ephemeral_distribution_files_expected": 4,
        "evidencemesh_runtime_network_requests": 0,
        "live_document_requests": 0,
        "live_model_requests": 0,
        "live_provider_requests": 0,
        "live_search_requests": 0,
        "live_tester_sessions": 0,
        "operating_system_service_activations": 0,
        "retries": 0,
        "workflow_attempts_maximum": 1,
        "workflow_reruns": 0,
    }
    assert not any(policy["authority"].values())
    assert policy["candidate_decision"] == {
        "decision": "pending_until_one_shot_ci",
        "failed_or_cancelled_attempt_is_terminal": True,
        "historical_failure_reinterpreted": False,
        "pr_remains_draft": True,
    }
    assert policy["correction"] == {
        "affected_test_count": 2,
        "allowed_runtime_or_harness_change": False,
        "corrected_path": "tests/test_smoke_installed_a2_p2.py",
        "corrected_test_sha256": CORRECTED_TEST_SHA256,
        "fixture_contract": "distinct_nonexistent_child_root_per_exercise",
        "tests": [
            "test_primary_v3_close_mints_authority_and_withdrawal_cleans",
            "test_exact_session_expiry_requires_then_resolves_recovery",
        ],
    }
    assert policy["revalidation"] == {
        "archive_inventory_and_reproducibility_required": True,
        "clean_git_exports": 2,
        "coverage_minimum_percent": 85.0,
        "full_suite_invocations": 1,
        "hashed_pep508_install_requirements_required": True,
        "installed_smoke_invocations": 2,
        "network_namespace_must_differ_from_parent": True,
        "pep610_hashed_url_required": True,
        "source_quality_gates_required": ["ruff_format", "ruff_lint", "mypy_strict"],
        "uv_offline_after_acquisition": True,
        "uv_pip_check_invocations": 2,
    }
    assert policy["successful_claim"] == {
        "local_offline_technical_alpha_v0_1_0_a2": True,
        "phase_12_ready": False,
        "public_distribution_available": False,
        "real_os_supervision_proven": False,
        "scope": ("single_host_local_offline_installed_distribution_after_fixture_correction_only"),
        "v1_ready": False,
    }


def test_correction_uses_two_distinct_initially_absent_child_roots_only() -> None:
    source = CORRECTED_TEST.read_text(encoding="utf-8")

    assert _sha256(CORRECTED_TEST) == CORRECTED_TEST_SHA256
    for marker in (
        'primary_root = tmp_path / "primary"',
        "assert not primary_root.exists()",
        'smoke._exercise_primary_v3(primary_root, "a" * 64, "wheel")',
        'recovery_root = tmp_path / "recovery"',
        "assert not recovery_root.exists()",
        'smoke._exercise_recovery(recovery_root, "b" * 64, "sdist")',
    ):
        assert marker in source
    assert "smoke._exercise_primary_v3(tmp_path," not in source
    assert "smoke._exercise_recovery(tmp_path," not in source


def test_policy_and_tree_preserve_every_untouched_p2_file_byte_exactly() -> None:
    policy = _policy()

    assert policy["immutable_parent_content"] == IMMUTABLE_P2_SHA256
    for relative_path, expected_sha256 in IMMUTABLE_P2_SHA256.items():
        assert _sha256(ROOT / relative_path) == expected_sha256


def test_protocol_records_failure_entry_stop_and_narrow_claim_boundaries() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    for marker in (
        "pending_until_one_shot_ci",
        str(FAILED_RUN_ID),
        str(FAILED_JOB_ID),
        "failed before either clean export or package build",
        "FileExistsError",
        "not observed product-runtime",
        PARENT_SHA,
        PARENT_TREE,
        "exact five-path allowlist",
        "distinct, initially absent `primary` and `recovery` child roots",
        "No production or smoke-harness source change is authorized",
        "two independent clean `git archive` exports",
        "hashed PEP 508 file requirements",
        "unconditional deletion and confirmation",
        "Stop without retry",
        "A failed or cancelled P2.1 attempt is terminal",
        "single-host, offline technical alpha",
        "Phase 12 readiness",
        "V1 readiness",
    ):
        assert marker in protocol


def test_workflow_is_exact_one_shot_read_only_scoped_and_hash_locked() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)
    assert isinstance(parsed, dict)
    triggers = parsed.get("on", parsed.get(True))

    assert triggers == {
        "pull_request": {
            "types": ["synchronize"],
            "paths": ALLOWED_PATHS,
        }
    }
    assert parsed["permissions"] == {"contents": "read"}
    assert parsed["concurrency"]["cancel-in-progress"] is False
    assert "workflow_dispatch" not in workflow
    assert "push:" not in workflow
    assert "github.run_attempt == 1" in workflow
    assert "github.event.pull_request.number == 1" in workflow
    assert "github.event.pull_request.draft == true" in workflow
    assert "github.event.pull_request.head.ref == 'agent/evidencemesh-v0.1'" in workflow
    assert f"github.event.before == '{PARENT_SHA}'" in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-tags: false" in workflow
    assert PARENT_SHA in workflow
    assert PARENT_TREE in workflow
    assert f"A2_P2_FAILED_RUN_ID: {FAILED_RUN_ID}" in workflow
    assert f"A2_P2_FAILED_JOB_ID: {FAILED_JOB_ID}" in workflow
    assert POLICY_SHA256 in workflow
    assert PROTOCOL_SHA256 in workflow
    assert CORRECTED_TEST_SHA256 in workflow
    assert (
        'echo "$POLICY_SHA256  alpha/alpha-a2-p2-1-fixture-root-correction-'
        'policy-v1.json"' in workflow
    )
    assert (
        'echo "$PROTOCOL_SHA256  docs/alpha-a2-p2-1-fixture-root-correction-'
        'offline-gate-v1.md"' in workflow
    )
    assert 'echo "$CORRECTED_TEST_SHA256  tests/test_smoke_installed_a2_p2.py"' in workflow
    assert 'test "$(git rev-list --parents --max-count=1 HEAD)"' in workflow
    assert 'test "${#changed_statuses[@]}" = 5' in workflow
    assert "--diff-filter=ACDMRT" in workflow
    for path in ADDITIONS:
        assert f"$'A\\t{path}'" in workflow
    assert "$'M\\ttests/test_smoke_installed_a2_p2.py'" in workflow
    for relative_path, expected_sha256 in IMMUTABLE_P2_SHA256.items():
        assert relative_path in workflow
        assert expected_sha256 in workflow


def test_workflow_repeats_complete_p2_source_and_distribution_contract() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    acquisition_at = workflow.index("uv sync --extra dev --locked --python 3.11 --no-cache")
    isolation_at = workflow.index("/usr/bin/unshare --net")
    assert acquisition_at < isolation_at
    assert workflow.count("--no-dev --no-install-project --python 3.11 --no-cache") == 2
    assert 'version: "0.11.33"' in workflow
    assert "enable-cache: false" in workflow
    assert "UV_HTTP_RETRIES: 0" in workflow
    assert "UV_OFFLINE=1" in workflow
    root_assignment = (
        'A2_P2_1_ROOT="${RUNNER_TEMP}/evidencemesh-alpha-a2-p2-1-'
        '${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"'
    )
    assert workflow.count(root_assignment) == 4
    assert "parent_network_namespace=$(readlink /proc/self/ns/net)" in workflow
    assert 'test "$isolated_network_namespace" != "$parent_network_namespace"' in workflow
    assert '"${run_isolated[@]}" /usr/bin/test ! -r /var/run/docker.sock' in workflow
    assert '"${run_isolated[@]}" /usr/bin/test ! -w /var/run/docker.sock' in workflow
    assert "--clear-groups" in workflow
    assert "--no-new-privs" in workflow
    assert "-m ruff format --check ." in workflow
    assert "-m ruff check ." in workflow
    assert "-m mypy src" in workflow
    assert "--cov=evidencemesh" in workflow
    assert workflow.count("/usr/bin/git archive") == 2
    assert workflow.count("-m hatchling build") == 2
    assert workflow.count("--target wheel --target sdist") == 2
    assert workflow.count("/usr/bin/cmp --silent") == 2
    assert "hatchling==1.31.0" in workflow
    assert workflow.count('version("hatchling") == "1.31.0"') == 2
    assert 'find_spec("hatchling") is None' in workflow
    assert 'denied_parts = {".git", ".venv", "__pycache__"}' in workflow
    assert "assert not item.issym() and not item.islnk()" in workflow
    assert '"evidencemesh-0.1.0-py3-none-any.whl"' in workflow
    assert '"evidencemesh-0.1.0.tar.gz"' in workflow


def test_workflow_installs_smokes_and_cleans_twice_without_publication() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count('find_spec("evidencemesh") is None') == 2
    assert workflow.count('== "evidencemesh" for item') == 2
    for launcher in ("wheel_cli", "wheel_mcp", "sdist_cli", "sdist_mcp"):
        assert f'/usr/bin/test ! -e "${launcher}"' in workflow
    assert workflow.count('"$uv_path" pip install') == 2
    assert workflow.count("--offline --no-index --no-deps --no-cache --no-build-isolation") == 2
    assert workflow.count('"$uv_path" pip check --python') == 2
    assert 'wheel_reference="evidencemesh @ file://${wheel_one}#sha256=${wheel_sha256}"' in workflow
    assert 'sdist_reference="evidencemesh @ file://${sdist_one}#sha256=${sdist_sha256}"' in workflow
    assert "verify_pep610_archive_sha256" in workflow
    assert 'assert direct_url["url"] == f"{archive.as_uri()}#sha256={expected}"' in workflow
    assert "assert archive_info == {} or declared" in workflow
    assert "assert all(digest == expected for digest in declared)" in workflow
    assert "A2_P2_FORBIDDEN_WORKSPACE" in workflow
    assert workflow.count('"$smoke_script"') == 2
    assert 'harness_root="$A2_P2_1_ROOT/harness/bin"' in workflow
    assert workflow.count("/usr/bin/install --mode=0500") == 2
    assert workflow.count("/usr/bin/sha256sum --check") == 2
    assert "--label wheel" in workflow
    assert "--label sdist" in workflow
    assert '--expected-archive-sha256 "$wheel_sha256"' in workflow
    assert '--expected-archive-sha256 "$sdist_sha256"' in workflow
    assert "PYTHONPATH=" in workflow
    assert workflow.count("if: always()") == 2
    assert 'sudo rm --recursive --force -- "$A2_P2_1_ROOT"' in workflow
    cleanup_at = workflow.index("- name: Remove every ephemeral A2-P2.1 output")
    confirm_at = workflow.index("- name: Confirm A2-P2.1 ephemeral output removal")
    summary_at = workflow.index("- name: Summarize correction only after complete pass and cleanup")
    assert cleanup_at < confirm_at < summary_at

    for forbidden in (
        "actions/upload-artifact",
        "actions/attest",
        "gh release create",
        "git tag ",
        "secrets.",
        "curl ",
        "wget ",
    ):
        assert forbidden not in workflow
