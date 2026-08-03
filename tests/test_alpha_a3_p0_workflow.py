from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/alpha-a3-p0-operator-clean-room-offline.yml"
POLICY = ROOT / "alpha/alpha-a3-p0-operator-clean-room-offline-policy-v1.json"
PROTOCOL = ROOT / "docs/alpha-a3-p0-operator-clean-room-offline-gate-v1.md"
RUNBOOK = ROOT / "docs/alpha-a3-p0-operator-clean-room-runbook-v1.md"
README = ROOT / "README.md"
HARNESS = ROOT / "scripts/verify_alpha_a3_p0_operator_clean_room.py"
UNIT_TEST = ROOT / "tests/test_verify_alpha_a3_p0_operator_clean_room.py"

PARENT_SHA = "41e0d18e1801cbde0bae61dfd85877fddbc64e4d"
PARENT_TREE = "41c74b75f270db66b4f5032172e5dff0f6a32aaa"
PARENT_RUN_ID = 30843140982
PARENT_JOB_ID = 91784859717
PARENT_CI_RUN_ID = 30843139966
WHEEL_SHA256 = "c38841da79c7a71275bda5a925096dc692ce4feabaf2f618233c5379ed1c577a"
WHEEL_SIZE = 146492
HASH = re.compile(r"[0-9a-f]{64}\Z")

ADDITIONS = [
    ".github/workflows/alpha-a3-p0-operator-clean-room-offline.yml",
    "alpha/alpha-a3-p0-operator-clean-room-offline-policy-v1.json",
    "docs/alpha-a3-p0-operator-clean-room-offline-gate-v1.md",
    "docs/alpha-a3-p0-operator-clean-room-runbook-v1.md",
    "scripts/verify_alpha_a3_p0_operator_clean_room.py",
    "tests/test_alpha_a3_p0_workflow.py",
    "tests/test_verify_alpha_a3_p0_operator_clean_room.py",
]
MODIFICATIONS = ["README.md"]
ALLOWED_PATHS = [
    ".github/workflows/alpha-a3-p0-operator-clean-room-offline.yml",
    "README.md",
    "alpha/alpha-a3-p0-operator-clean-room-offline-policy-v1.json",
    "docs/alpha-a3-p0-operator-clean-room-offline-gate-v1.md",
    "docs/alpha-a3-p0-operator-clean-room-runbook-v1.md",
    "scripts/verify_alpha_a3_p0_operator_clean_room.py",
    "tests/test_alpha_a3_p0_workflow.py",
    "tests/test_verify_alpha_a3_p0_operator_clean_room.py",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(POLICY.read_bytes()))


def _assert_hash_or_placeholder(value: str, placeholder: str) -> None:
    assert value == placeholder or HASH.fullmatch(value)


def test_policy_locks_entry_and_immutable_a2_subject() -> None:
    policy = _policy()

    assert policy["schema_version"] == (
        "evidencemesh.alpha-a3-p0-operator-clean-room-offline-policy.v1"
    )
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
    assert policy["immutable_a2_evidence"] == {
        "ci_conclusion": "success",
        "ci_run_id": PARENT_CI_RUN_ID,
        "gate_conclusion": "success",
        "gate_job_id": PARENT_JOB_ID,
        "gate_run_attempt": 1,
        "gate_run_id": PARENT_RUN_ID,
        "sdist_not_rebuilt_by_a3": True,
        "wheel_name": "evidencemesh-0.1.0-py3-none-any.whl",
        "wheel_sha256": WHEEL_SHA256,
        "wheel_size_bytes": WHEEL_SIZE,
    }


def test_policy_freezes_exact_scope_and_one_shot_budgets() -> None:
    policy = _policy()

    assert policy["scope"] == {
        "allowed_additions": ADDITIONS,
        "allowed_modifications": MODIFICATIONS,
        "runtime_and_packaging_immutable_paths": ["src", "pyproject.toml", "uv.lock"],
    }
    assert policy["budgets"] == {
        "branch_fast_forward_updates_maximum": 1,
        "candidate_commits_maximum": 1,
        "changed_files_exact": 8,
        "cli_invocations_exact": 1,
        "controller_offline_installations_exact": 1,
        "dependency_download_commands_maximum": 1,
        "distribution_publications": 0,
        "dns_attempts": 0,
        "evidencemesh_runtime_network_requests": 0,
        "ephemeral_parent_exports_exact": 1,
        "ephemeral_wheel_builds_exact": 1,
        "live_document_requests": 0,
        "live_model_requests": 0,
        "live_provider_requests": 0,
        "live_search_requests": 0,
        "mcp_initialize_requests_exact": 2,
        "mcp_initialized_notifications_exact": 2,
        "mcp_server_processes_exact": 2,
        "mcp_sessions_exact": 2,
        "mcp_tool_requests_exact": 2,
        "operating_system_service_activations": 0,
        "operator_installations_exact": 1,
        "operator_path_seconds_maximum": 600,
        "operator_uninstallations_exact": 1,
        "passive_ipv6_loopback_bind_probes_maximum": 1,
        "retries": 0,
        "toolchain_python_acquisition_commands_maximum": 1,
        "workflow_attempts_maximum": 1,
        "workflow_reruns": 0,
    }
    assert not any(policy["authority"].values())
    assert policy["candidate_decision"] == {
        "decision": "pending_until_dedicated_gate_and_same_head_ci",
        "failed_or_cancelled_attempt_is_terminal": True,
        "pr_remains_draft": True,
        "second_candidate_commit_allowed": False,
    }


def test_policy_locks_clean_room_handoff_lifecycle_and_narrow_claim() -> None:
    policy = _policy()

    assert policy["operator_boundary"] == {
        "checkout_must_be_masked_in_mount_namespace": True,
        "docker_socket_must_be_unavailable": True,
        "environment_allowlist_only": True,
        "existing_unprivileged_identity": "nobody:nogroup",
        "fresh_empty_install_prefix_required": True,
        "home_xdg_tmp_work_distinct_and_state_install_below_work": True,
        "kit_owner": "root:root",
        "kit_writable_by_operator": False,
        "network_namespace_must_differ_from_parent": True,
        "no_system_user_creation_or_deletion": True,
        "operator_uid_must_differ_from_runner_uid": True,
        "private_directory_mode": "0700",
        "process_tree_strace_required": True,
        "secret_and_proxy_environment_forbidden": True,
        "successful_path_process_signals": 0,
    }
    assert policy["operator_contract"] == {
        "cli_commands": ["providers"],
        "descriptor_source": "examples/evidencemesh.mcp.json",
        "descriptor_written_mode": "0600",
        "install_mode": "one_offline_no_index_hashed_transaction",
        "mcp_requests_per_session": ["initialize", "tools/call:health"],
        "mcp_sessions": 2,
        "package_state_after_uninstall": "absent",
        "restart_kind": "second_planned_start_after_first_natural_stop",
        "receipt_schema": "evidencemesh.alpha-a3-p0-operator-clean-room-receipt.v1",
        "state_after_uninstall": "present_and_byte_identical",
        "uninstall_scope": "evidencemesh_package_only",
    }
    assert policy["trace_contract"] == {
        "addressless_inet_socket_creation_allowed_only_for_safe_stream_or_datagram_identity": True,
        "authoritative_parser": "scripts/verify_alpha_a1_p2_named_host.py::_validate_strace",
        "explicit_local_socket_families_allowed": ["AF_LOCAL", "AF_NETLINK", "AF_UNIX"],
        "passive_ipv6_loopback_bind_probes_maximum": 1,
        "raw_packet_destination_ambiguous_or_unexpected_exec_allowed": False,
        "resolved_executable_allowlist": [
            "A3_BASE_PYTHON",
            "handoff/bin/uv",
            "work/install/bin/python",
            "work/install/bin/evidencemesh",
            "work/install/bin/evidencemesh-mcp",
        ],
        "single_strace_file": True,
        "successful_path_kill_tgkill_tkill_syscalls": 0,
    }
    supply_chain = policy["supply_chain"]
    assert supply_chain["uv_version_verified"] == "0.11.33"
    assert supply_chain["hatchling_version_verified"] == "1.31.0"
    assert supply_chain["python_minor_version_verified"] == "3.11.x"
    assert supply_chain["uv_handoff_hash_manifested"] is True
    assert supply_chain["pip_version_and_module_hash_observed_only"] is True
    assert "toolchain_versions_and_hashes_verified" not in supply_chain
    assert policy["successful_claim"] == {
        "automated_operator_simulation": True,
        "cross_platform_validated": False,
        "human_operator_usability_validated": False,
        "live_behavior_validated": False,
        "operating_system_supervision_validated": False,
        "phase_12_ready": False,
        "public_distribution_available": False,
        "public_installation_path_validated": False,
        "recovery_or_rollback_validated": False,
        "scope": (
            "ubuntu_24_04_python_3_11_ephemeral_unpublished_parent_wheel_"
            "install_two_clean_mcp_starts_and_package_uninstall_only"
        ),
        "v1_ready": False,
    }


def test_policy_content_hash_slots_match_current_files_or_explicit_placeholders() -> None:
    policy = _policy()

    slots = {
        "README.md": (README, "__A3_README_SHA256__"),
        "scripts/verify_alpha_a3_p0_operator_clean_room.py": (
            HARNESS,
            "__A3_HARNESS_SHA256__",
        ),
        "tests/test_alpha_a3_p0_workflow.py": (
            Path(__file__),
            "__A3_STATIC_TEST_SHA256__",
        ),
        "tests/test_verify_alpha_a3_p0_operator_clean_room.py": (
            UNIT_TEST,
            "__A3_UNIT_TEST_SHA256__",
        ),
    }
    assert set(policy["scope_hashes"]) == set(slots)
    for relative, (path, placeholder) in slots.items():
        value = policy["scope_hashes"][relative]
        _assert_hash_or_placeholder(value, placeholder)
        if value != placeholder:
            assert value == _sha256(path)

    for section, path, placeholder in (
        ("protocol", PROTOCOL, "__A3_PROTOCOL_SHA256__"),
        ("runbook", RUNBOOK, "__A3_RUNBOOK_SHA256__"),
    ):
        value = policy[section]["sha256"]
        _assert_hash_or_placeholder(value, placeholder)
        if value != placeholder:
            assert value == _sha256(path)


def test_readme_selects_the_a2_parent_without_claiming_public_a3_install() -> None:
    readme = README.read_text(encoding="utf-8")
    normalized = " ".join(readme.split())

    assert readme.count(f"ALPHA_SHA={PARENT_SHA}") == 1
    assert "ALPHA_SHA=145f5f923825ffeaeb485bd680bc79410ab290d1" not in readme
    assert "docs/alpha-a3-p0-operator-clean-room-runbook-v1.md" in readme
    assert "ephemeral, unpublished local wheel" in readme
    assert "it is not a public distribution or a public installation path" in normalized


def test_protocol_and_runbook_define_only_the_automated_clean_stop_path() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())
    runbook = " ".join(RUNBOOK.read_text(encoding="utf-8").split())

    for marker in (
        PARENT_SHA,
        PARENT_TREE,
        str(PARENT_RUN_ID),
        str(PARENT_JOB_ID),
        WHEEL_SHA256,
        "one `pip download` command",
        "existing `nobody:nogroup` identity",
        "private mount namespace replaces the checkout",
        "start MCP session one",
        "start MCP session two",
        "natural server exit",
        "state remains present and byte-identical",
        "does not establish human usability",
    ):
        assert marker in protocol
    for marker in (
        "not a public installation guide",
        WHEEL_SHA256,
        "--offline",
        "--no-index",
        "--require-hashes",
        "evidencemesh providers",
        "MCP `initialize`",
        "one `tools/call` for `health`",
        "natural server exit",
        "package removal only",
        "does not inject a crash",
    ):
        assert marker in runbook


def test_workflow_is_exact_read_only_direct_child_and_hash_locked() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)
    assert isinstance(parsed, dict)
    triggers = parsed.get("on", parsed.get(True))

    assert triggers == {"pull_request": {"types": ["synchronize"], "paths": ALLOWED_PATHS}}
    assert parsed["permissions"] == {"contents": "read"}
    assert parsed["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert parsed["concurrency"]["cancel-in-progress"] is False
    assert "workflow_dispatch" not in workflow
    assert "push:" not in workflow
    assert "github.run_attempt == 1" in workflow
    assert "github.event.pull_request.draft == true" in workflow
    assert f"github.event.before == '{PARENT_SHA}'" in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-tags: false" in workflow
    assert PARENT_SHA in workflow and PARENT_TREE in workflow
    assert f"A2_ACCEPTED_RUN_ID: {PARENT_RUN_ID}" in workflow
    assert f"A2_ACCEPTED_JOB_ID: {PARENT_JOB_ID}" in workflow
    assert f"A2_ACCEPTED_CI_RUN_ID: {PARENT_CI_RUN_ID}" in workflow
    assert 'test "${#changed_statuses[@]}" = 8' in workflow
    for path in ADDITIONS:
        assert f"$'A\\t{path}'" in workflow
    assert "$'M\\tREADME.md'" in workflow
    assert 'git diff --quiet "$A2_ACCEPTED_HEAD" HEAD -- src pyproject.toml uv.lock' in workflow
    for placeholder in (
        "__A3_HARNESS_SHA256__",
        "__A3_UNIT_TEST_SHA256__",
        "__A3_POLICY_SHA256__",
        "__A3_PROTOCOL_SHA256__",
        "__A3_RUNBOOK_SHA256__",
        "__A3_README_SHA256__",
        "__A3_STATIC_TEST_SHA256__",
    ):
        key = placeholder.removeprefix("__A3_").removesuffix("__")
        match = re.search(rf"{key}: ([^\n]+)", workflow)
        assert placeholder in workflow or (match is not None and HASH.fullmatch(match[1]))


def test_workflow_builds_exact_parent_and_one_complete_hashed_wheelhouse() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("git archive --format=tar") == 1
    assert '"$A2_ACCEPTED_HEAD"' in workflow
    assert workflow.count("-m hatchling build") == 1
    assert "--target wheel" in workflow
    assert "--target sdist" not in workflow
    assert WHEEL_SHA256 in workflow
    assert str(WHEEL_SIZE) in workflow
    assert workflow.count("uv export") == 2
    assert 'export TMPDIR="$A3_ROOT/build/tmp"' in workflow
    assert 'export RUFF_CACHE_DIR="$A3_ROOT/build/ruff-cache"' in workflow
    assert '--basetemp "$A3_ROOT/build/pytest"' in workflow
    assert "--locked" in workflow
    assert "--no-dev" in workflow
    assert "--no-emit-project" in workflow
    assert workflow.count("-m pip --isolated \\") == 2
    assert len(re.findall(r"^\s+download \\$", workflow, flags=re.MULTILINE)) == 1
    assert "download \\\n              --no-cache-dir" in workflow
    assert "--disable-pip-version-check" in workflow
    assert "--no-input" in workflow
    assert "--retries 0" in workflow
    assert "PIP_CONFIG_FILE=/dev/null" in workflow
    assert "--require-hashes" in workflow
    assert "--only-binary=:all:" in workflow
    assert "runtime-install-plan.json" in workflow
    assert "--dry-run" in workflow
    assert "--ignore-installed" in workflow
    assert 'source.parent == supply and source.suffix == ".whl"' in workflow
    assert "SHA256SUMS" in workflow
    assert "find . -type f ! -path './SHA256SUMS'" in workflow
    assert "evidencemesh==0.1.0 \\\\" in workflow
    assert "parse_wheel_filename" in workflow
    assert "len(projects) == len(set(projects))" in workflow
    assert "sudo chown --recursive root:root" in workflow
    assert "sudo --user=nobody test -w" in workflow


def test_workflow_masks_source_drops_privileges_and_invokes_declared_driver() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "/usr/bin/unshare --mount --net --propagation private" in workflow
    assert "mode=0000" in workflow
    assert "cd /" in workflow
    assert 'mount --bind "$mask_root" "$workspace"' in workflow
    assert "remount,bind,ro,nosuid,nodev,noexec" in workflow
    assert 'cd "$operator_work"' in workflow
    assert "test -r /var/run/docker.sock" in workflow
    assert "test -w /var/run/docker.sock" in workflow
    assert "/usr/bin/setpriv" in workflow
    assert '--reuid="$uid"' in workflow
    assert '--regid="$gid"' in workflow
    assert "--clear-groups" in workflow
    assert "--no-new-privs" in workflow
    assert "/usr/bin/env -i" in workflow
    assert "/usr/bin/strace -f -qq" in workflow
    assert "/usr/bin/strace -ff" not in workflow
    assert "-e trace=network,process,signal" in workflow
    assert "--expected-operator-uid" in workflow
    assert "--producer-uid" in workflow
    assert "--parent-net-namespace" in workflow
    assert "--parent-mount-namespace" in workflow
    assert "--expected-wheel-sha256" in workflow
    assert "--expected-wheel-size 146492" in workflow
    assert "--timeout-seconds 300" in workflow
    assert '--state-root "$operator_work/state"' in workflow
    assert '--install-root "$operator_work/install"' in workflow
    assert 'sudo chown --recursive "$(id -u):$(id -g)"' in workflow
    assert "scripts/verify_alpha_a1_p2_named_host.py" in workflow
    assert "module._validate_strace(trace_path, allowed_execs)" in workflow
    assert '"$A3_BASE_PYTHON" \\' in workflow
    assert '"$A3_HANDOFF/bin/uv" \\' in workflow
    assert '"$A3_OPERATOR_ROOT/work/install/bin/python" \\' in workflow
    assert '"$A3_OPERATOR_ROOT/work/install/bin/evidencemesh" \\' in workflow
    assert "\"$A3_OPERATOR_ROOT/work/install/bin/evidencemesh-mcp\" <<'PY'" in workflow
    assert "addressless_inet_socket_creations" in workflow
    assert "explicit_local_socket_syscalls" in workflow
    assert "passive_ipv6_loopback_bind_probes" in workflow
    assert "A3_STRACE_EXECVE_COUNT" in workflow
    assert "kill|tgkill|tkill" in workflow
    assert workflow.index('sudo chown --recursive "$(id -u):$(id -g)"') < workflow.index(
        "module._validate_strace(trace_path, allowed_execs)"
    )
    assert "connect|sendto|sendmsg|sendmmsg" not in workflow
    assert "socket\\(AF_INET6?" not in workflow


def test_workflow_validates_receipt_cleans_always_and_never_publishes() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "evidencemesh.alpha-a3-p0-operator-clean-room-receipt.v1" in workflow
    assert 'receipt["claim"]["restartability"] is True' in workflow
    assert 'receipt["claim"]["recovery"] is False' in workflow
    assert 'receipt["budgets"]["logical_mcp_requests"] == 4' in workflow
    assert 'receipt["budgets"]["health_tool_calls"] == 2' in workflow
    assert 'receipt["budgets"]["cli_invocations"] == 1' in workflow
    assert 'receipt["installation"]["pip_checks_passed"] == 2' in workflow
    assert 'all(value == 0 for value in receipt["traffic"].values())' in workflow
    assert workflow.count("if: always()") == 2
    assert 'sudo rm --recursive --force -- "$A3_ROOT"' in workflow
    cleanup_at = workflow.index("- name: Remove every ephemeral A3-P0 output")
    confirm_at = workflow.index("- name: Confirm complete A3-P0 cleanup")
    summary_at = workflow.index("- name: Summarize only after acceptance and cleanup")
    assert cleanup_at < confirm_at < summary_at

    for forbidden in (
        "actions/upload-artifact",
        "actions/attest",
        "gh release create",
        "git tag ",
        "secrets.",
        "workflow_dispatch",
        "useradd",
        "userdel",
    ):
        assert forbidden not in workflow
