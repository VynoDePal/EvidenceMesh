from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/alpha-rc4-1a-provider-policy-session-fail-closed-offline-protocol-v1.md"
POLICY = ROOT / "alpha/closed_alpha_rc4_1a_provider_policy_session_fail_closed_policy_v1.json"
WORKFLOW = ROOT / ".github/workflows/alpha-rc4-1a-provider-policy-session-fail-closed-offline.yml"

BASE_SHA = "61a58660cb77ba160e8ecfed53d09fdcd1d60c57"
BASE_TREE = "6a7424d4d8391c64a0ebb0c0445b8d85c8d7a5fe"
PROTOCOL_SHA256 = "6d0e2daf707cf8155ad0a39606bbd80ae984e59094df7f23ef2f7de02afb7d55"
POLICY_SHA256 = "4ee542ba49b2ca1fcac790f0279b6dae83129bf21266efe1addbf19bfb6c5d39"

ADDITIONS = [
    ".github/workflows/alpha-rc4-1a-provider-policy-session-fail-closed-offline.yml",
    "alpha/closed_alpha_rc4_1a_provider_policy_session_fail_closed_policy_v1.json",
    "docs/alpha-rc4-1a-provider-policy-session-fail-closed-offline-protocol-v1.md",
    "tests/test_alpha_rc4_1a_workflow.py",
]
MODIFICATIONS = [
    ".github/workflows/alpha-rc4-control-plane-offline.yml",
    "src/evidencemesh/__init__.py",
    "src/evidencemesh/closed_alpha_feedback.py",
    "src/evidencemesh/engine.py",
    "src/evidencemesh/governor.py",
    "tests/test_alpha_rc4_control_plane.py",
    "tests/test_alpha_rc4_feedback.py",
    "tests/test_alpha_rc4_integration.py",
    "tests/test_alpha_rc4_workflow.py",
]
FOCUSED_TESTS = [
    "tests/test_alpha_rc4_control_plane.py",
    "tests/test_alpha_rc4_feedback.py",
    "tests/test_alpha_rc4_integration.py",
    "tests/test_alpha_rc4_workflow.py",
    "tests/test_alpha_rc4_1a_workflow.py",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict[str, Any]:
    value = json.loads(POLICY.read_bytes())
    assert isinstance(value, dict)
    return value


def test_protocol_and_policy_are_hash_locked_to_the_exact_rc4_base() -> None:
    policy = _policy()

    assert _sha256(PROTOCOL) == PROTOCOL_SHA256
    assert _sha256(POLICY) == POLICY_SHA256
    assert policy["basis"] == {
        "base_sha": BASE_SHA,
        "base_tree": BASE_TREE,
        "rc4_offline_policy_sha256": (
            "d8108efa4aaa21b3bef671e7b754c47fde26e31bd7700b3a0e8414993612a83e"
        ),
        "rc4_offline_protocol_sha256": (
            "b4d6946565538ce865893592f5c0e0e09436780ae102b52629291de3175b455d"
        ),
    }
    assert policy["protocol"] == {
        "path": "docs/alpha-rc4-1a-provider-policy-session-fail-closed-offline-protocol-v1.md",
        "sha256": PROTOCOL_SHA256,
    }


def test_policy_freezes_one_update_zero_traffic_and_no_distribution() -> None:
    policy = _policy()

    assert policy["schema_version"] == (
        "evidencemesh.closed-alpha-rc4.1a-provider-policy-session-fail-closed-policy.v1"
    )
    assert policy["status"] == "offline_correction_validation_only"
    assert policy["authority"] == {
        "attestation_creation_authorized": False,
        "closed_alpha_adoption_authorized": False,
        "live_execution_authorized": False,
        "merge_authorized": False,
        "offline_fail_closed_correction_authorized": True,
        "public_binary_distribution_authorized": False,
        "public_release_authorized": False,
        "quality_claim_authorized": False,
        "tester_contact_authorized": False,
    }
    assert policy["change_control"] == {
        "allowed_additions": ADDITIONS,
        "allowed_modifications": MODIFICATIONS,
        "automatic_retries_max": 0,
        "branch_updates_max": 1,
        "direct_child_of_base_required": True,
        "merge_commit_allowed": False,
    }
    assert policy["distribution"] == {
        "actions_artifact_upload_allowed": False,
        "attestation_creation_allowed": False,
        "build_outputs_ephemeral": True,
        "package_publication_allowed": False,
        "release_creation_allowed": False,
    }
    assert policy["immutable_history"] == {
        "a0_and_rc3_evidence_required": True,
        "pyproject_required": True,
        "rc4_offline_protocol_and_policy_required": True,
        "uv_lock_required": True,
    }
    assert policy["offline_phase_budget"]
    assert all(
        type(value) is int and value == 0 for value in policy["offline_phase_budget"].values()
    )


def test_policy_requires_packaged_identity_durable_fault_and_runtime_binding() -> None:
    policy = _policy()

    assert policy["assurance_boundary"] == {
        "api_and_verified_files_enforced": True,
        "arbitrary_same_interpreter_code_in_tcb": True,
        "in_memory_unforgeability_claimed": False,
        "owner_resistant_os_file_deletion_claimed": False,
        "same_uid_owner_operator_in_tcb": True,
    }
    assert policy["feedback_identity"] == {
        "archive_digest_and_subject_binding_required": True,
        "class": "ClosedAlphaFeedbackIdentity",
        "direct_url_archive_binding_required": True,
        "distribution_imported_module_binding_required": True,
        "expected_record_sha256_required": True,
        "identity_import_from_built_wheel_required": True,
        "load_method": "ClosedAlphaFeedbackIdentity.load",
        "required_attestation_count": 3,
        "selected_archive_formats": ["wheel", "sdist"],
        "selected_archive_must_be_accepted_distribution_subject": True,
        "supported_api_raw_candidate_sha_constructor_allowed": False,
    }
    assert policy["feedback_admission"] == {
        "authoritative_context_required": True,
        "final_context_recheck_before_publish_or_replay_required": True,
    }
    assert policy["privacy_fault"] == {
        "blocks": [
            "transition_to_prepared",
            "atomic_reservation",
            "first_httpx_request_hook",
        ],
        "durable_across_process_restart": True,
        "locked_operations_linearized_by_sqlite_begin": True,
        "marker_mode": "0600",
        "marker_fallback_when_sqlite_begin_unavailable_required": True,
        "marker_fallback_is_safety_path_not_retry_or_repair": True,
        "marker_suffix": ".privacy-fault",
        "recording_failure_fails_closed": True,
        "rollback_must_not_erase_fault": True,
        "same_ledger_identity_required": True,
        "unsafe_link_or_mode_allowed": False,
    }
    assert policy["runtime_binding"] == {
        "legacy_governor_allowed_when_rc4_active": False,
        "legacy_policy_and_session_reassignment_behavior_preserved": True,
        "ledger_participant_session_profile_match_required": True,
        "non_rc4_behavior_preserved": True,
        "policy_exact_type_required": True,
        "policy_limit_exact_int_required": True,
        "policy_public_reassignment_allowed_in_rc4": False,
        "rc4_governor_required_when_rc4_active": True,
        "session_exact_type_required": True,
        "session_public_reassignment_allowed_in_rc4": False,
    }
    assert policy["out_of_scope_stop_conditions"] == {
        "allowlist_expansion_authorized": False,
    }
    assert policy["provider_identity"] == {
        "audited_class_count": 6,
        "canonical_name_exact_str_required": True,
        "class_metadata_identity_allowed": False,
        "exact_class_object_required": True,
        "governed_client_identity_required": True,
        "provider_subclasses_allowed": False,
    }
    assert policy["resolved_stop_findings"] == {
        "policy_reassignment": "corrected_and_adversarially_tested",
        "provider_class_spoofing": "corrected_and_adversarially_tested",
        "session_reassignment": "corrected_and_adversarially_tested",
    }
    assert policy["validation"]["focused_tests"] == FOCUSED_TESTS
    assert policy["validation"]["installed_distribution_module_binding_smoke_required"] is True
    assert policy["validation"]["wheel_identity_load_smoke_required"] is True


def test_protocol_states_entry_stop_identity_fault_and_budget_boundaries() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    for marker in (
        "single direct child",
        "At most one branch update is authorized",
        "no automatic retry",
        "## Entry criteria",
        "exactly the thirteen-file RC4.1A allowlist",
        "replace only the old raw-SHA wheel smoke",
        "ClosedAlphaFeedbackIdentity",
        "expected SHA-256 is supplied independently",
        "supported constructor surface",
        "selected archive must be exactly one accepted distribution subject",
        "actually imported `closed_alpha_feedback.py` module",
        "`ClosedAlphaFeedbackIdentity.load`",
        "hash-complete, test-only `direct_url.json`",
        "API- and verified-file guarantees",
        "`object.__new__`, `object.__setattr__` or monkeypatching",
        "same-UID owner/operator",
        "no claim of in-memory unforgeability",
        "no claim that the owner cannot delete or replace",
        "rolls back",
        "`BEGIN IMMEDIATE` is unavailable",
        "not an automatic research fallback, repair or retry",
        "already-locked decisions",
        "final authoritative feedback-context recheck",
        "transition to `prepared`, reservation and the first HTTPX request hook",
        "after restart and from a second process",
        "legacy governor",
        "## Provider, policy and session correction",
        "concrete class object is exactly one",
        "Module names, qualified names",
        "canonical provider name must be an exact `str`",
        "exact governed HTTPX client",
        "exact frozen `ClosedAlphaPolicy` type",
        "every ceiling must be an exact `int`",
        "six-attempt session ceiling",
        "exact immutable `ClosedAlphaSession`",
        "cannot become a `quality` governor",
        "Legacy non-RC4 policy and session assignment behavior remains unchanged",
        "empty Linux network namespace",
        "wheel-target import smoke for `ClosedAlphaFeedbackIdentity.load`",
        "Provider or search requests | 0",
        "Authorized branch updates | 1",
        "## Stop criteria",
        "Stop rather than retry",
    ):
        assert marker in protocol


def test_workflow_is_exact_read_only_offline_and_ephemeral() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    lowered = workflow.lower()
    parsed = yaml.safe_load(workflow)

    assert isinstance(parsed, dict)
    triggers = parsed.get("on", parsed.get(True))
    assert triggers == {
        "pull_request": {"types": ["opened", "reopened", "synchronize", "converted_to_draft"]}
    }
    assert parsed["permissions"] == {"contents": "read"}
    assert parsed["concurrency"]["cancel-in-progress"] is False
    assert "workflow_dispatch" not in workflow
    assert "github.event.pull_request.number == 1" in workflow
    assert "github.event.pull_request.draft == true" in workflow
    assert "github.event.pull_request.head.repo.full_name == 'VynoDePal/EvidenceMesh'" in workflow
    assert "github.event.pull_request.head.ref == 'agent/evidencemesh-v0.1'" in workflow
    assert "github.event.pull_request.head.sha" in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-depth: 2" in workflow
    assert BASE_SHA in workflow
    assert BASE_TREE in workflow
    assert PROTOCOL_SHA256 in workflow
    assert POLICY_SHA256 in workflow
    assert 'test "$(git rev-parse HEAD^)" = "$BASE_SHA"' in workflow
    assert '"$EXPECTED_HEAD $BASE_SHA"' in workflow
    assert 'git diff --name-status --no-renames "$BASE_SHA" HEAD' in workflow
    for path in ADDITIONS + MODIFICATIONS:
        assert path in workflow

    for immutable in (
        ".github/workflows/alpha-rc3-governor-offline.yml",
        ".github/workflows/closed-alpha-a0-preflight.yml",
        "alpha/alpha_rc3_head_acceptance_v1.json",
        "alpha/closed_alpha_a0_plan_v1.json",
        "alpha/closed_alpha_rc3_governor_policy_v1.json",
        "alpha/closed_alpha_rc4_control_plane_policy_v1.json",
        "docs/alpha-rc3-head-exact-protocol-v1.md",
        "docs/alpha-rc4-control-plane-offline-protocol-v1.md",
        "pyproject.toml",
        "uv.lock",
    ):
        assert immutable in workflow
    immutable_block = workflow.split("immutable=(", 1)[1].split(")", 1)[0]
    assert ".github/workflows/alpha-rc4-control-plane-offline.yml" not in immutable_block
    assert "tests/test_alpha_rc4_workflow.py" not in immutable_block

    install_at = workflow.index("uv sync --extra dev --locked")
    isolate_at = workflow.index("/usr/bin/unshare --net")
    assert install_at < isolate_at
    assert "enable-cache: false" in workflow
    assert "--no-cache" in workflow
    assert "sudo env -i" in workflow
    assert "/usr/bin/unshare --net" in workflow
    assert "/usr/bin/setpriv" in workflow
    assert "--clear-groups" in workflow
    assert "--no-new-privs" in workflow
    assert "UV_OFFLINE=1" in workflow
    assert '"${run_isolated[@]}" /usr/bin/test ! -w /var/run/docker.sock' in workflow
    assert "-m ruff format --check ." in workflow
    assert "-m ruff check ." in workflow
    assert "-m mypy src" in workflow
    for focused_test in FOCUSED_TESTS:
        assert focused_test in workflow
    assert workflow.count('"$python_path" -m pytest') == 2
    assert "--cov=evidencemesh" in workflow
    assert "--cov-report=term-missing" in workflow
    assert "-m hatchling build" in workflow
    assert "--target wheel" in workflow
    assert "--target sdist" in workflow
    assert 'smoke_target="$RC4_1A_ROOT/wheel-smoke"' in workflow
    assert 'PYTHONPATH="$smoke_target"' in workflow
    assert "from evidencemesh import ClosedAlphaFeedbackIdentity as ExportedIdentity" in workflow
    assert "from evidencemesh.closed_alpha_feedback import ClosedAlphaFeedbackIdentity" in workflow
    assert 'distribution = importlib.metadata.distribution("evidencemesh")' in workflow
    assert "distribution.locate_file(module_entries[0])" in workflow
    assert "is_relative_to(smoke_target)" in workflow
    assert "ClosedAlphaFeedbackIdentity.load(" in workflow
    assert 'PurePosixPath(str(entry)).name == "direct_url.json"' in workflow
    assert '"archive_info": {"hashes": {"sha256": wheel_digest}}' in workflow
    assert "archive_path=wheel_path" in workflow
    assert 'f"dist/{wheel_path.name}"' in workflow
    assert 'f"dist/{sdist_path.name}"' in workflow
    assert "if: always()" in workflow
    assert 'test ! -e "$RC4_1A_ROOT"' in workflow

    for forbidden in (
        "secrets.",
        "github.token",
        "actions/upload-artifact",
        "actions/attest",
        "artifact-metadata: write",
        "packages: write",
        "curl ",
        "wget ",
        "gh api",
        "gh release",
        "tavily_api_key",
        "gemini_api_key",
    ):
        assert forbidden not in lowered

    action_lines = [line.strip() for line in workflow.splitlines() if "uses:" in line]
    assert action_lines
    assert all(
        "@" in line and not line.rsplit("@", 1)[1].split()[0].startswith("v")
        for line in action_lines
    )
