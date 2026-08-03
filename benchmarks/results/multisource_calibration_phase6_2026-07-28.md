# Phase 6 multi-source calibration result

Date: 2026-07-28  
Workflow run:
[`30402484886`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30402484886)  
EvidenceMesh commit: `f79a7a919528e68096288498acf60c0babc80716`  
Raw report:
[`multisource_calibration_phase6_2026-07-28.json`](multisource_calibration_phase6_2026-07-28.json)  
Raw SHA-256:
`9fe5671b41136165b2e2856c0c2d6bff54020067859dff22021e135f099f96c4`

## Verdict

**Functional gate: fail. Release decision: no-go.**

The candidate returned results for every case and all four source families
contributed, but 8/24 cases had at least one provider failure. The measured
partial-failure rate was 33.3%, above the locked maximum of 25%. All eight
partial cases contained a SearXNG failure; its isolated DuckDuckGo path
succeeded and contributed in only 4/12 routed cases.

The unavailable second independent network is a separate mandatory blocker.
The cross-network gate remains `not_testable` at 1/2 environments. The 200-case
Stage B run was not performed, and no superiority or release-readiness claim is
made.

## Locked overall metrics

| Metric | Result | Gate | Pass |
|---|---:|---:|:---:|
| Availability | 24/24 (100%) | at least 90% | yes |
| Target-domain hit @10 | 22/24 (91.7%) | at least 75% | yes |
| Expected-family hit @10 | 22/24 (91.7%) | at least 80% | yes |
| Partial failures | 8/24 (33.3%) | at most 25% | **no** |
| p95 latency | 2,596 ms | at most 15,000 ms | yes |
| Contributing providers | 5 | at least 4 | yes |
| Contributing source families | 4 | all 4 | yes |

Wilson 95% intervals in the raw report are 86.2–100% for availability and
74.2–97.7% for both target-domain and expected-family hit rates.

## Topic breakdown

| Topic | Availability | Target @10 | Expected family @10 | Partial failures | p95 ms |
|---|---:|---:|---:|---:|---:|
| Web | 6/6 | 4/6 | 4/6 | 2/6 | 792 |
| Reference | 6/6 | 6/6 | 6/6 | 6/6 | 725 |
| Academic | 6/6 | 6/6 | 6/6 | 0/6 | 2,982 |
| Code | 6/6 | 6/6 | 6/6 | 0/6 | 876 |

Reference cases still succeeded through the direct Wikipedia adapter when
SearXNG failed. The two missed web targets (`web-05` and `web-06`) returned
reference-only results after SearXNG failure.

## Provider contribution

| Provider | Requested | Successful response | Contributed |
|---|---:|---:|---:|
| SearXNG / DuckDuckGo | 12 | 4 | 4 |
| Wikipedia | 18 | 18 | 18 |
| Crossref | 6 | 6 | 6 |
| arXiv | 6 | 6 | 6 |
| GitHub repositories | 6 | 6 | 6 |

The direct vertical providers completed every routed case in this single
environment. This is encouraging calibration evidence, not a reliability
guarantee: each topic has only six authored cases, and no second network was
available.

## Reproducibility and privacy

- Python `3.11.15`, EvidenceMesh `0.1.0`, httpx `0.28.1`
- GitHub-hosted `ubuntu-latest`; physical region not exposed
- checksum-pinned suite, SearXNG settings and container digest
- 24 sequential requests, no retry, no content fetching
- fresh cache; every outcome recorded zero cache hits
- arXiv base-query-only routing with three-second pacing
- public outcomes omit query, title, snippet, content, URL and result text

The complete thresholds and upstream traffic constraints were frozen in
[`docs/benchmark-protocol-v4.md`](../../docs/benchmark-protocol-v4.md) before
the workflow made its first live request.
