# Competitive benchmark

Snapshot date: **2026-07-28**.

Repository revisions and the exact fairness rules are pinned in
[benchmark protocol v1](benchmark-protocol-v1.md).

## Scope

EvidenceMesh is retrieval infrastructure for an external model. GPT Researcher,
Open Deep Research, Local Deep Research and Vane are mainly end-to-end research
agents or applications. SearXNG is a metasearch engine. A single leaderboard
score across these roles would be misleading, so this benchmark separates
documented capabilities from retrieval measurements.

The comparison was made against current project documentation, not marketing
copy from third parties:

- [SearXNG documentation](https://docs.searxng.org/)
- [GPT Researcher](https://github.com/assafelovic/gpt-researcher) and its
  [MCP server](https://github.com/assafelovic/gptr-mcp)
- [LangChain Open Deep Research](https://github.com/langchain-ai/open_deep_research)
- [Local Deep Research](https://github.com/LearningCircuit/local-deep-research)
- [Vane](https://github.com/ItzCrazyKns/Vane), formerly Perplexica
- [DeepResearch Bench](https://github.com/Ayanami0730/deep_research_bench)

## Capability matrix

“Documented” means the linked project explicitly describes the feature. “Not
documented” does not prove that a project cannot be extended to support it.

| Capability | EvidenceMesh | SearXNG | GPT Researcher MCP | Open Deep Research | Local Deep Research | Vane |
|---|---:|---:|---:|---:|---:|---:|
| Primary role | Retrieval layer | Metasearch | Research agent | Research agent | Research app | Answering app |
| External LLM required by core | No | No | Yes | Yes | Yes | Yes |
| Zero-key web path documented | Yes | Yes | No default | Not default | Yes | Yes |
| Native MCP server for retrieval | Yes | No | Yes | No | Not documented | Not documented |
| Provider-neutral typed SDK | Yes | HTTP API | Agent API | Agent graph | Python/HTTP APIs | HTTP API |
| Deterministic rank fusion | Yes | Engine aggregation | Not documented | Not documented | Search dependent | Search dependent |
| Stable citation IDs before synthesis | Yes | No | Agent generated | Agent generated | Agent generated | Agent generated |
| Evidence content hashes | Yes | No | Not documented | Not documented | Not documented | Not documented |
| Per-source prompt-injection flags | Yes | No | Not documented | Not documented | Not documented | Not documented |
| Public-IP and redirect revalidation | Yes | Service boundary | Not documented | Not documented | Egress controls documented | Not documented |
| Reproducible evaluation path | Offline + retrieval + generation harness | No QA harness | Project dependent | DeepResearch Bench | Published datasets | Not documented |

## What EvidenceMesh can claim today

- The package, CLI and six-tool FastMCP surface share the same typed engine.
- Its core profile has no required paid API and no required LLM.
- The 12-case synthetic regression fixture improves Hit@1 from `0.000` to
  `1.000` and MRR@10 from `0.472222` to `1.000` over the first-provider
  baseline. This only proves the intended fusion behavior on the fixture.
- The local test suite covers ranking, caching, provider adapters, URL safety,
  extraction, SDK orchestration, CLI and MCP contracts.

## What EvidenceMesh cannot claim yet

It has not yet beaten end-to-end agents on DeepResearch Bench, BrowseComp,
SimpleQA Verified or another shared live benchmark. Those comparisons require
the same client model, prompts, provider access, tool-call budget, date and
hardware. Until raw comparable runs exist, “best” is a product goal, not a
result.

The Phase 2 retrieval pilot compares EvidenceMesh provider compositions only.
It must not be presented as a leaderboard against the complete products in this
table.

Its [dated result](../benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.md)
found that the zero-key federated profile tied Wikipedia-only on retrieval
metrics because DDGS failed every call in the managed test environment. The
federation preserved partial results but inherited the failed provider's
15-second deadline. This is a reliability finding, not evidence of competitive
superiority.

Phase 4 removes DDGS from the recommended default, promotes the pinned private
SearXNG path and adds a controlled model-generation harness. Those are product
and evaluation improvements, not evidence that EvidenceMesh already beats the
complete agents in this table. The
[200-row SearXNG result](../benchmarks/results/simpleqa_retrieval_phase4_2026-07-28.md)
also found only 71.5% federated availability and 98.0% partial-query failure in
the measured GitHub environment. It is evidence against a best-in-class or
release claim, not evidence for one.

## Fair next comparison

Use EvidenceMesh as the retrieval MCP for a fixed external model, then compare
it with each system using:

1. the same benchmark sample and sampling seed;
2. the same model and reasoning settings;
3. the same maximum wall time and tool calls;
4. separate zero-key and paid-provider tracks;
5. retrieval coverage, citation correctness, citation completeness, latency
   and cost;
6. committed raw outputs plus the exact configuration.
