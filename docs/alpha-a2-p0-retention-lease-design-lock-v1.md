# EvidenceMesh Alpha A2-P0 retention lease design lock v1

## Decision

**A2-P0 locks a design only.** It does not implement, execute, or authorize a
live closed alpha. The accepted target is a future single-host Ubuntu control
plane in which the retention supervisor owns one durable lease and every
dispatch authority fails closed when that lease is absent, stale, failed,
foreign, or bound to another host boot.

The exact parent is the A1 documentary seal commit
`c07d4af581f20b782fc59287b0ea008ef80c8cce`, tree
`0e0de23d86a73ef94790568a818382d7f888a0ae`. The runtime candidate remains
EvidenceMesh 0.1.0 at `145f5f923825ffeaeb485bd680bc79410ab290d1`,
tree `3b36c2d3970a5e3c325a2b20260daabf23d33a29`. A1 remains an immutable
historical acceptance for its exact identities. A later implementation that
changes product source creates a new, not-evaluated candidate and must earn
separate installability and interoperability evidence.

## Observed blocking gap

The current control plane already has strong local controls. It has one private
SQLite ledger, the three states `paused`, `prepared`, and `stopped`, monotonic
control/admission/session epochs, single-use dispatch permits, a per-session
owner and 300-second lease, crash quarantine, durable privacy-fault handling,
atomic reservation, and a second validation at the first HTTPX request hook.

That session lease is renewed at reservation and request dispatch. It proves
that one session owner has recently interacted with the ledger; it does not
prove that feedback retention is still supervised. The current
`FeedbackRetentionScheduler` repeatedly purges a `ClosedAlphaFeedbackStore`
and purges once more on exit, but it has no identity or heartbeat in the
control-plane ledger. Consequently, `prepared`, reservation, and the request
hook cannot distinguish a healthy retention scheduler from one that was never
started, stopped, stalled, or failed.

There are two additional consequences of the same supervision gap. Session
leases are refreshed only by reservation and request activity: there is no
autonomous owner-fenced heartbeat and no independent reconciliation loop.
Traffic can therefore mask the death of the session owner, while an idle or
CPU-bound but healthy owner provides no liveness proof. In addition,
`_close_session_sync()` does not reconcile expiry first, so an expired but
unreconciled session can currently take the normal `active` to `closed` path
instead of `recovery_required`.

This is the actual live-adoption blocker. It does not invalidate A1 because A1
contains zero tester and live sessions. It does prevent treating the existing
RC4 controls as sufficient for a live closed alpha. The historical phrase
"absence of heartbeat or lease" is interpreted precisely here: the session
lease exists; autonomous session supervision and the distinct retention-
supervisor lease do not.

## Two independent supervision loops

The future control plane has two non-substitutable loops:

1. A singleton **retention supervisor** owns the global lease, runs a successful
   feedback purge, reconciles every active session lease, and only then renews
   its own lease. It proves that retention and expiry reconciliation continue.
2. Each active session has an autonomous **session heartbeat** around the
   existing session lease. It proves that the exact session owner remains
   alive independently of reservation, provider, transport, or idle activity.

The retention supervisor must not renew a session lease. A session heartbeat,
reservation, provider call, request hook, or transport departure must not renew
the retention-supervisor lease. In the target design, reservation and traffic
also stop renewing the session lease: otherwise traffic could indefinitely
mask a dead session heartbeat. No second session lease is introduced.

## Separate global supervisor lease

The future implementation must add one lease per ledger for the retention
supervisor. It is separate from all session leases and cannot be renewed by a
session, a reservation, a provider call, or an HTTPX hook.

The supervisor creates a 256-bit owner secret and persists only its SHA-256
digest. Each acquisition increments a durable `supervisor_epoch`; each
successful renewal increments a heartbeat sequence. The ledger stores only the
owner digest, supervisor epoch, heartbeat sequence, hashed host-boot identity,
boottime issue/heartbeat/expiry values, the existing high-water UTC value, and
a bounded fault code.
Participant identifiers, queries, tasks, URLs, provider results, payloads,
credentials, raw tokens, and raw exception messages are forbidden.

The maximum purge-and-heartbeat interval is 10 seconds and the lease lifetime
is 30 seconds. The lifetime therefore covers three maximum intervals, but the
lease is authority, not a target. Every authority gate requires strictly more
than five seconds of remaining freshness; equality is expired. There is no
grace period, override, or retry. Lease expiry is also capped by the next
mandatory feedback-purge deadline. The existing 60-second purge margin is
preserved. New departure authority ends no later than
`min(last_successful_heartbeat + 25 seconds, next_purge_at - 5 seconds)`.
Because `next_purge_at` precedes `delete_after` by 60 seconds, the
deadline-capped path leaves at least 65 seconds. This bounds authorization
only; it does not prove deletion while no process runs.

Lease acquisition is allowed only while the control plane is `paused`. A
current lease blocks a second owner. Expiry never grants automatic takeover:
the ledger first pauses, increments the control epoch, invalidates reserved
permits, quarantines active sessions, and requires explicit recovery. A
heartbeat can renew its own current lease; it cannot enter `prepared`, change
admission, refund budget, repair recovery rows, or unpause the ledger.

## Existing session lease under autonomous supervision

The existing 300-second session lease remains the single session-liveness
authority. Its new heartbeat interval is at most 100 seconds (`lease / 3`). A
heartbeat is accepted only for the exact owner digest, `session_epoch`,
`admission_epoch`, `control_epoch`, and boot identity. An owner, epoch,
admission, or boot mismatch can never renew it.

After an operator enters `prepared`, the heartbeat component calls an explicit
`open_session`. Under one `BEGIN IMMEDIATE`, it reconciles leases, validates the
current supervisor lease and boot, control state, admission, exact owner,
epochs, policy, and budgets, then creates the active session and its first
durable heartbeat atomically. Failure before commit creates no session;
failure after commit can only lead to expiry and quarantine. `reserve_batch`
must no longer create a session, and it returns no permit unless this exact
open path already succeeded.

Subsequent lease renewals come only from the autonomous heartbeat; reservation
and request activity may record use but may not extend expiry. A stale
heartbeat cannot take over, close, recover, or pause another owner's session.
Missing heartbeat is detected both at authority gates and by the retention
supervisor's independent reconciliation cycle, whose maximum interval is ten
seconds.

Normal close is also an authority boundary. Under `BEGIN IMMEDIATE`, it first
reconciles the global and exact session leases and validates the exact owner
and epochs. An expired session must transition to `recovery_required`, pause
the ledger, increment `control_epoch`, and invalidate reserved permits. It must
never take the ordinary `active` to `closed` path. Recovery and final closure
remain explicit operator actions and never refund a budget.

## Clock and restart boundary

Dispatch authority uses Linux `CLOCK_BOOTTIME`, not wall time. Suspension is
therefore included in lease age. The lease also binds a SHA-256 digest of the
Linux boot identity. There is no fallback clock: an unavailable or malformed
boot identity, unsupported clock, regression, or boot change fails closed.
Retention deadlines continue to use the store's non-regressing high-water UTC;
wall time never grants dispatch authority.

After a reboot or a process restart with a stale lease, the control plane must
pause, increment its epoch, invalidate outstanding permits, and require
operator recovery. It must never infer liveness from a persisted future expiry
or resume automatically.

## Heartbeat, retention, and lock ordering

The supervisor first runs one successful retention pass and advances the
store's durable high-water clock, then reconciles every active session, and
only then commits its first heartbeat. Every later renewal follows the same
order. An empty purge is a successful pass; a skipped, cancelled, timed-out,
or failed pass is not.

During the purge, the existing one-way order is preserved: feedback-store
lock, then bounded admission/high-water SQLite callbacks that never acquire the
feedback-store lock, then release the feedback-store lock. Only after
`purge()` returns may the supervisor open the separate `BEGIN IMMEDIATE`
transaction that reconciles sessions and acquires or renews its lease. A
control, session, or lease transaction must never acquire the feedback-store
lock. Feedback publication uses the same one-way direction: while holding the
store lock, its final bounded SQLite authorization callback may validate the
lease and session but can never call back into the store.

Recoverable liveness lapse and permanent integrity fault are distinct. Missed
heartbeat, ordinary expiry, process crash, reboot, unexpected cancellation, or
incomplete orderly stop creates no permanent marker. At first reconciliation,
it pauses, increments the control epoch, invalidates permits, quarantines
sessions, and requires explicit operator recovery. Expiry does not mutate
SQLite by itself while no process runs.

Clock regression, ledger/store identity drift, a privacy fault, an invalid
marker, or a confirmed renewal by the wrong owner in the same epoch is a
permanent integrity fault. It records a durable private marker and makes the
ledger non-preparable. A second acquisition while a current lease exists is
merely denied; a stale heartbeat is fenced and cannot itself create a permanent
split-brain fault. The marker is a regular owner-only, versioned file with a
distinct suffix and ledger binding. No supported runtime API may clear it;
same-UID operator tampering is outside the claimed boundary. Marker ambiguity
is fail-closed.

If the ledger is inaccessible, mandatory ledger access at every authority
checkpoint blocks dispatch and the unrenewed lease supplies an independent
authorization cutoff.

Orderly shutdown completes a final purge, then atomically pauses and revokes
before releasing the task. If either stage fails, it does not renew and the
lease follows the recoverable expiry path. No `finally` path may silently
renew, suppress a scheduler exception, or leave `prepared` active.

## Four mandatory authority checkpoints

### Transition to `prepared`

Under the same SQLite write transaction, reconcile expired session and
supervisor leases, validate the boot identity and clock, require a current
supervisor lease with more than five seconds remaining and a fresh successful
retention pass, require both privacy and supervisor-fault markers absent, and
require zero recovery row. Every active session must also have a current,
autonomously heartbeating owner. Only then may the existing compare-and-swap
transition bind the supervisor epoch, increment the control epoch, and enter
`prepared`.

### Atomic reservation

Before inserting an attempt row, repeat supervisor and session reconciliation.
Validate more than five seconds of supervisor freshness, the current supervisor
epoch, boot identity, control state, admission, autonomous session heartbeat,
session owner and epoch, policy, and budget in the same transaction. Bind the
supervisor epoch into every permit. No permit may be returned until the first
autonomous session heartbeat is durable. Dispatch activity must extend neither
lease.

### Governed transport departure

The current HTTPX request hook remains an early poison-pill check, but it is not
the final security boundary: another hook can run after it. A governed HTTPX
transport must therefore atomically consume one permit immediately before
delegating to its inner transport, and only if the permit's supervisor epoch
still matches a lease with strictly more than five seconds remaining and all
existing state, admission, session, policy, budget, boot, and fault checks
pass. A client belongs to exactly one governor and session. Environment proxy
inheritance, HTTP/2, automatic redirects, and transport retries are disabled.
Every invocation delegated to the governed HTTPX inner transport, including a
redirect, authentication replay, retry, or follow-up, requires a separately
reserved permit. The claim does not count DNS packets, TCP attempts, or other
activity internal to that delegated invocation as separate permits.

Successful transport-boundary consumption is the dispatch linearization point.
A pause or lease fault that linearizes later blocks subsequent departures but
cannot recall bytes already handed to transport. This design intentionally
rejects any stronger and false "zero packet after revocation" claim.

### Feedback publication

`ClosedAlphaFeedbackStore.put()` must validate the same current supervisor
lease with strictly more than five seconds remaining, epoch, boot identity,
high-water clock, and fault state immediately before the atomic `os.link`
publication and before returning an identical replay. A temporary file may be
prepared before the gate but is removed if the gate fails. A session-originated
report additionally requires the exact current session owner and epochs.
Purge, read-for-deletion, withdrawal, and recovery remain possible without a
live lease so failure cannot block privacy cleanup.

## Failure and concurrency semantics

At first reconciliation, a recoverable lapse must atomically pause where the
ledger is available, increment the control epoch, invalidate every reserved
permit, and mark active sessions `recovery_required`. Attempt and session rows
remain durable and no budget is refunded. A permanent integrity fault performs
the same containment and additionally leaves the durable marker that ordinary
recovery cannot clear.

Retention heartbeat, session heartbeat, operator pause, reservation, recovery,
normal close, feedback publication, and transport-boundary operations use
compare-and-swap identities under SQLite transactions. A stale owner or
heartbeat loses the comparison and is durably fenced without renewing. Only a
confirmed same-epoch contradictory owner is a permanent integrity fault. There
is no automatic retry, takeover, resume, or exception suppression.

## Process-supervision boundary

The lease bounds authorization after a dead supervisor; it cannot itself purge
data while no process runs. Before any live closed alpha, the singleton must be
wired as a dedicated local service under an OS supervisor, with startup after
storage validation, bounded restart, and explicit stop-to-pause ordering. A
restarted service may immediately purge and reconcile while dispatch remains
blocked, but it must acquire a new epoch only through paused operator recovery.
The implementation gate must prove both daemon wiring and purge after
supervised restart. Until then, continuous deletion after process death remains
unproved and live use stays `NO-GO`.

Recovery order is fixed: reconcile the stale lease into `paused` and quarantine
old sessions; explicitly resolve or close those sessions; complete a successful
purge; acquire a new supervisor epoch while still `paused`; perform an operator
CAS to `prepared`; then open only new sessions through `open_session`. No old
session or permit resumes automatically.

## Implementation acceptance boundary

A separately authorized implementation gate must adversarially cover at least:

- preparation racing expiry;
- reservation racing expiry;
- transport-boundary consumption racing expiry or scheduler failure;
- retention heartbeat racing pause, takeover, cancellation, and reboot drift;
- autonomous session heartbeat racing reservation, close, admission drift,
  expiry, and owner or epoch replacement;
- an idle or CPU-bound session whose provider activity cannot prove liveness;
- expired-but-unreconciled session close taking only `recovery_required`;
- feedback publication and identical replay racing lease expiry;
- clock rollback and stale persisted lease data;
- redirects, follow-ups, pooled clients, custom transports, and retries;
- daemon death and supervised restart without automatic resume;
- marker, ledger, owner, epoch, and storage-identity corruption; and
- restart recovery without deletion of attempt/session rows, refund, or
  automatic resume.

Those tests remain offline with a fake clock, fake boot identity, and
`httpx.MockTransport`; they must observe zero real network request. The future
implementation must also pass an installed-distribution smoke and create a new
product candidate. This design lock does not authorize that code change or
reclassify the current branch product.

The implementation uses a new ledger schema version. A v2 ledger must be
refused explicitly: it is neither silently migrated nor reset, and no old lease
value is treated as comparable. Migration tooling, if ever required, is a
separate operator-authorized gate.

## Entry, publication, and stop criteria

The gate requires open draft PR #1, branch `agent/evidencemesh-v0.1`, with
`c07d4af581f20b782fc59287b0ea008ef80c8cce` as the exact direct parent. Its
only changed paths are this protocol and
`alpha/alpha-a2-p0-retention-lease-design-lock-policy-v1.json`. Product,
runtime, dependency, workflow, test, benchmark, and historical evidence files
remain byte-identical.

Stop if either path or identity drifts; any runtime behavior or source changes;
the design describes the existing session lease as absent, reuses it as the
retention lease, permits traffic to renew it, or omits its autonomous
heartbeat; one of the four checkpoints or normal close can fail open; the
request hook is claimed as the final transport boundary; feedback publication
can succeed without a current lease; lock ordering is ambiguous; a retention
heartbeat can unpause, refund, or renew without a successful retention pass;
restart,
expiry, cancellation, split brain, clock, redirect, retry, pooled-client, or
storage behavior is ambiguous; private content enters the audit; or a real
request or live session is needed. Stop on any failed synchronization
workflow, with no rerun.

The maximum is one additive commit, two files, one fast-forward ref update,
ordinary pull-request CI, zero authorization label, zero retry or historical
rerun, zero provider/search/model/document/benchmark/tester request, zero live
session, and zero product runtime-network request. No artifact, tag,
distribution, release, merge, deployment, Phase 11.9, Phase 12, V1, quality, or
production claim is authorized.

## Result boundary

A pass means only `retention_and_session_liveness_design_locked`. Session
liveness is included because the retention supervisor promises independent
session-expiry reconciliation; leaving its heartbeat undefined would make that
promise false. The result closes design-choice ambiguity and defines the
fail-closed implementation contract. It does not close the implementation
blocker. PR #1 remains draft, and the A1 technical freeze remains the latest
accepted runtime result.
