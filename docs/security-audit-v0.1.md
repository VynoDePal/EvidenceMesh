# Security and release audit — v0.1

Date: 2026-07-28

## Scope and limits

This review covers the EvidenceMesh Python SDK, provider federation, URL
handling, document fetcher, extraction pipeline, FastMCP interface, container
build and CI configuration in pull request 1.

It is a maintainer-side adversarial review, not an independent penetration test
or a formal security certification.

## Methods

- manual trust-boundary and failure-path review;
- malformed and non-HTTP provider-result tests;
- redirect, byte-limit, provider/fetch deadline and concurrency-queue tests;
- 20,000 deterministic random URL parser cases;
- a local TLS integration check proving that an IP-pinned connection preserves
  the original HTTP Host and validates the certificate with the original SNI;
- Ruff security/static rules, strict mypy and branch-aware pytest coverage;
- wheel and source-distribution builds from the committed package metadata.

## Findings closed in this audit

| Severity | Finding | Resolution |
|---|---|---|
| High | DNS could change between validation and connection | Resolve once, reject the full answer set if any address is non-public, and connect to the exact validated IP while preserving Host and TLS SNI |
| High | Hostile provider URLs could expose non-HTTP links or crash ranking with malformed IPv6 | Filter malformed, credential-bearing, non-HTTP and literal local-network result URLs; make parsing non-throwing; preserve valid IPv6 brackets |
| Medium | `robots.txt` used an unbounded buffered read | Stream and cap decompressed robots data at 512 KB |
| Medium | A slow provider or a saturated concurrency queue could hold a tool call indefinitely | Apply total provider/fetch deadlines that include queue wait and return explicit partial failures |
| Medium | PDF parsing ran on the event loop without a page ceiling | Move extraction to a worker, enforce an extraction deadline and cap PDF pages |
| Medium | The container resolved runtime dependencies independently of `uv.lock` | Build the runtime environment from the frozen lock and validate the image in CI |
| Medium | The built virtual environment was copied to a different path, invalidating absolute console-script shebangs | Build it at its final runtime path and execute the installed CLI in the container CI job |
| Low | MCP progress logs included the raw user query | Log the operation and profile without query contents |
| Low | Invalid boolean environment values silently became false | Reject unknown boolean spellings during configuration |

## Residual risks

- Streamable HTTP has no built-in deployment authentication or per-user rate
  limiting. Keep it on loopback or place it behind authenticated TLS ingress.
- A public IP can still front a sensitive virtual service.
- A timed-out synchronous provider or extraction worker can continue briefly in
  its background thread.
- PDF and HTML parser dependencies remain an attack surface; production
  deployments still need container CPU and memory limits.
- Python and SearXNG container base tags are not digest-pinned, so image
  contents can drift even though Python dependencies use the frozen lock.
- Prompt-injection and source-quality signals are heuristic, not guarantees.
- No independent third-party security audit has been completed.

## Release gate

Status: **conditional pass for an alpha release**.

The branch may proceed to merge only after the complete GitHub Actions matrix,
including the container build and dependency audit, succeeds on the audit
commit. The remaining risks prevent a high-assurance or `1.0` security claim.
