# Phase 8 profile-aware quality calibration protocol (locked)

Status: locked before the first live request on 2026-07-29.

This protocol tests the profile-aware diversity and repository-query changes
motivated by Phase 7. It is a small retrieval calibration, not an end-to-end
answer-quality evaluation or a claim that EvidenceMesh is the best search or
deep-research system.

## Frozen candidate

The provider bundle is unchanged from the Phase 7 `quality` candidate:

| Search profile | Routed providers | Required source family | Default maximum per domain |
|---|---|---|---:|
| `web` | private SearXNG with DuckDuckGo; Wikipedia; Tavily basic | web | 3 |
| `reference` | Wikipedia | reference | 10 |
| `academic` | Crossref; arXiv; Wikipedia | academic | 10 |
| `code` | anonymous GitHub public repository search | code | 10 |

The Web and news profiles retain a three-result domain-diversity cap. The
single-domain reference, academic and code verticals may fill all ten result
slots. An explicit request value still overrides the profile default. Every
response records the effective cap and whether it came from a profile default
or a request override.

GitHub repository queries remove only trailing generic intent such as
`repository`, `official GitHub repository` or `source code`, then add
`in:name,description`. The normalized query is limited to GitHub's 256-character
query limit. Search remains anonymous, repository-only and limited to one API
call per case.

## Frozen inputs

- Suite: `benchmarks/data/quality_calibration_v3.json`
- Suite SHA-256:
  `4a080230b0fe4590f1ef1af9087c7dbfaa05910bdcbd9c43a197cf87c5e44dc4`
- Suite manifest SHA-256:
  `7afd84280ae74b6fe2e4e28b490c26375b0c130e3a1f3efdfbbd864e36e8834c`
- SearXNG configuration:
  `docker/searxng/community-calibration-settings.yml`
- Configuration SHA-256:
  `26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645`
- SearXNG image:
  `searxng/searxng:2026.7.26-b060c780d@sha256:d0aaeb14880e6e92bde1518fcc7261e995783367d63d95203383607bef9c6516`
- 32 authored public queries: eight each for web, reference, academic and
  repository-code retrieval
- no exact query overlap with the Phase 6 or Phase 7 calibration suites
- ten returned results maximum per case
- one search per case, no query variants and no retry
- sequential cases, 0.5 seconds between cases
- request deadline: 20 seconds
- content fetching: disabled
- fresh temporary cache, retained during the run

No query, title, snippet, content, result URL or target identity is copied into
public outcome rows.

## Canonical target identity

Protocol v6 replaces URL-prefix matching with typed identities:

- `domain:<host>` accepts the exact host or a subdomain;
- `wikipedia:<language>:<slug>` normalizes case, spaces and underscores;
- `arxiv:<id>` recognizes arXiv abstract and PDF URLs, version suffixes,
  HTTP/HTTPS aliases and `doi.org/10.48550/arXiv.<id>`;
- `github:<owner>/<repository>` normalizes case and an optional `.git` suffix.

The public suite contains these authored identities, but outcome rows contain
only match booleans and numeric ranks.

## Diagnostic rank capture

Each provider is wrapped in memory during the benchmark. The wrapper delegates
the search exactly once, records the returned `ProviderResult` objects for the
current case and makes no additional network request.

Each public outcome records:

- final `target_rank`, or null when absent from the returned top ten;
- `raw_target_seen`;
- minimum `raw_target_provider_ranks` by provider;
- `target_dropped_by_ranking`, true only when a provider returned the target
  but EvidenceMesh did not retain it.

This separates upstream retrieval misses from fusion, deduplication or
diversity losses without publishing result content.

## Credential and traffic boundary

The GitHub Actions secret is named `EVIDENCE_MESH_TAVILY_KEY` and is mapped only
to the runtime `TAVILY_API_KEY` variable. Neither the value nor a fingerprint
is written to logs, artifacts, reports, caches or manifests. A missing secret
aborts before live traffic.

- Tavily receives exactly the eight Web cases, at most one basic-search call
  and one credit per case. Generated answers and raw content stay disabled.
- arXiv receives only the base query. Calls are serialized process-wide per
  event loop, starts are at least three seconds apart and successful responses
  have a minimum 24-hour cache lifetime.
- GitHub receives only the base query and uses public repository search.
- The private SearXNG instance receives only the eight Web cases.
- Wikipedia alone receives the eight reference cases.
- There are no retries or failure-triggered extra requests.

## Metrics and frozen gates

The report records overall and per topic:

- availability;
- canonical target hit at 10 and final target-rank distribution;
- raw target seen and target dropped by ranking;
- expected-family hit at 10;
- any-provider degradation and required-family unsatisfied rates;
- p50 and p95 wall-clock latency;
- provider requested, succeeded and contributed case counts;
- source-family contribution counts.

The Phase 7 thresholds are retained unchanged.

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
| Requested Web cases | exactly 8 |
| Successful cases | at least 7/8 |
| Contributing cases | at least 6/8 |
| Query budget | at most one Tavily query per case |

No threshold, query, expected identity or routing rule may change after the
first live request. A failed gate can be investigated only with a new suite and
protocol version.

## Cross-network and release decision

Two successful runs from independently administered network environments
remain mandatory. A second environment is unavailable and is recorded as
`not_testable`, not waived.

Therefore Stage B remains blocked regardless of this single-network result.
Merge, package publication, production-readiness and superiority claims remain
blocked. A functional pass means only that the candidate warrants independent
replication.

Relevant upstream documentation:

- [GitHub repository search syntax](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)
- [GitHub REST search API](https://docs.github.com/en/rest/search/search)
- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily credits](https://docs.tavily.com/documentation/api-credits)
- [arXiv API terms](https://info.arxiv.org/help/api/tou.html)
- [Wikimedia API access policy](https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy)
