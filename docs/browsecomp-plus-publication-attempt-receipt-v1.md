# BrowseComp-Plus issue publication attempt receipt v1

Control fields:

- `status: issue-publication-failed-closed`
- `captured_on: 2026-08-01`
- `parent_preflight_commit: 3eeedaff65700ecf969db0d427fdc13f9b521728`
- `parent_preflight_sha256: 538bc6f8cec30f784e47ac5fc01894f221cff6ed3534886274e922fa0856cbbf`
- `public_issue_payload_sha256: 2225c5f25641ecfef944ffb55bd34403753ef8a1c4c191db520857af3660e77c`
- `target_repository: texttron/BrowseComp-Plus`
- `github_operation: github_create_issue`
- `issue_creation_attempts_authorized: 1`
- `issue_creation_attempts_performed: 1`
- `issue_creation_attempts_remaining: 0`
- `external_retries_authorized: 0`
- `external_retries_performed: 0`
- `publications_succeeded: 0`
- `write_receipt_observations: 1`
- `human_upstream_response_reads: 0`
- `issue_created: false`
- `issue_number: null`
- `issue_url: null`
- `http_status: 403`
- `error_code: FORBIDDEN`
- `error_message: Resource not accessible by integration`
- `failure_class: integration-write-permission-block`

## Attempt

Immediately before the single GitHub write, the local payload SHA-256 was
recalculated and matched the authorized value. Its JSON shape contained exactly
the `title` and `body` fields, and the focused local checks passed 14/14.

One `github_create_issue` operation targeted `texttron/BrowseComp-Plus`, with no
assignee, label, milestone or attachment. The GitHub connector returned HTTP
status `403`, error code `FORBIDDEN`, and the message
`Resource not accessible by integration`.

No issue identity was returned. The attempt therefore produced no successful
publication. No retry, alternate GitHub tool, CLI fallback, issue lookup,
response read or channel switch was performed.

## Inference limits

The receipt proves only that this connector integration was not permitted to
perform this write. It does not prove that repository Issues are disabled, that
the repository maintainers rejected the request, or that a separately
authenticated GitHub user could not create the issue.

The two EvidenceMesh admission gates remain blocked. The failed publication
attempt adds no benchmark evidence and consumes the complete one-attempt
publication budget.

## Single recommended next action

Provide the already locked public `title` and `body` payload to the user for a
manual one-shot publication through their own authenticated GitHub account.
That manual publication remains a separate public action and requires an
explicit user decision; it is not authorized or performed by this receipt.

- `proposed_manual_issue_attempts_maximum: 1`
- `proposed_manual_publications_maximum: 1`
- `proposed_manual_retries_maximum: 0`
- `proposed_manual_attachments_allowed: false`
- `proposed_manual_human_response_reads_maximum: 0`
- `manual_publication_go_required: true`

Any later response inspection or evidence ingestion requires another explicit
GO and a separate response budget.
