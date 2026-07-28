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
