from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks import phase11_8_9_external_eval as external
from benchmarks.phase11_8_9_external_eval import (
    ConformanceError,
    compute_retrieval_metrics,
    evaluate_compact_case,
    evaluate_fixture_file,
    evaluate_local_bundle,
    load_registry,
    validate_registry,
)

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "benchmarks/phase11_8_9_external_eval.py"
REGISTRY = ROOT / "benchmarks/data/phase11_8_9_external_benchmarks_v1.json"
FIXTURES = ROOT / "benchmarks/data/phase11_8_9_external_eval_fixtures_v1.json"

EXPECTED_METRIC_KEYS = {
    "recall_at_5",
    "recall_at_10",
    "recall_at_20",
    "recall_at_100",
    "recall_at_1000",
    "ndcg_at_5",
    "ndcg_at_10",
    "ndcg_at_20",
}


def _fixture_data() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def _suite(benchmark_id: str) -> dict[str, Any]:
    fixture = _fixture_data()
    return copy.deepcopy(
        next(
            case["suite_manifest"]
            for case in fixture["cases"]
            if case["suite_manifest"]["benchmark_id"] == benchmark_id
        )
    )


def _write(path: Path, content: str) -> dict[str, Any]:
    path.write_text(content, encoding="utf-8")
    return {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "byte_length": path.stat().st_size,
    }


def _write_manifest(
    bundle: Path,
    suite: dict[str, Any],
    files: dict[str, dict[str, Any]],
    *,
    counts: dict[str, int] | None = None,
) -> None:
    manifest = {
        "schema_version": "evidencemesh.phase11_8_9.local-bundle.v1",
        "suite_manifest": suite,
        "policy_id": "synthetic-local-bundle-strict-v1",
        "counts": counts
        or {
            "queries": 1,
            "corpus_documents": 2,
            "run_queries": 1,
            "run_entries": 2,
            "qrel_queries": 1,
            "qrel_entries": 2,
            "positive_qrels": 1,
        },
        "files": files,
    }
    (bundle / "bundle_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def _make_json_bundle(tmp_path: Path, name: str = "bundle") -> Path:
    bundle = tmp_path / name
    bundle.mkdir()
    queries = _write(bundle / "queries.json", json.dumps({"q": "Synthetic local query"}))
    corpus = _write(
        bundle / "corpus.json",
        json.dumps(
            [
                {
                    "docid": "d1",
                    "title": "Relevant",
                    "text": "Synthetic relevant text.",
                    "url": "https://synthetic.invalid/private-input",
                },
                {"docid": "d2", "title": "Distractor", "text": "Synthetic distractor."},
            ]
        ),
    )
    run = _write(bundle / "run.json", json.dumps({"q": {"d1": 2.0, "d2": 1.0}}))
    qrels = _write(bundle / "qrels.json", json.dumps({"q": {"d1": 1, "d2": 0}}))
    _write_manifest(
        bundle,
        _suite("browsecomp_plus"),
        {
            "queries": {**queries, "format": "json"},
            "corpus": {**corpus, "format": "json"},
            "run": {**run, "format": "json"},
            "qrels": {**qrels, "format": "json"},
        },
    )
    return bundle


def _make_trec_bundle(
    tmp_path: Path,
    name: str,
    *,
    run_iteration: str = "Q0",
    qrels_iteration: str = "Q0",
) -> Path:
    bundle = tmp_path / name
    bundle.mkdir()
    queries = _write(bundle / "queries.tsv", "q\tSynthetic local query\n")
    corpus = _write(
        bundle / "corpus.json",
        json.dumps([{"docid": "d1", "text": "Relevant"}, {"docid": "d2", "text": "Other"}]),
    )
    run = _write(
        bundle / "run.trec",
        f"q {run_iteration} d1 1 2.0 synthetic\nq {run_iteration} d2 2 1.0 synthetic\n",
    )
    qrels = _write(
        bundle / "qrels.trec",
        f"q {qrels_iteration} d1 1\nq {qrels_iteration} d2 0\n",
    )
    _write_manifest(
        bundle,
        _suite("browsecomp_plus"),
        {
            "queries": {**queries, "format": "tsv"},
            "corpus": {**corpus, "format": "json"},
            "run": {**run, "format": "trec"},
            "qrels": {**qrels, "format": "trec"},
        },
    )
    return bundle


def _manifest(bundle: Path) -> dict[str, Any]:
    return json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))


def _replace_manifest(bundle: Path, manifest: dict[str, Any]) -> None:
    (bundle / "bundle_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _refresh_descriptor(bundle: Path, role: str, path: Path) -> None:
    manifest = _manifest(bundle)
    manifest["files"][role].update(
        {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "byte_length": path.stat().st_size,
        }
    )
    _replace_manifest(bundle, manifest)


def test_registry_has_exact_authoritative_pins_and_fails_closed_on_asset_licenses() -> None:
    registry = load_registry()
    entries = {entry["benchmark_id"]: entry for entry in registry["benchmarks"]}
    assert entries["bright"]["repository_revision"] == ("d99e8391d967d4c2b3a74732530d2309e2fc92b6")
    assert entries["bright"]["repository_license_file"] == {
        "spdx_id": "CC-BY-4.0",
        "path": "LICENSE",
        "git_blob_sha1": "2f244ac814036ecd9ba9f69782e89ce6b1dca9eb",
        "scope": "repository-license-file-only",
    }
    assert entries["browsecomp_plus"]["repository_revision"] == (
        "046949032b0328319cc9a02663a759ec601d9402"
    )
    assert entries["browsecomp_plus"]["repository_license_file"] == {
        "spdx_id": "MIT",
        "path": "LICENSE",
        "git_blob_sha1": "1eeb9f2ab7b823eef913d01626ca28adf6422fba",
        "scope": "repository-software-only",
    }
    assert all(
        entry["benchmark_asset_license"]["status"] == "unresolved"
        and entry["benchmark_asset_license"]["real_external_evaluation_allowed"] is False
        and entry["benchmark_asset_license"]["spdx_id"] is None
        for entry in entries.values()
    )
    assert registry["publication_policy"]["real_external_scores_supported_in_v1"] is False
    assert registry["adapter_policies"] == {
        "corpus_document_id_aliases": ["doc_id", "docid", "_id", "id"],
        "corpus_url_field": "accepted-input-never-published",
        "trec_qrels_iteration": "Q0",
        "run_order": "score-desc-docid-asc-rank-must-match",
        "ndcg_gain": "trec-linear-relevance",
        "empty_run_per_query": "allowed-and-scored-zero",
    }
    official = registry["planned_official_evaluation_policy"]
    assert official["available_in_v1"] is False
    assert official["bright"]["required_domain_count"] == 12
    assert official["bright"]["excluded_ids_lock_required"] is True
    assert official["browsecomp_plus"]["required_qrels_views"] == ["evidence", "gold"]


def test_fixture_conformance_is_aggregate_only_and_never_an_external_score() -> None:
    result = evaluate_fixture_file()
    assert result["evaluation_status"] == "evaluated"
    assert result["all_expected_metrics_matched"] is True
    assert result["benchmark_count"] == 2
    assert result["real_external_scores_present"] is False
    assert result["external_quality_claim_allowed"] is False
    assert result["aggregate_only"] is True
    for benchmark in result["benchmarks"].values():
        assert benchmark["evaluation_scope"] == "integration_conformance_synthetic"
        assert benchmark["real_external_score"] is False
        assert benchmark["external_quality_claim_allowed"] is False
        assert set(benchmark["metrics"]) == EXPECTED_METRIC_KEYS
    rendered = json.dumps(result, sort_keys=True)
    assert "synthetic-" not in rendered
    assert "http://" not in rendered
    assert "https://" not in rendered
    assert "Which " not in rendered
    assert "Find " not in rendered


def test_metrics_are_deterministic_for_score_mappings_and_graded_qrels() -> None:
    run_a = {"q": {"d1": 1.0, "d0": 2.0, "d2": 0.5}}
    run_b = {"q": {"d2": 0.5, "d0": 2.0, "d1": 1.0}}
    qrels = {"q": {"d1": 3, "d2": 1, "d0": 0}}
    metrics = compute_retrieval_metrics(run_a, qrels)
    assert metrics == compute_retrieval_metrics(run_b, qrels)
    assert set(metrics) == EXPECTED_METRIC_KEYS
    assert metrics["recall_at_5"] == 1.0
    assert metrics["ndcg_at_5"] == pytest.approx(0.659001804802, abs=1e-12)
    assert metrics["ndcg_at_5"] == metrics["ndcg_at_10"] == metrics["ndcg_at_20"]


def test_ndcg_uses_linear_trec_gains_and_empty_run_scores_zero() -> None:
    metrics = compute_retrieval_metrics(
        {
            "q": [
                {"docid": "low", "rank": 1, "score": 2.0},
                {"docid": "high", "rank": 2, "score": 1.0},
            ]
        },
        {"q": {"high": 3, "low": 1}},
    )
    assert metrics["ndcg_at_5"] == pytest.approx(0.796707580991, abs=1e-12)
    assert metrics["ndcg_at_5"] != pytest.approx(0.709809741397, abs=1e-12)

    empty = compute_retrieval_metrics({"q": []}, {"q": {"relevant": 1}})
    assert set(empty.values()) == {0.0}


def test_score_order_ties_and_declared_ranks_are_deterministic() -> None:
    qrels = {"q": {"a": 1, "b": 0}}
    tied_a = {"q": {"b": 1.0, "a": 1.0}}
    tied_b = {"q": {"a": 1.0, "b": 1.0}}
    assert compute_retrieval_metrics(tied_a, qrels) == compute_retrieval_metrics(tied_b, qrels)
    assert compute_retrieval_metrics(tied_a, qrels)["ndcg_at_5"] == 1.0

    inconsistent = {
        "q": [
            {"docid": "a", "rank": 2, "score": 2.0},
            {"docid": "b", "rank": 1, "score": 1.0},
        ]
    }
    with pytest.raises(ConformanceError, match="descending score"):
        compute_retrieval_metrics(inconsistent, qrels)


def test_fixture_oracle_mismatch_is_a_failed_status(tmp_path: Path) -> None:
    fixture = _fixture_data()
    fixture["cases"][0]["expected_metrics"]["ndcg_at_10"] = 0.0
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    result = evaluate_fixture_file(path)
    assert result["evaluation_status"] == "failed"
    assert result["all_expected_metrics_matched"] is False
    assert result["real_external_scores_present"] is False


@pytest.mark.parametrize("field", ["repository_revision", "official_repository"])
def test_suite_pins_are_strict(field: str) -> None:
    case = copy.deepcopy(_fixture_data()["cases"][0])
    case["suite_manifest"][field] = "invalid"
    with pytest.raises(ConformanceError):
        evaluate_compact_case(case)


def test_repository_license_and_input_schema_are_strict() -> None:
    bad_license = copy.deepcopy(_fixture_data()["cases"][0])
    bad_license["suite_manifest"]["repository_license_file"]["spdx_id"] = "MIT"
    with pytest.raises(ConformanceError, match="repository-license lock"):
        evaluate_compact_case(bad_license)

    duplicate = copy.deepcopy(_fixture_data()["cases"][0])
    duplicate["queries"].append(copy.deepcopy(duplicate["queries"][0]))
    with pytest.raises(ConformanceError, match="duplicate query id"):
        evaluate_compact_case(duplicate)

    wrong_registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    wrong_registry["benchmarks"][0]["repository_revision"] = "0" * 40
    with pytest.raises(ConformanceError, match="revision pin drift"):
        validate_registry(wrong_registry)


def test_bright_style_json_and_jsonl_local_contract(tmp_path: Path) -> None:
    bundle = tmp_path / "bright"
    bundle.mkdir()
    queries = _write(
        bundle / "queries.jsonl",
        '{"_id":"q","query":"Synthetic local query"}\n',
    )
    corpus = _write(
        bundle / "corpus.json",
        json.dumps(
            [
                {
                    "_id": "d1",
                    "title": "Relevant",
                    "text": "Synthetic relevant text.",
                    "url": "https://synthetic.invalid/relevant",
                },
                {"_id": "d2", "title": "Distractor", "text": "Synthetic distractor."},
            ]
        ),
    )
    run = _write(bundle / "run.json", json.dumps({"q": {"d2": 2.0, "d1": 1.0}}))
    qrels = _write(bundle / "qrels.json", json.dumps({"q": {"d1": 1, "d2": 0}}))
    files = {
        "queries": {**queries, "format": "jsonl"},
        "corpus": {**corpus, "format": "json"},
        "run": {**run, "format": "json"},
        "qrels": {**qrels, "format": "json"},
    }
    _write_manifest(bundle, _suite("bright"), files)
    result = evaluate_local_bundle(bundle)
    assert result["evaluation_status"] == "evaluated"
    assert result["real_external_score"] is False
    assert result["metrics"]["recall_at_5"] == 1.0
    assert result["metrics"]["ndcg_at_10"] == pytest.approx(0.630929753571, abs=1e-12)


def test_browsecomp_tsv_jsonl_and_trec_local_contract(tmp_path: Path) -> None:
    bundle = tmp_path / "browsecomp"
    bundle.mkdir()
    queries = _write(bundle / "queries.tsv", "query_id\ttext\nq\tSynthetic local query\n")
    corpus = _write(
        bundle / "corpus.jsonl",
        "\n".join(
            [
                '{"docid":"d1","title":"Relevant","text":"Synthetic relevant text.",'
                '"url":"https://synthetic.invalid/relevant"}',
                '{"doc_id":"d2","title":"Distractor","text":"Synthetic distractor."}',
                "",
            ]
        ),
    )
    run = _write(
        bundle / "run.trec",
        "q Q0 d2 1 2.0 synthetic\nq Q0 d1 2 1.0 synthetic\n",
    )
    qrels = _write(bundle / "qrels.trec", "q Q0 d1 1\nq Q0 d2 0\n")
    files = {
        "queries": {**queries, "format": "tsv"},
        "corpus": {**corpus, "format": "jsonl"},
        "run": {**run, "format": "trec"},
        "qrels": {**qrels, "format": "trec"},
    }
    _write_manifest(bundle, _suite("browsecomp_plus"), files)
    result = evaluate_local_bundle(bundle)
    assert result["evaluation_status"] == "evaluated"
    assert result["evaluation_scope"] == "integration_conformance_synthetic"
    assert result["real_external_score"] is False
    assert result["metrics"]["ndcg_at_5"] == pytest.approx(0.630929753571, abs=1e-12)
    assert "synthetic.invalid" not in json.dumps(result)


def test_trec_qrels_iteration_policy_is_exactly_q0(tmp_path: Path) -> None:
    bundle = tmp_path / "bad-qrels-iteration"
    bundle.mkdir()
    queries = _write(bundle / "queries.tsv", "q\tSynthetic local query\n")
    corpus = _write(
        bundle / "corpus.json",
        json.dumps([{"docid": "d1", "text": "Relevant"}, {"docid": "d2", "text": "Other"}]),
    )
    run = _write(bundle / "run.trec", "q Q0 d1 1 2.0 synthetic\nq Q0 d2 2 1.0 synthetic\n")
    qrels = _write(bundle / "qrels.trec", "q 0 d1 1\nq 0 d2 0\n")
    _write_manifest(
        bundle,
        _suite("browsecomp_plus"),
        {
            "queries": {**queries, "format": "tsv"},
            "corpus": {**corpus, "format": "json"},
            "run": {**run, "format": "trec"},
            "qrels": {**qrels, "format": "trec"},
        },
    )
    with pytest.raises(ConformanceError, match="iteration must be Q0"):
        evaluate_local_bundle(bundle)


@pytest.mark.parametrize("role", ["run", "qrels"])
def test_trec_lowercase_q0_is_rejected(tmp_path: Path, role: str) -> None:
    bundle = _make_trec_bundle(
        tmp_path,
        f"lowercase-{role}",
        run_iteration="q0" if role == "run" else "Q0",
        qrels_iteration="q0" if role == "qrels" else "Q0",
    )
    with pytest.raises(ConformanceError, match="iteration must be Q0"):
        evaluate_local_bundle(bundle)


def test_each_bundle_role_is_read_once_and_parsed_from_verified_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _make_json_bundle(tmp_path, "single-read")
    role_names = {"queries.json", "corpus.json", "run.json", "qrels.json"}
    read_counts = dict.fromkeys(role_names, 0)
    original_read = external._read_file_once

    def counting_read(path: Path, *, max_bytes: int) -> tuple[bytes, str, int]:
        if path.parent == bundle and path.name in read_counts:
            read_counts[path.name] += 1
        return original_read(path, max_bytes=max_bytes)

    monkeypatch.setattr(external, "_read_file_once", counting_read)
    result = evaluate_local_bundle(bundle)
    assert result["evaluation_status"] == "evaluated"
    assert read_counts == dict.fromkeys(role_names, 1)


@pytest.mark.parametrize("target_name", ["bundle_manifest.json", "queries.json"])
def test_bundle_rejects_symlink_swap_between_lstat_and_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_name: str,
) -> None:
    bundle = _make_json_bundle(tmp_path, f"swap-{target_name}")
    target = bundle / target_name
    outside = tmp_path / f"outside-{target_name}"
    outside.write_bytes(target.read_bytes())
    original_open = external.os.open
    swapped = False

    def swapping_open(path: Any, *args: Any, **kwargs: Any) -> int:
        nonlocal swapped
        if not swapped and Path(path).name == target_name:
            swapped = True
            target.unlink()
            target.symlink_to(outside)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(external.os, "open", swapping_open)
    with pytest.raises(ConformanceError, match="securely open regular file"):
        evaluate_local_bundle(bundle)
    assert swapped is True


def test_bundle_byte_lengths_counts_caps_and_exact_coverage_are_enforced(
    tmp_path: Path,
) -> None:
    byte_mismatch = _make_json_bundle(tmp_path, "byte-mismatch")
    manifest = _manifest(byte_mismatch)
    manifest["files"]["queries"]["byte_length"] += 1
    _replace_manifest(byte_mismatch, manifest)
    with pytest.raises(ConformanceError, match="byte_length mismatch"):
        evaluate_local_bundle(byte_mismatch)

    count_mismatch = _make_json_bundle(tmp_path, "count-mismatch")
    manifest = _manifest(count_mismatch)
    manifest["counts"]["run_entries"] = 1
    _replace_manifest(count_mismatch, manifest)
    with pytest.raises(ConformanceError, match="declared counts"):
        evaluate_local_bundle(count_mismatch)

    over_cap = _make_json_bundle(tmp_path, "over-cap")
    manifest = _manifest(over_cap)
    manifest["counts"]["queries"] = 10_001
    _replace_manifest(over_cap, manifest)
    with pytest.raises(ConformanceError, match="exceeds policy cap"):
        evaluate_local_bundle(over_cap)

    byte_cap = _make_json_bundle(tmp_path, "byte-cap")
    manifest = _manifest(byte_cap)
    manifest["files"]["queries"]["byte_length"] = 2_097_153
    _replace_manifest(byte_cap, manifest)
    with pytest.raises(ConformanceError, match="byte_length exceeds policy cap"):
        evaluate_local_bundle(byte_cap)

    coverage = _make_json_bundle(tmp_path, "coverage")
    run_path = coverage / "run.json"
    run_path.write_text(json.dumps({"other": {"d1": 2.0, "d2": 1.0}}), encoding="utf-8")
    _refresh_descriptor(coverage, "run", run_path)
    with pytest.raises(ConformanceError, match="coverage must exactly match"):
        evaluate_local_bundle(coverage)


def test_bundle_rejects_path_escape_symlinks_non_regular_files_and_role_aliasing(
    tmp_path: Path,
) -> None:
    escaped = _make_json_bundle(tmp_path, "escaped")
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"q": "outside"}), encoding="utf-8")
    manifest = _manifest(escaped)
    manifest["files"]["queries"].update(
        {
            "path": "../outside.json",
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
            "byte_length": outside.stat().st_size,
        }
    )
    _replace_manifest(escaped, manifest)
    with pytest.raises(ConformanceError, match="escapes bundle"):
        evaluate_local_bundle(escaped)

    linked = _make_json_bundle(tmp_path, "linked")
    link = linked / "queries-link.json"
    link.symlink_to("queries.json")
    manifest = _manifest(linked)
    manifest["files"]["queries"]["path"] = link.name
    _replace_manifest(linked, manifest)
    with pytest.raises(ConformanceError, match="symlink"):
        evaluate_local_bundle(linked)

    non_regular = _make_json_bundle(tmp_path, "non-regular")
    directory = non_regular / "run-directory"
    directory.mkdir()
    manifest = _manifest(non_regular)
    manifest["files"]["run"]["path"] = directory.name
    _replace_manifest(non_regular, manifest)
    with pytest.raises(ConformanceError, match="regular file"):
        evaluate_local_bundle(non_regular)

    aliased = _make_json_bundle(tmp_path, "aliased")
    manifest = _manifest(aliased)
    manifest["files"]["run"] = {
        **manifest["files"]["queries"],
        "format": "json",
    }
    _replace_manifest(aliased, manifest)
    with pytest.raises(ConformanceError, match="distinct files"):
        evaluate_local_bundle(aliased)


def test_official_local_assets_are_not_opened_until_asset_license_is_resolved(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "official"
    bundle.mkdir()
    suite = _suite("browsecomp_plus")
    suite["content_origin"] = "official-local-copy"
    suite["contains_official_benchmark_content"] = True
    suite["asset_license"] = load_registry()["benchmarks"][1]["benchmark_asset_license"]
    _write_manifest(bundle, suite, {})
    result = evaluate_local_bundle(bundle)
    assert result == {
        "schema_version": "evidencemesh.phase11_8_9.external-eval-result.v1",
        "benchmark_id": "browsecomp_plus",
        "evaluation_scope": "real_external_fixed_corpus",
        "evaluation_status": "not_evaluated",
        "reason_code": "official_evaluation_not_supported_in_v1",
        "real_external_score": False,
        "external_quality_claim_allowed": False,
        "aggregate_only": True,
        "counts": None,
        "metrics": None,
    }

    forged = tmp_path / "forged-official"
    forged.mkdir()
    forged_suite = copy.deepcopy(suite)
    forged_suite["asset_license"] = {
        "status": "resolved",
        "scope": "self-declared",
        "spdx_id": "MIT",
        "evidence_revision": "f" * 64,
        "real_external_evaluation_allowed": True,
        "reason": "self declared",
    }
    _write_manifest(forged, forged_suite, {})
    with pytest.raises(ConformanceError, match="asset-license lock mismatch"):
        evaluate_local_bundle(forged)

    forged_registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    forged_registry["benchmarks"][0]["benchmark_asset_license"].update(
        {
            "status": "resolved",
            "spdx_id": "CC-BY-4.0",
            "evidence_revision": "f" * 64,
            "real_external_evaluation_allowed": True,
        }
    )
    with pytest.raises(ConformanceError, match="asset license must fail closed"):
        validate_registry(forged_registry)


def test_missing_bundle_is_an_explicit_not_evaluated_result(tmp_path: Path) -> None:
    result = evaluate_local_bundle(tmp_path / "absent", benchmark_id="bright")
    assert result["evaluation_status"] == "not_evaluated"
    assert result["reason_code"] == "local_bundle_manifest_missing"
    assert result["real_external_score"] is False
    assert result["metrics"] is None


def test_module_has_no_network_model_provider_secret_or_process_path() -> None:
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imports.discard("")
    assert imports <= {
        "__future__",
        "collections",
        "dataclasses",
        "hashlib",
        "json",
        "math",
        "os",
        "pathlib",
        "stat",
        "typing",
    }
    lowered = source.casefold()
    for forbidden in (
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "urllib",
        "getenv",
        "environ",
        "api_key",
        "gemini",
        "tavily",
    ):
        assert forbidden not in lowered
    assert ".read_bytes(" not in source
    assert '"real_external_score": true' not in lowered
    assert "'real_external_score': true" not in lowered
