# Benchmark protocol v2

Status: **locked for Phase 4 before execution**

Snapshot date: **2026-07-28**

Protocol v1 remains the historical protocol for the DDGS/Wikipedia Phase 2 and
Phase 3 runs. Version 2 changes the recommended zero-key web path to a private,
self-hosted SearXNG service and introduces an executable, but deliberately
ungraded, end-to-end answer-generation track.

## Track A: self-hosted retrieval

### Dataset and sample

The dataset, checksum, row IDs and sampling procedure are unchanged from
[protocol v1](benchmark-protocol-v1.md):

- official SimpleQA test set;
- byte SHA-256
  `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032`;
- 200 rows selected with `random.Random(0).sample` without replacement;
- no questions or reference answers in the committed public report.

### Profiles

| Profile | Providers | Purpose |
|---|---|---|
| `federated` | SearXNG + Wikipedia | Recommended zero-key web federation |
| `searxng` | SearXNG | Self-hosted general-web ablation |
| `wikipedia` | Wikipedia | Reference-source ablation |

Each provider/question pair is retrieved once and shared between profile
ablations. Cache and document fetching are disabled. Provider calls use a
single global concurrency slot to limit upstream load.

### SearXNG envelope

- Image:
  `searxng/searxng:2026.7.26-b060c780d@sha256:d0aaeb14880e6e92bde1518fcc7261e995783367d63d95203383607bef9c6516`
- Configuration: [`docker/searxng/settings.yml`](../docker/searxng/settings.yml),
  with its byte SHA-256 written into the raw report.
- Web engines used by this benchmark: `brave`, `duckduckgo`, and `wikipedia`.
  The pinned configuration also retains small news, science and code sets, but
  the SimpleQA run requests only the general category.
- Service scope: a private container dedicated to the run. A public shared
  SearXNG instance must not be load-tested.
- EvidenceMesh deadline: 15 seconds.
- SearXNG upstream request timeout: 4 seconds, bounded at 8 seconds.
- Circuit breaker: three consecutive failures, 60-second recovery delay.

The runner records SearXNG calls that return results while reporting
unresponsive upstream engines. A response with no results and one or more
unresponsive engines is a provider failure rather than a successful empty
result.

### Environment and publication

The first v2 run executes on a GitHub-hosted `ubuntu-latest` runner. GitHub does
not expose its physical network region, so the report must say so instead of
inventing a location. The benchmark workflow checks out the pull-request head
commit, verifies the container digest, uploads the raw JSON as an artifact and
does not use a public search instance.

The v1 reliability gates remain:

| Gate | Target |
|---|---:|
| Federated availability | at least 90% |
| Partial-query failure rate | below 20% |
| Federated p95 | below 10 seconds |
| Comparable full SearXNG runs | at least two network environments |

The GitHub run is a second full benchmark environment for the project, but only
one full v2 SearXNG environment. It therefore cannot by itself satisfy the last
gate or establish cross-network generality.

## Track B: controlled answer generation

[`benchmarks/run_end_to_end.py`](../benchmarks/run_end_to_end.py) connects an
EvidenceMesh research packet to an OpenAI-compatible chat-completions endpoint.
It can use a local model endpoint and does not require a paid service.

Controls fixed or recorded by the runner:

1. checksum-pinned dataset, sample seed and IDs;
2. exact prompt version and prompt hashes;
3. requested and returned model identifiers;
4. temperature zero, maximum output tokens and no selective retries;
5. research depth, source/content budgets, case wall time and concurrency;
6. provider health, failures, latency and token usage when returned;
7. hashes and citation telemetry instead of public question, evidence or answer
   text.

The runner emits two distinct artifacts:

- a public telemetry report safe to commit;
- an optional private JSONL grading bundle containing question, reference answer
  and generated response. `benchmarks/private-results/` is gitignored.

The runner never calculates answer correctness. For a comparable SimpleQA
result, grade the private bundle separately with the unchanged evaluator from
`openai/simple-evals` commit
[`652c89d0`](https://github.com/openai/simple-evals/commit/652c89d0ca9df547706735883097e9537d40dc47);
record the evaluator model and cost with the outputs.

DeepResearch Bench is not silently substituted with a free heuristic. At its
pinned commit
[`469cce54`](https://github.com/Ayanami0730/deep_research_bench/commit/469cce54ea7f6a63c163d3d9fec879cf289ec484),
the official workflow requires 100 long-form tasks, GPT-5.5 for RACE,
GPT-5.4-mini for FACT and a Jina key for FACT scraping. Phase 4 therefore starts
Track B with a reproducible SimpleQA generation harness; official
DeepResearch Bench execution remains a later, separately funded evaluation.

## Claim policy

Permitted:

> On the dated v2 retrieval run, the recorded SearXNG profile achieved metric X
> under the pinned container and configuration.

Not permitted:

- calling lexical answer coverage “SimpleQA accuracy”;
- deriving a correctness score from answer string overlap;
- claiming the end-to-end track passed before an official evaluator result;
- ranking EvidenceMesh above complete research agents from retrieval-only data;
- calling EvidenceMesh “best” from a single SearXNG network environment.
