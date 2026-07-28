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
- Per-provider circuit breakers with fail-fast open state, single half-open
  recovery probes and runtime health telemetry.
- Checksum-pinned SearXNG Compose profile with a live adapter integration job.
- Published 200-row SimpleQA reliability run with logical-call, network-attempt
  and circuit-skip accounting; release decision remains no-go.
- Replaced DDGS in the recommended profile with the pinned, self-hosted
  SearXNG path and added explicit upstream-engine failure accounting.
- Added a 200-case SearXNG GitHub Actions benchmark with image/config
  provenance and a privacy-separated end-to-end answer-generation harness.
- Published the Phase 4 retrieval result: SearXNG completed four of ten network
  attempts before 190 circuit skips; the overall release decision remains
  no-go.
- Locked the Phase 5 provider-selection protocol, independent 12-query
  calibration suite and 96-request GitHub workflow for eight keyless SearXNG
  engines. The workflow blocks a tuned 200-case run unless at least two
  engines pass every pre-registered gate.
- Published the valid Phase 5 calibration: DuckDuckGo was the sole eligible
  engine, so the minimum-two-engine gate closed, production configuration
  remained unchanged and the held-out retrieval and local-model stages were
  not run.
- Added result-engine isolation telemetry after invalidating an initial mixed-
  engine run, and confined the ephemeral calibration secret to the container
  launch command so it is not persisted in the GitHub Actions job environment.
