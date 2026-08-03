# Phase 10 controlled end-to-end result

Date: 2026-07-29

Workflow run:
[`30449727569`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30449727569)

EvidenceMesh commit: `ae9a0191dd01a175da649fe0b12dfb0424f905f6`

Raw report:
[`end_to_end_phase10_2026-07-29.json`](end_to_end_phase10_2026-07-29.json)

Raw SHA-256:
`95259c697c7b511dec0075a7782f07023f7e5ee48f8b863363794ec44c8bf263`

## Verdict

**Functional gate: fail. Release decision: no-go.**

The thin one-query `tavily_direct` arm produced the strongest measured result:
27/36 generated answers contained the normalized answer key. EvidenceMesh
`quality` reached 13/36, `community` reached 6/36 and `closed_book` reached
0/36. The quality profile improved over community by eight paired wins and one
regression, a net gain of seven, but lost to Tavily direct on 14 pairs without
recording a paired win.

This is a strict normalized-substring diagnostic on a 12-case SimpleQA pilot,
not official SimpleQA accuracy. The assistant's pre-reference web-search
diagnostic scored 8/12 with the same proxy, while manual inspection found three
formatting-equivalent misses and one rounded numeric near-match. No semantic
score is inferred from either result.

The frozen functional gate failed on community availability, retrieval
answer-key coverage, generated-answer coverage, quality citation coverage and
one model-completion threshold. The unavailable second independently
administered network remains a separate blocker. External-agent replication was
deferred, Stage B is blocked, the pull request remains draft and no release or
competitive-superiority claim is made.

## Generated-answer diagnostics

| Arm | Completed | Answer-key covered | Citation presence | Valid cited IDs | Citation-support proxy |
|---|---:|---:|---:|---:|---:|
| `closed_book` | 33/36 | 0/36 | — | — | — |
| `tavily_direct` | 36/36 | **27/36** | 16/36 | 16/16 | 16/36 |
| `community` | 36/36 | 6/36 | 8/36 | 8/8 | 2/36 |
| `quality` | 34/36 | 13/36 | 14/34 | 14/14 | 7/34 |

All cited IDs were valid, but citation presence was only 41.2% for completed
quality outputs, below the locked 75% threshold. Its support proxy was 20.6%,
below the locked 50% threshold. These proxies test strings and packet IDs; they
do not establish semantic citation correctness or completeness.

## Per-model answer-key coverage

| Model | Completed | `closed_book` | `tavily_direct` | `community` | `quality` |
|---|---:|---:|---:|---:|---:|
| `gemma-4-31b-it` | 45/48 | 0/12 | **9/12** | 1/12 | 4/12 |
| `gemma-4-26b-a4b-it` | 46/48 | 0/12 | **9/12** | 3/12 | 4/12 |
| `gemini-3.5-flash-lite` | 48/48 | 0/12 | **9/12** | 2/12 | 5/12 |

Five calls returned no non-thought answer text and remain failed without retry:
three `closed_book` calls and two `quality` calls. The 31B Gemma model completed
45/48, one below the locked minimum. The other two models passed the completion
gate. Tavily direct reached the same 9/12 answer-key coverage under all three
models.

## Retrieval diagnostics

| Arm | Available | Answer key in evidence | Mean evidence blocks | Provider degradation | p50 | p95 |
|---|---:|---:|---:|---:|---:|---:|
| `tavily_direct` | 12/12 | **10/12** | 9.000 | 0/12 | 1,988 ms | 2,435 ms |
| `community` | 5/12 | 1/12 | 1.583 | 12/12 | 312 ms | 2,925 ms |
| `quality` | 12/12 | 5/12 | 9.417 | 12/12 | 6,245 ms | 22,159 ms |

The self-hosted SearXNG route accumulated six consecutive failures and ended
with its circuit open in both EvidenceMesh profiles. Every community and
quality outcome recorded a SearXNG provider failure. The community profile
therefore returned no evidence for seven cases. Tavily and Wikipedia kept
quality available for all cases, but the relevant answer string survived in
only 5/12 final quality packets.

Tavily direct and the quality profile each issued exactly one Tavily basic
query per case. Direct Tavily retained answer-key evidence in 10/12 packets,
while the complete quality packet retained it in 5/12. This is consistent with
useful web evidence being displaced or diluted during multi-provider fusion,
ranking, fetching or prompt assembly. The privacy-safe report does not contain
final provider-contribution telemetry, so it cannot isolate which of those
stages caused each loss. That telemetry must be added before claiming a
specific root cause.

## Paired comparison

| Comparison | Candidate wins | Baseline wins | Shared hits | Shared misses | Net |
|---|---:|---:|---:|---:|---:|
| `quality` vs `community` | 8 | 1 | 5 | 22 | **+7** |
| `quality` vs `closed_book` | 13 | 0 | 0 | 23 | **+13** |
| `quality` vs `tavily_direct` | 0 | 14 | 13 | 9 | **-14** |

Quality passed the pre-registered paired gates against community and
closed-book. Those gains were insufficient to pass the complete functional
gate, and the diagnostic comparison against Tavily direct strongly favors the
thin baseline on this run.

## Locked gate failures

- `community` availability: 5/12, required at least 9/12;
- `community` evidence answer-key coverage: 1/12, required at least 6/12;
- `quality` evidence answer-key coverage: 5/12, required at least 8/12;
- `community` generated answer-key coverage: 6/36, required at least 15/36;
- `quality` generated answer-key coverage: 13/36, required at least 18/36;
- `gemma-4-31b-it` completion: 45/48, required at least 46/48;
- quality citation presence: 41.2%, required at least 75%;
- quality citation-support proxy: 20.6%, required at least 50%.

Protocol integrity, the Tavily request ceiling, zero retries, quality
availability, paired quality gains and cited-ID validity all passed.

## Traffic, usage and fairness

- 36 retrieval case-arm operations;
- 144 generation requests;
- exactly 24 recorded Tavily provider queries and at most 24 credits;
- zero cache use and zero retries;
- 48 case-arm prompt groups, each with one prompt hash and one evidence-block
  count reused across all three models;
- 89,020 reported total tokens for `gemini-3.5-flash-lite`;
- 78,557 reported total tokens for `gemma-4-26b-a4b-it`;
- 76,329 reported total tokens for `gemma-4-31b-it`.

The runner reports provider token usage but does not infer a monetary cost
because the API key does not reveal the Google project billing tier.

## Reproducibility and privacy

- Python `3.11.15`, FastMCP `3.4.5`, httpx `0.28.1`, Pydantic `2.13.4`;
- GitHub-hosted `ubuntu-latest`; physical region not exposed;
- checksum-pinned SimpleQA dataset and 12-case manifest;
- native Gemini `v1beta generateContent`, high thinking and provider-default
  sampling controls;
- public outcomes contain hashes and telemetry but no questions, reference
  answers, source titles, URLs, evidence text or generated answers;
- artifact ID: `8723827787`;
- artifact ZIP SHA-256:
  `68a08205bf7a5bb6b49211b7a8ffbd39dca154fd20aeeea521c335fbc47a99f2`.

The complete sample, settings, thresholds and claim boundary were frozen in
[`docs/benchmark-protocol-v8.md`](../../docs/benchmark-protocol-v8.md) before
the workflow made its first live request.

## Recommended next engineering work

1. Add privacy-safe pre-fusion, post-fusion and final-prompt contribution
   telemetry per provider.
2. Prevent the quality profile from discarding strong Tavily evidence, using a
   provider-aware quota or evidence-selection stage tested on a new calibration
   suite.
3. Replace the single fragile keyless web route with a reliability-qualified
   fallback strategy; do not treat one SearXNG instance as sufficient.
4. Enforce or validate citations before returning an evidence-backed answer.
5. Freeze a new untouched sample before evaluating any candidate fix. Do not
   tune and re-score on these 12 cases.
