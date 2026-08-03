# Alpha A1-P3 real AI host offline replay gate

## Decision

Alpha A1-P3 tests one named AI application host: Gemini CLI 0.53.1. The host must
load the existing EvidenceMesh MCP STDIO descriptor, discover only `health`, run
its normal headless agent loop, call `mcp_evidencemesh_health` once, consume the
real tool result, and finish successfully.

The model side is deliberately local and deterministic. Gemini CLI's built-in
strict `--fake-responses` engine supplies two locked response records: one tool
selection and one final sentinel. This executes the real host scheduler, tool
registry, MCP client, server process, and result-return path, but it is not a
real Gemini model and makes no Gemini API request. A pass therefore establishes
one offline-replayed real-host interoperability path; it does not establish
live-model behavior, Gemini authentication, quota, availability, or production
fitness.

Gemini CLI is chosen because it is an Apache-2.0 terminal AI agent, has a
headless stream-JSON mode, and implements native MCP STDIO discovery and tool
execution. Version 0.53.1, its npm integrity, its launcher hash, Node 22.20.0,
npm 10.9.3, the private harness, lockfile, and response replay are exact inputs.
No floating `npx` command is allowed. Installation uses one `npm ci` with
scripts and optional native dependencies omitted.

Primary upstream references are the official [Gemini CLI repository and
releases](https://github.com/google-gemini/gemini-cli), [headless mode
documentation](https://geminicli.com/docs/cli/headless/), [MCP server
documentation](https://geminicli.com/docs/tools/mcp-server/), and
[configuration reference](https://geminicli.com/docs/reference/configuration/).

## Entry criteria

The pull request must remain draft PR #1 in `VynoDePal/EvidenceMesh`, with the
same-repository head `agent/evidencemesh-v0.1`. Its single parent must be the
accepted A1-P2.1 checkpoint `3cc75a33790be353a74641034a3c5210dfc7bc17`
(tree `21abc6024a08a5528710a5fd8e49630c8fca2c9d`, run `30744506608`). The
candidate product remains the frozen 0.1.0 source commit
`145f5f923825ffeaeb485bd680bc79410ab290d1`. The event must be the addition of
the one-shot `alpha-a1-p3-authorized` label.

The candidate commit may add exactly eight A1-P3 text files. It may not modify
product source, `ci.yml`, the public MCP descriptor, packaging metadata, locks,
or any P0/P1/P2/P2.1 evidence. The A1-P0 verifier must first reproduce the one
non-editable public-source installation and observe the exact trigger HEAD.

## Locked journey

The verifier creates separate private directories for acquisition, Gemini
state, a read-only empty workspace, a read-only EvidenceMesh server home, and
the explicit cache. It derives Gemini's private native settings from the public
descriptor and adds only runtime security instrumentation, `includeTools:
["health"]`, trust for the isolated workspace, and a ten-second MCP timeout.
Gemini's core tool allowlist contains only `mcp_evidencemesh_health`.

One host invocation must emit exactly:

1. `init` for `gemini-3.1-flash-lite`;
2. the locked user message;
3. one `tool_use` for `mcp_evidencemesh_health` with `{}`;
4. the correlated successful `tool_result` containing ready EvidenceMesh 0.1.0;
5. the locked assistant sentinel; and
6. a successful result reporting exactly one tool call.

The EvidenceMesh process must observe exactly `initialize`, `prompts/list`,
`tools/list`, `resources/list`, and `tools/call health`, plus one
`notifications/initialized` notification. The guard rejects the message before
dispatch if the order, parameters, tool, call count, or progress token drifts.

## Runtime containment and budget

The Node host and Python server each arm an API-level network guard. `strace`
audits the complete process tree and every network syscall; no destination,
packet traffic, ambiguous network operation, DNS request, external model call,
EvidenceMesh provider call, search, or document request is allowed. The child
server must inherit no key, token, secret, password, credential, or proxy
variable. This is layered process auditing, not an operating-system network
namespace, and that limitation remains explicit.

The Node guard permits `fetch` only for the non-network `data:` scheme required
to load Gemini CLI's embedded WebAssembly asset. It rejects malformed targets
and every other scheme before dispatch; the syscall audit remains authoritative
for the zero-network result.

The maximum budget is one A1-P0 installation, one `npm ci`, one host invocation,
one MCP server, one session, five logical MCP requests, one `health` call, two
synthetic response turns, zero external model requests, zero retry, 60 seconds
for the host and 240 additional seconds for A1-P3. There is no workflow rerun.

## Stop and authority boundary

Stop on any prerequisite, scope, hash, version, package, event, response,
request, environment, process, state, timing, or network drift. Stop on a
second install, invocation, server, session or tool call; a third response turn;
an unconsumed replay record; a tool error; a non-canonical health receipt; or a
failed workflow. Do not retry or reinterpret a partial result as a pass.

A pass leaves PR #1 draft and publishes no artifact, distribution, release or
tag. It does not authorize a merge, Phase 12, production deployment, or V1.
