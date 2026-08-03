# Benchmark protocol v7: paired GitHub repository recall

Status: frozen before the first Phase 9 evaluation request.

## Objective

Phase 8 passed the overall target gate but found only 4/8 authored repository
targets. Its raw-rank diagnostics showed that all four repository misses were
absent from GitHub's returned results, so fusion and diversity tuning could not
recover them.

Phase 9 isolates that failure. It compares the Phase 8 GitHub query strategy
with a candidate entity-anchor strategy on the same 24 untouched repository
queries, in the same process and network environment.

This is a repository-retrieval calibration. It is not an end-to-end
deep-research benchmark or evidence of general superiority.

## Development evidence kept outside the evaluation suite

Before authoring the locked suite, the four Phase 8 repository misses were used
as a development set. Public GitHub API probes reproduced the failure:
descriptive multi-term searches did not return the authored FastAPI, Django,
Requests or NumPy repository in the first ten results. Searches using only the
repository entity placed each target first.

Those four targets and queries are excluded from the Phase 9 suite. Phase 7
targets are excluded as well.

The official GitHub documentation establishes the relevant constraints:

- repository search uses best-match ordering unless another sort is supplied;
- `in:name`, `in:description`, `in:topics` and `in:readme` control the searched
  repository fields;
- omitting `in:` searches name, description and topics;
- repository queries are limited to 256 non-qualifier characters and five
  boolean operators;
- anonymous search is limited to ten requests per minute.

## Candidate query strategy

Production defaults to `entity-anchor-v2`:

1. preserve explicit GitHub qualifiers unchanged;
2. convert an exact GitHub URL or `owner/repository` reference into a `repo:`
   qualifier;
3. remove leading intents such as `official repository for` and trailing
   intents such as `source code`;
4. retain the leading repository entity until a deterministic descriptor
   boundary such as a language, `framework`, `library`, `runtime` or
   `repository`;
5. search the entity in `name`, `description` and `topics`;
6. cap the resulting query at 256 characters.

No LLM, network lookup, target value or benchmark-specific repository list is
used by the planner.

The frozen baseline `legacy-v1` removes only trailing repository intent and
then appends `in:name,description`. Both implementations are present in the
same candidate commit so that the live comparison changes only the query
strategy.

## Frozen suite

- File: `benchmarks/data/github_recall_v1.json`
- SHA-256:
  `0cfafa78e44662af47e51f26775593af0e3e9d6dbbc417d18178f1218f5ad61a`
- Ordered ID manifest SHA-256:
  `7369c9a0f47e4dbf4f752885f32bdf28e44b0472a5129353e75f4da616d20e57`
- 24 unique public repository targets
- eight authored low-, medium- and high-ambiguity cases
- twelve entity-first and twelve intent-prefix queries
- no target or exact-query overlap with Phase 7 or Phase 8 repository cases
- every target repository was checked directly before locking and was neither
  archived nor disabled

Direct existence checks are not search probes and do not reveal how either arm
will rank a target.

## Paired execution

- Provider: GitHub public repository search only
- Authentication: anonymous
- Arms: `legacy-v1` and `entity-anchor-v2`
- 24 cases per arm, 48 requests total
- exactly one provider query per arm and case
- first page only, at most 20 provider results and ten final results
- alternating arm order for successive cases
- sequential requests with at least 6.5 seconds between starts
- 20-second request deadline
- no retry
- cache disabled
- content fetching disabled
- no Tavily, SearXNG or other provider
- no new user secret

The 6.5-second interval keeps one process below GitHub's documented anonymous
limit of ten search requests per minute. A rate-limit or provider failure is
recorded and not retried.

## Metrics

For each arm and each difficulty stratum, the report records:

- request success and result availability;
- canonical target hit at ten;
- target rank at one, three, five and ten;
- raw target presence in the provider's first 20 results;
- target loss between provider output and final ranking;
- p50, p95 and maximum latency;
- result, query and cache counts.

The paired report records candidate wins, baseline wins, ties, net gain and the
two-sided exact McNemar p-value for target hit and raw target presence.

Public outcomes contain case IDs, arm labels, booleans, counts, ranks and
latencies only. They omit queries, normalized queries, titles, snippets,
content, URLs, result lists and target identities.

## Frozen functional gates

### Candidate arm

| Gate | Threshold |
|---|---:|
| Successful requests | at least 23/24 |
| Available result sets | at least 23/24 |
| Raw target seen in first 20 | at least 20/24 |
| Final target hit at 10 | at least 18/24 |
| p95 latency | at most 15,000 ms |
| Query budget | exactly one per case |
| Cache hits | zero |

### Paired comparison

| Gate | Threshold |
|---|---:|
| Net final-target gain | at least four cases |
| Final-target regressions | zero |
| Candidate raw recall | not below baseline |

No threshold, suite row, target, planner rule or traffic constraint may change
after the first evaluation request. A failed gate requires a new suite and
protocol version.

## Release boundary

The second independently administered network remains unavailable, so the
cross-network gate stays `not_testable` at 1/2 environments.

Regardless of the Phase 9 functional result:

- the 200-case Stage B benchmark remains blocked;
- the pull request remains draft;
- merge, package publication, production-readiness and superiority claims
  remain blocked.

Relevant upstream documentation:

- [GitHub repository search syntax](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)
- [GitHub REST search API](https://docs.github.com/en/rest/search/search)
- [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
