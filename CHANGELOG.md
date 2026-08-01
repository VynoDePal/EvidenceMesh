# Changelog

All notable changes to EvidenceMesh are documented here.

## 0.1.0 - 2026-07-28

- Accepted exact tag `v0.1.0-alpha.local` as a single-host, offline technical
  alpha after clean-export tests, strict typing and lint, reproducible wheel
  and source builds, and installed CLI/MCP smokes. All distributions remain
  unpublished.
- Isolated the local-alpha decision from BrowseComp-Plus and BRIGHT. Upstream
  silence cannot invalidate the local alpha, while external admission, Phase
  11.9, Phase 12, V1 readiness, merge and release remain blocked.
- Added a draft-PR public projection of the local acceptance, based on exact
  Git-tree equivalence. The local tag, build distributions and release remain
  unpublished, and the retired one-update RC4.1A workflow is preserved as a
  byte-identical historical archive.
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
- Locked Phase 11.8.3 as an offline-by-default 2x2 causal calibration on
  the already-observed 24 Phase 11.7 cases. One shared Tavily packet crosses
  the locked equal-cap and candidate projections with the claims and direct-
  answer JSON contracts; Gemini 3.5 Flash Lite is the sole blocking model.
- Frozen the future live ceiling at exactly 24 Tavily requests and 96 Gemini
  generations with zero retry, fallback or repair, plus fourteen blocking
  traffic, identity, completion, schema, answer and citation gates.
- Added a no-secret lock-validation path and a separately authorized live
  job. This protocol commit makes no provider/model call, adds no live label,
  preserves both product profiles and the Phase 12 seal, and leaves the draft
  PR, merge, release, external comparison and superiority claims blocked.

- Executed the single authorized Phase 11.8.3 live calibration on the frozen
  24-case factorial suite. The run made exactly 24 Tavily requests and 96
  Gemini 3.5 Flash Lite generation requests with zero retry, fallback or repair.
- Recorded a 10/14 candidate no-go. Shared-packet, deterministic-budget and
  conditioned answer/citation gates passed, but candidate prompt coverage tied
  equal-cap at 17/24, all four arms missed the 23/24 completion floor, the
  direct contract accepted only 5/36 native responses, and the joint candidate
  had an all-attempt paired answer net of -7 against control.
- Audited 22 HTTP 429 responses and 31 direct-response schema failures. The
  privacy-safe report contains no questions, answers, prompts, evidence,
  credentials or Phase 12 reserved identifiers; no opportunistic rerun was made.
- Committed the raw report and interpreted provenance for run 30555171945 and
  artifact 8764644024. Phase 11.9 may not be frozen, product defaults remain
  unchanged, Phase 12 stays sealed, and merge, release and superiority claims
  remain blocked.
- Added the zero-network Phase 11.8.4 quota governor with explicit per-model
  RPM, input-TPM and RPD budgets, a 20% safety margin, rolling-window auditing,
  conservative tokenizer-free estimates and fail-before-request daily or
  oversized-request guards.
- Added privacy-safe Gemini 429 classification for RPM, TPM, RPD, spend and
  unknown dimensions. Scored runs abort unscored on the first 429 without a
  selective retry; bounded positive-jitter backoff remains available only for
  ordinary non-benchmark integrations.
- Replaced unsupported provider-facing JSON Schema keywords with Gemini's
  documented structured-output subset while preserving the strict local
  direct-answer parser for citation syntax, uniqueness, packet membership and
  insufficient-evidence semantics.
- Recorded a reproducible 15/15 offline engineering pass with zero Gemini,
  Tavily, provider or network calls. Phase 11.8.3 remains failed at 10/14, its
  projection defect is unchanged, no live smoke test is authorized, Phase 12
  remains sealed and release remains no-go.
- Locked Phase 11.8.5 as a four-fixture, two-repetition Gemini-only live
  micro-smoke for `gemini-3.5-flash-lite`. Its maximum traffic is eight
  sequential generation requests after a 60-second cold start, with zero
  Tavily, token-count, retry, fallback or repair calls.
- Added exact schema, quota, traffic, privacy and fixture-conformance gates,
  immediate stop on HTTP 429, non-success or transport failure, and a
  same-repository authorization-label boundary. The protocol commit does not
  itself execute the live smoke.
- Kept the historical Phase 11.8.3 result failed at 10/14. Even a passing
  Phase 11.8.5 smoke can validate only quota and response-contract mechanics;
  Phase 11.9, Phase 12, product changes, merge, release and superiority claims
  remain blocked.
- Recorded the single authorized Phase 11.8.5 live no-go at 8/12 gates. The
  first two Gemini requests returned native HTTP 200 outputs that passed the
  strict schema and synthetic semantics; the third reached the locked
  30-second request timeout, and the runner stopped before five later
  attempts.
- The run made three Gemini requests, zero Tavily or other-provider requests,
  and zero retries, fallbacks or repairs. It observed no HTTP 429, stayed
  within every quota-safety limit and preserved a privacy-safe one-file
  artifact. No opportunistic rerun was made; Phase 11.9 and release remain
  blocked.
- Added the entirely offline Phase 11.8.6 timeout diagnostic with distinct
  HTTPX connect, read, write and pool categories, an independent benchmark-wall
  category, fail-closed timeout-policy validation and privacy-bounded public
  telemetry.
- Recorded a reproducible 12/12 offline engineering pass with zero network,
  provider, model, secret, retry, fallback or repair activity. The historical
  Phase 11.8.5 timeout remains `legacy_request_timeout_unresolved`: its timing
  is compatible with the 30-second read deadline but does not prove a
  `ReadTimeout`.
- Separated test-model availability from product-release governance without
  weakening either gate. Phase 11.8.5 remains failed at 8/12, broader quality
  evidence keeps release no-go, and no rerun, Phase 11.9, Phase 12, merge or
  superiority claim is authorized.
- Applied the Phase 11.8.6 timeout taxonomy to the SDK and MCP runtime. Owned
  HTTPX clients now use explicit 5-second connect, 12-second read, 10-second
  write and 5-second pool deadlines under the existing 15-second provider wall
  deadline.
- Added fail-closed layered-timeout validation and environment overrides while
  preserving caller-supplied HTTPX timeout settings. Runtime telemetry now
  distinguishes connect, read, write, pool, generic HTTPX and provider-wall
  timeout kinds without retaining private request or exception data.
- Recorded a reproducible Phase 11.8.7 12/12 offline engineering pass with zero
  network, provider, model, secret, retry, fallback or repair activity.
  Historical results and product defaults remain unchanged; future live work,
  Phase 11.9, Phase 12, merge, release and superiority claims remain blocked.
- Locked Phase 11.8.8 as a zero-traffic projection-recovery phase with the
  answer-blind, source-preserving `fair_prefix_rarity_passage_pack_v2`
  projector, adversarial fixtures, a check-only-by-default future calibration
  runner and a read-only workflow containing no secret or live job.
- Recorded a reproducible 14/14 offline engineering pass. On twelve
  post-observation synthetic fixtures, equal-cap retained 3/12 authored
  markers, v1 retained 7/12 and v2 retained 12/12 with exact v2 budgets,
  source/metadata preservation and five deterministic replays in every case.
  These authored scores do not prove real-case quality.
- Separated the retrieval ceiling from projection retention: Phase 11.8.3
  remains failed at 10/14 with 19/24 selected-evidence proxy coverage and
  17/24 for both historical projectors. Any future Tavily-only calibration
  requires a new explicit authorization, while Phase 11.9, Phase 12, product
  changes, merge, release and superiority claims remain blocked.
- Recorded the single authorized Phase 11.8.8 live no-go at 8/13 gates after
  24/24 Tavily HTTP 200 responses and no model, retry, fallback, repair, cache
  or follow-up fetch. Selected/equal-cap/v1/v2 proxy coverage was
  18/16/17/17; v2 retained 17/18 (94.4444%) with paired net gains of +1
  versus equal-cap and 0 versus v1, so all five quality gates failed.
- Audited GitHub Actions run 30581595206 and artifact 8774869598,
  `phase11-8-8-live-projection-calibration-30581595206`: the 4,806-byte ZIP
  SHA-256 is `399cbd5c4bc4d26dde687ec2523ce9fa6e1f5d942f465e60653edc0676125d02`
  and the 13,984-byte raw JSON SHA-256 is
  `03e0ad7ef2d4859848c3b4d4d8bf9d25714b9d311741f15a91ec9b3311aca25f`.
- Provenance binds lock commit `d91f8a85f6e2770ecd83ca95cbc7112803d683cb`,
  authorization commit `c1f847be04bdf5574ad80885f7e00f1fdbb0f049`,
  protocol `e63ab4b3f25865890458abd2a001ce3428f9a3ca8c4f1a1a166f25432d1a8dc9`,
  runner `fabad5e66246a10f0f024201c1d031de22e4958141b57cf731393bd6cc936ac3`
  and dependency manifest
  `0d6ee7f91689fc2679ee0e5c6a2857d25219d5a71cd559d248875d1074693a00`.
  Phase 11.9, Phase 12, promotion, merge, release and superiority claims remain
  blocked; no rerun is authorized.
- Locked Phase 11.8.9 as a zero-traffic, answer-blind retrieval-recovery
  protocol with one transparent control, one v3 candidate, five-stage lineage,
  exact-byte source execution, adversarial conformance fixtures and a
  fail-closed external benchmark adapter.
- Recorded a reproducible 12/19 engineering-conformance-only result. All
  twelve local gates passed, including a 53/53 Gate 9 receipt over 43
  registered requirements, with zero network, provider, model, secret, retry,
  fallback, repair or live-cache activity.
- BRIGHT and BrowseComp-Plus remain `not_evaluated` because their complete
  authoritative assets and asset-level license locks are unresolved. No
  official external score is reported; Phase 11.9, Phase 12, product changes,
  merge, release and superiority claims remain blocked.
- Locked Phase 11.8.10A as metadata-only external-asset reconnaissance for
  BRIGHT and BrowseComp-Plus: exact immutable revisions, roles, 37 Git LFS
  content objects, byte lengths, SHA-256 digests and capacity bounds.
- Recorded a reproducible 15/15 engineering-gate pass with zero asset
  downloads or opens, query decryptions, scores, provider, search, model or
  secret calls. The inventory represents 5,013,088,007 transfer bytes and
  7,205,462,832 upstream-declared decoded bytes.
- Upstream license declarations are pinned, but component-level third-party
  rights and BRIGHT leaderboard comparability remain unresolved. Raw asset
  redistribution and evaluation stay blocked; Phase 11.8.10B, Phase 11.9,
  Phase 12, product changes, merge, release and superiority claims remain
  unauthorized.
- Locked Phase 11.8.10B-P0 as a public-metadata-only policy and comparability
  decision for BRIGHT and BrowseComp-Plus, bounded to ten of fifteen permitted
  primary documents and zero benchmark payload access.
- Preserved an official-comparability target and the option to use one
  individually admitted authoritative suite later, while admitting neither
  suite now: component-level third-party rights remain unverified, BRIGHT has
  no exact leaderboard/evaluator binding, and BrowseComp-Plus has no pinned
  judge, tokenizer or complete inference configuration.
- Recorded the fail-closed acquisition decision with zero downloads, opens,
  decryptions, scores, provider, model, external-tester, secret or publication
  calls. Phase 11.8.10B acquisition, Phase 11.9, Phase 12, merge, release and
  superiority claims require a separate authorization and remain blocked.
- Locked Phase 11.8.10B-P1 as a five-source, public-metadata-only BrowseComp-
  Plus clarification, exhausting the cumulative fifteen-of-fifteen primary-
  document budget without acquiring or opening any benchmark payload.
- Recorded a fail-closed `BLOCK`: component-level corpus rights remain
  unverified and the judge, tokenizer, prompt, generation, runtime and scoring
  identity remain insufficiently pinned for official comparability.
- Recorded bounded process attestations of zero payload download, query
  decryption, provider, model, judge, scoring, live-evaluation, secret or
  publication activity; no full runtime network instrumentation is claimed.
  Phase 11.8.10B acquisition, Phase 11.9, Phase 12, merge, release and
  superiority claims remain blocked.
