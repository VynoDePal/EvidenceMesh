# Phase 7 Tavily quality calibration result

Date: 2026-07-29

Workflow run:
[`30438587349`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30438587349)

EvidenceMesh commit: `c837f5d51d89a8577408f34386ca55886c9b7358`

Raw report:
[`quality_calibration_phase7_2026-07-29.json`](quality_calibration_phase7_2026-07-29.json)

Raw SHA-256:
`4a692732200105b4b6c269647ba3e776ea3b977b70358b66aa24021596ac4104`

## Verdict

**Functional gate: fail. Release decision: no-go.**

The quality candidate passed the availability, expected-family, provider
degradation, required-family, latency, provider-diversity and family-diversity
gates. It missed the pre-registered target-hit gate: 18/32 exact authored
targets were returned, or 56.25%, below the locked 80% minimum.

The failure is concentrated outside Tavily's route. Web and reference each hit
8/8 targets. Academic hit 2/8 exact paper URLs and repository search hit 0/8
exact repositories. Stage B was therefore not run.

The unavailable second independent network is a separate mandatory blocker.
The cross-network gate remains `not_testable` at 1/2 environments. No
production-readiness, release-readiness or superiority claim is made.

## Tavily result

Tavily passed every pre-registered provider-specific condition:

| Tavily metric | Result | Gate | Pass |
|---|---:|---:|:---:|
| Requested web cases | 8/8 | exactly 8 | yes |
| Successful cases | 8/8 | at least 7/8 | yes |
| Contributing cases | 8/8 | at least 6/8 | yes |
| Queries per case | 1 | at most 1 | yes |

All eight web cases were available, contained web-family evidence and hit their
official target domain. One web case also recorded a SearXNG failure, but
Tavily and Wikipedia still returned results. This is positive evidence for the
Tavily-backed web route in one small, single-network calibration; it does not
establish general reliability.

## Locked overall metrics

| Metric | Result | Gate | Pass |
|---|---:|---:|:---:|
| Availability | 31/32 (96.875%) | at least 90% | yes |
| Target hit @10 | 18/32 (56.25%) | at least 80% | **no** |
| Expected-family hit @10 | 31/32 (96.875%) | at least 90% | yes |
| Provider degradation | 1/32 (3.125%) | at most 25% | yes |
| Required family unsatisfied | 1/32 (3.125%) | at most 10% | yes |
| p95 latency | 2,714 ms | at most 15,000 ms | yes |
| Contributing providers | 6 | at least 5 | yes |
| Contributing source families | 4 | all 4 | yes |

The raw report records Wilson 95% intervals. In particular, the target-hit
interval is 39.3–71.8%, entirely below the locked 80% threshold.

## Topic breakdown

| Topic | Availability | Target @10 | Expected family @10 | Degraded | Required unsatisfied | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| Web | 8/8 | 8/8 | 8/8 | 1/8 | 0/8 | 3,536 |
| Reference | 8/8 | 8/8 | 8/8 | 0/8 | 0/8 | 296 |
| Academic | 8/8 | 2/8 | 8/8 | 0/8 | 0/8 | 3,889 |
| Code | 7/8 | 0/8 | 7/8 | 0/8 | 1/8 | 866 |

The academic misses were `p7-academic-02` and `p7-academic-04` through
`p7-academic-08`. All still returned academic-family results. All eight code
cases missed their exact target repository, and `p7-code-02` returned no
result. Public outcome rows intentionally do not contain result URLs, so they
cannot establish whether an exact target was absent upstream or removed later
by ranking.

## Provider contribution

| Provider | Requested | Successful response | Contributed |
|---|---:|---:|---:|
| SearXNG | 8 | 7 | 7 |
| Wikipedia | 24 | 24 | 20 |
| Crossref | 8 | 8 | 8 |
| arXiv | 8 | 8 | 8 |
| GitHub repositories | 8 | 8 | 7 |
| Tavily | 8 | 8 | 8 |

All six providers and all four required source families contributed. A
successful provider response is not the same as retrieving the intended
target: that distinction is the main Phase 7 finding.

## Configuration finding

The locked runner requested ten results but did not override
`SearchRequest.max_per_domain`, whose default is three. A code search has only
the `github.com` domain, so EvidenceMesh could return at most three repository
hits per case even though the metric is named target hit `@10`. The code result
count confirms the bound: no code case returned more than three hits.

This is a candidate configuration defect and a limitation of the measured
result, not a reason to change the frozen verdict. The Phase 7 report remains a
valid evaluation of the committed candidate. It must not be recomputed with
post-hoc settings or relabelled as a pass.

A future protocol should pre-register profile-aware diversity limits, record
the private target rank without publishing result content, and use a new suite
before evaluating any GitHub-query or academic-identity improvements.

## Reproducibility and privacy

- Python `3.11.15`, EvidenceMesh `0.1.0`, httpx `0.28.1`
- GitHub-hosted `ubuntu-latest`; physical region not exposed
- checksum-pinned 32-case suite, SearXNG settings and container digest
- 32 sequential searches, no query variants, no retry and no content fetching
- eight Tavily basic searches and at most eight Tavily credits
- fresh cache; every outcome recorded zero cache hits
- public outcomes omit query, title, snippet, content, URL, result and target
  values
- artifact ZIP SHA-256:
  `51b83cc061c0156121042752329767b6abd3bcd1bc94db6333cd03c2bac5f69b`

The complete thresholds and traffic constraints were frozen in
[`docs/benchmark-protocol-v5.md`](../../docs/benchmark-protocol-v5.md) before
the workflow made its first live request.
