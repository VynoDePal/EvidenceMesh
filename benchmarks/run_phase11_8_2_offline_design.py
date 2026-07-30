#!/usr/bin/env python3
"""Run the locked, synthetic and network-free Phase 11.8.2 design evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from benchmarks.phase11_8_2_candidate import (
        DirectAnswerResponseError,
        balanced_baseline_project_blocks,
        build_direct_answer_prompt,
        candidate_project_blocks,
        direct_answer_response_schema,
        parse_direct_answer,
        rendered_evidence_chars,
    )
except ModuleNotFoundError:
    from phase11_8_2_candidate import (  # type: ignore[no-redef]
        DirectAnswerResponseError,
        balanced_baseline_project_blocks,
        build_direct_answer_prompt,
        candidate_project_blocks,
        direct_answer_response_schema,
        parse_direct_answer,
        rendered_evidence_chars,
    )

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-2-offline-design-v1"
LOCKED_PROTOCOL_SHA256 = "67a7212f68eeb5ed1b81dd98fabeb2b80d1faa2a88d379c83d7fc20bcd839652"
LOCKED_FIXTURE_SHA256 = "16f5eb38eec4c8669fb6dac4eeb64992df5b81a46b6c02325a559d3da4f621ab"
LOCKED_CANDIDATE_SHA256 = "0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e"
LOCKED_PHASE11_8_RESULT_SHA256 = "0bd05884c6e6d019f22d18113ef449d1cf1c8158ac0e598d899ee1a93c4b687a"
LOCKED_PHASE11_8_1_DIAGNOSTIC_SHA256 = (
    "9032d9df7d71a3e9c4197577c3e33af315842cae18435d91a7f851e5489de6d8"
)
EXPECTED_PROJECTION_CASES = 12
EXPECTED_VALID_RESPONSES = 4
EXPECTED_INVALID_RESPONSES = 11
PROTOCOL_REPORT_PATH = "docs/benchmark-protocol-v17.md"
FIXTURE_REPORT_PATH = "benchmarks/data/phase11_8_2_offline_fixtures_v1.json"
CANDIDATE_REPORT_PATH = "benchmarks/phase11_8_2_candidate.py"


@dataclass(frozen=True)
class OfflineBlock:
    citation_id: str
    title: str
    url: str
    text: str
    providers: tuple[str, ...]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256_bytes(encoded)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _materialize_text(parts: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for part in parts:
        if set(part) == {"literal"} and isinstance(part["literal"], str):
            rendered.append(part["literal"])
        elif (
            set(part) == {"repeat", "count"}
            and isinstance(part["repeat"], str)
            and isinstance(part["count"], int)
            and 0 <= part["count"] <= 10_000
        ):
            rendered.append(part["repeat"] * part["count"])
        else:
            raise ValueError("invalid synthetic text part")
    return "".join(rendered)


def _materialize_blocks(raw_blocks: list[dict[str, Any]]) -> tuple[OfflineBlock, ...]:
    blocks: list[OfflineBlock] = []
    for raw in raw_blocks:
        _require(
            set(raw)
            == {
                "citation_id",
                "title",
                "url",
                "providers",
                "text_parts",
            },
            "invalid synthetic block keys",
        )
        blocks.append(
            OfflineBlock(
                citation_id=str(raw["citation_id"]),
                title=str(raw["title"]),
                url=str(raw["url"]),
                text=_materialize_text(list(raw["text_parts"])),
                providers=tuple(str(provider) for provider in raw["providers"]),
            )
        )
    return tuple(blocks)


def _packet_sha256(blocks: tuple[OfflineBlock, ...]) -> str:
    return canonical_sha256(
        [
            {
                "citation_id": block.citation_id,
                "title": block.title,
                "url": block.url,
                "text": block.text,
                "providers": list(block.providers),
            }
            for block in blocks
        ]
    )


def _metadata_preserved(
    original: tuple[OfflineBlock, ...],
    candidate: tuple[OfflineBlock, ...],
) -> bool:
    original_by_id = {block.citation_id: block for block in original}
    return all(
        block.citation_id in original_by_id
        and block.title == original_by_id[block.citation_id].title
        and block.url == original_by_id[block.citation_id].url
        and block.providers == original_by_id[block.citation_id].providers
        for block in candidate
    )


def _projection_outcomes(fixtures: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = fixtures["projection_defaults"]
    outcomes: list[dict[str, Any]] = []
    for case in fixtures["projection_cases"]:
        blocks = _materialize_blocks(case["blocks"])
        budget = int(case.get("budget_chars", defaults["budget_chars"]))
        max_block = int(case.get("max_block_chars", defaults["max_block_chars"]))
        min_block = int(case.get("min_block_chars", defaults["min_block_chars"]))
        baseline = balanced_baseline_project_blocks(blocks, budget, max_block)
        candidates = tuple(
            candidate_project_blocks(
                blocks,
                str(case["question"]),
                budget,
                max_block,
                min_block_chars=min_block,
            )
            for _ in range(3)
        )
        candidate = candidates[0]
        sentinel = str(case["sentinel"])
        expected_source_id = str(case["expected_source_id"])
        system_prompt, user_prompt = build_direct_answer_prompt(
            str(case["question"]),
            candidate,
        )
        outcomes.append(
            {
                "case_id": str(case["id"]),
                "original_packet_sha256": _packet_sha256(blocks),
                "baseline_packet_sha256": _packet_sha256(baseline),
                "candidate_packet_sha256": _packet_sha256(candidate),
                "baseline_retained_sentinel": sentinel in "".join(block.text for block in baseline),
                "candidate_retained_sentinel": sentinel
                in "".join(block.text for block in candidate),
                "expected_source_in_candidate": expected_source_id
                in {block.citation_id for block in candidate},
                "budget_chars": budget,
                "candidate_rendered_chars": rendered_evidence_chars(candidate),
                "budget_compliant": rendered_evidence_chars(candidate) <= budget,
                "deterministic_three_replays": len(
                    {_packet_sha256(projected) for projected in candidates}
                )
                == 1,
                "metadata_preserved": _metadata_preserved(blocks, candidate),
                "original_block_count": len(blocks),
                "baseline_block_count": len(baseline),
                "candidate_block_count": len(candidate),
                "candidate_prompt_sha256": canonical_sha256(
                    {
                        "system_instruction": system_prompt,
                        "user_prompt": user_prompt,
                    }
                ),
            }
        )
    return outcomes


def _paired_retention(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    candidate_wins = sum(
        bool(row["candidate_retained_sentinel"]) and not bool(row["baseline_retained_sentinel"])
        for row in outcomes
    )
    baseline_wins = sum(
        bool(row["baseline_retained_sentinel"]) and not bool(row["candidate_retained_sentinel"])
        for row in outcomes
    )
    shared_hits = sum(
        bool(row["baseline_retained_sentinel"]) and bool(row["candidate_retained_sentinel"])
        for row in outcomes
    )
    shared_misses = len(outcomes) - candidate_wins - baseline_wins - shared_hits
    return {
        "candidate_wins": candidate_wins,
        "baseline_wins": baseline_wins,
        "shared_hits": shared_hits,
        "shared_misses": shared_misses,
        "net_gain": candidate_wins - baseline_wins,
    }


def _structured_outcomes(fixtures: dict[str, Any]) -> dict[str, Any]:
    valid_rows: list[dict[str, Any]] = []
    for row in fixtures["valid_direct_answers"]:
        rendered = parse_direct_answer(
            str(row["raw"]),
            allowed_ids=frozenset(str(item) for item in row["allowed_ids"]),
        )
        valid_rows.append(
            {
                "case_id": str(row["id"]),
                "accepted": True,
                "rendered_matches": rendered == row["rendered"],
                "rendered_sha256": sha256_bytes(rendered.encode()),
            }
        )

    invalid_rows: list[dict[str, Any]] = []
    for row in fixtures["invalid_direct_answers"]:
        rejected = False
        try:
            parse_direct_answer(
                str(row["raw"]),
                allowed_ids=frozenset(str(item) for item in row["allowed_ids"]),
            )
        except DirectAnswerResponseError:
            rejected = True
        invalid_rows.append({"case_id": str(row["id"]), "rejected": rejected})

    schema = direct_answer_response_schema()
    return {
        "schema": schema,
        "schema_sha256": canonical_sha256(schema),
        "exact_top_level_keys": ["answer", "citation_ids"],
        "valid_cases": valid_rows,
        "invalid_cases": invalid_rows,
        "valid_accepted": sum(
            bool(row["accepted"]) and bool(row["rendered_matches"]) for row in valid_rows
        ),
        "invalid_rejected": sum(bool(row["rejected"]) for row in invalid_rows),
    }


def build_report(
    *,
    protocol_raw: bytes,
    fixture_raw: bytes,
    candidate_raw: bytes,
    phase11_8_source_sha256: str,
    phase11_8_decision: dict[str, Any],
    phase11_8_1_source_sha256: str,
    phase11_8_1_decision: dict[str, Any],
) -> dict[str, Any]:
    _require(sha256_bytes(protocol_raw) == LOCKED_PROTOCOL_SHA256, "protocol lock changed")
    _require(sha256_bytes(fixture_raw) == LOCKED_FIXTURE_SHA256, "fixture lock changed")
    _require(sha256_bytes(candidate_raw) == LOCKED_CANDIDATE_SHA256, "candidate lock changed")
    _require(
        phase11_8_source_sha256 == LOCKED_PHASE11_8_RESULT_SHA256,
        "Phase 11.8 source changed",
    )
    _require(
        phase11_8_1_source_sha256 == LOCKED_PHASE11_8_1_DIAGNOSTIC_SHA256,
        "Phase 11.8.1 source changed",
    )

    fixtures = json.loads(fixture_raw)
    _require(
        fixtures["benchmark"] == "evidencemesh-phase11-8-2-offline-design-fixtures-v1",
        "unexpected fixture benchmark",
    )
    _require(fixtures["authored_after_phase11_8"] is True, "fixture disclosure missing")
    _require(
        fixtures["contains_phase11_7_or_phase12_content"] is False,
        "private or reserve content is forbidden",
    )
    _require(
        fixtures["predictive_quality_claim_allowed"] is False,
        "synthetic fixtures cannot support predictive claims",
    )
    _require(
        phase11_8_decision["release_decision"] == "no-go"
        and phase11_8_decision["phase11_8_candidate_passed"] is False,
        "historical Phase 11.8 decision changed",
    )
    _require(
        phase11_8_1_decision["historical_phase11_8_result_changed"] is False,
        "Phase 11.8.1 boundary changed",
    )

    projection = _projection_outcomes(fixtures)
    structured = _structured_outcomes(fixtures)
    paired = _paired_retention(projection)
    candidate_hits = sum(bool(row["candidate_retained_sentinel"]) for row in projection)
    baseline_hits = sum(bool(row["baseline_retained_sentinel"]) for row in projection)
    gates = {
        "locked_source_integrity": {
            "passed": True,
            "protocol_sha256": LOCKED_PROTOCOL_SHA256,
            "fixture_sha256": LOCKED_FIXTURE_SHA256,
            "candidate_sha256": LOCKED_CANDIDATE_SHA256,
            "phase11_8_result_sha256": LOCKED_PHASE11_8_RESULT_SHA256,
            "phase11_8_1_diagnostic_sha256": LOCKED_PHASE11_8_1_DIAGNOSTIC_SHA256,
        },
        "synthetic_fixture_disclosure": {
            "passed": (
                fixtures["authored_after_phase11_8"] is True
                and fixtures["contains_phase11_7_or_phase12_content"] is False
                and fixtures["predictive_quality_claim_allowed"] is False
            )
        },
        "zero_network_provider_model_traffic": {
            "passed": True,
            "network_requests": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "provider_calls": 0,
            "model_calls": 0,
        },
        "candidate_retains_all_authored_sentinels": {
            "passed": candidate_hits == EXPECTED_PROJECTION_CASES,
            "observed": candidate_hits,
            "required": EXPECTED_PROJECTION_CASES,
        },
        "candidate_has_no_fixture_retention_regression": {
            "passed": paired["baseline_wins"] == 0,
            "paired": paired,
        },
        "candidate_has_positive_authored_fixture_gain": {
            "passed": paired["net_gain"] > 0,
            "paired": paired,
        },
        "exact_rendered_budget_compliance": {
            "passed": all(bool(row["budget_compliant"]) for row in projection),
            "observed": sum(bool(row["budget_compliant"]) for row in projection),
            "required": EXPECTED_PROJECTION_CASES,
        },
        "deterministic_three_replays": {
            "passed": all(bool(row["deterministic_three_replays"]) for row in projection),
            "observed": sum(bool(row["deterministic_three_replays"]) for row in projection),
            "required": EXPECTED_PROJECTION_CASES,
        },
        "evidence_metadata_preserved": {
            "passed": all(
                bool(row["metadata_preserved"]) and bool(row["expected_source_in_candidate"])
                for row in projection
            ),
            "observed": sum(
                bool(row["metadata_preserved"]) and bool(row["expected_source_in_candidate"])
                for row in projection
            ),
            "required": EXPECTED_PROJECTION_CASES,
        },
        "valid_direct_answers_accepted": {
            "passed": structured["valid_accepted"] == EXPECTED_VALID_RESPONSES,
            "observed": structured["valid_accepted"],
            "required": EXPECTED_VALID_RESPONSES,
        },
        "invalid_direct_answers_rejected": {
            "passed": structured["invalid_rejected"] == EXPECTED_INVALID_RESPONSES,
            "observed": structured["invalid_rejected"],
            "required": EXPECTED_INVALID_RESPONSES,
        },
        "historical_and_release_boundaries_preserved": {
            "passed": (
                phase11_8_decision["phase11_8_candidate_passed"] is False
                and phase11_8_decision["phase12_executed"] is False
                and phase11_8_1_decision["historical_phase11_8_result_changed"] is False
            ),
            "phase11_8_historical_result_changed": False,
            "phase12_accessed": False,
            "product_configuration_changed": False,
        },
    }
    offline_candidate_passed = all(bool(gate["passed"]) for gate in gates.values())
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": "synthetic offline projection and response-contract engineering",
        "source": {
            "phase11_8_result_sha256": LOCKED_PHASE11_8_RESULT_SHA256,
            "phase11_8_1_diagnostic_sha256": LOCKED_PHASE11_8_1_DIAGNOSTIC_SHA256,
            "historical_phase11_8_result": "fail_5_of_12",
            "historical_release_decision": "no-go",
        },
        "protocol": {
            "path": PROTOCOL_REPORT_PATH,
            "sha256": LOCKED_PROTOCOL_SHA256,
            "fixture_path": FIXTURE_REPORT_PATH,
            "fixture_sha256": LOCKED_FIXTURE_SHA256,
            "candidate_path": CANDIDATE_REPORT_PATH,
            "candidate_sha256": LOCKED_CANDIDATE_SHA256,
            "answer_blind_projection_inputs": ["question", "selected_evidence"],
            "answer_or_sentinel_passed_to_projector": False,
            "projection_replays_per_case": 3,
        },
        "fixture_disclosure": {
            "authored_after_phase11_8": True,
            "synthetic": True,
            "case_count": len(projection),
            "contains_phase11_7_or_phase12_content": False,
            "predictive_quality_claim_allowed": False,
        },
        "projection": {
            "baseline": "phase11_8_equal_per_block_cap_clone",
            "candidate": "rank_weighted_query_window_head_tail_v1",
            "baseline_retained": baseline_hits,
            "candidate_retained": candidate_hits,
            "paired": paired,
            "outcomes": projection,
        },
        "direct_answer_contract": structured,
        "traffic": {
            "network_requests": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "gates": gates,
        "decision": {
            "offline_engineering_candidate_passed": offline_candidate_passed,
            "real_case_quality_improvement_proven": False,
            "historical_phase11_8_result_changed": False,
            "phase11_8_3_live_calibration_authorized": False,
            "phase11_9_authorized": False,
            "phase12_executed": False,
            "phase12_authorized": False,
            "quality_profile_promotion_allowed": False,
            "merge_allowed": False,
            "release_allowed": False,
            "superiority_claim_allowed": False,
            "release_decision": "no-go",
            "next_step": (
                "Review and separately freeze a live observed-case causal protocol; "
                "synthetic success alone cannot authorize API traffic."
            ),
        },
        "privacy": {
            "phase11_7_questions_or_answers_in_output": False,
            "phase11_7_evidence_or_prompts_in_output": False,
            "generated_model_answers_in_output": False,
            "credentials_in_output": False,
            "phase12_identifiers_in_output": False,
            "synthetic_case_text_in_output": False,
        },
        "warnings": [
            (
                "Fixtures were authored after observing the Phase 11.8 failure and prove "
                "engineering invariants only; they are not an unbiased quality benchmark."
            ),
            (
                "No hosted model was called, so direct-answer schema adherence and answer "
                "quality on Gemma or Gemini remain unmeasured."
            ),
            (
                "The projection uses question terms but never answers or sentinels. A fresh "
                "or separately authorized observed-case evaluation is still required."
            ),
        ],
    }


def run(
    *,
    protocol_path: Path,
    fixture_path: Path,
    candidate_path: Path,
    phase11_8_result_path: Path,
    phase11_8_1_diagnostic_path: Path,
) -> dict[str, Any]:
    phase11_8_raw = phase11_8_result_path.read_bytes()
    phase11_8_1_raw = phase11_8_1_diagnostic_path.read_bytes()
    phase11_8 = json.loads(phase11_8_raw)
    phase11_8_1 = json.loads(phase11_8_1_raw)
    return build_report(
        protocol_raw=protocol_path.read_bytes(),
        fixture_raw=fixture_path.read_bytes(),
        candidate_raw=candidate_path.read_bytes(),
        phase11_8_source_sha256=sha256_bytes(phase11_8_raw),
        phase11_8_decision=phase11_8["decision"],
        phase11_8_1_source_sha256=sha256_bytes(phase11_8_1_raw),
        phase11_8_1_decision=phase11_8_1["decision"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "benchmark-protocol-v17.md",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=REPOSITORY_ROOT / "benchmarks" / "data" / "phase11_8_2_offline_fixtures_v1.json",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=REPOSITORY_ROOT / "benchmarks" / "phase11_8_2_candidate.py",
    )
    parser.add_argument(
        "--phase11-8-result",
        type=Path,
        default=REPOSITORY_ROOT / "benchmarks" / "results" / "phase11_8_recovery_2026-07-29.json",
    )
    parser.add_argument(
        "--phase11-8-1-diagnostic",
        type=Path,
        default=REPOSITORY_ROOT
        / "benchmarks"
        / "results"
        / "phase11_8_1_offline_diagnostic_2026-07-30.json",
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run(
        protocol_path=arguments.protocol,
        fixture_path=arguments.fixtures,
        candidate_path=arguments.candidate,
        phase11_8_result_path=arguments.phase11_8_result,
        phase11_8_1_diagnostic_path=arguments.phase11_8_1_diagnostic,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
