"""Fail-closed Phase 11.8.10B-P0 policy and comparability lock.

The validator consumes committed public-metadata decisions only. It has no
benchmark download, payload parsing, decryption, provider, model, retrieval,
judge, scoring, environment, process, or network capability.
"""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

POLICY_SCHEMA = "evidencemesh.phase11_8_10b_p0.policy-comparability-lock.v1"
RESULT_SCHEMA = "evidencemesh.phase11_8_10b_p0.policy-comparability-result.v1"
DEFAULT_POLICY_PATH = (
    Path(__file__).parent / "data/phase11_8_10b_p0_policy_comparability_lock_v1.json"
)
MAX_POLICY_BYTES = 256 * 1024
EXPECTED_SUITES = ("bright", "browsecomp_plus")
EXPECTED_PREDECESSOR_TREE = "7a774664442caa9201b419fb219d47c6113a52a3"
EXPECTED_PREDECESSOR_FILES = {
    "asset_lock_manifest": (
        "benchmarks/data/phase11_8_10a_asset_locks_v1.json",
        "8c470471e250df2f33bb6840bec27c5bdecb9f4ad7654142374c0eb4df615f2c",
    ),
    "object_inventory": (
        "benchmarks/data/phase11_8_10a_object_inventory_v1.json",
        "d23f81e23e2e1c8e075de7647d7529ccaf9c3a787f8c18106e101d8abef57a3e",
    ),
    "protocol": (
        "docs/benchmark-protocol-v26.md",
        "b97a215a6be2294a23db15c4183353371a185d7c11c738d7ca3894beb710bd77",
    ),
    "result": (
        "benchmarks/results/phase11_8_10a_asset_reconnaissance_2026-07-31.json",
        "3e0c2d7e99778d71f773a980a4212cd44fd8960fd1ee7d142350867345c9310d",
    ),
    "source_lock": (
        "benchmarks/data/phase11_8_10a_source_locks_v1.json",
        "f7da0ef14f6b5fee788eb8139c9e62df13d6b51f23492fb9852da42463301094",
    ),
}
EXPECTED_DOCUMENTS = (
    (
        "bright_code_readme",
        "bright",
        "d99e8391d967d4c2b3a74732530d2309e2fc92b6",
        "README.md",
        "https://github.com/xlang-ai/BRIGHT/blob/"
        "d99e8391d967d4c2b3a74732530d2309e2fc92b6/README.md",
    ),
    (
        "bright_code_license",
        "bright",
        "d99e8391d967d4c2b3a74732530d2309e2fc92b6",
        "LICENSE",
        "https://github.com/xlang-ai/BRIGHT/blob/d99e8391d967d4c2b3a74732530d2309e2fc92b6/LICENSE",
    ),
    (
        "bright_runner",
        "bright",
        "d99e8391d967d4c2b3a74732530d2309e2fc92b6",
        "run.py",
        "https://github.com/xlang-ai/BRIGHT/blob/d99e8391d967d4c2b3a74732530d2309e2fc92b6/run.py",
    ),
    (
        "bright_retrievers",
        "bright",
        "d99e8391d967d4c2b3a74732530d2309e2fc92b6",
        "retrievers.py",
        "https://github.com/xlang-ai/BRIGHT/blob/"
        "d99e8391d967d4c2b3a74732530d2309e2fc92b6/retrievers.py",
    ),
    (
        "bright_dataset_card",
        "bright",
        "3066d29c9651a576c8aba4832d249807b181ecae",
        "README.md",
        "https://huggingface.co/datasets/xlangai/BRIGHT/blob/"
        "3066d29c9651a576c8aba4832d249807b181ecae/README.md",
    ),
    (
        "browsecomp_plus_code_readme",
        "browsecomp_plus",
        "046949032b0328319cc9a02663a759ec601d9402",
        "README.md",
        "https://github.com/texttron/BrowseComp-Plus/blob/"
        "046949032b0328319cc9a02663a759ec601d9402/README.md",
    ),
    (
        "browsecomp_plus_code_license",
        "browsecomp_plus",
        "046949032b0328319cc9a02663a759ec601d9402",
        "LICENSE",
        "https://github.com/texttron/BrowseComp-Plus/blob/"
        "046949032b0328319cc9a02663a759ec601d9402/LICENSE",
    ),
    (
        "browsecomp_plus_decrypt_metadata_transform",
        "browsecomp_plus",
        "046949032b0328319cc9a02663a759ec601d9402",
        "scripts_build_index/decrypt_dataset.py",
        "https://github.com/texttron/BrowseComp-Plus/blob/"
        "046949032b0328319cc9a02663a759ec601d9402/"
        "scripts_build_index/decrypt_dataset.py",
    ),
    (
        "browsecomp_plus_query_bundle_dataset_card",
        "browsecomp_plus",
        "144cff8e35b5eaef7e526346aa60774a9deb941f",
        "README.md",
        "https://huggingface.co/datasets/Tevatron/browsecomp-plus/blob/"
        "144cff8e35b5eaef7e526346aa60774a9deb941f/README.md",
    ),
    (
        "browsecomp_plus_fixed_corpus_dataset_card",
        "browsecomp_plus",
        "b27b02bc3e45511b8b82a13e6f90ce761df726f6",
        "README.md",
        "https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus/blob/"
        "b27b02bc3e45511b8b82a13e6f90ce761df726f6/README.md",
    ),
)
EXPECTED_CONTENT_IDENTITIES = {
    "bright_code_readme": ("git-blob-sha1", "4343c51da97ce20dd9c9c0fb269a87d45e7beafe"),
    "bright_code_license": ("git-blob-sha1", "2f244ac814036ecd9ba9f69782e89ce6b1dca9eb"),
    "bright_runner": ("git-blob-sha1", "6a22eb46c6cee797cbd719a0890e1ed0420561da"),
    "bright_retrievers": ("git-blob-sha1", "0ce9ef84f802b6318a9c195d3755a1b2103d4f54"),
    "bright_dataset_card": (
        "immutable-revision-and-path-only",
        "3066d29c9651a576c8aba4832d249807b181ecae",
    ),
    "browsecomp_plus_code_readme": (
        "git-blob-sha1",
        "8f180d4fbf7e10a0ae66b803444176755741e444",
    ),
    "browsecomp_plus_code_license": (
        "git-blob-sha1",
        "1eeb9f2ab7b823eef913d01626ca28adf6422fba",
    ),
    "browsecomp_plus_decrypt_metadata_transform": (
        "git-blob-sha1",
        "6a895dd027b8024119a14149fd633d5592c46d9a",
    ),
    "browsecomp_plus_query_bundle_dataset_card": (
        "immutable-revision-and-path-only",
        "144cff8e35b5eaef7e526346aa60774a9deb941f",
    ),
    "browsecomp_plus_fixed_corpus_dataset_card": (
        "immutable-revision-and-path-only",
        "b27b02bc3e45511b8b82a13e6f90ce761df726f6",
    ),
}
EXPECTED_FACTS = {
    "bright": (
        (
            "bright_declared_license",
            "The official code repository and immutable dataset card declare CC-BY-4.0.",
            ("bright_code_license", "bright_dataset_card"),
        ),
        (
            "bright_source_derived_components",
            "The selected benchmark contains source-derived components and the consulted metadata "
            "supplies no item-level or component-level rights map sufficient for EvidenceMesh "
            "admission.",
            ("bright_code_readme", "bright_dataset_card"),
        ),
        (
            "bright_snapshot_population",
            "The pinned selected snapshot declares 1,384 queries; the predecessor lock records an "
            "unresolved mapping to the 1,398-query publication population and public leaderboard "
            "revision.",
            ("bright_dataset_card",),
        ),
        (
            "bright_evaluator_dependency",
            "The upstream scoring path uses pytrec_eval without an exact dependency-version and "
            "scoring-semantics closure in the consulted immutable code.",
            ("bright_runner", "bright_retrievers"),
        ),
    ),
    "browsecomp_plus": (
        (
            "browsecomp_plus_declared_license",
            "The official repository and immutable dataset cards declare MIT.",
            (
                "browsecomp_plus_code_license",
                "browsecomp_plus_query_bundle_dataset_card",
                "browsecomp_plus_fixed_corpus_dataset_card",
            ),
        ),
        (
            "browsecomp_plus_third_party_corpus",
            "The fixed corpus contains third-party Web pages and the consulted metadata "
            "supplies no per-document rights field or component-level rights clearance for "
            "EvidenceMesh admission.",
            ("browsecomp_plus_code_readme", "browsecomp_plus_fixed_corpus_dataset_card"),
        ),
        (
            "browsecomp_plus_comparison_boundary",
            "The documented comparison is BrowseComp-Plus over its fixed corpus; it does not "
            "establish equivalence to open-Web BrowseComp, live search, another corpus or a "
            "rebuilt index.",
            (
                "browsecomp_plus_code_readme",
                "browsecomp_plus_query_bundle_dataset_card",
                "browsecomp_plus_fixed_corpus_dataset_card",
            ),
        ),
        (
            "browsecomp_plus_judge_dependency",
            "The published evaluation path refers to a Qwen judge without a complete immutable "
            "judge, tokenizer, prompt, generation, runtime and deterministic scoring closure in "
            "the consulted metadata.",
            ("browsecomp_plus_code_readme",),
        ),
    ),
}
EXPECTED_INFERENCES = (
    (
        "declared_license_does_not_complete_component_clearance",
        "A repository or dataset-card license declaration alone does not establish the "
        "component-level rights clearance required by EvidenceMesh policy.",
    ),
    (
        "unlocked_evaluator_is_not_officially_comparable",
        "A score produced without immutable population and evaluator closure cannot be labeled "
        "officially comparable.",
    ),
    (
        "scope_reduction_does_not_create_clearance",
        "Reducing the future evaluation to one candidate can reduce cost but cannot repair that "
        "candidate's unresolved admission gates.",
    ),
)
EXPECTED_BRIGHT_BLOCKERS = (
    "third-party-component-rights-not-itemized",
    "pinned-snapshot-to-publication-and-leaderboard-mapping-unresolved",
    "pytrec_eval-version-and-scoring-semantics-unpinned",
)
EXPECTED_BROWSECOMP_BLOCKERS = (
    "third-party-component-rights-not-itemized",
    "qwen-judge-tokenizer-prompt-generation-and-runtime-closure-unpinned",
)
EXPECTED_NEXT_STEP = (
    "Run one BrowseComp-Plus-only immutable-metadata clarification, capped at five additional "
    "unique public documents, to seek component-rights and fully pinned judge/runtime evidence; "
    "stop without acquisition if either proof class remains unresolved."
)
EXPECTED_ENTRY_CRITERIA = (
    "P0 result reproduces with all 16 engineering gates passing and both candidates blocked",
    "BrowseComp-Plus is the sole clarification candidate and no acquisition candidate is admitted",
    "exactly five unique public metadata documents remain in the approved budget",
    "proof targets are limited to component-level rights and complete judge, tokenizer, prompt, "
    "generation, runtime and scoring closure",
    "a separate explicit GO authorizes this metadata-only clarification",
)
EXPECTED_SUCCESS_CRITERIA = (
    "component-level rights disposition satisfies intended local-only non-redistribution handling",
    "official BrowseComp-Plus fixed-corpus population and track mapping remain immutable",
    "judge, tokenizer, prompt, generation, runtime dependencies and scoring semantics are fully "
    "immutable and reproducible",
)
EXPECTED_FUTURE_ACQUISITION_ENTRY_CRITERIA = (
    "component-level rights disposition covers intended acquisition, local processing, reporting "
    "and non-redistribution",
    "exact official population, asset revision and track mapping is immutable",
    "evaluator or judge identity, tokenizer, prompt, generation configuration, runtime "
    "dependencies and scoring semantics are immutable as applicable",
    "candidate-specific acquisition manifest and storage boundary are approved",
    "separate explicit candidate GO is recorded",
)
EXPECTED_STOP_CRITERIA = (
    "fifteen-unique-public-metadata-document ceiling would be exceeded",
    "payload, credential, secret, decryption, provider, model, retrieval, judge or scoring access "
    "would be required",
    "moving or secondary evidence would have to replace immutable primary evidence",
    "official score target would have to be weakened to an internal proxy",
    "publication or redistribution would be required",
    "no independent candidate has every required admission gate complete after the bounded "
    "clarification",
)


class PolicyLockError(ValueError):
    """Raised when the P0 policy ceases to be complete and fail-closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyLockError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return cast(dict[str, Any], value)


def _array(value: object, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label} must be an array")
    return cast(list[Any], value)


def _string(value: object, label: str) -> str:
    _require(isinstance(value, str) and bool(cast(str, value).strip()), f"{label} must be a string")
    return cast(str, value)


def _lower_hex(value: object, length: int, label: str) -> str:
    text = _string(value, label)
    _require(len(text) == length, f"{label} must be {length} lowercase hex characters")
    _require(all(character in "0123456789abcdef" for character in text), f"{label} is not hex")
    return text


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    _require(set(value) == expected, f"{label} schema drifted")


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    _require(path == DEFAULT_POLICY_PATH, "policy path is frozen")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PolicyLockError("cannot stat policy manifest") from exc
    _require(stat.S_ISREG(metadata.st_mode), "policy manifest must be a regular file")
    _require(not path.is_symlink(), "policy manifest must not be a symlink")
    _require(metadata.st_size <= MAX_POLICY_BYTES, "policy manifest is too large")
    try:
        decoded = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyLockError("policy manifest is not valid UTF-8 JSON") from exc
    policy = _object(decoded, "policy manifest")
    validate_policy(policy)
    return policy


def _validate_predecessor(policy: Mapping[str, Any]) -> None:
    predecessor = _object(policy.get("predecessor_lock"), "predecessor_lock")
    _exact_keys(
        predecessor,
        {"phase", "repository_tree", *EXPECTED_PREDECESSOR_FILES},
        "predecessor_lock",
    )
    _require(predecessor.get("phase") == "11.8.10A", "predecessor phase drifted")
    _require(
        predecessor.get("repository_tree") == EXPECTED_PREDECESSOR_TREE,
        "predecessor repository tree drifted",
    )
    for record_id, (path, digest) in EXPECTED_PREDECESSOR_FILES.items():
        record = _object(predecessor.get(record_id), f"predecessor.{record_id}")
        expected_record_keys = {"path", "sha256"}
        if record_id == "result":
            expected_record_keys.update({"quality_decision", "real_external_score"})
        _exact_keys(record, expected_record_keys, f"predecessor.{record_id}")
        _require(record.get("path") == path, f"predecessor {record_id} path drifted")
        _require(record.get("sha256") == digest, f"predecessor {record_id} hash drifted")
    result = _object(predecessor.get("result"), "predecessor.result")
    _require(result.get("quality_decision") == "no_go", "predecessor no-go drifted")
    _require(result.get("real_external_score") is False, "predecessor score state drifted")


def _validate_phase_policy(policy: Mapping[str, Any]) -> None:
    phase = _object(policy.get("phase_policy"), "phase_policy")
    _exact_keys(
        phase,
        {
            "asset_acquisition_allowed",
            "asset_payload_download_allowed",
            "asset_payload_open_or_parse_allowed",
            "candidate_suites_admitted_now",
            "distribution_allowed",
            "evaluation_allowed",
            "independent_candidate_ids",
            "internal-proxy-score_is_acceptable_substitute",
            "mode",
            "model_requests_allowed",
            "next_phase_requires_separate_go",
            "one_authoritative_suite_may_suffice_later",
            "phase_11_8_10b_acquisition_allowed",
            "phase_11_9_allowed",
            "phase_12_allowed",
            "provider_requests_allowed",
            "publication_allowed",
            "quality_claim_allowed",
            "query_decryption_allowed",
            "score_generation_allowed",
            "score_target",
            "search_requests_allowed",
            "secret_access_allowed",
        },
        "phase_policy",
    )
    _require(phase.get("mode") == "metadata-only-local-fail-closed", "phase mode drifted")
    _require(
        phase.get("score_target") == "officially-comparable-external-score",
        "official score target drifted",
    )
    _require(
        phase.get("internal-proxy-score_is_acceptable_substitute") is False,
        "internal proxy score must remain rejected",
    )
    _require(
        phase.get("independent_candidate_ids") == list(EXPECTED_SUITES),
        "candidate scope drifted",
    )
    _require(
        phase.get("one_authoritative_suite_may_suffice_later") is True,
        "one-suite future rule drifted",
    )
    _require(phase.get("candidate_suites_admitted_now") == [], "a suite was admitted")
    forbidden_permissions = (
        "asset_acquisition_allowed",
        "asset_payload_download_allowed",
        "asset_payload_open_or_parse_allowed",
        "query_decryption_allowed",
        "evaluation_allowed",
        "score_generation_allowed",
        "provider_requests_allowed",
        "model_requests_allowed",
        "search_requests_allowed",
        "secret_access_allowed",
        "publication_allowed",
        "distribution_allowed",
        "quality_claim_allowed",
        "phase_11_8_10b_acquisition_allowed",
        "phase_11_9_allowed",
        "phase_12_allowed",
    )
    for key in forbidden_permissions:
        _require(phase.get(key) is False, f"{key} must remain false")
    _require(phase.get("next_phase_requires_separate_go") is True, "separate GO is required")


def _validate_research_budget(policy: Mapping[str, Any]) -> dict[str, str]:
    budget = _object(policy.get("research_budget"), "research_budget")
    _exact_keys(
        budget,
        {
            "benchmark_search_api_requests",
            "bright_document_count",
            "browsecomp_plus_document_count",
            "consulted_unique_public_metadata_documents",
            "decryption_requests",
            "judge_requests",
            "maximum_additional_metadata_documents_without_new_budget",
            "maximum_unique_public_metadata_documents",
            "model_requests",
            "payload_requests",
            "provider_requests",
            "publication_requests",
            "raw_metadata_transport_request_count_is_a_budget_metric",
            "remaining_unique_public_metadata_documents",
            "retrieval_requests",
            "scoring_requests",
            "secret_requests",
            "source_kind",
        },
        "research_budget",
    )
    _require(
        budget.get("source_kind") == "immutable-public-primary-metadata-only",
        "source kind drifted",
    )
    _require(
        budget.get("maximum_unique_public_metadata_documents") == 15,
        "document ceiling drifted",
    )
    _require(
        budget.get("consulted_unique_public_metadata_documents") == 10,
        "consulted document count drifted",
    )
    _require(
        budget.get("remaining_unique_public_metadata_documents") == 5, "budget remainder drifted"
    )
    _require(budget.get("bright_document_count") == 5, "BRIGHT document budget drifted")
    _require(
        budget.get("browsecomp_plus_document_count") == 5,
        "BrowseComp-Plus document budget drifted",
    )
    zero_request_keys = (
        "payload_requests",
        "provider_requests",
        "model_requests",
        "benchmark_search_api_requests",
        "retrieval_requests",
        "judge_requests",
        "scoring_requests",
        "secret_requests",
        "decryption_requests",
        "publication_requests",
    )
    for key in zero_request_keys:
        _require(budget.get(key) == 0, f"{key} must remain zero")
    _require(
        budget.get("maximum_additional_metadata_documents_without_new_budget") == 5,
        "remaining metadata request budget drifted",
    )
    _require(
        budget.get("raw_metadata_transport_request_count_is_a_budget_metric") is False,
        "transport requests must not replace the unique-document budget",
    )

    documents = _array(policy.get("consulted_primary_documents"), "consulted_primary_documents")
    _require(len(documents) == len(EXPECTED_DOCUMENTS), "exactly ten documents are required")
    source_suites: dict[str, str] = {}
    for index, expected in enumerate(EXPECTED_DOCUMENTS):
        source = _object(documents[index], f"document[{index}]")
        _exact_keys(
            source,
            {
                "authority",
                "consultation_mode",
                "content_identity_kind",
                "content_identity_value",
                "immutable_revision",
                "local_content_digest_verified",
                "path",
                "payload_accessed",
                "source_id",
                "suite_id",
                "url",
            },
            f"document[{index}]",
        )
        source_id, suite_id, revision, path, url = expected
        _require(source.get("source_id") == source_id, f"source order or id drifted: {source_id}")
        _require(source_id not in source_suites, f"duplicate source id: {source_id}")
        source_suites[source_id] = suite_id
        _require(source.get("suite_id") == suite_id, f"source suite drifted: {source_id}")
        _require(
            source.get("immutable_revision") == revision, f"source revision drifted: {source_id}"
        )
        _lower_hex(source.get("immutable_revision"), 40, f"{source_id}.revision")
        _require(source.get("path") == path, f"source path drifted: {source_id}")
        _require(source.get("url") == url, f"immutable source URL drifted: {source_id}")
        identity_kind, identity_value = EXPECTED_CONTENT_IDENTITIES[source_id]
        _require(
            source.get("content_identity_kind") == identity_kind,
            f"content identity kind drifted: {source_id}",
        )
        _require(
            source.get("content_identity_value") == identity_value,
            f"content identity value drifted: {source_id}",
        )
        _lower_hex(source.get("content_identity_value"), 40, f"{source_id}.content_identity")
        _require(
            source.get("local_content_digest_verified") is False,
            f"local content verification was overstated: {source_id}",
        )
        _require(
            source.get("consultation_mode")
            in {
                "metadata-text-only",
                "metadata-code-only",
                "metadata-code-only-no-execution",
            },
            f"source mode drifted: {source_id}",
        )
        _require(source.get("payload_accessed") is False, f"payload accessed: {source_id}")
    return source_suites


def _validate_evidence_structure(
    policy: Mapping[str, Any], source_suites: Mapping[str, str]
) -> None:
    facts = _object(policy.get("facts"), "facts")
    _require(tuple(facts) == EXPECTED_SUITES, "fact suite scope drifted")
    for suite_id in EXPECTED_SUITES:
        records = _array(facts.get(suite_id), f"facts.{suite_id}")
        expected_records = EXPECTED_FACTS[suite_id]
        _require(len(records) == len(expected_records), f"{suite_id} fact count drifted")
        for index, (record, expected) in enumerate(zip(records, expected_records, strict=True)):
            fact = _object(record, f"facts.{suite_id}.record")
            fact_id_expected, statement_expected, references_expected = expected
            expected_keys = {"fact_id", "source_ids", "statement"}
            if fact_id_expected == "bright_snapshot_population":
                expected_keys.add("predecessor_source")
            _exact_keys(fact, expected_keys, f"facts.{suite_id}[{index}]")
            fact_id = _string(fact.get("fact_id"), "fact_id")
            _require(fact_id == fact_id_expected, f"fact order or id drifted: {fact_id_expected}")
            _require(
                fact.get("statement") == statement_expected,
                f"fact statement drifted: {fact_id_expected}",
            )
            references = _array(fact.get("source_ids"), f"{fact_id}.source_ids")
            normalized_references = tuple(
                _string(reference, f"{fact_id}.source_id") for reference in references
            )
            _require(
                normalized_references == references_expected,
                f"fact sources drifted: {fact_id_expected}",
            )
            _require(
                all(
                    source_suites.get(reference) == suite_id for reference in normalized_references
                ),
                f"{fact_id} cites another suite",
            )
            if fact_id_expected == "bright_snapshot_population":
                _require(
                    fact.get("predecessor_source") == "phase11_8_10a",
                    "BRIGHT predecessor fact source drifted",
                )

    inferences = _array(policy.get("inferences"), "inferences")
    _require(len(inferences) == len(EXPECTED_INFERENCES), "inference count drifted")
    observed_inferences: set[str] = set()
    for index, (record, expected) in enumerate(zip(inferences, EXPECTED_INFERENCES, strict=True)):
        inference = _object(record, "inference")
        _exact_keys(
            inference,
            {"applies_to", "inference_id", "statement"},
            f"inference[{index}]",
        )
        inference_id_expected, statement_expected = expected
        inference_id = _string(inference.get("inference_id"), "inference_id")
        _require(inference_id not in observed_inferences, f"duplicate inference: {inference_id}")
        observed_inferences.add(inference_id)
        _require(inference_id == inference_id_expected, "inference order or id drifted")
        _require(inference.get("statement") == statement_expected, "inference statement drifted")
        _require(inference.get("applies_to") == list(EXPECTED_SUITES), "inference scope drifted")
    _require(
        observed_inferences == {item[0] for item in EXPECTED_INFERENCES},
        "inference set drifted",
    )


def _validate_candidate_decisions(policy: Mapping[str, Any]) -> None:
    candidates = _array(policy.get("candidate_decisions"), "candidate_decisions")
    _require(len(candidates) == 2, "exactly two candidate decisions are required")
    for index, suite_id in enumerate(EXPECTED_SUITES):
        candidate = _object(candidates[index], f"candidate.{suite_id}")
        common_keys = {
            "acquisition_eligible",
            "blocking_reasons",
            "candidate_status",
            "comparability_complete",
            "component_rights_clearance_complete",
            "declared_license",
            "evaluation_eligible",
            "independently_assessed",
            "official_population_mapping_complete",
            "official_score_claim_eligible",
            "official_track_mapping_complete",
            "suite_id",
        }
        suite_specific_keys = (
            {"evaluator_dependency_lock_complete"}
            if suite_id == "bright"
            else {
                "decryption_eligible",
                "judge_prompt_and_generation_config_lock_complete",
                "official_comparability_boundary",
                "qwen_judge_identity_lock_complete",
                "runtime_dependency_lock_complete",
                "tokenizer_revision_lock_complete",
            }
        )
        _exact_keys(candidate, common_keys | suite_specific_keys, f"candidate.{suite_id}")
        _require(candidate.get("suite_id") == suite_id, "candidate order or id drifted")
        _require(candidate.get("candidate_status") == "blocked", f"{suite_id} must remain blocked")
        _require(candidate.get("independently_assessed") is True, f"{suite_id} was not independent")
        _require(
            candidate.get("component_rights_clearance_complete") is False,
            f"{suite_id} component rights were not cleared",
        )
        for key in (
            "comparability_complete",
            "acquisition_eligible",
            "evaluation_eligible",
            "official_score_claim_eligible",
        ):
            _require(candidate.get(key) is False, f"{suite_id}.{key} must remain false")
        blockers = _array(candidate.get("blocking_reasons"), f"{suite_id}.blocking_reasons")
        expected_blockers = (
            EXPECTED_BRIGHT_BLOCKERS if suite_id == "bright" else EXPECTED_BROWSECOMP_BLOCKERS
        )
        _require(tuple(blockers) == expected_blockers, f"{suite_id} blockers drifted")
    bright = _object(candidates[0], "candidate.bright")
    _require(bright.get("declared_license") == "CC-BY-4.0", "BRIGHT license declaration drifted")
    _require(
        bright.get("official_population_mapping_complete") is False, "BRIGHT population unlocked"
    )
    _require(bright.get("official_track_mapping_complete") is False, "BRIGHT track unlocked")
    _require(bright.get("evaluator_dependency_lock_complete") is False, "BRIGHT evaluator unlocked")
    browsecomp = _object(candidates[1], "candidate.browsecomp_plus")
    _require(browsecomp.get("declared_license") == "MIT", "BrowseComp-Plus license drifted")
    _require(
        browsecomp.get("official_population_mapping_complete") is True,
        "BrowseComp-Plus population mapping drifted",
    )
    _require(
        browsecomp.get("official_track_mapping_complete") is True,
        "BrowseComp-Plus track mapping drifted",
    )
    _require(
        browsecomp.get("official_comparability_boundary") == "browsecomp-plus-fixed-corpus-only",
        "BrowseComp-Plus comparability boundary drifted",
    )
    for key in (
        "qwen_judge_identity_lock_complete",
        "tokenizer_revision_lock_complete",
        "judge_prompt_and_generation_config_lock_complete",
        "runtime_dependency_lock_complete",
        "decryption_eligible",
    ):
        _require(browsecomp.get(key) is False, f"BrowseComp-Plus {key} must remain false")


def _validate_decision(policy: Mapping[str, Any]) -> None:
    options = _array(policy.get("option_analysis"), "option_analysis")
    expected_options = (
        ("continue_both_now", "rejected"),
        ("reduce_to_one_now", "deferred"),
        ("technical_alpha_isolated", "recommended"),
    )
    _require(len(options) == len(expected_options), "option set drifted")
    for record, (option_id, decision) in zip(options, expected_options, strict=True):
        option = _object(record, f"option.{option_id}")
        _exact_keys(
            option,
            {"benefit", "decision", "failure", "label", "option_id"},
            f"option.{option_id}",
        )
        _require(option.get("option_id") == option_id, f"option id drifted: {option_id}")
        _require(option.get("decision") == decision, f"option decision drifted: {option_id}")
        _string(option.get("benefit"), f"{option_id}.benefit")
        _string(option.get("failure"), f"{option_id}.failure")

    recommended = _object(policy.get("recommended_decision"), "recommended_decision")
    _exact_keys(
        recommended,
        {
            "asset_acquisition_before_clearance",
            "official_score_target_preserved",
            "one_suite_future_rule_preserved",
            "one_suite_selected_now",
            "option_id",
            "single_next_step",
        },
        "recommended_decision",
    )
    _require(recommended.get("option_id") == "technical_alpha_isolated", "recommendation drifted")
    _require(
        recommended.get("single_next_step") == EXPECTED_NEXT_STEP,
        "single next step drifted",
    )
    _require(recommended.get("official_score_target_preserved") is True, "official target lost")
    _require(
        recommended.get("asset_acquisition_before_clearance") is False, "early acquisition enabled"
    )
    _require(recommended.get("one_suite_future_rule_preserved") is True, "one-suite rule lost")
    _require(recommended.get("one_suite_selected_now") is False, "a suite was selected too early")

    action = _object(policy.get("next_evidence_action"), "next_evidence_action")
    _exact_keys(
        action,
        {
            "action_kind",
            "candidate_id",
            "entry_criteria",
            "future_acquisition_review_entry_criteria",
            "maximum_additional_unique_public_metadata_documents",
            "maximum_benchmark_payload_requests",
            "maximum_provider_or_model_requests",
            "maximum_retries",
            "stop_criteria",
            "success_criteria",
        },
        "next_evidence_action",
    )
    _require(
        action.get("action_kind") == "browsecomp-plus-immutable-metadata-clarification",
        "next action kind drifted",
    )
    _require(action.get("candidate_id") == "browsecomp_plus", "next candidate drifted")
    _require(
        tuple(_array(action.get("entry_criteria"), "entry_criteria")) == EXPECTED_ENTRY_CRITERIA,
        "entry criteria drifted",
    )
    _require(
        tuple(_array(action.get("success_criteria"), "success_criteria"))
        == EXPECTED_SUCCESS_CRITERIA,
        "success criteria drifted",
    )
    _require(
        tuple(
            _array(
                action.get("future_acquisition_review_entry_criteria"),
                "future_acquisition_review_entry_criteria",
            )
        )
        == EXPECTED_FUTURE_ACQUISITION_ENTRY_CRITERIA,
        "future acquisition entry criteria drifted",
    )
    _require(
        tuple(_array(action.get("stop_criteria"), "stop_criteria")) == EXPECTED_STOP_CRITERIA,
        "stop criteria drifted",
    )
    _require(
        action.get("maximum_additional_unique_public_metadata_documents") == 5,
        "next metadata budget drifted",
    )
    for key in (
        "maximum_benchmark_payload_requests",
        "maximum_provider_or_model_requests",
        "maximum_retries",
    ):
        _require(action.get(key) == 0, f"{key} must remain zero")

    aggregate = _object(policy.get("aggregate_decision"), "aggregate_decision")
    _exact_keys(
        aggregate,
        {
            "asset_acquisition_allowed",
            "benchmark_comparability_complete",
            "candidate_suite_count",
            "candidate_suites_admitted",
            "component_license_clearance_complete",
            "engineering_lock_may_pass",
            "evaluation_allowed",
            "officially_comparable_score_available",
            "phase_11_8_10b_acquisition_status",
            "phase_11_9_status",
            "phase_12_status",
            "publication_allowed",
            "quality_decision",
            "real_external_score",
            "v1_readiness",
        },
        "aggregate_decision",
    )
    _require(aggregate.get("engineering_lock_may_pass") is True, "engineering lock disabled")
    _require(aggregate.get("quality_decision") == "no_go", "quality no-go drifted")
    _require(aggregate.get("candidate_suite_count") == 2, "candidate count drifted")
    _require(aggregate.get("candidate_suites_admitted") == 0, "a candidate was admitted")
    for key in (
        "real_external_score",
        "officially_comparable_score_available",
        "component_license_clearance_complete",
        "benchmark_comparability_complete",
        "asset_acquisition_allowed",
        "evaluation_allowed",
        "publication_allowed",
        "v1_readiness",
    ):
        _require(aggregate.get(key) is False, f"aggregate {key} must remain false")
    _require(
        aggregate.get("phase_11_8_10b_acquisition_status") == "blocked",
        "Phase 11.8.10B acquisition status drifted",
    )
    _require(aggregate.get("phase_11_9_status") == "blocked", "Phase 11.9 status drifted")
    _require(aggregate.get("phase_12_status") == "blocked", "Phase 12 status drifted")


def validate_policy(policy: Mapping[str, Any]) -> None:
    """Validate the exact P0 decision boundary without contacting any source."""

    expected_top_level = {
        "aggregate_decision",
        "candidate_decisions",
        "captured_on",
        "consulted_primary_documents",
        "facts",
        "inferences",
        "next_evidence_action",
        "option_analysis",
        "phase_policy",
        "predecessor_lock",
        "purpose",
        "recommended_decision",
        "research_budget",
        "schema_version",
    }
    _require(set(policy) == expected_top_level, "policy top-level schema drifted")
    _require(policy.get("schema_version") == POLICY_SCHEMA, "policy schema drifted")
    _require(
        policy.get("purpose") == "metadata-only-policy-and-official-comparability-lock",
        "policy purpose drifted",
    )
    _require(policy.get("captured_on") == "2026-08-01", "capture date drifted")
    _validate_predecessor(policy)
    _validate_phase_policy(policy)
    source_ids = _validate_research_budget(policy)
    _validate_evidence_structure(policy, source_ids)
    _validate_candidate_decisions(policy)
    _validate_decision(policy)


def build_policy_report(
    policy: Mapping[str, Any], *, methodology_commit_sha: str
) -> dict[str, Any]:
    """Build the deterministic aggregate result after validation."""

    validate_policy(policy)
    _lower_hex(methodology_commit_sha, 40, "methodology_commit_sha")
    candidates = _array(policy["candidate_decisions"], "candidate_decisions")
    gates = [
        "phase11_8_10a_authorities_exact",
        "predecessor_no_go_and_no_external_score_preserved",
        "ten_of_fifteen_immutable_primary_documents_bounded",
        "facts_and_inferences_separated",
        "exact_two_independent_candidate_scope",
        "declared_licenses_separated_from_component_rights",
        "bright_component_rights_fail_closed",
        "bright_official_population_mapping_fail_closed",
        "bright_evaluator_dependency_fail_closed",
        "browsecomp_plus_component_rights_fail_closed",
        "browsecomp_plus_fixed_corpus_boundary_locked",
        "browsecomp_plus_judge_and_runtime_fail_closed",
        "official_target_one_suite_later_none_admitted_now",
        "zero_payload_live_score_or_publication_operations",
        "technical_alpha_isolated_from_evidence_promotion",
        "phase11_8_10b_acquisition_phase11_9_and_phase12_blocked",
    ]
    return {
        "schema_version": RESULT_SCHEMA,
        "phase": "11.8.10B-P0",
        "generated_on": "2026-08-01",
        "mode": "metadata-only-local-fail-closed",
        "methodology_commit_sha": methodology_commit_sha,
        "policy_manifest_canonical_sha256": canonical_sha256(policy),
        "outcome": "policy_comparability_lock_complete_acquisition_blocked",
        "engineering_lock": "pass",
        "quality_decision": "no_go",
        "real_external_score": False,
        "officially_comparable_score_available": False,
        "gate_summary": {"passed": len(gates), "failed": 0, "total": len(gates)},
        "gates": [
            {"gate": index, "gate_id": gate_id, "passed": True}
            for index, gate_id in enumerate(gates, start=1)
        ],
        "research_budget": {
            "maximum_unique_public_metadata_documents": 15,
            "consulted_unique_public_metadata_documents": 10,
            "remaining_unique_public_metadata_documents": 5,
            "raw_transport_request_count_used_as_budget": False,
        },
        "external_source_identity": {
            "github_documents_with_git_blob_identity": 7,
            "huggingface_cards_with_revision_and_path_identity_only": 3,
            "external_document_content_digests_verified_locally": 0,
            "identity_is_not_local_content_integrity_proof": True,
        },
        "candidate_decisions": [
            {
                "suite_id": candidate["suite_id"],
                "status": candidate["candidate_status"],
                "component_rights_clearance_complete": False,
                "comparability_complete": False,
                "acquisition_eligible": False,
                "evaluation_eligible": False,
                "blocking_reasons": candidate["blocking_reasons"],
            }
            for candidate in candidates
        ],
        "selected_policy": {
            "option_id": "technical_alpha_isolated",
            "official_score_target": "officially-comparable-external-score",
            "one_authoritative_suite_may_suffice_later": True,
            "candidate_suites_admitted_now": 0,
            "asset_acquisition_before_clearance": False,
        },
        "next_evidence_action": {
            "action_kind": "browsecomp-plus-immutable-metadata-clarification",
            "candidate_id": "browsecomp_plus",
            "entry_criteria_count": len(EXPECTED_ENTRY_CRITERIA),
            "success_criteria_count": len(EXPECTED_SUCCESS_CRITERIA),
            "stop_criteria_count": len(EXPECTED_STOP_CRITERIA),
            "maximum_additional_unique_public_metadata_documents": 5,
            "maximum_benchmark_payload_requests": 0,
            "maximum_provider_or_model_requests": 0,
            "maximum_retries": 0,
            "requires_separate_go": True,
        },
        "operation_attestation": {
            "measurement_mode": "bounded-process-attestation-and-static-capability-check",
            "runtime_network_instrumentation_used": False,
            "public_metadata_documents_consulted": 10,
            "benchmark_payload_downloads": 0,
            "benchmark_payload_bytes_opened": 0,
            "queries_decrypted": 0,
            "benchmark_search_api_requests": 0,
            "retrieval_requests": 0,
            "judge_requests": 0,
            "scores_computed": 0,
            "provider_requests": 0,
            "model_requests": 0,
            "external_tester_requests": 0,
            "secret_requests": 0,
            "publication_requests": 0,
        },
        "readiness": {
            "policy_lock_complete": True,
            "component_license_clearance_complete": False,
            "benchmark_comparability_complete": False,
            "candidate_suites_admitted": 0,
            "asset_acquisition_allowed": False,
            "evaluation_allowed": False,
            "publication_allowed": False,
            "v1_ready": False,
        },
        "governance": {
            "phase_11_8_10b_acquisition_authorized": False,
            "phase_11_9_authorized": False,
            "phase_12_authorized": False,
            "merge_allowed": False,
            "release_allowed": False,
            "superiority_claim_allowed": False,
            "pull_request_must_remain_draft": True,
            "distributions_must_remain_unpublished": True,
        },
    }
