# Phase 11.8.9 offline retrieval recovery — 2026-07-31

## Outcome

**Engineering conformance only / no-go: 12 of 19 gates passed.** All twelve
local gates passed. The seven gates requiring BRIGHT or BrowseComp-Plus remain
`not_evaluated`, so this result does not establish external retrieval quality.
Phase 11.9, Phase 12, product-default changes, merge, release and superiority
claims remain blocked. The PR must remain draft.

## Provenance

- Methodology commit:
  `63e1b95d06173c27d1b7c10ab2b0e486fe5abebd`
- Successful GitHub Actions run:
  `30608416880`
- Protocol v25 SHA-256:
  `e08a9217d8d104202826b0f72944ae5864d181cb20f5fea10d52e908cc26f62c`
- Source-set SHA-256:
  `d5bf3470536f0a9cb9a527fab7a57480863b7157e23609c73d2e40b50358a125`
- Source-lock manifest SHA-256:
  `e16d1c5df80955a59b8ea685adaa5efd9d99865c8ed02687a969b983b73fbb38`
- Raw JSON: `14,600` bytes; SHA-256
  `cb3f4bd4e2862d4ef170d2c41d17cd7991090f5e933d480d3c76ccab7a197720`

## Offline conformance measurements

The five public synthetic cases matched every frozen expected selection for
both arms. The candidate retained nine authored canonical utility markers
against four for the transparent Phase 11.8.9 control. This is a deterministic
engineering fixture result only; it is not a BRIGHT, BrowseComp-Plus, live-Web
or end-to-end research-quality score.

The exact-byte Gate 9 receipt passed 53/53 tests, covered all 22 registered
test names and all 43 conformance requirements. The final local repository
validation passed 678 tests; the preceding coverage run passed 676 tests with
91.64% branch-aware coverage. Full Ruff
format/lint, strict MyPy and all 27 workflow YAML files.

Modules are compiled directly from hash-locked source bytes. Gate 9
materializes and executes only the locked sources in an isolated Python
process. External bundle reads use no-follow file-descriptor traversal,
regular-file validation and one bounded byte stream for length, hash and
parsing.

## External benchmark boundary

BRIGHT and BrowseComp-Plus are both `not_evaluated`. Their authoritative
evaluation assets and asset-level redistribution licenses are not yet fully
resolved and locked. The local adapters passed synthetic metric oracles, but
`real_external_score` remains false and no official external score is
reported.

## Traffic, privacy and governance

The run made zero network, Tavily, other-search-provider, Gemini, model,
token-count, local-inference, retry, fallback, repair, live-cache or follow-up
document-fetch requests and bound zero provider/model secrets. Privacy and
the strict aggregate-only public schema passed with no URL, absolute path or
forbidden content field.

The historical Phase 11.8.8 result remains unchanged at 8/13 and no-go. This
offline result authorizes no live rerun, external score, Phase 11.9 freeze,
Phase 12 access, product promotion, merge, release or superiority claim.
