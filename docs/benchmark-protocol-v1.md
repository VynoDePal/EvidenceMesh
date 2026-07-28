# Benchmark protocol v1

Status: **locked for the Phase 2 pilot**

Snapshot date: **2026-07-28**

## Decision

EvidenceMesh is a retrieval layer, while several projects commonly described as
competitors are complete research agents. Their headline scores are not directly
comparable. Protocol v1 therefore separates two tracks:

1. a retrieval-only, zero-key track that can run without an LLM;
2. an end-to-end research track in which every system must use the same client
   model, prompts, evaluator, budgets and network conditions.

Only the first track is automated by
`benchmarks/run_live_retrieval.py`. No result from that runner may be described
as SimpleQA accuracy or deep-research quality.

## Track A: zero-key retrieval

### Dataset and revision

The runner downloads the official SimpleQA test set referenced by
`openai/simple-evals` and rejects it unless its SHA-256 is:

```text
feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032
```

Reference repository commit:
[`652c89d0`](https://github.com/openai/simple-evals/commit/652c89d0ca9df547706735883097e9537d40dc47).
The `simpleqa_eval.py` blob read for this protocol is
`0fc266800a87ace55ec192c9a91cafe92fef7b48`.

SimpleQA has 4,326 rows. Its metadata includes curated source URLs, which makes
it useful for a retrieval-only test even though its official evaluator measures
answer correctness with an LLM judge. The pilot selects rows exactly as the
reference implementation does: `random.Random(seed).sample` without
replacement. A report records every selected question ID, where the ID is the
first 16 hexadecimal characters of `SHA-256(question)`. Questions and answers
are not copied into committed results.

### Profiles

The default zero-key profiles are:

| Profile | Providers | Interpretation |
|---|---|---|
| `federated` | DDGS + Wikipedia | EvidenceMesh zero-key web federation |
| `ddgs` | DDGS only | Component ablation through the same adapter and ranker |
| `wikipedia` | Wikipedia only | Component ablation through the same adapter and ranker |

These are EvidenceMesh configuration ablations, not full-product comparisons
with DuckDuckGo or Wikipedia. SearXNG may be added as a profile only when the
exact self-hosted image/configuration is recorded. Public shared instances must
not be used for published load tests.

Paid providers belong in a separate report. A profile that silently loses a
provider because a key is absent is invalid; its health section and warnings
must be inspected before publication.

### Execution controls

- Each provider is called exactly once per question. All profiles are ranked
  from those shared raw provider snapshots, preventing duplicate traffic and
  guaranteeing an identical live input for every ablation.
- Provider calls are scheduled question-first to reduce temporal ordering bias.
- The same query, language, maximum result count and deadline apply to all
  profiles.
- Search and document caches are disabled.
- Content fetching is disabled in the primary retrieval track.
- A single global concurrency cap applies across profiles.
- Raw query exceptions and provider-level partial failures are separate fields.
- Profile latency is the maximum measured latency of its component provider
  calls, modelling concurrent federation without including scheduler queue time.
- The report includes the dataset and sample hashes, UTC interval, platform,
  Python version, EvidenceMesh commit, provider configuration and health data.

Recommended pilot command:

```bash
EVIDENCEMESH_BENCHMARK_COMMIT="$(git rev-parse HEAD)" \
  uv run python benchmarks/run_live_retrieval.py \
  --simpleqa \
  --sample-size 30 \
  --seed 0 \
  --max-results 10 \
  --concurrency 3 \
  --request-timeout 15 \
  --network-region not-exposed-by-managed-runtime \
  --progress \
  --output benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.json
```

### Metrics

The primary metric is `gold_url_hit_at_10`: at least one of the curated source
URLs occurs in the first ten results after canonicalisation. HTTP and HTTPS are
treated as equivalent; host, path and non-tracking query parameters must still
match.

Secondary metrics are:

- `gold_domain_hit_at_k`: a result shares a registrable-domain hint with a
  curated source;
- `gold_url_mrr`: reciprocal rank of the first exact curated URL;
- `answer_coverage_at_k`: a normalised gold answer string occurs in a result
  title or snippet;
- availability, provider-call failures and query-level exceptions;
- result/domain diversity and p50/p95 wall-clock latency.

Binary rates include 95% Wilson score intervals. Pairwise comparisons report
left-only hits, right-only hits and the paired rate difference. No significance
claim is made from the 30-row pilot.

URL recall is intentionally strict and domain recall intentionally permissive.
Answer coverage is lexical and can both miss correct paraphrases and accept text
that merely mentions the answer. The three measures must be read together.

### Publication gate

A Track A result may be published only when:

- the dataset checksum and sample manifest match the report;
- every profile has the intended providers in `health`;
- raw outcomes are committed alongside a human-readable analysis;
- environmental provider failures are reported, not discarded or retried
  selectively;
- the report does not claim SimpleQA accuracy or superiority over agents.

## Track B: end-to-end research

This track is specified but is not part of the zero-key pilot. It is required
before EvidenceMesh can claim to outperform complete research agents.

| Evaluation | Measures | Required common controls |
|---|---|---|
| SimpleQA | Short-answer correctness | Same answer model, prompt and LLM judge |
| BrowseComp | Hard browsing-agent accuracy | Same client model, tool-call/time budget and judge |
| DeepResearch Bench | Citation and report quality through FACT/RACE | Same report model, evaluator models, prompt, search access and budget |

For each system, record:

1. repository commit and complete configuration;
2. exact client and evaluator model identifiers and reasoning settings;
3. prompt text, tool schemas, maximum tool calls and wall time;
4. network region, run interval, retries and concurrency;
5. token, provider and evaluator cost;
6. raw model responses, citations, evaluator outputs and errors.

The official benchmark evaluator must be used unchanged or every modification
must be published as a separate variant. A self-reported score using another
model, dataset revision or judge is context, not a comparable result.

## Competitor snapshot pins

Documentation and future adapters are evaluated against these repository
commits:

| Project | Commit |
|---|---|
| SearXNG | [`8372f5d8`](https://github.com/searxng/searxng/commit/8372f5d8551df9bf89716f82b14079b44d771e73) |
| GPT Researcher | [`5d84d2f5`](https://github.com/assafelovic/gpt-researcher/commit/5d84d2f5553e70a2765a8ff3a0d2672d60437ce8) |
| GPT Researcher MCP | [`63884773`](https://github.com/assafelovic/gptr-mcp/commit/63884773685b1f12c7f0d9e283b3d71a5b9b5fda) |
| Open Deep Research | [`d337ae32`](https://github.com/langchain-ai/open_deep_research/commit/d337ae32ed4ff8f4c6fbe192ba3bf1b2d6610799) |
| Local Deep Research | [`e5ff013c`](https://github.com/LearningCircuit/local-deep-research/commit/e5ff013c45a1e91e807f99a1f37e48ec8e2287ad) |
| Vane | [`7dc5d088`](https://github.com/ItzCrazyKns/Vane/commit/7dc5d088f7262fbc5e39037f84940a8a2193c5fb) |
| DeepResearch Bench | [`469cce54`](https://github.com/Ayanami0730/deep_research_bench/commit/469cce54ea7f6a63c163d3d9fec879cf289ec484) |

## Claim policy

The following wording is acceptable:

> On the dated, checksum-pinned retrieval-only pilot, profile A achieved metric
> X under the recorded environment.

The following wording is not acceptable:

> EvidenceMesh scores X% on SimpleQA.

It is also not acceptable to rank EvidenceMesh above an end-to-end agent using
retrieval-only results. “Best open-source deep-research tool” remains a product
goal until Track B has raw, controlled, reproducible results.
