# EvidenceMesh benchmark protocol v20

## Phase 11.8.5 — Gemini quota and native-schema live micro-smoke

Status: pre-registered live engineering smoke. This protocol authorizes at
most eight Gemini generation requests only after a separate explicit GitHub
authorization event. It authorizes no Tavily request, quality benchmark,
profile change, Phase 11.9 work, Phase 12 access, merge or release.

## 1. Purpose

Phase 11.8.3 used a fixed two-second start interval for 96 requests to
`gemini-3.5-flash-lite`. It recorded 22 HTTP 429 responses. Its provider-facing
direct-answer schema also contained JSON Schema keywords that are outside the
documented Gemini subset; only 5 of 36 native direct responses passed the
strict local contract.

Phase 11.8.4 corrected those engineering defects offline:

1. model-specific RPM, input-TPM and RPD governance with a 20% margin;
2. privacy-safe 429 classification and scored-run abortion;
3. a provider-facing schema limited to Gemini-supported keywords;
4. unchanged strict local validation of answer and citation semantics.

Phase 11.8.5 tests only whether those corrections work against the live
Gemini endpoint at very small scale. It does not retest retrieval or answer
quality.

## 2. Provider documentation boundary

Google documents that Gemini rate limits are evaluated across RPM, input TPM
and RPD, that exceeding any one dimension can produce a rate-limit error, and
that limits apply per project rather than per API key:

<https://ai.google.dev/gemini-api/docs/rate-limits>

Google currently lists `gemini-3.5-flash-lite` as a stable model with
structured-output support:

<https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite>

The existing EvidenceMesh benchmark integration uses the non-interactive
`generateContent` endpoint. Its generation configuration supports
`application/json` output and `responseJsonSchema`:

<https://ai.google.dev/api/generate-content>

The Interactions API may be evaluated separately in the future. Changing
endpoint and schema together here would prevent attribution to the Phase
11.8.4 correction.

## 3. Immutable sources

- Synthetic fixture:
  `benchmarks/data/phase11_8_5_live_smoke_v1.json`
- Fixture SHA-256:
  `64096454a2884817148694b6086043a7fdbecb911b8db4456994a6dfadfc47af`
- Phase 11.8.4 guardrails SHA-256:
  `83a4341b93c49b3fc8c6a7f46da40c24f8bed19b516472229e3b280a3ebc763d`
- Phase 11.8.4 result SHA-256:
  `480e60d9f1d9807d9f7d0e21b23f812dbed2a4c978d27b08a8b810fe719d000d`
- Historical Phase 11.8.3 result SHA-256:
  `167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c`
- Strict local candidate/parser SHA-256:
  `0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e`

The four fixtures are public and synthetic. They contain no SimpleQA case,
Phase 11.7 question, Phase 12 identifier, user data or retrieved Web content.
Each fixture is executed twice, producing eight maximum attempts.

## 4. Exact traffic contract

| Dimension | Maximum |
|---|---:|
| Gemini `generateContent` requests | 8 |
| Models | 1 |
| Tavily requests | 0 |
| Other provider requests | 0 |
| Token-count requests | 0 |
| Retries | 0 |
| Fallbacks | 0 |
| Repairs | 0 |

The sole model is `gemini-3.5-flash-lite`. The runner uses one sequential
client with transport retries disabled. It waits for a 60-second cold-start
window before the first request.

The live run stops immediately after:

- an HTTP 429;
- another non-success HTTP status;
- a network or wall-time failure.

A native HTTP 200 response that violates the JSON or local semantic contract
is recorded and does not trigger a repair or retry. Remaining pre-registered
fixtures may continue so adherence can be measured without selective reruns.

## 5. Quota governor

The active project ceilings observed in Google AI Studio on 2026-07-30 are
locked as calibration inputs, not universal defaults:

- 15 RPM;
- 250,000 input TPM;
- 500 RPD.

The Phase 11.8.4 four-fifths safety policy therefore enforces:

- 12 RPM;
- 200,000 estimated input TPM;
- 400 RPD.

Request starts must be separated by at least five seconds. The scheduler also
audits every rolling 60-second window.

For fail-closed planning, the runner starts from a deliberately conservative
synthetic daily reservation of 392 requests. Eight successful reservations
reach the effective 400-request budget exactly. This value is not a claim
about the provider dashboard's current count.

Pre-request input usage is conservatively estimated from the system prompt,
user prompt and canonical JSON schema. No `countTokens` request is made,
because it would consume additional RPM and alter the experiment.

## 6. Request and response contract

Every request uses:

- endpoint: Gemini `v1beta` `generateContent`;
- response MIME type: `application/json`;
- provider schema: the Phase 11.8.4 Gemini-supported direct-answer schema;
- maximum output: 256 tokens;
- thinking level: `minimal`;
- deterministic fixture/repetition-derived seed.

In accordance with the current Gemini 3.x guidance, `temperature`, `topP`,
`topK` and `candidateCount` are deliberately omitted. Provider sampling
defaults therefore apply. Determinism is constrained through the explicit
system instruction, immutable fixtures and repetition-derived seed instead.

The unchanged Phase 11.8.2 parser remains the semantic authority. It checks:

- exact object keys `answer` and `citation_ids`;
- non-empty answer text;
- exact insufficient-evidence form;
- citation identifier syntax and uniqueness;
- citation membership in the supplied packet;
- presence of citations for a supported answer.

The micro-smoke additionally compares the parsed answer and citation list with
the public synthetic expectation. This is fixture conformance, not a general
answer-quality score.

## 7. HTTP 429 behavior

Google documents HTTP 429 as rate or quota exhaustion:

<https://ai.google.dev/gemini-api/docs/troubleshooting>

On 429, the runner stores only:

- status `429`;
- error kind `http_429`;
- bounded quota dimension;
- bounded numeric retry delay when present.

It omits provider messages, raw error details, quota identifiers, headers,
prompts, responses and credentials. The smoke aborts without retrying.

## 8. Blocking gates

The live smoke passes only if all twelve gates pass:

1. every immutable source matches its locked SHA-256;
2. the model and request configuration match this protocol exactly;
3. no more than eight Gemini requests and no other provider request occur;
4. retries, fallbacks, repairs and token-count requests remain zero;
5. the 60-second cold start and quota-governed schedule are applied;
6. every rolling request and estimated-token window stays within safety limits;
7. no HTTP 429 occurs;
8. all eight requests return a native HTTP 200 completion;
9. all eight native answers pass the strict JSON/local schema;
10. all eight answers pass fixture-level semantic expectations;
11. usage metadata is present and non-negative for every native completion;
12. privacy and all historical/product/release boundaries remain intact.

An availability error, 429, schema failure or semantic failure produces a
valid technical artifact with a failed smoke decision. It must not be hidden
through a selective rerun.

## 9. Authorization and secret boundary

Publishing this protocol does not authorize traffic.

Live execution requires either:

- a manual workflow dispatch with `authorize_live_run=true`; or
- the exact `phase11.8.5-live-authorized` label added to the same-repository
  draft pull request.

The ordinary PR path runs only offline validation and receives no provider
secret. The live job receives only `EVIDENCE_MESH_GEMINI_KEY`. It never binds
the Tavily secret.

## 10. Public result and privacy

The public JSON artifact may contain:

- fixture IDs and repetition indices;
- hashes of prompts and generated answers;
- categorical success/failure fields;
- bounded usage, latency, quota and aggregate metrics;
- model/version and finish reason.

It must not contain:

- API keys or authorization headers;
- raw prompts, questions, evidence or expected answers;
- raw model responses or parsed answer text;
- raw provider error bodies or messages;
- SimpleQA, Phase 11.7 or Phase 12 content.

## 11. Decision semantics

A 12/12 pass proves only that this small synthetic run completed under the
authored quota and native-schema controls.

It does not repair the deterministic Phase 11.8.3 projection result:
candidate and equal-cap prompt coverage remain tied at 17/24, below the frozen
20/24 floor. Therefore even a live-smoke pass does not authorize an unchanged
Phase 11.8.3 rerun, freeze Phase 11.9, access Phase 12, change product
defaults, merge, release, publicize an alpha or support a superiority claim.

The rational next step after a pass is a separately reviewed projection
recovery design. The rational next step after a failure is diagnosis of the
specific availability, schema or semantic gate without an opportunistic live
rerun.
