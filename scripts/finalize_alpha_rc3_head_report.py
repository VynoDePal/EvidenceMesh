"""Create the metadata-only Alpha-RC3 HEAD report after primary attestations."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.build_alpha_rc3_head_bundle import (
        EXPECTED_BUNDLE_FILES,
        PHASE,
        RC_NAME,
        sha256_file,
        validate_bundle_inventory,
    )
except ModuleNotFoundError:
    from build_alpha_rc3_head_bundle import (
        EXPECTED_BUNDLE_FILES,
        PHASE,
        RC_NAME,
        sha256_file,
        validate_bundle_inventory,
    )


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain an object")
    return value


def _read_checksums(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) \*(.+)", line)
        if match is None or match.group(2) in records:
            raise ValueError("SHA256SUMS is malformed or contains a duplicate path")
        records[match.group(2)] = match.group(1)
    if not records:
        raise ValueError("SHA256SUMS is empty")
    return records


def _attestation(identifier: str, url: str, predicate_type: str) -> dict[str, Any]:
    if not identifier.isdigit() or int(identifier) <= 0:
        raise ValueError("Attestation identifiers must be positive integers")
    if not re.fullmatch(r"https://github\.com/[^\s]+", url):
        raise ValueError("Attestation URLs must be GitHub HTTPS URLs")
    return {
        "attestation_id": int(identifier),
        "attestation_url": url,
        "predicate_type": predicate_type,
        "verified_by_github_cli": True,
    }


def finalize_report(
    *,
    bundle_dir: Path,
    output: Path,
    repository: str,
    candidate_sha: str,
    candidate_tree: str,
    run_id: str,
    run_attempt: str,
    provenance_attestation_id: str,
    provenance_attestation_url: str,
    sbom_attestation_id: str,
    sbom_attestation_url: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
        raise ValueError("candidate_sha must be a full lowercase Git SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", candidate_tree):
        raise ValueError("candidate_tree must be a full lowercase Git tree SHA")
    if not run_id.isdigit() or not run_attempt.isdigit():
        raise ValueError("GitHub run identifiers must be numeric")

    manifest_path = bundle_dir / "alpha-rc3-head-manifest.json"
    checksums_path = bundle_dir / "SHA256SUMS"
    validate_bundle_inventory(bundle_dir, allow_generated_missing=False)
    manifest = _read_object(manifest_path)
    checksums = _read_checksums(checksums_path)
    expected_subjects = EXPECTED_BUNDLE_FILES - {"SHA256SUMS"}
    if set(checksums) != expected_subjects:
        raise ValueError("SHA256SUMS subject inventory differs from the locked bundle")
    for relative, expected_digest in checksums.items():
        subject = bundle_dir / relative
        if not subject.is_file() or subject.is_symlink():
            raise ValueError("Checksummed subject is missing or unsafe")
        if sha256_file(subject) != expected_digest:
            raise ValueError("Checksummed subject changed after bundle validation")
    identity = manifest.get("identity")
    if manifest.get("candidate") != RC_NAME or manifest.get("phase") != PHASE:
        raise ValueError("Manifest does not identify the RC3 HEAD exact candidate")
    if not isinstance(identity, dict) or identity.get("candidate_sha") != candidate_sha:
        raise ValueError("Manifest and workflow candidate SHAs differ")
    if identity.get("candidate_tree") != candidate_tree:
        raise ValueError("Manifest and workflow candidate trees differ")
    runtime_base_sha = identity.get("runtime_base_sha")
    runtime_base_tree = identity.get("runtime_base_tree")
    if not isinstance(runtime_base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", runtime_base_sha):
        raise ValueError("Manifest runtime base SHA is invalid")
    if not isinstance(runtime_base_tree, str) or not re.fullmatch(
        r"[0-9a-f]{40}", runtime_base_tree
    ):
        raise ValueError("Manifest runtime base tree is invalid")
    gates = manifest.get("gates")
    if (
        not isinstance(gates, dict)
        or not gates
        or any(type(value) is not bool or value is not True for value in gates.values())
    ):
        raise ValueError("At least one RC3 HEAD build gate failed")
    traffic = manifest.get("traffic")
    if (
        not isinstance(traffic, dict)
        or not traffic
        or any(type(value) is not int or value != 0 for value in traffic.values())
    ):
        raise ValueError("RC3 HEAD research traffic must remain integer zero")
    distribution = manifest.get("distribution")
    if distribution != {
        "binary_artifact_uploaded": False,
        "binaries_ephemeral_on_runner": True,
        "public_metadata_only": True,
    }:
        raise ValueError("RC3 HEAD distribution boundary drifted")

    report: dict[str, Any] = {
        "schema_version": 1,
        "evaluation": "evidencemesh-alpha-rc3-head-exact-v1",
        "phase": PHASE,
        "scored": False,
        "environment": {
            "repository": repository,
            "candidate_sha": candidate_sha,
            "candidate_tree": candidate_tree,
            "github_run_id": int(run_id),
            "github_run_attempt": int(run_attempt),
        },
        "candidate": {
            "name": RC_NAME,
            "sha": candidate_sha,
            "tree": candidate_tree,
            "parent_sha": runtime_base_sha,
            "parent_tree": runtime_base_tree,
            "manifest_sha256": sha256_file(manifest_path),
            "checksums_sha256": sha256_file(checksums_path),
            "subjects": checksums,
        },
        "protocol": manifest["protocol"],
        "workflow": manifest["workflow"],
        "validation": {
            "gates": gates,
            "artifacts": manifest["artifacts"],
            "sha256sums_verified": True,
            "installed_wheel_and_sdist": True,
            "byte_reproducible_distributions": True,
        },
        "supply_chain": {
            "provenance": _attestation(
                provenance_attestation_id,
                provenance_attestation_url,
                "https://slsa.dev/provenance/v1",
            ),
            "sbom": _attestation(
                sbom_attestation_id,
                sbom_attestation_url,
                "https://cyclonedx.org/bom",
            ),
        },
        "distribution": {
            **distribution,
            "github_actions_artifact_created": False,
            "private_delivery_channel_authorized": False,
        },
        "traffic": traffic,
        "decision": {
            "alpha_technical_candidate_passed": True,
            "single_host_governor_installed_and_verified": True,
            "distributed_global_enforcement_ready": False,
            "closed_alpha_adoption_authorized": False,
            "tester_contact_authorized": False,
            "live_execution_authorized": False,
            "public_binary_distribution_allowed": False,
            "merge_allowed": False,
            "release_allowed": False,
            "quality_claim_allowed": False,
            "sealing_commit_required": True,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--provenance-attestation-id", required=True)
    parser.add_argument("--provenance-attestation-url", required=True)
    parser.add_argument("--sbom-attestation-id", required=True)
    parser.add_argument("--sbom-attestation-url", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    finalize_report(
        bundle_dir=args.bundle_dir.resolve(),
        output=args.output.resolve(),
        repository=args.repository,
        candidate_sha=args.candidate_sha,
        candidate_tree=args.candidate_tree,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        provenance_attestation_id=args.provenance_attestation_id,
        provenance_attestation_url=args.provenance_attestation_url,
        sbom_attestation_id=args.sbom_attestation_id,
        sbom_attestation_url=args.sbom_attestation_url,
    )


if __name__ == "__main__":
    main()
