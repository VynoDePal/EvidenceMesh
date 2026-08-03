# EvidenceMesh Alpha A2-P2 installed-distribution offline gate v1

## Decision state

**A2-P2 is a one-shot, fail-closed installed-distribution gate for the current
local technical-alpha successor.** Its successful canonical run may establish
only that the exact A2 candidate can be reproducibly built, separately
installed from its wheel and sdist, and exercised offline on the canonical
single-host environment. The decision remains `pending_until_one_shot_ci`
until that run succeeds on the exact candidate.

This gate does not authorize a live closed alpha, an operating-system service,
Phase 12, a merge, a tag, an artifact upload, package distribution, a GitHub
Release, production use, or V1 readiness. BrowseComp-Plus, BRIGHT, provider
availability, retrieval quality, and model behavior are outside this gate.

## Exact entry identity and one-commit scope

The immutable public parent is commit
`d284f987f712d93980c4d0cf51bd6491153decbe`, tree
`bdddbcb3dfea16a11d584ebfbb74b44f8cc20966`, on draft PR #1 branch
`agent/evidencemesh-v0.1` in `VynoDePal/EvidenceMesh`.

The candidate must be exactly one direct, non-merge child of that parent. One
branch update, one candidate commit, and one workflow attempt are the maximum.
The exact six-file allowlist is:

1. `.github/workflows/alpha-a2-p2-installed-distribution-offline.yml`
2. `alpha/alpha-a2-p2-installed-distribution-offline-policy-v1.json`
3. `docs/alpha-a2-p2-installed-distribution-offline-gate-v1.md`
4. `scripts/smoke_installed_a2_p2.py`
5. `tests/test_alpha_a2_p2_workflow.py`
6. `tests/test_smoke_installed_a2_p2.py`

`src`, `pyproject.toml`, and `uv.lock` are immutable from the exact parent. The
policy and this protocol are content-hash locked by the workflow. Any lineage,
tree, scope, hash, or draft-state drift is a stop, not a reason to amend the
candidate or rerun it.

## Acquisition and empty-network boundary

The canonical environment is Ubuntu 24.04 x86_64 with Python 3.11, uv 0.11.33,
and Hatchling 1.31.0 from the locked environment. Python and locked dependencies
for the validation, wheel-smoke, and sdist-smoke environments are acquired
before isolation, with uv caches disabled and uv HTTP retries set to zero. The
run-scoped temporary root is derived from `RUNNER_TEMP`, the run identifier,
and attempt number; it must be absent and must not be a symlink before
acquisition. An unexplained leftover is a terminal stop. Supply-chain
acquisition does not authorize EvidenceMesh runtime traffic.

Every source quality check, build, archive installation, and installed smoke
then runs in a fresh Linux network namespace through `/usr/bin/unshare --net`.
The workflow proves that namespace identity differs from its parent and uses
`UV_OFFLINE=1`, privilege reduction, cleared supplementary groups, no new
privileges, and no readable or writable Docker socket. Provider, search,
document, model, DNS, and EvidenceMesh runtime requests all have a maximum of
zero.

## Reproducible clean-export build

The workflow creates two independent clean `git archive` exports of the exact
candidate. Neither export contains `.git`, the working tree, an editable
installation, or a prior build directory. With one common candidate-derived
`SOURCE_DATE_EPOCH`, each export is built exactly once into one wheel and one
sdist. This produces exactly two build invocations and four ephemeral files.

The corresponding wheel filenames and sdist filenames must match. Each wheel
pair and sdist pair must be byte-for-byte identical under `cmp`; their SHA-256
digests must consequently match. A missing, additional, renamed, or differing
archive fails the gate.

Before installation, the complete wheel and sdist inventories are traversed.
Absolute or escaping names, duplicate members, symlinks, hardlinks, special
files, private-key-like names, environment files, VCS state, virtual
environments, and cache bytecode are refused.

## Separate installed-distribution smokes

Before network isolation, two clean virtual environments receive only the
locked runtime dependencies. Hatchling 1.31.0 is then acquired separately only
for the sdist environment. Inside the empty network namespace, the first
environment installs the first build's wheel and the second installs the first
build's sdist. Both archive installations are non-editable, offline, no-index,
no-dependency, no-cache operations, followed by an offline `uv pip check`. The
sdist build isolation is disabled so that it can use only the separately
acquired exact build backend.

Before either install, an isolated interpreter probe must find neither the
`evidencemesh` package nor either console launcher. Hatchling must resolve to
exactly 1.31.0 in every build-capable environment. After installation, the real
PEP 610 `direct_url.json` must name the tested archive and must declare at least
one matching SHA-256; a URL-only record is insufficient. To make that binding
an installation input rather than rewritten evidence, each subject is supplied
to uv as a quoted `evidencemesh @ file://...#sha256=...` direct requirement.
The workflow also records each independently calculated archive SHA-256 and
byte size in the runner environment for the final receipt.

The A2-P2 and retained RC4.1A harness files are copied to a private temporary
harness directory and their SHA-256 digests are verified after the copy. From
that directory outside the repository, each installed interpreter runs the
copied `smoke_installed_a2_p2.py` once. The smoke binds the independently
calculated archive SHA-256, exact archive name, interpreter prefix, installed
console launchers, distribution metadata/RECORD, and five A2 runtime blobs to
the installed subject. It composes the retained RC4.1A installed checks and
exercises the additive A2 v3 lifecycle only with deterministic local state and
`httpx.MockTransport`, including fresh v3 bootstrap, unchanged v2 refusal,
supervisor/session authority, governed permit consumption, feedback retention,
withdrawal, and recovery. No source-tree import may satisfy an installed check.

The wheel and sdist reports are local diagnostic outputs only. They contain no
credential, secret, absolute private path, live observation, benchmark result,
or publication authority. They and every export, archive, environment, cache,
ledger, feedback file, and report are deleted by an unconditional final cleanup
and the workflow confirms that the root no longer exists. Only after that
confirmation may the workflow write a `pass` summary.

## Required pass conditions

A pass requires all of the following in the one canonical attempt:

- exact PR, draft branch, parent commit/tree, direct-child lineage, and six paths;
- unchanged runtime, packaging metadata, dependency lock, and 85% coverage floor;
- format, lint, strict source typing, and the complete test suite passing offline;
- two clean-export wheel+sdist builds and byte-identical corresponding archives;
- one isolated wheel installation and one isolated sdist installation;
- real PEP 610 archive URL and declared SHA-256 bindings for both installations;
- both installed A2-P2 smoke reports valid and bound to their archive digests;
- zero runtime/provider/search/document/model/DNS request and zero live session;
- unconditional deletion of every ephemeral output.

## Stop criteria

Stop without retry or reinterpretation if the exact parent/tree or direct-child
lineage differs, the candidate is a merge, the allowlist is not exactly six
files, an immutable runtime or packaging path changes, or a policy/protocol
hash differs. Stop on any quality failure, coverage weakening, archive count or
reproducibility failure, editable/source-tree import, installed origin or RECORD
drift, missing or URL-only PEP 610 archive binding, archive-digest mismatch, v2
migration/reset, A2 lifecycle failure, DNS or network attempt, live
provider/model/tester execution, service activation, or leftover ephemeral
output.

Stop if a second candidate, workflow rerun, retry, artifact or attestation
upload, distribution publication, tag, release, merge, Phase 12 case, or broader
claim is proposed. A failed or cancelled run is terminal for this candidate.

## Claim boundary

A successful exact run may accept **EvidenceMesh v0.1.0 A2 as a local,
single-host, offline technical alpha installed from reproducible wheel and
sdist subjects**. It does not prove real OS supervision or restart behavior,
live closed-alpha safety, public package availability, external benchmark
admission, research quality, Phase 12 readiness, production fitness, or V1
readiness. Those remain separate fail-closed gates even if BrowseComp-Plus
never responds.
