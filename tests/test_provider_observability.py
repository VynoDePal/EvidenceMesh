from __future__ import annotations

import json
import socket

import httpx
import pytest
from conftest import StaticProvider

from evidencemesh.engine import EvidenceMesh
from evidencemesh.errors import ProviderError
from evidencemesh.models import ProviderNetworkTelemetry, SearchRequest
from evidencemesh.providers.mwmbl import MwmblProvider
from evidencemesh.telemetry import classify_provider_failure

ENDPOINT = "https://mwmbl.example/api/v2/search/"


@pytest.mark.asyncio
async def test_successful_http_provider_reports_each_observability_stage(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Independent index",
                        "url": "https://result.example/page",
                        "content": "Evidence from an independent crawl.",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        engine = EvidenceMesh(
            settings,
            providers=[MwmblProvider(ENDPOINT, client)],
            client=client,
        )
        response = await engine.search(SearchRequest(query="independent search", use_cache=False))
        telemetry = response.metadata.provider_network_telemetry["mwmbl"]

        assert telemetry.logical_calls == 1
        assert telemetry.cache_hits == 0
        assert telemetry.circuit_skips == 0
        assert telemetry.adapter_invocations == 1
        assert telemetry.http_attempts == 1
        assert telemetry.http_responses == 1
        assert telemetry.http_failures_without_response == 0
        assert telemetry.http_status_counts == {"200": 1}
        assert len(telemetry.adapter_latency_ms) == 1
        assert len(telemetry.http_attempt_latency_ms) == 1
        assert response.metadata.provider_failure_kind_counts == {}
        await engine.aclose()


@pytest.mark.parametrize(
    ("response", "expected_kind", "expected_status"),
    [
        (httpx.Response(503), "http_status", {"503": 1}),
        (
            httpx.Response(200, content=b"{not-json"),
            "invalid_json",
            {"200": 1},
        ),
        (
            httpx.Response(200, json={"unexpected": []}),
            "invalid_schema",
            {"200": 1},
        ),
    ],
)
@pytest.mark.asyncio
async def test_http_status_json_and_schema_failures_are_sanitized(
    settings,
    response: httpx.Response,
    expected_kind: str,
    expected_status: dict[str, int],
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
        engine = EvidenceMesh(
            settings,
            providers=[MwmblProvider(ENDPOINT, client)],
            client=client,
        )
        result = await engine.search(
            SearchRequest(query="private query must not enter telemetry", use_cache=False)
        )
        telemetry = result.metadata.provider_network_telemetry["mwmbl"]

        assert result.metadata.provider_failure_kind_counts == {"mwmbl": {expected_kind: 1}}
        assert telemetry.http_attempts == 1
        assert telemetry.http_responses == 1
        assert telemetry.http_status_counts == expected_status
        serialized = json.dumps(telemetry.model_dump(mode="json"))
        assert "private query" not in serialized
        assert ENDPOINT not in serialized
        await engine.aclose()


@pytest.mark.asyncio
async def test_timeout_without_response_is_counted_as_one_http_failure(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("response contained a secret", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        engine = EvidenceMesh(
            settings,
            providers=[MwmblProvider(ENDPOINT, client)],
            client=client,
        )
        response = await engine.search(
            SearchRequest(query="private timeout query", use_cache=False)
        )
        telemetry = response.metadata.provider_network_telemetry["mwmbl"]

        assert response.metadata.provider_failure_kind_counts == {"mwmbl": {"timeout": 1}}
        assert telemetry.adapter_invocations == 1
        assert telemetry.http_attempts == 1
        assert telemetry.http_responses == 0
        assert telemetry.http_failures_without_response == 1
        assert telemetry.http_status_counts == {}
        assert len(telemetry.http_attempt_latency_ms) == 1
        await engine.aclose()


def test_dns_and_connection_failures_have_distinct_sanitized_classes() -> None:
    request = httpx.Request("GET", ENDPOINT)
    try:
        raise socket.gaierror(socket.EAI_NONAME, "private hostname")
    except socket.gaierror as cause:
        dns_error = httpx.ConnectError("private connection detail", request=request)
        dns_error.__cause__ = cause

    assert classify_provider_failure(dns_error).kind == "dns_error"
    assert (
        classify_provider_failure(
            httpx.ConnectError("private connection detail", request=request)
        ).kind
        == "connection_error"
    )


@pytest.mark.asyncio
async def test_circuit_skip_is_separate_from_adapter_and_http_attempts(settings) -> None:
    protected_settings = settings.model_copy(
        update={
            "provider_failure_threshold": 2,
            "provider_recovery_seconds": 300.0,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        engine = EvidenceMesh(
            protected_settings,
            providers=[MwmblProvider(ENDPOINT, client)],
            client=client,
        )
        first = await engine.search(SearchRequest(query="probe one", use_cache=False))
        second = await engine.search(SearchRequest(query="probe two", use_cache=False))
        skipped = await engine.search(SearchRequest(query="probe three", use_cache=False))

        assert first.metadata.provider_network_telemetry["mwmbl"].http_attempts == 1
        assert second.metadata.provider_network_telemetry["mwmbl"].http_attempts == 1
        skipped_telemetry = skipped.metadata.provider_network_telemetry["mwmbl"]
        assert skipped.metadata.provider_failure_kind_counts == {"mwmbl": {"circuit_open": 1}}
        assert skipped_telemetry.logical_calls == 1
        assert skipped_telemetry.circuit_skips == 1
        assert skipped_telemetry.adapter_invocations == 0
        assert skipped_telemetry.http_attempts == 0
        await engine.aclose()


@pytest.mark.asyncio
async def test_cache_hit_does_not_claim_adapter_or_network_activity(
    settings,
) -> None:
    engine = EvidenceMesh(settings, providers=[StaticProvider("cached")])
    request = SearchRequest(query="cache accounting")
    first = await engine.search(request)
    second = await engine.search(request)

    first_telemetry = first.metadata.provider_network_telemetry["cached"]
    second_telemetry = second.metadata.provider_network_telemetry["cached"]
    assert first_telemetry.adapter_invocations == 1
    assert first_telemetry.cache_hits == 0
    assert second_telemetry.cache_hits == 1
    assert second_telemetry.adapter_invocations == 0
    assert second_telemetry.http_attempts == 0
    await engine.aclose()


def test_network_telemetry_model_rejects_inconsistent_accounting() -> None:
    with pytest.raises(ValueError, match="http_responses cannot exceed"):
        ProviderNetworkTelemetry(
            logical_calls=1,
            cache_hits=0,
            circuit_skips=0,
            adapter_invocations=1,
            http_attempts=0,
            http_responses=1,
            http_failures_without_response=0,
            http_status_counts={"200": 1},
            adapter_latency_ms=[1.0],
            http_attempt_latency_ms=[],
        )


@pytest.mark.asyncio
async def test_engine_detaches_only_its_own_hooks_from_supplied_client(settings) -> None:
    observed: list[str] = []

    async def existing_hook(request: httpx.Request) -> None:
        observed.append(request.method)

    async with httpx.AsyncClient(event_hooks={"request": [existing_hook]}) as client:
        engine = EvidenceMesh(
            settings,
            providers=[StaticProvider("static")],
            client=client,
        )
        assert len(client.event_hooks["request"]) == 2
        assert len(client.event_hooks["response"]) == 1
        await engine.aclose()
        assert client.event_hooks["request"] == [existing_hook]
        assert client.event_hooks["response"] == []
        assert observed == []


def test_explicit_provider_error_kind_is_preserved() -> None:
    error = ProviderError("sanitized", kind="upstream_unavailable")
    assert classify_provider_failure(error).kind == "upstream_unavailable"
