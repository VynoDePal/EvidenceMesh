# EvidenceMesh Alpha-RC3 HEAD exact protocol v1

## Decision boundary

This protocol accepts one new technical candidate containing the already-audited
single-host closed-alpha governor. The candidate is
`evidencemesh-0.1.0-alpha-rc.3` and is the first direct child of
`710739311af1c11504e647e94026f13d3dfb221f` that adds only this protocol, its
one-shot workflow, dedicated bundle and report tooling, the installed-package
smoke, and their tests. Product runtime files, `pyproject.toml` and `uv.lock`
must remain byte-identical to that parent.

The GitHub push commit containing the one-shot workflow is the candidate and
the attestation source identity. The workflow uses `github.sha`; it never
claims a retrospective attestation for its parent. A later sealing commit may
record the accepted candidate SHA, run, digests and attestation identifiers,
but that sealing commit is not the candidate.

This phase authorizes no tester contact, live session, provider request, model
request, benchmark-asset download, merge, release or public binary
distribution. The pull request remains draft.

## One-shot identity

The candidate workflow accepts only a non-forced push to
`VynoDePal/EvidenceMesh` branch `agent/evidencemesh-v0.1` whose `before` value
is exactly `710739311af1c11504e647e94026f13d3dfb221f`. The commit must have that
single parent. Its changed-path set is exactly the six Alpha-RC3 HEAD exact
harness files. The pull request must still be open, draft and headed by the
candidate SHA before attestations are created.

The workflow receives explicit pull-request read permission only for these
identity checks. It rechecks the same state immediately before emitting the
seal record.

Pull-request events, manual dispatches, forks, other branches, later pushes
and force-pushes are outside the protocol. A later push cannot become a second
candidate under this workflow.

## Candidate build and installed proof

All source-executing validation after dependency installation runs as the
unprivileged GitHub runner user with supplementary groups cleared, `nogroup`
as the primary group, `no-new-privs`, an empty environment allowlist and an
empty Linux network namespace. The isolated identity must not be able to write
the Docker socket.

After the source gates, the workflow requires a clean checkout and materializes
the candidate with `git archive` into a root-owned, read-only source tree whose
path is anchored directly below the runner's sticky temporary directory. Its
checksum list is root-owned as well, so the unprivileged build identity cannot
replace either path. Both builds, the installed smoke script, SBOM input and
bundle validators use only that frozen tree. Its file checksums and the
original checkout are revalidated before any attestation.

The candidate must pass all of these gates in one run:

1. exact commit, parent, changed-path and clean-worktree checks;
2. unchanged runtime, packaging metadata and lockfile relative to the accepted
   RC3 parent;
3. the complete test suite, branch-aware coverage, Ruff formatting and lint,
   and strict MyPy;
4. a hash-locked runtime dependency audit with no blocking vulnerability;
5. two independent builds using the commit timestamp as
   `SOURCE_DATE_EPOCH`, with byte-identical wheel and source distribution;
6. Twine validation of both distributions;
7. safe archive paths, no duplicate members, no links or special files, and
   exact installed bytes for `governor.py`, `engine.py`, `fetcher.py` and
   `cli.py`;
8. separate CPython 3.11 environments whose dependencies and build backend
   come from hash-bearing `uv.lock` exports, followed by `--no-deps`
   installation of the wheel and source distribution;
9. installed SDK searches through `httpx.MockTransport` with exactly one
   governed admission and one dispatch;
10. installed CLI health with the governor active, plus fail-closed refusal of
    HTTP serving;
11. installed MCP STDIO initialization and health with the governor active and
    scope `single_host_shared_sqlite`;
12. the installed CLI deterministic offline benchmark remains 12/12 with
    fused hit@1 equal to 1.0;
13. CycloneDX 1.7 inventory includes every direct runtime dependency and passes
    a public-metadata scan excluding runner paths and credential identifiers;
14. the exact bundle inventory and every checksum validate;
15. GitHub keyless provenance covers every checksummed subject, the wheel has
    a CycloneDX SBOM attestation, and the final metadata-only report is
    separately attested;
16. every attestation verifies against the candidate SHA, branch and dedicated
    workflow; and
17. wheel, source distribution and all private runner outputs are deleted even
    if a later step fails.

## Ephemeral bundle

The private runner bundle is named `evidencemesh-0.1.0-alpha-rc.3` and contains
exactly eight files:

1. `SHA256SUMS`;
2. `alpha-rc3-head-manifest.json`;
3. `dist/evidencemesh-0.1.0-py3-none-any.whl`;
4. `dist/evidencemesh-0.1.0.tar.gz`;
5. `evidencemesh-0.1.0.cdx.json`;
6. `installed-wheel-rc3-smoke.json`;
7. `installed-sdist-rc3-smoke.json`; and
8. `installed-wheel-offline-benchmark.json`.

No bundle file is uploaded as a GitHub Actions artifact, committed to Git or
sent to another storage service. GitHub receives only attestation statements
and their subject digests. The job summary and a later sealing record may
publish bounded metadata: candidate identity, run identity, file sizes,
digests, gate booleans and attestation identifiers. They contain no package
bytes, task text, provider output, secret or runner path.

## Traffic and authority

The maximum research budget is exactly:

| Dimension | Maximum |
|---|---:|
| Search or provider requests | 0 |
| Tavily requests | 0 |
| Model or token-count requests | 0 |
| Follow-up document fetches | 0 |
| Retries, fallbacks or repairs | 0 |
| Benchmark asset downloads | 0 |
| Tester sessions or contacts | 0 |

Pinned dependency downloads, GitHub API reads and GitHub attestation traffic
are supply-chain operations and are reported separately from research
traffic. No provider or model secret is referenced. Repository contents remain
read-only; the workflow receives only the short-lived GitHub permissions
needed for keyless attestations.

## Stop and seal rules

Stop on the first identity, parent, path, runtime-diff, archive, reproducibility,
installation, dependency, smoke, coverage, type, lint, checksum, SBOM,
attestation, zero-network or cleanup failure. Stop if any package byte becomes
publicly downloadable, any task needs a real provider, any secret is read, any
transport is reached without a permit, or the pull request ceases to be the
expected open draft at the candidate SHA.

A successful run establishes only an installable, reproducible and attested
single-host technical candidate. It does not implement distributed budget
coordination, a feedback collector, withdrawal, automatic retention deletion
or tester operations. It cannot authorize live execution, A0 adoption, merge,
release, public distribution, product-default changes, Phase 12, or any
quality, superiority or production-readiness claim.

After success, one separate metadata-only sealing commit must retire the
one-shot workflow and record the candidate SHA and tree, its parent, run and
attempt, protocol and workflow hashes, subject digests, report digest and all
attestation identifiers. Any correction before sealing creates a new candidate
and requires a new explicit decision.
