# Phase 11.1 feasibility calibration result

Date: 2026-07-29

Successful workflow run:
[`30459875158`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30459875158)

EvidenceMesh commit: `7d83ea3bca128e50397c9898db8bf06cd78d6d25`

Raw report:
[`phase11_1_calibration_2026-07-29.json`](phase11_1_calibration_2026-07-29.json)

Raw SHA-256:
`0c8a0a08f54477e44968c40519f228e94341cf17b41e0ffaf163bb831a6abfe3`

## Verdict

**Candidate gate: fail. Phase 12: blocked. Release decision: no-go.**

The domain-aware reservation contract behaved as designed: every case filled
its feasible target. It did not meet the separate frozen strength floor,
however. The 8/2 arm reached 89 total target slots out of 96 requested, below
the required 90, and only 10/12 cases retained a target of at least six.

Wiby proved that the adapter, attribution and independent index work, but not
that it is a sufficiently broad default fallback for this suite. It returned
prompt evidence in 4/12 cases, below the required 6/12, and no Wiby result
survived community top-10 selection, below the required 3/12.

The thresholds remain unchanged after observing the run. Wiby stays available
as an explicit opt-in provider and is not promoted into the named deployment
bundles.

This authored suite measures retrieval availability and navigational
target-domain retention. It does not measure answer correctness, source truth,
citation quality or external-agent performance.

## Retrieval metrics

| Arm | Availability | Target-domain hit@10 | Mean Tavily selected | Mean Wiby selected |
|---|---:|---:|---:|---:|
| `tavily_direct` | 12/12 | 12/12 | 8.333 | 0.000 |
| `wiby_direct` | 4/12 | 0/12 | 0.000 | 0.583 |
| `community` | 12/12 | 12/12 | 0.000 | 0.000 |
| `quality_legacy` | 12/12 | 12/12 | 5.583 | 0.000 |
| `quality_safe_4_6` | 12/12 | 12/12 | 5.667 | 0.000 |
| `quality_safe_6_4` | 12/12 | 12/12 | 6.250 | 0.000 |
| `quality_safe_8_2` | 12/12 | 12/12 | 7.417 | 0.000 |

The 8/2 arm had zero paired target-domain losses against Tavily direct and
legacy quality. Those positive diagnostics do not override the three failed
gates.

## Frozen gates

| Gate | Observed | Required | Result |
|---|---:|---:|---|
| Community availability | 12/12 | at least 11/12 | pass |
| 8/2 target recall vs legacy | 12 vs 12 | not below legacy | pass |
| 8/2 paired losses vs Tavily direct | 0 | at most 1 | pass |
| Domain-aware target fulfillment | 12/12 | 12/12 | pass |
| Domain-aware target strength | 89/96; 10 targets at least 6 | at least 90/96; 12 targets at least 6 | **fail** |
| Wiby raw availability | 4/12 | at least 6/12 | **fail** |
| Wiby selected community contribution | 0/12 | at least 3/12 | **fail** |
| Wiby attribution | 4/4 applicable cases | all applicable cases | pass |
| Tavily and Wiby traffic | 12 each | at most 12 each | pass |

Because every frozen gate was mandatory, the candidate failed and this result
does not authorize Phase 12.

## Reservation diagnosis

The new telemetry prevents a domain-diversity constraint from being mislabeled
as an implementation failure:

- ten cases had a feasible target of at least six and fulfilled it;
- `p11-005` had six eligible Tavily results, five domain-feasible, target five
  and fulfilled five;
- `p11-009` had nine eligible, seven domain-feasible, target seven and fulfilled
  seven;
- `p11-011` had five eligible, five domain-feasible, target five and fulfilled
  five.

The failed strength floor is intentional: feasibility observability must not
allow the requested 8/10 policy to collapse silently.

## Independent-index diagnosis

Wiby returned seven total prompt results across four cases. The mandatory
`https://wiby.me/` attribution was present in all four applicable responses.
None of those results reached the community top ten after common fusion,
relevance and diversity ranking.

This result does not show that Wiby's index is invalid. It shows that the
specialized small-web index did not provide enough coverage or selected
contribution on this developer-documentation-heavy calibration to become a
default broad-web fallback.

The private SearXNG route also remained degraded:

- 2/12 calls failed because every configured upstream engine was unavailable;
- 10/12 returned partial results;
- DuckDuckGo was the only recorded contributing SearXNG engine;
- Brave and Startpage were unresponsive in all ten partial responses.

Community remained available and on target in 12/12 cases, but the independent
Wiby path did not survive selection. Broad independent-index redundancy is
therefore still unproven.

## Traffic, privacy and provenance

- 12 retrieval operations;
- 60 provider-query calls;
- exactly 12 Tavily requests;
- exactly 12 Wiby requests;
- zero Gemini requests;
- zero retries;
- p50 latency 2,729.748 ms;
- p95 latency 3,419.433 ms.

Public output excludes queries, target domains, source titles, source URLs,
snippets, evidence text and credentials. It retains only the fixed provider
attribution URL required by Wiby.

- authored suite SHA-256:
  `23f0a3c1c6d680b0ec6bdd0964a81f28b23e5778f4965632b03ed5dc4e78c5d7`;
- SearXNG configuration SHA-256:
  `e33610cdd83c89a0fb85e687e632b179ed36057d948db102c7a6e2c33b456efb`;
- artifact ID: `8727140793`;
- artifact ZIP SHA-256:
  `208d90aa794a5b542ae02adf76dc39a9f3a51ae5b2a3176fbb7a0f7646e20e30`;
- Python `3.11.15`, DDGS `9.14.4`, httpx `0.28.1`, Pydantic `2.13.4`;
- GitHub-hosted Ubuntu runner; the job log identified Azure region `westus`.

An initial workflow run
[`30459654258`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30459654258)
failed on a local module import before any benchmark provider call. Commit
`7d83ea3` added a direct-execution import fallback without changing the suite,
thresholds, provider configuration or traffic. The successful run above is the
only scored Phase 11.1 run.

The settings, thresholds and claim boundary were frozen in
[`docs/benchmark-protocol-v10.md`](../../docs/benchmark-protocol-v10.md) before
the first benchmark-suite request. One earlier non-suite Wiby `q=test` schema
check is disclosed there.

## Recommended next engineering work

1. Keep the domain-aware telemetry; it correctly separated feasibility from
   fulfillment while preserving a strength floor.
2. Keep Wiby as an opt-in specialized index, not default broad-web redundancy.
3. Evaluate a reproducibly self-hosted independent crawler/index, with a new
   protocol and an index-appropriate authored calibration before live traffic.
4. Do not run Phase 12 until the revised retrieval candidate passes its own
   frozen gates.
