# Phase 11.8.4 offline quota and structured-output guardrails

**Offline engineering verdict: pass (15/15 gates). Phase 11.8.3 remains
failed. No live traffic is authorized. Phase 12 remains sealed and blocked;
release remains no-go.**

## Scope

Phase 11.8.4 diagnoses and corrects the benchmark-engineering defects exposed
by the 22 HTTP 429 responses and 31 direct-contract schema failures recorded
in Phase 11.8.3. It made zero Gemini or Tavily calls, bound no secret and did
not modify or rescore any historical artifact.

Protocol: [benchmark protocol v19](../../docs/benchmark-protocol-v19.md)

Implementation:
[`phase11_8_4_guardrails.py`](../phase11_8_4_guardrails.py)

Reproducible result:
[`phase11_8_4_offline_guardrails_2026-07-30.json`](phase11_8_4_offline_guardrails_2026-07-30.json)

## Quota diagnosis

The observed active project limits are calibration inputs rather than
universal defaults. The 20% safety margin produces:

| Model | Effective RPM | Effective input TPM | Effective RPD |
|---|---:|---:|---:|
| Gemini 3.5 Flash Lite | 12 | 200,000 | 400 |
| Gemma 4 26B | 24 | 12,800 | 11,520 |
| Gemma 4 31B | 24 | 12,800 | 11,520 |

The simulated 96-request Flash Lite plan starts one request every five
seconds, lasts 475 seconds between its first and final starts, and reaches at
most 12 requests and 60,000 estimated input tokens in any rolling minute.

The 24-request Gemma fixture demonstrates the separate TPM risk: 4,000
estimated input tokens per request require an initial 18.75-second spacing,
despite the RPM-only interval being 2.5 seconds. It reaches at most three
requests and 12,000 estimated tokens in any rolling minute.

RPD exhaustion, a single request larger than effective TPM and an early
reservation all fail before a provider request can start.

## HTTP 429 contract

Authored RPM, TPM, RPD and unknown quota fixtures were classified correctly.
The public diagnostic retains only HTTP status, categorical dimension and a
bounded retry delay. Provider messages, raw quota identifiers and dimensions
are discarded.

A scored benchmark now has an explicit fail-closed design boundary: the first
429 aborts the run as unscored quota contamination. It is not converted into a
model-quality miss and receives no selective retry. A separate bounded
backoff helper exists only for ordinary non-benchmark integrations.

## Native structured output

Gemini 3.5 Flash Lite documents structured-output support. The candidate
request now uses `application/json` and a native response JSON schema.

The earlier offline schema contained `minLength`, `maxLength`, `pattern` and
`uniqueItems`, which are outside Gemini's documented supported subset. The new
provider-facing schema uses only supported syntax. The unchanged strict local
parser still enforces:

- a non-empty answer;
- bare, unique and packet-local citation identifiers;
- at least one citation for a supported answer;
- the exact insufficient-evidence form;
- no Markdown wrapper, repair or fallback.

All four authored semantic violations were rejected and the valid fixture was
accepted.

## Traffic and privacy

| Counter | Observed |
|---|---:|
| Network requests | 0 |
| Provider calls | 0 |
| Model calls | 0 |
| Tavily requests | 0 |
| Gemini requests | 0 |
| Retries, fallbacks and repairs | 0 |

The result contains no question, reference answer, evidence, prompt,
generated answer, credential, raw provider error or Phase 12 identifier.

## Decision boundary

The 15/15 pass validates only offline scheduling, quota diagnostics and
structured-output construction. It does not establish live provider
availability, real-case schema adherence, retrieval improvement or answer
quality.

The Phase 11.8.3 candidate remains failed at 10/14; its 17/24 projection gate
is unaffected. Phase 11.9 remains unauthorized, product defaults remain
unchanged, users retain provider/model/key choice, the pull request remains a
draft, and merge, release, public alpha, external comparison and superiority
claims remain blocked.

A small, separately pre-registered live quota/schema smoke test requires
explicit user authorization.
