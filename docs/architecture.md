# Architecture

## Boundary

EvidenceMesh retrieves and structures evidence. It does not bundle a language
model, issue hidden truth verdicts or write a final report. This makes the same
retrieval layer usable from MCP hosts, Python applications and shell workflows.

## Request flow

1. Validate the typed request and domain policy.
2. Build transparent query variants or use caller-supplied subqueries.
3. Route each search profile to compatible source families, enforce transparent
   per-provider query budgets, then read per-provider cache entries.
4. Admit routed calls through independent circuit breakers and execute safe
   groups concurrently with deadlines that include queue wait. Providers with
   stricter upstream rules, such as arXiv, add their own serialization and
   pacing.
5. Reject unsafe result URL forms, canonicalise accepted URLs and merge exact
   or same-domain near-duplicate titles.
6. Fuse ranks using weighted reciprocal-rank fusion.
7. Add lexical relevance, source/provenance signals and freshness.
8. Enforce a profile-aware per-domain cap for source diversity: three for web
   and news, up to ten for single-domain reference, academic and code
   verticals, unless the caller provides an explicit override.
9. Optionally resolve selected URLs, reject any non-public answer and connect
   to the exact validated address while preserving HTTP Host and TLS SNI.
10. Extract main HTML/PDF text under time, byte, character and PDF-page limits;
   flag risky patterns and compute SHA-256.
11. Return compact evidence, stable citation IDs and route telemetry, including
    raw provider degradation and the status of the profile's required source
    family, plus the effective diversity policy.

## Ranking

The final score is:

```text
0.55 × normalised RRF
+ 0.25 × lexical relevance
+ 0.15 × source signal
+ 0.05 × freshness
```

The source signal uses URL and source-type heuristics. It is explicitly not a
truth score. The deterministic tie-break is the canonical URL.

## Failure model

Provider calls are isolated. A failed provider-query pair is included in
`metadata.provider_failures`; successful results are still returned. A complete
absence of eligible providers produces an empty, typed response with a warning.
Timeouts are reported through the same partial-failure path. Three consecutive
operational failures open the provider's process-local circuit for 60 seconds by
default. Calls fail fast while open; after recovery delay, one probe determines
whether to close or reopen the circuit.

`metadata.required_source_family_status` is separate from raw provider
failures. It is `satisfied` when a result from the requested family survives,
`empty` when compatible calls complete without such a result, `failed` when all
required-family calls fail, and `not_configured` when no compatible route
exists. This distinction never suppresses `metadata.provider_failures`.

## Extension points

Implement `SearchProvider.search()`, declare its supported profiles, source
family, query budget and minimum cache lifetime, then register the adapter in
`providers/factory.py`. Provider adapters must preserve provider-native rank,
identify authentication requirements and translate dates/source types without
inventing missing values.
