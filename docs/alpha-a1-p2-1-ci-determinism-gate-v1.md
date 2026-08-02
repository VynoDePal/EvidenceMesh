# Alpha A1-P2.1 CI determinism gate v1

## Purpose and inherited checkpoint

A1-P2.1 removes a timing race from two concurrency-queue tests without changing
EvidenceMesh runtime behavior. It preserves the accepted A1-P2 checkpoint at
commit `e33fb3bbfe5278ea30fe568847a1caf263de8c4d`, tree
`3564672ea1bd1ba6ec0edfd2c7a325d3f033b257`, workflow run `30743849354` and
successful A1 gate job `91485918959`.

A1-P2 is a binary pass. The same workflow was globally red because Python 3.12
observed two valid provider wall timeouts where the test required exactly one.
Python 3.11 and 3.13 passed. This separate correction does not invent a
`PASS_WITH_EXCEPTION` state and does not rerun or rewrite A1-P2 evidence.

## Root cause

The old provider and fetch queue tests coupled a 50-millisecond `asyncio.sleep`
to an 80-millisecond wall deadline. They assumed the first coroutine would be
rescheduled within a 30-millisecond margin. Under runner contention the first
operation can legitimately cross its own wall deadline, so both concurrent
operations can time out. The engine is correct: its documented deadline covers
both semaphore waiting and adapter execution.

The exact provider failure reproduced locally under controlled CPU contention.
The analogous fetch test has the same race. No production source change is
required.

## Deterministic correction

The corrected tests use only public `search` and `fetch` operations plus
`asyncio.Event` synchronization. A controlled fetch holds the shared concurrency
slot while a provider request expires in the queue; then a controlled provider
holds it while a fetch expires in the queue. The target provider and fetcher
call lists must stay empty, proving that neither adapter was entered.

No sleep is used as the queue-timeout oracle, no private engine member is
accessed and no runtime behavior, dependency or product configuration changes.

## Entry and exact scope

The gate requires draft PR #1 in `VynoDePal/EvidenceMesh`, branch
`agent/evidencemesh-v0.1`, with `e33fb3bbfe5278ea30fe568847a1caf263de8c4d`
as the direct parent. The change set contains exactly these five paths:

1. `.github/workflows/ci.yml`;
2. `alpha/alpha_a1_p2_1_ci_determinism_policy_v1.json`;
3. `docs/alpha-a1-p2-1-ci-determinism-gate-v1.md`;
4. `tests/test_alpha_a1_p2_1_ci_determinism.py`;
5. `tests/test_engine_query_benchmark.py`.

All A1-P2 policy, documentation, harness, verifier and test files remain
byte-identical to the accepted checkpoint. The workflow limits the historical
A1 job to the exact P0, P1 and P2 heads. Node and Inspector remain pinned to the
exact P2 head. Therefore P2.1 must skip the complete A1 job and cannot perform a
second P0 acquisition or Inspector journey.

## Budgets, pass and stop criteria

The budget is one public commit, one automatically triggered canonical CI run,
zero manual rerun, zero retry and at most 1,900 local targeted stress scenarios.
CI dependency acquisition is inherited from the ordinary quality, test, package
and container jobs; it does not authorize EvidenceMesh live traffic. Search,
provider, external-document, model and EvidenceMesh runtime-network requests
remain zero.

P2.1 passes only if the A1 job is skipped; quality, package, container and the
Python 3.11/3.12/3.13 test matrix all succeed; and the canonical CI workflow is
globally successful on the new exact head.

The gate stops without a manual rerun if a path drifts, production or dependency
code changes, an A1 acquisition or Inspector step executes, any required job
fails, a live request occurs, or an artifact, distribution, tag or release is
published.

## Claim and publication boundary

A pass establishes deterministic CI coverage for the two queue-deadline
invariants. It adds no named-host compatibility claim beyond A1-P2, validates no
real AI host, measures no retrieval or answer quality and authorizes neither
Phase 12, merge, release nor V1 readiness. PR #1 remains draft.
