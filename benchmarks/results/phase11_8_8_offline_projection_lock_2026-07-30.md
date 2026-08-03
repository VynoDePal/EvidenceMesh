# Phase 11.8.8 offline projection lock

Status: **pass — 14/14 offline engineering gates**.

## Outcome

The answer-blind `fair_prefix_rarity_passage_pack_v2` projector is frozen for a
future, separately authorized calibration. It combines a fair per-source
prefix, bounded query-term rarity, capped repetition scoring, multiple
source-order passages and relevance-aware budget allocation.

The projector receives only the question, selected evidence and explicit
character limits. It performs no I/O and emits only ordered source substrings
joined by a visible omission separator. Citation identifiers, titles, URLs and
provider metadata remain attached to their source blocks.

## Offline verification

All fourteen gates passed. Across twelve public synthetic and adversarial
fixtures:

- historical equal-cap retained 3/12 authored markers;
- the locked v1 projector retained 7/12;
- v2 retained 12/12;
- v2 had zero fixture regressions against either control;
- v2 respected the rendered and per-block budgets in 12/12 cases;
- five byte-level replays were deterministic in 12/12 cases;
- source substring, metadata, identifier and order checks passed in 12/12.

These fixtures were authored after the historical failure. Their scores prove
engineering invariants only and are not evidence of real Web-search quality.
The historical equal-cap control exceeded its nominal fixture budget in four
cases because its locked implementation omits inter-block separators from its
budget calculation; it remains unchanged to preserve a fair historical
control.

## Historical boundary

Phase 11.8.3 remains an immutable 10/14 no-go. Its selected evidence contained
the transparent proxy in 19/24 cases, while equal-cap and v1 each retained
17/24. A 20/24 projector score was therefore impossible on that exact packet.
A future run must report the new Tavily selected-packet ceiling separately and
compare projectors only on the same new packet.

## Traffic and authorization

This phase made zero network, provider, search, Tavily, Gemini or other model
requests; bound zero secrets; and performed zero retries, fallbacks or repairs.
The read-only workflow contains no live job or provider credential.

The future runner defaults to checksum validation. Its live path is not
authorized by this result. A future run requires a new explicit authorization
and is capped at one Tavily attempt for each of the 24 observed calibration
selectors, with zero model requests.

Phase 11.9, Phase 12, product changes, merge, release and superiority claims
remain blocked. Users retain provider, model and credential choice.
