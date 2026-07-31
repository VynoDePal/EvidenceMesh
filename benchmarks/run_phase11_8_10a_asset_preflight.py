#!/usr/bin/env python3
"""Run the deterministic, metadata-only Phase 11.8.10A preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, cast

from benchmarks.phase11_8_10a_asset_preflight import (
    DEFAULT_MANIFEST_PATH,
    AssetLockError,
    build_reconnaissance_report,
    canonical_sha256,
    load_and_validate_inventory,
    load_manifest,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY_PATH = REPOSITORY_ROOT / "benchmarks/data/phase11_8_10a_object_inventory_v1.json"
DEFAULT_SOURCE_LOCK_PATH = REPOSITORY_ROOT / "benchmarks/data/phase11_8_10a_source_locks_v1.json"
SOURCE_LOCK_SCHEMA = "evidencemesh.phase11_8_10a.source-locks.v1"
MAX_SOURCE_LOCK_BYTES = 128 * 1024
PHASE12_MARKERS = ("phase12", "phase_12", "phase-12")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssetLockError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_authority_path(relative_path: object) -> tuple[str, Path]:
    _require(isinstance(relative_path, str) and bool(relative_path), "source path must be a string")
    relative_path = cast(str, relative_path)
    lowered = relative_path.lower()
    _require(
        not any(marker in lowered for marker in PHASE12_MARKERS),
        "Phase 12 source access is forbidden",
    )
    pure = PurePosixPath(relative_path)
    _require(
        not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts,
        "unsafe source path",
    )
    _require("\\" not in relative_path, "source path must use POSIX separators")
    resolved = REPOSITORY_ROOT.joinpath(*pure.parts)
    _require(
        resolved.is_file() and not resolved.is_symlink(),
        f"authority source is not a regular file: {relative_path}",
    )
    return relative_path, resolved


def validate_source_locks(path: Path = DEFAULT_SOURCE_LOCK_PATH) -> dict[str, Any]:
    _require(path == DEFAULT_SOURCE_LOCK_PATH, "source-lock path is frozen")
    _require(
        path.is_file() and not path.is_symlink(), "source-lock manifest must be a regular file"
    )
    payload = path.read_bytes()
    _require(len(payload) <= MAX_SOURCE_LOCK_BYTES, "source-lock manifest is too large")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetLockError("source-lock manifest is invalid") from exc
    _require(isinstance(decoded, dict), "source-lock manifest must be an object")
    _require(decoded.get("schema_version") == SOURCE_LOCK_SCHEMA, "source-lock schema drifted")
    records = decoded.get("authority_sources")
    _require(isinstance(records, list) and bool(records), "authority source set is empty")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        _require(isinstance(record, dict), "authority source record must be an object")
        relative_path, absolute_path = _safe_authority_path(record.get("relative_path"))
        expected_hash = record.get("sha256")
        _require(
            isinstance(expected_hash, str)
            and len(expected_hash) == 64
            and all(character in "0123456789abcdef" for character in expected_hash),
            f"invalid source hash: {relative_path}",
        )
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


def run(
    *,
    methodology_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    inventory_path: Path = DEFAULT_INVENTORY_PATH,
) -> dict[str, Any]:
    _require(manifest_path == DEFAULT_MANIFEST_PATH, "manifest path is frozen")
    _require(inventory_path == DEFAULT_INVENTORY_PATH, "inventory path is frozen")
    source_lock = validate_source_locks()
    manifest = load_manifest(manifest_path)
    committed_inventory = manifest["metadata_importer_policy"]["committed_inventory"]
    _require(
        _sha256_file(inventory_path) == committed_inventory["sha256"],
        "committed object inventory hash mismatch",
    )
    inventory_summary = load_and_validate_inventory(inventory_path, manifest)
    report = build_reconnaissance_report(
        manifest,
        methodology_commit_sha=methodology_commit_sha,
        inventory_summary=inventory_summary,
    )
    report["source_lock"] = source_lock
    report["inventory"] = {
        "inventory_sha256": inventory_summary["inventory_sha256"],
        "object_count": inventory_summary["object_count"],
        "total_content_bytes": inventory_summary["total_content_bytes"],
        "digest_source": "immutable-git-lfs-content-oids",
        "payload_content_accessed": False,
    }
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
    except AssetLockError as exc:
        raise SystemExit(f"phase11.8.10A preflight failed closed: {exc}") from exc
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
