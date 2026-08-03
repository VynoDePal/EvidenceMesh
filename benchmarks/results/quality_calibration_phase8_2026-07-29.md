# Phase 8 profile-aware quality calibration result

Date: 2026-07-29

Workflow run:
[`30441579572`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30441579572)

EvidenceMesh commit: `0b029f3df4b85ffe83b64406f0f88b50eff634e4`

Raw report:
[`quality_calibration_phase8_2026-07-29.json`](quality_calibration_phase8_2026-07-29.json)

Raw SHA-256:
`d13598c873e0e7092542bf2f078132efa38fb42b3c67bac60ffe67d113ab563f`

## Verdict

**Functional gate: fail. Release decision: no-go.**

The candidate passed every overall threshold: 32/32 availability, 26/32
canonical targets, 32/32 expected-family coverage, 12.5% provider degradation,
no unsatisfied required family and a 2,517 ms p95. It also passed every Tavily
condition and the web, reference and academic per-topic gates.

The code target gate failed. GitHub repository search retrieved 4/8 authored
targets, below the locked minimum of 6/8. Stage B was therefore not run.

The unavailable second independent network is a separate mandatory blocker.
The cross-network gate remains `not_testable` at 1/2 environments. No
production-readiness, release-readiness or superiority claim is made.

## Locked overall metrics

| Metric | Result | Gate | Pass |
|---|---:|---:|:---:|
| Availability | 32/32 (100%) | at least 90% | yes |
| Target hit @10 | 26/32 (81.25%) | at least 80% | yes |
| Raw target seen | 27/32 (84.375%) | diagnostic | — |
| Target dropped by ranking | 1/32 (3.125%) | diagnostic | — |
| Expected-family hit @10 | 32/32 (100%) | at least 90% | yes |
| Provider degradation | 4/32 (12.5%) | at most 25% | yes |
| Required family unsatisfied | 0/32 (0%) | at most 10% | yes |
| p95 latency | 2,517 ms | at most 15,000 ms | yes |
| Contributing providers | 6 | at least 5 | yes |
| Contributing source families | 4 | all 4 | yes |

The Wilson 95% interval for target hit is 64.7–91.1%. The point estimate clears
the locked 80% threshold, but the interval and small suite show why this is a
calibration result rather than a general quality claim.

## Topic breakdown

| Topic | Availability | Target @10 | Raw target | Expected family @10 | Degraded | Required unsatisfied | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Web | 8/8 | 7/8 | 8/8 | 8/8 | 4/8 | 0/8 | 2,517 |
| Reference | 8/8 | 8/8 | 8/8 | 8/8 | 0/8 | 0/8 | 403 |
| Academic | 8/8 | 7/8 | 7/8 | 8/8 | 0/8 | 0/8 | 2,807 |
| Code | 8/8 | **4/8** | 4/8 | 8/8 | 0/8 | 0/8 | 990 |

Web, reference and academic each cleared the locked 6/8 target condition. Code
did not.

## Target-rank diagnosis

Of the six final target misses:

- `p8-academic-06` and four code cases (`p8-code-01`, `p8-code-02`,
  `p8-code-04`, `p8-code-06`) were absent from every provider-native result
  list, so fusion and the diversity cap could not recover them;
- `p8-web-03` was present upstream at SearXNG rank 1 and Tavily rank 8 but was
  removed from the final top ten. This is the only measured ranking loss.

For the 26 retained targets, 12 ranked first, 22 were in the top three, 24 in
the top five and all 26 in the top ten. Their median final rank was 2 and p95
rank was 6.

The profile-aware policy was applied exactly as locked in all 32 outcomes:
three results per domain for web and ten for reference, academic and code. The
specialized routes returned 10 results in every academic and reference case;
seven of eight code cases returned 10, and one returned one upstream result.
The four missing repository targets are therefore upstream GitHub query misses,
not post-ranking losses or a recurrence of the Phase 7 `@3` configuration
defect.

## Provider contribution

| Provider | Requested | Successful response | Contributed |
|---|---:|---:|---:|
| SearXNG | 8 | 4 | 4 |
| Wikipedia | 24 | 24 | 15 |
| Crossref | 8 | 8 | 8 |
| arXiv | 8 | 8 | 8 |
| GitHub repositories | 8 | 8 | 8 |
| Tavily | 8 | 8 | 8 |

SearXNG failed in the final four web cases. Tavily succeeded and contributed in
all eight web cases, so every web request still contained required-family
evidence and the overall degradation rate stayed below the locked maximum.
Tavily used exactly one basic query per web case: eight requests and at most
eight credits.

## Relation to Phase 7

Phase 7 remains frozen at 18/32 targets overall, including 2/8 academic and 0/8
code. Phase 8 measured 26/32 overall, 7/8 academic and 4/8 code after applying
profile-aware caps, canonical identity matching and repository-query
normalization.

The two phases use different untouched suites, so this is not a paired A/B
estimate and the numerical change cannot be attributed to any one modification.
The new raw-rank telemetry does establish a narrower conclusion: the diversity
defect is fixed in the measured candidate, while GitHub query recall remains
the failing bottleneck.

## Reproducibility and privacy

- Python `3.11.15`, EvidenceMesh `0.1.0`, httpx `0.28.1`
- GitHub-hosted `ubuntu-latest`; physical region not exposed
- checksum-pinned 32-case suite, SearXNG settings and container digest
- 32 sequential searches, no query variants, no retry and no content fetching
- eight Tavily basic searches and at most eight Tavily credits
- fresh cache; every outcome recorded zero cache hits
- public outcomes omit query, title, snippet, content, URL, result and target
  identity values
- artifact ZIP SHA-256:
  `bcfdddd1bc2875404a15313da1e87e57a564b9871a520df3193416ac942ec276`

The complete thresholds and traffic constraints were frozen in
[`docs/benchmark-protocol-v6.md`](../../docs/benchmark-protocol-v6.md) before
the workflow made its first live request.
