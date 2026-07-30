# Phase 11.8.3 factorial calibration — audited result

**Verdict: candidate failed (10/14 gates passed). Phase 11.9 protocol may not be frozen. Phase 12 remains sealed and blocked. Release decision: no-go.**

## Provenance and scope

- Scored run: [GitHub Actions 30555171945](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30555171945)
- Artifact: [8764644024](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30555171945/artifacts/8764644024), `phase11-8-3-factorial-calibration-08f8e2497dd0b100dfa0917ac95b2fd8feb96671`
- Frozen protocol: [benchmark protocol v18](../../docs/benchmark-protocol-v18.md), SHA-256 `d139c1fed0d9c2bcfe7cdc02f1cda510802296ababbf360b6381c4db5e55239d`
- Protocol implementation: [`c8aa76f183668d67cb37af8e8bcad23b1be99c59`](https://github.com/VynoDePal/EvidenceMesh/commit/c8aa76f183668d67cb37af8e8bcad23b1be99c59)
- Scored head: [`a15a472b19dfc455d4dd0b1adba5e4c3484bcff5`](https://github.com/VynoDePal/EvidenceMesh/commit/a15a472b19dfc455d4dd0b1adba5e4c3484bcff5)
- Observed suite: 24 Phase 11.7 cases; this is corrective calibration, not a fresh confirmation.
- Sole blocking model: `gemini-3.5-flash-lite`.
- Runtime: 2026-07-30 15:08:43–15:13:57 UTC on a GitHub-hosted Linux runner, Python 3.11.15.

The exact same-repository authorization label launched one live run and was removed after the run started. The workflow completed technically and produced the single pre-registered report. Technical workflow success is not a quality pass, and no selective rerun was made.

## Exact accounting

| Counter | Observed | Locked |
|---|---:|---:|
| Case retrieval operations | 24 | 24 |
| Tavily requests | 24 | 24 |
| Generation requests | 96 | 96 |
| Retries | 0 | 0 |
| Fallback requests | 0 | 0 |
| Repair requests | 0 | 0 |

One raw Tavily pool and one selected packet were reused across all four arms for each case. Raw-pool and selected-packet identity passed in 24/24 cases. Both prompt-contract pairs received their projection-identical packets in 24/24 cases, and the candidate projection passed deterministic replay and exact-budget checks in 24/24 cases.

## Retrieval and projection

| Projection | Availability | Answer proxy in selected evidence | Answer proxy in prompt evidence | Mean selected | Mean prompt |
|---|---:|---:|---:|---:|---:|
| Locked equal-cap | 24/24 (100.00%) | 19/24 (79.17%) | 17/24 (70.83%) | 16.083 | 16.083 |
| Candidate rank-weighted | 24/24 (100.00%) | 19/24 (79.17%) | 17/24 (70.83%) | 16.083 | 16.083 |

The candidate projection produced one paired prompt-proxy win and one paired loss against equal-cap, for net zero. It therefore missed both frozen requirements: at least 20/24 candidate hits and paired net gain of at least +2.

## Generation

| Arm | Completed | Native responses | Conditional schema valid | Answer-key proxy | Citation presence | Valid citation IDs | Citation-support proxy |
|---|---:|---:|---:|---:|---:|---:|---:|
| `equal_claims` | 19/24 | 19/24 | 19/19 (100.00%) | 9/24 (37.50%) | 16/19 (84.21%) | 16/16 (100.00%) | 11/19 (57.89%) |
| `candidate_claims` | 19/24 | 19/24 | 19/19 (100.00%) | 11/24 (45.83%) | 17/19 (89.47%) | 17/17 (100.00%) | 12/19 (63.16%) |
| `equal_direct` | 3/24 | 18/24 | 3/18 (16.67%) | 2/24 (8.33%) | 3/3 (100.00%) | 3/3 (100.00%) | 2/3 (66.67%) |
| `candidate_direct` | 2/24 | 18/24 | 2/18 (11.11%) | 2/24 (8.33%) | 2/2 (100.00%) | 2/2 (100.00%) | 2/2 (100.00%) |

Only 43/96 generations completed the full arm contract. There were 22 HTTP 429 responses: five in each claims arm and six in each direct arm. The remaining 74 requests returned native responses. Both claims arms accepted all 38 of their native responses, while the direct contract accepted only 5/36; the other 31 were scored as `response_schema_failure`. No failed request was retried, repaired or sent to a fallback.

The candidate claims arm improved the completion-conditioned paired answer proxy by +1 against equal claims across 18 eligible pairs. That limited signal did not transfer to the joint candidate: on all 24 attempts, `candidate_direct` recorded two answer-proxy hits against nine for `equal_claims`, a paired net of -7.

## Frozen gates

| Gate | Result | Observation |
|---|:---:|---|
| Locked inputs and exact traffic | PASS | 24 retrieval, 24 Tavily and 96 generation requests; zero retry, fallback or repair |
| Shared raw pool and selected packet | PASS | 24/24 raw pools and 24/24 selected packets matched |
| Projection identity, determinism and budget | PASS | 24/24 contract pairs matched; candidate replay and budget checks passed |
| Candidate prompt proxy absolute floor and positive gain | FAIL | Candidate 17/24, equal-cap 17/24, paired net 0; required at least 20/24 and +2 |
| Completion at least 23/24 per arm | FAIL | 19, 19, 3 and 2 completions |
| Conditional schema validity at least 95% per arm | FAIL | Claims arms 100%; direct arms 16.67% and 11.11% |
| Projection answer does not regress under claims | PASS | 18 both-completed pairs; paired net +1 |
| Projection answer does not regress under direct | PASS | One both-completed pair; paired net 0 |
| Direct contract answer does not regress on equal projection | PASS | Three both-completed pairs; paired net 0 |
| Direct contract answer does not regress on candidate projection | PASS | Two both-completed pairs; paired net +1 |
| Joint answer has positive gain over control | FAIL | Candidate direct 2/24 versus equal claims 9/24; all-attempt paired net -7, required +2 |
| Candidate-direct citation presence at least 95% | PASS | 2/2 completed outputs |
| Candidate-direct citation identifiers are 100% valid | PASS | 2/2 emitted identifiers |
| Candidate-direct support floor and no regression | PASS | 2/2 completed outputs; two eligible paired ties |

The last three citation gates passed only on two completed `candidate_direct` outputs. The completion and schema gates explicitly prevent those small denominators from being interpreted as a product-quality success.

## Privacy and artifact integrity

The public JSON contains no API keys, questions, reference answers, generated answers, raw structured responses, prompts, source titles or URLs, snippets, evidence, or Phase 12 reserved case identifiers. It retains answer hashes for reproducibility.

- Raw JSON: 264,204 bytes; SHA-256 `167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c`
- Artifact ZIP: 25,457 bytes; SHA-256 `9b7596c849bf2bfd89a270b11704289d1892b186432d41b9f058d8bfa7ba4154`
- ZIP inventory: exactly `phase11_8_3_factorial_2026-07-30.json`

The answer-key and citation-support measurements are disclosed substring and identifier proxies. They are not an official SimpleQA accuracy score and do not establish semantic entailment. Hosted-model and Tavily outputs are non-deterministic; the frozen single run is preserved without opportunistic repetition.

## Decision boundary

The candidate failed four blocking gates. Therefore:

- A fresh Phase 11.9 protocol may not be frozen or executed.
- The quality profile is not promoted; quality and community defaults remain unchanged.
- Phase 12 remains sealed, untouched and blocked.
- External competitor benchmarking, public alpha, merge, release and superiority claims remain unauthorized.
- Users continue to choose their provider, model and credentials.
- Pull request #1 remains a draft.
