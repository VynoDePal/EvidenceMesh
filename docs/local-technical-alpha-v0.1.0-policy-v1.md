# EvidenceMesh local technical alpha v0.1.0 policy v1

## Decision

The exact commit `644064b5fa097bbf7055f3bf4335ea613afb6387`, identified by the
local tag `v0.1.0-alpha.local`, is a validated local, offline and unpublished
technical alpha. The Python package version remains `0.1.0`; that version is
not a V1-readiness claim.

The local-alpha decision is independent of every upstream response state. It
remains the same if BrowseComp-Plus replies, if a reply exists but is never
read or ingested, or if the public issue remains silent permanently.

This policy recognizes only the exact tagged candidate. It does not identify
the current branch head as a new candidate and does not authorize moving or
publishing the local tag.

## Frozen external-benchmark boundary

Protocol v27 selected an isolated technical-alpha path and explicitly denied
using it as evidence for Phase 11.9, Phase 12 or V1 readiness. Protocol v28
left BrowseComp-Plus unadmitted after exhausting the bounded metadata budget.
This policy preserves those decisions without reopening either protocol.

- BRIGHT remains `blocked` and unadmitted.
- BrowseComp-Plus remains `blocked` and unadmitted.
- No official external score is available.
- Benchmark acquisition, payload inspection, decryption, evaluation and
  scoring remain forbidden.

An absent or unknown external fact continues to fail closed for benchmark
admission. It is not an input to the separately scoped local technical-alpha
decision.

## Issue #28 and evidence strength

The user reported that the locked request was published manually through a
browser at <https://github.com/texttron/BrowseComp-Plus/issues/28>, followed
by a context comment. The only manual-publication state recorded here is
`manual_browser_user_attested`.

The user supplied these values:

- exact initial payload SHA-256:
  `2225c5f25641ecfef944ffb55bd34403753ef8a1c4c191db520857af3660e77c`;
- context-comment SHA-256:
  `cffc9bc965bd8dbddffba75e804a3b45c89a3b03750164798fac4aa326045287`.

They are self-attested values from the user/browser conversation. There is no
local GitHub success receipt and no remote-content read or cryptographic
verification. The values therefore do not prove the bytes currently served by
GitHub, add benchmark evidence or close either BrowseComp-Plus admission gate.

The existing connector receipt remains a separate, immutable historical
record. Its current bytes have SHA-256
`f8144511d2dd46d751cd7fa062f0db3be014f2ff2e6181b8a928cb0b93a003da`
and record only the connector's HTTP 403 failure. The later manual publication
does not supersede or rewrite that receipt.

No upstream response has been read or ingested. Reading, polling, commenting
or ingesting a future response requires a separate explicit GO and a new
budget. Permanent silence is permitted and requires no timeout transition.

## Independent state axes

| Axis | State | Consequence |
|---|---|---|
| Local technical alpha | `validated_local_unpublished` | Exact tagged source may be exercised offline and locally. |
| BRIGHT admission | `blocked` | No asset, evaluation or score. |
| BrowseComp-Plus admission | `blocked` | Issue creation and silence grant no admission. |
| Phase 11.9 | `blocked` | Not authorized or implied by the alpha. |
| Phase 12 | `sealed_blocked` | Not authorized or executed; seal remains intact. |
| V1 readiness | `no_go` | Package version `0.1.0` is not V1 readiness. |
| Public release | `false` | No PyPI, GitHub Release or public binary distribution. |

The local-alpha decision is exactly the conjunction of exact candidate
identity, successful offline technical validation, local-only scope and zero
research traffic. It contains no BRIGHT state, BrowseComp-Plus response state,
Phase 11.9 state, Phase 12 state or V1-readiness state.

## Authority and zero budgets

The local alpha authorizes no provider, model, document-fetch, benchmark-asset,
browser, connector, response-read, tester-contact, retry or publication
operation. Every such local-alpha budget is zero.

Without another explicit GO, every future budget for those same operations is
also zero. In particular, issue #28 does not authorize polling, response
inspection, a follow-up comment, acquisition, scoring, release, merge, live
execution or tester contact.

The local technical-alpha pass cannot authorize a quality or superiority
claim. Phase 11.9 remains blocked, Phase 12 remains sealed and blocked, V1
readiness remains false, merge remains false, and public release remains false.

## Fail-closed rules

Candidate identity or offline technical-gate drift invalidates the local-alpha
decision for the changed candidate. Upstream silence does not. A future reply,
even if authoritative, changes no gate automatically; a separately authorized
protocol must bind, inspect and evaluate it before any external-benchmark state
can change.
