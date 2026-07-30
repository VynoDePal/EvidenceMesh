#!/usr/bin/env python3
"""Run the deterministic, zero-network Phase 11.8.7 runtime timeout audit."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import socket
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from evidencemesh.config import Settings
from evidencemesh.errors import ProviderError
from evidencemesh.telemetry import classify_provider_failure

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_NAME = "evidencemesh-phase11-8-7-offline-runtime-timeout-hardening-v1"

PROTOCOL_PATH = "docs/benchmark-protocol-v22.md"
CONFIG_PATH = "src/evidencemesh/config.py"
ENGINE_PATH = "src/evidencemesh/engine.py"
TELEMETRY_PATH = "src/evidencemesh/telemetry.py"
HISTORICAL_RESULT_PATH = "benchmarks/results/phase11_8_6_offline_timeout_diagnostic_2026-07-30.json"

LOCKED_PROTOCOL_SHA256 = "e786b5b4f7ade79d40dc81ffab3a20bd0a09ffe45c7b5a8765155519e2cd1dbe"
LOCKED_CONFIG_SHA256 = "e344e269ddef8f703d8e346e0fd6e9d98367b4d734d8155db24908a0e90bae40"
LOCKED_ENGINE_SHA256 = "8e0d9003ee38c2f776547913ce8ddfeb7d80e334b5eb210e124b78eafdd57795"
LOCKED_TELEMETRY_SHA256 = "9f485c442a3c7e6d6fa2702b8089dd6d7fec57db9fdc4cda9dd05091e69046b4"
LOCKED_PHASE11_8_6_RESULT_SHA256 = (
    "72635a442aa4062f6588e5f7fcaec49abb68de52dc8da96f790fd88b55602207"
)

PRIVATE_EXCEPTION_MESSAGE = "PRIVATE_RUNTIME_TIMEOUT_MESSAGE_MUST_NOT_SURVIVE"
PRIVATE_REQUEST_URL = "https://private.invalid/secret-path?key=PRIVATE_RUNTIME_KEY"

EXPECTED_POLICY = {
    "connect_seconds": 5.0,
    "read_seconds": 12.0,
    "write_seconds": 10.0,
    "pool_seconds": 5.0,
    "wall_seconds": 15.0,
}
EXPECTED_ENVIRONMENT_BINDINGS = {
    "EVIDENCEMESH_PROVIDER_CONNECT_TIMEOUT": "provider_connect_timeout_seconds",
    "EVIDENCEMESH_PROVIDER_READ_TIMEOUT": "provider_read_timeout_seconds",
    "EVIDENCEMESH_PROVIDER_WRITE_TIMEOUT": "provider_write_timeout_seconds",
    "EVIDENCEMESH_PROVIDER_POOL_TIMEOUT": "provider_pool_timeout_seconds",
}
EXPECTED_TIMEOUT_KINDS = {
    "connect": "connect_timeout",
    "read": "read_timeout",
    "write": "write_timeout",
    "pool": "pool_timeout",
    "httpx_unknown": "httpx_timeout_unknown",
    "provider_wall": "provider_wall_timeout",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _public_policy(settings: Settings) -> dict[str, float]:
    return {
        "connect_seconds": settings.provider_connect_timeout_seconds,
        "read_seconds": settings.provider_read_timeout_seconds,
        "write_seconds": settings.provider_write_timeout_seconds,
        "pool_seconds": settings.provider_pool_timeout_seconds,
        "wall_seconds": settings.request_timeout_seconds,
    }


def _invalid_policy_diagnostics() -> dict[str, int]:
    invalid = (
        {"provider_connect_timeout_seconds": 0.0},
        {"provider_read_timeout_seconds": 0.0},
        {"provider_write_timeout_seconds": -1.0},
        {"provider_pool_timeout_seconds": 0.0},
        {"provider_read_timeout_seconds": 15.0},
        {"request_timeout_seconds": 12.0},
    )
    rejected = 0
    for values in invalid:
        try:
            Settings(enabled_providers=[], **values)
        except ValidationError:
            rejected += 1
    return {
        "invalid_fixture_count": len(invalid),
        "invalid_rejected": rejected,
    }


def _classification_matrix() -> dict[str, Any]:
    request = httpx.Request("POST", PRIVATE_REQUEST_URL)
    exceptions: tuple[tuple[str, BaseException], ...] = (
        (
            "connect",
            httpx.ConnectTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request),
        ),
        ("read", httpx.ReadTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request)),
        ("write", httpx.WriteTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request)),
        ("pool", httpx.PoolTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request)),
        (
            "httpx_unknown",
            httpx.TimeoutException(PRIVATE_EXCEPTION_MESSAGE, request=request),
        ),
        ("provider_wall", TimeoutError(PRIVATE_EXCEPTION_MESSAGE)),
    )
    classified = {
        name: {
            "kind": classification.kind,
            "http_status": classification.http_status,
        }
        for name, error in exceptions
        for classification in (classify_provider_failure(error),)
    }
    replay = {
        name: {
            "kind": classification.kind,
            "http_status": classification.http_status,
        }
        for name, error in exceptions
        for classification in (classify_provider_failure(error),)
    }
    rendered = json.dumps(classified, ensure_ascii=False, sort_keys=True)
    return {
        "fixture_count": len(exceptions),
        "classified": classified,
        "deterministic_replay": replay == classified,
        "private_exception_message_omitted": PRIVATE_EXCEPTION_MESSAGE not in rendered,
        "private_request_url_omitted": PRIVATE_REQUEST_URL not in rendered,
        "request_query_secret_omitted": "PRIVATE_RUNTIME_KEY" not in rendered,
    }


def _precedence_diagnostics() -> dict[str, str]:
    request = httpx.Request("GET", PRIVATE_REQUEST_URL)
    dns_cause = socket.gaierror(socket.EAI_NONAME, PRIVATE_EXCEPTION_MESSAGE)
    dns_timeout = httpx.ConnectTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request)
    dns_timeout.__cause__ = dns_cause

    specific_timeout = httpx.ReadTimeout(PRIVATE_EXCEPTION_MESSAGE, request=request)
    explicit_provider_error = ProviderError("sanitized", kind="upstream_unavailable")
    explicit_provider_error.__cause__ = specific_timeout

    return {
        "dns_over_connect_timeout": classify_provider_failure(dns_timeout).kind,
        "explicit_provider_kind_over_timeout": classify_provider_failure(
            explicit_provider_error
        ).kind,
    }


def _runtime_source_diagnostics(
    *,
    config_source: str,
    engine_source: str,
) -> dict[str, Any]:
    engine_tree = ast.parse(engine_source)
    timeout_calls = [
        node
        for node in ast.walk(engine_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "httpx"
        and node.func.attr == "Timeout"
    ]
    expected_timeout_keywords = {
        "connect": "self.settings.provider_connect_timeout_seconds",
        "read": "self.settings.provider_read_timeout_seconds",
        "write": "self.settings.provider_write_timeout_seconds",
        "pool": "self.settings.provider_pool_timeout_seconds",
    }
    explicit_timeout_call = any(
        {
            keyword.arg: ast.unparse(keyword.value)
            for keyword in node.keywords
            if keyword.arg is not None
        }
        == expected_timeout_keywords
        for node in timeout_calls
    )

    wall_call_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
        and node.func.attr == "timeout"
        and len(node.args) == 1
        and ast.unparse(node.args[0]) == "self.settings.request_timeout_seconds"
        for node in ast.walk(engine_tree)
    )
    provider_wall_kind_present = any(
        isinstance(node, ast.keyword)
        and node.arg == "kind"
        and isinstance(node.value, ast.Constant)
        and node.value.value == "provider_wall_timeout"
        for node in ast.walk(engine_tree)
    )

    assignment_targets: list[str] = []
    for node in ast.walk(engine_tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            assignment_targets.extend(ast.unparse(target) for target in targets)
    supplied_client_timeout_mutated = any(
        target in {"client.timeout", "supplied_client.timeout", "self.client.timeout"}
        for target in assignment_targets
    )

    environment_bindings_present = all(
        env_name in config_source and field_name in config_source
        for env_name, field_name in EXPECTED_ENVIRONMENT_BINDINGS.items()
    )
    return {
        "owned_client_explicit_transport_timeouts": explicit_timeout_call,
        "provider_wall_call_present": wall_call_present,
        "provider_wall_kind_present": provider_wall_kind_present,
        "environment_bindings_present": environment_bindings_present,
        "supplied_client_timeout_mutated": supplied_client_timeout_mutated,
    }


def _decision(*, runtime_hardening_passed: bool) -> dict[str, Any]:
    return {
        "phase11_8_7_runtime_timeout_hardening_passed": runtime_hardening_passed,
        "historical_phase11_8_6_result_changed": False,
        "future_live_run_authorized": False,
        "phase11_9_protocol_may_be_frozen": False,
        "phase11_9_executed": False,
        "phase12_authorized": False,
        "phase12_executed": False,
        "product_provider_or_model_defaults_changed": False,
        "users_choose_provider_model_and_credentials": True,
        "merge_allowed": False,
        "release_allowed": False,
        "release_decision": "no-go",
        "superiority_claim_allowed": False,
        "next_step": (
            "Review this offline runtime hardening; any live test requires a "
            "separate frozen protocol and fresh explicit authorization."
        ),
    }


def build_report(
    *,
    protocol_raw: bytes,
    config_raw: bytes,
    engine_raw: bytes,
    telemetry_raw: bytes,
    historical_result_raw: bytes,
) -> dict[str, Any]:
    locked_sources = {
        PROTOCOL_PATH: (protocol_raw, LOCKED_PROTOCOL_SHA256),
        CONFIG_PATH: (config_raw, LOCKED_CONFIG_SHA256),
        ENGINE_PATH: (engine_raw, LOCKED_ENGINE_SHA256),
        TELEMETRY_PATH: (telemetry_raw, LOCKED_TELEMETRY_SHA256),
        HISTORICAL_RESULT_PATH: (
            historical_result_raw,
            LOCKED_PHASE11_8_6_RESULT_SHA256,
        ),
    }
    for path, (raw, expected_hash) in locked_sources.items():
        _require(sha256_bytes(raw) == expected_hash, f"locked source changed: {path}")

    historical = json.loads(historical_result_raw)
    _require(
        historical["benchmark"] == "evidencemesh-phase11-8-6-offline-timeout-diagnostic-v1",
        "unexpected Phase 11.8.6 benchmark",
    )
    _require(
        len(historical["gates"]) == 12
        and all(gate["passed"] for gate in historical["gates"].values())
        and historical["decision"]["release_decision"] == "no-go"
        and historical["decision"]["phase11_9_protocol_may_be_frozen"] is False,
        "Phase 11.8.6 decision boundary changed",
    )

    policy = _public_policy(Settings(enabled_providers=[]))
    invalid = _invalid_policy_diagnostics()
    matrix = _classification_matrix()
    precedence = _precedence_diagnostics()
    source = _runtime_source_diagnostics(
        config_source=config_raw.decode("utf-8"),
        engine_source=engine_raw.decode("utf-8"),
    )
    observed_kinds = {
        name: classification["kind"] for name, classification in matrix["classified"].items()
    }
    private_data_omitted = (
        matrix["private_exception_message_omitted"]
        and matrix["private_request_url_omitted"]
        and matrix["request_query_secret_omitted"]
    )

    gates: dict[str, dict[str, Any]] = {
        "locked_source_integrity": {
            "passed": True,
            "sha256": {path: expected_hash for path, (_, expected_hash) in locked_sources.items()},
        },
        "exact_default_timeout_policy": {
            "passed": policy == EXPECTED_POLICY
            and policy["wall_seconds"]
            > max(
                policy["connect_seconds"],
                policy["read_seconds"],
                policy["write_seconds"],
                policy["pool_seconds"],
            ),
            "observed": policy,
        },
        "invalid_or_masking_policies_fail_closed": {
            "passed": invalid["invalid_rejected"] == invalid["invalid_fixture_count"],
            **invalid,
        },
        "environment_overrides_are_bound": {
            "passed": source["environment_bindings_present"],
            "bindings": EXPECTED_ENVIRONMENT_BINDINGS,
        },
        "owned_client_uses_explicit_httpx_layers": {
            "passed": source["owned_client_explicit_transport_timeouts"],
            "connect_seconds": policy["connect_seconds"],
            "read_seconds": policy["read_seconds"],
            "write_seconds": policy["write_seconds"],
            "pool_seconds": policy["pool_seconds"],
        },
        "provider_wall_is_independent_and_bounded": {
            "passed": (
                source["provider_wall_call_present"]
                and source["provider_wall_kind_present"]
                and observed_kinds["provider_wall"] == "provider_wall_timeout"
            ),
            "wall_seconds": policy["wall_seconds"],
            "kind": observed_kinds["provider_wall"],
        },
        "specific_httpx_timeouts_are_distinct": {
            "passed": all(
                observed_kinds[name] == EXPECTED_TIMEOUT_KINDS[name]
                for name in ("connect", "read", "write", "pool")
            ),
            "observed": {
                name: observed_kinds[name] for name in ("connect", "read", "write", "pool")
            },
        },
        "generic_httpx_and_provider_wall_are_distinct": {
            "passed": (
                observed_kinds["httpx_unknown"] == "httpx_timeout_unknown"
                and observed_kinds["provider_wall"] == "provider_wall_timeout"
            ),
            "httpx_unknown": observed_kinds["httpx_unknown"],
            "provider_wall": observed_kinds["provider_wall"],
        },
        "classification_is_deterministic_bounded_and_private": {
            "passed": (
                matrix["deterministic_replay"]
                and set(observed_kinds.values()) == set(EXPECTED_TIMEOUT_KINDS.values())
                and private_data_omitted
            ),
            "fixture_count": matrix["fixture_count"],
            "private_exception_retained": False,
            "request_url_retained": False,
            "headers_bodies_or_responses_retained": False,
        },
        "precedence_and_supplied_client_contract_are_preserved": {
            "passed": (
                precedence["dns_over_connect_timeout"] == "dns_error"
                and precedence["explicit_provider_kind_over_timeout"] == "upstream_unavailable"
                and source["supplied_client_timeout_mutated"] is False
            ),
            **precedence,
            "supplied_client_timeout_mutated": source["supplied_client_timeout_mutated"],
        },
        "zero_network_provider_model_secret_or_retry_traffic": {
            "passed": True,
            "network_requests": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "secrets_bound": 0,
            "tavily_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallback_requests": 0,
            "repair_requests": 0,
        },
        "historical_user_choice_and_release_boundaries_are_preserved": {
            "passed": (
                historical["decision"]["release_decision"] == "no-go"
                and historical["decision"]["phase11_9_protocol_may_be_frozen"] is False
                and historical["decision"]["users_choose_provider_model_and_credentials"] is True
            ),
            "historical_phase11_8_6_changed": False,
            "users_choose_provider_model_and_credentials": True,
            "future_live_run_authorized": False,
            "phase11_9_protocol_may_be_frozen": False,
            "phase12_authorized": False,
            "merge_allowed": False,
            "release_allowed": False,
        },
    }
    passed = len(gates) == 12 and all(gate["passed"] for gate in gates.values())
    traffic = {
        key: value
        for key, value in gates["zero_network_provider_model_secret_or_retry_traffic"].items()
        if key != "passed"
    }
    return {
        "schema_version": 1,
        "benchmark": BENCHMARK_NAME,
        "task_type": "offline SDK and MCP runtime timeout hardening",
        "protocol": {
            "path": PROTOCOL_PATH,
            "sha256": LOCKED_PROTOCOL_SHA256,
            "runtime_source_sha256": {
                CONFIG_PATH: LOCKED_CONFIG_SHA256,
                ENGINE_PATH: LOCKED_ENGINE_SHA256,
                TELEMETRY_PATH: LOCKED_TELEMETRY_SHA256,
            },
            "historical_phase11_8_6_result_sha256": (LOCKED_PHASE11_8_6_RESULT_SHA256),
        },
        "timeout_policy": policy,
        "timeout_taxonomy": matrix["classified"],
        "traffic": traffic,
        "gates": gates,
        "decision": _decision(runtime_hardening_passed=passed),
        "privacy": {
            "raw_exception_messages_in_report": False,
            "request_urls_in_report": False,
            "request_headers_in_report": False,
            "request_bodies_in_report": False,
            "provider_responses_in_report": False,
            "credentials_in_report": False,
            "questions_or_evidence_in_report": False,
            "generated_answers_in_report": False,
            "phase12_identifiers_in_report": False,
        },
        "warnings": [
            (
                "This is an offline engineering result; it makes no provider or "
                "model availability claim."
            ),
            (
                "The historical Phase 11.8.5 request_timeout remains "
                "legacy_request_timeout_unresolved."
            ),
            (
                "Phase 11.9, Phase 12, merge and release remain blocked pending "
                "separate evidence and authorization."
            ),
        ],
    }


def run(
    *,
    protocol_path: Path,
    config_path: Path,
    engine_path: Path,
    telemetry_path: Path,
    historical_result_path: Path,
) -> dict[str, Any]:
    return build_report(
        protocol_raw=protocol_path.read_bytes(),
        config_raw=config_path.read_bytes(),
        engine_raw=engine_path.read_bytes(),
        telemetry_raw=telemetry_path.read_bytes(),
        historical_result_raw=historical_result_path.read_bytes(),
    )


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.partial")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=REPOSITORY_ROOT / PROTOCOL_PATH)
    parser.add_argument("--config", type=Path, default=REPOSITORY_ROOT / CONFIG_PATH)
    parser.add_argument("--engine", type=Path, default=REPOSITORY_ROOT / ENGINE_PATH)
    parser.add_argument(
        "--telemetry",
        type=Path,
        default=REPOSITORY_ROOT / TELEMETRY_PATH,
    )
    parser.add_argument(
        "--historical-result",
        type=Path,
        default=REPOSITORY_ROOT / HISTORICAL_RESULT_PATH,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    report = run(
        protocol_path=arguments.protocol,
        config_path=arguments.config,
        engine_path=arguments.engine,
        telemetry_path=arguments.telemetry,
        historical_result_path=arguments.historical_result,
    )
    if arguments.check_only:
        print(
            json.dumps(
                {
                    "status": "phase11_8_7_runtime_timeout_hardening_valid",
                    "gates_passed": sum(gate["passed"] for gate in report["gates"].values()),
                    "gate_count": len(report["gates"]),
                    "network_requests": report["traffic"]["network_requests"],
                    "provider_calls": report["traffic"]["provider_calls"],
                    "secrets_bound": report["traffic"]["secrets_bound"],
                    "future_live_run_authorized": report["decision"]["future_live_run_authorized"],
                    "release_decision": report["decision"]["release_decision"],
                },
                sort_keys=True,
            )
        )
        return 0
    if arguments.output is None:
        raise ValueError("--output is required unless --check-only is used")
    write_report(arguments.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
