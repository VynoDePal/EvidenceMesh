# Alpha A1-P3.2 exact optional-leaf correction gate v1

## Preserved results

A1-P3 remains failed and non-evaluated at commit
`38eb63ade7024ab32963f894c719fa190fe9346a`, run `30745671040`: its direct
Python entrypoint failed before the P3 installation or host journey.

A1-P3.1 remains failed at commit
`06b57853332a89e8adf21317e85cc6f91deecacf`, run `30746105014`. It reproduced
the accepted A1-P0 installation and completed its only locked `npm ci`, then
stopped on `Optional package installed: @github`. It launched no Gemini host,
P3 MCP server, P3 session, or P3 tool call. The run proves that the `@github`
namespace path existed; because the assertion tested the namespace rather than
`@github/keytar`, it does not establish whether the optional package leaf was
installed. It is not an interoperability result and is never rerun.

## Exact-leaf correction

The frozen lock contains eleven entries marked `optional`. A1-P3.2 derives
that set from the integrity-pinned lock and requires each complete package path
to be absent after `npm ci --ignore-scripts --omit=optional`. It additionally
requires any existing `node_modules/@github` or `node_modules/@lydell`
namespace to be a real, empty directory. An absent namespace is also accepted;
a symlink or any entry beneath either namespace is rejected.

The installed top level may contain only `.bin`, `.package-lock.json`,
`@google`, and those two optional empty namespaces. The hidden npm lock must
identify only the pinned Gemini package, `@google` must contain only the real
`gemini-cli` directory, and `.bin` must contain only the canonical relative
`gemini` symlink. These checks also reject dangling links and undeclared
top-level content.

This distinguishes npm's harmless empty scope-directory bookkeeping from an
installed optional package without weakening the omission requirement. The
Gemini manifest, lock, installed version, license, launcher hash, root
dependency tree, disabled scripts, zero retries, and deleted acquisition cache
remain identical to the original P3 contract.

## Isolation and ancestry

A1-P3.2 is a five-file additive child of the preserved P3.1 failure. It pins
the P2.1, P3, and P3.1 ancestry and trees, the eighteen cumulative additions,
all prior immutable files, and the exact hashes of the five P3.1 files. It
temporarily adapts only the historical scope validator and installer, each
exactly once, then restores both even on failure. All host, MCP, replay,
network, process, environment, timing, and receipt checks continue to execute
inside the original P3 verifier.

## One-shot journey and budgets

The new label authorizes one new commit and one new workflow run. The workflow
first reproduces A1-P0 from the same public HEAD. P3.2 then permits one pinned
Gemini dependency installation, one Gemini CLI invocation, one EvidenceMesh
MCP server, one session, five logical MCP requests, one `health` call, and two
synthetic response turns. Retries and reruns are zero.

During host execution, external model, provider, search, document, DNS, socket,
and runtime-network requests are zero. Host time is capped at 60 seconds and
the P3 journey at 240 seconds. No artifact, distribution, release, or tag is
published.

## Stop and authority boundary

Stop on any ancestry, path, hash, lock, optional-leaf, namespace, package,
event, request, environment, process, state, timing, or network drift. Stop on
a second install, invocation, server, session, or tool call, a third synthetic
turn, an unconsumed replay record, any tool error, or a non-canonical health
receipt. A failed P3.2 run remains failed and receives no retry.

A pass validates only one Ubuntu headless Gemini CLI control-plane journey with
offline response replay. It leaves PR #1 draft and authorizes neither merge,
Phase 12, production deployment, V1, nor a live-model or quality claim.
