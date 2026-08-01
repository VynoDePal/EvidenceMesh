# EvidenceMesh 0.1.0 local technical alpha acceptance protocol v1

## Decision

This protocol accepts exactly the annotated Git tag
`v0.1.0-alpha.local` as an unpublished, local-only technical alpha. The tag
object is `196cfaca0458f81d4d5cd7de54f7adbf80ad1e57`; it resolves to commit
`644064b5fa097bbf7055f3bf4335ea613afb6387`, tree
`7a774664442caa9201b419fb219d47c6113a52a3` and parent
`61a58660cb77ba160e8ecfed53d09fdcd1d60c57`.

The accepted scope is one-host, offline technical use with synthetic inputs.
It is not a closed-alpha deployment, external-benchmark admission, quality
claim, Phase 11.9 or Phase 12 authorization, V1 readiness decision, public
distribution, merge or release.

One known live-only blocker is deliberately outside this candidate: the
retention scheduler has no control-plane heartbeat or lease checked at
`prepared`, reservation and the first HTTPX hook. A future RC4.2 must make
scheduler absence, expiry and failure pause the ledger before any live session
can be considered. That missing live supervision does not affect a zero-session
local technical alpha, but it is a hard stop for closed-alpha adoption.

## Independence from external responses

BrowseComp-Plus and BRIGHT are not inputs to this acceptance decision. A
BrowseComp-Plus response may be pending forever, absent, unread, positive,
negative or ambiguous without changing the local-alpha result. No response is
treated as neither permission nor refusal. It leaves BrowseComp-Plus blocked
and unadmitted.

The public issue is only a contact event. It is not benchmark evidence,
software publication or permission to acquire benchmark assets. The historical
failed connector receipt remains immutable. The later manual-browser event is
recorded separately as user-attested context and is not upgraded into a
cryptographic receipt.

## Exact-candidate entry criteria

Acceptance requires all of the following:

1. the annotated candidate tag, tag object, commit, tree and parent match the
   identities above;
2. the package metadata version is exactly `0.1.0` and the development-status
   classifier remains `Alpha`;
3. `pyproject.toml`, `uv.lock`, the RC4.1A protocol, policy and workflow match
   their recorded SHA-256 digests;
4. the candidate is exported from the tag, not copied from the later branch
   head, and all source-executing gates run from that clean export;
5. dependency acquisition is complete before the offline verification window;
6. the focused RC4/RC4.1A tests, complete candidate suite, branch-coverage
   floor, Ruff format and lint, strict MyPy, wheel and source-distribution
   builds, and isolated installed-distribution smokes all pass; and
7. the run makes no provider, search, model, token-count, document-fetch,
   benchmark-asset or tester request.

## Verification method

The clean export uses `SOURCE_DATE_EPOCH=1785577726`, the candidate commit
timestamp. Ruff checks all 225 candidate files. The focused RC4/RC4.1A set
contains 99 tests. The complete candidate suite contains 885 tests; it may be
split into disjoint groups only to remain within a bounded local runner, and
the union must still be the complete suite. Branch coverage must be at least
85 percent.

The wheel and source archive are built twice from clean candidate exports with
the same source epoch. Their names, sizes and SHA-256 digests must agree across
the two builds. Each archive is installed into its own isolated environment
from the local file. The installed checks exercise package import and version,
CLI, MCP over STDIO, provider isolation, the single-host governor, private
ledger permissions and HTTP-transport refusal. They bind the imported package,
the two console launchers and six critical package files to the installed
distribution, its RECORD SHA-256 values and the tested source archive.

For each distribution, three environment-binding probes and three product
subprocesses load a private `sitecustomize` guard. The guard permits the local
STDIO/AF_UNIX machinery needed by the harness but blocks the exercised Python
socket paths for AF_INET and AF_INET6. FastMCP update checks are explicitly
disabled. All six final-run guard markers remain armed and record no network
access attempt. This is process-level evidence with a Python-socket-API scope;
it is not an OS network namespace or a claim about every possible native
network syscall.

The installer recorded an exact PEP 610 source-archive URL but no archive
SHA-256. The verifier therefore re-hashes the archive after installation and
checks its six critical files against the installed copies and RECORD. That
materially binds the exercised runtime, but it does not eliminate every
install-to-smoke time-of-check/time-of-use possibility; the acceptance record
keeps that limitation explicit.

Build products and raw smoke logs are ephemeral. The normalized smoke reports
and their recorded digests identify what passed; they do not authorize
uploading or distributing those files.

The managed runner did not permit creation of a separate empty network
namespace. The final installed-smoke runs recorded no Python socket access and
performed no external request, but this acceptance does not claim OS-enforced
network isolation. That limitation, the URL-only PEP 610 receipt, the unsigned
local tag and the shallow repository history are acceptable only for this
narrow local scope and remain blockers for public provenance or release.

## Request and action budget

| Dimension | Maximum |
|---|---:|
| Provider or search requests | 0 |
| Tavily requests | 0 |
| Model or token-count requests | 0 |
| Document fetches | 0 |
| Benchmark-asset downloads | 0 |
| External-response reads | 0 |
| Tester contacts or sessions | 0 |
| Live sessions | 0 |
| Automatic retries, fallbacks or repairs | 0 |
| Branch publications or merges | 0 |
| Uploaded artifacts or attestations | 0 |
| Published distributions or releases | 0 |

Pinned interpreter and locked dependency acquisition before the offline window
is a supply-chain operation. It does not authorize research traffic or secrets.

## Stop criteria

Stop without retry or acceptance if any exact identity or immutable digest
differs; any gate, build, installed smoke, cleanup or reproducibility check
fails; coverage is below the floor; any real provider, model, document,
benchmark or tester access occurs; or any artifact must be published for the
result to hold.

An external response, including permanent silence, is not a local-alpha stop
condition. Permanent silence remains a stop condition for benchmark admission
and every downstream quality or release phase. Any future response has no
automatic authority: a separate ingestion and admission protocol would still
be required before one of those gates could open.

## Seal model

The machine-readable acceptance record binds the pre-existing candidate tag
and the exact ephemeral build identities. It is committed only after the run,
so it cannot be part of the candidate tree it attests. The non-runtime commit
containing that record, its verifier, tests and documentation is the local
acceptance seal. Neither that seal nor an optional local seal tag changes the
accepted candidate bytes.
