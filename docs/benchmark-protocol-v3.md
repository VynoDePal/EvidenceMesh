# Benchmark protocol v3

Status: **locked for Phase 5 before execution**

Snapshot date: **2026-07-28**

Protocol v3 responds to the Phase 4 finding that the SearXNG general-search
path returned results for only four of ten actual attempts before the provider
circuit opened. It separates engine selection from SimpleQA so the same
evaluation questions are not used to tune and assess the provider.

## Stage A: low-traffic engine calibration

### Suite

[`benchmarks/data/searxng_calibration_v1.json`](../benchmarks/data/searxng_calibration_v1.json)
contains 12 authored navigational queries spanning software, science, health,
research, law, standards, AI and Africa. Each case names one expected
authoritative domain. The suite:

- is independent of SimpleQA;
- contains no private or licensed benchmark content;
- has byte SHA-256
  `06a5d97980063999768127439f594090007dff7e793ad61567d248e134779dce`;
- is a provider-selection instrument, not a general search-quality leaderboard.

### Candidates and request schedule

The candidates are `brave`, `duckduckgo`, `startpage`, `qwant`, `mojeek`,
`wiby`, `mwmbl` and `yep`. They are available in the checksum-pinned SearXNG
image without API keys. Disabled defaults are explicitly enabled only in the
dedicated calibration configuration.

Every query/engine pair is requested once: 12 × 8 = 96 requests. Execution is
sequential in query-major deterministic rotation, with a 0.25-second pause,
English language, safe search enabled, at most ten results, an EvidenceMesh
12-second deadline and no retry. A private, single-purpose SearXNG container is
used; public shared instances must not be benchmarked.

The request sends only SearXNG's explicit `engines` parameter. It deliberately
omits `categories`: the pinned SearXNG implementation unions category engines
with explicit engines when both parameters are present. Result engine metadata
is recorded and any unexpected engine invalidates isolation for that request.

Provider envelope:

- image:
  `searxng/searxng:2026.7.26-b060c780d@sha256:d0aaeb14880e6e92bde1518fcc7261e995783367d63d95203383607bef9c6516`;
- calibration configuration:
  [`docker/searxng/calibration-settings.yml`](../docker/searxng/calibration-settings.yml);
- configuration byte SHA-256:
  `856ce08d2bf0c3512cb5a40f91aa54fde1860cad827bd8208fc09059c47d1584`;
- secret: generated randomly at job runtime and passed through
  `SEARXNG_SECRET`; never committed;
- SearXNG upstream timeout: 4 seconds, bounded at 8 seconds.

The public report records case IDs, result/domain counts, authoritative-domain
rank, failure type, upstream unresponsiveness and latency. It excludes query
and result text.

### Pre-registered selection gates

An engine is eligible only if every gate passes over all 12 requests:

| Gate | Target |
|---|---:|
| HTTP/JSON response success | at least 90% |
| At least one result | at least 80% |
| Expected authoritative domain in top 10 | at least 50% |
| Reported unresponsive | at most 20% |
| p95 latency | at most 10 seconds |
| Responses isolated to requested engine | 100% |

Eligible engines are ranked by expected-domain hit rate descending,
availability descending, unresponsive rate ascending, p95 ascending, then
engine name. At most three are promoted.

Stage B is allowed only if at least two engines pass every gate. If fewer pass,
the Phase 5 result is a measured blocker: the production configuration remains
unchanged and no new 200-case run is made.

## Stage B: held-out 200-case retrieval

If Stage A opens the gate, only the promoted engines replace the Phase 4
general-web set in `docker/searxng/settings.yml`. The unchanged official
SimpleQA dataset, checksum, 200 row IDs, sample seed and retrieval metrics from
protocol v2 are then rerun. Wikipedia remains a separate provider in the
federated profile.

The release gates remain:

| Gate | Target |
|---|---:|
| Federated availability | at least 90% |
| Partial-query failure rate | below 20% |
| Federated p95 | below 10 seconds |
| Comparable full SearXNG runs | at least two network environments |

Calibration success does not imply Stage B success.

## Stage C: local-model end-to-end pilot

After Stage B, the controlled runner from protocol v2 is exercised with a
checksum-pinned local model and runtime. Phase 5 targets a small reproducibility
pilot, not a competitive model-quality claim.

The public artifact may report completion, evidence, citation, failure,
latency, prompt, runtime and model provenance. It must not report answer
correctness. SimpleQA correctness remains **not graded** until the private
grading bundle is evaluated by the separately pinned official evaluator.

## Claim policy

Permitted:

> On the dated Phase 5 calibration, engine X passed the pre-registered
> reliability gates in the recorded GitHub Actions environment.

Not permitted:

- describing the 12 authored queries as an unbiased web-search leaderboard;
- changing gates after observing results;
- promoting an engine that failed a gate;
- running or reporting a tuned SimpleQA result when the Stage A gate is closed;
- calling ungraded generation “SimpleQA accuracy”;
- claiming EvidenceMesh is the best research system from these stages alone.
