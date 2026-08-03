"""Offline quota, 429 and structured-output guardrails for Phase 11.8.4.

This module is standard-library-only. It constructs requests and simulates
schedules, but it performs no network or filesystem I/O.
"""

from __future__ import annotations

import asyncio
import copy
import math
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

WINDOW_SECONDS = 60.0
DEFAULT_SAFETY_NUMERATOR = 4
DEFAULT_SAFETY_DENOMINATOR = 5
DEFAULT_BYTES_PER_ESTIMATED_TOKEN = 3
DEFAULT_REQUEST_TOKEN_OVERHEAD = 64
MAX_RETRY_AFTER_SECONDS = 86_400.0


class QuotaConfigurationError(ValueError):
    """The supplied quota policy cannot safely schedule a request."""


class DailyQuotaUnavailableError(RuntimeError):
    """The configured daily safety budget cannot accept another request."""


class ReservationTooEarlyError(RuntimeError):
    """A caller attempted to reserve before the safe start time."""

    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("quota reservation attempted before its safe start time")
        self.retry_after_seconds = retry_after_seconds


class BenchmarkQuotaContaminationError(RuntimeError):
    """A scientific benchmark received a 429 and must stop unscored."""

    def __init__(self, telemetry: dict[str, Any]) -> None:
        super().__init__(f"benchmark quota contamination: {telemetry['quota_dimension']}")
        self.telemetry = telemetry


@dataclass(frozen=True, slots=True)
class QuotaCeiling:
    """Active provider ceilings for one model in one Gemini project."""

    rpm: int
    tpm: int
    rpd: int

    def __post_init__(self) -> None:
        if self.rpm <= 0 or self.tpm <= 0 or self.rpd <= 0:
            raise QuotaConfigurationError("rpm, tpm and rpd must all be positive")


@dataclass(frozen=True, slots=True)
class QuotaPolicy:
    """A model-specific ceiling with an explicit integer safety margin."""

    model: str
    ceiling: QuotaCeiling
    safety_numerator: int = DEFAULT_SAFETY_NUMERATOR
    safety_denominator: int = DEFAULT_SAFETY_DENOMINATOR

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise QuotaConfigurationError("model must be non-empty")
        if (
            self.safety_numerator <= 0
            or self.safety_denominator <= 0
            or self.safety_numerator > self.safety_denominator
        ):
            raise QuotaConfigurationError(
                "safety margin must be a positive fraction no larger than one"
            )

    def _effective(self, value: int) -> int:
        return max(1, value * self.safety_numerator // self.safety_denominator)

    @property
    def effective_rpm(self) -> int:
        return self._effective(self.ceiling.rpm)

    @property
    def effective_tpm(self) -> int:
        return self._effective(self.ceiling.tpm)

    @property
    def effective_rpd(self) -> int:
        return self._effective(self.ceiling.rpd)

    def public_summary(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "observed_ceiling": {
                "rpm": self.ceiling.rpm,
                "tpm": self.ceiling.tpm,
                "rpd": self.ceiling.rpd,
            },
            "safety_fraction": {
                "numerator": self.safety_numerator,
                "denominator": self.safety_denominator,
            },
            "effective_budget": {
                "rpm": self.effective_rpm,
                "tpm": self.effective_tpm,
                "rpd": self.effective_rpd,
            },
        }


# These are the active project ceilings observed in AI Studio on 2026-07-30.
# They are calibration inputs, not universal defaults. Future runs must review
# and explicitly override them when the project's active limits differ.
OBSERVED_PROJECT_POLICIES: Mapping[str, QuotaPolicy] = {
    "gemini-3.5-flash-lite": QuotaPolicy(
        model="gemini-3.5-flash-lite",
        ceiling=QuotaCeiling(rpm=15, tpm=250_000, rpd=500),
    ),
    "gemma-4-26b-a4b-it": QuotaPolicy(
        model="gemma-4-26b-a4b-it",
        ceiling=QuotaCeiling(rpm=30, tpm=16_000, rpd=14_400),
    ),
    "gemma-4-31b-it": QuotaPolicy(
        model="gemma-4-31b-it",
        ceiling=QuotaCeiling(rpm=30, tpm=16_000, rpd=14_400),
    ),
}


def estimate_input_tokens(
    texts: Sequence[str],
    *,
    bytes_per_token: int = DEFAULT_BYTES_PER_ESTIMATED_TOKEN,
    fixed_overhead: int = DEFAULT_REQUEST_TOKEN_OVERHEAD,
) -> int:
    """Return a conservative tokenizer-free estimate for pre-request pacing."""

    if bytes_per_token <= 0 or fixed_overhead < 0:
        raise QuotaConfigurationError(
            "bytes_per_token must be positive and fixed_overhead non-negative"
        )
    if any(not isinstance(text, str) for text in texts):
        raise TypeError("all prompt parts must be strings")
    encoded_bytes = sum(len(text.encode("utf-8")) for text in texts)
    return fixed_overhead + math.ceil(encoded_bytes / bytes_per_token)


@dataclass(frozen=True, slots=True)
class QuotaReservation:
    started_at: float
    estimated_input_tokens: int


class ModelQuotaGovernor:
    """Sequential, smoothed RPM/TPM/RPD governor for one model bucket."""

    def __init__(
        self,
        policy: QuotaPolicy,
        *,
        daily_requests_already_used: int = 0,
    ) -> None:
        if daily_requests_already_used < 0:
            raise QuotaConfigurationError("daily_requests_already_used must be non-negative")
        if daily_requests_already_used > policy.effective_rpd:
            raise DailyQuotaUnavailableError("daily safety budget is already exhausted")
        self.policy = policy
        self.daily_requests = daily_requests_already_used
        self._reservations: list[QuotaReservation] = []

    @property
    def reservations(self) -> tuple[QuotaReservation, ...]:
        return tuple(self._reservations)

    def _validate_request(self, estimated_input_tokens: int) -> None:
        if estimated_input_tokens <= 0:
            raise QuotaConfigurationError("estimated_input_tokens must be positive")
        if estimated_input_tokens > self.policy.effective_tpm:
            raise QuotaConfigurationError(
                "one request exceeds the effective per-minute token budget"
            )
        if self.daily_requests >= self.policy.effective_rpd:
            raise DailyQuotaUnavailableError("daily safety budget is exhausted")

    def _smoothed_interval(self, estimated_input_tokens: int) -> float:
        rpm_interval = WINDOW_SECONDS / self.policy.effective_rpm
        tpm_interval = WINDOW_SECONDS * estimated_input_tokens / self.policy.effective_tpm
        return max(rpm_interval, tpm_interval)

    def next_delay(self, now: float, estimated_input_tokens: int) -> float:
        """Return the safe delay before the next sequential request start."""

        self._validate_request(estimated_input_tokens)
        candidate = float(now)
        if self._reservations:
            candidate = max(
                candidate,
                self._reservations[-1].started_at + self._smoothed_interval(estimated_input_tokens),
            )

        for _iteration in range(len(self._reservations) + 2):
            active = [
                reservation
                for reservation in self._reservations
                if reservation.started_at > candidate - WINDOW_SECONDS
            ]
            request_ok = len(active) < self.policy.effective_rpm
            token_ok = (
                sum(item.estimated_input_tokens for item in active) + estimated_input_tokens
                <= self.policy.effective_tpm
            )
            if request_ok and token_ok:
                return max(0.0, candidate - now)
            if not active:
                raise AssertionError("quota scheduler could not advance")
            candidate = min(item.started_at + WINDOW_SECONDS for item in active)
        raise AssertionError("quota scheduler did not converge")

    def reserve(self, now: float, estimated_input_tokens: int) -> QuotaReservation:
        delay = self.next_delay(now, estimated_input_tokens)
        if delay > 1e-9:
            raise ReservationTooEarlyError(delay)
        reservation = QuotaReservation(
            started_at=float(now),
            estimated_input_tokens=estimated_input_tokens,
        )
        self._reservations.append(reservation)
        self.daily_requests += 1
        return reservation

    def schedule(
        self,
        estimated_input_tokens: Sequence[int],
        *,
        start_at: float = 0.0,
    ) -> tuple[QuotaReservation, ...]:
        """Deterministically simulate a sequential plan without sleeping."""

        now = float(start_at)
        scheduled: list[QuotaReservation] = []
        for token_count in estimated_input_tokens:
            now += self.next_delay(now, token_count)
            scheduled.append(self.reserve(now, token_count))
        return tuple(scheduled)

    async def acquire(
        self,
        estimated_input_tokens: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> QuotaReservation:
        """Wait once for the computed delay, then reserve the request start."""

        now = clock()
        delay = self.next_delay(now, estimated_input_tokens)
        if delay > 0:
            await sleep(delay)
            now = clock()
        return self.reserve(now, estimated_input_tokens)


def audit_schedule(
    reservations: Sequence[QuotaReservation],
    policy: QuotaPolicy,
) -> dict[str, int | float | bool]:
    """Audit every rolling minute represented by the scheduled starts."""

    maximum_requests = 0
    maximum_tokens = 0
    for reservation in reservations:
        active = [
            item
            for item in reservations
            if reservation.started_at - WINDOW_SECONDS < item.started_at <= reservation.started_at
        ]
        maximum_requests = max(maximum_requests, len(active))
        maximum_tokens = max(
            maximum_tokens,
            sum(item.estimated_input_tokens for item in active),
        )
    duration = reservations[-1].started_at - reservations[0].started_at if reservations else 0.0
    return {
        "request_count": len(reservations),
        "duration_seconds": round(duration, 6),
        "maximum_rolling_requests": maximum_requests,
        "maximum_rolling_estimated_input_tokens": maximum_tokens,
        "effective_rpm": policy.effective_rpm,
        "effective_tpm": policy.effective_tpm,
        "within_rpm": maximum_requests <= policy.effective_rpm,
        "within_tpm": maximum_tokens <= policy.effective_tpm,
    }


def bounded_retry_delay(
    attempt: int,
    *,
    retry_after_seconds: float | None = None,
    base_seconds: float = 1.0,
    maximum_seconds: float = 60.0,
    positive_jitter_unit: float = 0.5,
) -> float:
    """Compute production-only positive-jitter backoff; benchmarks do not retry."""

    if attempt < 0 or base_seconds <= 0 or maximum_seconds <= 0:
        raise ValueError("attempt and retry bounds are invalid")
    if not 0.0 <= positive_jitter_unit <= 1.0:
        raise ValueError("positive_jitter_unit must be within [0, 1]")
    if retry_after_seconds is not None and retry_after_seconds < 0:
        raise ValueError("retry_after_seconds must be non-negative")
    server_floor = retry_after_seconds or 0.0
    exponential = min(maximum_seconds, base_seconds * (2**attempt))
    floor = max(server_floor, exponential)
    jittered = floor + (floor * 0.2 * positive_jitter_unit)
    client_ceiling = max(maximum_seconds, server_floor)
    return round(min(client_ceiling, jittered), 6)


def _quota_failure_strings(payload: Mapping[str, Any]) -> tuple[str, ...]:
    error = payload.get("error")
    if not isinstance(error, Mapping):
        return ()
    details = error.get("details")
    if not isinstance(details, list):
        return ()
    values: list[str] = []
    for detail in details:
        if not isinstance(detail, Mapping):
            continue
        violations = detail.get("violations")
        if not isinstance(violations, list):
            continue
        for violation in violations:
            if not isinstance(violation, Mapping):
                continue
            for key in ("quotaMetric", "quotaId"):
                value = violation.get(key)
                if isinstance(value, str):
                    values.append(value)
    return tuple(values)


def _quota_dimension(payload: Mapping[str, Any]) -> str:
    normalized = re.sub(
        r"[^a-z0-9]+",
        "",
        " ".join(_quota_failure_strings(payload)).casefold(),
    )
    if "spend" in normalized or "cost" in normalized:
        return "spend"
    if "token" in normalized and "perminute" in normalized:
        return "tpm"
    if "request" in normalized and "perday" in normalized:
        return "rpd"
    if "request" in normalized and "perminute" in normalized:
        return "rpm"
    return "unknown"


def _bounded_seconds(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
    elif isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s?\s*", value)
        if not match:
            return None
        seconds = float(match.group(1))
    else:
        return None
    if not 0.0 <= seconds <= MAX_RETRY_AFTER_SECONDS:
        return None
    return round(seconds, 6)


def _retry_after_seconds(
    payload: Mapping[str, Any],
    headers: Mapping[str, str] | None,
) -> float | None:
    candidates: list[float] = []
    if headers:
        for key, value in headers.items():
            if key.casefold() == "retry-after":
                parsed = _bounded_seconds(value)
                if parsed is not None:
                    candidates.append(parsed)
    error = payload.get("error")
    details = error.get("details") if isinstance(error, Mapping) else None
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, Mapping):
                continue
            parsed = _bounded_seconds(detail.get("retryDelay"))
            if parsed is not None:
                candidates.append(parsed)
    return max(candidates) if candidates else None


def sanitize_gemini_429(
    status_code: int,
    payload: Mapping[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Reduce a Gemini 429 response to a bounded, privacy-safe diagnostic."""

    if status_code != 429:
        raise ValueError("sanitize_gemini_429 requires HTTP 429")
    return {
        "http_status": 429,
        "error_kind": "http_429",
        "quota_dimension": _quota_dimension(payload),
        "retry_after_seconds": _retry_after_seconds(payload, headers),
    }


def abort_scored_benchmark_on_429(
    status_code: int,
    payload: Mapping[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
) -> None:
    """Abort instead of scoring a quota failure as model-quality failure."""

    if status_code == 429:
        raise BenchmarkQuotaContaminationError(
            sanitize_gemini_429(status_code, payload, headers=headers)
        )


SUPPORTED_GEMINI_SCHEMA_KEYS = frozenset(
    {
        "$anchor",
        "$defs",
        "$id",
        "$ref",
        "additionalProperties",
        "anyOf",
        "description",
        "enum",
        "format",
        "items",
        "maximum",
        "maxItems",
        "minimum",
        "minItems",
        "oneOf",
        "prefixItems",
        "properties",
        "propertyOrdering",
        "required",
        "title",
        "type",
    }
)


def validate_gemini_json_schema(schema: Mapping[str, Any]) -> None:
    """Reject schema keywords outside Gemini's documented supported subset."""

    def visit(node: Any) -> None:
        if not isinstance(node, Mapping):
            raise QuotaConfigurationError("every schema node must be an object")
        unsupported = set(node) - SUPPORTED_GEMINI_SCHEMA_KEYS
        if unsupported:
            raise QuotaConfigurationError(
                f"unsupported Gemini JSON Schema keywords: {sorted(unsupported)}"
            )
        properties = node.get("properties")
        if properties is not None:
            if not isinstance(properties, Mapping):
                raise QuotaConfigurationError("schema properties must be an object")
            for child in properties.values():
                visit(child)
        definitions = node.get("$defs")
        if definitions is not None:
            if not isinstance(definitions, Mapping):
                raise QuotaConfigurationError("schema $defs must be an object")
            for child in definitions.values():
                visit(child)
        items = node.get("items")
        if items is not None:
            visit(items)
        prefix_items = node.get("prefixItems")
        if prefix_items is not None:
            if not isinstance(prefix_items, list):
                raise QuotaConfigurationError("prefixItems must be a list")
            for child in prefix_items:
                visit(child)
        for keyword in ("anyOf", "oneOf"):
            alternatives = node.get(keyword)
            if alternatives is not None:
                if not isinstance(alternatives, list):
                    raise QuotaConfigurationError(f"{keyword} must be a list")
                for child in alternatives:
                    visit(child)

    visit(schema)


def gemini_direct_answer_schema() -> dict[str, Any]:
    """Gemini-compatible syntax schema; semantic strictness remains local."""

    return {
        "type": "object",
        "additionalProperties": False,
        "propertyOrdering": ["answer", "citation_ids"],
        "required": ["answer", "citation_ids"],
        "properties": {
            "answer": {
                "type": "string",
                "description": (
                    "Shortest exact answer supported by the supplied evidence, "
                    'or exactly "Insufficient evidence."'
                ),
            },
            "citation_ids": {
                "type": "array",
                "description": (
                    "Distinct bare identifiers copied from the allowed list; empty "
                    "only when the answer is exactly Insufficient evidence."
                ),
                "maxItems": 20,
                "items": {
                    "type": "string",
                    "description": "One allowed bare identifier such as S1.",
                },
            },
        },
    }


def build_gemini_json_generation_request(
    *,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    schema: Mapping[str, Any] | None = None,
    thinking_level: str = "high",
) -> dict[str, Any]:
    """Construct a native generateContent structured-output request body."""

    if not system_prompt or not user_prompt:
        raise ValueError("system_prompt and user_prompt must be non-empty")
    if max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be positive")
    if not thinking_level:
        raise ValueError("thinking_level must be non-empty")
    selected_schema = dict(schema or gemini_direct_answer_schema())
    validate_gemini_json_schema(selected_schema)
    return {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "thinkingConfig": {"thinkingLevel": thinking_level},
            "responseMimeType": "application/json",
            "responseJsonSchema": copy.deepcopy(selected_schema),
        },
    }
