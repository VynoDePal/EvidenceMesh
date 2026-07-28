# Threat model

## Protected assets

- model instructions and conversation context;
- local and private-network services;
- API keys and provider credentials;
- availability, memory and disk;
- citation integrity.

## Untrusted inputs

Queries, URLs, DNS responses, redirects, search-provider payloads, HTML, PDF
metadata/text and cached content are untrusted.

## Implemented controls

- HTTP(S)-only fetch targets without URL user information;
- DNS resolution check against private, loopback, link-local, reserved,
  multicast and unspecified addresses;
- non-standard port denial by default;
- redirect validation at every hop;
- 5 MB search-provider JSON limit plus document byte and character limits;
- conservative media-type handling;
- main-content extraction and active HTML removal;
- robots.txt checks when available;
- prompt-injection, hidden-text and bidi-control risk labels;
- structured evidence fields instead of concatenating pages into instructions;
- bounded provider and batch concurrency;
- content hashes and retrieval timestamps.

## Residual risks

- DNS can change between validation and the HTTP client's connection.
- Public IPs may still front sensitive services.
- Heuristics can miss or falsely flag prompt injection.
- Search snippets and high-authority domains can be incorrect.
- PDF parsers and decompression libraries expand the attack surface.
- An unauthenticated remote MCP endpoint can be abused.

For high-assurance deployments, add an egress proxy with DNS pinning, a
container sandbox, CPU/memory limits, authentication, per-user quotas, TLS and
central audit logs. Never enable private-network fetching on a public service.
