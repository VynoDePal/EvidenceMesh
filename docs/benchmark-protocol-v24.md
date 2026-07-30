# EvidenceMesh benchmark protocol v24

## Phase 11.8.8 — one-shot Tavily-only live projection calibration

Status: pre-registered live protocol. It is frozen before the first scored
Tavily request. The explicit `GO Phase 11.8.8 live` authorization is scoped to
the one-shot authorization commit and workflow run defined below. Publishing
the protocol-lock commit alone makes no provider request and does not consume
that authorization.

## 1. Purpose and evidence boundary

Phase 11.8.8 is corrective calibration on the 24 Phase 11.7 cases that have
already been observed. It is not fresh confirmation.

Phase 11.8.3 established that:

- the selected Tavily packet contained the normalized reference-answer proxy
  in 19/24 cases;
- equal-cap and the v1 projector each retained that proxy in 17/24 cases;
- its frozen 20/24 projection floor was therefore unreachable on that exact
  selected packet.

Protocol v23 subsequently froze the answer-blind, source-preserving v2
projector and passed all 14 offline engineering gates. Its authored synthetic
fixtures do not prove quality on Web results.

This live calibration makes one new Tavily attempt for each of the same 24
observed selectors, then compares equal-cap, v1 and v2 locally on one shared
selected packet. It makes no generation, judging, embedding, token-count or
other model request. It measures only retrieval availability and an explicit
reference-answer substring retention proxy.

A pass can show that v2 meets the pre-registered projection gates on this
single observed-case Tavily draw. It cannot establish semantic answer
correctness, citation correctness, generalization, competitive superiority or
product-market quality.

## 2. Immutable suite, dataset and source locks

### 2.1 Observed calibration suite

- Manifest:
  `benchmarks/data/phase11_7_fresh_confirmation_v1.json`
- Manifest SHA-256:
  `da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e`
- Suite: `evidencemesh-phase11-7-fresh-confirmation-v1`
- Selector count: exactly 24
- Status: previously observed calibration data

The 24 selectors and their order are immutable. The runner may materialize
exactly those 24 rows and no other benchmark row.

### 2.2 Immutable SimpleQA dataset

- Dataset: OpenAI SimpleQA test set
- Source repository commit:
  `652c89d0ca9df547706735883097e9537d40dc47`
- Source file blob:
  `0fc266800a87ace55ec192c9a91cafe92fef7b48`
- Source URL:
  `https://openaipublic.blob.core.windows.net/simple-evals/simple_qa_test_set.csv`
- Dataset SHA-256:
  `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032`

The workflow downloads this CSV once before binding the Tavily credential and
must verify the exact SHA-256 before any provider attempt. A missing,
unavailable or mismatched dataset aborts with zero Tavily attempts. No mirror,
updated revision or locally modified dataset may be substituted.

This one static dataset transfer is recorded separately from scored provider
traffic. It is not a Tavily, search or model request. Package installation,
repository checkout and GitHub artifact transport are CI infrastructure and
must not be misreported as scored benchmark traffic.

### 2.3 Phase 12 procedural reserve boundary

- Reserve manifest:
  `benchmarks/data/phase12_untouched_reserve_v1.json`
- Reserve manifest SHA-256:
  `472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee`
- Selector count: exactly 96

The Phase 12 selectors are already present in a public repository. They are
therefore not secret, hidden or statistically blind, and this protocol makes
no such claim. They remain a pre-registered procedural reserve only: this run
may checksum the reserve manifest and stream through the public CSV to resolve
the 24 authorized selectors, but it must not retain, select, query, search,
score, project, log or report any reserved row. Phase 12 execution remains
unauthorized.

### 2.4 Implementation locks

- Historical Phase 11.8.3 result:
  `benchmarks/results/phase11_8_3_factorial_2026-07-30.json`
- Historical result SHA-256:
  `167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c`
- Equal-cap and v1 implementation:
  `benchmarks/phase11_8_2_candidate.py`
- Equal-cap and v1 SHA-256:
  `0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e`
- v2 implementation:
  `benchmarks/phase11_8_8_projection_candidate.py`
- v2 SHA-256:
  `117968687a0c0c150acef42f997967d10b04006d14ed0efa9de87c9c08b1909e`
- Offline protocol:
  `docs/benchmark-protocol-v23.md`
- Offline protocol SHA-256:
  `11a8fe99a3e418eb4161978928f2d682a2adcf6b59b3bcc7b7641c26b601a653`
- Live dependency-lock manifest:
  `benchmarks/data/phase11_8_8_live_projection_dependency_locks_v1.json`
- Live dependency-lock manifest SHA-256:
  `0d6ee7f91689fc2679ee0e5c6a2857d25219d5a71cd559d248875d1074693a00`
- Live runner:
  `benchmarks/run_phase11_8_8_live_projection_calibration.py`
- Live runner SHA-256:
  `fabad5e66246a10f0f024201c1d031de22e4958141b57cf731393bd6cc936ac3`
- Targeted tests:
  `tests/test_phase11_8_8_live_projection_calibration.py`
- Workflow:
  `.github/workflows/phase11-8-8-live-projection-calibration.yml`

The dependency-lock manifest excludes the live runner, test, workflow and this
protocol so that no circular source-hash dependency exists. The runner locks
that manifest and validates every file listed in it. The workflow independently
locks the final protocol, dependency manifest and runner from the
protocol-lock commit before it can expose a provider credential.

Any source-lock mismatch is a preflight failure with zero Tavily attempts.
Historical results are immutable and must not be rescored or rewritten.

## 3. Retrieval and shared-packet contract

For each observed selector, in its frozen order:

1. materialize its question and reference answer from the hash-verified
   dataset;
2. send the unchanged question as one Tavily search query;
3. request at most 20 provider results;
4. deterministically select at most 20 results with at most three results per
   registrable domain;
5. create one raw packet and one selected packet;
6. give the byte-identical selected packet, in the same order, to equal-cap,
   v1 and v2;
7. project all three arms locally; and
8. only after projection, compute the frozen substring proxies.

Provider: Tavily only. Search profile: Web. Document fetching, cache reads,
cache writes, follow-up search, result-dependent query rewriting and adaptive
retrieval are forbidden.

The three projectors receive no reference answer, answer fragment, answer
hash, case identifier, row index, prior outcome, score or Phase 12 selector.
Scoring data is introduced only after every projection for that shared packet
is complete.

The exact projection order is:

1. `equal_cap`;
2. `rank_weighted_query_window_head_tail_v1`;
3. `fair_prefix_rarity_passage_pack_v2`.

Their frozen settings are:

- total rendered evidence budget: 12,000 characters;
- maximum evidence text per block: 1,500 characters;
- v1 and v2 minimum allocation: 192 characters;
- deterministic v2 replays: three.

Headers and separators count against the v2 rendered budget. V2 must remain
answer-blind, deterministic and source-preserving; citation identifiers and
metadata must remain attached to their original blocks.

## 4. Exact traffic, timeout and fail-fast accounting

### 4.1 Plan and hard ceilings

| Dimension | Plan | Hard ceiling |
|---|---:|---:|
| Observed selectors | 24 | 24 |
| Logical retrieval operations | 24 | 24 |
| Tavily HTTP attempts | 24 | 24 |
| Tavily requests per selector | 1 | 1 |
| Static dataset HTTP transfers | 1 | 1 |
| Gemini requests | 0 | 0 |
| Other model requests | 0 | 0 |
| Token-count requests | 0 | 0 |
| Retries | 0 | 0 |
| Fallbacks | 0 | 0 |
| Repairs | 0 | 0 |
| Follow-up document fetches | 0 | 0 |

The runner records logical and physical accounting separately:

- `logical_operations_planned`: always 24;
- `logical_operations_started`: incremented immediately before the single
  provider transport invocation for a selector;
- `logical_operations_completed`: incremented only when that selector yields a
  valid completed Tavily response, including a valid response with no useful
  result;
- `tavily_http_attempts_actual`: incremented at the transport boundary before
  waiting for a response;
- `tavily_http_attempts_maximum`: always 24.

At every point:

`logical_operations_completed <= logical_operations_started ==
tavily_http_attempts_actual <= 24`.

A complete run has all three actual counts equal to 24. An aborted run reports
the actual prefix attempted; it must never claim the 24-request complete-run
plan as observed traffic.

### 4.2 Timeouts and pacing

- connect timeout: 5 seconds;
- read timeout: 12 seconds;
- write timeout: 10 seconds;
- connection-pool timeout: 5 seconds;
- outer wall ceiling per retrieval operation: 30 seconds;
- fixed delay after each successful non-final retrieval: 0.5 seconds.

The HTTP client and all adapters must have automatic retries disabled.

### 4.3 First-failure abort and strict no-rerun rule

The first authentication error, HTTP error including HTTP 429, transport
error, timeout, malformed provider response, accounting mismatch or invariant
failure aborts the entire run. There is no retry of that request, no attempt
for a later selector and no partial recovery.

A valid successful provider response containing zero selected results is a
completed retrieval outcome and is scored as such. It is not a transport
failure and does not permit another request.

The authorized workflow must run with `github.run_attempt == 1`. GitHub
workflow reruns, failed-job reruns, selective selector reruns, resume files,
cached replay and manual continuation are forbidden after either a pass or a
failure. The output path must not already exist. Any second live execution
would require a new protocol version, a new traffic ceiling and a fresh
explicit authorization. A second execution under altered repository state is
outside this protocol and its result is inadmissible.

## 5. One-shot authorization and commit lineage

Live traffic is authorized only through two consecutive commits on draft pull
request #1, branch `agent/evidencemesh-v0.1`, in
`VynoDePal/EvidenceMesh`.

### Commit A — protocol lock

Commit A contains the final v24 protocol, dependency-lock manifest, live
runner, targeted tests and live workflow. It performs lock validation only,
binds no Tavily secret and makes no Tavily request. Its workflow still contains
the exact inert placeholder `__FROZEN_LOCK_COMMIT_SHA__`.

### Commit B — authorization consumed once

Commit B must:

- have Commit A as its single parent;
- use the exact subject
  `chore(benchmarks): authorize Phase 11.8.8 live once`;
- add
  `.github/authorizations/phase11-8-8-live-projection-calibration-once.json`;
- replace only `__FROZEN_LOCK_COMMIT_SHA__` in the live workflow with the full
  Commit A SHA;
- change no other path or workflow value.

The marker records Commit A, the 24-attempt ceiling, zero model requests,
zero retry/fallback/repair, and the one-shot/no-rerun boundary. It contains no
credential. The workflow must verify the repository, pull-request number,
branch, same-repository head, single parent, exact subject, exact two-path
diff, marker schema, pinned Commit A SHA and `github.run_attempt == 1` before
exposing the Tavily secret.

`run_attempt == 1` is necessary but not sufficient because a branch rewind can
create another first-attempt workflow run. The authorization job therefore has
read-only Actions access and must inspect the complete workflow-run history
returned by GitHub before exposing the provider secret. Excluding only the
current run, any retained prior run whose head commit has Commit A as its
single parent and the exact Commit B subject consumes the authorization and
blocks the current run. This applies both to replaying the same Commit B and to
recreating an equivalent Commit B with a different SHA. An unavailable,
incomplete, malformed or ambiguous history response fails closed. The
successful history check is included in the runner attestation.

This guard prevents normal reruns and branch-rewind replays while GitHub
retains the audit history. It does not claim resistance to a repository
administrator deliberately deleting workflow history or refs, or replacing
the workflow itself; those actions introduce new out-of-band authority,
invalidate the one-shot attestation and make any resulting benchmark
inadmissible.

The live job checks out Commit A, not mutable Commit B source. The only
credential available to that job is `EVIDENCE_MESH_TAVILY_KEY`, scoped to the
single live step after every repository, dataset and authorization preflight
passes. No Gemini or model secret is bound.

Ordinary pull-request events, Commit A by itself, a later synchronize event, a
changed marker, an amended authorization commit, a workflow rerun, a dispatch,
a label, a fork, a replay after rewinding the branch or a recreated Commit B
must execute lock validation only or fail closed under the retained-history
threat model above. Commit B consumes the existing authorization exactly once.

## 6. Frozen metrics

The scorer normalizes the reference answer and evidence exactly as the locked
historical implementation defines, then computes:

- `selected_coverage`: cases where the proxy occurs anywhere in the shared
  selected packet;
- `equal_cap_coverage`: cases where equal-cap retains the proxy;
- `v1_coverage`: cases where v1 retains the proxy;
- `v2_coverage`: cases where v2 retains the proxy;
- `v2_selected_retention`: `v2_coverage / selected_coverage`;
- `v2_vs_equal_net_gain`: v2-only hits minus equal-cap-only hits across all 24
  paired cases;
- `v2_vs_v1_net_gain`: v2-only hits minus v1-only hits across all 24 paired
  cases.

The denominator for each absolute coverage is 24. The retention denominator is
the observed selected-packet hit count. A missing or zero denominator cannot
pass. Pairing is valid only within this run because all arms receive the same
selected packet.

These metrics are transparent substring proxies. They are not official
SimpleQA accuracy, semantic entailment, answer generation quality or proof
that a cited source supports a claim.

## 7. Public result and privacy boundary

The public JSON and interpreted Markdown report are aggregate-only. They may
contain:

- benchmark and protocol names;
- source, commit and artifact SHA-256 values;
- aggregate traffic, completion and projection counts;
- aggregate coverage, retention and paired win/loss/net counts;
- aggregate latency statistics;
- bounded aggregate failure categories;
- the 13 aggregate gate decisions and final no-go decision.

They must not contain:

- case identifiers;
- question hashes or reference-answer hashes;
- dataset row indexes or selector positions;
- absolute filesystem paths;
- per-case outcomes, per-case packet hashes, per-case latencies or
  per-case failures;
- questions, reference answers, generated answers or prompts;
- source titles, URLs, snippets, raw results, selected evidence or projected
  text;
- Tavily response bodies, raw exception text or request URLs;
- HTTP headers, credentials, secret names' values or environment values;
- Phase 12 case identifiers, rows or outcomes.

Private per-case values may exist transiently in runner memory only as needed
for aggregate scoring. They must not be written to disk, emitted to logs,
uploaded as an artifact, committed or included in an exception. Progress logs
may disclose aggregate counts only.

## 8. Exactly thirteen blocking gates

The calibration passes only if all 13 gates below pass in the same authorized
one-shot run:

1. every historical and dependency source lock matches, and the checked-out
   protocol, dependency manifest and runner match Commit A;
2. Commit B has the exact one-shot authorization lineage, subject, marker,
   two-path diff and first workflow-run attempt required by section 5;
3. the immutable dataset hash matches, exactly the 24 observed selectors are
   retained in frozen order, and no Phase 12 row is selected, retained or
   executed;
4. logical and physical accounting is internally exact, all 24 retrievals
   complete, actual Tavily HTTP attempts equal 24 and never exceed 24, with
   exactly one attempt per observed selector;
5. first-failure abort, no-rerun and no-cache rules hold, while model, Gemini,
   token-count, retry, fallback, repair and follow-up document-fetch counts
   all remain zero;
6. equal-cap, v1 and v2 receive a byte-identical selected packet in the same
   order in 24/24 completed cases;
7. v2 is answer-blind, source-preserving, metadata-preserving, deterministic
   across three replays and exactly budget-compliant in 24/24 cases;
8. selected-packet proxy coverage is at least 20/24;
9. v2 projected proxy coverage is at least 20/24;
10. v2 retains at least 95% of proxy hits present in selected evidence;
11. v2 paired net gain against equal-cap is at least +2 across all 24 cases;
12. v2 paired net gain against v1 is at least +2 across all 24 cases;
13. the aggregate-only public artifact passes every privacy prohibition in
    section 7 and preserves all historical, Phase 11.9, Phase 12, merge,
    release and superiority boundaries.

Missing data, an aborted run, fewer than 24 completed retrievals, a missing
denominator or an indeterminate gate is a failure. There is no partial or
advisory pass.

## 9. Interpretation and decision semantics

If selected coverage is below 20/24, the run is retrieval-limited. If selected
coverage reaches 20/24 but v2 coverage is below 20/24 or retention is below
95%, the run is projection-limited. Paired gains may be interpreted only
against equal-cap and v1 on this run's shared packet.

The new scores must not be compared causally with the historical 17/24 scores:
the underlying Tavily draws differ. Historical results remain unchanged.

A 13/13 pass proves only that this frozen v2 projector met the registered
retention conditions on one one-shot Tavily draw over already-observed cases.
Even a pass does not authorize or unlock:

- a Phase 11.9 protocol or live run;
- Phase 12 inspection, execution or scoring;
- another Phase 11.8.8 live run;
- a generation or model benchmark;
- a provider, model, credential or product-default change;
- marking the draft pull request ready for review;
- merging the pull request or publishing a package;
- public alpha, external comparison or any claim that EvidenceMesh is the
  best or superior search/deep-research tool.

Any later phase requires a separate protocol and explicit `GO`. The pull
request remains draft and the release decision remains no-go regardless of
this result.
