# Benchmark methodology

## Two separate questions

EvidenceMesh intentionally separates:

1. **Algorithm regression:** Does fusion, deduplication and diversity behave
   deterministically on known result lists?
2. **Live retrieval quality:** Does a dated provider configuration retrieve
   evidence containing the expected answer on real questions?

The offline suite cannot prove superiority over a live search product. The live
suite cannot be bit-for-bit deterministic because the web changes.

A one-question [zero-key smoke run](../benchmarks/results/live_smoke_2026-07-28.md)
is committed only as an interface/connectivity check; it is not included in any
quality claim. The locked [benchmark protocol v1](benchmark-protocol-v1.md)
defines the comparative Phase 2 pilot and the publication rules.

The first
[30-row SimpleQA retrieval pilot](../benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.md)
is a critical baseline. It demonstrated provider failure isolation but did not
meet the proposed reliability or latency gates and does not support a
superiority claim.

The
[200-row Phase 3 reliability run](../benchmarks/results/simpleqa_retrieval_phase3_2026-07-28.md)
then exercised the provider circuit breaker. It reduced sustained federated p95
latency to 888 ms by skipping 195 repeated DDGS attempts, while availability
remained 70.5%. The raw report preserves both logical failures and actual
network-attempt accounting.

## Offline federation benchmark

`src/evidencemesh/data/federation_v1.json` is a packaged fixture containing
provider result lists and explicit relevant URLs. The runner reports:

- Hit@1
- Hit@5
- mean reciprocal rank at 10
- nDCG@10
- duplicate rate
- unique-domain ratio

It compares EvidenceMesh fusion with the first listed single-provider baseline.
The fixture is synthetic and is only a regression gate.

## Live retrieval benchmark

`benchmarks/run_live_retrieval.py` can download the checksum-pinned official
SimpleQA dataset or accept local JSONL objects:

```json
{"id":"q1","question":"...","answer":"...","gold_urls":["https://example.org/source"]}
```

It interleaves named provider profiles on the same sample. It measures curated
source URL/domain recall, lexical answer coverage in titles/snippets,
availability, provider failures, diversity and latency. This is retrieval
measurement, not end-to-end QA accuracy.

The runner uses the same provider admission path as the SDK. Reports distinguish
logical provider calls, actual network attempts, attempt failures and
circuit-open skips. Every compared profile is still ranked from the same shared
snapshot for a given provider/question pair.

Every published result must include:

- EvidenceMesh commit SHA and configuration;
- provider endpoints and enabled providers;
- dataset name, byte-level SHA-256, sample IDs, manifest SHA-256 and sampling
  seed;
- UTC start/end time;
- machine and network region;
- cache state;
- hit metrics with 95% Wilson intervals, latency percentiles and failure rates;
- raw machine-readable output.

The default zero-key pilot is:

```bash
uv run python benchmarks/run_live_retrieval.py \
  --simpleqa \
  --sample-size 30 \
  --seed 0 \
  --max-results 10 \
  --concurrency 3 \
  --request-timeout 15 \
  --progress \
  --output benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.json
```

For the Phase 3 reliability run:

```bash
uv run python benchmarks/run_live_retrieval.py \
  --simpleqa \
  --sample-size 200 \
  --seed 0 \
  --max-results 10 \
  --concurrency 3 \
  --request-timeout 15 \
  --provider-failure-threshold 3 \
  --provider-recovery-seconds 60 \
  --progress \
  --output benchmarks/results/simpleqa_retrieval_phase3_2026-07-28.json
```

## Planned standard evaluations

- SimpleQA for checksum-pinned source recall and, separately, answer accuracy
  with the official judge.
- BrowseComp for hard, multi-hop browsing with a fixed client model.
- DeepResearch Bench FACT/RACE for citation and report quality.

End-to-end comparisons must use the same client model, prompt, time budget and
maximum tool calls. Results obtained with paid providers are reported separately
from the zero-key profile.
