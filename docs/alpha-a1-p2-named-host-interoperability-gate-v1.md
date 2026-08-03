# Alpha A1-P2 named-host interoperability gate v1

## Purpose and claim boundary

A1-P2 verifies one named third-party MCP client path: the official MCP
Inspector CLI 2.0.0 loads an EvidenceMesh `mcpServers` configuration, launches
the frozen EvidenceMesh 0.1.0 STDIO server, discovers `health` and calls it.
MCP Inspector is a developer testing client, not an AI application host. The
phase name is retained for roadmap continuity; a pass does not establish Claude
Desktop, Cursor, VS Code, ChatGPT, GUI or universal MCP-host compatibility.

## Entry criteria

The gate starts only when all of the following are true:

1. The workflow is a draft PR #1 run in `VynoDePal/EvidenceMesh` for the
   same-repository branch `agent/evidencemesh-v0.1`. The public clone head and
   the exact `pull_request.head.sha` must match.
2. The accepted A1-P1 checkpoint is the exact public commit
   `b967114a177eec00a7ff5f03bcf1169e04b2faac`, tree
   `7477a10c89ae158a5f5ca197799b50088335d4d8`, and accepted workflow run
   `30721297774`. The commit and tree must be an ancestor of the trigger head.
3. A1-P0 has passed in the current job for frozen product commit
   `145f5f923825ffeaeb485bd680bc79410ab290d1`, tree
   `3b36c2d3970a5e3c325a2b20260daabf23d33a29`, Python 3.11 and a non-editable
   install. A1-P2 reuses that install.
4. The diff after the A1-P1 checkpoint contains exactly the eight A1-P2 files
   frozen by the verifier. A1-P1-specific policy, descriptor, client and
   verifier bytes therefore remain unchanged. The historical P1 step is not
   silently widened: it runs only for its exact accepted SHA and is skipped on
   a later P2 head.
5. Ubuntu 24.04 x86_64, Node 22.20.0, npm 10.9.3 and `strace` are available.
   The manifest and lock hashes must match the policy, and every acquired npm
   tarball must be an integrity-locked HTTPS registry object.

Missing, ambiguous or drifting entry evidence stops the gate.

## Supply-chain acquisition

The private harness locks `@modelcontextprotocol/inspector` to 2.0.0 and all
transitive dependencies in `alpha/a1-p2-inspector/package-lock.json`. Its exact
Inspector npm integrity is
`sha512-uEoeEG7/+ZbrvccPF3EsgbfjcyJ3bWVJXT4pcZtpmDUhA0zdK4T4Tuj2oUphi2Huwl66LqVdo3Mx2PkS2SUHXA==`.
The harness repeats the package's required `ink-select-input` override so
`npm ls --all` is valid without `--force` or `--legacy-peer-deps`.

A1-P2 performs one `npm ci --ignore-scripts --no-audit --no-fund` invocation
with npm fetch retries set to zero. Acquisition network is required and is
reported separately from MCP runtime traffic. No npm lifecycle script runs.
`npx`, a floating tag, a second install or an unlocked source fails the gate.
The installed launcher, CLI bundle and package manifest are re-hashed before
execution.

## Configuration and exact journey

The public descriptor is a template and cannot execute with its documented
placeholders. The gate materializes a private mode-`0600` copy by replacing only
the command with the absolute A1-P0 `evidencemesh-mcp` launcher and the cache
placeholder with an absolute private cache path. MCP Inspector accepts the
unchanged `mcpServers` STDIO shape without a `type` field. No protocol adapter,
wrapper or semantic translation is used.

One local Inspector launcher process receives exactly one CLI operation:

```text
--cli --config <private-descriptor> --server evidencemesh
--method tools/call --tool-name health --tool-args-json {}
--format json --connect-timeout 10000
```

The pinned Inspector resolves tools before calling one. Generic server-side
request instrumentation must observe this exact four-request sequence in one
connection and one server process:

1. `initialize`;
2. `logging/setLevel`;
3. `tools/list`;
4. `tools/call health`.

The one JSON stdout object must contain a successful, structured `health`
result for EvidenceMesh 0.1.0: status `ready`, profile `community`, only
Wikipedia configured, no configuration warning, private networks disabled and
DNS pinning enabled. A1-P1 remains the authority for the complete six-tool,
one-resource, one-prompt inventory and protocol version because the P2 CLI
result does not expose those observations in full.

## Runtime guard and privacy boundary

The Inspector process starts from a sanitized, secret-free environment. A Node
preload blocks common Node network APIs. Explicit Inspector `-e` harness
overrides load a Python `sitecustomize` guard in the server; it blocks common
Python socket and DNS APIs and records request classes without changing MCP
messages. `strace -f` independently audits process creation and network syscalls.
An addressless IPv4 or IPv6 `SOCK_STREAM`/`SOCK_DGRAM` allocation is audited but
is not classified as a network request because it has no destination and moves
no bytes. Unix-domain IPC and the Linux Netlink kernel control plane are
explicitly local. Any destination or traffic syscall without a decoded local
Unix/Netlink `sockaddr`, any raw IPv4/IPv6 socket, any packet/XDP-family socket,
or any incomplete, resumed, malformed or non-UTF-8 network trace fails the gate.
The audit tracks socket families by process and file descriptor so local
Netlink calls with a null address remain attributable. `setsockopt` is accepted
only on a descriptor already proven Unix/Netlink local. The locked dependency
stack also performs one `urllib3` IPv6 capability probe at import: one tracked
IPv6 STREAM socket may bind `::1` at port zero and must then close without
`listen`, `connect`, `accept`, send or receive. This passive local bind moves no
bytes and is reported separately from the zero runtime-network-request budget.

These controls are API blocking plus syscall observation, not an operating-
system network namespace. The runtime descriptor, original template, package
manifests, installed product source and read-only home must remain unchanged.
Host state directories must remain empty. The source checkout must remain
clean, and no write may escape the declared ephemeral P2 work tree or the
reused A1-P0 runtime paths. Logs are UTF-8, bounded and must not contain an
error, traceback, unhandled rejection or exception marker.

## Budgets and stop criteria

The whole A1-P2 verifier, including the single npm acquisition, is limited to
90 seconds. The host lifecycle is limited to 30 seconds. The budget is one
dependency install attempt, one Inspector invocation, one server launch, one
MCP session, four expected and at most twelve logical MCP requests, one local
`health` call, zero search/provider/model/external-document/runtime-network
request and zero retry.

The gate stops on any second install, host invocation, session, server or tool
call; a fifth observed MCP request; a timeout; a package, descriptor, process,
health, request-sequence or identity drift; an error marker; a runtime network
attempt; an orphaned process; or a filesystem mutation outside the declared
ephemeral P2 and reused A1-P0 runtime paths.

## Invalid diagnostic history

The following public runs are retained as failed diagnostics, never accepted
as gate evidence:

- `30742640148` stopped before Inspector launch because the installed manifest
  check omitted the launcher's published `./` path prefix;
- `30742752978` completed the Inspector journey but a coarse syscall audit
  classified every IPv4/IPv6 family mention as traffic;
- `30743437520` completed the Inspector journey and exposed two passive local
  operations that required exact classification: the locked `urllib3` IPv6
  loopback capability bind and Node/libuv buffer tuning on Unix socket pairs;
- `30743776406` never reached Inspector or Node because the one-shot A1-P0
  dependency acquisition received a connection reset while fetching
  `packaging==26.2` from `files.pythonhosted.org`.

No failed run was manually rerun. Each later run is tied to a new public commit,
and only a complete run for its exact trigger SHA can become accepted evidence.

## Decision and publication boundary

A pass proves only Ubuntu STDIO interoperability with MCP Inspector CLI 2.0.0.
It does not validate a real AI host, GUI behavior, macOS, native Windows, live
retrieval, evidence quality, latency, load, Phase 12 or V1 readiness. The
workflow uploads no artifact and publishes no distribution, tag or GitHub
Release. PR #1 remains draft and merge remains unauthorized.
