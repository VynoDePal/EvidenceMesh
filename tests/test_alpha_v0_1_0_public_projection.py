from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from scripts import verify_alpha_public_projection as projection_verifier

ROOT = Path(__file__).parents[1]
PROJECTION = ROOT / "alpha/local_technical_alpha_v0_1_0_public_projection_v1.json"
SUCCESSOR = ROOT / "alpha/local_technical_alpha_v0_1_0_runtime_successor_a2_v1.json"
WORKFLOW = ROOT / ".github/workflows/alpha-v0-1-0-public-projection-offline.yml"
RECONCILIATION_WORKFLOW = ROOT / (
    ".github/workflows/alpha-a2-p1-1-global-ci-acceptance-reconciliation-offline.yml"
)
A2_P1_WORKFLOW = ROOT / ".github/workflows/alpha-a2-p1-retention-session-liveness-offline.yml"
RECONCILIATION_POLICY = ROOT / (
    "alpha/alpha-a2-p1-1-global-ci-acceptance-reconciliation-policy-v1.json"
)
PUBLIC_SOURCE_COMMIT = "8026ace0f8c48abf9f9a5664d31d1e9cc66bdf2e"
PUBLIC_SOURCE_TREE = "7a774664442caa9201b419fb219d47c6113a52a3"
HISTORICAL_RUNTIME_BOUNDARY = "4044840fb3c79d2b65ff1ce7d3c96be423b331b5"
A2_ACCEPTED_HEAD = "a3140a5d7cfc2fde017cc5376aefc47fa02ee78e"
A2_ACCEPTED_TREE = "c155c355e472e08389c3d18fb88e6388defc376f"


def _record() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(PROJECTION.read_bytes()))


def _successor() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(SUCCESSOR.read_bytes()))


def test_public_projection_is_offline_verifiable_from_public_history() -> None:
    result = projection_verifier.verify(ROOT)

    assert result["passed"] is True
    assert result["provider_requests"] == 0
    assert result["public_source_commit"] == PUBLIC_SOURCE_COMMIT
    assert result["public_source_tree"] == PUBLIC_SOURCE_TREE
    assert result["historical_runtime_boundary_commit"] == HISTORICAL_RUNTIME_BOUNDARY
    assert result["accepted_successor_tree"] == A2_ACCEPTED_TREE


def test_public_projection_does_not_require_the_unpublished_local_tag(monkeypatch: Any) -> None:
    original_git_succeeds = projection_verifier._git_succeeds

    def git_succeeds_without_local_tag(root: Path, *args: str) -> bool:
        if args[:3] == ("show-ref", "--verify", "--quiet"):
            return False
        return original_git_succeeds(root, *args)

    monkeypatch.setattr(projection_verifier, "_git_succeeds", git_succeeds_without_local_tag)
    result = projection_verifier.verify(ROOT)

    assert result["passed"] is True
    assert result["local_identity_resolved"] is False


def test_public_projection_rejects_runtime_drift_after_the_registered_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_git_succeeds = projection_verifier._git_succeeds
    runtime_diff_checks = 0

    def fail_second_runtime_diff(root: Path, *args: str) -> bool:
        nonlocal runtime_diff_checks
        if args[:2] == ("diff", "--quiet"):
            runtime_diff_checks += 1
            if runtime_diff_checks == 2:
                return False
        return original_git_succeeds(root, *args)

    monkeypatch.setattr(projection_verifier, "_git_succeeds", fail_second_runtime_diff)
    with pytest.raises(ValueError, match="drifted after the accepted A2 successor"):
        projection_verifier.verify(ROOT)


def test_a2_runtime_successor_is_append_only_exact_and_non_authorizing() -> None:
    successor = _successor()

    assert successor["schema_version"] == (
        "evidencemesh.local-technical-alpha-v0.1.0-runtime-successor-a2.v1"
    )
    assert successor["historical_projection"] == {
        "historical_runtime_boundary_commit_sha": HISTORICAL_RUNTIME_BOUNDARY,
        "historical_runtime_boundary_tree_sha": "e9d54fef97c583f70dd00d4c095898e545ef6fed",
        "projection_record_path": ("alpha/local_technical_alpha_v0_1_0_public_projection_v1.json"),
        "projection_record_sha256": (
            "19aeace89b0dc978ff1c583132dced4b47d6ec2d2ec8536fe0ecff911f9c38e8"
        ),
        "public_commit_sha": PUBLIC_SOURCE_COMMIT,
        "public_tree_sha": PUBLIC_SOURCE_TREE,
        "runtime_immutable_paths": ["src", "pyproject.toml", "uv.lock"],
    }
    runtime = successor["runtime_successor"]
    assert runtime["accepted_head_commit_sha"] == A2_ACCEPTED_HEAD
    assert runtime["accepted_head_tree_sha"] == A2_ACCEPTED_TREE
    assert runtime["canonical_ci_run_id"] == 30836105388
    assert runtime["canonical_ci_run_attempt"] == 1
    assert runtime["canonical_ci_conclusion"] == "success"
    assert set(runtime["runtime_blob_sha1"]) == {
        "src/evidencemesh/__init__.py",
        "src/evidencemesh/alpha_liveness.py",
        "src/evidencemesh/closed_alpha_feedback.py",
        "src/evidencemesh/engine.py",
        "src/evidencemesh/fetcher.py",
    }
    assert not any(successor["authority"].values())


def test_projection_preserves_local_only_and_downstream_boundaries() -> None:
    record = _record()

    assert record["source_equivalence"] == {
        "basis": "identical_git_tree_sha1",
        "local_candidate_tree_sha": PUBLIC_SOURCE_TREE,
        "public_commit_sha": PUBLIC_SOURCE_COMMIT,
        "public_tree_sha": PUBLIC_SOURCE_TREE,
        "runtime_immutable_paths": ["src", "pyproject.toml", "uv.lock"],
    }
    assert record["local_acceptance"]["local_identity_resolution_required_in_ci"] is False
    assert record["local_acceptance"]["seal_head_tests_passed"] == 985
    assert record["publication_control"] == {
        "automatic_retries_max": 0,
        "branch_ref_updates_max": 1,
        "external_response_reads_max": 0,
        "model_requests_max": 0,
        "provider_requests_max": 0,
        "published_distributions_max": 0,
    }
    assert not any(record["publication_boundaries"].values())


def test_projection_workflow_is_read_only_draft_only_and_network_free() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)
    triggers = parsed.get("on", parsed.get(True))

    assert triggers["pull_request"]["types"] == [
        "opened",
        "reopened",
        "synchronize",
        "converted_to_draft",
    ]
    assert "workflow_dispatch" not in workflow
    assert parsed["permissions"] == {"contents": "read"}
    assert parsed["concurrency"]["cancel-in-progress"] is False
    assert "github.event.pull_request.number == 1" in workflow
    assert "github.event.pull_request.head.ref == 'agent/evidencemesh-v0.1'" in workflow
    assert (
        "github.event.pull_request.head.sha == "
        "'145f5f923825ffeaeb485bd680bc79410ab290d1'" in workflow
    )
    assert 'test "$PR_DRAFT" = "true"' in workflow
    assert "fetch-depth: 0" in workflow
    assert "fetch-tags: false" in workflow
    assert "persist-credentials: false" in workflow
    assert "verify_alpha_public_projection.py" in workflow
    for forbidden in ("curl ", "wget ", "uv sync", "pip install", "upload-artifact", "attest"):
        assert forbidden not in workflow.lower()


def test_a2_p1_1_reconciliation_workflow_is_one_shot_global_and_offline() -> None:
    workflow = RECONCILIATION_WORKFLOW.read_text(encoding="utf-8")
    sealed_a2_workflow = A2_P1_WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)
    triggers = parsed.get("on", parsed.get(True))
    policy = json.loads(RECONCILIATION_POLICY.read_bytes())

    assert triggers["pull_request"]["types"] == ["synchronize"]
    assert "workflow_dispatch" not in workflow
    assert parsed["permissions"] == {"contents": "read"}
    assert parsed["concurrency"]["cancel-in-progress"] is False
    assert f"github.event.before == '{A2_ACCEPTED_HEAD}'" in workflow
    assert f"github.event.pull_request.head.sha == '{A2_ACCEPTED_HEAD}'" in sealed_a2_workflow
    assert "github.run_attempt == 1" in workflow
    assert 'test "$GITHUB_RUN_ATTEMPT" = 1' in workflow
    assert "fetch-depth: 0" in workflow
    assert "persist-credentials: false" in workflow
    assert 'git diff --quiet "$A2_P1_ACCEPTED_HEAD" HEAD -- src pyproject.toml uv.lock' in workflow
    assert "-m ruff format --check ." in workflow
    assert "-m ruff check ." in workflow
    assert "-m mypy src" in workflow
    assert "--cov=evidencemesh" in workflow
    assert "/usr/bin/unshare --net --" in workflow
    assert 'test "${#changed_paths[@]}" = 11' in workflow
    for forbidden in (
        "curl ",
        "wget ",
        "upload-artifact",
        "gh ",
        "docker ",
        "hatchling build",
        "twine",
    ):
        assert forbidden not in workflow.lower()
    assert policy["entry"] == {
        "branch": "agent/evidencemesh-v0.1",
        "exact_parent_commit_sha": A2_ACCEPTED_HEAD,
        "exact_parent_tree_sha": A2_ACCEPTED_TREE,
        "pull_request": 1,
        "repository": "VynoDePal/EvidenceMesh",
    }
    assert policy["reconciliation"]["coverage"] == {
        "baseline_percent": 83.65,
        "minimum_percent": 85.0,
        "target_percent": 86.0,
        "threshold_or_exclusions_may_be_weakened": False,
    }
    assert policy["workflow"]["canonical_full_suite_invocations"] == 1
    assert policy["workflow"]["changed_path_allowlist_count"] == 11
    assert not any(policy["authority"].values())
