from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

from scripts import verify_alpha_public_projection as projection_verifier

ROOT = Path(__file__).parents[1]
PROJECTION = ROOT / "alpha/local_technical_alpha_v0_1_0_public_projection_v1.json"
WORKFLOW = ROOT / ".github/workflows/alpha-v0-1-0-public-projection-offline.yml"
PUBLIC_SOURCE_COMMIT = "8026ace0f8c48abf9f9a5664d31d1e9cc66bdf2e"
PUBLIC_SOURCE_TREE = "7a774664442caa9201b419fb219d47c6113a52a3"


def _record() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(PROJECTION.read_bytes()))


def test_public_projection_is_offline_verifiable_from_public_history() -> None:
    result = projection_verifier.verify(ROOT)

    assert result["passed"] is True
    assert result["provider_requests"] == 0
    assert result["public_source_commit"] == PUBLIC_SOURCE_COMMIT
    assert result["public_source_tree"] == PUBLIC_SOURCE_TREE


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
    assert 'test "$PR_DRAFT" = "true"' in workflow
    assert "fetch-depth: 0" in workflow
    assert "fetch-tags: false" in workflow
    assert "persist-credentials: false" in workflow
    assert "verify_alpha_public_projection.py" in workflow
    for forbidden in ("curl ", "wget ", "uv sync", "pip install", "upload-artifact", "attest"):
        assert forbidden not in workflow.lower()
