# Phase 11.8.10A external asset reconnaissance — 2026-07-31

## Outcome

**Identity and integrity lock complete; policy-blocked / no-go.** All 15
metadata-only engineering gates passed. This phase did not download, open,
decrypt, admit or score BRIGHT or BrowseComp-Plus data, so it establishes no
external retrieval-quality result.

## Provenance

- Methodology commit:
  `619ce675ba28d1411658af52002828c544dafbd7`
- Successful Phase 11.8.10A GitHub Actions run: `30631622498`
- Source-set SHA-256:
  `4c3fecf50e26b8e37e3ee361af38aca62745a632d0fd5ef59eb66a025dc3ed75`
- Canonical inventory SHA-256:
  `4601e9e5b9f6e66290822dff5a668d51aeaacbae42576c5b88fa3c386b496779`
- Raw JSON: `4,337` bytes; SHA-256
  `3e0c2d7e99778d71f773a980a4212cd44fd8960fd1ee7d142350867345c9310d`

## Locked inventory

The immutable inventory covers exactly 37 Git LFS content objects across the
two suites. Their expected transfer size is 5,013,088,007 bytes (about 4.67
GiB), and their upstream-declared decoded size is 7,205,462,832 bytes (about
6.71 GiB). A future controlled acquisition would require at least 20 GiB free.

Every required path has an exact byte length and full lowercase content
SHA-256. Git blob hashes, Xet descriptors, moving refs, signed URLs, mirrors,
globs and alternative paths are rejected.

## Blocking findings

The upstream BRIGHT declarations identify CC-BY-4.0, while BrowseComp-Plus
identifies MIT. Neither declaration supplies per-item or per-document rights
clearance for all incorporated third-party content, so EvidenceMesh must not
redistribute raw assets and cannot yet admit them for evaluation.

BRIGHT comparability is also unresolved because published query totals differ
between revisions, the leaderboard's immutable dataset revision is unstated,
and the upstream evaluator dependency is unpinned. Any later score therefore
requires explicit comparability resolution before it can be described as an
official or leaderboard-comparable score.

## Traffic, privacy and governance

The run made zero provider, search-API or model calls, read zero secrets,
downloaded and opened zero official asset bytes, decrypted zero queries, and
computed zero retrieval or answer scores. Only aggregate identities, counts,
sizes, hashes, license identifiers and policy statuses are published.

Phase 11.8.10B, Phase 11.9, Phase 12, merge, release, default promotion and
superiority claims remain unauthorized. The pull request must remain draft and
the next phase requires a separate explicit GO.
