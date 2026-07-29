# Phase 7 quality-profile calibration protocol (locked)

Status: locked before the first live request on 2026-07-29.

This protocol tests whether Tavily closes the general-web reliability gap found
in Phase 6 while preserving a zero-key `community` profile. It is a retrieval
calibration, not an end-to-end answer-quality test or a claim that EvidenceMesh
is the best search or deep-research system.

## Frozen candidate

The named `quality` profile contains the five `community` providers plus
Tavily. Other implemented keyed adapters remain available through an explicit
provider list, but they are outside this candidate.

| Search profile | Routed providers | Required source family |
|---|---|---|
| `web` | private SearXNG with DuckDuckGo; Wikipedia; Tavily basic search | web |
| `reference` | Wikipedia | reference |
| `academic` | Crossref; arXiv; Wikipedia | academic |
| `code` | GitHub public repository search | code |

The explicit `reference` profile prevents an encyclopedic lookup from
needlessly depending on the degradable general-web route. Wikipedia can still
supplement web and academic searches.

Tavily supports only web and news routes in this candidate. It receives the
base query only, uses `search_depth=basic`, disables generated answers and raw
content, and returns at most ten results. This bounds the live calibration to
eight Tavily requests and eight credits. Tavily is an external keyed service;
the EvidenceMesh implementation remains Apache-2.0 open source.

## Frozen inputs

- Suite: `benchmarks/data/quality_calibration_v2.json`
- Suite SHA-256:
  `bfa1b033d31e509f622d35d7eb224498db9ba7a939fce3554b0a57c44417b869`
- SearXNG configuration:
  `docker/searxng/community-calibration-settings.yml`
- Configuration SHA-256:
  `26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645`
- SearXNG image:
  `searxng/searxng:2026.7.26-b060c780d@sha256:d0aaeb14880e6e92bde1518fcc7261e995783367d63d95203383607bef9c6516`
- 32 authored public queries: eight each for web, reference, academic and
  repository-code retrieval
- no exact query overlap with the Phase 6 calibration suite
- exact expected URL prefixes for reference, academic and code cases; expected
  official domains for web cases
- ten returned results maximum per case
- one search per case; no query variants and no retry
- sequential cases; 0.5 seconds between cases
- request deadline: 20 seconds
- content fetching: disabled
- fresh temporary cache, retained during the run

No query, title, snippet, content, result URL, expected domain or expected URL
prefix is copied into public outcome rows.

## Credential boundary

The GitHub Actions secret is named `EVIDENCE_MESH_TAVILY_KEY`. The workflow maps
it to the runtime-only `TAVILY_API_KEY` variable expected by EvidenceMesh.
Neither the value nor a fingerprint is written to logs, artifacts, reports,
caches or configuration manifests. A missing secret aborts before live traffic.

## Source-specific traffic rules

- Tavily receives exactly the eight web cases, at most one call per case.
  `auto_parameters`, generated answers and raw content remain disabled.
- arXiv receives only the base query. Calls are serialized process-wide per
  event loop, request starts are at least three seconds apart, and successful
  responses have a minimum cache lifetime of 24 hours.
- GitHub receives only the base query and uses public repository search, not
  code-content search.
- The private SearXNG instance receives only the eight web cases.
- Wikipedia alone receives the eight explicit reference cases.
- There are no retries or failure-triggered extra requests.

## Failure semantics

Provider degradation and route failure are reported separately:

- `provider_degradation`: at least one routed provider-query call failed;
- `required_family_status=satisfied`: at least one result from the profile's
  required source family survived ranking;
- `empty`: a required-family call completed but produced no required-family
  result;
- `failed`: every required-family call failed;
- `not_configured`: no compatible required-family provider was routed.

Raw provider failures are retained. The new status does not erase or relabel a
failed provider; it identifies whether the failure prevented the requested
source family from producing evidence.

## Metrics

The report records overall and per topic:

- availability;
- authored target hit at 10;
- expected-family hit at 10;
- any-provider degradation rate;
- required-family unsatisfied rate;
- p50 and p95 wall-clock latency;
- provider requested, succeeded and contributed case counts;
- source-family contribution counts.

A provider contributes only if at least one of the ten returned hits retains
that provider in provenance. Exact URL-prefix targets are case-insensitive
prefix comparisons after EvidenceMesh URL canonicalisation. Domain targets
accept the exact host or a subdomain.

## Pre-registered gates

The single-environment functional gate passes only if every overall, per-topic
and Tavily-specific condition is true.

### Overall

| Gate | Threshold |
|---|---:|
| Availability | at least 90% |
| Target hit at 10 | at least 80% |
| Expected-family hit at 10 | at least 90% |
| Any-provider degradation | at most 25% |
| Required-family unsatisfied | at most 10% |
| p95 latency | at most 15,000 ms |
| Contributing providers | at least 5 |
| Contributing source families | all 4 expected families |

### Every topic independently

| Gate | Threshold |
|---|---:|
| Availability | at least 7/8 (87.5%) |
| Target hit at 10 | at least 6/8 (75%) |
| Expected-family hit at 10 | at least 7/8 (87.5%) |
| Required-family unsatisfied | at most 1/8 (12.5%) |

### Tavily

| Gate | Threshold |
|---|---:|
| Requested web cases | exactly 8 |
| Successful cases | at least 7/8 |
| Contributing cases | at least 6/8 |
| Query budget | at most one Tavily query per case |

No threshold, query or expected target may change after the first live request.
A failed gate can only be investigated on a new suite and protocol version.

## Cross-network and release decision

Two successful runs from independently administered network environments
remain a mandatory release gate. A second environment is unavailable for this
phase and is recorded as `not_testable`, not waived.

Consequences:

1. The 32-case GitHub-hosted calibration may run once.
2. The 200-case Stage B run remains blocked regardless of the Phase 7
   single-network result.
3. Merge, package publication, production-readiness and superiority claims
   remain blocked.
4. A functional pass means only that the candidate deserves independent
   replication.

Relevant upstream documentation:

- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily credits](https://docs.tavily.com/documentation/api-credits)
- [arXiv API terms](https://info.arxiv.org/help/api/tou.html)
- [Wikimedia API access policy](https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy)
- [GitHub repository search API](https://docs.github.com/en/rest/search/search)
