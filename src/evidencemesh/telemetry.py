"""Privacy-safe provider network observability."""

from __future__ import annotations

import json
import socket
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

import httpx

from evidencemesh.errors import ProviderCircuitOpenError, ProviderError
from evidencemesh.models import ProviderNetworkTelemetry


def _elapsed_ms(started_at: float, finished_at: float) -> float:
    return round(max(0.0, finished_at - started_at) * 1_000, 3)


@dataclass(slots=True)
class ProviderCallTrace:
    """One logical provider-query call without query, URL or response data."""

    provider: str
    cache_hits: int = 0
    circuit_skips: int = 0
    adapter_invocations: int = 0
    http_attempts: int = 0
    http_responses: int = 0
    adapter_latency_ms: list[float] = field(default_factory=list)
    http_attempt_latency_ms: list[float] = field(default_factory=list)
    http_status_counts: Counter[str] = field(default_factory=Counter)
    _adapter_started_at: float | None = None
    _active_http_attempts: dict[int, float] = field(default_factory=dict)

    def begin_adapter(self, now: float) -> None:
        self.adapter_invocations += 1
        self._adapter_started_at = now

    def finish_adapter(self, now: float) -> None:
        if self._adapter_started_at is None:
            return
        self.adapter_latency_ms.append(_elapsed_ms(self._adapter_started_at, now))
        self._adapter_started_at = None

    def begin_http_attempt(self, request: httpx.Request, now: float) -> None:
        self.http_attempts += 1
        self._active_http_attempts[id(request)] = now

    def finish_http_response(self, response: httpx.Response, now: float) -> None:
        started_at = self._active_http_attempts.pop(id(response.request), None)
        if started_at is None:
            return
        self.http_responses += 1
        self.http_status_counts[str(response.status_code)] += 1
        self.http_attempt_latency_ms.append(_elapsed_ms(started_at, now))

    def finish_open_http_attempts(self, now: float) -> None:
        for started_at in self._active_http_attempts.values():
            self.http_attempt_latency_ms.append(_elapsed_ms(started_at, now))
        self._active_http_attempts.clear()


class ProviderHTTPInstrumentation:
    """Attribute shared-client HTTP dispatches to the active provider call."""

    scope = "shared_httpx_client_event_hooks"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.client = client
        self._clock = clock
        self._active_trace: ContextVar[ProviderCallTrace | None] = ContextVar(
            f"evidencemesh_provider_trace_{id(self)}",
            default=None,
        )
        self.client.event_hooks["request"].append(self._on_request)
        self.client.event_hooks["response"].append(self._on_response)
        self._attached = True

    async def _on_request(self, request: httpx.Request) -> None:
        trace = self._active_trace.get()
        if trace is not None:
            trace.begin_http_attempt(request, self._clock())

    async def _on_response(self, response: httpx.Response) -> None:
        trace = self._active_trace.get()
        if trace is not None:
            trace.finish_http_response(response, self._clock())

    @contextmanager
    def capture(self, trace: ProviderCallTrace) -> Iterator[None]:
        token = self._active_trace.set(trace)
        try:
            yield
        finally:
            trace.finish_open_http_attempts(self._clock())
            self._active_trace.reset(token)

    def detach(self) -> None:
        if not self._attached:
            return
        request_hooks = self.client.event_hooks.get("request", [])
        response_hooks = self.client.event_hooks.get("response", [])
        if self._on_request in request_hooks:
            request_hooks.remove(self._on_request)
        if self._on_response in response_hooks:
            response_hooks.remove(self._on_response)
        self._attached = False


@dataclass(frozen=True, slots=True)
class ProviderFailureClassification:
    """Sanitized failure information safe for public telemetry."""

    kind: str
    http_status: int | None = None


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return chain


def classify_provider_failure(exc: BaseException) -> ProviderFailureClassification:
    """Map an exception chain to a bounded class without retaining its message."""

    chain = _exception_chain(exc)
    if any(isinstance(item, ProviderCircuitOpenError) for item in chain):
        return ProviderFailureClassification("circuit_open")

    explicit = next(
        (
            item.kind
            for item in chain
            if isinstance(item, ProviderError) and item.kind != "provider_error"
        ),
        None,
    )
    if explicit is not None:
        return ProviderFailureClassification(explicit)

    if any(isinstance(item, socket.gaierror) for item in chain):
        return ProviderFailureClassification("dns_error")
    if any(isinstance(item, (TimeoutError, httpx.TimeoutException)) for item in chain):
        return ProviderFailureClassification("timeout")

    status_error = next(
        (item for item in chain if isinstance(item, httpx.HTTPStatusError)),
        None,
    )
    if status_error is not None:
        return ProviderFailureClassification(
            "http_status",
            http_status=status_error.response.status_code,
        )

    if any(isinstance(item, json.JSONDecodeError) for item in chain):
        return ProviderFailureClassification("invalid_json")
    if any(isinstance(item, httpx.ConnectError) for item in chain):
        return ProviderFailureClassification("connection_error")
    if any(isinstance(item, httpx.DecodingError) for item in chain):
        return ProviderFailureClassification("invalid_response_encoding")
    if any(isinstance(item, httpx.ProtocolError) for item in chain):
        return ProviderFailureClassification("protocol_error")
    if any(isinstance(item, httpx.RequestError) for item in chain):
        return ProviderFailureClassification("network_error")
    if any(isinstance(item, ValueError) for item in chain):
        return ProviderFailureClassification("invalid_response")
    if isinstance(exc, ProviderError):
        return ProviderFailureClassification(exc.kind)
    return ProviderFailureClassification(f"unexpected_{type(exc).__name__}")


def aggregate_provider_traces(
    logical_call_counts: Counter[str],
    traces: dict[str, list[ProviderCallTrace]],
) -> dict[str, ProviderNetworkTelemetry]:
    """Aggregate call traces into the public SearchMetadata shape."""

    aggregated: dict[str, ProviderNetworkTelemetry] = {}
    for provider in sorted(set(logical_call_counts) | set(traces)):
        provider_traces = traces.get(provider, [])
        status_counts: Counter[str] = Counter()
        for trace in provider_traces:
            status_counts.update(trace.http_status_counts)
        http_attempts = sum(trace.http_attempts for trace in provider_traces)
        http_responses = sum(trace.http_responses for trace in provider_traces)
        aggregated[provider] = ProviderNetworkTelemetry(
            logical_calls=logical_call_counts[provider],
            cache_hits=sum(trace.cache_hits for trace in provider_traces),
            circuit_skips=sum(trace.circuit_skips for trace in provider_traces),
            adapter_invocations=sum(trace.adapter_invocations for trace in provider_traces),
            http_attempts=http_attempts,
            http_responses=http_responses,
            http_failures_without_response=max(0, http_attempts - http_responses),
            http_status_counts=dict(sorted(status_counts.items())),
            adapter_latency_ms=[
                latency for trace in provider_traces for latency in trace.adapter_latency_ms
            ],
            http_attempt_latency_ms=[
                latency for trace in provider_traces for latency in trace.http_attempt_latency_ms
            ],
        )
    return aggregated
