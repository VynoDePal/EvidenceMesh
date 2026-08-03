# Alpha A1-P3.1 launcher correction gate v1

## Historical result and root cause

The first A1-P3 submission is preserved at commit
`38eb63ade7024ab32963f894c719fa190fe9346a`, tree
`c21496bf690a8c2844a8957b7af12de72cf5b7ad`, run `30745671040` and job
`91490727817`. It failed closed before installing Gemini CLI, launching the
host, opening an MCP session or calling a tool.

The workflow invoked `scripts/verify_alpha_a1_p3_real_host_offline.py` as a
file. Python therefore placed the `scripts` directory, rather than the
repository root, first on the import path, and `from scripts import ...` raised
`ModuleNotFoundError`. Pytest imported the same verifier as a module and did not
exercise the workflow entrypoint. The failure is a harness-launch defect, not
an EvidenceMesh, Gemini CLI or MCP result. A1-P3 remains non-evaluated.

## Correction

A1-P3.1 uses a new workflow and invokes
`python -m scripts.verify_alpha_a1_p3_1_launcher_correction` from the repository
root. The wrapper preserves all eight original A1-P3 files byte-for-byte and
adds its own workflow, policy, protocol, verifier and tests. A subprocess test
executes the exact module import mode used by the corrective workflow.

The corrective verifier requires the new HEAD to be a one-parent child of the
failed commit and independently rechecks that the failed commit is a one-parent
child of the accepted A1-P2.1 checkpoint. It pins both historical trees, the
five additive corrective paths and the thirteen cumulative A1-P3/A1-P3.1 paths.

## Canonical journey

The separately labeled workflow first reproduces the accepted A1-P0 public
source installation. It then performs one integrity-locked `npm ci` with
scripts disabled and optional dependencies omitted, removes the acquisition
cache, and invokes Gemini CLI 0.53.1 once.

Gemini's official strict `--fake-responses` engine supplies two local synthetic
turns. It is not a real Gemini model and establishes no live-model behavior.
The real Gemini CLI scheduler and MCP client must discover only
`mcp_evidencemesh_health`, call it exactly once, receive ready EvidenceMesh
0.1.0, emit the locked sentinel and finish successfully.

The server must observe exactly `initialize`, `prompts/list`, `tools/list`,
`resources/list` and `tools/call health`, plus one
`notifications/initialized` notification. Any different order, parameter,
tool, call count or progress-token shape is rejected before dispatch.

## Runtime containment and budgets

Node and Python API guards block network access. Node permits `fetch` only for
the non-network `data:` scheme used by Gemini CLI's embedded WebAssembly asset.
`strace` audits the complete process tree and every network syscall. The
EvidenceMesh child receives no key, token, secret, password, credential or
proxy variable. No operating-system network namespace is claimed.

The corrective budget is one commit, one new workflow run, one A1-P0
installation, one `npm ci`, one host invocation, one MCP server, one session,
five logical MCP requests, one `health` call and two synthetic response turns.
External model, provider, search, document and runtime-network requests are
zero. Retries and reruns of either the historical failure or corrective run are
zero. Host time is capped at 60 seconds and A1-P3 execution at 240 seconds.

## Stop and authority boundary

Stop on any ancestry, tree, path, hash, package, event, request, environment,
process, state, timing or network drift. Stop on a second install, invocation,
server, session or tool call, a third synthetic turn, an unconsumed replay
record, any tool error or a non-canonical health receipt. A failed corrective
workflow remains failed; it is not retried or reinterpreted.

A pass validates only one Ubuntu headless Gemini CLI control-plane journey with
offline response replay. It leaves PR #1 draft and publishes no artifact,
distribution, release or tag. It authorizes neither merge, Phase 12,
production deployment nor V1.
