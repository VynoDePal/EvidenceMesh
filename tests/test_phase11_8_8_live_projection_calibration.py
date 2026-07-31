from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from benchmarks import run_phase11_8_8_live_projection_calibration as live


@dataclass(frozen=True, slots=True)
class Row:
    id: str
    question: str
    answers: tuple[str, ...]
    gold_urls: tuple[str, ...]


def _rows() -> list[Row]:
    return [
        Row(
            id=f"private-case-{index:02d}",
            question=f"Private question {index}?",
            answers=(f"Private answer {index}",),
            gold_urls=(f"https://gold-{index}.invalid/item",),
        )
        for index in range(24)
    ]


def _reserve_manifest() -> dict[str, Any]:
    return {
        "sealed_cases": [
            {"row_index": 1000 + index, "case_id": f"reserve-{index:02d}"} for index in range(96)
        ]
    }


def _selection_facts() -> live.SelectionFacts:
    return live.SelectionFacts(
        phase11_selection_count=24,
        phase12_reserve_count=96,
        selections_disjoint=True,
        loaded_rows_match_phase11_selection=True,
        reserve_rows_selected=0,
        reserve_rows_scored=0,
    )


def _authorization() -> live.AuthorizationAttestation:
    return live.AuthorizationAttestation(
        attestation_sha256="9" * 64,
        lock_commit_sha="a" * 40,
        authorization_commit_sha="b" * 40,
        workflow_run_attempt=1,
        commit_a_locks_verified=True,
        lineage_verified=True,
        no_prior_authorization_run_verified=True,
    )


def _outcomes() -> tuple[dict[str, Any], ...]:
    outcomes: list[dict[str, Any]] = []
    for index in range(24):
        selected_hit = index < 22
        for arm in live.locked.PROJECTION_ARMS:
            prompt_hit = index < (22 if arm == live.locked.V2_ARM else 19)
            outcomes.append(
                {
                    "case_id": f"private-case-{index:02d}",
                    "arm": arm,
                    "available": True,
                    "answer_key_in_selected_evidence": selected_hit,
                    "answer_key_in_prompt_evidence": prompt_hit,
                    "raw_pool_sha256": f"raw-{index}",
                    "selected_packet_sha256": f"selected-{index}",
                    "prompt_packet_sha256": f"prompt-{arm}-{index}",
                    "deterministic_replays": True,
                    "metadata_preserved": True,
                    "source_text_preserved": True,
                    "replay_count": 3,
                    "budget_compliant": arm != live.locked.EQUAL_CAP_ARM,
                    "historical_equal_cap_over_budget": (arm == live.locked.EQUAL_CAP_ARM),
                }
            )
    return tuple(outcomes)


def _retrieval(*, failure_kind: str | None = None) -> live.RetrievalResult:
    completed = 24 if failure_kind is None else 1
    return live.RetrievalResult(
        outcomes=_outcomes() if failure_kind is None else (),
        attempted_cases=completed,
        successful_cases=24 if failure_kind is None else 0,
        logical_calls=completed,
        actual_http_attempts=completed,
        http_responses=completed,
        status_counts={"200": 24} if failure_kind is None else {"429": 1},
        failure_kind=failure_kind,
        stopped_on_first_failure=failure_kind is not None,
        provider_private_values=(
            "Private provider title",
            "https://provider.invalid/private",
            "Private provider snippet",
        ),
    )


def test_argument_contract_requires_explicit_live_triplet() -> None:
    with pytest.raises(ValueError, match="authorize-live-run"):
        live.validate_arguments(
            argparse.Namespace(
                check_only=False,
                authorize_live_run=False,
                authorization_verified=False,
                authorization_attestation=None,
                dataset=None,
                output=None,
            )
        )
    with pytest.raises(ValueError, match="authorization-attestation"):
        live.validate_arguments(
            argparse.Namespace(
                check_only=False,
                authorize_live_run=True,
                authorization_verified=False,
                authorization_attestation=None,
                dataset=None,
                output=None,
            )
        )
    live.validate_arguments(
        argparse.Namespace(
            check_only=False,
            authorize_live_run=True,
            authorization_verified=True,
            authorization_attestation=Path("attestation.json"),
            dataset=Path("dataset.csv"),
            output=Path("result.json"),
        )
    )


def test_check_only_does_not_read_secret_dataset_network_or_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency = live.DependencyLock(
        "benchmarks/run_phase11_8_8_projection_calibration.py",
        "a" * 64,
    )
    monkeypatch.setattr(
        live,
        "validate_dependency_manifest",
        lambda _path: (dependency,),
    )
    monkeypatch.setattr(
        live.locked,
        "validate_locked_sources",
        lambda _arguments: {"historical_phase11_8_3_result": "fail_10_of_14"},
    )

    environment_type = type(live.os.environ)
    original_get = environment_type.get

    def guarded_get(
        environment: object,
        key: str,
        default: str | None = None,
    ) -> str | None:
        if key == "TAVILY_API_KEY":
            raise AssertionError("check-only accessed a secret")
        return original_get(environment, key, default)  # type: ignore[arg-type]

    monkeypatch.setattr(environment_type, "get", guarded_get)
    report = live.validate_check_only(Path("public-locks.json"))
    assert report["status"] == "check_only_passed"
    assert report["network_requests"] == 0
    assert report["secrets_read"] == 0
    assert report["dataset_opened"] is False
    assert report["output_reserved"] is False


def test_dependency_manifest_is_exact_relative_and_hash_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency = tmp_path / "dependency.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    relative_path = "dependency.py"
    manifest_payload = {
        "schema_version": 1,
        "manifest": live.DEPENDENCY_MANIFEST_NAME,
        "dependencies": {relative_path: hashlib.sha256(dependency.read_bytes()).hexdigest()},
    }
    manifest = tmp_path / "manifest.json"
    raw = (
        json.dumps(
            manifest_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    manifest.write_bytes(raw)
    monkeypatch.setattr(live, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        live,
        "SOURCE_MANIFEST_REQUIRED_PATHS",
        frozenset({relative_path}),
    )
    monkeypatch.setattr(
        live,
        "LOCKED_DEPENDENCY_MANIFEST_SHA256",
        hashlib.sha256(raw).hexdigest(),
    )
    assert live.validate_dependency_manifest(manifest) == (
        live.DependencyLock(
            relative_path,
            hashlib.sha256(dependency.read_bytes()).hexdigest(),
        ),
    )
    dependency.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="locked dependency changed"):
        live.validate_dependency_manifest(manifest)


def test_dependency_contract_covers_the_frozen_phase_runtime_and_lockfiles() -> None:
    root = Path(live.__file__).parents[1]
    runtime_sources = {
        path.relative_to(root).as_posix() for path in (root / "src/evidencemesh").rglob("*.py")
    }
    post_phase_sources = {"src/evidencemesh/governor.py"}
    assert post_phase_sources <= runtime_sources
    assert post_phase_sources.isdisjoint(live.SOURCE_MANIFEST_REQUIRED_PATHS)
    assert runtime_sources - post_phase_sources <= live.SOURCE_MANIFEST_REQUIRED_PATHS
    assert {
        "benchmarks/__init__.py",
        "pyproject.toml",
        "uv.lock",
    } <= live.SOURCE_MANIFEST_REQUIRED_PATHS
    assert "benchmarks/run_phase11_8_8_live_projection_calibration.py" not in (
        live.SOURCE_MANIFEST_REQUIRED_PATHS
    )


def test_selection_boundary_is_derived_without_publishing_selectors() -> None:
    rows = _rows()
    manifest = {
        "cases": [{"row_index": index, "case_id": row.id} for index, row in enumerate(rows)]
    }
    facts = live.derive_selection_facts(manifest, _reserve_manifest(), rows)
    assert facts.passed
    assert facts.reserve_rows_selected == 0
    assert facts.reserve_rows_scored == 0

    overlapping = _reserve_manifest()
    overlapping["sealed_cases"][0] = {
        "row_index": 0,
        "case_id": rows[0].id,
    }
    assert not live.derive_selection_facts(manifest, overlapping, rows).passed


def test_authorization_attestation_requires_exact_one_shot_lineage(
    tmp_path: Path,
) -> None:
    payload = {
        "schema_version": 1,
        "authorization": "phase11_8_8_live_projection_calibration_once",
        "repository": "VynoDePal/EvidenceMesh",
        "pull_request_number": 1,
        "head_branch": "agent/evidencemesh-v0.1",
        "workflow_path": (".github/workflows/phase11-8-8-live-projection-calibration.yml"),
        "lock_commit_sha": "a" * 40,
        "authorization_commit_sha": "b" * 40,
        "workflow_run_attempt": 1,
        "commit_a_locks_verified": True,
        "single_parent_verified": True,
        "subject_verified": True,
        "marker_verified": True,
        "two_path_diff_verified": True,
        "same_repository_head_verified": True,
        "no_rerun_verified": True,
        "no_prior_authorization_run_verified": True,
    }
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    attestation = live.validate_authorization_attestation(path)
    assert attestation.verified
    assert attestation.workflow_run_attempt == 1
    assert attestation.no_prior_authorization_run_verified is True

    payload["workflow_run_attempt"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="locked workflow"):
        live.validate_authorization_attestation(path)

    payload["workflow_run_attempt"] = 1
    payload["no_prior_authorization_run_verified"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="locked workflow"):
        live.validate_authorization_attestation(path)


def test_attempt_counter_enforces_the_actual_http_cap() -> None:
    counter = live.AttemptCounter(maximum=2)
    request = live.locked.phase11_8.httpx.Request(
        "POST",
        "https://api.tavily.com/search",
    )
    asyncio.run(counter.on_request(request))
    asyncio.run(counter.on_request(request))
    with pytest.raises(live.HTTPAttemptLimitError):
        asyncio.run(counter.on_request(request))
    assert counter.attempts == 2

    non_tavily = live.locked.phase11_8.httpx.Request(
        "POST",
        "https://example.invalid/model",
    )
    with pytest.raises(live.NonTavilyAttemptError):
        asyncio.run(live.AttemptCounter().on_request(non_tavily))


@pytest.mark.parametrize(
    "payload",
    [
        {"results": []},
        {
            "results": [
                {
                    "url": "https://source.example/item",
                    "title": "",
                    "content": "",
                }
            ]
        },
    ],
)
async def test_tavily_response_hook_accepts_valid_200_envelopes(
    payload: dict[str, Any],
) -> None:
    counter = live.AttemptCounter()
    response = live.locked.phase11_8.httpx.Response(
        200,
        json=payload,
        request=live.locked.phase11_8.httpx.Request(
            "POST",
            "https://api.tavily.com/search",
        ),
    )

    await counter.on_response(response)

    assert counter.responses == 1
    assert counter.validated_200_responses == 1
    assert counter.response_validation_failures == 0
    assert counter.first_failure_kind is None
    assert counter.status_counts == {"200": 1}


@pytest.mark.parametrize(
    ("payload", "expected_failure"),
    [
        ([], "invalid_response"),
        ({}, "invalid_response"),
        ({"results": None}, "invalid_response"),
        ({"results": ["not-an-object"]}, "invalid_response"),
        (
            {"results": [{"url": "", "title": "private", "content": "private"}]},
            "invalid_response",
        ),
        (
            {"results": [{"url": "   ", "title": "private", "content": "private"}]},
            "invalid_response",
        ),
        (
            {
                "results": [
                    {
                        "url": "https://source.example/item",
                        "title": 7,
                        "content": "private",
                    }
                ]
            },
            "invalid_response",
        ),
        (
            {
                "results": [
                    {
                        "url": "https://source.example/item",
                        "title": "private",
                    }
                ]
            },
            "invalid_response",
        ),
    ],
)
async def test_tavily_response_hook_rejects_malformed_200_schema_privately(
    payload: object,
    expected_failure: str,
) -> None:
    counter = live.AttemptCounter()
    response = live.locked.phase11_8.httpx.Response(
        200,
        json=payload,
        request=live.locked.phase11_8.httpx.Request(
            "POST",
            "https://api.tavily.com/search",
        ),
    )

    with pytest.raises(live.ProviderResponseValidationError) as raised:
        await counter.on_response(response)

    assert raised.value.failure_kind == expected_failure
    assert str(raised.value) == expected_failure
    assert counter.first_failure_kind == expected_failure
    assert counter.response_validation_failures == 1
    assert counter.validated_200_responses == 0
    assert "private" not in repr(counter)


@pytest.mark.parametrize(
    ("status_code", "expected_failure"),
    [
        (201, "http_status"),
        (429, "http_status_429"),
        (503, "http_status_503"),
    ],
)
async def test_tavily_response_hook_rejects_non_200_without_reading_content(
    status_code: int,
    expected_failure: str,
) -> None:
    private_marker = "DO_NOT_RETAIN_PROVIDER_CONTENT"
    counter = live.AttemptCounter()
    response = live.locked.phase11_8.httpx.Response(
        status_code,
        content=private_marker,
        request=live.locked.phase11_8.httpx.Request(
            "POST",
            "https://api.tavily.com/search",
        ),
    )

    with pytest.raises(live.ProviderResponseValidationError) as raised:
        await counter.on_response(response)

    assert raised.value.failure_kind == expected_failure
    assert counter.first_failure_kind == expected_failure
    assert counter.response_validation_failures == 1
    assert private_marker not in repr(counter)
    assert private_marker not in str(raised.value)


@pytest.mark.parametrize(
    ("content", "expected_failure"),
    [
        (b"not-json", "invalid_json"),
        (b"\xff", "invalid_response_encoding"),
    ],
)
async def test_tavily_response_hook_rejects_invalid_200_json(
    content: bytes,
    expected_failure: str,
) -> None:
    counter = live.AttemptCounter()
    response = live.locked.phase11_8.httpx.Response(
        200,
        content=content,
        request=live.locked.phase11_8.httpx.Request(
            "POST",
            "https://api.tavily.com/search",
        ),
    )

    with pytest.raises(live.ProviderResponseValidationError) as raised:
        await counter.on_response(response)

    assert raised.value.failure_kind == expected_failure
    assert counter.first_failure_kind == expected_failure
    assert counter.response_validation_failures == 1


def test_all_three_arms_are_projected_before_reference_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase11_8 = live.locked.phase11_8
    block = phase11_8.EvidenceBlock(
        citation_id="S1",
        title="Public title",
        url="https://source.example/item",
        text="Private answer appears in this selected evidence.",
        providers=("tavily",),
    )
    bundle = phase11_8.ArmBundle(
        case_id="private-case",
        arm=phase11_8.EXPANDED_ARM,
        status="completed",
        blocks=(block,),
        raw_result_count=1,
        fused_result_count=1,
        selected_result_count=1,
        unique_domains=1,
        selected_tavily_count=1,
        provider_stage_counts={},
        reservation_policy="none",
        reservation_requested=0,
        reservation_eligible=0,
        reservation_feasible=0,
        reservation_target=0,
        reservation_fulfilled=0,
        reservation_shortfall_reason=None,
        retrieval_latency_ms=1.0,
        error_kind=None,
    )
    row = Row(
        id="private-case",
        question="Private question?",
        answers=("Private answer",),
        gold_urls=(),
    )
    events: list[str] = []

    def project_spy(
        arm: str,
        question: str,
        blocks: tuple[Any, ...],
        **_parameters: Any,
    ) -> tuple[Any, ...]:
        assert question == row.question
        events.append(f"project:{arm}")
        return blocks

    def answer_covered_spy(
        answers: tuple[str, ...],
        texts: Any,
    ) -> bool:
        assert answers == row.answers
        tuple(texts)
        events.append("answer_covered")
        return True

    def coupled_outcome_must_not_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("historical coupled projection/scoring function was called")

    monkeypatch.setattr(live.locked, "project_blocks", project_spy)
    monkeypatch.setattr(live.locked.phase11_8, "answer_covered", answer_covered_spy)
    monkeypatch.setattr(
        live.locked,
        "public_projection_outcome",
        coupled_outcome_must_not_run,
    )

    outcomes = live.project_and_score_packet(
        row,
        bundle,
        raw_pool_hash="a" * 64,
        evidence_budget_chars=live.EVIDENCE_BUDGET_CHARS,
        max_block_chars=live.MAX_BLOCK_CHARS,
        min_block_chars=live.MIN_BLOCK_CHARS,
        projection_replays=1,
    )

    assert events[:3] == [f"project:{arm}" for arm in live.locked.PROJECTION_ARMS]
    assert events[3] == "answer_covered"
    assert len(outcomes) == 3


def test_output_reservation_is_exclusive_and_atomically_replaced(
    tmp_path: Path,
) -> None:
    output = tmp_path / "result.json"
    with live.OutputReservation(output) as reservation:
        assert output.read_bytes() == b"reserved\n"
        with pytest.raises(FileExistsError), live.OutputReservation(output):
            pass
        reservation.commit({"status": "complete"})
    assert json.loads(output.read_bytes()) == {"status": "complete"}
    assert not list(tmp_path.glob(".*.tmp"))


def test_public_report_is_aggregate_only_private_and_has_thirteen_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live,
        "LOCKED_DEPENDENCY_MANIFEST_SHA256",
        "b" * 64,
    )
    report = live.build_public_report(
        dependency_locks=(live.DependencyLock("benchmarks/dependency.py", "c" * 64),),
        authorization=_authorization(),
        dataset_sha256="d" * 64,
        selections=_selection_facts(),
        retrieval=_retrieval(),
        rows=_rows(),
        reserve_manifest=_reserve_manifest(),
        tavily_api_key="PRIVATE_TAVILY_KEY",
    )
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    assert report["run_status"] == "completed"
    assert report["traffic"]["static_dataset_fetches"] == 1
    assert report["traffic"]["logical_operations_started"] == 24
    assert report["traffic"]["logical_operations_completed"] == 24
    assert report["traffic"]["tavily_http_attempts_actual"] == 24
    assert report["traffic"]["model_requests"] == 0
    assert report["traffic"]["gemini_requests"] == 0
    assert report["traffic"]["token_count_requests"] == 0
    assert report["traffic"]["retries"] == 0
    assert report["traffic"]["fallback_requests"] == 0
    assert report["traffic"]["repair_requests"] == 0
    assert report["decision"]["gate_count"] == 13
    assert len(report["decision"]["gates"]) == 13
    assert [gate["name"] for gate in report["decision"]["gates"]] == list(live.GATE_NAMES)
    assert report["decision"]["gates"][1] == {
        "name": "one_shot_authorization_lineage",
        "passed": True,
    }
    assert report["decision"]["projection_candidate_passed"] is True
    assert report["decision"]["phase12_authorized"] is False
    assert report["decision"]["release_decision"] == "no-go"
    assert report["privacy"]["passed"] is True
    assert "PRIVATE_TAVILY_KEY" not in rendered
    assert "Private question" not in rendered
    assert "Private answer" not in rendered
    assert "gold-" not in rendered
    assert "provider.invalid" not in rendered
    assert "private-case-" not in rendered
    assert "reserve-" not in rendered
    assert "projection_outcomes" not in rendered
    assert "raw_pool_sha256" not in rendered
    assert "/workspace/" not in rendered


def test_provider_failure_is_bounded_fail_fast_and_consistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live,
        "LOCKED_DEPENDENCY_MANIFEST_SHA256",
        "e" * 64,
    )
    retrieval = _retrieval(failure_kind="http_status_429")
    assert retrieval.attempted_cases == 1
    assert retrieval.successful_cases == 0
    assert retrieval.outcomes == ()
    report = live.build_public_report(
        dependency_locks=(live.DependencyLock("benchmarks/dependency.py", "f" * 64),),
        authorization=_authorization(),
        dataset_sha256="1" * 64,
        selections=_selection_facts(),
        retrieval=retrieval,
        rows=_rows(),
        reserve_manifest=_reserve_manifest(),
        tavily_api_key="PRIVATE_TAVILY_KEY",
    )
    assert report["run_status"] == "aborted_provider_failure"
    assert report["retrieval"]["failure_kind"] == "http_status_429"
    assert report["retrieval"]["stopped_on_first_failure"] is True
    assert report["retrieval"]["attempted_cases"] == 1
    assert report["traffic"]["logical_operations_started"] == 1
    assert report["traffic"]["logical_operations_completed"] == 0
    assert report["traffic"]["tavily_http_attempts_actual"] == 1
    assert report["projection"]["scored_case_count"] == 0
    assert report["decision"]["projection_candidate_passed"] is False
    assert report["decision"]["diagnostic_status"] == ("provider_failure_inconclusive")


def test_runner_has_no_direct_model_or_gemini_client_imports() -> None:
    source = Path(live.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(
        module.startswith(
            (
                "google",
                "google.generativeai",
                "openai",
                "anthropic",
                "transformers",
                "torch",
            )
        )
        for module in imported_modules
    )
    assert "request_gemini_completion(" not in source
    assert "generateContent" not in source
