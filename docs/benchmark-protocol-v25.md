# EvidenceMesh benchmark protocol v25

## Phase 11.8.9 — offline retrieval-recovery candidate

Status: pre-registered offline engineering protocol. The committed v1 runner
performs local synthetic conformance only. A later, separately reviewed
non-scoring import may make public fixed-corpus assets available, but real
external scoring remains disabled until every asset, license and
suite-specific scoring rule in this protocol has an authoritative lock. The
evaluation itself performs no network, provider, search-API or model request,
binds no secret and does not authorize live traffic.

## 1. Purpose and evidence boundary

The one-shot Phase 11.8.8 live calibration completed all 24 authorized Tavily
attempts but failed five quality gates:

- selected proxy coverage was 18/24, below the required 20/24;
- v2 projected proxy coverage was 17/24, below 20/24;
- v2 retained 17/18 selected hits, or 94.4444%, below 95%;
- v2 gained only +1 against equal-cap, below +2; and
- v2 gained 0 against v1, below +2.

The diagnostic status was `retrieval_limited_inconclusive`. Repeating the same
live experiment would spend traffic without creating an independent
confirmation set.

Phase 11.8.9 therefore develops exactly one answer-blind retrieval candidate,
`retrieval_candidate_v3`, and evaluates its deterministic fixed-corpus
behavior against one frozen control. It also makes loss at each stage visible:

`raw -> fused -> eligible -> selected -> projected`

The phase has three distinct evidence classes:

1. local conformance fixtures prove only implementation and accounting
   invariants;
2. the 24 previously observed Phase 11.7/11.8 selectors are permanently
   development/diagnostic data; and
3. revision- and checksum-pinned BRIGHT and BrowseComp-Plus retrieval-only
   assets provide external fixed-corpus evaluation.

Neither fixture success nor a Phase 11.8.9 external pass proves end-to-end
answer quality, live Web quality, citation entailment, generalization to
future Web content, or competitive superiority.

## 2. Immutable historical facts and locks

The following facts are historical inputs, not scores to be repaired:

- observed-case manifest:
  `benchmarks/data/phase11_7_fresh_confirmation_v1.json`;
- observed-case manifest SHA-256:
  `da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e`;
- observed selector count: exactly 24;
- Phase 11.8.8 live protocol:
  `docs/benchmark-protocol-v24.md`;
- Phase 11.8.8 live protocol SHA-256:
  `e63ab4b3f25865890458abd2a001ce3428f9a3ca8c4f1a1a166f25432d1a8dc9`;
- Phase 11.8.8 aggregate JSON:
  `benchmarks/results/phase11_8_8_live_projection_calibration_2026-07-30.json`;
- Phase 11.8.8 aggregate JSON SHA-256:
  `03e0ad7ef2d4859848c3b4d4d8bf9d25714b9d311741f15a91ec9b3311aca25f`;
- Phase 11.8.8 v2 projector:
  `benchmarks/phase11_8_8_projection_candidate.py`;
- v2 projector SHA-256:
  `117968687a0c0c150acef42f997967d10b04006d14ed0efa9de87c9c08b1909e`.

The 8/13 Phase 11.8.8 result and every underlying aggregate count remain
immutable. Phase 11.8.9 must not rewrite, relabel, rescore or replace that
result.

The SHA-256 of each authority file and the canonical SHA-256 of the complete,
sorted source-lock set are the byte authority for this protocol, the v3
candidate, control adapter, asset manifest, fixture, runner, tests and
workflow. Any mismatch is a fail-closed preflight error.

The GitHub protocol-lock commit is a publication reference, not something the
offline runner can authenticate from an arbitrary 40-character argument. The
runner must label that reference as externally verified or unverified. The
publication process verifies through GitHub that the referenced commit
contains the exact locked bytes and that the pull request remains a draft.
Neither the commit reference nor Gate 1 may claim runner-side verification
when only syntax was checked.

## 3. Permanent treatment of the 24 observed cases

The 24 Phase 11.7 selectors and every later observation derived from them are
permanently classified as `development_diagnostic_only`.

They may be used only to:

- preserve the historical aggregate funnel and no-go facts;
- define generic failure categories;
- exercise schema compatibility without question, answer or retrieved-content
  disclosure; and
- motivate answer-blind engineering hypotheses.

They must not be:

- called fresh, hidden, holdout, confirmation or test data;
- used to tune a threshold after observing a candidate outcome;
- counted in a BRIGHT or BrowseComp-Plus metric;
- combined with external scores into a headline number;
- queried through Tavily or any other provider in this phase;
- re-materialized from SimpleQA for candidate evaluation;
- used to justify a quality-profile or product-default change; or
- used for a release, merge or superiority decision.

No aggregate improvement on these 24 cases can satisfy an external quality
gate. If any report mentions them, it must label them as previously observed
development diagnostics and keep their metrics separate.

## 4. Phase 12 hard no-access boundary

Phase 12 remains completely outside the Phase 11.8.9 authority. The runner,
candidate, asset importer, tests and workflow paths reachable from the
registered Phase 11.8.9 CLI must not open, stat, hash, parse, copy, select,
enumerate, log, score or otherwise access any Phase 12 manifest, selector,
row, question, answer, result or artifact.

This prohibition applies even to check-only and failure paths. An already
known historical filename or checksum may appear in documentation or a deny
list, but code in this phase may not use it to inspect the corresponding
resource.

Tests must enforce a deny-by-default path and identifier policy. Any attempted
Phase 12 access is a blocking failure, not a warning.

## 5. Permitted fixed-corpus assets

### 5.1 External suites

Exactly two external integrations are in scope:

1. **BRIGHT**, restricted to retrieval evaluation over its published fixed
   query, corpus and relevance-judgment assets; and
2. **BrowseComp-Plus**, restricted to its retrieval-only fixed corpus, query
   and relevance-judgment assets.

No browsing-agent, answer-generation, judge-model or end-to-end report score
is part of this phase.

Before any evidence-bearing evaluation, one committed asset-lock manifest
must define for every consumed upstream object:

- benchmark and split;
- canonical upstream project;
- immutable commit, tag or dataset revision;
- repository-relative upstream path or immutable object identifier;
- exact byte length and SHA-256;
- media type and compression type;
- expected query, document and qrel counts;
- document-identifier normalization rule;
- license identifier and redistribution policy; and
- the local logical role: query, corpus, qrel or metadata.

The suite policy lock must additionally define:

- BRIGHT's twelve task/domain splits, its excluded-query identifiers and an
  unweighted aggregate over the twelve task-level nDCG@10 values;
- BrowseComp-Plus evidence-qrel and gold-qrel tracks as separate reported
  results, with neither silently substituted for or averaged into the other;
- the exact TREC iteration token, rank/score tie policy and gain function;
- zero-result and no-relevant-document handling; and
- every accepted upstream field alias, including document-identifier
  normalization.

A moving branch, mutable `latest` URL, unpinned package version, glob-expanded
remote object, timestamp-selected snapshot or checksum learned after scoring
is forbidden.

If an upstream asset, revision, license or checksum is ambiguous, that suite
is `not_evaluated` and every gate requiring it fails. No mirror or alternative
version may be silently substituted.

### 5.2 Acquisition boundary

Evaluation and ordinary pull-request validation are network-independent and
make no evaluation network request. The workflow does not claim a host-level
network sandbox; the zero-traffic boundary is enforced by fixed local inputs,
closed executable-source capability audits, absent provider/model credentials
and explicit traffic accounting. Acquisition, if needed, is a separate
non-scoring import operation and may perform only bounded HTTPS GET transfers
for the exact public objects in the asset-lock manifest.

The importer:

- accepts no credential, cookie, authorization header or signed private URL;
- invokes no provider, search API, model API or telemetry endpoint;
- follows only explicitly allowlisted public redirects;
- enforces per-object and total byte ceilings before extraction;
- verifies SHA-256 before parsing or extraction;
- parses the exact same bounded bytes that were hashed, without a second
  path-based read that could race validation;
- rejects archive traversal, links and undeclared archive members;
- writes into a caller-supplied asset directory, never the source tree by
  default; and
- records acquisition provenance without query or document content.

Imported bytes become admissible only after all locks pass. Infrastructure
package installation and source checkout are not benchmark traffic, but they
must not be misreported as evaluation activity.

### 5.3 Ordinary pull-request validation

Ordinary pull-request validation uses only committed local conformance
fixtures. It must not download BRIGHT, BrowseComp-Plus or any other corpus,
and it must bind no secret.

Conformance success is reported as `engineering_conformance_only`; it is not
an external benchmark pass. If the complete locked external assets are absent,
the runner must return `external_evaluation_not_run`, and the overall
Phase 11.8.9 quality decision remains no-go.

The v1 adapter must fail closed for official benchmark content. A synthetic
bundle may validate parsing and metric oracles, but self-declared local hashes
must never unlock `real_external_score`. Enabling real scoring requires a new
reviewed asset-lock registry containing authoritative upstream revisions,
object identifiers, byte lengths, SHA-256 values, counts, licenses and the
suite policies above.

## 6. Frozen control and sole v3 candidate

The comparison has exactly two arms:

| Arm | Role |
|---|---|
| `pre_v3_pipeline_control` | newly registered uniform lexical/RRF control selection v1 followed by the hash-locked Phase 11.8.8 projector v2 |
| `retrieval_candidate_v3` | sole new Phase 11.8.9 selection v3 followed by its frozen source-preserving projector v3 |

Both arms receive byte-identical queries, corpus records, relevance-unaware
metadata and resource budgets. Both are evaluated on the same query order and
qrels. The control implementation and parameters are frozen before the first
external candidate score is computed.

The control selection is a transparent Phase 11.8.9 baseline, not a claim that
the same retrieval implementation existed historically in product code. The
historical component of the control is the independently hash-locked Phase
11.8.8 projector v2.

Recall and nDCG at `raw`, `fused`, `eligible` and `selected` isolate retrieval
behavior and are the only metrics used for Gates 13–16. Projection retention
is reported separately for Gate 17. Because the two arms use their registered
projectors, projected-stage differences must not be described as retrieval
causality.

There may be no v3a/v3b variants, per-suite parameter sets, result-dependent
fallback, post-score threshold search or selection of the best seed. Exactly
one frozen parameterization in the candidate source and one candidate source
hash apply to local fixtures, BRIGHT and BrowseComp-Plus.

## 7. Answer-blind v3 contract

The candidate may inspect only:

- the current query text;
- fixed-corpus document text and public retrieval metadata;
- corpus-wide statistics computed without relevance judgments;
- deterministic configuration; and
- stage outputs produced from those inputs.

It must not receive, inspect or infer behavior from:

- reference answers or answer fragments;
- qrels, relevant-document identifiers or relevance grades;
- benchmark scores or per-query outcomes;
- case labels, hidden sentinels or dataset row positions;
- historical hit/miss outcomes from the 24 observed cases;
- control outcomes for the current query;
- Phase 12 identifiers or content; or
- model-generated annotations, embeddings, reranking scores or summaries.

Qrels are loaded into an isolated scorer only after both arms have finalized
all five stage outputs for a query. Tripwire objects or an equivalent
interface test must prove that candidate code cannot access scorer-only
fields.

The candidate is deterministic and non-generative. Permitted answer-blind
signals include:

- Unicode-safe token and phrase matching;
- corpus-derived inverse document frequency;
- exact preservation and additional weight for numbers, dates, units,
  acronyms, proper-name-like spans and rare multi-token phrases;
- deterministic proximity and passage coverage;
- fixed reciprocal-rank or score fusion;
- canonical-document deduplication;
- fixed redundancy penalties; and
- deterministic source-group diversity subject to relevance-independent
  constraints.

Learned rerankers, hosted or local model inference, embedding generation,
query expansion by a model, answer synthesis and semantic judging are
forbidden. Public precomputed model outputs may not be used as a substitute.

## 8. Five-stage funnel contract

Every arm emits all five stages for every evaluated query:

1. `raw`: bounded initial candidates from the fixed local index;
2. `fused`: canonical documents after deterministic channel fusion and
   deduplication;
3. `eligible`: fused documents that pass fixed, relevance-independent content
   and metadata checks;
4. `selected`: the final ranked set, capped at 20 canonical documents; and
5. `projected`: source-preserving evidence excerpts and citations rendered
   from selected documents under the existing 12,000-character total budget.

The following invariants are blocking:

- every fused item has one or more raw parents;
- every eligible item has exactly one canonical fused parent;
- every selected item is eligible;
- every projected citation belongs to one selected item;
- canonical identifiers are unique within fused, eligible and selected;
- no stage invents a document, citation, title, URL, token, number or source
  span;
- selected contains at most 20 items;
- projected evidence is at most 12,000 rendered characters, including headers
  and separators;
- projected text consists only of exact ordered substrings of its source,
  apart from one fixed visible omission separator; and
- stable input bytes always produce stable stage order and bytes.

For every arm and suite, the aggregate report records:

- query count;
- total and mean item count at each stage;
- zero-result query count at each stage;
- duplicate collapses between raw and fused;
- fixed-rule exclusions between fused and eligible;
- truncations and diversity exclusions between eligible and selected;
- selected-to-projected citation retention;
- Recall@5, Recall@10, Recall@20, Recall@100 and Recall@1000 at each
  document-bearing stage, with cutoffs above a stage cap naturally equal to
  the full retained ranking for that stage;
- nDCG@5, nDCG@10 and nDCG@20 at each document-bearing stage; and
- stage-to-stage absolute and relative loss.

Metrics use canonical document identifiers and the upstream relevance grades.
The gain function is locked per suite and must match its official TREC
evaluator. For the registered BRIGHT and BrowseComp-Plus retrieval tracks this
means linear TREC gains; binary judgments naturally reduce to zero/one gains.
Ranks are derived from the locked score/tie policy consistently across JSON,
JSONL and TREC inputs. A query with an empty run remains in the denominator and
scores zero. Missing qrels and queries with no defined relevant document
follow the upstream suite policy locked in the adapter; they may not be
silently dropped.

## 9. Projection recovery boundary

Projection remains answer-blind and source-preserving. It must allocate a
bounded, nonzero opportunity to every selected document whenever the fixed
budget can represent its citation header and minimum excerpt. Any document
that cannot be represented must be counted as an explicit projection drop.

For each suite:

`projected_relevant_retention =
relevant_selected_documents_represented_in_projection /
relevant_selected_documents`

A zero denominator is reported as undefined for that query and excluded only
from this retention ratio, never from selection metrics. The aggregate report
must separately state the number of defined and undefined queries.

The projector may use the query and selected source text but not qrels,
answers, benchmark identity, suite-specific parameters or prior outcomes.

## 10. Local conformance fixture

The committed fixtures are synthetic, small and non-probative. They contain no
SimpleQA, BRIGHT, BrowseComp-Plus or Phase 12 query, answer, qrel, identifier
or corpus text.

Together, the retrieval fixture, external-adapter fixture and adversarial
tests must cover at least:

- exact, phrase, acronym, numeric, date, unit and rare-token retrieval;
- Unicode and punctuation boundaries;
- duplicated canonical documents from multiple raw channels;
- deterministic fusion ties;
- empty, short, long and malformed documents;
- fixed eligibility exclusions;
- source-group diversity and a diversity tie;
- rejection of a zero selected limit, plus valid selected limits of one and 20;
- projection head, middle and tail evidence;
- exact 12,000-character and insufficient-budget boundaries;
- duplicate citation identifiers;
- missing qrels and binary versus graded relevance;
- no-relevant-document policy;
- archive/path traversal rejection in the asset validator;
- forbidden scorer-field tripwires;
- forbidden network, environment-secret and Phase 12 access; and
- two cold deterministic replays.

The fixture contains an exact machine-readable requirement registry spanning
retrieval, external-adapter and runner probes. Gate 9 passes only when every
registered test is actually executed against the exact locked test bytes and
all tests succeed; test names, AST shape, `assert True`-style placeholders or a
self-declared coverage label are insufficient. The runner records only an
aggregate receipt containing the locked source-set identifier, test count,
pass count and bounded status—never test output or fixture content. Fixture
sentinels are visible only to the fixture scorer. A fixture pass proves that
authored invariants hold; it is not evidence of real retrieval quality.

## 11. External evaluation procedure

For each locked suite, the runner:

1. validates all source hashes and the canonical source-set SHA-256, while
   reporting GitHub commit-reference verification as a separate publication
   check;
2. validates every asset byte length, SHA-256, count and identifier policy;
3. constructs deterministic local indexes without qrels;
4. freezes index manifests and corpus statistics;
5. runs the control for every included query;
6. runs v3 for the same queries under identical caps;
7. verifies byte-identical replay of both arms from a cold start;
8. loads qrels into the isolated scorer;
9. computes per-query metrics in memory;
10. aggregates metrics and fixed paired deltas;
11. performs privacy and traffic audits; and
12. writes one canonical aggregate-only JSON result.

Query order is the canonical upstream order with a stable document-identifier
tie break where needed. No concurrency-dependent ordering is permitted.
Index and result serialization use canonical UTF-8 JSON with sorted keys,
fixed numeric precision and no wall-clock timestamp in the reproducibility
payload.

Any crash, missing query, duplicate query identifier, unknown qrel document,
asset mismatch, non-finite score, replay mismatch or incomplete suite makes
that suite fail. Partial metrics may be preserved only as
`inadmissible_diagnostic`; they cannot satisfy a gate.

## 12. Exact traffic and secret accounting

The evaluation, conformance workflow and candidate obey these hard ceilings:

| Dimension | Plan | Hard ceiling |
|---|---:|---:|
| Evaluation network requests | 0 | 0 |
| Tavily requests | 0 | 0 |
| Other search-provider requests | 0 | 0 |
| Gemini requests | 0 | 0 |
| Other model requests | 0 | 0 |
| Local model inference calls | 0 | 0 |
| Token-count API requests | 0 | 0 |
| Follow-up document fetches | 0 | 0 |
| Retries | 0 | 0 |
| Fallbacks | 0 | 0 |
| Repairs | 0 | 0 |
| Bound secrets | 0 | 0 |
| Cache reads from live-search phases | 0 | 0 |
| Cache writes to live-search phases | 0 | 0 |

The optional fixed-asset importer accounts separately for declared public
asset transfers and must never run inside evaluation. Import traffic cannot be
reported as search or model traffic, and it cannot satisfy a quality gate by
itself.

The workflow has read-only repository permission. It must not reference a
provider or model secret, expose a live flag, invoke a provider adapter, or
enable an authorization marker.

## 13. Determinism and resource fairness

Control and candidate use:

- the same machine class and process limits within a paired run;
- the same fixed corpus bytes and query bytes;
- the same maximum 20 selected documents;
- the same 12,000-character projected budget;
- no warm result cache shared from one arm to the other; and
- separately built or equivalently reset deterministic index state.

At least two independent-process replays are required. The runner's
same-process repetitions are labeled as in-process determinism checks, not
cold replays. The read-only workflow performs two separate CLI processes and
requires their canonical stage aggregates, rankings, metrics, decisions and
result payload to be byte-identical.
Durations, peak memory and index size may be recorded as non-gating aggregate
diagnostics outside the canonical reproducibility payload.

For a complete external run, the runner must report build time, query time,
peak resident memory and index bytes for cost visibility. These fields are
explicitly `not_applicable_without_external_assets` during local conformance;
they must not contain fabricated zero measurements. Phase 11.8.9 sets no
performance superiority claim. A later protocol may add resource gates only
after measurements exist.

## 14. Public result and privacy boundary

The public JSON and interpreted Markdown report are aggregate-only. The
privacy/schema audit is run over the complete final payload, including gates
and decisions, rather than only an intermediate prefix. They may contain:

- protocol, benchmark, split and arm names;
- upstream revision, asset and source hashes;
- aggregate query, corpus, qrel and stage counts;
- aggregate Recall, nDCG, retention and paired deltas;
- fixed paired confidence intervals as descriptive diagnostics;
- aggregate resource measurements;
- bounded aggregate failure categories;
- gate decisions and the final no-go/pass-for-engineering decision.

They must not contain:

- query or document identifiers;
- query hashes, answer hashes or qrel identifiers;
- dataset row indexes or selector positions;
- questions, answers, qrels, titles, URLs, snippets or document text;
- raw, fused, eligible, selected or projected per-query records;
- per-query scores, outcomes, latencies, failures or packet hashes;
- absolute filesystem paths;
- environment values, credentials, headers or raw exception text;
- content from the 24 observed selectors; or
- any Phase 12 identifier, row, content or outcome.

Per-query values may exist transiently in scorer memory only. They must not be
written to disk, logged, uploaded, committed or included in exceptions.
Progress output is limited to aggregate counts and bounded error categories.

If upstream licenses prohibit redistribution, corpus and qrel bytes remain
outside Git and outside artifacts. Only allowed aggregate measurements and
their hashes may be published.

## 15. Exactly nineteen blocking gates

The complete external quality evaluation passes only if all 19 gates pass in
one source-locked run. Local synthetic conformance may pass the local subset
(Gates 1–9, 12, 18 and 19), but it remains
`engineering_conformance_only`; Gates 10, 11 and 13–17 fail as
`not_evaluated` and the quality decision remains no-go:

1. every historical and source lock matches, the canonical source-set
   SHA-256 reproduces, and any GitHub commit reference is truthfully labeled
   as externally verified or unverified;
2. the Phase 11.8.8 8/13 no-go and its aggregate counts remain unchanged;
3. the 24 observed selectors are labeled and used only as development
   diagnostics, never as external confirmation;
4. no Phase 12 resource is accessed by any Phase 11.8.9 code path;
5. evaluation network, Tavily, provider, model, local inference, retry,
   fallback, repair and live-cache counts are all zero; no relevant
   provider/model credential name is present in the process environment; and
   the imported executable modules match the locked repository paths and
   bytes;
6. v3 has exactly one frozen answer-blind parameterization for both external
   suites, the control uses selection v1 plus the locked projector v2, and
   scorer-only tripwires remain inaccessible;
7. raw, fused, eligible, selected and projected lineage, uniqueness, limits
   and source-preservation invariants pass for every query;
8. in-process control/v3 repetitions are byte-identical and the workflow
   contract requires two independent-process canonical replays to match;
9. every local conformance and adversarial fixture behaves as registered;
10. BRIGHT assets, counts, query coverage and scoring policy validate
    completely, with no dropped or duplicated evaluated query;
11. BrowseComp-Plus retrieval-only assets, counts, query coverage and scoring
    policy validate completely, with no dropped or duplicated evaluated
    query;
12. metric implementations match hand-computed fixture oracles for Recall at
   5, 10, 20, 100 and 1000, and nDCG at 5, 10 and 20;
13. v3 BRIGHT nDCG@10 exceeds control BRIGHT nDCG@10 by at least 0.010
    absolute;
14. v3 BrowseComp-Plus nDCG@10 exceeds control BrowseComp-Plus nDCG@10 by at
    least 0.010 absolute;
15. the unweighted mean of the two v3 nDCG@10 deltas is at least 0.020
    absolute;
16. on each external suite, v3 Recall@20 is no more than 0.005 absolute below
    control Recall@20;
17. on each external suite, v3 projected relevant-document retention is at
    least 0.990;
18. the aggregate-only report passes every privacy and license prohibition;
19. the exact phase source scope contains no product-default, historical,
    Phase 11.9, Phase 12, merge, release or superiority mutation authority;
    the GitHub publication check separately confirms that the PR remains a
    draft.

The fixed paired confidence intervals are reported for transparency but are
not used to replace or relax gates 13–17. Missing data, absent external assets,
an incomplete suite, an undefined aggregate denominator, an indeterminate
gate or fixture-only execution is a failure. There is no partial or advisory
quality pass.

## 16. Decision semantics

Possible top-level outcomes are:

- `engineering_conformance_only`: all local gates pass, but one or both
  external suites were not executed;
- `external_fail`: external execution completed but at least one of the 19
  gates failed;
- `offline_engineering_pass`: all 19 gates passed; or
- `invalid`: provenance, traffic, privacy, Phase 12, determinism or source
  locks, or any required local conformance gate, failed.

`offline_engineering_pass` means only that one frozen, answer-blind v3
candidate improved the two pinned fixed-corpus retrieval evaluations under
the registered budgets. It does not establish live Web improvement or
end-to-end deep-research quality.

Regardless of outcome, Phase 11.8.9 does not authorize or unlock:

- a Phase 11.9 protocol or execution;
- Phase 12 inspection, execution or scoring;
- another Tavily or other provider run;
- a model-assisted benchmark;
- a product-default, provider, model or credential change;
- marking pull request #1 ready for review;
- merging pull request #1;
- publishing a package, release or public alpha; or
- claiming that EvidenceMesh is best, superior or state of the art.

The pull request remains draft and the release decision remains no-go. Any
later phase requires a separate protocol and a new explicit `GO`.
