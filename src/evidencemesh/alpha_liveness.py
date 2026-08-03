"""Offline, single-host A2 fail-closed liveness control plane.

This module is deliberately additive.  It neither opens nor migrates an RC4
v2 ledger.  Every authority is bound to a fresh v3 ledger, Linux boottime, a
hashed boot identity, and independently fenced supervisor and session owners.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import os
import secrets
import sqlite3
import stat
import threading
import time
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Final, NoReturn, TypeVar, cast
from uuid import UUID

import httpx

import evidencemesh.governor as _governor
from evidencemesh.closed_alpha_feedback import (
    ClosedAlphaFeedbackStore,
    FeedbackContext,
    FeedbackStoreBinding,
    PurgeResult,
)
from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError
from evidencemesh.governor import (
    AlphaControlState,
    ClosedAlphaAdmission,
    ClosedAlphaPolicy,
    ClosedAlphaSession,
    DispatchIntent,
    DispatchPermit,
)

_SCHEMA_VERSION: Final = "evidencemesh.closed-alpha-control-plane.v3"
_SESSION_LEASE_SECONDS: Final = 300.0
_SUPERVISOR_LEASE_SECONDS: Final = 30.0
_MINIMUM_FRESHNESS_SECONDS: Final = 5.0
_SUPERVISOR_HEARTBEAT_SECONDS: Final = 10.0
_SESSION_HEARTBEAT_SECONDS: Final = 100.0
_OWNER_SECRET_BYTES: Final = 32
_DIGEST_LENGTH: Final = 64
_FAULT_MARKER_SUFFIX: Final = ".retention-supervisor-fault-v1"
_FAULT_MARKER_SCHEMA: Final = "evidencemesh.retention-supervisor-fault.v1"
_SUPERVISOR_STATES: Final = frozenset({"unclaimed", "active", "expired", "revoked"})
_FAULT_CODES: Final = frozenset(
    {
        "boottime_regression",
        "boottime_invalid",
        "boot_identity_invalid",
        "ledger_identity_drift",
        "lease_state_invalid",
        "lease_timestamp_future",
        "metadata_drift",
        "supervisor_marker_invalid",
        "supervisor_owner_mismatch",
        "feedback_clock_regression",
    }
)
_A2_CONTROL_STATES: Final = frozenset(state.value for state in AlphaControlState)
_T = TypeVar("_T")
_LedgerIdentity = tuple[int, int, int, int]
_TRANSPORT_FACTORY_TOKEN: Final = object()


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _owner_digest(secret: bytes) -> str:
    if type(secret) is not bytes or len(secret) != _OWNER_SECRET_BYTES:
        raise BudgetConfigurationError("A2 owner secret must contain exactly 32 bytes")
    return hashlib.sha256(secret).hexdigest()


def _read_boottime_default() -> float:
    if not hasattr(time, "CLOCK_BOOTTIME"):
        raise BudgetConfigurationError("A2 requires Linux CLOCK_BOOTTIME")
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def _read_boot_identity_default() -> bytes:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_bytes()
    except OSError as exc:
        raise BudgetConfigurationError("A2 cannot read the Linux boot identity") from exc


def _boot_digest(reader: Callable[[], bytes]) -> str:
    try:
        raw = reader()
    except BaseException as exc:
        raise BudgetConfigurationError("A2 boot identity is unavailable") from exc
    if type(raw) is not bytes or not 1 <= len(raw) <= 64 or b"\x00" in raw:
        raise BudgetConfigurationError("A2 boot identity is invalid")
    normalized = raw.strip()
    try:
        text = normalized.decode("ascii")
        parsed = UUID(text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise BudgetConfigurationError("A2 boot identity is invalid") from exc
    if text != str(parsed):
        raise BudgetConfigurationError("A2 boot identity is invalid")
    return hashlib.sha256(normalized).hexdigest()


def _read_finite_clock(clock: Callable[[], float]) -> float:
    try:
        observed = clock()
    except BaseException as exc:
        raise BudgetConfigurationError("A2 boottime clock is unavailable") from exc
    if (
        not isinstance(observed, (int, float))
        or isinstance(observed, bool)
        or not math.isfinite(observed)
        or float(observed) < 0.0
    ):
        raise BudgetConfigurationError("A2 boottime clock is invalid")
    return float(observed)


def _fault_marker_path(ledger_path: Path) -> Path:
    return ledger_path.with_name(f"{ledger_path.name}{_FAULT_MARKER_SUFFIX}")


def _fault_marker_payload(identity: _LedgerIdentity, code: str) -> bytes:
    return _canonical_json(
        {
            "fault_code": code,
            "ledger_device": identity[2],
            "ledger_inode": identity[3],
            "schema_version": _FAULT_MARKER_SCHEMA,
        }
    )


def _read_fault_marker(ledger_path: Path, identity: _LedgerIdentity) -> str | None:
    marker = _fault_marker_path(ledger_path)
    try:
        metadata = marker.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BudgetConfigurationError("A2 supervisor fault marker cannot be inspected") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or marker.is_symlink()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
    ):
        raise BudgetConfigurationError("A2 supervisor fault marker is unsafe")
    try:
        payload = marker.read_bytes()
        decoded = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BudgetConfigurationError("A2 supervisor fault marker is invalid") from exc
    if not isinstance(decoded, dict):
        raise BudgetConfigurationError("A2 supervisor fault marker is invalid")
    code = decoded.get("fault_code")
    if (
        decoded.get("schema_version") != _FAULT_MARKER_SCHEMA
        or type(code) is not str
        or code not in _FAULT_CODES
        or decoded.get("ledger_device") != identity[2]
        or decoded.get("ledger_inode") != identity[3]
        or payload != _fault_marker_payload(identity, code)
    ):
        raise BudgetConfigurationError("A2 supervisor fault marker is invalid")
    return code


def _persist_fault_marker(ledger_path: Path, identity: _LedgerIdentity, code: str) -> None:
    if code not in _FAULT_CODES:
        raise BudgetConfigurationError("A2 supervisor fault code is invalid")
    existing = _read_fault_marker(ledger_path, identity)
    if existing is not None:
        return
    parent_fd = -1
    marker_fd = -1
    marker = _fault_marker_path(ledger_path)
    payload = _fault_marker_payload(identity, code)
    try:
        parent_fd = os.open(
            marker.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        parent_metadata = os.fstat(parent_fd)
        if (int(parent_metadata.st_dev), int(parent_metadata.st_ino)) != identity[:2]:
            raise BudgetConfigurationError("A2 supervisor marker directory identity changed")
        marker_fd = os.open(
            marker.name,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        os.fchmod(marker_fd, 0o600)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(marker_fd, remaining)
            if written <= 0:
                raise OSError("short A2 marker write")
            remaining = remaining[written:]
        os.fsync(marker_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        pass
    except BudgetConfigurationError:
        raise
    except OSError as exc:
        raise BudgetConfigurationError("A2 supervisor fault marker cannot be persisted") from exc
    finally:
        if marker_fd >= 0:
            os.close(marker_fd)
        if parent_fd >= 0:
            os.close(parent_fd)
    if _read_fault_marker(ledger_path, identity) is None:
        raise BudgetConfigurationError("A2 supervisor fault marker was not persisted")


@dataclass(frozen=True, slots=True)
class SupervisorLease:
    """Public, secret-free CAS view of the singleton supervisor lease."""

    state: str
    owner_digest: str | None
    supervisor_epoch: int
    heartbeat_sequence: int
    control_state: str
    control_epoch: int
    boot_identity_digest: str | None
    issued_at_boottime: float | None
    last_heartbeat_at_boottime: float | None
    last_successful_retention_high_water_utc: float | None
    lease_expires_at_boottime: float | None


@dataclass(frozen=True, slots=True)
class FeedbackPublicationAuthority:
    """Process-local capability minted by an exact successful session close."""

    token: str = field(repr=False)
    participant_code: str
    session_code: str
    owner_digest: str = field(repr=False)
    control_epoch: int
    admission_epoch: int
    session_epoch: int
    closed_at_boottime: float
    supervisor: SupervisorLease


@dataclass(frozen=True, slots=True)
class _PreparedFeedbackPublication:
    """Single-use process-local token joining the two publication phases."""

    token: str = field(repr=False)
    authority_token: str = field(repr=False)
    participant_code: str
    session_code: str
    checked_at_utc: float
    supervisor: SupervisorLease


@dataclass(frozen=True, slots=True)
class _FeedbackClockAnchor:
    """Single-use boottime captured before the store's UTC retention check."""

    token: str = field(repr=False)
    checked_at_boottime: float
    store_binding: FeedbackStoreBinding


class A2SQLiteAlphaControlPlane:
    """Fresh-schema, local-only A2 control plane; v2 is never migrated."""

    def __init__(
        self,
        ledger_path: Path,
        policy: ClosedAlphaPolicy | None = None,
        *,
        boottime: Callable[[], float] = _read_boottime_default,
        boot_identity: Callable[[], bytes] = _read_boot_identity_default,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self._policy = _governor._resolve_closed_alpha_policy(
            policy,
            exact_type_required=True,
        )
        self._boottime = boottime
        self._boot_identity_reader = boot_identity
        _boot_digest(boot_identity)
        self._ledger_identity = _governor._private_ledger_identity(self.ledger_path)
        self._validate_database()

    @classmethod
    def bootstrap(
        cls,
        ledger_path: Path,
        policy: ClosedAlphaPolicy | None = None,
        *,
        boottime: Callable[[], float] = _read_boottime_default,
        boot_identity: Callable[[], bytes] = _read_boot_identity_default,
    ) -> A2SQLiteAlphaControlPlane:
        """Create one new v3 ledger; any existing ledger is refused unchanged."""

        path = Path(ledger_path)
        resolved = _governor._resolve_closed_alpha_policy(
            policy,
            exact_type_required=True,
        )
        boot_digest = _boot_digest(boot_identity)
        now = _read_finite_clock(boottime)
        if _fault_marker_path(path).exists() or _fault_marker_path(path).is_symlink():
            raise BudgetConfigurationError("A2 supervisor fault marker blocks bootstrap")
        _governor.SQLiteAlphaControlPlane._prepare_new_ledger(path)
        identity = _governor._private_ledger_identity(path)
        try:
            with contextlib.closing(_governor.SQLiteAlphaControlPlane._connect_path(path)) as db:
                if _governor._private_ledger_identity(path) != identity:
                    raise BudgetConfigurationError("A2 ledger identity changed during bootstrap")
                db.executescript(
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
                        supervisor_fault INTEGER NOT NULL CHECK (supervisor_fault IN (0, 1)),
                        bound_supervisor_epoch INTEGER,
                        updated_at_boottime REAL NOT NULL
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
                        consent_accepted_at_boottime REAL NOT NULL,
                        input_authority_attested INTEGER NOT NULL CHECK (
                            input_authority_attested = 1
                        ),
                        non_sensitive_use_attested INTEGER NOT NULL CHECK (
                            non_sensitive_use_attested = 1
                        ),
                        admission_epoch INTEGER NOT NULL CHECK (admission_epoch >= 1),
                        withdrawn_at_boottime REAL,
                        FOREIGN KEY(slot_id, profile) REFERENCES cohort_slots(slot_id, profile)
                    );
                    CREATE TABLE supervisor_lease (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        state TEXT NOT NULL CHECK (
                            state IN ('unclaimed', 'active', 'expired', 'revoked')
                        ),
                        owner_digest TEXT,
                        supervisor_epoch INTEGER NOT NULL CHECK (supervisor_epoch >= 0),
                        heartbeat_sequence INTEGER NOT NULL CHECK (heartbeat_sequence >= 0),
                        boot_identity_digest TEXT,
                        issued_at_boottime REAL,
                        last_heartbeat_at_boottime REAL,
                        last_successful_retention_high_water_utc REAL,
                        lease_expires_at_boottime REAL
                    );
                    CREATE TABLE feedback_store_binding (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        state TEXT NOT NULL CHECK (state IN ('unbound', 'bound')),
                        root_device INTEGER,
                        root_inode INTEGER,
                        candidate_sha TEXT,
                        candidate_tree TEXT
                    );
                    CREATE TABLE sessions (
                        session_code TEXT PRIMARY KEY,
                        participant_code TEXT NOT NULL REFERENCES participants(participant_code),
                        profile TEXT NOT NULL CHECK (profile IN ('community', 'quality')),
                        owner_digest TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (
                            status IN ('active', 'closed', 'recovery_required')
                        ),
                        control_epoch INTEGER NOT NULL CHECK (control_epoch >= 1),
                        admission_epoch INTEGER NOT NULL CHECK (admission_epoch >= 1),
                        session_epoch INTEGER NOT NULL CHECK (session_epoch >= 1),
                        boot_identity_digest TEXT NOT NULL,
                        heartbeat_sequence INTEGER NOT NULL CHECK (heartbeat_sequence >= 1),
                        last_heartbeat_at_boottime REAL NOT NULL,
                        lease_expires_at_boottime REAL NOT NULL,
                        opened_at_boottime REAL NOT NULL,
                        closed_at_boottime REAL
                    );
                    CREATE TABLE attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token_digest TEXT NOT NULL UNIQUE,
                        session_code TEXT NOT NULL REFERENCES sessions(session_code),
                        kind TEXT NOT NULL,
                        provider TEXT,
                        reserved_at_boottime REAL NOT NULL,
                        supervisor_epoch INTEGER NOT NULL CHECK (supervisor_epoch >= 1),
                        control_epoch INTEGER NOT NULL CHECK (control_epoch >= 1),
                        admission_epoch INTEGER NOT NULL CHECK (admission_epoch >= 1),
                        session_epoch INTEGER NOT NULL CHECK (session_epoch >= 1),
                        dispatched INTEGER NOT NULL DEFAULT 0 CHECK (dispatched IN (0, 1)),
                        dispatched_at_boottime REAL,
                        consumed_at_boottime REAL,
                        outcome TEXT NOT NULL CHECK (
                            outcome IN (
                                'reserved', 'started', 'denied_state', 'denied_epoch',
                                'denied_rate', 'denied_recovery'
                            )
                        )
                    );
                    CREATE INDEX sessions_lease_idx
                        ON sessions(status, lease_expires_at_boottime);
                    CREATE INDEX attempts_session_idx ON attempts(session_code);
                    CREATE INDEX attempts_rate_idx ON attempts(dispatched_at_boottime);
                    COMMIT;
                    """
                )
                metadata = {
                    "schema_version": _SCHEMA_VERSION,
                    "policy_fingerprint": resolved.fingerprint,
                    "policy": resolved.canonical_json,
                    "consent_version": _governor._CONSENT_VERSION,
                    "session_lease_seconds": repr(_SESSION_LEASE_SECONDS),
                    "supervisor_lease_seconds": repr(_SUPERVISOR_LEASE_SECONDS),
                    "minimum_freshness_seconds": repr(_MINIMUM_FRESHNESS_SECONDS),
                    "last_boottime": repr(now),
                    "last_boottime_boot_identity_digest": boot_digest,
                    "ledger_parent_device": str(identity[0]),
                    "ledger_parent_inode": str(identity[1]),
                    "ledger_device": str(identity[2]),
                    "ledger_inode": str(identity[3]),
                }
                db.execute("BEGIN IMMEDIATE")
                db.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    tuple(metadata.items()),
                )
                db.execute(
                    """
                    INSERT INTO control_state(
                        singleton, state, control_epoch, privacy_fault, supervisor_fault,
                        bound_supervisor_epoch, updated_at_boottime
                    ) VALUES (1, 'paused', 1, 0, 0, NULL, ?)
                    """,
                    (now,),
                )
                db.execute(
                    """
                    INSERT INTO feedback_store_binding(
                        singleton, state, root_device, root_inode,
                        candidate_sha, candidate_tree
                    ) VALUES (1, 'unbound', NULL, NULL, NULL, NULL)
                    """
                )
                db.execute(
                    """
                    INSERT INTO supervisor_lease(
                        singleton, state, owner_digest, supervisor_epoch,
                        heartbeat_sequence, boot_identity_digest, issued_at_boottime,
                        last_heartbeat_at_boottime,
                        last_successful_retention_high_water_utc,
                        lease_expires_at_boottime
                    ) VALUES (1, 'unclaimed', NULL, 0, 0, NULL, NULL, NULL, NULL, NULL)
                    """
                )
                db.executemany(
                    "INSERT INTO cohort_slots(slot_id, profile) VALUES (?, ?)",
                    _governor._COHORT_SLOTS,
                )
                db.commit()
        except BaseException:
            # A partially created file is never reused.  We deliberately do not
            # delete it here: the caller must inspect and remove it explicitly.
            raise
        return cls(path, resolved, boottime=boottime, boot_identity=boot_identity)

    @property
    def policy(self) -> ClosedAlphaPolicy:
        return self._policy

    def _verified_store_binding(
        self,
        store: ClosedAlphaFeedbackStore,
    ) -> FeedbackStoreBinding:
        if type(store) is not ClosedAlphaFeedbackStore:
            raise BudgetConfigurationError("A2 requires the exact feedback store")
        admission = store.retention_admission
        if type(admission) is not A2SQLiteBudgetGovernor:
            raise BudgetConfigurationError("A2 feedback store requires its exact ledger bridge")
        if admission._control._ledger_identity != self._ledger_identity:
            raise BudgetConfigurationError("A2 feedback store belongs to another ledger")
        binding = store.retention_binding()
        self._validate_store_binding(binding)
        return binding

    def bind_feedback_store(
        self,
        store: ClosedAlphaFeedbackStore,
        *,
        expected_control_epoch: int,
    ) -> int:
        """Durably bind the one authoritative store before lease acquisition."""

        if (
            type(expected_control_epoch) is not int
            or isinstance(expected_control_epoch, bool)
            or expected_control_epoch < 1
        ):
            raise BudgetConfigurationError("A2 control epoch is invalid")
        binding = self._verified_store_binding(store)
        with contextlib.closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db)
                self._require_no_lapse_locked(db, now, boot_digest)
                control = self._control_row(db)
                supervisor = self._supervisor_row(db)
                row = self._store_binding_row(db)
                if (
                    control["state"] != AlphaControlState.PAUSED
                    or int(control["control_epoch"]) != expected_control_epoch
                    or supervisor["state"] not in {"unclaimed", "revoked"}
                    or db.execute(
                        "SELECT 1 FROM sessions WHERE status != 'closed' LIMIT 1"
                    ).fetchone()
                    is not None
                ):
                    raise BudgetConfigurationError("A2 feedback-store binding CAS failed")
                if row["state"] == "bound":
                    self._require_bound_store_locked(db, binding)
                    self._write_boottime(db, now, boot_digest)
                    db.commit()
                    return expected_control_epoch
                cursor = db.execute(
                    """
                    UPDATE feedback_store_binding
                    SET state = 'bound', root_device = ?, root_inode = ?,
                        candidate_sha = ?, candidate_tree = ?
                    WHERE singleton = 1 AND state = 'unbound'
                    """,
                    (
                        binding.root_device,
                        binding.root_inode,
                        binding.candidate_sha,
                        binding.candidate_tree,
                    ),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 feedback-store binding CAS failed")
                next_epoch = expected_control_epoch + 1
                control_cursor = db.execute(
                    """
                    UPDATE control_state SET control_epoch = ?, updated_at_boottime = ?
                    WHERE singleton = 1 AND state = 'paused' AND control_epoch = ?
                    """,
                    (next_epoch, now, expected_control_epoch),
                )
                if control_cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 feedback-store control CAS failed")
                self._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return next_epoch

    def _assert_safe(self) -> None:
        current = _governor._private_ledger_identity(self.ledger_path)
        if current != self._ledger_identity:
            with contextlib.suppress(BudgetConfigurationError):
                _persist_fault_marker(
                    self.ledger_path,
                    self._ledger_identity,
                    "ledger_identity_drift",
                )
            raise BudgetConfigurationError("A2 ledger identity changed")
        if _governor._private_privacy_fault_marker_present(self.ledger_path):
            raise BudgetConfigurationError("A2 privacy fault permanently blocks authority")
        if _read_fault_marker(self.ledger_path, self._ledger_identity) is not None:
            raise BudgetConfigurationError("A2 supervisor fault permanently blocks authority")

    def _connect(self, *, allow_fault: bool = False) -> sqlite3.Connection:
        if allow_fault:
            current = _governor._private_ledger_identity(self.ledger_path)
            if current != self._ledger_identity:
                raise BudgetConfigurationError("A2 ledger identity changed")
        else:
            self._assert_safe()
        db = _governor.SQLiteAlphaControlPlane._connect_path(self.ledger_path)
        try:
            current = _governor._private_ledger_identity(self.ledger_path)
            if current != self._ledger_identity:
                raise BudgetConfigurationError("A2 ledger identity changed")
        except BaseException:
            db.close()
            raise
        return db

    def _validate_database(self) -> None:
        try:
            with contextlib.closing(self._connect(allow_fault=True)) as db:
                rows = {
                    str(row["key"]): str(row["value"])
                    for row in db.execute("SELECT key, value FROM metadata")
                }
                expected = {
                    "schema_version": _SCHEMA_VERSION,
                    "policy_fingerprint": self.policy.fingerprint,
                    "policy": self.policy.canonical_json,
                    "consent_version": _governor._CONSENT_VERSION,
                    "session_lease_seconds": repr(_SESSION_LEASE_SECONDS),
                    "supervisor_lease_seconds": repr(_SUPERVISOR_LEASE_SECONDS),
                    "minimum_freshness_seconds": repr(_MINIMUM_FRESHNESS_SECONDS),
                    "ledger_parent_device": str(self._ledger_identity[0]),
                    "ledger_parent_inode": str(self._ledger_identity[1]),
                    "ledger_device": str(self._ledger_identity[2]),
                    "ledger_inode": str(self._ledger_identity[3]),
                }
                if any(rows.get(key) != value for key, value in expected.items()):
                    raise BudgetConfigurationError(
                        "A2 refuses non-v3, migrated, or policy-drifted ledgers"
                    )
                self._control_row(db, allow_faulted_prepared=True)
                self._supervisor_row(db)
                self._store_binding_row(db)
        except BudgetConfigurationError:
            raise
        except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as exc:
            raise BudgetConfigurationError("A2 cannot validate the v3 ledger") from exc

    @staticmethod
    def _control_row(
        db: sqlite3.Connection,
        *,
        allow_faulted_prepared: bool = False,
    ) -> sqlite3.Row:
        row = db.execute("SELECT * FROM control_state WHERE singleton = 1").fetchone()
        if (
            row is None
            or str(row["state"]) not in _A2_CONTROL_STATES
            or type(row["control_epoch"]) is not int
            or int(row["control_epoch"]) < 1
            or type(row["privacy_fault"]) is not int
            or int(row["privacy_fault"]) not in {0, 1}
            or type(row["supervisor_fault"]) is not int
            or int(row["supervisor_fault"]) not in {0, 1}
            or (
                not allow_faulted_prepared
                and row["state"] == AlphaControlState.PREPARED
                and (int(row["privacy_fault"]) != 0 or int(row["supervisor_fault"]) != 0)
            )
            or (
                row["state"] == AlphaControlState.PREPARED
                and (
                    type(row["bound_supervisor_epoch"]) is not int
                    or int(row["bound_supervisor_epoch"]) < 1
                )
            )
            or (
                row["state"] != AlphaControlState.PREPARED
                and row["bound_supervisor_epoch"] is not None
            )
        ):
            raise BudgetConfigurationError("A2 control state is invalid")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _supervisor_row(db: sqlite3.Connection) -> sqlite3.Row:
        row = db.execute("SELECT * FROM supervisor_lease WHERE singleton = 1").fetchone()
        basic_invalid = (
            row is None
            or str(row["state"]) not in _SUPERVISOR_STATES
            or type(row["supervisor_epoch"]) is not int
            or int(row["supervisor_epoch"]) < 0
            or type(row["heartbeat_sequence"]) is not int
            or int(row["heartbeat_sequence"]) < 0
        )
        if basic_invalid:
            raise BudgetConfigurationError("A2 supervisor state is invalid")
        checked = cast(sqlite3.Row, row)
        state = str(checked["state"])
        digest = checked["owner_digest"]
        boot_digest = checked["boot_identity_digest"]
        required_times = (
            checked["issued_at_boottime"],
            checked["last_heartbeat_at_boottime"],
            checked["last_successful_retention_high_water_utc"],
            checked["lease_expires_at_boottime"],
        )
        if state == "unclaimed":
            if (
                int(checked["supervisor_epoch"]) != 0
                or int(checked["heartbeat_sequence"]) != 0
                or digest is not None
                or boot_digest is not None
                or any(value is not None for value in required_times)
            ):
                raise BudgetConfigurationError("A2 unclaimed supervisor row is inconsistent")
        elif (
            type(digest) is not str
            or len(digest) != _DIGEST_LENGTH
            or any(character not in "0123456789abcdef" for character in digest)
            or type(boot_digest) is not str
            or len(boot_digest) != _DIGEST_LENGTH
            or any(character not in "0123456789abcdef" for character in boot_digest)
            or int(checked["supervisor_epoch"]) < 1
            or int(checked["heartbeat_sequence"]) < 1
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in required_times
            )
        ):
            raise BudgetConfigurationError("A2 claimed supervisor row is inconsistent")
        elif (
            float(checked["last_heartbeat_at_boottime"]) < float(checked["issued_at_boottime"])
            or float(checked["lease_expires_at_boottime"])
            <= float(checked["last_heartbeat_at_boottime"])
            or float(checked["lease_expires_at_boottime"])
            > float(checked["last_heartbeat_at_boottime"]) + _SUPERVISOR_LEASE_SECONDS
        ):
            raise BudgetConfigurationError("A2 supervisor lease bounds are inconsistent")
        return checked

    @staticmethod
    def _store_binding_row(db: sqlite3.Connection) -> sqlite3.Row:
        row = db.execute("SELECT * FROM feedback_store_binding WHERE singleton = 1").fetchone()
        if row is None or row["state"] not in {"unbound", "bound"}:
            raise BudgetConfigurationError("A2 feedback-store binding is invalid")
        checked = cast(sqlite3.Row, row)
        values = (
            checked["root_device"],
            checked["root_inode"],
            checked["candidate_sha"],
            checked["candidate_tree"],
        )
        if checked["state"] == "unbound":
            if any(value is not None for value in values):
                raise BudgetConfigurationError("A2 unbound feedback store is inconsistent")
            return checked
        root_device, root_inode, candidate_sha, candidate_tree = values
        if (
            type(root_device) is not int
            or root_device < 0
            or type(root_inode) is not int
            or root_inode < 1
            or type(candidate_sha) is not str
            or len(candidate_sha) != 40
            or any(character not in "0123456789abcdef" for character in candidate_sha)
            or type(candidate_tree) is not str
            or len(candidate_tree) != 40
            or any(character not in "0123456789abcdef" for character in candidate_tree)
        ):
            raise BudgetConfigurationError("A2 bound feedback store is inconsistent")
        return checked

    @staticmethod
    def _validate_store_binding(binding: FeedbackStoreBinding) -> None:
        if (
            type(binding) is not FeedbackStoreBinding
            or type(binding.root_device) is not int
            or binding.root_device < 0
            or type(binding.root_inode) is not int
            or binding.root_inode < 1
            or type(binding.candidate_sha) is not str
            or len(binding.candidate_sha) != 40
            or any(character not in "0123456789abcdef" for character in binding.candidate_sha)
            or type(binding.candidate_tree) is not str
            or len(binding.candidate_tree) != 40
            or any(character not in "0123456789abcdef" for character in binding.candidate_tree)
        ):
            raise BudgetConfigurationError("A2 feedback-store identity is invalid")

    def _require_bound_store_locked(
        self,
        db: sqlite3.Connection,
        binding: FeedbackStoreBinding,
    ) -> None:
        self._validate_store_binding(binding)
        row = self._store_binding_row(db)
        if (
            row["state"] != "bound"
            or int(row["root_device"]) != binding.root_device
            or int(row["root_inode"]) != binding.root_inode
            or row["candidate_sha"] != binding.candidate_sha
            or row["candidate_tree"] != binding.candidate_tree
        ):
            raise BudgetConfigurationError("A2 feedback store is unbound or foreign")

    @staticmethod
    def _metadata_value(db: sqlite3.Connection, key: str) -> str:
        row = db.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
        if row is None or type(row["value"]) is not str:
            raise BudgetConfigurationError("A2 clock metadata is invalid")
        return str(row["value"])

    def _require_authority_metadata_locked(
        self,
        db: sqlite3.Connection,
        now: float,
    ) -> None:
        expected = {
            "schema_version": _SCHEMA_VERSION,
            "policy_fingerprint": self.policy.fingerprint,
            "policy": self.policy.canonical_json,
            "consent_version": _governor._CONSENT_VERSION,
            "session_lease_seconds": repr(_SESSION_LEASE_SECONDS),
            "supervisor_lease_seconds": repr(_SUPERVISOR_LEASE_SECONDS),
            "minimum_freshness_seconds": repr(_MINIMUM_FRESHNESS_SECONDS),
            "ledger_parent_device": str(self._ledger_identity[0]),
            "ledger_parent_inode": str(self._ledger_identity[1]),
            "ledger_device": str(self._ledger_identity[2]),
            "ledger_inode": str(self._ledger_identity[3]),
        }
        rows = {
            str(row["key"]): str(row["value"])
            for row in db.execute("SELECT key, value FROM metadata")
        }
        if any(rows.get(key) != value for key, value in expected.items()):
            self._commit_fault_locked(
                db,
                now,
                "metadata_drift",
                "A2 immutable authority metadata drifted",
            )

    def _now_locked(
        self,
        db: sqlite3.Connection,
        *,
        allow_boot_rebase: bool = False,
    ) -> tuple[float, str]:
        """Read boot before boottime; a reboot is recoverable, not regression."""

        try:
            boot_digest = _boot_digest(self._boot_identity_reader)
        except BudgetConfigurationError as exc:
            fallback = self._safe_previous_boottime(db)
            self._commit_fault_locked(
                db,
                fallback,
                "boot_identity_invalid",
                "A2 boot identity is invalid",
                cause=exc,
            )
        try:
            now = _read_finite_clock(self._boottime)
        except BudgetConfigurationError as exc:
            fallback = self._safe_previous_boottime(db)
            self._commit_fault_locked(
                db,
                fallback,
                "boottime_invalid",
                "A2 boottime clock is invalid",
                cause=exc,
            )
        try:
            previous = float(self._metadata_value(db, "last_boottime"))
            previous_boot = self._metadata_value(
                db,
                "last_boottime_boot_identity_digest",
            )
        except (BudgetConfigurationError, ValueError) as exc:
            self._commit_fault_locked(
                db,
                now,
                "boottime_regression",
                "A2 boottime high-water is invalid",
                cause=exc,
            )
        if boot_digest != previous_boot:
            self._contain_all_locked(db, now, expire_supervisor=True)
            self._write_boottime(db, now, boot_digest)
            db.commit()
            if not allow_boot_rebase:
                raise BudgetExceededError("A2 host reboot requires explicit recovery")
            # Every caller entered with BEGIN IMMEDIATE.  Re-open the write
            # transaction after the durable containment commit so its later
            # reads and CAS remain atomic.
            db.execute("BEGIN IMMEDIATE")
            return now, boot_digest
        if now < previous:
            self._commit_fault_locked(
                db,
                now,
                "boottime_regression",
                "A2 boottime moved backwards",
            )
        return now, boot_digest

    @staticmethod
    def _safe_previous_boottime(db: sqlite3.Connection) -> float:
        try:
            value = float(A2SQLiteAlphaControlPlane._metadata_value(db, "last_boottime"))
        except (BudgetConfigurationError, ValueError):
            return 0.0
        return value if math.isfinite(value) and value >= 0.0 else 0.0

    @staticmethod
    def _write_boottime(db: sqlite3.Connection, now: float, boot_digest: str) -> None:
        db.execute(
            "UPDATE metadata SET value = ? WHERE key = 'last_boottime'",
            (repr(now),),
        )
        db.execute(
            """
            UPDATE metadata SET value = ?
            WHERE key = 'last_boottime_boot_identity_digest'
            """,
            (boot_digest,),
        )

    def _trip_fault_locked(self, db: sqlite3.Connection, now: float, code: str) -> None:
        _persist_fault_marker(self.ledger_path, self._ledger_identity, code)
        self._contain_all_locked(db, now, expire_supervisor=True)
        db.execute(
            """
            UPDATE control_state
            SET supervisor_fault = 1, updated_at_boottime = ?
            WHERE singleton = 1
            """,
            (now,),
        )

    def _commit_fault_locked(
        self,
        db: sqlite3.Connection,
        now: float,
        code: str,
        message: str,
        *,
        cause: BaseException | None = None,
    ) -> NoReturn:
        self._trip_fault_locked(db, now, code)
        db.commit()
        if cause is None:
            raise BudgetConfigurationError(message)
        raise BudgetConfigurationError(message) from cause

    @staticmethod
    def _invalidate_reserved_locked(
        db: sqlite3.Connection,
        now: float,
        outcome: str,
    ) -> None:
        db.execute(
            """
            UPDATE attempts
            SET dispatched = 1, consumed_at_boottime = ?, outcome = ?
            WHERE outcome = 'reserved'
            """,
            (now, outcome),
        )

    def _contain_all_locked(
        self,
        db: sqlite3.Connection,
        now: float,
        *,
        expire_supervisor: bool,
        advance_control_epoch: bool = True,
    ) -> None:
        if expire_supervisor:
            db.execute(
                """
                UPDATE supervisor_lease SET state = 'expired'
                WHERE singleton = 1 AND state = 'active'
                """
            )
        control = self._control_row(db, allow_faulted_prepared=True)
        next_epoch = int(control["control_epoch"]) + int(advance_control_epoch)
        db.execute(
            """
            UPDATE control_state
            SET state = CASE WHEN state = 'stopped' THEN state ELSE 'paused' END,
                control_epoch = ?, bound_supervisor_epoch = NULL,
                updated_at_boottime = ? WHERE singleton = 1
            """,
            (next_epoch, now),
        )
        db.execute("UPDATE sessions SET status = 'recovery_required' WHERE status = 'active'")
        self._invalidate_reserved_locked(db, now, "denied_state")

    def _reconcile_locked(
        self,
        db: sqlite3.Connection,
        now: float,
        boot_digest: str,
    ) -> tuple[int, int]:
        supervisor = self._supervisor_row(db)
        control = self._control_row(db, allow_faulted_prepared=True)
        faulted = bool(int(control["privacy_fault"]) or int(control["supervisor_fault"]))
        if faulted:
            active_sessions = int(
                db.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'").fetchone()[0]
            )
            reserved = int(
                db.execute("SELECT COUNT(*) FROM attempts WHERE outcome = 'reserved'").fetchone()[0]
            )
            if (
                control["state"] == AlphaControlState.PREPARED
                or supervisor["state"] == "active"
                or active_sessions
                or reserved
            ):
                self._contain_all_locked(db, now, expire_supervisor=True)
            return 1, active_sessions
        prepared_incoherent = bool(
            control["state"] == AlphaControlState.PREPARED
            and (
                supervisor["state"] != "active"
                or control["bound_supervisor_epoch"] is None
                or int(control["bound_supervisor_epoch"]) != int(supervisor["supervisor_epoch"])
            )
        )
        supervisor_lapsed = int(
            supervisor["state"] == "active"
            and (
                supervisor["lease_expires_at_boottime"] is None
                or float(supervisor["lease_expires_at_boottime"]) <= now
                or supervisor["boot_identity_digest"] != boot_digest
            )
        )
        if supervisor_lapsed:
            db.execute("UPDATE supervisor_lease SET state = 'expired' WHERE singleton = 1")
        expired_sessions = tuple(
            str(row["session_code"])
            for row in db.execute(
                """
                SELECT session_code FROM sessions
                WHERE status = 'active'
                  AND (lease_expires_at_boottime <= ? OR boot_identity_digest != ?)
                """,
                (now, boot_digest),
            )
        )
        if expired_sessions:
            db.execute(
                """
                UPDATE attempts
                SET dispatched = 1, consumed_at_boottime = ?, outcome = 'denied_recovery'
                WHERE outcome = 'reserved' AND session_code IN (
                    SELECT session_code FROM sessions
                    WHERE status = 'active'
                      AND (lease_expires_at_boottime <= ? OR boot_identity_digest != ?)
                )
                """,
                (now, now, boot_digest),
            )
            db.execute(
                """
                UPDATE sessions SET status = 'recovery_required'
                WHERE status = 'active'
                  AND (lease_expires_at_boottime <= ? OR boot_identity_digest != ?)
                """,
                (now, boot_digest),
            )
        if supervisor_lapsed:
            db.execute("UPDATE sessions SET status = 'recovery_required' WHERE status = 'active'")
        if supervisor_lapsed or expired_sessions or prepared_incoherent:
            self._contain_all_locked(db, now, expire_supervisor=True)
        return int(supervisor_lapsed or prepared_incoherent), len(expired_sessions)

    def _require_no_lapse_locked(
        self,
        db: sqlite3.Connection,
        now: float,
        boot_digest: str,
    ) -> None:
        """Commit containment before denying an authority operation."""

        self._require_authority_metadata_locked(db, now)
        self._require_authority_lease_integrity_locked(db, now, boot_digest)
        supervisor_lapsed, sessions_lapsed = self._reconcile_locked(db, now, boot_digest)
        if supervisor_lapsed or sessions_lapsed:
            control = self._control_row(db, allow_faulted_prepared=True)
            faulted = bool(int(control["privacy_fault"]) or int(control["supervisor_fault"]))
            self._write_boottime(db, now, boot_digest)
            db.commit()
            if faulted:
                raise BudgetConfigurationError("A2 fault bits permanently block authority")
            raise BudgetExceededError("A2 lease recovery is required; control plane paused")

    def _require_authority_lease_integrity_locked(
        self,
        db: sqlite3.Connection,
        now: float,
        boot_digest: str,
    ) -> None:
        """Durably fault malformed or future-issued authority lease state."""

        supervisor = self._supervisor_row(db)
        if (
            supervisor["state"] != "unclaimed"
            and supervisor["boot_identity_digest"] == boot_digest
            and (
                float(supervisor["issued_at_boottime"]) > now
                or float(supervisor["last_heartbeat_at_boottime"]) > now
            )
        ):
            self._commit_fault_locked(
                db,
                now,
                "lease_timestamp_future",
                "A2 supervisor lease timestamp is in the future",
            )
        for session in db.execute(
            """
            SELECT status, boot_identity_digest, opened_at_boottime,
                   last_heartbeat_at_boottime,
                   lease_expires_at_boottime, closed_at_boottime
            FROM sessions
            """
        ):
            opened = session["opened_at_boottime"]
            heartbeat = session["last_heartbeat_at_boottime"]
            expiry = session["lease_expires_at_boottime"]
            closed = session["closed_at_boottime"]
            times = (opened, heartbeat, expiry)
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in times
            ) or (
                closed is not None
                and (
                    not isinstance(closed, (int, float))
                    or isinstance(closed, bool)
                    or not math.isfinite(float(closed))
                )
            ):
                self._commit_fault_locked(
                    db,
                    now,
                    "lease_state_invalid",
                    "A2 session lease state is invalid",
                )
            if (
                float(heartbeat) < float(opened)
                or float(expiry) <= float(heartbeat)
                or float(expiry) > float(heartbeat) + _SESSION_LEASE_SECONDS
                or (session["status"] == "active" and closed is not None)
            ):
                self._commit_fault_locked(
                    db,
                    now,
                    "lease_state_invalid",
                    "A2 session lease state is invalid",
                )
            if session["boot_identity_digest"] == boot_digest and (
                float(opened) > now
                or float(heartbeat) > now
                or (closed is not None and float(closed) > now)
            ):
                self._commit_fault_locked(
                    db,
                    now,
                    "lease_timestamp_future",
                    "A2 session lease timestamp is in the future",
                )

    def _supervisor_snapshot_locked(self, db: sqlite3.Connection) -> SupervisorLease:
        row = self._supervisor_row(db)
        control = self._control_row(db)
        return SupervisorLease(
            state=str(row["state"]),
            owner_digest=(None if row["owner_digest"] is None else str(row["owner_digest"])),
            supervisor_epoch=int(row["supervisor_epoch"]),
            heartbeat_sequence=int(row["heartbeat_sequence"]),
            control_state=str(control["state"]),
            control_epoch=int(control["control_epoch"]),
            boot_identity_digest=(
                None if row["boot_identity_digest"] is None else str(row["boot_identity_digest"])
            ),
            issued_at_boottime=(
                None if row["issued_at_boottime"] is None else float(row["issued_at_boottime"])
            ),
            last_heartbeat_at_boottime=(
                None
                if row["last_heartbeat_at_boottime"] is None
                else float(row["last_heartbeat_at_boottime"])
            ),
            last_successful_retention_high_water_utc=(
                None
                if row["last_successful_retention_high_water_utc"] is None
                else float(row["last_successful_retention_high_water_utc"])
            ),
            lease_expires_at_boottime=(
                None
                if row["lease_expires_at_boottime"] is None
                else float(row["lease_expires_at_boottime"])
            ),
        )

    @staticmethod
    def _validate_retention_values(high_water_utc: float, next_purge: float) -> None:
        for value in (high_water_utc, next_purge):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise BudgetConfigurationError("A2 retention timestamp is invalid")

    def _fresh_supervisor_locked(
        self,
        db: sqlite3.Connection,
        now: float,
        boot_digest: str,
    ) -> sqlite3.Row:
        control = self._control_row(db)
        row = self._supervisor_row(db)
        if (
            row["state"] != "unclaimed"
            and row["boot_identity_digest"] == boot_digest
            and (
                float(row["issued_at_boottime"]) > now
                or float(row["last_heartbeat_at_boottime"]) > now
            )
        ):
            self._commit_fault_locked(
                db,
                now,
                "lease_timestamp_future",
                "A2 supervisor lease timestamp is in the future",
            )
        if (
            int(control["privacy_fault"]) != 0
            or int(control["supervisor_fault"]) != 0
            or row["state"] != "active"
            or row["boot_identity_digest"] != boot_digest
            or row["lease_expires_at_boottime"] is None
            or float(row["lease_expires_at_boottime"]) - now <= _MINIMUM_FRESHNESS_SECONDS
        ):
            raise BudgetExceededError("A2 supervisor lease is not freshly dispatchable")
        return row

    def admit(self, admission: ClosedAlphaAdmission) -> int:
        if type(admission) is not ClosedAlphaAdmission:
            raise BudgetConfigurationError("A2 requires the exact admission type")
        with contextlib.closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db)
                self._require_no_lapse_locked(db, now, boot_digest)
                control = self._control_row(db)
                if control["state"] != AlphaControlState.PAUSED:
                    raise BudgetConfigurationError("A2 admission requires paused state")
                db.execute(
                    """
                    INSERT INTO participants(
                        participant_code, slot_id, profile, status, consent_version,
                        consent_accepted_at_boottime, input_authority_attested,
                        non_sensitive_use_attested, admission_epoch, withdrawn_at_boottime
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
                self._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return 1

    def transition(
        self,
        target: AlphaControlState | str,
        *,
        expected_state: AlphaControlState | str,
        expected_epoch: int,
    ) -> int:
        try:
            target_state = AlphaControlState(target)
            source_state = AlphaControlState(expected_state)
        except ValueError as exc:
            raise BudgetConfigurationError("A2 control state is invalid") from exc
        if type(expected_epoch) is not int or expected_epoch < 1:
            raise BudgetConfigurationError("A2 control epoch is invalid")
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
            raise BudgetConfigurationError("A2 control transition is forbidden")
        with contextlib.closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db)
                self._require_no_lapse_locked(db, now, boot_digest)
                control = self._control_row(db)
                if (
                    control["state"] != source_state
                    or int(control["control_epoch"]) != expected_epoch
                ):
                    raise BudgetConfigurationError("A2 control CAS failed")
                bound_supervisor: int | None = None
                if target_state is AlphaControlState.PREPARED:
                    if self._store_binding_row(db)["state"] != "bound":
                        raise BudgetConfigurationError(
                            "A2 preparation requires the authoritative feedback store"
                        )
                    supervisor = self._fresh_supervisor_locked(db, now, boot_digest)
                    _governor.SQLiteAlphaControlPlane._assert_cohort_ready(db)
                    recovery = int(
                        db.execute(
                            "SELECT COUNT(*) FROM sessions WHERE status = 'recovery_required'"
                        ).fetchone()[0]
                    )
                    if recovery:
                        raise BudgetConfigurationError("A2 recovery must finish before prepare")
                    active = int(
                        db.execute(
                            "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
                        ).fetchone()[0]
                    )
                    if active:
                        raise BudgetConfigurationError(
                            "A2 active sessions must be zero before prepare"
                        )
                    bound_supervisor = int(supervisor["supervisor_epoch"])
                elif source_state is AlphaControlState.PREPARED:
                    db.execute(
                        """
                        UPDATE sessions SET status = 'recovery_required'
                        WHERE status = 'active'
                        """
                    )
                next_epoch = expected_epoch + 1
                db.execute(
                    """
                    UPDATE control_state
                    SET state = ?, control_epoch = ?, bound_supervisor_epoch = ?,
                        updated_at_boottime = ?
                    WHERE singleton = 1
                    """,
                    (target_state.value, next_epoch, bound_supervisor, now),
                )
                self._invalidate_reserved_locked(db, now, "denied_state")
                self._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return next_epoch

    def reconcile(self) -> dict[str, int | bool]:
        """Reconcile both independent lease domains in one write transaction."""

        with contextlib.closing(self._connect(allow_fault=True)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                try:
                    marker = _read_fault_marker(self.ledger_path, self._ledger_identity)
                except BudgetConfigurationError as exc:
                    now = self._safe_previous_boottime(db)
                    self._contain_all_locked(db, now, expire_supervisor=True)
                    db.execute(
                        """
                        UPDATE control_state SET supervisor_fault = 1
                        WHERE singleton = 1
                        """
                    )
                    db.commit()
                    raise BudgetConfigurationError(
                        "A2 invalid supervisor marker was durably contained"
                    ) from exc
                if marker is not None:
                    now = self._safe_previous_boottime(db)
                    self._trip_fault_locked(db, now, marker)
                    db.commit()
                    raise BudgetConfigurationError("A2 supervisor fault was durably contained")
                now, boot_digest = self._now_locked(db, allow_boot_rebase=True)
                supervisor_lapsed, sessions_lapsed = self._reconcile_locked(
                    db,
                    now,
                    boot_digest,
                )
                self._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return {
            "supervisor_lapsed": bool(supervisor_lapsed),
            "sessions_lapsed": sessions_lapsed,
        }

    def snapshot(self) -> dict[str, int | str | bool | float | None]:
        with contextlib.closing(self._connect(allow_fault=True)) as db:
            control = self._control_row(db)
            supervisor = self._supervisor_row(db)
            store_binding = self._store_binding_row(db)
            sessions = int(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
            recovery = int(
                db.execute(
                    "SELECT COUNT(*) FROM sessions WHERE status = 'recovery_required'"
                ).fetchone()[0]
            )
            attempts = int(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])
        try:
            marker = _read_fault_marker(self.ledger_path, self._ledger_identity)
        except BudgetConfigurationError:
            marker = "supervisor_marker_invalid"
        return {
            "schema_version": _SCHEMA_VERSION,
            "state": str(control["state"]),
            "control_epoch": int(control["control_epoch"]),
            "bound_supervisor_epoch": (
                None
                if control["bound_supervisor_epoch"] is None
                else int(control["bound_supervisor_epoch"])
            ),
            "privacy_fault": bool(control["privacy_fault"]),
            "supervisor_fault": bool(control["supervisor_fault"]) or marker is not None,
            "supervisor_state": str(supervisor["state"]),
            "feedback_store_bound": store_binding["state"] == "bound",
            "supervisor_epoch": int(supervisor["supervisor_epoch"]),
            "supervisor_heartbeat_sequence": int(supervisor["heartbeat_sequence"]),
            "supervisor_lease_expires_at_boottime": (
                None
                if supervisor["lease_expires_at_boottime"] is None
                else float(supervisor["lease_expires_at_boottime"])
            ),
            "sessions": sessions,
            "recovery_required_sessions": recovery,
            "global_attempts": attempts,
            "distributed_global_guarantee": False,
        }

    def supervisor_cas_snapshot(self) -> SupervisorLease:
        with contextlib.closing(self._connect(allow_fault=True)) as db:
            return self._supervisor_snapshot_locked(db)

    def _lease_expiry(self, now: float, next_purge_at: float) -> float:
        expiry = min(
            now + _SUPERVISOR_LEASE_SECONDS,
            next_purge_at - _MINIMUM_FRESHNESS_SECONDS,
        )
        if expiry - now <= _MINIMUM_FRESHNESS_SECONDS:
            raise BudgetConfigurationError("A2 retention deadline is too close for authority")
        return expiry

    def _acquire_supervisor(
        self,
        owner_secret: bytes,
        *,
        expected: SupervisorLease,
        store_binding: FeedbackStoreBinding,
        last_successful_retention_high_water_utc: float,
        next_purge_at_boottime: float,
    ) -> SupervisorLease:
        digest = _owner_digest(owner_secret)
        if type(expected) is not SupervisorLease:
            raise BudgetConfigurationError("A2 supervisor acquisition CAS is invalid")
        self._validate_retention_values(
            last_successful_retention_high_water_utc,
            next_purge_at_boottime,
        )
        with contextlib.closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db, allow_boot_rebase=True)
                self._require_no_lapse_locked(db, now, boot_digest)
                control = self._control_row(db)
                supervisor = self._supervisor_row(db)
                self._require_bound_store_locked(db, store_binding)
                if self._supervisor_snapshot_locked(db) != expected:
                    raise BudgetConfigurationError("A2 supervisor acquisition CAS failed")
                if control["state"] != AlphaControlState.PAUSED:
                    raise BudgetConfigurationError(
                        "A2 supervisor acquisition requires paused state"
                    )
                if supervisor["state"] not in {"unclaimed", "revoked"}:
                    raise BudgetConfigurationError(
                        "A2 supervisor acquisition requires explicit prior revocation"
                    )
                if int(
                    db.execute(
                        "SELECT COUNT(*) FROM sessions WHERE status = 'recovery_required'"
                    ).fetchone()[0]
                ):
                    raise BudgetConfigurationError("A2 session recovery blocks acquisition")
                previous_high_water = supervisor["last_successful_retention_high_water_utc"]
                if (
                    previous_high_water is not None
                    and last_successful_retention_high_water_utc < float(previous_high_water)
                ):
                    self._commit_fault_locked(
                        db,
                        now,
                        "feedback_clock_regression",
                        "A2 retention high-water moved backwards",
                    )
                expiry = self._lease_expiry(now, next_purge_at_boottime)
                epoch = int(supervisor["supervisor_epoch"]) + 1
                cursor = db.execute(
                    """
                    UPDATE supervisor_lease
                    SET state = 'active', owner_digest = ?, supervisor_epoch = ?,
                        heartbeat_sequence = 1, boot_identity_digest = ?,
                        issued_at_boottime = ?, last_heartbeat_at_boottime = ?,
                        last_successful_retention_high_water_utc = ?,
                        lease_expires_at_boottime = ?
                    WHERE singleton = 1 AND state = ? AND owner_digest IS ?
                      AND supervisor_epoch = ? AND heartbeat_sequence = ?
                      AND lease_expires_at_boottime IS ?
                    """,
                    (
                        digest,
                        epoch,
                        boot_digest,
                        now,
                        now,
                        float(last_successful_retention_high_water_utc),
                        expiry,
                        expected.state,
                        expected.owner_digest,
                        expected.supervisor_epoch,
                        expected.heartbeat_sequence,
                        expected.lease_expires_at_boottime,
                    ),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 supervisor acquisition CAS failed")
                self._write_boottime(db, now, boot_digest)
                lease = self._supervisor_snapshot_locked(db)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return lease

    def _renew_supervisor(
        self,
        owner_secret: bytes,
        *,
        expected: SupervisorLease,
        store_binding: FeedbackStoreBinding,
        last_successful_retention_high_water_utc: float,
        next_purge_at_boottime: float,
    ) -> SupervisorLease:
        digest = _owner_digest(owner_secret)
        if type(expected) is not SupervisorLease:
            raise BudgetConfigurationError("A2 supervisor renewal CAS is invalid")
        self._validate_retention_values(
            last_successful_retention_high_water_utc,
            next_purge_at_boottime,
        )
        with contextlib.closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db)
                self._require_no_lapse_locked(db, now, boot_digest)
                supervisor = self._supervisor_row(db)
                control = self._control_row(db)
                self._require_bound_store_locked(db, store_binding)
                if (
                    supervisor["state"] == "active"
                    and int(supervisor["supervisor_epoch"]) == expected.supervisor_epoch
                    and supervisor["owner_digest"] != digest
                ):
                    self._commit_fault_locked(
                        db,
                        now,
                        "supervisor_owner_mismatch",
                        "A2 same-epoch supervisor owner mismatch",
                    )
                if (
                    self._supervisor_snapshot_locked(db) != expected
                    or expected.lease_expires_at_boottime is None
                    or control["state"] == AlphaControlState.STOPPED
                    or supervisor["state"] != "active"
                    or supervisor["owner_digest"] != digest
                    or supervisor["boot_identity_digest"] != boot_digest
                ):
                    raise BudgetConfigurationError("A2 stale supervisor heartbeat is fenced")
                previous_high_water = float(supervisor["last_successful_retention_high_water_utc"])
                if last_successful_retention_high_water_utc < previous_high_water:
                    self._commit_fault_locked(
                        db,
                        now,
                        "feedback_clock_regression",
                        "A2 retention high-water moved backwards",
                    )
                expiry = self._lease_expiry(now, next_purge_at_boottime)
                cursor = db.execute(
                    """
                    UPDATE supervisor_lease
                    SET heartbeat_sequence = heartbeat_sequence + 1,
                        last_heartbeat_at_boottime = ?,
                        last_successful_retention_high_water_utc = ?,
                        lease_expires_at_boottime = ?
                    WHERE singleton = 1 AND state = 'active' AND owner_digest = ?
                      AND supervisor_epoch = ? AND heartbeat_sequence = ?
                      AND boot_identity_digest = ? AND lease_expires_at_boottime = ?
                    """,
                    (
                        now,
                        float(last_successful_retention_high_water_utc),
                        expiry,
                        digest,
                        expected.supervisor_epoch,
                        expected.heartbeat_sequence,
                        boot_digest,
                        expected.lease_expires_at_boottime,
                    ),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 supervisor heartbeat CAS failed")
                self._write_boottime(db, now, boot_digest)
                lease = self._supervisor_snapshot_locked(db)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return lease

    def _revoke_supervisor(
        self,
        owner_secret: bytes | None,
        *,
        expected: SupervisorLease,
    ) -> SupervisorLease:
        digest = None if owner_secret is None else _owner_digest(owner_secret)
        if type(expected) is not SupervisorLease:
            raise BudgetConfigurationError("A2 supervisor revoke CAS is invalid")
        with contextlib.closing(self._connect(allow_fault=True)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db, allow_boot_rebase=True)
                supervisor = self._supervisor_row(db)
                if self._supervisor_snapshot_locked(db) != expected:
                    raise BudgetConfigurationError("A2 supervisor revoke CAS failed")
                if supervisor["state"] == "active" and supervisor["owner_digest"] != digest:
                    raise BudgetConfigurationError("A2 supervisor revoke owner is fenced")
                if (
                    supervisor["state"] == "expired"
                    and owner_secret is not None
                    and supervisor["owner_digest"] != digest
                ):
                    raise BudgetConfigurationError("A2 expired supervisor owner is fenced")
                if supervisor["state"] not in {"active", "expired"}:
                    raise BudgetConfigurationError("A2 supervisor is not revocable")
                control = self._control_row(db, allow_faulted_prepared=True)
                unsafe = bool(
                    supervisor["state"] == "active"
                    or control["state"] == AlphaControlState.PREPARED
                    or db.execute(
                        "SELECT 1 FROM sessions WHERE status = 'active' LIMIT 1"
                    ).fetchone()
                    is not None
                    or db.execute(
                        "SELECT 1 FROM attempts WHERE outcome = 'reserved' LIMIT 1"
                    ).fetchone()
                    is not None
                )
                self._contain_all_locked(
                    db,
                    now,
                    expire_supervisor=False,
                    advance_control_epoch=unsafe,
                )
                cursor = db.execute(
                    """
                    UPDATE supervisor_lease SET state = 'revoked'
                    WHERE singleton = 1 AND state = ? AND owner_digest IS ?
                      AND supervisor_epoch = ? AND heartbeat_sequence = ?
                      AND lease_expires_at_boottime IS ?
                    """,
                    (
                        expected.state,
                        expected.owner_digest,
                        expected.supervisor_epoch,
                        expected.heartbeat_sequence,
                        expected.lease_expires_at_boottime,
                    ),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 supervisor revoke CAS failed")
                self._write_boottime(db, now, boot_digest)
                lease = self._supervisor_snapshot_locked(db)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return lease

    def _shutdown_supervisor(
        self,
        owner_secret: bytes,
        *,
        expected_supervisor_epoch: int,
        store_binding: FeedbackStoreBinding,
    ) -> SupervisorLease:
        """Pause and revoke the current owned epoch without a stale expiry CAS.

        This is the supervisor's orderly-shutdown primitive.  It deliberately
        accepts the current heartbeat sequence and expiry from inside the same
        transaction so a publication phase-A fence cannot strand authority.
        The owner secret and supervisor epoch remain exact, non-negotiable
        fences.
        """

        digest = _owner_digest(owner_secret)
        if (
            type(expected_supervisor_epoch) is not int
            or isinstance(expected_supervisor_epoch, bool)
            or expected_supervisor_epoch < 1
        ):
            raise BudgetConfigurationError("A2 supervisor shutdown epoch is invalid")
        with contextlib.closing(self._connect(allow_fault=True)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db, allow_boot_rebase=True)
                self._require_bound_store_locked(db, store_binding)
                supervisor = self._supervisor_row(db)
                if (
                    int(supervisor["supervisor_epoch"]) == expected_supervisor_epoch
                    and supervisor["owner_digest"] != digest
                ):
                    self._commit_fault_locked(
                        db,
                        now,
                        "supervisor_owner_mismatch",
                        "A2 same-epoch supervisor shutdown owner mismatch",
                    )
                if (
                    supervisor["state"] not in {"active", "expired"}
                    or supervisor["owner_digest"] != digest
                    or int(supervisor["supervisor_epoch"]) != expected_supervisor_epoch
                ):
                    raise BudgetConfigurationError("A2 supervisor shutdown is fenced")
                current_state = str(supervisor["state"])
                current_sequence = int(supervisor["heartbeat_sequence"])
                current_expiry = float(supervisor["lease_expires_at_boottime"])
                control = self._control_row(db, allow_faulted_prepared=True)
                unsafe = bool(
                    current_state == "active"
                    or control["state"] == AlphaControlState.PREPARED
                    or db.execute(
                        "SELECT 1 FROM sessions WHERE status = 'active' LIMIT 1"
                    ).fetchone()
                    is not None
                    or db.execute(
                        "SELECT 1 FROM attempts WHERE outcome = 'reserved' LIMIT 1"
                    ).fetchone()
                    is not None
                )
                self._contain_all_locked(
                    db,
                    now,
                    expire_supervisor=False,
                    advance_control_epoch=unsafe,
                )
                cursor = db.execute(
                    """
                    UPDATE supervisor_lease SET state = 'revoked'
                    WHERE singleton = 1 AND state = ? AND owner_digest = ?
                      AND supervisor_epoch = ? AND heartbeat_sequence = ?
                      AND lease_expires_at_boottime = ?
                    """,
                    (
                        current_state,
                        digest,
                        expected_supervisor_epoch,
                        current_sequence,
                        current_expiry,
                    ),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 supervisor shutdown CAS failed")
                self._write_boottime(db, now, boot_digest)
                lease = self._supervisor_snapshot_locked(db)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return lease

    def withdraw(self, participant_code: str, *, expected_admission_epoch: int) -> int:
        """Withdraw durably under paused, stopped, lapsed, or faulted authority."""

        if _governor._PARTICIPANT_PATTERN.fullmatch(participant_code) is None:
            raise BudgetConfigurationError("A2 participant code is invalid")
        if (
            type(expected_admission_epoch) is not int
            or isinstance(expected_admission_epoch, bool)
            or expected_admission_epoch < 1
        ):
            raise BudgetConfigurationError("A2 admission epoch is invalid")
        with contextlib.closing(self._connect(allow_fault=True)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db, allow_boot_rebase=True)
                participant = db.execute(
                    "SELECT * FROM participants WHERE participant_code = ?",
                    (participant_code,),
                ).fetchone()
                if (
                    participant is None
                    or participant["status"] != "admitted"
                    or int(participant["admission_epoch"]) != expected_admission_epoch
                ):
                    raise BudgetConfigurationError("A2 withdrawal CAS failed")
                next_admission_epoch = expected_admission_epoch + 1
                db.execute(
                    """
                    UPDATE participants
                    SET status = 'withdrawn', admission_epoch = ?,
                        withdrawn_at_boottime = ?
                    WHERE participant_code = ? AND status = 'admitted'
                      AND admission_epoch = ?
                    """,
                    (
                        next_admission_epoch,
                        now,
                        participant_code,
                        expected_admission_epoch,
                    ),
                )
                control = self._control_row(db, allow_faulted_prepared=True)
                supervisor = self._supervisor_row(db)
                active = int(
                    db.execute(
                        """
                        SELECT COUNT(*) FROM sessions
                        WHERE participant_code = ? AND status = 'active'
                        """,
                        (participant_code,),
                    ).fetchone()[0]
                )
                if control["state"] == AlphaControlState.PREPARED or active:
                    self._contain_all_locked(db, now, expire_supervisor=True)
                else:
                    db.execute(
                        """
                        UPDATE control_state SET control_epoch = control_epoch + 1,
                            updated_at_boottime = ? WHERE singleton = 1
                        """,
                        (now,),
                    )
                    if supervisor["state"] == "active":
                        db.execute(
                            """
                            UPDATE supervisor_lease SET state = 'expired'
                            WHERE singleton = 1 AND state = 'active'
                            """
                        )
                    db.execute(
                        """
                        UPDATE attempts SET dispatched = 1,
                            consumed_at_boottime = ?, outcome = 'denied_epoch'
                        WHERE outcome = 'reserved' AND session_code IN (
                            SELECT session_code FROM sessions WHERE participant_code = ?
                        )
                        """,
                        (now, participant_code),
                    )
                self._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return next_admission_epoch

    def resolve_recovery(self, session_code: str, *, expected_control_epoch: int) -> None:
        if _governor._SESSION_PATTERN.fullmatch(session_code) is None:
            raise BudgetConfigurationError("A2 session code is invalid")
        if (
            type(expected_control_epoch) is not int
            or isinstance(expected_control_epoch, bool)
            or expected_control_epoch < 1
        ):
            raise BudgetConfigurationError("A2 control epoch is invalid")
        with contextlib.closing(self._connect(allow_fault=True)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = self._now_locked(db, allow_boot_rebase=True)
                control = self._control_row(db, allow_faulted_prepared=True)
                if (
                    control["state"] not in {AlphaControlState.PAUSED, AlphaControlState.STOPPED}
                    or int(control["control_epoch"]) != expected_control_epoch
                ):
                    raise BudgetConfigurationError(
                        "A2 recovery requires the expected non-authoritative epoch"
                    )
                cursor = db.execute(
                    """
                    UPDATE sessions SET status = 'closed', closed_at_boottime = ?
                    WHERE session_code = ? AND status = 'recovery_required'
                    """,
                    (now, session_code),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 session is not recoverable")
                self._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise

    def _session_authority_locked(
        self,
        db: sqlite3.Connection,
        session: ClosedAlphaSession,
        owner_digest: str,
        now: float,
        boot_digest: str,
    ) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row, sqlite3.Row]:
        control = self._control_row(db)
        supervisor = self._fresh_supervisor_locked(db, now, boot_digest)
        participant = db.execute(
            "SELECT * FROM participants WHERE participant_code = ?",
            (session.participant_code,),
        ).fetchone()
        session_row = db.execute(
            "SELECT * FROM sessions WHERE session_code = ?",
            (session.session_code,),
        ).fetchone()
        if session_row is not None:
            owner = session_row["owner_digest"]
            session_times = (
                session_row["opened_at_boottime"],
                session_row["last_heartbeat_at_boottime"],
                session_row["lease_expires_at_boottime"],
            )
            if (
                type(owner) is not str
                or len(owner) != _DIGEST_LENGTH
                or any(character not in "0123456789abcdef" for character in owner)
                or type(session_row["heartbeat_sequence"]) is not int
                or int(session_row["heartbeat_sequence"]) < 1
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    for value in session_times
                )
                or float(session_row["last_heartbeat_at_boottime"])
                < float(session_row["opened_at_boottime"])
                or float(session_row["lease_expires_at_boottime"])
                <= float(session_row["last_heartbeat_at_boottime"])
                or float(session_row["lease_expires_at_boottime"])
                > float(session_row["last_heartbeat_at_boottime"]) + _SESSION_LEASE_SECONDS
                or (
                    session_row["status"] == "active"
                    and session_row["closed_at_boottime"] is not None
                )
            ):
                raise BudgetConfigurationError("A2 session lease bounds are inconsistent")
            if (
                float(session_row["opened_at_boottime"]) > now
                or float(session_row["last_heartbeat_at_boottime"]) > now
            ):
                self._commit_fault_locked(
                    db,
                    now,
                    "lease_timestamp_future",
                    "A2 session lease timestamp is in the future",
                )
        if (
            control["state"] != AlphaControlState.PREPARED
            or control["bound_supervisor_epoch"] is None
            or int(control["bound_supervisor_epoch"]) != int(supervisor["supervisor_epoch"])
        ):
            raise BudgetExceededError("A2 control state is not dispatchable")
        if (
            participant is None
            or participant["status"] != "admitted"
            or participant["profile"] != session.profile
            or participant["consent_version"] != _governor._CONSENT_VERSION
            or int(participant["input_authority_attested"]) != 1
            or int(participant["non_sensitive_use_attested"]) != 1
        ):
            raise BudgetExceededError("A2 participant admission is not current")
        if (
            session_row is None
            or session_row["participant_code"] != session.participant_code
            or session_row["profile"] != session.profile
            or session_row["status"] != "active"
            or session_row["owner_digest"] != owner_digest
            or session_row["boot_identity_digest"] != boot_digest
            or float(session_row["lease_expires_at_boottime"]) <= now
            or int(session_row["control_epoch"]) != int(control["control_epoch"])
            or int(session_row["admission_epoch"]) != int(participant["admission_epoch"])
        ):
            raise BudgetExceededError("A2 session authority is not current")
        return (
            control,
            supervisor,
            cast(sqlite3.Row, participant),
            cast(sqlite3.Row, session_row),
        )


class GovernedAsyncTransport(httpx.AsyncBaseTransport):
    """Consume one A2 permit immediately before one inner transport invocation."""

    def __init__(
        self,
        governor: A2SQLiteBudgetGovernor,
        inner: httpx.AsyncBaseTransport,
        *,
        _factory_token: object | None = None,
    ) -> None:
        if not (
            type(inner) is httpx.MockTransport
            or (
                type(inner) is httpx.AsyncHTTPTransport
                and _factory_token is _TRANSPORT_FACTORY_TOKEN
            )
        ):
            raise BudgetConfigurationError(
                "A2 accepts only its zero-retry production transport or exact MockTransport"
            )
        self._governor = governor
        self._inner = inner
        self._closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._closed:
            raise BudgetConfigurationError("A2 governed transport is closed")
        permit = self._governor._active_transport_permit()
        await self._governor._consume_for_transport(permit)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._inner.aclose()


class A2SQLiteBudgetGovernor:
    """One exact session owner using a fresh A2 v3 control plane."""

    def __init__(
        self,
        ledger_path: Path,
        session: ClosedAlphaSession,
        policy: ClosedAlphaPolicy | None = None,
        *,
        boottime: Callable[[], float] = _read_boottime_default,
        boot_identity: Callable[[], bytes] = _read_boot_identity_default,
        owner_secret: bytes | None = None,
    ) -> None:
        if type(session) is not ClosedAlphaSession:
            raise BudgetConfigurationError("A2 requires an exact immutable session identity")
        secret = secrets.token_bytes(_OWNER_SECRET_BYTES) if owner_secret is None else owner_secret
        self._owner_secret = secret
        self._owner_digest = _owner_digest(secret)
        self._governor_id = secrets.token_hex(16)
        self._control = A2SQLiteAlphaControlPlane(
            ledger_path,
            policy,
            boottime=boottime,
            boot_identity=boot_identity,
        )
        self._session = session
        self._active_permit: ContextVar[DispatchPermit | None] = ContextVar(
            f"evidencemesh_a2_permit_{self._governor_id}",
            default=None,
        )
        self._lock = asyncio.Lock()
        self._opened = False
        self._closed = False
        self._poisoned = False
        self._authority_epochs: tuple[int, int, int, int] | None = None
        self._last_session_heartbeat_boottime: float | None = None
        self._owned_clients: dict[int, httpx.AsyncClient] = {}
        self._feedback_authority: FeedbackPublicationAuthority | None = None
        self._feedback_lock = threading.Lock()
        self._feedback_clock_anchors: dict[str, _FeedbackClockAnchor] = {}
        self._prepared_feedback: dict[str, _PreparedFeedbackPublication] = {}

    @property
    def enabled(self) -> bool:
        return not self._closed and not self._poisoned

    @property
    def scope(self) -> str:
        return "single_host_shared_sqlite_a2"

    @property
    def session(self) -> ClosedAlphaSession:
        return self._session

    @property
    def policy(self) -> ClosedAlphaPolicy:
        return self._control.policy

    @property
    def owner_digest(self) -> str:
        return self._owner_digest

    def validate_provider_configuration(
        self,
        provider_names: Sequence[str],
        searxng_fallback_urls: Sequence[str],
        *,
        deployment_profile: str | None = None,
    ) -> None:
        """Require the exact audited bundle bound to this A2 admission."""

        if self._closed or self._poisoned:
            raise BudgetConfigurationError("A2 governor is fail-closed")
        if searxng_fallback_urls:
            raise BudgetConfigurationError("A2 forbids automatic SearXNG fallbacks")
        if deployment_profile != self.session.profile:
            raise BudgetConfigurationError("A2 deployment profile does not match admission")
        if tuple(provider_names) != _governor._ALPHA_PROVIDER_BUNDLES[self.session.profile]:
            raise BudgetConfigurationError("A2 requires the exact admitted provider bundle")

    def validate_provider_bundle(
        self,
        provider_names: Sequence[str],
        *,
        deployment_profile: str,
    ) -> None:
        """Reject custom or factory bundles that differ from the admission."""

        self.validate_provider_configuration(
            provider_names,
            (),
            deployment_profile=deployment_profile,
        )

    def validate_provider(self, provider: object, client: httpx.AsyncClient) -> str:
        """Accept only exact audited provider classes using this governed client."""

        if self._closed or self._poisoned:
            raise BudgetConfigurationError("A2 governor is fail-closed")
        provider_type = type(provider)
        expected_name = next(
            (
                provider_name
                for audited_type, provider_name in _governor._AUDITED_PROVIDER_TYPES
                if provider_type is audited_type
            ),
            None,
        )
        actual_name = getattr(provider, "name", None)
        if expected_name is None or type(actual_name) is not str or actual_name != expected_name:
            raise BudgetConfigurationError(
                "A2 accepts only audited single-dispatch HTTPX providers"
            )
        if getattr(provider, "client", None) is not client:
            raise BudgetConfigurationError("A2 provider does not use its governed HTTPX client")
        self.attach_client(client)
        return expected_name

    def attach_client(self, client: httpx.AsyncClient) -> None:
        """Verify that a client was built by this governor; never retrofit one."""

        if self._closed or self._poisoned:
            raise BudgetConfigurationError("A2 governor is fail-closed")
        if (
            type(client) is not httpx.AsyncClient
            or self._owned_clients.get(id(client)) is not client
        ):
            raise BudgetConfigurationError("A2 requires a client created by this governor")

    async def _database_call(self, operation: Callable[[], _T]) -> _T:
        async with self._lock:
            if self._closed or self._poisoned:
                raise BudgetConfigurationError("A2 governor is fail-closed")
            try:
                return await asyncio.to_thread(operation)
            except (BudgetExceededError, BudgetConfigurationError):
                raise
            except (OSError, sqlite3.Error) as exc:
                self._poisoned = True
                raise BudgetConfigurationError("A2 governor ledger operation failed") from exc

    @staticmethod
    def _token_digest(token: str) -> str:
        try:
            raw = bytes.fromhex(token)
        except ValueError as exc:
            raise BudgetConfigurationError("A2 permit token is invalid") from exc
        if len(raw) != _OWNER_SECRET_BYTES or token != raw.hex():
            raise BudgetConfigurationError("A2 permit token is invalid")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _validate_intents(session: ClosedAlphaSession, intents: Sequence[DispatchIntent]) -> None:
        bundle = _governor._ALPHA_PROVIDER_BUNDLES[session.profile]
        for intent in intents:
            if type(intent) is not DispatchIntent:
                raise BudgetConfigurationError("A2 requires exact dispatch intents")
            if intent.kind == "provider" and intent.provider not in bundle:
                raise BudgetConfigurationError("A2 provider is outside the admitted bundle")

    async def open_session(self) -> int:
        """Atomically create the active session and its first owner heartbeat."""

        if self._opened:
            raise BudgetConfigurationError("A2 session is already open")
        operation = asyncio.create_task(self._database_call(self._open_session_sync))
        cancellation: asyncio.CancelledError | None = None
        try:
            epochs, heartbeat_at = await asyncio.shield(operation)
        except asyncio.CancelledError as exc:
            cancellation = exc
            epochs, heartbeat_at = await operation
        self._authority_epochs = epochs
        self._last_session_heartbeat_boottime = heartbeat_at
        self._opened = True
        if cancellation is not None:
            raise cancellation
        return epochs[3]

    def _open_session_sync(self) -> tuple[tuple[int, int, int, int], float]:
        control_plane = self._control
        with contextlib.closing(control_plane._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db)
                control_plane._require_no_lapse_locked(db, now, boot_digest)
                control = control_plane._control_row(db)
                supervisor = control_plane._fresh_supervisor_locked(db, now, boot_digest)
                if (
                    control["state"] != AlphaControlState.PREPARED
                    or control["bound_supervisor_epoch"] is None
                    or int(control["bound_supervisor_epoch"]) != int(supervisor["supervisor_epoch"])
                ):
                    raise BudgetExceededError("A2 control plane is not prepared")
                participant = db.execute(
                    "SELECT * FROM participants WHERE participant_code = ?",
                    (self.session.participant_code,),
                ).fetchone()
                if (
                    participant is None
                    or participant["status"] != "admitted"
                    or participant["profile"] != self.session.profile
                    or participant["consent_version"] != _governor._CONSENT_VERSION
                    or int(participant["input_authority_attested"]) != 1
                    or int(participant["non_sensitive_use_attested"]) != 1
                ):
                    raise BudgetExceededError("A2 participant is not admitted")
                if (
                    db.execute(
                        "SELECT 1 FROM sessions WHERE session_code = ?",
                        (self.session.session_code,),
                    ).fetchone()
                    is not None
                ):
                    raise BudgetConfigurationError("A2 session identity was already used")
                total_sessions = int(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
                participant_sessions = int(
                    db.execute(
                        "SELECT COUNT(*) FROM sessions WHERE participant_code = ?",
                        (self.session.participant_code,),
                    ).fetchone()[0]
                )
                active_sessions = int(
                    db.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'").fetchone()[
                        0
                    ]
                )
                if total_sessions >= self.policy.sessions_total_max:
                    raise BudgetExceededError("A2 global session budget exhausted")
                if participant_sessions >= self.policy.sessions_per_participant_max:
                    raise BudgetExceededError("A2 participant session budget exhausted")
                if active_sessions >= self.policy.concurrent_sessions_max:
                    raise BudgetExceededError("A2 concurrent session budget exhausted")
                db.execute(
                    """
                    INSERT INTO sessions(
                        session_code, participant_code, profile, owner_digest, status,
                        control_epoch, admission_epoch, session_epoch,
                        boot_identity_digest, heartbeat_sequence,
                        last_heartbeat_at_boottime, lease_expires_at_boottime,
                        opened_at_boottime, closed_at_boottime
                    ) VALUES (?, ?, ?, ?, 'active', ?, ?, 1, ?, 1, ?, ?, ?, NULL)
                    """,
                    (
                        self.session.session_code,
                        self.session.participant_code,
                        self.session.profile,
                        self._owner_digest,
                        int(control["control_epoch"]),
                        int(participant["admission_epoch"]),
                        boot_digest,
                        now,
                        now + _SESSION_LEASE_SECONDS,
                        now,
                    ),
                )
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return (
            (
                int(supervisor["supervisor_epoch"]),
                int(control["control_epoch"]),
                int(participant["admission_epoch"]),
                1,
            ),
            now,
        )

    def _require_bound_epochs(
        self,
        control: sqlite3.Row,
        supervisor: sqlite3.Row,
        participant: sqlite3.Row,
        session_row: sqlite3.Row,
    ) -> None:
        expected = self._authority_epochs
        actual = (
            int(supervisor["supervisor_epoch"]),
            int(control["control_epoch"]),
            int(participant["admission_epoch"]),
            int(session_row["session_epoch"]),
        )
        if expected is None or actual != expected:
            raise BudgetExceededError("A2 session authority epoch changed")

    async def heartbeat_session(self) -> int:
        if not self._opened:
            raise BudgetConfigurationError("A2 session is not open")
        sequence, heartbeat_at = await self._database_call(self._heartbeat_session_sync)
        self._last_session_heartbeat_boottime = heartbeat_at
        return sequence

    def _heartbeat_session_sync(self) -> tuple[int, float]:
        control_plane = self._control
        with contextlib.closing(control_plane._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db)
                control_plane._require_no_lapse_locked(db, now, boot_digest)
                control, supervisor, participant, session_row = (
                    control_plane._session_authority_locked(
                        db,
                        self.session,
                        self._owner_digest,
                        now,
                        boot_digest,
                    )
                )
                self._require_bound_epochs(control, supervisor, participant, session_row)
                sequence = int(session_row["heartbeat_sequence"])
                cursor = db.execute(
                    """
                    UPDATE sessions
                    SET heartbeat_sequence = heartbeat_sequence + 1,
                        last_heartbeat_at_boottime = ?, lease_expires_at_boottime = ?
                    WHERE session_code = ? AND status = 'active' AND owner_digest = ?
                      AND session_epoch = ? AND admission_epoch = ? AND control_epoch = ?
                      AND boot_identity_digest = ? AND heartbeat_sequence = ?
                    """,
                    (
                        now,
                        now + _SESSION_LEASE_SECONDS,
                        self.session.session_code,
                        self._owner_digest,
                        int(session_row["session_epoch"]),
                        int(participant["admission_epoch"]),
                        int(control["control_epoch"]),
                        boot_digest,
                        sequence,
                    ),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 session heartbeat CAS failed")
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return sequence + 1, now

    async def run_session_heartbeat(
        self,
        stop: asyncio.Event,
        *,
        wait: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Autonomously renew only this exact session lease."""

        try:
            while not stop.is_set():
                last_heartbeat = self._last_session_heartbeat_boottime
                if last_heartbeat is None:
                    raise BudgetConfigurationError("A2 session heartbeat has no opening fence")
                deadline = last_heartbeat + _SESSION_HEARTBEAT_SECONDS
                now = _read_finite_clock(self._control._boottime)
                remaining = deadline - _MINIMUM_FRESHNESS_SECONDS - now
                if remaining < 0.0:
                    remaining = 0.0
                if wait is asyncio.sleep:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(
                            stop.wait(),
                            timeout=remaining,
                        )
                else:
                    await wait(remaining)
                if stop.is_set():
                    break
                if _read_finite_clock(self._control._boottime) > deadline:
                    raise BudgetConfigurationError("A2 session heartbeat deadline was missed")
                await self.heartbeat_session()
                if (
                    self._last_session_heartbeat_boottime is None
                    or self._last_session_heartbeat_boottime > deadline
                ):
                    raise BudgetConfigurationError("A2 session heartbeat deadline was missed")
        except BaseException:
            # A heartbeat runner is a single-use authority.  An unexpected
            # exit cannot silently leave the still-unexpired lease dispatchable.
            self._poisoned = True
            raise

    async def reserve_batch(self, intents: Sequence[DispatchIntent]) -> list[DispatchPermit]:
        if not self._opened:
            raise BudgetConfigurationError("A2 reserve requires explicit open_session")
        frozen = tuple(intents)
        if not frozen:
            raise BudgetConfigurationError("A2 reservation batch cannot be empty")
        self._validate_intents(self.session, frozen)
        raw_tokens = tuple(secrets.token_bytes(_OWNER_SECRET_BYTES) for _ in frozen)
        token_strings = tuple(token.hex() for token in raw_tokens)
        token_digests = tuple(hashlib.sha256(token).hexdigest() for token in raw_tokens)
        supervisor_epoch, control_epoch, admission_epoch, session_epoch = await self._database_call(
            lambda: self._reserve_sync(frozen, token_digests)
        )
        # supervisor_epoch is durably bound in each attempt row; possession of
        # its opaque token selects that exact row at the transport boundary.
        if supervisor_epoch < 1:
            raise BudgetConfigurationError("A2 supervisor epoch is invalid")
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
            for intent, token in zip(frozen, token_strings, strict=True)
        ]

    def _reserve_sync(
        self,
        intents: Sequence[DispatchIntent],
        token_digests: Sequence[str],
    ) -> tuple[int, int, int, int]:
        control_plane = self._control
        with contextlib.closing(control_plane._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db)
                control_plane._require_no_lapse_locked(db, now, boot_digest)
                control, supervisor, participant, session_row = (
                    control_plane._session_authority_locked(
                        db,
                        self.session,
                        self._owner_digest,
                        now,
                        boot_digest,
                    )
                )
                self._require_bound_epochs(control, supervisor, participant, session_row)
                batch_size = len(intents)
                session_attempts = int(
                    db.execute(
                        "SELECT COUNT(*) FROM attempts WHERE session_code = ?",
                        (self.session.session_code,),
                    ).fetchone()[0]
                )
                global_attempts = int(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])
                if session_attempts + batch_size > self.policy.provider_attempts_per_session_max:
                    raise BudgetExceededError("A2 session dispatch budget exhausted")
                if global_attempts + batch_size > self.policy.provider_attempts_total_max:
                    raise BudgetExceededError("A2 global dispatch budget exhausted")
                tavily_batch = sum(intent.provider == "tavily" for intent in intents)
                session_tavily = int(
                    db.execute(
                        """
                        SELECT COUNT(*) FROM attempts
                        WHERE session_code = ? AND provider = 'tavily'
                        """,
                        (self.session.session_code,),
                    ).fetchone()[0]
                )
                global_tavily = int(
                    db.execute(
                        "SELECT COUNT(*) FROM attempts WHERE provider = 'tavily'"
                    ).fetchone()[0]
                )
                tavily_limit = (
                    self.policy.tavily_attempts_quality_session_max
                    if self.session.profile == "quality"
                    else self.policy.tavily_attempts_community_session_max
                )
                if session_tavily + tavily_batch > tavily_limit:
                    raise BudgetExceededError("A2 Tavily session budget exhausted")
                if global_tavily + tavily_batch > self.policy.tavily_attempts_total_max:
                    raise BudgetExceededError("A2 Tavily global budget exhausted")
                recent = int(
                    db.execute(
                        """
                        SELECT COUNT(*) FROM attempts
                        WHERE (outcome = 'reserved' AND reserved_at_boottime > ?)
                           OR (dispatched_at_boottime IS NOT NULL
                               AND dispatched_at_boottime > ?)
                        """,
                        (now - 60.0, now - 60.0),
                    ).fetchone()[0]
                )
                if recent + batch_size > self.policy.request_starts_per_minute_max:
                    raise BudgetExceededError("A2 rolling request-start budget exhausted")
                db.executemany(
                    """
                    INSERT INTO attempts(
                        token_digest, session_code, kind, provider,
                        reserved_at_boottime, supervisor_epoch, control_epoch,
                        admission_epoch, session_epoch, dispatched,
                        dispatched_at_boottime, consumed_at_boottime, outcome
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, 'reserved')
                    """,
                    (
                        (
                            token_digest,
                            self.session.session_code,
                            intent.kind,
                            intent.provider,
                            now,
                            int(supervisor["supervisor_epoch"]),
                            int(control["control_epoch"]),
                            int(participant["admission_epoch"]),
                            int(session_row["session_epoch"]),
                        )
                        for intent, token_digest in zip(intents, token_digests, strict=True)
                    ),
                )
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return (
            int(supervisor["supervisor_epoch"]),
            int(control["control_epoch"]),
            int(participant["admission_epoch"]),
            int(session_row["session_epoch"]),
        )

    @contextmanager
    def capture(self, permit: DispatchPermit) -> Iterator[None]:
        self._validate_permit_owner(permit)
        if self._active_permit.get() is not None:
            raise BudgetConfigurationError("A2 nested dispatch permits are forbidden")
        token = self._active_permit.set(permit)
        try:
            yield
        finally:
            self._active_permit.reset(token)

    def _validate_permit_owner(self, permit: DispatchPermit) -> None:
        if self._closed or self._poisoned:
            raise BudgetConfigurationError("A2 governor is not dispatchable")
        if type(permit) is not DispatchPermit:
            raise BudgetConfigurationError("A2 requires an exact dispatch permit")
        if (
            permit._governor_id != self._governor_id
            or permit.session_code != self.session.session_code
        ):
            raise BudgetConfigurationError("A2 permit belongs to another governor or session")
        self._validate_intents(
            self.session,
            (DispatchIntent(permit.kind, permit.provider),),
        )

    def _active_transport_permit(self) -> DispatchPermit:
        if self._closed or self._poisoned:
            raise BudgetConfigurationError("A2 governor is not dispatchable")
        permit = self._active_permit.get()
        if permit is None:
            raise BudgetConfigurationError("A2 transport departure has no permit")
        self._validate_permit_owner(permit)
        return permit

    async def _on_request(self, _request: httpx.Request) -> None:
        permit = self._active_transport_permit()
        await self._database_call(lambda: self._early_check_sync(permit))

    def _early_check_sync(self, permit: DispatchPermit) -> None:
        self._check_or_consume_sync(permit, consume=False)

    async def _consume_for_transport(self, permit: DispatchPermit) -> None:
        self._validate_permit_owner(permit)
        await self._database_call(lambda: self._check_or_consume_sync(permit, consume=True))

    def _check_or_consume_sync(self, permit: DispatchPermit, *, consume: bool) -> None:
        control_plane = self._control
        token_digest = self._token_digest(permit.token)
        with contextlib.closing(control_plane._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db)
                control_plane._require_no_lapse_locked(db, now, boot_digest)
                control, supervisor, participant, session_row = (
                    control_plane._session_authority_locked(
                        db,
                        self.session,
                        self._owner_digest,
                        now,
                        boot_digest,
                    )
                )
                self._require_bound_epochs(control, supervisor, participant, session_row)
                attempt = db.execute(
                    """
                    SELECT * FROM attempts
                    WHERE token_digest = ? AND session_code = ? AND kind = ?
                      AND provider IS ? AND outcome = 'reserved' AND dispatched = 0
                    """,
                    (
                        token_digest,
                        permit.session_code,
                        permit.kind,
                        permit.provider,
                    ),
                ).fetchone()
                if attempt is None:
                    raise BudgetExceededError("A2 dispatch permit is invalid or consumed")
                if (
                    int(attempt["supervisor_epoch"]) != int(supervisor["supervisor_epoch"])
                    or int(attempt["control_epoch"]) != permit.control_epoch
                    or int(control["control_epoch"]) != permit.control_epoch
                    or int(attempt["admission_epoch"]) != permit.admission_epoch
                    or int(participant["admission_epoch"]) != permit.admission_epoch
                    or int(attempt["session_epoch"]) != permit.session_epoch
                    or int(session_row["session_epoch"]) != permit.session_epoch
                ):
                    if consume:
                        db.execute(
                            """
                            UPDATE attempts SET dispatched = 1,
                                consumed_at_boottime = ?, outcome = 'denied_epoch'
                            WHERE id = ? AND outcome = 'reserved'
                            """,
                            (now, int(attempt["id"])),
                        )
                        control_plane._write_boottime(db, now, boot_digest)
                        db.commit()
                    raise BudgetExceededError("A2 stale permit epoch")
                if consume:
                    recent = int(
                        db.execute(
                            """
                            SELECT COUNT(*) FROM attempts
                            WHERE dispatched_at_boottime > ?
                            """,
                            (now - 60.0,),
                        ).fetchone()[0]
                    )
                    if recent >= self.policy.request_starts_per_minute_max:
                        db.execute(
                            """
                            UPDATE attempts SET dispatched = 1,
                                consumed_at_boottime = ?, outcome = 'denied_rate'
                            WHERE id = ? AND outcome = 'reserved'
                            """,
                            (now, int(attempt["id"])),
                        )
                        control_plane._write_boottime(db, now, boot_digest)
                        db.commit()
                        raise BudgetExceededError("A2 rolling request-start budget exhausted")
                    cursor = db.execute(
                        """
                        UPDATE attempts
                        SET dispatched = 1, dispatched_at_boottime = ?,
                            consumed_at_boottime = ?, outcome = 'started'
                        WHERE id = ? AND dispatched = 0 AND outcome = 'reserved'
                        """,
                        (now, now, int(attempt["id"])),
                    )
                    if cursor.rowcount != 1:
                        raise BudgetExceededError("A2 permit consumption CAS failed")
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise

    def make_client(
        self,
        inner_transport: httpx.AsyncBaseTransport | None = None,
        *,
        timeout: float | httpx.Timeout = 20.0,
        headers: Mapping[str, str] | None = None,
        limits: httpx.Limits | None = None,
    ) -> httpx.AsyncClient:
        """Create one exact governed client with redirects, proxies and HTTP/2 off."""

        if self._closed or self._poisoned:
            raise BudgetConfigurationError("A2 governor is not dispatchable")
        inner: httpx.AsyncBaseTransport
        if inner_transport is None:
            inner = httpx.AsyncHTTPTransport(retries=0)
        elif type(inner_transport) is httpx.MockTransport:
            inner = inner_transport
        else:
            raise BudgetConfigurationError("A2 custom transports are forbidden")
        transport = GovernedAsyncTransport(
            self,
            inner,
            _factory_token=_TRANSPORT_FACTORY_TOKEN,
        )
        resolved_limits = httpx.Limits() if limits is None else limits
        client = httpx.AsyncClient(
            transport=transport,
            event_hooks={"request": [self._on_request]},
            follow_redirects=False,
            trust_env=False,
            http2=False,
            timeout=timeout,
            headers=headers,
            limits=resolved_limits,
        )
        self._owned_clients[id(client)] = client
        return client

    @property
    def feedback_authority(self) -> FeedbackPublicationAuthority:
        authority = self._feedback_authority
        if authority is None:
            raise BudgetConfigurationError("A2 feedback authority requires an exact close")
        return authority

    def feedback_context(
        self,
        participant_code: str,
        session_code: str,
    ) -> FeedbackContext | None:
        if (
            _governor._PARTICIPANT_PATTERN.fullmatch(participant_code) is None
            or _governor._SESSION_PATTERN.fullmatch(session_code) is None
        ):
            return None
        try:
            with contextlib.closing(self._control._connect(allow_fault=True)) as db:
                row = db.execute(
                    """
                    SELECT p.slot_id, p.profile, COUNT(a.id) AS provider_attempts,
                        COALESCE(SUM(CASE WHEN a.provider = 'tavily' THEN 1 ELSE 0 END), 0)
                            AS tavily_attempts
                    FROM sessions AS s
                    JOIN participants AS p
                      ON p.participant_code = s.participant_code
                    LEFT JOIN attempts AS a ON a.session_code = s.session_code
                    WHERE s.session_code = ? AND s.participant_code = ?
                      AND s.status = 'closed' AND s.closed_at_boottime IS NOT NULL
                      AND s.profile = p.profile AND p.status = 'admitted'
                      AND s.admission_epoch = p.admission_epoch
                      AND p.consent_version = ?
                      AND p.input_authority_attested = 1
                      AND p.non_sensitive_use_attested = 1
                    GROUP BY p.slot_id, p.profile
                    """,
                    (
                        session_code,
                        participant_code,
                        _governor._CONSENT_VERSION,
                    ),
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

    def withdrawal_committed(self, participant_code: str) -> bool:
        if _governor._PARTICIPANT_PATTERN.fullmatch(participant_code) is None:
            return False
        try:
            with contextlib.closing(self._control._connect(allow_fault=True)) as db:
                row = db.execute(
                    """
                    SELECT 1 FROM participants
                    WHERE participant_code = ? AND status = 'withdrawn'
                      AND withdrawn_at_boottime IS NOT NULL
                    """,
                    (participant_code,),
                ).fetchone()
                return row is not None
        except (OSError, sqlite3.Error, BudgetConfigurationError):
            return False

    def advance_feedback_clock(self, timestamp: float) -> bool:
        if (
            not isinstance(timestamp, (int, float))
            or isinstance(timestamp, bool)
            or not math.isfinite(timestamp)
        ):
            self.record_privacy_fault()
            return False
        observed = float(timestamp)
        control_plane = self._control
        with contextlib.closing(control_plane._connect(allow_fault=True)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db, allow_boot_rebase=True)
                row = db.execute(
                    "SELECT value FROM metadata WHERE key = 'feedback_clock_high_water'"
                ).fetchone()
                if row is not None and observed < float(row["value"]):
                    control_plane._trip_fault_locked(db, now, "feedback_clock_regression")
                    control_plane._write_boottime(db, now, boot_digest)
                    db.commit()
                    return False
                db.execute(
                    """
                    INSERT INTO metadata(key, value)
                    VALUES ('feedback_clock_high_water', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (repr(observed),),
                )
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return True

    def record_privacy_fault(self) -> None:
        control_plane = self._control
        with contextlib.closing(control_plane._connect(allow_fault=True)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                _governor.SQLiteAlphaControlPlane._ensure_privacy_fault_marker(
                    control_plane  # type: ignore[arg-type]
                )
                now, boot_digest = control_plane._now_locked(db, allow_boot_rebase=True)
                control_plane._contain_all_locked(db, now, expire_supervisor=True)
                db.execute(
                    """
                    UPDATE control_state SET privacy_fault = 1,
                        updated_at_boottime = ? WHERE singleton = 1
                    """,
                    (now,),
                )
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise

    def _require_feedback_authority(
        self,
        authority: object,
    ) -> FeedbackPublicationAuthority:
        expected = self._feedback_authority
        if (
            type(authority) is not FeedbackPublicationAuthority
            or expected is None
            or authority != expected
            or not secrets.compare_digest(authority.token, expected.token)
        ):
            raise BudgetConfigurationError("A2 feedback capability is stale or foreign")
        return authority

    def _closed_feedback_rows_locked(
        self,
        db: sqlite3.Connection,
        authority: FeedbackPublicationAuthority,
        now: float,
        boot_digest: str,
    ) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row, SupervisorLease]:
        control = self._control._control_row(db)
        supervisor = self._control._fresh_supervisor_locked(db, now, boot_digest)
        participant = db.execute(
            "SELECT * FROM participants WHERE participant_code = ?",
            (authority.participant_code,),
        ).fetchone()
        session_row = db.execute(
            "SELECT * FROM sessions WHERE session_code = ?",
            (authority.session_code,),
        ).fetchone()
        if (
            control["state"] != AlphaControlState.PREPARED
            or int(control["control_epoch"]) != authority.control_epoch
            or control["bound_supervisor_epoch"] is None
            or int(control["bound_supervisor_epoch"]) != authority.supervisor.supervisor_epoch
            or int(supervisor["supervisor_epoch"]) != authority.supervisor.supervisor_epoch
            or participant is None
            or participant["status"] != "admitted"
            or int(participant["admission_epoch"]) != authority.admission_epoch
            or session_row is None
            or session_row["status"] != "closed"
            or session_row["participant_code"] != authority.participant_code
            or session_row["owner_digest"] != authority.owner_digest
            or int(session_row["control_epoch"]) != authority.control_epoch
            or int(session_row["admission_epoch"]) != authority.admission_epoch
            or int(session_row["session_epoch"]) != authority.session_epoch
            or float(session_row["closed_at_boottime"]) != authority.closed_at_boottime
        ):
            raise BudgetConfigurationError("A2 closed feedback binding is not current")
        return (
            control,
            cast(sqlite3.Row, participant),
            cast(sqlite3.Row, session_row),
            self._control._supervisor_snapshot_locked(db),
        )

    def feedback_publication_clock_anchor(
        self,
        *,
        store_binding: FeedbackStoreBinding,
    ) -> object:
        control_plane = self._control
        with contextlib.closing(control_plane._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db)
                control_plane._require_no_lapse_locked(db, now, boot_digest)
                control_plane._require_bound_store_locked(db, store_binding)
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        anchor = _FeedbackClockAnchor(
            token=secrets.token_hex(_OWNER_SECRET_BYTES),
            checked_at_boottime=now,
            store_binding=store_binding,
        )
        with self._feedback_lock:
            self._feedback_clock_anchors[anchor.token] = anchor
        return anchor

    def discard_feedback_publication_clock_anchor(self, clock_anchor: object) -> None:
        if type(clock_anchor) is not _FeedbackClockAnchor:
            return
        with self._feedback_lock:
            if self._feedback_clock_anchors.get(clock_anchor.token) == clock_anchor:
                self._feedback_clock_anchors.pop(clock_anchor.token, None)

    def prepare_feedback_publication(
        self,
        authority: object,
        *,
        participant_code: str,
        session_code: str,
        checked_at_utc: float,
        purge_at_utc: float,
        is_new: bool,
        store_binding: FeedbackStoreBinding,
        clock_anchor: object,
    ) -> object:
        capability = self._require_feedback_authority(authority)
        if type(clock_anchor) is not _FeedbackClockAnchor:
            raise BudgetConfigurationError("A2 feedback clock anchor is invalid")
        with self._feedback_lock:
            captured_anchor = self._feedback_clock_anchors.pop(clock_anchor.token, None)
        if (
            captured_anchor != clock_anchor
            or clock_anchor.store_binding != store_binding
            or participant_code != capability.participant_code
            or session_code != capability.session_code
            or type(is_new) is not bool
            or not isinstance(checked_at_utc, (int, float))
            or isinstance(checked_at_utc, bool)
            or not math.isfinite(checked_at_utc)
            or not isinstance(purge_at_utc, (int, float))
            or isinstance(purge_at_utc, bool)
            or not math.isfinite(purge_at_utc)
            or purge_at_utc <= checked_at_utc
        ):
            raise BudgetConfigurationError("A2 feedback publication inputs are invalid")
        control_plane = self._control
        with contextlib.closing(control_plane._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db)
                control_plane._require_no_lapse_locked(db, now, boot_digest)
                control_plane._require_bound_store_locked(db, store_binding)
                _control, _participant, _session, supervisor = self._closed_feedback_rows_locked(
                    db,
                    capability,
                    now,
                    boot_digest,
                )
                if is_new:
                    current_expiry = supervisor.lease_expires_at_boottime
                    if current_expiry is None:
                        raise BudgetConfigurationError("A2 supervisor expiry is absent")
                    purge_cap = (
                        clock_anchor.checked_at_boottime
                        + (float(purge_at_utc) - float(checked_at_utc))
                        - _MINIMUM_FRESHNESS_SECONDS
                    )
                    fenced_expiry = math.nextafter(
                        min(current_expiry, purge_cap),
                        -math.inf,
                    )
                    if fenced_expiry - now <= _MINIMUM_FRESHNESS_SECONDS:
                        raise BudgetConfigurationError(
                            "A2 feedback retention deadline is too close"
                        )
                    cursor = db.execute(
                        """
                        UPDATE supervisor_lease SET lease_expires_at_boottime = ?
                        WHERE singleton = 1 AND state = 'active'
                          AND supervisor_epoch = ? AND heartbeat_sequence = ?
                          AND boot_identity_digest = ?
                          AND lease_expires_at_boottime = ?
                        """,
                        (
                            fenced_expiry,
                            supervisor.supervisor_epoch,
                            supervisor.heartbeat_sequence,
                            boot_digest,
                            current_expiry,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise BudgetConfigurationError("A2 feedback fence CAS failed")
                    supervisor = control_plane._supervisor_snapshot_locked(db)
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        prepared = _PreparedFeedbackPublication(
            token=secrets.token_hex(_OWNER_SECRET_BYTES),
            authority_token=capability.token,
            participant_code=participant_code,
            session_code=session_code,
            checked_at_utc=float(checked_at_utc),
            supervisor=supervisor,
        )
        with self._feedback_lock:
            self._prepared_feedback[prepared.token] = prepared
        return prepared

    @contextmanager
    def feedback_publication_guard(
        self,
        authority: object,
        *,
        participant_code: str,
        session_code: str,
        checked_at_utc: float,
        store_binding: FeedbackStoreBinding,
    ) -> Iterator[None]:
        if type(authority) is not _PreparedFeedbackPublication:
            raise BudgetConfigurationError("A2 feedback preparation token is invalid")
        with self._feedback_lock:
            prepared = self._prepared_feedback.pop(authority.token, None)
        if (
            prepared != authority
            or participant_code != authority.participant_code
            or session_code != authority.session_code
            or checked_at_utc != authority.checked_at_utc
        ):
            raise BudgetConfigurationError("A2 feedback preparation token is stale")
        capability = self._require_feedback_authority(self.feedback_authority)
        if not secrets.compare_digest(authority.authority_token, capability.token):
            raise BudgetConfigurationError("A2 feedback preparation capability changed")
        control_plane = self._control
        with contextlib.closing(control_plane._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db)
                control_plane._require_no_lapse_locked(db, now, boot_digest)
                control_plane._require_bound_store_locked(db, store_binding)
                _control, _participant, _session, supervisor = self._closed_feedback_rows_locked(
                    db,
                    capability,
                    now,
                    boot_digest,
                )
                if supervisor != authority.supervisor:
                    raise BudgetConfigurationError("A2 feedback final CAS is stale")
                yield
                control_plane._write_boottime(db, now, boot_digest)
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise

    async def snapshot(self) -> dict[str, int | str | bool | float | None]:
        return await asyncio.to_thread(self._control.snapshot)

    async def aclose(self) -> None:
        if self._closed:
            return
        failure: BaseException | None = None
        try:
            if self._opened and not self._poisoned:
                try:
                    self._feedback_authority = await self._database_call(self._close_session_sync)
                except BaseException as exc:
                    failure = exc
            for client in tuple(self._owned_clients.values()):
                try:
                    await client.aclose()
                except BaseException as exc:
                    if failure is None:
                        failure = exc
        finally:
            self._closed = True
            self._owned_clients.clear()
        if failure is not None:
            raise failure

    def _close_session_sync(self) -> FeedbackPublicationAuthority:
        control_plane = self._control
        with contextlib.closing(control_plane._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now, boot_digest = control_plane._now_locked(db)
                control_plane._require_no_lapse_locked(db, now, boot_digest)
                control, supervisor, participant, session_row = (
                    control_plane._session_authority_locked(
                        db,
                        self.session,
                        self._owner_digest,
                        now,
                        boot_digest,
                    )
                )
                self._require_bound_epochs(control, supervisor, participant, session_row)
                cursor = db.execute(
                    """
                    UPDATE sessions SET status = 'closed', closed_at_boottime = ?
                    WHERE session_code = ? AND status = 'active' AND owner_digest = ?
                      AND session_epoch = ? AND lease_expires_at_boottime > ?
                    """,
                    (
                        now,
                        self.session.session_code,
                        self._owner_digest,
                        int(session_row["session_epoch"]),
                        now,
                    ),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("A2 session cannot be closed safely")
                db.execute(
                    """
                    UPDATE attempts SET dispatched = 1, consumed_at_boottime = ?,
                        outcome = 'denied_state'
                    WHERE session_code = ? AND outcome = 'reserved'
                    """,
                    (now, self.session.session_code),
                )
                control_plane._write_boottime(db, now, boot_digest)
                authority = FeedbackPublicationAuthority(
                    token=secrets.token_hex(_OWNER_SECRET_BYTES),
                    participant_code=self.session.participant_code,
                    session_code=self.session.session_code,
                    owner_digest=self._owner_digest,
                    control_epoch=int(control["control_epoch"]),
                    admission_epoch=int(participant["admission_epoch"]),
                    session_epoch=int(session_row["session_epoch"]),
                    closed_at_boottime=now,
                    supervisor=control_plane._supervisor_snapshot_locked(db),
                )
                db.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
                raise
        return authority


class A2RetentionSupervisor:
    """Run successful retention before every singleton supervisor heartbeat."""

    def __init__(
        self,
        control_plane: A2SQLiteAlphaControlPlane,
        store: ClosedAlphaFeedbackStore,
        *,
        owner_secret: bytes | None = None,
        wait: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if type(control_plane) is not A2SQLiteAlphaControlPlane:
            raise BudgetConfigurationError("A2 supervisor requires the exact control plane")
        if type(store) is not ClosedAlphaFeedbackStore:
            raise BudgetConfigurationError("A2 supervisor requires the exact feedback store")
        secret = secrets.token_bytes(_OWNER_SECRET_BYTES) if owner_secret is None else owner_secret
        self._owner_secret = secret
        self._owner_digest = _owner_digest(secret)
        self._control = control_plane
        self._store = store
        self._store_binding = control_plane._verified_store_binding(store)
        with contextlib.closing(control_plane._connect()) as db:
            control_plane._require_bound_store_locked(db, self._store_binding)
        self._wait = wait
        self._lease: SupervisorLease | None = None
        self._closed = False
        self._lock = asyncio.Lock()

    @property
    def lease(self) -> SupervisorLease | None:
        return self._lease

    @staticmethod
    def _retention_values(result: PurgeResult, now: float) -> tuple[float, float]:
        if type(result) is not PurgeResult:
            raise BudgetConfigurationError("A2 retention pass returned an invalid result")
        checked_at = result.checked_at
        if checked_at.tzinfo is None:
            raise BudgetConfigurationError("A2 retention high-water is timezone-naive")
        try:
            high_water = checked_at.astimezone(UTC).timestamp()
        except (OSError, OverflowError, ValueError) as exc:
            raise BudgetConfigurationError("A2 retention high-water is invalid") from exc
        if not math.isfinite(high_water):
            raise BudgetConfigurationError("A2 retention high-water is invalid")
        if result.next_purge_at is None:
            # No report is due sooner.  Thirty-five seconds makes the normal
            # 30-second supervisor TTL, including the five-second deadline cap.
            next_purge = now + _SUPERVISOR_LEASE_SECONDS + _MINIMUM_FRESHNESS_SECONDS
        else:
            if result.next_purge_at.tzinfo is None:
                raise BudgetConfigurationError("A2 next purge deadline is timezone-naive")
            delay = (
                result.next_purge_at.astimezone(UTC) - checked_at.astimezone(UTC)
            ).total_seconds()
            if not math.isfinite(delay) or delay < 0.0:
                raise BudgetConfigurationError("A2 next purge deadline is invalid")
            next_purge = now + delay
        return high_water, next_purge

    async def run_once(self) -> SupervisorLease:
        """Purge, reconcile, then acquire or renew exactly once."""

        async with self._lock:
            if self._closed:
                raise BudgetConfigurationError("A2 retention supervisor is closed")
            result, expected, binding, retention_boottime = await asyncio.to_thread(
                self._store.bound_retention_pass,
                lambda _result, _binding: self._control.supervisor_cas_snapshot(),
                lambda: _read_finite_clock(self._control._boottime),
            )
            if (
                binding != self._store_binding
                or self._control._verified_store_binding(self._store) != self._store_binding
            ):
                raise BudgetConfigurationError("A2 authoritative feedback store changed")
            await asyncio.to_thread(self._control.reconcile)
            high_water, next_purge = self._retention_values(result, retention_boottime)
            if self._lease is None:
                if expected.state not in {"unclaimed", "revoked"}:
                    raise BudgetConfigurationError(
                        "A2 supervisor restart requires explicit paused recovery"
                    )
                operation = asyncio.create_task(
                    asyncio.to_thread(
                        self._control._acquire_supervisor,
                        self._owner_secret,
                        expected=expected,
                        store_binding=binding,
                        last_successful_retention_high_water_utc=high_water,
                        next_purge_at_boottime=next_purge,
                    )
                )
            else:
                operation = asyncio.create_task(
                    asyncio.to_thread(
                        self._control._renew_supervisor,
                        self._owner_secret,
                        expected=expected,
                        store_binding=binding,
                        last_successful_retention_high_water_utc=high_water,
                        next_purge_at_boottime=next_purge,
                    )
                )
            cancellation: asyncio.CancelledError | None = None
            try:
                lease = await asyncio.shield(operation)
            except asyncio.CancelledError as exc:
                cancellation = exc
                lease = await operation
            if lease.owner_digest != self._owner_digest or lease.state != "active":
                raise BudgetConfigurationError("A2 supervisor CAS returned foreign authority")
            self._lease = lease
            if cancellation is not None:
                raise cancellation
            return lease

    async def run(self, stop: asyncio.Event) -> None:
        """Run at ten-second maximum cadence; never retry a failed cycle."""

        failure: BaseException | None = None
        try:
            lease = await self.run_once()
            while not stop.is_set():
                heartbeat_at = lease.last_heartbeat_at_boottime
                if heartbeat_at is None:
                    raise BudgetConfigurationError("A2 supervisor heartbeat is absent")
                deadline = heartbeat_at + _SUPERVISOR_HEARTBEAT_SECONDS
                now = _read_finite_clock(self._control._boottime)
                remaining = deadline - _MINIMUM_FRESHNESS_SECONDS - now
                if remaining < 0.0:
                    remaining = 0.0
                if self._wait is asyncio.sleep:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=remaining)
                else:
                    await self._wait(remaining)
                if stop.is_set():
                    break
                if _read_finite_clock(self._control._boottime) > deadline:
                    raise BudgetConfigurationError("A2 supervisor heartbeat deadline was missed")
                lease = await self.run_once()
                if (
                    lease.last_heartbeat_at_boottime is None
                    or lease.last_heartbeat_at_boottime > deadline
                ):
                    raise BudgetConfigurationError("A2 supervisor heartbeat deadline was missed")
        except BaseException as exc:
            failure = exc
        try:
            await self.aclose()
        except BaseException as close_exc:
            if failure is None:
                failure = close_exc
        if failure is not None:
            raise failure

    async def aclose(self) -> None:
        """Final purge first, then pause and revoke; never renew in ``finally``."""

        async with self._lock:
            if self._closed:
                return
            failure: BaseException | None = None
            shutdown_epoch = None if self._lease is None else self._lease.supervisor_epoch
            shutdown_attempted = False
            final_snapshot: SupervisorLease | None = None

            def final_action(
                _result: PurgeResult,
                binding: FeedbackStoreBinding,
            ) -> SupervisorLease:
                nonlocal shutdown_attempted, final_snapshot, shutdown_epoch
                final_snapshot = self._control.supervisor_cas_snapshot()
                if (
                    shutdown_epoch is None
                    and final_snapshot.state in {"active", "expired"}
                    and final_snapshot.owner_digest == self._owner_digest
                ):
                    shutdown_epoch = final_snapshot.supervisor_epoch
                if shutdown_epoch is not None:
                    shutdown_attempted = True
                    final_snapshot = self._control._shutdown_supervisor(
                        self._owner_secret,
                        expected_supervisor_epoch=shutdown_epoch,
                        store_binding=binding,
                    )
                return final_snapshot

            try:
                _result, final_snapshot, binding, _retention_boottime = await asyncio.to_thread(
                    self._store.bound_retention_pass,
                    final_action,
                    lambda: _read_finite_clock(self._control._boottime),
                )
                if binding != self._store_binding:
                    raise BudgetConfigurationError("A2 authoritative feedback store changed")
            except BaseException as exc:
                failure = exc
            if shutdown_epoch is None and final_snapshot is None:
                try:
                    final_snapshot = await asyncio.to_thread(self._control.supervisor_cas_snapshot)
                    if (
                        final_snapshot.state in {"active", "expired"}
                        and final_snapshot.owner_digest == self._owner_digest
                    ):
                        shutdown_epoch = final_snapshot.supervisor_epoch
                except BaseException as exc:
                    if failure is None:
                        failure = exc
            if shutdown_epoch is not None and not shutdown_attempted:
                shutdown_attempted = True
                try:
                    final_snapshot = await asyncio.to_thread(
                        self._control._shutdown_supervisor,
                        self._owner_secret,
                        expected_supervisor_epoch=shutdown_epoch,
                        store_binding=self._store_binding,
                    )
                except BaseException as exc:
                    if failure is None:
                        failure = exc
            if final_snapshot is None:
                try:
                    final_snapshot = await asyncio.to_thread(self._control.supervisor_cas_snapshot)
                except BaseException as exc:
                    if failure is None:
                        failure = exc
            authority_contained = bool(
                shutdown_epoch is None
                or (
                    final_snapshot is not None
                    and final_snapshot.state != "active"
                    and final_snapshot.control_state != AlphaControlState.PREPARED
                )
            )
            if not authority_contained and failure is None:
                failure = BudgetConfigurationError(
                    "A2 supervisor shutdown did not contain authority"
                )
            if authority_contained:
                self._lease = None
                self._closed = True
            if failure is not None:
                raise failure


__all__ = [
    "A2RetentionSupervisor",
    "A2SQLiteAlphaControlPlane",
    "A2SQLiteBudgetGovernor",
    "FeedbackPublicationAuthority",
    "GovernedAsyncTransport",
    "SupervisorLease",
]
