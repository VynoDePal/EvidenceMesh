# Alpha RC protocol v1: Phase 11.4

Status: **frozen before the first Phase 11.4 GitHub release-candidate
build**.

Freeze date: **2026-07-29**.

Phase 11.4 evaluates distribution engineering, not search or answer quality.
It creates an ephemeral `evidencemesh-0.1.0-alpha-rc.1` bundle in GitHub
Actions, installs the wheel into a separate virtual environment, exercises the
installed MCP command over a real STDIO subprocess, inventories dependencies
and signs build evidence. It does not publish a GitHub Release or upload to
PyPI.

Before this freeze, local non-candidate checks inspected the FastMCP 3.4.5
STDIO client interface, the CycloneDX Python 7.3.0 command-line interface and
the `actions/attest` 4.1.0 source contract. A disposable SBOM was generated
only to confirm the CycloneDX 1.7 shape. No Phase 11.4 bundle was built, signed
or scored before this protocol was frozen.

## Locked inputs and tooling

- project and version: `evidencemesh==0.1.0`;
- candidate label: `evidencemesh-0.1.0-alpha-rc.1`;
- build interpreter: CPython 3.11;
- package manager and builder frontend: uv 0.11.33;
- package metadata check: Twine 7.0.0;
- SBOM generator: `cyclonedx-bom==7.3.0`;
- SBOM format: CycloneDX JSON 1.7;
- GitHub build and SBOM attestation action:
  `actions/attest` 4.1.0 at commit
  `59d89421af93a897026c735860bf21b6eb4f7b26`;
- artifact upload action: `actions/upload-artifact` 7.0.1 at commit
  `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`;
- checkout action: `actions/checkout` 7.0.1 at commit
  `3d3c42e5aac5ba805825da76410c181273ba90b1`.

The GitHub workflow checks out the exact pull-request head SHA with persisted
Git credentials disabled. New release actions are referenced by immutable
commit SHA, not by a mutable major-version tag.

## Locked candidate contents

The uploaded Actions artifact must contain one candidate directory with:

1. exactly one wheel and one source distribution;
2. `alpha-rc-manifest.json`;
3. `SHA256SUMS`;
4. `evidencemesh-0.1.0.cdx.json`;
5. `installed-wheel-mcp-stdio.json`;
6. `installed-wheel-offline-benchmark.json`.

The separate Phase 11.4 result JSON is uploaded beside that directory. GitHub
Actions artifacts are temporary validation evidence, not a durable public
release channel.

## Package gates

Every package gate is mandatory:

1. `uv build` emits exactly
   `evidencemesh-0.1.0-py3-none-any.whl` and
   `evidencemesh-0.1.0.tar.gz`;
2. Twine accepts both distributions;
3. wheel metadata contains project version `0.1.0`, Python `>=3.11`, the eight
   declared runtime dependencies and both console entry points;
4. wheel and source distribution contain `LICENSE`, `README.md`, `py.typed`,
   `data/federation_v1.json` and the MCP implementation;
5. a new virtual environment installs the built wheel, not the repository
   source tree;
6. the installed package resolves from inside that isolated environment and
   reports version `0.1.0`;
7. the installed `evidencemesh` command completes all 12 deterministic offline
   regression cases with fused hit@1 equal to 1.0.

The isolated installation resolves dependencies from the wheel's published
metadata. Its exact resulting inventory is captured by the SBOM; it is not
misrepresented as a bit-for-bit lockfile installation.

## Real MCP STDIO gates

The verifier must launch the installed `evidencemesh-mcp` console command as a
real subprocess through FastMCP's STDIO transport. An in-memory server object
does not satisfy this gate.

The initialization response must identify:

- server: `EvidenceMesh`;
- version: `0.1.0`;
- a non-empty negotiated MCP protocol version.

The observed inventory must equal, in order:

- tools: `search_web`, `deep_research`, `fetch_url`, `batch_search`,
  `verify_claim`, `health`;
- resource: `evidencemesh://research-guide`;
- prompt: `evidence_first_research`.

Only `health` is invoked. It must return `ready`, list only the deliberately
isolated `wikipedia` provider, preserve private-network blocking and report DNS
pinning. Search, fetch, paid-provider and model calls are forbidden.

## SBOM, checksum and attestation gates

The CycloneDX generator scans the isolated installed environment and validates
its own JSON output. The root component must be
`evidencemesh==0.1.0` with type `application`; all eight direct runtime
dependencies must be present. Secret names or values are not accepted in the
SBOM or smoke reports.

`SHA256SUMS` covers the wheel, source distribution, SBOM, both installed-wheel
reports and candidate manifest. GitHub then:

1. creates SLSA build-provenance attestations for every checksummed subject;
2. creates a CycloneDX SBOM attestation for the wheel;
3. verifies the wheel's provenance and SBOM attestations with GitHub CLI,
   constrained to repository `VynoDePal/EvidenceMesh` and the Phase 11.4
   signer workflow;
4. records the attestation IDs and URLs in the Phase 11.4 result.

The workflow requires only `contents: read`, `id-token: write`,
`attestations: write` and `artifact-metadata: write`. It uses GitHub's
short-lived workload identity; no signing key, provider key or model key is
read.

## Traffic and privacy boundary

Maximum Phase 11.4 external research traffic:

- provider search or fetch requests: 0;
- Tavily or other paid-provider requests: 0;
- Gemini or other model requests: 0;
- retries: 0.

Build dependency downloads and GitHub attestation API calls are supply-chain
operations, not benchmark traffic. Reports exclude environment values, server
stderr, signing tokens and secrets.

## Decision boundary

The technical alpha candidate passes only if every package, installed-wheel,
MCP, SBOM, checksum, provenance and verification gate succeeds in one GitHub
workflow run.

Even on a technical pass:

- answer and retrieval quality are not scored;
- no superiority or “best open-source search” claim is allowed;
- the Actions artifact is not a GitHub Release;
- PyPI and GitHub Release publication remain blocked;
- the pull request remains draft;
- merge remains blocked;
- Phase 12 remains blocked;
- overall release readiness and release decision remain `false` and `no-go`.

Any missing or failed technical gate also makes the alpha technical candidate
fail. Thresholds and inventories cannot be changed after the first candidate
build merely to obtain a pass.
