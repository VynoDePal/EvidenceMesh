"""Fail-closed, process-shared dispatch budgets for the closed alpha.

The governor stores only pseudonymous session identifiers and bounded counters.
It never stores queries, URLs, response data, credentials, or exception text.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import stat
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeVar, cast

import httpx

from evidencemesh.closed_alpha_feedback import FeedbackContext
from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError

_SCHEMA_VERSION: Final = "evidencemesh.closed-alpha-governor.v1"
_CONTROL_SCHEMA_VERSION: Final = "evidencemesh.closed-alpha-control-plane.v2"
_PARTICIPANT_PATTERN: Final = re.compile(r"^p-[0-9a-f]{16}$")
_SESSION_PATTERN: Final = re.compile(r"^s-[0-9a-f]{32}$")
_PROVIDER_PATTERN: Final = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_INTENT_KINDS: Final = frozenset({"provider", "fetch", "robots", "redirect"})
_ENV_LEDGER: Final = "EVIDENCEMESH_CLOSED_ALPHA_LEDGER"
_ENV_PARTICIPANT: Final = "EVIDENCEMESH_CLOSED_ALPHA_PARTICIPANT"
_ENV_SESSION: Final = "EVIDENCEMESH_CLOSED_ALPHA_SESSION"
_ENV_PROFILE: Final = "EVIDENCEMESH_CLOSED_ALPHA_PROFILE"
_ENV_CONTROL_PLANE: Final = "EVIDENCEMESH_CLOSED_ALPHA_CONTROL_PLANE"
_ENV_NAMES: Final = (
    _ENV_LEDGER,
    _ENV_PARTICIPANT,
    _ENV_SESSION,
    _ENV_PROFILE,
    _ENV_CONTROL_PLANE,
)
_CONTROL_PLANE_ACTIVATION: Final = "rc4"
_CONSENT_VERSION: Final = "closed-alpha-a0-consent-v1"
_CONTROL_STATES: Final = frozenset({"prepared", "paused", "stopped"})
_ALPHA_PROVIDER_BUNDLES: Final = {
    "community": ("arxiv", "crossref", "github", "searxng", "wikipedia"),
    "quality": ("arxiv", "crossref", "github", "searxng", "tavily", "wikipedia"),
}
_COHORT_SLOTS: Final = (
    *((f"C{index:02d}", "community") for index in range(1, 7)),
    *((f"Q{index:02d}", "quality") for index in range(1, 3)),
)
_T = TypeVar("_T")
_LedgerIdentity = tuple[int, int, int, int]


def _private_ledger_identity(path: Path) -> _LedgerIdentity:
    """Validate one private local ledger path and return its stable identities."""

    if not path.is_absolute():
        raise BudgetConfigurationError("closed-alpha ledger path must be absolute")
    parent = path.parent
    try:
        parent_metadata = parent.lstat()
        metadata = path.lstat()
    except OSError as exc:
        raise BudgetConfigurationError("closed-alpha ledger is missing") from exc
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent.is_symlink()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o077
        or parent_metadata.st_uid != os.geteuid()
    ):
        raise BudgetConfigurationError("closed-alpha ledger directory is not private")
    try:
        if parent.resolve(strict=True) != parent.absolute():
            raise BudgetConfigurationError("closed-alpha ledger directory uses a symlink")
    except OSError as exc:
        raise BudgetConfigurationError("cannot resolve closed-alpha ledger directory") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
    ):
        raise BudgetConfigurationError("closed-alpha ledger permissions are unsafe")
    return (
        int(parent_metadata.st_dev),
        int(parent_metadata.st_ino),
        int(metadata.st_dev),
        int(metadata.st_ino),
    )


class AlphaControlState(StrEnum):
    """Shared dispatch state for the single-host closed-alpha control plane."""

    PREPARED = "prepared"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class ClosedAlphaAdmission:
    """Pseudonymous admission bound to one frozen cohort slot and consent."""

    participant_code: str
    slot_id: str
    profile: str
    consent_version: str
    consent_accepted: bool
    input_authority_attested: bool
    non_sensitive_use_attested: bool

    def __post_init__(self) -> None:
        if _PARTICIPANT_PATTERN.fullmatch(self.participant_code) is None:
            raise BudgetConfigurationError("closed-alpha participant code is invalid")
        expected_profile = dict(_COHORT_SLOTS).get(self.slot_id)
        if expected_profile is None or self.profile != expected_profile:
            raise BudgetConfigurationError("closed-alpha cohort slot or profile is invalid")
        if self.consent_version != _CONSENT_VERSION:
            raise BudgetConfigurationError("closed-alpha consent version is invalid")
        if any(
            value is not True
            for value in (
                self.consent_accepted,
                self.input_authority_attested,
                self.non_sensitive_use_attested,
            )
        ):
            raise BudgetConfigurationError("closed-alpha admission attestations are incomplete")


@dataclass(frozen=True, slots=True)
class ClosedAlphaPolicy:
    """Frozen A0 ceilings. Limits are maxima, never targets."""

    sessions_total_max: int = 40
    sessions_per_participant_max: int = 5
    provider_attempts_per_session_max: int = 6
    provider_attempts_total_max: int = 240
    tavily_attempts_community_session_max: int = 0
    tavily_attempts_quality_session_max: int = 4
    tavily_attempts_total_max: int = 40
    concurrent_sessions_max: int = 2
    request_starts_per_minute_max: int = 10

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values.values()
        ):
            raise BudgetConfigurationError(
                "closed-alpha policy limits must be non-negative integers"
            )
        positive = (
            self.sessions_total_max,
            self.sessions_per_participant_max,
            self.provider_attempts_per_session_max,
            self.provider_attempts_total_max,
            self.concurrent_sessions_max,
            self.request_starts_per_minute_max,
        )
        if any(value < 1 for value in positive):
            raise BudgetConfigurationError("closed-alpha primary policy limits must be positive")
        if self.sessions_per_participant_max > self.sessions_total_max:
            raise BudgetConfigurationError("participant session limit exceeds the global limit")
        if self.provider_attempts_per_session_max > self.provider_attempts_total_max:
            raise BudgetConfigurationError("session attempt limit exceeds the global limit")
        if self.tavily_attempts_quality_session_max > self.provider_attempts_per_session_max:
            raise BudgetConfigurationError("Tavily session limit exceeds the session attempt limit")
        if self.tavily_attempts_total_max > self.provider_attempts_total_max:
            raise BudgetConfigurationError("Tavily global limit exceeds the global attempt limit")
        if self.tavily_attempts_community_session_max != 0:
            raise BudgetConfigurationError("community Tavily attempts must remain disabled")

    @property
    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json.encode()).hexdigest()


class SQLiteAlphaControlPlane:
    """Explicitly provisioned, local-only RC4 admission and dispatch control plane."""

    def __init__(
        self,
        ledger_path: Path,
        policy: ClosedAlphaPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self.policy = policy or ClosedAlphaPolicy()
        self._clock = clock
        self._ledger_identity = _private_ledger_identity(self.ledger_path)
        self._lease_seconds = self._validate_database()

    @classmethod
    def bootstrap(
        cls,
        ledger_path: Path,
        policy: ClosedAlphaPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        lease_seconds: float = 300.0,
    ) -> SQLiteAlphaControlPlane:
        """Create one paused v2 ledger; runtime paths are never allowed to do this."""

        resolved_policy = policy or ClosedAlphaPolicy()
        if (
            not isinstance(lease_seconds, (int, float))
            or isinstance(lease_seconds, bool)
            or not math.isfinite(lease_seconds)
            or lease_seconds < 1.0
        ):
            raise BudgetConfigurationError("closed-alpha session lease is invalid")
        path = Path(ledger_path)
        cls._prepare_new_ledger(path)
        ledger_identity = _private_ledger_identity(path)
        now = cls._read_clock(clock)
        try:
            with contextlib.closing(cls._connect_path(path)) as connection:
                if _private_ledger_identity(path) != ledger_identity:
                    raise BudgetConfigurationError(
                        "closed-alpha ledger identity changed during bootstrap"
                    )
                connection.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE control_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        state TEXT NOT NULL CHECK (state IN ('prepared', 'paused', 'stopped')),
                        control_epoch INTEGER NOT NULL CHECK (control_epoch >= 1),
                        privacy_fault INTEGER NOT NULL CHECK (privacy_fault IN (0, 1)),
                        updated_at REAL NOT NULL
                    );
                    CREATE TABLE cohort_slots (
                        slot_id TEXT PRIMARY KEY,
                        profile TEXT NOT NULL CHECK (profile IN ('community', 'quality')),
                        UNIQUE(slot_id, profile)
                    );
                    CREATE TABLE participants (
                        participant_code TEXT PRIMARY KEY,
                        slot_id TEXT NOT NULL UNIQUE,
                        profile TEXT NOT NULL CHECK (profile IN ('community', 'quality')),
                        status TEXT NOT NULL CHECK (status IN ('admitted', 'withdrawn')),
                        consent_version TEXT NOT NULL,
                        consent_accepted_at REAL NOT NULL,
                        input_authority_attested INTEGER NOT NULL CHECK (
                            input_authority_attested = 1
                        ),
                        non_sensitive_use_attested INTEGER NOT NULL CHECK (
                            non_sensitive_use_attested = 1
                        ),
                        admission_epoch INTEGER NOT NULL CHECK (admission_epoch >= 1),
                        withdrawn_at REAL,
                        FOREIGN KEY(slot_id, profile) REFERENCES cohort_slots(slot_id, profile)
                    );
                    CREATE TABLE sessions (
                        session_code TEXT PRIMARY KEY,
                        participant_code TEXT NOT NULL REFERENCES participants(participant_code),
                        profile TEXT NOT NULL CHECK (profile IN ('community', 'quality')),
                        owner_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (
                            status IN ('active', 'closed', 'recovery_required')
                        ),
                        session_epoch INTEGER NOT NULL CHECK (session_epoch >= 1),
                        lease_expires_at REAL NOT NULL,
                        opened_at REAL NOT NULL,
                        closed_at REAL
                    );
                    CREATE TABLE attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token TEXT NOT NULL UNIQUE,
                        session_code TEXT NOT NULL REFERENCES sessions(session_code),
                        kind TEXT NOT NULL,
                        provider TEXT,
                        reserved_at REAL NOT NULL,
                        control_epoch INTEGER NOT NULL CHECK (control_epoch >= 1),
                        admission_epoch INTEGER NOT NULL CHECK (admission_epoch >= 1),
                        session_epoch INTEGER NOT NULL CHECK (session_epoch >= 1),
                        dispatched INTEGER NOT NULL DEFAULT 0 CHECK (dispatched IN (0, 1)),
                        dispatched_at REAL,
                        consumed_at REAL,
                        outcome TEXT NOT NULL DEFAULT 'reserved' CHECK (
                            outcome IN (
                                'reserved', 'started', 'denied_state', 'denied_epoch',
                                'denied_rate', 'denied_recovery'
                            )
                        )
                    );
                    CREATE INDEX attempts_session_idx ON attempts(session_code);
                    CREATE INDEX attempts_rate_idx ON attempts(reserved_at);
                    CREATE INDEX sessions_lease_idx ON sessions(status, lease_expires_at);
                    COMMIT;
                    """
                )
                expected = {
                    "schema_version": _CONTROL_SCHEMA_VERSION,
                    "policy_fingerprint": resolved_policy.fingerprint,
                    "policy": resolved_policy.canonical_json,
                    "consent_version": _CONSENT_VERSION,
                    "lease_seconds": repr(float(lease_seconds)),
                }
                connection.execute("BEGIN IMMEDIATE")
                connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    tuple(expected.items()),
                )
                connection.execute(
                    """
                    INSERT INTO control_state(
                        singleton, state, control_epoch, privacy_fault, updated_at
                    ) VALUES (1, 'paused', 1, 0, ?)
                    """,
                    (now,),
                )
                connection.executemany(
                    "INSERT INTO cohort_slots(slot_id, profile) VALUES (?, ?)",
                    _COHORT_SLOTS,
                )
                connection.commit()
                if _private_ledger_identity(path) != ledger_identity:
                    raise BudgetConfigurationError(
                        "closed-alpha ledger identity changed during bootstrap"
                    )
        except (OSError, sqlite3.Error) as exc:
            raise BudgetConfigurationError("cannot bootstrap closed-alpha control plane") from exc
        return cls(path, resolved_policy, clock=clock)

    @property
    def lease_seconds(self) -> float:
        return self._lease_seconds

    def admit(self, admission: ClosedAlphaAdmission) -> int:
        """Admit one participant while paused and return its immutable first epoch."""

        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = self._now()
                self._check_clock(connection, now)
                control = self._control_row(connection)
                if control["state"] != AlphaControlState.PAUSED:
                    raise BudgetConfigurationError(
                        "closed-alpha admissions require the paused state"
                    )
                connection.execute(
                    """
                    INSERT INTO participants(
                        participant_code, slot_id, profile, status, consent_version,
                        consent_accepted_at, input_authority_attested,
                        non_sensitive_use_attested, admission_epoch, withdrawn_at
                    ) VALUES (?, ?, ?, 'admitted', ?, ?, 1, 1, 1, NULL)
                    """,
                    (
                        admission.participant_code,
                        admission.slot_id,
                        admission.profile,
                        admission.consent_version,
                        now,
                    ),
                )
                self._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        return 1

    def transition(
        self,
        target: AlphaControlState | str,
        *,
        expected_state: AlphaControlState | str,
        expected_epoch: int,
    ) -> int:
        """Compare-and-swap the shared state and invalidate every pending permit."""

        try:
            target_state = AlphaControlState(target)
            source_state = AlphaControlState(expected_state)
        except ValueError as exc:
            raise BudgetConfigurationError("closed-alpha control state is invalid") from exc
        if not isinstance(expected_epoch, int) or isinstance(expected_epoch, bool):
            raise BudgetConfigurationError("closed-alpha control epoch is invalid")
        allowed = {
            AlphaControlState.PAUSED: {
                AlphaControlState.PREPARED,
                AlphaControlState.STOPPED,
            },
            AlphaControlState.PREPARED: {
                AlphaControlState.PAUSED,
                AlphaControlState.STOPPED,
            },
            AlphaControlState.STOPPED: set(),
        }
        if target_state not in allowed[source_state]:
            raise BudgetConfigurationError("closed-alpha control transition is forbidden")

        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = self._now()
                self._check_clock(connection, now)
                control = self._control_row(connection)
                if (
                    control["state"] != source_state
                    or int(control["control_epoch"]) != expected_epoch
                ):
                    raise BudgetConfigurationError("closed-alpha control CAS failed")
                if target_state is AlphaControlState.PREPARED:
                    if int(control["privacy_fault"]) != 0:
                        raise BudgetConfigurationError(
                            "closed-alpha privacy fault permanently blocks preparation"
                        )
                    self._assert_cohort_ready(connection)
                    recovery_count = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM sessions WHERE status = 'recovery_required'"
                        ).fetchone()[0]
                    )
                    if recovery_count:
                        raise BudgetConfigurationError(
                            "closed-alpha recovery must be resolved before preparation"
                        )
                next_epoch = expected_epoch + 1
                connection.execute(
                    """
                    UPDATE control_state
                    SET state = ?, control_epoch = ?, updated_at = ?
                    WHERE singleton = 1
                    """,
                    (target_state.value, next_epoch, now),
                )
                self._invalidate_reserved(connection, now, "denied_state")
                self._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        return next_epoch

    def withdraw(self, participant_code: str, *, expected_admission_epoch: int) -> int:
        """Withdraw one participant and pause the wave before any later admission point."""

        if _PARTICIPANT_PATTERN.fullmatch(participant_code) is None:
            raise BudgetConfigurationError("closed-alpha participant code is invalid")
        if (
            not isinstance(expected_admission_epoch, int)
            or isinstance(expected_admission_epoch, bool)
            or expected_admission_epoch < 1
        ):
            raise BudgetConfigurationError("closed-alpha admission epoch is invalid")
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = self._now()
                self._check_clock(connection, now)
                row = connection.execute(
                    "SELECT * FROM participants WHERE participant_code = ?",
                    (participant_code,),
                ).fetchone()
                if (
                    row is None
                    or row["status"] != "admitted"
                    or int(row["admission_epoch"]) != expected_admission_epoch
                ):
                    raise BudgetConfigurationError("closed-alpha withdrawal CAS failed")
                next_admission_epoch = expected_admission_epoch + 1
                connection.execute(
                    """
                    UPDATE participants
                    SET status = 'withdrawn', admission_epoch = ?, withdrawn_at = ?
                    WHERE participant_code = ?
                    """,
                    (next_admission_epoch, now, participant_code),
                )
                control = self._control_row(connection)
                if control["state"] == AlphaControlState.PREPARED:
                    connection.execute(
                        """
                        UPDATE control_state
                        SET state = 'paused', control_epoch = control_epoch + 1, updated_at = ?
                        WHERE singleton = 1
                        """,
                        (now,),
                    )
                    self._invalidate_reserved(connection, now, "denied_state")
                else:
                    connection.execute(
                        """
                        UPDATE attempts SET dispatched = 1, consumed_at = ?,
                            outcome = 'denied_epoch'
                        WHERE session_code IN (
                            SELECT session_code FROM sessions WHERE participant_code = ?
                        ) AND outcome = 'reserved'
                        """,
                        (now, participant_code),
                    )
                self._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        return next_admission_epoch

    def reconcile_expired_sessions(self) -> int:
        """Pause and quarantine stale owners without deleting or refunding their rows."""

        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = self._now()
                self._check_clock(connection, now)
                expired = self._reconcile_expired_sessions_locked(connection, now)
                self._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        return len(expired)

    def resolve_recovery(self, session_code: str, *, expected_control_epoch: int) -> None:
        """Close one quarantined session while retaining every budget-bearing row."""

        if _SESSION_PATTERN.fullmatch(session_code) is None:
            raise BudgetConfigurationError("closed-alpha session code is invalid")
        if (
            not isinstance(expected_control_epoch, int)
            or isinstance(expected_control_epoch, bool)
            or expected_control_epoch < 1
        ):
            raise BudgetConfigurationError("closed-alpha control epoch is invalid")
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = self._now()
                self._check_clock(connection, now)
                control = self._control_row(connection)
                if (
                    control["state"] != AlphaControlState.PAUSED
                    or int(control["control_epoch"]) != expected_control_epoch
                ):
                    raise BudgetConfigurationError(
                        "closed-alpha recovery requires the expected paused epoch"
                    )
                cursor = connection.execute(
                    """
                    UPDATE sessions SET status = 'closed', closed_at = ?
                    WHERE session_code = ? AND status = 'recovery_required'
                    """,
                    (now, session_code),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("closed-alpha session is not recoverable")
                self._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise

    def snapshot(self) -> dict[str, int | str | bool]:
        with contextlib.closing(self._connect()) as connection:
            control = self._control_row(connection)
            admitted = int(
                connection.execute(
                    "SELECT COUNT(*) FROM participants WHERE status = 'admitted'"
                ).fetchone()[0]
            )
            attempts = int(connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])
            sessions = int(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
            recovery = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE status = 'recovery_required'"
                ).fetchone()[0]
            )
        return {
            "schema_version": _CONTROL_SCHEMA_VERSION,
            "state": str(control["state"]),
            "control_epoch": int(control["control_epoch"]),
            "admitted_participants": admitted,
            "sessions": sessions,
            "global_attempts": attempts,
            "recovery_required_sessions": recovery,
            "privacy_fault": bool(control["privacy_fault"]),
            "distributed_global_guarantee": False,
        }

    def feedback_context(
        self,
        participant_code: str,
        session_code: str,
    ) -> FeedbackContext | None:
        """Return report fields derived only from a closed authoritative session."""

        if (
            _PARTICIPANT_PATTERN.fullmatch(participant_code) is None
            or _SESSION_PATTERN.fullmatch(session_code) is None
        ):
            return None
        try:
            with contextlib.closing(self._connect()) as connection:
                control = self._control_row(connection)
                if (
                    control["state"] == AlphaControlState.STOPPED
                    or int(control["privacy_fault"]) != 0
                ):
                    return None
                row = connection.execute(
                    """
                    SELECT p.slot_id, p.profile,
                        COUNT(a.id) AS provider_attempts,
                        COALESCE(SUM(CASE WHEN a.provider = 'tavily' THEN 1 ELSE 0 END), 0)
                            AS tavily_attempts
                    FROM sessions AS s
                    JOIN participants AS p
                      ON p.participant_code = s.participant_code
                    LEFT JOIN attempts AS a ON a.session_code = s.session_code
                    WHERE s.session_code = ? AND s.participant_code = ?
                      AND s.status = 'closed'
                      AND p.status = 'admitted'
                      AND p.consent_version = ?
                      AND p.input_authority_attested = 1
                      AND p.non_sensitive_use_attested = 1
                    GROUP BY p.slot_id, p.profile
                    """,
                    (session_code, participant_code, _CONSENT_VERSION),
                ).fetchone()
                if row is None:
                    return None
                return FeedbackContext(
                    slot_id=str(row["slot_id"]),
                    profile=str(row["profile"]),
                    provider_attempts=int(row["provider_attempts"]),
                    tavily_attempts=int(row["tavily_attempts"]),
                )
        except (OSError, sqlite3.Error, BudgetConfigurationError, TypeError, ValueError):
            return None

    def report_allowed(self, participant_code: str, session_code: str) -> bool:
        """Expose the minimal read-only admission view used by the feedback store."""

        if (
            _PARTICIPANT_PATTERN.fullmatch(participant_code) is None
            or _SESSION_PATTERN.fullmatch(session_code) is None
        ):
            return False
        try:
            self._assert_ledger_safe()
            with contextlib.closing(self._connect()) as connection:
                control = self._control_row(connection)
                if (
                    control["state"] != AlphaControlState.PREPARED
                    or int(control["privacy_fault"]) != 0
                ):
                    return False
                row = connection.execute(
                    """
                    SELECT 1 FROM sessions AS s
                    JOIN participants AS p
                      ON p.participant_code = s.participant_code
                    WHERE s.session_code = ? AND s.participant_code = ?
                      AND s.status IN ('active', 'closed')
                      AND p.status = 'admitted'
                      AND p.consent_version = ?
                      AND p.input_authority_attested = 1
                      AND p.non_sensitive_use_attested = 1
                    """,
                    (session_code, participant_code, _CONSENT_VERSION),
                ).fetchone()
                return row is not None
        except (OSError, sqlite3.Error, BudgetConfigurationError):
            return False

    def advance_feedback_clock(self, timestamp: float) -> bool:
        """Persist the UTC retention high-water and trip privacy fault on rollback."""

        if (
            not isinstance(timestamp, (int, float))
            or isinstance(timestamp, bool)
            or not math.isfinite(timestamp)
        ):
            self.record_privacy_fault()
            return False
        observed = float(timestamp)
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = self._now()
                self._check_clock(connection, now)
                row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'feedback_clock_high_water'"
                ).fetchone()
                if row is not None and observed < float(row["value"]):
                    self._set_privacy_fault_locked(connection, now)
                    self._write_clock(connection, now)
                    connection.commit()
                    return False
                connection.execute(
                    """
                    INSERT INTO metadata(key, value)
                    VALUES ('feedback_clock_high_water', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (repr(observed),),
                )
                self._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        return True

    def record_privacy_fault(self) -> None:
        """Durably pause dispatch and make the privacy fault non-clearable."""

        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = self._now()
                self._check_clock(connection, now)
                self._set_privacy_fault_locked(connection, now)
                self._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise

    def withdrawal_committed(self, participant_code: str) -> bool:
        """Return true only for a durable withdrawn registry row."""

        if _PARTICIPANT_PATTERN.fullmatch(participant_code) is None:
            return False
        try:
            self._assert_ledger_safe()
            with contextlib.closing(self._connect()) as connection:
                row = connection.execute(
                    """
                    SELECT 1 FROM participants
                    WHERE participant_code = ? AND status = 'withdrawn'
                      AND withdrawn_at IS NOT NULL
                    """,
                    (participant_code,),
                ).fetchone()
                return row is not None
        except (OSError, sqlite3.Error, BudgetConfigurationError):
            return False

    @staticmethod
    def _read_clock(clock: Callable[[], float]) -> float:
        now = clock()
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
            raise BudgetConfigurationError("closed-alpha governor clock is invalid")
        return float(now)

    def _now(self) -> float:
        return self._read_clock(self._clock)

    @staticmethod
    def _prepare_new_ledger(path: Path) -> None:
        if not path.is_absolute():
            raise BudgetConfigurationError("closed-alpha ledger path must be absolute")
        parent = path.parent
        if not parent.exists():
            try:
                parent.mkdir(mode=0o700, parents=False)
            except OSError as exc:
                raise BudgetConfigurationError(
                    "cannot create closed-alpha ledger directory"
                ) from exc
        try:
            metadata = parent.lstat()
        except OSError as exc:
            raise BudgetConfigurationError("cannot inspect closed-alpha ledger directory") from exc
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or parent.is_symlink()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise BudgetConfigurationError("closed-alpha ledger directory is not private")
        try:
            if parent.resolve(strict=True) != parent.absolute():
                raise BudgetConfigurationError("closed-alpha ledger directory uses a symlink")
        except OSError as exc:
            raise BudgetConfigurationError("cannot resolve closed-alpha ledger directory") from exc
        if path.exists() or path.is_symlink():
            raise BudgetConfigurationError("closed-alpha control-plane ledger already exists")
        parent_descriptor = -1
        descriptor = -1
        try:
            parent_descriptor = os.open(
                parent,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            descriptor = os.open(
                path.name,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=parent_descriptor,
            )
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            os.fsync(parent_descriptor)
        except OSError as exc:
            raise BudgetConfigurationError("cannot create closed-alpha ledger") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if parent_descriptor >= 0:
                os.close(parent_descriptor)

    @staticmethod
    def _connect_path(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, isolation_level=None, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _connect(self) -> sqlite3.Connection:
        self._assert_ledger_safe()
        connection = self._connect_path(self.ledger_path)
        try:
            self._assert_ledger_safe()
        except BaseException:
            connection.close()
            raise
        return connection

    def _assert_ledger_safe(self) -> None:
        if _private_ledger_identity(self.ledger_path) != self._ledger_identity:
            raise BudgetConfigurationError("closed-alpha ledger identity changed")

    def _validate_database(self) -> float:
        try:
            with contextlib.closing(self._connect()) as connection:
                rows = {
                    str(row["key"]): str(row["value"])
                    for row in connection.execute("SELECT key, value FROM metadata")
                }
                expected = {
                    "schema_version": _CONTROL_SCHEMA_VERSION,
                    "policy_fingerprint": self.policy.fingerprint,
                    "policy": self.policy.canonical_json,
                    "consent_version": _CONSENT_VERSION,
                }
                if any(rows.get(key) != value for key, value in expected.items()):
                    raise BudgetConfigurationError(
                        "closed-alpha control-plane policy or schema drifted"
                    )
                lease_seconds = float(rows["lease_seconds"])
                if not math.isfinite(lease_seconds) or lease_seconds < 1.0:
                    raise BudgetConfigurationError("closed-alpha session lease is invalid")
                slots = tuple(
                    (str(row["slot_id"]), str(row["profile"]))
                    for row in connection.execute(
                        "SELECT slot_id, profile FROM cohort_slots ORDER BY slot_id"
                    )
                )
                if slots != tuple(sorted(_COHORT_SLOTS)):
                    raise BudgetConfigurationError("closed-alpha cohort slots drifted")
                self._control_row(connection)
                return lease_seconds
        except BudgetConfigurationError:
            raise
        except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            raise BudgetConfigurationError("cannot validate closed-alpha control plane") from exc

    @staticmethod
    def _control_row(connection: sqlite3.Connection) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT state, control_epoch, privacy_fault
            FROM control_state WHERE singleton = 1
            """
        ).fetchone()
        if (
            row is None
            or str(row["state"]) not in _CONTROL_STATES
            or not isinstance(row["control_epoch"], int)
            or int(row["control_epoch"]) < 1
            or not isinstance(row["privacy_fault"], int)
            or int(row["privacy_fault"]) not in {0, 1}
        ):
            raise BudgetConfigurationError("closed-alpha control state is invalid")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _check_clock(connection: sqlite3.Connection, now: float) -> None:
        row = connection.execute("SELECT value FROM metadata WHERE key = 'last_clock'").fetchone()
        if row is not None and now < float(row["value"]):
            raise BudgetConfigurationError("closed-alpha governor clock moved backwards")

    @staticmethod
    def _write_clock(connection: sqlite3.Connection, now: float) -> None:
        connection.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('last_clock', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (repr(now),),
        )

    @staticmethod
    def _invalidate_reserved(
        connection: sqlite3.Connection,
        now: float,
        outcome: str,
    ) -> None:
        connection.execute(
            """
            UPDATE attempts SET dispatched = 1, consumed_at = ?, outcome = ?
            WHERE outcome = 'reserved'
            """,
            (now, outcome),
        )

    @classmethod
    def _set_privacy_fault_locked(
        cls,
        connection: sqlite3.Connection,
        now: float,
    ) -> None:
        control = cls._control_row(connection)
        if int(control["privacy_fault"]) == 0:
            if control["state"] == AlphaControlState.PREPARED:
                connection.execute(
                    """
                    UPDATE control_state
                    SET state = 'paused', control_epoch = control_epoch + 1,
                        privacy_fault = 1, updated_at = ?
                    WHERE singleton = 1
                    """,
                    (now,),
                )
            else:
                connection.execute(
                    """
                    UPDATE control_state SET privacy_fault = 1, updated_at = ?
                    WHERE singleton = 1
                    """,
                    (now,),
                )
        cls._invalidate_reserved(connection, now, "denied_state")

    @classmethod
    def _reconcile_expired_sessions_locked(
        cls,
        connection: sqlite3.Connection,
        now: float,
    ) -> tuple[str, ...]:
        """Quarantine every expired owner while the caller holds the write lock."""

        expired = tuple(
            str(row["session_code"])
            for row in connection.execute(
                """
                SELECT session_code FROM sessions
                WHERE status = 'active' AND lease_expires_at <= ?
                """,
                (now,),
            )
        )
        if not expired:
            return ()
        connection.execute(
            """
            UPDATE attempts SET dispatched = 1, consumed_at = ?,
                outcome = 'denied_recovery'
            WHERE session_code IN (
                SELECT session_code FROM sessions
                WHERE status = 'active' AND lease_expires_at <= ?
            ) AND outcome = 'reserved'
            """,
            (now, now),
        )
        connection.execute(
            """
            UPDATE sessions SET status = 'recovery_required'
            WHERE status = 'active' AND lease_expires_at <= ?
            """,
            (now,),
        )
        control = cls._control_row(connection)
        if control["state"] == AlphaControlState.PREPARED:
            connection.execute(
                """
                UPDATE control_state SET state = 'paused',
                    control_epoch = control_epoch + 1, updated_at = ?
                WHERE singleton = 1
                """,
                (now,),
            )
            cls._invalidate_reserved(connection, now, "denied_state")
        return expired

    @staticmethod
    def _assert_cohort_ready(connection: sqlite3.Connection) -> None:
        rows = tuple(
            (str(row["slot_id"]), str(row["profile"]))
            for row in connection.execute(
                """
                SELECT slot_id, profile FROM participants
                WHERE status = 'admitted' AND consent_version = ?
                    AND input_authority_attested = 1
                    AND non_sensitive_use_attested = 1
                ORDER BY slot_id
                """,
                (_CONSENT_VERSION,),
            )
        )
        if rows != tuple(sorted(_COHORT_SLOTS)):
            raise BudgetConfigurationError("closed-alpha cohort admission is incomplete")


@dataclass(frozen=True, slots=True)
class ClosedAlphaSession:
    """Pseudonymous execution context for one single-task alpha session."""

    participant_code: str
    session_code: str
    profile: str

    def __post_init__(self) -> None:
        if _PARTICIPANT_PATTERN.fullmatch(self.participant_code) is None:
            raise BudgetConfigurationError("closed-alpha participant code is invalid")
        if _SESSION_PATTERN.fullmatch(self.session_code) is None:
            raise BudgetConfigurationError("closed-alpha session code is invalid")
        if self.profile not in {"community", "quality"}:
            raise BudgetConfigurationError("closed-alpha profile must be community or quality")


@dataclass(frozen=True, slots=True)
class DispatchIntent:
    """One outbound start to reserve without retaining its destination."""

    kind: str
    provider: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _INTENT_KINDS:
            raise BudgetConfigurationError("closed-alpha dispatch intent kind is invalid")
        if self.kind == "provider":
            if self.provider is None or _PROVIDER_PATTERN.fullmatch(self.provider) is None:
                raise BudgetConfigurationError(
                    "provider dispatch intent requires a safe provider name"
                )
        elif self.provider is not None:
            raise BudgetConfigurationError("non-provider dispatch intents cannot name a provider")


@dataclass(frozen=True, slots=True)
class DispatchPermit:
    """Opaque single-use authorization bound to one governor and session."""

    token: str
    session_code: str
    kind: str
    provider: str | None
    _governor_id: str = field(repr=False)
    control_epoch: int = 0
    admission_epoch: int = 0
    session_epoch: int = 0


class SQLiteBudgetGovernor:
    """Atomic local coordinator for CLI/MCP processes sharing one SQLite ledger.

    This is deliberately a single-host scope. Independent ledgers on multiple
    machines do not form a global budget and must never be described as one.
    """

    _AUDITED_PROVIDERS: Final = {
        "evidencemesh.providers.arxiv.ArxivProvider": "arxiv",
        "evidencemesh.providers.crossref.CrossrefProvider": "crossref",
        "evidencemesh.providers.github.GitHubProvider": "github",
        "evidencemesh.providers.searxng.SearxngProvider": "searxng",
        "evidencemesh.providers.tavily.TavilyProvider": "tavily",
        "evidencemesh.providers.wikipedia.WikipediaProvider": "wikipedia",
    }

    def __init__(
        self,
        ledger_path: Path,
        session: ClosedAlphaSession,
        policy: ClosedAlphaPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        _require_rc4: bool = False,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self.session = session
        self.policy = policy or ClosedAlphaPolicy()
        self._clock = clock
        self._owner_id = secrets.token_hex(16)
        self._governor_id = secrets.token_hex(16)
        self._active_permit: ContextVar[DispatchPermit | None] = ContextVar(
            f"evidencemesh_closed_alpha_permit_{self._governor_id}",
            default=None,
        )
        self._lock = asyncio.Lock()
        self._attached_clients: dict[int, httpx.AsyncClient] = {}
        self._opened = False
        self._closed = False
        self._poisoned = False
        self._rc4 = _require_rc4
        self._lease_seconds = 0.0
        self._prepare_ledger_file()
        self._ledger_identity = _private_ledger_identity(self.ledger_path)
        self._initialize_database()

    @property
    def enabled(self) -> bool:
        return not self._closed

    @property
    def scope(self) -> str:
        return "single_host_shared_sqlite"

    @classmethod
    def environment_requested(cls) -> bool:
        return any(os.getenv(name) is not None for name in _ENV_NAMES)

    @classmethod
    def from_env(cls) -> SQLiteBudgetGovernor | None:
        values = {name: os.getenv(name) for name in _ENV_NAMES}
        if all(value is None for value in values.values()):
            return None
        if any(value is None or not value for value in values.values()):
            raise BudgetConfigurationError(
                "closed-alpha RC4 control-plane environment is incomplete"
            )
        if values[_ENV_CONTROL_PLANE] != _CONTROL_PLANE_ACTIVATION:
            raise BudgetConfigurationError("closed-alpha RC4 activation marker is invalid")
        ledger = Path(str(values[_ENV_LEDGER]))
        if not ledger.is_absolute():
            raise BudgetConfigurationError("closed-alpha ledger path must be absolute")
        return cls(
            ledger,
            ClosedAlphaSession(
                participant_code=str(values[_ENV_PARTICIPANT]),
                session_code=str(values[_ENV_SESSION]),
                profile=str(values[_ENV_PROFILE]),
            ),
            _require_rc4=True,
        )

    def validate_provider_configuration(
        self,
        provider_names: Sequence[str],
        searxng_fallback_urls: Sequence[str],
        *,
        deployment_profile: str | None = None,
    ) -> None:
        """Reject configurations that cannot build only audited providers."""

        audited_names = frozenset(self._AUDITED_PROVIDERS.values())
        unsupported = sorted(set(provider_names) - audited_names)
        if unsupported:
            raise BudgetConfigurationError(
                "closed-alpha mode accepts only audited single-dispatch HTTPX providers"
            )
        if searxng_fallback_urls:
            raise BudgetConfigurationError(
                "closed-alpha mode forbids automatic SearXNG fallback dispatches"
            )
        if self._rc4:
            if deployment_profile != self.session.profile:
                raise BudgetConfigurationError(
                    "closed-alpha deployment profile does not match admission"
                )
            expected = _ALPHA_PROVIDER_BUNDLES[self.session.profile]
            if tuple(provider_names) != expected:
                raise BudgetConfigurationError(
                    "closed-alpha RC4 requires the exact admitted provider bundle"
                )

    def validate_provider_bundle(
        self,
        provider_names: Sequence[str],
        *,
        deployment_profile: str,
    ) -> None:
        """Ensure custom and factory-built RC4 providers retain the exact bundle."""

        if not self._rc4:
            return
        if deployment_profile != self.session.profile:
            raise BudgetConfigurationError(
                "closed-alpha deployment profile does not match admission"
            )
        if tuple(provider_names) != _ALPHA_PROVIDER_BUNDLES[self.session.profile]:
            raise BudgetConfigurationError(
                "closed-alpha RC4 requires the exact admitted provider bundle"
            )

    def validate_provider(self, provider: object, client: httpx.AsyncClient) -> str:
        provider_type = f"{type(provider).__module__}.{type(provider).__qualname__}"
        expected_name = self._AUDITED_PROVIDERS.get(provider_type)
        actual_name = getattr(provider, "name", None)
        if expected_name is None or actual_name != expected_name:
            raise BudgetConfigurationError(
                "closed-alpha mode accepts only audited single-dispatch HTTPX providers"
            )
        if getattr(provider, "client", None) is not client:
            raise BudgetConfigurationError(
                "closed-alpha provider does not use the governed HTTPX client"
            )
        return expected_name

    def _validate_rc4_dispatch(self, kind: str, provider: str | None) -> None:
        if kind == "provider" and provider not in _ALPHA_PROVIDER_BUNDLES[self.session.profile]:
            raise BudgetConfigurationError(
                "closed-alpha RC4 provider is outside the admitted bundle"
            )

    def _validate_rc4_intents(self, intents: Sequence[DispatchIntent]) -> None:
        for intent in intents:
            self._validate_rc4_dispatch(intent.kind, intent.provider)

    def _validate_rc4_permit(self, permit: DispatchPermit) -> None:
        self._validate_rc4_dispatch(permit.kind, permit.provider)

    def attach_client(self, client: httpx.AsyncClient) -> None:
        if self._closed:
            raise BudgetConfigurationError("closed-alpha governor is closed")
        client_id = id(client)
        if client_id in self._attached_clients:
            return
        client.event_hooks["request"].insert(0, self._on_request)
        self._attached_clients[client_id] = client

    async def reserve_batch(
        self,
        intents: Sequence[DispatchIntent],
    ) -> list[DispatchPermit]:
        if self._closed:
            raise BudgetConfigurationError("closed-alpha governor is closed")
        if self._poisoned:
            raise BudgetConfigurationError("closed-alpha governor is fail-closed")
        frozen = tuple(intents)
        if not frozen:
            raise BudgetConfigurationError("dispatch reservation batch cannot be empty")
        if self._rc4:
            self._validate_rc4_intents(frozen)
        tokens = tuple(secrets.token_hex(16) for _ in frozen)
        control_epoch, admission_epoch, session_epoch = await self._database_call(
            lambda: self._reserve_sync(frozen, tokens)
        )
        self._opened = True
        return [
            DispatchPermit(
                token=token,
                session_code=self.session.session_code,
                kind=intent.kind,
                provider=intent.provider,
                _governor_id=self._governor_id,
                control_epoch=control_epoch,
                admission_epoch=admission_epoch,
                session_epoch=session_epoch,
            )
            for intent, token in zip(frozen, tokens, strict=True)
        ]

    @contextmanager
    def capture(self, permit: DispatchPermit) -> Iterator[None]:
        if self._closed or self._poisoned:
            raise BudgetConfigurationError("closed-alpha governor is not dispatchable")
        if permit._governor_id != self._governor_id:
            raise BudgetConfigurationError("dispatch permit belongs to another governor")
        if permit.session_code != self.session.session_code:
            raise BudgetConfigurationError("dispatch permit belongs to another session")
        if self._active_permit.get() is not None:
            raise BudgetConfigurationError("nested dispatch permits are forbidden")
        token = self._active_permit.set(permit)
        try:
            yield
        finally:
            self._active_permit.reset(token)

    async def snapshot(self) -> dict[str, int | str | bool]:
        return await self._database_call(self._snapshot_sync)

    async def aclose(self) -> None:
        if self._closed:
            return
        try:
            if self._opened and not self._poisoned:
                await self._database_call(self._close_session_sync)
        finally:
            # Keep the request hook attached as a poison pill. A shared client
            # must not become ungoverned merely because its session was closed.
            self._closed = True

    async def _on_request(self, _: httpx.Request) -> None:
        if self._closed or self._poisoned:
            self._poisoned = True
            raise BudgetConfigurationError("closed-alpha governor is not dispatchable")
        permit = self._active_permit.get()
        if permit is None:
            self._poisoned = True
            raise BudgetConfigurationError("HTTP dispatch has no closed-alpha permit")
        await self._database_call(lambda: self._consume_sync(permit))

    async def _database_call(self, operation: Callable[[], _T]) -> _T:
        async with self._lock:
            if self._closed or self._poisoned:
                raise BudgetConfigurationError("closed-alpha governor is fail-closed")
            try:
                self._assert_ledger_safe()
                return await asyncio.to_thread(operation)
            except BudgetExceededError:
                raise
            except BudgetConfigurationError:
                self._poisoned = True
                raise
            except (OSError, sqlite3.Error) as exc:
                self._poisoned = True
                raise BudgetConfigurationError("closed-alpha ledger operation failed") from exc

    def _prepare_ledger_file(self) -> None:
        if not self.ledger_path.is_absolute():
            raise BudgetConfigurationError("closed-alpha ledger path must be absolute")
        parent = self.ledger_path.parent
        if not parent.exists():
            try:
                parent.mkdir(mode=0o700, parents=False)
            except OSError as exc:
                raise BudgetConfigurationError(
                    "cannot create closed-alpha ledger directory"
                ) from exc
        try:
            parent_metadata = parent.lstat()
        except OSError as exc:
            raise BudgetConfigurationError("cannot inspect closed-alpha ledger directory") from exc
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or parent.is_symlink()
            or stat.S_IMODE(parent_metadata.st_mode) & 0o077
        ):
            raise BudgetConfigurationError("closed-alpha ledger directory is not private")
        try:
            if parent.resolve(strict=True) != parent.absolute():
                raise BudgetConfigurationError("closed-alpha ledger directory uses a symlink")
        except OSError as exc:
            raise BudgetConfigurationError("cannot resolve closed-alpha ledger directory") from exc
        if self.ledger_path.exists() or self.ledger_path.is_symlink():
            self._assert_ledger_safe()
            return
        if self._rc4:
            raise BudgetConfigurationError(
                "closed-alpha RC4 requires an explicitly bootstrapped ledger"
            )
        try:
            descriptor = os.open(
                self.ledger_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.close(descriptor)
        except OSError as exc:
            raise BudgetConfigurationError("cannot create closed-alpha ledger") from exc
        self._assert_ledger_safe()

    def _assert_ledger_safe(self) -> None:
        current = _private_ledger_identity(self.ledger_path)
        expected = getattr(self, "_ledger_identity", None)
        if expected is not None and current != expected:
            raise BudgetConfigurationError("closed-alpha ledger identity changed")

    def _connect(self) -> sqlite3.Connection:
        self._assert_ledger_safe()
        connection = sqlite3.connect(
            self.ledger_path,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            self._assert_ledger_safe()
        except BaseException:
            connection.close()
            raise
        return connection

    def _initialize_database(self) -> None:
        if self._rc4:
            try:
                with contextlib.closing(self._connect()) as connection:
                    rows = {
                        str(row["key"]): str(row["value"])
                        for row in connection.execute("SELECT key, value FROM metadata")
                    }
                    expected = {
                        "schema_version": _CONTROL_SCHEMA_VERSION,
                        "policy_fingerprint": self.policy.fingerprint,
                        "policy": self.policy.canonical_json,
                        "consent_version": _CONSENT_VERSION,
                    }
                    if any(rows.get(key) != value for key, value in expected.items()):
                        raise BudgetConfigurationError("closed-alpha RC4 policy or schema drifted")
                    self._lease_seconds = float(rows["lease_seconds"])
                    if not math.isfinite(self._lease_seconds) or self._lease_seconds < 1.0:
                        raise BudgetConfigurationError("closed-alpha session lease is invalid")
                    SQLiteAlphaControlPlane._control_row(connection)
                    admission = connection.execute(
                        """
                        SELECT profile, status, consent_version,
                            input_authority_attested, non_sensitive_use_attested
                        FROM participants WHERE participant_code = ?
                        """,
                        (self.session.participant_code,),
                    ).fetchone()
                    if (
                        admission is None
                        or admission["status"] != "admitted"
                        or admission["profile"] != self.session.profile
                        or admission["consent_version"] != _CONSENT_VERSION
                        or int(admission["input_authority_attested"]) != 1
                        or int(admission["non_sensitive_use_attested"]) != 1
                    ):
                        raise BudgetConfigurationError(
                            "closed-alpha participant is not admitted for this profile"
                        )
            except BudgetConfigurationError:
                raise
            except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
                raise BudgetConfigurationError(
                    "cannot initialize closed-alpha RC4 governor"
                ) from exc
            self._assert_ledger_safe()
            return
        try:
            with contextlib.closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_code TEXT PRIMARY KEY,
                        participant_code TEXT NOT NULL,
                        profile TEXT NOT NULL CHECK (profile IN ('community', 'quality')),
                        owner_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('active', 'closed')),
                        opened_at REAL NOT NULL,
                        closed_at REAL
                    );
                    CREATE TABLE IF NOT EXISTS attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token TEXT NOT NULL UNIQUE,
                        session_code TEXT NOT NULL REFERENCES sessions(session_code),
                        kind TEXT NOT NULL,
                        provider TEXT,
                        reserved_at REAL NOT NULL,
                        dispatched INTEGER NOT NULL DEFAULT 0 CHECK (dispatched IN (0, 1)),
                        dispatched_at REAL
                    );
                    CREATE INDEX IF NOT EXISTS attempts_session_idx
                        ON attempts(session_code);
                    CREATE INDEX IF NOT EXISTS attempts_rate_idx
                        ON attempts(reserved_at);
                    """
                )
                expected = {
                    "schema_version": _SCHEMA_VERSION,
                    "policy_fingerprint": self.policy.fingerprint,
                    "policy": self.policy.canonical_json,
                }
                rows = {
                    str(row["key"]): str(row["value"])
                    for row in connection.execute("SELECT key, value FROM metadata")
                }
                if rows:
                    if any(rows.get(key) != value for key, value in expected.items()):
                        raise BudgetConfigurationError(
                            "closed-alpha ledger policy or schema drifted"
                        )
                else:
                    connection.executemany(
                        "INSERT INTO metadata(key, value) VALUES (?, ?)",
                        tuple(expected.items()),
                    )
                connection.commit()
        except BudgetConfigurationError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise BudgetConfigurationError("cannot initialize closed-alpha ledger") from exc
        self._assert_ledger_safe()

    def _reserve_sync(
        self,
        intents: tuple[DispatchIntent, ...],
        tokens: tuple[str, ...],
    ) -> tuple[int, int, int]:
        if self._rc4:
            return self._reserve_rc4_sync(intents, tokens)
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = SQLiteAlphaControlPlane._read_clock(self._clock)
                last_clock_row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'last_clock'"
                ).fetchone()
                if last_clock_row is not None and now < float(last_clock_row["value"]):
                    raise BudgetConfigurationError("closed-alpha governor clock moved backwards")

                session_row = connection.execute(
                    "SELECT * FROM sessions WHERE session_code = ?",
                    (self.session.session_code,),
                ).fetchone()
                if session_row is None:
                    total_sessions = int(
                        connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                    )
                    participant_sessions = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM sessions WHERE participant_code = ?",
                            (self.session.participant_code,),
                        ).fetchone()[0]
                    )
                    active_sessions = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
                        ).fetchone()[0]
                    )
                    if total_sessions >= self.policy.sessions_total_max:
                        raise BudgetExceededError("closed-alpha global session budget exhausted")
                    if participant_sessions >= self.policy.sessions_per_participant_max:
                        raise BudgetExceededError(
                            "closed-alpha participant session budget exhausted"
                        )
                    if active_sessions >= self.policy.concurrent_sessions_max:
                        raise BudgetExceededError(
                            "closed-alpha concurrent session budget exhausted"
                        )
                    connection.execute(
                        """
                        INSERT INTO sessions(
                            session_code, participant_code, profile, owner_id,
                            status, opened_at, closed_at
                        ) VALUES (?, ?, ?, ?, 'active', ?, NULL)
                        """,
                        (
                            self.session.session_code,
                            self.session.participant_code,
                            self.session.profile,
                            self._owner_id,
                            now,
                        ),
                    )
                else:
                    if (
                        session_row["participant_code"] != self.session.participant_code
                        or session_row["profile"] != self.session.profile
                    ):
                        raise BudgetConfigurationError("closed-alpha session identity drifted")
                    if (
                        session_row["status"] != "active"
                        or session_row["owner_id"] != self._owner_id
                    ):
                        raise BudgetConfigurationError(
                            "closed-alpha session is not owned by this process"
                        )

                batch_size = len(intents)
                session_attempts = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts WHERE session_code = ?",
                        (self.session.session_code,),
                    ).fetchone()[0]
                )
                global_attempts = int(
                    connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
                )
                if session_attempts + batch_size > self.policy.provider_attempts_per_session_max:
                    raise BudgetExceededError("closed-alpha session dispatch budget exhausted")
                if global_attempts + batch_size > self.policy.provider_attempts_total_max:
                    raise BudgetExceededError("closed-alpha global dispatch budget exhausted")

                tavily_batch = sum(intent.provider == "tavily" for intent in intents)
                session_tavily = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM attempts
                        WHERE session_code = ? AND provider = 'tavily'
                        """,
                        (self.session.session_code,),
                    ).fetchone()[0]
                )
                global_tavily = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts WHERE provider = 'tavily'"
                    ).fetchone()[0]
                )
                tavily_session_max = (
                    self.policy.tavily_attempts_quality_session_max
                    if self.session.profile == "quality"
                    else self.policy.tavily_attempts_community_session_max
                )
                if session_tavily + tavily_batch > tavily_session_max:
                    raise BudgetExceededError("closed-alpha Tavily session budget exhausted")
                if global_tavily + tavily_batch > self.policy.tavily_attempts_total_max:
                    raise BudgetExceededError("closed-alpha global Tavily budget exhausted")

                recent_starts_or_slots = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM attempts
                        WHERE (dispatched = 0 AND reserved_at > ?)
                           OR (dispatched_at IS NOT NULL AND dispatched_at > ?)
                        """,
                        (now - 60.0, now - 60.0),
                    ).fetchone()[0]
                )
                if recent_starts_or_slots + batch_size > self.policy.request_starts_per_minute_max:
                    raise BudgetExceededError("closed-alpha rolling request-start budget exhausted")

                connection.executemany(
                    """
                    INSERT INTO attempts(
                        token, session_code, kind, provider, reserved_at, dispatched
                    ) VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (
                        (
                            token,
                            self.session.session_code,
                            intent.kind,
                            intent.provider,
                            now,
                        )
                        for intent, token in zip(intents, tokens, strict=True)
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('last_clock', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (repr(now),),
                )
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        return (0, 0, 0)

    def _reserve_rc4_sync(
        self,
        intents: tuple[DispatchIntent, ...],
        tokens: tuple[str, ...],
    ) -> tuple[int, int, int]:
        self._validate_rc4_intents(intents)
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = SQLiteAlphaControlPlane._read_clock(self._clock)
                SQLiteAlphaControlPlane._check_clock(connection, now)
                expired = SQLiteAlphaControlPlane._reconcile_expired_sessions_locked(
                    connection, now
                )
                if expired:
                    SQLiteAlphaControlPlane._write_clock(connection, now)
                    connection.commit()
                    raise BudgetExceededError(
                        "closed-alpha session recovery is required; control plane paused"
                    )

                control = SQLiteAlphaControlPlane._control_row(connection)
                if int(control["privacy_fault"]) != 0:
                    raise BudgetExceededError("closed-alpha privacy fault blocks dispatch")
                if control["state"] != AlphaControlState.PREPARED:
                    raise BudgetExceededError(f"closed-alpha control plane is {control['state']}")
                control_epoch = int(control["control_epoch"])
                admission = connection.execute(
                    "SELECT * FROM participants WHERE participant_code = ?",
                    (self.session.participant_code,),
                ).fetchone()
                if (
                    admission is None
                    or admission["status"] != "admitted"
                    or admission["profile"] != self.session.profile
                    or admission["consent_version"] != _CONSENT_VERSION
                    or int(admission["input_authority_attested"]) != 1
                    or int(admission["non_sensitive_use_attested"]) != 1
                ):
                    raise BudgetConfigurationError("closed-alpha participant admission is invalid")
                admission_epoch = int(admission["admission_epoch"])

                session_row = connection.execute(
                    "SELECT * FROM sessions WHERE session_code = ?",
                    (self.session.session_code,),
                ).fetchone()
                if session_row is None:
                    total_sessions = int(
                        connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                    )
                    participant_sessions = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM sessions WHERE participant_code = ?",
                            (self.session.participant_code,),
                        ).fetchone()[0]
                    )
                    active_sessions = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
                        ).fetchone()[0]
                    )
                    if total_sessions >= self.policy.sessions_total_max:
                        raise BudgetExceededError("closed-alpha global session budget exhausted")
                    if participant_sessions >= self.policy.sessions_per_participant_max:
                        raise BudgetExceededError(
                            "closed-alpha participant session budget exhausted"
                        )
                    if active_sessions >= self.policy.concurrent_sessions_max:
                        raise BudgetExceededError(
                            "closed-alpha concurrent session budget exhausted"
                        )
                    session_epoch = 1
                    connection.execute(
                        """
                        INSERT INTO sessions(
                            session_code, participant_code, profile, owner_id, status,
                            session_epoch, lease_expires_at, opened_at, closed_at
                        ) VALUES (?, ?, ?, ?, 'active', 1, ?, ?, NULL)
                        """,
                        (
                            self.session.session_code,
                            self.session.participant_code,
                            self.session.profile,
                            self._owner_id,
                            now + self._lease_seconds,
                            now,
                        ),
                    )
                else:
                    if (
                        session_row["participant_code"] != self.session.participant_code
                        or session_row["profile"] != self.session.profile
                    ):
                        raise BudgetConfigurationError("closed-alpha session identity drifted")
                    if (
                        session_row["status"] != "active"
                        or session_row["owner_id"] != self._owner_id
                    ):
                        raise BudgetConfigurationError(
                            "closed-alpha session is not owned by this process"
                        )
                    session_epoch = int(session_row["session_epoch"])

                batch_size = len(intents)
                session_attempts = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts WHERE session_code = ?",
                        (self.session.session_code,),
                    ).fetchone()[0]
                )
                global_attempts = int(
                    connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
                )
                if session_attempts + batch_size > self.policy.provider_attempts_per_session_max:
                    raise BudgetExceededError("closed-alpha session dispatch budget exhausted")
                if global_attempts + batch_size > self.policy.provider_attempts_total_max:
                    raise BudgetExceededError("closed-alpha global dispatch budget exhausted")

                tavily_batch = sum(intent.provider == "tavily" for intent in intents)
                session_tavily = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM attempts
                        WHERE session_code = ? AND provider = 'tavily'
                        """,
                        (self.session.session_code,),
                    ).fetchone()[0]
                )
                global_tavily = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts WHERE provider = 'tavily'"
                    ).fetchone()[0]
                )
                tavily_session_max = (
                    self.policy.tavily_attempts_quality_session_max
                    if self.session.profile == "quality"
                    else self.policy.tavily_attempts_community_session_max
                )
                if session_tavily + tavily_batch > tavily_session_max:
                    raise BudgetExceededError("closed-alpha Tavily session budget exhausted")
                if global_tavily + tavily_batch > self.policy.tavily_attempts_total_max:
                    raise BudgetExceededError("closed-alpha global Tavily budget exhausted")

                recent_starts_or_slots = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM attempts
                        WHERE (outcome = 'reserved' AND reserved_at > ?)
                           OR (dispatched_at IS NOT NULL AND dispatched_at > ?)
                        """,
                        (now - 60.0, now - 60.0),
                    ).fetchone()[0]
                )
                if recent_starts_or_slots + batch_size > self.policy.request_starts_per_minute_max:
                    raise BudgetExceededError("closed-alpha rolling request-start budget exhausted")

                connection.executemany(
                    """
                    INSERT INTO attempts(
                        token, session_code, kind, provider, reserved_at,
                        control_epoch, admission_epoch, session_epoch, dispatched,
                        dispatched_at, consumed_at, outcome
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, 'reserved')
                    """,
                    (
                        (
                            token,
                            self.session.session_code,
                            intent.kind,
                            intent.provider,
                            now,
                            control_epoch,
                            admission_epoch,
                            session_epoch,
                        )
                        for intent, token in zip(intents, tokens, strict=True)
                    ),
                )
                connection.execute(
                    """
                    UPDATE sessions SET lease_expires_at = ?
                    WHERE session_code = ? AND owner_id = ? AND status = 'active'
                    """,
                    (
                        now + self._lease_seconds,
                        self.session.session_code,
                        self._owner_id,
                    ),
                )
                SQLiteAlphaControlPlane._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        return (control_epoch, admission_epoch, session_epoch)

    def _consume_sync(self, permit: DispatchPermit) -> None:
        if self._rc4:
            self._consume_rc4_sync(permit)
            return
        rate_denied = False
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = SQLiteAlphaControlPlane._read_clock(self._clock)
                last_clock_row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'last_clock'"
                ).fetchone()
                if last_clock_row is not None and now < float(last_clock_row["value"]):
                    raise BudgetConfigurationError("closed-alpha governor clock moved backwards")

                attempt = connection.execute(
                    """
                    SELECT id FROM attempts
                    WHERE token = ? AND session_code = ? AND kind = ?
                      AND provider IS ? AND dispatched = 0
                    """,
                    (
                        permit.token,
                        permit.session_code,
                        permit.kind,
                        permit.provider,
                    ),
                ).fetchone()
                if attempt is None:
                    raise BudgetExceededError("closed-alpha dispatch permit is invalid or consumed")

                recent_starts = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts WHERE dispatched_at > ?",
                        (now - 60.0,),
                    ).fetchone()[0]
                )
                rate_denied = recent_starts >= self.policy.request_starts_per_minute_max
                connection.execute(
                    """
                    UPDATE attempts
                    SET dispatched = 1, dispatched_at = ?
                    WHERE id = ? AND dispatched = 0
                    """,
                    (None if rate_denied else now, int(attempt["id"])),
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('last_clock', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (repr(now),),
                )
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        if rate_denied:
            raise BudgetExceededError(
                "closed-alpha rolling request-start budget exhausted; permit consumed"
            )

    def _consume_rc4_sync(self, permit: DispatchPermit) -> None:
        self._validate_rc4_permit(permit)
        denial: str | None = None
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = SQLiteAlphaControlPlane._read_clock(self._clock)
                SQLiteAlphaControlPlane._check_clock(connection, now)
                expired = SQLiteAlphaControlPlane._reconcile_expired_sessions_locked(
                    connection, now
                )
                if expired:
                    SQLiteAlphaControlPlane._write_clock(connection, now)
                    connection.commit()
                    raise BudgetExceededError(
                        "closed-alpha session recovery is required; control plane paused"
                    )
                attempt = connection.execute(
                    """
                    SELECT * FROM attempts
                    WHERE token = ? AND session_code = ? AND kind = ?
                      AND provider IS ? AND dispatched = 0 AND outcome = 'reserved'
                    """,
                    (
                        permit.token,
                        permit.session_code,
                        permit.kind,
                        permit.provider,
                    ),
                ).fetchone()
                if attempt is None:
                    raise BudgetExceededError("closed-alpha dispatch permit is invalid or consumed")
                session = connection.execute(
                    "SELECT * FROM sessions WHERE session_code = ?",
                    (self.session.session_code,),
                ).fetchone()
                if session is None:
                    raise BudgetConfigurationError("closed-alpha session is missing")
                control = SQLiteAlphaControlPlane._control_row(connection)
                admission = connection.execute(
                    "SELECT * FROM participants WHERE participant_code = ?",
                    (self.session.participant_code,),
                ).fetchone()

                if int(control["privacy_fault"]) != 0:
                    denial = "closed-alpha privacy fault blocks dispatch; permit consumed"
                elif control["state"] != AlphaControlState.PREPARED:
                    denial = "closed-alpha control state blocks dispatch; permit consumed"
                elif (
                    admission is None
                    or admission["status"] != "admitted"
                    or admission["profile"] != self.session.profile
                    or admission["consent_version"] != _CONSENT_VERSION
                    or int(admission["input_authority_attested"]) != 1
                    or int(admission["non_sensitive_use_attested"]) != 1
                ):
                    denial = "closed-alpha admission blocks dispatch; permit consumed"
                elif (
                    session["status"] != "active"
                    or session["owner_id"] != self._owner_id
                    or int(session["session_epoch"]) != permit.session_epoch
                ):
                    denial = "closed-alpha session epoch blocks dispatch; permit consumed"
                elif (
                    int(control["control_epoch"]) != permit.control_epoch
                    or int(admission["admission_epoch"]) != permit.admission_epoch
                    or int(attempt["control_epoch"]) != permit.control_epoch
                    or int(attempt["admission_epoch"]) != permit.admission_epoch
                    or int(attempt["session_epoch"]) != permit.session_epoch
                ):
                    denial = "closed-alpha stale permit epoch; permit consumed"
                else:
                    recent_starts = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM attempts WHERE dispatched_at > ?",
                            (now - 60.0,),
                        ).fetchone()[0]
                    )
                    if recent_starts >= self.policy.request_starts_per_minute_max:
                        denial = (
                            "closed-alpha rolling request-start budget exhausted; permit consumed"
                        )

                if denial is not None:
                    if str(attempt["outcome"]) == "reserved":
                        if "recovery" in denial:
                            outcome = "denied_recovery"
                        elif "state" in denial:
                            outcome = "denied_state"
                        elif "rolling" in denial:
                            outcome = "denied_rate"
                        else:
                            outcome = "denied_epoch"
                        connection.execute(
                            """
                            UPDATE attempts SET dispatched = 1, consumed_at = ?, outcome = ?
                            WHERE id = ? AND outcome = 'reserved'
                            """,
                            (now, outcome, int(attempt["id"])),
                        )
                else:
                    cursor = connection.execute(
                        """
                        UPDATE attempts SET dispatched = 1, dispatched_at = ?,
                            consumed_at = ?, outcome = 'started'
                        WHERE id = ? AND dispatched = 0 AND outcome = 'reserved'
                        """,
                        (now, now, int(attempt["id"])),
                    )
                    if cursor.rowcount != 1:
                        raise BudgetExceededError(
                            "closed-alpha dispatch permit is invalid or consumed"
                        )
                    connection.execute(
                        """
                        UPDATE sessions SET lease_expires_at = ?
                        WHERE session_code = ? AND owner_id = ? AND status = 'active'
                        """,
                        (
                            now + self._lease_seconds,
                            self.session.session_code,
                            self._owner_id,
                        ),
                    )
                SQLiteAlphaControlPlane._write_clock(connection, now)
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        if denial is not None:
            raise BudgetExceededError(denial)

    def _snapshot_sync(self) -> dict[str, int | str | bool]:
        with contextlib.closing(self._connect()) as connection:
            session_attempts = int(
                connection.execute(
                    "SELECT COUNT(*) FROM attempts WHERE session_code = ?",
                    (self.session.session_code,),
                ).fetchone()[0]
            )
            global_attempts = int(connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])
            session_tavily = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM attempts
                    WHERE session_code = ? AND provider = 'tavily'
                    """,
                    (self.session.session_code,),
                ).fetchone()[0]
            )
            global_tavily = int(
                connection.execute(
                    "SELECT COUNT(*) FROM attempts WHERE provider = 'tavily'"
                ).fetchone()[0]
            )
            dispatched = int(
                connection.execute(
                    "SELECT COUNT(*) FROM attempts WHERE dispatched_at IS NOT NULL"
                ).fetchone()[0]
            )
            active_sessions = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
                ).fetchone()[0]
            )
        return {
            "scope": self.scope,
            "distributed_global_guarantee": False,
            "session_attempts": session_attempts,
            "global_attempts": global_attempts,
            "session_tavily_attempts": session_tavily,
            "global_tavily_attempts": global_tavily,
            "dispatched_attempts": dispatched,
            "active_sessions": active_sessions,
        }

    def _close_session_sync(self) -> None:
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = SQLiteAlphaControlPlane._read_clock(self._clock)
                last_clock_row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'last_clock'"
                ).fetchone()
                if last_clock_row is not None and now < float(last_clock_row["value"]):
                    raise BudgetConfigurationError("closed-alpha governor clock moved backwards")
                cursor = connection.execute(
                    """
                    UPDATE sessions SET status = 'closed', closed_at = ?
                    WHERE session_code = ? AND owner_id = ? AND status = 'active'
                    """,
                    (now, self.session.session_code, self._owner_id),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("closed-alpha session cannot be closed safely")
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('last_clock', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (repr(now),),
                )
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
