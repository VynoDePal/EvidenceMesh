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
