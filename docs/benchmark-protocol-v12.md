# Phase 11.3 network-observability protocol

Protocol lock date: **2026-07-29**.

Phase 11.3 is a **non-scored diagnostic**. It corrects the telemetry limitation
published in Phase 11.2 and determines what happened between routing a Mwmbl
provider call and receiving a usable response. It does not evaluate retrieval
quality, ranking, factual answers or model behavior.

## Decision boundary

The diagnostic cannot:

- promote Mwmbl, YaCy or Wiby into a named provider bundle;
- unlock the untouched Phase 12 evaluation;
- support a comparative or “best” claim;
- make the draft pull request release-ready.

Those decisions remain `false` regardless of the observed endpoint behavior.
Mwmbl also remains experimental because its result license is marked
CC BY-NC-SA 4.0. YaCy is excluded from live Phase 11.3 because no persistent,
reproducibly populated index is available; an empty ephemeral node would test
only adapter correctness.

## Telemetry contract

For each provider, EvidenceMesh separates:

| Field | Meaning |
|---|---|
| `logical_calls` | provider-query operations selected by routing |
| `cache_hits` | logical calls satisfied before circuit or adapter execution |
| `circuit_skips` | logical calls rejected by an open or busy half-open circuit |
| `adapter_invocations` | calls that entered `provider.search` |
| `http_attempts` | requests dispatched through EvidenceMesh's shared HTTPX client |
| `http_responses` | attempts that received response headers |
| `http_failures_without_response` | dispatched attempts without response headers |
| `adapter_latency_ms` | invocation-to-return-or-exception latency |
| `http_attempt_latency_ms` | dispatch-to-headers-or-transport-exception latency |
| `http_status_counts` | response status counts without URLs or bodies |

An adapter that uses a different transport can legitimately report an adapter
invocation with zero instrumented HTTP attempts. The instrumentation scope is
therefore published as `shared_httpx_client_event_hooks`.

Failure messages, URLs, queries and response bodies are not retained in network
telemetry. Exception chains are reduced to a bounded class:

- `circuit_open`;
- an explicit provider class such as `upstream_unavailable` or `invalid_schema`;
- `dns_error`;
- `timeout`;
- `http_status`;
- `invalid_json`;
- `connection_error`;
- `invalid_response_encoding`;
- `protocol_error`;
- `network_error`;
- `invalid_response`;
- a bounded unexpected exception class.

## Live diagnostic

The runner contains four fixed, non-sensitive public probes. The public report
contains only `probe-01` through `probe-04`; it omits their query text.

- provider: Mwmbl only;
- endpoint: the documented public Mwmbl search API;
- cache: disabled;
- retries: none;
- maximum logical calls: 4;
- maximum adapter invocations: 4;
- maximum HTTP attempts: 4;
- provider request deadline: 15 seconds;
- outer wall deadline: 20 seconds per probe;
- pause: at least 1.1 seconds;
- circuit threshold: 3 failures;
- circuit recovery period: 300 seconds;
- Tavily calls: 0;
- Gemini or other model calls: 0;
- paid-provider calls: 0.

If the first three calls fail, the fourth probe is expected to demonstrate a
real circuit skip rather than another network attempt. If calls succeed, all
four may reach the public endpoint. There is no retry in either path.

## Public report

The JSON artifact may contain:

- fixed probe identifiers;
- result counts without result content;
- sanitized failure-class counts;
- HTTP status counts;
- adapter and HTTP-attempt latency;
- circuit state;
- dependency versions, commit and coarse runner environment.

It must not contain:

- query text or target domains;
- source titles, URLs, snippets or bodies;
- raw exception messages;
- request or response headers;
- credentials or environment-variable values.

The result is diagnostic evidence about one GitHub-hosted environment. It is
not an independent network replication and no opportunistic scored benchmark is
allowed after observing it.
