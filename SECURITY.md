# Security policy

## Reporting a vulnerability

Do not publish exploitable details in a public issue. Use GitHub's private
security advisory flow for this repository.

## Security boundaries

EvidenceMesh treats every search result and downloaded page as untrusted data.
It blocks loopback, private, link-local, reserved and non-HTTP(S) fetch targets
by default; revalidates redirects; limits response size; and labels common
prompt-injection patterns.

These controls reduce risk but cannot prove that arbitrary web content is safe
or true. Applications must preserve the separation between retrieved evidence
and model instructions. Remote HTTP deployments also need authentication,
request limits and TLS at the deployment layer.

See [docs/threat-model.md](docs/threat-model.md) for the detailed model.

## Distribution integrity

The repository is the only supported distribution route until an explicit
release gate authorizes publication. The Phase 11.4 candidate workflow builds
from the exact pull-request head with persisted Git credentials disabled,
installs the wheel in an isolated environment, emits a CycloneDX 1.7 SBOM and
SHA-256 checksums, and uses GitHub's short-lived workload identity for SLSA
provenance and SBOM attestations.

An Actions candidate is temporary validation evidence, not a GitHub Release.
Verify `SHA256SUMS`, the repository identity and the exact signer workflow
before installing it. See
[docs/alpha-release-v0.1.md](docs/alpha-release-v0.1.md).
