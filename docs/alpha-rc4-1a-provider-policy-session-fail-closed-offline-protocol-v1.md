# EvidenceMesh Alpha-RC4.1A provider/policy/session fail-closed offline protocol v1

## Decision boundary

Alpha-RC4.1A is one bounded correction and validation pass over the accepted
offline RC4 implementation. Its exact base is commit
`61a58660cb77ba160e8ecfed53d09fdcd1d60c57`, tree
`6a7424d4d8391c64a0ebb0c0445b8d85c8d7a5fe`. The correction commit must be its
single direct child and is limited to the closed fail-closed implementation,
its adversarial tests and the four RC4.1A offline control artifacts.

This phase is not an exact-HEAD acceptance, attestation, seal, closed-alpha
adoption or live decision. It authorizes no provider, model, tester or live
request; no secret; no artifact or attestation; no binary distribution; and no
merge, release, quality or production-readiness claim. Pull request 1 remains
open and draft. At most one branch update is authorized and no automatic retry,
fallback, repair or follow-up update is authorized.

## Entry criteria

Work may start only when all of the following remain true:

1. the repository is `VynoDePal/EvidenceMesh` and pull request 1 is open, draft,
   same-repository and headed by `agent/evidencemesh-v0.1`;
2. the checked-out head has the exact RC4 base as its only parent and Git resolves
   that base to the frozen tree above;
3. the changed paths and statuses are exactly the thirteen-file RC4.1A allowlist;
4. historical A0 and RC3 evidence, the RC4 offline protocol and policy,
   `pyproject.toml` and `uv.lock` remain byte-identical to the base;
5. the correction and all of its validation can complete with synthetic local
   inputs and an empty network namespace; and
6. no provider or model credential, tester contact, package upload or additional
   branch update is needed.

The allowed runtime and adversarial-test corrections are:

- `src/evidencemesh/__init__.py`;
- `src/evidencemesh/closed_alpha_feedback.py`;
- `src/evidencemesh/engine.py`;
- `src/evidencemesh/governor.py`;
- `tests/test_alpha_rc4_control_plane.py`;
- `tests/test_alpha_rc4_feedback.py`; and
- `tests/test_alpha_rc4_integration.py`.

Compatibility with the new identity constructor additionally requires bounded
updates to `.github/workflows/alpha-rc4-control-plane-offline.yml` and
`tests/test_alpha_rc4_workflow.py`. Those two updates may replace only the old
raw-SHA wheel smoke and its static expectations; they do not alter or rerun the
historical RC4 protocol or policy decision.

The only allowed new control artifacts are this protocol,
`alpha/closed_alpha_rc4_1a_provider_policy_session_fail_closed_policy_v1.json`,
`.github/workflows/alpha-rc4-1a-provider-policy-session-fail-closed-offline.yml`
and `tests/test_alpha_rc4_1a_workflow.py`.

## Identity correction

`ClosedAlphaFeedbackIdentity` is the only package-owned identity accepted by
the corrected feedback contract through the supported API. It is loaded from a
bounded public acceptance record whose expected SHA-256 is supplied
independently. The selected archive must be exactly one accepted distribution
subject ending in `.whl` or `.tar.gz`; its name and digest, the same installed
distribution's `direct_url.json`, and the distribution entry that resolves to
the actually imported `closed_alpha_feedback.py` module must all agree. A
caller using the supported constructor surface cannot substitute a raw
candidate SHA for those verified files.

Identity loading fails closed on record digest drift, invalid candidate SHA or
tree, an attestation inventory other than the three required statements,
invalid attestation identifiers or URLs, archive absence or digest drift,
subject or distribution-name drift, detached distribution metadata, and a
directory, VCS or otherwise inconsistent installed `direct_url.json`. Both
wheel and source-archive selection are covered by focused tests. The built-wheel
smoke must import the identity from its isolated target and execute
`ClosedAlphaFeedbackIdentity.load`, proving that the selected installed
distribution inventories that exact imported module and refers to the chosen
built wheel. Because the pinned target installer does not itself record an
archive hash, the smoke materializes hash-complete, test-only `direct_url.json`
metadata inside that ephemeral target from the wheel digest it just computed.
This proves the loader and origin-binding path; it is not an external installer
or publication claim.

These are API- and verified-file guarantees, not an in-process security
boundary. Arbitrary code already executing in the same Python interpreter,
including code using `object.__new__`, `object.__setattr__` or monkeypatching,
is part of the trusted computing base. The same-UID owner/operator is also in
the trusted computing base. RC4.1A therefore makes no claim of in-memory
unforgeability and no claim that the owner cannot delete or replace operating
system files. A supported-API bypass or an unexpected file change remains a
failure; deliberate arbitrary code or same-UID owner action is outside the
claimed boundary.

## Durable privacy fault and runtime binding

A feedback confidentiality or integrity failure must remain blocking even when
the SQLite transaction that first observes it rolls back. The control plane
therefore recognizes a private, durable fail-closed marker associated with the
exact ledger. The marker is a regular owner-only file, cannot be a symlink or
unsafe hard link, and cannot be replaced by a public or wrong-mode file.

Once a privacy fault is observed, transition to `prepared`, reservation and the
first HTTPX request hook all fail closed after restart and from a second process.
Failure to create, synchronize, inspect or validate the durable marker also
fails closed. A feedback store whose attempt to record the fault raises is
poisoned and propagates the durable failure; it may not pretend that a local
flag was successfully committed. The marker must still be created and
synchronized through the fail-closed fallback when opening SQLite or acquiring
`BEGIN IMMEDIATE` is unavailable, so transient database contention cannot erase
the fault across restart. This mandatory persistence path is a safety mechanism,
not an automatic research fallback, repair or retry charged against the zero
traffic phase budget.

Operations that have acquired a SQLite write lock remain linearized by that
lock: their authoritative state reads and clock sample occur after
`BEGIN IMMEDIATE`. The marker fallback does not move those already-locked
decisions outside their transaction. Feedback publication and identical-replay
acceptance also require a final authoritative feedback-context recheck at their
commit point; withdrawal or admission drift observed there blocks the result.

When the RC4 environment activates the shared control plane, `EvidenceMesh`
accepts only the RC4 governor bound to the same ledger, participant, session and
authoritative profile. A legacy governor or any binding mismatch is refused.
Execution outside the RC4 environment retains its prior behavior. These rules
are exercised only with local SQLite files, synthetic identities and in-process
mock transports; they do not authorize research traffic.

## Provider, policy and session correction

An RC4 provider is accepted only when its concrete class object is exactly one
of the six package-owned audited classes. Module names, qualified names,
metaclass equality, subclasses and instance- or class-shadowed registries are
not provider identities. The canonical provider name must be an exact `str`
with the frozen value, and the provider client must be the exact governed
HTTPX client. A metadata-copying class therefore fails before client attachment,
transport or ledger reservation. Factory-created exact providers remain
accepted. Mutation of an exact provider instance by arbitrary same-interpreter
code remains inside the trusted computing base described above.

The RC4 policy must be the exact frozen `ClosedAlphaPolicy` type and every
ceiling must be an exact `int`, never a comparison-overriding subclass. Neither
a policy subclass nor a forged limit can substitute expanded ceilings while
replaying an accepted JSON or fingerprint. The governor and control plane retain
their initial policy through a read-only supported surface. Reassignment cannot
raise the six-attempt session ceiling, and an oversized reservation remains
atomic with zero ledger spend.

The RC4 execution identity must likewise remain the exact immutable
`ClosedAlphaSession` accepted at construction and matched to the environment.
Public reassignment cannot change participant, session or profile after that
check. In particular, a `community` governor cannot become a `quality`
governor or acquire the latter's Tavily allowance. Legacy non-RC4 policy and
session assignment behavior remains unchanged; arbitrary access to private
attributes or `object.__setattr__` remains in the same-interpreter trusted
computing base.

## Pull-request workflow

The dedicated workflow is read-only and runs only for pull-request events while
pull request 1 is a draft from the repository-owned alpha branch. It checks the
exact head, single parent, base tree, clean checkout, changed-path statuses,
frozen protocol and policy hashes, and immutable historical files before any
source gate.

The Python interpreter and locked dependencies are installed before isolation.
Every source-executing gate then runs as the unprivileged runner identity with
supplementary groups cleared, no new privileges, an empty environment allowlist
and an empty Linux network namespace. The identity cannot write the Docker
socket. Focused RC4/RC4.1A adversarial tests run before the complete branch-aware
coverage suite, Ruff formatting and lint, strict MyPy, wheel and source
distribution builds, and a wheel-target import smoke for
`ClosedAlphaFeedbackIdentity.load` with the built wheel, its companion source
archive, a synthetic bounded acceptance record and the installed distribution
metadata.

All build and smoke output stays under one private temporary root. No GitHub
Actions artifact or attestation is created, no package is published, and the
temporary root is removed and its absence confirmed even after failure.

## Budgets

| Dimension | Maximum |
|---|---:|
| Authorized branch updates | 1 |
| Automatic workflow retries | 0 |
| Provider or search requests | 0 |
| Tavily requests | 0 |
| Model or token-count requests | 0 |
| Follow-up document fetches | 0 |
| Automatic fallbacks or repairs | 0 |
| Tester contacts or sessions | 0 |
| Live sessions | 0 |
| Uploaded artifacts or attestations | 0 |
| Published distributions | 0 |

Pinned interpreter and dependency acquisition before isolation is a
supply-chain operation, not research traffic. It does not permit a provider or
model secret.

## Stop criteria

Stop on the first repository, PR, draft, parent, tree, changed-path, immutable
file, protocol-hash, policy-hash, formatting, lint, typing, focused-test,
full-suite, coverage, build, installed-identity, zero-network or cleanup
failure. Also stop if an identity can be constructed from a raw SHA or detached
from its record, selected wheel/source archive, installed distribution or
actually imported module through the supported API; a privacy fault can be lost
on rollback, SQLite `BEGIN IMMEDIATE` failure, restart or a second process; an
unsafe marker is accepted; an already-locked operation samples state or time
before its SQLite write lock; final feedback admission is not rechecked;
`prepared`, reserve or the request hook remains reachable after a privacy fault;
or an RC4 runtime binding mismatch is accepted. Also stop if provider metadata
or a subclass passes as an audited class; the policy or any of its integer
limits is not exact or can be reassigned; the session participant, session code
or profile can be reassigned;
an oversized batch spends any ledger row; or legacy non-RC4 behavior regresses.
Stop if any historical evidence or lock metadata changes, or any real provider,
model, tester or live request is needed.

Stop rather than retry if the single branch update fails or if another code or
policy change is required. Stop immediately if a secret, artifact, attestation,
distribution, merge, release or live action would be required. A green run
establishes offline correction conformance only and returns control for a new
explicit decision.
