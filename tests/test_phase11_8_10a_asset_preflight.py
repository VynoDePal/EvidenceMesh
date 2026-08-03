from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.phase11_8_10a_asset_preflight import (
    DEFAULT_MANIFEST_PATH,
    AssetLockError,
    build_reconnaissance_report,
    expected_object_records,
    load_and_validate_inventory,
    load_manifest,
    validate_inventory,
    validate_manifest,
)

ROOT = Path(__file__).parents[1]
INVENTORY_PATH = ROOT / "benchmarks/data/phase11_8_10a_object_inventory_v1.json"
MODULE_PATH = ROOT / "benchmarks/phase11_8_10a_asset_preflight.py"
COMMIT = "a" * 40


def _manifest() -> dict[str, Any]:
    return json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))


def _inventory() -> dict[str, Any]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _suite(manifest: dict[str, Any], suite_id: str) -> dict[str, Any]:
    return next(suite for suite in manifest["suites"] if suite["suite_id"] == suite_id)


def test_committed_manifest_and_inventory_form_a_complete_integrity_lock() -> None:
    manifest = load_manifest()
    summary = load_and_validate_inventory(INVENTORY_PATH, manifest)

    assert len(expected_object_records(manifest)) == 37
    assert summary["object_count"] == 37
    assert summary["total_content_bytes"] == 5_013_088_007
    assert summary["object_inventory_complete"] is True
    assert summary["metadata_lock_complete"] is True
    assert summary["component_license_clearance_complete"] is False
    assert summary["benchmark_comparability_complete"] is False
    assert summary["acquisition_eligible"] is False
    assert summary["evaluation_eligible"] is False


def test_report_is_aggregate_only_and_keeps_future_work_blocked() -> None:
    manifest = load_manifest()
    inventory = load_and_validate_inventory(INVENTORY_PATH, manifest)
    report = build_reconnaissance_report(
        manifest,
        methodology_commit_sha=COMMIT,
        inventory_summary=inventory,
    )

    assert report["outcome"] == "asset_integrity_lock_complete_policy_blocked"
    assert report["quality_decision"] == "no_go"
    assert report["real_external_score"] is False
    assert report["external_evaluation_status"] == "not_run"
    assert report["gate_summary"] == {"passed": 15, "failed": 0, "total": 15}
    assert report["readiness"]["acquisition_eligible"] is False
    assert report["readiness"]["evaluation_eligible"] is False
    assert report["traffic"] == {
        "official_asset_downloads": 0,
        "official_asset_bytes_opened": 0,
        "queries_decrypted": 0,
        "retrieval_or_answer_scores_computed": 0,
        "provider_calls": 0,
        "model_calls": 0,
        "search_api_calls": 0,
        "secret_reads": 0,
    }
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in (
        "http://",
        "https://",
        ".parquet",
        "query_id",
        "docid",
        "canary guid",
        "evidence_mesh_gemini_key",
        "evidence_mesh_tavily_key",
        str(ROOT).lower(),
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["phase_policy"].__setitem__(
                "official_asset_download_allowed", True
            ),
            "official_asset_download_allowed",
        ),
        (
            lambda value: _suite(value, "bright")["dataset_snapshots"][0].__setitem__(
                "revision", "3066d29"
            ),
            "dataset_revision",
        ),
        (
            lambda value: _suite(value, "bright")["dataset_snapshots"][0].__setitem__(
                "immutable_tree", "https://huggingface.co/datasets/xlangai/BRIGHT/tree/main"
            ),
            "full revision",
        ),
        (
            lambda value: _suite(value, "bright")["dataset_snapshots"][0][
                "declared_license"
            ].__setitem__("scope", "upstream-code-repository"),
            "code license",
        ),
        (
            lambda value: _suite(value, "bright")["dataset_snapshots"][0][
                "declared_license"
            ].__setitem__("underlying_third_party_rights_individually_verified", True),
            "third-party rights",
        ),
        (
            lambda value: _suite(value, "bright")["selection"]["tasks"].pop(),
            "12-task",
        ),
        (
            lambda value: _suite(value, "bright")["selection"].__setitem__(
                "included_configs", ["examples", "long_documents"]
            ),
            "configs",
        ),
        (
            lambda value: _suite(value, "browsecomp_plus")["selection"].__setitem__(
                "qrel_tracks", ["gold"]
            ),
            "qrel tracks",
        ),
        (
            lambda value: _suite(value, "browsecomp_plus")["code_authority"].__setitem__(
                "gold_qrel_path", "topics-qrels/qrel_gold.txt"
            ),
            "plural gold-qrel",
        ),
        (
            lambda value: value["metadata_importer_policy"].__setitem__(
                "git_blob_or_xet_descriptor_sha_is_content_sha", True
            ),
            "Xet descriptor",
        ),
        (
            lambda value: value["aggregate_reconnaissance"].__setitem__(
                "acquisition_eligible", True
            ),
            "acquisition",
        ),
    ],
)
def test_manifest_mutations_fail_closed(mutator: Any, message: str) -> None:
    manifest = _manifest()
    mutator(manifest)
    with pytest.raises(AssetLockError, match=message):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["objects"].append(copy.deepcopy(value["objects"][0])),
            "duplicate object",
        ),
        (
            lambda value: value["objects"][0].__setitem__("relative_path", "../escape.parquet"),
            "traversal",
        ),
        (
            lambda value: value["objects"][0].__setitem__("relative_path", "documents/*.parquet"),
            "glob",
        ),
        (
            lambda value: value["objects"][0].__setitem__("content_sha256", "A" * 64),
            "lowercase hex",
        ),
        (
            lambda value: value["objects"][0].__setitem__("content_bytes", 0),
            "positive",
        ),
        (
            lambda value: value["objects"][0].__setitem__("digest_kind", "xet-descriptor-sha256"),
            "Git LFS",
        ),
        (
            lambda value: value.__setitem__("content_downloaded", True),
            "must not download",
        ),
    ],
)
def test_inventory_mutations_fail_closed(mutator: Any, message: str) -> None:
    manifest = load_manifest()
    inventory = _inventory()
    mutator(inventory)
    with pytest.raises(AssetLockError, match=message):
        validate_inventory(manifest, inventory)


def test_missing_inventory_object_fails_closed() -> None:
    inventory = _inventory()
    inventory["objects"].pop()
    with pytest.raises(AssetLockError, match="complete required object set"):
        validate_inventory(load_manifest(), inventory)


def test_phase12_inventory_path_is_rejected_before_open(tmp_path: Path) -> None:
    forbidden = tmp_path / "phase12-secret.json"
    with pytest.raises(AssetLockError, match="Phase 12"):
        load_and_validate_inventory(forbidden, load_manifest())
    assert not forbidden.exists()


def test_module_has_no_network_process_provider_or_dynamic_code_imports() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert imported_roots.isdisjoint(
        {
            "aiohttp",
            "asyncio",
            "boto3",
            "datasets",
            "google",
            "huggingface_hub",
            "httpx",
            "mistralai",
            "openai",
            "os",
            "requests",
            "socket",
            "subprocess",
            "tavily",
            "urllib3",
        }
    )
    assert calls.isdisjoint(
        {"__import__", "compile", "eval", "exec", "getenv", "popen", "system", "urlopen"}
    )
