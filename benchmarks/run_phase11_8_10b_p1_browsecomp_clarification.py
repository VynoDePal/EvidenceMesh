#!/usr/bin/env python3
"""Run the deterministic Phase 11.8.10B-P1 BrowseComp clarification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = (
    REPOSITORY_ROOT / "benchmarks/data/phase11_8_10b_p1_browsecomp_clarification_v1.json"
)
DEFAULT_SOURCE_LOCK_PATH = REPOSITORY_ROOT / "benchmarks/data/phase11_8_10b_p1_source_locks_v1.json"
SOURCE_LOCK_SCHEMA = "evidencemesh.phase11_8_10b_p1.source-locks.v1"
MAX_SOURCE_LOCK_BYTES = 128 * 1024
PHASE12_MARKERS = ("phase12", "phase_12", "phase-12")
EXPECTED_PREDECESSOR_FILES = {
    "policy_manifest": (
        "benchmarks/data/phase11_8_10b_p0_policy_comparability_lock_v1.json",
        "09e9dfb6475ccf40ffa4d844684ac7036c0255f35e2ad7c6fdeb5e0fe1027082",
    ),
    "protocol": (
        "docs/benchmark-protocol-v27.md",
        "8346b69b1b7261eaf94028d5f2ac2e40bc028b49db0ea68f4f779083680ab0c6",
    ),
    "result": (
        "benchmarks/results/phase11_8_10b_p0_policy_comparability_lock_2026-08-01.json",
        "7e4062e9270eb8dc681783b0aac2ff031ea53310bbd9982c61fea0e458fc3798",
    ),
    "source_lock": (
        "benchmarks/data/phase11_8_10b_p0_source_locks_v1.json",
        "045b28d1da12ee11f2ca9083d6ea8648de8827f9e80c396f12d8bb6e8ccf93ff",
    ),
}
EXPECTED_AUTHORITY_PATHS = (
    ".github/workflows/phase11-8-10b-p1-browsecomp-clarification.yml",
    "benchmarks/__init__.py",
    "benchmarks/data/phase11_8_10b_p0_policy_comparability_lock_v1.json",
    "benchmarks/data/phase11_8_10b_p0_source_locks_v1.json",
    "benchmarks/data/phase11_8_10b_p1_browsecomp_clarification_v1.json",
    "benchmarks/phase11_8_10b_p0_policy_lock.py",
    "benchmarks/phase11_8_10b_p1_browsecomp_clarification.py",
    "benchmarks/results/phase11_8_10b_p0_policy_comparability_lock_2026-08-01.json",
    "benchmarks/run_phase11_8_10b_p0_policy_lock.py",
    "benchmarks/run_phase11_8_10b_p1_browsecomp_clarification.py",
    "docs/benchmark-protocol-v27.md",
    "docs/benchmark-protocol-v28.md",
    "tests/test_phase11_8_10b_p1_browsecomp_clarification.py",
    "tests/test_phase11_8_10b_p1_runner.py",
)


class ClarificationLockError(ValueError):
    """Raised before or after locked modules load when P1 fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ClarificationLockError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_authority_path(relative_path: object) -> tuple[str, Path]:
    _require(isinstance(relative_path, str) and bool(relative_path), "source path must be a string")
    normalized = cast(str, relative_path)
    _require(
        not any(marker in normalized.lower() for marker in PHASE12_MARKERS),
        "Phase 12 source access is forbidden",
    )
    pure = PurePosixPath(normalized)
    _require(
        not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts,
        "unsafe source path",
    )
    _require("\\" not in normalized, "source path must use POSIX separators")
    resolved = REPOSITORY_ROOT.joinpath(*pure.parts)
    _require(
        resolved.is_file() and not resolved.is_symlink(),
        f"authority source is not a regular file: {normalized}",
    )
    return normalized, resolved


def _validate_authority_source_records(records: object) -> list[dict[str, str]]:
    """Reject any non-allowlisted path before a referenced file is opened."""

    _require(isinstance(records, list), "authority sources must be an array")
    raw_records = cast(list[object], records)
    _require(
        len(raw_records) == len(EXPECTED_AUTHORITY_PATHS),
        "authority source path set drifted",
    )
    validated: list[dict[str, str]] = []
    for record in raw_records:
        _require(isinstance(record, dict), "authority source record must be an object")
        normalized_record = cast(dict[str, object], record)
        _require(
            set(normalized_record) == {"relative_path", "sha256"},
            "authority source record schema drifted",
        )
        relative_path = normalized_record.get("relative_path")
        expected_hash = normalized_record.get("sha256")
        _require(
            isinstance(relative_path, str) and bool(relative_path),
            "source path must be a string",
        )
        _require(
            isinstance(expected_hash, str)
            and len(expected_hash) == 64
            and all(character in "0123456789abcdef" for character in expected_hash),
            f"invalid source hash: {relative_path}",
        )
        validated.append({"relative_path": relative_path, "sha256": expected_hash})
    _require(
        tuple(record["relative_path"] for record in validated) == EXPECTED_AUTHORITY_PATHS,
        "authority source path set drifted",
    )
    return validated


def validate_source_locks(path: Path = DEFAULT_SOURCE_LOCK_PATH) -> dict[str, Any]:
    _require(path == DEFAULT_SOURCE_LOCK_PATH, "source-lock path is frozen")
    _require(path.is_file() and not path.is_symlink(), "source-lock manifest must be regular")
    payload = path.read_bytes()
    _require(len(payload) <= MAX_SOURCE_LOCK_BYTES, "source-lock manifest is too large")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClarificationLockError("source-lock manifest is invalid") from exc
    _require(isinstance(decoded, dict), "source-lock manifest must be an object")
    _require(
        set(decoded) == {"authority_sources", "schema_version", "source_set_sha256"},
        "source-lock top-level schema drifted",
    )
    _require(decoded.get("schema_version") == SOURCE_LOCK_SCHEMA, "source-lock schema drifted")
    records = _validate_authority_source_records(decoded.get("authority_sources"))
    normalized: list[dict[str, str]] = []
    for record in records:
        relative_path, absolute_path = _safe_authority_path(record["relative_path"])
        _require(
            _sha256_file(absolute_path) == record["sha256"],
            f"source hash mismatch: {relative_path}",
        )
        normalized.append(record)
    _require(
        decoded.get("source_set_sha256") == canonical_sha256(normalized),
        "source-set digest mismatch",
    )
    return {
        "source_count": len(normalized),
        "source_set_sha256": decoded["source_set_sha256"],
    }


def validate_predecessor_files_and_result(manifest: dict[str, Any]) -> dict[str, Any]:
    # This import is intentionally delayed until run() has verified every P1
    # authority hash, including this runner and the predecessor runner's inputs.
    from benchmarks import run_phase11_8_10b_p0_policy_lock as predecessor_runner

    predecessor = cast(dict[str, Any], manifest["predecessor_lock"])
    verified: list[dict[str, str]] = []
    for record_id, (expected_path, expected_hash) in EXPECTED_PREDECESSOR_FILES.items():
        record = cast(dict[str, Any], predecessor[record_id])
        relative_path, absolute_path = _safe_authority_path(expected_path)
        _require(record["path"] == expected_path, f"predecessor path drifted: {record_id}")
        _require(record["sha256"] == expected_hash, f"predecessor hash drifted: {record_id}")
        _require(
            _sha256_file(absolute_path) == expected_hash,
            f"predecessor file mismatch: {record_id}",
        )
        verified.append(
            {"record_id": record_id, "relative_path": relative_path, "sha256": expected_hash}
        )

    result_path = REPOSITORY_ROOT / EXPECTED_PREDECESSOR_FILES["result"][0]
    try:
        committed_result = json.loads(result_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClarificationLockError("predecessor result is invalid") from exc
    reproduced_result = predecessor_runner.run(
        methodology_commit_sha=predecessor["methodology_commit"]
    )
    _require(committed_result == reproduced_result, "P0 result does not reproduce")
    _require(
        committed_result.get("gate_summary") == {"failed": 0, "passed": 16, "total": 16},
        "P0 gate summary drifted",
    )
    _require(committed_result.get("quality_decision") == "no_go", "P0 no-go drifted")
    _require(
        committed_result.get("selected_policy", {}).get("candidate_suites_admitted_now") == 0,
        "P0 admitted candidate drifted",
    )
    _require(
        committed_result.get("research_budget", {}).get(
            "remaining_unique_public_metadata_documents"
        )
        == 5,
        "P0 remaining budget drifted",
    )
    verified.sort(key=lambda item: item["record_id"])
    return {
        "verified_file_count": len(verified),
        "verified_file_set_sha256": canonical_sha256(verified),
        "result_reproduced": True,
        "gate_summary": {"failed": 0, "passed": 16, "total": 16},
        "quality_decision": "no_go",
        "candidate_suites_admitted": 0,
        "remaining_metadata_documents": 5,
    }


def run(
    *, methodology_commit_sha: str, manifest_path: Path = DEFAULT_MANIFEST_PATH
) -> dict[str, Any]:
    _require(manifest_path == DEFAULT_MANIFEST_PATH, "manifest path is frozen")
    source_lock = validate_source_locks()
    repository_root = str(REPOSITORY_ROOT)
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    # No repository-controlled benchmark module executes before the source-lock
    # allowlist and hashes have passed. Validator failures from the locked
    # clarification module are normalized to this runner's fail-closed exception;
    # an import failure also terminates execution without producing a result.
    from benchmarks import phase11_8_10b_p1_browsecomp_clarification as clarification

    try:
        manifest = clarification.load_manifest(manifest_path)
        predecessor = validate_predecessor_files_and_result(manifest)
        report = clarification.build_clarification_report(
            manifest, methodology_commit_sha=methodology_commit_sha
        )
    except clarification.ClarificationLockError as exc:
        raise ClarificationLockError(str(exc)) from exc
    report["source_lock"] = source_lock
    report["predecessor_verification"] = predecessor
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methodology-commit-sha", required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = run(methodology_commit_sha=args.methodology_commit_sha)
    except ClarificationLockError as exc:
        raise SystemExit(f"phase11.8.10B-P1 clarification failed closed: {exc}") from exc
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
