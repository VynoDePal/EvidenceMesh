# Phase 11.2 independent-index calibration

Run date: **2026-07-29**.

GitHub Actions run:
[30466469101](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30466469101).

Benchmark commit:
`de3407470d610c5bde67ab1d8c00ff5e30f76a7b`.

Frozen suite SHA-256:
`670454d6c6bdb93a21bc1ea81f28003e08cac9d24c1663aba53fea50d3ac2423`.

Raw report SHA-256:
`ae0a09bf789881177e53b7ce0f294bc67335d00ba91fc46b4abe5ba36ab961a7`.

Artifact ZIP SHA-256:
`6aa1a3039c040eb5d669840228ff6c75585c96d04acf8e66fb83721f4847d6b7`.

## Decision

**Retrieval candidate: fail. Default promotion: blocked. Phase 12: blocked.
Release: no-go.**

The candidate community route matched the legacy route, but Mwmbl returned no
raw result in any of the 16 cases. The independent fused arm therefore reduced
to Wiby and missed its frozen availability gate by five cases.

| Arm | Prompt availability | Target-domain hit@10 | Cases selecting Mwmbl | Cases selecting Wiby |
|---|---:|---:|---:|---:|
| `legacy_community` | 16/16 | 15/16 | 0/16 | 0/16 |
| `candidate_community` | 16/16 | 15/16 | 0/16 | 2/16 |
| `mwmbl_direct` | 0/16 | 0/16 | 0/16 | 0/16 |
| `wiby_direct` | 7/16 | 1/16 | 0/16 | 7/16 |
| `independent_fused` | 7/16 | 1/16 | 0/16 | 7/16 |

The candidate and legacy arms produced 16 paired ties, zero wins and zero
losses on target-domain hit@10. Adding the independent providers therefore
created no measured target-recall gain.

## Stratum results

| Arm | Broad availability | Broad target | Long-tail availability | Long-tail target |
|---|---:|---:|---:|---:|
| `legacy_community` | 8/8 | 8/8 | 8/8 | 7/8 |
| `candidate_community` | 8/8 | 8/8 | 8/8 | 7/8 |
| `mwmbl_direct` | 0/8 | 0/8 | 0/8 | 0/8 |
| `wiby_direct` | 4/8 | 1/8 | 3/8 | 0/8 |
| `independent_fused` | 4/8 | 1/8 | 3/8 | 0/8 |

## Frozen gates

| Gate | Observed | Required | Result |
|---|---:|---:|---|
| Candidate availability | 16/16; legacy 16/16 | at least 15/16 and no lower than legacy | pass |
| Candidate target recall | 15/16; legacy 15/16 | no lower than legacy | pass |
| Paired candidate losses | 0 | at most 1 | pass |
| Mwmbl availability | 0/16; broad 0/8; long-tail 0/8 | 12/16; 7/8; 6/8 | **fail** |
| Mwmbl selected by candidate | 0/16 | at least 8/16 | **fail** |
| Mwmbl direct target coverage | broad 0/8; long-tail 0/8 | 4/8 in each stratum | **fail** |
| Independent fused availability | 7/16 | at least 12/16 | **fail** |
| Applicable Mwmbl license notice | 0 raw-result cases | at least one raw case and complete notice | **fail** |
| Locked logical-call budget | 80/80 | exact, with zero paid/model/retry calls | pass |

The license-notice gate is unevaluable as a positive provenance claim because
Mwmbl returned no result. It is recorded as a failure by the frozen rule; it
does not indicate that EvidenceMesh stripped a notice from a returned result.

## Failure diagnosis

Mwmbl recorded a sanitized `provider_error` in all 16 routed cases. The first
three complete search operations each took about 25.03 seconds, matching the
configured provider timeout. The remaining 13 averaged about 2.38 seconds.
Together with the process-local circuit threshold of three, this timing is
consistent with three failed Mwmbl adapter attempts followed by circuit-open
skips. The privacy-safe report does not retain exception classes, so timeout is
an evidence-backed inference rather than a directly recorded fact.

The report's `mwmbl_requests: 16` field counts routed logical provider-query
calls. It must not be interpreted as 16 confirmed HTTP network attempts.
Phase 11.2 did not separately count adapter invocations, network attempts and
circuit skips. That telemetry gap is a protocol limitation and must be fixed
before a corrective run.

SearXNG reported total upstream unavailability in 4/16 cases. DDGS and
Wikipedia kept both community arms available in all cases. Wiby returned prompt
evidence in 7/16 cases but hit a target domain in only one case and survived
candidate top-10 selection in two.

Latency was 2.59 seconds at p50 and 25.03 seconds at p95.

## Traffic and privacy

- 16 case retrieval operations;
- 80 routed logical provider-query calls;
- 16 routed Mwmbl calls and 16 routed Wiby calls;
- 0 paid-provider calls;
- 0 Tavily calls;
- 0 Gemini or other model calls;
- 0 retries.

The committed report omits queries, target domains, source titles, source URLs,
snippets, evidence and credentials. It retains only fixed provider/license URLs
and privacy-safe lineage, outcomes and aggregates.

## Interpretation

This run rejects Mwmbl as a default public independent-index dependency in the
measured GitHub-hosted environment. It does not prove that Mwmbl's index has no
useful results: the endpoint did not deliver a usable response to EvidenceMesh
during the scored run.

The YaCy adapter remains an operator-controlled option, but no populated YaCy
index was benchmarked. Adapter correctness is not evidence of broad-Web
quality. Mwmbl and YaCy therefore remain explicit opt-ins; named provider
bundles are unchanged.

A corrective calibration is justified only after:

1. separating routed calls, adapter invocations, actual HTTP attempts and
   circuit skips;
2. preserving a sanitized failure class such as timeout, HTTP status, invalid
   JSON or circuit-open without exposing response data;
3. choosing either a reproducibly populated YaCy index or another active,
   independently administered index;
4. freezing the corrective protocol before any new scored request.

No opportunistic rerun was made. This authored retrieval calibration does not
measure factual answer quality, external-agent performance or an independent
replication network. It cannot support a “best open-source search” claim,
merge or release.
