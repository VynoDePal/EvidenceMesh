# EvidenceMesh Phase 11.6 Tavily citation-isolation protocol

Status: frozen before the first scored Phase 11.6 provider or model request.

## Purpose and decision boundary

Phase 11.6 is a disclosed causal calibration, not an untouched evaluation.
It isolates the citation contract from retrieval quality after Phase 11.5
showed that Tavily direct retained more answer-bearing evidence than the mixed
quality profile, while the strict candidate prompt produced stronger citation
metrics.

The only scored comparison is:

1. `tavily_legacy`: Tavily evidence with the Phase 10 legacy answer prompt;
2. `tavily_strict`: the exact same Tavily evidence with the Phase 11.5 strict
   packet-local citation prompt.

For every case, both arms receive byte-identical selected evidence and
byte-identical projected evidence. They differ only in their system and user
instructions. Retrieval is performed once per case and is never repeated per
generation arm.

The 12 questions are deliberately reused from Phases 10 and 11.5. They are
calibration cases and cannot establish generalization or competitive
superiority. No Phase 12 question, answer or artifact may be accessed or
generated during this phase.

## Locked inputs

- Manifest:
  `benchmarks/data/end_to_end_phase10_v1.json`
- Manifest SHA-256:
  `b38b89d316219be7dbd249f4365e0801330eb469ff6cc9b4fdaffebe6510134f`
- Dataset: OpenAI SimpleQA CSV downloaded from the source already used by the
  earlier phases.
- Dataset SHA-256:
  `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032`
- Exclusion source:
  `benchmarks/results/simpleqa_retrieval_phase3_2026-07-28.json`
- Case count: exactly 12.
- Provider: Tavily only.
- Search profile: web.
- Results per case: at most 10 after ranking and at most 3 per domain.
- Prompt evidence budget: 12,000 characters.
- Cache: disabled.

The product configuration is not changed before the scored run. At the start
of Phase 11.6, the community profile remains the zero-key community provider
bundle, while the quality profile remains the existing mixed bundle with a
Tavily primary-provider share of 0.8.

## Locked model matrix

The exact model order is:

1. `gemma-4-31b-it`;
2. `gemma-4-26b-a4b-it`;
3. `gemini-3.5-flash-lite`.

`gemma-4-26b-a4b-it` is blocking: its failures count exactly like failures
from the other two models. `gemini-3.5-flash-lite` is explicitly included in
all per-model and aggregate gates.

Each of the 12 cases is generated once for each of the two prompt arms and
each of the three models. Phase 11.6 therefore makes exactly 72 native Gemini
generation requests.

## Locked traffic and timeout budget

- 12 case-retrieval operations;
- exactly 12 Tavily requests, one per case;
- exactly 72 model requests;
- zero retries;
- zero fallback requests;
- zero citation-repair requests;
- zero cache reads or writes for scored retrieval;
- 0.5 seconds between Tavily operations;
- 2.0 seconds between model operations;
- 20 seconds provider request timeout;
- 30 seconds whole retrieval-operation ceiling;
- 60 seconds whole generation-request ceiling;
- 90 minutes whole GitHub Actions job ceiling;
- 2,048 maximum output tokens per generation.

A failed or timed-out call remains failed. It cannot be selectively rerun.
The arm and model order rotate deterministically across cases to reduce
ordering bias without changing the call count.

## Evidence and prompt isolation

One Tavily raw-result pool is collected for each case. The normal
EvidenceMesh ranking, canonicalization and domain-cap logic selects the
packet. The same sequential 12,000-character Phase 10 projection is then
applied to both prompt arms.

The report must prove, for all 12 cases, that:

- selected-packet SHA-256 values match between arms;
- projected-packet SHA-256 values match between arms;
- projected evidence counts match between arms.

The strict arm may only cite exact identifiers present in that projected
packet. Citation syntax and membership are audited deterministically. Semantic
support is represented only by the disclosed proxy defined below.

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

These are transparent calibration proxies. They are not the official
SimpleQA judge, a semantic citation judge or proof that every claim is
supported.

## Pre-registered gates

All ten gates must pass:

1. protocol accounting is exact: 12 retrieval operations, 12 Tavily requests
   and 72 model requests, with no retry or repair;
2. selected and projected Tavily packets are identical between prompt arms in
   all 12 cases;
3. Tavily retrieval is available in 12/12 cases and projected evidence
   contains a reference-answer key in at least 10/12 cases;
4. every model-arm pair completes at least 11/12 requests, including the
   blocking `gemma-4-26b-a4b-it`;
5. strict aggregate answer-key hits are not below legacy aggregate hits and
   the paired aggregate net gain is non-negative;
6. strict answer-key hits and paired net gain do not regress for any of the
   three models;
7. strict citation presence is at least 90% among completed strict outputs;
8. strict citation presence improves by at least 20 percentage points over
   legacy;
9. 100% of citations emitted by completed strict outputs use valid projected
   packet identifiers;
10. strict citation support proxy is at least 70% among completed strict
    outputs.

Missing denominators do not pass a rate gate.

## Promotion rule

If and only if all ten gates pass, a separate, reviewable result commit in the
same draft pull request may:

- set the default `quality` provider bundle to Tavily only;
- set the default Tavily share for `quality` to 1.0;
- update tests and documentation for that default;
- mark a separately authorized, untouched Phase 12 evaluation as unblocked.

The community profile remains unchanged and free regardless of the outcome.

If any gate fails, the quality profile is not promoted and Phase 12 remains
blocked. A passing run does not itself execute Phase 12.

## Privacy and publication limits

The uploaded report may contain case identifiers, counts, rates, latency,
usage metadata, categorical failures and SHA-256 values. It must not contain
questions, reference answers, generated answers, prompts, source titles, URLs,
snippets, evidence text or API keys.

The pull request remains draft. Phase 11.6 cannot authorize merge, a GitHub
Release, PyPI publication, a public alpha, an external-agent comparison or a
superiority claim. Those decisions remain separate and explicitly blocked.
