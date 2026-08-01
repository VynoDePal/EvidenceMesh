# EvidenceMesh benchmark protocol v28

## Phase 11.8.10B-P1 — BrowseComp-Plus bounded clarification

Status: frozen metadata-only, local-only and fail-closed methodology. This
protocol consumes the five public-metadata document slots left by Phase
11.8.10B-P0. It may produce an engineering `PASS` for the clarification lock,
but it cannot clear a benchmark candidate when a substantive admission gate
remains incomplete.

P1 authorizes no benchmark payload download or inspection, decryption,
provider, model or judge execution, scoring, retry, secret access, acquisition,
publication, distribution, Phase 11.9, Phase 12 or V1 quality claim.

## 1. Frozen predecessor

P1 is bound to the exact local P0 state below:

- methodology commit:
  `56989d4674f99184b11f72d18c503c320c65c868`;
- methodology tree: `5db66c294420c901e63ad7c276ba430a0f50ac33`;
- result commit: `f05498eb59dae75b02d176f2c0d6a53d4246df0f`;
- result tree: `7c7f366d3aef562aec387443d9432a27d5c5488b`;
- protocol v27 SHA-256:
  `8346b69b1b7261eaf94028d5f2ac2e40bc028b49db0ea68f4f779083680ab0c6`;
- P0 policy manifest SHA-256:
  `09e9dfb6475ccf40ffa4d844684ac7036c0255f35e2ad7c6fdeb5e0fe1027082`;
- P0 source-lock SHA-256:
  `045b28d1da12ee11f2ca9083d6ea8648de8827f9e80c396f12d8bb6e8ccf93ff`;
- P0 result SHA-256:
  `7e4062e9270eb8dc681783b0aac2ff031ea53310bbd9982c61fea0e458fc3798`.

The P0 result must reproduce with 16/16 engineering gates passing, both
candidate suites blocked, zero admitted suite and five unused metadata slots.
Any identity, digest or decision mismatch fails closed.

## 2. Scope and proof targets

BrowseComp-Plus is the sole P1 clarification candidate. BRIGHT remains frozen
at its P0 decision and receives no new source or inference.

The clarification asks only whether five additional primary documents close:

1. a component-level rights disposition adequate for acquisition, local
   processing, aggregate reporting and non-redistribution; and
2. an immutable end-to-end judge closure covering the model and tokenizer,
   prompt, generation settings, resolved runtime dependencies, parser and
   scoring semantics for the official BrowseComp-Plus fixed-corpus track.

An exact source file can partially lock a prompt or algorithm without locking
the effective execution. A named model or immutable model-card revision is not
a runner binding. These distinctions are mandatory and fail closed.

## 3. Final five-document source set

Exactly these five new public metadata documents are admitted:

1. [BrowseComp-Plus evaluation runner](https://github.com/texttron/BrowseComp-Plus/blob/046949032b0328319cc9a02663a759ec601d9402/scripts_evaluation/evaluate_run.py),
   Git blob `d90b1a1d3dfc4020a902ff16606eaea6c21dc543`;
2. [BrowseComp-Plus project dependencies](https://github.com/texttron/BrowseComp-Plus/blob/046949032b0328319cc9a02663a759ec601d9402/pyproject.toml),
   Git blob `bf43f78a9310b290c35be79ad5f902c267bd3b5f`;
3. [BrowseComp-Plus paper, arXiv v1](https://arxiv.org/abs/2508.06600v1);
4. [OpenAI BrowseComp benchmark page](https://openai.com/index/browsecomp/);
5. [Qwen3-32B model card at candidate revision](https://huggingface.co/Qwen/Qwen3-32B/blob/9216db5781bf21249d130ec9da846c4624c16137/README.md).

The GitHub files are fixed by repository commit, path and blob identity. The
paper is fixed by its explicit arXiv version. The Qwen card is fixed by model
repository revision and path, but its raw bytes were not locally hashed. The
OpenAI page is an official primary source with no immutable revision in its
URL; it is therefore contextual evidence only and cannot close an immutable
gate.

The moving OpenAI page did not replace an immutable proof and closed no gate.
It is counted because it was consulted, not because it is constitutive of the
decision. Rights and judge/runtime closure would still be blocked had P1
stopped after the other four new documents; exhaustion of 15/15 additionally
activates the numeric ceiling.

P0 consulted ten documents. P1 consults five, so the cumulative source budget
is 15/15 and no slot remains. Search-result pages, redirects, mirrors, payload
files, queries, answers, qrels, corpus rows, indexes and decrypted material are
not admissible evidence. Public-metadata transport attempts are not converted
into benchmark, model, judge or scoring requests, all of which remain zero.
Historical operation counts are bounded process attestations combined with a
static capability check of the local runner, not full runtime network
instrumentation.

## 4. Facts established by the bounded clarification

The immutable evaluation-runner blob contains a concrete grader prompt,
response parser, metric aggregation code and default generation values. Its
default judge identifier is `Qwen/Qwen3-32B`; the defaults include temperature
`0.7`, top-p `0.8`, top-k `20`, maximum output tokens `4096`, vLLM chat with
thinking disabled, batch size `64` and tensor parallel size `1`.

Those are source defaults, not an immutable execution record. The runner
accepts command-line overrides, resolves the model from a mutable name and does
not bind the Qwen model or tokenizer to
`9216db5781bf21249d130ec9da846c4624c16137`.

The pinned `pyproject.toml` expresses important runtime dependencies as version
ranges, including `vllm>=0.9.0` and `transformers>=4.53.2`, and resolves
Tevatron from the moving `main` branch. It is not a resolved lockfile and does
not determine a unique judge runtime.

The immutable Qwen model-card revision provides a candidate identity for the
named judge family. It does not prove that the upstream runner used those
exact weights, that revision's tokenizer, or a uniquely resolved dependency
environment. The paper and official BrowseComp page document benchmark
provenance and comparison context, but neither supplies an EvidenceMesh
component-level rights disposition or fills the missing runner-to-model and
runtime bindings.

None of the five new documents supplies a per-document or component-level
rights disposition for the third-party Web material in the fixed corpus that
is sufficient for the intended EvidenceMesh handling. P1 records that absence;
it does not infer that rights are granted or denied.

## 5. Inferences and limits

The following are policy inferences, kept separate from the source facts:

- a source-locked prompt, parser and aggregation algorithm are only a partial
  comparability lock when runtime choices can be overridden or resolved
  differently;
- an immutable model-card revision is a candidate identity, not proof that an
  evaluator invoked that revision or its tokenizer;
- benchmark lineage and a repository-level license declaration do not alone
  provide the component-level corpus disposition required by EvidenceMesh;
- a moving official page can contextualize a decision but cannot satisfy an
  immutable identity requirement; and
- once all fifteen source slots are consumed, unresolved gates trigger the P0
  stop rule rather than a wider search or a weaker internal proxy.

No legal conclusion is made. The operational conclusion is limited to whether
the EvidenceMesh admission evidence is complete under the frozen policy.

## 6. Gate decisions

### 6.1 Rights gate

`blocked`. Component-level rights clearance remains incomplete. Asset
acquisition, corpus opening, processing and redistribution remain forbidden.

### 6.2 Prompt and algorithm source lock

`partial`. The exact runner blob locks the text and code of the default grader
prompt, response parsing, citation/retrieval calculations and aggregate-score
construction. It does not lock an effective run after command-line overrides,
model resolution and environment resolution.

### 6.3 Judge and runtime gate

`blocked`. The Qwen revision is only a candidate. The runner does not bind it,
the tokenizer revision is not bound, and the dependency declaration does not
resolve a unique environment. End-to-end evaluator comparability is therefore
incomplete.

### 6.4 Aggregate admission

`no_go`. BrowseComp-Plus remains unadmitted. P1 may pass its engineering lock
only by reporting these blocks and the exhausted budget exactly; it cannot
turn a partial source lock into evaluation permission.

## 7. Stop criterion and prohibited continuations

The bounded clarification has consumed the final five slots while both proof
targets remain incomplete. The Phase 11.8.10B-P0 stop criterion is therefore
triggered.

P1 must not:

- consult a sixteenth document or replace an inconvenient source with a
  secondary or moving substitute;
- download, inspect, parse or decrypt benchmark payloads;
- invoke a provider, model, judge, retrieval or scoring path;
- create an internal proxy score or describe one as official;
- acquire or redistribute BrowseComp-Plus assets; or
- publish, push, attach, distribute, merge or release P1 artifacts.

Phase 11.9, Phase 12 and V1 remain blocked.

## 8. Single recommended next step

Prepare one local, unsent upstream clarification request. It should ask the
authoritative BrowseComp-Plus maintainers for:

1. a component-level rights disposition covering acquisition, local
   processing, aggregate reporting and non-redistribution; and
2. the exact model and tokenizer revisions, effective prompt and generation
   configuration, resolved runtime dependency lock and authoritative scoring
   contract used for the official fixed-corpus comparison.

This recommendation authorizes drafting only. It does not authorize contacting
any person or service. Sending the request, opening an issue, posting a comment,
emailing a maintainer or consulting a reply requires a separate explicit GO
and a newly defined contact/evidence budget.

The draft action enters only after a deterministic P1 result reports the
15/15 source budget, both substantive gates blocked and the stop criterion
triggered. It stops if drafting would require another source, a payload, a
legal conclusion, a secret, publication or any external contact. Its maximum
budget is zero external requests, zero retries and zero publication.

## 9. Result semantics

The required substantive values are:

- `engineering_lock_may_pass = true`;
- `clarification_decision = no_go`;
- `candidate_id = browsecomp_plus`;
- `candidate_admitted = false`;
- `new_metadata_documents = 5`;
- `cumulative_metadata_documents = 15`;
- `remaining_metadata_documents = 0`;
- `component_rights_clearance_complete = false`;
- `prompt_and_algorithm_source_lock = partial`;
- `qwen_candidate_revision_identified = true`;
- `runner_binds_qwen_candidate_revision = false`;
- `judge_runtime_closure_complete = false`;
- `end_to_end_comparability_complete = false`;
- `stop_criterion_triggered = true`;
- `asset_acquisition_allowed = false`;
- `evaluation_allowed = false`;
- `publication_allowed = false`;
- `phase_11_9_status = blocked`;
- `phase_12_status = blocked`;
- `v1_readiness = false`.

Unknown, absent or contradictory values fail closed.

## 10. Local-only boundary

The protocol, manifest, validators and aggregate P1 result may be created and
tested locally. They must not be pushed to the public pull request, uploaded as
workflow artifacts, distributed, merged or released without a separate
publication GO. The pull request stays draft and distributions stay
unpublished.
