from __future__ import annotations

import asyncio
import multiprocessing
import socket
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError
from evidencemesh.governor import (
    AlphaControlState,
    ClosedAlphaAdmission,
    ClosedAlphaSession,
    DispatchIntent,
    SQLiteAlphaControlPlane,
    SQLiteBudgetGovernor,
)


@dataclass
class FakeClock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class _SharedSignallingClock:
    value: Any
    called: Any

    def __call__(self) -> float:
        self.called.set()
        return float(self.value.value)


class _BeginSignallingGovernor(SQLiteBudgetGovernor):
    def __init__(
        self,
        ledger_path: Path,
        session: ClosedAlphaSession,
        *,
        clock: Callable[[], float],
        begin_attempted: Any,
    ) -> None:
        self._begin_attempted = begin_attempted
        super().__init__(ledger_path, session, clock=clock, _require_rc4=True)

    def _connect(self) -> sqlite3.Connection:
        connection = super()._connect()
        connection.set_trace_callback(self._trace_statement)
        return connection

    def _trace_statement(self, statement: str) -> None:
        if statement == "BEGIN IMMEDIATE":
            self._begin_attempted.set()


class _BeginSignallingControlPlane(SQLiteAlphaControlPlane):
    def __init__(
        self,
        ledger_path: Path,
        *,
        clock: Callable[[], float],
        begin_attempted: Any,
    ) -> None:
        self._begin_attempted = begin_attempted
        super().__init__(ledger_path, clock=clock)

    def _connect(self) -> sqlite3.Connection:
        connection = super()._connect()
        connection.set_trace_callback(self._trace_statement)
        return connection

    def _trace_statement(self, statement: str) -> None:
        if statement == "BEGIN IMMEDIATE":
            self._begin_attempted.set()


def _reserve_in_process(
    ledger: str,
    ready: Any,
    start: Any,
    begin_attempted: Any,
    clock_called: Any,
    clock_value: Any,
    result: Any,
) -> None:
    try:
        governor = _BeginSignallingGovernor(
            Path(ledger),
            ClosedAlphaSession(_participant(1), _session(1), "community"),
            clock=_SharedSignallingClock(clock_value, clock_called),
            begin_attempted=begin_attempted,
        )
    except Exception as exc:
        result.put(f"setup:{type(exc).__name__}:{exc}")
        ready.set()
        return
    ready.set()
    if not start.wait(5.0):
        result.put("start-timeout")
        return
    try:
        asyncio.run(governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))
    except Exception as exc:
        result.put(f"reserve:{type(exc).__name__}:{exc}")
    else:
        result.put("ok")


def _transition_in_process(
    ledger: str,
    ready: Any,
    start: Any,
    begin_attempted: Any,
    clock_called: Any,
    clock_value: Any,
    result: Any,
) -> None:
    try:
        control = _BeginSignallingControlPlane(
            Path(ledger),
            clock=_SharedSignallingClock(clock_value, clock_called),
            begin_attempted=begin_attempted,
        )
    except Exception as exc:
        result.put(f"setup:{type(exc).__name__}:{exc}")
        ready.set()
        return
    ready.set()
    if not start.wait(5.0):
        result.put("start-timeout")
        return
    try:
        control.transition("paused", expected_state="prepared", expected_epoch=2)
    except Exception as exc:
        result.put(f"transition:{type(exc).__name__}:{exc}")
    else:
        result.put("ok")


@pytest.fixture(autouse=True)
def _deny_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("RC4 control-plane tests must never access a real network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    yield


def _participant(index: int) -> str:
    return f"p-{index:016x}"


def _session(index: int) -> str:
    return f"s-{index:032x}"


def _admit_full_cohort(control: SQLiteAlphaControlPlane) -> None:
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


def _prepared_control(
    tmp_path: Path,
    clock: FakeClock,
    *,
    lease_seconds: float = 300.0,
) -> tuple[SQLiteAlphaControlPlane, Path, int]:
    ledger = tmp_path / "private" / "control.sqlite3"
    control = SQLiteAlphaControlPlane.bootstrap(
        ledger,
        clock=clock,
        lease_seconds=lease_seconds,
    )
    _admit_full_cohort(control)
    epoch = control.transition(
        AlphaControlState.PREPARED,
        expected_state=AlphaControlState.PAUSED,
        expected_epoch=1,
    )
    return control, ledger, epoch


def _governor(
    ledger: Path,
    clock: FakeClock,
    *,
    participant: int = 1,
    session: int = 1,
    profile: str = "community",
) -> SQLiteBudgetGovernor:
    return SQLiteBudgetGovernor(
        ledger,
        ClosedAlphaSession(
            participant_code=_participant(participant),
            session_code=_session(session),
            profile=profile,
        ),
        clock=clock,
        _require_rc4=True,
    )


def test_bootstrap_is_paused_with_exact_frozen_slots_and_requires_full_cohort(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    ledger = tmp_path / "private" / "control.sqlite3"
    control = SQLiteAlphaControlPlane.bootstrap(ledger, clock=clock)

    snapshot = control.snapshot()
    assert snapshot["state"] == "paused"
    assert snapshot["control_epoch"] == 1
    assert snapshot["admitted_participants"] == 0
    with sqlite3.connect(ledger) as connection:
        assert connection.execute(
            "SELECT slot_id, profile FROM cohort_slots ORDER BY slot_id"
        ).fetchall() == [
            *((f"C{index:02d}", "community") for index in range(1, 7)),
            *((f"Q{index:02d}", "quality") for index in range(1, 3)),
        ]

    with pytest.raises(BudgetConfigurationError, match="incomplete"):
        control.transition(
            "prepared",
            expected_state="paused",
            expected_epoch=1,
        )

    _admit_full_cohort(control)
    assert (
        control.transition(
            "prepared",
            expected_state="paused",
            expected_epoch=1,
        )
        == 2
    )


def test_admission_refuses_wrong_slot_profile_consent_and_attestations() -> None:
    with pytest.raises(BudgetConfigurationError, match="slot or profile"):
        ClosedAlphaAdmission(
            participant_code=_participant(1),
            slot_id="C01",
            profile="quality",
            consent_version="closed-alpha-a0-consent-v1",
            consent_accepted=True,
            input_authority_attested=True,
            non_sensitive_use_attested=True,
        )
    with pytest.raises(BudgetConfigurationError, match="consent"):
        ClosedAlphaAdmission(
            participant_code=_participant(1),
            slot_id="C01",
            profile="community",
            consent_version="other",
            consent_accepted=True,
            input_authority_attested=True,
            non_sensitive_use_attested=True,
        )
    with pytest.raises(BudgetConfigurationError, match="attestations"):
        ClosedAlphaAdmission(
            participant_code=_participant(1),
            slot_id="C01",
            profile="community",
            consent_version="closed-alpha-a0-consent-v1",
            consent_accepted=True,
            input_authority_attested=False,
            non_sensitive_use_attested=True,
        )


@pytest.mark.asyncio
async def test_from_env_requires_rc4_marker_and_prebootstrapped_admitted_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _control, ledger, _epoch = _prepared_control(tmp_path, clock)
    values = {
        "EVIDENCEMESH_CLOSED_ALPHA_LEDGER": str(ledger),
        "EVIDENCEMESH_CLOSED_ALPHA_PARTICIPANT": _participant(1),
        "EVIDENCEMESH_CLOSED_ALPHA_SESSION": _session(1),
        "EVIDENCEMESH_CLOSED_ALPHA_PROFILE": "community",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(BudgetConfigurationError, match="incomplete"):
        SQLiteBudgetGovernor.from_env()

    monkeypatch.setenv("EVIDENCEMESH_CLOSED_ALPHA_CONTROL_PLANE", "rc4")
    governor = SQLiteBudgetGovernor.from_env()
    assert governor is not None
    assert governor.scope == "single_host_shared_sqlite"
    await governor.aclose()

    monkeypatch.setenv(
        "EVIDENCEMESH_CLOSED_ALPHA_LEDGER",
        str(tmp_path / "private" / "replacement.sqlite3"),
    )
    with pytest.raises(BudgetConfigurationError, match="bootstrapped"):
        SQLiteBudgetGovernor.from_env()


@pytest.mark.asyncio
async def test_pause_invalidates_reserved_epoch_and_stop_is_terminal(tmp_path: Path) -> None:
    clock = FakeClock()
    control, ledger, epoch = _prepared_control(tmp_path, clock)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    governor = _governor(ledger, clock)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor.attach_client(client)
    try:
        stale = (await governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
        epoch = control.transition(
            "paused",
            expected_state="prepared",
            expected_epoch=epoch,
        )
        with pytest.raises(BudgetExceededError), governor.capture(stale):
            await client.get("https://offline.invalid/stale")
        assert calls == 0

        epoch = control.transition(
            "prepared",
            expected_state="paused",
            expected_epoch=epoch,
        )
        fresh = (await governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
        with governor.capture(fresh):
            assert (await client.get("https://offline.invalid/fresh")).status_code == 200
        with pytest.raises(BudgetExceededError), governor.capture(fresh):
            await client.get("https://offline.invalid/replay")
        assert calls == 1

        epoch = control.transition(
            "stopped",
            expected_state="prepared",
            expected_epoch=epoch,
        )
        with pytest.raises(BudgetExceededError, match="stopped"):
            await governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
        with pytest.raises(BudgetConfigurationError, match="forbidden"):
            control.transition(
                "paused",
                expected_state="stopped",
                expected_epoch=epoch,
            )
    finally:
        await governor.aclose()
        await client.aclose()


def test_rc4_provider_bundles_are_exact_and_never_include_ddgs(tmp_path: Path) -> None:
    clock = FakeClock()
    _control, ledger, _epoch = _prepared_control(tmp_path, clock)
    community = _governor(ledger, clock)
    community.validate_provider_configuration(
        ("arxiv", "crossref", "github", "searxng", "wikipedia"),
        (),
        deployment_profile="community",
    )
    for invalid in (
        ("wikipedia",),
        ("searxng", "ddgs", "wikipedia", "crossref", "arxiv", "github"),
        ("searxng", "wikipedia", "crossref", "arxiv", "github", "tavily"),
    ):
        with pytest.raises(BudgetConfigurationError):
            community.validate_provider_configuration(
                invalid,
                (),
                deployment_profile="community",
            )

    quality = _governor(ledger, clock, participant=7, session=7, profile="quality")
    quality.validate_provider_configuration(
        ("arxiv", "crossref", "github", "searxng", "tavily", "wikipedia"),
        (),
        deployment_profile="quality",
    )


@pytest.mark.asyncio
async def test_withdrawal_pauses_and_preserves_spent_budget(tmp_path: Path) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    permit = (await governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
    assert control.report_allowed(_participant(1), _session(1)) is True
    assert control.withdrawal_committed(_participant(1)) is False

    assert control.withdraw(_participant(1), expected_admission_epoch=1) == 2
    snapshot = control.snapshot()
    assert snapshot["state"] == "paused"
    assert snapshot["global_attempts"] == 1
    assert control.report_allowed(_participant(1), _session(1)) is False
    assert control.withdrawal_committed(_participant(1)) is True
    with pytest.raises(BudgetExceededError), governor.capture(permit):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
        governor.attach_client(client)
        try:
            await client.get("https://offline.invalid/withdrawn")
        finally:
            await client.aclose()
    await governor.aclose()


@pytest.mark.asyncio
async def test_crash_recovery_closes_without_deleting_or_refunding(tmp_path: Path) -> None:
    clock = FakeClock()
    control, ledger, prepared_epoch = _prepared_control(
        tmp_path,
        clock,
        lease_seconds=2.0,
    )
    governor = _governor(ledger, clock)
    await governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
    before = control.snapshot()
    assert before["sessions"] == 1
    assert before["global_attempts"] == 1

    clock.advance(2.0)
    assert control.reconcile_expired_sessions() == 1
    quarantined = control.snapshot()
    assert quarantined["state"] == "paused"
    assert quarantined["control_epoch"] == prepared_epoch + 1
    assert quarantined["recovery_required_sessions"] == 1
    assert quarantined["sessions"] == 1
    assert quarantined["global_attempts"] == 1

    control.resolve_recovery(
        _session(1),
        expected_control_epoch=prepared_epoch + 1,
    )
    recovered = control.snapshot()
    assert recovered["recovery_required_sessions"] == 0
    assert recovered["sessions"] == 1
    assert recovered["global_attempts"] == 1
    with sqlite3.connect(ledger) as connection:
        assert connection.execute("SELECT status FROM sessions").fetchone()[0] == "closed"
        assert connection.execute("SELECT outcome FROM attempts").fetchone()[0] == (
            "denied_recovery"
        )


@pytest.mark.asyncio
async def test_direct_rc4_dispatch_rejects_unadmitted_providers_before_write_or_transport(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor.attach_client(client)
    try:
        for provider in ("ddgs", "not-a-provider"):
            with pytest.raises(BudgetConfigurationError, match="outside the admitted bundle"):
                await governor.reserve_batch([DispatchIntent("provider", provider)])
        assert control.snapshot()["global_attempts"] == 0

        valid = (await governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
        forged = replace(valid, provider="ddgs")
        with (
            pytest.raises(BudgetConfigurationError, match="outside the admitted bundle"),
            governor.capture(forged),
        ):
            await client.get("https://offline.invalid/forged")
        assert calls == 0
        with sqlite3.connect(ledger) as connection:
            assert connection.execute(
                "SELECT dispatched, outcome FROM attempts WHERE token = ?",
                (valid.token,),
            ).fetchone() == (0, "reserved")
    finally:
        await governor.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_any_expired_session_pauses_before_another_session_transport(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    control, ledger, prepared_epoch = _prepared_control(
        tmp_path,
        clock,
        lease_seconds=2.0,
    )
    expired_governor = _governor(ledger, clock, participant=1, session=1)
    fresh_governor = _governor(ledger, clock, participant=2, session=2)
    await expired_governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
    clock.advance(1.0)
    fresh = (await fresh_governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    fresh_governor.attach_client(client)
    try:
        clock.advance(1.0)
        with pytest.raises(BudgetExceededError, match="recovery"), fresh_governor.capture(fresh):
            await client.get("https://offline.invalid/fresh")
        snapshot = control.snapshot()
        assert calls == 0
        assert snapshot["state"] == "paused"
        assert snapshot["control_epoch"] == prepared_epoch + 1
        assert snapshot["recovery_required_sessions"] == 1
        assert snapshot["global_attempts"] == 2
        with sqlite3.connect(ledger) as connection:
            assert connection.execute("SELECT outcome FROM attempts ORDER BY id").fetchall() == [
                ("denied_recovery",),
                ("denied_state",),
            ]
    finally:
        await fresh_governor.aclose()
        await client.aclose()


@pytest.mark.parametrize("operation", ["governor", "control"])
def test_process_shared_clock_is_sampled_after_sqlite_write_lock(
    tmp_path: Path,
    operation: str,
) -> None:
    clock = FakeClock()
    _control, ledger, _epoch = _prepared_control(tmp_path, clock)
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    start = context.Event()
    begin_attempted = context.Event()
    clock_called = context.Event()
    clock_value = context.Value("d", 1.0)
    result = context.Queue()
    target = _reserve_in_process if operation == "governor" else _transition_in_process
    process = context.Process(
        target=target,
        args=(
            str(ledger),
            ready,
            start,
            begin_attempted,
            clock_called,
            clock_value,
            result,
        ),
    )
    process.start()
    assert ready.wait(5.0)

    with sqlite3.connect(ledger, isolation_level=None) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        try:
            start.set()
            assert begin_attempted.wait(5.0)
            assert not clock_called.is_set()
            blocker.execute(
                """
                INSERT INTO metadata(key, value) VALUES ('last_clock', '2.0')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
            clock_value.value = 3.0
        finally:
            blocker.commit()

    process.join(5.0)
    assert not process.is_alive()
    assert process.exitcode == 0
    assert clock_called.is_set()
    assert result.get(timeout=1.0) == "ok"
