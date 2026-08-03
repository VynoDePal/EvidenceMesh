# EvidenceMesh Phase 11.8.2 offline design result

Date: 2026-07-30  
Protocol: `docs/benchmark-protocol-v17.md`  
Execution boundary: synthetic, deterministic and fully offline

## Result

The offline engineering candidate passed all 12 authored gates.

| Measure | Baseline | Candidate |
|---|---:|---:|
| Authored projection cases | 12 | 12 |
| Synthetic sentinels retained | 1 | 12 |
| Paired wins | — | 11 |
| Paired regressions | — | 0 |
| Exact rendered-budget passes | — | 12/12 |
| Deterministic three-replay passes | — | 12/12 |
| Metadata-preservation passes | — | 12/12 |

The minimal direct-answer parser accepted and rendered all 4 valid fixtures
and rejected all 11 invalid fixtures. It accepts exactly `answer` and
`citation_ids`, requires packet-local bare citation identifiers for supported
answers, and permits the exact insufficient-evidence response only with an
empty citation list.

## Candidate

The projection candidate is
`rank_weighted_query_window_head_tail_v1`. It receives only the question,
already-selected evidence and explicit character bounds. It never receives a
reference answer, expected answer or fixture sentinel.

It preserves provider-aware rank order, accounts for headers and separators,
allocates deterministic rank-weighted excerpt capacity, and retains head,
question-linked and tail windows when a block must be truncated.

## Traffic and isolation

| Boundary | Observed |
|---|---:|
| Network requests | 0 |
| Provider calls | 0 |
| Model calls | 0 |
| Tavily requests | 0 |
| Gemini requests | 0 |
| Retries, fallbacks and repairs | 0 |

No provider credential was required or exposed. Phase 11.7 content was not
included in the output, and Phase 12 was not accessed.

## Interpretation

This is a positive engineering result, not a real-case quality result. The
fixtures were deliberately authored after the Phase 11.8 failure to exercise
known truncation modes. Therefore:

- no improvement on the 24 observed Phase 11.8 cases has been proven;
- hosted-model adherence to the new response shape remains unmeasured;
- no live Phase 11.8.3 run is authorized;
- Phase 11.9 and Phase 12 remain unauthorized;
- product profiles and user model/provider choice remain unchanged;
- merge, release and superiority claims remain blocked.

The historical Phase 11.8 result remains fail at 5/12 and the release decision
remains **no-go**.

## Reproducibility

- Protocol SHA-256:
  `67a7212f68eeb5ed1b81dd98fabeb2b80d1faa2a88d379c83d7fc20bcd839652`
- Fixture SHA-256:
  `16f5eb38eec4c8669fb6dac4eeb64992df5b81a46b6c02325a559d3da4f621ab`
- Candidate SHA-256:
  `0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e`
- Locked Phase 11.8 source SHA-256:
  `0bd05884c6e6d019f22d18113ef449d1cf1c8158ac0e598d899ee1a93c4b687a`
- Locked Phase 11.8.1 source SHA-256:
  `9032d9df7d71a3e9c4197577c3e33af315842cae18435d91a7f851e5489de6d8`
- JSON result SHA-256:
  `91e2ab81e95ca34ba8766f552db60018e44783fe9792857d30d2d9b1195c9bbd`

The offline workflow recomputes the JSON result from the locked sources,
diffs it byte-for-byte against the committed artifact and runs the adversarial
test suite without binding any provider secret.
