# Phase 11.7: fresh Tavily confirmation calibration

Date: **2026-07-29**

Status: **candidate failed; quality was not promoted; Phase 12 remains
blocked**

Phase 11.7 is a fresh, pre-registered confirmation calibration on 24 SimpleQA
cases that exclude every case observed in the earlier EvidenceMesh phases. A
separate, disjoint 96-case Phase 12 reserve remained sealed. This calibration
is not an official SimpleQA evaluation and cannot support a competitive,
release or superiority claim.

The frozen protocol is
[`benchmark-protocol-v15.md`](../../docs/benchmark-protocol-v15.md), SHA-256
`a38cfdd9f8bb4ca9ebf39caac212e7868a773b62c874e1738bc8a5ff9ea1088e`.
No threshold, model, case, prompt arm, timeout, retry rule or decision boundary
was changed after the run.

## Audited run

| Field | Value |
|---|---|
| Source commit | `6c240d6f5ad8472108051a0dbb33e5266df6a997` |
| GitHub run | [`30495183403`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30495183403) |
| Artifact ID | `8741649271` |
| Artifact name | `phase11-7-fresh-confirmation-6c240d6f5ad8472108051a0dbb33e5266df6a997` |
| Artifact ZIP SHA-256 | `14feac392842fc0bb744216f2f4e987d3d52e81c1a67e25664ad9b7f54cf5642` |
| Raw JSON SHA-256 | `783fdaa60b351f975632b9cf23b57bab8766e39a8d81fabdead590962deea6de` |
| Runtime | 15 minutes 49.425 seconds |
| Network region | GitHub-hosted runner |

The ZIP is 18,695 bytes and contains exactly one 169,692-byte privacy-safe JSON
report. Questions, reference answers, source titles, URLs, snippets, evidence,
system and user prompts, generated answer text, credentials and all 96 Phase 12
case identifiers are absent. The 24 scored opaque case identifiers, aggregate
metrics and one-way answer hashes are retained for paired auditing.

## Locked traffic accounting

| Counter | Expected | Observed | Result |
|---|---:|---:|---|
| Case retrieval operations | 24 | 24 | pass |
| Provider invocations | 24 | 24 | pass |
| Tavily requests | 24 | 24 | pass |
| Gemini API generation requests | 96 | 96 | pass |
| Retries | 0 | 0 | pass |
| Repair requests | 0 | 0 | pass |

There was no model fallback, selective retry, citation repair, cache replay or
second scored run. `gemma-4-26b-a4b-it` was neither called nor blocking.

## Pre-registered gates

All ten gates had to pass in the same run.

| Gate | Observed | Required | Result |
|---|---|---|---|
| Protocol integrity | 24 retrieval, 24 Tavily, 96 generation, 0 retry/repair | exact | pass |
| Selected and projected packet identity | 24/24 case pairs | 24/24 | pass |
| Tavily availability and prompt answer-key proxy | 24/24 available; 18/24 answer-bearing | 24/24; at least 20/24 | **fail** |
| Completion by model and arm | 24/24 for all four model-arm pairs | at least 23/24 for every pair | pass |
| Strict aggregate answer non-regression | 32/48 vs 32/48; paired net `0` | no regression | pass |
| Strict per-model answer non-regression | both models net `0` | no regression for either model | pass |
| Strict citation presence | 45/48, 93.75% | at least 95% | **fail** |
| Strict citation-presence lift | +25 points over legacy | at least +20 points | pass |
| Strict citation-ID integrity | 45/45, 100% | 100% | pass |
| Strict citation-support proxy | 33/48, 68.75% | at least 75% | **fail** |

The candidate passed **7/10** gates. Each failed gate is independently
blocking, so the optional API-backed quality profile cannot be promoted and
the sealed Phase 12 evaluation remains blocked.

## Answer and completion results

| Model | Legacy hits | Strict hits | Legacy completed | Strict completed | Paired net |
|---|---:|---:|---:|---:|---:|
| `gemma-4-31b-it` | 15/24 | 15/24 | 24/24 | 24/24 | `0` |
| `gemini-3.5-flash-lite` | 17/24 | 17/24 | 24/24 | 24/24 | `0` |
| **Total** | **32/48** | **32/48** | **48/48** | **48/48** | **`0`** |

The overall pairing contains one strict win, one legacy win, 31 shared hits
and 15 shared misses. Gemma 31B is an exact case-level tie. Gemini 3.5 Flash
Lite contributes both opposite wins, so its paired net is also zero. The
strict citation contract therefore caused no measured answer-key regression,
but this substring measure is only a disclosed proxy.

## Retrieval and citation result

Tavily returned usable evidence for 24/24 cases. The selected packet contained
the answer-key proxy in 19/24 cases, while the prompt-budget projection
contained it in 18/24. The latter missed the frozen 20/24 gate.

| Arm | Presence | Valid IDs among cited responses | Contract pass | Support proxy |
|---|---:|---:|---:|---:|
| `tavily_legacy` | 33/48, 68.75% | 32/33, 96.97% | 32/48, 66.67% | 24/48, 50% |
| `tavily_strict` | **45/48, 93.75%** | **45/45, 100%** | **45/48, 93.75%** | **33/48, 68.75%** |

The strict packet-local contract improved citation presence by 25 percentage
points and made every emitted identifier valid. It still missed the 95%
presence floor by one cited response and the 75% support-proxy floor by three
supported responses. The support measure is a normalized answer-substring
proxy, not semantic entailment or claim-by-claim citation completeness.

## Reliability and latency

Every model call completed, and the report records no generation error kind.

| Stage or arm | p50 latency | p95 latency |
|---|---:|---:|
| Tavily retrieval | 1.77 s | 3.00 s |
| `tavily_legacy` generation | 8.49 s | 20.58 s |
| `tavily_strict` generation | 11.55 s | 22.06 s |

## Decision

The immutable scored result is:

- `phase11_7_candidate_passed`: **false**;
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
Tavily bundle with a 0.8 Tavily reservation. The zero-key community profile is
unchanged. No Tavily-only promotion, Phase 12 run, external-agent benchmark,
merge, PyPI publication, GitHub Release, public alpha or “best open-source
search” claim is authorized.
