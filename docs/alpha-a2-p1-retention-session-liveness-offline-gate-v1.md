# EvidenceMesh Alpha A2-P1 retention/session liveness offline gate v1

## Decision state

**A2-P1 is an offline implementation gate whose final seal is still pending.**
It implements the A2-P0 retention and session-liveness design as a separate,
additive v3 control-plane path. It does not activate a service, contact a live
provider or model, publish a distribution, authorize Phase 12, or establish
production or V1 readiness.

The exact immutable parent is commit
`4044840fb3c79d2b65ff1ce7d3c96be423b331b5`, tree
`e9d54fef97c583f70dd00d4c095898e545ef6fed`, on
`agent/evidencemesh-v0.1`. The final A2-P1 commit, tree, workflow run, and CI
conclusion are deliberately recorded as `pending_until_seal`; no provisional
local result may replace those identities.

## Entry and scope lock

The candidate must descend linearly from the exact parent by no more than two
commits and may change at most twelve files relative to that parent. The scope
is limited to the additive v3 liveness implementation, the narrow feedback
publication bridge required by that implementation, deterministic offline
tests, this gate's policy/evidence text, and its dedicated one-shot offline
workflow.

The A2 path must create a fresh private SQLite ledger with schema
`evidencemesh.closed-alpha-control-plane.v3`. An existing ledger, including an
RC4 v2 ledger, is refused unchanged. A2-P1 provides no v2-to-v3 migration,
in-place upgrade, implicit reset, automatic deletion, or fallback to v2.
Historical v2 behavior outside the explicit A2 path is not reclassified by
this gate.

The maximum execution/publication budget is:

- two candidate commits;
- twelve changed files;
- zero EvidenceMesh runtime network requests;
- zero live provider, search, document, or model requests;
- zero live tester session and zero operating-system service activation;
- zero retry and zero workflow rerun used to reinterpret a failure;
- zero artifact, distribution, release, or tag publication.

Exceeding any maximum is a stop, not a reason to widen the claim.

## Additive v3 authority model

The v3 ledger binds authority to Linux boottime, a hashed boot identity, the
control and admission epochs, a singleton retention-supervisor epoch, and the
exact session owner and session epoch. Raw owner secrets are never persisted.
It also durably binds the authoritative feedback store by directory
device/inode and candidate commit/tree; a decoy, replaced, or foreign store is
not eligible to supervise retention or publish feedback.
The design remains single-host and local; it makes no distributed-liveness or
cross-host consistency claim.

The retention supervisor and each session have independent heartbeat domains:

1. The singleton supervisor runs a successful retention pass, reconciles
   session expiry, and only then acquires or renews its 30-second lease. Its
   maximum heartbeat interval is 10 seconds, and every authority checkpoint
   requires strictly more than five seconds of freshness.
2. The exact session owner renews the existing 300-second session lease through
   an autonomous heartbeat at no more than 100-second intervals. Reservation,
   provider activity, request hooks, transport activity, and supervisor work do
   not renew that lease.

Owner digests, boot identity, supervisor/session/control/admission epochs, and
heartbeat sequence values are compare-and-swap fences. A stale or foreign
heartbeat cannot acquire authority. An ordinary lapse pauses authority,
invalidates reserved permits, quarantines active sessions for explicit
recovery, and never refunds budget. Boot or clock integrity faults remain
fail-closed. Every authority checkpoint also revalidates the immutable ledger
metadata and rejects lease issue/heartbeat timestamps later than the current
boottime; either corruption commits a durable fault before refusing authority.
Supervisor acquisition and renewal complete behind a cancellation shield; a
committed lease is recorded before cancellation is re-propagated. Final close
also discovers and contains an exact owned epoch even if process-local lease
state was interrupted before assignment.

## Authority checkpoints and final transport boundary

The `prepared` transition, atomic reservation, governed transport departure,
and feedback publication each repeat the relevant supervisor, session, state,
epoch, boot, fault, policy, and budget checks in the transaction that grants
their authority.

The final network authority boundary is a governed HTTPX transport wrapper,
not an event hook. It consumes one exact permit immediately before delegating
one invocation to its inner transport. A pause, stale lease, epoch drift,
foreign owner, reused permit, or failed check prevents delegation. Redirects,
automatic retries, HTTP/2, and environment-proxy inheritance are not enabled;
every separately delegated follow-up would require another permit. An early
request hook may remain a poison-pill check, but it is not credited as the
linearization point.

This gate exercises that wrapper only over `httpx.MockTransport`. No socket,
DNS, provider adapter, live model, or external endpoint is authorized.
Document fetching is deliberately unavailable on this offline A2 path: the
built-in guard refuses resolution before DNS and rejects a custom resolver.
Adding a DNS-aware governed document resolver is a separate future gate, not
an inferred permission in A2-P1.

## Crash-safe feedback publication

Feedback cleanup, withdrawal, and recovery must remain possible without a live
lease. Creating a report or accepting an identical replay, however, requires
the exact A2 publication authority and a current supervisor/session binding.

For a new report, the store stages and fsyncs the private temporary file before
the final authorization. Publication then uses two SQLite phases while the
feedback-store lock remains held:

1. A durable preparation transaction validates the authority and commits a
   lease fence before publication. The fence must change the relevant CAS
   token even when the numeric expiry cap would otherwise remain unchanged, so
   a heartbeat holding the earlier snapshot cannot later extend past the cap.
2. A fresh transaction revalidates the exact authority and is held open through
   the atomic `os.link` publication. An identical replay crosses the same final
   guard. A failure never converts a partial authorization into a pass.

Before observing the store's UTC retention clock, publication captures a
single-use boottime anchor. The deletion cap is derived from that earlier
anchor, so SQLite waiting, report validation, staging, and fsync latency can
only shorten the usable lease and can never move the real purge deadline
later.

The separate retention path performs the purge and captures the supervisor
heartbeat/expiry CAS snapshot before releasing the feedback-store lock. Its
boottime anchor is likewise captured before the UTC purge observation. Lease
acquisition or renewal occurs only after release and succeeds only against the
captured snapshot. Orderly shutdown is different by design: after its final
purge it pauses and revokes the exact owner+supervisor epoch while the same
store lock is still held, accepting only the current sequence/expiry read in
that transaction. This prevents a publication fence from slipping between the
final purge and containment. No control-plane path calls back into the store
while holding SQLite, preserving the one-way store-to-SQLite lock order.

Closed-session feedback context is durable and global to the ledger rather
than a single governor object. Restarted governor instances and concurrent
sessions therefore preserve their own exact authorities, while withdrawal,
fault, stop, expiry, or epoch drift invalidates them fail-closed.

## Offline verification contract

All A2-P1 tests use injected fake boottime, fake boot identity, bounded local
SQLite/filesystem fixtures, deterministic task scheduling, and
`httpx.MockTransport`. Sleeps, wall-clock timing, DNS, sockets, live endpoints,
credentials, and external provider/model semantics are not acceptance oracles.

The sealed suite must cover at least:

- fresh v3 bootstrap and unchanged refusal of an existing v2 ledger;
- supervisor and session owner/epoch/sequence fencing, lapse containment, and
  explicit recovery;
- the rule that traffic cannot substitute for either autonomous heartbeat;
- all four authority checkpoints, including final transport consumption;
- pause, expiry, stale-heartbeat, replay, link-failure, and concurrent
  publication races;
- the two-phase feedback fence, conservative pre-UTC time anchors, exact
  store binding, and retention CAS snapshot captured under the store lock;
- atomic final-purge shutdown, restart/multi-session feedback continuity,
  immutable-metadata drift, and future-timestamp faults;
- deterministic refusal of A2 document resolution before any DNS or attempt;
- preservation of offline cleanup and of the pre-existing RC4 test contract.

Local tests are diagnostic until the exact candidate is sealed. The canonical
CI run identifier, CI conclusion, final commit SHA, and final tree SHA are all
`pending_until_seal`.

The dedicated pull-request workflow accepts only PR #1's exact draft branch,
run attempt 1, the locked parent/tree, one or two linear commits, and the exact
ten-file allowlist. Dependency setup happens before isolation; format, lint,
typing, the focused A2-P1 suite, and historical RC4 regressions then execute in
a network namespace with no network interface. It has no manual-dispatch,
artifact, build, distribution, service, retry, or rerun path. The successful
run attached to the exact HEAD/tree plus a PR receipt is the seal; evidence is
not self-referentially written into that same commit.

## Stop criteria

Stop without retry or reinterpretation if the parent identity, two-commit
limit, twelve-file limit, v3-only bootstrap rule, lock order, CAS fencing,
heartbeat independence, final-transport boundary, or offline containment
drifts. Stop if a deadline is derived from a boottime observation later than
its corresponding UTC observation, if orderly shutdown releases the store lock
before owned-epoch containment, or if A2 document fetching can resolve a name.
Stop on any existing-ledger migration or reset, any live/network
request, any provider/model execution, any OS service activation, any required
test or quality failure, or any artifact/distribution/tag/release publication.

## Claim boundary

A future sealed pass may establish only that the A2-P0 retention/session
liveness design is implemented and deterministically exercised on the locked
offline single-host path. It does not establish real OS supervision, behavior
under a live provider or model, live closed-alpha safety, distribution
installability of the new candidate, Phase 12 readiness, production fitness,
or V1 readiness. Each of those remains a separate, explicitly authorized gate.
