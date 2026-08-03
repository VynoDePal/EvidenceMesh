# Phase 11.8.6 — offline timeout diagnostic

## Verdict

**PASS: 12/12 offline engineering gates.**

This result was produced with zero network or provider call, zero model call,
zero bound secret, zero retry, zero fallback and zero repair. It validates the
timeout taxonomy and governance guardrails only.

Phase 11.8.5 remains an unchanged **FAIL: 8/12**. Its third Gemini request
ended as `request_timeout` after 30,022.938 ms, with no HTTP response. The
duration is compatible with the locked 30-second read deadline, but the old
runner did not preserve the HTTPX subclass. The only supportable diagnosis is
therefore `legacy_request_timeout_unresolved`; a `ReadTimeout` is not proven.

## Reproducibility locks

| Artifact | SHA-256 |
|---|---|
| Protocol v21 | `b7d62af73021db103747acb5b0b0d670a6a52f0a4fa93986377657f1b2dc8120` |
| Timeout guardrails | `c20a094e56d638071780229cbb00a31482b4ac892c9bf66d091ad36af7eba231` |
| Historical Phase 11.8.5 JSON | `92e092a5929b9c2eb4d2090c61187e8d7d1eba9796d4de85f8f2d288e29a9423` |
| Phase 11.8.6 result JSON | `72635a442aa4062f6588e5f7fcaec49abb68de52dc8da96f790fd88b55602207` |

## Exact taxonomy for future benchmark runners

| Exception boundary | Public result |
|---|---|
| HTTPX `ConnectTimeout` | `connect_timeout` |
| HTTPX `ReadTimeout` | `read_timeout` |
| HTTPX `WriteTimeout` | `write_timeout` |
| HTTPX `PoolTimeout` | `pool_timeout` |
| Other HTTPX timeout | `httpx_timeout_unknown` |
| Independent benchmark wall deadline | `generation_wall_timeout` |

All six fixture classes replayed deterministically. Invalid timeout policies
and unsupported exceptions failed closed. Public diagnostics retained no raw
exception text, request URL, header, body, provider response or credential.

## Historical interpretation

The Phase 11.8.5 event cannot be rewritten as HTTP 429, schema failure or
answer-quality failure:

- no HTTP 429 response was observed;
- no provider response existed to validate against the schema;
- no generated answer existed to score semantically.

This preserves the raw failure without overclaiming its transport subtype.

## Product and release boundary

Gemini 3.5 Flash Lite remains one optional test model. Users choose their own
provider, model and credentials. This isolated model timeout does not, by itself,
block product release; model-smoke availability and product readiness are
separate gates.

The broader EvidenceMesh quality evidence is still blocking, so release
remains no-go. Phase 11.9 and Phase 12 remain blocked, as do merge, public
alpha, external comparison and superiority claims.

This phase authorizes no rerun and no future live request. A later availability
experiment would require a new frozen protocol, a new traffic ceiling and
fresh explicit authorization.
