# EvidenceMesh benchmark protocol v27

## Phase 11.8.10B-P0 — policy and comparability lock

Status: frozen metadata-only methodology. This protocol may produce an
engineering `PASS` for the lock while the evidence-quality decision remains
`no_go`. It does not authorize asset acquisition, payload inspection, query
decryption, evaluation, publication, a provider or model request, a score, a
merge, a release, Phase 11.9, Phase 12, or a quality claim.

## 1. Decision carried forward

Phase 11.8.10A completed the identity and integrity reconnaissance but left
four blocking classes unresolved: component-level rights, BRIGHT snapshot to
leaderboard equivalence, BRIGHT evaluator pinning, and evaluator pinning for a
reproducible BrowseComp-Plus comparison. Phase 11.8.10B-P0 resolves the policy
decision, not those upstream facts.

The target is an **officially comparable external score**. An internal score
on a convenient snapshot is not an acceptable substitute. No benchmark asset
may be acquired until its candidate suite independently satisfies both the
rights-clearance gate and the comparability gate.

A single authoritative suite may be sufficient in a later phase. This is a
future scope rule, not an admission decision: neither BRIGHT nor
BrowseComp-Plus is admitted now, and one suite cannot inherit the other
suite's clearance.

## 2. Frozen predecessor

This protocol is bound to the following Phase 11.8.10A state:

- repository tree: `7a774664442caa9201b419fb219d47c6113a52a3`;
- protocol v26 SHA-256:
  `b97a215a6be2294a23db15c4183353371a185d7c11c738d7ca3894beb710bd77`;
- asset-lock manifest SHA-256:
  `8c470471e250df2f33bb6840bec27c5bdecb9f4ad7654142374c0eb4df615f2c`;
- object-inventory SHA-256:
  `d23f81e23e2e1c8e075de7647d7529ccaf9c3a787f8c18106e101d8abef57a3e`;
- source-lock SHA-256:
  `f7da0ef14f6b5fee788eb8139c9e62df13d6b51f23492fb9852da42463301094`;
- aggregate result SHA-256:
  `3e0c2d7e99778d71f773a980a4212cd44fd8960fd1ee7d142350867345c9310d`.

Any mismatch fails closed. P0 does not reinterpret, expand, or materialize the
37 objects inventoried by Phase 11.8.10A.

## 3. Research boundary and source budget

Only ten immutable primary metadata documents were consulted: five for
BRIGHT and five for BrowseComp-Plus. The hard ceiling is fifteen unique public
metadata documents, leaving at most five for a separately authorized follow-up.
Redirect targets, mirrors, search-result pages, payload files, query rows,
documents, answers, qrels, indexes and decrypted material do not count as
acceptable policy evidence and must not be accessed.

No benchmark payload was downloaded, opened or decrypted. No provider, model,
benchmark-search, retrieval, scoring or secret-bearing request was made.
Public-metadata consultation is accounted for by unique primary document, not
by an unverifiable transport-request count. Source claims in the P0 manifest
are limited to what the ten identified documents support.
Absence of a per-item rights map or an immutable evaluator configuration is
recorded as an unresolved fact, not converted into an assertion about rights
ownership or benchmark equivalence.

The seven GitHub documents are additionally identified by their Git blob
SHA-1. The three Hugging Face cards are identified by immutable repository
revision and path only; P0 did not fetch and locally hash their raw bytes.
Those locks therefore establish source identity and bounded provenance, not a
new local proof of external document-content integrity.

## 4. Candidate isolation

BRIGHT and BrowseComp-Plus remain independent candidates. Each candidate must
pass every applicable gate on its own:

1. immutable official asset identity;
2. component-level rights clearance adequate for the intended acquisition,
   local processing, reporting and non-redistribution posture;
3. an immutable mapping to the official comparison population and track;
4. an immutable evaluator implementation, dependency closure and scoring
   configuration;
5. an approved acquisition plan with bounded storage and no repository or CI
   artifact redistribution.

Failure of one candidate neither blocks later consideration of the other nor
permits evidence to be shared between them. P0 admits neither candidate.

## 5. BRIGHT decision

### 5.1 Primary metadata set

The BRIGHT review is limited to these five immutable documents:

1. [README](https://github.com/xlang-ai/BRIGHT/blob/d99e8391d967d4c2b3a74732530d2309e2fc92b6/README.md)
2. [LICENSE](https://github.com/xlang-ai/BRIGHT/blob/d99e8391d967d4c2b3a74732530d2309e2fc92b6/LICENSE)
3. [run.py](https://github.com/xlang-ai/BRIGHT/blob/d99e8391d967d4c2b3a74732530d2309e2fc92b6/run.py)
4. [retrievers.py](https://github.com/xlang-ai/BRIGHT/blob/d99e8391d967d4c2b3a74732530d2309e2fc92b6/retrievers.py)
5. [immutable dataset card](https://huggingface.co/datasets/xlangai/BRIGHT/blob/3066d29c9651a576c8aba4832d249807b181ecae/README.md)

### 5.2 Facts and inference

The code repository and dataset card declare CC-BY-4.0. The selected corpus
also contains source-derived material, while the consulted metadata does not
provide a component-by-component or item-by-item rights map sufficient for an
EvidenceMesh acquisition clearance. The declaration is preserved; clearance
is not inferred from it.

The pinned dataset snapshot declares 1,384 selected queries, while the prior
official-comparability reconnaissance identified an unresolved 1,398-query
publication population. The consulted metadata does not bind the public
leaderboard to the pinned 1,384-query snapshot.

The upstream scoring path relies on `pytrec_eval`, but the consulted immutable
code does not close the evaluator dependency to an exact version and scoring
semantics. An implementation-shaped metric description is not an immutable
evaluator lock.

### 5.3 P0 outcome

BRIGHT is `blocked`. Its component-rights gate, official population mapping
gate and evaluator lock gate are incomplete. Acquisition and evaluation are
forbidden, and no future value may be described as an official or
leaderboard-comparable BRIGHT score until those gates pass.

## 6. BrowseComp-Plus decision

### 6.1 Primary metadata set

The BrowseComp-Plus review is limited to these five immutable documents:

1. [README](https://github.com/texttron/BrowseComp-Plus/blob/046949032b0328319cc9a02663a759ec601d9402/README.md)
2. [LICENSE](https://github.com/texttron/BrowseComp-Plus/blob/046949032b0328319cc9a02663a759ec601d9402/LICENSE)
3. [decrypt_dataset.py](https://github.com/texttron/BrowseComp-Plus/blob/046949032b0328319cc9a02663a759ec601d9402/scripts_build_index/decrypt_dataset.py)
4. [immutable query-bundle dataset card](https://huggingface.co/datasets/Tevatron/browsecomp-plus/blob/144cff8e35b5eaef7e526346aa60774a9deb941f/README.md)
5. [immutable fixed-corpus dataset card](https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus/blob/b27b02bc3e45511b8b82a13e6f90ce761df726f6/README.md)

### 6.2 Facts and inference

The repository and dataset cards declare MIT. The fixed corpus contains
third-party Web pages, while the consulted metadata exposes no per-document
rights field or component-level clearance adequate for EvidenceMesh asset
admission. The declarations do not prove clearance of every embedded source.

The official comparison described by these sources is bounded to
BrowseComp-Plus over its fixed corpus. It does not authorize an equivalence
claim to open-Web BrowseComp, a live-search setup, another corpus, a rebuilt
index, or a mixed evidence/gold-qrel composite.

The published evaluation path refers to a Qwen judge. The consulted immutable
metadata does not pin a complete judge identity, tokenizer revision, prompt
and generation configuration, runtime dependency closure and deterministic
scoring contract. This prevents an officially comparable evaluator lock even
within the fixed-corpus boundary.

### 6.3 P0 outcome

BrowseComp-Plus is `blocked`. Its component-rights and judge-configuration
gates are incomplete. Its comparability scope is restricted to the official
BrowseComp-Plus fixed-corpus track and cannot be broadened by inference.
Acquisition, decryption, evaluation and scoring remain forbidden.

## 7. Options and selected policy

Three options were considered:

1. **Continue with both suites now.** Rejected. It would cross unresolved
   rights and comparability gates and could produce numbers that are not
   defensibly official.
2. **Reduce immediately to one suite.** Deferred. One authoritative suite can
   be sufficient later, but neither candidate currently passes its independent
   admission gates. Reducing scope now would reduce work, not uncertainty.
3. **Keep the technical alpha isolated while locking policy.** Selected. The
   technical alpha may continue as an engineering artifact without external
   benchmark assets, external quality claims or evidence-track promotion.
   The single next evidence action is a BrowseComp-Plus-only immutable-metadata
   clarification inside the remaining five-document budget. It targets only
   component rights and the complete judge/runtime closure; it grants no
   acquisition preference or admission.

This selection does not convert the technical alpha into evidence for Phase
11.9, Phase 12 or V1 readiness.

## 8. Entry and stop criteria for the next evidence action

The BrowseComp-Plus metadata clarification may start only when the P0 result
reproduces at 16/16, both candidates remain blocked, BrowseComp-Plus is the
only clarification candidate, exactly five unique-document slots remain, the
proof targets are limited to component rights and complete judge/runtime
closure, and a separate explicit GO is recorded.

Success requires immutable primary evidence that closes the component-rights
disposition for local-only non-redistribution handling and the full judge,
tokenizer, prompt, generation, runtime and scoring closure while preserving
the official fixed-corpus population and track mapping.

Only after that success may BrowseComp-Plus enter an acquisition review, and
that later review still requires all of the following:

- a component-level rights disposition covering the intended handling;
- an exact official population, asset revision and track mapping;
- a fully pinned evaluator or judge dependency and configuration closure;
- a candidate-specific acquisition manifest and storage boundary; and
- a separate explicit GO for that candidate.

Research stops immediately when any of the following occurs:

- the fifteen-document ceiling would be exceeded;
- a payload, signed download, credential, secret, decryption step, provider or
  model call would be required;
- a moving reference or secondary source would have to replace immutable
  primary evidence;
- the official score target would have to be weakened to an internal proxy;
- evidence would need to be published or a benchmark asset redistributed; or
- after the bounded clarification, no independent candidate has every required
  admission gate complete.

At most five additional unique public metadata documents remain available for
that separately authorized clarification action. Benchmark, provider, model,
retrieval, judge and scoring requests remain capped at zero.

## 9. Result semantics

Successful validation of this protocol and its manifest may return
`engineering_lock = pass`. That means the policy is internally consistent,
source-bounded, deterministic and fail-closed. It does not clear a suite.

The required substantive values are:

- `quality_decision = no_go`;
- `officially_comparable_score_target = true`;
- `real_external_score = false`;
- `candidate_suites_admitted = 0`;
- `component_license_clearance_complete = false`;
- `benchmark_comparability_complete = false`;
- `asset_acquisition_allowed = false`;
- `evaluation_allowed = false`;
- `publication_allowed = false`;
- `phase_11_8_10b_acquisition_status = blocked`;
- `phase_11_9_status = blocked`;
- `phase_12_status = blocked`.

The lock is fail-closed: an unknown, omitted or contradictory field is a
failure, never implicit permission.

## 10. Publication boundary

P0 is local-only. The methodology, manifest and any aggregate lock result may
be tested locally, but they must not be pushed, attached to the public pull
request, uploaded as an artifact, distributed, merged or released without a
separate publication GO. The pull request remains draft and distributions
remain unpublished.
