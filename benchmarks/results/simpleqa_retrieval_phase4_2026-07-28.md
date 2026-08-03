# SimpleQA SearXNG retrieval run — Phase 4 — 2026-07-28

Status: **valid retrieval-only run; no-go for release or superiority claims**

## Artifacts

- Raw report:
  [`simpleqa_retrieval_phase4_2026-07-28.json`](simpleqa_retrieval_phase4_2026-07-28.json)
- Raw report SHA-256:
  `97742a6ceff0b9943ad9dfbb9a94fb36de36f05f38a7d82ea72dc34168f3a48b`
- Executed source commit:
  [`f78ce4bf53f1e167ea7a2b849e91f5543ba321e2`](https://github.com/VynoDePal/EvidenceMesh/commit/f78ce4bf53f1e167ea7a2b849e91f5543ba321e2)
- Executed source tree:
  `b002b8e0d4b564041cd9318058a4bb25ab2c40e0`
- GitHub Actions run:
  [`Phase 4 SearXNG Benchmark #1`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30393884099)
- Uploaded ZIP SHA-256:
  `c9144511e51225ca0d9c4fe417463257d83a78a0d10a0d88ee5697d7100ec8da`
- Protocol: [benchmark protocol v2](../../docs/benchmark-protocol-v2.md)

The downloaded ZIP hash matches the digest recorded by GitHub Actions. The
JSON records the executed commit, dataset and sample hashes, SearXNG image,
configuration hash, provider endpoints and dependency versions.

## Run envelope

| Field | Value |
|---|---|
| Dataset | Official SimpleQA test set |
| Dataset SHA-256 | `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032` |
| Sample | 200 rows, seed 0, without replacement |
| Sample manifest SHA-256 | `d41ec6c806792f4dc0730b6dd1bad0fe30310a7d3ca0b703bcfcd5cd7f580333` |
| Gold-source coverage | 200/200 sampled rows have curated URLs |
| UTC interval | 2026-07-28 19:54:02–19:55:01 |
| Wall time | 58.537 seconds |
| Network | GitHub-hosted `ubuntu-latest`; physical region not exposed |
| Python | 3.11.15 |
| SearXNG | `2026.7.26-b060c780d`, immutable digest pinned |
| SearXNG configuration SHA-256 | `6d55495b4dab4638a31719d0dc86c36e3ac163af0c4f75d8ff75dcdb1fba63b9` |
| Profiles | SearXNG + Wikipedia; SearXNG only; Wikipedia only |
| Logical calls / network attempts | 400 / 210 |
| Circuit-open skips | 190 |
| Cache / content fetch / LLM | Disabled / disabled / none |
| Deadline / global concurrency | 15 seconds / 1 |
| Circuit threshold / recovery delay | 3 consecutive failures / 60 seconds |

Every profile was ranked from the same provider/question snapshots. The raw
report contains hashed row IDs and text hashes, not questions or reference
answers.

## Results

Rates are over 200 questions. Bracketed values are 95% Wilson intervals.
Latency is measured over all logical profile calls, including fail-fast circuit
skips.

| Profile | Availability | Gold URL Hit@10 | Gold domain Hit@10 | Answer coverage@10 | Failed attempts / actual attempts | Circuit skips | Latency p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Federated | 71.5% [64.9, 77.3] | 13.0% [9.0, 18.4] | 61.5% [54.6, 68.0] | 9.5% [6.2, 14.4] | 6/210 (2.9%) | 190 | 253 / 499 ms |
| SearXNG only | 2.0% [0.8, 5.0] | 1.5% [0.5, 4.3] | 2.0% [0.8, 5.0] | 1.5% [0.5, 4.3] | 6/10 (60.0%) | 190 | 0.070 / 0.107 ms |
| Wikipedia only | 70.5% [63.8, 76.4] | 12.0% [8.2, 17.2] | 60.5% [53.6, 67.0] | 8.0% [5.0, 12.6] | 0/200 (0.0%) | 0 | 247 / 460 ms |

The SearXNG-only latency percentiles are dominated by 190 circuit-open skips
and must not be interpreted as upstream request latency. The ten actual
SearXNG attempts took 193–905 ms.

## SearXNG reliability finding

- SearXNG made ten actual requests: four returned results and six failed.
- Each successful request returned at least ten results. Three successful calls
  also reported unresponsive upstreams.
- Observed unresponsive engine names included `brave` and `duckduckgo`.
- Six zero-result responses also reported two unavailable upstream engines and
  were correctly treated as provider failures, not valid empty searches.
- After the final three consecutive failures, the circuit opened and skipped
  190 calls. The ending health snapshot records SearXNG as degraded/open.
- Wikipedia completed all 200 requests without a provider exception.
- EvidenceMesh returned zero top-level query exceptions and preserved
  Wikipedia evidence while SearXNG was unavailable.

The container itself, its JSON API and the adapter were operational. The
measured failure is in the configured metasearch upstream path from this GitHub
network, not a container-startup failure.

## Within-run ablation

Against the shared Wikipedia snapshots, federation added:

- three answer-coverage hits and no losses: +1.5 percentage points;
- two exact gold-URL hits and no losses: +1.0 point;
- two gold-domain hits and no losses: +1.0 point;
- two additional available questions: +1.0 point.

These discordant counts are too small to support a stable quality conclusion.
The two-sided exact sign-test values are 0.25 for the three answer additions and
0.50 for either two-hit source addition. More importantly, the gains came with
a 98% partial-query failure rate.

## Descriptive comparison with Phase 3

Both runs use the same dataset and 200-row manifest, but they use different
providers and network environments. The differences below are descriptive and
must not be attributed solely to SearXNG.

| Federated metric | Phase 3 DDGS + Wikipedia | Phase 4 SearXNG + Wikipedia |
|---|---:|---:|
| Availability | 70.5% | 71.5% |
| Gold URL Hit@10 | 12.0% | 13.0% |
| Gold domain Hit@10 | 60.5% | 61.5% |
| Answer coverage@10 | 7.5% | 9.5% |
| Partial-query failure | 100.0% | 98.0% |
| Failed attempts / actual attempts | 5/205 (2.4%) | 6/210 (2.9%) |
| Circuit-open skips | 195 | 190 |
| Latency p50 / p95 | 343 / 888 ms | 253 / 499 ms |

Phase 4 therefore validates the new path and its transparent failure
accounting, but does not solve zero-key web reliability in the measured
environment.

## Release gates

| Gate | Target | Measured | Result |
|---|---:|---:|---|
| Federated availability | at least 90% | 71.5% | **Fail** |
| Partial-query failure | below 20% | 98.0% | **Fail** |
| Federated p95 latency | below 10 seconds | 0.499 seconds | **Pass** |
| Comparable full SearXNG environments | at least 2 | 1 | **Fail** |

## End-to-end scope

Phase 4 adds a controlled EvidenceMesh-to-model generation runner, but this
retrieval run uses no LLM. No official SimpleQA answer score was generated.
The runner deliberately leaves `answer_correctness` unset until its private
grading bundle is evaluated with the separately pinned official evaluator.

## Decision

**No-go for a “best” claim, merge or release.** The source, container,
configuration and 200-row result are reproducible, and the fail-open behavior
works. However, the recommended zero-key federation still fails three of four
locked release gates. SearXNG's upstream availability from the GitHub runner is
too weak to serve as the sole general-web path.

The next phase should test a revised zero-key engine set without changing this
locked result, add a second SearXNG network environment, and execute the
controlled end-to-end harness with a fixed local model plus official grading.
