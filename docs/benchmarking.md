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
quality claim.

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

`benchmarks/run_live_retrieval.py` accepts JSONL objects:

```json
{"id":"q1","question":"...","answer":"..."}
```

It checks whether the normalised expected answer appears in a result title,
snippet or extracted evidence quotation. This is retrieval answer coverage, not
end-to-end QA accuracy.

Every published result must include:

- EvidenceMesh commit SHA and configuration;
- provider endpoints and enabled providers;
- dataset name, revision, sample IDs and sampling seed;
- UTC start/end time;
- machine and network region;
- cache state;
- hit metrics, latency percentiles and failure rate;
- raw machine-readable output.

## Planned standard evaluations

- SimpleQA Verified for factual retrieval coverage.
- BrowseComp for hard, multi-hop browsing with a fixed client model.
- DeepResearch Bench FACT/RACE for citation and report quality.

End-to-end comparisons must use the same client model, prompt, time budget and
maximum tool calls. Results obtained with paid providers are reported separately
from the zero-key profile.
