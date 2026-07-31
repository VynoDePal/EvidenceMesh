#!/usr/bin/env python3
"""Run the zero-traffic Phase 11.8.9 offline retrieval-recovery lock."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

BASELINE_FAMILY = ""
CANDIDATE_FAMILY = ""
CANDIDATE_PROJECTION_FAMILY = ""
CONTROL_PROJECTION_FAMILY = ""
OMISSION_SEPARATOR = ""
ProjectedEvidence: Any = None
ProjectionMetrics: Any = None
ProjectionOutcome: Any = None
RawResult: Any = None
SelectionOutcome: Any = None
candidate_project_blocks_v2: Any = None
canonical_funnel_json: Any = None
canonical_projection_json: Any = None
evaluate_fixture_file: Any = None
freeze_metadata: Any = None
fuse_results: Any = None
load_registry: Any = None
project_selected_v3: Any = None
rendered_control_projection_chars: Any = None
rendered_projection_chars: Any = None
select_baseline: Any = None
select_candidate_v3: Any = None
validate_registry: Any = None

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-9-offline-retrieval-recovery-v1"
SCHEMA_VERSION = "phase11.8.9-offline-retrieval-recovery-v1"
SOURCE_LOCK_MANIFEST_PATH = "benchmarks/data/phase11_8_9_source_locks_v1.json"
RETRIEVAL_FIXTURE_PATH = "benchmarks/data/phase11_8_9_retrieval_fixtures_v1.json"
EXTERNAL_REGISTRY_PATH = "benchmarks/data/phase11_8_9_external_benchmarks_v1.json"
EXTERNAL_FIXTURE_PATH = "benchmarks/data/phase11_8_9_external_eval_fixtures_v1.json"
HISTORICAL_RESULT_PATH = (
    "benchmarks/results/phase11_8_8_live_projection_calibration_2026-07-30.json"
)

EXPECTED_HISTORICAL_RESULT_SHA256 = (
    "03e0ad7ef2d4859848c3b4d4d8bf9d25714b9d311741f15a91ec9b3311aca25f"
)
EXPECTED_HISTORICAL_MANIFEST_SHA256 = (
    "da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e"
)
EXPECTED_V24_PROTOCOL_SHA256 = "e63ab4b3f25865890458abd2a001ce3428f9a3ca8c4f1a1a166f25432d1a8dc9"
EXPECTED_V2_PROJECTOR_SHA256 = "117968687a0c0c150acef42f997967d10b04006d14ed0efa9de87c9c08b1909e"
EXPECTED_FIXTURE_CASES = 5
EXPECTED_EXTERNAL_SUITES = ("bright", "browsecomp_plus")
EXPECTED_GATE_COUNT = 19
LOCK_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SOURCE_SET_DOMAIN = b"EvidenceMesh/phase11.8.9/source-set/v1\0"
MAX_SELECTED_DOCUMENTS = 20
PROJECTION_BUDGET_CHARS = 12_000
MAX_DOCUMENT_CHARS = 1_800
MIN_DOCUMENT_CHARS = 96
EXPECTED_AUTHORITY_PATHS = frozenset(
    {
        ".github/workflows/phase11-8-9-offline-retrieval-recovery.yml",
        "benchmarks/data/phase11_7_fresh_confirmation_v1.json",
        "benchmarks/data/phase11_8_9_external_benchmarks_v1.json",
        "benchmarks/data/phase11_8_9_external_eval_fixtures_v1.json",
        "benchmarks/data/phase11_8_9_retrieval_fixtures_v1.json",
        "benchmarks/phase11_8_8_projection_candidate.py",
        "benchmarks/phase11_8_9_external_eval.py",
        "benchmarks/phase11_8_9_retrieval_candidate.py",
        "benchmarks/results/phase11_8_8_live_projection_calibration_2026-07-30.json",
        "benchmarks/run_phase11_8_9_offline_retrieval_recovery.py",
        "docs/benchmark-protocol-v24.md",
        "docs/benchmark-protocol-v25.md",
        "pyproject.toml",
        "tests/test_phase11_8_9_external_eval.py",
        "tests/test_phase11_8_9_offline_retrieval_recovery.py",
        "tests/test_phase11_8_9_retrieval_candidate.py",
        "uv.lock",
    }
)
EXECUTABLE_SOURCE_PATHS = frozenset(
    {
        "benchmarks/phase11_8_8_projection_candidate.py",
        "benchmarks/phase11_8_9_external_eval.py",
        "benchmarks/phase11_8_9_retrieval_candidate.py",
        "benchmarks/run_phase11_8_9_offline_retrieval_recovery.py",
    }
)
IMPORT_ALLOWLIST = {
    "benchmarks/phase11_8_8_projection_candidate.py": frozenset(
        {
            "__future__",
            "dataclasses",
            "itertools",
            "re",
            "typing",
        }
    ),
    "benchmarks/phase11_8_9_external_eval.py": frozenset(
        {
            "__future__",
            "collections.abc",
            "dataclasses",
            "hashlib",
            "json",
            "math",
            "os",
            "pathlib",
            "stat",
            "typing",
        }
    ),
    "benchmarks/phase11_8_9_retrieval_candidate.py": frozenset(
        {
            "__future__",
            "collections",
            "dataclasses",
            "hashlib",
            "itertools",
            "json",
            "re",
            "typing",
            "unicodedata",
            "urllib.parse",
        }
    ),
    "benchmarks/run_phase11_8_9_offline_retrieval_recovery.py": frozenset(
        {
            "__future__",
            "argparse",
            "ast",
            "dataclasses",
            "hashlib",
            "json",
            "os",
            "pathlib",
            "re",
            "subprocess",
            "sys",
            "tempfile",
            "types",
            "typing",
            "xml.etree.ElementTree",
        }
    ),
}
FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "aiohttp",
        "asyncio",
        "boto3",
        "google",
        "httpx",
        "importlib",
        "mistralai",
        "openai",
        "os",
        "requests",
        "socket",
        "subprocess",
        "tavily",
        "urllib.request",
    }
)
FORBIDDEN_DYNAMIC_CALLS = frozenset(
    {
        "__import__",
        "compile",
        "eval",
        "exec",
        "getenv",
        "popen",
        "system",
        "urlopen",
    }
)
LOCAL_GATE_NUMBERS = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 18, 19})
EXTERNAL_GATE_NUMBERS = frozenset({10, 11, 13, 14, 15, 16, 17})
PRODUCT_MUTATION_PREFIXES = (
    "src/",
    "evidencemesh/",
    "packages/",
)
PRODUCT_DEFAULT_PATHS = frozenset(
    {
        "README.md",
        "src/evidencemesh/config.py",
        "src/evidencemesh/settings.py",
    }
)
RELEASE_MUTATION_PREFIXES = (
    ".github/workflows/release",
    "CHANGELOG",
    "releases/",
)
EXPECTED_CONFORMANCE_REQUIREMENT_IDS = frozenset(
    {
        "acronym_anchor",
        "aggregate_serialization_deterministic",
        "answer_qrel_blind",
        "archive_or_path_traversal_rejection",
        "binary_and_graded_relevance",
        "canonical_multi_provider_duplicate",
        "citation_ids_unique",
        "cold_process_replay",
        "cold_replays_two_plus",
        "date_anchor",
        "deterministic_fusion_tie",
        "deterministic_tie",
        "domain_diversity_tie",
        "duplicate_citation_rejected",
        "eligibility_exclusions",
        "empty_input",
        "environment_secret_zero_access",
        "exact_match",
        "external_metric_oracles",
        "forbidden_scorer_fields",
        "long_content",
        "malformed_content",
        "missing_qrels_policy",
        "network_zero_access",
        "no_io_network_env_process",
        "no_relevant_document_policy",
        "number_anchor",
        "official_assets_fail_closed",
        "phase12_zero_access",
        "phrase_match",
        "projection_budget_12000",
        "projection_head_middle_tail",
        "projection_insufficient_budget",
        "provider_diversity_tie",
        "rare_token_anchor",
        "selection_invalid_limits",
        "selection_limit_one",
        "selection_limit_twenty",
        "short_content",
        "source_preservation",
        "source_type_diversity_tie",
        "unicode_punctuation",
        "unit_anchor",
    }
)
LOCKED_MODULE_PATHS = {
    "_evidencemesh_phase11_8_8_projection_candidate_locked": (
        "benchmarks/phase11_8_8_projection_candidate.py"
    ),
    "_evidencemesh_phase11_8_9_external_eval_locked": ("benchmarks/phase11_8_9_external_eval.py"),
    "_evidencemesh_phase11_8_9_retrieval_candidate_locked": (
        "benchmarks/phase11_8_9_retrieval_candidate.py"
    ),
}
BOUND_SECRET_NAMES = (
    "EVIDENCE_MESH_GEMINI_KEY",
    "EVIDENCE_MESH_TAVILY_KEY",
)
RUNNER_RECEIPT_TEST_NODE_IDS = (
    (
        "tests/test_phase11_8_9_offline_retrieval_recovery.py"
        "::test_source_lock_manifest_is_complete_and_has_no_placeholders"
    ),
    ("tests/test_phase11_8_9_offline_retrieval_recovery.py::test_source_lock_paths_fail_closed"),
    (
        "tests/test_phase11_8_9_offline_retrieval_recovery.py"
        "::test_repository_reader_rejects_symlink"
    ),
    (
        "tests/test_phase11_8_9_offline_retrieval_recovery.py"
        "::test_locked_module_executes_preflight_bytes_despite_source_and_pyc_swap"
    ),
    (
        "tests/test_phase11_8_9_offline_retrieval_recovery.py"
        "::test_isolated_pytest_prefix_ignores_cwd_pytest_shadow"
    ),
    (
        "tests/test_phase11_8_9_offline_retrieval_recovery.py"
        "::test_workflow_is_read_only_local_and_secret_free"
    ),
    (
        "tests/test_phase11_8_9_offline_retrieval_recovery.py"
        "::test_secret_presence_probe_counts_names_without_reading_values"
    ),
    (
        "tests/test_phase11_8_9_offline_retrieval_recovery.py"
        "::test_duplicate_citation_or_empty_text_is_rejected_directly"
    ),
)
_LOCKED_RUNTIME_SOURCE_SET_SHA256: str | None = None
_CONFORMANCE_RECEIPT_CACHE: dict[str, dict[str, int | str]] = {}
CONFORMANCE_PYTEST_PREFIX = ("-I", "-m", "pytest")

ZERO_TRAFFIC = {
    "bound_secrets": 0,
    "cache_reads_from_live_search": 0,
    "cache_writes_to_live_search": 0,
    "evaluation_network_requests": 0,
    "fallbacks": 0,
    "follow_up_document_fetches": 0,
    "gemini_requests": 0,
    "local_model_inference_calls": 0,
    "model_requests": 0,
    "other_search_provider_requests": 0,
    "repairs": 0,
    "retries": 0,
    "tavily_requests": 0,
    "token_count_api_requests": 0,
}


def _bound_secret_count(environment: object) -> int:
    """Count only secret-name presence without reading or serializing values."""

    return sum(name in environment for name in BOUND_SECRET_NAMES)  # type: ignore[operator]


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 digest for ``value``."""

    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(payload: object) -> bytes:
    """Serialize a canonical, deterministic public result."""

    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ValueError(category)


def _safe_relative_path(value: object) -> str:
    _require(isinstance(value, str) and bool(value), "invalid_source_lock_path")
    path = PurePosixPath(value)
    lowered = value.casefold().replace("-", "_")
    _require(
        not path.is_absolute()
        and value == path.as_posix()
        and "\\" not in value
        and "\x00" not in value
        and "." not in path.parts
        and ".." not in path.parts
        and "phase12" not in lowered
        and "phase_12" not in lowered,
        "forbidden_source_lock_path",
    )
    return value


def _repository_file(
    relative_path: str,
    *,
    accessed_paths: set[str] | None = None,
) -> Path:
    safe_path = _safe_relative_path(relative_path)
    root = REPOSITORY_ROOT.resolve(strict=True)
    unresolved = root / safe_path
    current = root
    for part in PurePosixPath(safe_path).parts:
        current = current / part
        _require(not current.is_symlink(), "repository_source_symlink_forbidden")
    try:
        resolved = unresolved.resolve(strict=True)
    except OSError as exc:
        raise ValueError("repository_source_missing") from exc
    _require(
        resolved.is_relative_to(root) and resolved.is_file(),
        "repository_source_path_escape",
    )
    if accessed_paths is not None:
        accessed_paths.add(safe_path)
    return resolved


def _read_repository_file(
    relative_path: str,
    *,
    accessed_paths: set[str] | None = None,
) -> bytes:
    return _repository_file(relative_path, accessed_paths=accessed_paths).read_bytes()


def source_set_sha256(source_bytes: dict[str, bytes]) -> str:
    """Hash a length-framed, path-sorted set of exact authority bytes."""

    digest = hashlib.sha256()
    digest.update(SOURCE_SET_DOMAIN)
    for relative_path in sorted(source_bytes):
        path_bytes = relative_path.encode("utf-8")
        raw = source_bytes[relative_path]
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _load_source_locks(
    accessed_paths: set[str],
) -> tuple[dict[str, bytes], bytes, list[dict[str, str]], dict[str, Any]]:
    manifest_raw = _read_repository_file(
        SOURCE_LOCK_MANIFEST_PATH,
        accessed_paths=accessed_paths,
    )
    manifest = json.loads(manifest_raw)
    _require(
        isinstance(manifest, dict)
        and set(manifest)
        == {
            "authority_sources",
            "historical_locks",
            "schema_version",
            "source_set_sha256",
        },
        "invalid_source_lock_manifest",
    )
    _require(
        manifest.get("schema_version") == "evidencemesh.phase11_8_9.source-locks.v1",
        "invalid_source_lock_schema",
    )
    authorities = manifest.get("authority_sources")
    _require(
        isinstance(authorities, list) and bool(authorities),
        "missing_authority_source_locks",
    )

    source_bytes: dict[str, bytes] = {}
    source_locks: list[dict[str, str]] = []
    observed_paths: set[str] = set()
    for entry in authorities:
        _require(
            isinstance(entry, dict) and set(entry) == {"relative_path", "sha256"},
            "invalid_authority_source_lock",
        )
        relative_path = _safe_relative_path(entry["relative_path"])
        expected_sha256 = entry["sha256"]
        _require(
            isinstance(expected_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "unresolved_authority_source_lock",
        )
        _require(relative_path not in observed_paths, "duplicate_authority_source_lock")
        raw = _read_repository_file(relative_path, accessed_paths=accessed_paths)
        _require(
            sha256_bytes(raw) == expected_sha256,
            "authority_source_lock_mismatch",
        )
        observed_paths.add(relative_path)
        source_bytes[relative_path] = raw
        source_locks.append({"relative_path": relative_path, "sha256": expected_sha256})
    _require(
        observed_paths == EXPECTED_AUTHORITY_PATHS,
        "authority_source_lock_set_mismatch",
    )

    historical = manifest.get("historical_locks")
    _require(isinstance(historical, dict), "missing_historical_source_locks")
    _require(
        historical
        == {
            "phase11_7_observed_manifest_sha256": (EXPECTED_HISTORICAL_MANIFEST_SHA256),
            "phase11_8_8_live_result_sha256": (EXPECTED_HISTORICAL_RESULT_SHA256),
            "phase11_8_8_projector_sha256": EXPECTED_V2_PROJECTOR_SHA256,
            "phase11_8_8_protocol_sha256": EXPECTED_V24_PROTOCOL_SHA256,
        },
        "historical_source_lock_changed",
    )
    computed_source_set_sha256 = source_set_sha256(source_bytes)
    declared_source_set_sha256 = manifest.get("source_set_sha256")
    _require(
        isinstance(declared_source_set_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", declared_source_set_sha256) is not None,
        "invalid_declared_source_set_sha256",
    )
    _require(
        computed_source_set_sha256 == declared_source_set_sha256,
        "source_set_sha256_mismatch",
    )
    source_locks.append(
        {
            "relative_path": SOURCE_LOCK_MANIFEST_PATH,
            "sha256": sha256_bytes(manifest_raw),
        }
    )
    source_locks.sort(key=lambda item: item["relative_path"])
    source_integrity = {
        "authority_file_count": len(source_bytes),
        "computed_source_set_sha256": computed_source_set_sha256,
        "declared_source_set_sha256": declared_source_set_sha256,
        "manifest_sha256": sha256_bytes(manifest_raw),
        "matched_authority_hash_count": len(source_bytes),
        "source_set_byte_authority": True,
    }
    return source_bytes, manifest_raw, source_locks, source_integrity


def _load_exact_locked_module(
    module_name: str,
    relative_path: str,
    source_bytes: dict[str, bytes],
) -> ModuleType:
    expected_raw = source_bytes.get(relative_path)
    _require(expected_raw is not None, "locked_module_source_missing")
    safe_path = _safe_relative_path(relative_path)
    origin = str(REPOSITORY_ROOT.joinpath(*PurePosixPath(safe_path).parts))
    module = ModuleType(module_name)
    module.__file__ = origin
    module.__loader__ = None
    module.__package__ = module_name.rpartition(".")[0]
    module.__spec__ = None
    module.__cached__ = None
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        code = compile(
            expected_raw,
            origin,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(code, module.__dict__)  # noqa: S102 - executes exact hash-locked bytes
    except BaseException:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise
    _require(
        module.__file__ == origin
        and module.__loader__ is None
        and module.__package__ == module_name.rpartition(".")[0]
        and module.__spec__ is None
        and module.__cached__ is None,
        "locked_module_origin_mismatch",
    )
    return module


def _bind_locked_runtime(
    source_bytes: dict[str, bytes],
    locked_source_set_sha256: str,
) -> dict[str, int | bool]:
    global _LOCKED_RUNTIME_SOURCE_SET_SHA256
    if (
        locked_source_set_sha256 == _LOCKED_RUNTIME_SOURCE_SET_SHA256
        and "select_candidate_v3" in globals()
        and "evaluate_fixture_file" in globals()
        and "candidate_project_blocks_v2" in globals()
    ):
        return {
            "locked_module_count": len(LOCKED_MODULE_PATHS),
            "locked_module_origin_hash_passed": True,
        }

    modules = {
        module_name: _load_exact_locked_module(
            module_name,
            relative_path,
            source_bytes,
        )
        for module_name, relative_path in LOCKED_MODULE_PATHS.items()
    }
    control = modules["_evidencemesh_phase11_8_8_projection_candidate_locked"]
    external = modules["_evidencemesh_phase11_8_9_external_eval_locked"]
    candidate = modules["_evidencemesh_phase11_8_9_retrieval_candidate_locked"]
    bindings = {
        "BASELINE_FAMILY": candidate.BASELINE_FAMILY,
        "CANDIDATE_FAMILY": candidate.CANDIDATE_FAMILY,
        "CANDIDATE_PROJECTION_FAMILY": candidate.PROJECTION_FAMILY,
        "CONTROL_PROJECTION_FAMILY": control.PROJECTION_FAMILY,
        "OMISSION_SEPARATOR": candidate.OMISSION_SEPARATOR,
        "ProjectedEvidence": candidate.ProjectedEvidence,
        "ProjectionMetrics": candidate.ProjectionMetrics,
        "ProjectionOutcome": candidate.ProjectionOutcome,
        "RawResult": candidate.RawResult,
        "SelectionOutcome": candidate.SelectionOutcome,
        "candidate_project_blocks_v2": control.candidate_project_blocks_v2,
        "canonical_funnel_json": candidate.canonical_funnel_json,
        "canonical_projection_json": candidate.canonical_projection_json,
        "evaluate_fixture_file": external.evaluate_fixture_file,
        "freeze_metadata": candidate.freeze_metadata,
        "fuse_results": candidate.fuse_results,
        "load_registry": external.load_registry,
        "project_selected_v3": candidate.project_selected_v3,
        "rendered_control_projection_chars": control.rendered_evidence_chars,
        "rendered_projection_chars": candidate.rendered_projection_chars,
        "select_baseline": candidate.select_baseline,
        "select_candidate_v3": candidate.select_candidate_v3,
        "validate_registry": external.validate_registry,
    }
    globals().update(bindings)
    _LOCKED_RUNTIME_SOURCE_SET_SHA256 = locked_source_set_sha256
    return {
        "locked_module_count": len(modules),
        "locked_module_origin_hash_passed": True,
    }


def _historical_boundary(raw: bytes) -> dict[str, Any]:
    _require(
        sha256_bytes(raw) == EXPECTED_HISTORICAL_RESULT_SHA256,
        "historical_result_lock_mismatch",
    )
    payload = json.loads(raw)
    decision = payload.get("decision")
    projection = payload.get("projection")
    _require(
        isinstance(decision, dict) and isinstance(projection, dict),
        "invalid_historical_aggregate",
    )
    gates = decision.get("gates")
    _require(
        isinstance(gates, list)
        and len(gates) == 13
        and sum(bool(gate.get("passed")) for gate in gates) == 8,
        "historical_8_of_13_changed",
    )
    observed = {
        "diagnostic_status": decision.get("diagnostic_status"),
        "equal_cap_prompt_proxy_hits": projection.get("equal_cap_prompt_proxy_hits"),
        "gate_count": decision.get("gate_count"),
        "passed_gate_count": decision.get("passed_gate_count"),
        "release_decision": decision.get("release_decision"),
        "selected_proxy_hits": projection.get("selected_proxy_hits"),
        "v1_prompt_proxy_hits": projection.get("v1_prompt_proxy_hits"),
        "v2_prompt_proxy_hits": projection.get("v2_prompt_proxy_hits"),
        "v2_retention_denominator": projection.get("v2_retention_denominator"),
        "v2_retention_numerator": projection.get("v2_retention_numerator"),
        "v2_retention_rate": projection.get("v2_retention_rate"),
        "v2_vs_equal_net_gain": projection.get("v2_vs_equal_net_gain"),
        "v2_vs_v1_net_gain": projection.get("v2_vs_v1_net_gain"),
    }
    expected = {
        "diagnostic_status": "retrieval_limited_inconclusive",
        "equal_cap_prompt_proxy_hits": 16,
        "gate_count": 13,
        "passed_gate_count": 8,
        "release_decision": "no-go",
        "selected_proxy_hits": 18,
        "v1_prompt_proxy_hits": 17,
        "v2_prompt_proxy_hits": 17,
        "v2_retention_denominator": 18,
        "v2_retention_numerator": 17,
        "v2_retention_rate": 0.944444,
        "v2_vs_equal_net_gain": 1,
        "v2_vs_v1_net_gain": 0,
    }
    _require(observed == expected, "historical_aggregate_changed")
    return {
        **observed,
        "classification": "development_diagnostic_only",
        "quality_gate_reuse_allowed": False,
        "validation_passed": observed == expected,
    }


def _observed_development_boundary(
    manifest_raw: bytes,
    protocol_raw: bytes,
) -> dict[str, Any]:
    manifest = json.loads(manifest_raw)
    _require(isinstance(manifest, dict), "invalid_observed_manifest")
    cases = manifest.get("cases")
    selection = manifest.get("selection")
    privacy = manifest.get("privacy")
    protocol = protocol_raw.decode("utf-8")
    manifest_contract_passed = (
        isinstance(cases, list)
        and len(cases) == 24
        and isinstance(selection, dict)
        and selection.get("case_count") == 24
        and isinstance(privacy, dict)
        and privacy
        == {
            "generated_answers_committed": False,
            "questions_committed": False,
            "reference_answers_committed": False,
            "source_content_committed": False,
        }
    )
    protocol_contract_passed = all(
        phrase in protocol
        for phrase in (
            "permanently classified as `development_diagnostic_only`",
            "used for a release, merge or superiority decision",
            "No aggregate improvement on these 24 cases",
        )
    )
    return {
        "classification": "development_diagnostic_only",
        "external_confirmation_allowed": False,
        "manifest_case_count": len(cases) if isinstance(cases, list) else -1,
        "manifest_contract_passed": manifest_contract_passed,
        "protocol_contract_passed": protocol_contract_passed,
        "quality_gate_reuse_allowed": False,
    }


def _import_name(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    return (node.module or "",)


def _forbidden_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id.casefold() in FORBIDDEN_DYNAMIC_CALLS
    if isinstance(node.func, ast.Attribute):
        return node.func.attr.casefold() in {
            "getenv",
            "popen",
            "system",
            "urlopen",
        }
    return False


def _candidate_input_audit(tree: ast.AST) -> bool:
    candidate_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "select_candidate_v3"
    ]
    if len(candidate_functions) != 1:
        return False
    function = candidate_functions[0]
    arguments = {
        argument.arg
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
    }
    expected = {"limit", "max_per_domain", "query", "raw_results"}
    forbidden_identifier_fragments = (
        "answer",
        "expected",
        "gold",
        "judge",
        "oracle",
        "qrel",
        "relevance",
        "utility",
    )
    names = {node.id.casefold() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    return arguments == expected and not any(
        fragment in name for name in names for fragment in forbidden_identifier_fragments
    )


def _runner_environment_presence_only(tree: ast.AST) -> bool:
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    environment_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
        and node.attr == "environ"
    ]
    if len(environment_nodes) != 1:
        return False
    node = environment_nodes[0]
    parent = parents.get(node)
    return bool(
        (
            isinstance(parent, ast.Compare)
            and node in parent.comparators
            and any(isinstance(operator, ast.In) for operator in parent.ops)
        )
        or (
            isinstance(parent, ast.Call)
            and isinstance(parent.func, ast.Name)
            and parent.func.id == "_bound_secret_count"
            and node in parent.args
        )
    )


def _runner_exact_byte_loader_audit(
    tree: ast.AST,
) -> tuple[frozenset[ast.Call], bool]:
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_load_exact_locked_module"
    ]
    if len(functions) != 1:
        return frozenset(), False
    function = functions[0]
    dynamic_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"compile", "exec"}
    ]
    compile_calls = [
        node
        for node in dynamic_calls
        if isinstance(node.func, ast.Name) and node.func.id == "compile"
    ]
    exec_calls = [
        node for node in dynamic_calls if isinstance(node.func, ast.Name) and node.func.id == "exec"
    ]
    if len(compile_calls) != 1 or len(exec_calls) != 1:
        return frozenset(dynamic_calls), False
    compile_call = compile_calls[0]
    compile_keywords = {keyword.arg: keyword.value for keyword in compile_call.keywords}
    compile_valid = (
        len(compile_call.args) == 3
        and isinstance(compile_call.args[0], ast.Name)
        and compile_call.args[0].id == "expected_raw"
        and isinstance(compile_call.args[1], ast.Name)
        and compile_call.args[1].id == "origin"
        and isinstance(compile_call.args[2], ast.Constant)
        and compile_call.args[2].value == "exec"
        and set(compile_keywords) == {"dont_inherit", "optimize"}
        and isinstance(compile_keywords["dont_inherit"], ast.Constant)
        and compile_keywords["dont_inherit"].value is True
        and isinstance(compile_keywords["optimize"], ast.Constant)
        and compile_keywords["optimize"].value == 0
    )
    exec_call = exec_calls[0]
    exec_valid = (
        len(exec_call.args) == 2
        and not exec_call.keywords
        and isinstance(exec_call.args[0], ast.Name)
        and exec_call.args[0].id == "code"
        and isinstance(exec_call.args[1], ast.Attribute)
        and isinstance(exec_call.args[1].value, ast.Name)
        and exec_call.args[1].value.id == "module"
        and exec_call.args[1].attr == "__dict__"
    )
    forbidden_path_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and (
            (
                isinstance(node.func, ast.Name)
                and node.func.id in {"_read_repository_file", "_repository_file"}
            )
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"open", "read_bytes", "read_text", "resolve", "stat"}
            )
        )
    ]
    return (
        frozenset(dynamic_calls),
        compile_valid and exec_valid and not forbidden_path_calls,
    )


def _audit_executable_sources(source_bytes: dict[str, bytes]) -> dict[str, Any]:
    import_count = 0
    call_count = 0
    violation_count = 0
    parsed_count = 0
    candidate_answer_blind = False
    environment_presence_only = False
    exact_byte_module_loader = False
    fixed_local_subprocess_calls = 0
    for relative_path in sorted(EXECUTABLE_SOURCE_PATHS):
        raw = source_bytes.get(relative_path)
        if raw is None:
            violation_count += 1
            continue
        try:
            tree = ast.parse(raw.decode("utf-8"), filename=relative_path)
        except (SyntaxError, UnicodeError):
            violation_count += 1
            continue
        parsed_count += 1
        allowed_imports = IMPORT_ALLOWLIST[relative_path]
        allowed_dynamic_calls: frozenset[ast.Call] = frozenset()
        if relative_path == "benchmarks/run_phase11_8_9_offline_retrieval_recovery.py":
            allowed_dynamic_calls, exact_byte_module_loader = _runner_exact_byte_loader_audit(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                for imported in _import_name(node):
                    import_count += 1
                    if imported not in allowed_imports:
                        violation_count += 1
            elif isinstance(node, ast.Call):
                call_count += 1
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.func.attr == "run"
                ):
                    fixed_local_subprocess_calls += 1
                if _forbidden_call(node) and node not in allowed_dynamic_calls:
                    violation_count += 1
            elif (
                isinstance(node, ast.Attribute)
                and node.attr.casefold() in {"environ", "getenv"}
                and relative_path != "benchmarks/run_phase11_8_9_offline_retrieval_recovery.py"
            ):
                violation_count += 1
        if relative_path == "benchmarks/phase11_8_9_retrieval_candidate.py":
            candidate_answer_blind = _candidate_input_audit(tree)
        elif relative_path == "benchmarks/run_phase11_8_9_offline_retrieval_recovery.py":
            environment_presence_only = _runner_environment_presence_only(tree)

    return {
        "answer_blind_candidate_interface_passed": candidate_answer_blind,
        "ast_call_count": call_count,
        "ast_import_count": import_count,
        "executable_source_count": len(EXECUTABLE_SOURCE_PATHS),
        "exact_byte_module_loader_audit_passed": exact_byte_module_loader,
        "fixed_local_conformance_subprocess_call_count": fixed_local_subprocess_calls,
        "forbidden_capability_violation_count": violation_count,
        "presence_only_environment_audit_passed": environment_presence_only,
        "parsed_executable_source_count": parsed_count,
        "passed": (
            parsed_count == len(EXECUTABLE_SOURCE_PATHS)
            and violation_count == 0
            and candidate_answer_blind
            and environment_presence_only
            and exact_byte_module_loader
            and fixed_local_subprocess_calls == 1
        ),
    }


def _raw_results(case: dict[str, Any]) -> tuple[RawResult, ...]:
    rows = case.get("raw_results")
    _require(isinstance(rows, list), "invalid_fixture_raw_results")
    results: list[RawResult] = []
    for row in rows:
        _require(isinstance(row, dict), "invalid_fixture_raw_result")
        results.append(
            RawResult(
                result_id=str(row["result_id"]),
                title=str(row["title"]),
                url=str(row["url"]),
                snippet=str(row["snippet"]),
                provider=str(row["provider"]),
                rank=int(row["rank"]),
                query=str(row["query"]),
                source_type=str(row.get("source_type", "web")),
                provider_score_micros=(
                    int(row["provider_score_micros"])
                    if row.get("provider_score_micros") is not None
                    else None
                ),
                metadata=freeze_metadata(row.get("metadata")),
            )
        )
    return tuple(results)


def _aggregate_funnels(
    outcomes: list[SelectionOutcome],
) -> dict[str, int | str]:
    totals: dict[str, int | str] = {"family": outcomes[0].family}
    fields = asdict(outcomes[0].funnel)
    for field in fields:
        totals[field] = sum(int(getattr(outcome.funnel, field)) for outcome in outcomes)
    return totals


def _selected_utility_hits(
    outcome: SelectionOutcome,
    utility_result_ids: frozenset[str],
) -> int:
    return sum(
        bool(utility_result_ids.intersection(result.raw_result_ids)) for result in outcome.selected
    )


def _query_anchor_documents(evidence: tuple[ProjectedEvidence, ...], query: str) -> int:
    terms = {
        token.casefold()
        for token in re.findall(r"[\w-]+", query)
        if len(token) >= 3 or any(character.isdigit() for character in token)
    }
    return sum(
        any(
            re.search(rf"(?<!\w){re.escape(term)}(?!\w)", item.text, re.IGNORECASE)
            for term in terms
        )
        for item in evidence
    )


def _project_control_v2(
    outcome: SelectionOutcome,
    query: str,
) -> ProjectionOutcome:
    nonempty_sources = tuple(result for result in outcome.selected if result.snippet.strip())
    source_blocks = tuple(
        ProjectedEvidence(
            citation_id=f"S{index}",
            title=result.title,
            url=result.url,
            text=result.snippet,
            providers=result.providers,
            provider_ranks=result.provider_ranks,
            source_type=result.source_type,
        )
        for index, result in enumerate(nonempty_sources, start=1)
    )
    evidence = candidate_project_blocks_v2(
        source_blocks,
        query,
        PROJECTION_BUDGET_CHARS,
        MAX_DOCUMENT_CHARS,
        min_block_chars=MIN_DOCUMENT_CHARS,
    )
    rendered_chars = rendered_control_projection_chars(evidence)
    _require(
        rendered_chars <= PROJECTION_BUDGET_CHARS,
        "control_v2_projection_budget_exceeded",
    )
    return ProjectionOutcome(
        family=CONTROL_PROJECTION_FAMILY,
        evidence=evidence,
        metrics=ProjectionMetrics(
            selected_input_documents=len(outcome.selected),
            nonempty_source_documents=len(source_blocks),
            projected_documents=len(evidence),
            documents_with_nonzero_text=sum(bool(item.text) for item in evidence),
            dropped_for_header_budget=len(source_blocks) - len(evidence),
            documents_with_query_anchor=_query_anchor_documents(evidence, query),
            rendered_chars=rendered_chars,
            budget_chars=PROJECTION_BUDGET_CHARS,
            unused_budget_chars=PROJECTION_BUDGET_CHARS - rendered_chars,
        ),
    )


def _project_candidate_v3(
    outcome: SelectionOutcome,
    query: str,
) -> ProjectionOutcome:
    return project_selected_v3(
        outcome.selected,
        query,
        budget_chars=PROJECTION_BUDGET_CHARS,
        max_document_chars=MAX_DOCUMENT_CHARS,
        min_document_chars=MIN_DOCUMENT_CHARS,
    )


def _projection_source_preserved(
    outcome: SelectionOutcome,
    query: str,
    *,
    candidate: bool,
) -> tuple[bool, dict[str, int], ProjectionOutcome]:
    projection = (
        _project_candidate_v3(outcome, query) if candidate else _project_control_v2(outcome, query)
    )
    valid = _validate_projection(outcome, query, projection, candidate=candidate)
    return valid, asdict(projection.metrics), projection


def _validate_projection(
    outcome: SelectionOutcome,
    query: str,
    projection: ProjectionOutcome,
    *,
    candidate: bool,
) -> bool:
    nonempty_sources = tuple(result for result in outcome.selected if result.snippet.strip())
    source_by_citation = {
        f"S{index}": source for index, source in enumerate(nonempty_sources, start=1)
    }
    try:
        rendered_chars = (
            rendered_projection_chars(projection.evidence)
            if candidate
            else rendered_control_projection_chars(projection.evidence)
        )
    except ValueError:
        return False
    citation_ids = [evidence.citation_id for evidence in projection.evidence]
    metrics = projection.metrics
    valid = (
        rendered_chars <= PROJECTION_BUDGET_CHARS
        and len(projection.evidence) <= len(source_by_citation)
        and citation_ids == [f"S{index}" for index in range(1, len(citation_ids) + 1)]
        and len(citation_ids) == len(set(citation_ids))
        and all(bool(evidence.text.strip()) for evidence in projection.evidence)
        and all(len(evidence.text) <= MAX_DOCUMENT_CHARS for evidence in projection.evidence)
        and projection.family
        == (CANDIDATE_PROJECTION_FAMILY if candidate else CONTROL_PROJECTION_FAMILY)
        and metrics.selected_input_documents == len(outcome.selected)
        and metrics.nonempty_source_documents == len(nonempty_sources)
        and metrics.projected_documents == len(projection.evidence)
        and metrics.documents_with_nonzero_text
        == sum(bool(evidence.text.strip()) for evidence in projection.evidence)
        and metrics.dropped_for_header_budget == len(nonempty_sources) - len(projection.evidence)
        and metrics.documents_with_query_anchor
        == _query_anchor_documents(projection.evidence, query)
        and metrics.rendered_chars == rendered_chars
        and metrics.budget_chars == PROJECTION_BUDGET_CHARS
        and metrics.unused_budget_chars == PROJECTION_BUDGET_CHARS - rendered_chars
    )
    for evidence in projection.evidence:
        source = source_by_citation.get(evidence.citation_id)
        if source is None:
            valid = False
            continue
        valid = valid and (
            evidence.title == source.title
            and evidence.url == source.url
            and evidence.providers == source.providers
            and evidence.provider_ranks == source.provider_ranks
            and evidence.source_type == source.source_type
        )
        cursor = 0
        for segment in evidence.text.split(OMISSION_SEPARATOR):
            if not segment.strip():
                valid = False
                continue
            position = source.snippet.strip().find(segment, cursor)
            valid = valid and position >= 0
            if position >= 0:
                cursor = position + len(segment)
    return valid


def _test_function_names(test_source_raw: bytes) -> set[str]:
    try:
        tree = ast.parse(test_source_raw.decode("utf-8"))
    except (SyntaxError, UnicodeError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        meaningful_nodes = [
            child
            for child in ast.walk(node)
            if isinstance(child, ast.Assert | ast.Call | ast.Raise)
        ]
        if meaningful_nodes:
            names.add(node.name)
    return names


def _validate_conformance_registry(
    fixture: dict[str, Any],
    test_source_bytes: tuple[bytes, ...],
) -> tuple[dict[str, int | bool], frozenset[str]]:
    catalog = fixture.get("conformance_case_catalog")
    requirements = fixture.get("conformance_requirements")
    cases = fixture.get("cases")
    _require(
        isinstance(catalog, list) and isinstance(requirements, list) and isinstance(cases, list),
        "missing_conformance_registry",
    )
    catalog_ids: set[str] = set()
    catalog_valid = True
    for entry in catalog:
        entry_valid = (
            isinstance(entry, dict)
            and set(entry) == {"id", "kind", "purpose"}
            and isinstance(entry.get("id"), str)
            and bool(entry.get("id"))
            and isinstance(entry.get("kind"), str)
            and bool(entry.get("kind"))
            and isinstance(entry.get("purpose"), str)
            and bool(entry.get("purpose"))
        )
        catalog_valid = catalog_valid and entry_valid
        if entry_valid:
            catalog_ids.add(str(entry["id"]))
    case_ids = {
        str(case.get("id"))
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }
    known_case_ids = catalog_ids | case_ids
    available_tests = set().union(
        *(_test_function_names(test_source_raw) for test_source_raw in test_source_bytes)
    )
    requirement_ids: set[str] = set()
    referenced_test_names: set[str] = set()
    registry_valid = catalog_valid and len(catalog_ids) == len(catalog)
    for requirement in requirements:
        requirement_valid = (
            isinstance(requirement, dict)
            and set(requirement) == {"evidence", "id"}
            and isinstance(requirement.get("id"), str)
            and bool(requirement.get("id"))
            and isinstance(requirement.get("evidence"), dict)
            and set(requirement["evidence"]) == {"case_ids", "proof", "suite", "test_names"}
        )
        if not requirement_valid:
            registry_valid = False
            continue
        requirement_id = str(requirement["id"])
        evidence = requirement["evidence"]
        referenced_cases = evidence["case_ids"]
        test_names = evidence["test_names"]
        proof = evidence["proof"]
        suite = evidence["suite"]
        requirement_valid = (
            requirement_id not in requirement_ids
            and isinstance(referenced_cases, list)
            and bool(referenced_cases)
            and all(
                isinstance(case_id, str) and bool(case_id) and case_id in known_case_ids
                for case_id in referenced_cases
            )
            and isinstance(test_names, list)
            and bool(test_names)
            and all(
                isinstance(test_name, str) and bool(test_name) and test_name in available_tests
                for test_name in test_names
            )
            and isinstance(proof, str)
            and bool(proof.strip())
            and suite in {"external_adapter", "retrieval", "runner"}
        )
        registry_valid = registry_valid and requirement_valid
        requirement_ids.add(requirement_id)
        referenced_test_names.update(value for value in test_names if isinstance(value, str))

    registry_complete = (
        registry_valid
        and requirement_ids == EXPECTED_CONFORMANCE_REQUIREMENT_IDS
        and len(requirements) == len(EXPECTED_CONFORMANCE_REQUIREMENT_IDS)
    )
    return (
        {
            "catalog_case_count": len(catalog),
            "known_case_count": len(known_case_ids),
            "referenced_test_count": len(referenced_test_names),
            "registered_requirement_count": len(requirements),
            "registry_complete": registry_complete,
            "requirements_with_structural_evidence": (
                len(requirements) if registry_complete else 0
            ),
        },
        frozenset(referenced_test_names),
    )


def _failed_conformance_receipt(
    locked_source_set_sha256: str,
    registered_test_count: int,
) -> dict[str, int | str]:
    return {
        "collected": 0,
        "errors": 1,
        "failures": 0,
        "passed": 0,
        "registered_test_count": registered_test_count,
        "registered_tests_covered": 0,
        "skipped": 0,
        "source_set_sha256": locked_source_set_sha256,
        "status": "failed",
    }


def _parse_conformance_junit(
    path: Path,
    *,
    locked_source_set_sha256: str,
    registered_test_names: frozenset[str],
    process_returncode: int,
) -> dict[str, int | str]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 524_288:
            return _failed_conformance_receipt(
                locked_source_set_sha256,
                len(registered_test_names),
            )
        raw = path.read_bytes()
        if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
            return _failed_conformance_receipt(
                locked_source_set_sha256,
                len(registered_test_names),
            )
        root = ET.fromstring(raw)  # noqa: S314 - bounded, local pytest JUnit only
    except (OSError, ET.ParseError):
        return _failed_conformance_receipt(
            locked_source_set_sha256,
            len(registered_test_names),
        )
    if root.tag != "testsuites":
        return _failed_conformance_receipt(
            locked_source_set_sha256,
            len(registered_test_names),
        )
    suites = root.findall("testsuite")
    if len(suites) != 1:
        return _failed_conformance_receipt(
            locked_source_set_sha256,
            len(registered_test_names),
        )
    suite = suites[0]
    testcases = suite.findall("testcase")
    executed_test_names: set[str] = set()
    failures = 0
    errors = 0
    skipped = 0
    for testcase in testcases:
        name = testcase.get("name")
        if not name:
            return _failed_conformance_receipt(
                locked_source_set_sha256,
                len(registered_test_names),
            )
        executed_test_names.add(name.split("[", 1)[0])
        states = [child.tag for child in testcase if child.tag in {"error", "failure", "skipped"}]
        if len(states) > 1:
            return _failed_conformance_receipt(
                locked_source_set_sha256,
                len(registered_test_names),
            )
        failures += states == ["failure"]
        errors += states == ["error"]
        skipped += states == ["skipped"]
    collected = len(testcases)
    covered = len(registered_test_names.intersection(executed_test_names))
    passed = collected - failures - errors - skipped
    status = (
        "passed"
        if process_returncode == 0
        and collected > 0
        and passed == collected
        and covered == len(registered_test_names)
        else "failed"
    )
    return {
        "collected": collected,
        "errors": errors,
        "failures": failures,
        "passed": passed,
        "registered_test_count": len(registered_test_names),
        "registered_tests_covered": covered,
        "skipped": skipped,
        "source_set_sha256": locked_source_set_sha256,
        "status": status,
    }


def _materialize_locked_test_tree(
    root: Path,
    source_bytes: dict[str, bytes],
    manifest_raw: bytes,
) -> None:
    _require(root.is_dir() and not root.is_symlink(), "invalid_locked_test_tree_root")
    files = dict(source_bytes)
    _require(
        SOURCE_LOCK_MANIFEST_PATH not in files,
        "source_lock_manifest_in_authority_set",
    )
    files[SOURCE_LOCK_MANIFEST_PATH] = manifest_raw
    root_resolved = root.resolve(strict=True)
    for relative_path, raw in sorted(files.items()):
        safe_path = _safe_relative_path(relative_path)
        target = root.joinpath(*PurePosixPath(safe_path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        _require(
            target.parent.resolve(strict=True).is_relative_to(root_resolved),
            "locked_test_tree_path_escape",
        )
        _require(not target.exists() and not target.is_symlink(), "locked_test_tree_collision")
        _require(
            target.write_bytes(raw) == len(raw),
            "locked_test_tree_short_write",
        )
        _require(
            target.read_bytes() == raw,
            "locked_test_tree_verification_mismatch",
        )
        target.chmod(0o444)


def _run_conformance_receipt(
    locked_source_set_sha256: str,
    registered_test_names: frozenset[str],
    source_bytes: dict[str, bytes],
    manifest_raw: bytes,
) -> dict[str, int | str]:
    _require(
        set(source_bytes) == EXPECTED_AUTHORITY_PATHS
        and source_set_sha256(source_bytes) == locked_source_set_sha256,
        "invalid_conformance_source_bytes",
    )
    manifest = json.loads(manifest_raw)
    _require(
        isinstance(manifest, dict)
        and manifest.get("source_set_sha256") == locked_source_set_sha256,
        "invalid_conformance_source_lock_manifest",
    )
    cached = _CONFORMANCE_RECEIPT_CACHE.get(locked_source_set_sha256)
    if cached is not None:
        return dict(cached)
    with tempfile.TemporaryDirectory(prefix="evidencemesh-phase11-8-9-") as temp_dir:
        locked_tree = Path(temp_dir) / "locked-tree"
        locked_tree.mkdir()
        _materialize_locked_test_tree(
            locked_tree,
            source_bytes,
            manifest_raw,
        )
        junit_path = Path(temp_dir) / "gate9.junit.xml"
        command = (
            sys.executable,
            *CONFORMANCE_PYTEST_PREFIX,
            "-p",
            "pytest_asyncio.plugin",
            "-p",
            "no:cacheprovider",
            "--noconftest",
            "-c",
            "pyproject.toml",
            "--rootdir=.",
            "-o",
            "junit_family=xunit2",
            f"--junitxml={junit_path}",
            "-q",
            "tests/test_phase11_8_9_retrieval_candidate.py",
            "tests/test_phase11_8_9_external_eval.py",
            *RUNNER_RECEIPT_TEST_NODE_IDS,
        )
        environment = {
            "PATH": os.defpath,
            "PYTEST_ADDOPTS": "",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONHASHSEED": "0",
        }
        try:
            completed = subprocess.run(  # noqa: S603 - immutable local command
                command,
                cwd=locked_tree,
                env=environment,
                check=False,
                capture_output=True,
                timeout=120,
            )
            receipt = _parse_conformance_junit(
                junit_path,
                locked_source_set_sha256=locked_source_set_sha256,
                registered_test_names=registered_test_names,
                process_returncode=completed.returncode,
            )
        except (OSError, subprocess.SubprocessError):
            receipt = _failed_conformance_receipt(
                locked_source_set_sha256,
                len(registered_test_names),
            )
    _CONFORMANCE_RECEIPT_CACHE[locked_source_set_sha256] = dict(receipt)
    return receipt


def _run_retrieval_fixtures(
    raw: bytes,
    test_source_bytes: tuple[bytes, ...],
    source_audit: dict[str, Any],
    conformance_receipt: dict[str, int | str],
) -> dict[str, Any]:
    fixture = json.loads(raw)
    _require(
        isinstance(fixture, dict)
        and fixture.get("benchmark") == "evidencemesh-phase11-8-9-retrieval-fixtures-v1"
        and fixture.get("engineering_only") is True
        and fixture.get("development_diagnostic_only") is True
        and fixture.get("predictive_quality_claim_allowed") is False
        and fixture.get("real_world_quality_claim_allowed") is False,
        "retrieval_fixture_disclosure_changed",
    )
    cases = fixture.get("cases")
    _require(
        isinstance(cases, list) and len(cases) == EXPECTED_FIXTURE_CASES,
        "unexpected_retrieval_fixture_count",
    )
    conformance_registry, referenced_test_names = _validate_conformance_registry(
        fixture,
        test_source_bytes,
    )
    receipt_covers_registry = conformance_receipt.get("registered_test_count") == len(
        referenced_test_names
    ) and conformance_receipt.get("registered_tests_covered") == len(referenced_test_names)

    baseline_outcomes: list[SelectionOutcome] = []
    candidate_outcomes: list[SelectionOutcome] = []
    baseline_expected_matches = 0
    candidate_expected_matches = 0
    baseline_utility_hits = 0
    candidate_utility_hits = 0
    lineage_invariant_cases = 0
    projection_invariant_cases = 0
    replay_invariant_cases = 0
    stage_invariant_cases = 0
    baseline_projection_totals: dict[str, int] = {}
    candidate_projection_totals: dict[str, int] = {}

    for case in cases:
        _require(isinstance(case, dict), "invalid_retrieval_fixture_case")
        query = case.get("query")
        limit = case.get("limit")
        max_per_domain = case.get("max_per_domain")
        _require(
            isinstance(query, str)
            and isinstance(limit, int)
            and isinstance(max_per_domain, int)
            and 1 <= limit <= MAX_SELECTED_DOCUMENTS,
            "invalid_retrieval_fixture_contract",
        )
        raw_results = _raw_results(case)

        baseline_replays = tuple(
            select_baseline(
                raw_results,
                query,
                limit=limit,
                max_per_domain=max_per_domain,
            )
            for _ in range(2)
        )
        candidate_replays = tuple(
            select_candidate_v3(
                raw_results,
                query,
                limit=limit,
                max_per_domain=max_per_domain,
            )
            for _ in range(2)
        )
        baseline = baseline_replays[0]
        candidate = candidate_replays[0]
        baseline_outcomes.append(baseline)
        candidate_outcomes.append(candidate)

        expected_baseline = case.get("expected_baseline_selected_ids")
        expected_candidate = case.get("expected_candidate_selected_ids")
        utility_ids = case.get("utility_result_ids")
        _require(
            isinstance(expected_baseline, list)
            and isinstance(expected_candidate, list)
            and isinstance(utility_ids, list),
            "invalid_evaluator_only_fixture_fields",
        )
        baseline_selected = [result.representative_result_id for result in baseline.selected]
        candidate_selected = [result.representative_result_id for result in candidate.selected]
        baseline_expected_matches += baseline_selected == expected_baseline
        candidate_expected_matches += candidate_selected == expected_candidate
        utility = frozenset(str(value) for value in utility_ids)
        baseline_utility_hits += _selected_utility_hits(baseline, utility)
        candidate_utility_hits += _selected_utility_hits(candidate, utility)

        fused = fuse_results(raw_results, query)
        fused_urls = {result.canonical_url for result in fused}
        lineage_valid = (
            all(result.raw_result_ids for result in fused)
            and len(fused_urls) == len(fused)
            and all(
                result.canonical_url in fused_urls
                for outcome in (baseline, candidate)
                for result in outcome.selected
            )
            and all(
                len(outcome.selected) <= min(limit, MAX_SELECTED_DOCUMENTS)
                for outcome in (baseline, candidate)
            )
        )
        lineage_invariant_cases += lineage_valid

        baseline_projection_valid, baseline_projection, baseline_projection_outcome = (
            _projection_source_preserved(
                baseline,
                query,
                candidate=False,
            )
        )
        candidate_projection_valid, candidate_projection, candidate_projection_outcome = (
            _projection_source_preserved(
                candidate,
                query,
                candidate=True,
            )
        )
        projection_invariant_cases += baseline_projection_valid and candidate_projection_valid
        stage_invariant_cases += all(
            (
                outcome.funnel.raw_pool
                >= outcome.funnel.valid_raw
                >= outcome.funnel.fused
                >= outcome.funnel.eligible
                >= outcome.funnel.selected
                >= len(projection.evidence)
            )
            for outcome, projection in (
                (baseline, baseline_projection_outcome),
                (candidate, candidate_projection_outcome),
            )
        )
        for field, value in baseline_projection.items():
            baseline_projection_totals[field] = baseline_projection_totals.get(field, 0) + value
        for field, value in candidate_projection.items():
            candidate_projection_totals[field] = candidate_projection_totals.get(field, 0) + value

        replay_valid = canonical_funnel_json(baseline_replays[0]) == canonical_funnel_json(
            baseline_replays[1]
        ) and canonical_funnel_json(candidate_replays[0]) == canonical_funnel_json(
            candidate_replays[1]
        )
        for replay, is_candidate in (
            *((value, False) for value in baseline_replays),
            *((value, True) for value in candidate_replays),
        ):
            projection_replays = tuple(
                (
                    _project_candidate_v3(replay, query)
                    if is_candidate
                    else _project_control_v2(replay, query)
                )
                for _ in range(2)
            )
            replay_valid = replay_valid and (
                canonical_projection_json(projection_replays[0])
                == canonical_projection_json(projection_replays[1])
            )
        replay_invariant_cases += replay_valid

    return {
        "arm_aggregates": {
            "retrieval_candidate_v3": {
                "family": "retrieval_candidate_v3",
                "funnel": _aggregate_funnels(candidate_outcomes),
                "projection": candidate_projection_totals,
                "projection_family": CANDIDATE_PROJECTION_FAMILY,
                "selection_family": CANDIDATE_FAMILY,
                "synthetic_utility_canonical_hits": candidate_utility_hits,
            },
            "pre_v3_pipeline_control": {
                "family": "pre_v3_pipeline_control",
                "funnel": _aggregate_funnels(baseline_outcomes),
                "projection": baseline_projection_totals,
                "projection_family": CONTROL_PROJECTION_FAMILY,
                "selection_family": BASELINE_FAMILY,
                "synthetic_utility_canonical_hits": baseline_utility_hits,
            },
        },
        "candidate_expected_selection_match_cases": candidate_expected_matches,
        "case_count": len(cases),
        "conformance_receipt": conformance_receipt,
        "conformance_receipt_covers_registry": receipt_covers_registry,
        "control_expected_selection_match_cases": baseline_expected_matches,
        "control_projector_v2_invocation_cases": len(cases),
        "conformance_registry": conformance_registry,
        "evaluator_only_fields_reached_candidate": False,
        "in_process_replays_per_arm": 2,
        "independent_process_replay_status": "required_workflow_cmp",
        "lineage_invariant_cases": lineage_invariant_cases,
        "projection_invariant_cases": projection_invariant_cases,
        "real_external_score": False,
        "replay_invariant_cases": replay_invariant_cases,
        "scope": "local_synthetic_engineering_conformance",
        "source_capability_audit_passed": source_audit.get("passed") is True,
        "stage_invariant_cases": stage_invariant_cases,
    }


def _external_status(
    accessed_paths: set[str],
) -> tuple[dict[str, Any], bool, bool]:
    registry_path = _repository_file(
        EXTERNAL_REGISTRY_PATH,
        accessed_paths=accessed_paths,
    )
    fixture_path = _repository_file(
        EXTERNAL_FIXTURE_PATH,
        accessed_paths=accessed_paths,
    )
    registry = load_registry(registry_path)
    registry_validation = validate_registry(registry)
    fixture_result = evaluate_fixture_file(
        fixture_path,
        registry_path,
    )
    benchmarks = registry.get("benchmarks")
    _require(isinstance(benchmarks, list), "invalid_external_registry_benchmarks")
    suite_ids = tuple(
        str(benchmark.get("benchmark_id"))
        for benchmark in benchmarks
        if isinstance(benchmark, dict)
    )
    _require(
        tuple(sorted(suite_ids)) == tuple(sorted(EXPECTED_EXTERNAL_SUITES)),
        "unexpected_external_registry_suites",
    )
    unresolved = sum(
        benchmark.get("benchmark_asset_license", {}).get("status") != "resolved"
        for benchmark in benchmarks
        if isinstance(benchmark, dict)
    )
    explicit_license_entries = sum(
        isinstance(benchmark, dict)
        and isinstance(benchmark.get("benchmark_asset_license"), dict)
        and set(benchmark["benchmark_asset_license"])
        == {
            "evidence_revision",
            "real_external_evaluation_allowed",
            "reason",
            "scope",
            "spdx_id",
            "status",
        }
        and benchmark["benchmark_asset_license"].get("status") == "unresolved"
        and benchmark["benchmark_asset_license"].get("spdx_id") is None
        and benchmark["benchmark_asset_license"].get("real_external_evaluation_allowed") is False
        and isinstance(benchmark["benchmark_asset_license"].get("reason"), str)
        and bool(benchmark["benchmark_asset_license"]["reason"])
        for benchmark in benchmarks
    )

    registry_passed = registry_validation == registry
    fixture_passed = (
        fixture_result.get("evaluation_scope") == "integration_conformance_synthetic"
        and fixture_result.get("evaluation_status") == "evaluated"
        and fixture_result.get("real_external_scores_present") is False
        and fixture_result.get("external_quality_claim_allowed") is False
        and fixture_result.get("aggregate_only") is True
        and fixture_result.get("benchmark_count") == len(EXPECTED_EXTERNAL_SUITES)
        and fixture_result.get("all_expected_metrics_matched") is True
    )
    fixture_conformance = {
        "aggregate_only": fixture_result.get("aggregate_only"),
        "evaluation_scope": fixture_result.get("evaluation_scope"),
        "fixture_suite_count": fixture_result.get("benchmark_count"),
        "metric_oracles_matched": fixture_result.get("all_expected_metrics_matched"),
        "real_external_score": fixture_result.get("real_external_scores_present"),
        "status": "passed" if fixture_passed else "failed",
    }
    license_boundary_passed = (
        explicit_license_entries == len(EXPECTED_EXTERNAL_SUITES)
        and unresolved == len(EXPECTED_EXTERNAL_SUITES)
        and fixture_result.get("real_external_scores_present") is False
        and fixture_result.get("external_quality_claim_allowed") is False
    )
    return (
        {
            "asset_license_status": "unresolved",
            "complete_locked_assets_present": False,
            "explicit_asset_license_entry_count": explicit_license_entries,
            "license_boundary_passed": license_boundary_passed,
            "registry_suite_count": len(suite_ids),
            "registry_validation_passed": registry_passed,
            "status": "external_evaluation_not_run",
            "suite_statuses": {
                suite: {
                    "reason_category": "locked_assets_absent_or_inadmissible",
                    "status": "not_evaluated",
                }
                for suite in EXPECTED_EXTERNAL_SUITES
            },
            "synthetic_adapter_conformance": fixture_conformance,
            "unresolved_asset_license_count": unresolved,
        },
        registry_passed and fixture_passed,
        license_boundary_passed,
    )


def _privacy_audit(payload: object) -> dict[str, int | bool]:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    absolute_paths = len(re.findall(r"(?<![A-Za-z0-9_])/(?:tmp|home|workspace|root)/", serialized))
    web_urls = serialized.count("https://") + serialized.count("http://")
    forbidden_keys = (
        '"answer"',
        '"document_id"',
        '"per_query"',
        '"qrel_id"',
        '"query_hash"',
        '"query_id"',
        '"question"',
        '"row_index"',
        '"selector_position"',
        '"snippet"',
        '"title"',
        '"url"',
    )
    forbidden_key_occurrences = sum(serialized.count(key) for key in forbidden_keys)
    return {
        "absolute_path_occurrences": absolute_paths,
        "forbidden_key_occurrences": forbidden_key_occurrences,
        "passed": (absolute_paths == 0 and web_urls == 0 and forbidden_key_occurrences == 0),
        "web_url_occurrences": web_urls,
    }


def _path_access_audit(
    accessed_paths: set[str],
    source_bytes: dict[str, bytes],
) -> dict[str, int | bool]:
    allowed = set(source_bytes) | {SOURCE_LOCK_MANIFEST_PATH}
    forbidden = {
        path
        for path in accessed_paths
        if "phase12" in path.casefold().replace("-", "_")
        or "phase_12" in path.casefold().replace("-", "_")
    }
    outside = accessed_paths - allowed
    return {
        "accessed_repository_path_count": len(accessed_paths),
        "authority_path_read_count": len(accessed_paths.intersection(source_bytes)),
        "outside_source_set_path_count": len(outside),
        "phase12_path_access_count": len(forbidden),
        "passed": (
            not forbidden
            and not outside
            and set(source_bytes).issubset(accessed_paths)
            and SOURCE_LOCK_MANIFEST_PATH in accessed_paths
        ),
    }


def _governance_audit(authority_paths: set[str]) -> dict[str, int | bool | str]:
    product_runtime_paths = {
        path for path in authority_paths if path.startswith(PRODUCT_MUTATION_PREFIXES)
    }
    product_default_paths = authority_paths.intersection(PRODUCT_DEFAULT_PATHS)
    release_paths = {path for path in authority_paths if path.startswith(RELEASE_MUTATION_PREFIXES)}
    exact_source_scope = authority_paths == EXPECTED_AUTHORITY_PATHS
    passed = (
        exact_source_scope
        and not product_runtime_paths
        and not product_default_paths
        and not release_paths
    )
    return {
        "exact_source_scope_passed": exact_source_scope,
        "phase11_9_authorized": False,
        "phase12_authorized": False,
        "product_default_mutation_path_count": len(product_default_paths),
        "product_runtime_mutation_path_count": len(product_runtime_paths),
        "pull_request_state_verification": "externally_verified_by_github_process",
        "pull_request_state_verified_by_runner": False,
        "release_mutation_path_count": len(release_paths),
        "source_scope_path_count": len(authority_paths),
        "passed": passed,
    }


def _public_schema_audit(payload: dict[str, Any]) -> dict[str, int | bool]:
    checks = (
        set(payload)
        == {
            "benchmark",
            "external_evaluation",
            "fixture_evaluation",
            "governance",
            "historical_boundary",
            "observed_development_boundary",
            "path_access_audit",
            "publication_reference",
            "schema_version",
            "source_capability_audit",
            "source_integrity",
            "source_locks",
            "traffic",
        },
        set(payload["publication_reference"])
        == {
            "commit_sha",
            "required_external_verification",
            "runner_verified_commit_binding",
            "verification_status",
        },
        set(payload["source_integrity"])
        == {
            "authority_file_count",
            "computed_source_set_sha256",
            "declared_source_set_sha256",
            "manifest_sha256",
            "matched_authority_hash_count",
            "source_set_byte_authority",
        },
        set(payload["fixture_evaluation"])
        == {
            "arm_aggregates",
            "candidate_expected_selection_match_cases",
            "case_count",
            "conformance_receipt",
            "conformance_receipt_covers_registry",
            "conformance_registry",
            "control_expected_selection_match_cases",
            "control_projector_v2_invocation_cases",
            "evaluator_only_fields_reached_candidate",
            "in_process_replays_per_arm",
            "independent_process_replay_status",
            "lineage_invariant_cases",
            "projection_invariant_cases",
            "real_external_score",
            "replay_invariant_cases",
            "scope",
            "source_capability_audit_passed",
            "stage_invariant_cases",
        },
        set(payload["fixture_evaluation"]["arm_aggregates"])
        == {"pre_v3_pipeline_control", "retrieval_candidate_v3"},
        all(
            set(arm)
            == {
                "family",
                "funnel",
                "projection",
                "projection_family",
                "selection_family",
                "synthetic_utility_canonical_hits",
            }
            for arm in payload["fixture_evaluation"]["arm_aggregates"].values()
        ),
        set(payload["external_evaluation"])
        == {
            "asset_license_status",
            "complete_locked_assets_present",
            "explicit_asset_license_entry_count",
            "license_boundary_passed",
            "registry_suite_count",
            "registry_validation_passed",
            "status",
            "suite_statuses",
            "synthetic_adapter_conformance",
            "unresolved_asset_license_count",
        },
        all(
            isinstance(item, dict) and set(item) == {"relative_path", "sha256"}
            for item in payload["source_locks"]
        ),
        set(payload["traffic"]) == set(ZERO_TRAFFIC),
        set(payload["path_access_audit"])
        == {
            "accessed_repository_path_count",
            "authority_path_read_count",
            "outside_source_set_path_count",
            "passed",
            "phase12_path_access_count",
        },
        set(payload["governance"])
        == {
            "exact_source_scope_passed",
            "passed",
            "phase11_9_authorized",
            "phase12_authorized",
            "product_default_mutation_path_count",
            "product_runtime_mutation_path_count",
            "pull_request_state_verification",
            "pull_request_state_verified_by_runner",
            "release_mutation_path_count",
            "source_scope_path_count",
        },
    )
    passed_count = sum(checks)
    return {
        "failed_contract_count": len(checks) - passed_count,
        "passed": passed_count == len(checks),
        "strict_contract_count": len(checks),
    }


def _final_public_schema_audit(payload: dict[str, Any]) -> dict[str, int | bool]:
    pre_decision_keys = {
        "benchmark",
        "external_evaluation",
        "fixture_evaluation",
        "governance",
        "historical_boundary",
        "observed_development_boundary",
        "path_access_audit",
        "publication_reference",
        "schema_version",
        "source_capability_audit",
        "source_integrity",
        "source_locks",
        "traffic",
    }
    final_only_keys = {
        "decision",
        "gates",
        "privacy",
        "public_schema",
        "resource_diagnostics",
    }
    try:
        pre_decision = {key: payload[key] for key in pre_decision_keys}
        pre_audit = _public_schema_audit(pre_decision)
        checks = (
            set(payload) == pre_decision_keys | final_only_keys,
            pre_audit["passed"] is True,
            set(payload["decision"])
            == {
                "external_quality_passed",
                "gate_count",
                "merge_allowed",
                "offline_outcome",
                "passed_gate_count",
                "phase11_9_authorized",
                "phase12_authorized",
                "product_defaults_change_allowed",
                "pull_request_remains_draft_required",
                "pull_request_state_verification_required",
                "pull_request_state_verified_by_runner",
                "release_allowed",
                "release_decision",
                "superiority_claim_allowed",
            },
            isinstance(payload["gates"], list)
            and len(payload["gates"]) == EXPECTED_GATE_COUNT
            and all(
                isinstance(gate, dict)
                and set(gate)
                in (
                    {"name", "number", "passed"},
                    {"name", "number", "passed", "status"},
                )
                for gate in payload["gates"]
            ),
            set(payload["privacy"])
            == {
                "absolute_path_occurrences",
                "forbidden_key_occurrences",
                "passed",
                "web_url_occurrences",
            },
            set(payload["public_schema"])
            == {"failed_contract_count", "passed", "strict_contract_count"},
            set(payload["resource_diagnostics"])
            == {
                "build_time_seconds",
                "index_bytes",
                "measurement_status",
                "peak_resident_memory_bytes",
                "query_time_seconds",
            },
        )
    except (KeyError, TypeError):
        checks = (False,)
        pre_audit = {"strict_contract_count": 0}
    passed_count = sum(checks)
    total = int(pre_audit["strict_contract_count"]) + len(checks)
    failed = int(pre_audit.get("failed_contract_count", 0)) + len(checks) - passed_count
    return {
        "failed_contract_count": failed,
        "passed": failed == 0,
        "strict_contract_count": total,
    }


def _audit_final_public_payload(payload: dict[str, Any]) -> dict[str, dict[str, int | bool]]:
    privacy_subject = {
        key: value for key, value in payload.items() if key not in {"privacy", "public_schema"}
    }
    return {
        "privacy": _privacy_audit(privacy_subject),
        "public_schema": _final_public_schema_audit(payload),
    }


def _gates(
    *,
    source_integrity: dict[str, Any],
    publication_reference: dict[str, Any],
    historical: dict[str, Any],
    observed: dict[str, Any],
    path_access: dict[str, Any],
    source_audit: dict[str, Any],
    traffic: dict[str, int],
    fixture: dict[str, Any],
    external: dict[str, Any],
    adapter_conformance_passed: bool,
    privacy_passed: bool,
    public_schema_passed: bool,
    license_boundary_passed: bool,
    governance: dict[str, Any],
) -> list[dict[str, Any]]:
    case_count = int(fixture["case_count"])
    fixture_passed = (
        fixture["candidate_expected_selection_match_cases"] == case_count
        and fixture["control_expected_selection_match_cases"] == case_count
        and fixture["lineage_invariant_cases"] == case_count
        and fixture["projection_invariant_cases"] == case_count
        and fixture["replay_invariant_cases"] == case_count
        and fixture["stage_invariant_cases"] == case_count
        and fixture["evaluator_only_fields_reached_candidate"] is False
        and fixture["conformance_registry"]["registry_complete"] is True
        and fixture["conformance_registry"]["registered_requirement_count"]
        == len(EXPECTED_CONFORMANCE_REQUIREMENT_IDS)
        and fixture["source_capability_audit_passed"] is True
        and fixture["conformance_receipt"]["status"] == "passed"
        and fixture["conformance_receipt"]["collected"] == fixture["conformance_receipt"]["passed"]
        and fixture["conformance_receipt"]["failures"] == 0
        and fixture["conformance_receipt"]["errors"] == 0
        and fixture["conformance_receipt"]["skipped"] == 0
        and fixture["conformance_receipt_covers_registry"] is True
    )
    external_complete = external["complete_locked_assets_present"] is True
    source_lock_passed = (
        source_integrity["computed_source_set_sha256"]
        == source_integrity["declared_source_set_sha256"]
        and source_integrity["authority_file_count"]
        == source_integrity["matched_authority_hash_count"]
        == len(EXPECTED_AUTHORITY_PATHS)
        and source_integrity["source_set_byte_authority"] is True
        and source_audit["locked_module_count"] == len(LOCKED_MODULE_PATHS)
        and source_audit["locked_module_origin_hash_passed"] is True
        and source_audit["exact_byte_module_loader_audit_passed"] is True
        and publication_reference["runner_verified_commit_binding"] is False
        and publication_reference["verification_status"] == "not_verified_by_runner"
        and publication_reference["required_external_verification"]
        == "externally_verified_by_github_process"
    )
    historical_passed = (
        historical.get("validation_passed") is True
        and historical.get("gate_count") == 13
        and historical.get("passed_gate_count") == 8
        and historical.get("release_decision") == "no-go"
    )
    observed_passed = (
        observed.get("classification") == "development_diagnostic_only"
        and observed.get("manifest_case_count") == 24
        and observed.get("manifest_contract_passed") is True
        and observed.get("protocol_contract_passed") is True
        and observed.get("external_confirmation_allowed") is False
        and observed.get("quality_gate_reuse_allowed") is False
    )
    family_passed = (
        fixture["control_projector_v2_invocation_cases"] == case_count
        and fixture["arm_aggregates"]["pre_v3_pipeline_control"]["selection_family"]
        == BASELINE_FAMILY
        and fixture["arm_aggregates"]["pre_v3_pipeline_control"]["projection_family"]
        == CONTROL_PROJECTION_FAMILY
        and fixture["arm_aggregates"]["retrieval_candidate_v3"]["selection_family"]
        == CANDIDATE_FAMILY
        and fixture["arm_aggregates"]["retrieval_candidate_v3"]["projection_family"]
        == CANDIDATE_PROJECTION_FAMILY
        and source_audit["answer_blind_candidate_interface_passed"] is True
    )
    return [
        {
            "number": 1,
            "name": "historical_source_and_asset_locks",
            "passed": source_lock_passed,
        },
        {
            "number": 2,
            "name": "phase11_8_8_8_of_13_no_go_unchanged",
            "passed": historical_passed,
        },
        {
            "number": 3,
            "name": "observed_24_cases_development_diagnostic_only",
            "passed": observed_passed,
        },
        {
            "number": 4,
            "name": "phase12_zero_access",
            "passed": path_access["passed"] is True
            and path_access["phase12_path_access_count"] == 0
            and path_access["outside_source_set_path_count"] == 0,
        },
        {
            "number": 5,
            "name": "zero_traffic_model_secret_and_live_cache",
            "passed": all(value == 0 for value in traffic.values())
            and source_audit["passed"] is True
            and source_audit["forbidden_capability_violation_count"] == 0,
        },
        {
            "number": 6,
            "name": "single_frozen_answer_blind_v3",
            "passed": family_passed and fixture["evaluator_only_fields_reached_candidate"] is False,
        },
        {
            "number": 7,
            "name": "five_stage_lineage_and_projection_invariants",
            "passed": fixture["lineage_invariant_cases"] == case_count
            and fixture["projection_invariant_cases"] == case_count
            and fixture["stage_invariant_cases"] == case_count,
        },
        {
            "number": 8,
            "name": "two_cold_replays_per_arm_identical",
            "passed": fixture["replay_invariant_cases"] == case_count
            and fixture["in_process_replays_per_arm"] >= 2
            and fixture["independent_process_replay_status"] == "required_workflow_cmp",
        },
        {
            "number": 9,
            "name": "local_conformance_and_adversarial_fixtures",
            "passed": fixture_passed and adapter_conformance_passed,
        },
        {
            "number": 10,
            "name": "bright_assets_and_coverage_complete",
            "passed": external_complete,
            "status": "evaluated" if external_complete else "not_evaluated",
        },
        {
            "number": 11,
            "name": "browsecomp_plus_assets_and_coverage_complete",
            "passed": external_complete,
            "status": "evaluated" if external_complete else "not_evaluated",
        },
        {
            "number": 12,
            "name": "metric_implementation_oracles",
            "passed": adapter_conformance_passed,
        },
        {
            "number": 13,
            "name": "bright_ndcg10_delta_at_least_0_010",
            "passed": False,
            "status": "not_evaluated",
        },
        {
            "number": 14,
            "name": "browsecomp_plus_ndcg10_delta_at_least_0_010",
            "passed": False,
            "status": "not_evaluated",
        },
        {
            "number": 15,
            "name": "mean_ndcg10_delta_at_least_0_020",
            "passed": False,
            "status": "not_evaluated",
        },
        {
            "number": 16,
            "name": "recall20_non_regression_per_suite",
            "passed": False,
            "status": "not_evaluated",
        },
        {
            "number": 17,
            "name": "projected_relevant_retention_at_least_0_990",
            "passed": False,
            "status": "not_evaluated",
        },
        {
            "number": 18,
            "name": "aggregate_only_privacy_and_license_boundary",
            "passed": privacy_passed and public_schema_passed and license_boundary_passed,
        },
        {
            "number": 19,
            "name": "product_release_and_governance_boundaries_unchanged",
            "passed": governance["passed"] is True
            and governance["phase11_9_authorized"] is False
            and governance["phase12_authorized"] is False
            and governance["pull_request_state_verified_by_runner"] is False
            and governance["pull_request_state_verification"]
            == "externally_verified_by_github_process",
        },
    ]


def _derive_offline_outcome(
    gates: list[dict[str, Any]],
    external: dict[str, Any],
) -> str:
    gate_by_number = {
        int(gate["number"]): bool(gate["passed"])
        for gate in gates
        if isinstance(gate, dict) and "number" in gate and "passed" in gate
    }
    if set(gate_by_number) != set(range(1, EXPECTED_GATE_COUNT + 1)):
        return "invalid"
    if not all(gate_by_number[number] for number in LOCAL_GATE_NUMBERS):
        return "invalid"
    suite_statuses = external.get("suite_statuses")
    external_absent = (
        external.get("status") == "external_evaluation_not_run"
        and isinstance(suite_statuses, dict)
        and set(suite_statuses) == set(EXPECTED_EXTERNAL_SUITES)
        and all(
            isinstance(status, dict) and status.get("status") == "not_evaluated"
            for status in suite_statuses.values()
        )
    )
    if external_absent:
        return "engineering_conformance_only"
    if all(gate_by_number[number] for number in EXTERNAL_GATE_NUMBERS):
        return "offline_engineering_pass"
    return "external_fail"


def _decision_payload(
    gates: list[dict[str, Any]],
    external: dict[str, Any],
) -> dict[str, Any]:
    offline_outcome = _derive_offline_outcome(gates, external)
    return {
        "external_quality_passed": offline_outcome == "offline_engineering_pass",
        "gate_count": EXPECTED_GATE_COUNT,
        "merge_allowed": False,
        "offline_outcome": offline_outcome,
        "passed_gate_count": sum(bool(gate["passed"]) for gate in gates),
        "phase11_9_authorized": False,
        "phase12_authorized": False,
        "product_defaults_change_allowed": False,
        "pull_request_remains_draft_required": True,
        "pull_request_state_verified_by_runner": False,
        "pull_request_state_verification_required": ("externally_verified_by_github_process"),
        "release_allowed": False,
        "release_decision": "no-go",
        "superiority_claim_allowed": False,
    }


def _assemble_report(
    pre_decision: dict[str, Any],
    gates: list[dict[str, Any]],
    privacy: dict[str, int | bool],
    public_schema: dict[str, int | bool],
) -> dict[str, Any]:
    return {
        **pre_decision,
        "decision": _decision_payload(gates, pre_decision["external_evaluation"]),
        "gates": gates,
        "privacy": privacy,
        "public_schema": public_schema,
        "resource_diagnostics": {
            "build_time_seconds": "not_applicable_without_external_assets",
            "index_bytes": "not_applicable_without_external_assets",
            "measurement_status": "not_applicable_without_external_assets",
            "peak_resident_memory_bytes": "not_applicable_without_external_assets",
            "query_time_seconds": "not_applicable_without_external_assets",
        },
    }


def build_report(lock_commit_sha: str) -> dict[str, Any]:
    """Build one deterministic aggregate-only Phase 11.8.9 result."""

    _require(
        LOCK_COMMIT_PATTERN.fullmatch(lock_commit_sha) is not None,
        "invalid_lock_commit_sha",
    )
    accessed_paths: set[str] = set()
    source_bytes, manifest_raw, source_locks, source_integrity = _load_source_locks(
        accessed_paths,
    )
    _require(
        HISTORICAL_RESULT_PATH in source_bytes
        and RETRIEVAL_FIXTURE_PATH in source_bytes
        and "benchmarks/data/phase11_7_fresh_confirmation_v1.json" in source_bytes
        and "docs/benchmark-protocol-v25.md" in source_bytes
        and "tests/test_phase11_8_9_retrieval_candidate.py" in source_bytes,
        "required_authority_source_missing",
    )
    module_audit = _bind_locked_runtime(
        source_bytes,
        str(source_integrity["computed_source_set_sha256"]),
    )
    historical = _historical_boundary(source_bytes[HISTORICAL_RESULT_PATH])
    observed = _observed_development_boundary(
        source_bytes["benchmarks/data/phase11_7_fresh_confirmation_v1.json"],
        source_bytes["docs/benchmark-protocol-v25.md"],
    )
    source_audit = {
        **_audit_executable_sources(source_bytes),
        **module_audit,
    }
    test_source_bytes = (
        source_bytes["tests/test_phase11_8_9_retrieval_candidate.py"],
        source_bytes["tests/test_phase11_8_9_external_eval.py"],
        source_bytes["tests/test_phase11_8_9_offline_retrieval_recovery.py"],
    )
    fixture_payload = json.loads(source_bytes[RETRIEVAL_FIXTURE_PATH])
    _registry_summary, registered_test_names = _validate_conformance_registry(
        fixture_payload,
        test_source_bytes,
    )
    conformance_receipt = _run_conformance_receipt(
        str(source_integrity["computed_source_set_sha256"]),
        registered_test_names,
        source_bytes,
        manifest_raw,
    )
    fixture = _run_retrieval_fixtures(
        source_bytes[RETRIEVAL_FIXTURE_PATH],
        test_source_bytes,
        source_audit,
        conformance_receipt,
    )
    external, adapter_conformance_passed, license_boundary_passed = _external_status(
        accessed_paths,
    )
    path_access = _path_access_audit(accessed_paths, source_bytes)
    governance = _governance_audit(set(source_bytes))
    publication_reference = {
        "commit_sha": lock_commit_sha,
        "required_external_verification": "externally_verified_by_github_process",
        "runner_verified_commit_binding": False,
        "verification_status": "not_verified_by_runner",
    }
    traffic = dict(ZERO_TRAFFIC)
    traffic["bound_secrets"] = _bound_secret_count(os.environ)

    pre_decision = {
        "benchmark": BENCHMARK_NAME,
        "external_evaluation": external,
        "fixture_evaluation": fixture,
        "governance": governance,
        "historical_boundary": historical,
        "observed_development_boundary": observed,
        "path_access_audit": path_access,
        "publication_reference": publication_reference,
        "schema_version": SCHEMA_VERSION,
        "source_capability_audit": source_audit,
        "source_integrity": source_integrity,
        "source_locks": source_locks,
        "traffic": traffic,
    }
    preliminary_privacy = _privacy_audit(pre_decision)
    preliminary_schema = _public_schema_audit(pre_decision)
    preliminary_gates = _gates(
        source_integrity=source_integrity,
        publication_reference=publication_reference,
        historical=historical,
        observed=observed,
        path_access=path_access,
        source_audit=source_audit,
        traffic=traffic,
        fixture=fixture,
        external=external,
        adapter_conformance_passed=adapter_conformance_passed,
        privacy_passed=bool(preliminary_privacy["passed"]),
        public_schema_passed=bool(preliminary_schema["passed"]),
        license_boundary_passed=license_boundary_passed,
        governance=governance,
    )
    _require(
        len(preliminary_gates) == EXPECTED_GATE_COUNT,
        "incorrect_gate_count",
    )
    draft = _assemble_report(
        pre_decision,
        preliminary_gates,
        preliminary_privacy,
        preliminary_schema,
    )
    final_audit = _audit_final_public_payload(draft)
    gates = _gates(
        source_integrity=source_integrity,
        publication_reference=publication_reference,
        historical=historical,
        observed=observed,
        path_access=path_access,
        source_audit=source_audit,
        traffic=traffic,
        fixture=fixture,
        external=external,
        adapter_conformance_passed=adapter_conformance_passed,
        privacy_passed=bool(final_audit["privacy"]["passed"]),
        public_schema_passed=bool(final_audit["public_schema"]["passed"]),
        license_boundary_passed=license_boundary_passed,
        governance=governance,
    )
    report = _assemble_report(
        pre_decision,
        gates,
        final_audit["privacy"],
        final_audit["public_schema"],
    )
    verification = _audit_final_public_payload(report)
    _require(
        verification == final_audit,
        "final_public_payload_audit_not_stable",
    )
    return report


def run(*, lock_commit_sha: str) -> dict[str, Any]:
    """Public deterministic runner used by tests and the read-only workflow."""

    first = build_report(lock_commit_sha)
    second = build_report(lock_commit_sha)
    _require(
        canonical_json_bytes(first) == canonical_json_bytes(second),
        "cold_replay_result_mismatch",
    )
    return first


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock-commit-sha",
        required=True,
        help=(
            "40-character publication commit reference; the runner does not "
            "authenticate its GitHub binding."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination for the aggregate-only canonical JSON result.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    report = run(lock_commit_sha=arguments.lock_commit_sha)
    arguments.output.write_bytes(canonical_json_bytes(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
