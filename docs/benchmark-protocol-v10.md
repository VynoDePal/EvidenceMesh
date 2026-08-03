# Benchmark protocol v10: Phase 11.1 feasibility and independent index

Status: **frozen before the first Phase 11.1 benchmark-suite request**.

Freeze date: **2026-07-29**.

Phase 11.1 is a corrective retrieval calibration. It does not alter the
published Phase 11 report or turn its failed reservation gate into a pass.
It tests a more precise quota contract and adds one genuinely independent,
zero-key web index to the community route. It makes no model request.

Before this freeze, one non-suite `q=test` request was used only to verify the
public Wiby response schema documented by its API page. It was not scored, did
not use a calibration query, did not inform a threshold and made no Tavily
request.

## Defects under test

Phase 11 exposed two independent limitations:

1. the 8/2 policy requested eight Tavily results even when the domain-diversity
   cap made eight distinct eligible selections impossible;
2. DDGS and the working SearXNG upstream both depended on DuckDuckGo, so
   community availability did not prove independent-index redundancy.

The corrected reservation telemetry keeps five separate values:

- `requested`: the configured provider share;
- `eligible`: fused provider results remaining after URL/domain filters;
- `feasible`: the maximum selectable provider results under the domain cap;
- `target`: `min(requested, feasible)`;
- `fulfilled`: provider results actually reserved.

The shortfall reason distinguishes insufficient eligible results, the diversity
cap, or both. The target is not allowed to silently collapse: the gates below
retain an aggregate-strength floor.

## Independent-provider selection

The selected provider is [Wiby](https://wiby.me/). Its
[official JSON endpoint](https://wiby.me/json/) requires no key and requires a
link back to Wiby with results. Its
[installation guide](https://wiby.me/about/guide.html) describes an
independently crawled, GPLv2 search engine that can be self-hosted.

EvidenceMesh therefore:

- routes only the base web query to Wiby;
- never requests Wiby's optional unfiltered result mode;
- emits `https://wiby.me/` in provider attribution metadata whenever Wiby
  returns results;
- treats the public endpoint as a bounded best-effort dependency, not as an
  unlimited service;
- exposes `EVIDENCEMESH_WIBY_URL` for a compatible operator-controlled
  deployment.

Wiby is intentionally small and is not expected to replace a broad commercial
index. Marginalia was not selected because its current API requires a key and
its shared public key is constrained by noncommercial terms. YaCy remains a
future operator-controlled option: it is independent and open source, but a
reproducible useful index requires materially heavier deployment and no
protocol-approved public endpoint was available.

## Locked calibration inputs

The Phase 11 authored diagnostic suite is intentionally reused:

- path: `benchmarks/data/phase11_calibration_v1.json`;
- SHA-256:
  `23f0a3c1c6d680b0ec6bdd0964a81f28b23e5778f4965632b03ed5dc4e78c5d7`;
- cases: 12;
- result limit: 10;
- per-domain cap: 3;
- prompt projection: 12,000 characters.

Reuse is disclosed because this is corrective calibration, not untouched final
evaluation. Phase 12 remains the next eligible untouched end-to-end sample only
if every Phase 11.1 gate passes.

The private SearXNG configuration is unchanged from Phase 11:

- path: `docker/searxng/phase11-community-settings.yml`;
- SHA-256:
  `e33610cdd83c89a0fb85e687e632b179ed36057d948db102c7a6e2c33b456efb`.

## Shared live retrieval and replay arms

Each case makes one uncached quality retrieval through SearXNG, DDGS, Wiby,
Wikipedia and Tavily. There is no retry, extraction or answer model. Each case
therefore has exactly five routed provider calls, with at most one Tavily call
and one Wiby call.

The immutable raw pool is replayed locally through seven arms:

| Arm | Pool and policy |
|---|---|
| `tavily_direct` | Tavily only |
| `wiby_direct` | Wiby only |
| `community` | Every non-Tavily provider, including Wiby |
| `quality_legacy` | Complete pool without reservation |
| `quality_safe_4_6` | Complete pool; request 4/10 Tavily |
| `quality_safe_6_4` | Complete pool; request 6/10 Tavily |
| `quality_safe_8_2` | Complete pool; request 8/10 Tavily |

Provider calls are never replayed. Reservation never bypasses URL validation,
canonical deduplication or domain diversity.

## Frozen gates

The Phase 11.1 candidate passes only if every condition holds:

1. community prompt evidence is available in at least 11/12 cases;
2. 8/2 target-domain hit@10 is not below legacy quality;
3. 8/2 has at most one paired target-domain loss against Tavily direct;
4. every 8/2 case fulfills its domain-aware target, all 12 targets are at least
   six, and their total is at least 90/96 requested slots;
5. Wiby returns at least one raw result in at least 6/12 cases;
6. a Wiby result survives community selection in at least 3/12 cases;
7. every case containing raw Wiby results carries the required attribution;
8. Tavily and Wiby each receive at most 12 requests.

Thresholds cannot be changed after the live run.

## Claim and release boundary

The privacy-safe report excludes queries, target domains, result titles, source
URLs and snippets. The fixed provider attribution URL is retained. It records
traffic, environment, lineage, feasibility and gate outcomes.

Even if every gate passes:

- the run measures retrieval, not factual answer quality;
- external research agents remain untested;
- a second independent network remains unavailable;
- the pull request stays draft;
- merge, release and any “best open-source search” claim remain **no-go**.
