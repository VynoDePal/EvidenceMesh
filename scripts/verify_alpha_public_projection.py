"""Verify the local-alpha public projection without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

PROJECTION_PATH = Path("alpha/local_technical_alpha_v0_1_0_public_projection_v1.json")
SUCCESSOR_PATH = Path("alpha/local_technical_alpha_v0_1_0_runtime_successor_a2_v1.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed executable and arguments.
        ["/usr/bin/git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_succeeds(root: Path, *args: str) -> bool:
    completed = subprocess.run(  # noqa: S603 - fixed executable and arguments.
        ["/usr/bin/git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise ValueError(f"Public projection verification failed: {label}")


def _require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(
            f"Public projection verification failed: {label}: expected {expected!r}, got {actual!r}"
        )


def _ancestor_with_tree(root: Path, expected_tree: str) -> str:
    for line in _git(root, "log", "--format=%H %T", "HEAD").splitlines():
        commit_sha, tree_sha = line.split()
        if tree_sha == expected_tree:
            return commit_sha
    raise ValueError(
        "Public projection verification failed: "
        f"accepted runtime-successor tree {expected_tree!r} is not in HEAD history"
    )


def verify(root: Path) -> dict[str, Any]:
    """Validate the projection record and return a compact offline result."""
    projection_path = root / PROJECTION_PATH
    record = cast(dict[str, Any], json.loads(projection_path.read_bytes()))
    successor = cast(dict[str, Any], json.loads((root / SUCCESSOR_PATH).read_bytes()))

    _require_equal(
        record["schema_version"],
        "evidencemesh.local-technical-alpha-v0.1.0-public-projection.v1",
        "schema version",
    )
    _require_equal(
        record["projection"],
        {
            "head_branch": "agent/evidencemesh-v0.1",
            "pull_request_number": 1,
            "repository": "VynoDePal/EvidenceMesh",
            "required_pr_state": "draft",
            "scope": "public_projection_of_local_acceptance_record_only",
        },
        "projection identity",
    )

    acceptance = record["local_acceptance"]
    acceptance_path = root / acceptance["record_path"]
    _require_equal(_sha256(acceptance_path), acceptance["record_sha256"], "acceptance digest")
    acceptance_record = cast(dict[str, Any], json.loads(acceptance_path.read_bytes()))
    _require_equal(
        acceptance_record["candidate"]["commit_sha"],
        acceptance["candidate_commit_sha"],
        "candidate commit",
    )
    _require_equal(
        acceptance_record["candidate"]["tag_name"],
        acceptance["candidate_tag_name"],
        "candidate tag name",
    )
    _require_equal(
        acceptance_record["candidate"]["tag_object_sha"],
        acceptance["candidate_tag_object_sha"],
        "candidate tag object",
    )
    _require_equal(
        acceptance_record["candidate"]["tree_sha"],
        record["source_equivalence"]["local_candidate_tree_sha"],
        "candidate tree",
    )
    _require_equal(
        acceptance_record["verification"]["seal_head_tests_passed"],
        acceptance["seal_head_tests_passed"],
        "historical seal test count",
    )

    source = record["source_equivalence"]
    public_commit = source["public_commit_sha"]
    public_tree = source["public_tree_sha"]
    _require_equal(source["basis"], "identical_git_tree_sha1", "equivalence basis")
    _require_equal(public_tree, source["local_candidate_tree_sha"], "tree equivalence")
    _require_equal(
        _git(root, "rev-parse", f"{public_commit}^{{commit}}"),
        public_commit,
        "public commit resolution",
    )
    _require_equal(
        _git(root, "rev-parse", f"{public_commit}^{{tree}}"),
        public_tree,
        "public tree resolution",
    )
    _require(
        _git_succeeds(
            root,
            "merge-base",
            "--is-ancestor",
            public_commit,
            successor["historical_projection"]["historical_runtime_boundary_commit_sha"],
        ),
        "public source commit is not an ancestor of the historical runtime boundary",
    )

    _require_equal(
        successor["schema_version"],
        "evidencemesh.local-technical-alpha-v0.1.0-runtime-successor-a2.v1",
        "runtime-successor schema version",
    )
    historical = successor["historical_projection"]
    _require_equal(historical["projection_record_path"], PROJECTION_PATH.as_posix(), "record path")
    _require_equal(
        historical["projection_record_sha256"],
        _sha256(projection_path),
        "historical projection digest",
    )
    _require_equal(historical["public_commit_sha"], public_commit, "successor public commit")
    _require_equal(historical["public_tree_sha"], public_tree, "successor public tree")
    _require_equal(
        historical["runtime_immutable_paths"],
        source["runtime_immutable_paths"],
        "successor runtime paths",
    )
    boundary_commit = historical["historical_runtime_boundary_commit_sha"]
    _require_equal(
        _git(root, "rev-parse", f"{boundary_commit}^{{tree}}"),
        historical["historical_runtime_boundary_tree_sha"],
        "historical runtime-boundary tree",
    )
    _require(
        _git_succeeds(
            root,
            "diff",
            "--quiet",
            public_commit,
            boundary_commit,
            "--",
            *source["runtime_immutable_paths"],
        ),
        "runtime paths drifted before the historical runtime boundary",
    )

    runtime_successor = successor["runtime_successor"]
    successor_tree = runtime_successor["accepted_head_tree_sha"]
    successor_commit = _ancestor_with_tree(root, successor_tree)
    _require(
        _git_succeeds(root, "merge-base", "--is-ancestor", boundary_commit, successor_commit),
        "accepted A2 successor does not descend from the historical runtime boundary",
    )
    runtime_blobs = cast(dict[str, str], runtime_successor["runtime_blob_sha1"])
    changed_runtime_paths = _git(
        root,
        "diff",
        "--name-only",
        boundary_commit,
        successor_commit,
        "--",
        *source["runtime_immutable_paths"],
    ).splitlines()
    _require_equal(
        changed_runtime_paths,
        sorted(runtime_blobs),
        "exact A2 runtime-successor paths",
    )
    for relative_path, expected_blob in runtime_blobs.items():
        _require_equal(
            _git(root, "rev-parse", f"{successor_commit}:{relative_path}"),
            expected_blob,
            f"A2 runtime blob {relative_path}",
        )
    canonical_successor = runtime_successor["accepted_head_commit_sha"]
    if _git_succeeds(root, "cat-file", "-e", f"{canonical_successor}^{{commit}}"):
        _require_equal(
            _git(root, "rev-parse", f"{canonical_successor}^{{tree}}"),
            successor_tree,
            "canonical A2 successor tree",
        )
    _require(
        _git_succeeds(
            root,
            "diff",
            "--quiet",
            successor_commit,
            "HEAD",
            "--",
            *source["runtime_immutable_paths"],
        ),
        "runtime paths drifted after the accepted A2 successor",
    )

    retirement = record["workflow_retirement"]
    _require(
        not (root / retirement["active_path_absent"]).exists(),
        "retired one-update workflow remains active",
    )
    _require_equal(
        _sha256(root / retirement["archive_path"]),
        retirement["archive_sha256"],
        "workflow archive digest",
    )

    _require_equal(
        record["publication_control"],
        {
            "automatic_retries_max": 0,
            "branch_ref_updates_max": 1,
            "external_response_reads_max": 0,
            "model_requests_max": 0,
            "provider_requests_max": 0,
            "published_distributions_max": 0,
        },
        "publication control",
    )
    _require(
        not any(record["publication_boundaries"].values()),
        "a downstream publication boundary is open",
    )

    tag_ref = f"refs/tags/{acceptance['candidate_tag_name']}"
    local_tag_resolved = _git_succeeds(root, "show-ref", "--verify", "--quiet", tag_ref)
    if local_tag_resolved:
        _require_equal(
            _git(root, "rev-parse", tag_ref),
            acceptance["candidate_tag_object_sha"],
            "local tag object",
        )
        _require_equal(
            _git(root, "rev-parse", f"{tag_ref}^{{}}"),
            acceptance["candidate_commit_sha"],
            "local tag commit",
        )
        _require_equal(
            _git(root, "rev-parse", f"{tag_ref}^{{}}^{{tree}}"),
            public_tree,
            "local tag tree",
        )
    else:
        _require(
            acceptance["local_identity_resolution_required_in_ci"] is False,
            "unpublished local identity is incorrectly required in CI",
        )

    return {
        "local_identity_resolved": local_tag_resolved,
        "passed": True,
        "provider_requests": 0,
        "public_source_commit": public_commit,
        "public_source_tree": public_tree,
        "historical_runtime_boundary_commit": boundary_commit,
        "accepted_successor_commit": successor_commit,
        "accepted_successor_tree": successor_tree,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = verify(args.repository_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
