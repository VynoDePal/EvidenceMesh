# Controlled end-to-end benchmark

The end-to-end runner asks a fixed model to answer from an EvidenceMesh research
packet. It supports OpenAI-compatible endpoints, including local servers. It is
generation infrastructure, not a self-grading leaderboard.

## Local-first example

Start the recommended search service, then point the runner at an already
installed local model server:

```bash
docker compose up -d searxng

EVIDENCEMESH_BENCHMARK_COMMIT="$(git rev-parse HEAD)" \
EVIDENCEMESH_PROVIDERS=searxng,wikipedia,crossref \
uv run python benchmarks/run_end_to_end.py \
  --simpleqa \
  --sample-size 30 \
  --seed 0 \
  --model your-local-model-id \
  --base-url http://127.0.0.1:11434/v1 \
  --depth standard \
  --max-sources 12 \
  --max-output-tokens 256 \
  --output benchmarks/results/end_to_end_simpleqa.local.json \
  --private-grading-bundle \
    benchmarks/private-results/end_to_end_simpleqa_grading.jsonl \
  --progress
```

The default base URL is the same loopback endpoint. For a remote compatible
service, set `--base-url`, place its key in an environment variable and select
that variable with `--api-key-env`. Keys are never written to reports. A remote
endpoint receives the benchmark question and retrieved web evidence.

## Outputs

The public JSON contains:

- dataset/sample hashes and IDs;
- prompt, model, budget and environment metadata;
- retrieval/generation latency and provider health;
- answer hashes, lengths and citation validity;
- errors and token usage when the endpoint reports it.

It intentionally excludes question text, reference answers, evidence excerpts
and generated answer text. The private grading bundle contains the minimum
`problem`, `answer` and `response` fields needed to connect precomputed answers
to a separately pinned evaluator. Never commit that bundle.

`answer_correctness` is always `null` and `official_evaluation` remains
`pending` until an official evaluator run is attached. Citation syntax validity
does not show that a citation supports the answer.

## Fair comparison checklist

Use the same:

- dataset revision and sample manifest;
- answer model identifier and inference settings;
- EvidenceMesh commit and providers;
- prompt version;
- source, content, token, concurrency and wall-time budgets;
- network window;
- official evaluator implementation and evaluator model.

Record failed cases without selectively retrying them. If a run is resumed
after an infrastructure interruption, publish the interruption and the exact
resume rule.

## Current evaluator limits

The reference SimpleQA code is pinned in
[protocol v2](benchmark-protocol-v2.md). Its model-based grader is external to
this free runner, so no official score is produced automatically.

DeepResearch Bench is a different long-form task and currently requires
specific evaluator models and scraping credentials. Do not convert the short
answer output into a DeepResearch Bench score or replace its FACT/RACE judges
with a local string metric.

## Locked Phase 10 pilot

Phase 10 adds a separate, purpose-built runner:
`benchmarks/run_end_to_end_phase10.py`. It does not replace the generic
OpenAI-compatible generation harness above.

The locked pilot uses 12 untouched SimpleQA cases, four arms and three Google
API models:

- `closed_book`;
- one-query `tavily_direct`;
- zero-key EvidenceMesh `community`;
- Tavily-backed EvidenceMesh `quality`;
- `gemma-4-31b-it`;
- `gemma-4-26b-a4b-it`;
- `gemini-3.5-flash-lite`.

Retrieval occurs once per case and arm. All three models receive the exact same
packet and prompt for that pair. There are 36 retrieval case-arm operations,
144 generation calls, at most 24 Tavily basic-search requests and no retries.

Unlike the generic harness, this runner computes deterministic diagnostics:
answer-key substring coverage, evidence answer-key coverage, citation-ID
validity and a citation-support substring proxy. They are intentionally named
as proxies. The official SimpleQA model grader is not run, and public output
still excludes questions, references, evidence and generated answer text.

The exact sample, prompt, API settings, traffic cap and pre-registered gates are
frozen in [benchmark protocol v8](benchmark-protocol-v8.md). A passing pilot
cannot establish external-agent superiority or release readiness.

The published
[Phase 10 result](../benchmarks/results/end_to_end_phase10_2026-07-29.md)
failed the functional gate. `tavily_direct` reached 27/36 strict answer-key
hits, `quality` 13/36, `community` 6/36 and `closed_book` 0/36. SearXNG
degraded in every EvidenceMesh web case; quality remained available through
other providers but retained the answer key in only 5/12 evidence packets.
The raw privacy-safe report is committed beside the interpreted result.
