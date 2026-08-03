from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import socket
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
import pytest

import evidencemesh.closed_alpha_feedback as feedback_module
from evidencemesh.alpha_liveness import (
    A2RetentionSupervisor,
    A2SQLiteAlphaControlPlane,
    A2SQLiteBudgetGovernor,
    FeedbackPublicationAuthority,
)
from evidencemesh.closed_alpha_feedback import (
    ClosedAlphaFeedbackContract,
    ClosedAlphaFeedbackIdentity,
    ClosedAlphaFeedbackStore,
    FeedbackAdmissionError,
    FeedbackStoreBinding,
)
from evidencemesh.config import Settings
from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError
from evidencemesh.fetcher import WebFetcher
from evidencemesh.governor import (
    AlphaControlState,
    ClosedAlphaAdmission,
    ClosedAlphaSession,
    DispatchIntent,
)

CANDIDATE_SHA = "c1e0be437442b0d97da26f2c9085067a8c09955e"
CANDIDATE_TREE = "a" * 40
BOOT_ID = b"12345678-1234-5678-1234-567812345678\n"
SUPERVISOR_SECRET = b"r" * 32
SESSION_SECRET = b"s" * 32
_DEADLOCK_GUARD_SECONDS = 15.0


class _FeedbackClockAnchorView(Protocol):
    checked_at_boottime: float


@dataclass
class FakeBoottime:
    now: float = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class FakeFeedbackClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class Harness:
    boottime: FakeBoottime
    feedback_clock: FakeFeedbackClock
    control: A2SQLiteAlphaControlPlane
    governor: A2SQLiteBudgetGovernor
    supervisor: A2RetentionSupervisor
    store: ClosedAlphaFeedbackStore
    ledger: Path
    feedback_root: Path
    prepared_epoch: int

    async def shutdown(self) -> None:
        with contextlib.suppress(BaseException):
            await self.governor.aclose()
        with contextlib.suppress(BaseException):
            await self.supervisor.aclose()
        if not self.store.closed:
            with contextlib.suppress(BaseException):
                self.store.close()


@pytest.fixture(autouse=True)
def _deny_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A2-P1 feedback/transport tests must stay offline")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    yield


def _participant(index: int) -> str:
    return f"p-{index:016x}"


def _session(index: int) -> str:
    return f"s-{index:032x}"


def _admit_full_cohort(control: A2SQLiteAlphaControlPlane) -> None:
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


def _accepted_contract(root: Path, monkeypatch: pytest.MonkeyPatch) -> ClosedAlphaFeedbackContract:
    root.mkdir(parents=True)
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
                "url": f"https://github.com/VynoDePal/EvidenceMesh/attestations/{identifier}",
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
        "task": {
            "slot": 1,
            "kind": "prescribed",
            "category": "general_reference",
        },
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
            "provider_attempts": 0,
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


async def _prepared_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Harness:
    boottime = FakeBoottime()
    feedback_clock = FakeFeedbackClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    ledger = tmp_path / "private" / "control.sqlite3"
    control = A2SQLiteAlphaControlPlane.bootstrap(
        ledger,
        boottime=boottime,
        boot_identity=lambda: BOOT_ID,
    )
    _admit_full_cohort(control)
    governor = A2SQLiteBudgetGovernor(
        ledger,
        ClosedAlphaSession(_participant(1), _session(1), "community"),
        boottime=boottime,
        boot_identity=lambda: BOOT_ID,
        owner_secret=SESSION_SECRET,
    )
    feedback_root = tmp_path / "feedback"
    store = ClosedAlphaFeedbackStore(
        feedback_root,
        _accepted_contract(tmp_path / "accepted", monkeypatch),
        governor,
        clock=feedback_clock,
    )
    bound_epoch = control.bind_feedback_store(store, expected_control_epoch=1)
    supervisor = A2RetentionSupervisor(
        control,
        store,
        owner_secret=SUPERVISOR_SECRET,
    )
    await supervisor.run_once()
    prepared_epoch = control.transition(
        AlphaControlState.PREPARED,
        expected_state=AlphaControlState.PAUSED,
        expected_epoch=bound_epoch,
    )
    await governor.open_session()
    return Harness(
        boottime=boottime,
        feedback_clock=feedback_clock,
        control=control,
        governor=governor,
        supervisor=supervisor,
        store=store,
        ledger=ledger,
        feedback_root=feedback_root,
        prepared_epoch=prepared_epoch,
    )


async def _reserve_one(harness: Harness) -> object:
    permits = await harness.governor.reserve_batch([DispatchIntent("provider", "wikipedia")])
    assert len(permits) == 1
    return permits[0]


@pytest.mark.asyncio
async def test_bound_store_rejects_decoy_root_and_foreign_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    decoy_store = ClosedAlphaFeedbackStore(
        tmp_path / "feedback-decoy",
        _accepted_contract(tmp_path / "accepted-decoy", monkeypatch),
        harness.governor,
        clock=harness.feedback_clock,
    )
    foreign_ledger = tmp_path / "foreign" / "control.sqlite3"
    A2SQLiteAlphaControlPlane.bootstrap(
        foreign_ledger,
        boottime=harness.boottime,
        boot_identity=lambda: BOOT_ID,
    )
    foreign_governor = A2SQLiteBudgetGovernor(
        foreign_ledger,
        ClosedAlphaSession(_participant(1), _session(2), "community"),
        boottime=harness.boottime,
        boot_identity=lambda: BOOT_ID,
        owner_secret=b"f" * 32,
    )
    foreign_store = ClosedAlphaFeedbackStore(
        tmp_path / "feedback-foreign",
        _accepted_contract(tmp_path / "accepted-foreign", monkeypatch),
        foreign_governor,
        clock=harness.feedback_clock,
    )
    try:
        with pytest.raises(BudgetConfigurationError, match="unbound or foreign"):
            A2RetentionSupervisor(
                harness.control,
                decoy_store,
                owner_secret=b"d" * 32,
            )
        with pytest.raises(BudgetConfigurationError, match="another ledger"):
            A2RetentionSupervisor(
                harness.control,
                foreign_store,
                owner_secret=b"x" * 32,
            )
        await harness.governor.aclose()
        with pytest.raises(FeedbackAdmissionError, match="not authorized"):
            decoy_store.put(
                _report(harness.feedback_clock.now),
                authority=harness.governor.feedback_authority,
            )
        assert not (decoy_store.root / f"{_session(1)}.json").exists()
    finally:
        foreign_store.close()
        await foreign_governor.aclose()
        decoy_store.close()
        await harness.shutdown()


@pytest.mark.parametrize("late_change", ["pause", "expiry"])
@pytest.mark.asyncio
async def test_final_transport_rechecks_after_later_hook_and_never_calls_inner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    late_change: str,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    inner_calls = 0

    async def inner(_request: httpx.Request) -> httpx.Response:
        nonlocal inner_calls
        inner_calls += 1
        return httpx.Response(200)

    client = harness.governor.make_client(httpx.MockTransport(inner))

    async def change_authority_after_early_hook(_request: httpx.Request) -> None:
        if late_change == "pause":
            harness.control.transition(
                AlphaControlState.PAUSED,
                expected_state=AlphaControlState.PREPARED,
                expected_epoch=harness.prepared_epoch,
            )
        else:
            harness.boottime.advance(31.0)

    client.event_hooks["request"].append(change_authority_after_early_hook)
    permit = await _reserve_one(harness)
    try:
        with (
            harness.governor.capture(permit),  # type: ignore[arg-type]
            pytest.raises(BudgetExceededError),
        ):
            await client.get("https://offline.invalid/final-boundary")
        assert inner_calls == 0
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_final_transport_metadata_drift_commits_fault_without_delegation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    inner_calls = 0

    async def inner(_request: httpx.Request) -> httpx.Response:
        nonlocal inner_calls
        inner_calls += 1
        return httpx.Response(200)

    client = harness.governor.make_client(httpx.MockTransport(inner))
    # Exercise the actual transport linearization point, not the optional
    # poison-pill request hook.
    client.event_hooks["request"].clear()
    permit = await _reserve_one(harness)
    with sqlite3.connect(harness.ledger) as db:
        db.execute(
            "UPDATE metadata SET value = ? WHERE key = 'policy_fingerprint'",
            ("0" * 64,),
        )
        db.commit()

    try:
        with (
            harness.governor.capture(permit),  # type: ignore[arg-type]
            pytest.raises(BudgetConfigurationError, match="metadata drifted"),
        ):
            await client.get("https://offline.invalid/metadata-drift")
        assert inner_calls == 0
        snapshot = harness.control.snapshot()
        assert snapshot["supervisor_fault"] is True
        assert snapshot["state"] == "paused"
        assert snapshot["supervisor_state"] == "expired"
        marker = harness.ledger.with_name(f"{harness.ledger.name}.retention-supervisor-fault-v1")
        assert marker.is_file()
        with sqlite3.connect(harness.ledger) as db:
            attempt = db.execute("SELECT dispatched, outcome FROM attempts").fetchone()
        assert attempt == (1, "denied_state")
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_two_concurrent_departures_with_one_permit_delegate_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    entered = asyncio.Event()
    release = asyncio.Event()
    inner_calls = 0

    async def inner(_request: httpx.Request) -> httpx.Response:
        nonlocal inner_calls
        inner_calls += 1
        if inner_calls == 1:
            entered.set()
            await asyncio.wait_for(
                release.wait(),
                timeout=_DEADLOCK_GUARD_SECONDS,
            )
        return httpx.Response(200)

    client = harness.governor.make_client(httpx.MockTransport(inner))
    permit = await _reserve_one(harness)
    first: asyncio.Task[httpx.Response] | None = None
    try:
        with harness.governor.capture(permit):  # type: ignore[arg-type]
            first = asyncio.create_task(client.get("https://offline.invalid/first"))
            await asyncio.wait_for(
                entered.wait(),
                timeout=_DEADLOCK_GUARD_SECONDS,
            )
            second = asyncio.create_task(client.get("https://offline.invalid/second"))
            second_result = (
                await asyncio.wait_for(
                    asyncio.gather(second, return_exceptions=True),
                    timeout=_DEADLOCK_GUARD_SECONDS,
                )
            )[0]
            release.set()
            first_result = await asyncio.wait_for(
                first,
                timeout=_DEADLOCK_GUARD_SECONDS,
            )
        assert first_result.status_code == 200
        assert isinstance(second_result, BudgetExceededError)
        assert inner_calls == 1
    finally:
        release.set()
        if first is not None:
            if not first.done():
                first.cancel()
            with contextlib.suppress(BaseException):
                await first
        await harness.shutdown()


@pytest.mark.asyncio
async def test_permit_is_consumed_before_inner_error_and_transport_does_not_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    inner_calls = 0

    async def failing_inner(request: httpx.Request) -> httpx.Response:
        nonlocal inner_calls
        inner_calls += 1
        raise httpx.ConnectError("synthetic offline inner failure", request=request)

    client = harness.governor.make_client(httpx.MockTransport(failing_inner))
    permit = await _reserve_one(harness)
    try:
        with harness.governor.capture(permit):  # type: ignore[arg-type]
            with pytest.raises(httpx.ConnectError):
                await client.get("https://offline.invalid/fails")
            with pytest.raises(BudgetExceededError):
                await client.get("https://offline.invalid/reuse")
        assert inner_calls == 1
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_client_exposes_offline_trust_and_redirect_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    inner_calls = 0

    async def redirecting_inner(_request: httpx.Request) -> httpx.Response:
        nonlocal inner_calls
        inner_calls += 1
        return httpx.Response(302, headers={"location": "https://offline.invalid/follow-up"})

    client = harness.governor.make_client(httpx.MockTransport(redirecting_inner))
    permit = await _reserve_one(harness)
    try:
        assert client.trust_env is False
        assert client.follow_redirects is False
        with harness.governor.capture(permit):  # type: ignore[arg-type]
            response = await client.get("https://offline.invalid/redirect")
        assert response.status_code == 302
        assert response.next_request is not None
        assert inner_calls == 1
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_custom_transport_is_rejected_before_client_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)

    class CustomTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, _request: httpx.Request) -> httpx.Response:
            raise AssertionError("custom transport must never be delegated")

    try:
        with pytest.raises(BudgetConfigurationError, match="custom transports are forbidden"):
            harness.governor.make_client(CustomTransport())
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_web_fetcher_a2_refuses_resolution_and_fetch_before_dns_or_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    dns_calls = 0

    def observed_dns(*_args: object, **_kwargs: object) -> None:
        nonlocal dns_calls
        dns_calls += 1
        raise AssertionError("A2 WebFetcher must refuse before DNS")

    monkeypatch.setattr(socket, "getaddrinfo", observed_dns)
    fetcher = WebFetcher(
        Settings(
            enabled_providers=[],
            cache_path=tmp_path / "fetcher-cache.sqlite3",
            respect_robots_txt=False,
        ),
        governor=harness.governor,
    )
    target = "https://offline.invalid/document"
    try:
        with pytest.raises(BudgetConfigurationError, match="pre-transport DNS resolution"):
            await fetcher.guard.validate(target)
        assert harness.control.snapshot()["global_attempts"] == 0

        with pytest.raises(BudgetConfigurationError, match="pre-transport DNS resolution"):
            await fetcher.fetch(target)
        assert harness.control.snapshot()["global_attempts"] == 0
        assert dns_calls == 0
    finally:
        await fetcher.aclose()
        await harness.shutdown()


@pytest.mark.asyncio
async def test_concurrent_session_limit_is_global_across_governor_instances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    second = A2SQLiteBudgetGovernor(
        harness.ledger,
        ClosedAlphaSession(_participant(2), _session(2), "community"),
        boottime=harness.boottime,
        boot_identity=lambda: BOOT_ID,
        owner_secret=b"2" * 32,
    )
    third = A2SQLiteBudgetGovernor(
        harness.ledger,
        ClosedAlphaSession(_participant(3), _session(3), "community"),
        boottime=harness.boottime,
        boot_identity=lambda: BOOT_ID,
        owner_secret=b"3" * 32,
    )
    try:
        assert await second.open_session() == 1
        with pytest.raises(BudgetExceededError, match="concurrent session budget"):
            await third.open_session()
        assert harness.control.snapshot()["sessions"] == 2
    finally:
        await third.aclose()
        await second.aclose()
        await harness.shutdown()


@pytest.mark.asyncio
async def test_close_emits_only_a_process_local_feedback_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    try:
        with pytest.raises(BudgetConfigurationError):
            _ = harness.governor.feedback_authority
        await harness.governor.aclose()
        authority = harness.governor.feedback_authority
        assert type(authority) is FeedbackPublicationAuthority
        assert authority.participant_code == _participant(1)
        assert authority.session_code == _session(1)
        assert authority.token not in repr(authority)

        with sqlite3.connect(harness.ledger) as db:
            tables = {str(row[0]) for row in db.execute("SELECT name FROM sqlite_master")}
            dump = "\n".join(db.iterdump())
        assert not any("feedback_authorit" in table for table in tables)
        assert authority.token not in dump

        probe = A2SQLiteBudgetGovernor(
            harness.ledger,
            ClosedAlphaSession(_participant(1), _session(1), "community"),
            boottime=harness.boottime,
            boot_identity=lambda: BOOT_ID,
            owner_secret=b"p" * 32,
        )
        try:
            with pytest.raises(BudgetConfigurationError):
                _ = probe.feedback_authority
        finally:
            await probe.aclose()
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_store_restart_cannot_recover_or_reuse_feedback_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    await harness.governor.aclose()
    old_authority = harness.governor.feedback_authority
    report = _report(harness.feedback_clock.now)
    assert harness.store.put(report, authority=old_authority).created is True
    report_path = harness.feedback_root / f"{_session(1)}.json"
    assert report_path.is_file()
    harness.store.close()
    restarted_governor = A2SQLiteBudgetGovernor(
        harness.ledger,
        ClosedAlphaSession(_participant(1), _session(1), "community"),
        boottime=harness.boottime,
        boot_identity=lambda: BOOT_ID,
        owner_secret=b"n" * 32,
    )
    restarted_store = ClosedAlphaFeedbackStore(
        harness.feedback_root,
        _accepted_contract(tmp_path / "accepted-restart", monkeypatch),
        restarted_governor,
        clock=harness.feedback_clock,
    )
    try:
        assert restarted_store.reports() == (report,)
        with pytest.raises(FeedbackAdmissionError, match="authority is required"):
            restarted_store.put(report)
        with pytest.raises(FeedbackAdmissionError, match="not authorized"):
            restarted_store.put(
                report,
                authority=old_authority,
            )
        with pytest.raises(BudgetConfigurationError):
            _ = restarted_governor.feedback_authority
        assert report_path.is_file()
    finally:
        restarted_store.close()
        await restarted_governor.aclose()
        await harness.shutdown()


@pytest.mark.asyncio
async def test_one_bound_store_reconciles_reports_from_multiple_closed_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    second = A2SQLiteBudgetGovernor(
        harness.ledger,
        ClosedAlphaSession(_participant(2), _session(2), "community"),
        boottime=harness.boottime,
        boot_identity=lambda: BOOT_ID,
        owner_secret=b"m" * 32,
    )
    second_store: ClosedAlphaFeedbackStore | None = None
    try:
        await second.open_session()
        await harness.governor.aclose()
        first_report = _report(harness.feedback_clock.now)
        assert harness.store.put(
            first_report,
            authority=harness.governor.feedback_authority,
        ).created

        await second.aclose()
        second_store = ClosedAlphaFeedbackStore(
            harness.feedback_root,
            _accepted_contract(tmp_path / "accepted-second-session", monkeypatch),
            second,
            clock=harness.feedback_clock,
        )
        second_report = _report(harness.feedback_clock.now)
        second_report["participant_code"] = _participant(2)
        second_report["session_code"] = _session(2)
        second_report["slot_id"] = "C02"
        assert second_store.put(
            second_report,
            authority=second.feedback_authority,
        ).created

        reports = harness.store.reports()
        assert tuple(report["session_code"] for report in reports) == (
            _session(1),
            _session(2),
        )
        assert (await harness.supervisor.run_once()).state == "active"
    finally:
        if second_store is not None:
            second_store.close()
        await second.aclose()
        await harness.shutdown()


@pytest.mark.asyncio
async def test_publication_anchor_precedes_utc_and_validation_latency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    await harness.governor.aclose()
    start = harness.boottime.now
    original_anchor = harness.governor.feedback_publication_clock_anchor
    original_prepare = harness.governor.prepare_feedback_publication
    original_validate = harness.store._validate_report
    timeline: list[tuple[str, float]] = []
    supplied_anchor_times: list[float] = []

    def observed_anchor(*, store_binding: FeedbackStoreBinding) -> object:
        anchor = original_anchor(store_binding=store_binding)
        checked_at = cast(_FeedbackClockAnchorView, anchor).checked_at_boottime
        timeline.append(("anchor", float(checked_at)))
        return anchor

    def delayed_utc_clock() -> datetime:
        harness.boottime.advance(4.0)
        timeline.append(("utc_latency_complete", harness.boottime.now))
        return harness.feedback_clock.now

    def delayed_validation(
        report: Mapping[str, Any],
        *,
        now: datetime,
    ) -> tuple[str, str, datetime]:
        harness.boottime.advance(4.0)
        timeline.append(("validation_latency_complete", harness.boottime.now))
        return original_validate(report, now=now)

    def observed_prepare(
        supplied_authority: object,
        *,
        participant_code: str,
        session_code: str,
        checked_at_utc: float,
        purge_at_utc: float,
        is_new: bool,
        store_binding: FeedbackStoreBinding,
        clock_anchor: object,
    ) -> object:
        checked_at = cast(_FeedbackClockAnchorView, clock_anchor).checked_at_boottime
        supplied_anchor_times.append(float(checked_at))
        timeline.append(("prepare", harness.boottime.now))
        return original_prepare(
            supplied_authority,
            participant_code=participant_code,
            session_code=session_code,
            checked_at_utc=checked_at_utc,
            purge_at_utc=purge_at_utc,
            is_new=is_new,
            store_binding=store_binding,
            clock_anchor=clock_anchor,
        )

    monkeypatch.setattr(
        harness.governor,
        "feedback_publication_clock_anchor",
        observed_anchor,
    )
    monkeypatch.setattr(harness.store, "_clock", delayed_utc_clock)
    monkeypatch.setattr(harness.store, "_validate_report", delayed_validation)
    monkeypatch.setattr(harness.governor, "prepare_feedback_publication", observed_prepare)
    before = harness.control.supervisor_cas_snapshot()
    assert before.lease_expires_at_boottime is not None
    try:
        assert harness.store.put(
            _report(harness.feedback_clock.now),
            authority=harness.governor.feedback_authority,
        ).created
        assert [event for event, _at in timeline] == [
            "anchor",
            "utc_latency_complete",
            "validation_latency_complete",
            "prepare",
        ]
        assert timeline == [
            ("anchor", start),
            ("utc_latency_complete", start + 4.0),
            ("validation_latency_complete", start + 8.0),
            ("prepare", start + 8.0),
        ]
        assert supplied_anchor_times == [start]
        assert harness.control.supervisor_cas_snapshot().lease_expires_at_boottime == (
            math.nextafter(before.lease_expires_at_boottime, -math.inf)
        )
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_new_publication_and_identical_replay_both_cross_two_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    await harness.governor.aclose()
    authority = harness.governor.feedback_authority
    original_prepare = harness.governor.prepare_feedback_publication
    original_guard = harness.governor.feedback_publication_guard
    prepared_newness: list[bool] = []
    guard_events: list[str] = []

    def observed_prepare(
        supplied_authority: object,
        *,
        participant_code: str,
        session_code: str,
        checked_at_utc: float,
        purge_at_utc: float,
        is_new: bool,
        store_binding: FeedbackStoreBinding,
        clock_anchor: object,
    ) -> object:
        prepared_newness.append(is_new)
        return original_prepare(
            supplied_authority,
            participant_code=participant_code,
            session_code=session_code,
            checked_at_utc=checked_at_utc,
            purge_at_utc=purge_at_utc,
            is_new=is_new,
            store_binding=store_binding,
            clock_anchor=clock_anchor,
        )

    @contextmanager
    def observed_guard(
        prepared: object,
        *,
        participant_code: str,
        session_code: str,
        checked_at_utc: float,
        store_binding: FeedbackStoreBinding,
    ) -> Iterator[None]:
        guard_events.append("enter")
        with original_guard(
            prepared,
            participant_code=participant_code,
            session_code=session_code,
            checked_at_utc=checked_at_utc,
            store_binding=store_binding,
        ):
            guard_events.append("yield")
            yield
        guard_events.append("exit")

    monkeypatch.setattr(harness.governor, "prepare_feedback_publication", observed_prepare)
    monkeypatch.setattr(harness.governor, "feedback_publication_guard", observed_guard)
    report = _report(harness.feedback_clock.now)
    try:
        assert harness.store.put(report, authority=authority).created is True
        assert harness.store.put(report, authority=authority).created is False
        assert prepared_newness == [True, False]
        assert guard_events == ["enter", "yield", "exit", "enter", "yield", "exit"]
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_expiry_between_publication_phases_never_links_and_removes_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    await harness.governor.aclose()
    authority = harness.governor.feedback_authority
    original_prepare = harness.governor.prepare_feedback_publication
    original_link = feedback_module.os.link
    link_calls = 0

    def prepare_then_expire(
        supplied_authority: object,
        *,
        participant_code: str,
        session_code: str,
        checked_at_utc: float,
        purge_at_utc: float,
        is_new: bool,
        store_binding: FeedbackStoreBinding,
        clock_anchor: object,
    ) -> object:
        prepared = original_prepare(
            supplied_authority,
            participant_code=participant_code,
            session_code=session_code,
            checked_at_utc=checked_at_utc,
            purge_at_utc=purge_at_utc,
            is_new=is_new,
            store_binding=store_binding,
            clock_anchor=clock_anchor,
        )
        harness.boottime.advance(31.0)
        return prepared

    def observed_link(*args: Any, **kwargs: Any) -> None:
        nonlocal link_calls
        link_calls += 1
        original_link(*args, **kwargs)

    monkeypatch.setattr(harness.governor, "prepare_feedback_publication", prepare_then_expire)
    monkeypatch.setattr(feedback_module.os, "link", observed_link)
    try:
        with pytest.raises(FeedbackAdmissionError):
            harness.store.put(_report(harness.feedback_clock.now), authority=authority)
        assert link_calls == 0
        assert not (harness.feedback_root / f"{_session(1)}.json").exists()
        assert tuple(harness.feedback_root.glob(".feedback-tmp-*")) == ()
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_phase_a_changes_expiry_cas_token_even_when_purge_cap_is_later(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    await harness.governor.aclose()
    capability = harness.governor.feedback_authority
    store_binding = harness.store.retention_binding()
    clock_anchor = harness.governor.feedback_publication_clock_anchor(
        store_binding=store_binding,
    )
    before = harness.control.supervisor_cas_snapshot()
    assert before.lease_expires_at_boottime is not None
    checked_at = harness.feedback_clock.now.timestamp()
    prepared = harness.governor.prepare_feedback_publication(
        capability,
        participant_code=_participant(1),
        session_code=_session(1),
        checked_at_utc=checked_at,
        purge_at_utc=checked_at + 86400.0,
        is_new=True,
        store_binding=store_binding,
        clock_anchor=clock_anchor,
    )
    after = harness.control.supervisor_cas_snapshot()
    try:
        assert after.heartbeat_sequence == before.heartbeat_sequence
        assert after.lease_expires_at_boottime == math.nextafter(
            before.lease_expires_at_boottime,
            -math.inf,
        )
        with harness.governor.feedback_publication_guard(
            prepared,
            participant_code=_participant(1),
            session_code=_session(1),
            checked_at_utc=checked_at,
            store_binding=store_binding,
        ):
            pass
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_retention_pass_snapshot_makes_post_publication_renewal_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    await harness.governor.aclose()
    result, stale_snapshot = harness.store.retention_pass(
        lambda _result: harness.control.supervisor_cas_snapshot()
    )
    checked_at = harness.feedback_clock.now.timestamp()
    store_binding = harness.store.retention_binding()
    clock_anchor = harness.governor.feedback_publication_clock_anchor(
        store_binding=store_binding,
    )
    prepared = harness.governor.prepare_feedback_publication(
        harness.governor.feedback_authority,
        participant_code=_participant(1),
        session_code=_session(1),
        checked_at_utc=checked_at,
        purge_at_utc=checked_at + 86400.0,
        is_new=True,
        store_binding=store_binding,
        clock_anchor=clock_anchor,
    )
    current = harness.control.supervisor_cas_snapshot()
    try:
        assert current.lease_expires_at_boottime != stale_snapshot.lease_expires_at_boottime
        with pytest.raises(BudgetConfigurationError, match="stale supervisor heartbeat"):
            harness.control._renew_supervisor(
                SUPERVISOR_SECRET,
                expected=stale_snapshot,
                store_binding=store_binding,
                last_successful_retention_high_water_utc=result.checked_at.timestamp(),
                next_purge_at_boottime=harness.boottime.now + 35.0,
            )
        with harness.governor.feedback_publication_guard(
            prepared,
            participant_code=_participant(1),
            session_code=_session(1),
            checked_at_utc=checked_at,
            store_binding=store_binding,
        ):
            pass
    finally:
        await harness.shutdown()


@pytest.mark.parametrize("cleanup", ["purge", "withdraw"])
@pytest.mark.asyncio
async def test_purge_and_withdraw_cleanup_do_not_require_a_live_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup: str,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    await harness.governor.aclose()
    report_path = harness.feedback_root / f"{_session(1)}.json"
    assert harness.store.put(
        _report(harness.feedback_clock.now),
        authority=harness.governor.feedback_authority,
    ).created
    assert report_path.is_file()
    harness.boottime.advance(31.0)
    try:
        if cleanup == "purge":
            harness.feedback_clock.advance(15 * 86400.0)
            assert harness.store.purge().deleted == 1
        else:
            assert (
                harness.control.withdraw(
                    _participant(1),
                    expected_admission_epoch=1,
                )
                == 2
            )
            assert harness.store.withdraw(_participant(1)) == 1
        assert not report_path.exists()
    finally:
        await harness.shutdown()


@pytest.mark.parametrize("denial", ["stale-epoch", "rate-limit"])
@pytest.mark.asyncio
async def test_final_transport_denials_are_consumed_and_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    denial: str,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    inner_calls = 0

    async def inner(_request: httpx.Request) -> httpx.Response:
        nonlocal inner_calls
        inner_calls += 1
        return httpx.Response(200)

    client = harness.governor.make_client(httpx.MockTransport(inner))
    client.event_hooks["request"].clear()
    permit = await _reserve_one(harness)
    with sqlite3.connect(harness.ledger) as db:
        if denial == "stale-epoch":
            db.execute(
                "UPDATE attempts SET control_epoch = control_epoch + 1 WHERE outcome = 'reserved'"
            )
        else:
            row = db.execute("SELECT * FROM attempts WHERE outcome = 'reserved'").fetchone()
            assert row is not None
            for index in range(harness.governor.policy.request_starts_per_minute_max):
                db.execute(
                    """
                    INSERT INTO attempts(
                        token_digest, session_code, kind, provider,
                        reserved_at_boottime, supervisor_epoch, control_epoch,
                        admission_epoch, session_epoch, dispatched,
                        dispatched_at_boottime, consumed_at_boottime, outcome
                    ) VALUES (?, ?, 'provider', 'wikipedia', ?, ?, ?, ?, ?, 1, ?, ?, 'started')
                    """,
                    (
                        hashlib.sha256(f"started-{index}".encode()).hexdigest(),
                        _session(1),
                        harness.boottime.now,
                        row[6],
                        row[7],
                        row[8],
                        row[9],
                        harness.boottime.now,
                        harness.boottime.now,
                    ),
                )
        db.commit()

    try:
        with (
            harness.governor.capture(permit),  # type: ignore[arg-type]
            pytest.raises(BudgetExceededError),
        ):
            await client.get("https://offline.invalid/denied")
        assert inner_calls == 0
        with sqlite3.connect(harness.ledger) as db:
            outcome = db.execute(
                "SELECT dispatched, outcome FROM attempts WHERE token_digest = ?",
                (hashlib.sha256(bytes.fromhex(permit.token)).hexdigest(),),  # type: ignore[attr-defined]
            ).fetchone()
        expected = "denied_epoch" if denial == "stale-epoch" else "denied_rate"
        assert outcome == (1, expected)
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_public_capture_rejects_invalid_foreign_and_nested_permits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    permit = await _reserve_one(harness)
    try:
        with (
            pytest.raises(BudgetConfigurationError, match="exact dispatch permit"),
            harness.governor.capture(object()),  # type: ignore[arg-type]
        ):
            pass
        foreign = replace(permit, _governor_id="foreign")  # type: ignore[call-overload]
        with (
            pytest.raises(BudgetConfigurationError, match="another governor"),
            harness.governor.capture(foreign),
        ):
            pass
        with (
            harness.governor.capture(permit),  # type: ignore[arg-type]
            pytest.raises(BudgetConfigurationError, match="nested"),
            harness.governor.capture(permit),  # type: ignore[arg-type]
        ):
            pass

        client = harness.governor.make_client(
            httpx.MockTransport(lambda _request: httpx.Response(200))
        )
        with pytest.raises(BudgetConfigurationError, match="has no permit"):
            await client.get("https://offline.invalid/no-permit")
    finally:
        await harness.shutdown()


@pytest.mark.parametrize("token", ["not-hex", "AA" * 32])
@pytest.mark.asyncio
async def test_transport_rejects_noncanonical_public_permit_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    token: str,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    client = harness.governor.make_client(httpx.MockTransport(lambda _request: httpx.Response(200)))
    client.event_hooks["request"].clear()
    permit = await _reserve_one(harness)
    invalid = replace(permit, token=token)  # type: ignore[call-overload]
    try:
        with (
            harness.governor.capture(invalid),
            pytest.raises(BudgetConfigurationError, match="permit token"),
        ):
            await client.get("https://offline.invalid/invalid-token")
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_public_reservation_limits_fail_before_creating_extra_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    intent = DispatchIntent("provider", "wikipedia")
    try:
        with pytest.raises(BudgetConfigurationError, match="cannot be empty"):
            await harness.governor.reserve_batch([])
        with pytest.raises(BudgetConfigurationError, match="exact dispatch intents"):
            await harness.governor.reserve_batch([object()])  # type: ignore[list-item]
        with pytest.raises(BudgetConfigurationError, match="outside the admitted bundle"):
            await harness.governor.reserve_batch([DispatchIntent("provider", "tavily")])

        permits = await harness.governor.reserve_batch([intent] * 6)
        assert len(permits) == 6
        with pytest.raises(BudgetExceededError, match="session dispatch budget"):
            await harness.governor.reserve_batch([intent])
        assert harness.control.snapshot()["global_attempts"] == 6
    finally:
        await harness.shutdown()


@pytest.mark.asyncio
async def test_quality_tavily_and_global_rolling_limits_are_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tavily").mkdir()
    tavily_harness = await _prepared_harness(tmp_path / "tavily", monkeypatch)
    quality = A2SQLiteBudgetGovernor(
        tavily_harness.ledger,
        ClosedAlphaSession(_participant(7), _session(7), "quality"),
        boottime=tavily_harness.boottime,
        boot_identity=lambda: BOOT_ID,
        owner_secret=b"q" * 32,
    )
    try:
        await quality.open_session()
        with pytest.raises(BudgetExceededError, match="Tavily session budget"):
            await quality.reserve_batch([DispatchIntent("provider", "tavily")] * 5)
    finally:
        await quality.aclose()
        await tavily_harness.shutdown()

    (tmp_path / "rate").mkdir()
    rate_harness = await _prepared_harness(tmp_path / "rate", monkeypatch)
    second = A2SQLiteBudgetGovernor(
        rate_harness.ledger,
        ClosedAlphaSession(_participant(2), _session(2), "community"),
        boottime=rate_harness.boottime,
        boot_identity=lambda: BOOT_ID,
        owner_secret=b"2" * 32,
    )
    try:
        await rate_harness.governor.reserve_batch([DispatchIntent("provider", "wikipedia")] * 6)
        await second.open_session()
        with pytest.raises(BudgetExceededError, match="rolling request-start budget"):
            await second.reserve_batch([DispatchIntent("provider", "wikipedia")] * 5)
    finally:
        await second.aclose()
        await rate_harness.shutdown()


@pytest.mark.asyncio
async def test_public_provider_and_client_validation_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    exact_bundle = ("arxiv", "crossref", "github", "searxng", "wikipedia")
    try:
        with pytest.raises(BudgetConfigurationError, match="SearXNG fallbacks"):
            harness.governor.validate_provider_configuration(
                exact_bundle,
                ("https://offline.invalid",),
                deployment_profile="community",
            )
        with pytest.raises(BudgetConfigurationError, match="deployment profile"):
            harness.governor.validate_provider_configuration(
                exact_bundle,
                (),
                deployment_profile="quality",
            )
        with pytest.raises(BudgetConfigurationError, match="exact admitted provider bundle"):
            harness.governor.validate_provider_configuration(
                ("wikipedia",),
                (),
                deployment_profile="community",
            )
        with pytest.raises(BudgetConfigurationError, match="audited"):
            harness.governor.validate_provider(object(), httpx.AsyncClient())
        with pytest.raises(BudgetConfigurationError, match="client created by this governor"):
            harness.governor.attach_client(httpx.AsyncClient())
    finally:
        await harness.shutdown()

    with pytest.raises(BudgetConfigurationError, match="fail-closed"):
        harness.governor.validate_provider_configuration(
            exact_bundle,
            (),
            deployment_profile="community",
        )


@pytest.mark.parametrize(
    "rejection",
    ["anchor-type", "inputs", "deadline", "guard-type", "guard-stale", "binding-stale"],
)
@pytest.mark.asyncio
async def test_feedback_publication_public_rejection_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rejection: str,
) -> None:
    harness = await _prepared_harness(tmp_path, monkeypatch)
    await harness.governor.aclose()
    authority = harness.governor.feedback_authority
    binding = harness.store.retention_binding()
    checked = harness.feedback_clock.now.timestamp()
    try:
        if rejection == "guard-type":
            with (
                pytest.raises(BudgetConfigurationError, match="preparation token"),
                harness.governor.feedback_publication_guard(
                    object(),
                    participant_code=_participant(1),
                    session_code=_session(1),
                    checked_at_utc=checked,
                    store_binding=binding,
                ),
            ):
                pass
            return

        anchor = harness.governor.feedback_publication_clock_anchor(store_binding=binding)
        if rejection == "anchor-type":
            with pytest.raises(BudgetConfigurationError, match="clock anchor"):
                harness.governor.prepare_feedback_publication(
                    authority,
                    participant_code=_participant(1),
                    session_code=_session(1),
                    checked_at_utc=checked,
                    purge_at_utc=checked + 20.0,
                    is_new=True,
                    store_binding=binding,
                    clock_anchor=object(),
                )
            return
        if rejection == "inputs":
            with pytest.raises(BudgetConfigurationError, match="inputs"):
                harness.governor.prepare_feedback_publication(
                    authority,
                    participant_code=_participant(2),
                    session_code=_session(1),
                    checked_at_utc=checked,
                    purge_at_utc=checked + 20.0,
                    is_new=True,
                    store_binding=binding,
                    clock_anchor=anchor,
                )
            return
        if rejection == "binding-stale":
            with sqlite3.connect(harness.ledger) as db:
                db.execute(
                    "UPDATE participants SET admission_epoch = admission_epoch + 1 "
                    "WHERE participant_code = ?",
                    (_participant(1),),
                )
                db.commit()
            with pytest.raises(BudgetConfigurationError, match="closed feedback binding"):
                harness.governor.prepare_feedback_publication(
                    authority,
                    participant_code=_participant(1),
                    session_code=_session(1),
                    checked_at_utc=checked,
                    purge_at_utc=checked + 20.0,
                    is_new=True,
                    store_binding=binding,
                    clock_anchor=anchor,
                )
            return
        if rejection == "deadline":
            with pytest.raises(BudgetConfigurationError, match="deadline is too close"):
                harness.governor.prepare_feedback_publication(
                    authority,
                    participant_code=_participant(1),
                    session_code=_session(1),
                    checked_at_utc=checked,
                    purge_at_utc=checked + 5.0,
                    is_new=True,
                    store_binding=binding,
                    clock_anchor=anchor,
                )
            return

        prepared = harness.governor.prepare_feedback_publication(
            authority,
            participant_code=_participant(1),
            session_code=_session(1),
            checked_at_utc=checked,
            purge_at_utc=checked + 20.0,
            is_new=True,
            store_binding=binding,
            clock_anchor=anchor,
        )
        with (
            pytest.raises(BudgetConfigurationError, match="preparation token is stale"),
            harness.governor.feedback_publication_guard(
                prepared,
                participant_code=_participant(2),
                session_code=_session(1),
                checked_at_utc=checked,
                store_binding=binding,
            ),
        ):
            pass
    finally:
        await harness.shutdown()
