"""Concurrency-safe provider circuit breaking."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from evidencemesh.errors import ProviderCircuitOpenError


@dataclass(frozen=True, slots=True)
class CircuitPermit:
    """Permission to execute a provider call."""

    provider: str
    probe: bool


@dataclass(slots=True)
class _CircuitState:
    consecutive_failures: int = 0
    retry_at: float | None = None
    probe_in_flight: bool = False


class ProviderCircuitBreaker:
    """Open failing provider circuits and allow one recovery probe.

    State is process-local by design. A single lock protects transitions across
    providers, but it is held only for in-memory bookkeeping and never for I/O.
    """

    def __init__(
        self,
        failure_threshold: int,
        recovery_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if recovery_seconds <= 0:
            raise ValueError("recovery_seconds must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._clock = clock
        self._states: dict[str, _CircuitState] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, provider: str) -> CircuitPermit:
        """Return a call permit or fail fast while the circuit is unavailable."""

        async with self._lock:
            state = self._states.setdefault(provider, _CircuitState())
            now = self._clock()
            if state.retry_at is None:
                return CircuitPermit(provider=provider, probe=False)
            if now < state.retry_at:
                remaining = max(1, math.ceil(state.retry_at - now))
                raise ProviderCircuitOpenError(
                    f"{provider} circuit is open; recovery probe in {remaining}s"
                )
            if state.probe_in_flight:
                raise ProviderCircuitOpenError(
                    f"{provider} circuit is half-open; recovery probe already in progress"
                )
            state.probe_in_flight = True
            return CircuitPermit(provider=provider, probe=True)

    async def record_success(self, permit: CircuitPermit) -> None:
        """Close the circuit after a successful provider response."""

        async with self._lock:
            state = self._states.setdefault(permit.provider, _CircuitState())
            state.consecutive_failures = 0
            state.retry_at = None
            state.probe_in_flight = False

    async def record_failure(self, permit: CircuitPermit) -> None:
        """Count a failed attempt and open the circuit when required."""

        async with self._lock:
            state = self._states.setdefault(permit.provider, _CircuitState())
            state.consecutive_failures += 1
            state.probe_in_flight = False
            if permit.probe or state.consecutive_failures >= self.failure_threshold:
                state.retry_at = self._clock() + self.recovery_seconds

    async def release(self, permit: CircuitPermit) -> None:
        """Release a cancelled half-open probe without treating it as a failure."""

        if not permit.probe:
            return
        async with self._lock:
            state = self._states.setdefault(permit.provider, _CircuitState())
            state.probe_in_flight = False

    def snapshot(self, provider: str) -> dict[str, Any]:
        """Return secret-free runtime state for health and benchmark reports."""

        state = self._states.get(provider, _CircuitState())
        now = self._clock()
        if state.retry_at is None:
            status = "closed"
            retry_after_seconds = 0.0
        elif state.retry_at > now:
            status = "open"
            retry_after_seconds = round(state.retry_at - now, 3)
        else:
            status = "half_open"
            retry_after_seconds = 0.0
        return {
            "status": status,
            "consecutive_failures": state.consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "recovery_seconds": self.recovery_seconds,
            "retry_after_seconds": retry_after_seconds,
            "probe_in_flight": state.probe_in_flight,
        }
