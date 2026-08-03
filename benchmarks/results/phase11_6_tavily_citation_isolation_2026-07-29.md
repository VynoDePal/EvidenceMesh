# Phase 11.6: Tavily citation-contract isolation calibration

Date: **2026-07-29**

Status: **candidate failed; quality was not promoted; Phase 12 remains
blocked**

Phase 11.6 is a disclosed causal calibration on the 12 SimpleQA cases already
observed in Phases 10 and 11.5. It is not an untouched evaluation and cannot
support a competitive, release or superiority claim.

The frozen protocol is
[`benchmark-protocol-v14.md`](../../docs/benchmark-protocol-v14.md), SHA-256
`d72aa29b989d74cff09ca211e291b5d2d58d86d684fe6bca5f75a0dac429c4e8`.
No threshold, model, case, prompt arm, timeout, retry rule or decision boundary
was changed after the run.

## Audited run

| Field | Value |
|---|---|
| Source commit | `5140b1d458e1846f6aa971e6707be7832c90b341` |
| GitHub run | [`30487190189`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30487190189) |
| Artifact ID | `8738447777` |
| Artifact name | `phase11-6-tavily-citation-isolation-5140b1d458e1846f6aa971e6707be7832c90b341` |
| Artifact ZIP SHA-256 | `bec8ed89a6dba9facbdefe56d68279f86755e4a7e49fd37a825afe559938168a` |
| Raw JSON SHA-256 | `86b9eda8ecb55822bb93501dbd1d1614c84c04444d1df62fbf6252e1202d22bd` |
| Runtime | 12 minutes 6.885 seconds |
| Network region | GitHub-hosted runner |

The ZIP is 13,301 bytes and contains exactly one 123,574-byte privacy-safe
JSON report. Questions, reference answers, source titles, URLs, snippets,
evidence, system and user prompts, generated answer text and credentials are
absent. Case IDs, aggregate metrics and one-way answer hashes are retained for
paired auditing.

## Locked traffic accounting

| Counter | Expected | Observed | Result |
|---|---:|---:|---|
| Case retrieval operations | 12 | 12 | pass |
| Provider invocations | 12 | 12 | pass |
| Tavily requests | 12 | 12 | pass |
| Gemini generation requests | 72 | 72 | pass |
| Retries | 0 | 0 | pass |
| Repair requests | 0 | 0 | pass |

There was no model fallback, selective retry, citation repair, cache replay or
second scored run.

## Pre-registered gates

All ten gates had to pass in the same run.

| Gate | Observed | Required | Result |
|---|---|---|---|
| Protocol integrity | 12 retrieval, 12 Tavily, 72 generation, 0 retry/repair | exact | pass |
| Selected and projected packet identity | 12/12 case pairs | 12/12 | pass |
| Tavily availability and prompt answer-key proxy | 12/12 available; 10/12 answer-bearing | 12/12; at least 10/12 | pass |
| Completion by model and arm | Gemma 26B: 10/12 legacy and 10/12 strict | at least 11/12 for every pair | **fail** |
| Strict aggregate answer non-regression | 25/36 vs 25/36; paired net `0` | no regression | pass |
| Strict per-model answer non-regression | all three models net `0` | no regression for any model | pass |
| Strict citation presence | 34/34, 100% | at least 90% | pass |
| Strict citation-presence lift | +35.3 points over legacy | at least +20 points | pass |
| Strict citation-ID integrity | 34/34, 100% | 100% | pass |
| Strict citation-support proxy | 28/34, 82.4% | at least 70% | pass |

The candidate passed **9/10** gates. The completion failure is blocking because
`gemma-4-26b-a4b-it` was explicitly frozen as a blocking model.

## Answer and completion results

| Model | Legacy hits | Strict hits | Legacy completed | Strict completed | Paired net |
|---|---:|---:|---:|---:|---:|
| `gemma-4-31b-it` | 9/12 | 9/12 | 12/12 | 12/12 | `0` |
| `gemma-4-26b-a4b-it` | 7/12 | 7/12 | 10/12 | 10/12 | `0` |
| `gemini-3.5-flash-lite` | 9/12 | 9/12 | 12/12 | 12/12 | `0` |
| **Total** | **25/36** | **25/36** | **34/36** | **34/36** | **`0`** |

The overall pairing contains one strict win, one legacy win, 24 shared hits
and 10 shared misses. Gemma 31B and Gemini 3.5 Flash Lite are exact paired
ties. Gemma 26B contributes both opposite wins, so its paired net is also
zero.

This isolates the Phase 11.5 answer regression: when selected and projected
Tavily evidence is held byte-identical, the strict citation contract does not
reduce the measured answer-key proxy for the aggregate or for any tested
model.

## Citation result

| Arm | Presence | Valid IDs among cited responses | Contract pass | Support proxy |
|---|---:|---:|---:|---:|
| `tavily_legacy` | 22/34, 64.7% | 21/22, 95.5% | 21/34, 61.8% | 19/34, 55.9% |
| `tavily_strict` | **34/34, 100%** | **34/34, 100%** | **34/34, 100%** | **28/34, 82.4%** |

The strict packet-local contract raises citation presence by 35.3 percentage
points while keeping answer-key coverage unchanged. Identifier integrity is
deterministic. The support measure remains a disclosed substring proxy rather
than semantic entailment or claim-by-claim completeness.

## Reliability and latency

Gemma 26B produced two failed requests in each arm: one HTTP 500 response and
one response without answer text. Gemma 31B and Gemini 3.5 Flash Lite completed
12/12 requests in both arms. Selective retry was prohibited, so all four
failures remain in the scored result.

| Stage or arm | p50 latency | p95 latency |
|---|---:|---:|
| Tavily retrieval | 2.02 s | 2.44 s |
| `tavily_legacy` generation | 9.47 s | 17.14 s |
| `tavily_strict` generation | 10.19 s | 25.79 s |

## Decision

The immutable scored result is:

- `phase11_6_candidate_passed`: **false**;
- `quality_profile_promotion_allowed`: **false**;
- `quality_profile_promoted`: **false**;
- `phase12_untouched_evaluation_allowed`: **false**;
- `phase12_executed`: **false**;
- `community_profile_unchanged`: **true**;
- `public_alpha_allowed`: **false**;
- `merge_allowed`: **false**;
- `release_ready`: **false**;
- `release_decision`: **no-go**;
- `superiority_claim_allowed`: **false**.

The default quality profile therefore remains the existing community-plus-
Tavily bundle with a 0.8 Tavily reservation. The free community profile is
unchanged. No Tavily-only promotion, Phase 12 run, external-agent benchmark,
merge, PyPI publication, GitHub Release, public alpha or “best open-source
search” claim is authorized.
