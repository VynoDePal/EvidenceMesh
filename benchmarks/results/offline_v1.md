# Offline federation result v1

Run date: **2026-07-28**

Fixture: `src/evidencemesh/data/federation_v1.json`

Cases: **12 synthetic cases**

Command:

```bash
uv run evidencemesh benchmark-offline
```

| Metric | First-provider baseline | EvidenceMesh fusion | Delta |
|---|---:|---:|---:|
| Hit@1 | 0.000000 | 1.000000 | +1.000000 |
| Hit@5 | 1.000000 | 1.000000 | +0.000000 |
| MRR@10 | 0.472222 | 1.000000 | +0.527778 |
| nDCG@10 | 0.609108 | 1.000000 | +0.390892 |
| Output duplicate rate | 0.000000 | 0.000000 | +0.000000 |
| Unique-domain ratio | 1.000000 | 1.000000 | +0.000000 |

This is a deterministic algorithm regression result, not evidence of
real-world superiority over another search or research product.
