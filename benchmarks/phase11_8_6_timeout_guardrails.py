"""Offline timeout taxonomy and decision boundaries for Phase 11.8.6.

The module classifies already-raised timeout exceptions. It creates no HTTP
client, opens no socket, reads no environment variable and performs no I/O.
Diagnostics deliberately omit exception messages, request URLs, headers and
provider content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class TimeoutPolicyError(ValueError):
    """The timeout policy cannot preserve a precise fail-closed diagnosis."""


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    """Transport and outer-wall deadlines for one future benchmark request."""

    connect_seconds: float = 20.0
    read_seconds: float = 30.0
    write_seconds: float = 20.0
    pool_seconds: float = 20.0
    wall_seconds: float = 45.0

    def __post_init__(self) -> None:
        values = (
            self.connect_seconds,
            self.read_seconds,
            self.write_seconds,
            self.pool_seconds,
            self.wall_seconds,
        )
        if any(value <= 0 for value in values):
            raise TimeoutPolicyError("all timeout values must be positive")
        if self.wall_seconds <= max(values[:-1]):
            raise TimeoutPolicyError("wall timeout must exceed every HTTPX transport timeout")

    def public_summary(self) -> dict[str, float]:
        return {
            "connect_seconds": self.connect_seconds,
            "read_seconds": self.read_seconds,
            "write_seconds": self.write_seconds,
            "pool_seconds": self.pool_seconds,
            "wall_seconds": self.wall_seconds,
        }


@dataclass(frozen=True, slots=True)
class TimeoutDiagnostic:
    """Bounded timeout telemetry safe for a public benchmark artifact."""

    error_kind: str
    layer: str
    provider_response_observed: bool = False
    retry_allowed_in_scored_run: bool = False
    raw_exception_retained: bool = False
    request_url_retained: bool = False

    def public_summary(self) -> dict[str, str | bool]:
        return {
            "error_kind": self.error_kind,
            "layer": self.layer,
            "provider_response_observed": self.provider_response_observed,
            "retry_allowed_in_scored_run": self.retry_allowed_in_scored_run,
            "raw_exception_retained": self.raw_exception_retained,
            "request_url_retained": self.request_url_retained,
        }


HTTPX_TIMEOUT_TAXONOMY: tuple[tuple[type[httpx.TimeoutException], str, str], ...] = (
    (httpx.ConnectTimeout, "connect_timeout", "transport_connect"),
    (httpx.ReadTimeout, "read_timeout", "transport_read"),
    (httpx.WriteTimeout, "write_timeout", "transport_write"),
    (httpx.PoolTimeout, "pool_timeout", "connection_pool"),
)


def classify_timeout_exception(error: BaseException) -> TimeoutDiagnostic:
    """Classify a raised timeout without retaining attacker-controlled text."""

    for error_type, error_kind, layer in HTTPX_TIMEOUT_TAXONOMY:
        if isinstance(error, error_type):
            return TimeoutDiagnostic(error_kind=error_kind, layer=layer)
    if isinstance(error, httpx.TimeoutException):
        return TimeoutDiagnostic(
            error_kind="httpx_timeout_unknown",
            layer="transport_unknown",
        )
    if isinstance(error, TimeoutError):
        return TimeoutDiagnostic(
            error_kind="generation_wall_timeout",
            layer="benchmark_wall",
        )
    raise TypeError("error is not a supported timeout exception")


def diagnose_legacy_timeout(
    outcome: dict[str, Any],
    *,
    policy: TimeoutPolicy,
) -> dict[str, Any]:
    """Diagnose the historical coarse timeout without retroactive relabeling."""

    if outcome.get("error_kind") != "request_timeout":
        raise ValueError("historical outcome is not the locked request timeout")
    if outcome.get("native_http_200") is not False or outcome.get("http_status") is not None:
        raise ValueError("historical timeout unexpectedly contains an HTTP response")
    latency_ms = outcome.get("latency_ms")
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)):
        raise ValueError("historical timeout latency is invalid")
    if latency_ms < 0:
        raise ValueError("historical timeout latency must be non-negative")

    compatible_with_read_deadline = abs(float(latency_ms) / 1_000 - policy.read_seconds) <= 0.25
    return {
        "historical_error_kind": "request_timeout",
        "diagnosis": "legacy_request_timeout_unresolved",
        "precise_timeout_kind": None,
        "retroactive_reclassification_allowed": False,
        "provider_response_observed": False,
        "http_status_observed": False,
        "latency_ms": float(latency_ms),
        "compatible_with_locked_read_deadline": compatible_with_read_deadline,
        "read_timeout_proven": False,
        "excluded_interpretations": [
            "http_429",
            "native_schema_failure",
            "semantic_failure",
        ],
    }


def decision_boundaries(*, offline_guardrails_passed: bool) -> dict[str, Any]:
    """Separate model-smoke evidence from product and release governance."""

    return {
        "offline_timeout_guardrails_passed": offline_guardrails_passed,
        "historical_phase11_8_5_result_changed": False,
        "phase11_8_5_live_smoke_passed": False,
        "benchmark_model_availability_validated": False,
        "future_live_run_authorized": False,
        "product_release_blocked_by_phase11_8_5_timeout_alone": False,
        "product_release_decision_uses_broader_quality_evidence": True,
        "users_choose_provider_model_and_credentials": True,
        "product_model_defaults_changed": False,
        "unchanged_phase11_8_3_rerun_authorized": False,
        "phase11_9_protocol_may_be_frozen": False,
        "phase11_9_executed": False,
        "phase12_authorized": False,
        "phase12_executed": False,
        "merge_allowed": False,
        "release_allowed": False,
        "superiority_claim_allowed": False,
        "release_decision": "no-go",
        "next_step": (
            "Review a separately pre-registered future availability protocol; "
            "do not rerun Phase 11.8.5."
            if offline_guardrails_passed
            else "Repair the offline timeout guardrails before considering live work."
        ),
    }
