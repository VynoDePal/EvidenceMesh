# Phase 11.8.8 live projection calibration — 2026-07-30

## Outcome

**FAIL / no-go: 8 of 13 gates passed.** The one-shot live Tavily run completed successfully, but all five quality gates failed. Phase 11.9 protocol freeze, Phase 12 authorization, quality-profile promotion, merge, release, and superiority claims remain blocked. The PR must remain draft.

## Provenance

- GitHub Actions run: `30581595206`
- Artifact: `8774869598`
- Raw JSON: `13,984` bytes; SHA-256 `03e0ad7ef2d4859848c3b4d4d8bf9d25714b9d311741f15a91ec9b3311aca25f`
- Downloaded ZIP: `4,806` bytes; SHA-256 `399cbd5c4bc4d26dde687ec2523ce9fa6e1f5d942f465e60653edc0676125d02`
- Inert lock commit: `d91f8a85f6e2770ecd83ca95cbc7112803d683cb`
- One-shot authorization commit: `c1f847be04bdf5574ad80885f7e00f1fdbb0f049`
- Protocol v24 SHA-256: `e63ab4b3f25865890458abd2a001ce3428f9a3ca8c4f1a1a166f25432d1a8dc9`
- Live runner SHA-256: `fabad5e66246a10f0f024201c1d031de22e4958141b57cf731393bd6cc936ac3`
- Dependency manifest SHA-256: `0d6ee7f91689fc2679ee0e5c6a2857d25219d5a71cd559d248875d1074693a00`
- Selected dataset SHA-256: `feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032`
- `uv.lock` SHA-256: `5a47e1815cc2074698e1ab0cfec2932200bb013601d02246324513ffa5404898`

## Measurements

All 24 Tavily requests returned HTTP 200, and all 24 cases shared the expected selected packet and satisfied the v2 projection invariants.

| Measurement | Result | Required gate |
|---|---:|---:|
| Selected proxy coverage | 18/24 | at least 20/24 |
| Equal-cap proxy coverage | 16/24 | baseline only |
| v1 proxy coverage | 17/24 | baseline only |
| v2 proxy coverage | 17/24 | at least 20/24 |
| v2 retention of selected hits | 17/18 = 94.4444% | at least 95% |
| v2 vs equal-cap paired net gain | +1 (2 wins, 1 loss) | at least +2 |
| v2 vs v1 paired net gain | 0 (1 win, 1 loss) | at least +2 |

Traffic accounting recorded zero model requests, retries, fallback requests, repair requests, cache reads or writes, and follow-up document fetches. The Phase 12 reserve was neither scored nor selected.

## Interpretation and limits

The diagnostic status is `retrieval_limited_inconclusive`. These measurements are within-run paired comparisons on an already-observed public proxy suite. Reference-answer substring coverage is a transparent proxy; it is neither an official SimpleQA score nor a semantic-quality or correctness judgment. This result therefore does not justify Phase 11.9, Phase 12, merge, release, or any superiority claim.
