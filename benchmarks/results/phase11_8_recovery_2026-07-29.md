# Phase 11.8 corrective recovery — audited result

**Verdict: candidate failed (5/12 gates passed). Phase 11.9 is not authorized. Phase 12 remains sealed and blocked. Release decision: no-go.**

## Provenance and scope

- Scored run: [GitHub Actions 30521453796](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30521453796)
- Artifact: [8751729336](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30521453796/artifacts/8751729336), `phase11-8-corrective-recovery-972a9fd43422b95515fb5fcfd30adb5b6052dcd1`
- Frozen protocol: [benchmark protocol v16](../../docs/benchmark-protocol-v16.md), SHA-256 `55b18c9a0e91f645e630dbb0d340482c8821339ecfff97b7f81fc11b207df5ea`
- Protocol and run commit: [`b48fcfd6078270dac74ecb0c0c087a6c16066008`](https://github.com/VynoDePal/EvidenceMesh/commit/b48fcfd6078270dac74ecb0c0c087a6c16066008)
- Observed suite: 24 Phase 11.7 cases; this is corrective calibration, not a fresh confirmation.
- Runtime: 2026-07-30 07:01:20–07:36:33 UTC on a GitHub-hosted Linux runner, Python 3.11.15.

The live workflow completed technically and produced the single pre-registered report. Technical workflow success is not a quality pass.

## Exact accounting

| Counter | Observed | Locked |
|---|---:|---:|
| Case retrieval operations | 24 | 24 |
| Tavily requests | 24 | 24 |
| Generation requests | 144 | 144 |
| Retries | 0 | 0 |
| Fallback requests | 0 | 0 |
| Repair requests | 0 | 0 |

One raw Tavily pool was reused across the three arms for each case. Raw-pool identity passed in 24/24 cases, and the two expanded arms had byte-identical selected and prompt packets in 24/24 cases.

## Retrieval

| Arm | Availability | Answer proxy in selected evidence | Answer proxy in prompt evidence | Mean selected | Mean prompt |
|---|---:|---:|---:|---:|---:|
| `current_strict` | 24/24 (100.00%) | 20/24 (83.33%) | 20/24 (83.33%) | 10.000 | 9.542 |
| `expanded_strict` | 24/24 (100.00%) | 21/24 (87.50%) | 18/24 (75.00%) | 16.167 | 16.167 |
| `expanded_structured` | 24/24 (100.00%) | 21/24 (87.50%) | 18/24 (75.00%) | 16.167 | 16.167 |

Expansion raised selected-evidence proxy coverage from 20/24 to 21/24, but projection reduced expanded prompt coverage to 18/24. Against `current_strict`, the paired prompt-coverage net was -2 (one expanded win, three current wins).

## Generation

| Arm | Completed | Answer-key proxy | Citation presence | Valid citation IDs | Citation-support proxy | Structured schema |
|---|---:|---:|---:|---:|---:|---:|
| `current_strict` | 37/48 (77.08%) | 30/48 (62.50%) | 34/37 (91.89%) | 33/34 (97.06%) | 27/37 (72.97%) | n/a |
| `expanded_strict` | 39/48 (81.25%) | 27/48 (56.25%) | 36/39 (92.31%) | 35/36 (97.22%) | 22/39 (56.41%) | n/a |
| `expanded_structured` | 36/48 (75.00%) | 23/48 (47.92%) | 35/36 (97.22%) | 35/35 (100.00%) | 25/36 (69.44%) | 36/48 (75.00%) |

| Model | Current strict completed | Expanded strict completed | Expanded structured completed | Structured schema valid |
|---|---:|---:|---:|---:|
| `gemma-4-31b-it` | 14/24 | 17/24 | 15/24 | 15/24 |
| `gemini-3.5-flash-lite` | 23/24 | 22/24 | 21/24 | 21/24 |

Across all arms, 112/144 generations completed. Failures were 22 HTTP 503 responses, all from `gemma-4-31b-it`, eight wall-timeouts, and two structured-schema failures. No failed request was selectively retried.

## Frozen gates

| Gate | Result | Observation |
|---|:---:|---|
| Protocol integrity | PASS | 24 retrieval, 24 Tavily and 144 generation requests; zero retry, fallback or repair |
| Shared raw pool and expanded packet identity | PASS | 24/24 raw pools and 24/24 expanded packet pairs matched |
| Expanded retrieval available and answer-bearing | FAIL | 24/24 available, but prompt answer proxy was 18/24 versus required 20/24 |
| Expanded prompt answer coverage does not regress | FAIL | Current 20/24 versus expanded 18/24; paired net -2 |
| Completion at least 23/24 per model and arm | FAIL | Gemma: 14/24, 17/24, 15/24; Gemini: 23/24, 22/24, 21/24 |
| Structured schema valid at least 23/24 per model | FAIL | Gemma 15/24; Gemini 21/24 |
| Structured answer has no overall regression | FAIL | Current 30/48 versus structured 23/48; paired net -7 |
| Structured answer has no regression for either model | FAIL | Gemma 12→10 (net -2); Gemini 18→13 (net -5) |
| Structured citation presence at least 95% and no regression | PASS | Structured 35/36 (97.22%) versus expanded strict 36/39 (92.31%) |
| Structured citation IDs are 100% valid | PASS | 35/35 |
| Structured citation-support proxy at least 75% | FAIL | 25/36 (69.44%) |
| Structured citation-support proxy does not regress | PASS | Expanded strict 22 hits versus structured 25; paired net +3 |

The structured contract materially improved citation formatting and identifier validity, and its support proxy improved over the byte-identical expanded strict arm. Those gains did not offset the absolute support shortfall, answer-key regression, schema shortfall, or model availability failures.

## Privacy and artifact integrity

The public JSON contains no API keys, questions, reference answers, generated answers, raw structured responses, prompts, source titles or URLs, snippets, evidence, or Phase 12 reserved case identifiers. It retains answer hashes for reproducibility.

- Raw JSON: 274,463 bytes; SHA-256 `0bd05884c6e6d019f22d18113ef449d1cf1c8158ac0e598d899ee1a93c4b687a`
- Artifact ZIP: 28,508 bytes; SHA-256 `c6228576f1b52ab007e3041e46abcec9dc84632e3ec2a68aba72c071d070fe44`
- ZIP inventory: exactly `phase11_8_recovery_2026-07-29.json`

The answer-key and citation-support measurements are disclosed substring/identifier proxies. They are not an official SimpleQA accuracy score and do not establish semantic entailment.

## Decision boundary

The candidate failed seven blocking gates. Therefore:

- Phase 11.9 fresh confirmation is not authorized.
- The quality profile is not promoted; quality and community defaults remain unchanged.
- Phase 12 remains sealed, untouched and blocked.
- External competitor benchmarking, public alpha, merge, release and superiority claims remain unauthorized.
- Users continue to choose their provider, model and credentials.
- Pull request #1 remains a draft.
