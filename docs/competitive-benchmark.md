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

The subsequent
[Phase 5 engine calibration](../benchmarks/results/searxng_calibration_phase5_2026-07-28.md)
found DuckDuckGo reliable and relevant on the small provider-selection suite,
but only one of eight candidates passed every pre-registered gate. The
minimum-two-engine requirement prevented promotion and any tuned SimpleQA
rerun. This preserves evaluation independence; it does not establish a
competitive quality result.

Phase 6 adds direct academic, reference and repository verticals plus
deterministic traffic-aware routing. Its
[24-case multi-source result](../benchmarks/results/multisource_calibration_phase6_2026-07-28.md)
measured 100% availability and 91.7% target/family hit rates, but it also
measured a 33.3% partial-failure rate because SearXNG failed in 8/12 routed
cases. That exceeds the pre-registered 25% maximum. The functional gate and the
separate two-network gate are therefore both closed; this is still evidence
against a best-in-class claim.

Phase 7 does not retune the Phase 6 cases. It introduces an untouched 32-case
quality-track suite, an explicit reference profile and a Tavily basic-search
candidate capped at eight credits. The
[locked protocol](benchmark-protocol-v5.md) measures both raw provider
degradation and whether the requested source family remains satisfied. A
single-network result, pass or fail, cannot establish competitive superiority
or release readiness.

The
[Phase 7 result](../benchmarks/results/quality_calibration_phase7_2026-07-29.md)
passed every Tavily-specific gate and all eight web target cases, but the full
candidate retrieved only 18/32 exact targets. Academic reached 2/8 and
repository code reached 0/8, so the functional gate failed before the separate
network gate was considered. This is evidence that adding a strong general-web
provider is insufficient without improving vertical target ranking and its
profile-aware diversity policy.

Phase 8 addresses those measured defects without rewriting the Phase 7 result.
Its [locked protocol](benchmark-protocol-v6.md) uses a new 32-case suite,
profile-aware domain caps, conservative GitHub repository-query normalization,
canonical target identities and provider-native target-rank diagnostics. The
Tavily budget and all functional thresholds are unchanged. The experiment is
still retrieval-only and single-network, so even a functional pass cannot
support a best-in-class or release claim.

The
[Phase 8 result](../benchmarks/results/quality_calibration_phase8_2026-07-29.md)
cleared every overall threshold with 26/32 targets but failed the pre-registered
code gate at 4/8. Five targets were absent upstream and only one was lost by
EvidenceMesh ranking. This narrows the next engineering problem to repository
query recall, but the failed topic gate and missing independent network remain
evidence against release or superiority.

Phase 9 is intentionally narrower than a competitive benchmark. Its
[paired protocol](benchmark-protocol-v7.md) tests only GitHub repository recall,
using one anonymous request per arm and case on 24 new targets. It can establish
whether the entity-anchor planner improves the measured failure mode, but it
cannot establish overall search quality, deep-research quality or competitive
superiority.

The
[Phase 9 result](../benchmarks/results/github_recall_phase9_2026-07-29.md)
found 24/24 targets at ten for the entity-anchor candidate and 4/24 for the
frozen baseline, with 20 paired gains and zero regressions. This passes the
pre-registered functional gate and resolves the measured repository-query
defect on that suite. It does not change the competitive claim boundary:
replication is available from only one network, Stage B was not run and no
end-to-end agent comparison exists.

Phase 10 begins end-to-end measurement without crossing that claim boundary.
Its [locked protocol](benchmark-protocol-v8.md) applies the same three hosted
answer models to `closed_book`, one-query Tavily, EvidenceMesh `community` and
EvidenceMesh `quality` arms. Retrieval packets are reused across models, model
traffic is fixed at 144 calls, Tavily is capped at 24 basic requests and no
failed request is selectively retried.

The resulting answer-key and citation-support fields are transparent normalized
substring proxies. They are not official SimpleQA accuracy, semantic citation
judgments or DeepResearch Bench scores. The user deferred external-agent
replication, and a second independently administered network remains
unavailable. Phase 10 can therefore compare the internal deployment choices
under a fixed run, but cannot establish that EvidenceMesh is better than GPT
Researcher, Open Deep Research, Local Deep Research, Vane or another complete
agent.

The
[Phase 10 result](../benchmarks/results/end_to_end_phase10_2026-07-29.md)
does not support a competitive claim. Tavily direct produced 27/36 strict
answer-key hits, EvidenceMesh quality 13/36 and community 6/36. Quality gained
seven paired hits over community but lost 14 net pairs to Tavily direct.
SearXNG degraded in all EvidenceMesh web cases, and quality missed both
retrieval and citation gates. This failed pilot narrows the next work to
reliable free web retrieval, provider-aware evidence retention and citation
enforcement before an external-agent comparison is justified.

Phase 11.5 addresses the measured answer and citation defect without claiming
new evaluation independence. Its
[locked protocol](benchmark-protocol-v13.md) reuses the Phase 10 cases, shares
one raw provider pool per case, and compares Tavily direct, current 8/2 quality
and a provider-aware prompt candidate under the same three answer models. The
community pool remains observable but non-blocking.

The
[Phase 11.5 result](../benchmarks/results/phase11_5_quality_recovery_2026-07-29.md)
passed the protocol, prompt-evidence and three citation gates, but failed two
blocking gates. The candidate produced 25/36 strict answer-key hits against
28/36 for Tavily direct, a paired net `-3`. Gemma 26B also completed only
10/12, 9/12 and 10/12 requests across the three arms. Citation presence
recovered to 94.1%, identifier validity to 100% and support proxy to 76.5%.
The candidate is therefore a no-go; Phase 12 and an external-agent comparison
remain blocked, and no competitive superiority follows.

Phase 11.6 is the next disclosed calibration, still on the observed cases and
therefore still unsuitable for a competitive claim. Its
[frozen protocol](benchmark-protocol-v14.md) compares only legacy versus
strict citation instructions while sharing byte-identical Tavily evidence.
It includes blocking Gemma 26B and Gemini 3.5 Flash Lite. A passing result can
change the paid quality default and unblock a separately authorized untouched
evaluation; it cannot itself authorize Phase 12 or an external-agent
comparison. The free community profile is unchanged.

The
[Phase 11.6 result](../benchmarks/results/phase11_6_tavily_citation_isolation_2026-07-29.md)
isolated the citation contract successfully: strict and legacy answer-key hits
tied at 25/36, while strict citations reached 100% presence and identifier
validity. The run nevertheless failed its pre-registered completion gate
because blocking Gemma 26B completed 10/12 requests in each arm. No provider
default or evaluation boundary changed, so an external-agent comparison and
competitive claim remain blocked.

Phase 11.7 is a fresh confirmation calibration, not the competitive benchmark
itself. Its [frozen protocol](benchmark-protocol-v15.md) excludes every prior
SimpleQA identifier, evaluates 24 new cases with shared Tavily packets, and
seals a separate 96-case Phase 12 reserve without exposing questions, answers
or distributions. The blocking models are Gemma 4 31B and Gemini 3.5 Flash
Lite; Gemma 26B is not called and no longer gates the experiment. Exactly 24
Tavily and 96 generation requests are allowed, with no selective retry.

Even a ten-gate pass can only promote the optional paid-provider `quality`
default in a separate commit and make the sealed suite eligible for later
authorization. It cannot execute Phase 12, start the external-agent comparison
or support a “best” claim. Provider and model choices remain user-controlled,
and the zero-key community track stays distinct.

The
[Phase 11.7 result](../benchmarks/results/phase11_7_fresh_confirmation_2026-07-29.md)
passed seven of ten gates. Strict and legacy answer-key proxies tied at 32/48,
but the fresh Tavily prompt packet was answer-bearing for only 18/24 cases.
Strict citation presence reached 45/48 and support proxy reached 33/48, below
their frozen 95% and 75% gates. The optional quality default was not promoted,
the sealed Phase 12 evaluation remains blocked, and an external-agent
comparison or competitive claim is still unauthorized.

Phase 11.8 is also a calibration, not a competitive comparison. Its
[frozen protocol](benchmark-protocol-v16.md) reuses the observed Phase 11.7
cases to compare current strict evidence, expanded strict evidence and an
expanded structured-response contract. One up-to-20-result Tavily pool is
shared per case, and the two expanded arms receive byte-identical evidence.
The exact live ceiling is 24 Tavily and 144 generation requests over Gemma 4
31B and Gemini 3.5 Flash Lite, with no retry or repair.

The twelve gates can diagnose whether evidence depth and a schema-bound
citation contract recover the failed retrieval and citation floors. They
cannot establish generalization because the cases are already observed. A
complete pass can therefore unlock only the design of a fresh Phase 11.9
confirmation; it cannot change provider defaults, inspect Phase 12, start the
external-agent comparison or support a “best” claim. The protocol-lock commit
contains no Phase 11.8 live result. Ordinary PR updates remain offline; live
execution on the draft PR requires an exact same-repository authorization
label event.

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
