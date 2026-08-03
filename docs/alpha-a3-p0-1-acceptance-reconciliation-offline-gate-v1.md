# Alpha A3-P0.1 acceptance reconciliation offline gate v1

## Decision

Decision: pending_until_distinct_gate_and_same_head_ci.

A3-P0.1 is one new, one-shot reconciliation candidate. It does not alter,
replace, invoke again, or reinterpret the failed historical executions. A pass
establishes only that the complete candidate test suite and the unchanged A3
clean-room operator journey pass together on one exact descendant HEAD.

PR #1 remains draft. This gate authorizes no artifact upload, attestation,
distribution, tag, release, merge, public installation claim, Phase 12
transition, production use, or V1 claim.

## Immutable historical evidence

The exact entry parent is commit
88cf431b67619624c09840174451780b78a9ae41 and tree
960bacb500ad390d4ae3a38bc941e30c85e80a8d on branch
agent/evidencemesh-v0.1 in VynoDePal/EvidenceMesh PR #1.

The dedicated A3 execution remains failed:

- run 30852239811, job 91814758947, attempt one;
- the scope check used one single-line fixed-string operand while README stores
  the required sentence across a Markdown line break;
- fixed-string matching does not normalize that whitespace, so the check failed
  before the handoff build and before the operator journey began.

Ordinary CI run 30852239420 also remains failed. Its Python jobs 91814763021,
91814777751, and 91814777055 each reported the same single stale assertion in
tests/test_alpha_a1_p0_installability.py. That assertion still expected the
quick-start source identity that preceded the accepted A2 README update.

These are acceptance-control defects, not observed EvidenceMesh runtime,
packaging, provider, policy, session, or operator-lifecycle defects. The
operator journey was not executed by the failed A3 job, so that failure is not
evidence that the journey passed or failed.

## Exact five-path scope

The candidate must be one non-merge direct child of the exact failed parent and
must contain exactly these statuses:

1. add .github/workflows/alpha-a3-p0-1-acceptance-reconciliation-offline.yml;
2. add alpha/alpha-a3-p0-1-acceptance-reconciliation-policy-v1.json;
3. add docs/alpha-a3-p0-1-acceptance-reconciliation-offline-gate-v1.md;
4. add tests/test_alpha_a3_p0_1_workflow.py;
5. modify only tests/test_alpha_a1_p0_installability.py.

The fifth path may correct only stale Quick Start documentation expectations:
the current accepted source commit and whitespace-stable platform statements.
It must preserve the historical A1 runner assertions and may not weaken any
install, offline, command-order, or platform-honesty check. No source,
packaging, lockfile, A1 runner, A1 policy, strace parser, A3 workflow, A3
policy, A3 protocol, A3 runbook, A3 harness, A3 static test, A3 unit test, or
README change is authorized.

## Byte-exact failed-parent controls

Before dependency acquisition, the workflow must prove an empty diff from the
failed parent for all eight A3 paths and verify these SHA-256 values:

- A3 workflow:
  aaba296f3da13fc8405a6e579a2478b943a3a17a12ca21eaacae46d76d194e5e
- README:
  0a532c276a58f86b7c6134843c2779dfb8d5e9cc75ba8a00a794991b37c16f7d
- A3 policy:
  43255b673e4a90787a3bc95db3398d61d09fe9932f83978b5143816b2d3e62cf
- A3 protocol:
  d71c6c035b107a03eff9130163250f344b4c4eb6ef7ba894304ade9287c022a1
- A3 runbook:
  ec45efe1fffa9acb8acc1127383b4a97c684bf43a4a16316d078717800c8b791
- A3 harness:
  d7571ca65514e05ad3415d029ed67279f70141238152a8f6e5ef618975e19b83
- A3 static test:
  0aecc7ffe84facad14225420be58868776ded2e66c2f475c479c5d527cbfc7fb
- A3 harness unit test:
  230f1dda7bbe3c08d042c122df7c5b18a6b533dca44c4eb8dbd58b548b373d70

The unchanged A1 runner, A1 policy, and frozen named-host strace parser are also
hash-locked. The new policy, protocol, static test, and corrected A1 test are
hash-locked after their final content is sealed.

## Ordered reconciliation

The workflow has one attempt and zero retry. It must run the following stages
in order.

### 1. Fail-closed lineage and scope

Require a synchronize event, draft PR #1, the exact repository and branch, the
exact event-before commit, one direct parent, and the exact five-path status
list. Verify the failed parent tree, immutable source and packaging paths, all
eight A3 paths, and the supporting A1 controls.

### 2. Whitespace-stable README acceptance

Read README.md as UTF-8 and normalize all whitespace with the semantic
operation:

    normalized = " ".join(Path("README.md").read_text(encoding="utf-8").split())

Then require the sentence “it is not a public distribution or a public
installation path” exactly once in the normalized text. A literal multiline
shell match is forbidden because Markdown wrapping is not semantic drift.

### 3. One full candidate suite with coverage

Acquire the pinned Python toolchain once and download the locked binary
dependency supply once. Install the controller offline from that supply. Before
starting the operator step, run every test under tests once against the
candidate src tree, with pyproject.toml, branch coverage, the unchanged 85
percent minimum, no pytest cache, and a run-scoped base temporary directory.
Run that suite as the original runner UID with the neutral `nogroup` primary
GID, all supplementary groups and capabilities removed, inside one distinct
private network namespace. Replace the inherited environment with an allowlist.
Trace its complete process tree with `strace -ff -qq -e trace=network` into the
run-scoped root. Bring up only the loopback interface and require that the
namespace has no default route. The trace may contain local test traffic, but
fail on any non-loopback destination, port 53 request, or local resolver IPC
endpoint. The namespace and trace are both mandatory: isolation prevents
external access while the trace proves that the suite made no external or DNS
attempt.

Targeted A3 tests are not a substitute for this full-suite stage. Formatting
and linting must cover the unchanged A3 harness and tests, the new A3-P0.1
static test, and the corrected A1 test.

### 4. Complete unchanged A3 operator journey

Only after the full suite passes, perform the entire A3-P0 journey:

1. export exact A2 product commit 41e0d18e1801cbde0bae61dfd85877fddbc64e4d
   and verify tree 41c74b75f270db66b4f5032172e5dff0f6a32aaa;
2. rebuild the single unpublished wheel and require SHA-256
   c38841da79c7a71275bda5a925096dc692ce4feabaf2f618233c5379ed1c577a
   and 146492 bytes;
3. construct and recursively hash one read-only handoff;
4. use nobody:nogroup, a private mount namespace, a distinct network
   namespace, a mode-000 masked checkout, a denied Docker socket, and an
   allowlisted environment;
5. run one offline hashed installation, one providers CLI command, two fresh
   MCP server sessions, two initialize requests, two initialized
   notifications, and two tools/call:health requests;
6. trace the complete process tree once with strace -f -qq and validate it with
   scripts/verify_alpha_a1_p2_named_host.py::_validate_strace plus the exact
   five-executable allowlist;
7. require natural server stops, byte-identical retained state, package-only
   uninstall, absence of the installed package, and no surviving process;
8. unconditionally remove the run-scoped root and confirm its absence before
   writing the summary.

No live provider, search, document, model, tester, runtime network, or DNS
request is permitted. Dependency acquisition is limited to the single
pre-operator binary download command already declared by the A3 contract.

## Stop criteria

Stop without retry if any lineage, tree, path status, hash, normalized sentence,
format, lint, full-suite test, 85 percent coverage threshold, full-suite runner
identity, network namespace, network trace, A2 wheel identity, handoff,
privilege boundary, namespace, trace, executable, receipt, lifecycle, or cleanup
check differs.

Stop if the full suite does not complete before the operator journey. Stop if
either historical execution is invoked again or represented as successful.
Stop on any second candidate commit, retry, artifact, attestation, distribution,
tag, release, merge, public-installation claim, Phase 12 claim, production
claim, V1 claim, or surviving ephemeral output. A failed or cancelled A3-P0.1
attempt is terminal.

## Successful claim boundary

A successful A3-P0.1 result proves one automated Ubuntu 24.04/Python 3.11
candidate test suite with branch coverage and zero observed non-loopback
destination or DNS/resolver attempt, followed by one complete clean-room
simulation of the unpublished, byte-exact A2 wheel lifecycle. Same-HEAD
ordinary CI remains independently required for the global A3 acceptance claim.

It does not establish human operator usability, macOS or native Windows
compatibility, a public installation path, public distribution availability,
live behavior, crash recovery, rollback, purge semantics, operating-system
supervision, Phase 12 readiness, production readiness, or V1 readiness.
