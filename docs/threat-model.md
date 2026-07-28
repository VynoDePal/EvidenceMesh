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
- DNS pinning: document and robots requests connect to the exact validated
  public address while preserving the original HTTP Host and TLS SNI names;
- non-standard port denial by default;
- redirect validation at every hop;
- total provider/fetch deadlines including concurrency-queue wait, a 5 MB
  search-provider JSON limit, a bounded robots.txt stream, and document
  byte/character limits;
- conservative media-type handling;
- bounded PDF page extraction performed outside the event loop;
- main-content extraction and active HTML removal;
- robots.txt checks when available;
- prompt-injection, hidden-text and bidi-control risk labels;
- structured evidence fields instead of concatenating pages into instructions;
- bounded provider and batch concurrency;
- content hashes and retrieval timestamps.

## Residual risks

- Public IPs may still front sensitive services.
- Heuristics can miss or falsely flag prompt injection.
- Search snippets and high-authority domains can be incorrect.
- PDF parsers and decompression libraries expand the attack surface.
- A timed-out synchronous provider or extraction worker may continue briefly
  in its background thread even though the request has returned.
- An unauthenticated remote MCP endpoint can be abused.

For high-assurance deployments, retain an enforcing egress proxy, a container
sandbox, CPU/memory limits, authentication, per-user quotas, TLS and central
audit logs. Never enable private-network fetching on a public service.
