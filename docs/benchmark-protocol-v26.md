# EvidenceMesh benchmark protocol v26

## Phase 11.8.10A — external asset identity and integrity reconnaissance

Status: frozen metadata-only methodology. This protocol does not authorize an
asset download, query decryption, retrieval run, model call, score, merge,
release, product-default change, or quality claim.

## 1. Decision carried forward

Phase 11.8.9 remains `no_go`. Its synthetic checks established engineering
conformance only; BRIGHT and BrowseComp-Plus were not evaluated. Phase
11.8.10A narrows the remaining uncertainty without changing that decision.

The phase has four permitted outputs:

1. immutable identities for official code and dataset repositories;
2. an exact metadata inventory of required objects, byte lengths and full
   content SHA-256 values;
3. upstream-declared record counts, license declarations and storage bounds;
4. a fail-closed list of unresolved legal and comparability questions.

No benchmark payload is an EvidenceMesh source artifact. The Parquet files,
decrypted questions, documents, answers, qrels, source URLs and indexes must
not be committed, uploaded as workflow artifacts or published in a report.

## 2. Frozen scope

Exactly two suites are considered:

- [BRIGHT](https://github.com/xlang-ai/BRIGHT), code revision
  `d99e8391d967d4c2b3a74732530d2309e2fc92b6`, and dataset revision
  `3066d29c9651a576c8aba4832d249807b181ecae`;
- [BrowseComp-Plus](https://github.com/texttron/BrowseComp-Plus), code revision
  `046949032b0328319cc9a02663a759ec601d9402`, query-bundle revision
  `144cff8e35b5eaef7e526346aa60774a9deb941f`, and corpus revision
  `b27b02bc3e45511b8b82a13e6f90ce761df726f6`.

Moving branches, short revisions, timestamp selection, remote globs, mirrors,
converted Hub refs, alternative corpora and prebuilt indexes are excluded.

## 3. Authoritative object inventory

The committed inventory contains 37 Parquet paths:

- BRIGHT: 12 `examples` shards and 12 short `documents` shards;
- BrowseComp-Plus: 6 obfuscated test shards and 7 corpus shards.

Each record binds the suite, immutable dataset snapshot, exact relative path,
media type, byte length and the `oid sha256` from the immutable Git LFS pointer.
A Git LFS SHA-256 oid identifies the full content. A Git blob SHA-1, Xet
descriptor hash, ETag or expiring signed download URL does not substitute for
that content digest.

The inventory was obtained from upstream Git metadata only. No Parquet payload
was downloaded or opened. The metadata importer validates the exact 37-object
set and aggregate byte totals; it has no HTTP, authentication, decryption,
Parquet, provider, model, search or scoring implementation.

## 4. BRIGHT lock

### 4.1 Track and roles

Only the original-query short-document track is selected:

- `examples`: `id` and `query` are candidate-visible; `gold_ids` and
  `excluded_ids` are evaluator-only;
- `documents`: `id` and `content` form the fixed corpus;
- `long_documents` and every generated-reasoning configuration are excluded.

The exact task order is:

1. `biology`
2. `earth_science`
3. `economics`
4. `pony`
5. `psychology`
6. `robotics`
7. `stackoverflow`
8. `sustainable_living`
9. `aops`
10. `leetcode`
11. `theoremqa_theorems`
12. `theoremqa_questions`

The upstream snapshot declares 1,384 queries and 1,333,166 short documents.
Its selected compressed objects total 470,079,368 bytes and its decoded dataset
estimate totals 1,153,708,725 bytes.

If evaluation is later authorized, each task produces nDCG@10 and the suite
result is the unweighted macro average of all 12 task values. Excluded document
identifiers are applied before scoring. Candidate code must never receive
reasoning, answers, gold identifiers or excluded identifiers.

### 4.2 Unresolved BRIGHT questions

The code repository and dataset card declare CC-BY-4.0. That declaration does
not provide a per-item rights map for source-derived Stack Exchange, LeetCode,
AoPS, TheoremQA and general Web content. Raw data redistribution is therefore
forbidden by EvidenceMesh policy pending clarification.

Comparability is also unresolved: the current snapshot contains 1,384 queries,
while the ICLR proceedings description reports 1,398, and older snapshots have
different counts. The public leaderboard's exact immutable data revision is not
stated. The upstream evaluator dependency is not version-pinned either.

Consequently, a future number from the selected snapshot must not be called an
unqualified official or leaderboard-comparable BRIGHT score until these points
are resolved.

## 5. BrowseComp-Plus lock

The pinned query bundle declares 830 obfuscated rows. The fixed corpus declares
100,195 documents. Required compressed objects total 4,543,008,639 bytes and
the decoded dataset estimate totals 6,051,754,107 bytes.

The query-bundle fields derive three evaluator roles: query text, evidence
qrels, and gold qrels. Evidence and gold are distinct tracks and may never be
substituted for one another or averaged into an invented composite result.
The repository's real gold-qrel filename is `topics-qrels/qrel_golds.txt`
(plural); the singular spelling in prose is not an accepted alias. Retrieval
metrics, if later authorized, remain separate for each track.

The query bundle is not decrypted in this phase. Its canary, query text,
answers and nested document text are never copied into EvidenceMesh artifacts.
Prebuilt indexes are excluded because the subject under evaluation is the
EvidenceMesh retriever.

The code repository and both dataset cards declare MIT. The corpus is composed
of third-party Web pages and supplies no per-document rights field. EvidenceMesh
therefore records the declaration but does not assert complete rights clearance
or republish the assets.

## 6. Capacity boundary

The 37 selected objects total 5,013,088,007 bytes (about 4.67 GiB). Their
upstream-declared decoded size is 7,205,462,832 bytes (about 6.71 GiB). A future
import should require at least 20 GiB free to cover immutable downloads,
verified materialization and bounded working space before any index is built.

These numbers are capacity planning only. No bytes were transferred in Phase
11.8.10A.

## 7. Fail-closed importer contract

The Phase 11.8.10A importer accepts metadata inventory JSON only. It:

- rejects non-HTTPS, credential-bearing, signed, query-string and moving URLs;
- rejects short revisions, undeclared objects, duplicate paths, traversal,
  globs, zero lengths, malformed or non-lowercase hashes;
- distinguishes Git LFS content oids from Git blobs and Xet descriptors;
- requires exact coverage and exact suite byte totals;
- refuses any Phase 12 path before opening it;
- never reads environment variables or secrets; and
- never downloads, decrypts, parses or scores benchmark content.

A later importer with an actual transfer capability requires a separate phase,
review, GO and source lock. It must stream into a caller-supplied external
cache, enforce per-object and total limits, hash before admission, reject links
and archive traversal, and keep all raw data out of the repository and CI
artifacts.

## 8. Phase result semantics

Successful Phase 11.8.10A validation yields
`asset_integrity_lock_complete_policy_blocked`. This means identities, paths,
sizes and content hashes are locked. It does **not** mean the assets were
downloaded, admitted, legally cleared, evaluated or scored.

Required result values are:

- `quality_decision = no_go`;
- `real_external_score = false`;
- `external_evaluation_status = not_run`;
- `component_license_clearance_complete = false`;
- `benchmark_comparability_complete = false`;
- `acquisition_eligible = false`;
- `local_assets_admitted = false`;
- `evaluation_eligible = false`.

The next acquisition/evaluation phase remains blocked pending explicit policy
clearance and a separate user GO.

## 9. Reproducibility and publication

Methodology is published first as one immutable commit containing the protocol,
manifests, standard-library validator, runner, tests and read-only workflow.
Only after that commit passes CI may an aggregate-only result be generated from
that exact methodology commit and published in a second commit.

The report may contain hashes, counts, byte totals, license identifiers and
status flags. It may not contain query, answer, document or qrel content;
benchmark identifiers; source-page URLs; environment values; absolute paths;
or decrypted material.

The pull request stays draft. Merge, release, default promotion, Phase 11.9,
Phase 12 and superiority claims remain unauthorized.

