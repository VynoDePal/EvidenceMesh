# Providers

## Deployment profiles

`community` is the default and contains `searxng`, bounded one-query `ddgs`,
`wikipedia`, `crossref`, `arxiv` and `github`. It requires no key, but internet
access, compute and storage are not cost-free infrastructure. The independently
crawled Mwmbl and Wiby adapters and the self-hosted YaCy adapter are explicit
opt-ins. None is silently promoted by Phase 11.2.

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
quality, and the second-network release gate remains unavailable. Phase 10 then
showed a separate general-web regression: the one-query Tavily arm retained
substantially more useful evidence than the full quality route. The
[Phase 11 protocol](benchmark-protocol-v9.md) freezes provider-lineage
instrumentation, a temporary Tavily-first policy and community resilience tests
without making any model call.

The published
[Phase 11 result](../benchmarks/results/phase11_calibration_2026-07-29.md)
reached 12/12 availability and navigational target-domain hit@10 for community,
legacy quality, 8/2 quality and Tavily direct. The 8/2 candidate nevertheless
failed its frozen reservation gate: it filled eight Tavily slots in only 10/12
evaluable cases because the per-domain diversity cap constrained two cases.
SearXNG also failed completely in 4/12 cases and returned only partial results
in 8/12. Phase 12 remains blocked; these diagnostics do not establish factual
answer or source quality.

The [Phase 11.1 protocol](benchmark-protocol-v10.md) keeps that failed result
frozen, makes the reservation target explicitly domain-feasible and evaluates
Wiby as an independent-index fallback. It is a corrective calibration, not a
new untouched quality evaluation.

The published
[Phase 11.1 result](../benchmarks/results/phase11_1_calibration_2026-07-29.md)
fulfilled its domain-aware reservation target in 12/12 cases, but reached only
89/96 total target slots against the frozen minimum of 90. Wiby returned
results in 4/12 cases and survived community selection in 0/12. Its attribution
was present in all four applicable cases. The candidate failed, so Wiby remains
opt-in and Phase 12 remains blocked.

The [Phase 11.2 protocol](benchmark-protocol-v11.md) evaluates Mwmbl as a
larger public independent-index candidate and contract-tests YaCy as a
self-hosted path. It uses a new frozen 16-case suite, one request per public
provider and no paid API, model or retry. The
[architecture assessment](independent-index-assessment-v1.md) compares the
current alternatives. Retrieval performance and default eligibility are
separate gates: Mwmbl's result-license boundary and the absence of a measured,
reproducibly populated YaCy index keep both adapters opt-in even if retrieval
passes.

The published
[Phase 11.2 result](../benchmarks/results/phase11_2_independent_index_2026-07-29.md)
did not pass retrieval. Mwmbl produced a sanitized provider failure and no raw
result in all 16 routed cases. Candidate community consequently tied legacy
community at 16/16 availability and 15/16 target-domain hit@10, while the
Mwmbl-plus-Wiby independent arm reached only 7/16 availability. The first three
case latencies matched the 25-second timeout and later cases were much faster,
which is consistent with circuit opening after three failed adapter attempts.
Because the report counted routed calls rather than separating HTTP attempts
and circuit skips, that diagnosis remains an inference and the traffic field
must not be presented as confirmed network attempts.

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

The historical Phase 6/10 calibration file intentionally isolated DuckDuckGo,
but Phase 10 reused that single-engine file while the documentation described a
multi-engine route. Phase 11 corrects the mismatch with a new checksum-pinned
configuration containing Brave, DuckDuckGo, Startpage and Wikimedia web/news
engines. Historical files and results remain unchanged for reproducibility.

If every result is absent while SearXNG reports unresponsive upstream engines,
the adapter returns a provider failure. When results survive a partial upstream
failure, the raw provider records retain the unavailable engine names for
benchmark diagnostics.

### DDGS

DDGS is a bounded one-query best-effort fallback in the community bundle.
Upstream engines can rate-limit automated traffic and behavior can differ by
network. Phase 2 and Phase 3 observed persistent failure in one managed
environment, so DDGS is redundancy rather than a guaranteed independent search
index. Failures remain isolated as partial-provider warnings, and operators can
remove it with an explicit `EVIDENCEMESH_PROVIDERS` value.

### Wiby

[Wiby](https://wiby.me/) maintains its own crawler and deliberately small-web
index. Its [JSON API](https://wiby.me/json/) requires no key and requires a link
back to Wiby with results. EvidenceMesh routes one base web query, never
requests Wiby's optional unfiltered mode and emits the required link in
`metadata.provider_attributions` whenever Wiby returns results.

Wiby is a specialized, comparatively small index. It offers genuine index
independence but did not meet the frozen availability or selected-contribution
gates, so it is not enabled by either named bundle. Opt in with
`EVIDENCEMESH_PROVIDERS` when small-web recall is useful. The public endpoint is
best effort and must not be load-tested. The
[GPLv2 installation guide](https://wiby.me/about/guide.html) supports
self-hosting; point EvidenceMesh at a compatible deployment with
`EVIDENCEMESH_WIBY_URL`.

### Mwmbl

[Mwmbl](https://mwmbl.org/) is an open-source nonprofit search engine with its
own community-crawled index. EvidenceMesh calls the anonymous v2 endpoint once
per base Web query and enforces a 24-hour minimum search-cache lifetime. The
public service documents a 1,000-request monthly anonymous tier and a
one-request-per-second rate, so it is unsuitable for load testing.

Mwmbl marks returned search results as
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
EvidenceMesh emits that fixed URL in
`metadata.provider_result_licenses["mwmbl"]` whenever Mwmbl returns results.
This makes the constraint visible but does not resolve its downstream
application. Mwmbl is therefore absent from named bundles. Opt in with
`EVIDENCEMESH_PROVIDERS=mwmbl`; a compatible endpoint can be selected with
`EVIDENCEMESH_MWMBL_URL`.

In the Phase 11.2 GitHub-hosted run, the public endpoint did not return a usable
response through the adapter. This is a measured deployment-reliability failure,
not evidence that the underlying index contains no useful pages. Do not promote
the public endpoint without new, pre-registered calibration and corrected
network-attempt telemetry.

### YaCy

[YaCy](https://yacy.net/) crawls and indexes pages under operator control and
can query a local index or its peer network. EvidenceMesh calls
`/yacysearch.json` once per base Web query. The default resource is `local`;
select `global` explicitly with `EVIDENCEMESH_YACY_RESOURCE`.

Start the checksum-pinned optional service with
`docker compose --profile independent-index up -d yacy`, then populate and
administer its index according to YaCy's documentation. Adapter correctness
does not imply useful coverage: storage, bandwidth, crawl policy and ranking
quality remain operator responsibilities. Configure
`EVIDENCEMESH_PROVIDERS=yacy` and `EVIDENCEMESH_YACY_URL`.

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

For web and news in the named `quality` profile, ranking temporarily reserves
80% of the requested slots for eligible Tavily results before filling from the
global fused ranking. URL filtering and the per-domain cap still apply. Phase
11.1 reports the configured request separately from the maximum domain-feasible
target and the actually fulfilled count; a target reduction is never hidden.
Configure or disable the policy with
`EVIDENCEMESH_QUALITY_PRIMARY_PROVIDER` and
`EVIDENCEMESH_QUALITY_PRIMARY_PROVIDER_SHARE`. This is a Phase 11 safety policy,
not evidence that Tavily results are intrinsically correct.

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
| Web | SearXNG, DDGS, Wikipedia; quality adds Tavily; Mwmbl, Wiby and YaCy are opt-in | unlimited, 1, 2 and 1; each independent adapter 1 | 3 |
| Reference | Wikipedia | 2 | 10 |
| News | SearXNG, DDGS | unlimited and 1 | 3 |
| Academic | Crossref, arXiv, Wikipedia | 2, 1 and 2 | 10 |
| Code | GitHub repositories | 1 | 10 |

Quality adapters join only the profiles they support. Search metadata records
the deployment profile, routed query count and source family for every requested
provider. It also keeps per-family call, success, failure and result counts,
lists degraded and fully failed families, and reports the required family as
`satisfied`, `empty`, `failed` or `not_configured`. Raw provider failures remain
available even when another route satisfies the request. The effective
per-domain maximum and whether it came from the profile default or an explicit
request override are also reported. Provider lineage is counted at raw, fused,
eligible, selected and evidence stages, with adjacent loss counts. Metadata also
reports quality reservation request, eligibility, domain-feasible target,
fulfillment and shortfall reason, plus SearXNG contributing or unresponsive
engine query counts. Provider attribution and provider-result-license links are
explicit. Total upstream failures retain a sanitized failure kind and
unavailable-engine counts, including calls that returned no result.

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

Use `EVIDENCEMESH_SEARXNG_URL`, `EVIDENCEMESH_MWMBL_URL`,
`EVIDENCEMESH_WIBY_URL`, `EVIDENCEMESH_YACY_URL` and
`EVIDENCEMESH_FIRECRAWL_URL`. Additional
operator-controlled SearXNG endpoints can be supplied as a comma-separated
`EVIDENCEMESH_SEARXNG_FALLBACK_URLS` list. Each endpoint receives its own
provider name and circuit state. Provider service URLs are trusted administrator
configuration, while document URLs returned by search are still subject to the
outbound safety policy.
