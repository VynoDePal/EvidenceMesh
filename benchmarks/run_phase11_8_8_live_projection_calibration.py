#!/usr/bin/env python3
"""Run the separately authorized Phase 11.8.8 Tavily-only calibration.

This hardened wrapper intentionally leaves the historical v23 runner unchanged.
It validates an explicit dependency manifest, reserves the output exclusively,
counts both logical provider calls and actual HTTP attempts, stops on the first
bounded provider failure, and publishes aggregate-only diagnostics.

Check-only mode reads frozen public files only. It does not inspect environment
variables, create an HTTP client, load the private evaluation dataset, or write
an output file.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from benchmarks import run_phase11_8_8_projection_calibration as locked
except ModuleNotFoundError:
    import run_phase11_8_8_projection_calibration as locked  # type: ignore[no-redef]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-8-live-projection-calibration-v2"
DEPENDENCY_MANIFEST_NAME = "evidencemesh-phase11-8-8-live-projection-dependency-locks-v1"
DEPENDENCY_MANIFEST_PATH = (
    REPOSITORY_ROOT / "benchmarks/data/phase11_8_8_live_projection_dependency_locks_v1.json"
)

# Filled only after the non-circular dependency manifest is committed. The
# manifest deliberately excludes this runner; the protocol/workflow lock the
# runner itself.
LOCKED_DEPENDENCY_MANIFEST_SHA256 = (
    "0d6ee7f91689fc2679ee0e5c6a2857d25219d5a71cd559d248875d1074693a00"
)

EXPECTED_CASE_COUNT = 24
MAXIMUM_LOGICAL_CALLS = 24
MAXIMUM_HTTP_ATTEMPTS = 24
PROVIDER_MAX_RESULTS = 20
SELECTION_LIMIT = 20
MAX_PER_DOMAIN = 3
EVIDENCE_BUDGET_CHARS = 12_000
MAX_BLOCK_CHARS = 1_500
MIN_BLOCK_CHARS = 192
PROJECTION_REPLAYS = 3
RETRIEVAL_PAUSE_SECONDS = 0.5
PROVIDER_WALL_SECONDS = 15.0
OUTER_WALL_SECONDS = 30.0
CONNECT_SECONDS = 5.0
READ_SECONDS = 12.0
WRITE_SECONDS = 10.0
POOL_SECONDS = 5.0

MINIMUM_SELECTED_HITS = 20
MINIMUM_V2_HITS = 20
MINIMUM_V2_RETENTION = 0.95
MINIMUM_PAIRED_NET_GAIN = 2

SOURCE_MANIFEST_REQUIRED_PATHS = frozenset(
    {
        "benchmarks/__init__.py",
        "benchmarks/data/phase11_7_fresh_confirmation_v1.json",
        "benchmarks/data/phase11_8_8_offline_projection_fixtures_v1.json",
        "benchmarks/data/phase12_untouched_reserve_v1.json",
        "benchmarks/phase11_7_dataset.py",
        "benchmarks/phase11_8_2_candidate.py",
        "benchmarks/phase11_8_8_projection_candidate.py",
        "benchmarks/results/phase11_8_3_factorial_2026-07-30.json",
        "benchmarks/run_end_to_end_phase10.py",
        "benchmarks/run_live_retrieval.py",
        "benchmarks/run_phase11_5_quality_recovery.py",
        "benchmarks/run_phase11_7_fresh_confirmation.py",
        "benchmarks/run_phase11_8_8_projection_calibration.py",
        "benchmarks/run_phase11_8_recovery.py",
        "benchmarks/run_phase11_calibration.py",
        "docs/benchmark-protocol-v23.md",
        "pyproject.toml",
        "src/evidencemesh/__init__.py",
        "src/evidencemesh/__main__.py",
        "src/evidencemesh/benchmark.py",
        "src/evidencemesh/cache.py",
        "src/evidencemesh/citations.py",
        "src/evidencemesh/cli.py",
        "src/evidencemesh/config.py",
        "src/evidencemesh/engine.py",
        "src/evidencemesh/errors.py",
        "src/evidencemesh/extraction.py",
        "src/evidencemesh/fetcher.py",
        "src/evidencemesh/mcp_server.py",
        "src/evidencemesh/models.py",
        "src/evidencemesh/query.py",
        "src/evidencemesh/ranking.py",
        "src/evidencemesh/reliability.py",
        "src/evidencemesh/routing.py",
        "src/evidencemesh/telemetry.py",
        "src/evidencemesh/urls.py",
        "src/evidencemesh/providers/__init__.py",
        "src/evidencemesh/providers/arxiv.py",
        "src/evidencemesh/providers/base.py",
        "src/evidencemesh/providers/brave.py",
        "src/evidencemesh/providers/crossref.py",
        "src/evidencemesh/providers/ddgs.py",
        "src/evidencemesh/providers/exa.py",
        "src/evidencemesh/providers/factory.py",
        "src/evidencemesh/providers/firecrawl.py",
        "src/evidencemesh/providers/github.py",
        "src/evidencemesh/providers/mwmbl.py",
        "src/evidencemesh/providers/openalex.py",
        "src/evidencemesh/providers/searxng.py",
        "src/evidencemesh/providers/tavily.py",
        "src/evidencemesh/providers/wiby.py",
        "src/evidencemesh/providers/wikipedia.py",
        "src/evidencemesh/providers/yacy.py",
        "uv.lock",
    }
)

BOUNDED_FAILURE_KINDS = frozenset(
    {
        "accounting_mismatch",
        "circuit_open",
        "connection_error",
        "connect_timeout",
        "dns_error",
        "http_attempt_cap",
        "http_status",
        "http_status_400",
        "http_status_401",
        "http_status_403",
        "http_status_404",
        "http_status_408",
        "http_status_409",
        "http_status_422",
        "http_status_429",
        "http_status_500",
        "http_status_502",
        "http_status_503",
        "http_status_504",
        "httpx_timeout_unknown",
        "invalid_json",
        "invalid_response",
        "invalid_response_encoding",
        "network_error",
        "protocol_error",
        "provider_error",
        "provider_wall_timeout",
        "projection_invariant_failure",
        "read_timeout",
        "unexpected_provider_failure",
        "write_timeout",
    }
)

GATE_NAMES = (
    "historical_dependency_and_commit_a_locks",
    "one_shot_authorization_lineage",
    "dataset_selection_and_phase12_non_use",
    "complete_exact_24_tavily_accounting",
    "fail_fast_no_rerun_cache_or_nonretrieval_traffic",
    "shared_selected_packet_identity_24_of_24",
    "v2_projection_invariants_24_of_24",
    "selected_proxy_coverage_at_least_20_of_24",
    "v2_proxy_coverage_at_least_20_of_24",
    "v2_selected_retention_at_least_95_percent",
    "v2_paired_net_gain_vs_equal_at_least_2",
    "v2_paired_net_gain_vs_v1_at_least_2",
    "public_privacy_and_governance_boundaries",
)

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


class LiveCalibrationError(RuntimeError):
    """A fail-closed calibration error with no provider-controlled message."""


class HTTPAttemptLimitError(LiveCalibrationError):
    """The HTTP attempt cap prevented a further dispatch."""


class NonTavilyAttemptError(LiveCalibrationError):
    """A non-Tavily dispatch was blocked before transport."""


class ProviderResponseValidationError(LiveCalibrationError):
    """A privacy-safe, bounded Tavily response validation failure."""

    def __init__(self, failure_kind: str) -> None:
        if failure_kind not in BOUNDED_FAILURE_KINDS:
            raise ValueError("unbounded provider response failure kind")
        self.failure_kind = failure_kind
        super().__init__(failure_kind)


@dataclass(frozen=True, slots=True)
class DependencyLock:
    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class AuthorizationAttestation:
    attestation_sha256: str
    lock_commit_sha: str
    authorization_commit_sha: str
    workflow_run_attempt: int
    commit_a_locks_verified: bool
    lineage_verified: bool
    no_prior_authorization_run_verified: bool

    @property
    def verified(self) -> bool:
        return (
            self.workflow_run_attempt == 1
            and self.commit_a_locks_verified
            and self.lineage_verified
            and self.no_prior_authorization_run_verified
            and self.lock_commit_sha != self.authorization_commit_sha
        )


@dataclass(frozen=True, slots=True)
class SelectionFacts:
    phase11_selection_count: int
    phase12_reserve_count: int
    selections_disjoint: bool
    loaded_rows_match_phase11_selection: bool
    reserve_rows_selected: int
    reserve_rows_scored: int

    @property
    def passed(self) -> bool:
        return (
            self.phase11_selection_count == EXPECTED_CASE_COUNT
            and self.phase12_reserve_count == 96
            and self.selections_disjoint
            and self.loaded_rows_match_phase11_selection
            and self.reserve_rows_selected == 0
            and self.reserve_rows_scored == 0
        )


@dataclass(slots=True)
class AttemptCounter:
    """Count dispatches and validate Tavily responses without retaining content."""

    maximum: int = MAXIMUM_HTTP_ATTEMPTS
    attempts: int = 0
    responses: int = 0
    validated_200_responses: int = 0
    response_validation_failures: int = 0
    first_failure_kind: str | None = None
    status_counts: Counter[str] | None = None

    def __post_init__(self) -> None:
        self.status_counts = Counter()

    async def on_request(self, request: Any) -> None:
        url = request.url
        if url.scheme != "https" or url.host != "api.tavily.com" or url.path != "/search":
            raise NonTavilyAttemptError("non_tavily_http_attempt")
        if self.attempts >= self.maximum:
            raise HTTPAttemptLimitError("http_attempt_cap")
        self.attempts += 1

    async def on_response(self, response: Any) -> None:
        self.responses += 1
        if self.status_counts is None:
            raise RuntimeError("HTTP status accounting is not initialized")
        status_code = int(response.status_code)
        self.status_counts[str(status_code)] += 1
        if self.first_failure_kind is not None:
            raise ProviderResponseValidationError(self.first_failure_kind)
        failure_kind = await _http_response_failure_kind(
            response,
            status_code=status_code,
        )
        if failure_kind is None:
            self.validated_200_responses = min(
                self.maximum,
                self.validated_200_responses + 1,
            )
            return
        self.response_validation_failures = 1
        self.first_failure_kind = failure_kind
        raise ProviderResponseValidationError(failure_kind)


@dataclass(frozen=True, slots=True)
class ArmProjection:
    """All deterministic replays for one answer-blind projection arm."""

    arm: str
    replays: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    outcomes: tuple[dict[str, Any], ...]
    attempted_cases: int
    successful_cases: int
    logical_calls: int
    actual_http_attempts: int
    http_responses: int
    status_counts: dict[str, int]
    failure_kind: str | None
    stopped_on_first_failure: bool
    provider_private_values: tuple[str, ...]


class OutputReservation:
    """Reserve a result path exclusively, then publish with fsync + replace."""

    def __init__(self, output: Path) -> None:
        self.output = output
        self._temporary: Path | None = None
        self._committed = False

    def __enter__(self) -> OutputReservation:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.output,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, b"reserved\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        temporary_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.output.name}.",
            suffix=".tmp",
            dir=self.output.parent,
        )
        os.close(temporary_descriptor)
        self._temporary = Path(temporary_name)
        return self

    def commit(self, payload: Mapping[str, Any]) -> None:
        if self._temporary is None:
            raise RuntimeError("output reservation is not active")
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        with self._temporary.open("wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(self._temporary, self.output)
        self._temporary = None
        directory_descriptor = os.open(self.output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        self._committed = True

    def __exit__(self, *_error: object) -> None:
        if self._temporary is not None:
            self._temporary.unlink(missing_ok=True)
        if not self._committed:
            self.output.unlink(missing_ok=True)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and "\\" not in value
        and not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
        and str(path) == value
    )


async def _http_response_failure_kind(
    response: Any,
    *,
    status_code: int,
) -> str | None:
    """Validate one response while retaining only a bounded categorical result."""

    if status_code != 200:
        candidate = f"http_status_{status_code}"
        return candidate if candidate in BOUNDED_FAILURE_KINDS else "http_status"
    try:
        raw = await response.aread()
    except Exception:
        return "invalid_response"
    try:
        payload = json.loads(raw)
    except UnicodeDecodeError:
        return "invalid_response_encoding"
    except (json.JSONDecodeError, ValueError, TypeError):
        return "invalid_json"
    if not isinstance(payload, dict):
        return "invalid_response"
    results = payload.get("results")
    if not isinstance(results, list):
        return "invalid_response"
    for item in results:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("url"), str)
            or not item["url"].strip()
            or not isinstance(item.get("title"), str)
            or not isinstance(item.get("content"), str)
        ):
            return "invalid_response"
    return None


def validate_dependency_manifest(path: Path) -> tuple[DependencyLock, ...]:
    """Validate the manifest hash, exact path set, and every dependency hash."""

    raw = path.read_bytes()
    expected_manifest_hash = LOCKED_DEPENDENCY_MANIFEST_SHA256
    if not _HEX_SHA256.fullmatch(expected_manifest_hash):
        raise ValueError("dependency manifest checksum lock is unresolved")
    if _sha256(raw) != expected_manifest_hash:
        raise ValueError("dependency manifest checksum changed")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("dependency manifest is not valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "manifest",
        "dependencies",
    }:
        raise ValueError("dependency manifest envelope changed")
    if (
        payload["schema_version"] != 1
        or payload["manifest"] != DEPENDENCY_MANIFEST_NAME
        or not isinstance(payload["dependencies"], dict)
    ):
        raise ValueError("dependency manifest identity changed")
    dependencies = payload["dependencies"]
    if set(dependencies) != SOURCE_MANIFEST_REQUIRED_PATHS:
        missing = sorted(SOURCE_MANIFEST_REQUIRED_PATHS - set(dependencies))
        extra = sorted(set(dependencies) - SOURCE_MANIFEST_REQUIRED_PATHS)
        raise ValueError(f"dependency manifest path set changed; missing={missing}, extra={extra}")

    locks: list[DependencyLock] = []
    root_resolved = REPOSITORY_ROOT.resolve()
    for relative_path in sorted(dependencies):
        expected_hash = dependencies[relative_path]
        if not _is_safe_relative_path(relative_path):
            raise ValueError("dependency manifest contains an unsafe path")
        if not isinstance(expected_hash, str) or not _HEX_SHA256.fullmatch(expected_hash):
            raise ValueError("dependency manifest contains an invalid SHA-256")
        dependency_path = (REPOSITORY_ROOT / relative_path).resolve()
        if dependency_path.parent != root_resolved and root_resolved not in (
            dependency_path.parents
        ):
            raise ValueError("dependency path escapes the repository")
        if _sha256(dependency_path.read_bytes()) != expected_hash:
            raise ValueError(f"locked dependency changed: {relative_path}")
        locks.append(DependencyLock(relative_path, expected_hash))
    return tuple(locks)


def validate_authorization_attestation(path: Path) -> AuthorizationAttestation:
    """Validate the workflow-produced, non-secret one-shot provenance record."""

    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("authorization attestation is not valid JSON") from exc
    required = {
        "schema_version",
        "authorization",
        "repository",
        "pull_request_number",
        "head_branch",
        "workflow_path",
        "lock_commit_sha",
        "authorization_commit_sha",
        "workflow_run_attempt",
        "commit_a_locks_verified",
        "single_parent_verified",
        "subject_verified",
        "marker_verified",
        "two_path_diff_verified",
        "same_repository_head_verified",
        "no_rerun_verified",
        "no_prior_authorization_run_verified",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("authorization attestation schema changed")
    exact_values = {
        "schema_version": 1,
        "authorization": "phase11_8_8_live_projection_calibration_once",
        "repository": "VynoDePal/EvidenceMesh",
        "pull_request_number": 1,
        "head_branch": "agent/evidencemesh-v0.1",
        "workflow_path": (".github/workflows/phase11-8-8-live-projection-calibration.yml"),
        "workflow_run_attempt": 1,
        "commit_a_locks_verified": True,
        "single_parent_verified": True,
        "subject_verified": True,
        "marker_verified": True,
        "two_path_diff_verified": True,
        "same_repository_head_verified": True,
        "no_rerun_verified": True,
        "no_prior_authorization_run_verified": True,
    }
    if any(payload.get(name) != expected for name, expected in exact_values.items()):
        raise ValueError("authorization attestation did not verify the locked workflow")
    lock_commit = payload["lock_commit_sha"]
    authorization_commit = payload["authorization_commit_sha"]
    if (
        not isinstance(lock_commit, str)
        or not re.fullmatch(r"[0-9a-f]{40}", lock_commit)
        or not isinstance(authorization_commit, str)
        or not re.fullmatch(r"[0-9a-f]{40}", authorization_commit)
        or lock_commit == authorization_commit
    ):
        raise ValueError("authorization commit lineage is invalid")
    return AuthorizationAttestation(
        attestation_sha256=_sha256(raw),
        lock_commit_sha=lock_commit,
        authorization_commit_sha=authorization_commit,
        workflow_run_attempt=1,
        commit_a_locks_verified=True,
        lineage_verified=True,
        no_prior_authorization_run_verified=True,
    )


def _historical_validation_arguments() -> argparse.Namespace:
    root = REPOSITORY_ROOT
    return argparse.Namespace(
        protocol=root / "docs/benchmark-protocol-v23.md",
        manifest=root / "benchmarks/data/phase11_7_fresh_confirmation_v1.json",
        reserve_manifest=root / "benchmarks/data/phase12_untouched_reserve_v1.json",
        phase11_8_3_result=(root / "benchmarks/results/phase11_8_3_factorial_2026-07-30.json"),
        candidate_v1=root / "benchmarks/phase11_8_2_candidate.py",
        candidate_v2=root / "benchmarks/phase11_8_8_projection_candidate.py",
        fixture=(root / "benchmarks/data/phase11_8_8_offline_projection_fixtures_v1.json"),
    )


def validate_check_only(path: Path = DEPENDENCY_MANIFEST_PATH) -> dict[str, Any]:
    """Validate all public locks without dataset, secret, network, or output access."""

    dependency_locks = validate_dependency_manifest(path)
    historical = locked.validate_locked_sources(_historical_validation_arguments())
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "status": "check_only_passed",
        "dependency_manifest_sha256": LOCKED_DEPENDENCY_MANIFEST_SHA256,
        "dependency_count": len(dependency_locks),
        "historical_boundary": historical["historical_phase11_8_3_result"],
        "planned_cases": EXPECTED_CASE_COUNT,
        "maximum_logical_calls": MAXIMUM_LOGICAL_CALLS,
        "maximum_http_attempts": MAXIMUM_HTTP_ATTEMPTS,
        "network_requests": 0,
        "provider_calls": 0,
        "tavily_requests": 0,
        "model_requests": 0,
        "gemini_requests": 0,
        "token_count_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
        "cache_reads": 0,
        "cache_writes": 0,
        "follow_up_document_fetches": 0,
        "secrets_read": 0,
        "dataset_opened": False,
        "output_reserved": False,
        "live_authorized": False,
    }


def _case_selectors(value: object, *, expected_count: int) -> tuple[tuple[int, str], ...]:
    if not isinstance(value, list) or len(value) != expected_count:
        raise ValueError("selection count changed")
    selectors: list[tuple[int, str]] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"row_index", "case_id"}
            or isinstance(item["row_index"], bool)
            or not isinstance(item["row_index"], int)
            or item["row_index"] < 0
            or not isinstance(item["case_id"], str)
            or not item["case_id"]
        ):
            raise ValueError("selection entry changed")
        selectors.append((item["row_index"], item["case_id"]))
    if len(set(selectors)) != len(selectors):
        raise ValueError("selection contains duplicates")
    return tuple(selectors)


def derive_selection_facts(
    manifest: Mapping[str, Any],
    reserve_manifest: Mapping[str, Any],
    rows: Sequence[Any],
) -> SelectionFacts:
    """Derive Phase 12 non-use from the selected manifests and loaded row IDs."""

    phase11 = _case_selectors(manifest.get("cases"), expected_count=EXPECTED_CASE_COUNT)
    reserve = _case_selectors(
        reserve_manifest.get("sealed_cases"),
        expected_count=96,
    )
    phase11_indexes = {row_index for row_index, _case_id in phase11}
    reserve_indexes = {row_index for row_index, _case_id in reserve}
    phase11_ids = {case_id for _row_index, case_id in phase11}
    reserve_ids = {case_id for _row_index, case_id in reserve}
    loaded_ids = [str(row.id) for row in rows]
    selections_disjoint = not (phase11_indexes & reserve_indexes or phase11_ids & reserve_ids)
    reserve_rows_selected = len(set(loaded_ids) & reserve_ids)
    return SelectionFacts(
        phase11_selection_count=len(phase11),
        phase12_reserve_count=len(reserve),
        selections_disjoint=selections_disjoint,
        loaded_rows_match_phase11_selection=(
            loaded_ids == [case_id for _row_index, case_id in phase11]
        ),
        reserve_rows_selected=reserve_rows_selected,
        reserve_rows_scored=reserve_rows_selected,
    )


def _bounded_failure_kind(
    response: Any | None,
    *,
    outer_failure: str | None,
) -> str | None:
    if outer_failure:
        return (
            outer_failure
            if outer_failure in BOUNDED_FAILURE_KINDS
            else ("unexpected_provider_failure")
        )
    if response is None:
        return "unexpected_provider_failure"
    metadata = response.metadata
    telemetry = metadata.provider_network_telemetry.get("tavily")
    if telemetry is not None:
        status_codes = sorted(
            status
            for status, count in telemetry.http_status_counts.items()
            if count > 0 and status.startswith(("4", "5"))
        )
        if status_codes:
            candidate = f"http_status_{status_codes[0]}"
            return candidate if candidate in BOUNDED_FAILURE_KINDS else "http_status"
    failure_counts = metadata.provider_failure_kind_counts.get("tavily", {})
    observed = sorted(kind for kind, count in failure_counts.items() if count > 0)
    if observed:
        return (
            observed[0] if observed[0] in BOUNDED_FAILURE_KINDS else "unexpected_provider_failure"
        )
    return None


def _private_provider_values(results: Sequence[Any]) -> tuple[str, ...]:
    values: list[str] = []
    for result in results:
        for attribute in ("title", "url", "snippet", "query"):
            value = getattr(result, attribute, None)
            if isinstance(value, str) and value:
                values.append(value)
    return tuple(values)


def project_packet_arms(
    question: str,
    blocks: tuple[Any, ...],
    *,
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
    projection_replays: int,
) -> tuple[ArmProjection, ...]:
    """Finish every answer-blind arm projection before reference scoring."""

    if projection_replays < 1:
        raise ValueError("projection replay count must be positive")
    projected: list[ArmProjection] = []
    for arm in locked.PROJECTION_ARMS:
        replays = tuple(
            locked.project_blocks(
                arm,
                question,
                blocks,
                evidence_budget_chars=evidence_budget_chars,
                max_block_chars=max_block_chars,
                min_block_chars=min_block_chars,
            )
            for _ in range(projection_replays)
        )
        projected.append(ArmProjection(arm=arm, replays=replays))
    return tuple(projected)


def score_projected_packet(
    row: Any,
    bundle: Any,
    *,
    raw_pool_hash: str,
    projections: tuple[ArmProjection, ...],
    evidence_budget_chars: int,
) -> tuple[dict[str, Any], ...]:
    """Build public outcomes only after all arm projections are immutable."""

    if tuple(projection.arm for projection in projections) != tuple(locked.PROJECTION_ARMS) or any(
        not projection.replays for projection in projections
    ):
        raise ValueError("projection arm set is incomplete")

    outcomes: list[dict[str, Any]] = []
    phase11_8 = locked.phase11_8
    for projection in projections:
        arm = projection.arm
        included = projection.replays[0]
        packet_hashes = {
            phase11_8.prompt_packet_sha256(projected) for projected in projection.replays
        }
        rendered_chars = locked.rendered_evidence_chars(included)
        outcomes.append(
            {
                "case_id": row.id,
                "arm": locked.projection_family(arm),
                "status": bundle.status,
                "available": bundle.available,
                "raw_result_count": bundle.raw_result_count,
                "fused_result_count": bundle.fused_result_count,
                "selected_result_count": bundle.selected_result_count,
                "prompt_result_count": len(included),
                "unique_domains": bundle.unique_domains,
                "selected_tavily_count": bundle.selected_tavily_count,
                "prompt_tavily_count": sum("tavily" in block.providers for block in included),
                "answer_key_in_selected_evidence": phase11_8.answer_covered(
                    row.answers,
                    (block.text for block in bundle.blocks),
                ),
                "answer_key_in_prompt_evidence": phase11_8.answer_covered(
                    row.answers,
                    (block.text for block in included),
                ),
                "raw_pool_sha256": raw_pool_hash,
                "selected_packet_sha256": phase11_8.prompt_packet_sha256(bundle.blocks),
                "prompt_packet_sha256": phase11_8.prompt_packet_sha256(included),
                "rendered_evidence_chars": rendered_chars,
                "budget_compliant": rendered_chars <= evidence_budget_chars,
                "budget_gate_applicable": arm != locked.EQUAL_CAP_ARM,
                "historical_equal_cap_over_budget": (
                    arm == locked.EQUAL_CAP_ARM and rendered_chars > evidence_budget_chars
                ),
                "deterministic_replays": len(packet_hashes) == 1,
                "replay_count": len(projection.replays),
                "metadata_preserved": locked.projection_metadata_preserved(
                    bundle.blocks,
                    included,
                ),
                "source_text_preserved": locked.projection_text_is_source_preserving(
                    bundle.blocks,
                    included,
                ),
                "retrieval_latency_ms": bundle.retrieval_latency_ms,
                "error_kind": bundle.error_kind,
            }
        )
    return tuple(outcomes)


def project_and_score_packet(
    row: Any,
    bundle: Any,
    *,
    raw_pool_hash: str,
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
    projection_replays: int,
) -> tuple[dict[str, Any], ...]:
    """Keep the answer-blind projection phase ahead of the scoring phase."""

    projections = project_packet_arms(
        row.question,
        bundle.blocks,
        evidence_budget_chars=evidence_budget_chars,
        max_block_chars=max_block_chars,
        min_block_chars=min_block_chars,
        projection_replays=projection_replays,
    )
    return score_projected_packet(
        row,
        bundle,
        raw_pool_hash=raw_pool_hash,
        projections=projections,
        evidence_budget_chars=evidence_budget_chars,
    )


async def retrieve_and_project(
    rows: Sequence[Any],
    *,
    tavily_api_key: str,
    progress: bool,
) -> RetrievalResult:
    """Retrieve sequentially, account exactly, and stop on the first failure."""

    phase11_8 = locked.phase11_8
    counter = AttemptCounter()
    timeout = phase11_8.httpx.Timeout(
        connect=CONNECT_SECONDS,
        read=READ_SECONDS,
        write=WRITE_SECONDS,
        pool=POOL_SECONDS,
    )
    client = phase11_8.httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": "EvidenceMesh-Phase11.8.8-live-calibration/1"},
        follow_redirects=False,
        event_hooks={
            "request": [counter.on_request],
            "response": [counter.on_response],
        },
    )
    settings = phase11_8.Settings(
        deployment_profile=phase11_8.DeploymentProfile.QUALITY,
        enabled_providers=["tavily"],
        tavily_api_key=tavily_api_key,
        quality_primary_provider="tavily",
        quality_primary_provider_share=1.0,
        cache_path=Path(":memory:"),
        request_timeout_seconds=PROVIDER_WALL_SECONDS,
        provider_connect_timeout_seconds=CONNECT_SECONDS,
        provider_read_timeout_seconds=READ_SECONDS,
        provider_write_timeout_seconds=WRITE_SECONDS,
        provider_pool_timeout_seconds=POOL_SECONDS,
        max_concurrency=1,
        respect_robots_txt=False,
    )
    recorder = phase11_8.RawResultRecorder()
    engine = phase11_8.EvidenceMesh(settings, client=client)
    providers = [
        phase11_8.CountingRecordingProvider(provider, recorder) for provider in engine.providers
    ]
    engine.providers = providers

    outcomes: list[dict[str, Any]] = []
    private_values: list[str] = []
    logical_calls = 0
    successful_cases = 0
    failure_kind: str | None = None
    attempted_cases = 0
    try:
        for index, row in enumerate(rows):
            if logical_calls >= MAXIMUM_LOGICAL_CALLS:
                failure_kind = "accounting_mismatch"
                break
            if index and RETRIEVAL_PAUSE_SECONDS:
                await asyncio.sleep(RETRIEVAL_PAUSE_SECONDS)
            attempted_cases += 1
            recorder.reset()
            logical_before = sum(provider.query_calls for provider in providers)
            actual_before = counter.attempts
            response = None
            outer_failure: str | None = None
            started = time.perf_counter()
            try:
                async with asyncio.timeout(OUTER_WALL_SECONDS):
                    response = await engine.search(
                        phase11_8.SearchRequest(
                            query=row.question,
                            limit=PROVIDER_MAX_RESULTS,
                            profile=phase11_8.SearchProfile.WEB,
                            fetch_content=False,
                            max_per_domain=MAX_PER_DOMAIN,
                            use_cache=False,
                        )
                    )
            except HTTPAttemptLimitError:
                outer_failure = "http_attempt_cap"
            except ProviderResponseValidationError as exc:
                outer_failure = exc.failure_kind
            except TimeoutError:
                outer_failure = "provider_wall_timeout"
            except Exception:
                outer_failure = "unexpected_provider_failure"
            elapsed_ms = round((time.perf_counter() - started) * 1_000, 3)
            raw_results = recorder.all_results()
            private_values.extend(_private_provider_values(raw_results))

            logical_delta = sum(provider.query_calls for provider in providers) - logical_before
            actual_delta = counter.attempts - actual_before
            logical_calls += logical_delta
            accounting_failure = (
                logical_delta != 1
                or actual_delta not in {0, 1}
                or logical_calls > MAXIMUM_LOGICAL_CALLS
                or counter.attempts > MAXIMUM_HTTP_ATTEMPTS
            )
            if response is not None:
                telemetry = response.metadata.provider_network_telemetry.get("tavily")
                accounting_failure = accounting_failure or (
                    telemetry is None
                    or telemetry.logical_calls != logical_delta
                    or telemetry.http_attempts != actual_delta
                )
            case_failure = counter.first_failure_kind or (
                "accounting_mismatch"
                if accounting_failure
                else _bounded_failure_kind(
                    response,
                    outer_failure=outer_failure,
                )
            )

            if case_failure is not None:
                failure_kind = case_failure
                break
            try:
                bundle = phase11_8.replay_arm(
                    row.id,
                    row.question,
                    raw_results,
                    arm=phase11_8.EXPANDED_ARM,
                    limit=SELECTION_LIMIT,
                    max_per_domain=MAX_PER_DOMAIN,
                    retrieval_latency_ms=elapsed_ms,
                    error_kind=None,
                )
                raw_pool_hash = phase11_8.raw_pool_sha256(raw_results)
                case_outcomes = project_and_score_packet(
                    row,
                    bundle,
                    raw_pool_hash=raw_pool_hash,
                    evidence_budget_chars=EVIDENCE_BUDGET_CHARS,
                    max_block_chars=MAX_BLOCK_CHARS,
                    min_block_chars=MIN_BLOCK_CHARS,
                    projection_replays=PROJECTION_REPLAYS,
                )
            except Exception:
                failure_kind = "projection_invariant_failure"
                break
            outcomes.extend(case_outcomes)
            successful_cases += 1
            if progress:
                print(
                    f"[retrieval {attempted_cases}/{EXPECTED_CASE_COUNT}] completed",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        await engine.aclose()
        await client.aclose()

    return RetrievalResult(
        outcomes=tuple(outcomes),
        attempted_cases=attempted_cases,
        successful_cases=successful_cases,
        logical_calls=logical_calls,
        actual_http_attempts=counter.attempts,
        http_responses=counter.responses,
        status_counts=dict(sorted((counter.status_counts or {}).items())),
        failure_kind=failure_kind,
        stopped_on_first_failure=(failure_kind is not None),
        provider_private_values=tuple(private_values),
    )


def _ratio(numerator: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 6) if denominator else None,
    }


def aggregate_projection(
    outcomes: Sequence[dict[str, Any]],
) -> dict[str, int | float | None]:
    by_arm = {
        arm: [outcome for outcome in outcomes if outcome["arm"] == arm]
        for arm in locked.PROJECTION_ARMS
    }
    selected_hits = sum(
        bool(outcome["answer_key_in_selected_evidence"]) for outcome in by_arm[locked.V2_ARM]
    )
    equal_hits = sum(
        bool(outcome["answer_key_in_prompt_evidence"]) for outcome in by_arm[locked.EQUAL_CAP_ARM]
    )
    v1_hits = sum(
        bool(outcome["answer_key_in_prompt_evidence"]) for outcome in by_arm[locked.V1_ARM]
    )
    v2_hits = sum(
        bool(outcome["answer_key_in_prompt_evidence"]) for outcome in by_arm[locked.V2_ARM]
    )
    identity = locked.packet_identity(list(outcomes))
    paired_equal = locked.paired_projection_metrics(
        list(outcomes),
        candidate_arm=locked.V2_ARM,
        baseline_arm=locked.EQUAL_CAP_ARM,
    )
    paired_v1 = locked.paired_projection_metrics(
        list(outcomes),
        candidate_arm=locked.V2_ARM,
        baseline_arm=locked.V1_ARM,
    )
    retention = locked.selected_proxy_retention(
        list(outcomes),
        arm=locked.V2_ARM,
    )
    return {
        "scored_case_count": len(by_arm[locked.V2_ARM]),
        "available_case_count": sum(
            bool(outcome["available"]) for outcome in by_arm[locked.V2_ARM]
        ),
        "selected_proxy_hits": selected_hits,
        "equal_cap_prompt_proxy_hits": equal_hits,
        "v1_prompt_proxy_hits": v1_hits,
        "v2_prompt_proxy_hits": v2_hits,
        "v2_retention_numerator": int(retention["numerator"]),
        "v2_retention_denominator": int(retention["denominator"]),
        "v2_retention_rate": (float(retention["rate"]) if retention["rate"] is not None else None),
        "v2_vs_equal_candidate_wins": int(paired_equal["candidate_wins"]),
        "v2_vs_equal_baseline_wins": int(paired_equal["baseline_wins"]),
        "v2_vs_equal_net_gain": int(paired_equal["net_gain"]),
        "v2_vs_v1_candidate_wins": int(paired_v1["candidate_wins"]),
        "v2_vs_v1_baseline_wins": int(paired_v1["baseline_wins"]),
        "v2_vs_v1_net_gain": int(paired_v1["net_gain"]),
        "raw_pool_matching_cases": int(identity["raw_pool_matching_cases"]),
        "selected_packet_matching_cases": int(identity["selected_packet_matching_cases"]),
        "projection_invariant_cases": int(identity["deterministic_metadata_source_cases"]),
        "candidate_budget_cases": int(identity["candidate_budget_cases"]),
        "equal_cap_over_budget_cases": int(identity["equal_cap_over_budget_cases"]),
    }


def _decision(
    *,
    dependencies_valid: bool,
    authorization: AuthorizationAttestation,
    selections: SelectionFacts,
    retrieval: RetrievalResult,
    projection: Mapping[str, int | float | None],
    privacy_passed: bool,
) -> dict[str, Any]:
    complete = (
        retrieval.failure_kind is None
        and retrieval.attempted_cases == EXPECTED_CASE_COUNT
        and retrieval.successful_cases == EXPECTED_CASE_COUNT
        and int(projection["scored_case_count"] or 0) == EXPECTED_CASE_COUNT
    )
    exact_complete_traffic = (
        complete
        and retrieval.logical_calls == EXPECTED_CASE_COUNT
        and retrieval.actual_http_attempts == EXPECTED_CASE_COUNT
        and retrieval.http_responses == EXPECTED_CASE_COUNT
        and retrieval.logical_calls == retrieval.actual_http_attempts
        and retrieval.logical_calls <= MAXIMUM_LOGICAL_CALLS
        and retrieval.actual_http_attempts <= MAXIMUM_HTTP_ATTEMPTS
    )
    fixed_zero_counters = {
        "other_provider_requests": 0,
        "model_requests": 0,
        "gemini_requests": 0,
        "token_count_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
        "cache_reads": 0,
        "cache_writes": 0,
        "follow_up_document_fetches": 0,
    }
    gates = {
        "historical_dependency_and_commit_a_locks": (
            dependencies_valid and authorization.commit_a_locks_verified
        ),
        "one_shot_authorization_lineage": authorization.verified,
        "dataset_selection_and_phase12_non_use": selections.passed,
        "complete_exact_24_tavily_accounting": exact_complete_traffic,
        "fail_fast_no_rerun_cache_or_nonretrieval_traffic": (
            authorization.workflow_run_attempt == 1
            and (retrieval.failure_kind is None or retrieval.stopped_on_first_failure)
            and all(value == 0 for value in fixed_zero_counters.values())
        ),
        "shared_selected_packet_identity_24_of_24": (
            int(projection["raw_pool_matching_cases"] or 0) == EXPECTED_CASE_COUNT
            and int(projection["selected_packet_matching_cases"] or 0) == EXPECTED_CASE_COUNT
        ),
        "v2_projection_invariants_24_of_24": (
            int(projection["projection_invariant_cases"] or 0) == EXPECTED_CASE_COUNT
            and int(projection["candidate_budget_cases"] or 0) == EXPECTED_CASE_COUNT
        ),
        "selected_proxy_coverage_at_least_20_of_24": (
            int(projection["selected_proxy_hits"] or 0) >= MINIMUM_SELECTED_HITS
        ),
        "v2_proxy_coverage_at_least_20_of_24": (
            int(projection["v2_prompt_proxy_hits"] or 0) >= MINIMUM_V2_HITS
        ),
        "v2_selected_retention_at_least_95_percent": (
            projection["v2_retention_rate"] is not None
            and float(projection["v2_retention_rate"]) >= MINIMUM_V2_RETENTION
        ),
        "v2_paired_net_gain_vs_equal_at_least_2": (
            int(projection["v2_vs_equal_net_gain"] or 0) >= MINIMUM_PAIRED_NET_GAIN
        ),
        "v2_paired_net_gain_vs_v1_at_least_2": (
            int(projection["v2_vs_v1_net_gain"] or 0) >= MINIMUM_PAIRED_NET_GAIN
        ),
        "public_privacy_and_governance_boundaries": privacy_passed,
    }
    if tuple(gates) != GATE_NAMES:
        raise RuntimeError("decision gate order or identity changed")
    candidate_passed = all(gates.values())
    if retrieval.failure_kind is not None:
        diagnostic_status = "provider_failure_inconclusive"
    elif int(projection["selected_proxy_hits"] or 0) < MINIMUM_SELECTED_HITS:
        diagnostic_status = "retrieval_limited_inconclusive"
    elif candidate_passed:
        diagnostic_status = "projection_calibration_pass"
    else:
        diagnostic_status = "projection_candidate_fail"
    return {
        "gate_count": len(gates),
        "passed_gate_count": sum(gates.values()),
        "gates": [{"name": name, "passed": passed} for name, passed in gates.items()],
        "projection_candidate_passed": candidate_passed,
        "diagnostic_status": diagnostic_status,
        "phase11_9_protocol_may_be_frozen": False,
        "phase12_authorized": False,
        "phase12_executed": False,
        "quality_profile_promoted": False,
        "merge_allowed": False,
        "release_allowed": False,
        "superiority_claim_allowed": False,
        "release_decision": "no-go",
    }


PUBLIC_SCHEMA: dict[str, Any] = {
    "schema_version": int,
    "benchmark": str,
    "run_status": str,
    "dependency_manifest_sha256": str,
    "source_locks": [{"relative_path": str, "sha256": str}],
    "authorization": {
        "attestation_sha256": str,
        "lock_commit_sha": str,
        "authorization_commit_sha": str,
        "workflow_run_attempt": int,
        "verified": bool,
    },
    "dataset": {"sha256": str, "selected_case_count": int},
    "selection": {
        "phase11_selection_count": int,
        "phase12_reserve_count": int,
        "selections_disjoint": bool,
        "loaded_rows_match_phase11_selection": bool,
        "reserve_rows_selected": int,
        "reserve_rows_scored": int,
    },
    "protocol": {
        "provider": str,
        "provider_max_results": int,
        "selection_limit": int,
        "max_per_domain": int,
        "evidence_budget_chars": int,
        "max_block_chars": int,
        "min_block_chars": int,
        "projection_replays": int,
        "connect_seconds": float,
        "read_seconds": float,
        "write_seconds": float,
        "pool_seconds": float,
        "provider_wall_seconds": float,
        "outer_wall_seconds": float,
        "abort_on_first_provider_failure": bool,
        "models": list,
    },
    "traffic": {
        "benchmark_network_scope": str,
        "static_dataset_fetches": int,
        "logical_operations_planned": int,
        "logical_operations_started": int,
        "logical_operations_completed": int,
        "tavily_http_attempts_actual": int,
        "tavily_http_attempts_maximum": int,
        "http_responses": int,
        "tavily_requests": int,
        "other_provider_requests": int,
        "model_requests": int,
        "gemini_requests": int,
        "token_count_requests": int,
        "retries": int,
        "fallback_requests": int,
        "repair_requests": int,
        "cache_reads": int,
        "cache_writes": int,
        "follow_up_document_fetches": int,
    },
    "retrieval": {
        "attempted_cases": int,
        "successful_cases": int,
        "failure_kind": (str, type(None)),
        "stopped_on_first_failure": bool,
        "http_status_counts": dict,
    },
    "projection": {
        "scored_case_count": int,
        "available_case_count": int,
        "selected_proxy_hits": int,
        "equal_cap_prompt_proxy_hits": int,
        "v1_prompt_proxy_hits": int,
        "v2_prompt_proxy_hits": int,
        "v2_retention_numerator": int,
        "v2_retention_denominator": int,
        "v2_retention_rate": (float, type(None)),
        "v2_vs_equal_candidate_wins": int,
        "v2_vs_equal_baseline_wins": int,
        "v2_vs_equal_net_gain": int,
        "v2_vs_v1_candidate_wins": int,
        "v2_vs_v1_baseline_wins": int,
        "v2_vs_v1_net_gain": int,
        "raw_pool_matching_cases": int,
        "selected_packet_matching_cases": int,
        "projection_invariant_cases": int,
        "candidate_budget_cases": int,
        "equal_cap_over_budget_cases": int,
    },
    "privacy": {
        "passed": bool,
        "strict_allowlist_passed": bool,
        "absolute_paths_found": int,
        "case_ids_found": int,
        "row_indexes_found": int,
        "questions_found": int,
        "reference_answers_found": int,
        "gold_urls_found": int,
        "provider_content_values_found": int,
        "api_key_found": bool,
        "forbidden_keys_found": int,
    },
    "decision": {
        "gate_count": int,
        "passed_gate_count": int,
        "gates": [{"name": str, "passed": bool}],
        "projection_candidate_passed": bool,
        "diagnostic_status": str,
        "phase11_9_protocol_may_be_frozen": bool,
        "phase12_authorized": bool,
        "phase12_executed": bool,
        "quality_profile_promoted": bool,
        "merge_allowed": bool,
        "release_allowed": bool,
        "superiority_claim_allowed": bool,
        "release_decision": str,
    },
    "warnings": [str],
}


def _schema_matches(value: object, schema: object) -> bool:
    if isinstance(schema, dict):
        return (
            isinstance(value, dict)
            and set(value) == set(schema)
            and all(_schema_matches(value[key], child) for key, child in schema.items())
        )
    if isinstance(schema, list):
        return (
            isinstance(value, list)
            and len(schema) == 1
            and all(_schema_matches(item, schema[0]) for item in value)
        )
    if isinstance(schema, tuple):
        return type(value) in schema
    if schema is list:
        return isinstance(value, list)
    if schema is dict:
        return isinstance(value, dict)
    return type(value) is schema


def _walk_strings(value: object) -> Sequence[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, Mapping):
        for nested in value.values():
            strings.extend(_walk_strings(nested))
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for nested in value:
            strings.extend(_walk_strings(nested))
    return strings


def _walk_keys(value: object) -> Sequence[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for nested in value:
            keys.extend(_walk_keys(nested))
    return keys


def _contains_value(rendered: str, value: str) -> bool:
    return bool(value) and json.dumps(value, ensure_ascii=False) in rendered


def audit_public_report(
    report: Mapping[str, Any],
    *,
    rows: Sequence[Any],
    reserve_manifest: Mapping[str, Any],
    tavily_api_key: str,
    provider_private_values: Sequence[str],
) -> dict[str, Any]:
    """Apply the strict schema and private-value scans to a public report."""

    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    strings = _walk_strings(report)
    keys = _walk_keys(report)
    reserve_items = reserve_manifest.get("sealed_cases", [])
    reserve_ids = [
        item["case_id"]
        for item in reserve_items
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    ]
    all_case_ids = [str(row.id) for row in rows] + reserve_ids
    questions = [str(row.question) for row in rows]
    answers = [str(answer) for row in rows for answer in row.answers]
    gold_urls = [str(url) for row in rows for url in row.gold_urls]
    absolute_paths = sum(
        value.startswith("/") or bool(_WINDOWS_ABSOLUTE.match(value)) for value in strings
    )
    forbidden_keys = {
        "case_id",
        "case_ids",
        "row_index",
        "row_indexes",
        "question",
        "questions",
        "answer",
        "answers",
        "gold_url",
        "gold_urls",
        "title",
        "url",
        "snippet",
        "raw_results",
        "projection_outcomes",
        "raw_pool_sha256",
        "selected_packet_sha256",
        "prompt_packet_sha256",
        "network_region",
        "environment",
        "env",
        "provider_message",
        "exception_message",
    }
    result = {
        "passed": False,
        "strict_allowlist_passed": _schema_matches(report, PUBLIC_SCHEMA),
        "absolute_paths_found": absolute_paths,
        "case_ids_found": sum(_contains_value(rendered, value) for value in all_case_ids),
        "row_indexes_found": sum(key in {"row_index", "row_indexes"} for key in keys),
        "questions_found": sum(_contains_value(rendered, value) for value in questions),
        "reference_answers_found": sum(_contains_value(rendered, value) for value in answers),
        "gold_urls_found": sum(_contains_value(rendered, value) for value in gold_urls),
        "provider_content_values_found": sum(
            _contains_value(rendered, value) for value in provider_private_values
        ),
        "api_key_found": _contains_value(rendered, tavily_api_key),
        "forbidden_keys_found": sum(key in forbidden_keys for key in keys),
    }
    result["passed"] = bool(
        result["strict_allowlist_passed"]
        and result["absolute_paths_found"] == 0
        and result["case_ids_found"] == 0
        and result["row_indexes_found"] == 0
        and result["questions_found"] == 0
        and result["reference_answers_found"] == 0
        and result["gold_urls_found"] == 0
        and result["provider_content_values_found"] == 0
        and result["api_key_found"] is False
        and result["forbidden_keys_found"] == 0
    )
    return result


def build_public_report(
    *,
    dependency_locks: Sequence[DependencyLock],
    authorization: AuthorizationAttestation,
    dataset_sha256: str,
    selections: SelectionFacts,
    retrieval: RetrievalResult,
    rows: Sequence[Any],
    reserve_manifest: Mapping[str, Any],
    tavily_api_key: str,
) -> dict[str, Any]:
    """Build and audit the aggregate-only public result."""

    projection = aggregate_projection(retrieval.outcomes)
    traffic = {
        "benchmark_network_scope": (
            "one checksum-pinned static dataset fetch plus at most 24 Tavily "
            "requests; checkout, install and artifact CI traffic excluded"
        ),
        "static_dataset_fetches": 1,
        "logical_operations_planned": EXPECTED_CASE_COUNT,
        "logical_operations_started": retrieval.logical_calls,
        "logical_operations_completed": retrieval.successful_cases,
        "tavily_http_attempts_actual": retrieval.actual_http_attempts,
        "tavily_http_attempts_maximum": MAXIMUM_HTTP_ATTEMPTS,
        "http_responses": retrieval.http_responses,
        "tavily_requests": retrieval.actual_http_attempts,
        "other_provider_requests": 0,
        "model_requests": 0,
        "gemini_requests": 0,
        "token_count_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
        "cache_reads": 0,
        "cache_writes": 0,
        "follow_up_document_fetches": 0,
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "run_status": (
            "aborted_provider_failure" if retrieval.failure_kind is not None else "completed"
        ),
        "dependency_manifest_sha256": LOCKED_DEPENDENCY_MANIFEST_SHA256,
        "source_locks": [
            {
                "relative_path": dependency.relative_path,
                "sha256": dependency.sha256,
            }
            for dependency in dependency_locks
        ],
        "authorization": {
            "attestation_sha256": authorization.attestation_sha256,
            "lock_commit_sha": authorization.lock_commit_sha,
            "authorization_commit_sha": authorization.authorization_commit_sha,
            "workflow_run_attempt": authorization.workflow_run_attempt,
            "verified": authorization.verified,
        },
        "dataset": {
            "sha256": dataset_sha256,
            "selected_case_count": EXPECTED_CASE_COUNT,
        },
        "selection": {
            "phase11_selection_count": selections.phase11_selection_count,
            "phase12_reserve_count": selections.phase12_reserve_count,
            "selections_disjoint": selections.selections_disjoint,
            "loaded_rows_match_phase11_selection": (selections.loaded_rows_match_phase11_selection),
            "reserve_rows_selected": selections.reserve_rows_selected,
            "reserve_rows_scored": selections.reserve_rows_scored,
        },
        "protocol": {
            "provider": "tavily",
            "provider_max_results": PROVIDER_MAX_RESULTS,
            "selection_limit": SELECTION_LIMIT,
            "max_per_domain": MAX_PER_DOMAIN,
            "evidence_budget_chars": EVIDENCE_BUDGET_CHARS,
            "max_block_chars": MAX_BLOCK_CHARS,
            "min_block_chars": MIN_BLOCK_CHARS,
            "projection_replays": PROJECTION_REPLAYS,
            "connect_seconds": CONNECT_SECONDS,
            "read_seconds": READ_SECONDS,
            "write_seconds": WRITE_SECONDS,
            "pool_seconds": POOL_SECONDS,
            "provider_wall_seconds": PROVIDER_WALL_SECONDS,
            "outer_wall_seconds": OUTER_WALL_SECONDS,
            "abort_on_first_provider_failure": True,
            "models": [],
        },
        "traffic": traffic,
        "retrieval": {
            "attempted_cases": retrieval.attempted_cases,
            "successful_cases": retrieval.successful_cases,
            "failure_kind": retrieval.failure_kind,
            "stopped_on_first_failure": retrieval.stopped_on_first_failure,
            "http_status_counts": retrieval.status_counts,
        },
        "projection": projection,
        "privacy": {
            "passed": False,
            "strict_allowlist_passed": True,
            "absolute_paths_found": 0,
            "case_ids_found": 0,
            "row_indexes_found": 0,
            "questions_found": 0,
            "reference_answers_found": 0,
            "gold_urls_found": 0,
            "provider_content_values_found": 0,
            "api_key_found": False,
            "forbidden_keys_found": 0,
        },
        "decision": {
            "gate_count": len(GATE_NAMES),
            "passed_gate_count": 0,
            "gates": [{"name": name, "passed": False} for name in GATE_NAMES],
            "projection_candidate_passed": False,
            "diagnostic_status": "privacy_audit_pending",
            "phase11_9_protocol_may_be_frozen": False,
            "phase12_authorized": False,
            "phase12_executed": False,
            "quality_profile_promoted": False,
            "merge_allowed": False,
            "release_allowed": False,
            "superiority_claim_allowed": False,
            "release_decision": "no-go",
        },
        "warnings": [
            (
                "This already-observed selector suite supports within-run paired "
                "projection comparisons only."
            ),
            (
                "Reference-answer substring coverage is a transparent proxy, not "
                "an official SimpleQA score or semantic correctness judgment."
            ),
            (
                "Phase 11.9, Phase 12, product promotion, merge, release and "
                "superiority claims remain blocked regardless of this result."
            ),
        ],
    }
    first_audit = audit_public_report(
        report,
        rows=rows,
        reserve_manifest=reserve_manifest,
        tavily_api_key=tavily_api_key,
        provider_private_values=retrieval.provider_private_values,
    )
    report["privacy"] = first_audit
    report["decision"] = _decision(
        dependencies_valid=True,
        authorization=authorization,
        selections=selections,
        retrieval=retrieval,
        projection=projection,
        privacy_passed=bool(first_audit["passed"]),
    )
    final_audit = audit_public_report(
        report,
        rows=rows,
        reserve_manifest=reserve_manifest,
        tavily_api_key=tavily_api_key,
        provider_private_values=retrieval.provider_private_values,
    )
    if not final_audit["passed"]:
        raise LiveCalibrationError("public_report_privacy_or_schema_failure")
    report["privacy"] = final_audit
    report["decision"] = _decision(
        dependencies_valid=True,
        authorization=authorization,
        selections=selections,
        retrieval=retrieval,
        projection=projection,
        privacy_passed=True,
    )
    if not _schema_matches(report, PUBLIC_SCHEMA):
        raise LiveCalibrationError("public_report_schema_failure")
    return report


def validate_arguments(arguments: argparse.Namespace) -> None:
    if arguments.check_only and arguments.authorize_live_run:
        raise ValueError("--check-only and --authorize-live-run are mutually exclusive")
    if not arguments.check_only and not arguments.authorize_live_run:
        raise ValueError("live execution requires --authorize-live-run")
    if arguments.authorize_live_run and (
        arguments.dataset is None
        or arguments.output is None
        or not arguments.authorization_verified
        or arguments.authorization_attestation is None
    ):
        raise ValueError(
            "live execution requires --dataset, --output, "
            "--authorization-verified and --authorization-attestation"
        )


async def run_live(arguments: argparse.Namespace) -> dict[str, Any]:
    validate_arguments(arguments)
    dependency_locks = validate_dependency_manifest(arguments.dependency_lock_manifest)
    locked.validate_locked_sources(_historical_validation_arguments())
    if arguments.dataset is None or arguments.output is None:
        raise ValueError("live execution requires --dataset and --output")
    if not arguments.authorization_verified or arguments.authorization_attestation is None:
        raise ValueError("live execution requires verified one-shot authorization")
    authorization = validate_authorization_attestation(arguments.authorization_attestation)

    manifest_path = REPOSITORY_ROOT / "benchmarks/data/phase11_7_fresh_confirmation_v1.json"
    reserve_path = REPOSITORY_ROOT / "benchmarks/data/phase12_untouched_reserve_v1.json"
    with OutputReservation(arguments.output) as reservation:
        rows, manifest, _dataset_metadata, _reserve_metadata = locked.phase11_8.load_phase11_7_rows(
            arguments.dataset,
            manifest_path,
            reserve_path,
            root=REPOSITORY_ROOT,
            expected_manifest_sha256=locked.LOCKED_MANIFEST_SHA256,
            expected_reserve_manifest_sha256=(locked.LOCKED_RESERVE_MANIFEST_SHA256),
        )
        reserve_manifest = json.loads(reserve_path.read_bytes())
        if not isinstance(reserve_manifest, dict):
            raise ValueError("Phase 12 reserve manifest changed")
        selections = derive_selection_facts(manifest, reserve_manifest, rows)
        if not selections.passed:
            raise ValueError("Phase 11/Phase 12 selection boundary changed")

        # This is deliberately the first environment access in the live path.
        tavily_api_key = os.environ.get("TAVILY_API_KEY")
        if not tavily_api_key:
            raise ValueError("TAVILY_API_KEY is not configured")
        retrieval = await retrieve_and_project(
            rows,
            tavily_api_key=tavily_api_key,
            progress=arguments.progress,
        )
        report = build_public_report(
            dependency_locks=dependency_locks,
            authorization=authorization,
            dataset_sha256=_sha256(arguments.dataset.read_bytes()),
            selections=selections,
            retrieval=retrieval,
            rows=rows,
            reserve_manifest=reserve_manifest,
            tavily_api_key=tavily_api_key,
        )
        reservation.commit(report)
        return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--authorize-live-run", action="store_true")
    parser.add_argument("--authorization-verified", action="store_true")
    parser.add_argument("--authorization-attestation", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--dependency-lock-manifest",
        type=Path,
        default=DEPENDENCY_MANIFEST_PATH,
    )
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    if arguments.check_only:
        validate_arguments(arguments)
        print(
            json.dumps(
                validate_check_only(arguments.dependency_lock_manifest),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    report = asyncio.run(run_live(arguments))
    print(
        json.dumps(
            {
                "benchmark": report["benchmark"],
                "run_status": report["run_status"],
                "output_written": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
