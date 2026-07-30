# EvidenceMesh benchmark protocol v23

## Phase 11.8.8 — offline projection-recovery lock

Status: frozen offline engineering protocol. This phase performs no network,
provider, search or model request, binds no secret and does not authorize a
live calibration.

## 1. Purpose and evidence boundary

Phase 11.8.3 isolated projection and response-contract effects on the 24
already-observed Phase 11.7 cases. Its candidate failed 10/14 blocking gates.
The selected evidence contained the transparent answer-key proxy in 19/24
cases, while both equal-cap and the v1 candidate projections retained it in
17/24 cases.

Those counts establish two different limits:

1. projection could recover at most 19/24 on that exact selected packet;
2. the frozen 20/24 projection floor was therefore mathematically unreachable
   without a different retrieval packet.

Phase 11.8.8 closes only the offline projection-design gap. It freezes and
tests one answer-blind, source-preserving v2 projector and pre-registers the
minimum contract that a separate future Tavily-only calibration would have to
satisfy.

Synthetic fixture performance is engineering evidence only. It cannot prove
quality on Web results, repair the Phase 11.8.3 no-go, authorize live traffic
or establish generalization.

## 2. Immutable historical sources

- Phase 11.7 observed-case manifest:
  `benchmarks/data/phase11_7_fresh_confirmation_v1.json`
- Manifest SHA-256:
  `da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e`
- Phase 12 sealed reserve:
  `benchmarks/data/phase12_untouched_reserve_v1.json`
- Reserve SHA-256:
  `472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee`
- Phase 11.8.3 protocol:
  `docs/benchmark-protocol-v18.md`
- Phase 11.8.3 protocol SHA-256:
  `d139c1fed0d9c2bcfe7cdc02f1cda510802296ababbf360b6381c4db5e55239d`
- Phase 11.8.3 result:
  `benchmarks/results/phase11_8_3_factorial_2026-07-30.json`
- Phase 11.8.3 result SHA-256:
  `167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c`
- Historical equal-cap and v1 implementation:
  `benchmarks/phase11_8_2_candidate.py`
- Historical implementation SHA-256:
  `0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e`
- Phase 11.8.7 runtime protocol:
  `docs/benchmark-protocol-v22.md`
- Phase 11.8.7 runtime protocol SHA-256:
  `e786b5b4f7ade79d40dc81ffab3a20bd0a09ffe45c7b5a8765155519e2cd1dbe`
- Phase 11.8.7 runtime result:
  `benchmarks/results/phase11_8_7_offline_runtime_timeout_hardening_2026-07-30.json`
- Phase 11.8.7 runtime result SHA-256:
  `375718f1ba8ed4d4623bb76df3253a7d64b2dbbc813a69615488ab2e084f8fd7`

The Phase 11.8.3 10/14 failure, its 19/24 selected-evidence coverage, the
17/24 equal-cap and v1 projection scores, the Phase 11.8.5 8/12 live-smoke
failure and the Phase 12 seal are immutable. This phase must not rescore,
relabel or rewrite them.

## 3. New offline sources

- v2 projector:
  `benchmarks/phase11_8_8_projection_candidate.py`
- v2 projector SHA-256:
  `117968687a0c0c150acef42f997967d10b04006d14ed0efa9de87c9c08b1909e`
- Synthetic fixture:
  `benchmarks/data/phase11_8_8_projection_fixtures_v1.json`
- Synthetic fixture SHA-256:
  `8955ac33c89c2e16a474182c14eac8df5acaf649642f4dd90a313cf6227db614`
- Offline report runner:
  `benchmarks/run_phase11_8_8_offline_projection_lock.py`
- Future calibration runner, check-only by default:
  `benchmarks/run_phase11_8_8_projection_calibration.py`

The offline runner locks this protocol, the candidate, fixture, future runner
and historical inputs. The read-only workflow independently locks the offline
runner and the reproduced result, avoiding circular source hashes.

## 4. Answer-blind v2 projector contract

The v2 projector receives only:

- the question;
- the already-selected evidence blocks;
- the rendered-character budget;
- the per-block character ceiling;
- explicitly documented projection parameters.

It must not receive or inspect a reference answer, expected-answer fragment,
answer hash, score, scoring sentinel, case identifier, dataset row index,
historical outcome or Phase 12 identifier. It performs no file, environment,
network, provider or model access.

The implementation is deterministic and extractive:

- emitted evidence text consists only of exact, ordered source substrings;
- omissions may be represented only by a fixed visible separator;
- no word, punctuation mark, number, date, name or unit may be invented or
  normalized;
- citation identifiers, titles, URLs and provider metadata remain attached to
  their original blocks and are never fabricated or reassigned;
- duplicate citation identifiers fail closed;
- empty or invalid inputs produce a bounded deterministic result or a bounded
  documented validation error.

The exact source hash is the algorithmic authority. Fixtures and tests must
also use tripwire objects or equivalent checks proving that forbidden
answer-side fields cannot be accessed.

## 5. Projection and budget lock

The offline comparison contains exactly three projectors:

| Projector | Role |
|---|---|
| `equal_cap` | locked Phase 11.8.3 control |
| `query_window_v1` | locked Phase 11.8.2/11.8.3 candidate |
| `projection_v2` | sole new Phase 11.8.8 candidate |

No second v2 variant, adaptive selector or result-dependent parameter search
is permitted.

All three projectors receive the same input block order. The v2 defaults are:

- total rendered evidence budget: 12,000 characters;
- maximum evidence text per block: 1,500 characters;
- headers and inter-block separators count against the total;
- candidate deterministic replays per fixture: at least three.

Every emitted citation identifier must be unique and present in the input
packet. The rendered packet must remain within its exact budget for every
replay and every boundary fixture.

## 6. Synthetic fixture boundary

Fixtures are public, authored and non-probative. They contain no SimpleQA
question or reference answer, no Phase 11.7 or Phase 11.8 case content, no
retrieved Web content, no provider response, no user data and no Phase 12
identifier.

They cover at least:

- answer-like source spans at the head, middle and tail;
- multi-token names, dates, numbers, punctuation and Unicode;
- long irrelevant regions and query-term decoys;
- repeated terms and overlapping candidate windows;
- short, empty and very long blocks;
- exact-budget and insufficient-budget boundaries;
- duplicate citation identifiers;
- deterministic ties and reordered metadata.

Only the fixture scorer receives fixture sentinels. Passing the fixtures means
that the authored invariants hold; it is not evidence that v2 improves real
retrieval or answer quality.

## 7. Exact offline traffic and workflow boundary

| Dimension | Required |
|---|---:|
| Network requests made by the evaluation | 0 |
| Provider calls | 0 |
| Search calls | 0 |
| Model calls | 0 |
| Bound secrets | 0 |
| Tavily requests | 0 |
| Gemini requests | 0 |
| Retries | 0 |
| Fallbacks | 0 |
| Repairs | 0 |

The Phase 11.8.8 workflow has read-only repository permission, receives no
provider secret and contains no live job or live authorization label. Ordinary
pull-request and manual workflow events may reproduce only the committed
offline report.

Publishing this protocol, its implementation, tests or result does not
authorize Tavily, Gemini or any other external request.

## 8. Blocking offline gates

Phase 11.8.8 passes only if all fourteen engineering gates pass:

1. every historical source matches its locked hash;
2. the candidate, fixture, future runner and protocol match their final locked
   hashes;
3. the Phase 11.8.3 10/14 no-go and its 19/24 and 17/24 observations remain
   unchanged;
4. network, provider, search, model, secret, retry, fallback and repair counts
   are zero;
5. the v2 input surface is answer-blind and forbidden scorer fields are
   inaccessible;
6. every v2 evidence segment is an exact ordered substring of its source;
7. citation identifiers and metadata remain source-bound, unique and
   unmodified;
8. all v2 outputs respect the exact rendered and per-block budgets;
9. repeated v2 projections are byte-identical;
10. malformed and duplicate-identifier inputs fail closed with bounded
    categories;
11. all documented boundary and adversarial fixtures behave as pre-registered;
12. v2 does not regress against equal-cap or v1 on the synthetic retention
    fixtures;
13. the future live traffic, metrics, privacy and decision contract below is
    represented exactly, defaults to check-only and has no live workflow;
14. historical, user-choice, Phase 11.9, Phase 12, merge and release
    boundaries remain unchanged.

## 9. Future Tavily-only calibration — non-authorizing design

The following design is a prerequisite for a separate future live protocol.
It is not a live job and cannot be executed under Phase 11.8.8.

The pre-registered future runner is
`benchmarks/run_phase11_8_8_projection_calibration.py`. It defaults to
checksum validation without provider access and requires an explicit live
flag, a dataset and an output path before it can enter its live code path. Its
source hash is locked by the offline report and workflow after this protocol
is frozen. No workflow binds a provider secret or exposes that live path in
this phase. A separate explicit user authorization is required before any
provider credential may be bound.

### 9.1 Dataset and shared retrieval packet

The calibration would reuse exactly the 24 already-observed Phase 11.7
selectors. It would therefore remain corrective calibration, never fresh
confirmation.

For each attempted case:

- provider: Tavily only;
- query: the checksum-pinned dataset question, unchanged;
- maximum raw results: 20;
- selected results: at most 20;
- maximum results per domain: 3;
- document fetching: disabled;
- cache: disabled;
- retries, fallbacks and repairs: forbidden;
- one Tavily attempt supplies one raw pool and one selected packet;
- equal-cap, v1 and v2 receive that same selected packet without another
  request.

The packet supplied to the three projectors must be byte-identical before
projection. Scoring occurs only after all three projections are complete.
Reference answers and scoring sentinels remain inaccessible to every
projector.

### 9.2 Planned traffic and fail-fast behavior

| Dimension | Plan | Hard ceiling |
|---|---:|---:|
| Cases | 24 | 24 |
| Tavily requests | 24 | 24 |
| Projectors per completed packet | 3 | 3 |
| Gemini requests | 0 | 0 |
| Other model requests | 0 | 0 |
| Token-count requests | 0 | 0 |
| Retries | 0 | 0 |
| Fallbacks | 0 | 0 |
| Repairs | 0 | 0 |

“24 requests” is the complete-run plan, while 24 is the hard maximum. A
provider HTTP failure, HTTP 429, authentication failure, transport timeout or
outer wall timeout aborts the run without retry. The resulting artifact is an
availability no-go and may contain fewer than 24 attempts; it must not claim
an exact completed traffic count.

A successful provider response with no useful result remains a completed
retrieval outcome and is scored as such. Passing quality gates requires 24/24
completed retrievals. Selective or opportunistic reruns are forbidden.

### 9.3 Projection metrics

The transparent proxy remains the normalized reference-answer substring:

- `selected_coverage`: proxy present anywhere in the shared selected packet;
- `equal_cap_coverage`: proxy retained by equal-cap;
- `v1_coverage`: proxy retained by v1;
- `v2_coverage`: proxy retained by v2;
- `v2_selected_retention`: v2 hits divided by selected-packet hits;
- paired gains: candidate wins minus baseline wins across all 24 cases.

These are projection-retention proxies, not official SimpleQA accuracy,
semantic entailment, citation correctness or generated-answer quality.

### 9.4 Blocking future live gates

A separate future Tavily-only calibration could pass only if all of the
following are true:

1. every historical, candidate, dataset, protocol and live-runner lock
   matches;
2. exactly the 24 observed selectors are attempted once and all 24 retrievals
   complete successfully;
3. Tavily traffic is exactly 24 for a complete run and never exceeds 24;
4. Gemini, other-model, token-count, retry, fallback and repair requests remain
   zero;
5. raw and selected packets are shared identically across all three
   projectors in 24/24 cases;
6. v2 remains deterministic, answer-blind, source-preserving and
   budget-compliant in 24/24 cases;
7. selected-packet proxy coverage is at least 20/24;
8. v2 projected proxy coverage is at least 20/24;
9. v2 has an all-case paired net gain of at least +2 against equal-cap;
10. v2 has an all-case paired net gain of at least +2 against v1;
11. v2 retains at least 95% of proxy hits present in selected evidence;
12. privacy, traffic, historical and release boundaries remain intact.

If selected coverage is below 20/24, the result is retrieval-limited and the
projection candidate cannot pass the absolute gate. If selected coverage
reaches 20/24 but v2 does not, the result is projection-limited. A new live
score must never be compared causally with the historical 17/24 because the
underlying Tavily packet has changed; only within-run paired comparisons are
valid.

## 10. Public output and confidentiality

The offline report may contain fixture identifiers, source hashes, bounded
counts, invariant Booleans, rendered lengths, gate decisions and zero-traffic
accounting.

A future live report may additionally contain existing opaque case
identifiers, raw/selected/projected packet hashes, per-arm Boolean proxies,
bounded failure kinds, latencies and aggregate traffic.

Neither report may contain:

- questions, dataset row indexes or reference answers;
- hashes of questions or reference answers;
- source titles, URLs, snippets, selected evidence or projected text;
- Tavily response bodies or raw error messages;
- prompts, generated answers or model responses;
- headers, credentials or environment values;
- Phase 12 reserved identifiers.

The runtime timeout taxonomy from Phase 11.8.7 may be used for bounded failure
classification. Exception text, request URLs and provider content remain
private.

## 11. Decision semantics

A 14/14 offline pass proves only that the v2 implementation and the
non-authorizing future calibration contract satisfy their authored
engineering invariants.

It does not authorize:

- the future Tavily-only calibration;
- a live workflow label or dispatch;
- Gemini or another model request;
- an unchanged Phase 11.8.3 rerun;
- Phase 11.9 or Phase 12;
- a provider, model, credential or product-default change;
- marking the draft pull request ready, merging it or releasing a package;
- an external comparison, public-alpha or superiority claim.

Even a future Tavily-only 12/12 pass would be observed-case calibration only.
It could justify at most reviewing a separately frozen generation
availability/schema validation. Phase 11.9 would still require a fresh,
non-overlapping protocol, a new traffic ceiling and a separate explicit user
authorization. Phase 12 remains sealed throughout.

Users retain provider, model and credential choice. The release decision
remains no-go.
