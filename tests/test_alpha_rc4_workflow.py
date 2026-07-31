from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/alpha-rc4-control-plane-offline-protocol-v1.md"
POLICY = ROOT / "alpha/closed_alpha_rc4_control_plane_policy_v1.json"
WORKFLOW = ROOT / ".github/workflows/alpha-rc4-control-plane-offline.yml"

C2_SHA = "033d893d7c07e8c31a19e543187d15e28aa58d90"
C2_TREE = "d0d0fb5b6d5954920728a9928891ab73b468d063"
C1_SHA = "c1e0be437442b0d97da26f2c9085067a8c09955e"
PROTOCOL_SHA256 = "b4d6946565538ce865893592f5c0e0e09436780ae102b52629291de3175b455d"
POLICY_SHA256 = "d8108efa4aaa21b3bef671e7b754c47fde26e31bd7700b3a0e8414993612a83e"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict[str, Any]:
    value = json.loads(POLICY.read_bytes())
    assert isinstance(value, dict)
    return value


def test_protocol_and_policy_are_hash_locked_to_the_rc3_seal() -> None:
    policy = _policy()

    assert _sha256(PROTOCOL) == PROTOCOL_SHA256
    assert _sha256(POLICY) == POLICY_SHA256
    assert policy["basis"] == {
        "accepted_rc3_candidate_sha": C1_SHA,
        "accepted_rc3_candidate_tree": "44bb1df79b6026c1fc1c2a40218c7347117697a0",
        "rc3_seal_sha": C2_SHA,
        "rc3_seal_tree": C2_TREE,
    }
    assert policy["protocol"] == {
        "path": "docs/alpha-rc4-control-plane-offline-protocol-v1.md",
        "sha256": PROTOCOL_SHA256,
    }


def test_policy_keeps_every_live_and_distribution_authority_blocked() -> None:
    policy = _policy()

    assert policy["schema_version"] == ("evidencemesh.closed-alpha-rc4-control-plane-policy.v1")
    assert policy["status"] == "offline_implementation_validation_only"
    assert policy["authority"] == {
        "closed_alpha_adoption_authorized": False,
        "live_execution_authorized": False,
        "merge_authorized": False,
        "offline_implementation_and_validation_authorized": True,
        "public_binary_distribution_authorized": False,
        "public_release_authorized": False,
        "quality_claim_authorized": False,
        "tester_contact_authorized": False,
    }
    assert policy["distribution"] == {
        "actions_artifact_upload_allowed": False,
        "attestation_creation_allowed_in_this_phase": False,
        "build_outputs_ephemeral": True,
        "package_publication_allowed": False,
        "sealing_commit_authorized_in_this_phase": False,
    }
    assert policy["offline_phase_budget"]
    assert all(
        type(value) is int and value == 0 for value in policy["offline_phase_budget"].values()
    )


def test_policy_freezes_single_host_state_admission_recovery_and_privacy() -> None:
    policy = _policy()

    assert policy["control_plane"] == {
        "classes": ["SQLiteAlphaControlPlane", "ClosedAlphaFeedbackStore"],
        "dispatch_checks": ["atomic_reservation", "first_httpx_request_hook"],
        "dispatchable_state": "prepared",
        "epoch_invalidates_prior_permits": True,
        "feedback_context_authoritative_fields": [
            "slot_id",
            "profile",
            "provider_attempts",
            "tavily_attempts",
        ],
        "feedback_context_source": "sqlite_registry_and_attempt_ledger",
        "ledger_scope": "single_host_shared_sqlite",
        "privacy_fault_blocks": [
            "transition_to_prepared",
            "atomic_reservation",
            "first_httpx_request_hook",
        ],
        "privacy_fault_durable": True,
        "remote_or_distributed_coordinator": False,
        "states": ["prepared", "paused", "stopped"],
        "stopped_is_terminal": True,
    }
    assert policy["cohort"] == {
        "community_slots": 6,
        "consent_version": "closed-alpha-a0-consent-v1",
        "contact_data_allowed": False,
        "profile_source": "sqlite_registry",
        "pseudonymous_identifiers_only": True,
        "quality_slots": 2,
        "slots_total": 8,
    }
    assert policy["providers"]["community"] == [
        "arxiv",
        "crossref",
        "github",
        "searxng",
        "wikipedia",
    ]
    assert policy["providers"]["quality"] == [
        "arxiv",
        "crossref",
        "github",
        "searxng",
        "tavily",
        "wikipedia",
    ]
    assert policy["providers"]["ddgs"] == "forbidden"
    assert policy["recovery"]["automatic_resume_allowed"] is False
    assert policy["recovery"]["budget_refund_allowed"] is False
    assert policy["recovery"]["budget_reset_allowed"] is False
    assert policy["recovery"]["outstanding_permits_invalidated"] is True
    assert policy["feedback_validator"] == {
        "arbitrary_or_noop_validator_allowed": False,
        "candidate_sha_binding": "exact_pull_request_head",
        "class": "ClosedAlphaFeedbackContract",
        "final_class_required": True,
        "packaged_in_candidate_wheel_required": True,
    }
    assert policy["privacy"]["withdrawal_blocks_before_purge"] is True
    assert policy["privacy"]["withdrawal_caller_session_list_allowed"] is False
    assert policy["privacy"]["withdrawal_report_discovery"] == "private_store_inventory"
    assert policy["privacy"]["withdrawal_reconciliation_points"] == [
        "startup",
        "access",
        "shutdown",
        "scheduler",
    ]
    assert policy["privacy"]["purge_at_startup"] is True
    assert policy["privacy"]["purge_at_access"] is True
    assert policy["privacy"]["purge_at_shutdown"] is True
    assert policy["privacy"]["scheduler_required"] is True
    assert policy["privacy"]["feedback_utc_high_water_durable"] is True
    assert policy["privacy"]["feedback_utc_high_water_store"] == "shared_sqlite_control_plane"
    assert policy["privacy"]["privacy_fault_store"] == "shared_sqlite_control_plane"
    assert policy["scheduler"] == {
        "component": "FeedbackRetentionScheduler",
        "continuous_local_supervision_required_before_live": True,
        "deployed_daemon_in_offline_phase": False,
        "entry_criterion_before_live": True,
        "local_component": True,
        "remote_service": False,
    }
    assert policy["validation"]["wheel_smoke_candidate_sha_binding_required"] is True
    assert policy["validation"]["wheel_smoke_network_namespace_required"] is True


def test_protocol_states_the_non_live_boundary_and_fail_closed_invariants() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    for marker in (
        "pull-request validation phase, not an exact-HEAD candidate acceptance",
        "The pull request remains draft",
        "SQLiteAlphaControlPlane",
        "ClosedAlphaFeedbackStore",
        "final, package-owned `ClosedAlphaFeedbackContract`",
        "exact candidate commit SHA",
        "authoritative SQLite registry and attempt ledger",
        "`prepared` is the only mechanically dispatchable state",
        "It does not mean that live execution has been authorized",
        "Every state transition increments a monotonic control epoch",
        "first HTTPX request hook immediately before transport",
        "six `community` and two `quality`",
        "DDGS, custom providers",
        "without deleting attempts or refunding any counter",
        "at startup, before every access, at orderly shutdown",
        "no caller session list is accepted or trusted",
        "durable high-water mark in the same SQLite control plane",
        "blocks transition to `prepared`, reservation and the first HTTPX request hook",
        "Continuous local supervision of that component is an entry criterion",
        "neither installs nor claims a deployed daemon",
        "smoke-tested in the same empty network namespace",
        "No GitHub Actions artifact or attestation is created",
        "Search or provider requests | 0",
        "later explicit authorization",
    ):
        assert marker in protocol


def test_pull_request_workflow_is_read_only_secret_free_and_network_isolated() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    lowered = workflow.lower()
    parsed = yaml.safe_load(workflow)

    assert isinstance(parsed, dict)
    triggers = parsed.get("on", parsed.get(True))
    assert isinstance(triggers, dict)
    assert "pull_request" in triggers
    assert "push" not in triggers
    assert triggers["pull_request"]["types"] == [
        "opened",
        "reopened",
        "synchronize",
        "converted_to_draft",
    ]
    assert parsed["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" not in workflow
    assert "github.event.pull_request.draft == true" in workflow
    assert "github.event.pull_request.number == 1" in workflow
    assert "github.event.pull_request.head.sha" in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-depth: 0" in workflow
    assert C2_SHA in workflow
    assert C2_TREE in workflow
    assert C1_SHA in workflow
    assert PROTOCOL_SHA256 in workflow
    assert POLICY_SHA256 in workflow
    assert 'git merge-base --is-ancestor "$C2_SHA" HEAD' in workflow
    assert 'git diff --quiet "$C2_SHA" HEAD -- "${immutable[@]}"' in workflow
    for immutable in (
        "alpha/alpha_rc3_head_acceptance_v1.json",
        "alpha/closed_alpha_a0_feedback.schema.json",
        "alpha/closed_alpha_a0_plan_v1.json",
        "alpha/closed_alpha_rc3_governor_policy_v1.json",
        "docs/alpha-rc3-head-exact-protocol-v1.md",
        "docs/closed-alpha-a0-protocol-v1.md",
        "pyproject.toml",
        "uv.lock",
    ):
        assert immutable in workflow

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
    assert '"${run_isolated[@]}" /usr/bin/test ! -w /var/run/docker.sock' in workflow
    assert "-m ruff format --check ." in workflow
    assert "-m ruff check ." in workflow
    assert "-m mypy src" in workflow
    assert "-m pytest" in workflow
    assert "--cov=evidencemesh" in workflow
    assert "-m hatchling build" in workflow
    assert "--target wheel" in workflow
    assert "--target sdist" in workflow
    assert "candidate_sha=$(git rev-parse HEAD)" in workflow
    assert 'wheel_path=$(find "$RC4_ROOT/dist"' in workflow
    assert 'smoke_target="$RC4_ROOT/wheel-smoke"' in workflow
    assert '"$uv_path" pip install' in workflow
    assert "--offline" in workflow
    assert "--no-index" in workflow
    assert "--no-deps" in workflow
    assert 'PYTHONPATH="$smoke_target"' in workflow
    assert "from evidencemesh.closed_alpha_feedback import ClosedAlphaFeedbackContract" in workflow
    assert "contract = ClosedAlphaFeedbackContract(candidate_sha)" in workflow
    assert 'getattr(ClosedAlphaFeedbackContract, "__final__", False) is True' in workflow
    assert "is_relative_to(Path(smoke_target).resolve())" in workflow
    assert "if: always()" in workflow
    assert 'test ! -e "$RC4_ROOT"' in workflow

    for forbidden in (
        "secrets.",
        "github.token",
        "upload-artifact",
        "actions/attest",
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
