from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from evidencemesh.closed_alpha_feedback import (
    ClosedAlphaFeedbackContract,
    ClosedAlphaFeedbackStore,
    FeedbackContext,
)
from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError
from evidencemesh.governor import (
    ClosedAlphaAdmission,
    ClosedAlphaSession,
    DispatchIntent,
    SQLiteAlphaControlPlane,
    SQLiteBudgetGovernor,
)

CANDIDATE_SHA = "c1e0be437442b0d97da26f2c9085067a8c09955e"


@dataclass
class MonotonicClock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass
class FeedbackClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def _participant(index: int) -> str:
    return f"p-{index:016x}"


def _session(index: int) -> str:
    return f"s-{index:032x}"


def _prepared_control(
    tmp_path: Path,
    clock: MonotonicClock,
) -> tuple[SQLiteAlphaControlPlane, Path, int]:
    ledger = tmp_path / "private" / "control.sqlite3"
    control = SQLiteAlphaControlPlane.bootstrap(ledger, clock=clock)
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
    for index in range(1, 3):
        control.admit(
            ClosedAlphaAdmission(
                participant_code=_participant(6 + index),
                slot_id=f"Q{index:02d}",
                profile="quality",
                consent_version="closed-alpha-a0-consent-v1",
                consent_accepted=True,
                input_authority_attested=True,
                non_sensitive_use_attested=True,
            )
        )
    epoch = control.transition("prepared", expected_state="paused", expected_epoch=1)
    return control, ledger, epoch


def _governor(ledger: Path, clock: MonotonicClock) -> SQLiteBudgetGovernor:
    return SQLiteBudgetGovernor(
        ledger,
        ClosedAlphaSession(
            participant_code=_participant(1),
            session_code=_session(1),
            profile="community",
        ),
        clock=clock,
        _require_rc4=True,
    )


def _report(collected_at: datetime) -> dict[str, object]:
    collected_on = collected_at.date()
    return {
        "schema_version": "evidencemesh.closed-alpha-a0.session.v1",
        "protocol_version": "closed-alpha-a0-v1",
        "candidate_sha": CANDIDATE_SHA,
        "participant_code": _participant(1),
        "session_code": _session(1),
        "slot_id": "C01",
        "profile": "community",
        "task": {"slot": 1, "kind": "prescribed", "category": "general_reference"},
        "retention": {
            "collected_on": collected_on.isoformat(),
            "delete_after": (collected_on + timedelta(days=14)).isoformat(),
        },
        "consent": {
            "version": "closed-alpha-a0-consent-v1",
            "confirmed": True,
            "authority_confirmed": True,
            "withdrawal_requested": False,
        },
        "outcome": {
            "status": "completed",
            "duration_seconds": 45,
            "useful": True,
            "blocking": False,
            "failure_kind": "none",
        },
        "traffic": {
            "provider_attempts": 3,
            "tavily_attempts": 0,
            "provider_errors": 0,
            "evidencemesh_model_attempts": 0,
            "automatic_retries": 0,
            "fallbacks": 0,
            "repairs": 0,
        },
        "grounding_counts": {
            "results": 10,
            "citations": 4,
            "resolvable_citations": 4,
            "supported_citations": 4,
        },
        "privacy": {
            "cache_disabled": True,
            "raw_runtime_objects_serialized": False,
            "sensitive_input_detected": False,
            "incident_detected": False,
        },
    }


@pytest.mark.asyncio
async def test_real_control_plane_binds_feedback_and_recovers_withdrawal(
    tmp_path: Path,
) -> None:
    monotonic = MonotonicClock()
    control, ledger, _epoch = _prepared_control(tmp_path, monotonic)
    governor = _governor(ledger, monotonic)
    await governor.reserve_batch(
        [
            DispatchIntent("provider", "arxiv"),
            DispatchIntent("provider", "crossref"),
            DispatchIntent("provider", "wikipedia"),
        ]
    )
    assert control.feedback_context(_participant(1), _session(1)) is None
    await governor.aclose()
    assert control.feedback_context(_participant(1), _session(1)) == FeedbackContext(
        slot_id="C01",
        profile="community",
        provider_attempts=3,
        tavily_attempts=0,
    )

    feedback_clock = FeedbackClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    root = tmp_path / "feedback"
    store = ClosedAlphaFeedbackStore(
        root,
        ClosedAlphaFeedbackContract(CANDIDATE_SHA),
        control,
        clock=feedback_clock,
    )
    report = _report(feedback_clock.now)
    assert store.put(report).created is True
    store.close()

    control.withdraw(_participant(1), expected_admission_epoch=1)
    reopened = ClosedAlphaFeedbackStore(
        root,
        ClosedAlphaFeedbackContract(CANDIDATE_SHA),
        control,
        clock=feedback_clock,
    )
    try:
        assert reopened.get(_session(1)) is None
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_privacy_fault_is_durable_and_blocks_reserve_hook_and_resume(
    tmp_path: Path,
) -> None:
    clock = MonotonicClock()
    control, ledger, epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    permit = (await governor.reserve_batch([DispatchIntent("provider", "wikipedia")]))[0]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    governor.attach_client(client)
    control.record_privacy_fault()
    snapshot = control.snapshot()
    assert snapshot["state"] == "paused"
    assert snapshot["control_epoch"] == epoch + 1
    assert snapshot["privacy_fault"] is True

    with pytest.raises(BudgetExceededError), governor.capture(permit):
        await client.get("https://offline.invalid/privacy-fault")
    with pytest.raises(BudgetExceededError, match="privacy fault"):
        await governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
    with pytest.raises(BudgetConfigurationError, match="privacy fault"):
        control.transition(
            "prepared",
            expected_state="paused",
            expected_epoch=epoch + 1,
        )
    assert calls == 0
    await client.aclose()
    await governor.aclose()


def test_feedback_clock_high_water_survives_instances_and_trips_fault(tmp_path: Path) -> None:
    clock = MonotonicClock()
    control, ledger, epoch = _prepared_control(tmp_path, clock)
    assert control.advance_feedback_clock(100.0) is True

    reopened = SQLiteAlphaControlPlane(ledger, clock=clock)
    assert reopened.advance_feedback_clock(100.0) is True
    assert reopened.advance_feedback_clock(99.0) is False
    snapshot = control.snapshot()
    assert snapshot["state"] == "paused"
    assert snapshot["control_epoch"] == epoch + 1
    assert snapshot["privacy_fault"] is True


def test_control_plane_rejects_hardlink_and_inode_replacement(tmp_path: Path) -> None:
    clock = MonotonicClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    external_link = tmp_path / "control-hardlink.sqlite3"
    os.link(ledger, external_link)
    with pytest.raises(BudgetConfigurationError, match="permissions"):
        control.snapshot()
    external_link.unlink()
    assert control.snapshot()["state"] == "prepared"

    replacement = tmp_path / "replacement.sqlite3"
    replacement.write_bytes(ledger.read_bytes())
    replacement.chmod(0o600)
    backup = tmp_path / "original.sqlite3"
    ledger.rename(backup)
    replacement.rename(ledger)
    with pytest.raises(BudgetConfigurationError, match="identity changed"):
        control.snapshot()
