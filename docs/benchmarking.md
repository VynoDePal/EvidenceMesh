# Benchmark methodology

## Two separate questions

EvidenceMesh intentionally separates:

1. **Algorithm regression:** Does fusion, deduplication and diversity behave
   deterministically on known result lists?
2. **Live retrieval quality:** Does a dated provider configuration retrieve
   evidence containing the expected answer on real questions?

The offline suite cannot prove superiority over a live search product. The live
suite cannot be bit-for-bit deterministic because the web changes.

Provider observability is a third, non-scored question: did routing reach the
adapter and shared HTTP transport, or was the call served from cache, blocked
by the circuit, or lost before dispatch? The locked
[Phase 11.3 protocol](benchmark-protocol-v12.md) adds this accounting to core
search metadata and runs four privacy-safe Mwmbl diagnostics. It computes no
retrieval or answer-quality metric and cannot unlock a later evaluation.
The [published result](../benchmarks/results/phase11_3_network_diagnostic_2026-07-29.md)
recorded four real HTTP attempts: three HTTP 200 responses with results and one
sanitized timeout without a response.

A one-question [zero-key smoke run](../benchmarks/results/live_smoke_2026-07-28.md)
is committed only as an interface/connectivity check; it is not included in any
quality claim. The historical [benchmark protocol v1](benchmark-protocol-v1.md)
defines the Phase 2/3 DDGS runs. The locked
[benchmark protocol v2](benchmark-protocol-v2.md) defines the Phase 4
self-hosted SearXNG run and controlled answer-generation track. The locked
[benchmark protocol v3](benchmark-protocol-v3.md) defines the Phase 5
engine-calibration gate before any further SimpleQA run.

The first
[30-row SimpleQA retrieval pilot](../benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.md)
is a critical baseline. It demonstrated provider failure isolation but did not
meet the proposed reliability or latency gates and does not support a
superiority claim.

The
[200-row Phase 3 reliability run](../benchmarks/results/simpleqa_retrieval_phase3_2026-07-28.md)
then exercised the provider circuit breaker. It reduced sustained federated p95
latency to 888 ms by skipping 195 repeated DDGS attempts, while availability
remained 70.5%. The raw report preserves both logical failures and actual
network-attempt accounting.

The
[200-row Phase 4 SearXNG run](../benchmarks/results/simpleqa_retrieval_phase4_2026-07-28.md)
used the unchanged sample on a GitHub-hosted runner. SearXNG completed four of
ten actual attempts before its circuit opened; 190 later calls were skipped.
Federated availability was 71.5%, partial-query failure was 98.0%, and the
release decision remained no-go.

Phase 5 does not choose SearXNG engines on those SimpleQA questions. Its
independent 12-query navigational suite issues one request to each of eight
keyless engines, with no retry and pre-registered response, availability,
authoritative-domain, unresponsive and latency gates. A new 200-case run is
blocked unless at least two engines pass all gates.

The
[valid Phase 5 calibration](../benchmarks/results/searxng_calibration_phase5_2026-07-28.md)
completed all 96 requests with full requested-engine isolation. DuckDuckGo was
the only eligible engine: availability was 100%, target-domain hit@10 was
91.7%, unresponsiveness was 0% and p95 was 996.469 ms. Wiby was the next
closest but missed both availability (75%) and target-domain hit@10 (8.3%).
The remaining six engines failed at least three gates. The minimum-two-engine
gate therefore closed, leaving the production configuration unchanged and
blocking both the held-out 200-case run and local-model pilot.

## Offline federation benchmark

`src/evidencemesh/data/federation_v1.json` is a packaged fixture containing
provider result lists and explicit relevant URLs. The runner reports:

- Hit@1
- Hit@5
- mean reciprocal rank at 10
- nDCG@10
- duplicate rate
- unique-domain ratio

It compares EvidenceMesh fusion with the first listed single-provider baseline.
The fixture is synthetic and is only a regression gate.

## Live retrieval benchmark

`benchmarks/run_live_retrieval.py` can download the checksum-pinned official
SimpleQA dataset or accept local JSONL objects:

```json
{"id":"q1","question":"...","answer":"...","gold_urls":["https://example.org/source"]}
```

It interleaves named provider profiles on the same sample. It measures curated
source URL/domain recall, lexical answer coverage in titles/snippets,
availability, provider failures, diversity and latency. This is retrieval
measurement, not end-to-end QA accuracy.

The runner uses the same provider admission path as the SDK. Reports distinguish
logical provider calls, actual network attempts, attempt failures and
circuit-open skips. Every compared profile is still ranked from the same shared
snapshot for a given provider/question pair.

Every published result must include:

- EvidenceMesh commit SHA and configuration;
- provider endpoints and enabled providers;
- dataset name, byte-level SHA-256, sample IDs, manifest SHA-256 and sampling
  seed;
- UTC start/end time;
- machine and network region;
- cache state;
- hit metrics with 95% Wilson intervals, latency percentiles and failure rates;
- raw machine-readable output.

The current default zero-key retrieval profile is:

```bash
uv run python benchmarks/run_live_retrieval.py \
  --simpleqa \
  --sample-size 30 \
  --seed 0 \
  --profile federated=searxng,wikipedia \
  --profile searxng=searxng \
  --profile wikipedia=wikipedia \
  --provider-config searxng=docker/searxng/settings.yml \
  --provider-image \
    searxng=searxng/searxng:2026.7.26-b060c780d@sha256:d0aaeb14880e6e92bde1518fcc7261e995783367d63d95203383607bef9c6516 \
  --max-results 10 \
  --concurrency 1 \
  --request-timeout 15 \
  --progress \
  --output benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.json
```

The dedicated Phase 4 workflow ran the same profile over 200 rows on a
GitHub-hosted runner, verified the image digest and uploaded the
[raw report](../benchmarks/results/simpleqa_retrieval_phase4_2026-07-28.json).

For the Phase 3 reliability run:

```bash
uv run python benchmarks/run_live_retrieval.py \
  --simpleqa \
  --sample-size 200 \
  --seed 0 \
  --max-results 10 \
  --concurrency 3 \
  --request-timeout 15 \
  --provider-failure-threshold 3 \
  --provider-recovery-seconds 60 \
  --progress \
  --output benchmarks/results/simpleqa_retrieval_phase3_2026-07-28.json
```

## Multi-source calibration

`benchmarks/run_multisource_calibration.py` exercises the zero-key community
route across web, reference, academic and code sources. Its 24 authored queries
are separate from SimpleQA, and its public outcome rows omit query and result
content. The runner enforces the suite/config hashes, traffic budget, no-retry
policy and pre-registered gates in
[benchmark protocol v4](benchmark-protocol-v4.md).

The two-independent-network gate is intentionally separate from the functional
metrics. A one-network pass cannot authorize the 200-case stage or a release
claim. The committed
[Phase 6 result](../benchmarks/results/multisource_calibration_phase6_2026-07-28.md)
failed the functional gate on partial failures, so no Stage B run was made.

## Quality-profile calibration

`benchmarks/run_quality_calibration.py` evaluates the Tavily-backed `quality`
candidate on a new 32-case suite with no exact query overlap with Phase 6.
Reference, academic and code cases use exact expected URL prefixes; web cases
use official target domains. The runner reports raw provider degradation
separately from required-family satisfaction and enforces overall, per-topic
and Tavily-specific gates. Tavily is limited to eight basic calls and eight
credits for the entire run. Inputs and thresholds are frozen in
[benchmark protocol v5](benchmark-protocol-v5.md).

The unavailable second independent network remains a hard release boundary.
Consequently, even a functional pass cannot authorize Stage B, merge,
publication or a superiority claim.

The committed
[Phase 7 result](../benchmarks/results/quality_calibration_phase7_2026-07-29.md)
failed the functional gate. Tavily passed its 8/8 requested, successful and
contributing checks, and web retrieved 8/8 official domains. Overall exact
target hit was only 18/32: academic retrieved 2/8 exact paper URLs and code
retrieved 0/8 exact repositories. The locked runner also exposed that its
default three-results-per-domain diversity cap makes single-domain verticals
effectively `@3` despite the `@10` metric name. The frozen result is preserved;
any correction requires a new protocol and untouched suite.

## Profile-aware quality calibration

`benchmarks/run_quality_calibration_v2.py` implements the locked Phase 8
follow-up on `quality_calibration_v3.json`. It keeps the provider bundle,
thresholds, Tavily eight-credit ceiling and single-network release block
unchanged. It changes only pre-registered candidate behavior and measurement:

- web/news retain three results per domain, while reference, academic and code
  can use all ten result slots;
- GitHub repository intent is normalized to name/description search;
- authored targets use canonical domain, Wikipedia, arXiv and GitHub
  identities rather than URL prefixes;
- an in-memory provider wrapper records raw target ranks without issuing extra
  calls, so upstream misses can be separated from ranking losses.

Inputs, privacy rules and traffic limits are frozen in
[benchmark protocol v6](benchmark-protocol-v6.md). A result from the one
available GitHub-hosted environment cannot authorize Stage B or release.

The committed
[Phase 8 result](../benchmarks/results/quality_calibration_phase8_2026-07-29.md)
passed all overall thresholds at 26/32 target hits, but failed the code-specific
target gate at 4/8 versus the required 6/8. Raw-rank telemetry attributed five
of six total misses to upstream retrieval and one web miss to final ranking.
The functional, Stage B and release decisions therefore remain no-go.

## Paired GitHub repository recall

`benchmarks/run_github_recall_paired.py` implements the locked Phase 9
repository-only comparison. It interleaves the frozen `legacy-v1` normalizer
and the production `entity-anchor-v2` planner over the same 24 new targets.
Each arm makes exactly one anonymous GitHub repository-search request per case;
requests are sequential, cache and retries are disabled, and no Tavily credit
or new secret is used.

The candidate must find at least 20/24 raw targets and retain at least 18/24 in
the final top ten. It must gain at least four paired targets with no regression
against the baseline. The complete traffic, privacy and decision contract is
frozen in [benchmark protocol v7](benchmark-protocol-v7.md).

The committed
[Phase 9 result](../benchmarks/results/github_recall_phase9_2026-07-29.md)
passed every functional condition. The candidate found 24/24 targets at ten
against 4/24 for the baseline, with 20 paired gains, no regression and no
additional queries. This validates the repository-query correction on the
locked suite only. The cross-network gate remains `not_testable` at 1/2, so
Stage B and release remain blocked.

## End-to-end generation

`benchmarks/run_end_to_end.py` now fixes the evidence-to-answer prompt and
records model, budget, latency, usage and citation telemetry. Its public report
contains hashes rather than benchmark text; an optional gitignored bundle
carries the text for separate official grading. See the
[end-to-end guide](end-to-end-benchmark.md).

The runner intentionally produces no correctness score. That prevents local
string matching from being presented as official SimpleQA accuracy.

Phase 10 adds the locked `benchmarks/run_end_to_end_phase10.py` pilot without
changing that generic runner. It samples 12 SimpleQA cases not used in Phase 3,
retrieves each `tavily_direct`, `community` and `quality` packet once, and
reuses it across `gemma-4-31b-it`, `gemma-4-26b-a4b-it` and
`gemini-3.5-flash-lite`. The fourth arm is `closed_book`.

The run contains 36 retrieval case-arm operations, 144 generation calls, no
retries and at most 24 Tavily basic requests. Its deterministic
`answer_key_covered`, evidence-coverage and citation-support values are named
and documented as substring proxies, not official accuracy or semantic
judgments. The sample, API payload, ordering, budgets and functional thresholds
are frozen in [benchmark protocol v8](benchmark-protocol-v8.md).

The assistant's separate, pre-reference web-search diagnostic recognized 8/12
under the same strict proxy, including known false negatives from harmless
formatting differences. That diagnostic is not a benchmark arm because its
search backend and budget are not reproducible from this repository.

The
[Phase 10 result](../benchmarks/results/end_to_end_phase10_2026-07-29.md)
completed all 36 retrieval operations and 144 model requests without retries.
Tavily direct retained answer-key evidence in 10/12 packets and produced 27/36
answer-key-covered outputs. Quality retained it in 5/12 packets and produced
13/36; community reached 1/12 and 6/36. Quality improved over community by a
paired net +7 but lost to Tavily direct by -14. SearXNG degraded in every
community and quality case, and quality citation presence reached only 14/34.
The frozen functional gate therefore failed and release remains no-go.

## Phase 11.5 quality recovery

`benchmarks/run_phase11_5_quality_recovery.py` reuses the already-observed
Phase 10 cases as a disclosed corrective calibration. It collects one raw
provider pool per case and replays Tavily direct, current 8/2 quality and a
candidate arm across the same three models. Community results are also
reported in a retrieval-only, non-blocking observability arm.

The candidate keeps the current selected 8/2 evidence but prevents sequential
prompt starvation by applying an equal 900-character cap to every selected
block. It also requires an exact returned citation immediately after every
factual statement and uses the SDK's deterministic citation-ID audit. The
protocol fixes 12 Tavily calls, 108 model calls, no retries or citation repair,
and all decision gates in
[benchmark protocol v13](benchmark-protocol-v13.md).

A pass can only unblock a separately authorized untouched Phase 12 run. It
cannot authorize merge, public distribution, an external-agent comparison or
a superiority claim.

The
[audited Phase 11.5 result](../benchmarks/results/phase11_5_quality_recovery_2026-07-29.md)
made exactly 12 Tavily and 108 model requests with no retry or repair. Six of
eight gates passed. The candidate recovered citation presence to 32/34
(94.1%), exact citation-ID integrity to 32/32 and support proxy to 26/34
(76.5%). It did not recover answer quality: candidate and current 8/2 each
produced 25/36 answer-key hits versus 28/36 for Tavily direct, a paired
candidate net of `-3`. Gemma 26B also missed the 11/12 completion floor on all
three arms. The candidate failed, Phase 12 remains blocked and release remains
no-go.

## Phase 11.6 Tavily citation isolation

`benchmarks/run_phase11_6_tavily_citation_isolation.py` removes retrieval
composition as a variable. It retrieves Tavily once for each already-observed
Phase 10 case, then sends the exact same selected and projected packet to a
legacy prompt and the strict Phase 11.5 citation contract.

The [frozen protocol](benchmark-protocol-v14.md) fixes all 12 retrieval
operations, 12 Tavily requests and 72 generations across
`gemma-4-31b-it`, blocking `gemma-4-26b-a4b-it` and
`gemini-3.5-flash-lite`. There are no retries, fallbacks or repair calls. Ten
pre-registered gates cover accounting, packet identity, retrieval coverage,
per-model completion, answer non-regression and citation quality.

A pass may promote the paid `quality` profile to Tavily only in a separate
result commit and may unblock a separately authorized untouched Phase 12 run.
It does not execute Phase 12. The zero-key `community` profile remains
unchanged regardless of the result.

The
[audited Phase 11.6 result](../benchmarks/results/phase11_6_tavily_citation_isolation_2026-07-29.md)
made exactly 12 Tavily and 72 model requests without retry or repair. Selected
and projected packets matched in 12/12 pairs. Strict and legacy answer-key
hits tied at 25/36 for the aggregate and did not regress for any model. The
strict contract reached 34/34 citation presence, 34/34 valid identifiers and
28/34 support proxy.

Nine of ten gates passed. Gemma 26B completed only 10/12 requests in each arm,
below its blocking 11/12 floor. The candidate therefore failed: the paid
quality profile remains mixed, the free community profile is unchanged and
Phase 12 remains blocked.

## Planned standard evaluations

- SimpleQA answer accuracy with the official judge over the new generation
  bundle.
- BrowseComp for hard, multi-hop browsing with a fixed client model.
- DeepResearch Bench FACT/RACE for citation and report quality.

End-to-end comparisons must use the same client model, prompt, time budget and
maximum tool calls. Results obtained with paid providers are reported separately
from the zero-key profile.
