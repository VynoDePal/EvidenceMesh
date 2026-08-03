from __future__ import annotations

import asyncio
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from evidencemesh.governor import (
    BudgetConfigurationError,
    BudgetExceededError,
    ClosedAlphaPolicy,
    ClosedAlphaSession,
    DispatchIntent,
    SQLiteBudgetGovernor,
)


@dataclass
class FakeClock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _participant(index: int) -> str:
    return f"p-{index:016x}"


def _session(index: int) -> str:
    return f"s-{index:032x}"


def _context(index: int, *, participant: int = 1, profile: str = "community") -> ClosedAlphaSession:
    return ClosedAlphaSession(
        participant_code=_participant(participant),
        session_code=_session(index),
        profile=profile,
    )


def _provider(provider: str = "wikipedia") -> DispatchIntent:
    return DispatchIntent(kind="provider", provider=provider)


@pytest.fixture(autouse=True)
def _deny_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("RC3 governor tests must never access a real network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    yield


@pytest.mark.asyncio
async def test_six_attempt_session_cap_is_atomic_and_rejected_batch_spends_nothing(
    tmp_path: Path,
) -> None:
    governor = SQLiteBudgetGovernor(
        tmp_path / "ledger.sqlite3",
        _context(1),
        clock=FakeClock(),
    )
    try:
        with pytest.raises(BudgetExceededError):
            await governor.reserve_batch([_provider() for _ in range(7)])

        permits = await governor.reserve_batch([_provider() for _ in range(6)])
        assert len(permits) == 6

        with pytest.raises(BudgetExceededError):
            await governor.reserve_batch([_provider()])
    finally:
        await governor.aclose()


@pytest.mark.asyncio
async def test_global_cap_is_atomic_across_two_governors(tmp_path: Path) -> None:
    policy = ClosedAlphaPolicy(
        provider_attempts_per_session_max=3,
        provider_attempts_total_max=3,
        tavily_attempts_quality_session_max=3,
        tavily_attempts_total_max=3,
        request_starts_per_minute_max=10,
        concurrent_sessions_max=2,
    )
    clock = FakeClock()
    ledger = tmp_path / "ledger.sqlite3"
    first = SQLiteBudgetGovernor(ledger, _context(1), policy=policy, clock=clock)
    second = SQLiteBudgetGovernor(ledger, _context(2, participant=2), policy=policy, clock=clock)
    try:
        outcomes = await asyncio.gather(
            first.reserve_batch([_provider(), _provider()]),
            second.reserve_batch([_provider(), _provider()]),
            return_exceptions=True,
        )
        accepted = [result for result in outcomes if not isinstance(result, BaseException)]
        rejected = [result for result in outcomes if isinstance(result, BaseException)]

        assert len(accepted) == 1
        assert len(accepted[0]) == 2
        assert len(rejected) == 1
        assert isinstance(rejected[0], BudgetExceededError)

        remaining_governor = first if accepted[0] == outcomes[0] else second
        final = await remaining_governor.reserve_batch([_provider()])
        assert len(final) == 1
        with pytest.raises(BudgetExceededError):
            await remaining_governor.reserve_batch([_provider()])
    finally:
        await first.aclose()
        await second.aclose()


@pytest.mark.asyncio
async def test_tavily_community_zero_and_quality_caps_are_atomic(tmp_path: Path) -> None:
    clock = FakeClock()

    community = SQLiteBudgetGovernor(
        tmp_path / "community.sqlite3",
        _context(1),
        clock=clock,
    )
    try:
        with pytest.raises(BudgetExceededError):
            await community.reserve_batch([_provider("tavily")])
        assert len(await community.reserve_batch([_provider() for _ in range(6)])) == 6
    finally:
        await community.aclose()

    quality = SQLiteBudgetGovernor(
        tmp_path / "quality.sqlite3",
        _context(2, profile="quality"),
        clock=clock,
    )
    try:
        with pytest.raises(BudgetExceededError):
            await quality.reserve_batch([_provider("tavily") for _ in range(5)])
        assert len(await quality.reserve_batch([_provider("tavily") for _ in range(4)])) == 4
        with pytest.raises(BudgetExceededError):
            await quality.reserve_batch([_provider("tavily")])
    finally:
        await quality.aclose()


@pytest.mark.asyncio
async def test_tavily_global_cap_persists_across_quality_sessions(tmp_path: Path) -> None:
    clock = FakeClock()
    ledger = tmp_path / "ledger.sqlite3"

    for participant in range(1, 3):
        for participant_session in range(5):
            index = (participant - 1) * 5 + participant_session + 1
            governor = SQLiteBudgetGovernor(
                ledger,
                _context(index, participant=participant, profile="quality"),
                clock=clock,
            )
            try:
                assert (
                    len(await governor.reserve_batch([_provider("tavily") for _ in range(4)])) == 4
                )
            finally:
                await governor.aclose()
            clock.advance(60.0)

    over_budget = SQLiteBudgetGovernor(
        ledger,
        _context(11, participant=3, profile="quality"),
        clock=clock,
    )
    try:
        with pytest.raises(BudgetExceededError):
            await over_budget.reserve_batch([_provider("tavily")])
    finally:
        await over_budget.aclose()


@pytest.mark.asyncio
async def test_rolling_ten_per_minute_boundary_uses_injected_clock(tmp_path: Path) -> None:
    clock = FakeClock()
    ledger = tmp_path / "ledger.sqlite3"
    first = SQLiteBudgetGovernor(ledger, _context(1), clock=clock)
    second = SQLiteBudgetGovernor(ledger, _context(2, participant=2), clock=clock)
    try:
        assert len(await first.reserve_batch([_provider() for _ in range(5)])) == 5
        assert len(await second.reserve_batch([_provider() for _ in range(5)])) == 5

        clock.advance(59.999)
        with pytest.raises(BudgetExceededError) as too_early:
            await first.reserve_batch([_provider()])
        assert any(
            marker in str(too_early.value).lower()
            for marker in ("rate", "minute", "rolling", "request-start")
        )

        clock.advance(0.001)
        assert len(await first.reserve_batch([_provider()])) == 1
    finally:
        await first.aclose()
        await second.aclose()


@pytest.mark.asyncio
async def test_delayed_permits_cannot_exceed_ten_governed_request_starts_per_minute(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    clock = FakeClock()
    ledger = tmp_path / "ledger.sqlite3"
    first = SQLiteBudgetGovernor(ledger, _context(1), clock=clock)
    second = SQLiteBudgetGovernor(ledger, _context(2, participant=2), clock=clock)
    first_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    second_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    first.attach_client(first_client)
    second.attach_client(second_client)
    try:
        first_permits = await first.reserve_batch([_provider() for _ in range(6)])
        second_permits = await second.reserve_batch([_provider() for _ in range(4)])
        clock.advance(61.0)
        denied_permits = await second.reserve_batch([_provider() for _ in range(2)])

        for permit in first_permits:
            with first.capture(permit):
                await first_client.get("https://offline.invalid/first")
        for permit in second_permits:
            with second.capture(permit):
                await second_client.get("https://offline.invalid/second")
        for permit in denied_permits:
            with pytest.raises(BudgetExceededError), second.capture(permit):
                await second_client.get("https://offline.invalid/rate-denied")

        assert calls == 10
        with pytest.raises(BudgetExceededError), second.capture(denied_permits[0]):
            await second_client.get("https://offline.invalid/replay")
        assert calls == 10
        snapshot = await first.snapshot()
        assert snapshot["global_attempts"] == 12
        assert snapshot["dispatched_attempts"] == 10
    finally:
        await first.aclose()
        await second.aclose()
        await first_client.aclose()
        await second_client.aclose()


@pytest.mark.asyncio
async def test_only_two_sessions_can_be_active_and_close_releases_one_slot(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    ledger = tmp_path / "ledger.sqlite3"
    governors = [
        SQLiteBudgetGovernor(
            ledger,
            _context(index, participant=index),
            clock=clock,
        )
        for index in range(1, 4)
    ]
    first, second, third = governors
    try:
        assert len(await first.reserve_batch([_provider()])) == 1
        assert len(await second.reserve_batch([_provider()])) == 1
        with pytest.raises(BudgetExceededError):
            await third.reserve_batch([_provider()])

        await first.aclose()
        assert not first.enabled
        assert len(await third.reserve_batch([_provider()])) == 1
    finally:
        for governor in governors:
            if governor.enabled:
                await governor.aclose()


@pytest.mark.asyncio
async def test_httpx_hook_requires_one_fresh_permit_and_never_reaches_transport_after_refusal(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    governor = SQLiteBudgetGovernor(
        tmp_path / "ledger.sqlite3",
        _context(1),
        clock=FakeClock(),
    )
    governor.attach_client(client)
    try:
        permit = (await governor.reserve_batch([_provider()]))[0]
        with governor.capture(permit):
            response = await client.get("https://offline.invalid/allowed")
            assert response.status_code == 200
            with pytest.raises((BudgetExceededError, BudgetConfigurationError)):
                await client.get("https://offline.invalid/reused")
        assert calls == 1

        with (
            pytest.raises((BudgetExceededError, BudgetConfigurationError)),
            governor.capture(permit),
        ):
            await client.get("https://offline.invalid/replayed")
        assert calls == 1

        with pytest.raises((BudgetExceededError, BudgetConfigurationError)):
            await client.get("https://offline.invalid/no-permit")
        assert calls == 1
    finally:
        await governor.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_transport_error_consumes_permit_and_cannot_be_retried_for_free(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline synthetic failure", request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    governor = SQLiteBudgetGovernor(
        tmp_path / "ledger.sqlite3",
        _context(1),
        clock=FakeClock(),
    )
    governor.attach_client(client)
    try:
        permit = (await governor.reserve_batch([_provider()]))[0]
        with pytest.raises(httpx.ConnectError), governor.capture(permit):
            await client.get("https://offline.invalid/fails")
        assert calls == 1

        with (
            pytest.raises((BudgetExceededError, BudgetConfigurationError)),
            governor.capture(permit),
        ):
            await client.get("https://offline.invalid/retry")
        assert calls == 1
    finally:
        await governor.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_cache_and_unknown_dispatch_kinds_fail_closed(tmp_path: Path) -> None:
    governor = SQLiteBudgetGovernor(
        tmp_path / "ledger.sqlite3",
        _context(1),
        clock=FakeClock(),
    )
    try:
        for values in (
            {"kind": "cache"},
            {"kind": "retry", "provider": "wikipedia"},
            {"kind": "fallback", "provider": "wikipedia"},
        ):
            with pytest.raises(BudgetConfigurationError):
                intent = DispatchIntent(**values)
                await governor.reserve_batch([intent])

        with pytest.raises(BudgetConfigurationError):
            await governor.reserve_batch([])
        assert len(await governor.reserve_batch([_provider() for _ in range(6)])) == 6
    finally:
        await governor.aclose()


@pytest.mark.asyncio
async def test_private_regular_sqlite_ledger_is_required(tmp_path: Path) -> None:
    public_directory = tmp_path / "public"
    public_directory.mkdir(mode=0o755)
    public_directory.chmod(0o755)
    with pytest.raises(BudgetConfigurationError):
        SQLiteBudgetGovernor(
            public_directory / "ledger.sqlite3",
            _context(1),
            clock=FakeClock(),
        )

    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"not a database")
    target.chmod(0o600)
    link = tmp_path / "ledger-link.sqlite3"
    link.symlink_to(target)
    with pytest.raises(BudgetConfigurationError):
        SQLiteBudgetGovernor(link, _context(2), clock=FakeClock())

    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"this is not sqlite")
    corrupt.chmod(0o600)
    with pytest.raises(BudgetConfigurationError):
        SQLiteBudgetGovernor(corrupt, _context(3), clock=FakeClock())


@pytest.mark.asyncio
async def test_closed_governor_remains_fail_closed_for_reservation_and_http(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor = SQLiteBudgetGovernor(
        tmp_path / "ledger.sqlite3",
        _context(1),
        clock=FakeClock(),
    )
    governor.attach_client(client)
    await governor.aclose()
    assert not governor.enabled

    with pytest.raises(BudgetConfigurationError):
        await governor.reserve_batch([_provider()])
    with pytest.raises((BudgetExceededError, BudgetConfigurationError)):
        await client.get("https://offline.invalid/closed")
    assert calls == 0
    await client.aclose()


@pytest.mark.asyncio
async def test_permit_captured_before_close_cannot_dispatch_after_close(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor = SQLiteBudgetGovernor(
        tmp_path / "ledger.sqlite3",
        _context(1),
        clock=FakeClock(),
    )
    governor.attach_client(client)
    permit = (await governor.reserve_batch([_provider()]))[0]

    with governor.capture(permit):
        await governor.aclose()
        with pytest.raises(BudgetConfigurationError):
            await client.get("https://offline.invalid/closed-capture")
    assert calls == 0
    await client.aclose()


@pytest.mark.asyncio
async def test_ledger_permission_drift_poison_cannot_be_repaired_and_replayed(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    ledger = tmp_path / "ledger.sqlite3"
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor = SQLiteBudgetGovernor(ledger, _context(1), clock=FakeClock())
    governor.attach_client(client)
    permit = (await governor.reserve_batch([_provider()]))[0]

    ledger.chmod(0o644)
    with pytest.raises(BudgetConfigurationError), governor.capture(permit):
        await client.get("https://offline.invalid/drift")
    assert calls == 0

    ledger.chmod(0o600)
    with pytest.raises(BudgetConfigurationError), governor.capture(permit):
        await client.get("https://offline.invalid/repaired")
    assert calls == 0

    await governor.aclose()
    await client.aclose()


@pytest.mark.asyncio
async def test_clock_regression_poison_cannot_be_repaired(tmp_path: Path) -> None:
    clock = FakeClock(now=10.0)
    governor = SQLiteBudgetGovernor(
        tmp_path / "ledger.sqlite3",
        _context(1),
        clock=clock,
    )
    await governor.reserve_batch([_provider()])

    clock.now = 9.0
    with pytest.raises(BudgetConfigurationError, match="backwards"):
        await governor.reserve_batch([_provider()])

    clock.now = 11.0
    with pytest.raises(BudgetConfigurationError, match="fail-closed"):
        await governor.reserve_batch([_provider()])
    await governor.aclose()
