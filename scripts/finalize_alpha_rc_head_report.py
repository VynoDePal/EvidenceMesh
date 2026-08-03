"""Create the Alpha-RC HEAD result after GitHub signs and verifies the candidate."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.build_alpha_rc_head_bundle import RC_NAME, sha256_file
except ModuleNotFoundError:
    from build_alpha_rc_head_bundle import RC_NAME, sha256_file


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain a JSON object")
    return value


def finalize_report(
    *,
    bundle_dir: Path,
    output: Path,
    repository: str,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    artifact_name: str,
    provenance_attestation_id: str,
    provenance_attestation_url: str,
    sbom_attestation_id: str,
    sbom_attestation_url: str,
) -> dict[str, Any]:
    manifest_path = bundle_dir / "alpha-rc-manifest.json"
    checksums_path = bundle_dir / "SHA256SUMS"
    manifest = _read_object(manifest_path)
    if manifest.get("candidate") != RC_NAME:
        raise ValueError("The bundle manifest does not identify the locked alpha RC")
    if manifest.get("phase") != "alpha-rc-head":
        raise ValueError("The bundle manifest does not identify the Alpha-RC HEAD phase")
    if manifest.get("protocol", {}).get("path") != ("docs/alpha-rc-head-protocol-v1.md"):
        raise ValueError("The bundle manifest does not identify the locked protocol")
    if manifest.get("environment", {}).get("commit_sha") != commit_sha:
        raise ValueError("The bundle and GitHub workflow commit SHAs differ")
    gates = manifest.get("gates")
    if not isinstance(gates, dict) or not gates or not all(gates.values()):
        raise ValueError("At least one local alpha RC build gate failed")
    traffic = manifest.get("traffic")
    if (
        not isinstance(traffic, dict)
        or not traffic
        or any(not isinstance(value, int) or value != 0 for value in traffic.values())
    ):
        raise ValueError("Alpha-RC HEAD research traffic must remain exactly zero")
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("commit_sha must be a full lowercase Git commit SHA")
    if not run_id.isdigit() or not run_attempt.isdigit():
        raise ValueError("GitHub run identifiers must be numeric")
    if not provenance_attestation_id or not sbom_attestation_id:
        raise ValueError("Both GitHub attestation IDs are required")
    for url in (provenance_attestation_url, sbom_attestation_url):
        if not url.startswith("https://github.com/"):
            raise ValueError("GitHub attestation URLs must use https://github.com/")

    artifact_records = manifest["artifacts"]
    report: dict[str, Any] = {
        "schema_version": 1,
        "evaluation": "evidencemesh-alpha-rc-head-v1",
        "phase": "alpha-rc-head",
        "scored": False,
        "environment": {
            "repository": repository,
            "commit_sha": commit_sha,
            "github_run_id": int(run_id),
            "github_run_attempt": int(run_attempt),
        },
        "protocol": manifest["protocol"],
        "candidate": {
            "name": RC_NAME,
            "github_actions_artifact": artifact_name,
            "manifest_sha256": sha256_file(manifest_path),
            "checksums_sha256": sha256_file(checksums_path),
            "wheel": artifact_records["wheel"],
            "sdist": artifact_records["sdist"],
            "sbom": artifact_records["sbom"],
        },
        "validation": {
            "local_build_gates": gates,
            "installed_wheel_mcp": artifact_records["mcp_stdio_smoke"],
            "installed_wheel_cli": artifact_records["offline_cli_smoke"],
            "twine_check_passed": True,
            "sha256sums_verified": True,
        },
        "supply_chain": {
            "builder": "GitHub-hosted ubuntu-latest",
            "signing": "GitHub artifact attestations with keyless Sigstore identity",
            "provenance": {
                "attestation_id": provenance_attestation_id,
                "attestation_url": provenance_attestation_url,
                "predicate_type": "https://slsa.dev/provenance/v1",
                "verified_by_github_cli": True,
            },
            "sbom": {
                "attestation_id": sbom_attestation_id,
                "attestation_url": sbom_attestation_url,
                "predicate_type": "https://cyclonedx.org/bom",
                "verified_by_github_cli": True,
            },
        },
        "traffic": traffic,
        "decision": {
            "alpha_technical_candidate_passed": True,
            "quality_benchmark_passed": False,
            "quality_claim_allowed": False,
            "public_distribution_allowed": False,
            "github_release_allowed": False,
            "pypi_publish_allowed": False,
            "merge_allowed": False,
            "phase12_allowed": False,
            "release_ready": False,
            "release_decision": "no-go",
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
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--artifact-name", required=True)
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
        commit_sha=args.commit_sha,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        artifact_name=args.artifact_name,
        provenance_attestation_id=args.provenance_attestation_id,
        provenance_attestation_url=args.provenance_attestation_url,
        sbom_attestation_id=args.sbom_attestation_id,
        sbom_attestation_url=args.sbom_attestation_url,
    )


if __name__ == "__main__":
    main()
