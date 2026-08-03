# DRAFT — LOCAL ONLY — UNSENT — DO NOT SEND

Local control fields:

- `status: local-unsent-draft`
- `send_authorized: false`
- `external_requests_authorized: 0`
- `external_retries_authorized: 0`
- `publications_authorized: 0`
- `response_ingestion_authorized: false`
- `recipient_identity_resolved: false`
- `p1_result_sha256: 90336e77544b5ba7a3c4ddf21cf9f535377a57c19c5756941f67ee2304d00016`
- `p1_result_commit: aeb71a4a58c011de8182f603a9aaeba66a78cfe6`

This file is a local drafting artifact only. It contains no recipient, address,
handle, link, attachment or sending mechanism. Sending it, identifying or
contacting a recipient, and reading or ingesting any future response each
require a separate explicit authorization and a new evidence budget.

---

Subject: BrowseComp-Plus clarification — component rights and immutable
evaluation configuration

Hello,

EvidenceMesh is assessing whether BrowseComp-Plus could satisfy our internal
admission policy for an officially comparable fixed-corpus benchmark. In the
bounded evidence set reviewed so far, we do not yet have sufficient evidence
to close two gates: component-level rights disposition and immutable effective
evaluation configuration.

This is a request for documented facts and artifact identities, not legal
advice or a legal conclusion. We do not assume that the benchmark maintainers
can speak for every third-party rights holder. Where the responsible authority
or status is unknown, an explicit `unknown`, `not confirmed` or `not covered`
answer is preferable to an inferred permission.

Please do not provide benchmark payloads, corpus content, examples, queries,
answers, qrels, model weights, secrets, personal data or a newly executed score.
Identifiers, digests, immutable references and a machine-readable configuration
are sufficient for this clarification.

## 1. Component-level rights disposition

For every component required to run the official fixed-corpus evaluation,
could you identify or point to an authoritative record for:

1. the component name, type, provenance and exact version or snapshot;
2. the relevant rights holder or authority competent to document its status;
3. the applicable license, permission, terms or other documented basis, with
   an immutable artifact identity where one exists;
4. whether that documented basis separately covers:
   - acquisition of the component;
   - private local storage and processing solely for evaluation;
   - publication of aggregate metrics or scores only, without content,
     excerpts or examples; and
   - those uses under a strict non-redistribution condition for the component
     and underlying corpus material;
5. every restriction, unresolved status or component for which the responsible
   authority or documented permission remains unknown.

Please distinguish rights or permissions documented by the benchmark project
from rights originating with third-party Web-content owners. A project-level
license or general availability statement should not be treated as a
component-level disposition unless its scope explicitly covers that component
and each intended use above.

## 2. Immutable effective evaluation closure

For each published result, result row or result family intended to represent
the official fixed-corpus comparison, could you provide a stable result
identifier and a one-to-one mapping to:

1. the evaluation-runner repository, exact commit, path and content identity;
2. the judge model repository, exact revision and relevant artifact digests;
3. the tokenizer repository, exact revision, tokenizer configuration and chat
   template identity;
4. the exact effective grader prompt, including system and user wrappers or
   templates, with a source identity or content digest;
5. every effective generation setting and override, including decoding
   parameters, maximum output length, stop conditions, thinking mode, seed or
   seed policy, repetition policy, batch size and parallelism;
6. the fully resolved runtime, including Python version, exact dependency
   versions or commits, effective runtime flags, and a lockfile or container
   image digest where available;
7. the parser source identity and effective configuration, including
   normalization and malformed-output handling;
8. the scoring source identity and effective configuration, including metric
   definitions, aggregation, missing-output handling and error handling; and
9. the exact invocation or machine-readable effective-run manifest that binds
   the result identifier to all the elements above.

Please distinguish source-code defaults from the effective values actually
used for each reported comparison. If different official results used different
configurations, a separate mapping for each configuration would avoid treating
them as one evaluator identity.

This request records an EvidenceMesh evidence gap only. It does not assert that
any permission exists or does not exist, and a future response would not
automatically admit the benchmark or authorize acquisition, evaluation or
publication.

Thank you.

---

Local stop note: do not resolve a recipient, open a channel, attach this file,
send it, publish it, or inspect a response under the present authorization.
