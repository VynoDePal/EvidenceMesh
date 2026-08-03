# Phase 11.8.5 Gemini quota/schema micro-smoke — audited result

**Verdict: live smoke failed (8/12 gates passed). The run stopped on a
request timeout after three Gemini requests, with zero HTTP 429 response.
Phase 11.9 and Phase 12 remain blocked; release remains no-go.**

## Provenance and scope

- Live run:
  [GitHub Actions 30568779397](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30568779397)
- Artifact:
  [8769965903](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30568779397/artifacts/8769965903),
  `phase11-8-5-live-smoke-30568779397`
- Frozen protocol:
  [benchmark protocol v20](../../docs/benchmark-protocol-v20.md), SHA-256
  `6c41f28afbf1ae4d4d6c2efaf83d54610dc6fdbc98256aeff7cacef90956b001`
- Scored head:
  [`23be221715ba5870ee6a2fa0078356ec6ad3afc5`](https://github.com/VynoDePal/EvidenceMesh/commit/23be221715ba5870ee6a2fa0078356ec6ad3afc5)
- Model: `gemini-3.5-flash-lite`.
- Runtime: 2026-07-30 18:04:47–18:06:27 UTC on a GitHub-hosted Linux
  runner, Python 3.11.15 and HTTPX 0.28.1.

The exact same-repository authorization label launched one live run and was
removed afterward. Technical workflow success means the artifact was safely
produced; it is not a smoke-test pass. No selective rerun was made.

## Exact accounting

| Counter | Observed | Maximum |
|---|---:|---:|
| Gemini generation requests | 3 | 8 |
| Native HTTP 200 responses | 2 | 8 required to pass |
| HTTP 429 responses | 0 | 0 |
| Other failed requests | 1 timeout | 0 |
| Tavily requests | 0 | 0 |
| Other provider requests | 0 | 0 |
| Token-count requests | 0 | 0 |
| Retries, fallbacks and repairs | 0 | 0 |

The first two requests completed in 810.304 and 683.252 milliseconds. Both
returned the exact native JSON structure, passed the unchanged strict local
parser and matched their synthetic answer and citation expectations. The
third request produced no HTTP response before the locked 30-second request
deadline and was recorded as `request_timeout` after 30,022.938 milliseconds.
The runner then stopped before the other five planned attempts.

The bounded category does not preserve a raw exception and cannot prove which
HTTPX timeout phase or upstream component stalled. The timing is compatible
with the configured request deadline, but it must not be rewritten as a rate
limit, schema failure or model-quality miss.

## Quota and schema observations

The run waited for the locked 60-second cold-start window. Request starts were
at least 5.005047 seconds apart. The largest rolling window held three
requests and 1,864 conservatively estimated input tokens, below the effective
12 RPM and 200,000 input-TPM limits. The synthetic daily reservation reached
395/400. No HTTP 429 was observed.

This small run therefore does not reproduce the Phase 11.8.3 rate-limit
failure. It also supplies two positive native-schema observations: both
received answers passed the provider JSON-schema path and the strict local
answer/citation contract. Two responses are insufficient for the frozen
eight-of-eight availability, schema, semantic and usage gates.

## Frozen gates

| Gate group | Result | Observation |
|---|:---:|---|
| Immutable sources and exact request configuration | PASS | Locked hashes and `gemini-3.5-flash-lite` configuration matched |
| Traffic ceiling and provider isolation | PASS | 3/8 maximum Gemini; zero Tavily or other provider |
| Zero retry, fallback and repair | PASS | All zero |
| Cold start and paced scheduling | PASS | 60 seconds; minimum start interval 5.005047 seconds |
| Rolling RPM, TPM and RPD safety | PASS | Within every effective limit |
| No HTTP 429 | PASS | 0 observed |
| All eight native completions | FAIL | 2/8 |
| All eight strict-schema outputs | FAIL | 2/8 |
| All eight fixture-semantic outputs | FAIL | 2/8 |
| Usage metadata for all eight | FAIL | 2/8 |
| Privacy and historical boundaries | PASS | Preserved |

The full machine-readable decision contains twelve gates; the first row above
summarizes two separate passing gates.

## Privacy and artifact integrity

The JSON contains fixture identifiers, hashes and bounded diagnostics, but no
API key, question, expected or generated answer text, evidence, prompt, raw
provider error, raw quota detail or Phase 12 identifier.

- Raw JSON: 12,567 bytes; SHA-256
  `92e092a5929b9c2eb4d2090c61187e8d7d1eba9796d4de85f8f2d288e29a9423`
- Artifact ZIP: 3,527 bytes; SHA-256
  `e0237bd057ac3db44dc37c56e0b8a3ea6e6c4fdb23a045344239fbc06793d004`
- ZIP inventory: exactly
  `phase11_8_5_live_smoke_2026-07-30.json`

## Decision boundary

The live smoke failed four blocking gates, so it does not authorize a
projection-recovery design, an unchanged Phase 11.8.3 rerun or a Phase 11.9
protocol. The historical Phase 11.8.3 result remains failed at 10/14 and its
17/24 projection tie remains unresolved.

Product defaults are unchanged. Phase 12 stays sealed and unexecuted. The
draft pull request may not be merged or released, and external-comparison,
public-alpha and superiority claims remain unauthorized. The next action is
an offline diagnosis of the timeout observability boundary, followed only by
a separately reviewed protocol if more live traffic is ever proposed.
