# EvidenceMesh benchmark protocol v22

## Phase 11.8.7 — offline runtime timeout hardening

Status: frozen offline implementation and verification phase. This phase sends no
network, provider, search or model request, binds no secret and authorizes no future
live traffic.

## 1. Purpose

Phase 11.8.6 defined a privacy-safe timeout taxonomy but did not apply it to the
EvidenceMesh SDK and MCP runtime. The runtime still configured one equal HTTPX
timeout and reported every transport or wall timeout as the generic `timeout`
category.

Phase 11.8.7 closes that runtime gap only:

1. configure distinct HTTPX connect, read, write and pool deadlines on clients
   owned by EvidenceMesh;
2. preserve the existing 15-second provider wall deadline;
3. expose exact bounded timeout categories in normal SDK and MCP search metadata;
4. validate the layered policy at configuration time;
5. preserve caller ownership and timeout settings for a supplied HTTPX client;
6. document and test the behavior without contacting any provider.

It does not rerun Phase 11.8.5, change a provider or model default, repair the
known 17/24 projection defect or measure search or answer quality.

## 2. Locked runtime policy

| Runtime layer | Default seconds | Environment variable |
|---|---:|---|
| HTTPX connect | 5 | `EVIDENCEMESH_PROVIDER_CONNECT_TIMEOUT` |
| HTTPX read | 12 | `EVIDENCEMESH_PROVIDER_READ_TIMEOUT` |
| HTTPX write | 10 | `EVIDENCEMESH_PROVIDER_WRITE_TIMEOUT` |
| HTTPX pool | 5 | `EVIDENCEMESH_PROVIDER_POOL_TIMEOUT` |
| Provider wall | 15 | `EVIDENCEMESH_REQUEST_TIMEOUT` |

All values must be positive. The provider wall deadline must be strictly greater
than every transport deadline. An invalid policy fails configuration validation
before any request can be made.

The wall includes concurrency-queue time and the provider adapter invocation. A
specific HTTPX transport deadline is intentionally shorter so its exact category
can surface before the wall masks it.

## 3. Client ownership contract

When EvidenceMesh creates its shared `httpx.AsyncClient`, it installs the four
transport deadlines above. When a caller supplies a client, EvidenceMesh attaches
only its existing request/response telemetry hooks; it does not replace or mutate
that client's timeout policy and does not close the supplied client.

The independent document fetcher retains its separate fetch, DNS and extraction
deadlines. This phase changes provider-search transport timing only.

## 4. Public timeout taxonomy

| Runtime exception | Public failure kind |
|---|---|
| `httpx.ConnectTimeout` | `connect_timeout` |
| `httpx.ReadTimeout` | `read_timeout` |
| `httpx.WriteTimeout` | `write_timeout` |
| `httpx.PoolTimeout` | `pool_timeout` |
| other `httpx.TimeoutException` | `httpx_timeout_unknown` |
| provider wall `TimeoutError` | `provider_wall_timeout` |

DNS failure remains `dns_error`, including when it appears under a connection
exception. An explicit non-generic `ProviderError.kind` remains authoritative.
The public classifier retains only a bounded kind and, where applicable, a numeric
HTTP status. It never retains an exception message, URL, query, headers, body,
provider response or credential.

Historical reports are immutable. In particular, the Phase 11.8.5
`request_timeout` remains `legacy_request_timeout_unresolved`; Phase 11.8.7 does
not relabel it.

## 5. Exact offline traffic contract

| Dimension | Required |
|---|---:|
| Network requests | 0 |
| Provider calls | 0 |
| Model calls | 0 |
| Bound secrets | 0 |
| Gemini requests | 0 |
| Tavily requests | 0 |
| Retries | 0 |
| Fallbacks | 0 |
| Repairs | 0 |

The deterministic report creates only local settings, request and exception
objects. It creates no HTTPX client or transport. Runtime unit tests use local
providers or `MockTransport`; no DNS lookup or socket is permitted.

## 6. Reproducibility and source boundary

The offline runner locks:

- this protocol;
- `src/evidencemesh/config.py`;
- `src/evidencemesh/engine.py`;
- `src/evidencemesh/telemetry.py`;
- the immutable Phase 11.8.6 JSON result.

The CI workflow has read-only repository permission, receives no secret and
byte-compares a freshly generated report with the committed JSON.

## 7. Blocking offline gates

Phase 11.8.7 passes only if all twelve engineering gates pass:

1. the protocol, runtime sources and Phase 11.8.6 result match locked hashes;
2. the exact 5/12/10/5/15-second default policy is present;
3. every invalid or masking timeout policy fails closed;
4. all four environment overrides map to their intended fields;
5. the owned client uses all four explicit HTTPX timeout layers;
6. the provider wall remains independent and reports `provider_wall_timeout`;
7. all four specific HTTPX timeout classes remain distinct;
8. generic HTTPX and provider-wall timeouts remain distinct;
9. classification is deterministic, bounded and omits private fixture data;
10. DNS precedence, explicit provider kinds and supplied-client ownership remain
    preserved;
11. network, provider, model, secret, retry, fallback and repair counts are zero;
12. historical no-go, user choice and phase/release boundaries remain preserved.

## 8. Decision semantics

A 12/12 pass validates runtime timeout engineering only. It does not establish
provider availability, quota headroom, retrieval quality, answer quality or
release readiness. Users retain provider, model and credential choice.

This phase does not authorize:

- a Phase 11.8.5 rerun or any other live request;
- Phase 11.9 or Phase 12;
- a provider, model or credential default change;
- marking the draft pull request ready, merging it or releasing a package;
- an external comparison or superiority claim.

Any future live test requires a separately frozen protocol, a new bounded traffic
ceiling and fresh explicit user authorization.
