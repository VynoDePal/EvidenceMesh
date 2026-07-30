#!/usr/bin/env python3
"""Reproduce the zero-traffic Phase 11.8.8 projection engineering lock."""

from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from benchmarks.phase11_8_2_candidate import (
        balanced_baseline_project_blocks,
        candidate_project_blocks,
    )
    from benchmarks.phase11_8_2_candidate import (
        rendered_evidence_chars as rendered_evidence_chars_v1,
    )
    from benchmarks.phase11_8_8_projection_candidate import (
        OMISSION_SEPARATOR,
        PROJECTION_FAMILY,
        candidate_project_blocks_v2,
        rendered_evidence_chars,
    )
except ModuleNotFoundError:
    from phase11_8_2_candidate import (  # type: ignore[no-redef]
        balanced_baseline_project_blocks,
        candidate_project_blocks,
    )
    from phase11_8_2_candidate import (
        rendered_evidence_chars as rendered_evidence_chars_v1,
    )
    from phase11_8_8_projection_candidate import (  # type: ignore[no-redef]
        OMISSION_SEPARATOR,
        PROJECTION_FAMILY,
        candidate_project_blocks_v2,
        rendered_evidence_chars,
    )

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-8-offline-projection-lock-v1"

PROTOCOL_PATH = "docs/benchmark-protocol-v23.md"
FIXTURE_PATH = "benchmarks/data/phase11_8_8_offline_projection_fixtures_v1.json"
CANDIDATE_V2_PATH = "benchmarks/phase11_8_8_projection_candidate.py"
LIVE_RUNNER_PATH = "benchmarks/run_phase11_8_8_projection_calibration.py"
MANIFEST_PATH = "benchmarks/data/phase11_7_fresh_confirmation_v1.json"
RESERVE_PATH = "benchmarks/data/phase12_untouched_reserve_v1.json"
PHASE11_8_3_RESULT_PATH = "benchmarks/results/phase11_8_3_factorial_2026-07-30.json"
CANDIDATE_V1_PATH = "benchmarks/phase11_8_2_candidate.py"
RUNTIME_PROTOCOL_PATH = "docs/benchmark-protocol-v22.md"
RUNTIME_RESULT_PATH = (
    "benchmarks/results/phase11_8_7_offline_runtime_timeout_hardening_2026-07-30.json"
)

LOCKED_PROTOCOL_SHA256 = "11a8fe99a3e418eb4161978928f2d682a2adcf6b59b3bcc7b7641c26b601a653"
LOCKED_FIXTURE_SHA256 = "8955ac33c89c2e16a474182c14eac8df5acaf649642f4dd90a313cf6227db614"
LOCKED_CANDIDATE_V2_SHA256 = "117968687a0c0c150acef42f997967d10b04006d14ed0efa9de87c9c08b1909e"
LOCKED_LIVE_RUNNER_SHA256 = "80643144da925c4b9b2d4e106a6c779ce2e6c4cf33ae5470fffe53de5a314c63"
LOCKED_MANIFEST_SHA256 = "da6d1e21c3c1d53539f481fe6789eedc55359bb3b9d32b0be73f96bc693da79e"
LOCKED_RESERVE_SHA256 = "472ec47a21b99f14ab05c4e7b79d179034fc42558910c0bf2ef053b0d25411ee"
LOCKED_PHASE11_8_3_RESULT_SHA256 = (
    "167a7eb531966ee0591a1ae01b2a8d9d47307cb1eb52ec152946bbe0dbc6e39c"
)
LOCKED_CANDIDATE_V1_SHA256 = "0eb71a0e94b7e21d33105788d05076382f96ab9e5fd6cea9d16669305d38c74e"
LOCKED_RUNTIME_PROTOCOL_SHA256 = "e786b5b4f7ade79d40dc81ffab3a20bd0a09ffe45c7b5a8765155519e2cd1dbe"
LOCKED_RUNTIME_RESULT_SHA256 = "375718f1ba8ed4d4623bb76df3253a7d64b2dbbc813a69615488ab2e084f8fd7"

EXPECTED_FIXTURE_CASES = 12
EXPECTED_REPLAYS = 5


@dataclass(frozen=True, slots=True)
class FixtureBlock:
    citation_id: str
    title: str
    url: str
    text: str
    providers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TripwireBlock:
    citation_id: str
    title: str
    url: str
    text: str
    providers: tuple[str, ...]

    @property
    def answer(self) -> str:
        raise AssertionError("projector accessed a forbidden answer field")

    @property
    def reference_answer(self) -> str:
        raise AssertionError("projector accessed a forbidden reference field")

    @property
    def sentinel(self) -> str:
        raise AssertionError("projector accessed a forbidden sentinel field")

    @property
    def case_id(self) -> str:
        raise AssertionError("projector accessed a forbidden case identifier")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _locked_hash(path: str, raw: bytes, expected: str) -> str:
    _require(
        len(expected) == 64 and not expected.startswith("__"),
        f"unresolved checksum lock: {path}",
    )
    observed = sha256_bytes(raw)
    _require(observed == expected, f"locked source changed: {path}")
    return observed


def _materialize_text(parts: object) -> str:
    _require(isinstance(parts, list) and bool(parts), "text_parts must be a non-empty list")
    rendered: list[str] = []
    for part in parts:
        _require(isinstance(part, dict), "each text part must be an object")
        if set(part) == {"literal"}:
            _require(isinstance(part["literal"], str), "literal text must be a string")
            rendered.append(part["literal"])
            continue
        _require(set(part) == {"repeat", "count"}, "unexpected text part shape")
        _require(
            isinstance(part["repeat"], str)
            and isinstance(part["count"], int)
            and not isinstance(part["count"], bool)
            and 0 <= part["count"] <= 1_000,
            "invalid repeat part",
        )
        rendered.append(part["repeat"] * part["count"])
    return "".join(rendered)


def _fixture_blocks(case: dict[str, Any]) -> tuple[FixtureBlock, ...]:
    raw_blocks = case.get("blocks")
    _require(isinstance(raw_blocks, list) and bool(raw_blocks), "case blocks must be non-empty")
    blocks: list[FixtureBlock] = []
    for raw in raw_blocks:
        _require(isinstance(raw, dict), "fixture block must be an object")
        _require(
            set(raw) == {"citation_id", "title", "url", "providers", "text_parts"},
            "unexpected fixture block shape",
        )
        providers = raw["providers"]
        _require(
            isinstance(providers, list)
            and all(isinstance(provider, str) for provider in providers),
            "invalid fixture providers",
        )
        blocks.append(
            FixtureBlock(
                citation_id=str(raw["citation_id"]),
                title=str(raw["title"]),
                url=str(raw["url"]),
                text=_materialize_text(raw["text_parts"]),
                providers=tuple(providers),
            )
        )
    return tuple(blocks)


def _metadata_preserved(
    source: tuple[FixtureBlock, ...],
    projected: tuple[FixtureBlock, ...],
) -> bool:
    source_by_id = {block.citation_id: block for block in source}
    if len(source_by_id) != len(source):
        return False
    projected_ids = [block.citation_id for block in projected]
    source_ids = [block.citation_id for block in source]
    if len(projected_ids) != len(set(projected_ids)):
        return False
    positions = [source_ids.index(citation_id) for citation_id in projected_ids]
    return positions == sorted(positions) and all(
        (
            block.citation_id,
            block.title,
            block.url,
            block.providers,
        )
        == (
            source_by_id[block.citation_id].citation_id,
            source_by_id[block.citation_id].title,
            source_by_id[block.citation_id].url,
            source_by_id[block.citation_id].providers,
        )
        for block in projected
        if block.citation_id in source_by_id
    )


def _source_preserved(
    source: tuple[FixtureBlock, ...],
    projected: tuple[FixtureBlock, ...],
) -> bool:
    source_by_id = {block.citation_id: block.text.strip() for block in source}
    for block in projected:
        original = source_by_id.get(block.citation_id)
        if original is None:
            return False
        cursor = 0
        segments = [segment for segment in block.text.split(OMISSION_SEPARATOR) if segment]
        for segment in segments:
            position = original.find(segment, cursor)
            if position < 0:
                return False
            cursor = position + len(segment)
    return True


def _project_fixture_case(
    case: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    blocks = _fixture_blocks(case)
    question = case.get("question")
    marker = case.get("marker")
    _require(isinstance(question, str) and question, "fixture question is required")
    _require(isinstance(marker, str) and marker, "fixture marker is required")
    budget = int(case.get("budget_chars", defaults["budget_chars"]))
    max_block = int(case.get("max_block_chars", defaults["max_block_chars"]))
    min_block = int(case.get("min_block_chars", defaults["min_block_chars"]))

    equal = balanced_baseline_project_blocks(blocks, budget, max_block)
    v1 = candidate_project_blocks(
        blocks,
        question,
        budget,
        max_block,
        min_block_chars=min_block,
    )
    v2_replays = tuple(
        candidate_project_blocks_v2(
            blocks,
            question,
            budget,
            max_block,
            min_block_chars=min_block,
        )
        for _ in range(EXPECTED_REPLAYS)
    )
    v2 = v2_replays[0]
    replay_hashes = {
        sha256_bytes(
            json.dumps(
                [
                    {
                        "citation_id": block.citation_id,
                        "title": block.title,
                        "url": block.url,
                        "text": block.text,
                        "providers": list(block.providers),
                    }
                    for block in replay
                ],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
        for replay in v2_replays
    }
    return {
        "id": str(case["id"]),
        "input_block_count": len(blocks),
        "equal_cap_retained_marker": any(marker in block.text for block in equal),
        "v1_retained_marker": any(marker in block.text for block in v1),
        "v2_retained_marker": any(marker in block.text for block in v2),
        "equal_cap_rendered_chars": rendered_evidence_chars_v1(equal),
        "equal_cap_over_budget": rendered_evidence_chars_v1(equal) > budget,
        "v1_rendered_chars": rendered_evidence_chars_v1(v1),
        "v2_rendered_chars": rendered_evidence_chars(v2),
        "v2_budget_compliant": rendered_evidence_chars(v2) <= budget,
        "v2_per_block_cap_compliant": all(len(block.text) <= max_block for block in v2),
        "v2_deterministic_five_replays": len(replay_hashes) == 1,
        "v2_metadata_preserved": _metadata_preserved(blocks, v2),
        "v2_source_preserved": _source_preserved(blocks, v2),
        "v2_output_block_count": len(v2),
    }


def _paired(rows: list[dict[str, Any]], baseline_field: str) -> dict[str, int]:
    candidate_wins = sum(
        bool(row["v2_retained_marker"]) and not bool(row[baseline_field]) for row in rows
    )
    baseline_wins = sum(
        bool(row[baseline_field]) and not bool(row["v2_retained_marker"]) for row in rows
    )
    shared_hits = sum(bool(row[baseline_field]) and bool(row["v2_retained_marker"]) for row in rows)
    shared_misses = len(rows) - candidate_wins - baseline_wins - shared_hits
    return {
        "candidate_wins": candidate_wins,
        "baseline_wins": baseline_wins,
        "shared_hits": shared_hits,
        "shared_misses": shared_misses,
        "net_gain": candidate_wins - baseline_wins,
    }


def _answer_blind_diagnostics(candidate_source: str) -> dict[str, Any]:
    signature = inspect.signature(candidate_project_blocks_v2)
    parameter_names = list(signature.parameters)
    expected_parameters = [
        "blocks",
        "question",
        "budget_chars",
        "max_block_chars",
        "min_block_chars",
    ]
    tree = ast.parse(candidate_source)
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
    forbidden_parameters = {
        "answer",
        "answers",
        "expected_answer",
        "reference_answer",
        "answer_hash",
        "sentinel",
        "case_id",
        "row_index",
    }
    forbidden_calls = {
        "open",
        "getenv",
        "urlopen",
        "request",
        "connect",
        "socket",
    }
    observed_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    tripwire = TripwireBlock(
        citation_id="S1",
        title="Synthetic Atlas",
        url="https://example.test/atlas",
        text=("Synthetic Atlas entry. " * 60) + "The registry code is AA-17.",
        providers=("tavily",),
    )
    tripwire_output = candidate_project_blocks_v2(
        (tripwire,),
        "What is the Synthetic Atlas registry code?",
        420,
        360,
        min_block_chars=96,
    )
    return {
        "signature_parameters": parameter_names,
        "exact_signature": parameter_names == expected_parameters,
        "forbidden_parameter_present": bool(forbidden_parameters & set(parameter_names)),
        "imports": sorted(imports),
        "stdlib_only": imports
        <= {
            "__future__",
            "collections",
            "dataclasses",
            "itertools",
            "re",
            "typing",
        },
        "forbidden_io_call_present": bool(forbidden_calls & observed_calls),
        "tripwire_projection_completed": bool(tripwire_output),
    }


def _edge_diagnostics() -> dict[str, Any]:
    block = FixtureBlock(
        citation_id="S1",
        title="Boundary",
        url="https://example.test/boundary",
        text="Boundary evidence.",
        providers=("tavily",),
    )
    duplicate = (block, block)
    invalid_calls = (
        lambda: candidate_project_blocks_v2(duplicate, "Boundary?", 500, 200),
        lambda: candidate_project_blocks_v2((block,), "Boundary?", 0, 200),
        lambda: candidate_project_blocks_v2((block,), "Boundary?", 500, 0),
        lambda: candidate_project_blocks_v2(
            (block,),
            "Boundary?",
            500,
            100,
            min_block_chars=101,
        ),
    )
    rejected = 0
    categories: list[str] = []
    for call in invalid_calls:
        try:
            call()
        except ValueError as exc:
            rejected += 1
            categories.append(str(exc))
    whitespace = FixtureBlock(
        citation_id="S2",
        title="Whitespace",
        url="https://example.test/whitespace",
        text="   ",
        providers=("tavily",),
    )
    return {
        "invalid_fixture_count": len(invalid_calls),
        "invalid_rejected": rejected,
        "bounded_error_categories": categories,
        "empty_packet_returns_empty": candidate_project_blocks_v2(
            (),
            "Boundary?",
            100,
            50,
            min_block_chars=50,
        )
        == (),
        "whitespace_packet_returns_empty": candidate_project_blocks_v2(
            (whitespace,),
            "Boundary?",
            100,
            50,
            min_block_chars=50,
        )
        == (),
        "tiny_header_budget_returns_empty": candidate_project_blocks_v2(
            (block,),
            "Boundary?",
            10,
            10,
            min_block_chars=10,
        )
        == (),
    }


def _future_runner_diagnostics(live_source: str) -> dict[str, Any]:
    tree = ast.parse(live_source)
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    return {
        "syntax_valid": True,
        "default_mode_is_check_only": "if arguments.check_only or not arguments.authorize_live_run"
        in live_source,
        "explicit_live_flag_required": "--authorize-live-run" in strings,
        "tavily_key_only": "TAVILY_API_KEY" in strings and "GEMINI_API_KEY" not in strings,
        "three_projection_arms": len(PROJECTION_FAMILY) > 0
        and "PROJECTION_ARMS = (EQUAL_CAP_ARM, V1_ARM, V2_ARM)" in live_source,
        "planned_tavily_ceiling_24": "MAXIMUM_TAVILY_REQUESTS = EXPECTED_CASE_COUNT" in live_source,
        "zero_model_contract": '"model_requests": 0' in live_source
        and '"gemini_requests": 0' in live_source,
        "no_live_workflow_created": True,
    }


def build_report(
    *,
    protocol_raw: bytes,
    fixture_raw: bytes,
    candidate_v2_raw: bytes,
    live_runner_raw: bytes,
    historical_raw: dict[str, bytes],
) -> dict[str, Any]:
    expected_hashes = {
        PROTOCOL_PATH: LOCKED_PROTOCOL_SHA256,
        FIXTURE_PATH: LOCKED_FIXTURE_SHA256,
        CANDIDATE_V2_PATH: LOCKED_CANDIDATE_V2_SHA256,
        LIVE_RUNNER_PATH: LOCKED_LIVE_RUNNER_SHA256,
        MANIFEST_PATH: LOCKED_MANIFEST_SHA256,
        RESERVE_PATH: LOCKED_RESERVE_SHA256,
        PHASE11_8_3_RESULT_PATH: LOCKED_PHASE11_8_3_RESULT_SHA256,
        CANDIDATE_V1_PATH: LOCKED_CANDIDATE_V1_SHA256,
        RUNTIME_PROTOCOL_PATH: LOCKED_RUNTIME_PROTOCOL_SHA256,
        RUNTIME_RESULT_PATH: LOCKED_RUNTIME_RESULT_SHA256,
    }
    raw_sources = {
        PROTOCOL_PATH: protocol_raw,
        FIXTURE_PATH: fixture_raw,
        CANDIDATE_V2_PATH: candidate_v2_raw,
        LIVE_RUNNER_PATH: live_runner_raw,
        **historical_raw,
    }
    locked_hashes = {
        path: _locked_hash(path, raw_sources[path], expected)
        for path, expected in expected_hashes.items()
    }

    fixture = json.loads(fixture_raw)
    _require(
        isinstance(fixture, dict)
        and fixture.get("benchmark") == "evidencemesh-phase11-8-8-offline-projection-fixtures-v1"
        and fixture.get("authored_after_phase11_8") is True
        and fixture.get("contains_phase11_7_or_phase12_content") is False
        and fixture.get("predictive_quality_claim_allowed") is False,
        "synthetic fixture disclosure changed",
    )
    defaults = fixture.get("projection_defaults")
    cases = fixture.get("cases")
    _require(isinstance(defaults, dict), "fixture defaults missing")
    _require(
        isinstance(cases, list) and len(cases) == EXPECTED_FIXTURE_CASES,
        "unexpected fixture case count",
    )
    outcomes = [_project_fixture_case(case, defaults) for case in cases]

    historical = json.loads(historical_raw[PHASE11_8_3_RESULT_PATH])
    historical_gates = historical["decision"]["gates"]
    historical_passed = sum(bool(gate["passed"]) for gate in historical_gates.values())
    retrieval = historical["retrieval_metrics"]
    selected_hits = retrieval["equal_claims"]["answer_key_in_selected_evidence"]["numerator"]
    equal_hits = retrieval["equal_claims"]["answer_key_in_prompt_evidence"]["numerator"]
    v1_hits = retrieval["candidate_claims"]["answer_key_in_prompt_evidence"]["numerator"]
    historical_boundary = {
        "gate_passes": historical_passed,
        "gate_count": len(historical_gates),
        "candidate_passed": historical["decision"]["phase11_8_3_candidate_passed"],
        "selected_evidence_proxy_hits": selected_hits,
        "equal_cap_proxy_hits": equal_hits,
        "v1_proxy_hits": v1_hits,
        "phase11_9_protocol_may_be_frozen": historical["decision"][
            "phase11_9_protocol_may_be_frozen"
        ],
        "release_decision": historical["decision"]["release_decision"],
    }
    _require(
        historical_boundary
        == {
            "gate_passes": 10,
            "gate_count": 14,
            "candidate_passed": False,
            "selected_evidence_proxy_hits": 19,
            "equal_cap_proxy_hits": 17,
            "v1_proxy_hits": 17,
            "phase11_9_protocol_may_be_frozen": False,
            "release_decision": "no-go",
        },
        "Phase 11.8.3 historical boundary changed",
    )

    answer_blind = _answer_blind_diagnostics(candidate_v2_raw.decode())
    edges = _edge_diagnostics()
    future_runner = _future_runner_diagnostics(live_runner_raw.decode())
    paired_equal = _paired(outcomes, "equal_cap_retained_marker")
    paired_v1 = _paired(outcomes, "v1_retained_marker")
    v2_hits = sum(bool(row["v2_retained_marker"]) for row in outcomes)
    equal_fixture_hits = sum(bool(row["equal_cap_retained_marker"]) for row in outcomes)
    v1_fixture_hits = sum(bool(row["v1_retained_marker"]) for row in outcomes)
    baseline_over_budget = sum(bool(row["equal_cap_over_budget"]) for row in outcomes)

    gates: dict[str, dict[str, Any]] = {
        "locked_source_integrity": {
            "passed": True,
            "sha256": locked_hashes,
        },
        "historical_10_of_14_no_go_preserved": {
            "passed": True,
            "observed": historical_boundary,
        },
        "synthetic_fixture_disclosure": {
            "passed": True,
            "authored_after_observation": True,
            "predictive_quality_claim_allowed": False,
        },
        "zero_network_provider_model_or_secret_traffic": {
            "passed": True,
            "network_requests": 0,
            "provider_calls": 0,
            "search_calls": 0,
            "model_calls": 0,
            "secrets_bound": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "answer_blind_no_io_interface": {
            "passed": (
                answer_blind["exact_signature"]
                and not answer_blind["forbidden_parameter_present"]
                and answer_blind["stdlib_only"]
                and not answer_blind["forbidden_io_call_present"]
                and answer_blind["tripwire_projection_completed"]
            ),
            "observed": answer_blind,
        },
        "source_substrings_only": {
            "passed": all(bool(row["v2_source_preserved"]) for row in outcomes),
            "observed": sum(bool(row["v2_source_preserved"]) for row in outcomes),
            "required": EXPECTED_FIXTURE_CASES,
        },
        "metadata_ids_and_order_preserved": {
            "passed": all(bool(row["v2_metadata_preserved"]) for row in outcomes),
            "observed": sum(bool(row["v2_metadata_preserved"]) for row in outcomes),
            "required": EXPECTED_FIXTURE_CASES,
        },
        "exact_budget_and_per_block_cap": {
            "passed": all(
                bool(row["v2_budget_compliant"]) and bool(row["v2_per_block_cap_compliant"])
                for row in outcomes
            ),
            "observed": {
                "v2_compliant_cases": sum(
                    bool(row["v2_budget_compliant"]) and bool(row["v2_per_block_cap_compliant"])
                    for row in outcomes
                ),
                "historical_equal_cap_over_budget_cases": baseline_over_budget,
            },
            "required_v2_cases": EXPECTED_FIXTURE_CASES,
        },
        "deterministic_five_replays": {
            "passed": all(bool(row["v2_deterministic_five_replays"]) for row in outcomes),
            "observed": sum(bool(row["v2_deterministic_five_replays"]) for row in outcomes),
            "required": EXPECTED_FIXTURE_CASES,
        },
        "malformed_and_boundary_inputs_fail_closed": {
            "passed": (
                edges["invalid_rejected"] == edges["invalid_fixture_count"]
                and edges["empty_packet_returns_empty"]
                and edges["whitespace_packet_returns_empty"]
                and edges["tiny_header_budget_returns_empty"]
            ),
            "observed": edges,
        },
        "adversarial_fixture_retention": {
            "passed": v2_hits == EXPECTED_FIXTURE_CASES,
            "observed": v2_hits,
            "required": EXPECTED_FIXTURE_CASES,
        },
        "synthetic_non_regression_vs_both_controls": {
            "passed": (
                paired_equal["baseline_wins"] == 0
                and paired_v1["baseline_wins"] == 0
                and v2_hits >= max(equal_fixture_hits, v1_fixture_hits)
            ),
            "equal_cap_hits": equal_fixture_hits,
            "v1_hits": v1_fixture_hits,
            "v2_hits": v2_hits,
            "paired_vs_equal_cap": paired_equal,
            "paired_vs_v1": paired_v1,
        },
        "future_live_contract_locked_but_not_authorized": {
            "passed": all(bool(value) for value in future_runner.values()),
            "observed": future_runner,
        },
        "privacy_and_release_boundaries_preserved": {
            "passed": True,
            "fixture_text_in_public_outcomes": False,
            "question_or_marker_in_public_outcomes": False,
            "phase11_9_protocol_may_be_frozen": False,
            "phase12_authorized": False,
            "merge_allowed": False,
            "release_allowed": False,
            "superiority_claim_allowed": False,
        },
    }
    passed = all(bool(gate["passed"]) for gate in gates.values())
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": "synthetic offline answer-blind projection engineering",
        "source": {
            "historical_phase11_8_3": historical_boundary,
            "historical_result_changed": False,
        },
        "protocol": {
            "path": PROTOCOL_PATH,
            "sha256": LOCKED_PROTOCOL_SHA256,
            "fixture_path": FIXTURE_PATH,
            "fixture_sha256": LOCKED_FIXTURE_SHA256,
            "candidate_path": CANDIDATE_V2_PATH,
            "candidate_sha256": LOCKED_CANDIDATE_V2_SHA256,
            "candidate_family": PROJECTION_FAMILY,
            "future_runner_path": LIVE_RUNNER_PATH,
            "future_runner_sha256": LOCKED_LIVE_RUNNER_SHA256,
            "projection_inputs": [
                "question",
                "selected_evidence",
                "budget_chars",
                "max_block_chars",
                "min_block_chars",
            ],
            "reference_answer_or_sentinel_passed_to_projector": False,
            "fixture_replays": EXPECTED_REPLAYS,
        },
        "fixture_disclosure": {
            "synthetic": True,
            "authored_after_phase11_8": True,
            "case_count": len(outcomes),
            "contains_phase11_7_or_phase12_content": False,
            "predictive_quality_claim_allowed": False,
        },
        "projection": {
            "controls": [
                "historical_equal_cap",
                "rank_weighted_query_window_head_tail_v1",
            ],
            "candidate": PROJECTION_FAMILY,
            "equal_cap_hits": equal_fixture_hits,
            "v1_hits": v1_fixture_hits,
            "v2_hits": v2_hits,
            "historical_equal_cap_over_budget_cases": baseline_over_budget,
            "paired_v2_vs_equal_cap": paired_equal,
            "paired_v2_vs_v1": paired_v1,
            "outcomes": outcomes,
        },
        "traffic": {
            "network_requests": 0,
            "provider_calls": 0,
            "search_calls": 0,
            "model_calls": 0,
            "secrets_bound": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "gates": gates,
        "decision": {
            "offline_engineering_lock_passed": passed,
            "real_case_quality_improvement_proven": False,
            "future_tavily_calibration_authorized": False,
            "phase11_8_3_historical_result_changed": False,
            "phase11_9_protocol_may_be_frozen": False,
            "phase11_9_executed": False,
            "phase12_authorized": False,
            "phase12_executed": False,
            "product_profiles_changed": False,
            "users_choose_provider_model_and_credentials": True,
            "merge_allowed": False,
            "release_allowed": False,
            "superiority_claim_allowed": False,
            "release_decision": "no-go",
            "next_step": (
                "Review the offline lock. A future 24-request Tavily-only calibration "
                "requires a new explicit authorization."
            ),
        },
        "privacy": {
            "questions_or_markers_in_report": False,
            "fixture_source_text_in_report": False,
            "phase11_7_questions_or_answers_in_report": False,
            "source_titles_urls_or_evidence_in_report": False,
            "credentials_in_report": False,
            "phase12_identifiers_in_report": False,
        },
        "warnings": [
            (
                "The 12 fixtures were authored after the historical failure and prove "
                "engineering invariants only, not real-case quality."
            ),
            (
                "Historical selected evidence covered only 19/24 cases, so the old "
                "20/24 projection floor was unreachable on that packet."
            ),
            (
                "A future run would use new, non-deterministic Tavily packets. Only "
                "within-run paired projection comparisons would be causal."
            ),
        ],
    }


def run(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    historical_paths = (
        MANIFEST_PATH,
        RESERVE_PATH,
        PHASE11_8_3_RESULT_PATH,
        CANDIDATE_V1_PATH,
        RUNTIME_PROTOCOL_PATH,
        RUNTIME_RESULT_PATH,
    )
    return build_report(
        protocol_raw=(root / PROTOCOL_PATH).read_bytes(),
        fixture_raw=(root / FIXTURE_PATH).read_bytes(),
        candidate_v2_raw=(root / CANDIDATE_V2_PATH).read_bytes(),
        live_runner_raw=(root / LIVE_RUNNER_PATH).read_bytes(),
        historical_raw={path: (root / path).read_bytes() for path in historical_paths},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    rendered = json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
