# EvidenceMesh closed alpha A0 protocol v1

## Decision boundary

A0 prepares a closed-alpha kit around the already accepted technical candidate
`evidencemesh-0.1.0-alpha-rc.2` at commit
`81b5f8a8abd4302b27ad123bd5505e1757eadc7f`. The accepted GitHub Actions run is
`30632190869`; its artifact digest is
`487e7118f18ec425908fb1fbb94678795fb8197c9124435957ea843b49327561` and its
provenance and SBOM attestation identifiers are `38176497` and `38176506`.

A0 is preparation-only. It authorizes no tester contact, session, provider
request, model request, telemetry, upload, merge, release or public claim. A
separate explicit GO is required before any live session.

The currently blocking live-readiness defect is budget enforcement. The
runtime records attempts after execution but has no fail-closed global governor
before dispatch. In addition, the named `quality` deployment profile can enable
seven providers, so one search can exceed the six-attempt session ceiling. A0
therefore records `runtime_budget_enforcement_ready=false` and must not be
treated as live-ready.

## Frozen design

The single allowed wave has eight pseudonymous slots: six `community` and two
`quality`. Each participant performs five one-task sessions: three prescribed
tasks and two participant-chosen, non-sensitive real tasks. This yields at most
40 sessions. Task reports contain only the prescribed task slot and a coarse
category; task text is never collected.

The traffic ceilings are hard limits, not targets:

| Dimension | Maximum |
|---|---:|
| Sessions | 40 |
| Sessions per participant | 5 |
| Provider attempts per session | 6 |
| Provider attempts over the wave | 240 |
| Tavily attempts per `community` session | 0 |
| Tavily attempts per `quality` session | 4 |
| Tavily attempts over the wave | 40 |
| Model attempts initiated by EvidenceMesh | 0 |
| Automatic retries, fallbacks or repairs | 0 |
| Concurrent sessions | 2 |
| New request starts per minute | 10 |
| Local report retention | 14 days |

Participants in `quality` use only their own authorized Tavily credential. A
credential value must never enter the report process. The community profile
uses no Tavily credential. The cache must be disabled. A client or host that
cannot prove `use_cache=false` for every operation is incompatible with this
protocol and cannot enter the closed alpha.

The three prescribed tasks are immutable and contain only public, non-sensitive
material:

1. **P1 — general reference:** Find the release date and license of CPython
   3.11.0 using official `python.org` sources, and cite the source for each.
2. **P2 — technical comparison:** Using the official Git documentation,
   compare how `git init --initial-branch` and `init.defaultBranch` select the
   initial branch name, and cite each relevant claim.
3. **P3 — current information:** Identify every CPython release series currently
   marked `security` or `bugfix` on the official Python developer-guide status
   page, state the lookup date, and cite the official page.

The exact `closed-alpha-a0-consent-v1` statement is:

> I choose to participate in the EvidenceMesh closed alpha. I understand that
> the local report stores only pseudonymous identifiers, dates, bounded counts,
> statuses and boolean ratings for at most 14 days, and never stores my task
> text or provider output. A search provider receives my request and network
> address under its own retention policy; the quality profile uses only my own
> authorized Tavily credential. I confirm that I control the input and will not
> submit personal data about another person, confidential material,
> credentials, or sensitive medical, legal, financial or safety-critical work.
> I may skip, stop or withdraw without giving a reason. Withdrawal deletes the
> local report but cannot reverse provider processing or backups.

## Privacy contract

The report schema is a new allowlist and never serializes `SearchMetadata`,
`SearchResponse`, `ResearchPacket`, provider results, logs or exceptions. It
allows only pseudonymous random codes, enums, bounded counters, boolean
ratings, a whole-session duration and date-only retention fields. It has no
free-text field.

At every depth, reports must exclude task text, prompts, questions, queries,
answers, model output, titles, snippets, quotes, document content, source
locations, network addresses, credential material, headers, environment
values, exception messages, stack traces, local paths, host/user identifiers,
contact information and hashes derived from any of those values. A participant
code must be random and must not be an email hash. Reports remain local, in a
`0700` directory as `0600` regular files, with no symlink and no GitHub artifact
upload.

Consent is explicit and versioned before a first request. The disclosure must
state the purpose, aggregate fields, local destination, 14-day maximum, BYOK
scope, and that a provider receives the task request and network address under
its own retention policy. Participants may skip or withdraw without providing
a reason. Withdrawal deletes the local report; it cannot reverse provider
processing or backups. Personal data about third parties, confidential input,
credentials, and medical, legal, financial, safety-critical or otherwise
sensitive use are excluded.

The A0 validator refuses an expired report but does not implement a report
store or background deletion. A later live collector must delete each report
before the beginning of the UTC `delete_after` date and must purge at startup,
shutdown and access. A separately tested local scheduler is required to enforce
the deadline when that collector is not running. Shell history, terminals, MCP
hosts, crash dumps, synced folders, backups and provider retention remain
outside the report tool and must be covered by the participant disclosure.

The JSON Schema is authoritative for field shape and its expressible
conditions. `validate_feedback_report` is additionally authoritative for
cross-counter ordering, exact 14-day date arithmetic and expiration, which JSON
Schema cannot express. Both validations are mandatory before any local write.

## Entry criteria for a later live GO

Every item is mandatory:

1. this A0 preflight is green at the PR head and still pins the accepted RC2;
2. the RC2 artifact, its six checksummed subjects and both attestations have
   been independently verified;
3. a pre-dispatch governor enforces per-session and global budgets atomically,
   including concurrent sessions, and its fail-closed tests are green;
4. cache disabling, private file permissions, expiry deletion and the local
   scheduler have been tested on each supported installation path;
5. exactly eight eligible participants have opted in: six `community`, two
   `quality`, with personal authorized Tavily credentials only where required;
6. every participant has accepted `closed-alpha-a0-consent-v1`, attested
   authority over their inputs and chosen only non-sensitive tasks; and
7. the repository owner gives a separate explicit live-wave GO.

The installation kit is allowed to fetch only the artifact from run
`30632190869`. Before installation, verify the artifact name binds the full
candidate SHA, run `sha256sum --check` inside the seven-file bundle, then
verify each checksummed subject against the provenance attestation and the
wheel against the CycloneDX attestation. Install the verified wheel in a new
CPython 3.11 virtual environment. An absent or expired artifact, mismatched SHA,
checksum or attestation is a hard stop; source checkout is not a substitute for
the frozen RC2.

The following preparation commands download and verify only supply-chain
material; they do not authorize or perform a research request:

```bash
candidate_sha=81b5f8a8abd4302b27ad123bd5505e1757eadc7f
artifact_name="alpha-rc-head-$candidate_sha"
expected_digest=sha256:487e7118f18ec425908fb1fbb94678795fb8197c9124435957ea843b49327561
install_root=$(mktemp -d)
observed_digest=$(gh api \
  repos/VynoDePal/EvidenceMesh/actions/runs/30632190869/artifacts \
  --jq ".artifacts[] | select(.name == \"$artifact_name\") | .digest")
test "$observed_digest" = "$expected_digest"
gh run download 30632190869 \
  --repo VynoDePal/EvidenceMesh \
  --name "$artifact_name" \
  --dir "$install_root"
bundle="$install_root/evidencemesh-0.1.0-alpha-rc.2"
(cd "$bundle" && sha256sum --check SHA256SUMS)
while read -r _ subject; do
  subject="${subject#\*}"
  gh attestation verify "$bundle/$subject" \
    --repo VynoDePal/EvidenceMesh \
    --signer-workflow VynoDePal/EvidenceMesh/.github/workflows/alpha-rc-head.yml \
    --source-digest "$candidate_sha" \
    --source-ref refs/heads/agent/evidencemesh-v0.1 \
    --signer-digest "$candidate_sha" \
    --deny-self-hosted-runners
done < "$bundle/SHA256SUMS"
gh attestation verify \
  "$bundle/dist/evidencemesh-0.1.0-py3-none-any.whl" \
  --repo VynoDePal/EvidenceMesh \
  --signer-workflow VynoDePal/EvidenceMesh/.github/workflows/alpha-rc-head.yml \
  --source-digest "$candidate_sha" \
  --source-ref refs/heads/agent/evidencemesh-v0.1 \
  --signer-digest "$candidate_sha" \
  --deny-self-hosted-runners \
  --predicate-type https://cyclonedx.org/bom
python3.11 -m venv "$install_root/venv"
"$install_root/venv/bin/pip" install \
  "$bundle/dist/evidencemesh-0.1.0-py3-none-any.whl"
"$install_root/venv/bin/pip" check
```

The commands intentionally do not start EvidenceMesh or supply a task.

## Stop criteria

Stop immediately before the next dispatch on any candidate, checksum,
attestation, consent, privacy, cache, permission, deletion, telemetry or budget
inconsistency; on any forbidden report field or raw-data retention; on any
EvidenceMesh-initiated model attempt; or on any retry, fallback, repair or
limit breach.

Once at least 20 valid sessions exist, stop the wave when blocking sessions
exceed 10%, provider errors exceed 15% of provider attempts, supported
citations fall below 90% of citations, or useful sessions fall below 70%.
Also stop after two distinct sessions contain citations that cannot be
resolved. If the latency p95 exceeds 120 seconds after 20 valid sessions, pause
dispatch and diagnose; do not spend more traffic to confirm the failure.

Any stop preserves the remaining budget. A0 and any later closed-alpha result
cannot authorize merge, Phase 12, public distribution, a quality claim or a
change to product defaults.
