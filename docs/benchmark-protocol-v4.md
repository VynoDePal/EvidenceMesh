# Phase 6 multi-source calibration protocol (locked)

Status: locked before the first live request on 2026-07-28.

This protocol evaluates whether the new zero-key `community` composition is
operationally useful across several source families. It is a calibration, not a
claim that EvidenceMesh is the best search or deep-research system.

## Frozen system

The candidate composition is:

| Search profile | Routed providers | Source family |
|---|---|---|
| `web` | private SearXNG with DuckDuckGo; Wikimedia search | web; reference |
| `academic` | Crossref; arXiv; Wikimedia search | academic; reference |
| `code` | GitHub public repository search | code |

The SearXNG candidate uses the Phase 5 winner in isolation. It is experimental
and does not modify `docker/searxng/settings.yml`.

The `quality` deployment profile is structurally tested but is outside this live
calibration because it depends on user-supplied keys. OpenAlex is optional
because its 2026 API policy requires a free API key. Brave, Tavily, Exa and
cloud Firecrawl remain optional. A GitHub token is optional and only raises the
public repository-search quota.

Common Crawl is excluded from query search: its CDX index locates archived URLs
and is not a full-text web-search engine. A future archive lookup must have its
own API contract and traffic protocol.

## Frozen inputs

- Suite: `benchmarks/data/multisource_calibration_v1.json`
- Suite SHA-256:
  `e99e584cb115a3bb343d052b368e127acd924be7a6aabef98ae90c3c86acce34`
- SearXNG configuration:
  `docker/searxng/community-calibration-settings.yml`
- Configuration SHA-256:
  `26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645`
- SearXNG image:
  `searxng/searxng:2026.7.26-b060c780d@sha256:d0aaeb14880e6e92bde1518fcc7261e995783367d63d95203383607bef9c6516`
- 24 authored public queries: six each for web, reference, academic and
  repository-code retrieval
- 10 returned results maximum per case
- one call per case; no retry
- sequential cases; 0.5 seconds between cases
- request deadline: 20 seconds
- content fetching: disabled
- fresh temporary cache, retained during the run

The suite does not contain SimpleQA questions and is not an answer-quality
dataset. Query and result text are omitted from the public outcome rows.

## Source-specific traffic rules

- arXiv receives only the base query. Calls are serialized process-wide per
  event loop, request starts are at least three seconds apart, and successful
  responses have a minimum cache lifetime of 24 hours.
- GitHub receives only the base query and uses public repository search, not
  code-content search. Anonymous execution is limited to this six-case suite.
- Wikimedia receives an identifying EvidenceMesh `User-Agent`.
- The private SearXNG instance sends only the six web and six reference cases
  to its isolated DuckDuckGo engine.
- There are no retries or failure-triggered extra requests.

## Metrics

The report records overall and per-topic:

- availability: at least one result;
- target-domain hit at 10;
- expected source-family hit at 10;
- partial-failure rate;
- p50 and p95 wall-clock latency;
- provider requested, succeeded and contributed case counts;
- source-family contribution counts.

A provider contributes to a case only if at least one of the ten returned hits
contains that provider in provenance. Domain matching accepts the exact host or
a subdomain.

## Pre-registered gates

The single-environment functional gate passes only if every condition is true:

| Gate | Threshold |
|---|---:|
| Availability | at least 90% |
| Target-domain hit at 10 | at least 75% |
| Expected-family hit at 10 | at least 80% |
| Partial failures | at most 25% |
| p95 latency | at most 15,000 ms |
| Contributing providers | at least 4 |
| Contributing source families | all 4 expected families |

No threshold may be changed after the first live request. A failed gate can only
be investigated on a new suite and protocol version.

## Cross-network and release decision

Two successful runs from independently administered network environments are a
mandatory release gate. The user cannot provide a second network for Phase 6,
so this condition is pre-recorded as `not_testable`, not waived.

Consequences:

1. The 24-case GitHub-hosted calibration may run once.
2. A 200-case Stage B run is allowed only after both the functional gate and
   the two-network gate pass.
3. Phase 6 cannot produce a release-ready or superiority verdict.
4. Passing the functional gate means only that the candidate deserves an
   independent-network replication.

## Public provenance

The raw JSON report must include the commit SHA, UTC timestamp, Python and
platform versions, network label, suite and configuration hashes, immutable
container digest, exact protocol parameters, aggregate metrics and 24 redacted
outcome rows. It must not include queries, titles, snippets, content or URLs.

Relevant upstream policies:

- [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)
- [arXiv API terms](https://info.arxiv.org/help/api/tou.html)
- [Wikimedia API access policy](https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy)
- [GitHub repository search API](https://docs.github.com/en/rest/search/search)
- [OpenAlex API key guidance](https://developers.openalex.org/guides/llm-quick-reference)
- [Common Crawl index server](https://index.commoncrawl.org/)
