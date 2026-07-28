# Providers

## Zero-key defaults

### SearXNG

EvidenceMesh calls `/search?format=json`. The included Compose configuration is
the recommended zero-key general-web path. It pins SearXNG
`2026.7.26-b060c780d` and its multi-platform image digest, enables JSON
explicitly, and retains a small zero-key engine set for web, news, science and
code searches. General web uses `brave`, `duckduckgo` and `wikipedia`; the
complete list is reviewable in the settings file. Upstream requests are bounded
at eight seconds. Public SearXNG instances can throttle or disable JSON; do not
load-test them. Run the included private instance.

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

Wikipedia is used as a reference source for web and academic profiles. It
improves entity coverage but should not replace primary sources.

### Crossref

Crossref is enabled only for the academic profile. Set `CROSSREF_MAILTO` to use
the polite pool and identify your client.

## Optional API providers

| Provider | Environment variable | Authentication |
|---|---|---|
| Brave | `BRAVE_API_KEY` | `X-Subscription-Token` |
| Tavily | `TAVILY_API_KEY` | Bearer |
| Exa | `EXA_API_KEY` | `x-api-key` |
| Firecrawl | `FIRECRAWL_API_KEY` | Bearer for cloud |

Provider pricing, retention and quotas are controlled by those providers and can
change independently. EvidenceMesh never labels a limited free tier as an
unlimited free backend. Every HTTP provider response is streamed through a
5 MB decompressed-size limit before JSON parsing.

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
