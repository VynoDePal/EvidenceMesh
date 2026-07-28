# Phase 5 SearXNG engine calibration

Date: **2026-07-28**

Verdict: **valid Stage A; gate closed; release remains no-go**

The isolated calibration completed all 96 pre-registered requests. Only
`duckduckgo` passed every gate. Protocol v3 requires at least two eligible
engines before changing the production SearXNG configuration or evaluating it
on the held-out 200-case SimpleQA sample. Therefore:

- `docker/searxng/settings.yml` remains unchanged;
- no engines are promoted;
- Stage B (200-case retrieval) was not run;
- Stage C (local-model end-to-end pilot) was not run;
- this result supports neither a release nor a superiority claim.

## Provenance

| Item | Value |
|---|---|
| Valid workflow run | [30399260090](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30399260090) |
| Source commit | [`216e99fda3d7eecfb25e25e51d65395ec86539c6`](https://github.com/VynoDePal/EvidenceMesh/commit/216e99fda3d7eecfb25e25e51d65395ec86539c6) |
| Source tree | `58574bd8904b9e02ed6d3c9ef141a64d9ca556a6` |
| Runtime | Python 3.11.15 on GitHub-hosted `ubuntu-latest` |
| Window (UTC) | 21:06:52–21:08:06 |
| Raw report | [`searxng_calibration_phase5_2026-07-28.json`](searxng_calibration_phase5_2026-07-28.json) |
| Raw report SHA-256 | `140f5c1804ab5b29ea2c83a0018364ddd0335a5d4221ea88ebe1bfb9be7bfd53` |
| GitHub artifact ID | `8704074173` |
| Artifact ZIP SHA-256 | `e9184eb469ba067b508b09369aa5e604820d6c37e7de123ba532ce7f7a66c589` |
| Calibration suite SHA-256 | `06a5d97980063999768127439f594090007dff7e793ad61567d248e134779dce` |
| Calibration config SHA-256 | `856ce08d2bf0c3512cb5a40f91aa54fde1860cad827bd8208fc09059c47d1584` |
| SearXNG image | `searxng/searxng:2026.7.26-b060c780d@sha256:d0aaeb14880e6e92bde1518fcc7261e995783367d63d95203383607bef9c6516` |

The artifact ZIP digest was verified before extraction, and the committed JSON
is byte-identical to the extracted report. The public report contains case IDs
and telemetry only; it contains no query, answer, result title, snippet, URL or
document content.

The valid run's source workflow temporarily placed its randomly generated
SearXNG secret in the GitHub Actions job environment, whose later step metadata
displayed the value. It was not a reusable account credential, the service was
bound to loopback, and the container was destroyed at job completion. The
follow-up workflow generates the value only inside `docker run`; it is no
longer persisted to the job environment. The value itself is intentionally not
reproduced here.

## Pre-registered gates

Each engine was queried once for each of 12 independent navigational cases,
with no retry. Eligibility required all of:

- HTTP/JSON response success at least 90%;
- at least one result on at least 80% of requests;
- expected authoritative domain in the top 10 on at least 50%;
- upstream unresponsiveness on at most 20%;
- p95 latency at most 10 seconds;
- 100% isolation to the requested engine.

Stage B required at least two eligible engines.

## Results

| Engine | Response | Availability | Target domain @10 | Unresponsive | Isolation | p95 ms | Eligible |
|---|---:|---:|---:|---:|---:|---:|:---:|
| `brave` | 100.0% | 0.0% | 0.0% | 100.0% | 100.0% | 5.071 | no |
| `duckduckgo` | 100.0% | 100.0% | 91.7% | 0.0% | 100.0% | 996.469 | **yes** |
| `startpage` | 100.0% | 0.0% | 0.0% | 100.0% | 100.0% | 4.097 | no |
| `qwant` | 100.0% | 0.0% | 0.0% | 100.0% | 100.0% | 458.181 | no |
| `mojeek` | 100.0% | 0.0% | 0.0% | 100.0% | 100.0% | 3.539 | no |
| `wiby` | 100.0% | 75.0% | 8.3% | 0.0% | 100.0% | 1,999.166 | no |
| `mwmbl` | 100.0% | 16.7% | 16.7% | 83.3% | 100.0% | 4,004.238 | no |
| `yep` | 100.0% | 0.0% | 0.0% | 100.0% | 100.0% | 3.490 | no |

“Response” means that the local SearXNG API returned valid HTTP/JSON. It does
not mean that an upstream engine produced results. This distinction explains
the 100% response rate alongside zero availability for several engines.

DuckDuckGo retrieved at least one result for all 12 cases and found the
expected authoritative domain for 11. Its Wilson 95% interval for the target
hit rate is wide (`64.6%–98.5%`) because this is intentionally a small
calibration suite. Wiby missed both its 80% availability and 50% target-domain
gates. Every other engine missed at least three gates.

## Validity and incident record

The first workflow execution
([30398761622](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30398761622))
was invalidated and is not used here. It supplied both `categories=general` and
an explicit engine. The pinned SearXNG adapter
[unions those selections](https://github.com/searxng/searxng/blob/b060c780d/searx/webadapter.py),
so responses were not isolated to the requested engine.

Before the valid rerun, the request was corrected to send only `engines`, and
an engine-isolation field plus a 100% isolation gate were added. The suite,
engine list, request budget and all pre-existing thresholds were unchanged.
The valid run achieved 96/96 isolated responses.

## Interpretation and limits

This is a dated provider-selection measurement from one GitHub-hosted network
egress, not a general web-search leaderboard. Live upstream behavior can vary
by time and network. The 12 authored cases are too small to establish broad
quality, and no official answer evaluator was run.

The evidence is nevertheless sufficient for the protocol decision: the
minimum-two-engine gate failed `1 < 2`, so proceeding to a tuned 200-case run
would violate the locked methodology.
