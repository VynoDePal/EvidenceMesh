"""Offline conformance adapter for Phase 11.8.9 external retrieval benchmarks.

This module deliberately separates two things:

* deterministic integration checks over tiny, synthetic fixtures; and
* fail-closed handling of any purported official BRIGHT or BrowseComp-Plus
  bundle.

The committed registry pins the upstream repositories and repository-license
files, but does not claim that those files license separately distributed
queries, corpora, or qrels.  Real evaluation therefore fails closed until the
asset-license lock is resolved in a future reviewed registry revision.

The implementation uses only the Python standard library.  It has no download,
authentication, provider, model, secret, or network path.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "evidencemesh.phase11_8_9.external-benchmarks.v1"
FIXTURES_SCHEMA = "evidencemesh.phase11_8_9.external-eval-fixtures.v1"
SUITE_SCHEMA = "evidencemesh.phase11_8_9.external-suite.v1"
RESULT_SCHEMA = "evidencemesh.phase11_8_9.external-eval-result.v1"
FIXTURE_RESULT_SCHEMA = "evidencemesh.phase11_8_9.external-conformance-result.v1"
BUNDLE_SCHEMA = "evidencemesh.phase11_8_9.local-bundle.v1"

DEFAULT_REGISTRY_PATH = Path(__file__).parent / "data/phase11_8_9_external_benchmarks_v1.json"
DEFAULT_FIXTURES_PATH = Path(__file__).parent / "data/phase11_8_9_external_eval_fixtures_v1.json"
BUNDLE_MANIFEST_NAME = "bundle_manifest.json"

RECALL_CUTOFFS = (5, 10, 20, 100, 1000)
NDCG_CUTOFFS = (5, 10, 20)
ADAPTER_CONTRACT = "local-fixed-corpus-retrieval-v1"
SYNTHETIC_ORIGIN = "synthetic-conformance"
OFFICIAL_ORIGIN = "official-local-copy"
SYNTHETIC_BUNDLE_POLICY_ID = "synthetic-local-bundle-strict-v1"
TREC_QRELS_ITERATION = "Q0"
RUN_ORDER_POLICY = "score-desc-docid-asc-rank-must-match"
NDCG_GAIN_POLICY = "trec-linear-relevance"

_MANIFEST_MAX_BYTES = 256 * 1024
_ROLE_MAX_BYTES = {
    "queries": 2 * 1024 * 1024,
    "corpus": 8 * 1024 * 1024,
    "run": 8 * 1024 * 1024,
    "qrels": 8 * 1024 * 1024,
}
_COUNT_CAPS = {
    "queries": 10_000,
    "corpus_documents": 50_000,
    "run_queries": 10_000,
    "run_entries": 250_000,
    "qrel_queries": 10_000,
    "qrel_entries": 250_000,
    "positive_qrels": 250_000,
}
_EXPECTED_COUNT_KEYS = frozenset(_COUNT_CAPS)

_ADAPTER_POLICIES: dict[str, Any] = {
    "corpus_document_id_aliases": ["doc_id", "docid", "_id", "id"],
    "corpus_url_field": "accepted-input-never-published",
    "trec_qrels_iteration": TREC_QRELS_ITERATION,
    "run_order": RUN_ORDER_POLICY,
    "ndcg_gain": NDCG_GAIN_POLICY,
    "empty_run_per_query": "allowed-and-scored-zero",
}
_SYNTHETIC_BUNDLE_POLICY: dict[str, Any] = {
    "policy_id": SYNTHETIC_BUNDLE_POLICY_ID,
    "regular_files_only": True,
    "symlinks_forbidden": True,
    "path_escape_forbidden": True,
    "sha256_policy": "streaming-full-file",
    "byte_length_required": True,
    "exact_query_coverage": True,
    "max_manifest_bytes": _MANIFEST_MAX_BYTES,
    "max_file_bytes_by_role": _ROLE_MAX_BYTES,
    "max_counts": _COUNT_CAPS,
}
_PLANNED_OFFICIAL_POLICY: dict[str, Any] = {
    "available_in_v1": False,
    "score_publication_in_v1": "forbidden",
    "global_requirements": [
        "authoritative asset revision",
        "authoritative per-asset SHA-256",
        "authoritative per-asset byte length",
        "authoritative per-asset record count",
        "resolved asset-license evidence",
    ],
    "bright": {
        "required_domain_count": 12,
        "aggregation": "macro-average-across-all-12-domains",
        "excluded_ids_lock_required": True,
        "required_asset_roles": ["queries", "corpus", "qrels", "excluded_ids"],
    },
    "browsecomp_plus": {
        "required_qrels_views": ["evidence", "gold"],
        "report_each_qrels_view_separately": True,
        "required_asset_roles": ["queries", "corpus", "evidence_qrels", "gold_qrels"],
    },
}

_HEX_40 = frozenset("0123456789abcdef")
_HEX_64 = frozenset("0123456789abcdef")
_SUPPORTED_FORMATS = {
    "queries": frozenset({"json", "jsonl", "tsv"}),
    "corpus": frozenset({"json", "jsonl"}),
    "run": frozenset({"json", "jsonl", "trec"}),
    "qrels": frozenset({"json", "jsonl", "trec"}),
}
_PINNED_BENCHMARKS: dict[str, dict[str, str]] = {
    "bright": {
        "official_repository": "https://github.com/xlang-ai/BRIGHT",
        "repository_revision": "d99e8391d967d4c2b3a74732530d2309e2fc92b6",
        "license_spdx_id": "CC-BY-4.0",
        "license_path": "LICENSE",
        "license_git_blob_sha1": "2f244ac814036ecd9ba9f69782e89ce6b1dca9eb",
        "license_scope": "repository-license-file-only",
    },
    "browsecomp_plus": {
        "official_repository": "https://github.com/texttron/BrowseComp-Plus",
        "repository_revision": "046949032b0328319cc9a02663a759ec601d9402",
        "license_spdx_id": "MIT",
        "license_path": "LICENSE",
        "license_git_blob_sha1": "1eeb9f2ab7b823eef913d01626ca28adf6422fba",
        "license_scope": "repository-software-only",
    },
}


class ConformanceError(ValueError):
    """Raised when an input violates a locked local evaluation contract."""


class _OfficialEvaluationBlockedError(ConformanceError):
    """Internal signal for the intentionally unavailable v1 official path."""


@dataclass(frozen=True, slots=True)
class RankedDocument:
    """One deterministic ranked-run entry."""

    doc_id: str
    rank: int
    score: float


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConformanceError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _array(value: object, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label} must be a JSON array")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    required: set[str],
    label: str,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - value.keys()
    extra = value.keys() - required - optional
    _require(not missing, f"{label} is missing keys: {sorted(missing)}")
    _require(not extra, f"{label} has unsupported keys: {sorted(extra)}")


def _identifier(value: object, label: str) -> str:
    _require(isinstance(value, str), f"{label} must be a string")
    normalized = value.strip()
    _require(bool(normalized), f"{label} must not be empty")
    _require("\t" not in normalized and "\n" not in normalized, f"{label} has control separators")
    return normalized


def _finite_number(value: object, label: str) -> float:
    _require(
        isinstance(value, int | float) and not isinstance(value, bool),
        f"{label} must be numeric",
    )
    number = float(value)
    _require(math.isfinite(number), f"{label} must be finite")
    return number


def _positive_integer(value: object, label: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    _require(value > 0, f"{label} must be positive")
    return value


def _non_negative_integer(value: object, label: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    _require(value >= 0, f"{label} must be non-negative")
    return value


def _open_regular_file_fd(path: Path) -> int:
    """Open ``path`` without following a symlink in any path component."""

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    _require(nofollow != 0 and directory != 0, "secure local file opening is unavailable")

    absolute = Path(os.path.abspath(path))
    parts = absolute.parts
    _require(
        absolute.is_absolute() and len(parts) >= 2,
        f"cannot securely resolve regular file: {path.name}",
    )
    directory_flags = os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    directory_fd = -1
    file_fd = -1
    try:
        directory_fd = os.open(absolute.anchor, directory_flags)
        for component in parts[1:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(parts[-1], file_flags, dir_fd=directory_fd)
        metadata = os.fstat(file_fd)
        _require(stat.S_ISREG(metadata.st_mode), f"{path.name} must be a regular file")
        result_fd = file_fd
        file_fd = -1
        return result_fd
    except OSError as exc:
        raise ConformanceError(f"cannot securely open regular file: {path.name}") from exc
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)
        if file_fd >= 0:
            os.close(file_fd)


def _read_file_once(path: Path, *, max_bytes: int) -> tuple[bytes, str, int]:
    digest = hashlib.sha256()
    byte_length = 0
    chunks: list[bytes] = []
    file_fd = -1
    try:
        file_fd = _open_regular_file_fd(path)
        while chunk := os.read(file_fd, 64 * 1024):
            byte_length += len(chunk)
            _require(byte_length <= max_bytes, f"{path.name} exceeds its byte limit")
            digest.update(chunk)
            chunks.append(chunk)
    except OSError as exc:
        raise ConformanceError(f"cannot read regular file: {path.name}") from exc
    finally:
        if file_fd >= 0:
            os.close(file_fd)
    return b"".join(chunks), digest.hexdigest(), byte_length


def _decode_utf8(content: bytes, label: str, source_name: str) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeError as exc:
        raise ConformanceError(f"cannot decode valid {label}: {source_name}") from exc


def _parse_json_bytes(content: bytes, label: str, source_name: str) -> Any:
    try:
        return json.loads(_decode_utf8(content, label, source_name))
    except json.JSONDecodeError as exc:
        raise ConformanceError(f"cannot parse valid {label} JSON: {source_name}") from exc


def _load_json(path: Path, label: str, *, max_bytes: int = _MANIFEST_MAX_BYTES) -> Any:
    content, _digest, _byte_length = _read_file_once(path, max_bytes=max_bytes)
    return _parse_json_bytes(content, label, path.name)


def _is_lower_hex(value: object, length: int) -> bool:
    alphabet = _HEX_40 if length == 40 else _HEX_64
    return isinstance(value, str) and len(value) == length and set(value) <= alphabet


def validate_registry(data: object) -> dict[str, Any]:
    """Validate the committed registry against hard-coded authoritative pins."""

    registry = _object(data, "registry")
    _exact_keys(
        registry,
        {
            "schema_version",
            "purpose",
            "network_policy",
            "publication_policy",
            "adapter_policies",
            "synthetic_bundle_policy",
            "planned_official_evaluation_policy",
            "benchmarks",
        },
        "registry",
    )
    _require(registry["schema_version"] == REGISTRY_SCHEMA, "unsupported registry schema")
    _require(registry["purpose"] == "integration-conformance-only", "registry purpose drift")

    network_policy = _object(registry["network_policy"], "registry.network_policy")
    expected_network_keys = {
        "ordinary_tests_must_not_download",
        "ordinary_tests_must_not_authenticate",
        "ordinary_tests_must_not_call_models",
        "ordinary_tests_must_not_call_providers",
    }
    _exact_keys(network_policy, expected_network_keys, "registry.network_policy")
    _require(
        all(network_policy[key] is True for key in expected_network_keys),
        "ordinary-test network isolation must remain locked",
    )

    publication = _object(registry["publication_policy"], "registry.publication_policy")
    expected_publication = {
        "synthetic_fixture_metrics_are_real_external_scores": False,
        "synthetic_fixture_metrics_support_quality_claims": False,
        "real_external_scores_require_resolved_asset_license": True,
        "real_external_scores_require_exact_repository_revision": True,
        "real_external_scores_supported_in_v1": False,
    }
    _exact_keys(publication, set(expected_publication), "registry.publication_policy")
    _require(publication == expected_publication, "publication policy drift")
    _require(
        registry["adapter_policies"] == _ADAPTER_POLICIES,
        "adapter policy drift",
    )
    _require(
        registry["synthetic_bundle_policy"] == _SYNTHETIC_BUNDLE_POLICY,
        "synthetic bundle policy drift",
    )
    _require(
        registry["planned_official_evaluation_policy"] == _PLANNED_OFFICIAL_POLICY,
        "planned official evaluation policy drift",
    )

    entries = _array(registry["benchmarks"], "registry.benchmarks")
    _require(len(entries) == len(_PINNED_BENCHMARKS), "registry benchmark count drift")
    seen: set[str] = set()
    for raw_entry in entries:
        entry = _object(raw_entry, "registry benchmark")
        required = {
            "benchmark_id",
            "display_name",
            "adapter_contract",
            "official_repository",
            "repository_revision",
            "repository_license_file",
            "benchmark_asset_license",
            "official_metadata",
            "v1_official_blockers",
            "supported_local_formats",
        }
        _exact_keys(entry, required, "registry benchmark")
        benchmark_id = _identifier(entry["benchmark_id"], "benchmark_id")
        _require(benchmark_id in _PINNED_BENCHMARKS, "unknown benchmark id")
        _require(benchmark_id not in seen, "duplicate benchmark id")
        seen.add(benchmark_id)
        pin = _PINNED_BENCHMARKS[benchmark_id]
        _require(entry["adapter_contract"] == ADAPTER_CONTRACT, "adapter contract drift")
        _require(entry["official_repository"] == pin["official_repository"], "repository pin drift")
        _require(
            entry["repository_revision"] == pin["repository_revision"]
            and _is_lower_hex(entry["repository_revision"], 40),
            "repository revision pin drift",
        )

        repository_license = _object(
            entry["repository_license_file"],
            f"{benchmark_id}.repository_license_file",
        )
        _exact_keys(
            repository_license,
            {"spdx_id", "path", "git_blob_sha1", "scope"},
            f"{benchmark_id}.repository_license_file",
        )
        expected_license = {
            "spdx_id": pin["license_spdx_id"],
            "path": pin["license_path"],
            "git_blob_sha1": pin["license_git_blob_sha1"],
            "scope": pin["license_scope"],
        }
        _require(repository_license == expected_license, "repository license pin drift")
        _require(
            _is_lower_hex(repository_license["git_blob_sha1"], 40),
            "repository license blob must be a full SHA-1",
        )

        asset_license = _object(
            entry["benchmark_asset_license"],
            f"{benchmark_id}.benchmark_asset_license",
        )
        _exact_keys(
            asset_license,
            {
                "status",
                "scope",
                "spdx_id",
                "evidence_revision",
                "real_external_evaluation_allowed",
                "reason",
            },
            f"{benchmark_id}.benchmark_asset_license",
        )
        _require(asset_license["status"] == "unresolved", "asset license must fail closed")
        _require(asset_license["spdx_id"] is None, "unverified asset SPDX id is forbidden")
        _require(
            asset_license["evidence_revision"] is None,
            "unverified asset license evidence is forbidden",
        )
        _require(
            asset_license["real_external_evaluation_allowed"] is False,
            "real external evaluation cannot be authorized by this registry",
        )
        _identifier(asset_license["scope"], f"{benchmark_id}.asset_license.scope")
        _identifier(asset_license["reason"], f"{benchmark_id}.asset_license.reason")
        blockers = _array(entry["v1_official_blockers"], f"{benchmark_id}.v1_official_blockers")
        _require(bool(blockers), f"{benchmark_id} official blockers must be explicit")
        _require(
            all(isinstance(blocker, str) and blocker.strip() for blocker in blockers),
            f"{benchmark_id} official blockers must be non-empty strings",
        )

        formats = _object(
            entry["supported_local_formats"],
            f"{benchmark_id}.supported_local_formats",
        )
        _exact_keys(formats, set(_SUPPORTED_FORMATS), f"{benchmark_id}.supported_local_formats")
        for role, allowed in _SUPPORTED_FORMATS.items():
            actual = _array(formats[role], f"{benchmark_id}.{role} formats")
            _require(
                set(actual) == set(allowed) and len(actual) == len(allowed),
                f"{benchmark_id}.{role} format lock drift",
            )
    _require(seen == set(_PINNED_BENCHMARKS), "registry benchmark set drift")
    return registry


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    """Read and validate the local registry without performing any I/O beyond the file."""

    return validate_registry(_load_json(path, "registry"))


def _registry_entry(registry: Mapping[str, Any], benchmark_id: str) -> dict[str, Any]:
    for raw_entry in _array(registry["benchmarks"], "registry.benchmarks"):
        entry = _object(raw_entry, "registry benchmark")
        if entry["benchmark_id"] == benchmark_id:
            return entry
    raise ConformanceError(f"benchmark is not registered: {benchmark_id}")


def _validate_suite_manifest(
    value: object,
    registry: Mapping[str, Any],
    *,
    expected_origin: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    suite = _object(value, "suite_manifest")
    _exact_keys(
        suite,
        {
            "schema_version",
            "benchmark_id",
            "adapter_contract",
            "content_origin",
            "contains_official_benchmark_content",
            "official_repository",
            "repository_revision",
            "repository_license_file",
            "asset_license",
        },
        "suite_manifest",
    )
    _require(suite["schema_version"] == SUITE_SCHEMA, "unsupported suite schema")
    benchmark_id = _identifier(suite["benchmark_id"], "suite benchmark_id")
    entry = _registry_entry(registry, benchmark_id)
    _require(suite["adapter_contract"] == ADAPTER_CONTRACT, "suite adapter contract drift")
    origin = suite["content_origin"]
    _require(origin in {SYNTHETIC_ORIGIN, OFFICIAL_ORIGIN}, "unsupported content origin")
    if expected_origin is not None:
        _require(origin == expected_origin, "unexpected suite content origin")
    _require(
        suite["official_repository"] == entry["official_repository"],
        "suite repository does not match registry",
    )
    _require(
        suite["repository_revision"] == entry["repository_revision"],
        "suite revision does not match registry",
    )
    _require(
        suite["repository_license_file"] == entry["repository_license_file"],
        "suite repository-license lock does not match registry",
    )

    asset_license = _object(suite["asset_license"], "suite asset_license")
    if origin == SYNTHETIC_ORIGIN:
        _exact_keys(
            asset_license,
            {"status", "spdx_id", "scope"},
            "suite synthetic asset_license",
        )
        _require(
            suite["contains_official_benchmark_content"] is False,
            "synthetic fixtures must not contain official benchmark content",
        )
        _require(asset_license["status"] == "resolved", "synthetic fixture license is required")
        _require(asset_license["spdx_id"] == "Apache-2.0", "synthetic fixture license drift")
        _require(
            asset_license["scope"] == "synthetic-fixture-only",
            "synthetic fixture license scope drift",
        )
    else:
        _require(
            suite["contains_official_benchmark_content"] is True,
            "official local copies must declare official content",
        )
        locked_assets = _object(
            entry["benchmark_asset_license"],
            "registry benchmark_asset_license",
        )
        _require(asset_license == locked_assets, "official asset-license lock mismatch")
        raise _OfficialEvaluationBlockedError(
            "official evaluation is unavailable in adapter v1; authoritative asset locks "
            "and benchmark-specific aggregation policies are not implemented"
        )
    return suite, entry


def _one_alias(record: Mapping[str, Any], aliases: tuple[str, ...], label: str) -> str:
    present = [key for key in aliases if key in record]
    _require(len(present) == 1, f"{label} must contain exactly one of {aliases}")
    return present[0]


def _normalize_queries(raw: object) -> dict[str, str]:
    queries: dict[str, str] = {}
    if isinstance(raw, dict):
        records: list[object] = [
            {"query_id": query_id, "text": text} for query_id, text in raw.items()
        ]
    else:
        records = _array(raw, "queries")
    _require(bool(records), "queries must not be empty")
    for index, raw_record in enumerate(records):
        record = _object(raw_record, f"queries[{index}]")
        id_key = _one_alias(record, ("query_id", "_id", "id"), f"queries[{index}]")
        text_key = _one_alias(record, ("text", "query"), f"queries[{index}]")
        allowed = {id_key, text_key}
        _require(record.keys() <= allowed, f"queries[{index}] has unsupported fields")
        query_id = _identifier(record[id_key], f"queries[{index}].{id_key}")
        text = _identifier(record[text_key], f"queries[{index}].{text_key}")
        _require(query_id not in queries, f"duplicate query id: {query_id}")
        queries[query_id] = text
    return queries


def _normalize_corpus(raw: object) -> dict[str, tuple[str, str]]:
    corpus: dict[str, tuple[str, str]] = {}
    if isinstance(raw, dict):
        records: list[object] = []
        for doc_id, value in raw.items():
            if isinstance(value, str):
                records.append({"doc_id": doc_id, "text": value})
            else:
                record = dict(_object(value, f"corpus[{doc_id}]"))
                record["doc_id"] = doc_id
                records.append(record)
    else:
        records = _array(raw, "corpus")
    _require(bool(records), "corpus must not be empty")
    for index, raw_record in enumerate(records):
        record = _object(raw_record, f"corpus[{index}]")
        id_key = _one_alias(record, ("doc_id", "docid", "_id", "id"), f"corpus[{index}]")
        text_key = _one_alias(
            record,
            ("text", "contents", "content"),
            f"corpus[{index}]",
        )
        allowed = {id_key, text_key, "title", "url"}
        _require(record.keys() <= allowed, f"corpus[{index}] has unsupported fields")
        doc_id = _identifier(record[id_key], f"corpus[{index}].{id_key}")
        text = _identifier(record[text_key], f"corpus[{index}].{text_key}")
        title_value = record.get("title", "")
        _require(isinstance(title_value, str), f"corpus[{index}].title must be a string")
        if "url" in record:
            _identifier(record["url"], f"corpus[{index}].url")
        _require(doc_id not in corpus, f"duplicate document id: {doc_id}")
        # URLs are accepted for BrowseComp-Plus input compatibility, but are
        # intentionally discarded so aggregate outputs can never publish them.
        corpus[doc_id] = (title_value, text)
    return corpus


def _run_record(
    record: Mapping[str, Any],
    label: str,
    default_rank: int | None = None,
) -> tuple[str, RankedDocument]:
    query_key = _one_alias(record, ("query_id", "qid"), label)
    doc_key = _one_alias(record, ("doc_id", "docid", "_id", "id"), label)
    allowed = {query_key, doc_key, "rank", "score", "system"}
    _require(record.keys() <= allowed, f"{label} has unsupported fields")
    query_id = _identifier(record[query_key], f"{label}.{query_key}")
    doc_id = _identifier(record[doc_key], f"{label}.{doc_key}")
    rank_value = record.get("rank", default_rank)
    _require(rank_value is not None, f"{label}.rank is required")
    rank = _positive_integer(rank_value, f"{label}.rank")
    score = _finite_number(record.get("score", -rank), f"{label}.score")
    if "system" in record:
        _identifier(record["system"], f"{label}.system")
    return query_id, RankedDocument(doc_id=doc_id, rank=rank, score=score)


def _normalize_run(raw: object) -> dict[str, tuple[RankedDocument, ...]]:
    grouped: dict[str, list[RankedDocument]] = {}
    if isinstance(raw, dict):
        for raw_query_id, raw_results in raw.items():
            query_id = _identifier(raw_query_id, "run query id")
            entries: list[RankedDocument] = []
            if isinstance(raw_results, dict):
                scored = [
                    (
                        _identifier(doc_id, f"run[{query_id}] document id"),
                        _finite_number(score, f"run[{query_id}][{doc_id}]"),
                    )
                    for doc_id, score in raw_results.items()
                ]
                scored.sort(key=lambda item: (-item[1], item[0]))
                entries = [
                    RankedDocument(doc_id=doc_id, rank=rank, score=score)
                    for rank, (doc_id, score) in enumerate(scored, start=1)
                ]
            else:
                result_list = _array(raw_results, f"run[{query_id}]")
                for rank, raw_entry in enumerate(result_list, start=1):
                    if isinstance(raw_entry, str):
                        entries.append(
                            RankedDocument(
                                doc_id=_identifier(raw_entry, "run doc id"),
                                rank=rank,
                                score=-rank,
                            )
                        )
                    else:
                        entry = dict(_object(raw_entry, f"run[{query_id}][{rank}]"))
                        entry.setdefault("query_id", query_id)
                        parsed_query_id, parsed = _run_record(
                            entry,
                            f"run[{query_id}][{rank}]",
                            default_rank=rank,
                        )
                        _require(parsed_query_id == query_id, "nested run query id mismatch")
                        entries.append(parsed)
            grouped[query_id] = entries
    else:
        for index, raw_record in enumerate(_array(raw, "run")):
            query_id, entry = _run_record(_object(raw_record, f"run[{index}]"), f"run[{index}]")
            grouped.setdefault(query_id, []).append(entry)

    _require(bool(grouped), "run must declare at least one query")
    normalized: dict[str, tuple[RankedDocument, ...]] = {}
    for query_id, entries in grouped.items():
        doc_ids = [entry.doc_id for entry in entries]
        _require(len(doc_ids) == len(set(doc_ids)), f"run[{query_id}] has duplicate documents")
        if not entries:
            normalized[query_id] = ()
            continue
        entries.sort(key=lambda item: (-item.score, item.doc_id))
        _require(
            [entry.rank for entry in entries] == list(range(1, len(entries) + 1)),
            f"run[{query_id}] ranks must match descending score and ascending doc_id ties",
        )
        normalized[query_id] = tuple(entries)
    return normalized


def _normalize_qrels(raw: object) -> dict[str, dict[str, int]]:
    grouped: dict[str, dict[str, int]] = {}
    if isinstance(raw, dict):
        records: list[object] = []
        for query_id, raw_judgements in raw.items():
            if isinstance(raw_judgements, dict):
                records.extend(
                    {
                        "query_id": query_id,
                        "doc_id": doc_id,
                        "relevance": relevance,
                    }
                    for doc_id, relevance in raw_judgements.items()
                )
            else:
                records.extend(
                    {"query_id": query_id, "doc_id": doc_id, "relevance": 1}
                    for doc_id in _array(raw_judgements, f"qrels[{query_id}]")
                )
    else:
        records = _array(raw, "qrels")
    _require(bool(records), "qrels must not be empty")
    for index, raw_record in enumerate(records):
        record = _object(raw_record, f"qrels[{index}]")
        query_key = _one_alias(record, ("query_id", "qid"), f"qrels[{index}]")
        doc_key = _one_alias(record, ("doc_id", "docid", "_id", "id"), f"qrels[{index}]")
        rel_key = _one_alias(record, ("relevance", "rel", "score"), f"qrels[{index}]")
        _require(
            record.keys() <= {query_key, doc_key, rel_key},
            f"qrels[{index}] has unsupported fields",
        )
        query_id = _identifier(record[query_key], f"qrels[{index}].{query_key}")
        doc_id = _identifier(record[doc_key], f"qrels[{index}].{doc_key}")
        relevance = record[rel_key]
        _require(
            isinstance(relevance, int) and not isinstance(relevance, bool) and relevance >= 0,
            f"qrels[{index}].{rel_key} must be a non-negative integer",
        )
        query_qrels = grouped.setdefault(query_id, {})
        _require(doc_id not in query_qrels, f"duplicate qrel: {query_id}/{doc_id}")
        query_qrels[doc_id] = relevance
    return grouped


def _validate_collections(
    queries: Mapping[str, str],
    corpus: Mapping[str, tuple[str, str]],
    run: Mapping[str, tuple[RankedDocument, ...]],
    qrels: Mapping[str, Mapping[str, int]],
) -> None:
    query_ids = set(queries)
    _require(set(run) == query_ids, "run query coverage must exactly match queries")
    _require(set(qrels) == query_ids, "qrels query coverage must exactly match queries")
    corpus_ids = set(corpus)
    for query_id in sorted(query_ids):
        positive = {doc_id for doc_id, relevance in qrels[query_id].items() if relevance > 0}
        _require(bool(positive), f"qrels[{query_id}] has no relevant document")
        _require(
            set(qrels[query_id]) <= corpus_ids,
            f"qrels[{query_id}] references a document outside the corpus",
        )
        _require(
            {entry.doc_id for entry in run[query_id]} <= corpus_ids,
            f"run[{query_id}] references a document outside the corpus",
        )


def _dcg(relevances: Sequence[int]) -> float:
    return sum(
        relevance / math.log2(rank + 1) for rank, relevance in enumerate(relevances, start=1)
    )


def _compute_normalized_metrics(
    run: Mapping[str, tuple[RankedDocument, ...]],
    qrels: Mapping[str, Mapping[str, int]],
) -> dict[str, float]:
    _require(set(run) == set(qrels), "run/qrels query coverage mismatch")
    query_ids = sorted(qrels)
    recalls: dict[int, list[float]] = {cutoff: [] for cutoff in RECALL_CUTOFFS}
    ndcgs: dict[int, list[float]] = {cutoff: [] for cutoff in NDCG_CUTOFFS}
    for query_id in query_ids:
        judgements = qrels[query_id]
        relevant = {doc_id for doc_id, relevance in judgements.items() if relevance > 0}
        _require(bool(relevant), f"qrels[{query_id}] has no relevant document")
        ranked_ids = [entry.doc_id for entry in run[query_id]]
        for cutoff in RECALL_CUTOFFS:
            hits = len(relevant.intersection(ranked_ids[:cutoff]))
            recalls[cutoff].append(hits / len(relevant))
        for cutoff in NDCG_CUTOFFS:
            retrieved_relevance = [judgements.get(doc_id, 0) for doc_id in ranked_ids[:cutoff]]
            ideal_relevance = sorted(judgements.values(), reverse=True)[:cutoff]
            ideal = _dcg(ideal_relevance)
            _require(ideal > 0, f"qrels[{query_id}] has zero ideal DCG")
            ndcgs[cutoff].append(_dcg(retrieved_relevance) / ideal)

    def mean(values: Sequence[float]) -> float:
        return round(math.fsum(values) / len(values), 12)

    return {
        **{f"recall_at_{cutoff}": mean(recalls[cutoff]) for cutoff in RECALL_CUTOFFS},
        **{f"ndcg_at_{cutoff}": mean(ndcgs[cutoff]) for cutoff in NDCG_CUTOFFS},
    }


def compute_retrieval_metrics(
    run: object,
    qrels: object,
) -> dict[str, float]:
    """Return deterministic macro Recall@5/10/20/100/1000 and nDCG@5/10/20.

    ``run`` may be a TREC-like list of records, a query-to-ranked-list
    mapping, or BRIGHT's query-to-document-score mapping. ``qrels`` may be a
    list of records or a query-to-document-relevance mapping.
    """

    normalized_qrels = _normalize_qrels(qrels)
    normalized_run = _normalize_run(run)
    return _compute_normalized_metrics(normalized_run, normalized_qrels)


def _evaluated_result(
    benchmark_id: str,
    queries: Mapping[str, str],
    corpus: Mapping[str, tuple[str, str]],
    run: Mapping[str, tuple[RankedDocument, ...]],
    qrels: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA,
        "benchmark_id": benchmark_id,
        "evaluation_scope": "integration_conformance_synthetic",
        "evaluation_status": "evaluated",
        "real_external_score": False,
        "external_quality_claim_allowed": False,
        "aggregate_only": True,
        "counts": {
            "queries": len(queries),
            "corpus_documents": len(corpus),
            "run_entries": sum(len(entries) for entries in run.values()),
            "positive_qrels": sum(
                relevance > 0 for judgements in qrels.values() for relevance in judgements.values()
            ),
        },
        "metrics": _compute_normalized_metrics(run, qrels),
    }


def _not_evaluated_result(
    benchmark_id: str | None,
    reason_code: str,
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA,
        "benchmark_id": benchmark_id,
        "evaluation_scope": "real_external_fixed_corpus",
        "evaluation_status": "not_evaluated",
        "reason_code": reason_code,
        "real_external_score": False,
        "external_quality_claim_allowed": False,
        "aggregate_only": True,
        "counts": None,
        "metrics": None,
    }


def evaluate_compact_case(
    case: object,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one self-contained synthetic conformance case."""

    locked_registry = validate_registry(registry) if registry is not None else load_registry()
    payload = _object(case, "compact case")
    _exact_keys(
        payload,
        {"suite_manifest", "queries", "corpus", "run", "qrels"},
        "compact case",
        optional={"expected_metrics"},
    )
    suite, _entry = _validate_suite_manifest(
        payload["suite_manifest"],
        locked_registry,
        expected_origin=SYNTHETIC_ORIGIN,
    )
    queries = _normalize_queries(payload["queries"])
    corpus = _normalize_corpus(payload["corpus"])
    run = _normalize_run(payload["run"])
    qrels = _normalize_qrels(payload["qrels"])
    _validate_collections(queries, corpus, run, qrels)
    return _evaluated_result(suite["benchmark_id"], queries, corpus, run, qrels)


def evaluate_fixture_file(
    path: Path = DEFAULT_FIXTURES_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    """Evaluate all committed synthetic adapters and return aggregate-only data."""

    registry = load_registry(registry_path)
    fixture = _object(_load_json(path, "fixture"), "fixture")
    _exact_keys(
        fixture,
        {
            "schema_version",
            "fixture_scope",
            "contains_official_benchmark_content",
            "real_external_scores",
            "cases",
        },
        "fixture",
    )
    _require(fixture["schema_version"] == FIXTURES_SCHEMA, "unsupported fixture schema")
    _require(fixture["fixture_scope"] == "synthetic-integration-conformance", "fixture scope drift")
    _require(
        fixture["contains_official_benchmark_content"] is False,
        "fixture cannot contain official benchmark content",
    )
    _require(fixture["real_external_scores"] is False, "fixture cannot claim external scores")

    results: dict[str, dict[str, Any]] = {}
    all_expected_metrics_matched = True
    cases = _array(fixture["cases"], "fixture.cases")
    _require(len(cases) == len(_PINNED_BENCHMARKS), "fixture must cover every adapter once")
    for raw_case in cases:
        case = _object(raw_case, "fixture case")
        result = evaluate_compact_case(case, registry)
        benchmark_id = result["benchmark_id"]
        _require(benchmark_id not in results, "duplicate fixture benchmark")
        expected = _object(case["expected_metrics"], "fixture expected_metrics")
        _exact_keys(
            expected,
            {
                "recall_at_5",
                "recall_at_10",
                "recall_at_20",
                "recall_at_100",
                "recall_at_1000",
                "ndcg_at_5",
                "ndcg_at_10",
                "ndcg_at_20",
            },
            "fixture expected_metrics",
        )
        all_expected_metrics_matched = (
            all_expected_metrics_matched and result["metrics"] == expected
        )
        results[benchmark_id] = result
    _require(set(results) == set(_PINNED_BENCHMARKS), "fixture adapter coverage drift")
    return {
        "schema_version": FIXTURE_RESULT_SCHEMA,
        "evaluation_scope": "integration_conformance_synthetic",
        "evaluation_status": "evaluated" if all_expected_metrics_matched else "failed",
        "real_external_scores_present": False,
        "external_quality_claim_allowed": False,
        "aggregate_only": True,
        "benchmark_count": len(results),
        "benchmarks": {key: results[key] for key in sorted(results)},
        "all_expected_metrics_matched": all_expected_metrics_matched,
    }


def _safe_asset_path(bundle_dir: Path, relative: object, role: str) -> Path:
    _require(isinstance(relative, str), f"bundle {role} path must be a string")
    candidate = Path(relative)
    _require(not candidate.is_absolute(), f"bundle {role} path must be relative")
    _require(
        candidate.parts and ".." not in candidate.parts,
        f"bundle {role} path escapes bundle",
    )
    _require(not bundle_dir.is_symlink(), "bundle directory must not be a symlink")
    resolved_bundle = bundle_dir.resolve()
    unresolved_candidate = bundle_dir / candidate
    current = bundle_dir
    for component in candidate.parts:
        current /= component
        _require(not current.is_symlink(), f"bundle {role} path contains a symlink")
    resolved_candidate = unresolved_candidate.resolve()
    _require(
        resolved_candidate.parent == resolved_bundle
        or resolved_bundle in resolved_candidate.parents,
        f"bundle {role} path escapes bundle",
    )
    return unresolved_candidate


def _require_regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ConformanceError(f"cannot inspect {label}: {path.name}") from exc
    _require(stat.S_ISREG(mode), f"{label} must be a regular file")


def _collection_counts(
    queries: Mapping[str, str],
    corpus: Mapping[str, tuple[str, str]],
    run: Mapping[str, tuple[RankedDocument, ...]],
    qrels: Mapping[str, Mapping[str, int]],
) -> dict[str, int]:
    return {
        "queries": len(queries),
        "corpus_documents": len(corpus),
        "run_queries": len(run),
        "run_entries": sum(len(entries) for entries in run.values()),
        "qrel_queries": len(qrels),
        "qrel_entries": sum(len(entries) for entries in qrels.values()),
        "positive_qrels": sum(
            relevance > 0 for entries in qrels.values() for relevance in entries.values()
        ),
    }


def _validate_expected_counts(value: object) -> dict[str, int]:
    counts = _object(value, "bundle counts")
    _exact_keys(counts, set(_EXPECTED_COUNT_KEYS), "bundle counts")
    normalized = {
        key: _non_negative_integer(counts[key], f"bundle counts.{key}")
        for key in sorted(_EXPECTED_COUNT_KEYS)
    }
    _require(normalized["queries"] > 0, "bundle query count must be positive")
    _require(
        normalized["corpus_documents"] > 0,
        "bundle corpus document count must be positive",
    )
    _require(normalized["qrel_queries"] > 0, "bundle qrel query count must be positive")
    for key, limit in _COUNT_CAPS.items():
        _require(normalized[key] <= limit, f"bundle counts.{key} exceeds policy cap")
    return normalized


def _parse_jsonl(content: bytes, label: str, source_name: str) -> list[Any]:
    records: list[Any] = []
    lines = _decode_utf8(content, label, source_name).splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ConformanceError(f"invalid {label} JSONL at line {line_number}") from exc
    _require(bool(records), f"{label} JSONL is empty")
    return records


def _parse_queries_tsv(content: bytes, source_name: str) -> list[dict[str, str]]:
    lines = _decode_utf8(content, "queries TSV", source_name).splitlines()
    records: list[dict[str, str]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        fields = line.split("\t")
        _require(len(fields) == 2, f"queries TSV line {line_number} must have two fields")
        if line_number == 1 and fields[0].casefold() in {"query_id", "qid", "id"}:
            _require(fields[1].casefold() in {"text", "query"}, "unsupported queries TSV header")
            continue
        records.append({"query_id": fields[0], "text": fields[1]})
    _require(bool(records), "queries TSV is empty")
    return records


def _parse_trec_run(content: bytes, source_name: str) -> list[dict[str, Any]]:
    lines = _decode_utf8(content, "TREC run", source_name).splitlines()
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        fields = line.split()
        _require(len(fields) == 6, f"TREC run line {line_number} must have six fields")
        query_id, q0, doc_id, raw_rank, raw_score, system = fields
        _require(
            q0 == TREC_QRELS_ITERATION,
            f"TREC run line {line_number} iteration must be {TREC_QRELS_ITERATION}",
        )
        try:
            rank = int(raw_rank)
            score = float(raw_score)
        except ValueError as exc:
            raise ConformanceError(f"TREC run line {line_number} has invalid numbers") from exc
        records.append(
            {
                "query_id": query_id,
                "doc_id": doc_id,
                "rank": rank,
                "score": score,
                "system": system,
            }
        )
    _require(bool(records), "TREC run is empty")
    return records


def _parse_trec_qrels(content: bytes, source_name: str) -> list[dict[str, Any]]:
    lines = _decode_utf8(content, "TREC qrels", source_name).splitlines()
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        fields = line.split()
        _require(len(fields) == 4, f"TREC qrels line {line_number} must have four fields")
        query_id, iteration, doc_id, raw_relevance = fields
        _require(
            iteration == TREC_QRELS_ITERATION,
            f"TREC qrels line {line_number} iteration must be {TREC_QRELS_ITERATION}",
        )
        try:
            relevance = int(raw_relevance)
        except ValueError as exc:
            raise ConformanceError(f"TREC qrels line {line_number} has invalid relevance") from exc
        records.append({"query_id": query_id, "doc_id": doc_id, "relevance": relevance})
    _require(bool(records), "TREC qrels are empty")
    return records


def _parse_bundle_asset(
    content: bytes,
    source_name: str,
    role: str,
    file_format: str,
) -> object:
    if file_format == "json":
        return _parse_json_bytes(content, f"bundle {role}", source_name)
    if file_format == "jsonl":
        return _parse_jsonl(content, f"bundle {role}", source_name)
    if role == "queries" and file_format == "tsv":
        return _parse_queries_tsv(content, source_name)
    if role == "run" and file_format == "trec":
        return _parse_trec_run(content, source_name)
    if role == "qrels" and file_format == "trec":
        return _parse_trec_qrels(content, source_name)
    raise ConformanceError(f"unsupported {role} format: {file_format}")


def evaluate_local_bundle(
    bundle_dir: Path,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    *,
    benchmark_id: str | None = None,
) -> dict[str, Any]:
    """Inspect and evaluate a checksummed local bundle when its license permits.

    A missing bundle is an expected ``not_evaluated`` outcome. Invalid present
    metadata raises ``ConformanceError``. Synthetic bundles exercise the local
    file adapters. With the v1 registry, an otherwise valid official bundle is
    ``not_evaluated`` because the asset licenses remain unresolved; no official
    asset file is opened in that state.
    """

    registry = load_registry(registry_path)
    manifest_path = bundle_dir / BUNDLE_MANIFEST_NAME
    if not manifest_path.exists() and not manifest_path.is_symlink():
        return _not_evaluated_result(benchmark_id, "local_bundle_manifest_missing")
    _require(not bundle_dir.is_symlink(), "bundle directory must not be a symlink")
    _require(not manifest_path.is_symlink(), "bundle manifest must not be a symlink")
    _require_regular_file(manifest_path, "bundle manifest")

    manifest = _object(_load_json(manifest_path, "bundle manifest"), "bundle manifest")
    _exact_keys(
        manifest,
        {"schema_version", "suite_manifest", "policy_id", "counts", "files"},
        "bundle manifest",
    )
    _require(manifest["schema_version"] == BUNDLE_SCHEMA, "unsupported bundle schema")
    _require(
        manifest["policy_id"] == SYNTHETIC_BUNDLE_POLICY_ID,
        "unsupported bundle policy",
    )
    expected_counts = _validate_expected_counts(manifest["counts"])
    suite = _object(manifest["suite_manifest"], "bundle suite_manifest")
    declared_id = _identifier(suite.get("benchmark_id"), "bundle benchmark_id")
    if benchmark_id is not None:
        _require(declared_id == benchmark_id, "requested benchmark does not match bundle")

    try:
        validated_suite, _entry = _validate_suite_manifest(
            suite,
            registry,
        )
    except _OfficialEvaluationBlockedError:
        return _not_evaluated_result(
            declared_id,
            "official_evaluation_not_supported_in_v1",
        )

    files = _object(manifest["files"], "bundle files")
    _exact_keys(files, set(_SUPPORTED_FORMATS), "bundle files")
    loaded: dict[str, object] = {}
    seen_asset_paths: set[Path] = set()
    for role, raw_descriptor in files.items():
        descriptor = _object(raw_descriptor, f"bundle files.{role}")
        _exact_keys(
            descriptor,
            {"path", "format", "sha256", "byte_length"},
            f"bundle files.{role}",
        )
        file_format = descriptor["format"]
        _require(
            isinstance(file_format, str) and file_format in _SUPPORTED_FORMATS[role],
            f"unsupported bundle {role} format",
        )
        _require(_is_lower_hex(descriptor["sha256"], 64), f"bundle {role} SHA-256 is invalid")
        declared_byte_length = _non_negative_integer(
            descriptor["byte_length"],
            f"bundle {role} byte_length",
        )
        _require(
            declared_byte_length <= _ROLE_MAX_BYTES[role],
            f"bundle {role} byte_length exceeds policy cap",
        )
        asset_path = _safe_asset_path(bundle_dir, descriptor["path"], role)
        _require(
            asset_path != manifest_path,
            f"bundle {role} cannot reuse the bundle manifest",
        )
        _require(asset_path not in seen_asset_paths, "bundle roles must use distinct files")
        seen_asset_paths.add(asset_path)
        if not asset_path.exists() and not asset_path.is_symlink():
            return _not_evaluated_result(
                validated_suite["benchmark_id"],
                f"local_{role}_asset_missing",
            )
        _require_regular_file(asset_path, f"bundle {role} asset")
        content, digest, actual_byte_length = _read_file_once(
            asset_path,
            max_bytes=_ROLE_MAX_BYTES[role],
        )
        _require(
            actual_byte_length == declared_byte_length,
            f"bundle {role} byte_length mismatch",
        )
        _require(digest == descriptor["sha256"], f"bundle {role} checksum mismatch")
        loaded[role] = _parse_bundle_asset(
            content,
            asset_path.name,
            role,
            file_format,
        )

    queries = _normalize_queries(loaded["queries"])
    corpus = _normalize_corpus(loaded["corpus"])
    run = _normalize_run(loaded["run"])
    qrels = _normalize_qrels(loaded["qrels"])
    _validate_collections(queries, corpus, run, qrels)
    actual_counts = _collection_counts(queries, corpus, run, qrels)
    _require(actual_counts == expected_counts, "bundle declared counts do not match content")
    return _evaluated_result(
        validated_suite["benchmark_id"],
        queries,
        corpus,
        run,
        qrels,
    )


__all__ = [
    "BUNDLE_MANIFEST_NAME",
    "DEFAULT_FIXTURES_PATH",
    "DEFAULT_REGISTRY_PATH",
    "ConformanceError",
    "RankedDocument",
    "compute_retrieval_metrics",
    "evaluate_compact_case",
    "evaluate_fixture_file",
    "evaluate_local_bundle",
    "load_registry",
    "validate_registry",
]
