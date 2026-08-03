# EvidenceMesh Alpha-RC3 governor offline protocol v1

## Decision boundary

This phase implements and tests the closed-alpha dispatch governor. It sends no
research, provider, Tavily or model request. It authorizes no tester contact,
live session, merge, release or quality claim. The historical RC2 candidate at
`81b5f8a8abd4302b27ad123bd5505e1757eadc7f` and the A0 preparation commit at
`540eca26ffb97908320a5ecea5f1bf3fb4f0247a` remain immutable evidence.

RC3 is a new runtime candidate because pre-dispatch enforcement changes product
code. It is not an amendment to RC2 and does not silently promote A0 to live.

## Enforced contract

The process opens one pseudonymous, single-task session. Every outbound start is
reserved in a private SQLite ledger before the provider task or HTTP transport
can run. The reservation transaction atomically checks all applicable ceilings:

| Dimension | Maximum |
|---|---:|
| Sessions in the ledger | 40 |
| Sessions per participant code | 5 |
| Outbound attempts per session | 6 |
| Outbound attempts in the ledger | 240 |
| Tavily attempts per community session | 0 |
| Tavily attempts per quality session | 4 |
| Tavily attempts in the ledger | 40 |
| Concurrent active sessions | 2 |
| Governed HTTPX request starts in any rolling 60 seconds | 10 |

A rejected batch spends nothing. An accepted reservation is never refunded on
timeout, cancellation, transport error or empty response. Each permit can reach
the HTTP transport once. A second request, retry or replay fails before the
transport. Fetch, `robots.txt` and each redirect reserve their own attempt.
For this contract, a request starts when the first governor HTTPX request hook
atomically admits it, before any later HTTPX hook or transport operation. The
rolling window is checked there; a permit refused there is consumed without
reaching transport. Multi-address fallback is disabled in strict mode. The
shared timestamps use the host monotonic clock; a regression, including a stale
ledger after host reboot, poisons closed.

Cache use is rejected before dispatch. The ledger directory and file must be
private (`0700` and `0600`), regular and non-symlinked. Corruption, permission
drift, policy drift, clock regression, session reuse or missing context poisons
the path closed. The ledger stores only participant/session codes, profile,
bounded intent kind, provider name, timestamps, owner/token identifiers and
counters. It stores no query, URL, title, snippet, evidence, response, exception
text or credential.

## Supported runtime boundary

Strict mode accepts only the audited, single-request HTTPX adapters for arXiv,
Crossref, GitHub, SearXNG, Tavily and Wikipedia, all bound to the governed
client. DDGS is refused before `asyncio.to_thread` because its internal backend
fan-out cannot consume one EvidenceMesh permit per upstream request. Custom
providers and extra SearXNG fallback endpoints are also refused.

CLI and MCP STDIO are supported only as one process per session. MCP HTTP is
refused because a long-lived multi-user process cannot bind one immutable
session context safely. `search`, `research`, `fetch`, `batch_search` and
`verify_claim` all force `use_cache=false` when the strict environment is
selected. A provider plan larger than six is rejected atomically before
`asyncio.gather`; it is never truncated into an undisclosed partial plan.

Four environment values activate the strict CLI/MCP path, and partial
configuration is an error:

- `EVIDENCEMESH_CLOSED_ALPHA_LEDGER`: absolute SQLite path under a private directory;
- `EVIDENCEMESH_CLOSED_ALPHA_PARTICIPANT`: `p-` plus 16 lowercase hexadecimal digits;
- `EVIDENCEMESH_CLOSED_ALPHA_SESSION`: `s-` plus 32 lowercase hexadecimal digits;
- `EVIDENCEMESH_CLOSED_ALPHA_PROFILE`: `community` or `quality`.

The enabled provider list must also exclude DDGS and all unaudited providers.
No credential value may enter the ledger or an offline report.

## Scope limitation

The word global means all processes sharing one ledger on one host. Eight
independent device-local ledgers cannot enforce a shared 240-attempt ceiling,
two-session concurrency or ten-start rolling rate. RC3 deliberately reports
`distributed_global_budget_enforcement_ready=false`. A later live design must
either centralize all sessions on one execution host or introduce a separately
reviewed remote coordinator. This offline phase chooses neither.

## Offline validation

The dedicated workflow installs dependencies first, then executes the complete
test suite, formatting, lint, strict type checking and package build inside a
network namespace with no research networking. The generic CI SearXNG job is
skipped only for the exact PR #1 alpha branch because its external engines
would violate the zero-research-traffic boundary; the adapter remains covered
by the mocked complete suite. Focused adversarial tests prove:

1. atomic session, participant, global and Tavily limits;
2. exact rolling-minute and concurrent-session boundaries;
3. rejected batches and community Tavily spend zero;
4. permits remain spent after errors and cannot be replayed;
5. an absent permit never reaches `httpx.MockTransport`;
6. cache-on, DDGS, custom providers and HTTP MCP fail closed;
7. robots, page fetches and redirects each reserve separately;
8. a provider plan above six reaches no transport;
9. corrupt, public, symlinked or policy-mismatched ledgers are rejected; and
10. historical RC2, A0 and benchmark results reproduce without mutation.

The maximum research budget for the workflow and local validation is exactly
zero provider requests and zero model requests. Synthetic `MockTransport`
requests do not leave the process.

## Stop criteria

Stop before publication if any runtime path can reach a transport without a
permit; a concurrent transaction can oversubscribe; a rejected operation
increments a counter; a permit can be reused; cache becomes reachable; DDGS or
an unknown provider enters strict mode; a historical A0/RC2 file changes; any
test, lint, type, build or zero-network gate fails; or any real provider/model
request is needed.

Even after all offline gates pass, live remains blocked. A separate decision is
required for centralized execution versus distributed coordination, followed
by a new A0 adoption record bound to an accepted RC3 artifact and a separate
explicit live GO.
