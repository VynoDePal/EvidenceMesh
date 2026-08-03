# EvidenceMesh Phase 11.7 fresh Tavily confirmation protocol

Status: frozen before the first scored Phase 11.7 provider or model request.

## Purpose and decision boundary

Phase 11.7 is a fresh, pre-registered confirmation calibration. It tests
whether the Phase 11.6 Tavily-only strict-citation result generalizes to 24
previously unobserved SimpleQA cases while removing the unreliable
`gemma-4-26b-a4b-it` endpoint from the blocking matrix.

The only scored comparison is:

1. `tavily_legacy`: Tavily evidence with the Phase 10 legacy answer prompt;
2. `tavily_strict`: the exact same Tavily evidence with the Phase 11.5 strict
   packet-local citation prompt.

For every case, both arms receive byte-identical selected evidence and
byte-identical projected evidence. They differ only in their system and user
instructions. Retrieval is performed once per case and is never repeated per
generation arm.

This phase can confirm or reject a Tavily-only `quality` default. It cannot
establish competitive superiority, authorize merge or publication, or replace
the separately reserved untouched Phase 12 evaluation.

## Locked fresh split and sealed reserve

The split was generated once before any Phase 11.7 live request with
`benchmarks/phase11_7_dataset.py`. Selection sorts eligible stable case IDs by
`SHA-256(namespace + NUL + case_id)`. All opaque 16-hex SimpleQA identifiers
found in the following frozen prior inputs are excluded:

- the Phase 2 pilot result;
- the Phase 3 and Phase 4 results;
- the Phase 10 manifest and result;
- the Phase 11.5 and Phase 11.6 results.

The exclusion union contains 212 identifiers. The immutable SimpleQA dataset
contains 4,326 rows, leaving 4,114 eligible fresh rows before Phase 11.7
selection.

Phase 11.7 manifest:

- path:
  `benchmarks/data/phase11_7_fresh_confirmation_v1.json`;
- SHA-256:
  `da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e`;
- namespace:
  `EvidenceMesh/phase11.7/fresh-confirmation/v1`;
- case count: exactly 24.

Phase 12 reserve:

- path:
  `benchmarks/data/phase12_untouched_reserve_v1.json`;
- SHA-256:
  `472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee`;
- namespace:
  `EvidenceMesh/phase12/untouched-reserve/v1`;
- case count: exactly 96.

The reserve commits opaque row positions and stable case identifiers only. It
does not commit questions, reference answers, topics or answer types. The
Phase 11.7 loader must materialize only the 24 Phase 11.7 selectors; it must
not select, score, prompt, log or return any reserved Phase 12 row. Downloading
and checksum-verifying the immutable source CSV does not authorize Phase 12.

The two manifests must be disjoint by both row position and case identifier.
Changing either manifest invalidates this protocol.

## Locked dataset and retrieval

- Dataset: OpenAI SimpleQA CSV.
- Dataset SHA-256:
  `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032`.
- Provider: Tavily only.
- Search profile: web.
- Results per case: at most 10 after ranking and at most 3 per domain.
- Prompt evidence budget: 12,000 characters.
- Cache: disabled.

The product configuration is not changed before the scored run. The
zero-key `community` profile and the existing mixed `quality` profile remain
unchanged until a separate result commit proves that every gate passed.

## Locked model matrix

The exact blocking model order is:

1. `gemma-4-31b-it`;
2. `gemini-3.5-flash-lite`.

Both models are blocking in every per-model and aggregate gate.
`gemma-4-26b-a4b-it` is not called and is not blocking. This is a benchmark
matrix decision, not a product restriction: EvidenceMesh users remain free to
select any model supported by their own generation client and credentials.

Each of the 24 cases is generated once for each prompt arm and each blocking
model. Phase 11.7 therefore makes exactly 96 native Gemini API generation
requests.

## Locked traffic and timeout budget

- 24 case-retrieval operations;
- exactly 24 Tavily requests, one per case;
- exactly 96 model requests;
- zero retries;
- zero fallback requests;
- zero citation-repair requests;
- zero cache reads or writes for scored retrieval;
- 0.5 seconds between Tavily operations;
- 2.0 seconds between model operations;
- 20 seconds provider request timeout;
- 30 seconds whole retrieval-operation ceiling;
- 60 seconds whole generation-request ceiling;
- 120 minutes whole GitHub Actions job ceiling;
- 2,048 maximum output tokens per generation.

A failed or timed-out call remains failed and cannot be selectively rerun.
The arm and model order rotate deterministically across cases to reduce
ordering bias without changing the request count.

## Evidence and prompt isolation

One Tavily raw-result pool is collected for each case. Normal EvidenceMesh
ranking, canonicalization and domain caps select the packet. The same
sequential 12,000-character Phase 10 projection is applied to both prompt
arms.

The report must prove, for all 24 cases, that:

- selected-packet SHA-256 values match between arms;
- projected-packet SHA-256 values match between arms;
- projected evidence counts match between arms.

The strict arm may cite only exact identifiers present in the projected
packet. Citation syntax and membership are audited deterministically. Semantic
support is represented only by the disclosed proxy below.

## Scoring

The scored proxies are:

- retrieval availability;
- normalized reference-answer substring in selected evidence;
- normalized reference-answer substring in projected evidence;
- normalized reference-answer substring in a generated answer;
- exact citation presence;
- citation identifier integrity;
- citation support proxy: at least one cited projected block contains a
  normalized reference answer.

These are transparent calibration proxies. They are not the official SimpleQA
judge, a semantic citation judge or proof that every claim is supported.

## Pre-registered gates

All ten gates must pass:

1. protocol accounting is exact: 24 retrieval operations, 24 Tavily requests
   and 96 model requests, with no retry or repair;
2. selected and projected Tavily packets are identical between prompt arms in
   all 24 cases;
3. Tavily retrieval is available in 24/24 cases and projected evidence
   contains a reference-answer key in at least 20/24 cases;
4. every model-arm pair completes at least 23/24 requests;
5. strict aggregate answer-key hits are not below legacy aggregate hits and
   the paired aggregate net gain is non-negative;
6. strict answer-key hits and paired net gain do not regress for either model;
7. strict citation presence is at least 95% among completed strict outputs;
8. strict citation presence improves by at least 20 percentage points over
   legacy;
9. 100% of citations emitted by completed strict outputs use valid projected
   packet identifiers;
10. strict citation support proxy is at least 75% among completed strict
    outputs.

Missing denominators do not pass a rate gate.

## Promotion rule

If and only if all ten gates pass, a separate, reviewable result commit in the
same draft pull request may:

- set the default `quality` provider bundle to Tavily only;
- set the default Tavily share for `quality` to 1.0;
- update tests and documentation for that default;
- mark the already sealed Phase 12 reserve as eligible for a later, separately
  authorized untouched run.

The zero-key `community` profile remains unchanged and free regardless of the
outcome.

If any gate fails, the `quality` profile is not promoted and Phase 12 remains
blocked. A passing run does not itself execute or inspect Phase 12.

## Product positioning

EvidenceMesh remains open source and provider/model neutral. Tavily is an
optional API-backed route, not a requirement for the free community profile.
Users choose their provider bundle, model client and API keys. The benchmark
records one tested configuration and does not claim that its optional paid
components are universally free.

## Privacy and publication limits

The uploaded report may contain Phase 11.7 case identifiers, counts, rates,
latency, usage metadata, categorical failures and SHA-256 values. It must not
contain questions, reference answers, generated answers, prompts, source
titles, URLs, snippets, evidence text, reserved Phase 12 identifiers or API
keys.

The pull request remains draft. Phase 11.7 cannot authorize merge, a GitHub
Release, PyPI publication, a public alpha, an external-agent comparison or a
superiority claim. Those decisions remain separate and explicitly blocked.
