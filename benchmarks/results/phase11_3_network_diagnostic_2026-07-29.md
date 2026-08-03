# Phase 11.3 network observability diagnostic

Run date: **2026-07-29**.

GitHub Actions run:
[30471182674](https://github.com/VynoDePal/EvidenceMesh/actions/runs/30471182674).

Diagnostic commit:
`6a1925771048dcd0e66945ad6876512db88a8adb`.

Protocol SHA-256:
`d5d4b4e066e2010d3e420e91dfa4a11202eeb98d61174c5c7de965e7f7eff764`.

Raw report SHA-256:
`dba044f47aa3960fcc212c2b53cdea0470acfdc4b9816c2e6d709f71aea8d20f`.

Artifact ZIP SHA-256:
`72250c7316f033ca6e82125c803971c75314893e34db1cebc9ba55f2b87138a2`.

## Decision

**Diagnostic only: no retrieval candidate was evaluated. Default promotion:
blocked. Phase 12: blocked. Release: no-go.**

The public Mwmbl endpoint returned ten results in three of four fixed probes.
One probe reached the configured 15-second deadline without receiving an HTTP
response. The endpoint and adapter therefore worked during this run, but the
observed timeout also confirms intermittent deployment reliability.

This result corrects the Phase 11.2 traffic interpretation. It does not score
relevance, target recall, result quality, answer quality or citation quality,
and it cannot promote Mwmbl or support a superiority claim.

## Stage accounting

| Stage | Observed |
|---|---:|
| Logical calls | 4 |
| Cache hits | 0 |
| Circuit-open skips | 0 |
| Adapter invocations | 4 |
| HTTP attempts | 4 |
| HTTP responses | 3 |
| HTTP failures without response | 1 |
| HTTP 200 responses | 3 |
| Cases returning results | 3/4 |
| Result rows returned | 30 |

Every logical call reached both the provider adapter and the shared HTTPX
transport. No call was satisfied from cache or skipped by the circuit breaker.
The three received responses all had HTTP status 200. The remaining attempt
was classified as a sanitized `timeout`, with no URL, response body or
exception message retained.

The three successful HTTP attempts reached response headers in 202.441,
674.831 and 796.689 milliseconds. The failed attempt ended at 15,015.539
milliseconds, matching the configured 15-second provider deadline. One failure
did not open the circuit because the threshold was three, and the later
successful call reset the consecutive-failure count.

## What changed from Phase 11.2

Phase 11.2 reported 16 routed Mwmbl calls and no usable result, but could not
distinguish actual network dispatches from circuit-open skips. Its timing
suggested three attempts followed by skipped calls; that remained an inference.

Phase 11.3 measures the stages directly. In this run:

- all 4 logical calls became adapter invocations;
- all 4 adapter invocations dispatched an HTTP request;
- 3 requests received valid HTTP 200 responses and produced results;
- 1 request failed without a response and was directly classified as a timeout;
- 0 calls were skipped by the circuit.

The evidence now rules out a permanently broken Mwmbl adapter or universally
invalid response schema in the measured environment. The difference from
Phase 11.2 is consistent with a public endpoint whose availability varies over
time. Because the protocol intentionally defines no relevance targets, it says
nothing about whether the returned results were useful.

## Traffic and privacy

- 4 Mwmbl logical calls, adapter invocations and HTTP attempts;
- 0 cache hits;
- 0 retries;
- 0 paid-provider calls;
- 0 Tavily calls;
- 0 Gemini or other model calls.

The committed raw report identifies probes only as `probe-01` through
`probe-04`. It omits query text, target domains, source titles and URLs,
snippets, response bodies, raw exception messages and credentials. The
workflow recursively checks these privacy and traffic invariants before
uploading the artifact.

## Interpretation

This diagnostic validates the new observability contract and establishes that
Mwmbl can return results through EvidenceMesh from a GitHub-hosted runner. It
also measures one timeout in four attempts, so it does not establish production
reliability. A larger reliability run would require a separately frozen
protocol and rate budget; it must not be improvised from these four probes.

Mwmbl remains outside named defaults under its current CC BY-NC-SA 4.0 result
boundary. No persistent, reproducibly populated YaCy index was available, so
an empty ephemeral YaCy node was correctly excluded. Named bundles remain
unchanged, Phase 12 remains blocked, and the draft PR cannot claim to be the
best open-source search or deep-research system.
