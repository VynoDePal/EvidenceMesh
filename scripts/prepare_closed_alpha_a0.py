#!/usr/bin/env python3
"""Validate the zero-traffic closed-alpha A0 kit and private report contract."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "alpha/closed_alpha_a0_plan_v1.json"
DEFAULT_SCHEMA = ROOT / "alpha/closed_alpha_a0_feedback.schema.json"
DEFAULT_PROTOCOL = ROOT / "docs/closed-alpha-a0-protocol-v1.md"
PLAN_SCHEMA = "evidencemesh.closed-alpha-a0.plan.v1"
REPORT_SCHEMA = "evidencemesh.closed-alpha-a0.session.v1"
PREFLIGHT_SCHEMA = "evidencemesh.closed-alpha-a0.preflight.v1"
PROTOCOL_VERSION = "closed-alpha-a0-v1"
CONSENT_VERSION = "closed-alpha-a0-consent-v1"
CANDIDATE_SHA = "81b5f8a8abd4302b27ad123bd5505e1757eadc7f"
CANDIDATE_TREE = "8bf47f72814befd5868adc48c7766a0cb278d52d"
MAX_JSON_BYTES = 128 * 1024
SLOTS = {
    "C01": "community",
    "C02": "community",
    "C03": "community",
    "C04": "community",
    "C05": "community",
    "C06": "community",
    "Q01": "quality",
    "Q02": "quality",
}
FAILURE_KINDS = {
    "none",
    "installation",
    "configuration",
    "provider",
    "timeout",
    "empty_result",
    "citation",
    "privacy",
    "budget",
    "candidate_identity",
    "other",
}
TASK_CATEGORIES = {
    "general_reference",
    "current_information",
    "technical",
    "academic",
    "code",
    "other_non_sensitive",
}
FORBIDDEN_PROPERTY_MARKERS = {
    "answer",
    "comment",
    "content",
    "cookie",
    "domain",
    "email",
    "exception",
    "header",
    "hostname",
    "link",
    "message",
    "prompt",
    "query",
    "quote",
    "snippet",
    "stack",
    "title",
    "token",
    "traceback",
    "uri",
    "url",
    "username",
}


class A0Error(ValueError):
    """Raised when the A0 preparation contract fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise A0Error(message)


def _object(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return cast(dict[str, Any], value)


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    _require(set(value) == expected, f"{label} fields drifted")


def _bounded_int(value: object, minimum: int, maximum: int, label: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be integer")
    normalized = cast(int, value)
    _require(minimum <= normalized <= maximum, f"{label} is outside its bound")
    return normalized


def _read_regular(path: Path, *, max_bytes: int, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise A0Error(f"cannot stat {label}") from exc
    _require(stat.S_ISREG(metadata.st_mode), f"{label} must be a regular file")
    _require(not path.is_symlink(), f"{label} must not be a symlink")
    _require(metadata.st_size <= max_bytes, f"{label} exceeds its byte limit")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise A0Error(f"cannot read {label}") from exc
    _require(len(payload) == metadata.st_size, f"{label} changed while read")
    return payload


def _read_json(path: Path, label: str) -> dict[str, Any]:
    payload = _read_regular(path, max_bytes=MAX_JSON_BYTES, label=label)
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A0Error(f"{label} is not valid JSON") from exc
    return _object(decoded, label)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def validate_plan(plan: Mapping[str, Any]) -> None:
    _exact_keys(
        plan,
        {
            "authority",
            "budget",
            "candidate",
            "cohort",
            "feedback_schema_path",
            "feedback_schema_sha256",
            "privacy",
            "protocol_path",
            "protocol_sha256",
            "runtime_readiness",
            "schema_version",
            "status",
            "stop_thresholds",
            "tasks",
            "traffic",
        },
        "plan",
    )
    _require(plan["schema_version"] == PLAN_SCHEMA, "plan schema drifted")
    _require(plan["status"] == "prepared_blocked_before_live", "plan status drifted")
    _require(
        plan["authority"]
        == {
            "preparation_authorized": True,
            "tester_contact_authorized": False,
            "live_execution_authorized": False,
            "separate_live_go_required": True,
        },
        "A0 authority boundary drifted",
    )
    _require(
        plan["candidate"]
        == {
            "name": "evidencemesh-0.1.0-alpha-rc.2",
            "commit_sha": CANDIDATE_SHA,
            "git_tree_sha1": CANDIDATE_TREE,
            "workflow_run_id": 30632190869,
            "workflow_run_attempt": 1,
            "artifact_name": f"alpha-rc-head-{CANDIDATE_SHA}",
            "artifact_digest_sha256": (
                "487e7118f18ec425908fb1fbb94678795fb8197c9124435957ea843b49327561"
            ),
            "provenance_attestation_id": 38176497,
            "sbom_attestation_id": 38176506,
        },
        "candidate identity drifted",
    )
    expected_budget = {
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
    _require(plan["budget"] == expected_budget, "budget drifted")
    _require(
        plan["tasks"]
        == {
            "per_participant": 5,
            "prescribed_per_participant": 3,
            "real_non_sensitive_per_participant": 2,
            "task_text_collected": False,
        },
        "task allocation drifted",
    )
    cohort = _object(plan["cohort"], "cohort")
    _exact_keys(cohort, {"participant_count", "slots"}, "cohort")
    _require(cohort["participant_count"] == 8, "participant count drifted")
    expected_slots = [
        {"profile": profile, "slot_id": slot_id} for slot_id, profile in SLOTS.items()
    ]
    _require(cohort["slots"] == expected_slots, "cohort slots drifted")
    _require(
        plan["privacy"]
        == {
            "cache_disabled_required": True,
            "free_text_allowed": False,
            "local_only": True,
            "raw_runtime_object_serialization_allowed": False,
            "report_directory_mode": "0700",
            "report_file_mode": "0600",
            "retention_days_max": 14,
            "upload_allowed": False,
        },
        "privacy contract drifted",
    )
    _require(
        plan["runtime_readiness"]
        == {
            "pre_dispatch_global_governor_implemented": False,
            "quality_profile_within_session_attempt_cap": False,
            "runtime_budget_enforcement_ready": False,
        },
        "runtime blocker drifted",
    )
    _require(
        plan["traffic"]
        == {
            "model_attempts": 0,
            "provider_attempts": 0,
            "research_requests": 0,
            "tavily_attempts": 0,
            "tester_sessions": 0,
        },
        "A0 traffic must remain zero",
    )
    _require(
        plan["stop_thresholds"]
        == {
            "blocking_session_rate_strictly_greater_than": 0.1,
            "citation_support_rate_less_than": 0.9,
            "latency_p95_seconds_greater_than": 120,
            "minimum_valid_sessions_for_rate_gates": 20,
            "provider_error_rate_strictly_greater_than": 0.15,
            "unresolvable_citation_sessions_max": 1,
            "useful_session_rate_less_than": 0.7,
        },
        "stop thresholds drifted",
    )
    _require(
        plan["protocol_path"] == "docs/closed-alpha-a0-protocol-v1.md",
        "protocol path drifted",
    )
    _require(
        plan["feedback_schema_path"] == "alpha/closed_alpha_a0_feedback.schema.json",
        "feedback schema path drifted",
    )
    for field in ("protocol_sha256", "feedback_schema_sha256"):
        value = plan[field]
        _require(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            f"{field} must be lowercase SHA-256",
        )


def _walk_schema_objects(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            _require(value.get("additionalProperties") is False, "schema object is not closed")
        for child in value.values():
            _walk_schema_objects(child)
    elif isinstance(value, list):
        for child in value:
            _walk_schema_objects(child)


def validate_feedback_schema(schema: Mapping[str, Any]) -> None:
    _require(schema.get("type") == "object", "feedback schema root drifted")
    _require(schema.get("additionalProperties") is False, "feedback schema root is open")
    conditions = schema.get("allOf")
    _require(isinstance(conditions, list) and len(conditions) == 6, "schema conditions drifted")
    properties = _object(schema.get("properties"), "feedback schema properties")
    required = schema.get("required")
    _require(isinstance(required, list), "feedback schema required list is missing")
    required_fields = cast(list[Any], required)
    _require(set(required_fields) == set(properties), "feedback schema fields are not all required")
    _require(
        properties.get("schema_version", {}).get("const") == REPORT_SCHEMA, "report schema drifted"
    )
    _require(
        properties.get("candidate_sha", {}).get("const") == CANDIDATE_SHA,
        "report candidate drifted",
    )
    _require(
        properties.get("protocol_version", {}).get("const") == PROTOCOL_VERSION,
        "report protocol drifted",
    )
    _require(
        properties.get("participant_code", {}).get("pattern") == r"^p-[0-9a-f]{16}$",
        "participant-code constraint drifted",
    )
    _require(
        properties.get("session_code", {}).get("pattern") == r"^s-[0-9a-f]{32}$",
        "session-code constraint drifted",
    )
    property_names: list[str] = []

    def collect_names(value: object) -> None:
        if isinstance(value, dict):
            nested = value.get("properties")
            if isinstance(nested, dict):
                property_names.extend(str(name) for name in nested)
            for child in value.values():
                collect_names(child)
        elif isinstance(value, list):
            for child in value:
                collect_names(child)

    collect_names(schema)
    for name in property_names:
        lowered = name.lower()
        _require(
            not any(marker in lowered for marker in FORBIDDEN_PROPERTY_MARKERS),
            "feedback schema contains a forbidden property",
        )
    _walk_schema_objects(schema)
    rendered = json.dumps(schema, sort_keys=True).lower()
    _require('"additionalproperties": true' not in rendered, "schema allows extra fields")
    _require('"free_text"' not in rendered, "schema contains free text")


def _date(value: object, label: str) -> date:
    _require(isinstance(value, str), f"{label} must be a date")
    try:
        parsed = date.fromisoformat(cast(str, value))
    except ValueError as exc:
        raise A0Error(f"{label} must be an ISO date") from exc
    _require(parsed.isoformat() == value, f"{label} must be a canonical ISO date")
    return parsed


def validate_feedback_report(report: Mapping[str, Any], *, today: date) -> None:
    expected_root = {
        "schema_version",
        "protocol_version",
        "candidate_sha",
        "participant_code",
        "session_code",
        "slot_id",
        "profile",
        "task",
        "retention",
        "consent",
        "outcome",
        "traffic",
        "grounding_counts",
        "privacy",
    }
    _exact_keys(report, expected_root, "feedback report")
    _require(report["schema_version"] == REPORT_SCHEMA, "feedback schema drifted")
    _require(report["protocol_version"] == PROTOCOL_VERSION, "feedback protocol drifted")
    _require(report["candidate_sha"] == CANDIDATE_SHA, "feedback candidate drifted")
    _require(
        isinstance(report["participant_code"], str)
        and re.fullmatch(r"p-[0-9a-f]{16}", report["participant_code"]) is not None,
        "participant code is invalid",
    )
    _require(
        isinstance(report["session_code"], str)
        and re.fullmatch(r"s-[0-9a-f]{32}", report["session_code"]) is not None,
        "session code is invalid",
    )
    slot_id = report["slot_id"]
    _require(isinstance(slot_id, str) and slot_id in SLOTS, "slot is invalid")
    _require(report["profile"] == SLOTS[cast(str, slot_id)], "slot/profile mismatch")

    task = _object(report["task"], "task")
    _exact_keys(task, {"slot", "kind", "category"}, "task")
    task_slot = _bounded_int(task["slot"], 1, 5, "task slot")
    expected_kind = "prescribed" if task_slot <= 3 else "real_non_sensitive"
    _require(task["kind"] == expected_kind, "task kind does not match task slot")
    _require(task["category"] in TASK_CATEGORIES, "task category is invalid")

    retention = _object(report["retention"], "retention")
    _exact_keys(retention, {"collected_on", "delete_after"}, "retention")
    collected_on = _date(retention["collected_on"], "collection date")
    delete_after = _date(retention["delete_after"], "deletion date")
    _require(delete_after == collected_on + timedelta(days=14), "retention is not 14 days")
    _require(collected_on <= today, "collection date is in the future")
    _require(today < delete_after, "feedback report is expired")

    consent = _object(report["consent"], "consent")
    _require(
        consent
        == {
            "version": CONSENT_VERSION,
            "confirmed": True,
            "authority_confirmed": True,
            "withdrawal_requested": False,
        },
        "consent contract failed",
    )

    outcome = _object(report["outcome"], "outcome")
    _exact_keys(
        outcome,
        {"status", "duration_seconds", "useful", "blocking", "failure_kind"},
        "outcome",
    )
    status_value = outcome["status"]
    _require(status_value in {"completed", "blocked", "aborted"}, "status is invalid")
    _bounded_int(outcome["duration_seconds"], 0, 3600, "duration")
    _require(isinstance(outcome["useful"], bool), "useful must be boolean")
    _require(isinstance(outcome["blocking"], bool), "blocking must be boolean")
    _require(outcome["failure_kind"] in FAILURE_KINDS, "failure kind is invalid")
    completed = status_value == "completed"
    _require(outcome["blocking"] is not completed, "blocking/status mismatch")
    _require((outcome["failure_kind"] == "none") is completed, "failure/status mismatch")
    _require(completed or outcome["useful"] is False, "failed session cannot be useful")

    traffic = _object(report["traffic"], "traffic")
    _exact_keys(
        traffic,
        {
            "provider_attempts",
            "tavily_attempts",
            "provider_errors",
            "evidencemesh_model_attempts",
            "automatic_retries",
            "fallbacks",
            "repairs",
        },
        "traffic",
    )
    attempts = _bounded_int(traffic["provider_attempts"], 0, 6, "provider attempts")
    tavily = _bounded_int(traffic["tavily_attempts"], 0, 4, "Tavily attempts")
    errors = _bounded_int(traffic["provider_errors"], 0, 6, "provider errors")
    _require(tavily <= attempts and errors <= attempts, "traffic counters are inconsistent")
    _require(report["profile"] == "quality" or tavily == 0, "community Tavily use is forbidden")
    for field in (
        "evidencemesh_model_attempts",
        "automatic_retries",
        "fallbacks",
        "repairs",
    ):
        _require(traffic[field] == 0, f"{field} must remain zero")

    counts = _object(report["grounding_counts"], "grounding counts")
    _exact_keys(
        counts,
        {"results", "citations", "resolvable_citations", "supported_citations"},
        "grounding counts",
    )
    _bounded_int(counts["results"], 0, 100, "result count")
    citations = _bounded_int(counts["citations"], 0, 100, "citation count")
    resolvable = _bounded_int(counts["resolvable_citations"], 0, 100, "resolvable citation count")
    supported = _bounded_int(counts["supported_citations"], 0, 100, "supported citation count")
    _require(supported <= resolvable <= citations, "citation counters are inconsistent")

    privacy = _object(report["privacy"], "privacy")
    _require(
        privacy
        == {
            "cache_disabled": True,
            "raw_runtime_objects_serialized": False,
            "sensitive_input_detected": False,
            "incident_detected": False,
        },
        "privacy gate failed",
    )
    serialized = _canonical_json(report).decode("utf-8")
    _require("@" not in serialized, "feedback contains contact-like data")
    _require("://" not in serialized, "feedback contains a network location")
    _require("\\" not in serialized, "feedback contains a path-like value")


def build_preflight(
    *,
    plan: Mapping[str, Any],
    plan_payload: bytes,
    protocol_payload: bytes,
    schema_payload: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "phase": "closed-alpha-a0",
        "status": "prepared_blocked_before_live",
        "candidate": {
            "name": plan["candidate"]["name"],
            "commit_sha": CANDIDATE_SHA,
            "git_tree_sha1": CANDIDATE_TREE,
            "workflow_run_id": plan["candidate"]["workflow_run_id"],
        },
        "kit": {
            "plan_sha256": _sha256(plan_payload),
            "protocol_sha256": _sha256(protocol_payload),
            "feedback_schema_sha256": _sha256(schema_payload),
        },
        "gates": {
            "authority_boundary_locked": True,
            "budgets_locked": True,
            "candidate_locked": True,
            "feedback_allowlist_locked": True,
            "privacy_contract_locked": True,
            "runtime_blocker_recorded": True,
            "zero_traffic_verified": True,
        },
        "budget": plan["budget"],
        "traffic": plan["traffic"],
        "decision": {
            "preparation_passed": True,
            "runtime_budget_enforcement_ready": False,
            "tester_contact_allowed": False,
            "live_execution_allowed": False,
            "merge_allowed": False,
            "public_release_allowed": False,
            "quality_claim_allowed": False,
            "phase12_allowed": False,
        },
    }


def run() -> dict[str, Any]:
    plan_payload = _read_regular(DEFAULT_PLAN, max_bytes=MAX_JSON_BYTES, label="A0 plan")
    schema_payload = _read_regular(
        DEFAULT_SCHEMA, max_bytes=MAX_JSON_BYTES, label="feedback schema"
    )
    protocol_payload = _read_regular(
        DEFAULT_PROTOCOL, max_bytes=MAX_JSON_BYTES, label="A0 protocol"
    )
    try:
        plan = _object(json.loads(plan_payload), "A0 plan")
        schema = _object(json.loads(schema_payload), "feedback schema")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A0Error("A0 kit contains invalid JSON") from exc
    validate_plan(plan)
    validate_feedback_schema(schema)
    _require(plan["protocol_sha256"] == _sha256(protocol_payload), "protocol hash mismatch")
    _require(
        plan["feedback_schema_sha256"] == _sha256(schema_payload),
        "feedback schema hash mismatch",
    )
    return build_preflight(
        plan=plan,
        plan_payload=plan_payload,
        protocol_payload=protocol_payload,
        schema_payload=schema_payload,
    )


def write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    parent = path.parent
    if not parent.exists():
        try:
            parent.mkdir(mode=0o700, parents=False)
        except OSError as exc:
            raise A0Error("cannot create private output directory") from exc
    try:
        metadata = parent.lstat()
    except OSError as exc:
        raise A0Error("cannot stat private output directory") from exc
    _require(stat.S_ISDIR(metadata.st_mode) and not parent.is_symlink(), "unsafe output directory")
    _require(stat.S_IMODE(metadata.st_mode) & 0o077 == 0, "output directory is not private")
    _require(parent.resolve(strict=True) == parent.absolute(), "output directory uses a symlink")
    if path.exists() or path.is_symlink():
        target_metadata = path.lstat()
        _require(
            stat.S_ISREG(target_metadata.st_mode) and not path.is_symlink(), "unsafe output target"
        )
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor = -1
    temporary_name = ""
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".closed-alpha-a0-", dir=parent)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary = Path(temporary_name)
        _require(stat.S_IMODE(temporary.lstat().st_mode) == 0o600, "temporary file is not private")
        _require(json.loads(temporary.read_bytes()) == value, "serialized preflight changed")
        os.replace(temporary, path)
        directory_descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except (OSError, TypeError, json.JSONDecodeError) as exc:
        raise A0Error("cannot write private preflight") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name:
            with contextlib.suppress(OSError):
                Path(temporary_name).unlink(missing_ok=True)
    _require(stat.S_IMODE(path.lstat().st_mode) == 0o600, "output file is not private")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--output", type=Path)
    mode.add_argument("--validate-feedback", type=Path)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        preflight = run()
        if arguments.validate_feedback is not None:
            feedback = _read_json(arguments.validate_feedback, "feedback report")
            validate_feedback_report(feedback, today=datetime.now(UTC).date())
        elif arguments.output is not None:
            write_private_json(arguments.output, preflight)
    except A0Error as exc:
        raise SystemExit("closed-alpha A0 preflight failed closed") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
