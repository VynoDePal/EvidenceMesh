# EvidenceMesh 0.1.0 alpha distribution status

EvidenceMesh `0.1.0` is source-available under Apache-2.0, but it is not yet a
published PyPI package or GitHub Release. Phase 11.4 prepares and validates an
ephemeral technical release candidate without changing that publication
boundary.

## What Phase 11.4 proves

A successful Phase 11.4 run proves that the exact pull-request commit can:

- build a valid wheel and source distribution;
- install the wheel in a clean Python 3.11 virtual environment;
- run the installed CLI;
- negotiate MCP over a real STDIO subprocess and expose the documented
  interface;
- produce a CycloneDX 1.7 dependency inventory;
- produce SHA-256 checksums;
- receive and pass GitHub keyless provenance and SBOM attestation
  verification.

It does not prove real-world search quality, provider availability, answer
quality, benchmark superiority or production readiness.

## Candidate layout

The temporary Actions artifact is named with the candidate commit and contains:

```text
evidencemesh-0.1.0-alpha-rc.1/
├── SHA256SUMS
├── alpha-rc-manifest.json
├── dist/
│   ├── evidencemesh-0.1.0-py3-none-any.whl
│   └── evidencemesh-0.1.0.tar.gz
├── evidencemesh-0.1.0.cdx.json
├── installed-wheel-mcp-stdio.json
└── installed-wheel-offline-benchmark.json
```

The privacy-safe Phase 11.4 result JSON is stored beside the candidate
directory.

## Verifying a candidate

After a successful run, use GitHub CLI with the run ID and artifact name
recorded in the committed Phase 11.4 report:

```bash
gh run download RUN_ID \
  --repo VynoDePal/EvidenceMesh \
  --name ARTIFACT_NAME \
  --dir evidencemesh-alpha-rc

cd evidencemesh-alpha-rc/evidencemesh-0.1.0-alpha-rc.1
sha256sum --check SHA256SUMS

gh attestation verify dist/evidencemesh-0.1.0-py3-none-any.whl \
  --repo VynoDePal/EvidenceMesh \
  --signer-workflow \
  github.com/VynoDePal/EvidenceMesh/.github/workflows/phase11-4-alpha-rc.yml

gh attestation verify dist/evidencemesh-0.1.0-py3-none-any.whl \
  --repo VynoDePal/EvidenceMesh \
  --signer-workflow \
  github.com/VynoDePal/EvidenceMesh/.github/workflows/phase11-4-alpha-rc.yml \
  --predicate-type https://cyclonedx.org/bom
```

Only install a wheel whose checksum and both attestations verify:

```bash
python3.11 -m venv .venv-alpha
.venv-alpha/bin/python -m pip install \
  evidencemesh-0.1.0-alpha-rc.1/dist/evidencemesh-0.1.0-py3-none-any.whl
.venv-alpha/bin/evidencemesh benchmark-offline
```

The candidate version remains `0.1.0`; `alpha-rc.1` labels the validation
bundle, not Python package metadata.

## Current supported route

Until a later explicit publication gate passes, use the repository source as
documented in the README. The Actions candidate expires and must not be linked
as if it were a durable release. Publishing to PyPI or creating a GitHub
Release requires a separate approved phase after technical, quality,
governance and release gates are all satisfied.
