# Zero-key live smoke test

Run date: **2026-07-28**

Network region: managed development environment

Cache: disabled by the live harness

Dataset: `benchmarks/fixtures/smoke_v1.jsonl` (one diagnostic question)

This is a connectivity and contract smoke test, not a statistically meaningful
quality benchmark.

## Wikipedia-only harness run

```bash
EVIDENCEMESH_PROVIDERS=wikipedia \
  uv run python benchmarks/run_live_retrieval.py \
  --dataset benchmarks/fixtures/smoke_v1.jsonl
```

The request completed successfully through the zero-key Wikipedia adapter. The
expected phrase was present in the retrieved material (`coverage=1.0`,
`failure_rate=0.0`, one sample, about 3.4 seconds). A one-question result is not
used for a product comparison.

## Partial-failure run

A second zero-key search enabled `ddgs,wikipedia`. Wikipedia succeeded and DDGS
timed out in this environment. EvidenceMesh returned the Wikipedia results plus
an explicit provider failure and partial-results warning, confirming failure
isolation. The observed failure is not interpreted as a general DDGS quality or
availability result.
