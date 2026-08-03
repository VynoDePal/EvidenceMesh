# Alpha A1-P1 first-run MCP gate v1

## Purpose

A1-P1 verifies that a documented EvidenceMesh STDIO descriptor can be loaded
from disk and exercised by the official Python MCP SDK. It is deliberately
different from A1-P0, which already tested the installed entry point with the
FastMCP client. This gate proves one headless first-run path; it does not prove
compatibility with every MCP host, live retrieval quality or release readiness.

## Entry criteria

The gate starts only when all of the following are true:

1. The workflow is running for draft PR #1 in `VynoDePal/EvidenceMesh` from the
   same-repository branch `agent/evidencemesh-v0.1`. The head cloned by A1-P0
   must equal the exact `pull_request.head.sha` that triggered the workflow.
2. Public A1-P0 commit
   `d34abe56b95c9daccf361eb86ff1c19421085f62` and tree
   `c622cfe868a2bc77cd487ec17107eb225f882a4c` are an exact ancestor.
3. The immediately preceding A1-P0 receipt passed for product commit
   `145f5f923825ffeaeb485bd680bc79410ab290d1`, tree
   `3b36c2d3970a5e3c325a2b20260daabf23d33a29`, Python 3.11 and a locked,
   non-editable EvidenceMesh 0.1.0 installation.
4. Changes after the A1-P0 prerequisite are limited to the frozen A1-P1 file
   set. The public descriptor and client verifier must be byte-identical to
   the versions used by the workflow.
5. The descriptor template hash is
   `81f631f82166f70d81712d7e9ab82cdb3dc20b8ba592d65ba59473faf5b4295e`.
   Its runtime command and cache path must resolve to absolute paths inside the
   reused A1-P0 clean room, with no unknown environment key or secret.

Any missing, ambiguous or drifting entry observation stops the gate.

## Exact journey

P1 adds no clone and no dependency installation. It reuses the exact A1-P0
virtual environment, loads an immutable runtime descriptor from a JSON file,
and launches one `evidencemesh-mcp` process from an empty state directory. The
client must be `mcp==1.29.0` using `StdioServerParameters`, `stdio_client` and
`ClientSession`; loading `fastmcp.Client` fails the gate.

The descriptor and verifier are A1-P1 control inputs from the exact triggering
PR head; the installed server remains the older frozen product candidate. This
separation is intentional and byte-checked. The published Quick Start preserves
the branch-head descriptor before detaching the product source so a user can
reproduce the same two-identity path.

The single session performs exactly seven logical MCP requests:

1. initialize;
2. list tools;
3. list resources;
4. list prompts;
5. call only the local `health` tool;
6. read the packaged `evidencemesh://research-guide` resource;
7. get the packaged `evidence_first_research` prompt with a fixed local test
   question.

The expected negotiation is protocol `2025-11-25`, server
`EvidenceMesh/0.1.0`, six exact tools, one exact resource and one exact prompt.
Health must report `ready`, profile `community`, only `wikipedia`, no warning,
private networks disabled and DNS pinning enabled. Reading the packaged guide
and prompt is local; neither operation is an external document or model call.

## Budgets and stop criteria

The additional P1 budget is one server launch, one session, at most seven MCP
requests, one local tool call, one local resource read, one local prompt get,
zero search, zero provider/model/external-document/network request and zero
retry. Each read has a 10-second timeout, the client lifecycle has a 30-second
timeout and the whole additional gate has 60 seconds.

The gate stops on an eighth MCP request; a second process, session or launch;
any retry or timeout; any contract, identity, health, source or configuration
drift; an unknown/relative command; a secret-shaped environment key; a source
or read-only-HOME mutation; stderr overflow or error marker; a network attempt;
or failure to exit both SDK context managers. The context-managed shutdown is
observed, but the SDK does not expose whether the server exited by itself
before its internal termination fallback, so A1-P1 does not claim a proven
graceful server self-exit.

FastMCP diagnostics remain enabled and are captured from stderr, while MCP
JSON-RPC stays on stdout. Stderr is limited to 16 KiB of UTF-8 and fails on a
traceback, an exception marker, or any line beginning with `ERROR` or
`CRITICAL` after an optional Rich timestamp; ordinary startup information is
permitted and hashed in the receipt.

## Guard and privacy boundary

The public descriptor contains only user-facing product settings. The harness
adds a separate, explicitly reported instrumentation overlay to block common
Python socket and DNS APIs in both client and server processes. The shared log
must remain empty and both guard imports must be observed. This is not an
operating-system network namespace and is not a proof against arbitrary native
code. Runtime state and the instantiated descriptor use mode `0600` under a
`0700` parent; HOME is read-only and must remain empty.

## Decision and publication boundary

A pass validates only the headless Ubuntu 24.04/Python 3.11 SDK journey. No GUI
host, macOS, native Windows, live provider, evidence quality, latency or load
claim follows. The workflow uploads no artifact and publishes no distribution,
tag or GitHub Release. It leaves PR #1 in draft and does not authorize merge,
Phase 12, V1 or a public release.
