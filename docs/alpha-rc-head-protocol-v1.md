# EvidenceMesh Alpha-RC HEAD protocol v1

## Status and purpose

This protocol creates one fresh technical release-candidate artifact from the
exact head commit of pull request #1. The candidate is
`evidencemesh-0.1.0-alpha-rc.2`. It replaces no historical result and does not
reuse the Phase 11.4 artifact or decision.

The run validates packaging, installation, the installed CLI, the installed
FastMCP STDIO interface, dependency inventory, checksums and GitHub keyless
attestations. It does not score retrieval, answers, citations, live Web
quality or competitive quality.

## Candidate and source identity

The workflow runs only on a `push` to `agent/evidencemesh-v0.1` and must check
out exactly `github.sha`. The checked-out Git commit, bundle manifest, result
and attestations must all name that same full 40-character SHA. A synthetic
pull-request merge commit is not an acceptable candidate identity.

The candidate job is allowed only in repository `VynoDePal/EvidenceMesh` on
branch `refs/heads/agent/evidencemesh-v0.1`. Forks, pull-request events,
manual dispatches and other branches are outside this protocol.

The build must execute every candidate step in one job. A committed historical
result, an existing artifact or a successful earlier workflow must never skip
the build, installation, smoke, SBOM, checksum, attestation or verification
steps.

Any source change after a successful run creates a different candidate and
invalidates the previous artifact as evidence for the new head.

## Exact bundle inventory

The candidate directory is exactly
`evidencemesh-0.1.0-alpha-rc.2/` and contains seven files:

1. `SHA256SUMS`;
2. `alpha-rc-manifest.json`;
3. `dist/evidencemesh-0.1.0-py3-none-any.whl`;
4. `dist/evidencemesh-0.1.0.tar.gz`;
5. `evidencemesh-0.1.0.cdx.json`;
6. `installed-wheel-mcp-stdio.json`;
7. `installed-wheel-offline-benchmark.json`.

The privacy-safe final result JSON is uploaded beside the candidate bundle in
one staging root containing exactly the seven-file candidate directory plus
`alpha-rc-head-result.json`, for eight files total. No log, symbolic link,
undeclared file or unchecked artifact is permitted.
`SHA256SUMS` covers the two distributions, SBOM, both installed-wheel reports
and the manifest.

## Mandatory technical gates

All gates are blocking and must pass in one workflow run:

1. the protocol hash and checked-out SHA match the frozen workflow inputs;
2. the complete test suite with branch-aware coverage, strict MyPy, Ruff
   checks and formatting checks pass;
3. the locked runtime dependency audit reports no known vulnerability;
4. `uv build` creates exactly one wheel and one source distribution;
5. Twine accepts both distributions;
6. package metadata, license, package data, dependencies and console scripts
   match the locked EvidenceMesh 0.1.0 contract;
7. the wheel and source distribution install into separate clean CPython 3.11
   virtual environments outside the repository source environment and both
   pass dependency consistency checks;
8. the installed CLI completes the 12-case deterministic offline regression
   with fused hit@1 equal to 1.0;
9. the installed `evidencemesh-mcp` command negotiates MCP over a real STDIO
   subprocess and exposes exactly six tools, one resource and one prompt;
10. the MCP health response is `ready`, uses only the isolated Wikipedia
    provider and preserves private-network blocking and DNS pinning;
11. CycloneDX 1.7 describes the installed environment and includes every
    direct runtime dependency;
12. the exact seven-file inventory and all checksums validate;
13. GitHub creates and verifies SLSA provenance for every checksummed subject;
14. GitHub creates and verifies a CycloneDX SBOM attestation for the wheel;
15. the final result binds the current SHA, run, artifact and attestation IDs;
16. the result retains every release and quality prohibition in this protocol;
17. the staged upload root contains exactly the expected eight regular files.

A build step that is skipped is not a pass. An attestation that identifies a
different commit or signer workflow is invalid.

## Traffic, secrets and permissions

The hard research-traffic ceilings are:

| Dimension | Maximum |
|---|---:|
| Tavily or other search-provider requests | 0 |
| Gemini or other model requests | 0 |
| Token-count requests | 0 |
| Follow-up document fetches | 0 |
| Retries | 0 |
| Fallbacks | 0 |
| Repairs | 0 |
| Provider or model secrets | 0 |

Package downloads, the GitHub artifact service and GitHub attestation APIs are
supply-chain operations, not research traffic. The workflow may use only the
short-lived GitHub token and workload identity needed for checkout,
attestations and artifact upload. It must not reference a provider or model
secret.

Repository contents are read-only. The workflow receives only `contents:
read`, `id-token: write`, `attestations: write` and `artifact-metadata: write`.
It may not modify Git refs, pull-request state, releases, packages or source
files.

## Decision and stop rules

A complete pass establishes only that the exact head is a valid technical
alpha candidate suitable for a separately authorized closed evaluation. It
does not establish product-market fit, retrieval quality, answer quality,
provider reliability, production readiness or superiority.

Even on success:

- the pull request remains a draft;
- merge remains blocked;
- public distribution, PyPI and GitHub Release remain blocked;
- product defaults remain unchanged;
- Phase 11.9 and Phase 12 remain blocked;
- no quality, “best”, superior or state-of-the-art claim is allowed; and
- no live benchmark or provider/model request is authorized.

The run stops on the first technical, integrity, dependency, provenance,
inventory or traffic failure. One rerun is allowed only for a clearly
identified GitHub Actions infrastructure failure that occurred before a valid
candidate was produced. A code, dependency, protocol or workflow correction
requires a new candidate SHA rather than a selective rerun.
