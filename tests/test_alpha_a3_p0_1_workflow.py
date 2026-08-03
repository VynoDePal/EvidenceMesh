from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/alpha-a3-p0-1-acceptance-reconciliation-offline.yml"
POLICY = ROOT / "alpha/alpha-a3-p0-1-acceptance-reconciliation-policy-v1.json"
PROTOCOL = ROOT / "docs/alpha-a3-p0-1-acceptance-reconciliation-offline-gate-v1.md"
CORRECTED_A1_TEST = ROOT / "tests/test_alpha_a1_p0_installability.py"

FAILED_HEAD = "88cf431b67619624c09840174451780b78a9ae41"
FAILED_TREE = "960bacb500ad390d4ae3a38bc941e30c85e80a8d"
FAILED_RUN_ID = 30852239811
FAILED_JOB_ID = 91814758947
FAILED_CI_RUN_ID = 30852239420
FAILED_CI_JOB_IDS = [91814763021, 91814777751, 91814777055]
A2_HEAD = "41e0d18e1801cbde0bae61dfd85877fddbc64e4d"
A2_TREE = "41c74b75f270db66b4f5032172e5dff0f6a32aaa"
WHEEL_SHA256 = "c38841da79c7a71275bda5a925096dc692ce4feabaf2f618233c5379ed1c577a"
WHEEL_SIZE = 146492
OLD_A1_HEAD = "145f5f923825ffeaeb485bd680bc79410ab290d1"

ADDITIONS = [
    ".github/workflows/alpha-a3-p0-1-acceptance-reconciliation-offline.yml",
    "alpha/alpha-a3-p0-1-acceptance-reconciliation-policy-v1.json",
    "docs/alpha-a3-p0-1-acceptance-reconciliation-offline-gate-v1.md",
    "tests/test_alpha_a3_p0_1_workflow.py",
]
MODIFICATIONS = ["tests/test_alpha_a1_p0_installability.py"]
ALLOWED_PATHS = [*ADDITIONS, *MODIFICATIONS]

IMMUTABLE_A3 = {
    ".github/workflows/alpha-a3-p0-operator-clean-room-offline.yml": (
        "aaba296f3da13fc8405a6e579a2478b943a3a17a12ca21eaacae46d76d194e5e"
    ),
    "README.md": "0a532c276a58f86b7c6134843c2779dfb8d5e9cc75ba8a00a794991b37c16f7d",
    "alpha/alpha-a3-p0-operator-clean-room-offline-policy-v1.json": (
        "43255b673e4a90787a3bc95db3398d61d09fe9932f83978b5143816b2d3e62cf"
    ),
    "docs/alpha-a3-p0-operator-clean-room-offline-gate-v1.md": (
        "d71c6c035b107a03eff9130163250f344b4c4eb6ef7ba894304ade9287c022a1"
    ),
    "docs/alpha-a3-p0-operator-clean-room-runbook-v1.md": (
        "ec45efe1fffa9acb8acc1127383b4a97c684bf43a4a16316d078717800c8b791"
    ),
    "scripts/verify_alpha_a3_p0_operator_clean_room.py": (
        "d7571ca65514e05ad3415d029ed67279f70141238152a8f6e5ef618975e19b83"
    ),
    "tests/test_alpha_a3_p0_workflow.py": (
        "0aecc7ffe84facad14225420be58868776ded2e66c2f475c479c5d527cbfc7fb"
    ),
    "tests/test_verify_alpha_a3_p0_operator_clean_room.py": (
        "230f1dda7bbe3c08d042c122df7c5b18a6b533dca44c4eb8dbd58b548b373d70"
    ),
}
IMMUTABLE_SUPPORT = {
    "alpha/alpha_a1_p0_installability_policy_v1.json": (
        "7e3fbdb3ddb95c6dd25f82626fa0a05cd041c72a53aa725ddb2b081ad64096d8"
    ),
    "scripts/verify_alpha_a1_p0_installability.py": (
        "8fa9ec81c9c159a634f1f7ea573aa371a2401dbd6c0abc59701f22ba2a35e8fe"
    ),
    "scripts/verify_alpha_a1_p2_named_host.py": (
        "d52bf8cb9f57daed160a2dd10b7e28063640ee2893033c86defaeac7bf718cf9"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(POLICY.read_bytes()))


def test_policy_locks_distinct_direct_child_and_failed_evidence() -> None:
    policy = _policy()

    assert policy["schema_version"] == (
        "evidencemesh.alpha-a3-p0.1-acceptance-reconciliation-offline-policy.v1"
    )
    assert policy["entry"] == {
        "branch": "agent/evidencemesh-v0.1",
        "direct_child_required": True,
        "exact_parent_commit_sha": FAILED_HEAD,
        "exact_parent_tree_sha": FAILED_TREE,
        "merge_commit_allowed": False,
        "pull_request": 1,
        "pull_request_must_remain_draft": True,
        "repository": "VynoDePal/EvidenceMesh",
    }
    assert policy["historical_failures"] == {
        "dedicated_a3": {
            "conclusion": "failure",
            "failed_before_operator_journey": True,
            "immutable": True,
            "job_id": FAILED_JOB_ID,
            "product_runtime_defect_observed": False,
            "root_cause": ("literal_multiline_grep_could_not_match_the_wrapped_readme_sentence"),
            "run_attempt": 1,
            "run_id": FAILED_RUN_ID,
        },
        "ordinary_ci": {
            "conclusion": "failure",
            "failed_test_count_per_python_job": 1,
            "immutable": True,
            "product_runtime_defect_observed": False,
            "python_job_ids": FAILED_CI_JOB_IDS,
            "root_cause": "one_stale_a1_readme_source_commit_expectation",
            "run_id": FAILED_CI_RUN_ID,
        },
    }


def test_policy_preserves_exact_a2_distribution_subject() -> None:
    evidence = _policy()["immutable_a2_evidence"]

    assert evidence == {
        "ci_conclusion": "success",
        "ci_run_id": 30843139966,
        "gate_conclusion": "success",
        "gate_job_id": 91784859717,
        "gate_run_attempt": 1,
        "gate_run_id": 30843140982,
        "product_commit_sha": A2_HEAD,
        "product_tree_sha": A2_TREE,
        "sdist_not_rebuilt_by_a3": True,
        "wheel_name": "evidencemesh-0.1.0-py3-none-any.whl",
        "wheel_sha256": WHEEL_SHA256,
        "wheel_size_bytes": WHEEL_SIZE,
    }


def test_policy_freezes_scope_budgets_authority_and_terminal_decision() -> None:
    policy = _policy()

    assert policy["scope"] == {
        "allowed_additions": ADDITIONS,
        "allowed_modifications": MODIFICATIONS,
        "runtime_and_packaging_immutable_paths": ["src", "pyproject.toml", "uv.lock"],
    }
    assert policy["budgets"] == {
        "branch_fast_forward_updates_maximum": 1,
        "candidate_commits_maximum": 1,
        "changed_files_exact": 5,
        "cli_invocations_exact": 1,
        "controller_offline_installations_exact": 1,
        "dependency_download_commands_maximum": 1,
        "distribution_publications": 0,
        "dns_attempts": 0,
        "ephemeral_parent_exports_exact": 1,
        "ephemeral_wheel_builds_exact": 1,
        "evidencemesh_runtime_network_requests": 0,
        "full_suite_dns_attempts": 0,
        "full_suite_external_destination_attempts": 0,
        "full_suite_invocations_exact": 1,
        "full_suite_network_namespaces_exact": 1,
        "full_suite_network_trace_groups_exact": 1,
        "historical_failed_a3_workflow_reruns": 0,
        "historical_failed_ci_reruns": 0,
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
        "decision": "pending_until_distinct_gate_and_same_head_ci",
        "failed_or_cancelled_attempt_is_terminal": True,
        "historical_failures_remain_failed": True,
        "pr_remains_draft": True,
        "second_candidate_commit_allowed": False,
    }
    reconciliation = policy["reconciliation"]
    assert reconciliation["full_suite_dns_attempts_exact"] == 0
    assert reconciliation["full_suite_external_destination_attempts_exact"] == 0
    assert reconciliation["full_suite_loopback_only_namespace"] is True
    assert reconciliation["full_suite_network_namespace_distinct"] is True
    assert reconciliation["full_suite_network_trace_is_run_scoped"] is True
    assert reconciliation["full_suite_runs_as_runner_uid"] is True
    assert reconciliation["full_suite_uses_neutral_primary_gid"] is True


def test_every_failed_parent_and_supporting_control_is_byte_exact() -> None:
    policy = _policy()

    assert policy["immutable_a3_parent_content"] == IMMUTABLE_A3
    assert policy["immutable_supporting_controls"] == IMMUTABLE_SUPPORT
    for relative, expected in {**IMMUTABLE_A3, **IMMUTABLE_SUPPORT}.items():
        assert _sha256(ROOT / relative) == expected


def test_new_content_is_fully_sealed_without_hash_cycles() -> None:
    policy = _policy()
    workflow = WORKFLOW.read_text(encoding="utf-8")
    policy_source = POLICY.read_text(encoding="utf-8")

    assert "__A3_P0_1_" not in workflow
    assert "__A3_P0_1_" not in policy_source
    assert policy["protocol"] == {
        "path": "docs/alpha-a3-p0-1-acceptance-reconciliation-offline-gate-v1.md",
        "sha256": _sha256(PROTOCOL),
    }
    assert policy["reconciliation"]["a1_correction_sha256"] == _sha256(CORRECTED_A1_TEST)
    assert policy["reconciliation"]["static_test_sha256"] == _sha256(Path(__file__))


def test_a1_test_preserves_history_and_reconciles_current_quick_start() -> None:
    source = CORRECTED_A1_TEST.read_text(encoding="utf-8")

    for marker in (
        f'CURRENT_ALPHA_SOURCE_COMMIT = "{A2_HEAD}"',
        f'assert gate.SOURCE_COMMIT == "{OLD_A1_HEAD}"',
        "assert gate.SOURCE_COMMIT != CURRENT_ALPHA_SOURCE_COMMIT",
        "assert gate.SOURCE_COMMIT not in quick_start",
        'normalized_quick_start = " ".join(quick_start.split())',
        'assert "automated Ubuntu 24.04/Python 3.11 simulation"',
        'assert "macOS has not been validated" in normalized_quick_start',
        'assert "native windows is not supported" in normalized_quick_start.lower()',
    ):
        assert marker in source
    assert 'assert "Ubuntu 24.04 x86_64" in quick_start' not in source
    assert "assert gate.SOURCE_COMMIT in quick_start" not in source


def test_protocol_records_exact_scope_order_stop_and_claim_boundaries() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    for marker in (
        "pending_until_distinct_gate_and_same_head_ci",
        FAILED_HEAD,
        FAILED_TREE,
        str(FAILED_RUN_ID),
        str(FAILED_JOB_ID),
        str(FAILED_CI_RUN_ID),
        "Exact five-path scope",
        "whitespace-stable platform statements",
        "One full candidate suite with coverage",
        "original runner UID",
        "neutral `nogroup` primary GID",
        "distinct private network namespace",
        "no default route",
        "non-loopback destination",
        "local resolver IPC endpoint",
        "Complete unchanged A3 operator journey",
        A2_HEAD,
        WHEEL_SHA256,
        "Stop without retry",
        "A failed or cancelled A3-P0.1 attempt is terminal",
        "Same-HEAD ordinary CI remains independently required",
        "Phase 12 readiness",
        "V1 readiness",
    ):
        assert marker in protocol


def test_workflow_trigger_permissions_and_lineage_are_exact() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)
    assert isinstance(parsed, dict)
    triggers = parsed.get("on", parsed.get(True))

    assert triggers == {"pull_request": {"types": ["synchronize"], "paths": ALLOWED_PATHS}}
    assert parsed["permissions"] == {"contents": "read"}
    assert parsed["concurrency"]["cancel-in-progress"] is False
    assert "workflow_dispatch" not in workflow
    assert "push:" not in workflow
    assert "github.run_attempt == 1" in workflow
    assert "github.event.pull_request.number == 1" in workflow
    assert "github.event.pull_request.draft == true" in workflow
    assert "github.event.pull_request.head.ref == 'agent/evidencemesh-v0.1'" in workflow
    assert f"github.event.before == '{FAILED_HEAD}'" in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-tags: false" in workflow
    assert '"$EXPECTED_HEAD $A3_FAILED_HEAD"' in workflow
    assert 'test "${#changed_statuses[@]}" = 5' in workflow
    for path in ADDITIONS:
        assert f"$'A\\t{path}'" in workflow
    assert "$'M\\ttests/test_alpha_a1_p0_installability.py'" in workflow


def test_workflow_locks_a3_a1_and_a2_subject_before_acquisition() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    acquisition_at = workflow.index("- name: Set up pinned uv without an Actions cache")
    preflight = workflow[:acquisition_at]

    assert f"A3_FAILED_HEAD: {FAILED_HEAD}" in preflight
    assert f"A3_FAILED_TREE: {FAILED_TREE}" in preflight
    assert f"A2_ACCEPTED_HEAD: {A2_HEAD}" in preflight
    assert f"A2_ACCEPTED_TREE: {A2_TREE}" in preflight
    assert 'test "$(git rev-parse "$A2_ACCEPTED_HEAD^{tree}")"' in preflight
    assert 'git show "$A2_ACCEPTED_HEAD:README.md"' in preflight
    assert 'git show "$A2_ACCEPTED_HEAD:examples/evidencemesh.mcp.json"' in preflight
    for relative, expected in {**IMMUTABLE_A3, **IMMUTABLE_SUPPORT}.items():
        assert relative in preflight
        assert expected in preflight
    assert "src pyproject.toml uv.lock" in preflight


def test_workflow_normalizes_readme_and_runs_full_suite_before_operator() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    normalized_at = workflow.index(
        'normalized = " ".join(Path("README.md").read_text(encoding="utf-8").split())'
    )
    suite_at = workflow.index('PYTHONPATH="$workspace/src"')
    operator_at = workflow.index("- name: Execute the complete bounded clean-room operator journey")

    assert normalized_at < suite_at < operator_at
    assert workflow.count('"$A3_CONTROLLER_PYTHON" -m pytest') == 1
    assert "-c pyproject.toml" in workflow
    assert '--basetemp "$A3_BASETEMP"' in workflow
    assert 'full_suite_basetemp="$A3_ROOT/build/pytest"' in workflow
    assert "--cov=evidencemesh" in workflow
    assert "--cov-report=term-missing" in workflow
    assert "-p no:cacheprovider" in workflow
    assert 'export COVERAGE_FILE="$A3_ROOT/build/.coverage"' in workflow
    assert "tests/test_alpha_a3_p0_1_workflow.py" in workflow
    assert "tests/test_alpha_a1_p0_installability.py" in workflow


def test_full_suite_is_distinct_network_isolated_traced_and_fail_closed() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    suite_at = workflow.index('full_suite_trace="$A3_ROOT/build/full-suite-network.strace"')
    operator_at = workflow.index("- name: Execute the complete bounded clean-room operator journey")
    suite = workflow[suite_at:operator_at]

    assert "sudo /usr/bin/unshare --net --" in suite
    assert 'test "$child_netns" != "$parent_netns"' in suite
    assert '"$ip_bin" link set dev lo up' in suite
    assert 'test "${#links[@]}" = 1' in suite
    assert 'test -z "$("$ip_bin" -4 route show default)"' in suite
    assert 'test -z "$("$ip_bin" -6 route show default)"' in suite
    assert '--reuid="$expected_uid"' in suite
    assert "isolated_gid=$(id -g nobody)" in suite
    assert 'test "$isolated_gid" != "$runner_gid"' in suite
    assert 'test "$(id -gn nobody)" = nogroup' in suite
    assert '--regid="$isolated_gid"' in suite
    assert "--clear-groups" in suite
    assert "--bounding-set=-all" in suite
    assert "--no-new-privs" in suite
    assert "/usr/bin/env -i" in suite
    assert "/usr/bin/strace" in suite
    assert "-ff" in suite
    assert "-yy" in suite
    assert "-e trace=network" in suite
    assert '"dns_attempts": 0' in suite
    assert '"external_destination_attempts": 0' in suite
    assert "address.is_loopback" in suite
    assert "53 in ports" in suite
    assert 'print("A3_FULL_SUITE_DNS_ATTEMPTS=0")' in suite
    assert 'print("A3_FULL_SUITE_EXTERNAL_ATTEMPTS=0")' in suite
    assert suite.index('"$A3_CONTROLLER_PYTHON" -m pytest') < suite.index(
        'print("A3_FULL_SUITE_DNS_ATTEMPTS=0")'
    )
    assert suite.index('print("A3_FULL_SUITE_DNS_ATTEMPTS=0")') < suite.index(
        'echo "A3_FULL_SUITE_PASSED=1"'
    )
    for proxy in ("HTTP_PROXY=", "HTTPS_PROXY=", "ALL_PROXY=", "NO_PROXY="):
        assert proxy not in suite


def test_workflow_repeats_supply_operator_trace_and_lifecycle_contract() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("uv python install 3.11") == 1
    assert workflow.count("download \\") == 1
    assert workflow.count("--retries 0") == 2
    assert workflow.count("uv export \\") == 2
    assert workflow.count("-m hatchling build") == 1
    assert 'echo "$A2_WHEEL_SHA256  $built_wheel"' in workflow
    assert "sudo /usr/bin/unshare --mount --net --propagation private" in workflow
    assert '--reuid="$uid"' in workflow
    assert 'HOME="$operator_root/home"' in workflow
    assert "/usr/bin/strace -f -qq" in workflow
    assert "scripts/verify_alpha_a1_p2_named_host.py" in workflow
    assert "module._validate_strace(trace_path, allowed_execs)" in workflow
    assert "successful operator path signalled a process" in workflow
    assert 'receipt["budgets"]["installations"] == 1' in workflow
    assert 'receipt["budgets"]["uninstallations"] == 1' in workflow
    assert 'receipt["budgets"]["mcp_server_launches"] == 2' in workflow
    assert 'receipt["budgets"]["logical_mcp_requests"] == 4' in workflow
    assert 'assert all(value == 0 for value in receipt["traffic"].values())' in workflow


def test_workflow_cleanup_precedes_summary_and_forbids_publication() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    cleanup_at = workflow.index("- name: Remove every ephemeral A3-P0.1 output")
    confirm_at = workflow.index("- name: Confirm complete A3-P0.1 cleanup")
    summary_at = workflow.index("- name: Summarize only after reconciliation and cleanup")

    assert cleanup_at < confirm_at < summary_at
    cleanup = workflow[cleanup_at:confirm_at]
    confirm = workflow[confirm_at:summary_at]
    assert cleanup.index('sudo rm --recursive --force -- "$A3_ROOT"') < cleanup.index(
        "A3_CLEANUP_COMPLETED=1"
    )
    assert "run: |\n          set -euo pipefail" in confirm
    assert 'expected_root="${RUNNER_TEMP%/}/evidencemesh-alpha-a3-p0-1-' in cleanup
    assert 'test "$A3_ROOT" = "$expected_root"' in cleanup
    assert 'test "$A3_ROOT" != /' in cleanup
    assert 'test "${A3_CLEANUP_COMPLETED:-}" = 1' in confirm
    assert "pgrep_status=$?" in confirm
    assert 'test "$pgrep_status" = 1' in confirm
    assert "workspace_status=$(git status --porcelain --untracked-files=all)" in confirm
    assert 'sudo rm --recursive --force -- "$A3_ROOT"' in workflow
    assert 'test ! -e "$A3_ROOT"' in workflow
    assert 'test -z "$workspace_status"' in confirm
    assert 'test "${A3_FULL_SUITE_PASSED:-}" = 1' in workflow
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
