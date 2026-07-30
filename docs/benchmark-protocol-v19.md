# EvidenceMesh benchmark protocol v19

## Phase 11.8.4 — offline quota and structured-output guardrails

Status: offline engineering protocol. It authorizes no provider or model
traffic and does not rewrite the scored Phase 11.8.3 result.

## 1. Purpose

Phase 11.8.3 recorded 22 HTTP 429 responses across 96 requests to
`gemini-3.5-flash-lite`. Its fixed two-second request-start interval allowed
up to 30 requests per minute, while the active project limit observed in
Google AI Studio was 15 requests per minute. The same run also recorded 31
direct-contract schema failures among 36 native direct responses.

Phase 11.8.4 addresses those two engineering defects without calling Tavily,
Gemini or any other network service:

1. model-specific RPM, TPM and RPD scheduling with a 20% safety margin;
2. bounded and privacy-safe classification of Gemini HTTP 429 details;
3. fail-closed scientific behavior that aborts a scored run on any 429;
4. a Gemini-supported native JSON schema plus unchanged strict local semantic
   validation for the direct-answer contract.

This phase does not attempt to repair the failed Phase 11.8.3 projection
quality gate.

## 2. Immutable historical source

- Phase 11.8.3 result:
  `benchmarks/results/phase11_8_3_factorial_2026-07-30.json`
- SHA-256:
  `167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c`
- Historical decision: candidate failed 10/14 gates; Phase 11.9 is not
  authorized; Phase 12 remains sealed and blocked; release remains no-go.

The result, report, protocol v18 and its candidate implementation remain
unchanged. Phase 11.8.4 may diagnose the 429 availability confound, but it
must not rescore, relabel or selectively rerun Phase 11.8.3.

## 3. Quota assumptions and source boundary

Google documents that Gemini rate limits are evaluated across RPM, input TPM
and RPD, that exceeding any one dimension produces a rate-limit error, and
that limits are applied per project rather than per API key:

<https://ai.google.dev/gemini-api/docs/rate-limits>

Active limits vary by model, project and usage tier. The following values are
the project limits observed in AI Studio on 2026-07-30 and are locked only as
offline calibration fixtures:

| Model | Observed RPM | Observed input TPM | Observed RPD |
|---|---:|---:|---:|
| `gemini-3.5-flash-lite` | 15 | 250,000 | 500 |
| `gemma-4-26b-a4b-it` | 30 | 16,000 | 14,400 |
| `gemma-4-31b-it` | 30 | 16,000 | 14,400 |

They are not universal defaults. Every future live protocol must explicitly
review or override its active project limits.

The effective offline safety budgets are the integer floor of four fifths of
each observed ceiling. Flash Lite therefore uses 12 RPM, 200,000 TPM and 400
RPD. The two Gemma fixtures use 24 RPM, 12,800 TPM and 11,520 RPD.

## 4. Scheduler contract

The scheduler is sequential and model-specific.

- Request starts are smoothed by the stricter of:
  - `60 / effective RPM`;
  - `60 × estimated input tokens / effective TPM`.
- Every proposed start is also audited against the preceding rolling
  60-second window.
- A tokenizer-free pre-request estimate uses UTF-8 bytes divided by three,
  rounded upward, plus 64 request-overhead tokens.
- A single request larger than the effective TPM budget is rejected before
  scheduling.
- The caller must supply the already-consumed daily request count. A request
  exceeding the effective RPD budget is rejected before scheduling.
- Active limits are project-level; using another key from the same project
  does not create another bucket.

The future live runner may reconcile estimates with returned
`promptTokenCount`, but it must never depend on a successful response to
prevent the first quota violation.

## 5. HTTP 429 contract

Google documents HTTP 429 as a rate or quota exhaustion response:

<https://ai.google.dev/gemini-api/docs/troubleshooting>

The sanitizer may retain only:

- HTTP status `429`;
- categorical error kind `http_429`;
- quota dimension `rpm`, `tpm`, `rpd`, `spend` or `unknown`;
- a bounded numeric retry delay when supplied.

It must not retain response messages, raw details, quota identifiers, URLs,
prompts, answers, headers other than a parsed numeric `Retry-After`, or
credentials.

A future scored benchmark must abort unscored on the first 429. It must not
record the request as a model-quality miss and must not retry selectively.
Ordinary non-benchmark integrations may use bounded exponential backoff with
positive jitter, but that policy is explicitly outside scored traffic.

## 6. Native structured-output contract

Google lists structured outputs as supported for
`gemini-3.5-flash-lite`:

<https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite>

For the existing `generateContent` endpoint, the request uses:

- `generationConfig.responseMimeType = application/json`;
- `generationConfig.responseJsonSchema = <schema>`.

The documented supported JSON Schema subset is defined in the Gemini API
reference:

<https://ai.google.dev/api/generate-content>

The prior offline schema included `minLength`, `maxLength`, `pattern` and
`uniqueItems`, which are not in that supported subset. Phase 11.8.4 therefore
uses only supported syntax keywords:

- a closed object with `answer` and `citation_ids`;
- required keys and stable property ordering;
- string and array types;
- a 20-item maximum;
- descriptive field instructions.

Native structured output guarantees only syntactic shape. The unchanged
Phase 11.8.2 local parser remains authoritative for non-empty answers,
identifier syntax and uniqueness, membership in the evidence packet,
supported-answer citations and the exact insufficient-evidence form. No
permissive parsing, repair or fallback is introduced.

## 7. Offline fixtures

The deterministic evaluation contains:

1. a 96-request, 5,000-estimated-token Flash Lite schedule;
2. a 24-request, 4,000-estimated-token Gemma schedule demonstrating that TPM,
   not RPM, is the binding dimension;
3. RPM, TPM, RPD and unknown 429 response fixtures;
4. numeric `Retry-After` and protobuf retry-delay fixtures;
5. a valid native direct-answer request body;
6. valid and invalid direct-answer payloads checked by the locked local
   parser.

Fixtures contain no Phase 11.7 question, reference answer, evidence, prompt,
generated answer, API response from the scored run or Phase 12 identifier.

## 8. Exact traffic boundary

- network requests: 0
- provider calls: 0
- model calls: 0
- Tavily requests: 0
- Gemini requests: 0
- retries: 0
- fallbacks: 0
- repairs: 0
- required secrets: none

The workflow has read-only repository permissions, binds no provider secret
and contains no live job.

## 9. Blocking offline gates

All gates must pass:

1. protocol, implementation and historical source integrity;
2. exact preservation of the Phase 11.8.3 no-go;
3. zero network, provider and model traffic;
4. exact 20%-margin effective quota budgets;
5. Flash Lite schedule remains within rolling RPM and TPM;
6. Flash Lite starts are separated by at least five seconds;
7. Gemma schedule remains within rolling RPM and TPM;
8. Gemma fixture is demonstrably TPM-bound;
9. daily-budget exhaustion fails before scheduling;
10. 429 fixtures map to the correct bounded dimensions;
11. sanitized 429 telemetry omits all raw provider content;
12. a 429 aborts the scored benchmark path;
13. the native request uses only Gemini-supported schema keywords and the
    required JSON fields;
14. the strict local parser continues to reject semantic contract violations;
15. historical, product, authorization, Phase 12, merge and release boundaries
    remain unchanged.

## 10. Decision semantics

A 15/15 pass means only:

> the offline quota, 429 and structured-output guardrails satisfy their
> authored engineering invariants.

It does not prove that a live request will avoid all provider-side capacity
errors, establish direct-answer schema adherence on real cases, improve
retrieval or answer quality, authorize a live smoke test, authorize Phase
11.9, access Phase 12, change product defaults, permit merge or release, or
support a “best” or superiority claim.

Any live smoke test requires a separate user authorization and a distinct,
small, pre-registered traffic ceiling.

## 11. Public output and privacy

The result may contain model names, observed and effective quota fixtures,
synthetic token counts, simulated timestamps, bounded 429 categories, schema
hashes, request hashes, gates and decisions.

It must not contain questions, reference answers, source titles, URLs,
snippets, evidence, generated text, prompts, credentials, raw 429 messages or
details, or Phase 12 reserved identifiers.
