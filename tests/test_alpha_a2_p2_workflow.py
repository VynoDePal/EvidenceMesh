from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/alpha-a2-p2-installed-distribution-offline-gate-v1.md"
POLICY = ROOT / "alpha/alpha-a2-p2-installed-distribution-offline-policy-v1.json"
WORKFLOW = ROOT / ".github/workflows/alpha-a2-p2-installed-distribution-offline.yml"

PARENT_SHA = "d284f987f712d93980c4d0cf51bd6491153decbe"
PARENT_TREE = "bdddbcb3dfea16a11d584ebfbb74b44f8cc20966"
PROTOCOL_SHA256 = "2b64d1364b5c90894e109d016afa85ef466e9b4f285b2f2c86985b3ad7189cd1"
POLICY_SHA256 = "6356e5da4dc9ddb5db6cc643a894cc6dd404687297aa86c2005c1963303936f8"
ALLOWED_PATHS = [
    ".github/workflows/alpha-a2-p2-installed-distribution-offline.yml",
    "alpha/alpha-a2-p2-installed-distribution-offline-policy-v1.json",
    "docs/alpha-a2-p2-installed-distribution-offline-gate-v1.md",
    "scripts/smoke_installed_a2_p2.py",
    "tests/test_alpha_a2_p2_workflow.py",
    "tests/test_smoke_installed_a2_p2.py",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(POLICY.read_bytes()))


def test_protocol_and_policy_are_hash_locked_to_the_exact_parent() -> None:
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
        "path": "docs/alpha-a2-p2-installed-distribution-offline-gate-v1.md",
        "sha256": PROTOCOL_SHA256,
    }


def test_policy_freezes_one_shot_scope_budgets_and_no_go_authority() -> None:
    policy = _policy()

    assert policy["schema_version"] == (
        "evidencemesh.alpha-a2-p2-installed-distribution-offline-policy.v1"
    )
    assert policy["scope"] == {
        "allowed_paths": ALLOWED_PATHS,
        "runtime_and_packaging_immutable_paths": ["src", "pyproject.toml", "uv.lock"],
    }
    assert policy["budgets"] == {
        "branch_ref_updates_maximum": 1,
        "build_invocations_maximum": 2,
        "candidate_commits_maximum": 1,
        "changed_files_maximum": 6,
        "candidate_distribution_installations_maximum": 2,
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
        "failure_or_cancellation_is_terminal": True,
        "historical_evidence_reinterpreted": False,
        "pr_remains_draft": True,
    }
    assert policy["successful_claim"] == {
        "local_offline_technical_alpha_v0_1_0_a2": True,
        "phase_12_ready": False,
        "public_distribution_available": False,
        "real_os_supervision_proven": False,
        "scope": "single_host_local_offline_installed_distribution_successor_only",
        "v1_ready": False,
    }


def test_policy_requires_reproducible_builds_and_separate_installed_smokes() -> None:
    policy = _policy()

    assert policy["build"] == {
        "builds_per_clean_export": 1,
        "clean_git_exports": 2,
        "corresponding_archives_byte_identical_required": True,
        "digest_and_size_exported_for_final_receipt": True,
        "expected_archive_names": [
            "evidencemesh-0.1.0-py3-none-any.whl",
            "evidencemesh-0.1.0.tar.gz",
        ],
        "source_date_epoch": "exact_candidate_commit_timestamp",
        "targets_per_build": ["wheel", "sdist"],
    }
    assert policy["installation"] == {
        "archive_sha256_bound_independently": True,
        "dependency_acquisition_before_network_isolation": True,
        "editable_install_allowed": False,
        "installed_archive_kinds": ["wheel", "sdist"],
        "isolated_environment_count": 2,
        "network_namespace_disabled_during_install_and_smoke": True,
        "pep610_archive_sha256_declaration_required": True,
        "pep610_exact_archive_url_required": True,
        "pep610_hashed_direct_requirement_required": True,
        "post_install_uv_pip_check_required": True,
        "preinstall_package_and_launchers_absent_required": True,
        "runtime_dependency_profile_before_install": "locked_no_dev_no_project",
        "sdist_build_backend_acquired_separately": "hatchling==1.31.0",
        "sdist_build_isolation_allowed": False,
        "uv_flags": [
            "--offline",
            "--no-index",
            "--no-deps",
            "--no-cache",
            "--no-build-isolation",
        ],
    }
    assert policy["smoke"]["a2_runtime_blob_count"] == 5
    assert policy["smoke"]["distribution_metadata_and_record_binding_required"] is True
    assert policy["smoke"]["installed_origin_within_exact_environment_required"] is True
    assert policy["smoke"]["mock_transport_only"] is True
    assert policy["smoke"]["source_tree_import_allowed"] is False
    assert policy["validation"] == {
        "coverage_minimum_percent": 85.0,
        "docker_socket_readable_or_writable": False,
        "full_suite_invocations": 1,
        "installed_smoke_invocations": 2,
        "network_namespace": "/usr/bin/unshare --net",
        "network_namespace_must_differ_from_parent": True,
        "policy_hash_locked_in_workflow": True,
        "protocol_hash_locked_in_workflow": True,
        "uv_offline_during_all_gates": True,
    }
    assert policy["canonical_environment"]["hatchling_version"] == "1.31.0"
    assert policy["archive_inventory"] == {
        "absolute_or_parent_escaping_members_allowed": False,
        "duplicate_members_allowed": False,
        "private_key_or_environment_file_names_allowed": False,
        "sdist_hardlinks_or_special_files_allowed": False,
        "symlinks_allowed": False,
        "vcs_venv_or_bytecode_cache_members_allowed": False,
    }
    assert policy["ephemeral_control"] == {
        "cleanup_confirmed_before_pass_summary": True,
        "root_template": (
            "${RUNNER_TEMP}/evidencemesh-alpha-a2-p2-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
        ),
        "preexisting_root_allowed": False,
        "preexisting_symlink_allowed": False,
    }


def test_protocol_states_entry_stop_and_narrow_claim_boundaries() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    for marker in (
        "pending_until_one_shot_ci",
        PARENT_SHA,
        PARENT_TREE,
        "exact six-file allowlist",
        "`src`, `pyproject.toml`, and `uv.lock` are immutable",
        "acquired before isolation",
        "`/usr/bin/unshare --net`",
        "two independent clean `git archive` exports",
        "byte-for-byte identical",
        "complete wheel and sdist inventories",
        "first environment installs the first build's wheel",
        "second installs the first build's sdist",
        "distribution metadata/RECORD",
        "`evidencemesh @ file://...#sha256=...`",
        "five A2 runtime blobs",
        "`httpx.MockTransport`",
        "deleted by an unconditional final cleanup",
        "Stop without retry or reinterpretation",
        "A failed or cancelled run is terminal",
        "single-host, offline technical alpha",
        "Phase 12 readiness",
        "even if BrowseComp-Plus never responds",
    ):
        assert marker in protocol


def test_workflow_is_exact_one_shot_read_only_and_hash_locked() -> None:
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
    assert POLICY_SHA256 in workflow
    assert PROTOCOL_SHA256 in workflow
    assert (
        'echo "$POLICY_SHA256  '
        'alpha/alpha-a2-p2-installed-distribution-offline-policy-v1.json"' in workflow
    )
    assert (
        'echo "$PROTOCOL_SHA256  '
        'docs/alpha-a2-p2-installed-distribution-offline-gate-v1.md"' in workflow
    )
    assert 'test "$(git rev-list --parents --max-count=1 HEAD)"' in workflow
    assert (
        'git diff --quiet "$A2_P1_1_ACCEPTED_HEAD" HEAD -- src pyproject.toml uv.lock' in workflow
    )
    assert "--diff-filter=ACDMRT" in workflow
    assert 'test "${#changed_paths[@]}" = 6' in workflow
    for path in ALLOWED_PATHS:
        assert workflow.count(path) >= 2


def test_workflow_acquires_before_isolation_and_builds_reproducibly() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    acquisition_at = workflow.index("uv sync --extra dev --locked --python 3.11 --no-cache")
    isolation_at = workflow.index("/usr/bin/unshare --net")
    assert acquisition_at < isolation_at
    assert workflow.count("--no-install-project --python 3.11 --no-cache") == 2
    assert workflow.count("--no-dev --no-install-project --python 3.11 --no-cache") == 2
    assert "enable-cache: false" in workflow
    assert "UV_HTTP_RETRIES: 0" in workflow
    assert "UV_OFFLINE=1" in workflow
    assert 'test ! -e "$A2_P2_ROOT"' in workflow
    assert 'test ! -L "$A2_P2_ROOT"' in workflow
    root_assignment = (
        'A2_P2_ROOT="${RUNNER_TEMP}/evidencemesh-alpha-a2-p2-'
        '${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"'
    )
    assert workflow.count(root_assignment) == 4
    assert "parent_network_namespace=$(readlink /proc/self/ns/net)" in workflow
    assert 'test "$isolated_network_namespace" != "$parent_network_namespace"' in workflow
    assert '"${run_isolated[@]}" /usr/bin/test ! -r /var/run/docker.sock' in workflow
    assert '"${run_isolated[@]}" /usr/bin/test ! -w /var/run/docker.sock' in workflow
    assert "--clear-groups" in workflow
    assert "--no-new-privs" in workflow
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
    assert "-m ruff format --check ." in workflow
    assert "-m ruff check ." in workflow
    assert "-m mypy src" in workflow
    assert "--cov=evidencemesh" in workflow


def test_workflow_installs_and_smokes_wheel_and_sdist_separately_then_cleans() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count('find_spec("evidencemesh") is None') == 2
    assert workflow.count('== "evidencemesh" for item') == 2
    for launcher in ("wheel_cli", "wheel_mcp", "sdist_cli", "sdist_mcp"):
        assert f'/usr/bin/test ! -e "${launcher}"' in workflow
    assert workflow.count('"$uv_path" pip install') == 2
    assert workflow.count("--offline --no-index --no-deps --no-cache --no-build-isolation") == 2
    assert '--python "$wheel_python"' in workflow
    assert '--python "$sdist_python"' in workflow
    assert workflow.count('"$uv_path" pip check --python') == 2
    assert 'wheel_reference="evidencemesh @ file://${wheel_one}#sha256=${wheel_sha256}"' in workflow
    assert 'sdist_reference="evidencemesh @ file://${sdist_one}#sha256=${sdist_sha256}"' in workflow
    assert "verify_pep610_archive_sha256" in workflow
    assert 'assert direct_url["url"] == f"{archive.as_uri()}#sha256={expected}"' in workflow
    assert "assert archive_info == {} or declared" in workflow
    assert "assert all(digest == expected for digest in declared)" in workflow
    assert "A2_P2_FORBIDDEN_WORKSPACE" in workflow
    assert workflow.count('"$smoke_script"') == 2
    assert 'harness_root="$A2_P2_ROOT/harness/bin"' in workflow
    assert workflow.count("/usr/bin/install --mode=0500") == 2
    assert workflow.count("/usr/bin/sha256sum --check") == 2
    assert "--label wheel" in workflow
    assert "--label sdist" in workflow
    assert '--expected-archive-sha256 "$wheel_sha256"' in workflow
    assert '--expected-archive-sha256 "$sdist_sha256"' in workflow
    assert "PYTHONPATH=" in workflow
    assert 'echo "A2_P2_WHEEL_SHA256=$wheel_sha256"' in workflow
    assert 'echo "A2_P2_SDIST_SHA256=$sdist_sha256"' in workflow
    assert workflow.count("if: always()") == 2
    assert 'sudo rm --recursive --force -- "$A2_P2_ROOT"' in workflow
    assert 'test ! -e "$A2_P2_ROOT"' in workflow
    cleanup_at = workflow.index("- name: Remove every ephemeral A2-P2 output")
    confirm_at = workflow.index("- name: Confirm ephemeral output removal")
    summary_at = workflow.index(
        "- name: Summarize the narrow technical-alpha boundary after cleanup"
    )
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
