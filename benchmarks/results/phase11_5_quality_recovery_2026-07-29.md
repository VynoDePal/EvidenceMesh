# Phase 11.5: quality-recovery calibration

Date: **2026-07-29**

Status: **candidate failed; Phase 12 remains blocked**

Phase 11.5 is a disclosed corrective calibration on the 12 SimpleQA cases
already observed in Phase 10. It is not an untouched evaluation and cannot
support a competitive, release or superiority claim.

The frozen protocol is
[`benchmark-protocol-v13.md`](../../docs/benchmark-protocol-v13.md), SHA-256
`7fa9f6a0e40d2c7e18260de6468fa1b86770752f1b366985a2bedc5b070155b6`.
No threshold, model, case, provider, retry rule or decision boundary was
changed after the run.

## Audited run

| Field | Value |
|---|---|
| Source commit | `c496186b64a07db035f96898cb0c9ec45e573833` |
| GitHub run | [`30482256579`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30482256579) |
| Artifact ID | `8736707211` |
| Artifact name | `phase11-5-quality-recovery-c496186b64a07db035f96898cb0c9ec45e573833` |
| Artifact ZIP SHA-256 | `1fae8d46e4644511a94f3d983809cf5ca837a455f2f5693cc1efec913cad619d` |
| Raw JSON SHA-256 | `7c9716cd970c3f955934ccf218ecbd835b261f1cf885c2b749217452b90af29c` |
| Runtime | 18 minutes 25 seconds |
| Network region | GitHub-hosted runner |

The artifact contains exactly one 215,752-byte privacy-safe JSON report.
Questions, reference answers, source titles, URLs, snippets, evidence, prompts,
generated answer text and credentials are absent. Case IDs and answer hashes
are retained for paired auditing.

## Locked traffic accounting

| Counter | Expected | Observed | Result |
|---|---:|---:|---|
| Case retrieval operations | 12 | 12 | pass |
| Tavily requests | 12 | 12 | pass |
| Gemini generation requests | 108 | 108 | pass |
| Provider query calls | disclosed | 48 | observed |
| Retries | 0 | 0 | pass |
| Repair requests | 0 | 0 | pass |

There was no selective retry, model fallback, citation repair or second scored
run.

## Pre-registered gates

All eight gates had to pass in the same run.

| Gate | Observed | Required | Result |
|---|---|---|---|
| Protocol integrity | 12 retrieval, 12 Tavily, 108 generation, 0 retry/repair | exact | pass |
| Completion by model and arm | Gemma 26B: 10/12, 9/12, 10/12 | at least 11/12 each | **fail** |
| Candidate prompt evidence coverage | 10/12; Tavily direct 10/12 | gap at most 1/12 | pass |
| Candidate answers vs Tavily direct | 25/36 vs 28/36; paired net `-3` | no regression | **fail** |
| Candidate answers vs current 8/2 | 25/36 vs 25/36; paired net `0` | no regression | pass |
| Candidate citation presence | 32/34, 94.1% | at least 90% | pass |
| Candidate citation-ID integrity | 32/32, 100% | 100% | pass |
| Candidate citation-support proxy | 26/34, 76.5% | at least 70% | pass |

The candidate therefore passed **6/8** gates. The two failures are both
blocking.

## Answer and completion results

| Model | Tavily direct hits | Current 8/2 hits | Candidate hits | Candidate completions |
|---|---:|---:|---:|---:|
| `gemma-4-31b-it` | 10/12 | 9/12 | 9/12 | 12/12 |
| `gemma-4-26b-a4b-it` | 8/12 | 7/12 | 7/12 | 10/12 |
| `gemini-3.5-flash-lite` | 10/12 | 9/12 | 9/12 | 12/12 |
| **Total** | **28/36** | **25/36** | **25/36** | **34/36** |

Against Tavily direct, the paired candidate result was five baseline wins, two
candidate wins, 23 shared hits and six shared misses. The net result was
`-3`. Each model contributed a net `-1`.

The two candidate wins occurred where the corresponding Gemma 26B Tavily
request failed. Two baseline wins likewise occurred where the Gemma 26B
candidate request failed, so those transport failures cancel in the paired
net. The remaining three baseline wins are the same anonymized case across all
three models: Tavily direct covered the answer in all three completed outputs,
while both 8/2 variants did not. The answer-key substring was still present in
the projected candidate evidence for that case.

This is evidence of an evidence-salience or mixed-packet generation defect, not
a demonstrated retrieval-recall deficit. That diagnosis is an inference from
the locked proxy metrics; the private question and answer were not inspected.

## Citation recovery

| Arm | Presence | Valid IDs among cited responses | Support proxy |
|---|---:|---:|---:|
| Tavily direct | 19/34, 55.9% | 17/19, 89.5% | 16/34, 47.1% |
| Current 8/2 | 17/32, 53.1% | 17/17, 100% | 13/32, 40.6% |
| Candidate | **32/34, 94.1%** | **32/32, 100%** | **26/34, 76.5%** |

The strict packet-local citation contract fixed the measured citation defect.
It did not recover answer quality: the candidate and current 8/2 arm both
produced 25/36 answer-key hits.

The validator establishes exact `[S#]` syntax and membership only. The support
measure is a substring proxy, not semantic entailment or complete
claim-by-claim citation verification.

## Reliability and latency

Eight generation requests failed:

- Gemma 26B: three HTTP 500 responses, three HTTP 503 responses, and one
  response without answer text;
- Gemma 31B: one HTTP 503 response;
- Gemini Flash Lite: no failed request.

Gemma 26B therefore missed the completion gate on all three arms. Selective
retry was prohibited, so the failures remain part of the result.

| Arm | Completed | p50 latency | p95 latency |
|---|---:|---:|---:|
| Tavily direct | 34/36 | 9.32 s | 17.13 s |
| Current 8/2 | 32/36 | 8.34 s | 14.81 s |
| Candidate | 34/36 | 12.68 s | 30.73 s |

The generation loop was deliberately sequential and added at least two seconds
between request starts. This made accounting deterministic but produced an
18-minute run. The 120-second per-generation ceiling is also inconsistent
with a strict 60-minute whole-job guarantee in the pathological all-timeout
case; this run completed, but the protocol has that operational weakness.

## Retrieval observability

Tavily direct and both 8/2 quality arms retained the answer-key substring in
10/12 projected packets. The retrieval-only community arm reached 9/12 with
12/12 availability and no Tavily result.

SearXNG reported four `upstream_unavailable` observations and then five
`circuit_open` observations. The final EvidenceMesh health state was degraded,
although DDGS and Wikipedia allowed every shared retrieval operation to
complete. Community retrieval was pre-registered as non-blocking and did not
alter the candidate decision.

## Decision

The immutable result is:

- `phase11_5_candidate_passed`: **false**;
- `phase12_untouched_evaluation_allowed`: **false**;
- `phase12_executed`: **false**;
- `public_alpha_allowed`: **false**;
- `merge_allowed`: **false**;
- `release_ready`: **false**;
- `release_decision`: **no-go**;
- `superiority_claim_allowed`: **false**.

The PR remains draft. No merge, PyPI publication, GitHub Release, public alpha,
Phase 12 run, external-agent benchmark or “best open-source search” claim is
authorized by this result.
