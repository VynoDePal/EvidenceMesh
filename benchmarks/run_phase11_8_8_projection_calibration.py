#!/usr/bin/env python3
"""Run the locked Phase 11.8.8 Tavily-only projection calibration.

The already-observed 24-case Phase 11.7 suite is reused for calibration. Each
case makes one Tavily retrieval and the resulting selected packet is projected
locally by the locked equal-cap baseline, the Phase 11.8.2 v1 candidate and the
Phase 11.8.8 v2 candidate. No model request is made. Public output contains
only opaque identifiers, hashes, bounded diagnostics and aggregate proxy
metrics; it never contains questions, answers, evidence or credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from benchmarks import run_phase11_8_recovery as phase11_8
    from benchmarks.phase11_7_dataset import (
        PHASE11_7_SUITE,
        PHASE12_RESERVE_SUITE,
    )
    from benchmarks.phase11_8_2_candidate import (
        balanced_baseline_project_blocks,
        candidate_project_blocks,
        rendered_evidence_chars,
    )
    from benchmarks.phase11_8_8_projection_candidate import (
        OMISSION_SEPARATOR,
        PROJECTION_FAMILY,
        candidate_project_blocks_v2,
    )
except ModuleNotFoundError:
    import run_phase11_8_recovery as phase11_8  # type: ignore[no-redef]
    from phase11_7_dataset import (  # type: ignore[import-not-found,no-redef]
        PHASE11_7_SUITE,
        PHASE12_RESERVE_SUITE,
    )
    from phase11_8_2_candidate import (  # type: ignore[no-redef]
        balanced_baseline_project_blocks,
        candidate_project_blocks,
        rendered_evidence_chars,
    )
    from phase11_8_8_projection_candidate import (  # type: ignore[no-redef]
        OMISSION_SEPARATOR,
        PROJECTION_FAMILY,
        candidate_project_blocks_v2,
    )

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-8-projection-calibration-v1"

LOCKED_PROTOCOL_SHA256 = "11a8fe99a3e418eb4161978928f2d682a2adcf6b59b3bcc7b7641c26b601a653"
LOCKED_MANIFEST_SHA256 = "da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e"
LOCKED_RESERVE_MANIFEST_SHA256 = "472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee"
LOCKED_PHASE11_8_3_RESULT_SHA256 = (
    "167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c"
)
LOCKED_CANDIDATE_V1_SHA256 = "0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e"
LOCKED_CANDIDATE_V2_SHA256 = "117968687a0c0c150acef42f997967d10b04006d14ed0efa9de87c9c08b1909e"
LOCKED_FIXTURE_SHA256 = "8955ac33c89c2e16a474182c14eac8df5acaf649642f4dd90a313cf6227db614"

EQUAL_CAP_ARM = "equal_cap"
V1_ARM = "rank_weighted_query_window_head_tail_v1"
V2_ARM = PROJECTION_FAMILY
PROJECTION_ARMS = (EQUAL_CAP_ARM, V1_ARM, V2_ARM)

EXPECTED_CASE_COUNT = phase11_8.PHASE11_7_CASE_COUNT
EXPECTED_RETRIEVAL_OPERATIONS = EXPECTED_CASE_COUNT
MAXIMUM_TAVILY_REQUESTS = EXPECTED_CASE_COUNT
EXPECTED_PROJECTION_REPLAYS = 3
MINIMUM_SELECTED_ANSWER_COVERAGE = 20
MINIMUM_V2_ANSWER_COVERAGE = 20
MINIMUM_V2_PAIRED_NET_GAIN = 2
MINIMUM_V2_SELECTED_RETENTION = 0.95


def _sha256_file(path: Path) -> str:
    return phase11_8.sha256_bytes(path.read_bytes())


def _assert_locked_hash(path: Path, expected: str, label: str) -> str:
    if expected.startswith("__") and expected.endswith("__"):
        raise ValueError(f"{label} checksum lock is unresolved: {expected}")
    observed = _sha256_file(path)
    if observed != expected:
        raise ValueError(
            f"{label} checksum does not match the frozen lock: "
            f"expected {expected}, observed {observed}"
        )
    return observed


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not a readable JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return value


def validate_locked_sources(arguments: argparse.Namespace) -> dict[str, Any]:
    """Validate every immutable input without loading a dataset or using a key."""

    hashes = {
        "protocol": _assert_locked_hash(
            arguments.protocol,
            LOCKED_PROTOCOL_SHA256,
            "Phase 11.8.8 protocol",
        ),
        "manifest": _assert_locked_hash(
            arguments.manifest,
            LOCKED_MANIFEST_SHA256,
            "Phase 11.7 manifest",
        ),
        "reserve_manifest": _assert_locked_hash(
            arguments.reserve_manifest,
            LOCKED_RESERVE_MANIFEST_SHA256,
            "Phase 12 reserve manifest",
        ),
        "phase11_8_3_result": _assert_locked_hash(
            arguments.phase11_8_3_result,
            LOCKED_PHASE11_8_3_RESULT_SHA256,
            "Phase 11.8.3 result",
        ),
        "candidate_v1": _assert_locked_hash(
            arguments.candidate_v1,
            LOCKED_CANDIDATE_V1_SHA256,
            "Phase 11.8.2 projection candidate",
        ),
        "candidate_v2": _assert_locked_hash(
            arguments.candidate_v2,
            LOCKED_CANDIDATE_V2_SHA256,
            "Phase 11.8.8 projection candidate",
        ),
        "fixture": _assert_locked_hash(
            arguments.fixture,
            LOCKED_FIXTURE_SHA256,
            "Phase 11.8.8 adversarial fixture",
        ),
    }

    manifest = _load_json_object(arguments.manifest, "Phase 11.7 manifest")
    reserve = _load_json_object(arguments.reserve_manifest, "Phase 12 reserve manifest")
    historical = _load_json_object(
        arguments.phase11_8_3_result,
        "Phase 11.8.3 result",
    )
    fixture = _load_json_object(arguments.fixture, "Phase 11.8.8 adversarial fixture")

    manifest_selection = manifest.get("selection")
    if (
        manifest.get("suite") != PHASE11_7_SUITE
        or not isinstance(manifest_selection, dict)
        or manifest_selection.get("case_count") != EXPECTED_CASE_COUNT
        or not isinstance(manifest.get("cases"), list)
        or len(manifest["cases"]) != EXPECTED_CASE_COUNT
    ):
        raise ValueError("Phase 11.7 manifest does not preserve the locked 24-case suite")

    reserve_selection = reserve.get("selection")
    sealed_cases = reserve.get("sealed_cases")
    if (
        reserve.get("suite") != PHASE12_RESERVE_SUITE
        or not isinstance(reserve_selection, dict)
        or reserve_selection.get("case_count") != 96
        or not isinstance(sealed_cases, list)
        or len(sealed_cases) != 96
    ):
        raise ValueError("Phase 12 reserve does not preserve its sealed 96-case boundary")

    historical_decision = historical.get("decision")
    if not isinstance(historical_decision, dict):
        raise ValueError("Phase 11.8.3 result has no bounded decision object")
    historical_gates = historical_decision.get("gates")
    if not isinstance(historical_gates, dict):
        raise ValueError("Phase 11.8.3 result has no gate map")
    passed_historical_gates = sum(
        isinstance(gate, dict) and gate.get("passed") is True for gate in historical_gates.values()
    )
    if (
        historical.get("benchmark") != "evidencemesh-phase11-8-3-factorial-calibration-v1"
        or len(historical_gates) != 14
        or passed_historical_gates != 10
        or historical_decision.get("phase11_8_3_candidate_passed") is not False
        or historical_decision.get("phase12_authorized") is not False
        or historical_decision.get("release_decision") != "no-go"
    ):
        raise ValueError("Phase 11.8.3 historical 10/14 no-go boundary changed")

    fixture_defaults = fixture.get("projection_defaults")
    fixture_cases = fixture.get("cases")
    if (
        fixture.get("benchmark") != "evidencemesh-phase11-8-8-offline-projection-fixtures-v1"
        or fixture.get("authored_after_phase11_8") is not True
        or fixture.get("contains_phase11_7_or_phase12_content") is not False
        or fixture.get("predictive_quality_claim_allowed") is not False
        or not isinstance(fixture_defaults, dict)
        or not isinstance(fixture_defaults.get("budget_chars"), int)
        or fixture_defaults["budget_chars"] <= 0
        or not isinstance(fixture_defaults.get("max_block_chars"), int)
        or fixture_defaults["max_block_chars"] <= 0
        or not isinstance(fixture_defaults.get("min_block_chars"), int)
        or not 0 < fixture_defaults["min_block_chars"] <= fixture_defaults["max_block_chars"]
        or not isinstance(fixture_cases, list)
        or not fixture_cases
    ):
        raise ValueError("Phase 11.8.8 fixture disclosure or defaults changed")
    historical_case_ids = {
        str(item["case_id"])
        for item in [*manifest["cases"], *sealed_cases]
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }
    fixture_rendered = json.dumps(fixture, ensure_ascii=False, sort_keys=True)
    if any(case_id in fixture_rendered for case_id in historical_case_ids):
        raise ValueError("Phase 11.8.8 fixture contains a historical or sealed case ID")

    return {
        "status": "phase11_8_8_protocol_lock_valid",
        "benchmark": BENCHMARK_NAME,
        "hashes": hashes,
        "case_count": EXPECTED_CASE_COUNT,
        "projection_arms": list(PROJECTION_ARMS),
        "projection_replays": EXPECTED_PROJECTION_REPLAYS,
        "planned_retrieval_operations": EXPECTED_RETRIEVAL_OPERATIONS,
        "maximum_tavily_requests": MAXIMUM_TAVILY_REQUESTS,
        "network_requests": 0,
        "provider_calls": 0,
        "tavily_requests": 0,
        "model_calls": 0,
        "gemini_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
        "secrets_bound": 0,
        "protocol_publication_authorizes_live": False,
        "historical_phase11_8_3_result": "fail_10_of_14",
        "phase11_9_protocol_may_be_frozen": False,
        "phase12_authorized": False,
        "merge_allowed": False,
        "release_allowed": False,
        "release_decision": "no-go",
    }


def projection_family(arm: str) -> str:
    if arm in PROJECTION_ARMS:
        return arm
    raise ValueError(f"unknown Phase 11.8.8 projection arm: {arm}")


def project_blocks(
    arm: str,
    question: str,
    blocks: tuple[phase11_8.EvidenceBlock, ...],
    *,
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
) -> tuple[phase11_8.EvidenceBlock, ...]:
    """Project one selected packet locally without receiving an expected answer."""

    if arm == EQUAL_CAP_ARM:
        return balanced_baseline_project_blocks(
            blocks,
            evidence_budget_chars,
            max_block_chars,
        )
    if arm == V1_ARM:
        return candidate_project_blocks(
            blocks,
            question,
            evidence_budget_chars,
            max_block_chars,
            min_block_chars=min_block_chars,
        )
    if arm == V2_ARM:
        return candidate_project_blocks_v2(
            blocks,
            question,
            evidence_budget_chars,
            max_block_chars,
            min_block_chars=min_block_chars,
        )
    raise ValueError(f"unknown Phase 11.8.8 projection arm: {arm}")


def _block_metadata(block: phase11_8.EvidenceBlock) -> tuple[Any, ...]:
    return (
        block.citation_id,
        block.title,
        block.url,
        tuple(block.providers),
    )


def projection_metadata_preserved(
    selected: tuple[phase11_8.EvidenceBlock, ...],
    projected: tuple[phase11_8.EvidenceBlock, ...],
) -> bool:
    """Require projected blocks to be an ordered metadata-preserving subset."""

    selected_by_id = {block.citation_id: block for block in selected}
    if len(selected_by_id) != len(selected):
        return False
    projected_ids = [block.citation_id for block in projected]
    if len(projected_ids) != len(set(projected_ids)):
        return False
    try:
        positions = [
            next(
                index
                for index, selected_block in enumerate(selected)
                if selected_block.citation_id == citation_id
            )
            for citation_id in projected_ids
        ]
    except StopIteration:
        return False
    return positions == sorted(positions) and all(
        _block_metadata(block) == _block_metadata(selected_by_id[block.citation_id])
        for block in projected
    )


def projection_text_is_source_preserving(
    selected: tuple[phase11_8.EvidenceBlock, ...],
    projected: tuple[phase11_8.EvidenceBlock, ...],
) -> bool:
    """Accept only exact ordered source substrings and the fixed omission marker."""

    selected_by_id = {block.citation_id: block for block in selected}
    for block in projected:
        source = selected_by_id.get(block.citation_id)
        if source is None:
            return False
        cursor = 0
        for segment in block.text.split(OMISSION_SEPARATOR):
            if not segment:
                return False
            position = source.text.find(segment, cursor)
            if position < 0:
                return False
            cursor = position + len(segment)
    return True


def public_projection_outcome(
    row: phase11_8.BenchmarkRow,
    bundle: phase11_8.ArmBundle,
    *,
    arm: str,
    raw_pool_hash: str,
    evidence_budget_chars: int,
    max_block_chars: int,
    min_block_chars: int,
    projection_replays: int,
) -> dict[str, Any]:
    projections = tuple(
        project_blocks(
            arm,
            row.question,
            bundle.blocks,
            evidence_budget_chars=evidence_budget_chars,
            max_block_chars=max_block_chars,
            min_block_chars=min_block_chars,
        )
        for _ in range(projection_replays)
    )
    included = projections[0]
    packet_hashes = {phase11_8.prompt_packet_sha256(projected) for projected in projections}
    rendered_chars = rendered_evidence_chars(included)
    return {
        "case_id": row.id,
        "arm": projection_family(arm),
        "status": bundle.status,
        "available": bundle.available,
        "raw_result_count": bundle.raw_result_count,
        "fused_result_count": bundle.fused_result_count,
        "selected_result_count": bundle.selected_result_count,
        "prompt_result_count": len(included),
        "unique_domains": bundle.unique_domains,
        "selected_tavily_count": bundle.selected_tavily_count,
        "prompt_tavily_count": sum("tavily" in block.providers for block in included),
        "answer_key_in_selected_evidence": phase11_8.answer_covered(
            row.answers,
            (block.text for block in bundle.blocks),
        ),
        "answer_key_in_prompt_evidence": phase11_8.answer_covered(
            row.answers,
            (block.text for block in included),
        ),
        "raw_pool_sha256": raw_pool_hash,
        "selected_packet_sha256": phase11_8.prompt_packet_sha256(bundle.blocks),
        "prompt_packet_sha256": phase11_8.prompt_packet_sha256(included),
        "rendered_evidence_chars": rendered_chars,
        "budget_compliant": rendered_chars <= evidence_budget_chars,
        "budget_gate_applicable": arm != EQUAL_CAP_ARM,
        "historical_equal_cap_over_budget": (
            arm == EQUAL_CAP_ARM and rendered_chars > evidence_budget_chars
        ),
        "deterministic_replays": len(packet_hashes) == 1,
        "replay_count": projection_replays,
        "metadata_preserved": projection_metadata_preserved(
            bundle.blocks,
            included,
        ),
        "source_text_preserved": projection_text_is_source_preserving(
            bundle.blocks,
            included,
        ),
        "retrieval_latency_ms": bundle.retrieval_latency_ms,
        "error_kind": bundle.error_kind,
    }


def aggregate_projection(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for arm in PROJECTION_ARMS:
        rows = [outcome for outcome in outcomes if outcome["arm"] == arm]
        metrics[arm] = {
            "case_count": len(rows),
            "availability": phase11_8.ratio(
                sum(bool(row["available"]) for row in rows),
                len(rows),
            ),
            "answer_key_in_selected_evidence": phase11_8.ratio(
                sum(bool(row["answer_key_in_selected_evidence"]) for row in rows),
                len(rows),
            ),
            "answer_key_in_prompt_evidence": phase11_8.ratio(
                sum(bool(row["answer_key_in_prompt_evidence"]) for row in rows),
                len(rows),
            ),
            "budget_compliance": phase11_8.ratio(
                sum(bool(row["budget_compliant"]) for row in rows),
                len(rows),
            ),
            "deterministic_replays": phase11_8.ratio(
                sum(bool(row["deterministic_replays"]) for row in rows),
                len(rows),
            ),
            "metadata_preservation": phase11_8.ratio(
                sum(bool(row["metadata_preserved"]) for row in rows),
                len(rows),
            ),
            "source_text_preservation": phase11_8.ratio(
                sum(bool(row["source_text_preserved"]) for row in rows),
                len(rows),
            ),
            "historical_equal_cap_over_budget": phase11_8.ratio(
                sum(bool(row["historical_equal_cap_over_budget"]) for row in rows),
                len(rows),
            ),
            "mean_selected_result_count": round(
                statistics.fmean(int(row["selected_result_count"]) for row in rows),
                3,
            ),
            "mean_prompt_result_count": round(
                statistics.fmean(int(row["prompt_result_count"]) for row in rows),
                3,
            ),
            "mean_rendered_evidence_chars": round(
                statistics.fmean(int(row["rendered_evidence_chars"]) for row in rows),
                3,
            ),
        }
    return metrics


def selected_proxy_retention(
    outcomes: list[dict[str, Any]],
    *,
    arm: str,
) -> dict[str, Any]:
    eligible = [
        outcome
        for outcome in outcomes
        if outcome["arm"] == arm and outcome["answer_key_in_selected_evidence"]
    ]
    retained = sum(bool(outcome["answer_key_in_prompt_evidence"]) for outcome in eligible)
    return phase11_8.ratio(retained, len(eligible))


def paired_projection_metrics(
    outcomes: list[dict[str, Any]],
    *,
    candidate_arm: str,
    baseline_arm: str,
) -> dict[str, Any]:
    records = {(str(outcome["case_id"]), str(outcome["arm"])): outcome for outcome in outcomes}
    case_ids = sorted({case_id for case_id, _arm in records})
    candidate_wins = 0
    baseline_wins = 0
    shared_hits = 0
    shared_misses = 0
    for case_id in case_ids:
        candidate = bool(records[(case_id, candidate_arm)]["answer_key_in_prompt_evidence"])
        baseline = bool(records[(case_id, baseline_arm)]["answer_key_in_prompt_evidence"])
        candidate_wins += candidate and not baseline
        baseline_wins += baseline and not candidate
        shared_hits += candidate and baseline
        shared_misses += not candidate and not baseline
    return {
        "field": "answer_key_in_prompt_evidence",
        "candidate_arm": candidate_arm,
        "baseline_arm": baseline_arm,
        "eligible_pairs": len(case_ids),
        "candidate_wins": candidate_wins,
        "baseline_wins": baseline_wins,
        "shared_hits": shared_hits,
        "shared_misses": shared_misses,
        "net_gain": candidate_wins - baseline_wins,
    }


def packet_identity(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for outcome in outcomes:
        by_case.setdefault(str(outcome["case_id"]), {})[str(outcome["arm"])] = outcome
    raw_pool_matching_cases = 0
    selected_packet_matching_cases = 0
    deterministic_metadata_source_cases = 0
    candidate_budget_cases = 0
    equal_cap_over_budget_cases = 0
    for arms in by_case.values():
        if set(arms) != set(PROJECTION_ARMS):
            continue
        if len({str(value["raw_pool_sha256"]) for value in arms.values()}) == 1:
            raw_pool_matching_cases += 1
        if len({str(value["selected_packet_sha256"]) for value in arms.values()}) == 1:
            selected_packet_matching_cases += 1
        if all(
            bool(value["deterministic_replays"])
            and bool(value["metadata_preserved"])
            and bool(value["source_text_preserved"])
            and int(value["replay_count"]) == EXPECTED_PROJECTION_REPLAYS
            for value in arms.values()
        ):
            deterministic_metadata_source_cases += 1
        if all(bool(arms[arm]["budget_compliant"]) for arm in (V1_ARM, V2_ARM)):
            candidate_budget_cases += 1
        if bool(arms[EQUAL_CAP_ARM]["historical_equal_cap_over_budget"]):
            equal_cap_over_budget_cases += 1
    return {
        "denominator": len(by_case),
        "raw_pool_matching_cases": raw_pool_matching_cases,
        "selected_packet_matching_cases": selected_packet_matching_cases,
        "deterministic_metadata_source_cases": deterministic_metadata_source_cases,
        "candidate_budget_cases": candidate_budget_cases,
        "equal_cap_over_budget_cases": equal_cap_over_budget_cases,
        "shared_packet_identity_passed": (
            len(by_case) == EXPECTED_CASE_COUNT
            and raw_pool_matching_cases == EXPECTED_CASE_COUNT
            and selected_packet_matching_cases == EXPECTED_CASE_COUNT
        ),
        "projection_invariants_passed": (
            len(by_case) == EXPECTED_CASE_COUNT
            and deterministic_metadata_source_cases == EXPECTED_CASE_COUNT
            and candidate_budget_cases == EXPECTED_CASE_COUNT
        ),
    }


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield str(key)
            yield from _walk_keys(nested)
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for nested in value:
            yield from _walk_keys(nested)


def audit_public_payload(
    public_payload: dict[str, Any],
    *,
    rows: list[phase11_8.BenchmarkRow],
    tavily_api_key: str,
    reserve_manifest: dict[str, Any],
) -> dict[str, Any]:
    rendered = json.dumps(public_payload, ensure_ascii=False, sort_keys=True)
    sealed_cases = reserve_manifest.get("sealed_cases")
    questions_in_report = any(
        json.dumps(row.question, ensure_ascii=False) in rendered for row in rows
    )
    reference_answers_in_report = any(
        json.dumps(answer, ensure_ascii=False) in rendered
        for row in rows
        for answer in row.answers
        if answer
    )
    gold_urls_in_report = any(
        json.dumps(url, ensure_ascii=False) in rendered
        for row in rows
        for url in row.gold_urls
        if url
    )
    phase12_ids_in_report = any(
        isinstance(item, dict)
        and isinstance(item.get("case_id"), str)
        and json.dumps(item["case_id"]) in rendered
        for item in sealed_cases or []
    )
    forbidden_keys = {
        "question",
        "questions",
        "answer",
        "answers",
        "reference_answer",
        "reference_answers",
        "title",
        "url",
        "snippet",
        "evidence",
        "prompt",
        "raw_results",
        "api_key",
        "authorization",
        "provider_message",
        "exception_message",
    }
    observed_keys = set(_walk_keys(public_payload))
    leaked_keys = sorted(forbidden_keys & observed_keys)
    private_value_match_count = sum(
        (
            bool(tavily_api_key and tavily_api_key in rendered),
            questions_in_report,
            reference_answers_in_report,
            gold_urls_in_report,
            phase12_ids_in_report,
        )
    )
    return {
        "passed": private_value_match_count == 0 and not leaked_keys,
        "questions_in_report": questions_in_report,
        "reference_answers_in_report": reference_answers_in_report,
        "retrieved_titles_urls_or_snippets_in_report": (gold_urls_in_report or bool(leaked_keys)),
        "api_key_in_report": bool(tavily_api_key and tavily_api_key in rendered),
        "phase12_reserved_case_ids_in_report": phase12_ids_in_report,
        "forbidden_public_field_count": len(leaked_keys),
        "private_value_match_count": private_value_match_count,
    }


def build_decision(
    metrics: dict[str, Any],
    paired_vs_equal: dict[str, Any],
    paired_vs_v1: dict[str, Any],
    v2_retention: dict[str, Any],
    identity: dict[str, Any],
    traffic: dict[str, int],
    privacy: dict[str, Any],
) -> dict[str, Any]:
    availability = int(metrics[V2_ARM]["availability"]["numerator"])
    selected_hits = int(metrics[V2_ARM]["answer_key_in_selected_evidence"]["numerator"])
    v2_hits = int(metrics[V2_ARM]["answer_key_in_prompt_evidence"]["numerator"])
    gates = {
        "locked_plan_and_exact_traffic": {
            "passed": (
                traffic["case_retrieval_operations"] == EXPECTED_RETRIEVAL_OPERATIONS
                and traffic["provider_query_calls"] == MAXIMUM_TAVILY_REQUESTS
                and traffic["tavily_requests"] == MAXIMUM_TAVILY_REQUESTS
                and traffic["other_provider_requests"] == 0
                and traffic["model_requests"] == 0
                and traffic["gemini_requests"] == 0
                and traffic["retries"] == 0
                and traffic["fallback_requests"] == 0
                and traffic["repair_requests"] == 0
            ),
            "observed": traffic,
            "planned_retrieval_operations": EXPECTED_RETRIEVAL_OPERATIONS,
            "maximum_tavily_requests": MAXIMUM_TAVILY_REQUESTS,
        },
        "availability_24_of_24": {
            "passed": availability == EXPECTED_CASE_COUNT,
            "observed": availability,
            "required": EXPECTED_CASE_COUNT,
        },
        "one_raw_and_selected_packet_per_case": {
            "passed": bool(identity["shared_packet_identity_passed"]),
            "observed": identity,
        },
        "determinism_budget_and_metadata_24_of_24": {
            "passed": bool(identity["projection_invariants_passed"]),
            "observed": identity,
        },
        "selected_evidence_proxy_at_least_20_of_24": {
            "passed": selected_hits >= MINIMUM_SELECTED_ANSWER_COVERAGE,
            "observed": selected_hits,
            "required": MINIMUM_SELECTED_ANSWER_COVERAGE,
            "meaning": "retrieval ceiling prerequisite for a projection score",
        },
        "v2_prompt_proxy_at_least_20_of_24": {
            "passed": v2_hits >= MINIMUM_V2_ANSWER_COVERAGE,
            "observed": v2_hits,
            "required": MINIMUM_V2_ANSWER_COVERAGE,
        },
        "v2_retains_at_least_95_percent_of_selected_proxy": {
            "passed": (
                v2_retention["rate"] is not None
                and float(v2_retention["rate"]) >= MINIMUM_V2_SELECTED_RETENTION
            ),
            "observed": v2_retention,
            "required_rate": MINIMUM_V2_SELECTED_RETENTION,
        },
        "v2_paired_gain_at_least_2_vs_equal_cap": {
            "passed": int(paired_vs_equal["net_gain"]) >= MINIMUM_V2_PAIRED_NET_GAIN,
            "observed": paired_vs_equal,
            "required_net_gain": MINIMUM_V2_PAIRED_NET_GAIN,
        },
        "v2_paired_gain_at_least_2_vs_v1": {
            "passed": int(paired_vs_v1["net_gain"]) >= MINIMUM_V2_PAIRED_NET_GAIN,
            "observed": paired_vs_v1,
            "required_net_gain": MINIMUM_V2_PAIRED_NET_GAIN,
        },
        "zero_model_retry_fallback_or_repair": {
            "passed": all(
                traffic[name] == 0
                for name in (
                    "model_requests",
                    "gemini_requests",
                    "retries",
                    "fallback_requests",
                    "repair_requests",
                )
            ),
            "observed": {
                name: traffic[name]
                for name in (
                    "model_requests",
                    "gemini_requests",
                    "retries",
                    "fallback_requests",
                    "repair_requests",
                )
            },
        },
        "public_report_privacy": {
            "passed": privacy.get("passed") is True,
            "observed": privacy,
        },
        "phase12_remains_sealed": {
            "passed": True,
            "phase12_cases_used": False,
            "phase12_questions_or_answers_materialized": False,
        },
        "product_and_release_boundaries_unchanged": {
            "passed": True,
            "product_profiles_changed": False,
            "phase11_9_protocol_may_be_frozen": False,
            "merge_allowed": False,
            "release_allowed": False,
        },
    }
    candidate_passed = all(bool(gate["passed"]) for gate in gates.values())
    if selected_hits < MINIMUM_SELECTED_ANSWER_COVERAGE:
        diagnostic_status = "retrieval_limited_inconclusive"
    elif candidate_passed:
        diagnostic_status = "projection_calibration_pass"
    else:
        diagnostic_status = "projection_candidate_fail"
    return {
        "gates": gates,
        "phase11_8_8_projection_candidate_passed": candidate_passed,
        "diagnostic_status": diagnostic_status,
        "historical_phase11_8_3_result_changed": False,
        "future_live_rerun_authorized": False,
        "quality_profile_promotion_allowed": False,
        "quality_profile_promoted": False,
        "community_profile_unchanged": True,
        "quality_profile_unchanged": True,
        "users_choose_provider_model_and_credentials": True,
        "phase11_9_protocol_may_be_frozen": False,
        "phase11_9_executed": False,
        "phase12_authorized": False,
        "phase12_executed": False,
        "external_competitor_benchmark_allowed": False,
        "public_alpha_allowed": False,
        "superiority_claim_allowed": False,
        "merge_allowed": False,
        "release_allowed": False,
        "release_decision": "no-go",
        "reason": (
            "Phase 11.8.8 reuses observed calibration selectors and measures "
            "projection proxies only. It cannot freeze Phase 11.9, access Phase 12, "
            "change product profiles, merge or release."
        ),
    }


def validate_arguments(arguments: argparse.Namespace) -> None:
    locked_values = {
        "provider_max_results": (arguments.provider_max_results, 20),
        "selection_limit": (arguments.selection_limit, 20),
        "max_per_domain": (arguments.max_per_domain, 3),
        "evidence_budget_chars": (arguments.evidence_budget_chars, 12_000),
        "max_block_chars": (arguments.max_block_chars, 1_500),
        "min_block_chars": (arguments.min_block_chars, 192),
        "projection_replays": (
            arguments.projection_replays,
            EXPECTED_PROJECTION_REPLAYS,
        ),
        "retrieval_wall_time_seconds": (
            arguments.retrieval_wall_time_seconds,
            30.0,
        ),
        "retrieval_pause_seconds": (arguments.retrieval_pause_seconds, 0.5),
        "request_timeout_seconds": (arguments.request_timeout_seconds, 15.0),
    }
    changed = [
        f"{name}={actual!r} (expected {expected!r})"
        for name, (actual, expected) in locked_values.items()
        if actual != expected
    ]
    if changed:
        raise ValueError("Phase 11.8.8 locked arguments changed: " + ", ".join(changed))
    if arguments.tavily_api_key_env != "TAVILY_API_KEY":
        raise ValueError("Phase 11.8.8 requires TAVILY_API_KEY")
    if arguments.check_only and arguments.authorize_live_run:
        raise ValueError("--check-only and --authorize-live-run are mutually exclusive")
    if arguments.authorize_live_run and (arguments.dataset is None or arguments.output is None):
        raise ValueError("live execution requires --dataset and --output")


async def retrieve_all_fail_fast(
    rows: list[phase11_8.BenchmarkRow],
    *,
    tavily_api_key: str,
    cache_root: Path,
    provider_max_results: int,
    selection_limit: int,
    max_per_domain: int,
    request_timeout_seconds: float,
    wall_time_seconds: float,
    pause_seconds: float,
    progress: bool,
) -> tuple[
    dict[tuple[str, str], phase11_8.ArmBundle],
    dict[str, str],
    list[dict[str, Any]],
    dict[str, int],
    dict[str, Any],
    str | None,
]:
    """Reuse Phase 11.8 retrieval one case at a time and stop on first failure."""

    bundles: dict[tuple[str, str], phase11_8.ArmBundle] = {}
    raw_hashes: dict[str, str] = {}
    diagnostics: list[dict[str, Any]] = []
    traffic = {
        "case_retrieval_operations": 0,
        "provider_query_calls": 0,
        "tavily_requests": 0,
    }
    health: dict[str, Any] = {}
    aborted_reason: str | None = None
    for index, row in enumerate(rows):
        if index and pause_seconds:
            await asyncio.sleep(pause_seconds)
        (
            case_bundles,
            case_hashes,
            case_diagnostics,
            case_traffic,
            health,
        ) = await phase11_8.retrieve_all(
            [row],
            tavily_api_key=tavily_api_key,
            cache_root=cache_root,
            provider_max_results=provider_max_results,
            current_selection_limit=selection_limit,
            expanded_selection_limit=selection_limit,
            max_per_domain=max_per_domain,
            request_timeout_seconds=request_timeout_seconds,
            wall_time_seconds=wall_time_seconds,
            pause_seconds=0.0,
            progress=progress,
        )
        bundles.update(case_bundles)
        raw_hashes.update(case_hashes)
        diagnostics.extend(case_diagnostics)
        for name in traffic:
            traffic[name] += int(case_traffic[name])

        diagnostic = case_diagnostics[0]
        failure_counts = diagnostic.get("provider_failure_kind_counts")
        bounded_failure_kind = diagnostic.get("error_kind")
        if not bounded_failure_kind and isinstance(failure_counts, dict):
            bounded_kinds = sorted(
                str(kind)
                for counts in failure_counts.values()
                if isinstance(counts, dict)
                for kind, count in counts.items()
                if isinstance(count, int) and count > 0
            )
            bounded_failure_kind = bounded_kinds[0] if bounded_kinds else None
        if bounded_failure_kind:
            aborted_reason = str(bounded_failure_kind)
            break
    return (
        bundles,
        raw_hashes,
        diagnostics,
        traffic,
        health,
        aborted_reason,
    )


async def run(arguments: argparse.Namespace) -> dict[str, Any]:
    """Execute the single-shot Tavily calibration after all locks validate."""

    validate_arguments(arguments)
    if not arguments.authorize_live_run:
        raise ValueError("live execution requires the explicit --authorize-live-run flag")
    lock_validation = validate_locked_sources(arguments)
    if arguments.dataset is None:
        raise ValueError("live execution requires --dataset")
    if arguments.output is None:
        raise ValueError("live execution requires --output")
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite existing Phase 11.8.8 result: {arguments.output}"
        )

    rows, manifest, dataset_metadata, reserve_metadata = phase11_8.load_phase11_7_rows(
        arguments.dataset,
        arguments.manifest,
        arguments.reserve_manifest,
        root=REPOSITORY_ROOT,
        expected_manifest_sha256=LOCKED_MANIFEST_SHA256,
        expected_reserve_manifest_sha256=LOCKED_RESERVE_MANIFEST_SHA256,
    )
    tavily_api_key = os.getenv(arguments.tavily_api_key_env)
    if not tavily_api_key:
        raise ValueError("Tavily API key is not configured")

    cache_root = Path(arguments.cache_root)
    await asyncio.to_thread(cache_root.mkdir, parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    (
        bundles,
        raw_hashes,
        retrieval_diagnostics,
        retrieval_traffic,
        health,
        aborted_reason,
    ) = await retrieve_all_fail_fast(
        rows,
        tavily_api_key=tavily_api_key,
        cache_root=cache_root,
        provider_max_results=arguments.provider_max_results,
        selection_limit=arguments.selection_limit,
        max_per_domain=arguments.max_per_domain,
        request_timeout_seconds=arguments.request_timeout_seconds,
        wall_time_seconds=arguments.retrieval_wall_time_seconds,
        pause_seconds=arguments.retrieval_pause_seconds,
        progress=arguments.progress,
    )
    outcomes = [
        public_projection_outcome(
            row,
            bundles[(row.id, phase11_8.EXPANDED_ARM)],
            arm=arm,
            raw_pool_hash=raw_hashes[row.id],
            evidence_budget_chars=arguments.evidence_budget_chars,
            max_block_chars=arguments.max_block_chars,
            min_block_chars=arguments.min_block_chars,
            projection_replays=arguments.projection_replays,
        )
        for row in rows[: len(retrieval_diagnostics)]
        for arm in PROJECTION_ARMS
    ]
    metrics = aggregate_projection(outcomes)
    identity = packet_identity(outcomes)
    paired_vs_equal = paired_projection_metrics(
        outcomes,
        candidate_arm=V2_ARM,
        baseline_arm=EQUAL_CAP_ARM,
    )
    paired_vs_v1 = paired_projection_metrics(
        outcomes,
        candidate_arm=V2_ARM,
        baseline_arm=V1_ARM,
    )
    v2_retention = selected_proxy_retention(outcomes, arm=V2_ARM)
    traffic = {
        **retrieval_traffic,
        "planned_retrieval_operations": EXPECTED_RETRIEVAL_OPERATIONS,
        "maximum_tavily_requests": MAXIMUM_TAVILY_REQUESTS,
        "other_provider_requests": max(
            0,
            int(retrieval_traffic["provider_query_calls"])
            - int(retrieval_traffic["tavily_requests"]),
        ),
        "model_requests": 0,
        "gemini_requests": 0,
        "token_count_requests": 0,
        "retries": 0,
        "fallback_requests": 0,
        "repair_requests": 0,
    }

    public_payload = {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": "observed-case Tavily-only three-projection calibration",
        "suite": {
            "manifest_sha256": LOCKED_MANIFEST_SHA256,
            "sample_count": len(rows),
            "case_ids": [row.id for row in rows],
            "topic_distribution": manifest["topic_distribution"],
            "answer_type_distribution": manifest["answer_type_distribution"],
            "purpose": (
                "corrective projection calibration on already-observed Phase 11.7 selectors"
            ),
            "fresh_for_phase11_8_8": False,
            "historical_selected_packets_replayed": False,
            "phase12_cases_used": False,
        },
        "dataset": dataset_metadata,
        "phase12_reserve": reserve_metadata,
        "protocol": {
            "path": str(arguments.protocol),
            "sha256": LOCKED_PROTOCOL_SHA256,
            "projection_arms": list(PROJECTION_ARMS),
            "control_arm": EQUAL_CAP_ARM,
            "historical_candidate_arm": V1_ARM,
            "candidate_arm": V2_ARM,
            "projection_replays": arguments.projection_replays,
            "provider_bundle": ["tavily"],
            "provider_max_results": arguments.provider_max_results,
            "selection_limit": arguments.selection_limit,
            "max_per_domain": arguments.max_per_domain,
            "evidence_prompt_budget_chars": arguments.evidence_budget_chars,
            "max_block_chars": arguments.max_block_chars,
            "min_block_chars": arguments.min_block_chars,
            "one_raw_tavily_pool_per_case": True,
            "one_selected_packet_per_case": True,
            "provider_request_repeated_per_projection": False,
            "cache": False,
            "provider_wall_timeout_seconds": arguments.request_timeout_seconds,
            "provider_transport_timeout_seconds": {
                "connect": 5.0,
                "read": 12.0,
                "write": 10.0,
                "pool": 5.0,
            },
            "retrieval_outer_wall_timeout_seconds": (arguments.retrieval_wall_time_seconds),
            "abort_on_first_provider_failure": True,
            "models": [],
            "model_requests": 0,
            "retry_policy": "none; no retry, fallback or repair",
            "explicit_live_authorization_required": True,
            "protocol_publication_authorizes_live": False,
            "quality_profile_after_run": "unchanged regardless of result",
            "community_profile_unchanged": True,
            "users_choose_provider_model_and_credentials": True,
            "scoring": {
                "selected_answer_proxy": (
                    "normalized reference-answer substring in selected evidence"
                ),
                "prompt_answer_proxy": (
                    "normalized reference-answer substring in projected evidence"
                ),
                "official_simpleqa_evaluation": "not run",
            },
        },
        "lock_validation": lock_validation,
        "environment": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "commit_sha": phase11_8.commit_sha(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "network_region": arguments.network_region,
            "dependency_versions": {
                package: phase11_8.package_version(package)
                for package in ("fastmcp", "httpx", "pydantic")
            },
        },
        "traffic": traffic,
        "retrieval_health_after": health,
        "retrieval_diagnostics": retrieval_diagnostics,
        "projection_metrics": metrics,
        "v2_selected_proxy_retention": v2_retention,
        "packet_identity": identity,
        "paired_v2_vs_equal_cap": paired_vs_equal,
        "paired_v2_vs_v1": paired_vs_v1,
        "projection_outcomes": outcomes,
        "aborted": aborted_reason is not None,
        "aborted_reason": aborted_reason,
    }
    reserve_manifest = _load_json_object(
        arguments.reserve_manifest,
        "Phase 12 reserve manifest",
    )
    privacy = audit_public_payload(
        public_payload,
        rows=rows,
        tavily_api_key=tavily_api_key,
        reserve_manifest=reserve_manifest,
    )
    decision = build_decision(
        metrics,
        paired_vs_equal,
        paired_vs_v1,
        v2_retention,
        identity,
        traffic,
        privacy,
    )
    return {
        **public_payload,
        "privacy": privacy,
        "decision": decision,
        "warnings": [
            (
                "Phase 11.8.8 reuses observed selectors and obtains a new live "
                "Tavily packet. Within-run projection comparisons are paired, but "
                "provider results may differ from historical runs."
            ),
            (
                "A projected packet cannot contain an answer proxy absent from its "
                "selected packet. Selected coverage below 20/24 makes the projection "
                "result retrieval-limited and inconclusive."
            ),
            (
                "Substring coverage is a transparent proxy, not an official "
                "SimpleQA score or semantic correctness judgment."
            ),
            (
                "No model is called. Phase 11.9, Phase 12, product changes, merge, "
                "release and superiority claims remain blocked regardless of result."
            ),
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    root = REPOSITORY_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument(
        "--authorize-live-run",
        action="store_true",
        help="explicitly authorize the locked Tavily-only live calibration",
    )
    parser.add_argument("--dataset", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=root / "benchmarks/data/phase11_7_fresh_confirmation_v1.json",
    )
    parser.add_argument(
        "--reserve-manifest",
        type=Path,
        default=root / "benchmarks/data/phase12_untouched_reserve_v1.json",
    )
    parser.add_argument(
        "--phase11-8-3-result",
        type=Path,
        default=(root / "benchmarks/results/phase11_8_3_factorial_2026-07-30.json"),
    )
    parser.add_argument(
        "--candidate-v1",
        type=Path,
        default=root / "benchmarks/phase11_8_2_candidate.py",
    )
    parser.add_argument(
        "--candidate-v2",
        type=Path,
        default=root / "benchmarks/phase11_8_8_projection_candidate.py",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=(root / "benchmarks/data/phase11_8_8_offline_projection_fixtures_v1.json"),
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=root / "docs/benchmark-protocol-v23.md",
    )
    parser.add_argument("--tavily-api-key-env", default="TAVILY_API_KEY")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(tempfile.gettempdir()) / "evidencemesh-phase11-8-8",
    )
    parser.add_argument("--provider-max-results", type=int, default=20)
    parser.add_argument("--selection-limit", type=int, default=20)
    parser.add_argument("--max-per-domain", type=int, default=3)
    parser.add_argument("--evidence-budget-chars", type=int, default=12_000)
    parser.add_argument("--max-block-chars", type=int, default=1_500)
    parser.add_argument("--min-block-chars", type=int, default=192)
    parser.add_argument(
        "--projection-replays",
        type=int,
        default=EXPECTED_PROJECTION_REPLAYS,
    )
    parser.add_argument("--retrieval-wall-time-seconds", type=float, default=30.0)
    parser.add_argument("--retrieval-pause-seconds", type=float, default=0.5)
    parser.add_argument("--request-timeout-seconds", type=float, default=15.0)
    parser.add_argument(
        "--network-region",
        default=os.getenv("EVIDENCEMESH_BENCHMARK_REGION", "not reported"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    validate_arguments(arguments)
    if arguments.check_only or not arguments.authorize_live_run:
        print(
            json.dumps(
                validate_locked_sources(arguments),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    report = asyncio.run(run(arguments))
    if arguments.output is None:
        raise ValueError("live execution requires --output")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
