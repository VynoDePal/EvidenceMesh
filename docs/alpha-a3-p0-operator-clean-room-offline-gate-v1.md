# EvidenceMesh Alpha A3-P0 operator clean-room acceptance offline gate v1

## Decision state

Alpha A3-P0 is a one-shot, automated operator simulation for the exact A2
wheel. It is not another source, test-suite, wheel/sdist reproducibility, or A2
internal-liveness gate. It begins with a locally prepared, unpublished handoff
kit, gives that kit to a distinct unprivileged identity that cannot read the
checkout, and observes only the documented installation, local health, clean
restart, and package-uninstall path.

The candidate decision is `pending_until_dedicated_gate_and_same_head_ci`.
Both the dedicated A3-P0 attempt and ordinary CI for the same candidate SHA
must pass. A pass does not authorize a public distribution, live closed alpha,
recovery or rollback claim, service activation, Phase 12, merge, production,
or V1.

## Immutable entry evidence

The product subject is commit
`41e0d18e1801cbde0bae61dfd85877fddbc64e4d`, tree
`41c74b75f270db66b4f5032172e5dff0f6a32aaa`. Its A2-P2.1 acceptance is GitHub
Actions run `30843140982`, job `91784859717`, attempt 1, conclusion `success`.
Ordinary CI run `30843139966` also concluded `success`.

The only distribution subject used by A3-P0 is the A2 wheel:

- name: `evidencemesh-0.1.0-py3-none-any.whl`;
- SHA-256: `c38841da79c7a71275bda5a925096dc692ce4feabaf2f618233c5379ed1c577a`;
- size: `146492` bytes.

A3-P0 rebuilds that wheel once from one clean export of the exact parent, using
the parent's timestamp as `SOURCE_DATE_EPOCH`, and requires byte identity with
the accepted subject. It does not rebuild or reinterpret the accepted sdist.
The A3 control commit is never used as a distribution source.

## Exact candidate scope

The A3 candidate must be one non-merge direct child of the exact parent, on
draft PR #1 branch `agent/evidencemesh-v0.1`. One commit, one fast-forward
branch update, one workflow attempt, zero retry, and zero rerun are the maxima.

The exact additions are:

1. `.github/workflows/alpha-a3-p0-operator-clean-room-offline.yml`;
2. `alpha/alpha-a3-p0-operator-clean-room-offline-policy-v1.json`;
3. `docs/alpha-a3-p0-operator-clean-room-offline-gate-v1.md`;
4. `docs/alpha-a3-p0-operator-clean-room-runbook-v1.md`;
5. `scripts/verify_alpha_a3_p0_operator_clean_room.py`;
6. `tests/test_alpha_a3_p0_workflow.py`;
7. `tests/test_verify_alpha_a3_p0_operator_clean_room.py`.

`README.md` is the only modification. It replaces the stale A1 Quick Start SHA
with the accepted A2 parent and links the internal A3 runbook while explicitly
retaining the unpublished, simulation-only limitation. `src`, `pyproject.toml`,
and `uv.lock` are immutable. Every policy, protocol, runbook, README, driver,
and test input is content-hash locked by the workflow before execution.

## Handoff construction before isolation

Dependency acquisition is a supply-chain preparation step, not EvidenceMesh
runtime traffic. uv 0.11.33 and Python 3.11 are acquired before operator
isolation with transport retries disabled. The controller uses the unchanged
lock to:

1. export runtime requirements with `uv export --locked --no-dev
   --no-emit-project`, and a controller superset with the locked development
   extra but still no project;
2. execute one `pip download` command with `--require-hashes`,
   `--only-binary=:all:`, zero retries, and version checks disabled;
3. reject every non-wheel or link in the staging supply, then install the
   controller/build tools offline from it and require Hatchling 1.31.0;
4. compute one offline, no-index, hash-required pip installation report for the
   runtime export and copy only the wheels selected by that report into the
   operator wheelhouse;
5. reject every link, non-wheel, duplicate normalized project, unexpected, or
   unmanifested operator-wheelhouse entry, then add the accepted EvidenceMesh
   wheel and one exact
   `evidencemesh==0.1.0` requirement bound to its accepted SHA-256;
6. recursively SHA-256-manifest every wheel and every other final handoff
   input in one exact `SHA256SUMS` inventory.

The handoff is made root-owned and non-writable to the operator. No handoff
file is uploaded as an Actions artifact, attestation, distribution, release,
or any other externally consumable package.

Bytecode generation is disabled for the whole job. Controller temporary files
and pytest's base temporary directory are both confined beneath the deterministic
run-scoped `build` root, so unconditional cleanup covers them.

The gate verifies uv 0.11.33, Python 3.11.x, and Hatchling 1.31.0. The copied uv
binary is included in the handoff manifest. The downloader's pip version and
one module digest are observations only; neither is misreported as matching an
externally frozen expected digest, and no Python binary hash claim is made.

The number of underlying supply-chain HTTP exchanges is registry-dependent
and is not misreported as zero. Its enforceable budget is one download command,
zero retry. After handoff completion, the operator path has a strict external
network and DNS budget of zero.

## Clean-room operator boundary

The workflow uses the existing `nobody:nogroup` identity; it creates or deletes
no system user. The identity must be unprivileged and distinct from the runner.
The workflow creates distinct, initially empty, mode-0700 HOME, XDG cache,
configuration, data, TMP, work, and trace roots beneath a root-owned traversal
root, then transfers only those operator paths to `nobody`. State and install
paths do not pre-exist; the driver creates them below the private work root.

The driver runs beneath `env -i`, with an exact benign environment allowlist.
Secret-, credential-, authentication-, token-, key-, password-, and proxy-like
variables are forbidden. The root-owned handoff must be readable but not
writable. Before mounting, the isolated controller changes directory to `/`,
then a private mount namespace replaces the checkout with a root-owned,
mode-000, read-only empty view. It changes to the private operator work root
before dropping privileges, and the driver must prove that the workspace is
neither readable nor traversable. A distinct network namespace,
unreadable/unwritable Docker socket, and process-tree `strace` covering network,
process, and signal syscalls are mandatory. A successful path must not signal
either server; both exits are natural.

The trace is evidence in addition to the namespace, not a substitute for it.
One `strace -f -qq` file is validated after the operator exits by the immutable
`scripts/verify_alpha_a1_p2_named_host.py::_validate_strace` parser inherited
from the exact parent. Its resolved executable allowlist is exactly the base
Python, sealed uv, installed Python, `evidencemesh`, and `evidencemesh-mcp`.
The exact eight-path candidate scope proves that parser did not change, so no
separate parser hash slot is necessary.

Explicit AF_UNIX/AF_LOCAL/AF_NETLINK local control-plane syscalls are allowed.
Safe stream or datagram AF_INET/AF_INET6 socket creation without an address is
reported but is not traffic. At most one exact passive IPv6 `::1`, port-zero
bind probe is allowed. Any raw or packet socket, destination-bearing syscall,
DNS action, ambiguous network syscall, second or widened loopback probe, or
unexpected executable is a stop. Successful execution must also contain no
`kill`, `tgkill`, or `tkill` syscall. The report records addressless INET
creations, explicit local syscalls, the passive probe count, and the `execve`
count. The trace and report remain ephemeral.

## Exact operator path

The driver must complete within 600 seconds and use only its declared inputs.
It performs the following bounded sequence:

1. verify the handoff manifest, distinct private roots, empty installation
   prefix, masked checkout, clean environment, and product absence;
2. create one fresh Python 3.11 virtual environment without inherited project
   or user packages;
3. run one uv installation transaction using the combined requirements,
   `--offline`, `--no-index`, `--require-hashes`, and the local wheelhouse;
4. require EvidenceMesh 0.1.0, the accepted wheel SHA-256 in the exact pinned
   requirements input, installed origins and RECORD hashes inside the prefix,
   exact CLI/MCP entry points, both launchers, and a successful dependency
   check;
5. run exactly one CLI command, `evidencemesh providers`, and require local
   status `ready`, community profile, only Wikipedia, no configuration warning,
   private networks disabled, and DNS pinning enabled;
6. render one private mode-0600 descriptor from the exact parent MCP template,
   replacing only the command and cache paths;
7. start MCP session one, perform only `initialize` and `health`, validate the
   same local contract, close the client, and require natural server exit with
   no surviving process;
8. start MCP session two from the same descriptor and state after the first
   natural stop, repeat only `initialize` and `health`, close naturally, and
   again require no surviving process;
9. verify the local SQLite state is structurally sound, snapshot its bytes,
   uninstall only the EvidenceMesh package once, and require dependencies to
   remain coherent;
10. start a new `python -I` probe outside the repository and prove that every
    EvidenceMesh path captured from the installed RECORD, plus metadata,
    import, entry points, and launchers, is absent while the operator state
    remains present and byte-identical.

The second planned start proves restart repeatability after a clean stop only.
There is no crash injection, recovery operation, control-plane repair,
rollback, data purge, or machine restoration claim.

## Evidence and cleanup

The driver writes one bounded JSON receipt. It records only hashes, counts,
booleans, versions, modes, and claim limitations; it must not serialize secrets,
environment values, absolute public locations, queries, URLs, document data,
or model data. Supporting requirements, manifest, descriptor, CLI output, MCP
stderr, SQLite state, the single strace file, and its bounded parser report stay
within the run-scoped root.

After a successful driver exit, the controller takes ownership only of the
private receipt/work and trace trees so it can audit them. Cleanup then runs
unconditionally, recomputes the one deterministic run root even if handoff
construction failed before exporting environment state, terminates only any
surviving process owned by the run's exact operator execution, removes that
root, and confirms that no root, symlink, mount, trace, process, or other output
remains before a success summary is permitted. It does not create or delete the
`nobody` user.

## Stop criteria and claim boundary

The gate stops without retry on any identity, tree, scope, hash, wheel,
wheelhouse, manifest, isolation, permission, environment, installation, RECORD,
entry-point, CLI, descriptor, MCP, natural-stop, process-count, SQLite,
uninstall, state-preservation, trace, traffic, budget, or cleanup failure. A
failed or cancelled attempt is terminal for this candidate.

A successful dedicated run, together with successful ordinary CI on the same
SHA, may establish only an automated Ubuntu 24.04/Python 3.11 simulation of an
unprivileged operator installing one ephemeral unpublished A2 wheel, checking
local configuration, starting and naturally stopping MCP twice, and removing
the package without removing its state.

It does not establish human usability, a public installation path, recovery,
rollback, purge, OS supervision, live provider behavior, research quality,
cross-platform support, Phase 12 readiness, production fitness, or V1
readiness.
