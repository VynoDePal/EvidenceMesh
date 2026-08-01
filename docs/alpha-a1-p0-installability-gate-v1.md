# Alpha A1-P0 installability gate v1

## Purpose

This gate verifies that the exact public EvidenceMesh technical-alpha source can be
installed and exercised in a clean environment. It is an installability check, not a
live-retrieval, research-quality, release or V1-readiness claim.

## Frozen candidate

- Repository: `VynoDePal/EvidenceMesh`
- Branch: `agent/evidencemesh-v0.1`
- Commit: `145f5f923825ffeaeb485bd680bc79410ab290d1`
- Tree: `3b36c2d3970a5e3c325a2b20260daabf23d33a29`

The gate must stop if the fetched commit or tree differs from either frozen value.

## Canonical environment and installation

The canonical environment is Ubuntu 24.04 x86_64 with Python 3.11. The source must be
cloned from the public repository, checked out at the frozen commit and installed once
with the locked command:

```bash
uv sync --locked --no-dev --no-editable --python 3.11 \
  --no-config --no-python-downloads --no-cache
```

The public clone and dependency installation each have one attempt and zero retries.
Git and uv may perform a variable number of internal HTTP transactions, so acquisition
is bounded by command attempts and the shared deadline, not by an invented HTTP count.
Dependency acquisition is permitted only before runtime; it does not authorize live
EvidenceMesh traffic. The runtime maximum is zero network, provider, document and model
requests.

The runtime verifier fails on Python socket and DNS attempts from the installed CLI and
MCP processes. It is not an operating-system network namespace or a proof about arbitrary
native code. The lock and artifact hashes constrain the tested installation, but A1-P0
does not claim bit-for-bit build reproducibility.

## Required runtime checks

All checks run from the installed environment and must finish within a shared limit of
900 seconds:

1. `evidencemesh providers` returns the local configuration health inventory.
2. `evidencemesh benchmark-offline` completes its packaged deterministic regression.
3. The installed `evidencemesh-mcp` entry point completes a real MCP STDIO handshake,
   exposes its contract and answers the `health` tool.

The complete gate permits zero provider calls, zero model calls and zero retries. No
search, fetch, live benchmark or external-quality evaluation belongs to this gate.

## Decision and publication boundary

The gate passes only when source identity, canonical environment, locked installation,
all three runtime checks, traffic budgets and the 900-second limit pass together. Any
missing, ambiguous or drifting observation fails closed.

Running or passing A1-P0 must not publish a workflow artifact, package distribution,
tag or GitHub Release. It does not authorize a merge, public release, quality claim,
Phase 12 or V1 readiness.

## Explicit limitations

Native Windows is unsupported in this alpha and macOS installability has not been
validated. A1-P0 also does not validate live provider availability, network retrieval,
evidence quality, latency under load or an end-user MCP client configuration.
