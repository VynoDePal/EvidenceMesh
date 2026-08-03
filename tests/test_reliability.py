from __future__ import annotations

import asyncio

import pytest

from evidencemesh.errors import ProviderCircuitOpenError
from evidencemesh.reliability import ProviderCircuitBreaker


@pytest.mark.asyncio
async def test_circuit_opens_then_allows_one_recovery_probe() -> None:
    now = [100.0]
    breaker = ProviderCircuitBreaker(2, 10.0, clock=lambda: now[0])

    first = await breaker.acquire("stub")
    await breaker.record_failure(first)
    assert breaker.snapshot("stub")["status"] == "closed"

    second = await breaker.acquire("stub")
    await breaker.record_failure(second)
    assert breaker.snapshot("stub")["status"] == "open"
    with pytest.raises(ProviderCircuitOpenError, match="recovery probe in 10s"):
        await breaker.acquire("stub")

    now[0] += 10.0
    probe = await breaker.acquire("stub")
    assert probe.probe is True
    with pytest.raises(ProviderCircuitOpenError, match="already in progress"):
        await breaker.acquire("stub")

    await breaker.record_success(probe)
    assert breaker.snapshot("stub") == {
        "status": "closed",
        "consecutive_failures": 0,
        "failure_threshold": 2,
        "recovery_seconds": 10.0,
        "retry_after_seconds": 0.0,
        "probe_in_flight": False,
    }


@pytest.mark.asyncio
async def test_failed_probe_reopens_and_cancelled_probe_is_released() -> None:
    now = [10.0]
    breaker = ProviderCircuitBreaker(1, 5.0, clock=lambda: now[0])

    permit = await breaker.acquire("stub")
    await breaker.record_failure(permit)
    now[0] += 5.0
    probe = await breaker.acquire("stub")
    await breaker.release(probe)
    replacement_probe = await breaker.acquire("stub")
    await breaker.record_failure(replacement_probe)
    assert breaker.snapshot("stub")["status"] == "open"
    assert breaker.snapshot("stub")["consecutive_failures"] == 2


@pytest.mark.asyncio
async def test_circuit_state_is_independent_per_provider() -> None:
    breaker = ProviderCircuitBreaker(1, 60.0)
    failed = await breaker.acquire("failed")
    await breaker.record_failure(failed)
    healthy = await breaker.acquire("healthy")
    await breaker.record_success(healthy)

    assert breaker.snapshot("failed")["status"] == "open"
    assert breaker.snapshot("healthy")["status"] == "closed"


def test_circuit_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        ProviderCircuitBreaker(0, 1.0)
    with pytest.raises(ValueError, match="positive"):
        ProviderCircuitBreaker(1, 0.0)


@pytest.mark.asyncio
async def test_release_is_a_noop_for_regular_permit() -> None:
    breaker = ProviderCircuitBreaker(2, 10.0)
    permit = await breaker.acquire("stub")
    await breaker.release(permit)
    await asyncio.sleep(0)
    assert breaker.snapshot("stub")["status"] == "closed"
