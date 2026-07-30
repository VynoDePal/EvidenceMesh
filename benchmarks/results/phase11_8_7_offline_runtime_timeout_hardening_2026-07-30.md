# Phase 11.8.7 offline runtime timeout hardening

Status: **pass — 12/12 offline engineering gates**.

## Outcome

The timeout taxonomy designed in Phase 11.8.6 is now enforced by the actual
EvidenceMesh SDK and MCP runtime. An EvidenceMesh-owned HTTPX client uses
5-second connect, 12-second read, 10-second write and 5-second pool deadlines
under the existing independent 15-second provider wall deadline.

Runtime telemetry now distinguishes:

- `connect_timeout`;
- `read_timeout`;
- `write_timeout`;
- `pool_timeout`;
- `httpx_timeout_unknown`;
- `provider_wall_timeout`.

Invalid configurations in which the wall would equal or undercut a transport
deadline fail before any request. A caller-supplied HTTPX client keeps its own
timeout policy.

## Verification

All twelve locked gates passed. The deterministic replay confirmed the exact
default policy, four environment bindings, owned-client construction, wall
separation, timeout classification, DNS and explicit-kind precedence,
supplied-client ownership, source hashes and historical boundaries.

The generated public record contains no raw exception message, request URL,
query, header, body, provider response, credential, question, evidence or
answer.

## Traffic

This phase made **zero network, provider or model calls**, bound zero secrets and
performed zero retries, fallbacks or repairs. Gemini requests: 0. Tavily
requests: 0.

Local runtime tests use static providers or HTTPX `MockTransport`; they perform
no DNS lookup or socket connection.

## Interpretation boundary

This is an engineering pass, not an availability or quality result. The
historical Phase 11.8.5 `request_timeout` remains
`legacy_request_timeout_unresolved` and its 8/12 no-go is unchanged.

Users still choose their provider, model and credentials. Product defaults are
unchanged. No future live run is authorized. Phase 11.9 and Phase 12 remain
blocked, the pull request remains draft, and merge, release and superiority
claims remain no-go.
