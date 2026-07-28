# SimpleQA reliability run — Phase 3 — 2026-07-28

Status: **valid retrieval-only reliability run; no-go for release or superiority claims**

## Artifacts

- Raw report:
  [`simpleqa_retrieval_phase3_2026-07-28.json`](simpleqa_retrieval_phase3_2026-07-28.json)
- Raw report SHA-256:
  `777157b67d35ec956d34da220e2043260476b89407d3c015c8dda5762420277c`
- Published runner commit:
  [`48e091f8194e8535280408fbce72897414896ec0`](https://github.com/VynoDePal/EvidenceMesh/commit/48e091f8194e8535280408fbce72897414896ec0)
- Executed local commit: `2646c38b22b93ac3eb51a9b69bafc47d59514d14`
- Executed and published source tree:
  `c0b9559226dfef9c278c370c1c422e7bc760d79c`
- Protocol: [benchmark protocol v1](../../docs/benchmark-protocol-v1.md)

The local execution commit and the published runner commit have the exact same
Git tree. The published commit is recorded in the raw report so the tested
source can be fetched without local repository access.

## Run envelope

| Field | Value |
|---|---|
| Dataset | Official SimpleQA test set |
| Dataset SHA-256 | `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032` |
| Sample | 200 rows, seed 0, without replacement |
| Sample manifest SHA-256 | `d41ec6c806792f4dc0730b6dd1bad0fe30310a7d3ca0b703bcfcd5cd7f580333` |
| Gold-source coverage | 200/200 sampled rows have curated URLs |
| UTC interval | 2026-07-28 18:55:47–18:56:45 |
| Wall time | 58.085 seconds |
| Network region | Africa/Porto-Novo sandbox; provider-observed egress not exposed |
| Python | 3.12.13 |
| Providers | DDGS 9.14.4 and Wikipedia API |
| Logical provider calls | 400 |
| Actual network attempts | 205 |
| Circuit-open skips | 195 |
| Cache / content fetch / LLM | Disabled / disabled / none |
| Deadline / global concurrency | 15 seconds / 3 |
| Circuit threshold / recovery delay | 3 consecutive failures / 60 seconds |

Every profile was ranked from the same provider/question snapshots. A
circuit-open decision remains a logical provider failure in the report, while
the actual network-attempt and skip counters expose the avoided work.

## Results

Rates are over 200 questions. Bracketed values are 95% Wilson intervals.

| Profile | Availability | Gold URL Hit@10 | Gold domain Hit@10 | Answer coverage@10 | Failed attempts / actual attempts | Circuit skips | Latency p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Federated | 70.5% [63.8, 76.4] | 12.0% [8.2, 17.2] | 60.5% [53.6, 67.0] | 7.5% [4.6, 12.0] | 5/205 (2.4%) | 195 | 343 / 888 ms |
| DDGS only | 0.0% [0.0, 1.9] | 0.0% [0.0, 1.9] | 0.0% [0.0, 1.9] | 0.0% [0.0, 1.9] | 5/5 (100%) | 195 | 0.068 / 0.108 ms |
| Wikipedia only | 70.5% [63.8, 76.4] | 12.0% [8.2, 17.2] | 60.5% [53.6, 67.0] | 7.5% [4.6, 12.0] | 0/200 (0%) | 0 | 339 / 593 ms |

The federated and Wikipedia profiles tie on every retrieval-quality metric
because DDGS returned no result. Their paired differences are exactly zero.

## Circuit-breaker analysis

- Five DDGS calls were already admitted while the first failures were in
  flight. All five reached the 15-second EvidenceMesh deadline.
- After the failure threshold was crossed, the circuit rejected the remaining
  195 DDGS calls without network I/O. The final health snapshot records the
  DDGS circuit as open and the Wikipedia circuit as closed.
- Wikipedia completed all 200 actual calls without a provider exception.
  It returned at least one result for 141 questions and a valid empty result
  list for 59.
- EvidenceMesh returned zero top-level query exceptions. Federated results were
  preserved whenever Wikipedia returned evidence.
- The full 200-row federated p95 fell to 888 ms. The five cold-start DDGS
  deadlines remain visible as outliers instead of being hidden.

The federated partial-query failure rate is still 100% because every question
has either a failed DDGS attempt or a transparent circuit-open DDGS skip. The
2.4% attempt failure rate measures a different fact: only five of 205 actual
network attempts failed.

## Comparison with the Phase 2 pilot

The 200-row sample starts with the exact 30 IDs from the Phase 2 pilot, but live
results are time-dependent. Retrieval-quality changes must not be attributed to
the circuit breaker.

On those same 30 IDs, federated median latency changed from 15,003 ms to
351 ms. The 30-row p95 remained approximately 15 seconds because five cold
DDGS attempts occurred before the circuit was open. Across all 200 rows, those
five outliers fall below the p95 cutoff and the federated p95 is 888 ms.

The Phase 2 pilot took 176.7 seconds for 30 questions; this run took 58.1
seconds for 200 questions. This is strong evidence that repeated failing
provider calls no longer dominate a sustained batch, but it is not a controlled
throughput benchmark.

## Release gates

| Gate | Target | Measured | Result |
|---|---:|---:|---|
| Federated availability | at least 90% | 70.5% | **Fail** |
| Partial-query failure | below 20% | 100% | **Fail** |
| Federated p95 latency | below 10 seconds | 0.888 seconds | **Pass** |
| Full runs across network environments | at least 2 | 1 | **Fail** |

## Separate SearXNG validation

The checksum-pinned self-hosted SearXNG profile is exercised separately in
[GitHub Actions run #7](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30390582239).
All seven jobs passed. The SearXNG job validates container startup, the exact
image digest and a live EvidenceMesh adapter call. It is a
connectivity/integration check, not part of the 200-row quality table and not a
second full benchmark environment.

## What this run does not establish

- It is not official SimpleQA answer accuracy. Lexical answer coverage is only
  a retrieval diagnostic.
- It does not measure SearXNG retrieval quality; Docker was unavailable in the
  benchmark runtime.
- It does not compare complete agents or paid-provider profiles.
- It does not generalize DDGS failure to other networks or to DuckDuckGo
  itself.
- One 200-row run cannot support a best-in-class claim.

## Decision

**No-go for a “best” claim, merge or release.** Phase 3 succeeds at isolating a
persistently failing provider and removes its sustained latency penalty. The
default zero-key profile still misses two reliability gates and has only one
full-run network environment.

The next phase should replace or repair the unreliable zero-key path, run the
same 200-row protocol in at least one additional network, and begin the
separately controlled end-to-end agent evaluation.
