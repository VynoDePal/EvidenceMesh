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
- Added named zero-key `community` and optional-key `quality` deployments,
  deterministic source-family routing and per-provider query budgets.
- Added bounded arXiv Atom, GitHub public-repository and keyed OpenAlex
  adapters, including arXiv pacing and a 24-hour minimum search cache.
- Locked the 24-case Phase 6 multi-source calibration and its two-independent-
  network release gate; Common Crawl remains an archive candidate rather than
  being misrepresented as full-text query search.
- Published the Phase 6 result: 24/24 availability, 22/24 target and expected-
  family hits, but 8/24 partial failures because SearXNG succeeded in only 4/12
  routed cases. The functional gate failed, so Stage B was not run and the
  release decision remains no-go.
- Added an explicit reference profile and per-family call, result and failure
  telemetry without suppressing raw provider errors.
- Narrowed the recommended keyed `quality` bundle to Tavily, capped Tavily at
  one basic web/news query per search, and left other keyed adapters available
  as explicit opt-ins.
- Locked the Phase 7 quality protocol, an untouched 32-case suite, strict
  per-topic gates and a maximum eight-credit Tavily calibration. The
  independent-network and release gates remain closed.
- Published the Phase 7 result: Tavily passed its 8/8 requested, successful and
  contributing gates and web hit 8/8 targets, but the complete candidate hit
  only 18/32 exact targets because academic reached 2/8 and code reached 0/8.
  The functional gate failed, Stage B was not run and release remains no-go.
- Added profile-aware source diversity: web/news retain a three-result
  per-domain default while reference, academic and code can fill ten result
  slots; explicit request overrides and the effective policy are reported.
- Normalized natural-language GitHub repository queries into bounded
  name/description search without increasing the one-query provider budget.
- Locked the Phase 8 protocol and untouched 32-case suite with canonical target
  identities, provider-native target-rank diagnostics, unchanged functional
  thresholds and the same eight-credit Tavily ceiling. The independent-network
  and release gates remain closed.
- Published the Phase 8 result: all overall gates passed at 26/32 targets, but
  code reached only 4/8 against the locked 6/8 minimum. Five of six misses were
  absent upstream and one was removed by ranking; the functional gate failed,
  Stage B was not run and release remains no-go.
- Replaced descriptive GitHub repository searches with a deterministic
  entity-anchor planner that preserves explicit qualifiers and exact
  repository references, searches name/description/topics, and retains the
  one-query provider budget.
- Locked the Phase 9 paired GitHub-recall protocol and 24-case suite. The
  Phase 8 baseline and candidate run on the same cases with anonymous,
  rate-paced traffic, no Tavily calls, no cache and no retries; the
  independent-network and release gates remain closed.
- Published the Phase 9 result: the entity-anchor candidate retrieved 24/24
  repository targets at ten against 4/24 for the frozen baseline, producing 20
  paired gains and zero regressions while staying within one query per case.
  Every functional gate passed, but the unavailable second network keeps Stage
  B blocked and the release decision at no-go.
- Locked the Phase 10 controlled end-to-end protocol and an untouched 12-case
  SimpleQA manifest excluding the Phase 3 sample. Four retrieval arms reuse
  identical evidence packets across `gemma-4-31b-it`,
  `gemma-4-26b-a4b-it` and `gemini-3.5-flash-lite`.
- Added a native Gemini `generateContent` runner with high thinking, 144
  generation calls, 36 retrieval case-arm operations, a 24-request Tavily
  ceiling, no retries, privacy-safe output and explicitly labeled
  answer/evidence/citation substring proxies. External replication and the
  unavailable second network keep Stage B and release blocked.
- Published the Phase 10 result: Tavily direct reached 27/36 strict
  answer-key-covered outputs, quality 13/36 and community 6/36. SearXNG
  degraded in all EvidenceMesh web cases, quality lost 14 net pairs to Tavily
  direct and missed retrieval, generation and citation gates. The functional
  gate failed and release remains no-go.
- Added raw-to-prompt provider lineage, sanitized upstream-engine failure
  telemetry, bounded DDGS community fallback, independent SearXNG endpoint
  circuits and a temporary Tavily-first quality reservation.
- Published the Phase 11 retrieval calibration: community and 8/2 quality both
  reached 12/12 availability and target-domain hit@10, but the 8/2 reservation
  was fully satisfied in only 10/12 evaluable cases. The frozen candidate gate
  failed, Phase 12 remains blocked and release remains no-go.
- Added a zero-key Wiby adapter as a bounded independent-crawl source,
  including mandatory provider attribution and a configurable compatible
  endpoint.
- Split primary-provider reservation telemetry into requested, eligible,
  domain-feasible, target and fulfilled counts with explicit shortfall causes.
- Locked the Phase 11.1 corrective protocol and GitHub workflow before any
  benchmark-suite traffic, after one disclosed non-suite Wiby schema check. It
  reuses the authored Phase 11 diagnostic suite, caps Tavily and Wiby at 12
  calls each, makes no model request and keeps release no-go.
- Published the Phase 11.1 result: the domain-aware target was fulfilled in
  12/12 cases but reached 89/96 total slots against a frozen minimum of 90;
  Wiby returned results in 4/12 cases and survived community selection in
  0/12. The candidate failed, Wiby remains opt-in, Phase 12 stays blocked and
  release remains no-go.
- Added opt-in Mwmbl and YaCy adapters for a public community-crawled index and
  an operator-controlled local or peer index. Mwmbl result-license metadata is
  preserved, and YaCy is available through a checksum-pinned optional Compose
  profile without implying that an unpopulated index has broad coverage.
- Locked the Phase 11.2 independent-index protocol and balanced 16-case
  calibration suite before scored traffic. Five arms replay one shared raw
  pool with exactly 16 Mwmbl and 16 Wiby requests, no paid API, no model and no
  retry; default promotion, Phase 12 and release remain blocked independently
  of retrieval performance.
