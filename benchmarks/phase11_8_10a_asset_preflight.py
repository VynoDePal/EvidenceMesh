"""Metadata-only preflight for Phase 11.8.10A external benchmark assets.

This module validates immutable upstream metadata and, optionally, an object
inventory supplied by a later acquisition phase.  It has deliberately no HTTP,
provider, model, search, authentication, decryption, corpus parsing, or scoring
capability.
"""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import urlsplit

MANIFEST_SCHEMA = "evidencemesh.phase11_8_10a.asset-reconnaissance.v1"
INVENTORY_SCHEMA = "evidencemesh.phase11_8_10a.content-object-inventory.v1"
DEFAULT_MANIFEST_PATH = Path(__file__).parent / "data/phase11_8_10a_asset_locks_v1.json"
EXPECTED_SUITES = ("bright", "browsecomp_plus")
EXPECTED_BRIGHT_TASKS = (
    "biology",
    "earth_science",
    "economics",
    "pony",
    "psychology",
    "robotics",
    "stackoverflow",
    "sustainable_living",
    "aops",
    "leetcode",
    "theoremqa_theorems",
    "theoremqa_questions",
)
EXPECTED_DOWNLOAD_BYTES = 5_013_088_007
EXPECTED_DECODED_BYTES = 7_205_462_832
EXPECTED_OBJECT_COUNT = 37
MAX_MANIFEST_BYTES = 256 * 1024
PHASE12_MARKERS = ("phase12", "phase_12", "phase-12")
FORBIDDEN_PUBLIC_MARKERS = (
    "evidence_mesh_gemini_key",
    "evidence_mesh_tavily_key",
    "gemini_api_key",
    "tavily_api_key",
    "authorization: bearer",
)


class AssetLockError(ValueError):
    """Raised when reconnaissance metadata violates the locked contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssetLockError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _array(value: object, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label} must be a JSON array")
    return cast(list[Any], value)


def _string(value: object, label: str) -> str:
    _require(isinstance(value, str), f"{label} must be a string")
    normalized = cast(str, value).strip()
    _require(bool(normalized), f"{label} must not be empty")
    return normalized


def _positive_integer(value: object, label: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    normalized = cast(int, value)
    _require(normalized > 0, f"{label} must be positive")
    return normalized


def _lower_hex(value: object, length: int, label: str) -> str:
    text = _string(value, label)
    _require(len(text) == length, f"{label} must contain exactly {length} lowercase hex characters")
    _require(
        all(character in "0123456789abcdef" for character in text), f"{label} is not lowercase hex"
    )
    return text


def canonical_json_bytes(value: object) -> bytes:
    """Return the single canonical JSON encoding used by this phase."""

    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _reject_phase12_path(path: Path) -> None:
    lowered = str(path).replace("\\", "/").lower()
    _require(
        not any(marker in lowered for marker in PHASE12_MARKERS),
        "Phase 12 paths are outside the Phase 11.8.10A authority boundary",
    )


def _read_regular_json(path: Path, *, max_bytes: int, label: str) -> dict[str, Any]:
    _reject_phase12_path(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AssetLockError(f"cannot stat {label}") from exc
    _require(stat.S_ISREG(metadata.st_mode), f"{label} must be a regular file")
    _require(not path.is_symlink(), f"{label} must not be a symlink")
    _require(metadata.st_size <= max_bytes, f"{label} exceeds its byte limit")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise AssetLockError(f"cannot read {label}") from exc
    _require(len(payload) == metadata.st_size, f"{label} changed while it was read")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetLockError(f"{label} is not valid UTF-8 JSON") from exc
    return _object(decoded, label)


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    manifest = _read_regular_json(path, max_bytes=MAX_MANIFEST_BYTES, label="asset manifest")
    validate_manifest(manifest)
    return manifest


def _validate_https_url(value: object, *, label: str, host: str) -> str:
    url = _string(value, label)
    parsed = urlsplit(url)
    _require(parsed.scheme == "https", f"{label} must use HTTPS")
    _require(parsed.hostname == host, f"{label} uses a non-allowlisted host")
    _require(
        parsed.username is None and parsed.password is None, f"{label} must not embed credentials"
    )
    _require(
        not parsed.query and not parsed.fragment, f"{label} must not contain a query or fragment"
    )
    return url


def _validate_relative_path(value: object, label: str) -> str:
    path = _string(value, label)
    pure = PurePosixPath(path)
    _require(not pure.is_absolute(), f"{label} must be relative")
    _require(".." not in pure.parts and "." not in pure.parts, f"{label} contains traversal")
    _require("*" not in path and "?" not in path and "[" not in path, f"{label} contains a glob")
    _require("\\" not in path, f"{label} must use POSIX separators")
    return path


def _expanded_required_objects(suite: Mapping[str, Any]) -> list[dict[str, Any]]:
    suite_id = _string(suite.get("suite_id"), "suite_id")
    records: list[dict[str, Any]] = []
    required_groups = _array(suite.get("required_objects"), f"{suite_id}.required_objects")
    for index, raw_group in enumerate(required_groups):
        group = _object(raw_group, f"{suite_id}.required_objects[{index}]")
        snapshot_id = _string(group.get("snapshot_id"), f"{suite_id}.snapshot_id")
        template = _string(group.get("path_template"), f"{suite_id}.path_template")
        media_type = _string(group.get("media_type"), f"{suite_id}.media_type")
        roles = tuple(
            _string(role, f"{suite_id}.roles")
            for role in _array(group.get("roles"), f"{suite_id}.roles")
        )
        _require(len(set(roles)) == len(roles), f"{suite_id} has duplicate roles")
        if suite_id == "bright":
            _require(
                template.count("{task}") == 1, "BRIGHT path template must contain one task token"
            )
            paths = [template.format(task=task) for task in EXPECTED_BRIGHT_TASKS]
        else:
            shard_range = _array(group.get("shard_range"), f"{suite_id}.shard_range")
            _require(len(shard_range) == 2, f"{suite_id}.shard_range must contain two integers")
            start, end = shard_range
            _require(
                isinstance(start, int)
                and not isinstance(start, bool)
                and isinstance(end, int)
                and not isinstance(end, bool)
                and 0 <= start <= end,
                f"{suite_id}.shard_range is invalid",
            )
            try:
                paths = [template.format(shard=shard) for shard in range(start, end + 1)]
            except (IndexError, KeyError, ValueError) as exc:
                raise AssetLockError(f"{suite_id} has an invalid shard template") from exc
        expected_count = _positive_integer(
            group.get("expanded_object_count"), f"{suite_id}.expanded_object_count"
        )
        _require(
            len(paths) == expected_count, f"{suite_id} object count does not match its template"
        )
        _require(
            group.get("content_sha256_inventory_complete") is True,
            f"{suite_id} must bind the committed SHA-256 inventory",
        )
        _require(
            group.get("exact_content_bytes_inventory_complete") is True,
            f"{suite_id} must bind the committed exact byte inventory",
        )
        for path in paths:
            records.append(
                {
                    "suite_id": suite_id,
                    "snapshot_id": snapshot_id,
                    "relative_path": _validate_relative_path(path, f"{suite_id}.expanded_path"),
                    "roles": list(roles),
                    "media_type": media_type,
                }
            )
    return records


def expected_object_records(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_suite in _array(manifest.get("suites"), "suites"):
        records.extend(_expanded_required_objects(_object(raw_suite, "suite")))
    return sorted(
        records,
        key=lambda item: (item["suite_id"], item["snapshot_id"], item["relative_path"]),
    )


def _validate_code_authority(suite: Mapping[str, Any]) -> None:
    suite_id = _string(suite.get("suite_id"), "suite_id")
    code = _object(suite.get("code_authority"), f"{suite_id}.code_authority")
    _validate_https_url(
        code.get("repository"), label=f"{suite_id}.code_repository", host="github.com"
    )
    _lower_hex(code.get("revision"), 40, f"{suite_id}.code_revision")
    license_record = _object(code.get("license"), f"{suite_id}.code_license")
    _validate_relative_path(license_record.get("path"), f"{suite_id}.code_license.path")
    _lower_hex(license_record.get("git_blob_sha1"), 40, f"{suite_id}.code_license.blob")
    _require(
        license_record.get("scope") == "upstream-code-repository",
        f"{suite_id} code license scope drifted",
    )


def _validate_dataset_snapshots(suite: Mapping[str, Any]) -> set[str]:
    suite_id = _string(suite.get("suite_id"), "suite_id")
    snapshot_ids: set[str] = set()
    snapshots = _array(suite.get("dataset_snapshots"), f"{suite_id}.dataset_snapshots")
    _require(bool(snapshots), f"{suite_id} must pin at least one dataset snapshot")
    for index, raw_snapshot in enumerate(snapshots):
        snapshot = _object(raw_snapshot, f"{suite_id}.dataset_snapshots[{index}]")
        snapshot_id = _string(snapshot.get("snapshot_id"), f"{suite_id}.snapshot_id")
        _require(snapshot_id not in snapshot_ids, f"{suite_id} has a duplicate snapshot id")
        snapshot_ids.add(snapshot_id)
        repository = _validate_https_url(
            snapshot.get("repository"),
            label=f"{suite_id}.dataset_repository",
            host="huggingface.co",
        )
        revision = _lower_hex(snapshot.get("revision"), 40, f"{suite_id}.dataset_revision")
        immutable_tree = _validate_https_url(
            snapshot.get("immutable_tree"),
            label=f"{suite_id}.immutable_tree",
            host="huggingface.co",
        )
        _require(
            repository in immutable_tree, f"{suite_id} immutable tree does not match its repository"
        )
        _require(
            revision in immutable_tree,
            f"{suite_id} immutable tree does not contain its full revision",
        )
        _validate_relative_path(snapshot.get("metadata_path"), f"{suite_id}.metadata_path")
        declared = _object(snapshot.get("declared_license"), f"{suite_id}.declared_license")
        _require(
            declared.get("scope") == "upstream-dataset-card-declaration",
            f"{suite_id} must not use a code license as the dataset license",
        )
        _require(
            declared.get("declaration_resolved") is True,
            f"{suite_id} license declaration is unresolved",
        )
        _require(
            declared.get("underlying_third_party_rights_individually_verified") is False,
            f"{suite_id} must not overclaim third-party rights review",
        )
        _require(
            declared.get("redistribution_policy") == "external-cache-only-do-not-republish",
            f"{suite_id} redistribution policy must remain fail-closed",
        )
        _require(
            declared.get("evidence_revision") == revision,
            f"{suite_id} license evidence is not pinned to the dataset snapshot",
        )
    return snapshot_ids


def _validate_suite_specific(suite: Mapping[str, Any]) -> None:
    suite_id = _string(suite.get("suite_id"), "suite_id")
    selection = _object(suite.get("selection"), f"{suite_id}.selection")
    if suite_id == "bright":
        tasks = _array(selection.get("tasks"), "bright.tasks")
        task_ids = tuple(
            _string(_object(task, "bright.task").get("task_id"), "task_id") for task in tasks
        )
        _require(task_ids == EXPECTED_BRIGHT_TASKS, "BRIGHT must contain the frozen 12-task order")
        _require(
            selection.get("included_configs") == ["examples", "documents"], "BRIGHT configs drifted"
        )
        _require(
            "long_documents" in selection.get("excluded_configs", []),
            "BRIGHT long documents must be excluded",
        )
        _require(
            selection.get("aggregation") == "unweighted-macro-average-of-12-task-ndcg-at-10",
            "BRIGHT aggregation drifted",
        )
        query_total = sum(
            _positive_integer(_object(task, "task").get("query_records"), "query_records")
            for task in tasks
        )
        document_total = sum(
            _positive_integer(_object(task, "task").get("document_records"), "document_records")
            for task in tasks
        )
        totals = _object(suite.get("upstream_declared_totals"), "bright.totals")
        _require(query_total == totals.get("query_records") == 1384, "BRIGHT query total drifted")
        _require(
            document_total == totals.get("document_records") == 1_333_166,
            "BRIGHT document total drifted",
        )
    else:
        _require(
            selection.get("qrel_tracks") == ["evidence", "gold"], "BrowseComp qrel tracks drifted"
        )
        _require(
            selection.get("qrel_tracks_reported_separately") is True,
            "BrowseComp qrels must remain separate",
        )
        _require(
            selection.get("decryption_in_phase_11_8_10a") is False,
            "BrowseComp decryption is forbidden",
        )
        _require(
            selection.get("prebuilt_indexes_in_scope") is False,
            "BrowseComp prebuilt indexes are out of scope",
        )
        code = _object(suite.get("code_authority"), "browsecomp.code_authority")
        _require(
            code.get("gold_qrel_repository_path_present") is True,
            "the official gold-qrel file must be present",
        )
        _require(
            code.get("gold_qrel_path") == "topics-qrels/qrel_golds.txt",
            "the official plural gold-qrel path drifted",
        )


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the committed metadata-only reconnaissance manifest."""

    _require(manifest.get("schema_version") == MANIFEST_SCHEMA, "unsupported asset manifest schema")
    _require(
        manifest.get("purpose") == "metadata-only-non-scoring-external-asset-reconnaissance",
        "manifest purpose drifted",
    )
    policy = _object(manifest.get("phase_policy"), "phase_policy")
    _require(
        tuple(policy.get("suite_ids", [])) == EXPECTED_SUITES, "phase policy suite set drifted"
    )
    for forbidden_flag in (
        "official_asset_download_allowed",
        "official_asset_open_or_parse_allowed",
        "query_decryption_allowed",
        "retrieval_or_answer_scoring_allowed",
        "provider_search_or_model_calls_allowed",
        "secret_access_allowed",
        "phase12_access_allowed",
        "asset_bytes_may_be_committed_or_uploaded",
        "real_external_score",
        "quality_claim_allowed",
    ):
        _require(policy.get(forbidden_flag) is False, f"{forbidden_flag} must remain false")
    _require(
        policy.get("next_phase_requires_separate_go") is True, "the next phase requires separate GO"
    )

    importer = _object(manifest.get("metadata_importer_policy"), "metadata_importer_policy")
    _require(importer.get("allowed_hosts") == ["huggingface.co"], "metadata host allowlist drifted")
    _require(importer.get("credentials_allowed") is False, "credentials are forbidden")
    _require(importer.get("signed_or_query_urls_allowed") is False, "signed URLs are forbidden")
    _require(importer.get("moving_revisions_allowed") is False, "moving revisions are forbidden")
    _require(
        importer.get("content_sha256_required") is True, "content SHA-256 must remain required"
    )
    _require(
        importer.get("exact_content_bytes_required") is True,
        "exact object bytes must remain required",
    )
    _require(
        importer.get("git_lfs_oid_sha256_is_content_sha") is True,
        "Git LFS content oids must remain admissible",
    )
    _require(
        importer.get("git_blob_or_xet_descriptor_sha_is_content_sha") is False,
        "Git blob and Xet descriptor hashes must not be treated as content hashes",
    )
    committed_inventory = _object(importer.get("committed_inventory"), "committed_inventory")
    _validate_relative_path(committed_inventory.get("path"), "committed_inventory.path")
    _lower_hex(committed_inventory.get("sha256"), 64, "committed_inventory.sha256")

    predecessor = _object(manifest.get("predecessor"), "predecessor")
    _lower_hex(predecessor.get("remote_head_commit"), 40, "predecessor.remote_head_commit")
    for key in ("protocol", "external_registry", "result"):
        _lower_hex(
            _object(predecessor.get(key), f"predecessor.{key}").get("sha256"), 64, f"{key}.sha256"
        )
    _require(
        _object(predecessor.get("result"), "predecessor.result").get("real_external_score")
        is False,
        "predecessor score boundary drifted",
    )

    suites = [_object(suite, "suite") for suite in _array(manifest.get("suites"), "suites")]
    suite_ids = tuple(_string(suite.get("suite_id"), "suite_id") for suite in suites)
    _require(suite_ids == EXPECTED_SUITES, "manifest must contain exactly the two frozen suites")
    for suite in suites:
        _validate_code_authority(suite)
        snapshot_ids = _validate_dataset_snapshots(suite)
        _validate_suite_specific(suite)
        required = _expanded_required_objects(suite)
        _require(
            all(record["snapshot_id"] in snapshot_ids for record in required),
            "object references an unknown snapshot",
        )
        readiness = _object(suite.get("readiness"), f"{suite['suite_id']}.readiness")
        _require(
            readiness.get("per_object_content_sha256_complete") is True,
            "SHA inventory must be complete",
        )
        _require(
            readiness.get("per_object_exact_content_bytes_complete") is True,
            "byte inventory must be complete",
        )
        _require(
            readiness.get("component_license_clearance_complete") is False,
            "component license clearance must remain unresolved",
        )
        _require(readiness.get("local_assets_admitted") is False, "local assets were not admitted")
        _require(
            readiness.get("evaluation_eligible") is False, "external evaluation must remain blocked"
        )

    records = expected_object_records(manifest)
    keys = [
        (record["suite_id"], record["snapshot_id"], record["relative_path"]) for record in records
    ]
    _require(
        len(records) == len(set(keys)) == EXPECTED_OBJECT_COUNT,
        "required object set must contain 37 unique paths",
    )
    aggregate = _object(manifest.get("aggregate_reconnaissance"), "aggregate_reconnaissance")
    _require(
        aggregate.get("required_object_count") == EXPECTED_OBJECT_COUNT,
        "aggregate object count drifted",
    )
    _require(
        aggregate.get("expected_download_bytes") == EXPECTED_DOWNLOAD_BYTES,
        "aggregate download bytes drifted",
    )
    _require(
        aggregate.get("expected_decoded_dataset_bytes") == EXPECTED_DECODED_BYTES,
        "aggregate decoded bytes drifted",
    )
    _require(
        aggregate.get("object_inventory_complete") is True, "object inventory must be complete"
    )
    _require(
        aggregate.get("metadata_lock_complete") is True, "metadata integrity lock must be complete"
    )
    _require(
        aggregate.get("component_license_clearance_complete") is False,
        "component license clearance must remain unresolved",
    )
    _require(
        aggregate.get("benchmark_comparability_complete") is False,
        "benchmark comparability must remain unresolved",
    )
    _require(aggregate.get("acquisition_eligible") is False, "acquisition must remain blocked")
    _require(aggregate.get("evaluation_eligible") is False, "evaluation must remain blocked")

    public_text = json.dumps(manifest, ensure_ascii=False).lower()
    _require(
        not any(marker in public_text for marker in FORBIDDEN_PUBLIC_MARKERS),
        "manifest contains a secret marker",
    )


def validate_inventory(manifest: Mapping[str, Any], inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a metadata inventory without opening any referenced asset."""

    validate_manifest(manifest)
    _require(
        inventory.get("schema_version") == INVENTORY_SCHEMA, "unsupported object inventory schema"
    )
    _require(
        inventory.get("content_opened") is False, "metadata import must not open asset content"
    )
    _require(
        inventory.get("content_downloaded") is False,
        "metadata import must not download asset content",
    )
    _require(
        inventory.get("content_scored") is False, "metadata import must not score asset content"
    )
    expected = expected_object_records(manifest)
    expected_by_key = {
        (record["suite_id"], record["snapshot_id"], record["relative_path"]): record
        for record in expected
    }
    imported_records = _array(inventory.get("objects"), "inventory.objects")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    suite_bytes = dict.fromkeys(EXPECTED_SUITES, 0)
    for index, raw_record in enumerate(imported_records):
        record = _object(raw_record, f"inventory.objects[{index}]")
        suite_id = _string(record.get("suite_id"), "inventory.suite_id")
        snapshot_id = _string(record.get("snapshot_id"), "inventory.snapshot_id")
        relative_path = _validate_relative_path(
            record.get("relative_path"), "inventory.relative_path"
        )
        key = (suite_id, snapshot_id, relative_path)
        _require(key in expected_by_key, "inventory contains an undeclared object")
        _require(key not in seen, "inventory contains a duplicate object")
        seen.add(key)
        content_sha256 = _lower_hex(record.get("content_sha256"), 64, "inventory.content_sha256")
        content_bytes = _positive_integer(record.get("content_bytes"), "inventory.content_bytes")
        media_type = _string(record.get("media_type"), "inventory.media_type")
        _require(media_type == expected_by_key[key]["media_type"], "inventory media type drifted")
        _require(
            record.get("digest_kind") in {"full-content-sha256", "git-lfs-oid-sha256"},
            "only full-content or Git LFS content SHA-256 digests are accepted",
        )
        suite_bytes[suite_id] += content_bytes
        normalized.append(
            {
                "suite_id": suite_id,
                "snapshot_id": snapshot_id,
                "relative_path": relative_path,
                "content_sha256": content_sha256,
                "content_bytes": content_bytes,
                "media_type": media_type,
                "digest_kind": record["digest_kind"],
            }
        )
    _require(
        seen == set(expected_by_key), "inventory does not cover the complete required object set"
    )

    suites = {_string(suite.get("suite_id"), "suite_id"): suite for suite in manifest["suites"]}
    for suite_id, total_bytes in suite_bytes.items():
        declared = _object(suites[suite_id].get("upstream_declared_totals"), f"{suite_id}.totals")
        _require(
            total_bytes == declared.get("download_bytes"),
            f"{suite_id} inventory byte total drifted",
        )
    normalized.sort(key=lambda item: (item["suite_id"], item["snapshot_id"], item["relative_path"]))
    return {
        "schema_version": INVENTORY_SCHEMA,
        "object_count": len(normalized),
        "total_content_bytes": sum(record["content_bytes"] for record in normalized),
        "suite_content_bytes": suite_bytes,
        "inventory_sha256": canonical_sha256(normalized),
        "object_inventory_complete": True,
        "metadata_lock_complete": True,
        "component_license_clearance_complete": False,
        "benchmark_comparability_complete": False,
        "acquisition_eligible": False,
        "local_assets_admitted": False,
        "evaluation_eligible": False,
    }


def load_and_validate_inventory(path: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    importer_policy = _object(manifest.get("metadata_importer_policy"), "metadata_importer_policy")
    max_bytes = _positive_integer(
        importer_policy.get("maximum_inventory_bytes"), "maximum_inventory_bytes"
    )
    inventory = _read_regular_json(path, max_bytes=max_bytes, label="object inventory")
    return validate_inventory(manifest, inventory)


def build_reconnaissance_report(
    manifest: Mapping[str, Any],
    *,
    methodology_commit_sha: str,
    inventory_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the aggregate-only deterministic Phase 11.8.10A report."""

    validate_manifest(manifest)
    commit_sha = _lower_hex(methodology_commit_sha, 40, "methodology_commit_sha")
    records = expected_object_records(manifest)
    manifest_sha = canonical_sha256(manifest)
    path_set_sha = canonical_sha256(
        [
            {
                "suite_id": record["suite_id"],
                "snapshot_id": record["snapshot_id"],
                "relative_path": record["relative_path"],
            }
            for record in records
        ]
    )
    inventory_complete = bool(
        inventory_summary and inventory_summary.get("object_inventory_complete")
    )
    gates = [
        ("predecessor_authority_locked", True),
        ("exact_two_suite_scope", True),
        ("immutable_code_and_dataset_revisions", True),
        ("dataset_license_declarations_pinned", True),
        ("bright_12_task_role_map", True),
        ("browsecomp_separate_evidence_and_gold_roles", True),
        ("upstream_counts_and_aggregate_volume_recorded", True),
        ("required_object_path_set_complete", True),
        ("per_object_content_sha256_complete", inventory_complete),
        ("per_object_exact_content_bytes_complete", inventory_complete),
        ("metadata_only_no_auth_import_contract", True),
        ("zero_corpus_download_open_decrypt_or_score", True),
        ("zero_provider_model_search_or_secret_access", True),
        ("aggregate_only_privacy_boundary", True),
        ("governance_no_go_and_next_phase_block", True),
    ]
    gate_records = [
        {"gate": index, "gate_id": gate_id, "passed": passed}
        for index, (gate_id, passed) in enumerate(gates, start=1)
    ]
    passed = sum(1 for gate in gate_records if gate["passed"])
    failed = len(gate_records) - passed
    return {
        "schema_version": "evidencemesh.phase11_8_10a.asset-reconnaissance-result.v1",
        "phase": "11.8.10A",
        "generated_on": manifest["captured_on"],
        "methodology_commit_sha": commit_sha,
        "mode": "metadata-only-non-scoring",
        "outcome": (
            "asset_integrity_lock_complete_policy_blocked"
            if inventory_complete
            else "asset_metadata_lock_incomplete"
        ),
        "phase_status": "completed_with_blockers",
        "quality_decision": "no_go",
        "real_external_score": False,
        "external_evaluation_status": "not_run",
        "manifest_sha256": manifest_sha,
        "required_path_set_sha256": path_set_sha,
        "suite_count": len(EXPECTED_SUITES),
        "required_object_count": len(records),
        "expected_download_bytes": EXPECTED_DOWNLOAD_BYTES,
        "expected_decoded_dataset_bytes": EXPECTED_DECODED_BYTES,
        "recommended_free_disk_bytes_for_future_import": manifest["aggregate_reconnaissance"][
            "recommended_free_disk_bytes_for_future_import"
        ],
        "license_declarations": {
            "bright": "CC-BY-4.0",
            "browsecomp_plus": "MIT",
            "underlying_third_party_rights_individually_verified": False,
            "raw_asset_redistribution_allowed": False,
        },
        "readiness": {
            "object_inventory_complete": inventory_complete,
            "metadata_lock_complete": inventory_complete,
            "component_license_clearance_complete": False,
            "benchmark_comparability_complete": False,
            "acquisition_eligible": False,
            "local_assets_admitted": False,
            "evaluation_eligible": False,
            "next_phase_requires_separate_go": True,
        },
        "gates": gate_records,
        "gate_summary": {"passed": passed, "failed": failed, "total": len(gate_records)},
        "blocking_findings": (
            [
                "component_license_clearance_unresolved_bright",
                "component_license_clearance_unresolved_browsecomp_plus",
                "bright_leaderboard_revision_equivalence_unresolved",
                "bright_upstream_evaluator_version_unpinned",
            ]
            if inventory_complete
            else [
                "authoritative_per_object_content_sha256_missing",
                "authoritative_per_object_exact_content_bytes_missing",
                "component_license_clearance_unresolved_bright",
                "component_license_clearance_unresolved_browsecomp_plus",
            ]
        ),
        "traffic": {
            "official_asset_downloads": 0,
            "official_asset_bytes_opened": 0,
            "queries_decrypted": 0,
            "retrieval_or_answer_scores_computed": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "search_api_calls": 0,
            "secret_reads": 0,
        },
        "governance": {
            "pull_request_must_remain_draft": True,
            "merge_allowed": False,
            "release_allowed": False,
            "default_promotion_allowed": False,
            "superiority_claim_allowed": False,
            "phase_11_8_10b_authorized": False,
            "phase_11_9_authorized": False,
            "phase12_accesses": 0,
        },
    }
