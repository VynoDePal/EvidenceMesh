# Phase 11.8.1 offline causal diagnostic

## Status

**Diagnostic complete. Historical Phase 11.8 result: unchanged at fail (5/12).
Phase 11.9: not authorized. Phase 12: sealed and blocked. Release decision:
no-go.**

This diagnostic recomputes the committed, privacy-safe Phase 11.8 result. It
makes no Tavily or Gemini request, reads no secret, consumes no Phase 12 case
and changes no EvidenceMesh profile, provider, model or product behavior.

Source result:
[`phase11_8_recovery_2026-07-29.json`](phase11_8_recovery_2026-07-29.json),
SHA-256
`0bd05884c6e6d019f22d18113ef449d1cf1c8158ac0e598d899ee1a93c4b687a`.

Reproducible diagnostic:
[`phase11_8_1_offline_diagnostic_2026-07-30.json`](phase11_8_1_offline_diagnostic_2026-07-30.json),
SHA-256
`9032d9df7d71a3e9c4197577c3e33af315842cae18435d91a7f851e5489de6d8`.

## What failed, by causal layer

| Historical gate | Result | Primary diagnostic layer |
|---|---:|---|
| Protocol integrity | pass | experimental integrity |
| Shared raw pool and expanded packet identity | pass | experimental integrity |
| Expanded retrieval available and answer-bearing | fail | evidence projection quality |
| Expanded prompt coverage no regression | fail | evidence projection quality |
| Completion at least 23/24 per model/arm | fail | provider/model availability |
| Structured schema at least 23/24 per model | fail | availability plus schema contract |
| Structured answer no overall regression | fail | end-to-end answer quality, availability-confounded |
| Structured answer no per-model regression | fail | end-to-end answer quality, availability-confounded |
| Structured citation presence | pass | citation contract quality |
| Structured citation identifiers valid | pass | citation contract quality |
| Structured citation support at least 75% | fail | citation semantic proxy |
| Structured citation support no regression | pass | citation semantic proxy |

This table classifies the already-frozen gates; it does not rescore or replace
them.

## Finding 1: selection improved, projection lost three answer-bearing cases

Expanded selection contained the answer-key proxy in 21/24 cases. The expanded
prompt contained it in 18/24. The case-level transition is exact:

- 18 selected hits remained prompt hits;
- 3 selected hits became prompt misses;
- 0 selected misses became prompt hits;
- 3 cases missed at both stages.

Against the current projection, expanded projection produced one paired gain
and three paired losses, for net `-2` and 18/24 versus 20/24 prompt hits.
Retrieval availability was 24/24 and expanded selection itself cleared the
20/24 floor. The observed failure is therefore downstream of selection and
directly implicates projection.

The implementation gives every expanded block the same character cap after
subtracting all headers. A deterministic adversarial fixture now demonstrates
that an answer-bearing span can survive the current first-block allocation but
be cut by equal per-block truncation. This proves that the mechanism is
possible; it does not prove that exact content mechanism for the three live
cases because public artifacts intentionally omit evidence.

## Finding 2: provider/model availability dominated completion

The run completed 112/144 generations. Its 32 failures decompose exactly into:

| Failure class | Count | Attribution |
|---|---:|---|
| HTTP 503 | 22 | all `gemma-4-31b-it` |
| Wall timeout | 8 | both tested models |
| Native structured-schema rejection | 2 | `gemma-4-31b-it` |

Relative to the frozen 23/24 floor in each of six model/arm cells, the total
completion deficit was 26. Gemma 4 31B accounted for 23 deficit units; Gemini
3.5 Flash Lite accounted for 3.

This is a benchmark availability failure for the selected hosted model paths.
It is not evidence of an EvidenceMesh retrieval defect and does not justify
imposing a model default. EvidenceMesh users retain their own provider, model
and credential choices.

## Finding 3: the schema gate mixed availability with schema validity

The structured arm made 48 attempts:

- 38 returned a native model response;
- 36 passed the exact structured parser;
- 10 never reached schema validation;
- 2 returned a native response rejected by the schema parser.

The historical gate correctly remains 36/48 and fails. For diagnosis only,
schema validity conditional on receiving a native response was 36/38
(94.74%). Thus 10 of the 12 attempts counted as not schema-valid were
availability failures, while 2 were actual schema-contract failures.

## Finding 4: structured output traded answer proxy for citation discipline

The expanded strict and expanded structured arms used byte-identical projected
evidence in 24/24 cases. This makes their comparison the strongest available
contract isolation.

| Paired metric, structured vs expanded strict | All 48 attempts | 33 pairs where both completed |
|---|---:|---:|
| Answer-key proxy net | -4 | -3 |
| Citation-support proxy net | +3 | +4 |

Among the 33 pairs where both arms completed, structured output had zero answer
wins and three answer losses, while it had four citation-support wins and zero
support losses. Across all completed structured answers, citation presence was
35/36 (97.22%), identifier validity was 35/35 (100%) and support was 25/36
(69.44%).

The structured contract therefore improved citation form and paired support
but did not preserve answer-key coverage. Since the hosted generations are
non-deterministic and the public artifact contains hashes rather than answer
text, this is a controlled association rather than a complete semantic root
cause.

## Recommended future gate taxonomy

For a future, separately frozen protocol, report these layers independently:

1. experimental integrity: traffic, packet identity and privacy;
2. provider/model availability: native completion by model and arm;
3. response-contract validity: schema validity conditional on native
   completion;
4. completion-conditioned product quality: paired answer and citation metrics
   where both arms completed;
5. end-to-end user quality: every attempted request, including availability
   failures.

Both quality views matter. Completion-conditioned metrics must not hide an
unreliable endpoint, and end-to-end metrics must not mislabel an outage as a
retrieval, formatting or semantic defect. Thresholds must be pre-registered
before any new live run. This proposal is not retroactively applied to Phase
11.8.

## Ranked corrective hypotheses

1. Replace equal per-block truncation with a separately tested projection
   allocation that protects high-value spans while preserving source
   diversity.
2. Keep provider/model availability blocking when required, but classify it
   separately from retrieval and schema validity.
3. Test a revised structured answer contract that preserves direct answer
   wording without giving up exact citation identifiers.

The next valid action would be to freeze and review an offline Phase 11.8.2
candidate and its adversarial fixtures. No live call, quality-profile
promotion, Phase 11.9 run, Phase 12 access, merge, release, public alpha,
external competitor benchmark or superiority claim is authorized by this
diagnostic.

## Observability limit

The committed Phase 11.8 result excludes questions, reference answers, source
titles and URLs, evidence, prompts, generated answers, raw structured
responses, credentials and Phase 12 identifiers. Phase 11.8.1 preserves that
boundary. It can attribute failures to recorded stages and error classes, but
it cannot reconstruct the omitted content or claim an unobserved semantic root
cause.
