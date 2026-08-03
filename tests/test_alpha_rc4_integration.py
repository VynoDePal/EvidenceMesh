from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

import evidencemesh.closed_alpha_feedback as feedback_module
import evidencemesh.governor as governor_module
from evidencemesh.closed_alpha_feedback import (
    ClosedAlphaFeedbackContract,
    ClosedAlphaFeedbackIdentity,
    ClosedAlphaFeedbackStore,
    FeedbackAdmissionError,
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
CANDIDATE_TREE = "a" * 40


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


def _accepted_contract(root: Path, monkeypatch: pytest.MonkeyPatch) -> ClosedAlphaFeedbackContract:
    root.mkdir()
    wheel = root / "evidencemesh-0.1.0-py3-none-any.whl"
    sdist = root / "evidencemesh-0.1.0.tar.gz"
    wheel.write_bytes(b"synthetic accepted wheel\n")
    sdist.write_bytes(b"synthetic accepted sdist\n")
    wheel_digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    sdist_digest = hashlib.sha256(sdist.read_bytes()).hexdigest()
    record = {
        "schema_version": 1,
        "acceptance": {
            "scope": "single_host_technical_alpha_only",
            "scored": False,
            "status": "accepted",
        },
        "attestations": {
            name: {
                "id": identifier,
                "url": (f"https://github.com/VynoDePal/EvidenceMesh/attestations/{identifier}"),
            }
            for name, identifier in (("provenance", 101), ("result", 102), ("sbom", 103))
        },
        "candidate": {
            "sha": CANDIDATE_SHA,
            "tree": CANDIDATE_TREE,
            "subjects": {
                f"dist/{wheel.name}": wheel_digest,
                f"dist/{sdist.name}": sdist_digest,
            },
        },
        "distribution": {
            "binary_artifact_uploaded": False,
            "github_actions_artifact_count": 0,
            "public_metadata_only": True,
            "unpublished_distributions": True,
        },
        "seal": {"completed": True, "workflow_retired": True},
    }
    record_payload = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
    record_path = root / "acceptance.json"
    record_path.write_bytes(record_payload)
    direct_url_payload = json.dumps(
        {
            "archive_info": {"hashes": {"sha256": wheel_digest}},
            "url": wheel.resolve().as_uri(),
        }
    ).encode()
    with monkeypatch.context() as patch:
        patch.setattr(feedback_module, "_read_installed_direct_url", lambda: direct_url_payload)
        identity = ClosedAlphaFeedbackIdentity.load(
            record_path,
            expected_record_sha256=hashlib.sha256(record_payload).hexdigest(),
            archive_path=wheel,
        )
    return ClosedAlphaFeedbackContract(identity)


@pytest.mark.asyncio
async def test_real_control_plane_binds_feedback_and_recovers_withdrawal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    contract = _accepted_contract(tmp_path / "accepted-identity", monkeypatch)
    store = ClosedAlphaFeedbackStore(
        root,
        contract,
        control,
        clock=feedback_clock,
    )
    report = _report(feedback_clock.now)
    assert store.put(report).created is True
    store.close()

    control.withdraw(_participant(1), expected_admission_epoch=1)
    reopened = ClosedAlphaFeedbackStore(
        root,
        contract,
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


@pytest.mark.asyncio
async def test_feedback_put_cannot_publish_after_racing_fault_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = MonotonicClock()
    control, ledger, _epoch = _prepared_control(tmp_path, clock)
    governor = _governor(ledger, clock)
    await governor.reserve_batch(
        [
            DispatchIntent("provider", "arxiv"),
            DispatchIntent("provider", "crossref"),
            DispatchIntent("provider", "wikipedia"),
        ]
    )
    await governor.aclose()

    feedback_clock = FeedbackClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    root = tmp_path / "feedback-race"
    store = ClosedAlphaFeedbackStore(
        root,
        _accepted_contract(tmp_path / "accepted-race-identity", monkeypatch),
        control,
        clock=feedback_clock,
    )
    final_check_entered = threading.Event()
    marker_created = threading.Event()
    release_final_check = threading.Event()
    original_marker_check = governor_module._private_privacy_fault_marker_present
    writer_checks = 0

    def synchronized_marker_check(path: Path) -> bool:
        nonlocal writer_checks
        if threading.current_thread().name == "feedback-writer":
            writer_checks += 1
            if writer_checks == 2:
                final_check_entered.set()
                if not release_final_check.wait(5.0):
                    raise AssertionError("feedback fault synchronization timed out")
        present = original_marker_check(path)
        if threading.current_thread().name == "fault-writer" and present:
            marker_created.set()
        return present

    monkeypatch.setattr(
        governor_module,
        "_private_privacy_fault_marker_present",
        synchronized_marker_check,
    )
    put_failures: list[BaseException] = []
    fault_failures: list[BaseException] = []

    def put_report() -> None:
        try:
            store.put(_report(feedback_clock.now))
        except BaseException as exc:
            put_failures.append(exc)

    def record_fault() -> None:
        try:
            control.record_privacy_fault()
        except BaseException as exc:  # pragma: no cover - asserted below
            fault_failures.append(exc)

    writer = threading.Thread(target=put_report, name="feedback-writer")
    writer.start()
    assert final_check_entered.wait(5.0)
    fault_writer = threading.Thread(target=record_fault, name="fault-writer")
    fault_writer.start()
    assert marker_created.wait(5.0)
    release_final_check.set()
    writer.join(5.0)
    fault_writer.join(5.0)
    try:
        assert not writer.is_alive()
        assert not fault_writer.is_alive()
        assert fault_failures == []
        assert len(put_failures) == 1
        assert isinstance(put_failures[0], FeedbackAdmissionError)
        assert not (root / f"{_session(1)}.json").exists()
    finally:
        store.close()


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
