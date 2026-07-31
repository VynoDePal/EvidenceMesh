from __future__ import annotations

import ast
import copy
import hashlib
import json
import stat
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scripts.prepare_closed_alpha_a0 import (
    CANDIDATE_SHA,
    CANDIDATE_TREE,
    DEFAULT_PLAN,
    DEFAULT_PROTOCOL,
    DEFAULT_SCHEMA,
    A0Error,
    run,
    validate_feedback_report,
    validate_feedback_schema,
    validate_plan,
    write_private_json,
)

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/prepare_closed_alpha_a0.py"
WORKFLOW = ROOT / ".github/workflows/closed-alpha-a0-preflight.yml"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _feedback(today: date) -> dict[str, Any]:
    return {
        "schema_version": "evidencemesh.closed-alpha-a0.session.v1",
        "protocol_version": "closed-alpha-a0-v1",
        "candidate_sha": CANDIDATE_SHA,
        "participant_code": "p-0123456789abcdef",
        "session_code": "s-0123456789abcdef0123456789abcdef",
        "slot_id": "C01",
        "profile": "community",
        "task": {
            "slot": 1,
            "kind": "prescribed",
            "category": "general_reference",
        },
        "retention": {
            "collected_on": today.isoformat(),
            "delete_after": (today + timedelta(days=14)).isoformat(),
        },
        "consent": {
            "version": "closed-alpha-a0-consent-v1",
            "confirmed": True,
            "authority_confirmed": True,
            "withdrawal_requested": False,
        },
        "outcome": {
            "status": "completed",
            "duration_seconds": 45,
            "useful": True,
            "blocking": False,
            "failure_kind": "none",
        },
        "traffic": {
            "provider_attempts": 3,
            "tavily_attempts": 0,
            "provider_errors": 0,
            "evidencemesh_model_attempts": 0,
            "automatic_retries": 0,
            "fallbacks": 0,
            "repairs": 0,
        },
        "grounding_counts": {
            "results": 10,
            "citations": 4,
            "resolvable_citations": 4,
            "supported_citations": 4,
        },
        "privacy": {
            "cache_disabled": True,
            "raw_runtime_objects_serialized": False,
            "sensitive_input_detected": False,
            "incident_detected": False,
        },
    }


def test_committed_a0_kit_is_deterministic_zero_traffic_and_live_blocked() -> None:
    first = run()
    second = run()

    assert first == second
    assert first["status"] == "prepared_blocked_before_live"
    assert first["candidate"] == {
        "name": "evidencemesh-0.1.0-alpha-rc.2",
        "commit_sha": CANDIDATE_SHA,
        "git_tree_sha1": CANDIDATE_TREE,
        "workflow_run_id": 30632190869,
    }
    assert all(first["gates"].values())
    assert all(value == 0 for value in first["traffic"].values())
    assert first["decision"] == {
        "preparation_passed": True,
        "runtime_budget_enforcement_ready": False,
        "tester_contact_allowed": False,
        "live_execution_allowed": False,
        "merge_allowed": False,
        "public_release_allowed": False,
        "quality_claim_allowed": False,
        "phase12_allowed": False,
    }
    serialized = json.dumps(first, sort_keys=True).lower()
    for forbidden in ("http://", "https://", "@", "query", "answer", "snippet", str(ROOT)):
        assert forbidden not in serialized


def test_committed_hashes_and_recommended_budget_are_frozen() -> None:
    plan = _json(DEFAULT_PLAN)
    assert plan["protocol_sha256"] == hashlib.sha256(DEFAULT_PROTOCOL.read_bytes()).hexdigest()
    assert plan["feedback_schema_sha256"] == hashlib.sha256(DEFAULT_SCHEMA.read_bytes()).hexdigest()
    assert plan["budget"] == {
        "sessions_total_max": 40,
        "sessions_per_participant_max": 5,
        "provider_attempts_per_session_max": 6,
        "provider_attempts_total_max": 240,
        "tavily_attempts_community_session_max": 0,
        "tavily_attempts_quality_session_max": 4,
        "tavily_attempts_total_max": 40,
        "evidencemesh_model_attempts_total_max": 0,
        "automatic_retries_total_max": 0,
        "fallbacks_total_max": 0,
        "repairs_total_max": 0,
        "concurrent_sessions_max": 2,
        "request_starts_per_minute_max": 10,
        "waves_max": 1,
    }
    assert [slot["profile"] for slot in plan["cohort"]["slots"]].count("community") == 6
    assert [slot["profile"] for slot in plan["cohort"]["slots"]].count("quality") == 2


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value["authority"].__setitem__("live_execution_authorized", True),
        lambda value: value["authority"].__setitem__("tester_contact_authorized", True),
        lambda value: value["candidate"].__setitem__("commit_sha", "a" * 40),
        lambda value: value["budget"].__setitem__("provider_attempts_total_max", 241),
        lambda value: value["budget"].__setitem__("automatic_retries_total_max", 1),
        lambda value: value["runtime_readiness"].__setitem__(
            "runtime_budget_enforcement_ready", True
        ),
        lambda value: value["traffic"].__setitem__("provider_attempts", 1),
        lambda value: value["privacy"].__setitem__("free_text_allowed", True),
        lambda value: value["cohort"]["slots"][0].__setitem__("profile", "quality"),
    ],
)
def test_plan_mutations_fail_closed(mutator: Any) -> None:
    plan = copy.deepcopy(_json(DEFAULT_PLAN))
    mutator(plan)
    with pytest.raises(A0Error):
        validate_plan(plan)


def test_feedback_schema_is_recursively_closed_and_aggregate_only() -> None:
    schema = _json(DEFAULT_SCHEMA)
    validate_feedback_schema(schema)

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    properties = schema["properties"]
    assert set(schema["required"]) == set(properties)
    assert "description" not in properties
    assert "free_text" not in properties


def test_json_schema_and_python_validator_share_cross_field_failures() -> None:
    today = date(2026, 7, 31)
    schema = _json(DEFAULT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    mutations = [
        lambda value: value.__setitem__("profile", "quality"),
        lambda value: value["traffic"].__setitem__("tavily_attempts", 1),
        lambda value: value["task"].__setitem__("kind", "real_non_sensitive"),
        lambda value: value["outcome"].__setitem__("blocking", True),
        lambda value: value["outcome"].__setitem__("failure_kind", "provider"),
    ]
    for mutator in mutations:
        report = _feedback(today)
        mutator(report)
        assert list(validator.iter_errors(report))
        with pytest.raises(A0Error):
            validate_feedback_report(report, today=today)


def test_valid_aggregate_feedback_passes_without_runtime_payloads() -> None:
    today = date(2026, 7, 31)
    report = _feedback(today)
    validate_feedback_report(report, today=today)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.__setitem__("query", "canary"),
        lambda value: value["task"].__setitem__("text", "canary"),
        lambda value: value.__setitem__("participant_code", "person@example.test"),
        lambda value: value.__setitem__("profile", "quality"),
        lambda value: value["traffic"].__setitem__("provider_attempts", 7),
        lambda value: value["traffic"].__setitem__("tavily_attempts", 1),
        lambda value: value["traffic"].__setitem__("evidencemesh_model_attempts", 1),
        lambda value: value["traffic"].__setitem__("automatic_retries", 1),
        lambda value: value["traffic"].__setitem__("provider_errors", 4),
        lambda value: value["retention"].__setitem__("delete_after", "2026-08-15"),
        lambda value: value["consent"].__setitem__("withdrawal_requested", True),
        lambda value: value["outcome"].__setitem__("blocking", True),
        lambda value: value["grounding_counts"].__setitem__("supported_citations", 5),
        lambda value: value["privacy"].__setitem__("cache_disabled", False),
        lambda value: value["privacy"].__setitem__("raw_runtime_objects_serialized", True),
    ],
)
def test_feedback_mutations_fail_closed(mutator: Any) -> None:
    today = date(2026, 7, 31)
    report = _feedback(today)
    mutator(report)
    with pytest.raises(A0Error):
        validate_feedback_report(report, today=today)


def test_expired_and_future_feedback_fail_closed() -> None:
    collected = date(2026, 7, 1)
    report = _feedback(collected)
    with pytest.raises(A0Error, match="expired"):
        validate_feedback_report(report, today=collected + timedelta(days=14))
    with pytest.raises(A0Error, match="future"):
        validate_feedback_report(report, today=collected - timedelta(days=1))


def test_private_writer_is_atomic_and_enforces_modes(tmp_path: Path) -> None:
    private_directory = tmp_path / "private"
    first = run()
    output = private_directory / "preflight.json"

    write_private_json(output, first)
    write_private_json(output, first)

    assert json.loads(output.read_bytes()) == first
    assert stat.S_IMODE(private_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert list(private_directory.iterdir()) == [output]


def test_private_writer_rejects_public_directory_and_symlink(tmp_path: Path) -> None:
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    with pytest.raises(A0Error, match="not private"):
        write_private_json(public / "preflight.json", run())

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = private / "preflight.json"
    link.symlink_to(target)
    with pytest.raises(A0Error, match="unsafe output target"):
        write_private_json(link, run())
    assert target.read_text(encoding="utf-8") == "{}"


def test_runner_has_no_network_process_environment_or_dynamic_code_capability() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    calls: set[str] = set()
    attributes: set[str] = set()
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
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)

    assert imported_roots.isdisjoint(
        {
            "aiohttp",
            "asyncio",
            "boto3",
            "httpx",
            "openai",
            "requests",
            "socket",
            "subprocess",
            "tavily",
            "urllib",
        }
    )
    assert calls.isdisjoint({"compile", "eval", "exec", "getenv", "popen", "system", "urlopen"})
    assert attributes.isdisjoint({"environ", "environb"})


def test_workflow_is_read_only_a0_only_and_disables_research_networking() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "permissions:\n  contents: read\n" in text
    assert "workflow_dispatch" not in text
    assert "paths:" not in text
    assert "github.event.pull_request.number == 1" in text
    assert "github.event.pull_request.head.sha" in text
    assert "persist-credentials: false" in text
    assert "fetch-depth: 0" in text
    assert CANDIDATE_SHA in text
    assert CANDIDATE_TREE in text
    assert "git merge-base --is-ancestor" in text
    assert "git diff --name-only" in text
    assert "/usr/bin/unshare --net" in text
    assert "env -i" in text
    assert "cmp " in text
    assert "stat --format=%a" in text
    for forbidden in (
        "secrets.",
        "github.token",
        "curl ",
        "wget ",
        "upload-artifact",
        "download-artifact",
        "actions/attest",
        "gh release",
    ):
        assert forbidden not in lowered
    action_lines = [line.strip() for line in text.splitlines() if "uses:" in line]
    assert action_lines
    assert all(
        "@" in line and not line.rsplit("@", 1)[1].split()[0].startswith("v")
        for line in action_lines
    )


def test_protocol_keeps_live_release_and_sensitive_use_blocked() -> None:
    protocol = DEFAULT_PROTOCOL.read_text(encoding="utf-8")
    for required in (
        "A0 is preparation-only",
        "separate explicit GO",
        "no fail-closed global governor",
        "six-attempt session ceiling",
        "40 sessions",
        "240",
        "14 days",
        "medical, legal, financial",
        "cannot authorize merge",
    ):
        assert required in protocol
