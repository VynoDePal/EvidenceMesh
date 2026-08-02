# EvidenceMesh 0.1.0 Alpha A1 technical acceptance freeze v1

## Decision

**Alpha A1 is accepted for one unpublished, offline technical-alpha scope.**
EvidenceMesh 0.1.0 may be described as a technical alpha only within the exact
installation and interoperability boundary recorded below. This is not a
quality, production, release, or V1 decision.

The freeze deliberately binds two identities:

- **product candidate:** commit
  `145f5f923825ffeaeb485bd680bc79410ab290d1`, tree
  `3b36c2d3970a5e3c325a2b20260daabf23d33a29`, package version `0.1.0`;
- **A1 evidence closure:** commit
  `ff02de19c2e44cec043603ecb4fa5b526dd10c18`, tree
  `6b2006d75adc64c6cd76a9a23db6e02cfe062bb6`, on draft PR #1 branch
  `agent/evidencemesh-v0.1`.

Between the product candidate and the evidence closure there is no change
under `src/`, or to `pyproject.toml` or `uv.lock`. The later commits add or
harden A1 controls, tests, descriptors, harnesses, documentation, and CI
evidence. P0, P1, P2, and P3.3 continue to install and exercise the frozen
product candidate; P2.1 intentionally executes no A1 journey. The evidence
closure is therefore not represented as a different product build. The commit
containing this document is a one-file, non-runtime seal whose direct parent
must be the exact A1 evidence closure above.

The earlier unpublished local acceptance of `v0.1.0-alpha.local` remains a
separate historical record. This A1 freeze neither moves nor republishes that
tag and does not publish a replacement tag or distribution.

The candidate source and the draft PR are public. Built distributions, the
local candidate tag, release objects, and deployment remain unpublished.

## Accepted evidence

| Gate | Exact accepted evidence | Result and bounded claim |
|---|---|---|
| A1-P0 | Control commit `d34abe56b95c9daccf361eb86ff1c19421085f62`, tree `c622cfe868a2bc77cd487ec17107eb225f882a4c`; CI run `30720191984`, job `91422564979` | Pass: one locked, non-editable public-source installation of the frozen product candidate on Ubuntu 24.04 x86_64 / Python 3.11, followed by installed CLI, offline benchmark, MCP handshake, and health checks. |
| A1-P1 | Commit `b967114a177eec00a7ff5f03bcf1169e04b2faac`, tree `7477a10c89ae158a5f5ca197799b50088335d4d8`; CI run `30721297774`, job `91425445938` | Pass: one official Python MCP SDK 1.29.0 first-run STDIO journey; exact six-tool, one-resource, one-prompt contract; local health only. |
| A1-P2 | Commit `e33fb3bbfe5278ea30fe568847a1caf263de8c4d`, tree `3564672ea1bd1ba6ec0edfd2c7a325d3f033b257`; run `30743849354`, gate job `91485918959` | Gate pass: MCP Inspector CLI 2.0.0 discovered and called `health` through one native STDIO configuration. The run's unrelated Python 3.12 timing failure is not ignored; it is closed only by A1-P2.1. |
| A1-P2.1 | Commit `3cc75a33790be353a74641034a3c5210dfc7bc17`, tree `21abc6024a08a5528710a5fd8e49630c8fca2c9d`; CI run `30744506608` | Pass: deterministic queue-deadline tests and successful Python 3.11/3.12/3.13, quality, package, and container jobs, with no product-source change. |
| A1-P3.3 | Evidence closure commit `ff02de19c2e44cec043603ecb4fa5b526dd10c18`; run `30747747932`, job `91496156256` | Pass: one Gemini CLI 0.53.1 Ubuntu headless agent loop using two locked fake-response turns, one EvidenceMesh MCP session, one `health` call, exact canonical Node supervisor-child topology, and zero runtime-network request. |

At the evidence closure, all 34 pull-request synchronization workflows
completed successfully. Local pre-publication validation recorded 1,139 tests,
Ruff, and strict MyPy passing. The A1-P3.3 execution used one attempt, zero
retry, zero rerun, and published no artifact.

The local validation count is supporting pre-publication evidence, not a
replacement for any canonical public run or job listed in the table.

The 34-workflow matrix includes governed skipped or no-op jobs. It establishes
the expected synchronization conclusions at that HEAD; it does not replay or
replace every one-shot A1 gate.

## What this freeze proves

Within the frozen identities and environments, the evidence supports all of
the following together:

1. the EvidenceMesh 0.1.0 product candidate is installable from its public
   source with the locked, non-editable Ubuntu/Python path;
2. its local CLI and MCP STDIO entry point start and report a ready
   `community` profile without runtime provider, search, model, document, or
   network traffic;
3. one official Python MCP SDK first-run journey preserves the expected local
   tool, resource, prompt, protocol, and health contract;
4. MCP Inspector CLI 2.0.0 interoperates with the server for local health;
5. Gemini CLI 0.53.1 completes one offline-replayed agent/tool/result control
   path with an exactly attested launcher topology; and
6. the ordinary CI matrix is deterministic on Python 3.11, 3.12, and 3.13 at
   the A1 evidence closure.

The network statement is limited to the layered API guards and syscall
observations used by each accepted gate. It is not a universal operating-system
network-namespace proof.

## What this freeze does not prove

This freeze does **not** establish:

- live Gemini behavior, production authentication, quota, provider
  availability, or any model-generated answer;
- live search, retrieval, answer, citation, latency, load, or retention
  quality;
- BRIGHT or BrowseComp-Plus admission or an official external score;
- interoperability with another AI host, a GUI, macOS, native Windows, or a
  platform matrix;
- security certification, public provenance, a signed release, production
  fitness, superiority, a "best" claim, or V1 readiness.

MCP Inspector is a developer testing client, not an AI application host. The
Gemini result uses the real host control path but synthetic response records,
not a live model.

## Phase 11.8.9 and downstream boundary

Phase 11.8.9 remains **engineering conformance only / no-go**, with 12 of 19
gates passed and seven external BRIGHT or BrowseComp-Plus gates
`not_evaluated`. The five public synthetic cases are development fixtures, not
independent scientific evidence. This does not contradict A1: A1 freezes
installability and bounded offline interoperability, while Phase 11.8.9 blocks
every external-quality or superiority conclusion.

Phase 11.8.10B-P0 and P1 likewise retain `no_go` quality and clarification
decisions even though their engineering locks passed 16/16 and 18/18. BRIGHT
and BrowseComp-Plus remain unadmitted; the component-rights and immutable
judge/runtime gates remain open.

Accordingly, this freeze authorizes no product-default change, Phase 11.9,
Phase 12, merge, tag, distribution, GitHub Release, production deployment, V1,
or public quality claim. PR #1 must remain draft.

The previously documented absence of a live-session retention heartbeat or
lease also remains a hard stop for any closed-alpha live session. Permanent
silence from BrowseComp-Plus or BRIGHT does not invalidate this offline A1
result, but it cannot be treated as benchmark admission or evidence.

## Preserved failures

The following executions remain immutable failed diagnostics and are not
converted into successful evidence:

- A1-P2 diagnostics: runs `30742640148`, `30742752978`, `30743437520`, and
  `30743776406`; none is the accepted P2 gate result;
- A1-P3: commit `38eb63ade7024ab32963f894c719fa190fe9346a`, run
  `30745671040`, job `91490727817`, entrypoint failure before host execution;
- A1-P3.1: commit `06b57853332a89e8adf21317e85cc6f91deecacf`, run
  `30746105014`, job `91491870812`, optional-package scope assertion failure
  before host execution; and
- A1-P3.2: commit `d3b3a00427321ca9130797f179edc0302e2b5952`, run
  `30746731127`, job `91493485240`, post-journey Node guard-cardinality
  failure.

None was retried or rerun. A1-P3.3 is a separate accepted correction; it does
not rewrite those outcomes.

## Entry, invalidation, and stop criteria

This freeze is valid only if:

1. the product candidate and evidence-closure commit and tree identities match
   exactly;
2. all accepted run and job identities above remain publicly available with
   their recorded conclusions;
3. the historical failures remain failures and are not rerun or reclassified;
4. PR #1 is open and draft on the same-repository branch;
5. the seal commit is a direct, one-parent child of the evidence closure and
   adds exactly this one Markdown file; and
6. the ordinary synchronization workflows for the seal commit all terminate
   successfully without a manual rerun.

Stop and invalidate the freeze on any identity, ancestry, scope, evidence, or
conclusion drift; any difference between the product candidate and evidence
closure under `src/`, in `pyproject.toml`, or in `uv.lock`; a seal delta other
than this one Markdown file; any failed required CI job; any provider, search,
model, external-document, benchmark-asset, or EvidenceMesh runtime-network
request made for this freeze; or any attempt to widen the claim to quality,
Phase 12, release, production, superiority, or V1.

This historical freeze remains valid for its exact frozen identities. A later
branch HEAD is `not_evaluated` by this record until a separately governed gate
binds it; branch movement does not retroactively rewrite the recorded result.

## Freeze budget

| Dimension | Maximum |
|---|---:|
| Provider, search, model, token-count, or document requests | 0 |
| EvidenceMesh runtime-network requests | 0 |
| Benchmark-asset downloads or external-response reads | 0 |
| Historical reruns or retries | 0 |
| Additive repository commits | 1 |
| Files added by the seal commit | 1 Markdown file |
| Branch-ref updates | 1 fast-forward update |
| Authorization labels or A1 one-shot gate runs | 0 |
| Manual workflow reruns | 0 |
| Artifacts, tags, distributions, releases, or deployments | 0 |

Ordinary pull-request CI and its locked dependency acquisition are permitted.
The historical uv and npm acquisitions also used separately governed network
access. None of those supply-chain operations is a zero-network claim or
authorizes live EvidenceMesh traffic. The zero-request result applies to the
bounded EvidenceMesh, MCP, and host runtime windows recorded by the gates.

## Final status

Subject to the seal commit's successful ordinary CI, the final status is
`alpha_a1_technical_acceptance_frozen`. EvidenceMesh 0.1.0 is an unpublished
technical alpha for the exact offline Ubuntu scope above. All quality and
release decisions remain blocked.

**Alpha A1 technical acceptance: PASS. Phase 12, merge, release, V1, and
production: NO-GO.**
