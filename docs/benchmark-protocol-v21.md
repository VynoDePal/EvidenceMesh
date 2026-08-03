# EvidenceMesh benchmark protocol v21

## Phase 11.8.6 — offline timeout taxonomy and governance diagnostic

Status: frozen offline engineering diagnosis. This phase performs no network,
provider, search or model request and binds no secret. It authorizes no future live
traffic.

## 1. Purpose

The single authorized Phase 11.8.5 live micro-smoke stopped after its third
Gemini request. Two requests returned native HTTP 200 outputs that passed the
strict schema and synthetic semantics. The third produced no HTTP response
before the locked request deadline and was recorded as the coarse category
`request_timeout`.

Phase 11.8.6 closes only the observability and governance gap:

1. define distinct bounded categories for HTTPX connect, read, write and pool
   timeouts;
2. keep the independent benchmark wall timeout separate;
3. prove that raw exception text, URLs, headers, bodies and credentials are
   discarded;
4. refuse to retroactively relabel the historical timeout;
5. separate test-model availability from product-release governance.

It does not rerun Phase 11.8.5, repair the known 17/24 projection defect or
measure retrieval, schema adherence, answer quality or provider availability.

## 2. Documented timeout boundary

HTTPX documents four fine-grained timeout types:

- `ConnectTimeout`: establishing the socket connection;
- `ReadTimeout`: receiving a response-body chunk;
- `WriteTimeout`: sending a request-body chunk;
- `PoolTimeout`: acquiring a pooled connection.

References:

- <https://www.python-httpx.org/advanced/timeouts/>
- <https://www.python-httpx.org/exceptions/>

The benchmark also uses an outer wall deadline implemented independently of
HTTPX. A future runner must preserve these five distinct categories and a
sixth bounded fallback, `httpx_timeout_unknown`, for the HTTPX base timeout
class.

## 3. Immutable historical source

- Phase 11.8.5 raw result:
  `benchmarks/results/phase11_8_5_live_smoke_2026-07-30.json`
- SHA-256:
  `92e092a5929b9c2eb4d2090c61187e8d7d1eba9796d4de85f8f2d288e29a9423`
- Historical verdict: fail, 8/12 gates.
- Historical traffic: three Gemini requests, two native HTTP 200 responses,
  zero HTTP 429, one coarse request timeout, zero Tavily and zero retries.

The historical JSON and verdict are never modified or rescored.

## 4. Exact offline traffic contract

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

No test creates an HTTPX client or transport. HTTPX exception objects are
constructed locally with deliberately private fixture messages and URLs, then
passed directly to the classifier.

## 5. Future timeout policy invariant

The authored policy mirrors the Phase 11.8.5 deadlines:

| Layer | Seconds |
|---|---:|
| Connect | 20 |
| Read | 30 |
| Write | 20 |
| Pool | 20 |
| Benchmark wall | 45 |

Every value must be positive. The wall deadline must be greater than each
transport deadline so a specific HTTPX timeout can surface before the outer
wall masks it. Changing the numerical values requires a separate future
protocol; this phase does not claim that 30 seconds is empirically optimal.

## 6. Public timeout contract

Every newly classified timeout retains only:

- a bounded error kind;
- a bounded layer;
- whether a provider response was observed;
- whether retry is allowed in a scored run;
- explicit false flags for raw-exception and request-URL retention.

Allowed kinds are:

| Exception | Public kind |
|---|---|
| `ConnectTimeout` | `connect_timeout` |
| `ReadTimeout` | `read_timeout` |
| `WriteTimeout` | `write_timeout` |
| `PoolTimeout` | `pool_timeout` |
| other HTTPX `TimeoutException` | `httpx_timeout_unknown` |
| benchmark wall `TimeoutError` | `generation_wall_timeout` |

No scored timeout permits retry, fallback or repair.

## 7. Historical inference boundary

The Phase 11.8.5 runner collapsed every HTTPX timeout into
`request_timeout`. Its 30,022.938-millisecond latency is compatible with the
configured 30-second read deadline, but timing alone does not prove that the
exception was `ReadTimeout`.

The only valid diagnosis is therefore
`legacy_request_timeout_unresolved`. It must not be relabeled as:

- HTTP 429, because no 429 response was observed;
- schema failure, because no native response existed;
- semantic or model-quality failure, because no answer existed.

## 8. Product and benchmark governance

Gemini 3.5 Flash Lite is one test model, not a mandatory EvidenceMesh runtime
dependency. Users retain provider, model and credential choice.

The failed model smoke means benchmark-model availability is unvalidated. The
single timeout does not, by itself, define product-release readiness.
EvidenceMesh nevertheless remains release no-go because broader retrieval,
projection, completion and answer-quality evidence is still blocking.

This separation cannot be used to erase a failed benchmark, weaken quality
gates or authorize a release.

## 9. Blocking offline gates

Phase 11.8.6 passes only if all twelve engineering gates pass:

1. immutable sources match their locked hashes;
2. the Phase 11.8.5 8/12 no-go remains unchanged;
3. all four documented HTTPX transport timeouts are distinct;
4. generic HTTPX and benchmark-wall timeouts are distinct;
5. classification replays deterministically;
6. invalid timeout policies and unsupported exceptions fail closed;
7. private exception and request data are absent;
8. the historical timeout remains unresolved;
9. it is not rewritten as quota, schema or answer-quality evidence;
10. all traffic, secret, retry, fallback and repair counters remain zero;
11. model-smoke and product-release gates remain separate;
12. Phase 11.9, Phase 12, merge and release boundaries remain blocked.

## 10. Decision semantics

A 12/12 pass validates the offline taxonomy and governance contract only. It
does not convert Phase 11.8.5 into a pass and does not authorize:

- a Phase 11.8.5 rerun;
- a future live label or workflow dispatch;
- Phase 11.9 or Phase 12;
- a model or provider default change;
- merge, release, public alpha, external comparison or superiority claims.

Any future live availability test requires a separately frozen protocol,
fresh explicit user authorization and a new traffic ceiling.
