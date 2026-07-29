# Providers

## Deployment profiles

`community` is the default and contains `searxng`, `wikipedia`, `crossref`,
`arxiv` and `github`. It requires no key and is self-hostable, but internet
access, compute and storage are not cost-free infrastructure.

`quality` includes the community set plus Tavily, the current recommended
general-web candidate. Tavily is enabled only when `TAVILY_API_KEY` is
configured; a missing credential remains visible as a health warning and marks
the service degraded. OpenAlex, Brave, Exa and Firecrawl remain implemented
explicit opt-ins. Set `EVIDENCEMESH_DEPLOYMENT_PROFILE=quality`, or override
either bundle with an explicit comma-separated `EVIDENCEMESH_PROVIDERS`.

In the locked Phase 7 calibration, Tavily was requested, succeeded and
contributed in 8/8 web cases, and every web target was retrieved. The complete
quality candidate still failed its functional gate because exact academic and
repository targets underperformed. See the
[raw and interpreted result](../benchmarks/results/quality_calibration_phase7_2026-07-29.md).
The separate [Phase 8 protocol](benchmark-protocol-v6.md) preserves that result
and pre-registers profile-aware diversity and target-rank diagnostics on a new
suite. Its
[committed result](../benchmarks/results/quality_calibration_phase8_2026-07-29.md)
retrieved 7/8 academic targets but only 4/8 repository targets. All four
repository misses were absent from GitHub's provider-native result list rather
than removed by EvidenceMesh ranking, identifying repository-query recall as
the next isolated defect. The locked
[Phase 9 protocol](benchmark-protocol-v7.md) compares that Phase 8 strategy
against the default entity-anchor planner on the same 24 new repository cases.
Its
[committed result](../benchmarks/results/github_recall_phase9_2026-07-29.md)
found 24/24 targets for the candidate against 4/24 for the baseline, with 20
paired gains and no regression. That resolves the measured query-planning
defect on the locked repository suite; it does not establish general search
quality, and the second-network release gate remains unavailable.

## Zero-key community providers

### SearXNG

EvidenceMesh calls `/search?format=json`. The included Compose configuration is
the recommended zero-key general-web path. It pins SearXNG
`2026.7.26-b060c780d` and its multi-platform image digest, enables JSON
explicitly, and retains a small zero-key engine set for web, news, science and
code searches. General web uses `brave`, `duckduckgo` and `wikipedia`; the
complete list is reviewable in the settings file. Upstream requests are bounded
at eight seconds. Public SearXNG instances can throttle or disable JSON; do not
load-test them. Run the included private instance. The router uses SearXNG for
web and news only; dedicated providers handle academic and repository searches.
The isolated DuckDuckGo candidate still failed 8/12 routed calls in the Phase 6
GitHub calibration, so it must be treated as a degradable path rather than a
reliable sole web backend.

If every result is absent while SearXNG reports unresponsive upstream engines,
the adapter returns a provider failure. When results survive a partial upstream
failure, the raw provider records retain the unavailable engine names for
benchmark diagnostics.

### DDGS

DDGS is an opt-in experimental fallback, not a default. Upstream engines can
rate-limit automated traffic and behavior can differ by network. Phase 2 and
Phase 3 observed persistent failure in one managed environment, so enabling it
requires an explicit `EVIDENCEMESH_PROVIDERS` value. Failures remain isolated as
partial-provider warnings.

### Wikipedia

Wikipedia is the sole provider for the explicit reference profile and can also
supplement web and academic searches. It improves entity coverage but should
not replace primary sources.

### Crossref

Crossref is enabled only for the academic profile. Set `CROSSREF_MAILTO` to use
the polite pool and identify your client.

### arXiv

arXiv is enabled only for the academic profile and reads its bounded Atom feed.
EvidenceMesh routes only the base query, serializes calls, keeps request starts
at least three seconds apart within the active event loop, and applies a minimum
24-hour search-cache lifetime. Those controls reduce traffic but cannot
coordinate independent EvidenceMesh processes or machines; operators remain
responsible for the [arXiv API terms](https://info.arxiv.org/help/api/tou.html).

### GitHub repositories

The code profile uses public repository search. EvidenceMesh deliberately does
not treat anonymous GitHub code-content search as a dependable zero-key API. It
routes only the base query. Exact GitHub URLs, `owner/repository` references and
explicit search qualifiers are preserved. For natural-language intent, the
deterministic planner removes repository boilerplate, extracts the leading
project entity and searches it in `name`, `description` and `topics`. Queries
remain bounded to 256 characters. The planner uses no LLM or lookup and does
not increase the one-query budget. Anonymous public repository search has a low
rate limit; `GITHUB_TOKEN` is optional and raises the applicable quota.

## Optional API providers

| Provider | Environment variable | Authentication |
|---|---|---|
| OpenAlex | `OPENALEX_API_KEY` | `api_key` query parameter |
| GitHub | `GITHUB_TOKEN` | Bearer; optional for public repositories |
| Brave | `BRAVE_API_KEY` | `X-Subscription-Token` |
| Tavily | `TAVILY_API_KEY` | Bearer |
| Exa | `EXA_API_KEY` | `x-api-key` |
| Firecrawl | `FIRECRAWL_API_KEY` | Bearer for cloud |

Provider pricing, retention and quotas are controlled by those providers and can
change independently. EvidenceMesh never labels a limited free tier as an
unlimited free backend. Every HTTP provider response is streamed through a
5 MB decompressed-size limit before parsing. OpenAlex is not in the zero-key
profile: its current API guidance requires a free key for meaningful quota.

### Tavily quality route

The named quality profile routes Tavily only for web and news. A single
EvidenceMesh search sends Tavily at most the base query, explicitly selects
basic depth, disables generated answers and raw content, and caps the API
response at 20 results. Basic Tavily search currently consumes one credit per
request; provider terms and quotas can change independently.

## Deliberate exclusions

Common Crawl's CDX API searches archived URL patterns rather than arbitrary page
text. It is therefore not presented as a search provider. A future archive
lookup would need separate inputs, aggressive caching and its own rate-limit
policy. This distinction prevents an archive index from being benchmarked as if
it were a general search engine.

## Deterministic routing

The public search profile selects compatible source types:

| Profile | Community route | Maximum query variants per provider | Default maximum per domain |
|---|---|---|---:|
| Web | SearXNG, Wikipedia; quality adds Tavily | unlimited, 2 and 1 | 3 |
| Reference | Wikipedia | 2 | 10 |
| News | SearXNG | unlimited | 3 |
| Academic | Crossref, arXiv, Wikipedia | 2, 1 and 2 | 10 |
| Code | GitHub repositories | 1 | 10 |

Quality adapters join only the profiles they support. Search metadata records
the deployment profile, routed query count and source family for every requested
provider. It also keeps per-family call, success, failure and result counts,
lists degraded and fully failed families, and reports the required family as
`satisfied`, `empty`, `failed` or `not_configured`. Raw provider failures remain
available even when another route satisfies the request. The effective
per-domain maximum and whether it came from the profile default or an explicit
request override are also reported.

## Runtime reliability

Each provider has an independent, process-local circuit breaker. Operational
exceptions and EvidenceMesh request deadlines count as failed attempts; empty
but valid result lists count as successful responses except when SearXNG
explicitly reports unavailable upstream engines. The default circuit opens
after three consecutive failures, rejects later network attempts immediately
for 60 seconds, and then permits one half-open recovery probe. A success closes
the circuit. Cached search results are read before circuit admission, so useful
cached evidence remains available while an upstream service recovers.

Configure the policy with:

```bash
export EVIDENCEMESH_PROVIDER_FAILURE_THRESHOLD=3
export EVIDENCEMESH_PROVIDER_RECOVERY_SECONDS=60
```

The `health` tool reports each provider's current state, failure count and
remaining recovery delay without making a network request.

## Custom/self-hosted services

Use `EVIDENCEMESH_SEARXNG_URL` and `EVIDENCEMESH_FIRECRAWL_URL`. Provider
service URLs are trusted administrator configuration, while document URLs
returned by search are still subject to the outbound safety policy.
