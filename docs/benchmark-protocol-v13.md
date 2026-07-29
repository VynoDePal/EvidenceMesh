# EvidenceMesh Phase 11.5 quality-recovery protocol

Status: frozen before the first scored Phase 11.5 provider or model request.

Date frozen: 2026-07-29.

## Purpose

Phase 11.5 tests whether the Tavily-backed quality profile can recover the
answer and citation quality lost in Phase 10. It isolates two disclosed
changes:

1. provider-aware prompt projection that prevents an early long evidence block
   from consuming the complete 12,000-character budget;
2. a strict citation contract plus deterministic citation-ID validation.

This is corrective calibration, not an untouched evaluation. It deliberately
reuses the 12 SimpleQA cases observed in Phase 10. No Phase 12 question,
reference answer or result may be accessed or generated in this phase.

## Locked data

- SimpleQA revision:
  `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032`;
- reused Phase 10 manifest:
  `b38b89d316219be7dbd249f4365e0801330eb469ff6cc9b4fdaffebe6510134f`;
- 12 cases selected with the already-published Phase 10 seed and exclusions;
- SearXNG configuration:
  `docker/searxng/phase11-community-settings.yml`;
- SearXNG configuration SHA-256:
  `e33610cdd83c89a0fb85e687e632b179ed36057d948db102c7a6e2c33b456efb`.

Reference answers are available only to the transparent substring scorer. They
must not influence query construction, provider selection, ranking, prompt
projection or generation instructions.

## Shared retrieval

Exactly one uncached search operation runs for each case. Its provider-native
results form one raw pool replayed without another provider request.

Configured providers:

- SearXNG;
- bounded DDGS;
- Wikipedia;
- Crossref;
- arXiv;
- GitHub;
- Tavily.

Tavily is capped at exactly one logical request per case and 12 for the run.
No other paid search provider is enabled. Provider failures remain visible and
receive no retry.

## Arms

Three arms receive model generations:

| Arm | Raw pool | Ranking | Prompt |
|---|---|---|---|
| `tavily_direct` | Tavily results only | current deterministic ranking | Phase 10 sequential projection and prompt |
| `quality_current_8_2` | complete shared pool | current Tavily 8/2 reservation | Phase 10 sequential projection and prompt |
| `quality_candidate` | complete shared pool | same Tavily 8/2 reservation | provider-aware balanced projection and strict citation contract |

`community_observability` replays non-Tavily results for retrieval metrics only.
It receives no model call and cannot fail the candidate gate.

The candidate projection:

- preserves the current selected evidence and citation identifiers;
- orders up to four Tavily-backed blocks before one complementary block;
- includes every selected non-empty block whose headers fit;
- caps each included excerpt at 900 characters;
- applies the same cap to every block;
- does not fill unused space by expanding an earlier block.

With eight Tavily-backed and two complementary blocks, the prompt allocation is
therefore 8/2 by both source count and equal-cap evidence capacity.

## Generation

The exact model order is:

1. `gemma-4-31b-it`;
2. `gemma-4-26b-a4b-it`;
3. `gemini-3.5-flash-lite`.

Every model receives every generation arm for every case:

- 12 cases;
- 3 arms;
- 3 models;
- exactly 108 native Gemini `generateContent` requests.

The runner uses high thinking, a 2,048-token output ceiling, a 120-second
generation wall-time ceiling and at least two seconds between request starts.
There is no retry, selective retry, model fallback, citation repair pass or
manual replacement of a failed response.

The legacy arms retain the Phase 10 system and user prompts. The candidate
requires:

- evidence-only factual answering;
- an exact returned `[S#]` identifier immediately after every externally
  verifiable factual statement;
- no invented, altered or renumbered identifier;
- claim splitting when different sources support different clauses;
- an explicit evidence gap instead of unsupported internal completion;
- no bibliography.

## Metrics

The public report computes:

- retrieval and prompt availability;
- selected and prompt answer-key substring coverage;
- generated answer-key substring coverage;
- paired candidate wins, losses and net gain;
- completion by model and arm;
- citation presence;
- exact citation-ID syntax and packet membership;
- a citation-support substring proxy;
- provider contribution, reservation and failure telemetry;
- request counts, latency and provider/model usage.

The answer and support measures are normalized substring proxies. They are not
official SimpleQA accuracy, semantic entailment, citation correctness or
citation completeness.

## Pre-registered gates

All gates must pass in the same run:

1. exactly 12 retrieval operations, 12 Tavily requests, 108 generation
   requests and zero retries or repairs;
2. at least 11/12 completed generations for every model-arm pair;
3. candidate prompt answer-key evidence coverage no more than 1/12 below
   Tavily direct;
4. candidate generated answer-key coverage and paired net gain not below
   Tavily direct;
5. candidate paired net gain not below the current 8/2 arm;
6. candidate citation presence at least 90%;
7. candidate citation IDs 100% valid among responses containing citations;
8. candidate citation-support proxy at least 70%.

The community observability arm is explicitly excluded from these gates.

## Privacy and integrity

The public JSON may contain case IDs, hashes, counts, booleans, bounded failure
classes, aggregate usage and latency. It must not contain:

- questions or reference answers;
- source titles, URLs, snippets or extracted evidence;
- system or user prompt text;
- generated answer text;
- credentials, raw exceptions or response bodies.

Generated answer hashes are allowed. Keys remain GitHub Actions secrets and are
sent only in provider-required headers.

## Decision boundary

A gate pass authorizes only a later, separately requested Phase 12 run. It does
not authorize Phase 12 execution during this workflow.

Regardless of the result:

- the PR remains draft;
- merge remains blocked;
- PyPI and GitHub Release remain blocked;
- public alpha distribution remains blocked pending a separate governance and
  security decision;
- external competitor claims remain blocked;
- no superiority or “best open-source search” claim is allowed.
