# Alpha A1-P3.3 Node launcher topology attestation gate v1

## Preserved results

A1-P3 remains failed and non-evaluated at commit
`38eb63ade7024ab32963f894c719fa190fe9346a`, run `30745671040`, because its
entrypoint failed before installation or host execution. A1-P3.1 remains
failed at commit `06b57853332a89e8adf21317e85cc6f91deecacf`, run
`30746105014`, after its single npm installation stopped on a scope-directory
assertion. Neither run is an interoperability result.

A1-P3.2 remains failed at commit
`d3b3a00427321ca9130797f179edc0302e2b5952`, run `30746731127`, job
`91493485240`. It passed P0, exact optional-leaf installation, the Gemini host
event sequence, EvidenceMesh health at `0.1.0`, the five-request MCP sequence,
the strace network check, and empty Node and Python network markers. It then
stopped on `Node guard arming count drifted`. The later Python-cardinality,
process-extinction, state, source, total-time, and receipt controls were not
evaluated. No artifact or canonical receipt was published, and this partial
evidence is never reclassified as a pass or rerun.

## Exact topology attestation

The blocking assertion confused one root host invocation with one Node
process. Gemini CLI 0.53.1 canonically starts as a Node supervisor, then
relaunches one direct Node child with `GEMINI_CLI_NO_RELAUNCH=true`. The child
inherits `NODE_OPTIONS`, so both processes correctly arm the same network
guard. Two local exact-command reproductions and one independent
instrumentation observed the same normalized graph: one supervisor, one
direct relaunched child, one EvidenceMesh Python server, the complete offline
agent loop, and zero runtime-network attempt.

A1-P3.3 preserves that canonical relaunch. It does not replace the failed
cardinality rule with `>= 1` or a bare count of two. The private guard journal
contains exactly two bounded JSON events. Each event records only its PID,
parent PID, canonical executable, fixed host-argv digest, normalized exec-argv
kind, relaunch role, and main-thread identity. It records no argv, environment,
prompt, target URL, credential, or secret value. A network refusal journal also
omits the target and must remain empty on success.

The verifier independently parses successful `execve` and absolute-path
`execveat` records from the original `strace -f` log, including paired
unfinished/resumed records. A successful `execveat` with an empty or relative
path is rejected because its executable identity cannot be proven. The oracle
requires exactly two distinct single-execution Node PIDs, both using the
canonical Node executable. The guard PID multiset must equal that traced Node
multiset exactly. One event must be the root supervisor with no Node exec
argument; the other must be its direct child, marked as the relaunch. The child
may have no extra exec argument or the single version-defined automatic
`--max-old-space-size` positive-integer argument. Both must have the exact
locked host argv digest, be main threads, and be connected by the direct
process-creation edge also present in strace.

This rejects an unarmed Node, an armed non-traced PID, duplicate arming or
execution, a second root, a third Node, a worker, a different executable,
different host arguments, an unknown memory argument, or an unexplained
parent. The historical strace network validator and both API-level network
guards remain independent. The existing process check receives both Node
PIDs, the single Python PID, and the MCP server PID and requires all of them to
be gone.

## Isolation and ancestry

A1-P3.3 is a five-file additive child of the preserved P3.2 failure. It pins
the P2.1, P3, P3.1, and P3.2 ancestry and trees; the twenty-three cumulative
P3 additions; and every prior P3, P3.1, and P3.2 file byte-for-byte. Product,
server, harness, lock, replay, and historical verifier files do not change.

The additive wrapper reuses the P3.2 exact-leaf installer and the original P3
host engine. It temporarily adapts only the P3.2 scope check, the P3 strace
validator, the P3 PID reader, and the in-memory Node guard source. Scope and
strace are called once; PID reading is called once for Node and once for
Python. Every function and constant is restored in `finally`, including on
failure.

## One-shot journey and budgets

The new label authorizes one corrective commit and one workflow run. The
workflow reproduces P0 once, performs one pinned `npm ci`, starts one root
Gemini host invocation, one EvidenceMesh MCP server, and one MCP session. The
locked journey contains exactly five MCP requests, one `health` call, and two
synthetic response turns. The supervisor's one direct Node child does not
count as a second host invocation. Retries and reruns are zero.

External model, provider, search, document, DNS, socket, and runtime-network
requests remain zero. Host time is capped at 60 seconds and the complete P3
journey at 240 seconds. No artifact, distribution, release, or tag is
published.

## Stop and authority boundary

Stop on any ancestry, path, hash, trace, guard, role, parent, executable,
argument, process, request, environment, state, timing, or network drift. Stop
if the two PID multisets are not identical, if the direct supervisor-child
edge is absent, if any process survives, or if any earlier P3 control fails.
A failed P3.3 run remains failed and receives no retry or rerun.

A pass validates only one Ubuntu headless Gemini CLI control-plane journey
with offline response replay and its exact canonical Node launcher topology.
It leaves PR #1 draft and authorizes neither merge, Phase 12, production
deployment, V1, distribution, nor a live-model, quality, or superiority claim.
