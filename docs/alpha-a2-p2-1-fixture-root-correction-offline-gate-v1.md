# EvidenceMesh Alpha A2-P2.1 fixture-root correction offline gate v1

## Decision state

**A2-P2.1 is a one-shot correction and complete revalidation gate.** The
preceding A2-P2 candidate remains failed. This gate neither reruns nor
reinterprets that attempt; it creates one direct-child candidate whose only
behavioral change is a deterministic test-fixture root correction, then repeats
the complete A2-P2 source, build, installation, and installed-smoke contract.

The candidate decision is `pending_until_one_shot_ci`. A pass may recover only
the local, single-host, offline technical-alpha installability claim. Live
closed-alpha use, OS-service activation, Phase 12, merge, tag, artifact upload,
distribution publication, release, production, and V1 remain NO-GO.

## Immutable historical failure

GitHub Actions run `30841501822`, job `91779399419`, failed before either clean
export or package build. The complete suite reached two test-only failures:

- `test_primary_v3_close_mints_authority_and_withdrawal_cleans`;
- `test_exact_session_expiry_requires_then_resolves_recovery`.

Both supplied pytest's already-existing `tmp_path` directory to an exercise
whose private-root helper intentionally creates its own root with
`exist_ok=False`. The resulting `FileExistsError` is a fixture-contract error,
not observed product-runtime, archive, installation, network, provider, model,
or quality behavior. The failed run, job, conclusion, and stage remain
immutable evidence; no later success converts them into a pass.

## Exact parent, correction, and scope

The exact failed parent is commit
`18340f972bbc907912d1fcfa9fe5a2385751cc97`, tree
`06e745383904c37ca277c8f57c45db9ed96df6b4`, on draft PR #1 branch
`agent/evidencemesh-v0.1` in `VynoDePal/EvidenceMesh`.

The correction candidate must be exactly one non-merge direct child of that
parent. One commit, one fast-forward branch update, one workflow attempt, zero
retry, and zero rerun are the maximum. The exact five-path allowlist is:

1. `.github/workflows/alpha-a2-p2-1-fixture-root-correction-offline.yml`
2. `alpha/alpha-a2-p2-1-fixture-root-correction-policy-v1.json`
3. `docs/alpha-a2-p2-1-fixture-root-correction-offline-gate-v1.md`
4. `tests/test_alpha_a2_p2_1_workflow.py`
5. `tests/test_smoke_installed_a2_p2.py`

The first four paths must be additions and the existing smoke test must be the
only modification. Its two affected tests must create distinct, initially
absent `primary` and `recovery` child roots beneath `tmp_path`, assert absence,
and pass those exact children to the unchanged A2 exercises. No production or
smoke-harness source change is authorized.

`src`, `pyproject.toml`, `uv.lock`, and these five untouched A2-P2 files remain
byte-identical to the exact parent:

- `.github/workflows/alpha-a2-p2-installed-distribution-offline.yml`;
- `alpha/alpha-a2-p2-installed-distribution-offline-policy-v1.json`;
- `docs/alpha-a2-p2-installed-distribution-offline-gate-v1.md`;
- `scripts/smoke_installed_a2_p2.py`;
- `tests/test_alpha_a2_p2_workflow.py`.

The dedicated P2.1 policy and this protocol are content-hash locked by the new
workflow. Any identity, status, scope, or immutable-content drift is a stop.

## Complete A2-P2 revalidation

Dependencies are acquired before isolation with uv 0.11.33, Python 3.11, the
locked runtime dependency set, and separately acquired Hatchling 1.31.0 for the
sdist environment. All validation after acquisition runs with `UV_OFFLINE=1`
inside a Linux network namespace proven distinct from its parent. The reduced
process has no readable or writable Docker socket.

The canonical attempt must repeat every material P2 control:

1. format, lint, strict source typing, and the full suite at the unchanged 85%
   branch-coverage floor;
2. two independent clean `git archive` exports using one candidate-derived
   `SOURCE_DATE_EPOCH`;
3. one wheel and one sdist built from each export, with corresponding filenames
   and bytes exactly equal;
4. complete safe archive-inventory checks and independent SHA-256/size capture;
5. two initially product-free environments, runtime dependencies only, plus
   exact Hatchling only where the sdist requires it;
6. hashed PEP 508 file requirements, offline/no-index/no-dependency installs,
   followed by `uv pip check`;
7. strict PEP 610 hashed URL, installed-prefix, sys.path, metadata, RECORD, A2
   runtime-blob, CLI, MCP, v2-refusal, v3-liveness, MockTransport, feedback,
   withdrawal, retention, and recovery checks for both wheel and sdist;
8. unconditional deletion and confirmation of the run-scoped temporary root
   before any pass summary.

All exports, distributions, environments, caches, ledgers, feedback files, and
reports remain ephemeral. The maximum EvidenceMesh runtime/provider/search/
document/model/DNS traffic, live tester sessions, and OS-service activations is
zero.

## Stop criteria

Stop without retry if the candidate is not the one direct child of the exact
parent, the parent tree differs, a historical failure is rewritten, any of the
five path statuses differs, or an immutable path/hash changes. Stop if either
fixture root exists before the exercise, is shared, or is not the exact child
declared by the corrected test.

Stop on any format, lint, typing, coverage, full-suite, export, build,
reproducibility, inventory, installation, dependency, PEP 610, RECORD,
installed-origin, CLI, MCP, or A2 smoke failure. Stop on any network/DNS/live
request, service activation, retry, rerun, second correction commit, artifact,
attestation, distribution, tag, release, merge, Phase 12 case, or leftover
ephemeral output. A failed or cancelled P2.1 attempt is terminal.

## Claim boundary

A successful exact P2.1 run may establish only that EvidenceMesh v0.1.0 A2 is
an installable local, single-host, offline technical alpha from reproducible
wheel and sdist subjects after the narrow fixture correction. It does not prove
live behavior, real OS supervision, external benchmark admission, research
quality, public distribution, Phase 12 readiness, production fitness, or V1
readiness.
