# EvidenceMesh benchmark protocol v18

## Phase 11.8.3 — observed-case factorial causal calibration

Status: frozen protocol candidate. This document and its offline validation do
not authorize live traffic. A separate explicit authorization is required
after the protocol commit is reviewed.

## 1. Purpose and evidence boundary

Phase 11.8 failed at 5/12. Its expanded selection contained the transparent
answer-key proxy in 21/24 cases, but equal-cap prompt projection retained it in
18/24. Its multi-claim structured contract improved citation behavior while
regressing the answer-key proxy.

Phase 11.8.2 then produced two engineering candidates:

1. deterministic rank-weighted head, question-window and tail projection;
2. a closed direct-answer JSON contract with packet-local citations.

The Phase 11.8.2 fixtures were deliberately authored after the failure. Their
12/12 pass cannot establish real-case quality. Phase 11.8.3 therefore measures
both candidates on the already-observed 24 Phase 11.7 cases.

This is corrective calibration, not a fresh confirmation. A pass may authorize
only a separately frozen Phase 11.9 confirmation. It cannot change a product
profile or open Phase 12.

## 2. Locked inputs

- Phase 11.7 manifest:
  `benchmarks/data/phase11_7_fresh_confirmation_v1.json`
- Manifest SHA-256:
  `da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e`
- Phase 12 sealed manifest:
  `benchmarks/data/phase12_untouched_reserve_v1.json`
- Reserve SHA-256:
  `472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee`
- Phase 11.8 result:
  `benchmarks/results/phase11_8_recovery_2026-07-29.json`
- Phase 11.8 result SHA-256:
  `0bd05884c6e6d019f22d18113ef449d1cf1c8158ac0e598d899ee1a93c4b687a`
- Phase 11.8.2 result:
  `benchmarks/results/phase11_8_2_offline_design_2026-07-30.json`
- Phase 11.8.2 result SHA-256:
  `91e2ab81e95ca34ba8766f552db60018e44783fe9792857d30d2d9b1195c9bbd`
- Candidate implementation:
  `benchmarks/phase11_8_2_candidate.py`
- Candidate SHA-256:
  `0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e`

The Phase 11.8 no-go and Phase 12 seal are immutable.

## 3. Dataset and retrieval

The exact 24 Phase 11.7 selectors are materialized from the checksum-pinned
SimpleQA CSV. Questions and reference answers may exist only in runner memory.
They are never written to the public result.

Each case performs exactly one Tavily retrieval:

- provider: Tavily only;
- maximum raw results: 20;
- selected results: at most 20;
- maximum results per domain: 3;
- cache: disabled;
- retries and fallback: forbidden.

The same selected evidence packet feeds all four generation arms. Provider
traffic is never repeated per arm.

## 4. Factorial arms

The experiment crosses two projection levels with two response-contract
levels:

| Arm | Projection | Response contract |
|---|---|---|
| `equal_claims` | locked Phase 11.8 equal-cap | locked Phase 11.8 claims JSON |
| `candidate_claims` | Phase 11.8.2 candidate | locked Phase 11.8 claims JSON |
| `equal_direct` | locked Phase 11.8 equal-cap | Phase 11.8.2 direct-answer JSON |
| `candidate_direct` | Phase 11.8.2 candidate | Phase 11.8.2 direct-answer JSON |

`equal_claims` is the control and must reproduce the Phase 11.8 expanded
structured prompt construction for an identical selected packet.

This design estimates:

- projection effect under the claims contract;
- projection effect under the direct contract;
- contract effect under equal-cap projection;
- contract effect under candidate projection;
- the joint effect against the control.

## 5. Projection lock

- total rendered evidence budget: 12,000 characters;
- maximum excerpt per block: 1,500 characters;
- candidate minimum excerpt target: 192 characters;
- candidate replays per case: 3.

The equal-cap arm intentionally reproduces the historical implementation. The
candidate must include headers and separators in its exact budget, preserve
metadata, reject duplicate citation IDs and receive only the question and
selected evidence. Expected answers, reference answers and scoring sentinels
are forbidden projector inputs.

The two contracts using the same projection must receive byte-identical
projected evidence packets.

## 6. Response contracts

The claims contract is the exact Phase 11.8 closed `claims` object. The direct
contract is the exact Phase 11.8.2 closed object:

```json
{"answer":"Shortest exact answer supported by evidence.","citation_ids":["S1"]}
```

Both parsers:

- require raw JSON with no code-fence normalization;
- reject unknown keys and malformed citation identifiers;
- allow no retry, repair, permissive fallback or second model request.

The direct parser rejects identifiers outside the projected packet. The locked
claims parser preserves Phase 11.8 behavior: packet membership is enforced by
the deterministic citation audit and an unknown identifier cannot pass the
citation contract.

## 7. Model choice

The sole blocking calibration model is:

- `gemini-3.5-flash-lite`

Gemma 4 31B is excluded from this causal calibration because Phase 11.8
observed 22 HTTP 503 responses from that model. Including it would reintroduce
the availability confound that Phase 11.8.1 separated from product quality.

This choice does not make Gemini a product default and does not restrict which
model users may configure. Cross-model robustness remains unproven and belongs
in a later, separately frozen confirmation.

## 8. Exact traffic ceiling

- case retrieval operations: 24;
- Tavily requests: exactly 24;
- generation arms: 4;
- blocking models: 1;
- generation requests: exactly 96;
- retries: 0;
- fallback requests: 0;
- repair requests: 0.

Generation uses at most 2,048 output tokens, a 60-second wall limit, a
20-second request timeout and a two-second request pacer.

## 9. Metrics

Metrics remain transparent proxies:

- answer-key coverage: normalized reference-answer substring in generated text;
- prompt coverage: normalized reference-answer substring in projected evidence;
- citation presence: at least one exact packet-local citation token;
- citation identifier integrity: exact syntax and packet membership;
- citation support proxy: at least one cited block contains the answer-key
  substring;
- schema validity: exact local parser acceptance.

No official SimpleQA grader or semantic entailment judge is used. Results must
report both all-attempt outcomes and completion-conditioned paired outcomes.

## 10. Fourteen blocking calibration gates

All gates must pass:

1. locked input hashes, exact traffic and zero retry/fallback/repair match;
2. all four arms share the raw pool and selected packet in 24/24 cases;
3. equal-contract packets match, candidate-contract packets match, candidate
   projection is deterministic and its rendered budget passes in 24/24 cases;
4. candidate prompt coverage is at least 20/24, no lower than equal-cap and has
   an all-case paired net gain of at least +2;
5. every arm completes at least 23/24 generation requests;
6. conditional schema validity is at least 95% for every arm among native
   responses;
7. `candidate_direct` answer coverage is no lower than `equal_claims`, has an
   all-attempt paired net gain of at least +2 and no negative
   completion-conditioned paired net;
8. candidate projection does not regress answer coverage under claims on
   completion-conditioned pairs;
9. candidate projection does not regress answer coverage under direct answers
   on completion-conditioned pairs;
10. the direct contract does not regress answer coverage on equal-cap
    completion-conditioned pairs;
11. the direct contract does not regress answer coverage on candidate
    completion-conditioned pairs;
12. `candidate_direct` citation presence is at least 95%;
13. every emitted `candidate_direct` citation identifier is valid;
14. `candidate_direct` citation support is at least 75% and does not regress
    against `equal_claims` on completion-conditioned pairs.

The +2 gates are calibration signals, not statistical significance claims.

## 11. Authorization and workflow boundary

Ordinary pull-request open, reopen and synchronize events run offline lock and
test validation only. They receive no provider secret.

A live job requires one of:

1. a manual dispatch with `authorize_live_run=true`; or
2. a same-repository PR `labeled` event adding exactly
   `phase11.8.3-live-authorized`.

Publishing this protocol must not add that label or dispatch the live job.
Live traffic requires a separate explicit user instruction after review.

The first result is single-shot. The workflow refuses to overwrite an existing
Phase 11.8.3 JSON or Markdown result. Selective or opportunistic reruns are
forbidden.

## 12. Decision semantics

A 14/14 pass means only that the observed-case calibration produced a positive
causal signal and may justify freezing Phase 11.9 on fresh cases.

Regardless of result:

- quality and community profiles remain unchanged;
- users keep provider, model and credential choice;
- Phase 12 remains sealed and unexecuted;
- merge, release, public-alpha and superiority claims remain blocked;
- external competitor benchmarking remains unauthorized.

## 13. Public output and privacy

The public report may contain case IDs, hashes, counts, Boolean proxies,
latencies, bounded failure classes, aggregate usage and gate decisions.

It must not contain questions, reference answers, source titles, URLs,
snippets, evidence, prompts, generated text, raw JSON responses, credentials
or Phase 12 reserved identifiers.
