# Phase 11.4: technical alpha release candidate

Date: **2026-07-29**

Status: **technical candidate pass; overall release no-go**

Phase 11.4 evaluates distribution engineering only. It does not score search,
retrieval, answer or citation quality. The frozen protocol remains
[`alpha-rc-protocol-v1.md`](../../docs/alpha-rc-protocol-v1.md), SHA-256
`560e3e0932863ba78c4b5432af78b8dd47e0cdfe80c9e8ff5be9fcb1c2107ed5`.
No threshold, inventory or decision boundary was changed after the freeze.

## Post-build audit and invalidated first artifact

GitHub run
[`30475162303`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30475162303)
completed all workflow steps, but the mandatory post-download audit found
`installed-wheel-mcp-stdio.server.log` inside the candidate directory. The
1,755-byte file contained only the FastMCP banner and startup message; no
credential name, token or secret was present. It was nevertheless absent from
the locked candidate contents and not covered by `SHA256SUMS`.

That first artifact, ID `8733299881`, digest
`sha256:237bc6d93128d13cff0c8f5a6d4ff4c821ff14beb1e4ebf23e7356927ec609db`,
is therefore **invalidated and must not be treated as the Phase 11.4
candidate**. Its attestations `37793956` and `37793961` remain audit history,
not accepted release evidence.

The correction keeps server stderr outside the candidate, removes uv's
generated `dist/.gitignore`, rejects any missing, extra or symbolic-link entry,
and uploads the seven locked paths explicitly. This enforces the frozen
protocol; it does not relax or replace it.

## Accepted GitHub candidate

| Field | Accepted value |
|---|---|
| Candidate | `evidencemesh-0.1.0-alpha-rc.1` |
| Source commit | `41b2698deee13eb92205a5733452681cc84c9f4c` |
| GitHub run | [`30476241370`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30476241370) |
| Artifact ID | `8733721877` |
| Artifact name | `phase11-4-alpha-rc-41b2698deee13eb92205a5733452681cc84c9f4c` |
| Artifact ZIP SHA-256 | `0d0ddb24bb8a6515c18e94fdd828ffadbaee10940e6a77a68412b412394b4545` |
| Artifact size | 692,182 bytes |
| Artifact expiry | 2026-08-28 |
| Raw result SHA-256 | `53f07d0eadf9dcd61ab6971a0dc84768cee67f2956b5ab8e756e9bfb95644138` |

The downloaded ZIP contains exactly the separate result JSON and these seven
candidate files:

1. `SHA256SUMS`;
2. `alpha-rc-manifest.json`;
3. `dist/evidencemesh-0.1.0-py3-none-any.whl`;
4. `dist/evidencemesh-0.1.0.tar.gz`;
5. `evidencemesh-0.1.0.cdx.json`;
6. `installed-wheel-mcp-stdio.json`;
7. `installed-wheel-offline-benchmark.json`.

There are no extra files, logs or symbolic links. All six entries in
`SHA256SUMS` verify.

## Package and installed-wheel gates

| Gate | Result |
|---|---|
| Exactly one wheel | pass |
| Exactly one source distribution | pass |
| Package metadata | pass |
| License and package data | pass |
| Isolated wheel installation | pass |
| Installed CLI offline regression | pass |
| Real MCP STDIO handshake | pass |
| Exact MCP inventory | pass |
| MCP health without network | pass |
| CycloneDX 1.7 SBOM | pass |
| Exact candidate inventory | pass |
| Twine metadata check | pass |
| SHA-256 verification | pass |

The installed CLI completed 12/12 deterministic cases with fused hit@1 equal
to 1.0 and zero network requests.

The installed `evidencemesh-mcp` command ran as a real subprocess from an
isolated CPython 3.11.15 environment. FastMCP negotiated protocol
`2025-11-25`; the server identified itself as `EvidenceMesh` version `0.1.0`.
The observed contract was exactly:

- tools: `search_web`, `deep_research`, `fetch_url`, `batch_search`,
  `verify_claim`, `health`;
- resource: `evidencemesh://research-guide`;
- prompt: `evidence_first_research`;
- health: `ready`, Wikipedia-only provider isolation, private-network blocking
  enabled and DNS pinning enabled.

Only `health` was called. The run made zero provider search, provider HTTP,
paid-provider, model and retry requests.

## Candidate hashes and supply-chain evidence

| Subject | SHA-256 |
|---|---|
| Wheel | `49bfc2020618c37b48e0a2d5420c2e30798a78961c997bac4dba1dada6a7e73e` |
| Source distribution | `f84b884bc114aac595768a2bf998b397184d2b03e8b960ce8f92d4f1ea15ed8c` |
| CycloneDX SBOM | `4416309250e495eb633f2a9522c819c9d3cf3a111b9be5555c34ce8730d71357` |
| MCP STDIO report | `1764c52a858b694b219db45eab1cd6701b954c771a736d089bd7996f502a1437` |
| Offline CLI report | `f2d7214e9fd268c1e61ac9de814a6a3c2435013be84903f15215fa6b7ccca4da` |
| Candidate manifest | `cb64b1ef5765009b8696e51f43832c953dc9d549934665652b26b2b1675a9359` |
| `SHA256SUMS` | `1382a8383bfbbf23d9473716964619ed45395f825091f238e85e56d722c4ecaf` |

The CycloneDX 1.7 SBOM identifies `evidencemesh==0.1.0` as the root application,
contains 100 components including all eight direct runtime dependencies, and
contains no known credential identifier or credential-shaped value.

GitHub created and the workflow verified:

- SLSA provenance attestation
  [`37796765`](https://github.com/VynoDePal/EvidenceMesh/attestations/37796765);
- CycloneDX SBOM attestation
  [`37796768`](https://github.com/VynoDePal/EvidenceMesh/attestations/37796768).

Both verifications were constrained to repository `VynoDePal/EvidenceMesh`,
the exact Phase 11.4 signer workflow and GitHub-hosted runners.

## Decision

The corrected candidate satisfies every frozen Phase 11.4 technical gate in
one GitHub workflow run. Therefore:

- `alpha_technical_candidate_passed`: **true**;
- `quality_benchmark_passed`: **false**;
- `quality_claim_allowed`: **false**;
- `public_distribution_allowed`: **false**;
- `pypi_publish_allowed`: **false**;
- `github_release_allowed`: **false**;
- `merge_allowed`: **false**;
- `phase12_allowed`: **false**;
- `release_ready`: **false**;
- `release_decision`: **no-go**.

This is a technical distribution candidate, not evidence that EvidenceMesh is
the best open-source search or deep-research system. The PR remains draft.
