from __future__ import annotations

import ast
import asyncio
import copy
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from evidencemesh.closed_alpha_feedback import (
    PURGE_MARGIN,
    ClosedAlphaFeedbackContract,
    ClosedAlphaFeedbackError,
    ClosedAlphaFeedbackStore,
    FeedbackAdmissionError,
    FeedbackContext,
    FeedbackRetentionScheduler,
    FeedbackValidationError,
)

MODULE = Path(__file__).parents[1] / "src/evidencemesh/closed_alpha_feedback.py"
CANDIDATE_SHA = "c1e0be437442b0d97da26f2c9085067a8c09955e"


@dataclass
class FakeClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class FakeAdmission:
    active: set[tuple[str, str]] = field(default_factory=set)
    withdrawn: set[str] = field(default_factory=set)
    contexts: dict[tuple[str, str], FeedbackContext] = field(default_factory=dict)
    feedback_high_water: float | None = None
    privacy_faults: int = 0
    fail_feedback_context: bool = False
    fail_withdrawal_check: bool = False

    def feedback_context(
        self,
        participant_code: str,
        session_code: str,
    ) -> FeedbackContext | None:
        if self.fail_feedback_context:
            raise RuntimeError("synthetic feedback context failure")
        identity = (participant_code, session_code)
        if identity not in self.active or participant_code in self.withdrawn:
            return None
        return self.contexts.get(
            identity,
            FeedbackContext(
                slot_id="C01",
                profile="community",
                provider_attempts=3,
                tavily_attempts=0,
            ),
        )

    def withdrawal_committed(self, participant_code: str) -> bool:
        if self.fail_withdrawal_check:
            raise RuntimeError("synthetic withdrawal check failure")
        return participant_code in self.withdrawn

    def advance_feedback_clock(self, timestamp: float) -> bool:
        if self.feedback_high_water is not None and timestamp < self.feedback_high_water:
            return False
        self.feedback_high_water = timestamp
        return True

    def record_privacy_fault(self) -> None:
        self.privacy_faults += 1


def _participant(index: int) -> str:
    return f"p-{index:016x}"


def _session(index: int) -> str:
    return f"s-{index:032x}"


def _feedback(
    collected_on: date,
    *,
    participant: int = 1,
    session: int = 1,
) -> dict[str, Any]:
    return {
        "schema_version": "evidencemesh.closed-alpha-a0.session.v1",
        "protocol_version": "closed-alpha-a0-v1",
        "candidate_sha": CANDIDATE_SHA,
        "participant_code": _participant(participant),
        "session_code": _session(session),
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


def _store(
    root: Path,
    clock: FakeClock,
    admission: FakeAdmission,
) -> ClosedAlphaFeedbackStore:
    return ClosedAlphaFeedbackStore(
        root,
        ClosedAlphaFeedbackContract(CANDIDATE_SHA),
        admission,
        clock=clock,
    )


def test_create_once_is_private_canonical_idempotent_and_no_clobber(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    root = tmp_path / "feedback"

    with _store(root, clock, admission) as store:
        first = store.put(report)
        second = store.put(copy.deepcopy(report))
        assert first.created is True
        assert second.created is False
        assert first.size_bytes == second.size_bytes
        assert store.get(report["session_code"]) == report
        assert store.reports() == (report,)

        divergent = copy.deepcopy(report)
        divergent["outcome"]["duration_seconds"] = 46
        with pytest.raises(FeedbackValidationError, match="another report"):
            store.put(divergent)

    report_path = root / f"{report['session_code']}.json"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((root / ".feedback.lock").stat().st_mode) == 0o600
    assert report_path.stat().st_nlink == 1
    expected = (
        json.dumps(
            report, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode()
    assert report_path.read_bytes() == expected
    assert sorted(path.name for path in root.iterdir()) == [
        ".feedback.lock",
        f"{report['session_code']}.json",
    ]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda report: report.__setitem__("notes", "private task"),
        lambda report: report.__setitem__("query", "private task"),
        lambda report: report["task"].__setitem__("content", "private task"),
        lambda report: report.__setitem__("candidate_sha", "0" * 40),
        lambda report: report.__setitem__("profile", "quality"),
        lambda report: report["traffic"].__setitem__("provider_attempts", 7),
        lambda report: report["traffic"].__setitem__("provider_errors", 4),
        lambda report: report["traffic"].__setitem__("automatic_retries", 1),
        lambda report: report["grounding_counts"].__setitem__("supported_citations", 5),
        lambda report: report["consent"].__setitem__("confirmed", False),
        lambda report: report["privacy"].__setitem__("raw_runtime_objects_serialized", True),
        lambda report: report["retention"].__setitem__("delete_after", "2026-08-20"),
    ],
)
def test_allowlist_and_semantic_validation_happen_before_any_write(
    tmp_path: Path,
    mutator: Any,
) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    mutator(report)

    with _store(tmp_path / "feedback", clock, admission) as store:
        with pytest.raises(FeedbackValidationError):
            store.put(report)
        assert store.reports() == ()
        assert all(not name.startswith(".feedback-tmp-") for name in os.listdir(store.root))


def test_arbitrary_or_noop_validator_is_rejected_and_admission_is_mandatory(
    tmp_path: Path,
) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())

    def noop_validator(_report: dict[str, Any], *, today: date) -> None:
        assert today == clock.now.date()

    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    with pytest.raises(ClosedAlphaFeedbackError, match="final packaged contract"):
        ClosedAlphaFeedbackStore(
            tmp_path / "noop",
            noop_validator,  # type: ignore[arg-type]
            admission,
            clock=clock,
        )

    not_admitted = FakeAdmission()
    with _store(tmp_path / "not-admitted", clock, not_admitted) as store:
        with pytest.raises(FeedbackAdmissionError, match="not admitted"):
            store.put(report)
        assert store.reports() == ()


def test_contract_requires_exact_candidate_sha_and_validator_cannot_mutate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for invalid in ("", "A" * 40, "0" * 39, "0" * 41):
        with pytest.raises(FeedbackValidationError, match="candidate SHA"):
            ClosedAlphaFeedbackContract(invalid)

    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    original = ClosedAlphaFeedbackContract.validate

    def mutating_validate(
        self: ClosedAlphaFeedbackContract,
        candidate: dict[str, Any],
        *,
        today: date,
    ) -> None:
        original(self, candidate, today=today)
        candidate["candidate_sha"] = "0" * 40

    store = _store(tmp_path / "feedback", clock, admission)
    monkeypatch.setattr(ClosedAlphaFeedbackContract, "validate", mutating_validate)
    with pytest.raises(FeedbackValidationError, match="mutated"):
        store.put(report)
    assert not (store.root / f"{report['session_code']}.json").exists()
    store.close()


def test_purge_boundary_is_sixty_seconds_before_delete_after(tmp_path: Path) -> None:
    collected = date(2026, 7, 31)
    report = _feedback(collected)
    delete_after = datetime(2026, 8, 14, tzinfo=UTC)
    purge_at = delete_after - PURGE_MARGIN
    clock = FakeClock(purge_at - timedelta(microseconds=1))
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})

    with _store(tmp_path / "feedback", clock, admission) as store:
        store.put(report)
        assert store.get(report["session_code"]) == report
        clock.advance(0.000001)
        result = store.purge()
        assert result.checked_at == purge_at
        assert result.deleted == 1
        assert result.next_purge_at is None
        assert store.get(report["session_code"]) is None


def test_startup_access_and_shutdown_each_enforce_purge(tmp_path: Path) -> None:
    collected = date(2026, 7, 31)
    delete_after = datetime(2026, 8, 14, tzinfo=UTC)
    purge_at = delete_after - PURGE_MARGIN

    for phase in ("startup", "access", "shutdown"):
        report = _feedback(collected, session={"startup": 1, "access": 2, "shutdown": 3}[phase])
        root = tmp_path / phase
        clock = FakeClock(purge_at - timedelta(seconds=1))
        admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
        store = _store(root, clock, admission)
        store.put(report)
        store.close()
        assert (root / f"{report['session_code']}.json").exists()
        clock.now = purge_at

        if phase == "startup":
            reopened = _store(root, clock, admission)
            assert reopened.get(report["session_code"]) is None
            reopened.close()
        elif phase == "access":
            reopened = _store(root, FakeClock(purge_at - timedelta(seconds=1)), admission)
            reopened._clock = clock
            assert reopened.reports() == ()
            reopened.close()
        else:
            reopened_clock = FakeClock(purge_at - timedelta(seconds=1))
            reopened = _store(root, reopened_clock, admission)
            reopened_clock.now = purge_at
            reopened.close()
            assert not (root / f"{report['session_code']}.json").exists()


def test_withdraw_is_idempotent_scoped_and_blocks_reappearance(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    first = _feedback(clock.now.date(), participant=1, session=1)
    second = _feedback(clock.now.date(), participant=2, session=2)
    admission = FakeAdmission(
        active={
            (first["participant_code"], first["session_code"]),
            (second["participant_code"], second["session_code"]),
        }
    )

    with _store(tmp_path / "feedback", clock, admission) as store:
        store.put(first)
        store.put(second)
        with pytest.raises(FeedbackAdmissionError, match="not committed"):
            store.withdraw(first["participant_code"])

        admission.withdrawn.add(first["participant_code"])
        assert store.withdraw(first["participant_code"]) == 1
        assert store.withdraw(first["participant_code"]) == 0
        assert store.get(first["session_code"]) is None
        assert store.get(second["session_code"]) == second
        with pytest.raises(FeedbackAdmissionError, match="not admitted"):
            store.put(first)


def test_withdraw_scans_all_owned_reports_without_deleting_another_participant(
    tmp_path: Path,
) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    first = _feedback(clock.now.date(), participant=1, session=1)
    second = _feedback(clock.now.date(), participant=1, session=2)
    other = _feedback(clock.now.date(), participant=2, session=3)
    admission = FakeAdmission(
        active={
            (first["participant_code"], first["session_code"]),
            (second["participant_code"], second["session_code"]),
            (other["participant_code"], other["session_code"]),
        }
    )

    with _store(tmp_path / "feedback", clock, admission) as store:
        store.put(first)
        store.put(second)
        store.put(other)
        admission.withdrawn.add(first["participant_code"])
        assert store.withdraw(first["participant_code"]) == 2
        assert store.get(first["session_code"]) is None
        assert store.get(second["session_code"]) is None
        assert store.get(other["session_code"]) == other


def test_committed_withdrawal_is_recovered_by_startup_after_crash(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    first = _feedback(clock.now.date(), participant=1, session=1)
    second = _feedback(clock.now.date(), participant=1, session=2)
    other = _feedback(clock.now.date(), participant=2, session=3)
    admission = FakeAdmission(
        active={
            (first["participant_code"], first["session_code"]),
            (second["participant_code"], second["session_code"]),
            (other["participant_code"], other["session_code"]),
        }
    )
    root = tmp_path / "feedback"
    store = _store(root, clock, admission)
    store.put(first)
    store.put(second)
    store.put(other)
    store.close()

    # The registry commit survives, while the process that should have called
    # store.withdraw() is simulated as having crashed before doing so.
    admission.withdrawn.add(first["participant_code"])
    reopened = _store(root, clock, admission)
    try:
        assert reopened.get(first["session_code"]) is None
        assert reopened.get(second["session_code"]) is None
        assert reopened.get(other["session_code"]) == other
    finally:
        reopened.close()


def test_authoritative_context_binds_slot_profile_and_traffic_counts(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    identity = (report["participant_code"], report["session_code"])
    mismatches = (
        FeedbackContext("C02", "community", 3, 0),
        FeedbackContext("Q01", "quality", 3, 0),
        FeedbackContext("C01", "community", 2, 0),
    )
    for index, context in enumerate(mismatches, start=1):
        admission = FakeAdmission(active={identity}, contexts={identity: context})
        with _store(tmp_path / f"mismatch-{index}", clock, admission) as store:
            with pytest.raises(FeedbackAdmissionError, match="authoritative context"):
                store.put(report)
            assert store.reports() == ()

    quality = _feedback(clock.now.date(), participant=7, session=7)
    quality["slot_id"] = "Q01"
    quality["profile"] = "quality"
    quality["traffic"]["tavily_attempts"] = 1
    quality_identity = (quality["participant_code"], quality["session_code"])
    tavily_mismatch = FakeAdmission(
        active={quality_identity},
        contexts={quality_identity: FeedbackContext("Q01", "quality", 3, 0)},
    )
    with (
        _store(tmp_path / "tavily-mismatch", clock, tavily_mismatch) as store,
        pytest.raises(FeedbackAdmissionError, match="authoritative context"),
    ):
        store.put(quality)


def test_persisted_clock_high_water_erases_on_rollback_after_reopen(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    root = tmp_path / "feedback"
    store = _store(root, clock, admission)
    store.put(report)
    store.close()
    report_path = root / f"{report['session_code']}.json"
    assert report_path.exists()

    clock.advance(-1)
    with pytest.raises(ClosedAlphaFeedbackError, match="across restart"):
        _store(root, clock, admission)
    assert not report_path.exists()
    assert admission.privacy_faults == 1


@pytest.mark.parametrize("failed_callback", ["withdrawal", "context"])
def test_reconciliation_callback_failure_poison_store_and_records_privacy_fault(
    tmp_path: Path,
    failed_callback: str,
) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    root = tmp_path / failed_callback
    store = _store(root, clock, admission)
    store.put(report)

    if failed_callback == "withdrawal":
        admission.fail_withdrawal_check = True
        failure = "withdrawal check failed"
    else:
        admission.fail_feedback_context = True
        failure = "context check failed"

    with pytest.raises(ClosedAlphaFeedbackError, match=failure):
        store.purge()
    assert (root / f"{report['session_code']}.json").exists()
    assert admission.privacy_faults == 1
    with pytest.raises(ClosedAlphaFeedbackError, match="fail-closed"):
        store.reports()
    with pytest.raises(ClosedAlphaFeedbackError, match="fail-closed"):
        store.close()
    assert admission.privacy_faults == 1


def test_public_root_and_symlinked_ancestor_fail_closed(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    admission = FakeAdmission()
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    with pytest.raises(ClosedAlphaFeedbackError, match="unsafe"):
        _store(public, clock, admission)

    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ClosedAlphaFeedbackError, match="anchor"):
        _store(linked_parent / "feedback", clock, admission)
    assert admission.privacy_faults == 2


def test_report_symlink_and_hardlink_are_never_followed(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    root = tmp_path / "feedback"
    store = _store(root, clock, admission)
    outside = tmp_path / "outside.json"
    outside.write_text("do not touch", encoding="utf-8")
    (root / f"{report['session_code']}.json").symlink_to(outside)
    with pytest.raises(ClosedAlphaFeedbackError):
        store.purge()
    with pytest.raises(ClosedAlphaFeedbackError):
        store.close()
    assert outside.read_text(encoding="utf-8") == "do not touch"

    hard_root = tmp_path / "hard-feedback"
    hard_store = _store(hard_root, clock, admission)
    hard_store.put(report)
    hard_path = hard_root / f"{report['session_code']}.json"
    external_link = tmp_path / "external-hardlink.json"
    os.link(hard_path, external_link)
    with pytest.raises(ClosedAlphaFeedbackError, match="metadata"):
        hard_store.reports()
    external_link.unlink()
    with pytest.raises(ClosedAlphaFeedbackError):
        hard_store.close()


def test_identical_concurrent_writers_publish_one_complete_file(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    root = tmp_path / "feedback"
    first = _store(root, clock, admission)
    second = _store(root, clock, admission)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda store: store.put(report), (first, second)))
        assert sorted(result.created for result in results) == [False, True]
        assert first.reports() == (report,)
        path = root / f"{report['session_code']}.json"
        assert path.stat().st_nlink == 1
        assert not any(name.startswith(".feedback-tmp-") for name in os.listdir(root))
    finally:
        first.close()
        second.close()


def test_publish_failure_leaves_no_partial_report_or_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    root = tmp_path / "feedback"
    store = _store(root, clock, admission)

    def fail_link(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic link failure")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(ClosedAlphaFeedbackError, match="publish"):
        store.put(report)
    assert not (root / f"{report['session_code']}.json").exists()
    assert not any(name.startswith(".feedback-tmp-") for name in os.listdir(root))
    with pytest.raises(ClosedAlphaFeedbackError):
        store.close()


def test_clock_regression_erases_reports_and_poison_store(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 31, 12, tzinfo=UTC))
    report = _feedback(clock.now.date())
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    root = tmp_path / "feedback"
    store = _store(root, clock, admission)
    store.put(report)
    clock.advance(-1)

    with pytest.raises(ClosedAlphaFeedbackError, match="backwards"):
        store.purge()
    assert not (root / f"{report['session_code']}.json").exists()
    assert admission.privacy_faults == 1
    with pytest.raises(ClosedAlphaFeedbackError):
        store.close()


@pytest.mark.asyncio
async def test_scheduler_uses_fake_clock_and_purges_at_guarded_deadline(tmp_path: Path) -> None:
    collected = date(2026, 7, 31)
    report = _feedback(collected)
    purge_at = datetime(2026, 8, 14, tzinfo=UTC) - PURGE_MARGIN
    clock = FakeClock(purge_at - timedelta(seconds=61))
    admission = FakeAdmission(active={(report["participant_code"], report["session_code"])})
    store = _store(tmp_path / "feedback", clock, admission)
    store.put(report)
    stop = asyncio.Event()
    waits: list[float] = []

    async def fake_wait(seconds: float) -> None:
        waits.append(seconds)
        clock.advance(seconds)
        if len(waits) == 4:
            stop.set()

    scheduler = FeedbackRetentionScheduler(store, wait=fake_wait, poll_interval_seconds=30)
    await scheduler.run(stop)

    assert waits[:3] == [30.0, 30.0, 1.0]
    assert store.get(report["session_code"]) is None
    store.close()


def test_module_has_no_network_process_environment_or_content_logging_capability() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    calls: set[str] = set()
    attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)

    assert imported_roots.isdisjoint(
        {"aiohttp", "httpx", "logging", "requests", "socket", "subprocess", "urllib"}
    )
    assert calls.isdisjoint({"eval", "exec", "getenv", "popen", "print", "system", "urlopen"})
    assert attributes.isdisjoint({"environ", "environb"})
