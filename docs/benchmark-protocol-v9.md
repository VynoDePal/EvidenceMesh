# Benchmark protocol v9: Phase 11 retrieval lineage and resilience

Status: **frozen before the first Phase 11 Tavily request**.

Freeze date: **2026-07-29**.

This protocol covers Phase 11A and Phase 11B. It diagnoses the Phase 10
retrieval regression, evaluates a temporary Tavily-first quality policy and
tests a more resilient zero-key community route. It makes no Gemini request and
does not reuse the Phase 10 questions.

## Phase 10 defect being tested

Phase 10 produced evidence for only 5/12 community cases. SearXNG was degraded
in every community and quality case, while the one-query Tavily arm retained
substantially more answer-key evidence than the full quality route.

The committed Phase 10 SearXNG file kept only `duckduckgo`, despite the provider
documentation describing a multi-engine route. That protocol/documentation
divergence is a concrete defect. It is a strong causal hypothesis for the
SearXNG collapse, but it is not treated as proven until the new calibration is
run.

Phase 11 addresses two separate risks:

1. fusion and diversity logic can remove useful Tavily results;
2. one SearXNG upstream path is not a reliable community web backend.

## Locked authored suite

The public suite is
[`benchmarks/data/phase11_calibration_v1.json`](../benchmarks/data/phase11_calibration_v1.json).
It contains 12 authored navigational queries covering developer documentation,
protocols, public policy, public data, security and research. Each case has one
or more expected authoritative domains.

- suite SHA-256:
  `23f0a3c1c6d680b0ec6bdd0964a81f28b23e5778f4965632b03ed5dc4e78c5d7`;
- case count: 12;
- maximum result count: 10;
- default domain cap: 3.

This is an inspectable calibration set, not an untouched final evaluation.
Phase 10's 12-case sample is retired from future final scoring. A new hidden,
untouched sample is reserved for Phase 12 only if the Phase 11 gates pass.

## Shared live retrieval

Each case performs one EvidenceMesh quality retrieval with:

- private, checksum-pinned SearXNG;
- DDGS as a bounded one-query best-effort fallback;
- Wikipedia;
- Tavily basic search;
- no cache;
- no retry;
- snippets only;
- no page extraction request;
- no answer model.

Web routing excludes the configured academic and code providers, so each case
has at most four live provider-query calls. Tavily remains capped at one request
per case and 12 requests for the complete run.

The SearXNG configuration is
[`docker/searxng/phase11-community-settings.yml`](../docker/searxng/phase11-community-settings.yml),
SHA-256
`e33610cdd83c89a0fb85e687e632b179ed36057d948db102c7a6e2c33b456efb`.
It keeps the zero-key Brave, DuckDuckGo, Startpage and Wikimedia web/news
engines instead of a single DuckDuckGo engine. Engine names and default
configuration are verifiable in
[SearXNG's official settings](https://github.com/searxng/searxng/blob/master/searx/settings.yml).

## Deterministic replay arms

The provider-native results are captured once per case. The same immutable raw
pool is then replayed locally through six arms:

| Arm | Pool and ranking policy |
|---|---|
| `tavily_direct` | Tavily subset only |
| `community` | Every non-Tavily result |
| `quality_legacy` | Complete pool, no provider reservation |
| `quality_safe_4_6` | Complete pool, reserve 4/10 slots for Tavily |
| `quality_safe_6_4` | Complete pool, reserve 6/10 slots for Tavily |
| `quality_safe_8_2` | Complete pool, reserve 8/10 slots for Tavily |

Reservation never bypasses URL filtering or the per-domain cap. If a provider
does not have enough eligible diverse results, unused reserved slots are filled
from the global ranking. Selected results are finally ordered by the common
score, so reservation changes membership rather than inventing a separate
provider score.

The production `quality` default is temporarily fixed at 80% Tavily for web and
news. Operators can change or disable it with:

```bash
export EVIDENCEMESH_QUALITY_PRIMARY_PROVIDER=tavily
export EVIDENCEMESH_QUALITY_PRIMARY_PROVIDER_SHARE=0.8
```

## Lineage telemetry

For every arm, provider presence is counted at:

1. `raw`;
2. `fused`, after URL validation and canonical deduplication;
3. `eligible`, after include/exclude-domain filters;
4. `selected`, after ranking, reservation and diversity;
5. `evidence`, after removing empty snippets;
6. `prompt`, after the deterministic 12,000-character projection.

Loss counts are emitted for every adjacent transition. Search metadata also
records reservation demand and fulfillment, contributing SearXNG engines,
unresponsive engines, provider failures and provider-query counts.

No prompt is sent to a model. The prompt stage is a size-bounded projection used
only to detect whether provider evidence would survive to a caller.

## Frozen gates

The Phase 11 candidate passes only if all of these conditions hold:

1. community prompt evidence is available in at least 11/12 cases (at least
   90%);
2. `quality_safe_8_2` target-domain hit@10 is not below `quality_legacy`;
3. `quality_safe_8_2` has at most one paired target-domain loss against
   `tavily_direct`;
4. at least nine cases have eight eligible Tavily results and every such case
   fulfills its 8/10 reservation;
5. Tavily traffic is at most 12 requests.

Thresholds are not changed after seeing the live result. Target-domain hit is a
navigational diagnostic, not factual accuracy or source correctness.

## Report and claim boundary

The report includes case IDs, counts, booleans, provider lineage, engine
telemetry, traffic and environment provenance. It excludes queries, target
domains, source titles, URLs, snippets and credentials.

Regardless of outcome:

- Gemini requests remain zero;
- external research agents remain untested;
- Phase 12 remains the first eligible untouched end-to-end evaluation;
- merge, release and any “best open-source search” claim remain **no-go**.
