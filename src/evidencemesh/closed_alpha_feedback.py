"""Private, aggregate-only storage for closed-alpha feedback reports.

The store is intentionally POSIX-only.  It owns a dedicated directory and
anchors every filesystem operation to an open directory descriptor so that a
path or symbolic-link replacement cannot redirect an operation elsewhere.
It does not accept task text, provider output, credentials, or log messages;
the final packaged contract enforces the exact closed feedback schema.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
import re
import secrets
import stat
import threading
from collections.abc import Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Final, Protocol, cast, final

from evidencemesh.errors import ConfigurationError

MAX_REPORT_BYTES: Final = 128 * 1024
PURGE_MARGIN: Final = timedelta(seconds=60)
MAX_SCHEDULER_POLL_SECONDS: Final = 30.0
MAX_ACCEPTANCE_RECORD_BYTES: Final = 256 * 1024
MAX_DIRECT_URL_BYTES: Final = 16 * 1024
MAX_ACCEPTED_ARCHIVE_BYTES: Final = 512 * 1024 * 1024

_LOCK_NAME: Final = ".feedback.lock"
_REPORT_PATTERN: Final = re.compile(r"^s-[0-9a-f]{32}\.json$")
_SESSION_PATTERN: Final = re.compile(r"^s-[0-9a-f]{32}$")
_PARTICIPANT_PATTERN: Final = re.compile(r"^p-[0-9a-f]{16}$")
_TEMP_PATTERN: Final = re.compile(r"^\.feedback-tmp-[0-9a-f]{32}$")
_CANDIDATE_PATTERN: Final = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
_ATTESTATION_URL_PATTERN: Final = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/attestations/([1-9][0-9]*)$"
)
_REPORT_SCHEMA: Final = "evidencemesh.closed-alpha-a0.session.v1"
_PROTOCOL_VERSION: Final = "closed-alpha-a0-v1"
_CONSENT_VERSION: Final = "closed-alpha-a0-consent-v1"
_SLOTS: Final = {
    "C01": "community",
    "C02": "community",
    "C03": "community",
    "C04": "community",
    "C05": "community",
    "C06": "community",
    "Q01": "quality",
    "Q02": "quality",
}
_FAILURE_KINDS: Final = frozenset(
    {
        "none",
        "installation",
        "configuration",
        "provider",
        "timeout",
        "empty_result",
        "citation",
        "privacy",
        "budget",
        "candidate_identity",
        "other",
    }
)
_TASK_CATEGORIES: Final = frozenset(
    {
        "general_reference",
        "current_information",
        "technical",
        "academic",
        "code",
        "other_non_sensitive",
    }
)
_FORBIDDEN_PROPERTY_MARKERS: Final = frozenset(
    {
        "answer",
        "comment",
        "content",
        "cookie",
        "domain",
        "email",
        "exception",
        "header",
        "hostname",
        "link",
        "message",
        "prompt",
        "query",
        "quote",
        "snippet",
        "stack",
        "title",
        "token",
        "traceback",
        "uri",
        "url",
        "username",
    }
)
_IDENTITY_VERIFICATION: Final = object()


class ClosedAlphaFeedbackError(ConfigurationError):
    """Raised when private feedback handling cannot remain fail-closed."""


class FeedbackValidationError(ClosedAlphaFeedbackError):
    """Raised when an input is outside the aggregate-only report contract."""


class FeedbackAdmissionError(ClosedAlphaFeedbackError):
    """Raised when the control-plane registry does not authorize an operation."""


def _require_validation(condition: bool, message: str) -> None:
    if not condition:
        raise FeedbackValidationError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    _require_validation(isinstance(value, dict), f"{label} must be an object")
    return cast(dict[str, Any], value)


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    _require_validation(set(value) == expected, f"{label} fields drifted")


def _bounded_int(value: object, minimum: int, maximum: int, label: str) -> int:
    _require_validation(
        isinstance(value, int) and not isinstance(value, bool),
        f"{label} must be an integer",
    )
    normalized = cast(int, value)
    _require_validation(minimum <= normalized <= maximum, f"{label} is outside its bound")
    return normalized


def _canonical_date(value: object, label: str) -> date:
    _require_validation(isinstance(value, str), f"{label} must be a date")
    try:
        parsed = date.fromisoformat(cast(str, value))
    except ValueError as exc:
        raise FeedbackValidationError(f"{label} must be an ISO date") from exc
    _require_validation(parsed.isoformat() == value, f"{label} must be a canonical ISO date")
    return parsed


def _open_identity_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> tuple[int, os.stat_result]:
    if not path.is_absolute():
        raise FeedbackValidationError(f"{label} path must be absolute")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        metadata = os.fstat(descriptor)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise FeedbackValidationError(f"cannot open {label}") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size <= 0
        or metadata.st_size > maximum_bytes
    ):
        os.close(descriptor)
        raise FeedbackValidationError(f"{label} is not a safe bounded regular file")
    return descriptor, metadata


def _assert_identity_file_stable(
    path: Path,
    before: os.stat_result,
    after: os.stat_result,
    *,
    label: str,
) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise FeedbackValidationError(f"cannot recheck {label}") from exc
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(
        getattr(before, field) != getattr(after, field)
        or getattr(after, field) != getattr(current, field)
        for field in stable_fields
    ):
        raise FeedbackValidationError(f"{label} changed while it was verified")


def _read_identity_file(path: Path, *, label: str, maximum_bytes: int) -> bytes:
    descriptor, before = _open_identity_file(path, label=label, maximum_bytes=maximum_bytes)
    try:
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise FeedbackValidationError(f"cannot read {label}") from exc
    finally:
        os.close(descriptor)
    if len(payload) != before.st_size or len(payload) > maximum_bytes:
        raise FeedbackValidationError(f"{label} size changed while it was verified")
    _assert_identity_file_stable(path, before, after, label=label)
    return payload


def _sha256_identity_file(path: Path, *, label: str, maximum_bytes: int) -> str:
    descriptor, before = _open_identity_file(path, label=label, maximum_bytes=maximum_bytes)
    digest = hashlib.sha256()
    observed_size = 0
    try:
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            observed_size += len(chunk)
            if observed_size > maximum_bytes:
                raise FeedbackValidationError(f"{label} exceeds its byte limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise FeedbackValidationError(f"cannot hash {label}") from exc
    finally:
        os.close(descriptor)
    if observed_size != before.st_size:
        raise FeedbackValidationError(f"{label} size changed while it was verified")
    _assert_identity_file_stable(path, before, after, label=label)
    return digest.hexdigest()


def _identity_json(payload: bytes, *, label: str) -> dict[str, Any]:
    def reject_constant(_value: str) -> None:
        raise FeedbackValidationError(f"{label} contains a non-finite number")

    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, child in pairs:
            if not isinstance(key, str) or key in value:
                raise FeedbackValidationError(f"{label} contains a duplicate property")
            value[key] = child
        return value

    try:
        parsed = json.loads(
            payload,
            object_pairs_hook=closed_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeedbackValidationError(f"{label} is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise FeedbackValidationError(f"{label} must be an object")
    return cast(dict[str, Any], parsed)


def _read_installed_direct_url() -> bytes:
    """Read PEP 610 metadata from the installed EvidenceMesh distribution."""

    try:
        distribution = importlib.metadata.distribution("evidencemesh")
    except (OSError, UnicodeError, importlib.metadata.PackageNotFoundError) as exc:
        raise FeedbackValidationError("cannot locate installed EvidenceMesh distribution") from exc
    try:
        files = distribution.files
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise FeedbackValidationError(
            "cannot inspect installed EvidenceMesh file inventory"
        ) from exc
    if files is None:
        raise FeedbackValidationError(
            "installed EvidenceMesh distribution has no verifiable file inventory"
        )
    module_entries = tuple(
        entry
        for entry in files
        if PurePosixPath(str(entry)) == PurePosixPath("evidencemesh/closed_alpha_feedback.py")
    )
    if len(module_entries) != 1:
        raise FeedbackValidationError(
            "installed EvidenceMesh distribution does not inventory the imported feedback module"
        )
    try:
        located_module = Path(str(distribution.locate_file(module_entries[0]))).resolve(strict=True)
        imported_module = Path(__file__).resolve(strict=True)
        located_metadata = located_module.stat()
        imported_metadata = imported_module.stat()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise FeedbackValidationError(
            "cannot bind installed EvidenceMesh distribution to the imported feedback module"
        ) from exc
    if (
        not stat.S_ISREG(located_metadata.st_mode)
        or not stat.S_ISREG(imported_metadata.st_mode)
        or (located_metadata.st_dev, located_metadata.st_ino)
        != (imported_metadata.st_dev, imported_metadata.st_ino)
    ):
        raise FeedbackValidationError(
            "installed EvidenceMesh distribution does not contain the imported feedback module"
        )
    try:
        direct_url = distribution.read_text("direct_url.json")
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise FeedbackValidationError("cannot read installed EvidenceMesh direct_url.json") from exc
    if not isinstance(direct_url, str):
        raise FeedbackValidationError("installed EvidenceMesh distribution has no direct_url.json")
    payload = direct_url.encode("utf-8")
    if not payload or len(payload) > MAX_DIRECT_URL_BYTES:
        raise FeedbackValidationError(
            "installed EvidenceMesh direct_url.json is not safely bounded"
        )
    return payload


def _acceptance_subjects(candidate: Mapping[str, Any]) -> dict[str, str]:
    raw_subjects = candidate.get("subjects")
    if not isinstance(raw_subjects, dict) or not raw_subjects:
        raise FeedbackValidationError("acceptance record subjects are invalid")
    subjects: dict[str, str] = {}
    for raw_path, raw_digest in raw_subjects.items():
        if not isinstance(raw_path, str) or not isinstance(raw_digest, str):
            raise FeedbackValidationError("acceptance record subject is invalid")
        subject_path = PurePosixPath(raw_path)
        if (
            subject_path.is_absolute()
            or str(subject_path) != raw_path
            or not subject_path.parts
            or any(part in {"", ".", ".."} for part in subject_path.parts)
            or _SHA256_PATTERN.fullmatch(raw_digest) is None
        ):
            raise FeedbackValidationError("acceptance record subject is unsafe")
        subjects[raw_path] = raw_digest
    wheels = [path for path in subjects if path.endswith(".whl")]
    sdists = [path for path in subjects if path.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1:
        raise FeedbackValidationError("acceptance record must bind one wheel and one sdist")
    return subjects


@final
@dataclass(frozen=True, slots=True, init=False)
class ClosedAlphaFeedbackIdentity:
    """Verified installed identity of one metadata-only accepted candidate.

    Loading is offline and fail-closed.  The raw acceptance-record digest is
    the external trust anchor; the record then binds the candidate, its three
    public attestations, the installed archive and its PEP 610 direct URL.
    Direct construction is forbidden so a caller cannot select a raw SHA.
    """

    candidate_sha: str
    candidate_tree: str
    repository: str
    record_sha256: str
    archive_subject: str
    archive_sha256: str
    _verification: object

    def __init__(self) -> None:
        raise FeedbackValidationError(
            "closed-alpha feedback identity must be loaded from accepted metadata"
        )

    @classmethod
    def load(
        cls,
        record_path: Path,
        *,
        expected_record_sha256: str,
        archive_path: Path,
    ) -> ClosedAlphaFeedbackIdentity:
        """Load and cross-bind an acceptance record and installed archive."""

        if _SHA256_PATTERN.fullmatch(expected_record_sha256) is None:
            raise FeedbackValidationError("expected acceptance record SHA-256 is invalid")
        record_path = Path(record_path)
        archive_path = Path(archive_path)
        record_payload = _read_identity_file(
            record_path,
            label="acceptance record",
            maximum_bytes=MAX_ACCEPTANCE_RECORD_BYTES,
        )
        if hashlib.sha256(record_payload).hexdigest() != expected_record_sha256:
            raise FeedbackValidationError("acceptance record SHA-256 does not match")
        record = _identity_json(record_payload, label="acceptance record")
        if record.get("schema_version") != 1:
            raise FeedbackValidationError("acceptance record schema is invalid")

        acceptance = _object(record.get("acceptance"), "acceptance decision")
        if (
            acceptance.get("status") != "accepted"
            or acceptance.get("scored") is not False
            or not isinstance(acceptance.get("scope"), str)
            or not acceptance["scope"]
        ):
            raise FeedbackValidationError("acceptance decision is not final")
        seal = _object(record.get("seal"), "acceptance seal")
        if seal.get("completed") is not True or seal.get("workflow_retired") is not True:
            raise FeedbackValidationError("acceptance metadata is not sealed")
        distribution = _object(record.get("distribution"), "acceptance distribution")
        if (
            distribution.get("public_metadata_only") is not True
            or distribution.get("binary_artifact_uploaded") is not False
            or distribution.get("unpublished_distributions") is not True
            or type(distribution.get("github_actions_artifact_count")) is not int
            or distribution["github_actions_artifact_count"] != 0
        ):
            raise FeedbackValidationError("acceptance distribution boundary is invalid")

        candidate = _object(record.get("candidate"), "accepted candidate")
        candidate_sha = candidate.get("sha")
        candidate_tree = candidate.get("tree")
        if (
            not isinstance(candidate_sha, str)
            or _CANDIDATE_PATTERN.fullmatch(candidate_sha) is None
        ):
            raise FeedbackValidationError("accepted candidate SHA is invalid")
        if (
            not isinstance(candidate_tree, str)
            or _CANDIDATE_PATTERN.fullmatch(candidate_tree) is None
        ):
            raise FeedbackValidationError("accepted candidate tree is invalid")
        subjects = _acceptance_subjects(candidate)

        attestations = record.get("attestations")
        if not isinstance(attestations, dict) or set(attestations) != {
            "provenance",
            "result",
            "sbom",
        }:
            raise FeedbackValidationError("acceptance record attestations are incomplete")
        repository: str | None = None
        attestation_ids: set[int] = set()
        for name in ("provenance", "result", "sbom"):
            attestation = _object(attestations[name], f"{name} attestation")
            if set(attestation) != {"id", "url"}:
                raise FeedbackValidationError(f"{name} attestation fields drifted")
            identifier = attestation.get("id")
            url = attestation.get("url")
            if type(identifier) is not int or identifier <= 0 or not isinstance(url, str):
                raise FeedbackValidationError(f"{name} attestation is invalid")
            match = _ATTESTATION_URL_PATTERN.fullmatch(url)
            if match is None or int(match.group(3)) != identifier:
                raise FeedbackValidationError(f"{name} attestation URL is invalid")
            observed_repository = f"{match.group(1)}/{match.group(2)}"
            if repository is None:
                repository = observed_repository
            elif repository != observed_repository:
                raise FeedbackValidationError("acceptance attestations disagree on repository")
            if identifier in attestation_ids:
                raise FeedbackValidationError("acceptance attestation identifiers are not unique")
            attestation_ids.add(identifier)
        if repository is None:  # pragma: no cover - exact key check above makes this unreachable
            raise FeedbackValidationError("acceptance attestation repository is missing")

        archive_digest = _sha256_identity_file(
            archive_path,
            label="accepted distribution archive",
            maximum_bytes=MAX_ACCEPTED_ARCHIVE_BYTES,
        )
        accepted_distribution_subjects = {
            path: digest for path, digest in subjects.items() if path.endswith((".whl", ".tar.gz"))
        }
        matching_subjects = [
            (path, digest)
            for path, digest in accepted_distribution_subjects.items()
            if PurePosixPath(path).name == archive_path.name
        ]
        if len(matching_subjects) != 1:
            raise FeedbackValidationError(
                "installed archive is not a unique accepted distribution subject"
            )
        archive_subject, expected_archive_digest = matching_subjects[0]
        if expected_archive_digest != archive_digest:
            raise FeedbackValidationError("installed archive SHA-256 does not match acceptance")

        direct_url_payload = _read_installed_direct_url()
        direct_url = _identity_json(direct_url_payload, label="installed direct_url.json")
        if set(direct_url) != {"archive_info", "url"}:
            raise FeedbackValidationError("installed direct_url.json is not an archive reference")
        try:
            archive_uri = archive_path.resolve(strict=True).as_uri()
        except (OSError, ValueError) as exc:
            raise FeedbackValidationError("cannot resolve accepted distribution archive") from exc
        if direct_url.get("url") != archive_uri:
            raise FeedbackValidationError("installed direct URL does not match accepted archive")
        archive_info = _object(direct_url.get("archive_info"), "installed archive info")
        if not archive_info or not set(archive_info).issubset({"hash", "hashes"}):
            raise FeedbackValidationError("installed archive hash metadata is invalid")
        hashes = archive_info.get("hashes")
        legacy_hash = archive_info.get("hash")
        observed_hash = False
        if hashes is not None:
            if hashes != {"sha256": archive_digest}:
                raise FeedbackValidationError("installed archive hashes do not match acceptance")
            observed_hash = True
        if legacy_hash is not None:
            if legacy_hash != f"sha256={archive_digest}":
                raise FeedbackValidationError("installed archive hash does not match acceptance")
            observed_hash = True
        if not observed_hash:
            raise FeedbackValidationError("installed direct URL has no accepted archive hash")

        identity = object.__new__(cls)
        object.__setattr__(identity, "candidate_sha", candidate_sha)
        object.__setattr__(identity, "candidate_tree", candidate_tree)
        object.__setattr__(identity, "repository", repository)
        object.__setattr__(identity, "record_sha256", expected_record_sha256)
        object.__setattr__(identity, "archive_subject", archive_subject)
        object.__setattr__(identity, "archive_sha256", archive_digest)
        object.__setattr__(identity, "_verification", _IDENTITY_VERIFICATION)
        return identity


@final
@dataclass(frozen=True, slots=True)
class ClosedAlphaFeedbackContract:
    """Final packaged validator for the closed aggregate A0 report shape.

    The report shape, enumerations, bounds and cross-field rules are frozen.
    Candidate selection comes only from a verified installed acceptance
    identity; callers cannot supply a raw candidate SHA.
    """

    identity: ClosedAlphaFeedbackIdentity

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not ClosedAlphaFeedbackIdentity
            or getattr(self.identity, "_verification", None) is not _IDENTITY_VERIFICATION
        ):
            raise FeedbackValidationError("feedback contract requires a verified accepted identity")

    @property
    def candidate_sha(self) -> str:
        """Return the accepted candidate bound by the verified identity."""

        return self.identity.candidate_sha

    @property
    def candidate_tree(self) -> str:
        """Return the accepted Git tree bound by the verified identity."""

        return self.identity.candidate_tree

    def validate(self, report: Mapping[str, Any], *, today: date) -> None:
        """Apply the complete closed shape and semantic A0 report contract."""

        expected_root = {
            "schema_version",
            "protocol_version",
            "candidate_sha",
            "participant_code",
            "session_code",
            "slot_id",
            "profile",
            "task",
            "retention",
            "consent",
            "outcome",
            "traffic",
            "grounding_counts",
            "privacy",
        }
        _exact_keys(report, expected_root, "feedback report")
        _require_validation(report["schema_version"] == _REPORT_SCHEMA, "feedback schema drifted")
        _require_validation(
            report["protocol_version"] == _PROTOCOL_VERSION,
            "feedback protocol drifted",
        )
        _require_validation(
            report["candidate_sha"] == self.candidate_sha,
            "feedback candidate drifted",
        )

        participant_code = report["participant_code"]
        session_code = report["session_code"]
        _require_validation(
            isinstance(participant_code, str)
            and _PARTICIPANT_PATTERN.fullmatch(participant_code) is not None,
            "feedback participant code is invalid",
        )
        _require_validation(
            isinstance(session_code, str) and _SESSION_PATTERN.fullmatch(session_code) is not None,
            "feedback session code is invalid",
        )
        slot_id = report["slot_id"]
        _require_validation(
            isinstance(slot_id, str) and slot_id in _SLOTS,
            "feedback slot is invalid",
        )
        _require_validation(
            report["profile"] == _SLOTS[cast(str, slot_id)],
            "feedback slot and profile do not match",
        )

        task = _object(report["task"], "feedback task")
        _exact_keys(task, {"slot", "kind", "category"}, "feedback task")
        task_slot = _bounded_int(task["slot"], 1, 5, "feedback task slot")
        expected_kind = "prescribed" if task_slot <= 3 else "real_non_sensitive"
        _require_validation(
            task["kind"] == expected_kind,
            "feedback task kind does not match its slot",
        )
        _require_validation(
            task["category"] in _TASK_CATEGORIES,
            "feedback task category is invalid",
        )

        retention = _object(report["retention"], "feedback retention")
        _exact_keys(retention, {"collected_on", "delete_after"}, "feedback retention")
        collected_on = _canonical_date(retention["collected_on"], "feedback collection date")
        delete_after = _canonical_date(retention["delete_after"], "feedback deletion date")
        _require_validation(
            delete_after == collected_on + timedelta(days=14),
            "feedback retention is not exactly fourteen days",
        )
        _require_validation(collected_on <= today, "feedback collection date is in the future")
        _require_validation(today < delete_after, "feedback report is expired")

        consent = _object(report["consent"], "feedback consent")
        _require_validation(
            consent
            == {
                "version": _CONSENT_VERSION,
                "confirmed": True,
                "authority_confirmed": True,
                "withdrawal_requested": False,
            },
            "feedback consent contract failed",
        )

        outcome = _object(report["outcome"], "feedback outcome")
        _exact_keys(
            outcome,
            {"status", "duration_seconds", "useful", "blocking", "failure_kind"},
            "feedback outcome",
        )
        status_value = outcome["status"]
        _require_validation(
            status_value in {"completed", "blocked", "aborted"},
            "feedback outcome status is invalid",
        )
        _bounded_int(outcome["duration_seconds"], 0, 3600, "feedback duration")
        _require_validation(isinstance(outcome["useful"], bool), "feedback useful must be boolean")
        _require_validation(
            isinstance(outcome["blocking"], bool),
            "feedback blocking must be boolean",
        )
        _require_validation(
            outcome["failure_kind"] in _FAILURE_KINDS,
            "feedback failure kind is invalid",
        )
        completed = status_value == "completed"
        _require_validation(
            outcome["blocking"] is not completed,
            "feedback blocking and status do not match",
        )
        _require_validation(
            (outcome["failure_kind"] == "none") is completed,
            "feedback failure and status do not match",
        )
        _require_validation(
            completed or outcome["useful"] is False,
            "failed feedback session cannot be useful",
        )

        traffic = _object(report["traffic"], "feedback traffic")
        _exact_keys(
            traffic,
            {
                "provider_attempts",
                "tavily_attempts",
                "provider_errors",
                "evidencemesh_model_attempts",
                "automatic_retries",
                "fallbacks",
                "repairs",
            },
            "feedback traffic",
        )
        attempts = _bounded_int(traffic["provider_attempts"], 0, 6, "provider attempts")
        tavily = _bounded_int(traffic["tavily_attempts"], 0, 4, "Tavily attempts")
        errors = _bounded_int(traffic["provider_errors"], 0, 6, "provider errors")
        _require_validation(
            tavily <= attempts and errors <= attempts,
            "feedback traffic counters are inconsistent",
        )
        _require_validation(
            report["profile"] == "quality" or tavily == 0,
            "community Tavily feedback is forbidden",
        )
        for field in (
            "evidencemesh_model_attempts",
            "automatic_retries",
            "fallbacks",
            "repairs",
        ):
            _require_validation(traffic[field] == 0, f"feedback {field} must remain zero")

        counts = _object(report["grounding_counts"], "feedback grounding counts")
        _exact_keys(
            counts,
            {"results", "citations", "resolvable_citations", "supported_citations"},
            "feedback grounding counts",
        )
        _bounded_int(counts["results"], 0, 100, "feedback result count")
        citations = _bounded_int(counts["citations"], 0, 100, "feedback citation count")
        resolvable = _bounded_int(
            counts["resolvable_citations"],
            0,
            100,
            "feedback resolvable citation count",
        )
        supported = _bounded_int(
            counts["supported_citations"],
            0,
            100,
            "feedback supported citation count",
        )
        _require_validation(
            supported <= resolvable <= citations,
            "feedback citation counters are inconsistent",
        )

        privacy = _object(report["privacy"], "feedback privacy")
        _require_validation(
            privacy
            == {
                "cache_disabled": True,
                "raw_runtime_objects_serialized": False,
                "sensitive_input_detected": False,
                "incident_detected": False,
            },
            "feedback privacy contract failed",
        )
        _reject_raw_property_names(report)
        serialized = _canonical_json(report).decode("utf-8")
        _require_validation("@" not in serialized, "feedback contains contact-like data")
        _require_validation("://" not in serialized, "feedback contains a network location")
        _require_validation("\\" not in serialized, "feedback contains a path-like value")


class FeedbackAdmission(Protocol):
    """Fail-closed bridge to the authoritative control-plane registry.

    Every callback must finish its database transaction before returning and
    must never acquire the feedback filesystem lock.  Control-plane mutators
    likewise commit and release their transaction before calling a store method.
    This one-way lock ordering prevents database/filesystem lock cycles while a
    concurrent writer either finishes before withdrawal deletes its reports, or
    observes the committed withdrawal and fails admission.
    """

    def feedback_context(
        self,
        participant_code: str,
        session_code: str,
    ) -> FeedbackContext | None:
        """Return authoritative report fields for an admitted bound session."""

    def withdrawal_committed(self, participant_code: str) -> bool:
        """Return true only after the participant is durably withdrawn."""

    def advance_feedback_clock(self, timestamp: float) -> bool:
        """Persist a UTC high-water timestamp; refuse a value below it."""

    def record_privacy_fault(self) -> None:
        """Durably block dispatch after a feedback integrity failure."""


@dataclass(frozen=True, slots=True)
class FeedbackContext:
    """Authoritative registry and ledger fields bound to one report."""

    slot_id: str
    profile: str
    provider_attempts: int
    tavily_attempts: int


@dataclass(frozen=True, slots=True)
class PutResult:
    """Non-sensitive result of one create-once operation."""

    session_code: str
    created: bool
    size_bytes: int


@dataclass(frozen=True, slots=True)
class PurgeResult:
    """Non-sensitive result of one retention pass."""

    checked_at: datetime
    deleted: int
    next_purge_at: datetime | None


def _canonical_json(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise FeedbackValidationError("feedback is not canonical JSON data") from exc
    payload = (rendered + "\n").encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise FeedbackValidationError("feedback exceeds the private report byte limit")
    return payload


def _closed_mapping(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeedbackValidationError("feedback is not valid JSON") from exc
    if not isinstance(value, dict):
        raise FeedbackValidationError("feedback must be an object")
    return cast(dict[str, Any], value)


def _reject_raw_property_names(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise FeedbackValidationError("feedback property names must be strings")
            lowered = key.lower()
            if any(marker in lowered for marker in _FORBIDDEN_PROPERTY_MARKERS):
                raise FeedbackValidationError("feedback contains a forbidden property")
            _reject_raw_property_names(child)
    elif isinstance(value, list):
        for child in value:
            _reject_raw_property_names(child)


class ClosedAlphaFeedbackStore:
    """Create-once private JSON store with fail-closed retention enforcement."""

    def __init__(
        self,
        root: Path,
        contract: ClosedAlphaFeedbackContract,
        admission: FeedbackAdmission,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if type(contract) is not ClosedAlphaFeedbackContract:
            raise ClosedAlphaFeedbackError(
                "private feedback store requires the final packaged contract"
            )
        self.root = Path(root)
        self._contract = contract
        self._admission = admission
        self._clock = clock
        self._thread_lock = threading.RLock()
        self._root_fd = -1
        self._lock_fd = -1
        self._closed = False
        self._poisoned = False
        self._privacy_fault_recorded = False
        self._last_now: datetime | None = None

        try:
            self._require_posix_primitives()
            self._root_fd = self._open_private_root()
            self._lock_fd = self._open_lock_file()
            with self._exclusive():
                now = self._clock_locked()
                self._purge_locked(now)
        except BaseException as exc:
            try:
                if isinstance(exc, ClosedAlphaFeedbackError):
                    self._record_privacy_fault()
            finally:
                self._close_descriptors()
                self._closed = True
            raise

    def __enter__(self) -> ClosedAlphaFeedbackStore:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object,
    ) -> None:
        self.close()

    @property
    def closed(self) -> bool:
        return self._closed

    def put(self, report: Mapping[str, Any]) -> PutResult:
        """Validate and publish one immutable report, or accept an identical replay."""

        payload = _canonical_json(report)
        frozen = _closed_mapping(payload)
        _reject_raw_property_names(frozen)
        if _canonical_json(frozen) != payload:
            raise FeedbackValidationError("feedback canonicalization changed its value")

        with self._exclusive():
            now = self._clock_locked()
            self._purge_locked(now)
            _participant_code, session_code, purge_at = self._validate_report(frozen, now=now)
            if now >= purge_at:
                raise FeedbackValidationError("feedback is already due for private deletion")

            name = f"{session_code}.json"
            existing = self._read_optional_locked(name)
            if existing is not None:
                existing_payload, _ = existing
                if existing_payload != payload:
                    raise FeedbackValidationError("feedback session already has another report")
                return PutResult(
                    session_code=session_code,
                    created=False,
                    size_bytes=len(payload),
                )

            self._publish_locked(name, payload)
            return PutResult(
                session_code=session_code,
                created=True,
                size_bytes=len(payload),
            )

    def get(self, session_code: str) -> dict[str, Any] | None:
        """Return one validated aggregate report after enforcing retention."""

        self._require_session_code(session_code)
        with self._exclusive():
            now = self._clock_locked()
            self._purge_locked(now)
            loaded = self._read_optional_locked(f"{session_code}.json")
            if loaded is None:
                return None
            _, report = loaded
            self._validate_report(report, now=now)
            return report

    def reports(self) -> tuple[dict[str, Any], ...]:
        """Return all validated aggregate reports after enforcing retention."""

        with self._exclusive():
            now = self._clock_locked()
            self._purge_locked(now)
            reports: list[dict[str, Any]] = []
            for name in self._report_names_locked():
                payload, report = self._read_required_locked(name)
                if _canonical_json(report) != payload:
                    self._integrity_failure("stored feedback is not canonical")
                self._validate_report(report, now=now)
                reports.append(report)
            return tuple(reports)

    def withdraw(self, participant_code: str) -> int:
        """Delete every owned report after withdrawal was durably committed.

        Repeating the same call is safe and returns zero.  A future ``put`` is
        independently refused by ``feedback_context`` after registry withdrawal.
        Report names are discovered inside the private store; no caller can
        accidentally omit one of the participant's sessions.
        """

        self._require_participant_code(participant_code)

        with self._exclusive():
            now = self._clock_locked()
            if not self._withdrawal_committed(participant_code):
                raise FeedbackAdmissionError("withdrawal is not committed")
            _, withdrawn_counts = self._purge_details_locked(now)
            return withdrawn_counts.get(participant_code, 0)

    def purge(self) -> PurgeResult:
        """Delete all reports at their guarded pre-``delete_after`` deadline."""

        with self._exclusive():
            now = self._clock_locked()
            return self._purge_locked(now)

    def close(self) -> None:
        """Purge on orderly shutdown, then close all anchored descriptors."""

        if self._closed:
            return
        failure: BaseException | None = None
        if self._poisoned:
            failure = ClosedAlphaFeedbackError("private feedback store is fail-closed")
        else:
            try:
                with self._exclusive():
                    now = self._clock_locked()
                    self._purge_locked(now)
            except BaseException as exc:  # closing must still release descriptors
                failure = exc
        self._closed = True
        self._close_descriptors()
        if failure is not None:
            raise failure

    def _require_posix_primitives(self) -> None:
        flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
        if any(not hasattr(os, name) for name in flags):
            raise ClosedAlphaFeedbackError("private feedback store requires POSIX open flags")
        required_dir_fd = (os.open, os.stat, os.unlink, os.link)
        if any(function not in os.supports_dir_fd for function in required_dir_fd):
            raise ClosedAlphaFeedbackError("private feedback store requires dir-fd operations")
        if not self.root.is_absolute() or ".." in self.root.parts or len(self.root.parts) < 2:
            raise ClosedAlphaFeedbackError("private feedback root must be an absolute child path")

    def _open_private_root(self) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = -1
        try:
            descriptor = os.open("/", flags)
            components = self.root.parts[1:]
            for index, component in enumerate(components):
                if component in {"", ".", ".."}:
                    raise ClosedAlphaFeedbackError("private feedback root is not canonical")
                is_final = index == len(components) - 1
                created = False
                if is_final:
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                        os.fsync(descriptor)
                        created = True
                    except FileExistsError:
                        pass
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
                if is_final and created:
                    os.fchmod(descriptor, 0o700)

            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or metadata.st_uid != os.geteuid()
            ):
                raise ClosedAlphaFeedbackError("private feedback directory is unsafe")
            return descriptor
        except ClosedAlphaFeedbackError:
            if descriptor >= 0:
                os.close(descriptor)
            raise
        except OSError as exc:
            if descriptor >= 0:
                os.close(descriptor)
            raise ClosedAlphaFeedbackError("cannot anchor private feedback directory") from exc

    def _open_lock_file(self) -> int:
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
        created = False
        try:
            try:
                descriptor = os.open(
                    _LOCK_NAME,
                    flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=self._root_fd,
                )
                created = True
            except FileExistsError:
                descriptor = os.open(_LOCK_NAME, flags, dir_fd=self._root_fd)
            if created:
                os.fchmod(descriptor, 0o600)
                self._fsync_root_locked()
            self._assert_regular_metadata(os.fstat(descriptor), expected_mode=0o600)
            return descriptor
        except ClosedAlphaFeedbackError:
            raise
        except OSError as exc:
            raise ClosedAlphaFeedbackError("cannot open private feedback lock") from exc

    @contextlib.contextmanager
    def _exclusive(self) -> Iterator[None]:
        if self._closed or self._poisoned or self._root_fd < 0 or self._lock_fd < 0:
            raise ClosedAlphaFeedbackError("private feedback store is fail-closed")
        with self._thread_lock:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
                self._assert_anchors_locked()
            except (OSError, ClosedAlphaFeedbackError) as exc:
                self._integrity_failure("cannot lock private feedback store", cause=exc)
            try:
                yield
            finally:
                try:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                except OSError as exc:
                    self._integrity_failure("cannot unlock private feedback store", cause=exc)

    def _assert_anchors_locked(self) -> None:
        try:
            root_descriptor = os.fstat(self._root_fd)
            root_path = os.stat(self.root, follow_symlinks=False)
            lock_descriptor = os.fstat(self._lock_fd)
            lock_path = os.stat(_LOCK_NAME, dir_fd=self._root_fd, follow_symlinks=False)
        except OSError as exc:
            self._integrity_failure("private feedback anchors are missing", cause=exc)
        if (
            (root_descriptor.st_dev, root_descriptor.st_ino) != (root_path.st_dev, root_path.st_ino)
            or not stat.S_ISDIR(root_descriptor.st_mode)
            or stat.S_IMODE(root_descriptor.st_mode) != 0o700
            or root_descriptor.st_uid != os.geteuid()
        ):
            self._integrity_failure("private feedback directory identity drifted")
        if (lock_descriptor.st_dev, lock_descriptor.st_ino) != (lock_path.st_dev, lock_path.st_ino):
            self._integrity_failure("private feedback lock identity drifted")
        self._assert_regular_metadata(lock_descriptor, expected_mode=0o600)

    def _clock_locked(self) -> datetime:
        try:
            observed = self._clock()
        except BaseException as exc:
            self._erase_all_reports_locked()
            self._integrity_failure("private feedback clock failed", cause=exc)
        if not isinstance(observed, datetime) or observed.tzinfo is None:
            self._erase_all_reports_locked()
            self._integrity_failure("private feedback clock must be timezone-aware")
        try:
            normalized = observed.astimezone(UTC)
            timestamp = normalized.timestamp()
        except (OSError, OverflowError, ValueError) as exc:
            self._erase_all_reports_locked()
            self._integrity_failure("private feedback clock is invalid", cause=exc)
        if not math.isfinite(timestamp):
            self._erase_all_reports_locked()
            self._integrity_failure("private feedback clock is invalid")
        if self._last_now is not None and normalized < self._last_now:
            self._erase_all_reports_locked()
            self._integrity_failure("private feedback clock moved backwards")
        try:
            advanced = self._admission.advance_feedback_clock(timestamp)
        except BaseException as exc:
            self._erase_all_reports_locked()
            self._integrity_failure("private feedback clock high-water failed", cause=exc)
        if advanced is not True:
            self._erase_all_reports_locked()
            self._integrity_failure("private feedback clock moved backwards across restart")
        self._last_now = normalized
        return normalized

    def _validate_report(
        self,
        report: Mapping[str, Any],
        *,
        now: datetime,
    ) -> tuple[str, str, datetime]:
        before = _canonical_json(report)
        try:
            self._contract.validate(report, today=now.date())
        except BaseException as exc:
            raise FeedbackValidationError("feedback validator rejected the report") from exc
        if _canonical_json(report) != before:
            raise FeedbackValidationError("feedback validator mutated the report")
        participant_code = report.get("participant_code")
        session_code = report.get("session_code")
        if not isinstance(participant_code, str):
            raise FeedbackValidationError("feedback participant code is invalid")
        if not isinstance(session_code, str):
            raise FeedbackValidationError("feedback session code is invalid")
        self._require_participant_code(participant_code)
        self._require_session_code(session_code)
        context = self._feedback_context(participant_code, session_code)
        traffic = _object(report.get("traffic"), "feedback traffic")
        if (
            report.get("slot_id") != context.slot_id
            or report.get("profile") != context.profile
            or traffic.get("provider_attempts") != context.provider_attempts
            or traffic.get("tavily_attempts") != context.tavily_attempts
        ):
            raise FeedbackAdmissionError("feedback fields do not match the authoritative context")
        purge_at = self._purge_at(report)
        return participant_code, session_code, purge_at

    def _purge_at(self, report: Mapping[str, Any]) -> datetime:
        retention = report.get("retention")
        if not isinstance(retention, dict):
            raise FeedbackValidationError("feedback retention is invalid")
        delete_after = retention.get("delete_after")
        if not isinstance(delete_after, str):
            raise FeedbackValidationError("feedback deletion date is invalid")
        try:
            parsed = date.fromisoformat(delete_after)
        except ValueError as exc:
            raise FeedbackValidationError("feedback deletion date is invalid") from exc
        if parsed.isoformat() != delete_after:
            raise FeedbackValidationError("feedback deletion date is not canonical")
        return datetime.combine(parsed, time.min, tzinfo=UTC) - PURGE_MARGIN

    def _feedback_context(
        self,
        participant_code: str,
        session_code: str,
    ) -> FeedbackContext:
        try:
            context = self._admission.feedback_context(participant_code, session_code)
        except BaseException as exc:
            self._integrity_failure("feedback context check failed", cause=exc)
        if context is None:
            raise FeedbackAdmissionError("feedback session is not admitted")
        if type(context) is not FeedbackContext:
            self._integrity_failure("feedback context returned an invalid decision")
        if (
            context.slot_id not in _SLOTS
            or context.profile != _SLOTS[context.slot_id]
            or not isinstance(context.provider_attempts, int)
            or isinstance(context.provider_attempts, bool)
            or not 0 <= context.provider_attempts <= 6
            or not isinstance(context.tavily_attempts, int)
            or isinstance(context.tavily_attempts, bool)
            or not 0 <= context.tavily_attempts <= 4
            or context.tavily_attempts > context.provider_attempts
            or (context.profile == "community" and context.tavily_attempts != 0)
        ):
            self._integrity_failure("feedback context is invalid")
        return context

    def _withdrawal_committed(self, participant_code: str) -> bool:
        try:
            committed = self._admission.withdrawal_committed(participant_code)
        except BaseException as exc:
            self._integrity_failure("feedback withdrawal check failed", cause=exc)
        if not isinstance(committed, bool):
            self._integrity_failure("feedback withdrawal returned an invalid decision")
        return committed

    def _publish_locked(self, name: str, payload: bytes) -> None:
        temporary_name = f".feedback-tmp-{secrets.token_hex(16)}"
        descriptor = -1
        published = False
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=self._root_fd,
            )
            os.fchmod(descriptor, 0o600)
            view = memoryview(payload)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError("short private feedback write")
                written += count
            os.fsync(descriptor)
            self._assert_regular_metadata(os.fstat(descriptor), expected_mode=0o600)
            os.close(descriptor)
            descriptor = -1
            os.link(
                temporary_name,
                name,
                src_dir_fd=self._root_fd,
                dst_dir_fd=self._root_fd,
                follow_symlinks=False,
            )
            published = True
            os.unlink(temporary_name, dir_fd=self._root_fd)
            metadata = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            self._assert_regular_metadata(metadata, expected_mode=0o600)
            self._fsync_root_locked()
        except FileExistsError as exc:
            raise FeedbackValidationError("feedback session was published concurrently") from exc
        except (OSError, ClosedAlphaFeedbackError) as exc:
            self._integrity_failure("cannot atomically publish private feedback", cause=exc)
        finally:
            if descriptor >= 0:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
            if not published:
                with contextlib.suppress(OSError):
                    os.unlink(temporary_name, dir_fd=self._root_fd)

    def _purge_locked(self, now: datetime) -> PurgeResult:
        result, _ = self._purge_details_locked(now)
        return result

    def _purge_details_locked(
        self,
        now: datetime,
    ) -> tuple[PurgeResult, dict[str, int]]:
        self._cleanup_temps_locked()
        deleted = 0
        withdrawn_counts: dict[str, int] = {}
        next_purge_at: datetime | None = None
        corrupted = False
        for name in self._report_names_locked():
            try:
                _, report = self._read_required_locked(name)
                purge_at = self._purge_at(report)
            except FeedbackValidationError:
                self._unlink_regular_locked(name)
                deleted += 1
                corrupted = True
                continue
            participant_code = report.get("participant_code")
            if (
                isinstance(participant_code, str)
                and _PARTICIPANT_PATTERN.fullmatch(participant_code) is not None
                and self._withdrawal_committed(participant_code)
            ):
                self._unlink_regular_locked(name)
                withdrawn_counts[participant_code] = withdrawn_counts.get(participant_code, 0) + 1
                deleted += 1
                continue
            if now >= purge_at:
                self._unlink_regular_locked(name)
                deleted += 1
                continue
            try:
                self._validate_report(report, now=now)
            except FeedbackValidationError:
                self._unlink_regular_locked(name)
                deleted += 1
                corrupted = True
                continue
            except FeedbackAdmissionError as exc:
                self._integrity_failure(
                    "stored feedback failed authoritative reconciliation",
                    cause=exc,
                )
            if next_purge_at is None or purge_at < next_purge_at:
                next_purge_at = purge_at
        if deleted:
            self._fsync_root_locked()
        if corrupted:
            self._integrity_failure("invalid stored feedback was removed")
        return (
            PurgeResult(
                checked_at=now,
                deleted=deleted,
                next_purge_at=next_purge_at,
            ),
            withdrawn_counts,
        )

    def _cleanup_temps_locked(self) -> None:
        removed = False
        for name in self._names_locked():
            if not _TEMP_PATTERN.fullmatch(name):
                continue
            try:
                metadata = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            except OSError as exc:
                self._integrity_failure("cannot inspect temporary feedback", cause=exc)
            self._assert_regular_metadata(metadata, expected_mode=0o600, maximum_links=2)
            try:
                os.unlink(name, dir_fd=self._root_fd)
            except OSError as exc:
                self._integrity_failure("cannot remove temporary feedback", cause=exc)
            removed = True
        if removed:
            self._fsync_root_locked()

    def _erase_all_reports_locked(self) -> None:
        if self._root_fd < 0:
            return
        deleted = False
        try:
            names = self._names_locked()
        except ClosedAlphaFeedbackError:
            return
        for name in names:
            if not _REPORT_PATTERN.fullmatch(name) and not _TEMP_PATTERN.fullmatch(name):
                continue
            try:
                metadata = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
                if stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.geteuid():
                    os.unlink(name, dir_fd=self._root_fd)
                    deleted = True
            except OSError:
                continue
        if deleted:
            with contextlib.suppress(OSError):
                os.fsync(self._root_fd)

    def _report_names_locked(self) -> tuple[str, ...]:
        reports: list[str] = []
        for name in self._names_locked():
            if name == _LOCK_NAME or _TEMP_PATTERN.fullmatch(name):
                continue
            if _REPORT_PATTERN.fullmatch(name) is None:
                self._integrity_failure("private feedback directory contains an unknown entry")
            reports.append(name)
        return tuple(sorted(reports))

    def _names_locked(self) -> tuple[str, ...]:
        try:
            names = os.listdir(self._root_fd)
        except OSError as exc:
            self._integrity_failure("cannot list private feedback directory", cause=exc)
        if not all(isinstance(name, str) for name in names):
            self._integrity_failure("private feedback directory contains an invalid name")
        return tuple(names)

    def _read_optional_locked(self, name: str) -> tuple[bytes, dict[str, Any]] | None:
        try:
            os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            self._integrity_failure("cannot inspect private feedback", cause=exc)
        return self._read_required_locked(name)

    def _read_required_locked(self, name: str) -> tuple[bytes, dict[str, Any]]:
        descriptor = -1
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=self._root_fd,
            )
            before = os.fstat(descriptor)
            self._assert_regular_metadata(before, expected_mode=0o600)
            if before.st_size > MAX_REPORT_BYTES:
                raise FeedbackValidationError("stored feedback exceeds its byte limit")
            chunks: list[bytes] = []
            remaining = MAX_REPORT_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            if (
                len(payload) != before.st_size
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
            ):
                self._integrity_failure("stored feedback changed while read")
            path_metadata = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            if (after.st_dev, after.st_ino) != (path_metadata.st_dev, path_metadata.st_ino):
                self._integrity_failure("stored feedback identity changed while read")
        except FeedbackValidationError:
            raise
        except ClosedAlphaFeedbackError:
            raise
        except OSError as exc:
            self._integrity_failure("cannot read private feedback", cause=exc)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        report = _closed_mapping(payload)
        if _canonical_json(report) != payload:
            raise FeedbackValidationError("stored feedback is not canonical")
        _reject_raw_property_names(report)
        return payload, report

    def _unlink_regular_locked(self, name: str) -> None:
        try:
            before = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            self._assert_regular_metadata(before, expected_mode=0o600)
            current = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
                self._integrity_failure("private feedback identity changed before deletion")
            os.unlink(name, dir_fd=self._root_fd)
        except ClosedAlphaFeedbackError:
            raise
        except OSError as exc:
            self._integrity_failure("cannot delete private feedback", cause=exc)

    def _assert_regular_metadata(
        self,
        metadata: os.stat_result,
        *,
        expected_mode: int,
        maximum_links: int = 1,
    ) -> None:
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != expected_mode
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink < 1
            or metadata.st_nlink > maximum_links
        ):
            self._integrity_failure("private feedback file metadata is unsafe")

    def _fsync_root_locked(self) -> None:
        try:
            os.fsync(self._root_fd)
        except OSError as exc:
            self._integrity_failure("cannot sync private feedback directory", cause=exc)

    def _require_participant_code(self, participant_code: str) -> None:
        if _PARTICIPANT_PATTERN.fullmatch(participant_code) is None:
            raise FeedbackValidationError("feedback participant code is invalid")

    def _require_session_code(self, session_code: str) -> None:
        if _SESSION_PATTERN.fullmatch(session_code) is None:
            raise FeedbackValidationError("feedback session code is invalid")

    def _integrity_failure(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self._poisoned = True
        self._record_privacy_fault()
        if cause is None:
            raise ClosedAlphaFeedbackError(message)
        raise ClosedAlphaFeedbackError(message) from cause

    def _record_privacy_fault(self) -> None:
        if self._privacy_fault_recorded:
            return
        self._poisoned = True
        try:
            self._admission.record_privacy_fault()
        except BaseException as exc:
            raise ClosedAlphaFeedbackError("cannot durably record private feedback fault") from exc
        self._privacy_fault_recorded = True

    def _close_descriptors(self) -> None:
        for descriptor_name in ("_lock_fd", "_root_fd"):
            descriptor = cast(int, getattr(self, descriptor_name))
            if descriptor >= 0:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
                setattr(self, descriptor_name, -1)


class FeedbackRetentionScheduler:
    """Small injectable scheduler that keeps purge active without a collector."""

    def __init__(
        self,
        store: ClosedAlphaFeedbackStore,
        *,
        wait: Callable[[float], Awaitable[None]] = asyncio.sleep,
        poll_interval_seconds: float = MAX_SCHEDULER_POLL_SECONDS,
    ) -> None:
        if (
            not isinstance(poll_interval_seconds, (int, float))
            or isinstance(poll_interval_seconds, bool)
            or not math.isfinite(poll_interval_seconds)
            or not 0 < poll_interval_seconds <= MAX_SCHEDULER_POLL_SECONDS
        ):
            raise ClosedAlphaFeedbackError("feedback scheduler poll interval is invalid")
        self._store = store
        self._wait = wait
        self._poll_interval_seconds = float(poll_interval_seconds)

    async def run_once(self) -> PurgeResult:
        """Execute one retention pass without sleeping."""

        return self._store.purge()

    async def run(self, stop: asyncio.Event) -> None:
        """Purge until stopped; cancellation and orderly exit both purge once more."""

        try:
            while not stop.is_set():
                result = await self.run_once()
                if stop.is_set():
                    break
                delay = self._poll_interval_seconds
                if result.next_purge_at is not None:
                    until_due = (result.next_purge_at - result.checked_at).total_seconds()
                    delay = min(delay, max(0.0, until_due))
                await self._wait(delay)
        finally:
            self._store.purge()
