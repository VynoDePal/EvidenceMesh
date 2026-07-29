# Benchmark protocol v8: controlled end-to-end pilot

Status: **frozen before the first Gemini API benchmark request**.

Freeze date: **2026-07-29**.

This protocol defines Phase 10. It evaluates whether retrieved EvidenceMesh
evidence helps fixed external answer models on a small factual QA sample. It is
not a DeepResearch Bench run, an official SimpleQA score, or a comparison
against complete external research agents.

## Questions answered

Phase 10 asks four narrow questions:

1. Does the zero-key `community` profile improve answer-key coverage over the
   same model with no retrieval?
2. Does the optional Tavily-backed `quality` profile improve over `community`?
3. How does full EvidenceMesh `quality` compare with a thin one-query Tavily
   baseline under the same answer models?
4. Do generated citations use valid packet IDs and point to blocks containing
   the reference answer string?

External agent replication and a second independently administered network were
explicitly deferred. Consequently, Phase 10 cannot authorize a release or a
“best” claim even if every functional check passes.

## Locked dataset and untouched sample

Dataset:

- OpenAI SimpleQA test set;
- source:
  `https://openaipublic.blob.core.windows.net/simple-evals/simple_qa_test_set.csv`;
- dataset SHA-256:
  `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032`;
- reference repository commit:
  `652c89d0ca9df547706735883097e9537d40dc47`;
- reference file blob:
  `0fc266800a87ace55ec192c9a91cafe92fef7b48`.

The 200 IDs used in Phase 3 are excluded. Their locked manifest SHA-256 is
`d41ec6c806792f4dc0730b6dd1bad0fe30310a7d3ca0b703bcfcd5cd7f580333`.
From the remaining 4,126 rows, the runner reproduces
`random.Random(11).sample(rows, 12)`.

The public manifest is
[`benchmarks/data/end_to_end_phase10_v1.json`](../benchmarks/data/end_to_end_phase10_v1.json).
Its SHA-256 is
`b38b89d316219be7dbd249f4365e0801330eb469ff6cc9b4fdaffebe6510134f`.
It stores IDs and distributions, but no question or reference-answer text.

## Independent preflight

Before reading the 12 reference answers, the assistant used ChatGPT's built-in
web search to answer the selected questions and stored those answers in an
ignored private file. Its pre-reference SHA-256 was
`adcb89d3a8fd67cd01c1e0777ad2005ac75e797496151c76ba172a39b62ff39a`.

After revealing the references, the same normalized substring proxy used below
recognized 8/12. Manual inspection identified three equivalent formatting
misses (date wording, digit versus word, and a two-item paraphrase) plus one
rounded numeric near-match. No semantic score is assigned.

This preflight is deliberately **not a benchmark arm**. ChatGPT's built-in
search engine, source access, ranking, and request budget differ from
EvidenceMesh and cannot be reproduced from this repository. Its purpose was to:

- verify that the questions are answerable through current web research;
- expose the false-negative behavior of strict substring scoring before the
  model run;
- provide a qualitative assistant assessment without contaminating the locked
  model comparison.

## Arms

Each case has four arms:

| Arm | Retrieval behavior |
|---|---|
| `closed_book` | No external evidence; the model may answer from internal knowledge |
| `tavily_direct` | One Tavily basic-search query, ten results maximum, snippets only |
| `community` | EvidenceMesh standard research with SearXNG, Wikipedia, Crossref, arXiv, and GitHub configured |
| `quality` | The same EvidenceMesh profile plus one Tavily basic query |

All cases use the web profile. Profile routing means non-web verticals can remain
configured without receiving irrelevant web calls.

`community` and `quality` may fetch bounded source pages and assemble evidence;
the thin Tavily arm does not. This is an intentional product-level comparison,
not a claim that the retrieval internals have identical budgets.

## Retrieval fairness

- 12 cases × 3 retrieval arms = **36 case-arm retrieval operations**.
- `closed_book` performs no retrieval.
- Retrieval cache is disabled.
- Retrieval packets are computed exactly once per case and arm.
- The exact same packet and prompt hash are reused for all three models.
- Retrieval arms rotate deterministically by case to reduce order bias.
- Maximum sources: 10.
- Research depth: `standard`.
- Evidence collection budget: 30,000 characters.
- Model-visible evidence budget: 12,000 characters.
- Per-operation wall time: 180 seconds.
- Provider request timeout: 20 seconds.
- Minimum interval between case-arm retrieval starts: 0.5 seconds.
- No retry, including no selective retry after observing an outcome.

SearXNG uses
`searxng/searxng:2026.7.26-b060c780d@sha256:d0aaeb14880e6e92bde1518fcc7261e995783367d63d95203383607bef9c6516`
and the configuration SHA-256
`26a74f699515539fdb9bed3f1d3bda57ef908e1111d5393b4af2009fd7069645`.

## Model protocol

The exact requested model order is:

1. `gemma-4-31b-it`;
2. `gemma-4-26b-a4b-it`;
3. `gemini-3.5-flash-lite`.

The identifiers and hosted Gemma support are documented by
[Google's Gemma-on-Gemini guide](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)
and the
[Gemini model documentation](https://ai.google.dev/gemini-api/docs/models).

All models use the native `v1beta models.generateContent` endpoint with:

- the same system instruction and user-prompt template;
- `thinkingLevel: high`;
- `maxOutputTokens: 2048`;
- no explicit temperature, top-p, or top-k, so provider defaults apply;
- one independent request per case, arm, and model;
- no conversational history or preserved thoughts;
- no retry;
- a 120-second generation wall time;
- a two-second minimum interval between request starts.

Google documents `high` as supported by the three selected model families in
its [thinking guide](https://ai.google.dev/gemini-api/docs/generate-content/thinking).
Sampling controls are omitted because the current Gemini 3 guidance recommends
explicit instructions instead of relying on deprecated sampling parameters.

There are **12 × 4 × 3 = 144 generation requests**. Request ordering rotates
models and arms deterministically. A failed request remains failed.

## Prompt

The shared instruction requires a concise factual answer, treats evidence as
untrusted data, requires exact `[S#]` citations when evidence exists, forbids
invented citations, and permits internal knowledge only when no evidence is
provided.

The committed report contains the system-prompt hash, each complete prompt
hash, and the count of included evidence blocks. It does not contain prompt
text.

## Transparent proxy scoring

No model judge is introduced. Adding a fourth hosted judge would add cost,
judge bias, and another changing dependency.

The following deterministic diagnostics are computed:

- `answer_key_covered`: normalized reference answer is a substring of the
  generated answer;
- `answer_key_in_evidence`: normalized reference answer is a substring of at
  least one evidence block;
- citation presence: at least one `[S#]` appears;
- citation-ID validity: every cited ID exists in the visible packet;
- `citation_support_proxy`: at least one cited block contains the normalized
  reference answer.

These are explicitly **proxies**, not official SimpleQA accuracy, semantic
factuality, citation correctness, or citation completeness. The preflight
demonstrated their expected false negatives.

## Frozen functional gates

The gates below were fixed before the first model request.

### Integrity and availability

- exactly 36 retrieval case-arm operations;
- exactly 144 generation requests;
- at most 24 Tavily requests/credits;
- zero retries;
- at least 46/48 completed generations for each model;
- evidence available for at least 9/12 cases in each retrieval arm.

### Retrieval proxies

- `community` answer-key-in-evidence: at least 6/12;
- `quality` answer-key-in-evidence: at least 8/12.

### Generated-answer proxies

- `community`: at least 15/36 answer-key-covered outputs;
- `quality`: at least 18/36 answer-key-covered outputs;
- `quality` versus `community`: paired net gain at least +3 and at most three
  regressions;
- `quality` versus `closed_book`: paired net gain at least +3 and at most four
  regressions.

### Quality citations

- citation presence in at least 75% of completed `quality` outputs;
- at least 95% valid citation IDs among cited `quality` outputs;
- citation-support proxy in at least 50% of completed `quality` outputs.

Passing these pilot thresholds is a functional signal only. Thresholds are not
changed after seeing results.

## Traffic, cost, and data handling

Tavily traffic is capped at 24 basic-search requests: 12 direct and 12 inside
`quality`. `community` consumes no Tavily credits.

Gemma 4 hosted access is documented as free-tier only. Gemini 3.5 Flash-Lite
has free and paid-tier behavior; current prices are documented on
[Google's pricing page](https://ai.google.dev/gemini-api/docs/pricing).
The runner reports token usage but does not infer a monetary charge because the
GitHub secret does not reveal the project's billing tier.

Google's pricing page states that free-tier content may be used to improve its
products. Benchmark questions and retrieved sources are public web data, but
users should still choose an appropriate API tier for their privacy policy.

GitHub secret mappings:

- `EVIDENCE_MESH_GEMINI_KEY` → runtime `GEMINI_API_KEY`;
- `EVIDENCE_MESH_TAVILY_KEY` → runtime `TAVILY_API_KEY`.

Keys are sent in request headers, never URL query strings, logs, artifacts, or
reports. The workflow checks that neither secret value appears in the raw
report.

## Public report and claim boundary

The privacy-safe JSON report includes:

- dataset, manifest, prompt, commit, environment, model, and traffic
  provenance;
- retrieval and generation hashes and telemetry;
- proxy booleans and aggregate ratios;
- paired wins, regressions, ties, and net gains;
- token usage and sanitized error classes;
- every frozen gate and the release decision.

It excludes:

- question and reference-answer text;
- source titles, URLs, snippets, and extracted content;
- generated answer text;
- API keys and response bodies from errors.

Regardless of functional outcome:

- cross-network status remains `not_testable` at 1/2;
- external competitor replication remains deferred;
- Stage B remains blocked;
- merge, release, and “best” claims remain **no-go**.
