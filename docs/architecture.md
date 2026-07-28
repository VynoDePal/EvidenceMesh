# Architecture

## Boundary

EvidenceMesh retrieves and structures evidence. It does not bundle a language
model, issue hidden truth verdicts or write a final report. This makes the same
retrieval layer usable from MCP hosts, Python applications and shell workflows.

## Request flow

1. Validate the typed request and domain policy.
2. Build transparent query variants or use caller-supplied subqueries.
3. Read per-provider cache entries, then admit compatible provider calls through
   independent circuit breakers and execute them concurrently with deadlines
   that include queue wait.
4. Reject unsafe result URL forms, canonicalise accepted URLs and merge exact
   or same-domain near-duplicate titles.
5. Fuse ranks using weighted reciprocal-rank fusion.
6. Add lexical relevance, source/provenance signals and freshness.
7. Enforce a per-domain cap for source diversity.
8. Optionally resolve selected URLs, reject any non-public answer and connect
   to the exact validated address while preserving HTTP Host and TLS SNI.
9. Extract main HTML/PDF text under time, byte, character and PDF-page limits;
   flag risky patterns and compute SHA-256.
10. Return compact evidence and stable citation IDs.

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

## Extension points

Implement `SearchProvider.search()` and register the adapter in
`providers/factory.py`. Provider adapters must preserve provider-native rank,
identify authentication requirements and translate dates/source types without
inventing missing values.
