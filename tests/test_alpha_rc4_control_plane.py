from __future__ import annotations

import asyncio
import multiprocessing
import os
import socket
import sqlite3
import stat
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
import pytest

import evidencemesh.governor as governor_module
from evidencemesh.config import Settings
from evidencemesh.engine import EvidenceMesh
from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError
from evidencemesh.fetcher import WebFetcher
from evidencemesh.governor import (
    AlphaControlState,
    ClosedAlphaAdmission,
    ClosedAlphaPolicy,
    ClosedAlphaSession,
    DispatchIntent,
    SQLiteAlphaControlPlane,
    SQLiteBudgetGovernor,
)
from evidencemesh.providers import build_providers
from evidencemesh.providers.wikipedia import WikipediaProvider


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


class _NoWaitPrivacyFaultControl(SQLiteAlphaControlPlane):
    def _connect(self) -> sqlite3.Connection:
        connection = super()._connect()
        connection.execute("PRAGMA busy_timeout = 0")
        return connection


class _EqualityForgedSession:
    participant_code = "p-0000000000000001"
    session_code = "s-00000000000000000000000000000001"
    profile = "community"

    def __init__(self) -> None:
        self.comparisons = 0

    def __eq__(self, _other: object) -> bool:
        self.comparisons += 1
        return True

    def __ne__(self, _other: object) -> bool:
        self.comparisons += 1
        return False


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
async def test_rc4_session_identity_is_exact_and_immutable_but_legacy_is_unchanged(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    forged: Any = _EqualityForgedSession()
    with pytest.raises(BudgetConfigurationError, match="exact immutable session"):
        SQLiteBudgetGovernor(ledger, forged, clock=clock, _require_rc4=True)
    assert forged.comparisons == 0

    governor = _governor(ledger, clock)
    quality_session = ClosedAlphaSession(_participant(7), _session(7), "quality")
    with pytest.raises(BudgetConfigurationError, match="session identity is immutable"):
        governor.session = quality_session
    assert governor.session.profile == "community"
    with pytest.raises(BudgetConfigurationError, match="outside the admitted bundle"):
        await governor.reserve_batch([DispatchIntent("provider", "tavily") for _ in range(4)])
    assert control.snapshot()["global_attempts"] == 0
    await governor.aclose()

    legacy = SQLiteBudgetGovernor(
        ledger.parent / "legacy-duck-session.sqlite3",
        forged,
        clock=clock,
    )
    assert legacy.session is forged
    legacy.session = quality_session
    assert legacy.session is quality_session
    await legacy.aclose()


@pytest.mark.asyncio
async def test_rc4_policy_is_exact_and_immutable_and_cannot_expand_ledger_limits(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    relaxed = replace(governor.policy, provider_attempts_per_session_max=7)

    with pytest.raises(BudgetConfigurationError, match="policy is immutable"):
        governor.policy = relaxed
    with pytest.raises(BudgetConfigurationError, match="policy is immutable"):
        control.policy = relaxed
    with pytest.raises(BudgetExceededError, match="session dispatch budget exhausted"):
        await governor.reserve_batch([DispatchIntent("provider", "wikipedia") for _ in range(7)])
    assert governor.policy.provider_attempts_per_session_max == 6
    assert control.policy.provider_attempts_per_session_max == 6
    assert control.snapshot()["global_attempts"] == 0
    await governor.aclose()

    legacy = SQLiteBudgetGovernor(
        ledger.parent / "legacy-mutable-policy.sqlite3",
        ClosedAlphaSession(_participant(1), _session(1), "community"),
        clock=clock,
    )
    duck_policy: Any = object()
    legacy.policy = duck_policy
    assert legacy.policy is duck_policy
    legacy.policy = relaxed
    assert legacy.policy is relaxed
    await legacy.aclose()

    falsey_policy: Any = []
    falsey_legacy = SQLiteBudgetGovernor(
        ledger.parent / "legacy-falsey-policy.sqlite3",
        ClosedAlphaSession(_participant(1), _session(2), "community"),
        falsey_policy,
        clock=clock,
    )
    assert type(falsey_legacy.policy) is ClosedAlphaPolicy
    await falsey_legacy.aclose()


def test_rc4_rejects_policy_subclasses_even_when_metadata_is_spoofed(tmp_path: Path) -> None:
    default = ClosedAlphaPolicy()

    class ForgedPolicy(ClosedAlphaPolicy):
        @property
        def canonical_json(self) -> str:
            return default.canonical_json

        @property
        def fingerprint(self) -> str:
            return default.fingerprint

    forged = ForgedPolicy(provider_attempts_per_session_max=7)
    forged_ledger = tmp_path / "forged-policy" / "control.sqlite3"
    with pytest.raises(BudgetConfigurationError, match="exact frozen policy type"):
        SQLiteAlphaControlPlane.bootstrap(forged_ledger, forged)
    assert not forged_ledger.exists()

    clock = FakeClock()
    _control, ledger, _epoch = _prepared_control(tmp_path, clock)
    with pytest.raises(BudgetConfigurationError, match="exact frozen policy type"):
        SQLiteBudgetGovernor(
            ledger,
            ClosedAlphaSession(_participant(1), _session(1), "community"),
            forged,
            clock=clock,
            _require_rc4=True,
        )


def test_rc4_rejects_integer_subclass_limits_before_ledger_creation(tmp_path: Path) -> None:
    class ComparisonForgedInt(int):
        def __lt__(self, _other: object) -> bool:
            return False

    forged_limit = ComparisonForgedInt(6)
    assert not forged_limit < 7
    forged_ledger = tmp_path / "forged-limit" / "control.sqlite3"

    with pytest.raises(BudgetConfigurationError, match="exact integer limits"):
        forged_policy = ClosedAlphaPolicy(
            provider_attempts_per_session_max=forged_limit,
        )
        SQLiteAlphaControlPlane.bootstrap(forged_ledger, forged_policy)
    assert not forged_ledger.exists()


@pytest.mark.asyncio
async def test_engine_requires_exact_explicit_rc4_environment_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _control, ledger, _epoch = _prepared_control(tmp_path, clock)
    rc4_governor = _governor(ledger, clock)
    values = {
        "EVIDENCEMESH_CLOSED_ALPHA_LEDGER": str(ledger),
        "EVIDENCEMESH_CLOSED_ALPHA_PARTICIPANT": _participant(1),
        "EVIDENCEMESH_CLOSED_ALPHA_SESSION": _session(1),
        "EVIDENCEMESH_CLOSED_ALPHA_PROFILE": "community",
        "EVIDENCEMESH_CLOSED_ALPHA_CONTROL_PLANE": "rc4",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    settings = Settings(
        enabled_providers=["arxiv", "crossref", "github", "searxng", "wikipedia"],
        cache_path=tmp_path / "cache.sqlite3",
    )

    for name, mismatch in (
        ("EVIDENCEMESH_CLOSED_ALPHA_LEDGER", str(tmp_path / "other.sqlite3")),
        ("EVIDENCEMESH_CLOSED_ALPHA_SESSION", _session(2)),
        ("EVIDENCEMESH_CLOSED_ALPHA_PROFILE", "quality"),
    ):
        with monkeypatch.context() as patch:
            patch.setenv(name, mismatch)
            with pytest.raises(BudgetConfigurationError, match="exactly match"):
                EvidenceMesh(settings, governor=rc4_governor)

    forged: Any = _EqualityForgedSession()
    with pytest.raises(BudgetConfigurationError, match="session identity is immutable"):
        rc4_governor.session = forged
    assert forged.comparisons == 0
    assert rc4_governor.session == ClosedAlphaSession(
        _participant(1),
        _session(1),
        "community",
    )

    class ExplicitGovernorSubclass(SQLiteBudgetGovernor):
        pass

    subclass = ExplicitGovernorSubclass(
        ledger,
        ClosedAlphaSession(_participant(1), _session(1), "community"),
        clock=clock,
        _require_rc4=True,
    )
    with pytest.raises(BudgetConfigurationError, match="exactly match"):
        EvidenceMesh(settings, governor=subclass)
    await subclass.aclose()

    legacy = SQLiteBudgetGovernor(
        ledger.parent / "legacy.sqlite3",
        ClosedAlphaSession(_participant(1), _session(1), "community"),
        clock=clock,
    )
    with monkeypatch.context() as patch:
        patch.setenv("EVIDENCEMESH_CLOSED_ALPHA_LEDGER", str(legacy.ledger_path))
        with pytest.raises(BudgetConfigurationError, match="exactly match"):
            EvidenceMesh(settings, governor=legacy)

    # Explicit legacy governors retain their existing behavior when RC4 is not requested.
    for name in values:
        monkeypatch.delenv(name)
    legacy_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        trust_env=False,
    )
    legacy_engine = EvidenceMesh(
        settings,
        providers=[],
        client=legacy_client,
        governor=legacy,
    )
    assert legacy_engine.governor is legacy
    await legacy_engine.aclose()
    await legacy_client.aclose()

    for name, value in values.items():
        monkeypatch.setenv(name, value)
    rc4_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        trust_env=False,
    )
    rc4_engine = EvidenceMesh(settings, client=rc4_client, governor=rc4_governor)
    assert rc4_engine.governor is rc4_governor
    await rc4_engine.aclose()
    await rc4_client.aclose()


@pytest.mark.asyncio
async def test_engine_rejects_rc4_fetcher_override_before_transport_or_ledger_write(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    settings = Settings(enabled_providers=[], cache_path=tmp_path / "fetcher-cache.sqlite3")
    transport_calls = 0
    override_calls = 0

    def rogue_handler(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(200, request=request)

    rogue_client = httpx.AsyncClient(
        transport=httpx.MockTransport(rogue_handler),
        trust_env=False,
    )

    class BypassFetcher(WebFetcher):
        async def fetch(self, url: str, *, max_chars: int = 30_000) -> Any:
            nonlocal override_calls
            override_calls += 1
            return await rogue_client.get(url)

    governed_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        trust_env=False,
    )
    engine_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        trust_env=False,
    )
    bypass_fetcher = BypassFetcher(settings, client=governed_client, governor=governor)
    try:
        with pytest.raises(BudgetConfigurationError, match="built-in WebFetcher"):
            EvidenceMesh(
                settings,
                providers=[],
                client=engine_client,
                fetcher=bypass_fetcher,
                governor=governor,
            )
        assert override_calls == 0
        assert transport_calls == 0
        assert control.snapshot()["global_attempts"] == 0
    finally:
        await bypass_fetcher.aclose()
        await governor.aclose()
        await engine_client.aclose()
        await governed_client.aclose()
        await rogue_client.aclose()


@pytest.mark.asyncio
async def test_legacy_fetcher_subclass_remains_supported_without_rc4(tmp_path: Path) -> None:
    clock = FakeClock()
    settings = Settings(enabled_providers=[], cache_path=tmp_path / "legacy-cache.sqlite3")
    governor = SQLiteBudgetGovernor(
        tmp_path / "private" / "legacy-fetcher.sqlite3",
        ClosedAlphaSession(_participant(1), _session(1), "community"),
        clock=clock,
    )

    class LegacyFetcher(WebFetcher):
        pass

    fetcher_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        trust_env=False,
    )
    engine_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        trust_env=False,
    )
    fetcher = LegacyFetcher(settings, client=fetcher_client, governor=governor)
    engine = EvidenceMesh(
        settings,
        providers=[],
        client=engine_client,
        fetcher=fetcher,
        governor=governor,
    )
    try:
        assert engine.fetcher is fetcher
    finally:
        await engine.aclose()
        await fetcher_client.aclose()
        await engine_client.aclose()


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


@pytest.mark.asyncio
async def test_privacy_fault_marker_survives_sqlite_failure_and_blocks_new_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    control, ledger, prepared_epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    permit = (await governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    def fail_sqlite_write(
        _cls: type[SQLiteAlphaControlPlane],
        _connection: sqlite3.Connection,
        _now: float,
    ) -> None:
        raise sqlite3.OperationalError("synthetic write failure after marker")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor.attach_client(client)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                SQLiteAlphaControlPlane,
                "_set_privacy_fault_locked",
                classmethod(fail_sqlite_write),
            )
            with pytest.raises(sqlite3.OperationalError, match="after marker"):
                control.record_privacy_fault()

        marker = ledger.with_name(f"{ledger.name}.privacy-fault")
        marker_metadata = marker.lstat()
        assert stat.S_ISREG(marker_metadata.st_mode)
        assert stat.S_IMODE(marker_metadata.st_mode) == 0o600
        assert marker_metadata.st_uid == os.geteuid()
        assert marker_metadata.st_nlink == 1
        assert marker.read_bytes() == b"evidencemesh.closed-alpha-privacy-fault.v1\n"
        with sqlite3.connect(ledger) as connection:
            assert connection.execute(
                "SELECT state, privacy_fault FROM control_state WHERE singleton = 1"
            ).fetchone() == ("prepared", 0)

        # Snapshot remains available and derives the effective fault from the marker.
        assert control.snapshot()["privacy_fault"] is True
        reopened = SQLiteAlphaControlPlane(ledger, clock=clock)
        second_governor = _governor(ledger, clock, participant=2, session=2)
        try:
            with pytest.raises(BudgetExceededError, match="privacy fault"):
                await second_governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
            with (
                pytest.raises(BudgetExceededError, match="privacy fault"),
                governor.capture(permit),
            ):
                await client.get("https://offline.invalid/marker-fault")
            paused_epoch = reopened.transition(
                "paused",
                expected_state="prepared",
                expected_epoch=prepared_epoch,
            )
            with pytest.raises(BudgetConfigurationError, match="privacy fault"):
                reopened.transition(
                    "prepared",
                    expected_state="paused",
                    expected_epoch=paused_epoch,
                )
            assert calls == 0
        finally:
            await second_governor.aclose()
    finally:
        await governor.aclose()
        await client.aclose()


@pytest.mark.parametrize("fault_operation", ["record", "advance_feedback_clock"])
@pytest.mark.asyncio
async def test_privacy_fault_marker_precedes_clock_validation_and_blocks_other_instance(
    tmp_path: Path,
    fault_operation: str,
) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    permit = (await governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
    with sqlite3.connect(ledger) as connection:
        connection.execute("UPDATE metadata SET value = '1.0' WHERE key = 'last_clock'")
        connection.commit()

    if fault_operation == "record":
        with pytest.raises(BudgetConfigurationError, match="clock moved backwards"):
            control.record_privacy_fault()
    else:
        with pytest.raises(BudgetConfigurationError, match="clock moved backwards"):
            control.advance_feedback_clock(100.0)

    marker = ledger.with_name(f"{ledger.name}.privacy-fault")
    assert marker.read_bytes() == b"evidencemesh.closed-alpha-privacy-fault.v1\n"
    assert control.snapshot()["privacy_fault"] is True
    second_governor = _governor(ledger, clock, participant=2, session=2)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor.attach_client(client)
    try:
        with pytest.raises(BudgetExceededError, match="privacy fault"):
            await second_governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
        with pytest.raises(BudgetExceededError, match="privacy fault"), governor.capture(permit):
            await client.get("https://offline.invalid/clock-fault")
        assert calls == 0
    finally:
        clock.now = 2.0
        await second_governor.aclose()
        await governor.aclose()
        await client.aclose()


@pytest.mark.parametrize("fault_operation", ["record", "advance_feedback_clock"])
@pytest.mark.asyncio
async def test_privacy_fault_marker_survives_begin_immediate_lock_failure(
    tmp_path: Path,
    fault_operation: str,
) -> None:
    clock = FakeClock()
    _control, ledger, _epoch = _prepared_control(tmp_path, clock)
    fault_control = _NoWaitPrivacyFaultControl(ledger, clock=clock)
    marker = ledger.with_name(f"{ledger.name}.privacy-fault")

    with sqlite3.connect(ledger, isolation_level=None) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                if fault_operation == "record":
                    fault_control.record_privacy_fault()
                else:
                    fault_control.advance_feedback_clock(100.0)
            assert marker.read_bytes() == b"evidencemesh.closed-alpha-privacy-fault.v1\n"
        finally:
            blocker.rollback()

    second_governor = _governor(ledger, clock, participant=2, session=2)
    try:
        with pytest.raises(BudgetExceededError, match="privacy fault"):
            await second_governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
        assert fault_control.snapshot()["privacy_fault"] is True
    finally:
        await second_governor.aclose()


@pytest.mark.parametrize("marker_shape", ["symlink", "hardlink", "mode", "content"])
@pytest.mark.asyncio
async def test_unsafe_privacy_fault_marker_fails_closed_but_snapshot_is_inspectable(
    tmp_path: Path,
    marker_shape: str,
) -> None:
    clock = FakeClock()
    control, ledger, prepared_epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    permit = (await governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
    paused_epoch = control.transition(
        "paused",
        expected_state="prepared",
        expected_epoch=prepared_epoch,
    )
    marker = ledger.with_name(f"{ledger.name}.privacy-fault")
    marker_content = b"evidencemesh.closed-alpha-privacy-fault.v1\n"
    if marker_shape == "symlink":
        marker.symlink_to(ledger.name)
    elif marker_shape == "hardlink":
        source = ledger.with_name("privacy-fault-source")
        source.write_bytes(marker_content)
        source.chmod(0o600)
        os.link(source, marker)
    else:
        marker.write_bytes(marker_content if marker_shape == "mode" else b"corrupt\n")
        marker.chmod(0o640 if marker_shape == "mode" else 0o600)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor.attach_client(client)
    reserve_governor = _governor(ledger, clock, participant=2, session=2)
    try:
        assert control.snapshot()["privacy_fault"] is True
        with pytest.raises(BudgetConfigurationError, match="privacy-fault marker"):
            control.transition(
                "prepared",
                expected_state="paused",
                expected_epoch=paused_epoch,
            )
        with (
            pytest.raises(BudgetConfigurationError, match="privacy-fault marker"),
            governor.capture(permit),
        ):
            await client.get("https://offline.invalid/unsafe-marker")
        with pytest.raises(BudgetConfigurationError, match="privacy-fault marker"):
            await reserve_governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
        assert calls == 0
    finally:
        await reserve_governor.aclose()
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
async def test_rc4_provider_identity_uses_exact_class_objects_not_spoofable_metadata(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    transport_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    try:
        genuine = WikipediaProvider(
            "https://{language}.wikipedia.invalid/w/api.php",
            client,
        )
        assert governor.validate_provider(genuine, client) == "wikipedia"

        class WikipediaSubclass(WikipediaProvider):
            pass

        subclass = WikipediaSubclass(
            "https://{language}.wikipedia.invalid/w/api.php",
            client,
        )
        with pytest.raises(BudgetConfigurationError, match="only audited"):
            governor.validate_provider(subclass, client)

        class EqualitySpoofedName:
            def __init__(self) -> None:
                self.comparisons = 0

            def __eq__(self, _other: object) -> bool:
                self.comparisons += 1
                return True

            def __ne__(self, _other: object) -> bool:
                self.comparisons += 1
                return False

        spoofed_name = EqualitySpoofedName()
        genuine.name = spoofed_name
        with pytest.raises(BudgetConfigurationError, match="only audited"):
            governor.validate_provider(genuine, client)
        assert spoofed_name.comparisons == 0
        del genuine.name

        identities = (
            ("evidencemesh.providers.arxiv", "ArxivProvider", "arxiv"),
            ("evidencemesh.providers.crossref", "CrossrefProvider", "crossref"),
            ("evidencemesh.providers.github", "GitHubProvider", "github"),
            ("evidencemesh.providers.searxng", "SearxngProvider", "searxng"),
            ("evidencemesh.providers.tavily", "TavilyProvider", "tavily"),
            ("evidencemesh.providers.wikipedia", "WikipediaProvider", "wikipedia"),
        )
        for module_name, class_name, provider_name in identities:
            forged_type = type(
                class_name,
                (),
                {"__module__": module_name, "name": provider_name},
            )
            forged: Any = forged_type()
            forged.client = client
            governor._AUDITED_PROVIDER_TYPES = ((forged_type, provider_name),)
            governor._AUDITED_PROVIDERS = {f"{module_name}.{class_name}": provider_name}
            with pytest.raises(BudgetConfigurationError, match="only audited"):
                governor.validate_provider(forged, client)

        assert transport_calls == 0
        assert control.snapshot()["global_attempts"] == 0
    finally:
        await governor.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_legacy_provider_metadata_identity_behavior_is_unchanged(tmp_path: Path) -> None:
    clock = FakeClock()
    legacy = SQLiteBudgetGovernor(
        tmp_path / "legacy-provider.sqlite3",
        ClosedAlphaSession(_participant(1), _session(1), "community"),
        clock=clock,
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        trust_env=False,
    )
    forged_type = type(
        "WikipediaProvider",
        (),
        {"__module__": "evidencemesh.providers.wikipedia", "name": "wikipedia"},
    )
    forged: Any = forged_type()
    forged.client = client
    try:
        assert legacy.validate_provider(forged, client) == "wikipedia"

        shadowed_type = type(
            "ShadowProvider",
            (),
            {"__module__": "legacy.shadowed", "name": "custom"},
        )
        shadowed: Any = shadowed_type()
        shadowed.client = client
        legacy._AUDITED_PROVIDERS = {"legacy.shadowed.ShadowProvider": "custom"}
        legacy.validate_provider_configuration(("custom",), ())
        assert legacy.validate_provider(shadowed, client) == "custom"
    finally:
        await legacy.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_engine_rejects_provider_class_spoof_before_attach_or_ledger_write(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    transport_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    forged_type = type(
        "WikipediaProvider",
        (),
        {"__module__": "evidencemesh.providers.wikipedia", "name": "wikipedia"},
    )
    forged: Any = forged_type()
    forged.client = client
    settings = Settings(
        enabled_providers=["arxiv", "crossref", "github", "searxng", "wikipedia"],
        cache_path=tmp_path / "spoof-cache.sqlite3",
    )
    providers, warnings = build_providers(settings, client)
    assert warnings == []
    assert tuple(provider.name for provider in providers) == (
        "arxiv",
        "crossref",
        "github",
        "searxng",
        "wikipedia",
    )
    providers[-1] = forged
    try:
        with pytest.raises(BudgetConfigurationError, match="only audited"):
            EvidenceMesh(
                settings,
                providers=providers,
                client=client,
                governor=governor,
            )
        assert client.event_hooks["request"] == []
        assert transport_calls == 0
        assert control.snapshot()["global_attempts"] == 0
    finally:
        await governor.aclose()
        await client.aclose()


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


@pytest.mark.parametrize("operation", ["feedback_context", "report_allowed"])
def test_feedback_admission_rechecks_marker_at_transactional_return_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    clock = FakeClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    asyncio.run(governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))
    asyncio.run(governor.aclose())

    final_check_entered = threading.Event()
    marker_created = threading.Event()
    release_final_check = threading.Event()
    original_marker_check = governor_module._private_privacy_fault_marker_present
    reader_checks = 0

    def synchronized_marker_check(path: Path) -> bool:
        nonlocal reader_checks
        if threading.current_thread().name == "feedback-reader":
            reader_checks += 1
            if reader_checks == 2:
                final_check_entered.set()
                if not release_final_check.wait(5.0):
                    raise AssertionError("fault marker synchronization timed out")
        present = original_marker_check(path)
        if threading.current_thread().name == "fault-writer" and present:
            marker_created.set()
        return present

    monkeypatch.setattr(
        governor_module,
        "_private_privacy_fault_marker_present",
        synchronized_marker_check,
    )
    result: list[object] = []
    failures: list[BaseException] = []

    def read_admission() -> None:
        try:
            if operation == "feedback_context":
                result.append(control.feedback_context(_participant(1), _session(1)))
            else:
                result.append(control.report_allowed(_participant(1), _session(1)))
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    fault_failures: list[BaseException] = []

    def record_fault() -> None:
        try:
            control.record_privacy_fault()
        except BaseException as exc:  # pragma: no cover - asserted below
            fault_failures.append(exc)

    reader = threading.Thread(target=read_admission, name="feedback-reader")
    reader.start()
    assert final_check_entered.wait(5.0)
    fault_writer = threading.Thread(target=record_fault, name="fault-writer")
    fault_writer.start()
    assert marker_created.wait(5.0)
    release_final_check.set()
    reader.join(5.0)
    fault_writer.join(5.0)
    assert not reader.is_alive()
    assert not fault_writer.is_alive()
    assert failures == []
    assert fault_failures == []
    assert result == [None if operation == "feedback_context" else False]


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
