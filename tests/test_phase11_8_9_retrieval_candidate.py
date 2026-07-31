from __future__ import annotations

import ast
import hashlib
import inspect
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from benchmarks.phase11_8_9_external_eval import (
    ConformanceError,
    compute_retrieval_metrics,
)
from benchmarks.phase11_8_9_retrieval_candidate import (
    BASELINE_FAMILY,
    CANDIDATE_FAMILY,
    FUNNEL_SCHEMA,
    OMISSION_SEPARATOR,
    PROJECTION_FAMILY,
    PROJECTION_SCHEMA,
    RawResult,
    canonical_funnel_json,
    canonical_funnel_sha256,
    canonical_projection_json,
    canonical_projection_sha256,
    freeze_metadata,
    fuse_results,
    project_selected_v3,
    rendered_projection_chars,
    select_baseline,
    select_candidate_v3,
)

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "benchmarks/data/phase11_8_9_retrieval_fixtures_v1.json"
CANDIDATE = ROOT / "benchmarks/phase11_8_9_retrieval_candidate.py"

EXPECTED_CONFORMANCE_REQUIREMENTS = {
    "exact_match",
    "phrase_match",
    "acronym_anchor",
    "number_anchor",
    "date_anchor",
    "unit_anchor",
    "rare_token_anchor",
    "unicode_punctuation",
    "canonical_multi_provider_duplicate",
    "deterministic_tie",
    "empty_input",
    "short_content",
    "long_content",
    "malformed_content",
    "eligibility_exclusions",
    "domain_diversity_tie",
    "provider_diversity_tie",
    "source_type_diversity_tie",
    "selection_limit_one",
    "selection_limit_twenty",
    "selection_invalid_limits",
    "projection_head_middle_tail",
    "projection_budget_12000",
    "projection_insufficient_budget",
    "citation_ids_unique",
    "source_preservation",
    "answer_qrel_blind",
    "no_io_network_env_process",
    "cold_replays_two_plus",
    "aggregate_serialization_deterministic",
    "archive_or_path_traversal_rejection",
    "binary_and_graded_relevance",
    "cold_process_replay",
    "deterministic_fusion_tie",
    "duplicate_citation_rejected",
    "environment_secret_zero_access",
    "external_metric_oracles",
    "forbidden_scorer_fields",
    "missing_qrels_policy",
    "network_zero_access",
    "no_relevant_document_policy",
    "official_assets_fail_closed",
    "phase12_zero_access",
}
EXPECTED_CONFORMANCE_CASES = {
    "lexical_anchor_matrix",
    "canonical_fusion_lineage_and_invalid_url",
    "deterministic_tie_and_diversity",
    "content_eligibility_matrix",
    "adaptive_domain_diversity",
    "provider_and_source_type_diversity",
    "selection_boundaries",
    "projection_anchor_budget",
    "projection_insufficient_budget",
    "static_candidate_audit",
    "aggregate_replay",
    "cold_process_replay",
    "external_asset_path_validation",
    "external_metric_oracles",
    "external_official_asset_gate",
    "external_qrels_policy",
    "projection_duplicate_citation",
    "runner_zero_access",
}
EXPECTED_CONFORMANCE_SUITES = {
    "external_adapter",
    "retrieval",
    "runner",
}
EXTERNAL_ADAPTER_REQUIREMENTS = {
    "archive_or_path_traversal_rejection",
    "binary_and_graded_relevance",
    "external_metric_oracles",
    "missing_qrels_policy",
    "no_relevant_document_policy",
    "official_assets_fail_closed",
}
RUNNER_REQUIREMENTS = {
    "cold_process_replay",
    "environment_secret_zero_access",
    "network_zero_access",
    "phase12_zero_access",
}
EXPECTED_REQUIREMENT_SUITES = {
    requirement_id: (
        "external_adapter"
        if requirement_id in EXTERNAL_ADAPTER_REQUIREMENTS
        else "runner"
        if requirement_id in RUNNER_REQUIREMENTS
        else "retrieval"
    )
    for requirement_id in EXPECTED_CONFORMANCE_REQUIREMENTS
}
TEST_MODULES = (
    ROOT / "tests/test_phase11_8_9_retrieval_candidate.py",
    ROOT / "tests/test_phase11_8_9_external_eval.py",
    ROOT / "tests/test_phase11_8_9_offline_retrieval_recovery.py",
)


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _raw_results(case: dict[str, Any]) -> tuple[RawResult, ...]:
    return tuple(
        RawResult(
            result_id=item["result_id"],
            title=item["title"],
            url=item["url"],
            snippet=item["snippet"],
            provider=item["provider"],
            rank=item["rank"],
            query=item["query"],
            source_type=item.get("source_type", "web"),
            provider_score_micros=item.get("provider_score_micros"),
            metadata=freeze_metadata(item.get("metadata")),
        )
        for item in case["raw_results"]
    )


def _selected_ids(outcome: Any) -> list[str]:
    return [item.representative_result_id for item in outcome.selected]


def _utility_count(outcome: Any, utility_ids: set[str]) -> int:
    return sum(bool(set(item.raw_result_ids) & utility_ids) for item in outcome.selected)


def test_fixture_is_explicitly_post_observation_engineering_only() -> None:
    fixture = _fixture()
    assert fixture["engineering_only"] is True
    assert fixture["authored_after_phase11_8_8_live_observation"] is True
    assert fixture["development_diagnostic_only"] is True
    assert fixture["predictive_quality_claim_allowed"] is False
    assert fixture["real_world_quality_claim_allowed"] is False
    assert fixture["execution_contract"] == {
        "network_allowed": False,
        "provider_calls_allowed": False,
        "model_calls_allowed": False,
        "secrets_allowed": False,
        "candidate_inputs": [
            "query",
            "raw_results",
            "limit",
            "max_per_domain",
        ],
        "evaluator_only_fields": [
            "utility_result_ids",
            "expected_baseline_selected_ids",
            "expected_candidate_selected_ids",
        ],
    }
    assert len(fixture["cases"]) == 5


def test_conformance_registry_is_exact_complete_and_resolvable() -> None:
    fixture = _fixture()
    catalog = fixture["conformance_case_catalog"]
    requirements = fixture["conformance_requirements"]
    catalog_ids = [item["id"] for item in catalog]
    requirement_ids = [item["id"] for item in requirements]
    assert len(catalog_ids) == len(set(catalog_ids))
    assert len(requirement_ids) == len(set(requirement_ids))
    assert len(requirement_ids) == 43
    assert set(catalog_ids) == EXPECTED_CONFORMANCE_CASES
    assert set(requirement_ids) == EXPECTED_CONFORMANCE_REQUIREMENTS
    assert all(
        set(item) == {"id", "kind", "purpose"}
        and isinstance(item["kind"], str)
        and bool(item["kind"])
        and isinstance(item["purpose"], str)
        and bool(item["purpose"].strip())
        for item in catalog
    )

    available_tests: set[str] = set()
    for test_module in TEST_MODULES:
        test_tree = ast.parse(test_module.read_text(encoding="utf-8"))
        available_tests.update(
            node.name
            for node in test_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    registered_cases: set[str] = set()
    registered_suites: set[str] = set()
    registered_tests: set[str] = set()
    for requirement in requirements:
        assert set(requirement) == {"id", "evidence"}
        evidence = requirement["evidence"]
        assert set(evidence) == {"case_ids", "proof", "suite", "test_names"}
        assert evidence["suite"] in EXPECTED_CONFORMANCE_SUITES
        assert evidence["case_ids"]
        assert evidence["test_names"]
        assert len(evidence["case_ids"]) == len(set(evidence["case_ids"]))
        assert len(evidence["test_names"]) == len(set(evidence["test_names"]))
        assert isinstance(evidence["proof"], str) and evidence["proof"].strip()
        assert set(evidence["case_ids"]) <= EXPECTED_CONFORMANCE_CASES
        assert set(evidence["test_names"]) <= available_tests
        registered_cases.update(evidence["case_ids"])
        registered_suites.add(evidence["suite"])
        registered_tests.update(evidence["test_names"])
    assert registered_cases == EXPECTED_CONFORMANCE_CASES
    assert registered_suites == EXPECTED_CONFORMANCE_SUITES
    assert {
        requirement["id"]: requirement["evidence"]["suite"] for requirement in requirements
    } == EXPECTED_REQUIREMENT_SUITES
    assert {
        "test_candidate_interfaces_are_answer_qrel_blind_and_side_effect_free",
        "test_duplicate_citation_identifiers_are_rejected",
        "test_empty_short_long_and_malformed_content_have_explicit_eligibility",
        "test_external_adapter_missing_qrels_no_relevant_and_relevance_modes",
        "test_lexical_anchor_matrix_handles_exact_phrase_acronym_number_date_unit_rare_unicode",
        "test_projection_head_middle_tail_exact_12000_budget_and_source_preservation",
        "test_selection_boundaries_zero_one_twenty_and_invalid_limits",
        "test_secret_presence_probe_counts_names_without_reading_values",
        "test_source_lock_paths_fail_closed",
        "test_three_cold_process_replays_are_byte_identical",
    } <= registered_tests


def test_candidate_interfaces_are_answer_qrel_blind_and_side_effect_free() -> None:
    for function in (fuse_results, select_candidate_v3, project_selected_v3):
        parameters = set(inspect.signature(function).parameters)
        assert parameters.isdisjoint(
            {
                "expected_marker",
                "reference",
                "reference_text",
                "gold",
                "target_result_ids",
                "utility_result_ids",
                "answer",
                "answers",
                "qrel",
                "qrels",
            }
        )

    source = CANDIDATE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported_modules.discard("")
    assert imported_modules == {
        "__future__",
        "collections",
        "dataclasses",
        "hashlib",
        "itertools",
        "json",
        "re",
        "typing",
        "unicodedata",
        "urllib.parse",
    }
    direct_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)
    }
    assert direct_calls.isdisjoint(
        {
            "__import__",
            "compile",
            "eval",
            "exec",
            "getenv",
            "input",
            "open",
            "Popen",
            "run",
            "socket",
            "system",
            "urlopen",
        }
    )
    assert attribute_calls.isdisjoint(
        {
            "connect",
            "getenv",
            "open",
            "read_bytes",
            "read_text",
            "recv",
            "request",
            "send",
            "system",
            "write_bytes",
            "write_text",
        }
    )
    assert identifiers.isdisjoint(
        {
            "answer",
            "answers",
            "expected_candidate_selected_ids",
            "gold",
            "gold_answer",
            "qrel",
            "qrels",
            "reference_text",
            "relevance_labels",
            "target_result_ids",
            "utility_result_ids",
        }
    )
    assert all(
        forbidden not in source
        for forbidden in (
            "httpx",
            "os.environ",
            "requests",
            "subprocess",
            "urllib.request",
        )
    )


def test_external_adapter_missing_qrels_no_relevant_and_relevance_modes() -> None:
    with pytest.raises(ConformanceError, match="coverage mismatch"):
        compute_retrieval_metrics(
            {"query-a": []},
            {"query-b": {"document": 1}},
        )
    with pytest.raises(ConformanceError, match="no relevant document"):
        compute_retrieval_metrics(
            {"query": []},
            {"query": {"document": 0}},
        )

    ranked = {
        "query": [
            {"docid": "low", "rank": 1, "score": 2.0},
            {"docid": "high", "rank": 2, "score": 1.0},
        ]
    }
    binary = compute_retrieval_metrics(
        ranked,
        {"query": {"low": 1, "high": 1}},
    )
    graded = compute_retrieval_metrics(
        ranked,
        {"query": {"low": 1, "high": 3}},
    )
    assert binary["recall_at_5"] == graded["recall_at_5"] == 1.0
    assert binary["ndcg_at_5"] == 1.0
    assert graded["ndcg_at_5"] == pytest.approx(0.796707580991, abs=1e-12)


def test_lexical_anchor_matrix_handles_exact_phrase_acronym_number_date_unit_rare_unicode() -> None:
    query = "Résumé — NASA Orion Delta QN-7 2026-07-31 19.5 µg/m³ Zephyra"
    raw_results = (
        RawResult(
            result_id="rank_prior_scatter",
            title="19.5 NASA Delta archive Orion QN-7 2026-07-31 m³ µg Résumé",
            url="https://scatter.example.test/record",
            snippet="A high-ranked keyword index with the anchors in an unrelated order.",
            provider="fixture-a",
            rank=1,
            query=query,
        ),
        RawResult(
            result_id="exact_anchor_source",
            title=("Re\u0301sume\u0301: NASA Orion Delta QN-7 — 2026-07-31, 19.5 μg/m³; Zephyra"),
            url="https://exact.example.org/record",
            snippet=(
                "The exact NASA Orion Delta phrase and rare Zephyra token accompany "
                "the dated 19.5 μg/m³ QN-7 measurement."
            ),
            provider="fixture-b",
            rank=20,
            query=query,
            source_type="reference",
        ),
        *tuple(
            RawResult(
                result_id=f"filler-{index}",
                title=f"Generic archive volume {index}",
                url=f"https://filler-{index}.invalid.test/item",
                snippet="Unrelated synthetic index content.",
                provider="fixture-a",
                rank=index + 2,
                query=query,
            )
            for index in range(4)
        ),
    )
    outcome = select_candidate_v3(
        raw_results,
        query,
        limit=1,
        max_per_domain=1,
    )
    assert _selected_ids(outcome) == ["exact_anchor_source"]
    assert outcome.funnel.query_terms == 9
    assert outcome.funnel.protected_query_terms == 9
    assert outcome.funnel.protected_terms_present_in_selected == 9


def test_empty_short_long_and_malformed_content_have_explicit_eligibility() -> None:
    query = "content eligibility matrix"
    long_text = ("λong valid Unicode source. " * 2_500).strip()
    raw_results = (
        RawResult(
            result_id="short",
            title="Short valid source",
            url="https://short.example.test/source",
            snippet="x",
            provider="fixture",
            rank=1,
            query=query,
        ),
        RawResult(
            result_id="long",
            title="Long valid source",
            url="https://long.example.test/source",
            snippet=long_text,
            provider="fixture",
            rank=2,
            query=query,
        ),
        RawResult(
            result_id="empty",
            title="Empty source",
            url="https://empty.example.test/source",
            snippet="",
            provider="fixture",
            rank=3,
            query=query,
        ),
        RawResult(
            result_id="whitespace",
            title="Whitespace source",
            url="https://whitespace.example.test/source",
            snippet=" \n\t ",
            provider="fixture",
            rank=4,
            query=query,
        ),
        RawResult(
            result_id="control",
            title="Control source",
            url="https://control.example.test/source",
            snippet="malformed\u0000content",
            provider="fixture",
            rank=5,
            query=query,
        ),
        RawResult(
            result_id="surrogate",
            title="Surrogate source",
            url="https://surrogate.example.test/source",
            snippet="malformed\ud800content",
            provider="fixture",
            rank=6,
            query=query,
        ),
        RawResult(
            result_id="non-text",
            title="Non-text source",
            url="https://non-text.example.test/source",
            snippet=None,  # type: ignore[arg-type]
            provider="fixture",
            rank=7,
            query=query,
        ),
    )
    fused = fuse_results(raw_results, query)
    outcome = select_candidate_v3(
        raw_results,
        query,
        limit=20,
        max_per_domain=20,
    )
    assert len(fused) == 7
    assert _selected_ids(outcome) == ["short", "long"]
    assert next(item for item in fused if item.representative_result_id == "long").snippet == (
        long_text
    )
    assert outcome.funnel.raw_pool == 7
    assert outcome.funnel.valid_raw == 7
    assert outcome.funnel.invalid_raw == 0
    assert outcome.funnel.fused == 7
    assert outcome.funnel.eligible == 2
    assert outcome.funnel.selected == 2


def test_deterministic_ties_and_domain_provider_source_diversity() -> None:
    query = "deterministic synthetic tie"
    tied = (
        RawResult(
            result_id="first",
            title="Deterministic synthetic tie",
            url="https://first.alpha.test/source",
            snippet="Deterministic synthetic tie evidence.",
            provider="fixture",
            rank=1,
            query=query,
        ),
        RawResult(
            result_id="second",
            title="Deterministic synthetic tie",
            url="https://second.beta.test/source",
            snippet="Deterministic synthetic tie evidence.",
            provider="fixture",
            rank=1,
            query=query,
        ),
    )
    assert {
        tuple(_selected_ids(select_candidate_v3(tied, query, limit=1, max_per_domain=1)))
        for _ in range(20)
    } == {("first",)}

    fusion_tie = (
        RawResult(
            result_id="fusion-first",
            title="Deterministic fusion tie",
            url="https://fusion.example.test/source?utm_source=first",
            snippet="Equal deterministic fusion evidence.",
            provider="fixture-a",
            rank=1,
            query=query,
        ),
        RawResult(
            result_id="fusion-second",
            title="Deterministic fusion tie",
            url="https://fusion.example.test/source",
            snippet="Equal deterministic fusion evidence.",
            provider="fixture-b",
            rank=1,
            query=query,
        ),
    )
    fused_replays = tuple(fuse_results(fusion_tie, query) for _ in range(20))
    assert {replay[0].representative_result_id for replay in fused_replays} == {"fusion-first"}
    assert {replay[0].raw_result_ids for replay in fused_replays} == {
        ("fusion-first", "fusion-second")
    }

    cases = {case["id"]: case for case in _fixture()["cases"]}
    domain_case = cases["adaptive_domain_diversity"]
    domain_outcome = select_candidate_v3(
        _raw_results(domain_case),
        domain_case["query"],
        limit=domain_case["limit"],
        max_per_domain=domain_case["max_per_domain"],
    )
    assert _selected_ids(domain_outcome) == domain_case["expected_candidate_selected_ids"]
    assert domain_outcome.funnel.selected_distinct_domains == 3

    provider_case = cases["provider_and_source_type_diversity"]
    provider_outcome = select_candidate_v3(
        _raw_results(provider_case),
        provider_case["query"],
        limit=provider_case["limit"],
        max_per_domain=provider_case["max_per_domain"],
    )
    assert _selected_ids(provider_outcome) == provider_case["expected_candidate_selected_ids"]
    assert provider_outcome.funnel.selected_distinct_providers == 2
    assert provider_outcome.funnel.selected_distinct_source_types == 2


def test_locked_synthetic_comparisons_replay_and_candidate_improves_controls() -> None:
    baseline_utility = 0
    candidate_utility = 0
    for case in _fixture()["cases"]:
        raw_results = _raw_results(case)
        baseline = select_baseline(
            raw_results,
            case["query"],
            limit=case["limit"],
            max_per_domain=case["max_per_domain"],
        )
        candidate = select_candidate_v3(
            raw_results,
            case["query"],
            limit=case["limit"],
            max_per_domain=case["max_per_domain"],
        )
        assert baseline.family == BASELINE_FAMILY
        assert candidate.family == CANDIDATE_FAMILY
        assert _selected_ids(baseline) == case["expected_baseline_selected_ids"]
        assert _selected_ids(candidate) == case["expected_candidate_selected_ids"]
        utility_ids = set(case["utility_result_ids"])
        baseline_utility += _utility_count(baseline, utility_ids)
        candidate_utility += _utility_count(candidate, utility_ids)

    assert baseline_utility == 4
    assert candidate_utility == 9
    assert candidate_utility > baseline_utility


def test_identifier_and_diversity_controls_measure_the_intended_stage() -> None:
    cases = {case["id"]: case for case in _fixture()["cases"]}
    identifier = cases["hyphenated_identifier_beats_rank_prior"]
    raw_identifier = _raw_results(identifier)
    baseline = select_baseline(
        raw_identifier,
        identifier["query"],
        limit=1,
        max_per_domain=1,
    )
    candidate = select_candidate_v3(
        raw_identifier,
        identifier["query"],
        limit=1,
        max_per_domain=1,
    )
    assert baseline.funnel.protected_terms_present_in_selected == 0
    assert candidate.funnel.protected_terms_present_in_selected == 1

    diversity = cases["adaptive_domain_diversity"]
    raw_diversity = _raw_results(diversity)
    baseline = select_baseline(
        raw_diversity,
        diversity["query"],
        limit=3,
        max_per_domain=3,
    )
    candidate = select_candidate_v3(
        raw_diversity,
        diversity["query"],
        limit=3,
        max_per_domain=3,
    )
    assert baseline.funnel.selected_distinct_domains == 1
    assert candidate.funnel.selected_distinct_domains == 3
    assert candidate.funnel.selected_distinct_providers == 3
    assert candidate.funnel.selected_distinct_source_types == 3


def test_fusion_preserves_ordered_provider_lineage_and_counts_only_invalid() -> None:
    case = _fixture()["cases"][-1]
    raw_results = _raw_results(case)
    fused = fuse_results(raw_results, case["query"])
    assert len(fused) == 2
    orion = fused[0]
    assert orion.canonical_url == "https://docs.example.test/orion"
    assert orion.representative_result_id == "orion_brave"
    assert orion.raw_result_ids == ("orion_tavily", "orion_brave")
    assert orion.providers == ("tavily", "brave")
    assert orion.provider_ranks == (("tavily", 2), ("brave", 4))
    assert orion.matched_queries == ("Orion SDK API documentation",)
    assert tuple(item.input_order for item in orion.observations) == (0, 1)
    assert orion.observations[0].metadata == (
        ("region", "global"),
        ("adapter_order", 1),
    )
    assert orion.observations[1].metadata == (
        ("region", "global"),
        ("adapter_order", 2),
    )

    outcome = select_candidate_v3(
        raw_results,
        case["query"],
        limit=2,
        max_per_domain=1,
    )
    assert outcome.funnel.raw_pool == 4
    assert outcome.funnel.valid_raw == 3
    assert outcome.funnel.invalid_raw == 1
    assert outcome.funnel.fused == 2
    assert outcome.funnel.collapsed_duplicates == 1
    assert outcome.funnel.eligible == 2
    assert outcome.funnel.selected == 2


def test_empty_title_is_preserved_and_excluded_without_url_fallback() -> None:
    raw_results = (
        RawResult(
            result_id="empty-title",
            title=" \t ",
            url="https://example.test/source",
            snippet="A valid evidence snippet that is long enough for eligibility.",
            provider="synthetic",
            rank=1,
            query="valid evidence",
            source_type="web",
            provider_score_micros=1_000_000,
            metadata=(),
        ),
    )
    fused = fuse_results(raw_results, "valid evidence")
    assert len(fused) == 1
    assert fused[0].title == ""
    outcome = select_candidate_v3(
        raw_results,
        "valid evidence",
        limit=1,
        max_per_domain=1,
    )
    assert outcome.funnel.fused == 1
    assert outcome.funnel.eligible == 0
    assert outcome.funnel.selected == 0
    assert outcome.selected == ()


def test_replay_and_aggregate_funnel_serialization_are_canonical_and_private() -> None:
    case = _fixture()["cases"][2]
    raw_results = _raw_results(case)
    outcomes = [
        select_candidate_v3(
            raw_results,
            case["query"],
            limit=case["limit"],
            max_per_domain=case["max_per_domain"],
        )
        for _ in range(20)
    ]
    assert len({outcome.selected for outcome in outcomes}) == 1
    serializations = {canonical_funnel_json(outcome) for outcome in outcomes}
    hashes = {canonical_funnel_sha256(outcome) for outcome in outcomes}
    assert len(serializations) == 1
    assert len(hashes) == 1
    serialized = serializations.pop()
    digest = hashes.pop()
    payload = json.loads(serialized)
    assert payload["schema"] == FUNNEL_SCHEMA
    assert payload["family"] == CANDIDATE_FAMILY
    assert set(payload) == {"family", "funnel", "schema"}
    assert hashlib.sha256(serialized.encode()).hexdigest() == digest
    forbidden_values = [
        case["query"],
        *(item["title"] for item in case["raw_results"]),
        *(item["url"] for item in case["raw_results"]),
        *(item["result_id"] for item in case["raw_results"]),
        *(item["provider"] for item in case["raw_results"]),
    ]
    assert all(value not in serialized for value in forbidden_values)


def test_projection_head_middle_tail_exact_12000_budget_and_source_preservation() -> None:
    query = "Where is the QN-7 middle anchor?"
    first_text = ("H" * 8_000) + " QN-7 middle anchor " + ("T" * 8_000)
    second_text = ("A" * 8_000) + " independent middle context " + ("Z" * 8_000)
    raw_results = (
        RawResult(
            result_id="first",
            title="QN-7 middle anchor register",
            url="https://first.alpha.test/qn-7",
            snippet=first_text,
            provider="fixture-a",
            rank=1,
            query=query,
            source_type="reference",
        ),
        RawResult(
            result_id="second",
            title="Independent middle context",
            url="https://second.beta.test/context",
            snippet=second_text,
            provider="fixture-b",
            rank=2,
            query=query,
            source_type="academic",
        ),
    )
    selected = select_candidate_v3(
        raw_results,
        query,
        limit=2,
        max_per_domain=1,
    ).selected
    projection = project_selected_v3(
        selected,
        query,
        budget_chars=12_000,
        max_document_chars=12_000,
        min_document_chars=96,
    )
    assert projection.metrics.budget_chars == 12_000
    assert projection.metrics.rendered_chars == 12_000
    assert projection.metrics.unused_budget_chars == 0
    assert rendered_projection_chars(projection.evidence) == 12_000
    citation_ids = [item.citation_id for item in projection.evidence]
    assert citation_ids == ["S1", "S2"]
    assert len(citation_ids) == len(set(citation_ids))

    originals = {
        "https://first.alpha.test/qn-7": first_text,
        "https://second.beta.test/context": second_text,
    }
    for item in projection.evidence:
        original = originals[item.url]
        cursor = 0
        for segment in item.text.split(OMISSION_SEPARATOR):
            position = original.find(segment, cursor)
            assert segment
            assert position >= 0
            cursor = position + len(segment)
    first_projection = projection.evidence[0].text
    assert first_projection.startswith("H" * 32)
    assert "QN-7 middle anchor" in first_projection
    assert first_projection.endswith("T" * 32)


def test_duplicate_citation_identifiers_are_rejected() -> None:
    case = _fixture()["cases"][2]
    selected = select_candidate_v3(
        _raw_results(case),
        case["query"],
        limit=2,
        max_per_domain=case["max_per_domain"],
    ).selected
    projection = project_selected_v3(
        selected,
        case["query"],
        budget_chars=1_000,
        max_document_chars=300,
        min_document_chars=20,
    )
    assert len(projection.evidence) == 2
    duplicated = (
        projection.evidence[0],
        replace(
            projection.evidence[1],
            citation_id=projection.evidence[0].citation_id,
        ),
    )
    with pytest.raises(ValueError, match="must be unique"):
        rendered_projection_chars(duplicated)


def test_projection_insufficient_budget_is_bounded_and_deterministic() -> None:
    case = _fixture()["cases"][2]
    selected = select_candidate_v3(
        _raw_results(case),
        case["query"],
        limit=case["limit"],
        max_per_domain=case["max_per_domain"],
    ).selected
    first_header = len(f"[S1] {selected[0].title}\nURL: {selected[0].url}\nEvidence: ")
    projections = tuple(
        project_selected_v3(
            selected,
            case["query"],
            budget_chars=first_header + 1,
            max_document_chars=100,
            min_document_chars=20,
        )
        for _ in range(3)
    )
    assert len({canonical_projection_json(item) for item in projections}) == 1
    projection = projections[0]
    assert rendered_projection_chars(projection.evidence) == first_header + 1
    assert [item.citation_id for item in projection.evidence] == ["S1"]
    assert projection.metrics.dropped_for_header_budget == len(selected) - 1
    assert projection.metrics.unused_budget_chars == 0


def test_projection_preserves_source_substrings_metadata_citations_and_budget() -> None:
    query = "Where is the rare QN-7 calibration anchor?"
    first_text = (
        ("opening registry context. " * 18)
        + "The rare QN-7 calibration anchor is recorded in this middle passage. "
        + ("closing appendix context. " * 20)
    )
    second_text = (
        ("secondary opening context. " * 15)
        + "A separate calibration discussion appears in the middle. "
        + ("secondary closing context. " * 18)
    )
    raw_results = (
        RawResult(
            result_id="first",
            title="QN-7 calibration register",
            url="https://one.example.test/qn-7",
            snippet=first_text,
            provider="tavily",
            rank=1,
            query=query,
            source_type="reference",
            metadata=(("order", 1),),
        ),
        RawResult(
            result_id="second",
            title="Calibration field notes",
            url="https://two.example.org/notes",
            snippet=second_text,
            provider="openalex",
            rank=2,
            query=query,
            source_type="academic",
            metadata=(("order", 2),),
        ),
    )
    selected = select_candidate_v3(
        raw_results,
        query,
        limit=2,
        max_per_domain=1,
    ).selected
    projection = project_selected_v3(
        selected,
        query,
        budget_chars=760,
        max_document_chars=320,
        min_document_chars=96,
    )
    assert projection.family == PROJECTION_FAMILY
    assert [item.citation_id for item in projection.evidence] == ["S1", "S2"]
    assert projection.metrics.projected_documents == 2
    assert projection.metrics.documents_with_nonzero_text == 2
    assert projection.metrics.documents_with_query_anchor >= 1
    assert rendered_projection_chars(projection.evidence) <= 760
    assert projection.metrics.rendered_chars == rendered_projection_chars(projection.evidence)
    assert projection.metrics.unused_budget_chars == 760 - projection.metrics.rendered_chars

    originals = {
        "https://one.example.test/qn-7": first_text.strip(),
        "https://two.example.org/notes": second_text.strip(),
    }
    selected_by_url = {item.url: item for item in selected}
    for item in projection.evidence:
        source = originals[item.url]
        cursor = 0
        for segment in item.text.split(OMISSION_SEPARATOR):
            if not segment:
                continue
            position = source.find(segment, cursor)
            assert position >= 0
            cursor = position + len(segment)
        fused = selected_by_url[item.url]
        assert item.providers == fused.providers
        assert item.provider_ranks == fused.provider_ranks
        assert item.source_type == fused.source_type
    assert "QN-7" in projection.evidence[0].text


def test_projection_replay_hash_is_aggregate_only_and_tiny_budget_drops_tail() -> None:
    case = _fixture()["cases"][2]
    selected = select_candidate_v3(
        _raw_results(case),
        case["query"],
        limit=case["limit"],
        max_per_domain=case["max_per_domain"],
    ).selected
    header_one = len(f"[S1] {selected[0].title}\nURL: {selected[0].url}\nEvidence: ")
    projection = project_selected_v3(
        selected,
        case["query"],
        budget_chars=header_one + 1,
        max_document_chars=100,
        min_document_chars=20,
    )
    assert len(projection.evidence) == 1
    assert projection.evidence[0].text
    assert projection.metrics.dropped_for_header_budget == len(selected) - 1

    replay = project_selected_v3(
        selected,
        case["query"],
        budget_chars=header_one + 1,
        max_document_chars=100,
        min_document_chars=20,
    )
    serialized = canonical_projection_json(projection)
    assert serialized == canonical_projection_json(replay)
    assert canonical_projection_sha256(projection) == canonical_projection_sha256(replay)
    payload = json.loads(serialized)
    assert payload["schema"] == PROJECTION_SCHEMA
    assert payload["family"] == PROJECTION_FAMILY
    assert set(payload) == {"family", "metrics", "schema"}
    assert all(item.title not in serialized for item in selected)
    assert all(item.url not in serialized for item in selected)
    assert case["query"] not in serialized


def test_three_cold_process_replays_are_byte_identical() -> None:
    script = """
import json
from benchmarks.phase11_8_9_retrieval_candidate import (
    RawResult,
    canonical_funnel_json,
    select_candidate_v3,
)

query = "cold replay QN-7"
raw = (
    RawResult(
        result_id="cold-a",
        title="Cold replay QN-7",
        url="https://cold-a.example.test/source",
        snippet="Cold replay QN-7 evidence.",
        provider="fixture",
        rank=2,
        query=query,
    ),
    RawResult(
        result_id="cold-b",
        title="Cold replay index",
        url="https://cold-b.example.org/source",
        snippet="Generic replay evidence.",
        provider="fixture",
        rank=1,
        query=query,
    ),
)
outcome = select_candidate_v3(raw, query, limit=1, max_per_domain=1)
print(json.dumps({
    "funnel": canonical_funnel_json(outcome),
    "selected": [item.representative_result_id for item in outcome.selected],
}, sort_keys=True, separators=(",", ":")))
"""
    outputs = tuple(
        subprocess.run(  # noqa: S603 - fixed interpreter and static conformance script
            [sys.executable, "-c", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            timeout=10,
        ).stdout
        for _ in range(3)
    )
    assert len(set(outputs)) == 1
    assert json.loads(outputs[0])["selected"] == ["cold-a"]


def test_selection_boundaries_zero_one_twenty_and_invalid_limits() -> None:
    valid = RawResult(
        result_id="one",
        title="One",
        url="https://one.example.test/",
        snippet="source text",
        provider="tavily",
        rank=1,
        query="source text",
    )
    with pytest.raises(FrozenInstanceError):
        valid.rank = 2  # type: ignore[misc]
    for selector in (select_baseline, select_candidate_v3):
        empty = selector((), "source text", limit=1, max_per_domain=1)
        assert empty.selected == ()
        assert empty.funnel.raw_pool == 0
        assert empty.funnel.invalid_raw == 0
        assert empty.funnel.fused == 0
        assert empty.funnel.eligible == 0
        assert empty.funnel.selected == 0
        assert (
            len(
                selector(
                    (valid,),
                    "source text",
                    limit=1,
                    max_per_domain=1,
                ).selected
            )
            == 1
        )
    with pytest.raises(ValueError, match="unique"):
        fuse_results((valid, valid), "source text")
    with pytest.raises(ValueError, match="positive"):
        fuse_results(
            (
                RawResult(
                    result_id="bad",
                    title="Bad",
                    url="https://bad.example.test/",
                    snippet="bad",
                    provider="tavily",
                    rank=0,
                    query="bad",
                ),
            ),
            "bad",
        )
    for selector in (select_baseline, select_candidate_v3):
        for invalid_limit in (0, -1, 21, 20.5, True):
            with pytest.raises(ValueError, match="limit"):
                selector(
                    (valid,),
                    "source text",
                    limit=invalid_limit,  # type: ignore[arg-type]
                    max_per_domain=1,
                )
        for invalid_domain_cap in (0, 1.5, True):
            with pytest.raises(ValueError, match="max_per_domain"):
                selector(
                    (valid,),
                    "source text",
                    limit=1,
                    max_per_domain=invalid_domain_cap,  # type: ignore[arg-type]
                )

    twenty_one = tuple(
        RawResult(
            result_id=f"boundary-{index}",
            title=f"Boundary source {index}",
            url=f"https://source-{index}.example.test/",
            snippet=f"source text boundary {index}",
            provider="fixture",
            rank=index + 1,
            query="source text",
        )
        for index in range(21)
    )
    for selector in (select_baseline, select_candidate_v3):
        assert (
            len(
                selector(
                    twenty_one,
                    "source text",
                    limit=20,
                    max_per_domain=20,
                ).selected
            )
            == 20
        )
        with pytest.raises(ValueError, match="limit"):
            selector(
                twenty_one,
                "source text",
                limit=21,
                max_per_domain=20,
            )

    selected = select_candidate_v3(
        (valid,),
        "source text",
        limit=1,
        max_per_domain=1,
    ).selected
    with pytest.raises(ValueError, match="budget_chars"):
        project_selected_v3(
            selected,
            "source text",
            budget_chars=0,
            max_document_chars=10,
        )
    with pytest.raises(ValueError, match="max_document_chars"):
        project_selected_v3(
            selected,
            "source text",
            budget_chars=100,
            max_document_chars=0,
        )
    with pytest.raises(ValueError, match="min_document_chars"):
        project_selected_v3(
            selected,
            "source text",
            budget_chars=100,
            max_document_chars=10,
            min_document_chars=11,
        )
