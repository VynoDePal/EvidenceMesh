from __future__ import annotations

import asyncio
import contextlib
import hashlib
import socket
import sqlite3
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

import evidencemesh.alpha_liveness as liveness_module
import evidencemesh.closed_alpha_feedback as feedback_module
from evidencemesh.alpha_liveness import (
    A2RetentionSupervisor,
    A2SQLiteAlphaControlPlane,
    A2SQLiteBudgetGovernor,
    GovernedAsyncTransport,
)
from evidencemesh.closed_alpha_feedback import (
    ClosedAlphaFeedbackContract,
    ClosedAlphaFeedbackIdentity,
    ClosedAlphaFeedbackStore,
    PurgeResult,
)
from evidencemesh.config import Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError
from evidencemesh.governor import (
    AlphaControlState,
    ClosedAlphaAdmission,
    ClosedAlphaSession,
    DispatchIntent,
    SQLiteAlphaControlPlane,
)

_BOOT_A = "12345678-1234-5678-1234-567812345678"
_BOOT_B = "87654321-4321-6789-4321-678987654321"
_SUPERVISOR_SECRET = b"s" * 32
_SESSION_SECRET = b"o" * 32
_DEADLOCK_GUARD_SECONDS = 15.0


@dataclass
class HostClock:
    now: float = 100.0
    boot: str = _BOOT_A

    def boottime(self) -> float:
        return self.now

    def boot_identity(self) -> bytes:
        return f"{self.boot}\n".encode("ascii")

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class FeedbackClock:
    now: datetime = datetime(2026, 8, 3, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def _deny_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A2-P1 tests must not access a real network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    yield


def _participant(index: int) -> str:
    return f"p-{index:016x}"


def _session(index: int) -> str:
    return f"s-{index:032x}"


def _admit_full_cohort(control: A2SQLiteAlphaControlPlane) -> None:
    for index in range(1, 7):
        control.admit(
            ClosedAlphaAdmission(
                participant_code=_participant(index),
                slot_id=f"C{index:02d}",
                profile="community",
                consent_version="closed-alpha-a0-consent-v1",
                consent_accepted=True,
                input_authority_attested=True,
                non_sensitive_use_attested=True,
            )
        )
    for offset in range(1, 3):
        control.admit(
            ClosedAlphaAdmission(
                participant_code=_participant(6 + offset),
                slot_id=f"Q{offset:02d}",
                profile="quality",
                consent_version="closed-alpha-a0-consent-v1",
                consent_accepted=True,
                input_authority_attested=True,
                non_sensitive_use_attested=True,
            )
        )


def _bootstrap(
    root: Path,
    host: HostClock,
) -> tuple[A2SQLiteAlphaControlPlane, Path]:
    if not root.exists():
        root.mkdir(mode=0o700)
    ledger = root / "private" / "a2-control.sqlite3"
    control = A2SQLiteAlphaControlPlane.bootstrap(
        ledger,
        boottime=host.boottime,
        boot_identity=host.boot_identity,
    )
    return control, ledger


def _synthetic_contract() -> ClosedAlphaFeedbackContract:
    identity = object.__new__(ClosedAlphaFeedbackIdentity)
    values = {
        "candidate_sha": "c1e0be437442b0d97da26f2c9085067a8c09955e",
        "candidate_tree": "a" * 40,
        "repository": "VynoDePal/EvidenceMesh",
        "record_sha256": "b" * 64,
        "archive_subject": "dist/evidencemesh-0.1.0-py3-none-any.whl",
        "archive_sha256": "c" * 64,
        "_verification": feedback_module._IDENTITY_VERIFICATION,
    }
    for name, value in values.items():
        object.__setattr__(identity, name, value)
    return ClosedAlphaFeedbackContract(identity)


def _feedback_store(
    root: Path,
    clock: FeedbackClock,
    governor: A2SQLiteBudgetGovernor,
) -> ClosedAlphaFeedbackStore:
    return ClosedAlphaFeedbackStore(
        root / "private-feedback",
        _synthetic_contract(),
        governor,
        clock=clock,
    )


def _bound_runtime(
    root: Path,
    host: HostClock,
    feedback_clock: FeedbackClock,
) -> tuple[
    A2SQLiteAlphaControlPlane,
    Path,
    ClosedAlphaFeedbackStore,
    A2SQLiteBudgetGovernor,
]:
    control, ledger = _bootstrap(root, host)
    governor = A2SQLiteBudgetGovernor(
        ledger,
        ClosedAlphaSession(
            participant_code=_participant(1),
            session_code=_session(1),
            profile="community",
        ),
        boottime=host.boottime,
        boot_identity=host.boot_identity,
        owner_secret=_SESSION_SECRET,
    )
    store = _feedback_store(root, feedback_clock, governor)
    assert control.bind_feedback_store(store, expected_control_epoch=1) == 2
    assert control.snapshot()["feedback_store_bound"] is True
    return control, ledger, store, governor


async def _prepared_runtime(
    root: Path,
    host: HostClock,
    feedback_clock: FeedbackClock,
) -> tuple[
    A2SQLiteAlphaControlPlane,
    Path,
    ClosedAlphaFeedbackStore,
    A2RetentionSupervisor,
    A2SQLiteBudgetGovernor,
]:
    control, ledger, store, governor = _bound_runtime(root, host, feedback_clock)
    supervisor = A2RetentionSupervisor(
        control,
        store,
        owner_secret=_SUPERVISOR_SECRET,
    )
    await supervisor.run_once()
    _admit_full_cohort(control)
    assert (
        control.transition(
            AlphaControlState.PREPARED,
            expected_state=AlphaControlState.PAUSED,
            expected_epoch=2,
        )
        == 3
    )
    return control, ledger, store, supervisor, governor


def _session_row(ledger: Path) -> sqlite3.Row:
    with sqlite3.connect(ledger) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM sessions WHERE session_code = ?", (_session(1),)).fetchone()
    assert row is not None
    return row


def test_v2_is_refused_without_mutation_and_v3_binds_metadata_digests(
    tmp_path: Path,
) -> None:
    host = HostClock()
    v2_ledger = tmp_path / "v2" / "control.sqlite3"
    SQLiteAlphaControlPlane.bootstrap(v2_ledger, clock=host.boottime)
    before_payload = v2_ledger.read_bytes()
    before_names = sorted(path.name for path in v2_ledger.parent.iterdir())

    with pytest.raises(BudgetConfigurationError, match=r"non-v3|migrated|policy-drifted"):
        A2SQLiteAlphaControlPlane(
            v2_ledger,
            boottime=host.boottime,
            boot_identity=host.boot_identity,
        )

    assert v2_ledger.read_bytes() == before_payload
    assert sorted(path.name for path in v2_ledger.parent.iterdir()) == before_names

    control, ledger = _bootstrap(tmp_path / "v3", host)
    assert control.snapshot()["schema_version"] == "evidencemesh.closed-alpha-control-plane.v3"
    with sqlite3.connect(ledger) as db:
        metadata = dict(db.execute("SELECT key, value FROM metadata"))
        supervisor_columns = {row[1] for row in db.execute("PRAGMA table_info(supervisor_lease)")}
    assert metadata["schema_version"] == "evidencemesh.closed-alpha-control-plane.v3"
    assert (
        metadata["last_boottime_boot_identity_digest"]
        == hashlib.sha256(_BOOT_A.encode("ascii")).hexdigest()
    )
    assert len(metadata["policy_fingerprint"]) == 64
    assert metadata["ledger_device"].isdigit()
    assert metadata["ledger_inode"].isdigit()
    assert _BOOT_A.encode("ascii") not in ledger.read_bytes()
    assert "next_purge_at_boottime" not in supervisor_columns


@pytest.mark.asyncio
async def test_real_retention_pass_acquires_then_renews_supervisor(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, _governor = _bound_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    supervisor = A2RetentionSupervisor(
        control,
        store,
        owner_secret=_SUPERVISOR_SECRET,
    )
    try:
        first = await supervisor.run_once()
        assert first.state == "active"
        assert first.heartbeat_sequence == 1
        assert first.lease_expires_at_boottime == host.now + 30.0
        assert first.last_successful_retention_high_water_utc == feedback_clock.now.timestamp()

        host.advance(10.0)
        feedback_clock.advance(10.0)
        second = await supervisor.run_once()
        assert second.supervisor_epoch == first.supervisor_epoch
        assert second.heartbeat_sequence == 2
        assert second.lease_expires_at_boottime == host.now + 30.0
        assert second.last_successful_retention_high_water_utc == feedback_clock.now.timestamp()
    finally:
        await supervisor.aclose()
        store.close()
    assert control.snapshot()["supervisor_state"] == "revoked"


def test_supervisor_freshness_is_strictly_greater_than_five_seconds(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, _governor = _bound_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    binding = store.retention_binding()
    expected = control.supervisor_cas_snapshot()
    with pytest.raises(BudgetConfigurationError, match="too close"):
        control._acquire_supervisor(
            _SUPERVISOR_SECRET,
            expected=expected,
            store_binding=binding,
            last_successful_retention_high_water_utc=1_775_000_000.0,
            next_purge_at_boottime=host.now + 10.0,
        )
    assert control.supervisor_cas_snapshot() == expected

    lease = control._acquire_supervisor(
        _SUPERVISOR_SECRET,
        expected=expected,
        store_binding=binding,
        last_successful_retention_high_water_utc=1_775_000_000.0,
        next_purge_at_boottime=host.now + 10.000_001,
    )
    assert lease.lease_expires_at_boottime is not None
    assert lease.lease_expires_at_boottime - host.now > 5.0
    store.close()


@pytest.mark.asyncio
async def test_prepare_requires_fresh_supervisor_and_zero_active_sessions(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, governor = _bound_runtime(tmp_path, host, feedback_clock)
    _admit_full_cohort(control)
    with pytest.raises(BudgetExceededError, match="supervisor lease"):
        control.transition("prepared", expected_state="paused", expected_epoch=2)

    supervisor = A2RetentionSupervisor(
        control,
        store,
        owner_secret=_SUPERVISOR_SECRET,
    )
    await supervisor.run_once()
    assert control.transition("prepared", expected_state="paused", expected_epoch=2) == 3
    await governor.open_session()
    with sqlite3.connect(ledger) as db:
        db.execute(
            """
            UPDATE control_state SET state = 'paused', control_epoch = 4,
                bound_supervisor_epoch = NULL WHERE singleton = 1
            """
        )
        db.commit()
    with pytest.raises(BudgetConfigurationError, match="active sessions"):
        control.transition("prepared", expected_state="paused", expected_epoch=4)
    assert _session_row(ledger)["status"] == "active"
    store.close()


@pytest.mark.asyncio
async def test_open_is_explicit_and_reserve_and_transport_never_renew_session(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    intent = DispatchIntent("provider", "wikipedia")
    with pytest.raises(BudgetConfigurationError, match="open_session"):
        await governor.reserve_batch([intent])
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0

    await governor.open_session()
    initial_expiry = float(_session_row(ledger)["lease_expires_at_boottime"])
    host.advance(1.0)
    permit = (await governor.reserve_batch([intent]))[0]
    assert float(_session_row(ledger)["lease_expires_at_boottime"]) == initial_expiry

    delegated = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal delegated
        delegated += 1
        return httpx.Response(200, request=request)

    client = governor.make_client(httpx.MockTransport(handler))
    with governor.capture(permit):
        response = await client.get("https://offline.invalid/test")
    assert response.status_code == 200
    assert delegated == 1
    assert float(_session_row(ledger)["lease_expires_at_boottime"]) == initial_expiry
    assert control.snapshot()["sessions"] == 1

    await governor.aclose()
    await supervisor.aclose()
    store.close()


@pytest.mark.asyncio
async def test_engine_opens_one_session_and_starts_heartbeat_only_on_first_use(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    _control, ledger, store, supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    settings = Settings(
        deployment_profile="community",
        enabled_providers=["arxiv", "crossref", "github", "searxng", "wikipedia"],
        cache_path=tmp_path / "engine-cache.sqlite3",
        respect_robots_txt=False,
    )
    engine = EvidenceMesh(settings, governor=governor)
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert engine._a2_session_task is None

    await engine._ensure_a2_session()
    heartbeat = engine._a2_session_task
    assert isinstance(heartbeat, asyncio.Task)
    assert not heartbeat.done()
    assert int(_session_row(ledger)["heartbeat_sequence"]) == 1

    await engine._ensure_a2_session()
    assert engine._a2_session_task is heartbeat
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1

    await engine.aclose()
    assert heartbeat.done()
    assert _session_row(ledger)["status"] == "closed"
    await supervisor.aclose()
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fence",
    [
        "owner",
        "supervisor_epoch",
        "control_epoch",
        "admission_epoch",
        "session_epoch",
        "boot",
    ],
)
async def test_session_heartbeat_fences_owner_all_epochs_and_boot(
    tmp_path: Path,
    fence: str,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    _control, ledger, store, _supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    await governor.open_session()
    with sqlite3.connect(ledger) as db:
        if fence == "owner":
            db.execute(
                "UPDATE sessions SET owner_digest = ? WHERE session_code = ?",
                (hashlib.sha256(b"foreign-owner").hexdigest(), _session(1)),
            )
        elif fence == "supervisor_epoch":
            db.execute("UPDATE supervisor_lease SET supervisor_epoch = supervisor_epoch + 1")
        elif fence == "control_epoch":
            db.execute("UPDATE control_state SET control_epoch = control_epoch + 1")
        elif fence == "admission_epoch":
            db.execute(
                """
                UPDATE participants SET admission_epoch = admission_epoch + 1
                WHERE participant_code = ?
                """,
                (_participant(1),),
            )
        elif fence == "session_epoch":
            db.execute(
                "UPDATE sessions SET session_epoch = session_epoch + 1 WHERE session_code = ?",
                (_session(1),),
            )
        else:
            db.execute(
                "UPDATE sessions SET boot_identity_digest = ? WHERE session_code = ?",
                ("0" * 64, _session(1)),
            )
        db.commit()

    with pytest.raises(BudgetExceededError, match=r"authority|recovery|control state"):
        await governor.heartbeat_session()
    assert int(_session_row(ledger)["heartbeat_sequence"]) == 1
    store.close()


@pytest.mark.asyncio
async def test_expired_session_close_commits_recovery_instead_of_closing(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    _control, ledger, store, _supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    await governor.open_session()
    await governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
    host.advance(300.0)

    with pytest.raises(BudgetExceededError, match="recovery"):
        await governor.aclose()

    row = _session_row(ledger)
    assert row["status"] == "recovery_required"
    assert row["closed_at_boottime"] is None
    with sqlite3.connect(ledger) as db:
        attempt = db.execute("SELECT dispatched, outcome FROM attempts").fetchone()
    assert attempt == (1, "denied_recovery")
    store.close()


def test_reboot_is_recoverable_but_same_boot_rollback_is_permanent(
    tmp_path: Path,
) -> None:
    reboot_host = HostClock()
    reboot_clock = FeedbackClock()
    rebooted, reboot_ledger, reboot_store, _reboot_governor = _bound_runtime(
        tmp_path / "reboot",
        reboot_host,
        reboot_clock,
    )
    reboot_binding = reboot_store.retention_binding()
    initial = rebooted.supervisor_cas_snapshot()
    active = rebooted._acquire_supervisor(
        _SUPERVISOR_SECRET,
        expected=initial,
        store_binding=reboot_binding,
        last_successful_retention_high_water_utc=1_775_000_000.0,
        next_purge_at_boottime=reboot_host.now + 35.0,
    )
    assert active.state == "active"
    reboot_host.boot = _BOOT_B
    reboot_host.now = 1.0
    rebooted.reconcile()
    expired = rebooted.supervisor_cas_snapshot()
    assert expired.state == "expired"
    assert rebooted.snapshot()["supervisor_fault"] is False
    assert rebooted.snapshot()["control_epoch"] == 3
    revoked = rebooted._revoke_supervisor(
        _SUPERVISOR_SECRET,
        expected=expired,
    )
    with pytest.raises(BudgetExceededError, match="not freshly dispatchable"):
        rebooted.transition(
            "prepared",
            expected_state="paused",
            expected_epoch=3,
        )
    assert rebooted.snapshot()["supervisor_fault"] is False
    reacquired = rebooted._acquire_supervisor(
        _SUPERVISOR_SECRET,
        expected=revoked,
        store_binding=reboot_binding,
        last_successful_retention_high_water_utc=1_775_000_001.0,
        next_purge_at_boottime=reboot_host.now + 35.0,
    )
    assert reacquired.state == "active"
    assert reacquired.supervisor_epoch == active.supervisor_epoch + 1
    assert not tuple(reboot_ledger.parent.glob("*.retention-supervisor-fault-v1"))
    reboot_store.close()

    rollback_host = HostClock()
    rollback_clock = FeedbackClock()
    rollback, rollback_ledger, rollback_store, _rollback_governor = _bound_runtime(
        tmp_path / "rollback",
        rollback_host,
        rollback_clock,
    )
    rollback_host.now -= 1.0
    with pytest.raises(BudgetConfigurationError, match="backwards"):
        rollback.reconcile()
    marker = rollback_ledger.with_name(f"{rollback_ledger.name}.retention-supervisor-fault-v1")
    assert marker.is_file()
    assert rollback.snapshot()["supervisor_fault"] is True
    rollback_host.now += 2.0
    with pytest.raises(BudgetConfigurationError, match="fault"):
        rollback.admit(
            ClosedAlphaAdmission(
                participant_code=_participant(1),
                slot_id="C01",
                profile="community",
                consent_version="closed-alpha-a0-consent-v1",
                consent_accepted=True,
                input_authority_attested=True,
                non_sensitive_use_attested=True,
            )
        )
    rollback_store.close()


def test_stale_expected_expiry_cannot_renew_supervisor(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, _governor = _bound_runtime(tmp_path, host, feedback_clock)
    binding = store.retention_binding()
    active = control._acquire_supervisor(
        _SUPERVISOR_SECRET,
        expected=control.supervisor_cas_snapshot(),
        store_binding=binding,
        last_successful_retention_high_water_utc=1_775_000_000.0,
        next_purge_at_boottime=host.now + 35.0,
    )
    assert active.lease_expires_at_boottime is not None
    fenced_expiry = active.lease_expires_at_boottime - 1.0
    with sqlite3.connect(ledger) as db:
        db.execute(
            "UPDATE supervisor_lease SET lease_expires_at_boottime = ? WHERE singleton = 1",
            (fenced_expiry,),
        )
        db.commit()

    with pytest.raises(BudgetConfigurationError, match="stale"):
        control._renew_supervisor(
            _SUPERVISOR_SECRET,
            expected=active,
            store_binding=binding,
            last_successful_retention_high_water_utc=1_775_000_001.0,
            next_purge_at_boottime=host.now + 35.0,
        )
    current = control.supervisor_cas_snapshot()
    assert current.heartbeat_sequence == active.heartbeat_sequence
    assert current.lease_expires_at_boottime == fenced_expiry
    store.close()


@pytest.mark.asyncio
async def test_same_epoch_wrong_supervisor_owner_commits_permanent_fault(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, _governor = _bound_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    supervisor = A2RetentionSupervisor(
        control,
        store,
        owner_secret=_SUPERVISOR_SECRET,
    )
    active = await supervisor.run_once()

    with pytest.raises(BudgetConfigurationError, match="owner mismatch"):
        control._renew_supervisor(
            b"x" * 32,
            expected=active,
            store_binding=store.retention_binding(),
            last_successful_retention_high_water_utc=feedback_clock.now.timestamp(),
            next_purge_at_boottime=host.now + 35.0,
        )

    marker = ledger.with_name(f"{ledger.name}.retention-supervisor-fault-v1")
    snapshot = control.snapshot()
    assert marker.is_file()
    assert snapshot["supervisor_fault"] is True
    assert snapshot["state"] == "paused"
    assert snapshot["control_epoch"] == 3
    assert snapshot["supervisor_state"] == "expired"
    with pytest.raises(BudgetConfigurationError, match="permanently blocks authority"):
        control._renew_supervisor(
            _SUPERVISOR_SECRET,
            expected=control.supervisor_cas_snapshot(),
            store_binding=store.retention_binding(),
            last_successful_retention_high_water_utc=feedback_clock.now.timestamp(),
            next_purge_at_boottime=host.now + 35.0,
        )
    store.close()


def test_boot_rebase_commits_epoch_before_stale_acquisition_is_fenced(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, _governor = _bound_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    binding = store.retention_binding()
    active = control._acquire_supervisor(
        _SUPERVISOR_SECRET,
        expected=control.supervisor_cas_snapshot(),
        store_binding=binding,
        last_successful_retention_high_water_utc=feedback_clock.now.timestamp(),
        next_purge_at_boottime=host.now + 35.0,
    )

    host.boot = _BOOT_B
    host.now = 1.0
    with pytest.raises(BudgetConfigurationError, match="acquisition CAS"):
        control._acquire_supervisor(
            _SUPERVISOR_SECRET,
            expected=active,
            store_binding=binding,
            last_successful_retention_high_water_utc=feedback_clock.now.timestamp(),
            next_purge_at_boottime=host.now + 35.0,
        )

    contained = control.snapshot()
    expired = control.supervisor_cas_snapshot()
    assert contained["state"] == "paused"
    assert contained["control_epoch"] == 3
    assert expired.state == "expired"
    with sqlite3.connect(ledger) as db:
        metadata = dict(db.execute("SELECT key, value FROM metadata"))
    assert float(metadata["last_boottime"]) == host.now
    assert (
        metadata["last_boottime_boot_identity_digest"]
        == hashlib.sha256(_BOOT_B.encode("ascii")).hexdigest()
    )

    revoked = control._revoke_supervisor(_SUPERVISOR_SECRET, expected=expired)
    recovered = control._acquire_supervisor(
        _SUPERVISOR_SECRET,
        expected=revoked,
        store_binding=binding,
        last_successful_retention_high_water_utc=feedback_clock.now.timestamp(),
        next_purge_at_boottime=host.now + 35.0,
    )
    assert recovered.supervisor_epoch == active.supervisor_epoch + 1
    assert recovered.control_epoch == 3
    store.close()


@pytest.mark.parametrize("fault_column", ["privacy_fault", "supervisor_fault"])
def test_fault_bits_deny_new_supervisor_authority(
    tmp_path: Path,
    fault_column: str,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, _governor = _bound_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    with sqlite3.connect(ledger) as db:
        if fault_column == "privacy_fault":
            db.execute("UPDATE control_state SET privacy_fault = 1 WHERE singleton = 1")
        else:
            db.execute("UPDATE control_state SET supervisor_fault = 1 WHERE singleton = 1")
        db.commit()

    with pytest.raises(
        (BudgetConfigurationError, BudgetExceededError),
        match=r"fault|authority",
    ):
        control._acquire_supervisor(
            _SUPERVISOR_SECRET,
            expected=control.supervisor_cas_snapshot(),
            store_binding=store.retention_binding(),
            last_successful_retention_high_water_utc=feedback_clock.now.timestamp(),
            next_purge_at_boottime=host.now + 35.0,
        )
    snapshot = control.snapshot()
    assert snapshot[fault_column] is True
    assert snapshot["supervisor_state"] == "unclaimed"
    assert snapshot["supervisor_heartbeat_sequence"] == 0
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("containment", ["paused", "stopped", "fault"])
async def test_withdrawal_and_recovery_remain_available_after_containment(
    tmp_path: Path,
    containment: str,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, _supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    await governor.open_session()

    if containment == "fault":
        governor.record_privacy_fault()
        assert control.snapshot()["privacy_fault"] is True
    else:
        assert (
            control.transition(
                containment,
                expected_state="prepared",
                expected_epoch=3,
            )
            == 4
        )
    assert control.snapshot()["state"] == ("paused" if containment == "fault" else containment)
    assert _session_row(ledger)["status"] == "recovery_required"

    assert control.withdraw(_participant(1), expected_admission_epoch=1) == 2
    recovery_epoch = int(control.snapshot()["control_epoch"])
    control.resolve_recovery(_session(1), expected_control_epoch=recovery_epoch)

    with sqlite3.connect(ledger) as db:
        participant = db.execute(
            "SELECT status, admission_epoch FROM participants WHERE participant_code = ?",
            (_participant(1),),
        ).fetchone()
    assert participant == ("withdrawn", 2)
    assert _session_row(ledger)["status"] == "closed"
    assert governor.withdrawal_committed(_participant(1)) is True
    store.close()


@pytest.mark.asyncio
async def test_supervisor_and_session_cadence_fail_closed_after_deadline(
    tmp_path: Path,
) -> None:
    supervisor_host = HostClock()
    supervisor_clock = FeedbackClock()
    control, _ledger, supervisor_store, _governor = _bound_runtime(
        tmp_path / "supervisor",
        supervisor_host,
        supervisor_clock,
    )
    supervisor_delays: list[float] = []

    async def late_supervisor_wait(delay: float) -> None:
        supervisor_delays.append(delay)
        supervisor_host.advance(delay + 5.001)

    supervisor = A2RetentionSupervisor(
        control,
        supervisor_store,
        owner_secret=_SUPERVISOR_SECRET,
        wait=late_supervisor_wait,
    )
    with pytest.raises(BudgetConfigurationError, match="deadline was missed"):
        await supervisor.run(asyncio.Event())
    assert supervisor_delays == pytest.approx([5.0])
    assert control.snapshot()["supervisor_heartbeat_sequence"] == 1
    assert control.snapshot()["supervisor_state"] == "revoked"
    supervisor_store.close()

    session_host = HostClock()
    session_clock = FeedbackClock()
    (
        _session_control,
        session_ledger,
        session_store,
        _session_supervisor,
        session_governor,
    ) = await _prepared_runtime(tmp_path / "session", session_host, session_clock)
    await session_governor.open_session()
    session_delays: list[float] = []

    async def late_session_wait(delay: float) -> None:
        session_delays.append(delay)
        session_host.advance(delay + 5.001)

    with pytest.raises(BudgetConfigurationError, match="deadline was missed"):
        await session_governor.run_session_heartbeat(
            asyncio.Event(),
            wait=late_session_wait,
        )
    assert session_delays == pytest.approx([95.0])
    assert int(_session_row(session_ledger)["heartbeat_sequence"]) == 1
    assert session_governor.enabled is False
    await session_governor.aclose()
    session_store.close()


@pytest.mark.asyncio
async def test_cancelled_open_finishes_atomic_open_before_propagating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    _control, ledger, store, supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original_database_call = governor._database_call

    async def delayed_database_call(operation: Callable[[], object]) -> object:
        entered.set()
        await release.wait()
        return await original_database_call(operation)

    monkeypatch.setattr(governor, "_database_call", delayed_database_call)
    opening = asyncio.create_task(governor.open_session())
    try:
        await asyncio.wait_for(
            entered.wait(),
            timeout=_DEADLOCK_GUARD_SECONDS,
        )
        opening.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(
                opening,
                timeout=_DEADLOCK_GUARD_SECONDS,
            )

        row = _session_row(ledger)
        assert row["status"] == "active"
        assert int(row["heartbeat_sequence"]) == 1
        assert governor.enabled is True
        await governor.aclose()
        assert _session_row(ledger)["status"] == "closed"
    finally:
        release.set()
        if not opening.done():
            opening.cancel()
        with contextlib.suppress(BaseException):
            await opening
        with contextlib.suppress(BaseException):
            await governor.aclose()
        with contextlib.suppress(BaseException):
            await supervisor.aclose()
        if not store.closed:
            store.close()


@pytest.mark.asyncio
async def test_cancelled_supervisor_acquire_records_committed_lease_before_propagating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, _governor = _bound_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    supervisor = A2RetentionSupervisor(
        control,
        store,
        owner_secret=_SUPERVISOR_SECRET,
    )
    committed = threading.Event()
    release = threading.Event()
    original_acquire = control._acquire_supervisor

    def acquire_then_wait(*args: object, **kwargs: object) -> object:
        lease = original_acquire(*args, **kwargs)
        committed.set()
        if not release.wait(timeout=_DEADLOCK_GUARD_SECONDS):
            raise AssertionError("supervisor cancellation barrier timed out")
        return lease

    monkeypatch.setattr(control, "_acquire_supervisor", acquire_then_wait)
    acquisition = asyncio.create_task(supervisor.run_once())
    try:
        assert await asyncio.to_thread(
            committed.wait,
            _DEADLOCK_GUARD_SECONDS,
        )
        acquisition.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(
                acquisition,
                timeout=_DEADLOCK_GUARD_SECONDS,
            )

        lease = supervisor.lease
        assert lease is not None
        assert lease.state == "active"
        assert lease.owner_digest is not None
        await supervisor.aclose()
        revoked = control.supervisor_cas_snapshot()
        assert revoked.state == "revoked"
        assert revoked.owner_digest == lease.owner_digest
        assert revoked.supervisor_epoch == lease.supervisor_epoch
    finally:
        release.set()
        if not acquisition.done():
            acquisition.cancel()
        with contextlib.suppress(BaseException):
            await acquisition
        with contextlib.suppress(BaseException):
            await supervisor.aclose()
        if not store.closed:
            store.close()


@pytest.mark.asyncio
async def test_supervisor_retention_deadline_uses_boottime_before_utc_purge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, _governor = _bound_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    supervisor = A2RetentionSupervisor(
        control,
        store,
        owner_secret=_SUPERVISOR_SECRET,
    )
    observed_utc = feedback_clock.now

    def slow_utc_purge_clock() -> datetime:
        host.advance(20.0)
        return observed_utc

    monkeypatch.setattr(store, "_clock", slow_utc_purge_clock)
    lease = await supervisor.run_once()

    assert lease.issued_at_boottime == 120.0
    assert lease.last_heartbeat_at_boottime == 120.0
    assert lease.lease_expires_at_boottime == 130.0
    assert lease.lease_expires_at_boottime < host.now + 30.0

    monkeypatch.setattr(store, "_clock", feedback_clock)
    await supervisor.aclose()
    store.close()


@pytest.mark.asyncio
async def test_supervisor_close_revokes_owned_epoch_after_publication_expiry_fence(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    await governor.open_session()
    await governor.aclose()
    active = supervisor.lease
    assert active is not None
    assert active.lease_expires_at_boottime is not None

    binding = store.retention_binding()
    checked_at_utc = feedback_clock.now.timestamp()
    clock_anchor = governor.feedback_publication_clock_anchor(store_binding=binding)
    governor.prepare_feedback_publication(
        governor.feedback_authority,
        participant_code=_participant(1),
        session_code=_session(1),
        checked_at_utc=checked_at_utc,
        purge_at_utc=checked_at_utc + 20.0,
        is_new=True,
        store_binding=binding,
        clock_anchor=clock_anchor,
    )
    fenced = control.supervisor_cas_snapshot()
    assert fenced.owner_digest == active.owner_digest
    assert fenced.supervisor_epoch == active.supervisor_epoch
    assert fenced.lease_expires_at_boottime is not None
    assert fenced.lease_expires_at_boottime < active.lease_expires_at_boottime

    await supervisor.aclose()

    revoked = control.supervisor_cas_snapshot()
    assert revoked.state == "revoked"
    assert revoked.owner_digest == active.owner_digest
    assert revoked.supervisor_epoch == active.supervisor_epoch
    assert revoked.lease_expires_at_boottime == fenced.lease_expires_at_boottime
    assert revoked.control_state == "paused"
    with sqlite3.connect(ledger) as db:
        row = db.execute(
            "SELECT state, owner_digest, supervisor_epoch FROM supervisor_lease"
        ).fetchone()
    assert row == ("revoked", active.owner_digest, active.supervisor_epoch)
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("lease_domain", ["supervisor", "session"])
async def test_future_heartbeat_timestamp_commits_permanent_fault(
    tmp_path: Path,
    lease_domain: str,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, _supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    if lease_domain == "session":
        await governor.open_session()

    with sqlite3.connect(ledger) as db:
        if lease_domain == "supervisor":
            db.execute(
                """
                UPDATE supervisor_lease SET last_heartbeat_at_boottime = ?
                WHERE singleton = 1
                """,
                (host.now + 1.0,),
            )
        else:
            db.execute(
                """
                UPDATE sessions SET last_heartbeat_at_boottime = ?
                WHERE session_code = ?
                """,
                (host.now + 1.0, _session(1)),
            )
        db.commit()

    with pytest.raises(BudgetConfigurationError, match="timestamp is in the future"):
        if lease_domain == "supervisor":
            await governor.open_session()
        else:
            await governor.heartbeat_session()

    marker = ledger.with_name(f"{ledger.name}.retention-supervisor-fault-v1")
    snapshot = control.snapshot()
    assert marker.is_file()
    assert snapshot["supervisor_fault"] is True
    assert snapshot["state"] == "paused"
    assert snapshot["supervisor_state"] == "expired"
    if lease_domain == "session":
        assert _session_row(ledger)["status"] == "recovery_required"
    with pytest.raises(BudgetConfigurationError, match="permanently blocks authority"):
        if lease_domain == "supervisor":
            await governor.open_session()
        else:
            await governor.heartbeat_session()
    store.close()


@pytest.mark.parametrize(
    "failure",
    [
        "boot-reader-error",
        "boot-not-bytes",
        "boot-nul",
        "boot-not-ascii",
        "boot-not-uuid",
        "boot-not-canonical",
        "clock-error",
        "clock-bool",
        "clock-nan",
        "clock-negative",
    ],
)
def test_bootstrap_rejects_invalid_public_clock_sources(
    tmp_path: Path,
    failure: str,
) -> None:
    def boot_identity() -> bytes:
        if failure == "boot-reader-error":
            raise OSError("synthetic boot identity failure")
        if failure == "boot-not-bytes":
            return "not-bytes"  # type: ignore[return-value]
        if failure == "boot-nul":
            return b"bad\x00boot"
        if failure == "boot-not-ascii":
            return b"\xff" * 16
        if failure == "boot-not-uuid":
            return b"not-a-uuid"
        if failure == "boot-not-canonical":
            return b"ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB"
        return f"{_BOOT_A}\n".encode("ascii")

    def boottime() -> float:
        if failure == "clock-error":
            raise OSError("synthetic boottime failure")
        if failure == "clock-bool":
            return True  # type: ignore[return-value]
        if failure == "clock-nan":
            return float("nan")
        if failure == "clock-negative":
            return -1.0
        return 100.0

    with pytest.raises(BudgetConfigurationError, match=r"boot identity|boottime clock"):
        A2SQLiteAlphaControlPlane.bootstrap(
            tmp_path / failure / "control.sqlite3",
            boottime=boottime,
            boot_identity=boot_identity,
        )


def test_bootstrap_uses_and_requires_linux_default_liveness_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = A2SQLiteAlphaControlPlane.bootstrap(tmp_path / "default" / "control.sqlite3")
    snapshot = control.snapshot()
    assert snapshot["state"] == "paused"
    assert snapshot["schema_version"] == "evidencemesh.closed-alpha-control-plane.v3"

    monkeypatch.delattr(liveness_module.time, "CLOCK_BOOTTIME")
    with pytest.raises(BudgetConfigurationError, match="boottime clock is unavailable"):
        A2SQLiteAlphaControlPlane.bootstrap(tmp_path / "missing-clock" / "control.sqlite3")


def test_public_binding_and_transition_cas_rejections(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, _governor = _bound_runtime(
        tmp_path / "bound",
        host,
        feedback_clock,
    )
    try:
        with pytest.raises(BudgetConfigurationError, match="control epoch"):
            control.bind_feedback_store(store, expected_control_epoch=False)
        assert control.bind_feedback_store(store, expected_control_epoch=2) == 2
        with pytest.raises(BudgetConfigurationError, match="binding CAS"):
            control.bind_feedback_store(store, expected_control_epoch=1)

        with pytest.raises(BudgetConfigurationError, match="control state"):
            control.transition("invalid", expected_state="paused", expected_epoch=2)
        with pytest.raises(BudgetConfigurationError, match="control epoch"):
            control.transition("stopped", expected_state="paused", expected_epoch=0)
        with pytest.raises(BudgetConfigurationError, match="forbidden"):
            control.transition("paused", expected_state="paused", expected_epoch=2)
        with pytest.raises(BudgetConfigurationError, match="control CAS"):
            control.transition("stopped", expected_state="paused", expected_epoch=99)
    finally:
        store.close()

    unbound, _ledger = _bootstrap(tmp_path / "unbound", HostClock())
    with pytest.raises(BudgetConfigurationError, match="authoritative feedback store"):
        unbound.transition("prepared", expected_state="paused", expected_epoch=1)


@pytest.mark.asyncio
async def test_prepare_rejects_recovery_required_session(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    try:
        await governor.open_session()
        paused_epoch = control.transition(
            "paused",
            expected_state="prepared",
            expected_epoch=3,
        )
        with pytest.raises(BudgetConfigurationError, match="recovery must finish"):
            control.transition(
                "prepared",
                expected_state="paused",
                expected_epoch=paused_epoch,
            )
    finally:
        with contextlib.suppress(BaseException):
            await governor.aclose()
        with contextlib.suppress(BaseException):
            await supervisor.aclose()
        store.close()


@pytest.mark.parametrize(
    ("payload", "mode"),
    [
        (b"{}\n", 0o644),
        (b"not-json\n", 0o600),
        (b"[]\n", 0o600),
        (b'{"schema_version":1}\n', 0o600),
    ],
)
def test_reconcile_invalid_public_marker_is_durably_contained(
    tmp_path: Path,
    payload: bytes,
    mode: int,
) -> None:
    host = HostClock()
    control, ledger = _bootstrap(tmp_path, host)
    marker = ledger.with_name(f"{ledger.name}.retention-supervisor-fault-v1")
    marker.write_bytes(payload)
    marker.chmod(mode)

    with pytest.raises(BudgetConfigurationError, match="durably contained"):
        control.reconcile()

    snapshot = control.snapshot()
    assert snapshot["state"] == "paused"
    assert snapshot["supervisor_fault"] is True


def test_reconcile_existing_valid_marker_remains_fail_closed(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, _governor = _bound_runtime(tmp_path, host, feedback_clock)
    try:
        host.now -= 1.0
        with pytest.raises(BudgetConfigurationError, match="backwards"):
            control.reconcile()
        host.now += 2.0
        with pytest.raises(BudgetConfigurationError, match="durably contained"):
            control.reconcile()
        assert control.snapshot()["supervisor_fault"] is True
    finally:
        store.close()


@pytest.mark.asyncio
async def test_session_heartbeat_runner_renews_then_stops_cleanly(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    _control, ledger, store, supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    stop = asyncio.Event()
    waits: list[float] = []

    async def one_renewal_then_stop(delay: float) -> None:
        waits.append(delay)
        if len(waits) == 1:
            host.advance(5.0)
            return
        stop.set()

    try:
        await governor.open_session()
        await governor.run_session_heartbeat(stop, wait=one_renewal_then_stop)
        row = _session_row(ledger)
        assert int(row["heartbeat_sequence"]) == 2
        assert float(row["last_heartbeat_at_boottime"]) == host.now
        assert float(row["lease_expires_at_boottime"]) == host.now + 300.0
        assert waits == pytest.approx([95.0, 95.0])
    finally:
        await governor.aclose()
        await supervisor.aclose()
        store.close()


@pytest.mark.asyncio
async def test_supervisor_runner_renews_then_stops_cleanly(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, _governor = _bound_runtime(tmp_path, host, feedback_clock)
    stop = asyncio.Event()
    waits: list[float] = []

    async def one_renewal_then_stop(delay: float) -> None:
        waits.append(delay)
        if len(waits) == 1:
            host.advance(delay)
            feedback_clock.advance(delay)
            return
        stop.set()

    supervisor = A2RetentionSupervisor(
        control,
        store,
        owner_secret=_SUPERVISOR_SECRET,
        wait=one_renewal_then_stop,
    )
    try:
        await supervisor.run(stop)
        assert waits == pytest.approx([5.0, 5.0])
        assert supervisor.lease is None
        assert control.snapshot()["supervisor_state"] == "revoked"
    finally:
        with contextlib.suppress(BaseException):
            await supervisor.aclose()
        store.close()


@pytest.mark.parametrize("invalid_result", ["object", "naive-checked", "naive-next", "past-next"])
@pytest.mark.asyncio
async def test_supervisor_rejects_invalid_retention_results_through_run_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_result: str,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, _governor = _bound_runtime(tmp_path, host, feedback_clock)
    supervisor = A2RetentionSupervisor(control, store, owner_secret=_SUPERVISOR_SECRET)
    binding = store.retention_binding()
    checked = feedback_clock.now
    if invalid_result == "object":
        result: object = object()
    elif invalid_result == "naive-checked":
        result = PurgeResult(checked.replace(tzinfo=None), 0, None)
    elif invalid_result == "naive-next":
        result = PurgeResult(checked, 0, checked.replace(tzinfo=None))
    else:
        result = PurgeResult(checked, 0, checked - timedelta(seconds=1))

    monkeypatch.setattr(
        store,
        "bound_retention_pass",
        lambda _action, _clock: (
            result,
            control.supervisor_cas_snapshot(),
            binding,
            host.now,
        ),
    )
    try:
        with pytest.raises(BudgetConfigurationError, match=r"retention|timezone|deadline"):
            await supervisor.run_once()
    finally:
        with contextlib.suppress(BaseException):
            await supervisor.aclose()
        store.close()


@pytest.mark.parametrize("case", ["invalid", "regression"])
@pytest.mark.asyncio
async def test_feedback_clock_public_api_fails_closed(
    tmp_path: Path,
    case: str,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, _ledger, store, supervisor, governor = await _prepared_runtime(
        tmp_path,
        host,
        feedback_clock,
    )
    try:
        if case == "invalid":
            assert governor.advance_feedback_clock(float("nan")) is False
            assert control.snapshot()["privacy_fault"] is True
        else:
            high_water = feedback_clock.now.timestamp()
            assert governor.advance_feedback_clock(high_water) is True
            assert governor.advance_feedback_clock(high_water - 1.0) is False
            snapshot = control.snapshot()
            assert snapshot["supervisor_fault"] is True
            assert snapshot["state"] == "paused"
    finally:
        with contextlib.suppress(BaseException):
            await governor.aclose()
        with contextlib.suppress(BaseException):
            await supervisor.aclose()
        store.close()


def test_withdraw_and_recovery_reject_invalid_public_cas_inputs(
    tmp_path: Path,
) -> None:
    host = HostClock()
    control, _ledger = _bootstrap(tmp_path, host)

    with pytest.raises(BudgetConfigurationError, match="participant code"):
        control.withdraw("invalid", expected_admission_epoch=1)
    with pytest.raises(BudgetConfigurationError, match="admission epoch"):
        control.withdraw(_participant(1), expected_admission_epoch=False)
    with pytest.raises(BudgetConfigurationError, match="withdrawal CAS"):
        control.withdraw(_participant(1), expected_admission_epoch=1)
    with pytest.raises(BudgetConfigurationError, match="session code"):
        control.resolve_recovery("invalid", expected_control_epoch=1)
    with pytest.raises(BudgetConfigurationError, match="control epoch"):
        control.resolve_recovery(_session(1), expected_control_epoch=False)
    with pytest.raises(BudgetConfigurationError, match="not recoverable"):
        control.resolve_recovery(_session(1), expected_control_epoch=1)


@pytest.mark.parametrize("fault", ["boot", "clock", "metadata"])
def test_public_reconcile_commits_runtime_source_faults(
    tmp_path: Path,
    fault: str,
) -> None:
    host = HostClock()
    control, ledger = _bootstrap(tmp_path, host)
    if fault == "boot":
        host.boot = "not-a-uuid"
        message = "boot identity"
    elif fault == "clock":
        host.now = float("nan")
        message = "boottime clock"
    else:
        with sqlite3.connect(ledger) as db:
            db.execute("UPDATE metadata SET value = 'invalid' WHERE key = 'last_boottime'")
            db.commit()
        message = "high-water"

    with pytest.raises(BudgetConfigurationError, match=message):
        control.reconcile()
    snapshot = control.snapshot()
    assert snapshot["supervisor_fault"] is True
    assert snapshot["state"] == "paused"


@pytest.mark.asyncio
async def test_public_constructor_and_transport_boundaries_fail_closed(
    tmp_path: Path,
) -> None:
    host = HostClock()
    feedback_clock = FeedbackClock()
    control, ledger, store, governor = _bound_runtime(tmp_path, host, feedback_clock)

    class CustomTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, _request: httpx.Request) -> httpx.Response:
            raise AssertionError("invalid transport must not be delegated")

    try:
        with pytest.raises(BudgetConfigurationError, match="exact control plane"):
            A2RetentionSupervisor(object(), store)  # type: ignore[arg-type]
        with pytest.raises(BudgetConfigurationError, match="exact feedback store"):
            A2RetentionSupervisor(control, object())  # type: ignore[arg-type]
        with pytest.raises(BudgetConfigurationError, match="owner secret"):
            A2RetentionSupervisor(control, store, owner_secret=b"short")
        with pytest.raises(BudgetConfigurationError, match="exact feedback store"):
            control.bind_feedback_store(object(), expected_control_epoch=2)  # type: ignore[arg-type]
        with pytest.raises(BudgetConfigurationError, match="session identity"):
            A2SQLiteBudgetGovernor(ledger, object())  # type: ignore[arg-type]
        with pytest.raises(BudgetConfigurationError, match="zero-retry production transport"):
            GovernedAsyncTransport(governor, CustomTransport())

        assert governor.scope == "single_host_shared_sqlite_a2"
        assert governor.owner_digest == hashlib.sha256(_SESSION_SECRET).hexdigest()
        transport = GovernedAsyncTransport(
            governor,
            httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        )
        await transport.aclose()
        await transport.aclose()
        with pytest.raises(BudgetConfigurationError, match="transport is closed"):
            await transport.handle_async_request(httpx.Request("GET", "https://offline.invalid"))
    finally:
        await governor.aclose()
        store.close()
