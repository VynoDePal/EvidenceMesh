# Changelog

All notable changes to EvidenceMesh are documented here.

## 0.1.0 - 2026-07-28

- Initial evidence-first search engine and Python SDK.
- FastMCP tools over STDIO and Streamable HTTP.
- Keyless SearXNG, DDGS, Wikipedia and Crossref providers.
- Optional Brave, Tavily, Exa and Firecrawl providers.
- Reciprocal-rank fusion, source diversity and deterministic deduplication.
- Bounded provider JSON, robots.txt and document fetching; total request
  deadlines; DNS-pinned public-address connections; bounded PDF extraction;
  and prompt-injection risk flags.
- Defensive filtering of malformed, credential-bearing, non-HTTP and literal
  local-network result URLs.
- Frozen-lock runtime dependency installation and container entrypoint smoke
  validation in CI.
- Reproducible offline benchmark and live retrieval benchmark harness.
