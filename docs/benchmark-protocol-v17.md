# EvidenceMesh benchmark protocol v17

## Phase 11.8.2 — offline projection and direct-answer design

Status: frozen offline engineering protocol. It is authored after the Phase
11.8 result and the Phase 11.8.1 causal diagnostic. It authorizes no provider
or model traffic.

## 1. Purpose

Phase 11.8 established two distinct quality defects:

1. expanded selection contained the answer-key proxy in 21/24 cases, while
   equal-cap projection retained it in only 18/24;
2. the structured claims contract improved citation discipline but regressed
   the answer-key proxy.

Phase 11.8.2 may design and test mechanisms addressing those defects without
using the omitted Phase 11.7 content, the Phase 12 reserve, Tavily, Gemini or
any other network source. It is an engineering-invariant test, not an
unbiased quality benchmark.

## 2. Locked historical sources

- Phase 11.8 result:
  `benchmarks/results/phase11_8_recovery_2026-07-29.json`
- Phase 11.8 result SHA-256:
  `0bd05884c6e6d019f22d18113ef449d1cf1c8158ac0e598d899ee1a93c4b687a`
- Phase 11.8.1 diagnostic:
  `benchmarks/results/phase11_8_1_offline_diagnostic_2026-07-30.json`
- Phase 11.8.1 diagnostic SHA-256:
  `9032d9df7d71a3e9c4197577c3e33af315842cae18435d91a7f851e5489de6d8`

Their decisions are immutable. Phase 11.8 remains fail at 5/12 and release
remains no-go.

## 3. Locked candidate and fixtures

- Candidate implementation:
  `benchmarks/phase11_8_2_candidate.py`
- Candidate SHA-256:
  `0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e`
- Synthetic fixtures:
  `benchmarks/data/phase11_8_2_offline_fixtures_v1.json`
- Fixture SHA-256:
  `16f5eb38eec4c8669fb6dac4eeb64992df5b81a46b6c02325a559d3da4f621ab`

The fixture manifest contains 12 authored projection cases, four valid
direct-answer responses and eleven invalid responses. It contains no Phase
11.7 or Phase 12 question, answer, identifier, source or evidence.

Because the fixtures were authored after the observed failure, success cannot
support a predictive quality, release or superiority claim.

## 4. Projection arms

### 4.1 Baseline

The baseline clones the Phase 11.8 provider-aware ordering and equal
per-block character cap.

### 4.2 Candidate

The candidate is `rank_weighted_query_window_head_tail_v1`.

Inputs are limited to:

- the user question;
- already-selected evidence blocks;
- the total rendered-character budget;
- maximum and minimum per-block character bounds.

The expected answer, fixture sentinel and any reference answer are forbidden
inputs.

The candidate:

1. preserves the locked provider-aware block ordering;
2. filters empty blocks and rejects duplicate citation identifiers;
3. accounts for headers and separators inside the exact rendered budget;
4. reserves a bounded minimum excerpt for every retained block;
5. allocates remaining capacity by deterministic rank weights;
6. for truncated blocks, preserves deterministic head and tail guards plus a
   window selected only by overlap with significant question terms;
7. preserves citation ID, title, URL and provider metadata;
8. makes no relevance, answer or semantic claim.

Every case is replayed three times and must produce the same packet hash.

## 5. Direct-answer contract

The candidate replaces the multi-claim JSON shape with exactly:

```json
{"answer":"Shortest exact answer supported by evidence.","citation_ids":["S1"]}
```

Only `answer` and `citation_ids` are accepted.

- `answer` must be a non-empty string of at most 4,000 characters and must not
  contain rendered `[S#]` tokens.
- `citation_ids` must contain no duplicate, at most 20 bare `S#` identifiers,
  and every identifier must belong to the supplied evidence packet.
- A supported answer requires at least one citation.
- Insufficient evidence must use exactly `Insufficient evidence.` with an
  empty list.
- No repair, fallback or permissive parser is allowed.

This phase validates parser behavior and prompt shape only. It does not measure
hosted-model schema adherence.

## 6. Exact traffic boundary

- network requests: 0
- provider calls: 0
- model calls: 0
- Tavily requests: 0
- Gemini requests: 0
- retries: 0
- fallbacks: 0
- repairs: 0
- required secrets: none

The workflow has read-only repository permissions and receives no provider
secret.

## 7. Twelve offline engineering gates

All gates are blocking for the offline engineering candidate:

1. all protocol, fixture, candidate and historical source hashes match;
2. synthetic/post-observation disclosure is present and no reserved content is
   used;
3. provider/model/network traffic is exactly zero;
4. candidate retains all 12 authored sentinels;
5. candidate has zero paired retention regression against the equal-cap
   baseline;
6. candidate has a positive paired gain on the authored fixtures;
7. all 12 rendered packets respect their exact character budget;
8. all 12 cases have byte-identical packet hashes across three replays;
9. all 12 cases preserve evidence metadata and the expected synthetic source;
10. all four valid direct-answer cases are accepted and rendered exactly;
11. all eleven invalid direct-answer cases are rejected;
12. historical, product, Phase 12, merge and release boundaries remain
    unchanged.

## 8. Decision semantics

A twelve-gate pass means only:

> the candidate satisfies the authored offline engineering invariants and is
> ready for protocol review.

It does not prove improvement on the 24 observed cases, authorize a live Phase
11.8.3 run, authorize Phase 11.9, open Phase 12, change the quality/community
profiles, choose a model for users, permit merge or release, or support a
“best” or superiority claim.

Any future live calibration requires a separate frozen protocol and explicit
user authorization.

## 9. Public output and privacy

The result may contain:

- fixture case IDs;
- hashes;
- lengths and counts;
- Boolean invariant outcomes;
- aggregate paired retention counts;
- gate and decision objects.

It must not contain:

- Phase 11.7 questions, answers, evidence or prompts;
- generated model answers;
- credentials;
- Phase 12 identifiers;
- synthetic fixture text or sentinels.
