# EvidenceMesh Alpha A3-P0 internal operator clean-room runbook v1

## Purpose and boundary

This is the locked runbook exercised by the A3-P0 GitHub Actions gate. It is
not a public installation guide. The referenced wheel and dependency
wheelhouse are created ephemerally inside the canonical workflow and are not
available from PyPI, a GitHub Release, an Actions artifact, or another public
distribution channel.

The product subject is the exact A2 parent
`41e0d18e1801cbde0bae61dfd85877fddbc64e4d`. The expected local wheel is
`evidencemesh-0.1.0-py3-none-any.whl`, SHA-256
`c38841da79c7a71275bda5a925096dc692ce4feabaf2f618233c5379ed1c577a`,
146492 bytes. Stop if any identity differs.

The workflow implements the commands through
`scripts/verify_alpha_a3_p0_operator_clean_room.py`; bracketed paths below are
private inputs supplied by the workflow, not values for a public download.

## 1. Accept the private handoff

Required inputs are:

- `[HANDOFF]/wheelhouse/`, containing binary wheels only;
- `[HANDOFF]/requirements.txt`, containing exact `==` pins and SHA-256 hashes,
  including `evidencemesh==0.1.0` bound to the accepted wheel hash;
- `[HANDOFF]/SHA256SUMS`, recursively inventorying every final handoff file;
- `[HANDOFF]/evidencemesh.mcp.json`, copied from the exact parent;
- the content-hash-locked operator driver.

Before the operator receives the kit, the controller verifies the exact manifest,
rejects links and unmanifested content, and changes the handoff to root-owned,
read-only content. The operator must be able to read the handoff and must not
be able to write, replace, rename, or delete any member.

## 2. Enter the clean room

The canonical host is Ubuntu 24.04 x86_64 with Python 3.11. The existing
`nobody:nogroup` identity is used; no account is created. The runner establishes
a private mount namespace, replaces the checkout with an empty, read-only,
mode-000 view that the operator cannot traverse, establishes a distinct network
namespace, drops groups and privileges, and finally starts the driver beneath
`env -i`.

The following sibling roots are distinct, mode 0700, and empty at entry:

- `[HOME]`;
- `[XDG_CACHE_HOME]`;
- `[XDG_CONFIG_HOME]`;
- `[XDG_DATA_HOME]`;
- `[TMPDIR]`;
- `[WORK]`.

`[STATE]` and `[INSTALL]` do not exist at entry. The driver creates both below
`[WORK]`. The isolated controller changes directory to `/` before masking the
checkout with a root-owned, mode-000, read-only empty view, then changes to
`[WORK]` before dropping to `nobody`.

Only locale, timezone, deterministic Python settings, the paths above, and the
minimum executable search path are admitted. Any token, key, secret,
credential, authentication, password, or proxy variable is a stop.

## 3. Install once, offline

The driver first proves that the install prefix contains neither EvidenceMesh
metadata nor either launcher. It creates one fresh Python 3.11 virtual
environment, then performs exactly one package installation transaction with
the equivalent locked shape:

```bash
uv pip install \
  --python "[INSTALL]/bin/python" \
  --offline \
  --no-index \
  --no-cache \
  --no-config \
  --require-hashes \
  --find-links "[HANDOFF]/wheelhouse" \
  --requirements "[HANDOFF]/requirements.txt"
```

No editable, VCS, source-tree, source-distribution, dependency-resolution
fallback, or network installation is allowed. The driver then requires:

- package version 0.1.0;
- the exact accepted wheel SHA-256 in the pinned handoff requirement;
- package metadata and imported modules inside `[INSTALL]`;
- every hashed installed RECORD entry matching its installed bytes;
- exact `evidencemesh` and `evidencemesh-mcp` entry points and launchers;
- a successful dependency check.

## 4. Check local CLI configuration

With the private cache path set to `[STATE]/cache.sqlite3`, the driver executes
exactly:

`evidencemesh providers` is the sole CLI invocation in this gate.

```bash
EVIDENCEMESH_PROVIDERS=wikipedia \
EVIDENCEMESH_CACHE_PATH="[STATE]/cache.sqlite3" \
FASTMCP_CHECK_FOR_UPDATES=off \
"[INSTALL]/bin/evidencemesh" providers
```

The JSON must report version 0.1.0, status `ready`, community profile,
Wikipedia only, no configuration warning, private networks disabled, and DNS
pinning enabled. This command is a local configuration probe, not evidence that
Wikipedia is reachable.

## 5. Render the private MCP descriptor

The driver reads the exact handoff template, changes only its command to
`[INSTALL]/bin/evidencemesh-mcp` and its cache path to
`[STATE]/cache.sqlite3`, and writes `[WORK]/evidencemesh.mcp.json` atomically
with mode 0600. No unresolved placeholder, relative path, shell expansion,
secret, or additional provider is accepted.

## 6. Start and stop twice

For each of two sequential sessions, the driver uses the rendered descriptor
and performs exactly:

1. MCP `initialize`;
2. the initialized notification;
3. one `tools/call` for `health`;
4. client context close;
5. bounded wait for natural server exit;
6. verification that no EvidenceMesh process survived.

Both health responses must match the CLI contract. The second session uses the
same descriptor and state only after the first server has stopped naturally.
This proves two planned clean starts and stops. It does not inject a crash and
does not prove recovery, repair, rollback, or OS supervision.

## 7. Uninstall the package only

After a SQLite integrity check, the driver snapshots the state file and runs
one equivalent uninstall:

```bash
uv pip uninstall \
  --python "[INSTALL]/bin/python" \
  --offline \
  --no-cache \
  --no-config \
  evidencemesh
```

The final probe requires no EvidenceMesh metadata, import, entry point, or
launcher, and requires remaining dependencies to be coherent. The state must
still exist with identical bytes. This is package removal only: dependencies,
the environment, and state are not claimed to be purged or rolled back.

## 8. Receipt and unconditional cleanup

The bounded receipt records identity hashes, counts, booleans, versions,
permissions, successful natural exits, zero observed runtime network/DNS
traffic, package absence, state preservation, and the explicit claim limits.
No handoff, descriptor, trace, receipt, database, wheel, or environment is
uploaded.

After the operator exits, the controller takes ownership only of the private
work/receipt and trace trees for audit. It passes the single `strace -f -qq`
file to the immutable parent
`scripts/verify_alpha_a1_p2_named_host.py::_validate_strace` parser with an
exact resolved allowlist: base Python, sealed uv, installed Python,
`evidencemesh`, and `evidencemesh-mcp`. AF_UNIX/AF_LOCAL/AF_NETLINK local
control-plane calls and safe addressless INET stream/datagram socket creation
are reportable. At most one exact passive IPv6 loopback port-zero bind probe is
accepted. Raw/packet sockets, destinations, DNS actions, ambiguity, unexpected
executables, or a second/widened loopback probe fail closed. The successful
trace must also contain no `kill`, `tgkill`, or `tkill` syscall.

The controller records only the addressless-INET, explicit-local, passive-probe,
and `execve` counts in its bounded ephemeral report and summary. It then
recomputes and removes the exact run-scoped root and confirms no process, mount,
symlink, trace, report, or file survived. The existing `nobody` identity is not
modified or deleted.

## Maximum claim

Subject to the dedicated A3-P0 gate and ordinary CI both succeeding on the same
SHA, this runbook supports only an automated Ubuntu 24.04/Python 3.11 operator
simulation for one ephemeral unpublished wheel: one offline installation, one
local CLI configuration check, two clean MCP starts/stops, and one package-only
uninstall with state preservation.

Human usability, public installation, crash recovery, rollback, purge, service
supervision, live search, cross-platform support, Phase 12, production, and V1
remain unvalidated.
