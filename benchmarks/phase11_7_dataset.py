#!/usr/bin/env python3
"""Create and load the sealed Phase 11.7/Phase 12 SimpleQA split.

The generator is run once before any Phase 11.7 provider or model request. It
commits only opaque row positions, stable case identifiers and aggregate
metadata. The scored Phase 11.7 loader materializes only its 24 selected rows;
the 96 reserved Phase 12 questions and answers are never selected or returned.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from benchmarks.run_end_to_end_phase10 import canonical_json_sha256
    from benchmarks.run_live_retrieval import (
        SIMPLEQA_DATASET_SHA256,
        SIMPLEQA_DATASET_URL,
        SIMPLEQA_REFERENCE_FILE_BLOB,
        SIMPLEQA_REFERENCE_REPO_COMMIT,
        BenchmarkRow,
        extract_source_urls,
        parse_simpleqa,
        sha256_bytes,
        stable_row_id,
    )
except ModuleNotFoundError:
    from run_end_to_end_phase10 import canonical_json_sha256  # type: ignore[no-redef]
    from run_live_retrieval import (  # type: ignore[no-redef]
        SIMPLEQA_DATASET_SHA256,
        SIMPLEQA_DATASET_URL,
        SIMPLEQA_REFERENCE_FILE_BLOB,
        SIMPLEQA_REFERENCE_REPO_COMMIT,
        BenchmarkRow,
        extract_source_urls,
        parse_simpleqa,
        sha256_bytes,
        stable_row_id,
    )

PHASE11_7_SUITE = "evidencemesh-phase11-7-fresh-confirmation-v1"
PHASE12_RESERVE_SUITE = "evidencemesh-phase12-untouched-reserve-v1"
PHASE11_7_NAMESPACE = "EvidenceMesh/phase11.7/fresh-confirmation/v1"
PHASE12_NAMESPACE = "EvidenceMesh/phase12/untouched-reserve/v1"
PHASE11_7_CASE_COUNT = 24
PHASE12_RESERVE_CASE_COUNT = 96
CASE_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")

PRIOR_SIMPLEQA_SOURCES = (
    "benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.json",
    "benchmarks/results/simpleqa_retrieval_phase3_2026-07-28.json",
    "benchmarks/results/simpleqa_retrieval_phase4_2026-07-28.json",
    "benchmarks/data/end_to_end_phase10_v1.json",
    "benchmarks/results/end_to_end_phase10_2026-07-29.json",
    "benchmarks/results/phase11_5_quality_recovery_2026-07-29.json",
    "benchmarks/results/phase11_6_tavily_citation_isolation_2026-07-29.json",
)


def _distribution(values: Iterable[str | None]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        label = value or "Unknown"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _walk_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _walk_strings(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            yield from _walk_strings(nested)


def collect_prior_case_ids(root: Path) -> tuple[set[str], list[dict[str, str]]]:
    """Collect every opaque 16-hex SimpleQA-style ID from frozen prior inputs."""

    case_ids: set[str] = set()
    sources: list[dict[str, str]] = []
    for relative_path in PRIOR_SIMPLEQA_SOURCES:
        path = root / relative_path
        payload = path.read_bytes()
        parsed = json.loads(payload)
        case_ids.update(
            value for value in _walk_strings(parsed) if CASE_ID_PATTERN.fullmatch(value)
        )
        sources.append(
            {
                "path": relative_path,
                "sha256": sha256_bytes(payload),
            }
        )
    return case_ids, sources


def _rank(namespace: str, case_id: str) -> str:
    return hashlib.sha256(f"{namespace}\0{case_id}".encode()).hexdigest()


def _select(
    indexed_rows: Sequence[tuple[int, BenchmarkRow]],
    *,
    namespace: str,
    count: int,
) -> list[tuple[int, BenchmarkRow]]:
    if len(indexed_rows) < count:
        raise ValueError(f"not enough eligible rows: {len(indexed_rows)} available, {count} needed")
    return sorted(indexed_rows, key=lambda item: (_rank(namespace, item[1].id), item[1].id))[:count]


def _dataset_metadata() -> dict[str, Any]:
    return {
        "name": "SimpleQA test set",
        "source_url": SIMPLEQA_DATASET_URL,
        "sha256": SIMPLEQA_DATASET_SHA256,
        "reference_repository_commit": SIMPLEQA_REFERENCE_REPO_COMMIT,
        "reference_file_blob": SIMPLEQA_REFERENCE_FILE_BLOB,
        "license": "MIT (openai/simple-evals)",
    }


def build_split_manifests(
    rows: Sequence[BenchmarkRow],
    *,
    prior_case_ids: set[str],
    prior_sources: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build deterministic fresh-calibration and sealed-reserve manifests."""

    if len({row.id for row in rows}) != len(rows):
        raise ValueError("dataset row IDs are not unique")
    indexed_rows = list(enumerate(rows))
    eligible = [item for item in indexed_rows if item[1].id not in prior_case_ids]
    phase11_7 = _select(
        eligible,
        namespace=PHASE11_7_NAMESPACE,
        count=PHASE11_7_CASE_COUNT,
    )
    phase11_7_ids = {row.id for _, row in phase11_7}
    reserve_eligible = [item for item in eligible if item[1].id not in phase11_7_ids]
    phase12 = _select(
        reserve_eligible,
        namespace=PHASE12_NAMESPACE,
        count=PHASE12_RESERVE_CASE_COUNT,
    )
    phase12_ids = {row.id for _, row in phase12}
    if phase11_7_ids & phase12_ids:
        raise ValueError("Phase 11.7 and Phase 12 selections overlap")

    prior_digest = canonical_json_sha256(sorted(prior_case_ids))
    phase11_7_cases = [{"row_index": row_index, "case_id": row.id} for row_index, row in phase11_7]
    phase12_cases = [{"row_index": row_index, "case_id": row.id} for row_index, row in phase12]
    phase11_7_manifest = {
        "schema_version": 1,
        "suite": PHASE11_7_SUITE,
        "dataset": _dataset_metadata(),
        "selection": {
            "namespace": PHASE11_7_NAMESPACE,
            "method": "ascending SHA-256(namespace + NUL + stable case ID)",
            "eligible_row_count": len(eligible),
            "excluded_prior_case_count": len(prior_case_ids),
            "excluded_prior_case_ids_sha256": prior_digest,
            "case_count": PHASE11_7_CASE_COUNT,
            "row_index_semantics": "zero-based data-row index after the CSV header",
        },
        "prior_sources": prior_sources,
        "cases": phase11_7_cases,
        "case_ids_sha256": canonical_json_sha256([row.id for _, row in phase11_7]),
        "topic_distribution": _distribution(row.topic for _, row in phase11_7),
        "answer_type_distribution": _distribution(row.answer_type for _, row in phase11_7),
        "privacy": {
            "questions_committed": False,
            "reference_answers_committed": False,
            "source_content_committed": False,
            "generated_answers_committed": False,
        },
    }
    reserve_manifest = {
        "schema_version": 1,
        "suite": PHASE12_RESERVE_SUITE,
        "dataset": _dataset_metadata(),
        "selection": {
            "namespace": PHASE12_NAMESPACE,
            "method": "ascending SHA-256(namespace + NUL + stable case ID)",
            "eligible_row_count": len(reserve_eligible),
            "excluded_prior_and_phase11_7_case_count": (len(prior_case_ids | phase11_7_ids)),
            "excluded_prior_case_ids_sha256": prior_digest,
            "phase11_7_case_ids_sha256": canonical_json_sha256([row.id for _, row in phase11_7]),
            "case_count": PHASE12_RESERVE_CASE_COUNT,
            "row_index_semantics": "zero-based data-row index after the CSV header",
        },
        "sealed_cases": phase12_cases,
        "sealed_case_ids_sha256": canonical_json_sha256([row.id for _, row in phase12]),
        "seal": {
            "questions_committed": False,
            "reference_answers_committed": False,
            "topic_distribution_committed": False,
            "answer_type_distribution_committed": False,
            "phase11_7_loader_may_materialize_reserved_rows": False,
        },
    }
    return phase11_7_manifest, reserve_manifest


def _validate_case_entries(
    value: object,
    *,
    expected_count: int,
    field: str,
) -> list[tuple[int, str]]:
    if not isinstance(value, list) or len(value) != expected_count:
        raise ValueError(f"{field} must contain exactly {expected_count} entries")
    entries: list[tuple[int, str]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError(f"{field} contains a non-object entry")
        row_index = raw.get("row_index")
        case_id = raw.get("case_id")
        if (
            not isinstance(row_index, int)
            or row_index < 0
            or not isinstance(case_id, str)
            or not CASE_ID_PATTERN.fullmatch(case_id)
        ):
            raise ValueError(f"{field} contains an invalid selector")
        entries.append((row_index, case_id))
    if len({row_index for row_index, _ in entries}) != expected_count:
        raise ValueError(f"{field} row indexes are not unique")
    if len({case_id for _, case_id in entries}) != expected_count:
        raise ValueError(f"{field} case IDs are not unique")
    return entries


def parse_selected_simpleqa(
    payload: bytes,
    selectors: Sequence[tuple[int, str]],
) -> tuple[list[BenchmarkRow], int]:
    """Materialize only selected rows; all other CSV rows are skipped immediately."""

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("SimpleQA dataset is not valid UTF-8") from exc
    selected_by_index = dict(selectors)
    materialized: dict[int, BenchmarkRow] = {}
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ["metadata", "problem", "answer"]:
        raise ValueError(f"unexpected SimpleQA columns: {reader.fieldnames}")
    row_count = 0
    for row_index, raw in enumerate(reader):
        row_count += 1
        expected_case_id = selected_by_index.get(row_index)
        if expected_case_id is None:
            continue
        question = (raw.get("problem") or "").strip()
        answer = (raw.get("answer") or "").strip()
        if not question or not answer:
            raise ValueError(f"selected SimpleQA row {row_index} is incomplete")
        if stable_row_id(question) != expected_case_id:
            raise ValueError(f"selected SimpleQA row {row_index} has an unexpected case ID")
        metadata_text = raw.get("metadata") or ""
        try:
            metadata = ast.literal_eval(metadata_text)
        except (SyntaxError, ValueError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        materialized[row_index] = BenchmarkRow(
            id=expected_case_id,
            question=question,
            answers=(answer,),
            gold_urls=extract_source_urls(metadata),
            topic=str(metadata["topic"]) if metadata.get("topic") else None,
            answer_type=(str(metadata["answer_type"]) if metadata.get("answer_type") else None),
        )
    missing = [row_index for row_index, _ in selectors if row_index not in materialized]
    if missing:
        raise ValueError(f"selected SimpleQA row indexes are missing: {missing}")
    return [materialized[row_index] for row_index, _ in selectors], row_count


def load_phase11_7_rows(
    dataset_path: Path,
    manifest_path: Path,
    reserve_manifest_path: Path,
    *,
    root: Path,
    expected_manifest_sha256: str,
    expected_reserve_manifest_sha256: str,
) -> tuple[list[BenchmarkRow], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load the 24 scored rows while keeping all 96 reserved rows sealed."""

    dataset_bytes = dataset_path.read_bytes()
    if sha256_bytes(dataset_bytes) != SIMPLEQA_DATASET_SHA256:
        raise ValueError("SimpleQA dataset checksum does not match the locked revision")
    manifest_bytes = manifest_path.read_bytes()
    if sha256_bytes(manifest_bytes) != expected_manifest_sha256:
        raise ValueError("Phase 11.7 manifest checksum does not match the frozen lock")
    reserve_bytes = reserve_manifest_path.read_bytes()
    if sha256_bytes(reserve_bytes) != expected_reserve_manifest_sha256:
        raise ValueError("Phase 12 reserve checksum does not match the frozen lock")
    manifest = json.loads(manifest_bytes)
    reserve = json.loads(reserve_bytes)
    if not isinstance(manifest, dict) or manifest.get("suite") != PHASE11_7_SUITE:
        raise ValueError("Phase 11.7 manifest has an unexpected suite")
    if not isinstance(reserve, dict) or reserve.get("suite") != PHASE12_RESERVE_SUITE:
        raise ValueError("Phase 12 reserve has an unexpected suite")

    selectors = _validate_case_entries(
        manifest.get("cases"),
        expected_count=PHASE11_7_CASE_COUNT,
        field="Phase 11.7 cases",
    )
    reserve_selectors = _validate_case_entries(
        reserve.get("sealed_cases"),
        expected_count=PHASE12_RESERVE_CASE_COUNT,
        field="Phase 12 sealed cases",
    )
    selected_ids = {case_id for _, case_id in selectors}
    reserve_ids = {case_id for _, case_id in reserve_selectors}
    selected_indexes = {row_index for row_index, _ in selectors}
    reserve_indexes = {row_index for row_index, _ in reserve_selectors}
    if selected_ids & reserve_ids or selected_indexes & reserve_indexes:
        raise ValueError("Phase 11.7 and Phase 12 selectors overlap")

    prior_case_ids, prior_sources = collect_prior_case_ids(root)
    prior_digest = canonical_json_sha256(sorted(prior_case_ids))
    selection = manifest.get("selection")
    reserve_selection = reserve.get("selection")
    if (
        not isinstance(selection, dict)
        or selection.get("namespace") != PHASE11_7_NAMESPACE
        or selection.get("case_count") != PHASE11_7_CASE_COUNT
        or selection.get("excluded_prior_case_ids_sha256") != prior_digest
        or manifest.get("prior_sources") != prior_sources
        or selected_ids & prior_case_ids
    ):
        raise ValueError("Phase 11.7 selection lock is invalid")
    selected_id_list = [case_id for _, case_id in selectors]
    if manifest.get("case_ids_sha256") != canonical_json_sha256(selected_id_list):
        raise ValueError("Phase 11.7 case-ID commitment is invalid")
    if (
        not isinstance(reserve_selection, dict)
        or reserve_selection.get("namespace") != PHASE12_NAMESPACE
        or reserve_selection.get("case_count") != PHASE12_RESERVE_CASE_COUNT
        or reserve_selection.get("excluded_prior_case_ids_sha256") != prior_digest
        or reserve_selection.get("phase11_7_case_ids_sha256")
        != canonical_json_sha256(selected_id_list)
        or reserve.get("sealed_case_ids_sha256")
        != canonical_json_sha256([case_id for _, case_id in reserve_selectors])
    ):
        raise ValueError("Phase 12 reserve selection lock is invalid")

    rows, dataset_row_count = parse_selected_simpleqa(dataset_bytes, selectors)
    if manifest.get("topic_distribution") != _distribution(row.topic for row in rows):
        raise ValueError("Phase 11.7 topic distribution changed")
    if manifest.get("answer_type_distribution") != _distribution(row.answer_type for row in rows):
        raise ValueError("Phase 11.7 answer-type distribution changed")
    if selection.get("eligible_row_count") != dataset_row_count - len(prior_case_ids):
        raise ValueError("Phase 11.7 eligible-row count changed")

    reserve_metadata = {
        "manifest_path": str(reserve_manifest_path),
        "manifest_sha256": expected_reserve_manifest_sha256,
        "case_count": PHASE12_RESERVE_CASE_COUNT,
        "case_ids_sha256": reserve["sealed_case_ids_sha256"],
        "questions_or_answers_materialized": False,
        "used_by_phase11_7": False,
    }
    return rows, manifest, _dataset_metadata(), reserve_metadata


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--phase11-7-output",
        type=Path,
        default=root / "benchmarks/data/phase11_7_fresh_confirmation_v1.json",
    )
    parser.add_argument(
        "--phase12-output",
        type=Path,
        default=root / "benchmarks/data/phase12_untouched_reserve_v1.json",
    )
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    dataset_bytes = arguments.dataset.read_bytes()
    if sha256_bytes(dataset_bytes) != SIMPLEQA_DATASET_SHA256:
        raise ValueError("SimpleQA dataset checksum does not match the locked revision")
    rows = parse_simpleqa(dataset_bytes)
    prior_case_ids, prior_sources = collect_prior_case_ids(arguments.root)
    phase11_7, phase12 = build_split_manifests(
        rows,
        prior_case_ids=prior_case_ids,
        prior_sources=prior_sources,
    )
    _write_json(arguments.phase11_7_output, phase11_7)
    _write_json(arguments.phase12_output, phase12)


if __name__ == "__main__":
    main()
