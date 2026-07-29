# Benchmark protocol v11: Phase 11.2 independent-index calibration

Status: **frozen before the first scored Phase 11.2 suite request**.

Freeze date: **2026-07-29**.

Phase 11.2 tests whether a materially larger independent public index improves
the zero-key community retrieval path. It also adds a self-hosted YaCy adapter,
but does not claim that an empty or newly created YaCy index has broad Web
coverage. No paid search API, answer model, Gemini request, extraction or retry
is permitted in this phase.

Before this freeze, one non-suite Mwmbl request for `open source search engine`
was used only to verify the current response schema. It is excluded from every
score and threshold. No frozen suite query was issued before this protocol and
suite hash were committed.

## Architecture decision

The evaluated public candidate is [Mwmbl](https://mwmbl.org/), an open-source,
nonprofit search engine with its own community-crawled index. The current
anonymous API tier documents a limit of 1,000 requests per month and one request
per second. EvidenceMesh therefore makes one Mwmbl request per case and pauses
at least 1.1 seconds between cases.

Mwmbl's terms permit API use, while its returned search results are marked
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
That combination is not sufficiently clear for an unrestricted default in a
general-purpose Apache-2.0 project. EvidenceMesh propagates the result-license
URL in response metadata and keeps Mwmbl opt-in until the operator clarifies
the downstream boundary.

[YaCy](https://yacy.net/) is integrated as the operator-controlled independent
path. It is open-source and exposes `/yacysearch.json`, but its usefulness
depends on the operator's crawl and index. Phase 11.2 therefore verifies the
adapter contract and a checksum-pinned optional Compose service; it does not
include an unpopulated YaCy instance in broad-Web scoring.

## Locked calibration inputs

- suite: `benchmarks/data/independent_index_calibration_v1.json`;
- SHA-256:
  `670454d6c6bdb93a21bc1ea81f28003e08cac9d24c1663aba53fea50d3ac2423`;
- cases: 16;
- strata: 8 `broad_web`, 8 `long_tail`;
- result limit: 10;
- per-domain cap: 3;
- prompt projection: 12,000 characters;
- pause between live case retrievals: at least 1.1 seconds.

The suite is authored calibration data, not an untouched final evaluation.
Phase 12 remains blocked regardless of the Phase 11.2 result.

## Shared live retrieval and offline replay

Each case makes exactly one uncached base-query request through five providers:

1. the pinned private SearXNG deployment;
2. DDGS;
3. Wikipedia;
4. Wiby;
5. Mwmbl.

The immutable raw result pool is then replayed locally through five arms:

| Arm | Pool |
|---|---|
| `legacy_community` | SearXNG, DDGS and Wikipedia |
| `candidate_community` | The complete raw pool |
| `mwmbl_direct` | Mwmbl only |
| `wiby_direct` | Wiby only |
| `independent_fused` | Mwmbl and Wiby |

No arm causes another network request. There is no provider reservation,
provider-specific ranking boost, model reranking or query expansion. The design
compares indexes without tuning EvidenceMesh to make the candidate win.

The maximum scored traffic is fixed at:

- 16 case retrieval operations;
- 80 provider-query calls;
- 16 Mwmbl requests;
- 16 Wiby requests;
- 0 Tavily requests;
- 0 Gemini requests;
- 0 retries.

## Frozen retrieval gates

The retrieval candidate passes only if all conditions hold:

1. candidate prompt evidence is available in at least 15/16 cases and no less
   often than legacy community;
2. candidate target-domain hit@10 is not below legacy community;
3. candidate has at most one paired target-domain loss against legacy;
4. Mwmbl returns at least one result in at least 12/16 cases, including at
   least 7/8 broad-Web cases and 6/8 long-tail cases;
5. a Mwmbl result survives candidate selection in at least 8/16 cases;
6. the Mwmbl direct arm hits a target domain in at least 4/8 broad-Web and 4/8
   long-tail cases;
7. the independent fused arm has prompt evidence in at least 12/16 cases;
8. every case with a raw Mwmbl result carries the fixed result-license notice;
9. traffic exactly matches the provider budget and contains no paid provider,
   model request or retry.

Thresholds cannot change after the first scored request.

## Default and release boundary

Retrieval success and default eligibility are separate decisions.

Even if all retrieval gates pass:

- Mwmbl remains opt-in while the result-license boundary is unresolved;
- YaCy remains opt-in until a reproducible, populated index is measured;
- the community and quality profile defaults do not change;
- Phase 12 is not unlocked by this calibration;
- external research agents remain untested;
- the pull request remains draft;
- merge, release and a “best open-source search” claim remain **no-go**.

The privacy-safe report may include case IDs, strata, aggregate counts,
booleans, fixed provider/license URLs, environment lineage and gate outcomes.
It excludes queries, target domains, result titles, source URLs and snippets.
