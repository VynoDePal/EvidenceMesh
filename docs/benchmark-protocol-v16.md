# EvidenceMesh Phase 11.8 corrective recovery protocol

Status: frozen before the first scored Phase 11.8 provider or model request.

## Purpose and decision boundary

Phase 11.8 is a corrective calibration on the 24 SimpleQA cases already
observed in Phase 11.7. It diagnoses and tests the two remaining quality
defects without consuming another fresh case:

- projected Tavily evidence contained the answer-key proxy in 18/24 cases,
  below the frozen 20/24 floor;
- the strict arm reached 45/48 citation presence and 33/48 citation-support
  proxy, below the frozen 95% and 75% floors.

Phase 11.7 completed all 96 generation requests and strict answer-key coverage
tied the legacy arm at 32/48. Phase 11.8 therefore keeps the exact two-model
matrix and changes only retrieval depth, deterministic evidence projection and
the response contract.

This phase is calibration, not confirmation. A pass may authorize a separately
frozen Phase 11.9 confirmation on new cases. It cannot promote a provider
default, authorize or inspect Phase 12, establish competitive superiority,
merge the pull request or publish a release.

## Locked observed suite and sealed reserve

Phase 11.8 reuses exactly the Phase 11.7 manifest:

- path:
  `benchmarks/data/phase11_7_fresh_confirmation_v1.json`;
- SHA-256:
  `da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e`;
- case count: exactly 24;
- status: observed calibration data.

The immutable Phase 11.7 result is:

- path:
  `benchmarks/results/phase11_7_fresh_confirmation_2026-07-29.json`;
- SHA-256:
  `783fdaa60b351f975632b9cf23b57bab8766e39a8d81fabdead590962deea6de`.

The Phase 12 reserve remains:

- path:
  `benchmarks/data/phase12_untouched_reserve_v1.json`;
- SHA-256:
  `472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee`;
- case count: exactly 96.

The reserve contains opaque row positions and stable case identifiers only. It
does not contain questions, reference answers, topics or answer-type
distributions. The Phase 11.8 loader may materialize only the 24 Phase 11.7
selectors. It must not select, score, prompt, log or return any Phase 12 row.
Downloading and checksum-verifying the source CSV does not authorize Phase 12.

Changing the observed manifest, the Phase 11.7 result or the reserve manifest
invalidates this protocol.

## Locked dataset and one-request retrieval

- Dataset: OpenAI SimpleQA CSV.
- Dataset SHA-256:
  `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032`.
- Provider: Tavily only.
- Search profile: web.
- One provider request per case.
- Requested provider results: at most 20.
- Domain cap: at most 3 selected results per registrable domain.
- Cache: disabled.

Each case creates one raw Tavily pool. That same pool is replayed
deterministically into:

1. a current packet selected at limit 10;
2. an expanded packet selected at limit 20.

No provider request is repeated for a generation arm. The report retains only
one-way packet hashes and aggregate diagnostics, never source content.

The product configuration is unchanged before and after this calibration. The
zero-key `community` profile and existing mixed `quality` profile remain the
defaults regardless of the result.

## Locked causal arms

The exact generation-arm order is:

1. `current_strict`;
2. `expanded_strict`;
3. `expanded_structured`.

### Current strict

`current_strict` applies the Phase 11.7 strict packet-local citation prompt to
the current limit-10 selected packet and the existing sequential
12,000-character projection.

### Expanded strict

`expanded_strict` applies the same strict prompt to the limit-20 selected
packet. Its deterministic balanced projection:

- preserves ranking order;
- retains every non-empty selected block whose headers fit;
- allocates the remaining 12,000-character budget evenly;
- caps each block excerpt at 1,500 characters;
- never reads a reference answer.

The comparison between `current_strict` and `expanded_strict` isolates
retrieval selection and projection.

### Expanded structured

`expanded_structured` receives byte-identical selected and projected evidence
to `expanded_strict`. It differs only in the response contract.

The model must return one raw JSON object with this exact shape:

```json
{
  "claims": [
    {
      "text": "Concise factual claim.",
      "citation_ids": ["S1"]
    }
  ]
}
```

The parser requires:

- exactly one top-level `claims` field;
- between one and eight claim objects;
- exactly `text` and `citation_ids` in each claim;
- non-empty claim text without embedded `[S#]` tokens;
- a list of unique string identifiers in each claim;
- at least one identifier for a factual claim;
- an empty identifier list only for the exact sentence
  `Insufficient evidence.`.

The parser renders valid claims deterministically as claim text followed by
their `[S#]` identifiers. It never invents, removes or changes an identifier.
Invalid JSON or schema is a scored `response_schema_failure`. There is no
repair request, permissive code-fence stripping or fallback to free-form text.
Identifier membership and citation support are then audited by the same
deterministic EvidenceMesh citation code used in Phase 11.7.

The comparison between `expanded_strict` and `expanded_structured` isolates the
response contract.

## Locked model matrix

The exact blocking model order is:

1. `gemma-4-31b-it`;
2. `gemini-3.5-flash-lite`.

Both models are blocking in every per-model and aggregate gate.
`gemma-4-26b-a4b-it` is not called and is not blocking. This benchmark choice
does not restrict EvidenceMesh users: they choose their own provider bundle,
generation client, model and credentials.

Each of the 24 cases is generated once for each of the three arms and each of
the two blocking models. Phase 11.8 therefore makes exactly 144 native Gemini
API generation requests.

## Locked traffic and timeout budget

- 24 case-retrieval operations;
- exactly 24 Tavily requests;
- exactly 144 model requests;
- zero retries;
- zero fallback requests;
- zero citation-repair requests;
- zero cache reads or writes for scored retrieval;
- 0.5 seconds between Tavily operations;
- 2.0 seconds between model operations;
- 20 seconds provider request timeout;
- 30 seconds whole retrieval-operation ceiling;
- 60 seconds whole generation-request ceiling;
- 180 minutes whole GitHub Actions job ceiling;
- 2,048 maximum output tokens per generation.

A failed, timed-out or schema-invalid call remains failed and cannot be
selectively rerun. Arm and model order rotate deterministically across cases to
reduce ordering bias without changing the request count.

The workflow runs live traffic only after one of two explicit authorization
events:

1. a manual `workflow_dispatch` with `authorize_live_run=true`, once the
   workflow exists on the default branch; or
2. while the workflow exists only in the draft PR, the deliberate addition of
   the exact `phase11.8-live-authorized` label to that same-repository PR.

The live job accepts the label path only for a `pull_request` event whose
action is exactly `labeled`, whose new label has the exact locked name and
whose head repository equals the base repository. PR open, reopen and
synchronize events run only lock validation. They do not receive provider or
model credentials and do not make a scored request. Leaving the label attached
does not authorize later synchronize events; removing and re-adding it would
be a new explicit authorization event.

## Scoring

The disclosed proxies are:

- retrieval availability;
- normalized reference-answer substring in selected evidence;
- normalized reference-answer substring in projected evidence;
- normalized reference-answer substring in a generated answer;
- exact citation presence;
- citation identifier integrity;
- citation support proxy: at least one cited projected block contains a
  normalized reference answer;
- strict JSON/schema validity for the structured arm.

Paired binary comparisons count candidate wins, baseline wins, shared hits,
shared misses and net gain on the same case-model pairs. These measures are
calibration proxies, not the official SimpleQA judge, a semantic citation
judge or proof that every claim is supported.

## Pre-registered gates

All twelve gates must pass in one authorized run:

1. protocol accounting is exact: 24 retrieval operations, 24 Tavily requests
   and 144 model requests, with no retry or repair;
2. all three arms share the same raw-pool hash per case, and
   `expanded_strict` and `expanded_structured` have identical selected and
   projected packets in all 24 cases;
3. expanded retrieval is available in 24/24 cases and expanded projected
   evidence contains a reference-answer key in at least 20/24 cases;
4. expanded projected answer-key coverage does not regress from current
   projection and its paired case-level net gain is non-negative;
5. every model-arm pair completes at least 23/24 requests;
6. structured JSON/schema validity is at least 23/24 for each model;
7. structured aggregate answer-key hits do not regress from `current_strict`
   and paired aggregate net gain is non-negative;
8. structured answer-key hits and paired net gain do not regress for either
   model;
9. structured citation presence is at least 95% and does not regress from
   `expanded_strict`;
10. 100% of citations emitted by completed structured outputs use valid
    projected-packet identifiers;
11. structured citation support proxy is at least 75%;
12. structured citation-support hits do not regress from `expanded_strict`
    and their paired net gain is non-negative.

Missing denominators do not pass a rate gate.

## Decision rule

If all twelve gates pass, a separate result commit may mark a new, disjoint
Phase 11.9 confirmation as eligible for protocol design and later explicit
authorization.

Phase 11.8 cannot:

- promote the `quality` profile;
- change `QUALITY_PROVIDERS` or its 0.8 Tavily reservation;
- authorize, execute or inspect Phase 12;
- authorize an external-agent benchmark;
- authorize merge, publication, public alpha or a superiority claim.

If any gate fails, Phase 11.9 remains blocked until another separately
authorized corrective protocol is frozen. The Phase 12 reserve remains sealed
in either outcome.

## Privacy and publication limits

The uploaded report may contain Phase 11.7 case identifiers, counts, rates,
latency, usage metadata, categorical failures and SHA-256 values. It must not
contain questions, reference answers, generated answers, raw structured
responses, prompts, source titles, URLs, snippets, evidence text, Phase 12
identifiers or API keys.

The pull request remains draft. No result from this calibration supports a
claim that EvidenceMesh is the best open-source search or deep-research tool.
