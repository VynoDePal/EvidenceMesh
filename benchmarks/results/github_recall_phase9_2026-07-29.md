# Phase 9 paired GitHub repository recall result

Date: 2026-07-29

Workflow run:
[`30444712944`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30444712944)

EvidenceMesh commit: `71bb02c8580bc2dff9dc651514ce0098d17eea22`

Raw report:
[`github_recall_phase9_2026-07-29.json`](github_recall_phase9_2026-07-29.json)

Raw SHA-256:
`17b6f266d6d828b8f013b460810143a1cb02f98c52fea28a1c3811af844e5aab`

## Verdict

**Functional gate: pass. Release decision: no-go.**

The production `entity-anchor-v2` candidate retrieved all 24 authored
repositories in both the provider's first 20 results and EvidenceMesh's final
top ten. The frozen `legacy-v1` baseline retrieved 4/24. The paired comparison
therefore measured 20 candidate wins, zero baseline wins and a net gain of 20
targets. Every pre-registered candidate and paired functional gate passed.

This is a narrow repository-recall result, not an end-to-end search or
deep-research result. The unavailable second independently administered
network remains a mandatory blocker: the cross-network gate is `not_testable`
at 1/2 environments. Stage B was not run, the pull request remains draft and
no release-readiness or superiority claim is made.

## Arm-level metrics

| Metric | `legacy-v1` baseline | `entity-anchor-v2` candidate | Candidate gate |
|---|---:|---:|---:|
| Successful requests | 23/24 | 24/24 | at least 23/24 |
| Available result sets | 8/24 | 24/24 | at least 23/24 |
| Raw target seen in first 20 | 4/24 | 24/24 | at least 20/24 |
| Final target hit @10 | 4/24 | 24/24 | at least 18/24 |
| Target rank @1 | 3/24 | 21/24 | diagnostic |
| Target rank @3 | 4/24 | 24/24 | diagnostic |
| Median target rank when seen | 1 | 1 | diagnostic |
| p95 target rank when seen | 2 | 2 | diagnostic |
| p50 latency | 338 ms | 709 ms | diagnostic |
| p95 latency | 1,086 ms | 865 ms | at most 15,000 ms |
| Provider queries | 24 | 24 | exactly one per case |
| Cache hits | 0 | 0 | zero |

The Wilson 95% interval for candidate target hit is 86.2–100%; the baseline
interval is 6.7–35.9%. The candidate returned ten final results for every case.
The baseline produced an available result set for only eight cases; one request
failed at the provider boundary and the remaining unavailable cases returned
no usable result. No request was retried.

## Paired comparison

| Outcome | Final target @10 | Raw target in first 20 |
|---|---:|---:|
| Candidate wins | 20 | 20 |
| Baseline wins / regressions | 0 | 0 |
| Both succeed | 4 | 4 |
| Neither succeeds | 0 | 0 |
| Net candidate gain | +20 | +20 |
| Exact two-sided McNemar p-value | 0.000002 | 0.000002 |

The paired design holds the authored target, process and network environment
constant for both strategies. It supports the measured conclusion that
entity-anchored GitHub queries fixed the Phase 8 repository-query failure mode
on this suite. It does not establish performance outside this task class.

## Difficulty and query-form breakdown

| Stratum | Baseline target @10 | Candidate target @10 |
|---|---:|---:|
| Low ambiguity | 0/8 | 8/8 |
| Medium ambiguity | 2/8 | 8/8 |
| High ambiguity | 2/8 | 8/8 |
| Entity-first query | 4/12 | 12/12 |
| Intent-prefix query | 0/12 | 12/12 |

The candidate reached 8/8 in every difficulty stratum and 12/12 for both query
forms. The baseline's four hits all came from entity-first inputs; it retrieved
none of the 12 intent-prefix targets.

## Rank diagnosis

All 24 candidate targets appeared within GitHub's first ten provider results
and survived EvidenceMesh's final ranking. Twenty-one finished first and three
finished second. The three rank-two outcomes were provider rank one before
fusion, but none was lost from the final top ten, so the locked
`target_dropped_by_ranking` diagnostic remained zero.

The identical 24-query budget in each arm rules out extra query expansion as
the explanation for the gain. The candidate changes only deterministic query
planning: it extracts the repository entity, searches
`name,description,topics`, preserves explicit qualifiers and maps exact
repository references to `repo:owner/name`.

## Reproducibility and privacy

- Python `3.11.15`, EvidenceMesh `0.1.0`, httpx `0.28.1`
- GitHub-hosted `ubuntu-latest`; physical region not exposed
- anonymous GitHub repository search, API version `2022-11-28`
- checksum-pinned 24-case suite, with 24 requests per arm and 48 total
- alternating arm order and at least 6.5 seconds between request starts
- one request per arm and case, no retry, no cache and no content fetching
- no Tavily, SearXNG, new secret or paid-provider call
- public outcomes omit queries, normalized queries, target identities, titles,
  snippets, content, URLs and result lists
- artifact ZIP SHA-256:
  `2ae217253ccbafcfdaf8c0e07d6a54b7623b00fcbffdc788af49b5bbc5a97593`

GitHub repository best-match ordering can change over time, and this authored
24-case suite is too small and specialized to estimate general search quality.
Replication on a second independently administered network remains required.

The complete thresholds and traffic constraints were frozen in
[`docs/benchmark-protocol-v7.md`](../../docs/benchmark-protocol-v7.md) before
the workflow made its first live request.
