# SimpleQA retrieval pilot — 2026-07-28

Status: **valid retrieval-only pilot; not a release or superiority result**

## Artifacts

- Raw report:
  [`simpleqa_retrieval_pilot_2026-07-28.json`](simpleqa_retrieval_pilot_2026-07-28.json)
- Raw report SHA-256:
  `8619e64971b33da02477dd6d46da8d49e9a63ce51d3439e2b4538de89e9afd34`
- Published runner commit: `cf654b184132e9ae8bbf5d9598b48a52ad4a22ad`
- Executed local commit: `781e6d62a875b9d1c910d4b506f54dcdabffe960`
- Shared source tree: `2af9340fbb5c8e7769d5b3b8a06a169430cd0f25`
- Protocol: [benchmark protocol v1](../../docs/benchmark-protocol-v1.md)

The GitHub app created a new commit object because local `gh` credentials were
not retained. The executed and published commits above point to the exact same
Git tree; the raw report records both identities.

## Run envelope

| Field | Value |
|---|---|
| Dataset | Official SimpleQA test set |
| Dataset SHA-256 | `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032` |
| Sample | 30 rows, seed 0, without replacement |
| Sample manifest SHA-256 | `32257293df2cc2eba1381fd7275391ec54d25fb868f4fb3f0d85be7b9403f613` |
| Gold-source coverage | 30/30 sampled rows have curated URLs |
| UTC interval | 2026-07-28 18:06:28–18:09:24 |
| Network region | Not exposed by the managed runtime |
| Python | 3.12.13 |
| Providers | DDGS 9.14.4 and Wikipedia API |
| Live calls | 60: one call per provider and question |
| Cache / content fetch / LLM | Disabled / disabled / none |
| Deadline / global concurrency | 15 seconds / 3 |

Every profile was ranked from the same raw provider snapshots. The run did not
send duplicate provider requests for the federation and component ablations.

## Results

Rates are over 30 questions. Bracketed values are 95% Wilson intervals.

| Profile | Availability | Gold URL Hit@10 | Gold domain Hit@10 | Answer coverage@10 | Provider-call failures | Latency p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|
| Federated | 56.7% [39.2, 72.6] | 13.3% [5.3, 29.7] | 50.0% [33.2, 66.8] | 3.3% [0.6, 16.7] | 32/60 (53.3%) | 15,003 / 15,008 ms |
| DDGS only | 0.0% [0.0, 11.4] | 0.0% [0.0, 11.4] | 0.0% [0.0, 11.4] | 0.0% [0.0, 11.4] | 30/30 (100%) | 15,003 / 15,008 ms |
| Wikipedia only | 56.7% [39.2, 72.6] | 13.3% [5.3, 29.7] | 50.0% [33.2, 66.8] | 3.3% [0.6, 16.7] | 2/30 (6.7%) | 725 / 8,591 ms |

The federated and Wikipedia profiles tie on every retrieval metric because DDGS
returned no results. Their paired differences are therefore exactly zero.

## Failure analysis

- DDGS failed 30/30 calls: 28 benchmark deadline expirations, one provider
  timeout exception and one generic DDGS exception.
- Wikipedia had two transport failures, eleven successful calls with no result
  for the exact question, and seventeen calls with at least one result.
- EvidenceMesh returned no query-level exception. Despite one failed provider on
  every federated question, it preserved Wikipedia results for 17/30 questions.
  This validates fail-open isolation, not retrieval quality.
- The federation waited for DDGS, so its median latency rose from 725 ms for
  Wikipedia alone to the 15-second deadline with no quality gain.

The repeated DDGS failures may be specific to this managed network, its selected
backend or both. They must not be generalized to DuckDuckGo or all EvidenceMesh
deployments. They are still valid evidence that the current default profile has
an environment-sensitive reliability risk.

## What this run establishes

1. The dataset, sample, provider inputs and raw outcomes are reproducibly
   identified.
2. Shared provider snapshots make the federation/component comparison
   internally fair.
3. Provider failure isolation works: partial provider failure did not become a
   top-level query exception.
4. The current zero-key federation can become as slow as its failing component.

## What this run does not establish

- It is not official SimpleQA answer accuracy. Lexical answer coverage is only a
  retrieval diagnostic.
- It does not compare EvidenceMesh with SearXNG or complete agents. Docker was
  unavailable locally, and a shared public SearXNG instance was deliberately
  not load-tested.
- It does not compare GPT Researcher, Open Deep Research, Local Deep Research or
  Vane. Those require the controlled end-to-end track with the same client and
  evaluator models.
- Thirty rows are a pilot, not a stable leaderboard.
- It does not support the claim that EvidenceMesh is the best open-source
  research tool.

## Decision

**No-go for a “best” claim, merge or release.** Phase 2 succeeds as benchmark
infrastructure and as a critical baseline, but the measured default zero-key
profile is not yet release-grade in this environment.

The next engineering gates should be:

1. add per-provider health/circuit-breaking so a repeatedly failing provider
   does not impose its full deadline on every query;
2. add a pinned self-hosted SearXNG profile and test it in an environment with
   Docker;
3. rerun at least 200 SimpleQA rows across more than one network environment;
4. require at least 90% availability, less than 20% partial-query failure and a
   p95 below 10 seconds before a release candidate;
5. run the separately controlled SimpleQA/BrowseComp/DeepResearch Bench
   end-to-end track before any cross-agent superiority claim.
