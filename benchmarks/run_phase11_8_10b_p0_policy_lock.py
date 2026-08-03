#!/usr/bin/env python3
"""Run the deterministic Phase 11.8.10B-P0 policy/comparability lock."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, cast

from benchmarks.phase11_8_10b_p0_policy_lock import (
    DEFAULT_POLICY_PATH,
    EXPECTED_PREDECESSOR_FILES,
    PolicyLockError,
    build_policy_report,
    canonical_sha256,
    load_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_LOCK_PATH = REPOSITORY_ROOT / "benchmarks/data/phase11_8_10b_p0_source_locks_v1.json"
SOURCE_LOCK_SCHEMA = "evidencemesh.phase11_8_10b_p0.source-locks.v1"
MAX_SOURCE_LOCK_BYTES = 128 * 1024
PHASE12_MARKERS = ("phase12", "phase_12", "phase-12")
EXPECTED_AUTHORITY_PATHS = (
    ".github/workflows/phase11-8-10b-p0-policy-comparability-lock.yml",
    "benchmarks/data/phase11_8_10a_asset_locks_v1.json",
    "benchmarks/data/phase11_8_10a_object_inventory_v1.json",
    "benchmarks/data/phase11_8_10a_source_locks_v1.json",
    "benchmarks/data/phase11_8_10b_p0_policy_comparability_lock_v1.json",
    "benchmarks/phase11_8_10b_p0_policy_lock.py",
    "benchmarks/results/phase11_8_10a_asset_reconnaissance_2026-07-31.json",
    "benchmarks/run_phase11_8_10b_p0_policy_lock.py",
    "docs/benchmark-protocol-v26.md",
    "docs/benchmark-protocol-v27.md",
    "tests/test_phase11_8_10b_p0_policy_lock.py",
    "tests/test_phase11_8_10b_p0_runner.py",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyLockError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_authority_path(relative_path: object) -> tuple[str, Path]:
    _require(isinstance(relative_path, str) and bool(relative_path), "source path must be a string")
    normalized = cast(str, relative_path)
    lowered = normalized.lower()
    _require(
        not any(marker in lowered for marker in PHASE12_MARKERS),
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
    """Reject any non-allowlisted path before a referenced file can be opened."""

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
        raise PolicyLockError("source-lock manifest is invalid") from exc
    _require(isinstance(decoded, dict), "source-lock manifest must be an object")
    _require(
        set(decoded) == {"authority_sources", "schema_version", "source_set_sha256"},
        "source-lock top-level schema drifted",
    )
    _require(decoded.get("schema_version") == SOURCE_LOCK_SCHEMA, "source-lock schema drifted")
    records = _validate_authority_source_records(decoded.get("authority_sources"))
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        relative_path, absolute_path = _safe_authority_path(record.get("relative_path"))
        expected_hash = record.get("sha256")
        _require(relative_path not in seen, f"duplicate source path: {relative_path}")
        seen.add(relative_path)
        _require(
            _sha256_file(absolute_path) == expected_hash, f"source hash mismatch: {relative_path}"
        )
        normalized.append({"relative_path": relative_path, "sha256": expected_hash})
    normalized.sort(key=lambda item: item["relative_path"])
    _require(records == normalized, "authority source records must be canonically ordered")
    _require(
        decoded.get("source_set_sha256") == canonical_sha256(normalized),
        "source-set digest mismatch",
    )
    return {
        "source_count": len(normalized),
        "source_set_sha256": decoded["source_set_sha256"],
    }


def validate_predecessor_files(policy: dict[str, Any]) -> dict[str, Any]:
    predecessor = cast(dict[str, Any], policy["predecessor_lock"])
    verified: list[dict[str, str]] = []
    for record_id, (expected_path, expected_hash) in EXPECTED_PREDECESSOR_FILES.items():
        record = cast(dict[str, Any], predecessor[record_id])
        _require(record["path"] == expected_path, f"predecessor path drifted: {record_id}")
        relative_path, absolute_path = _safe_authority_path(expected_path)
        _require(record["sha256"] == expected_hash, f"predecessor hash drifted: {record_id}")
        _require(
            _sha256_file(absolute_path) == expected_hash, f"predecessor file mismatch: {record_id}"
        )
        verified.append(
            {"record_id": record_id, "relative_path": relative_path, "sha256": expected_hash}
        )

    result_path = REPOSITORY_ROOT / EXPECTED_PREDECESSOR_FILES["result"][0]
    try:
        predecessor_result = json.loads(result_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyLockError("predecessor result is invalid") from exc
    _require(predecessor_result.get("quality_decision") == "no_go", "predecessor no-go changed")
    _require(predecessor_result.get("real_external_score") is False, "predecessor score changed")
    _require(
        predecessor_result.get("external_evaluation_status") == "not_run",
        "predecessor evaluation status changed",
    )
    verified.sort(key=lambda item: item["record_id"])
    return {
        "verified_file_count": len(verified),
        "verified_file_set_sha256": canonical_sha256(verified),
        "quality_decision": "no_go",
        "real_external_score": False,
        "external_evaluation_status": "not_run",
    }


def run(
    *,
    methodology_commit_sha: str,
    policy_path: Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    _require(policy_path == DEFAULT_POLICY_PATH, "policy path is frozen")
    source_lock = validate_source_locks()
    policy = load_policy(policy_path)
    predecessor = validate_predecessor_files(policy)
    report = build_policy_report(policy, methodology_commit_sha=methodology_commit_sha)
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
    except PolicyLockError as exc:
        raise SystemExit(f"phase11.8.10B-P0 policy lock failed closed: {exc}") from exc
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
