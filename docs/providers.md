# Providers

## Zero-key defaults

### SearXNG

EvidenceMesh calls `/search?format=json`. The included Compose configuration is
for local development. Public SearXNG instances can throttle or disable JSON,
so a private instance is recommended.

### DDGS

DDGS is a keyless fallback. Upstream engines can rate-limit automated traffic;
failures are returned as partial-provider warnings.

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

## Custom/self-hosted services

Use `EVIDENCEMESH_SEARXNG_URL` and `EVIDENCEMESH_FIRECRAWL_URL`. Provider
service URLs are trusted administrator configuration, while document URLs
returned by search are still subject to the outbound safety policy.
