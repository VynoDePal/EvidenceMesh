# Independent-index assessment v1

Assessment date: **2026-07-29**.

The goal is not merely to add another metasearch endpoint. Phase 11.2 compares
projects that operate or enable a search index independent of dominant
commercial engines, while preserving a free and open-source EvidenceMesh core.

| Candidate | Independence | Practical integration | Constraint | Phase 11.2 decision |
|---|---|---|---|---|
| [Mwmbl](https://github.com/mwmbl/mwmbl) | Own community-crawled centralized index | Public zero-key API; AGPL search engine | Anonymous quota; results marked CC BY-NC-SA 4.0 | Integrate and benchmark as opt-in public candidate |
| [YaCy](https://github.com/yacy/yacy_search_server) | Operator-local or peer-to-peer crawl and index | Stable JSON endpoint; GPL-2.0-or-later; official container | Operator must supply compute, storage and crawl coverage | Integrate as opt-in self-hosted path; contract-test only in this phase |
| [Marginalia](https://github.com/MarginaliaSearch/MarginaliaSearch) | Own text-oriented index | Open source; public API exists | API key and usage terms; materially heavier self-hosting | Do not add to the default candidate set |
| [Common Crawl](https://index.commoncrawl.org/) | Independent public Web corpus | Open data and URL/capture index | CDXJ index is not arbitrary full-text search; ranking/indexing must be built | Treat as a future ingestion source, not a provider |
| [Wiby](https://wiby.me/) | Own small-Web crawl | Existing zero-key JSON adapter | Availability and broad coverage were insufficient in Phase 11.1 | Retain opt-in and use as a fused independent baseline |
| [Stract](https://github.com/StractOrg/stract) | Former independent search stack | Open-source code remains | Project archived and public product discontinued in 2026 | Reject as an active dependency |
| [OpenSERP](https://github.com/karust/openserp) | Scrapes upstream search products | Self-hostable | Does not create index independence | Reject for this objective |

## Recommended architecture

EvidenceMesh uses two complementary layers:

1. **public calibration layer:** Mwmbl measures the practical value of a larger
   independent index with a strict one-request-per-case budget;
2. **operator-controlled layer:** YaCy lets an organization build and own its
   local corpus and ranking surface without a paid API.

Neither provider is added to the default bundles. Users opt in with:

```bash
EVIDENCEMESH_PROVIDERS=mwmbl evidencemesh search "independent web search"
```

or, for a populated local YaCy node:

```bash
docker compose --profile independent-index up -d yacy
EVIDENCEMESH_PROVIDERS=yacy EVIDENCEMESH_YACY_URL=http://127.0.0.1:8090 \
  evidencemesh search "operator controlled index"
```

The software is free, but a self-hosted Web index still consumes storage,
bandwidth and compute. EvidenceMesh therefore does not describe YaCy operation
as zero-cost infrastructure.

## Promotion requirements

Mwmbl can only be considered for a default bundle after:

- Phase 11.2 retrieval gates pass on the frozen suite;
- the result-license boundary is clarified for general downstream use;
- an independent untouched evaluation confirms the calibration result;
- endpoint stability and sustainable traffic terms are documented.

YaCy can only support a broad-coverage claim after a reproducible snapshot or
crawl recipe is published and evaluated. Adapter correctness alone is not
evidence of search quality.

## Phase 11.3 policy note

No persistent, reproducibly populated YaCy index is available for the next
diagnostic. An ephemeral empty node is therefore excluded. Mwmbl also remains
outside named defaults under its current CC BY-NC-SA result boundary,
independently of endpoint health. Phase 11.3 measures network behavior only and
does not revise this dated architecture assessment's Phase 11.2 evidence.
