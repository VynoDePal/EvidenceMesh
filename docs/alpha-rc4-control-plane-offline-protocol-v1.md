# EvidenceMesh Alpha-RC4 control-plane offline protocol v1

## Decision boundary

This phase implements and validates the local control plane required before a
closed alpha can be reconsidered. It is a pull-request validation phase, not an
exact-HEAD candidate acceptance, attestation or sealing phase. It sends no
research, provider, Tavily or model request and authorizes no tester contact,
live session, closed-alpha adoption, binary distribution, merge, release,
quality claim or production-readiness claim. The pull request remains draft.
No retention daemon or other operational service is deployed in this offline
phase.

The immutable starting point is the Alpha-RC3 metadata seal at
`033d893d7c07e8c31a19e543187d15e28aa58d90`, tree
`d0d0fb5b6d5954920728a9928891ab73b468d063`. The accepted RC3 technical
candidate remains `c1e0be437442b0d97da26f2c9085067a8c09955e`. Its acceptance
record, the historical A0-v1 kit, RC3 protocols and policies, `pyproject.toml`
and `uv.lock` remain byte-immutable. RC4 changes runtime governance but does
not rewrite historical evidence.

## Single-host boundary

`SQLiteAlphaControlPlane` and the dispatch governor share one private SQLite
ledger on one host. The control plane does not claim distributed coordination.
Independent ledgers, replicated files, network filesystems and multiple hosts
cannot enforce one global budget and are refused or remain explicitly out of
scope.

The future closed-alpha ceilings inherited from A0 are exercised only with
synthetic inputs and in-process mock transports. They are not traffic
authorization. The current phase budget is zero for every research and tester
dimension.

## Atomic operating state

The ledger has exactly three operator states:

- `prepared` is the only mechanically dispatchable state;
- `paused` is reversible through an explicit compare-and-swap transition; and
- `stopped` is terminal and cannot return to another state.

`prepared` means only that offline control-plane invariants are satisfied. It
does not mean that live execution has been authorized. A later adoption record
and a separate explicit live decision remain mandatory.

Every state transition increments a monotonic control epoch. Each dispatch
permit is bound to the epoch observed when it is reserved. The governor checks
the state, epoch, participant status, consent, session ownership and remaining
budgets atomically both when reserving a batch and again in the first HTTPX
request hook immediately before transport. A transition serialized before the
hook prevents the request. A request already admitted before a later pause
cannot be recalled. Permits from an earlier epoch are invalid, single-use and
never refunded.

## Admission and profiles

The registry accepts exactly eight pseudonymous slots: six `community` and two
`quality`. Participant and session identifiers must match the closed patterns;
names, email addresses and contact data are forbidden. A participant is bound
immutably to one slot and one profile. The profile is read from the registry,
not trusted from a caller-controlled environment value.

The exact versioned consent statement and authority confirmation must be
recorded before a first reservation. Missing, withdrawn, mismatched or expired
admission fails before transport. A withdrawal is committed in the SQLite
control plane before any report deletion, immediately preventing new permits
and writes for that participant.

The `community` profile accepts exactly arXiv, Crossref, GitHub, SearXNG and
Wikipedia. The `quality` profile adds Tavily. DDGS, custom providers, additional
SearXNG fallback endpoints, cache use and MCP HTTP remain forbidden. CLI and MCP
STDIO retain the one-process-per-session boundary.

## Crash and recovery contract

An expired owner lease or abandoned active session moves the global state to
`paused` and marks recovery as required. Outstanding permits are invalidated
without deleting attempts or refunding any counter. Recovery explicitly closes
abandoned sessions under compare-and-swap and preserves all budget rows before
a separate resume transition can be considered. It never creates a replacement
ledger or resumes automatically. Clock regression, corruption, policy drift or
an unsafe ledger path fails closed; a host reboot is not claimed as a supported
transparent recovery path.

## Private feedback lifecycle

`ClosedAlphaFeedbackStore` accepts only the closed aggregate schema and semantic
checks. It never serializes task text, prompts, queries, answers, model output,
titles, snippets, quotes, URLs, source content, headers, credentials, exception
messages, stack traces, local paths, host identifiers or contact data.

The only accepted validator is the final, package-owned
`ClosedAlphaFeedbackContract` class shipped in the candidate wheel. It is bound
at construction to the exact candidate commit SHA and rejects a report carrying
any other SHA. An arbitrary, caller-supplied or no-op validator is forbidden.
For every write and stored-report validation, the slot, profile, provider-attempt
counter and Tavily-attempt counter come from the authoritative SQLite registry
and attempt ledger. Matching caller fields are checked against that context;
they never select it.

The store root is absolute, private and anchored with directory-descriptor
operations. Directories use mode `0700`; regular files and the inter-process
lock use `0600`. Names derive only from allowlisted pseudonymous codes. A write
validates schema and cross-field semantics before canonical JSON is written to
an exclusive no-follow temporary file, synchronized, published atomically
without overwrite and followed by a directory synchronization.

Expiry and withdrawal reconciliation run under the inter-process lock at
startup, before every access, at orderly shutdown and through an independently
invocable local scheduler. Every report must be deleted before the beginning of
the UTC `delete_after` date. After withdrawal commits in SQLite, reconciliation
discovers every owned report from the private store and deletes it; no caller
session list is accepted or trusted. This makes a crash between the registry
commit and deletion recoverable on the next reconciliation point.

Every observed UTC instant advances a durable high-water mark in the same
SQLite control plane before retention decisions rely on it. The high-water mark
survives store and process restarts. A regressing, invalid or unavailable clock,
an admission-context mismatch, or any confidentiality, integrity, deletion,
permission, link, deadline or durability fault records a durable SQLite privacy
fault. That fault blocks transition to `prepared`, reservation and the first
HTTPX request hook. Failure to record or read the fault is itself fail-closed.

`FeedbackRetentionScheduler` is a small local component that invokes the same
reconciliation path. Continuous local supervision of that component is an entry
criterion before any later live decision. This phase only validates it with
offline tests: it neither installs nor claims a deployed daemon, collector or
remote service.

## Pull-request validation

The dedicated workflow runs only for pull request 1 from the repository-owned
alpha branch while the pull request is draft, including when it is converted
back to draft. It verifies that the RC3 sealing commit and tree remain ancestors,
and that historical A0-v1, RC3 acceptance, packaging metadata and lockfile bytes
have not changed.

Dependency and interpreter installation occur first from the locked project.
Every source-executing gate then runs as the unprivileged runner identity with
supplementary groups cleared, no new privileges, an empty environment allowlist
and an empty Linux network namespace. The isolated identity cannot write the
Docker socket. The complete suite with branch-aware coverage, focused RC4
adversarial tests, Ruff formatting and lint, strict MyPy, and wheel and source
distribution builds must all pass. The built wheel is installed into an
ephemeral target and smoke-tested in the same empty network namespace; the
smoke proves that the final feedback contract is packaged and binds to the exact
pull-request-head SHA. Temporary output is removed even after a failure. No
GitHub Actions artifact or attestation is created, uploaded or published in this
phase.

## Traffic budget

| Dimension | Maximum |
|---|---:|
| Search or provider requests | 0 |
| Tavily requests | 0 |
| Model or token-count requests | 0 |
| Follow-up document fetches | 0 |
| Automatic retries, fallbacks or repairs | 0 |
| Tester contacts or sessions | 0 |
| Live sessions | 0 |
| Uploaded artifacts or published distributions | 0 |

Pinned interpreter and dependency acquisition is a supply-chain operation that
occurs before isolation and is reported separately from research traffic. The
workflow references no provider or model secret.

## Stop criteria

Stop on the first baseline, ancestry, hash, draft-state, formatting, lint,
typing, test, coverage, build, wheel-smoke, zero-network or cleanup failure. Also stop if a
request can reach transport outside `prepared`; a participant can bypass slot,
profile or consent admission; a pre-transition permit survives an epoch change;
pause, stop or withdrawal races can dispatch; a crash resets, removes or refunds
budget state; recovery resumes automatically; a report admits a forbidden
field; its candidate SHA, slot, profile or authoritative counters can drift;
withdrawal or expiry reconciliation is incomplete at startup, access, shutdown
or scheduler execution; a caller session list is required; the durable UTC
high-water mark regresses; a privacy fault does not block `prepared`, reserve and
the first request hook; scheduler supervision cannot be established before
live; permissions, links or file replacement are unsafe; DDGS, an unknown
provider, cache or MCP HTTP becomes reachable; any real provider, model or
tester request is needed; or any package byte becomes downloadable.

A green run establishes offline implementation conformance only. Exact-HEAD
candidate acceptance, public attestations, metadata sealing, A0 adoption and a
live decision each require later explicit authorization.
