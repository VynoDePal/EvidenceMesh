# Phase 11 retrieval calibration result

Date: 2026-07-29

Workflow run:
[`30456822157`](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30456822157)

EvidenceMesh commit: `4a1ed0a63ec5711fdc326d9d39073f10d972f6dc`

Raw report:
[`phase11_calibration_2026-07-29.json`](phase11_calibration_2026-07-29.json)

Raw SHA-256:
`bafeacfad2d0b831910b6ce1470970b6bf7521e544d238cbf51cfdbdcb8305f7`

## Verdict

**Candidate gate: fail. Phase 12: blocked. Release decision: no-go.**

The community fallback and target-domain diagnostics improved strongly on this
authored 12-case calibration. Every arm except `quality_safe_4_6` retained a
target-domain result in all 12 cases, and every arm returned a full prompt
packet. However, the frozen 8/2 reservation gate failed: all 12 cases had at
least eight eligible Tavily results, but the requested eight slots were filled
in only 10 cases.

The two shortfalls were `p11-005` at 6/8 and `p11-009` at 7/8. Both had nine
eligible Tavily results. The ranking implementation preserves the per-domain
diversity cap while reserving primary-provider slots, so the configured 8/10
share is not an unconditional guarantee. The protocol required full
reservation whenever eight eligible results existed; that threshold is not
changed after observing the run.

This suite measures navigational target-domain retention. It does not measure
answer accuracy, evidence correctness, source quality, citation quality or
external-agent performance.

## Retrieval metrics

| Arm | Availability | Target-domain hit@10 | Mean Tavily selected | Mean prompt results |
|---|---:|---:|---:|---:|
| `tavily_direct` | 12/12 | 12/12 | 8.667 | 8.667 |
| `community` | 12/12 | 12/12 | 0.000 | 10.000 |
| `quality_legacy` | 12/12 | 12/12 | 5.250 | 10.000 |
| `quality_safe_4_6` | 12/12 | 11/12 | 5.417 | 10.000 |
| `quality_safe_6_4` | 12/12 | 12/12 | 6.250 | 10.000 |
| `quality_safe_8_2` | 12/12 | 12/12 | 7.750 | 10.000 |

`quality_safe_8_2` had zero paired target-domain losses against both
`tavily_direct` and `quality_legacy`. Those are positive calibration signals,
but they do not override the failed reservation gate.

## Frozen gates

| Gate | Observed | Required | Result |
|---|---:|---:|---|
| Community availability | 12/12 | at least 11/12 | pass |
| 8/2 target recall vs legacy | 12 vs 12 | not below legacy | pass |
| 8/2 paired losses vs Tavily direct | 0 | at most 1 | pass |
| 8/2 reservation fulfillment | 10/12 | 12/12 evaluable cases | **fail** |
| Tavily traffic | 12 | at most 12 | pass |

Because every frozen gate was mandatory, the Phase 11 candidate did not pass
and the untouched Phase 12 evaluation is not authorized by this result.

## Community resilience

The bounded direct DDGS fallback kept the community arm available and on target
for 12/12 cases. The restored multi-engine SearXNG route still degraded:

- 4/12 SearXNG calls failed because every upstream engine was unavailable;
- 8/12 returned partial results;
- DuckDuckGo was the only recorded contributing SearXNG engine in those eight
  partial responses;
- Brave and Startpage were recorded as unresponsive in every partial response.

This establishes that the direct fallback materially improved this run, but it
does not establish independent free-search redundancy: both the direct DDGS
route and SearXNG's surviving path depended on DuckDuckGo behavior.

## Lineage and traffic

The report traces provider counts through raw, fused, eligible, selected,
evidence and prompt stages, including adjacent losses and sanitized SearXNG
engine failures. No selected evidence was lost during evidence or prompt
projection in this run.

- 12 retrieval operations;
- 48 provider-query calls;
- exactly 12 Tavily basic requests;
- zero Gemini requests;
- zero retries;
- p50 latency 2,487.711 ms;
- p95 latency 2,995.315 ms.

Public output contains no queries, target domains, source titles, URLs,
snippets, evidence text or credentials.

## Provenance

- authored calibration manifest SHA-256:
  `23f0a3c1c6d680b0ec6bdd0964a81f28b23e5778f4965632b03ed5dc4e78c5d7`;
- SearXNG configuration SHA-256:
  `e33610cdd83c89a0fb85e687e632b179ed36057d948db102c7a6e2c33b456efb`;
- artifact ID: `8725894167`;
- artifact ZIP SHA-256:
  `96cda792bae58d34f120fa72592bb45d71d7ca3d5731bde343c0e0c1838e7b54`;
- Python `3.11.15`, DDGS `9.14.4`, httpx `0.28.1`, Pydantic
  `2.13.4`;
- GitHub-hosted `ubuntu-latest`; physical region not exposed.

The settings, sample, thresholds and claim boundary were frozen in
[`docs/benchmark-protocol-v9.md`](../../docs/benchmark-protocol-v9.md) before
the first live request.

## Recommended next engineering work

1. Define a domain-aware primary-provider contract: report both requested and
   feasible reservation, without weakening the diversity cap.
2. Add a genuinely independent free web backend or a second independently
   administered SearXNG route; do not count two DuckDuckGo paths as independent
   redundancy.
3. Run a new authored calibration revision after that change. Do not reinterpret
   this frozen failure as a pass.
4. Keep the PR draft and Phase 12 blocked until the revised retrieval candidate
   passes its own pre-registered gates.
