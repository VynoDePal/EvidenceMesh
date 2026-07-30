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
- Published the Phase 11.2 result: candidate and legacy community tied at
  16/16 availability and 15/16 target-domain hit@10, while Mwmbl returned no
  raw result and the Mwmbl-plus-Wiby independent arm reached only 7/16
  availability. The retrieval candidate failed, no opportunistic rerun was
  made, named defaults remain unchanged and Phase 12 stays blocked.
- Documented that Phase 11.2 counted routed logical provider calls rather than
  separately measuring HTTP attempts and circuit-open skips. Corrected attempt
  telemetry is required before any independent-index corrective calibration.
- Added privacy-safe provider network observability to the core engine,
  separating logical calls, cache hits, circuit skips, adapter invocations,
  shared-client HTTP attempts, responses, status counts and per-attempt
  latencies.
- Added bounded failure classification for circuit, timeout, DNS, connection,
  HTTP status, JSON, schema, encoding and protocol failures without retaining
  response bodies, URLs or raw exception messages.
- Locked Phase 11.3 as a four-probe, non-scored Mwmbl diagnostic with zero
  Tavily, Gemini, paid-provider or retry traffic. Mwmbl remains outside named
  defaults under its current result-license boundary, no unpopulated YaCy node
  is benchmarked, Phase 12 stays blocked and release remains no-go.
- Published the Phase 11.3 result: all four logical calls reached the adapter
  and HTTP transport, three received HTTP 200 responses with results and one
  timed out without a response at the 15-second deadline. The diagnostic
  validates the observability contract and identifies intermittent endpoint
  reliability without scoring retrieval quality or changing any release gate.
- Locked the Phase 11.4 technical alpha protocol separately from quality
  evaluation. The permanent package CI now installs the built wheel and
  exercises the installed CLI and MCP STDIO subprocess instead of only
  inspecting distribution metadata.
- Added an ephemeral alpha RC workflow with an isolated wheel installation,
  CycloneDX 1.7 SBOM, SHA-256 bundle manifest, immutable action references,
  GitHub keyless SLSA provenance and SBOM attestations, and in-workflow GitHub
  CLI verification. PyPI, GitHub Release, merge, Phase 12 and quality claims
  remain blocked independently of the technical result.
- Rejected the first Phase 11.4 artifact after its post-download audit found an
  unchecksummed MCP stderr log. The accepted rerun keeps logs outside the
  candidate, enforces an exact seven-file inventory and uploads only explicit
  candidate paths.
- Added a deterministic citation audit that validates exact `[S#]` syntax and
  membership without pretending to judge semantic support. Tightened the MCP
  research guide and reusable prompt so externally verifiable claims require
  immediate, packet-local citations.
- Locked Phase 11.5 as a corrective quality calibration on the already-observed
  Phase 10 sample. Three generation arms replay one raw provider pool across
  the same three Gemini API models, with exactly 12 Tavily requests, 108 model
  requests, no retry or repair, a non-blocking community observability arm and
  no access to Phase 12.
- Recorded the audited Phase 11.5 no-go. Six of eight gates passed, including
  94.1% candidate citation presence, 100% citation-ID integrity and 76.5%
  support proxy. Candidate answer-key coverage remained 25/36 versus 28/36
  for Tavily direct, while Gemma 26B missed the completion floor on every arm.
  Phase 12, merge, publication and superiority claims remain blocked.
- Locked Phase 11.6 before its first scored request as a two-arm Tavily
  citation-contract isolation calibration. Both prompts receive byte-identical
  evidence across the three exact Gemini API models, including blocking Gemma
  26B and Gemini 3.5 Flash Lite. The budget is exactly 12 Tavily and 72 model
  requests with no retry, fallback or repair. A ten-gate pass may promote only
  the paid quality default in a separate commit; the free community profile
  remains unchanged and Phase 12 is not executed.
- Recorded the audited Phase 11.6 no-go. Nine of ten gates passed: strict and
  legacy answer-key coverage tied at 25/36, strict citation presence and
  identifier integrity reached 100%, and support proxy reached 82.4%.
  Blocking Gemma 26B completed 10/12 requests in both arms, below the frozen
  11/12 floor. The quality and community defaults are unchanged and Phase 12
  remains blocked.
- Locked Phase 11.7 before its first request as a fresh 24-case Tavily
  confirmation across blocking Gemma 4 31B and Gemini 3.5 Flash Lite. The
  exact budget is 24 Tavily and 96 generation requests with no retry,
  fallback or repair; Gemma 26B is not called and is not blocking.
- Deterministically excluded 212 previously observed SimpleQA identifiers and
  sealed a disjoint 96-case Phase 12 reserve containing no questions, answers
  or distributions. The Phase 11.7 loader may materialize only its own 24
  selectors. The zero-key community profile, draft PR, release boundary and
  user-controlled provider/model choices remain unchanged.
- Recorded the audited Phase 11.7 no-go. Seven of ten gates passed: all 96
  generations completed, strict and legacy answer-key coverage tied at 32/48,
  and strict citation identifiers were 45/45 valid. Prompt evidence was
  answer-bearing for 18/24 cases, strict citation presence reached 45/48 and
  support proxy reached 33/48, below the frozen 20/24, 95% and 75% gates. The
  quality profile is unchanged and Phase 12 remains sealed and blocked.
- Locked Phase 11.8 as an observed-case corrective calibration before its
  first scored request. A single up-to-20-result Tavily pool per Phase 11.7
  case feeds current strict, expanded strict and expanded structured arms;
  the expanded arms share byte-identical evidence.
- Added a strict claim-and-citation JSON parser, deterministic balanced
  evidence projection and twelve blocking retrieval, schema, answer and
  citation gates across Gemma 4 31B and Gemini 3.5 Flash Lite. The exact
  authorized budget is 24 Tavily and 144 generation requests with no retry,
  fallback or repair.
- Added an offline-by-default GitHub workflow. Live execution requires either
  a manual dispatch with an explicit authorization input when the workflow is
  on the default branch, or an exact same-repository PR label event while the
  workflow exists only on the draft branch. A passing Phase 11.8 result can
  authorize only a separately frozen fresh Phase 11.9 confirmation; product
  defaults, the Phase 12 seal, draft PR, merge, release, external comparison
  and superiority-claim boundaries remain unchanged.
- Recorded the audited Phase 11.8 no-go. Five of twelve gates passed:
  packet identity and the structured citation-presence, identifier-integrity and
  support non-regression gates passed, while retrieval prompt coverage,
  completion, schema validity, answer non-regression and the absolute support
  floor remained blocking.
- The single scored run made exactly 24 Tavily and 144 generation requests with
  zero retry, fallback or repair. Only 112/144 generations completed; 22 HTTP
  503 responses came from Gemma 4 31B, alongside eight wall-timeouts and two
  structured-schema failures.
- Committed the privacy-safe raw report and interpreted provenance for run
  30521453796. Phase 11.9 is not authorized, quality/community defaults are
  unchanged, Phase 12 remains sealed, and merge, release and superiority claims
  remain blocked.
- Added a deterministic, standard-library-only Phase 11.8.1 analyzer that
  recomputes the committed privacy-safe Phase 11.8 result with zero provider or
  model traffic and preserves the historical 5/12 no-go without changing
  product configuration or accessing Phase 12.
- Isolated three answer-proxy losses between expanded selection and prompt
  projection; decomposed the structured schema gate into ten requests that
  never reached native validation and two actual schema rejects; and separated
  hosted-model availability from retrieval and answer-quality diagnostics.
- Added adversarial equal-truncation and structured-contract fixtures, a
  reproducible diagnostic JSON/Markdown report and an offline-only GitHub
  workflow with no secret inputs. The proposed future gate taxonomy is not
  retroactive, Phase 11.9 remains unauthorized and the draft PR remains no-go.
- Locked Phase 11.8.2 as a standard-library-only, synthetic and entirely
  offline projection/response-contract design phase with no provider, model,
  network, secret, product-profile or Phase 12 access.
- Added a deterministic rank-weighted question-window/head/tail evidence
  projector with exact rendered-budget accounting and a minimal closed
  direct-answer JSON contract requiring packet-local citations.
- Recorded a 12/12 authored engineering-gate pass: sentinel retention improved
  from 1/12 for the locked equal-cap baseline to 12/12 with zero paired
  regression, while explicitly preserving the historical 5/12 no-go and
  making no real-case quality, merge, release or superiority claim.
