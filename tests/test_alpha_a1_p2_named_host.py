from __future__ import annotations

import copy
import hashlib
import json
import re
import stat
from pathlib import Path

import pytest

from scripts import verify_alpha_a1_p2_named_host as gate

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "alpha" / "alpha_a1_p2_named_host_policy_v1.json"
PROTOCOL = ROOT / "docs" / "alpha-a1-p2-named-host-interoperability-gate-v1.md"
MANIFEST = ROOT / "alpha" / "a1-p2-inspector" / "package.json"
LOCK = ROOT / "alpha" / "a1-p2-inspector" / "package-lock.json"
DESCRIPTOR = ROOT / "examples" / "evidencemesh.mcp.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

P1_COMMIT = "b967114a177eec00a7ff5f03bcf1169e04b2faac"
P1_TREE = "7477a10c89ae158a5f5ca197799b50088335d4d8"
P1_RUN_ID = 30721297774
INSPECTOR_INTEGRITY = (
    "sha512-uEoeEG7/+ZbrvccPF3EsgbfjcyJ3bWVJXT4pcZtpmDUhA0zdK4T4Tuj2oUphi2Huwl66"
    "LqVdo3Mx2PkS2SUHXA=="
)
INSPECTOR_CLI_SHA256 = "bce0edfa3a72dca4d3b1f81771172ded2e1294128539c353a51e11f05871a4b6"
INSPECTOR_LAUNCHER_SHA256 = "c114e7c78afcfa01523232ae9639c3e49919952db6b8901ec7c0f49267ce0c23"
INSPECTOR_PACKAGE_JSON_SHA256 = "d6be3029cd7b300575c4d54950dbcf372813055d9e14a555f5226a11ea6862d4"
MANIFEST_SHA256 = "ec21ceac22f4897d454ffbf1cce610cafaf68fcfd700340300151fea68642071"
LOCK_SHA256 = "b8c2d8cd2a8f16fcfd28dc7aedc3aae8e5baa6bf5bac508ee7b22bbd4343a33e"
EXPECTED_REQUEST_SEQUENCE = [
    "initialize",
    "logging/setLevel",
    "tools/list",
    "tools/call health",
]
EXPECTED_P2_SCOPE = {
    ".github/workflows/ci.yml",
    "README.md",
    "alpha/a1-p2-inspector/package-lock.json",
    "alpha/a1-p2-inspector/package.json",
    "alpha/alpha_a1_p2_named_host_policy_v1.json",
    "docs/alpha-a1-p2-named-host-interoperability-gate-v1.md",
    "scripts/verify_alpha_a1_p2_named_host.py",
    "tests/test_alpha_a1_p2_named_host.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _health() -> dict[str, object]:
    return {
        "configuration_warnings": [],
        "deployment_profile": "community",
        "providers": [{"name": "wikipedia"}],
        "safety": {"dns_pinning": True, "private_networks_allowed": False},
        "status": "ready",
        "version": "0.1.0",
    }


def _inspector_envelope() -> dict[str, object]:
    health = _health()
    return {
        "result": {
            "content": [{"type": "text", "text": json.dumps(health, sort_keys=True)}],
            "isError": False,
            "structuredContent": health,
        }
    }


def _write_jsonl(path: Path, events: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )


def _valid_request_events() -> list[dict[str, object]]:
    return [
        {"event": "server_start", "pid": 321},
        {"event": "request", "id": 1, "method": "initialize"},
        {"event": "notification", "method": "notifications/initialized"},
        {"event": "request", "id": 2, "method": "logging/setLevel"},
        {"event": "request", "id": 3, "method": "tools/list"},
        {"event": "request", "id": 4, "method": "tools/call"},
        {"event": "server_exit", "request_sequence_complete": True},
    ]


def test_policy_freezes_named_client_claim_identity_and_authority() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["schema_version"] == "evidencemesh.alpha-a1-p2-named-host-policy.v1"
    assert policy["prerequisite"] == {
        "accepted_workflow_run_id": P1_RUN_ID,
        "branch": "agent/evidencemesh-v0.1",
        "commit_sha": P1_COMMIT,
        "gate": "Alpha A1-P1 MCP first-run",
        "historical_step_rerun_required": False,
        "tree_sha": P1_TREE,
    }
    assert policy["named_client"] == {
        "classification": "official MCP developer client",
        "cli_bundle_sha256": INSPECTOR_CLI_SHA256,
        "gui_mode_executed": False,
        "launcher_sha256": INSPECTOR_LAUNCHER_SHA256,
        "name": "MCP Inspector CLI",
        "npm_integrity": INSPECTOR_INTEGRITY,
        "package": "@modelcontextprotocol/inspector",
        "package_json_sha256": INSPECTOR_PACKAGE_JSON_SHA256,
        "version": "2.0.0",
    }
    assert policy["request_sequence"] == EXPECTED_REQUEST_SEQUENCE
    assert policy["decision"]["named_ai_host_validated"] is False
    assert policy["limitations"]["gui_host_validated"] is False
    assert policy["limitations"]["protocol_version_reobserved_by_p2"] is False
    assert policy["limitations"]["complete_six_tool_inventory_revalidated_by_p2"] is False
    assert not any(policy["authority"].values())


def test_policy_freezes_one_shot_budgets_and_guard_limitations() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["budgets"] == {
        "dependency_install_attempts": 1,
        "external_document_requests": 0,
        "host_invocations": 1,
        "host_timeout_seconds": 30,
        "logical_mcp_requests_expected": 4,
        "logical_mcp_requests_maximum": 12,
        "maximum_total_seconds": 90,
        "mcp_server_launch_attempts": 1,
        "mcp_sessions": 1,
        "mcp_tool_calls": 1,
        "model_calls": 0,
        "provider_calls": 0,
        "retries": 0,
        "runtime_network_requests": 0,
        "search_calls": 0,
    }
    assert policy["runtime_guard"] == {
        "addressless_inet_socket_creation_is_network_request": False,
        "ambiguous_network_syscalls_allowed": False,
        "destination_or_traffic_requires_explicit_local_sockaddr": True,
        "local_unix_and_netlink_syscalls_allowed": True,
        "node_api_blocking": True,
        "operating_system_network_namespace_enforced": False,
        "packet_xdp_and_raw_inet_sockets_allowed": False,
        "passive_ipv6_loopback_bind_is_network_request": False,
        "passive_ipv6_loopback_bind_probe_maximum": 1,
        "python_api_blocking": True,
        "setsockopt_on_proven_local_fd_allowed": True,
        "setsockopt_on_unproven_or_inet_fd_allowed": False,
        "strace_fd_family_tracking": True,
        "strace_family_classification": "syscall_and_sockaddr",
        "strace_external_socket_audit": True,
    }
    assert policy["publication"] == {
        "artifacts": 0,
        "distributions": 0,
        "releases": 0,
        "tags": 0,
    }


def test_npm_manifest_and_lock_are_exact_private_registry_only_inputs() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert _sha256(MANIFEST) == MANIFEST_SHA256 == policy["supply_chain"]["manifest_sha256"]
    assert _sha256(LOCK) == LOCK_SHA256 == policy["supply_chain"]["lock_sha256"]
    assert manifest["private"] is True
    assert manifest["engines"] == {"node": "22.20.0", "npm": "10.9.3"}
    assert manifest["dependencies"] == {"@modelcontextprotocol/inspector": "2.0.0"}
    assert manifest["overrides"] == {"ink-select-input": "6.2.0"}
    assert "scripts" not in manifest
    assert lock["lockfileVersion"] == 3
    assert len(lock["packages"]) == 241
    assert policy["supply_chain"]["lock_package_entries"] == len(lock["packages"])

    inspector = lock["packages"]["node_modules/@modelcontextprotocol/inspector"]
    assert inspector["version"] == "2.0.0"
    assert inspector["integrity"] == INSPECTOR_INTEGRITY
    assert inspector["resolved"] == (
        "https://registry.npmjs.org/@modelcontextprotocol/inspector/-/inspector-2.0.0.tgz"
    )
    for name, package in lock["packages"].items():
        if name == "" or "resolved" not in package:
            continue
        assert package["resolved"].startswith("https://registry.npmjs.org/")
        assert package.get("integrity", "").startswith("sha512-")


def test_verifier_pins_exact_p1_checkpoint_and_eight_file_scope() -> None:
    assert gate.PREREQUISITE_COMMIT == P1_COMMIT
    assert gate.PREREQUISITE_TREE == P1_TREE
    assert gate.EXPECTED_CHANGED_PATHS == EXPECTED_P2_SCOPE
    assert gate.EXPECTED_INSPECTOR_VERSION == "2.0.0"
    assert gate.EXPECTED_INSPECTOR_INTEGRITY == INSPECTOR_INTEGRITY
    assert gate.EXPECTED_INSPECTOR_FILES == {
        "package.json": INSPECTOR_PACKAGE_JSON_SHA256,
        "clients/launcher/build/index.js": INSPECTOR_LAUNCHER_SHA256,
        "clients/launcher/build/parse-launcher-argv.js": (
            "a417cf4d755b2c5ed3d08fa2ce0b7488fbfcbeb856794437990dd55c64139b73"
        ),
        "clients/cli/build/index.js": INSPECTOR_CLI_SHA256,
    }
    assert gate.EXPECTED_INSPECTOR_BIN == {"mcp-inspector": "./clients/launcher/build/index.js"}
    assert gate.EXPECTED_REQUEST_METHODS == [
        "initialize",
        "logging/setLevel",
        "tools/list",
        "tools/call",
    ]
    assert gate.LOGICAL_MCP_REQUESTS_MAXIMUM == 12
    assert gate.HOST_TIMEOUT_SECONDS == 30
    assert gate.MAXIMUM_ADDITIONAL_SECONDS == 90


def test_protocol_and_readme_state_the_reduced_claim_and_stop_boundary() -> None:
    protocol = PROTOCOL.read_text(encoding="utf-8")
    normalized_protocol = " ".join(protocol.split())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stdio = readme.split("### STDIO", maxsplit=1)[1].split("### Streamable HTTP", maxsplit=1)[0]
    normalized_stdio = " ".join(stdio.split())

    assert "MCP Inspector is a developer testing client, not an AI application host" in protocol
    assert "one named third-party MCP client path" in normalized_protocol
    assert "four expected and at most twelve logical MCP requests" in normalized_protocol
    assert (
        "stops on any second install, host invocation, session, server or tool call"
        in normalized_protocol
    )
    assert "a fifth observed MCP request" in normalized_protocol
    assert "not an operating- system network namespace" in normalized_protocol
    assert "uploads no artifact" in normalized_protocol
    assert "PR #1 remains draft" in normalized_protocol
    assert (
        "MCP Inspector is a developer testing client, not an AI application host"
        in normalized_stdio
    )
    assert "does not establish compatibility with Claude Desktop, Cursor, VS Code, ChatGPT" in (
        normalized_stdio
    )
    assert "one Ubuntu STDIO session" in normalized_stdio


def test_workflow_sha_gates_historical_p1_and_runs_one_locked_p2_path() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow.split("  alpha-a1-p0-installability:", maxsplit=1)[1].split(
        "\n  container:", maxsplit=1
    )[0]
    p1 = job.split("- name: Verify official MCP SDK first-run journey", maxsplit=1)[1].split(
        "- name:", maxsplit=1
    )[0]
    p2 = job.split("- name: Verify MCP Inspector CLI interoperability", maxsplit=1)[1]

    assert f"github.event.pull_request.head.sha == '{P1_COMMIT}'" in p1
    assert job.count("verify_alpha_a1_p1_mcp_first_run.py") == 1
    assert job.count("verify_alpha_a1_p2_named_host.py") == 1
    assert job.index("verify_alpha_a1_p0_installability.py") < job.index(
        "verify_alpha_a1_p2_named_host.py"
    )
    assert re.search(r"uses: actions/setup-node@[0-9a-f]{40}", job)
    assert 'node-version: "22.20.0"' in job
    assert 'NPM_CONFIG_FETCH_RETRIES: "0"' in p2
    assert 'NPM_CONFIG_UPDATE_NOTIFIER: "false"' in p2
    assert "NPM_CONFIG_CACHE:" in p2
    assert "A1_EXPECTED_HEAD: ${{ github.event.pull_request.head.sha }}" in p2
    assert "npx" not in p2
    assert "upload-artifact" not in job
    assert "secrets." not in job
    assert "git tag" not in job
    assert "gh release" not in job


def test_verifier_invokes_only_the_exact_inspector_health_operation() -> None:
    source = (ROOT / "scripts" / "verify_alpha_a1_p2_named_host.py").read_text(encoding="utf-8")

    for token in (
        '"--cli"',
        '"--config"',
        '"--server"',
        '"evidencemesh"',
        '"--method"',
        '"tools/call"',
        '"--tool-name"',
        '"health"',
        '"--tool-args-json"',
        '"{}"',
        '"--format"',
        '"json"',
        '"--connect-timeout"',
        '"10000"',
    ):
        assert token in source
    assert "npx" not in source
    assert '"--catalog"' not in source
    assert '"--server-url"' not in source
    assert '"--app-info"' not in source
    assert source.count('"ci",') == 1
    assert '"--ignore-scripts"' in source
    assert '"--no-audit"' in source
    assert '"--no-fund"' in source
    assert '"NPM_CONFIG_FETCH_RETRIES": "0"' in source
    assert "10.9.3" in source
    assert "start_new_session=True" in source
    assert "killpg" in source
    assert "strace" in source
    assert "NODE_OPTIONS" in source
    assert "sitecustomize.py" in source


def test_full_sha_validation_rejects_short_or_non_hex_values() -> None:
    gate._validate_full_sha("a" * 40, "Triggering PR head")
    gate._validate_full_sha("A" * 40, "Triggering PR head")

    for invalid in ("short", "g" * 40, "a" * 39, "a" * 41):
        with pytest.raises(gate.GateError, match="full commit SHA"):
            gate._validate_full_sha(invalid, "Triggering PR head")


def test_json_stdout_accepts_only_one_json_object_line() -> None:
    assert gate._json_stdout('{"ok": true}\n', "Inspector") == {"ok": True}
    assert gate._json_stdout('\n {"ok": true} \n', "Inspector") == {"ok": True}

    for invalid in (
        "",
        '{"ok": true}\n{"extra": true}\n',
        'banner\n{"ok": true}\n',
        "[]\n",
        "not-json\n",
    ):
        with pytest.raises(gate.GateError):
            gate._json_stdout(invalid, "Inspector")


def test_inspector_envelope_accepts_only_one_result_object() -> None:
    envelope = _inspector_envelope()
    result = envelope["result"]
    assert isinstance(result, dict)
    assert gate._validate_inspector_envelope(envelope) == result

    for invalid in (
        {},
        {"result": None},
        {"result": []},
        {"result": result, "extra": True},
        {"content": result},
    ):
        with pytest.raises(gate.GateError):
            gate._validate_inspector_envelope(invalid)


def test_health_validation_accepts_only_the_frozen_success_shape() -> None:
    result = _inspector_envelope()["result"]
    assert isinstance(result, dict)

    assert gate._validate_health(result) == {
        "configuration_warnings": [],
        "deployment_profile": "community",
        "dns_pinning": True,
        "private_networks_allowed": False,
        "providers": ["wikipedia"],
        "status": "ready",
        "version": "0.1.0",
    }


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("isError",), True, "MCP error"),
        (("structuredContent", "status"), "degraded", "not ready"),
        (("structuredContent", "version"), "0.1.1", "version drifted"),
        (("structuredContent", "deployment_profile"), "enterprise", "profile drifted"),
        (("structuredContent", "providers"), [], "providers drifted"),
        (
            ("structuredContent", "providers"),
            [{"name": "private"}],
            "provider isolation drifted",
        ),
        (("structuredContent", "configuration_warnings"), ["warning"], "warnings"),
        (
            ("structuredContent", "safety", "private_networks_allowed"),
            True,
            "Private networks",
        ),
        (("structuredContent", "safety", "dns_pinning"), False, "DNS pinning"),
    ],
)
def test_health_validation_rejects_semantic_drift(
    path: tuple[str, ...], replacement: object, message: str
) -> None:
    result = _inspector_envelope()["result"]
    assert isinstance(result, dict)
    mutated = copy.deepcopy(result)
    target = mutated
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = replacement
    structured = mutated.get("structuredContent")
    if isinstance(structured, dict) and path[0] == "structuredContent":
        content = mutated["content"]
        assert isinstance(content, list)
        item = content[0]
        assert isinstance(item, dict)
        item["text"] = json.dumps(structured, sort_keys=True)

    with pytest.raises(gate.GateError, match=message):
        gate._validate_health(mutated)


def test_health_validation_rejects_text_structured_mismatch() -> None:
    result = _inspector_envelope()["result"]
    assert isinstance(result, dict)
    content = result["content"]
    assert isinstance(content, list)
    item = content[0]
    assert isinstance(item, dict)
    item["text"] = json.dumps({"status": "ready"})

    with pytest.raises(gate.GateError, match="differ"):
        gate._validate_health(result)


def test_request_trace_accepts_one_exact_session(tmp_path: Path) -> None:
    trace = tmp_path / "request-trace.jsonl"
    _write_jsonl(trace, _valid_request_events())

    assert gate._validate_request_trace(trace) == {
        "logical_requests": 4,
        "methods": ["initialize", "logging/setLevel", "tools/list", "tools/call"],
        "notifications": ["notifications/initialized"],
        "server_pid": 321,
        "server_launches": 1,
        "sessions": 1,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("fifth_request", "sequence"),
        ("wrong_method", "sequence"),
        ("denied", "denied"),
        ("second_launch", "launch count"),
        ("missing_exit", "exit was not observed"),
        ("incomplete_exit", "incomplete at exit"),
        ("wrong_notification", "notification sequence"),
    ],
)
def test_request_trace_rejects_budget_or_sequence_drift(
    tmp_path: Path, mutation: str, message: str
) -> None:
    events = _valid_request_events()
    if mutation == "fifth_request":
        events.insert(-1, {"event": "request", "id": 5, "method": "tools/list"})
    elif mutation == "wrong_method":
        events[4]["method"] = "resources/list"
    elif mutation == "denied":
        events.insert(-1, {"event": "denied", "reason": "unexpected"})
    elif mutation == "second_launch":
        events.insert(1, {"event": "server_start", "pid": 654})
    elif mutation == "missing_exit":
        events.pop()
    elif mutation == "incomplete_exit":
        events[-1]["request_sequence_complete"] = False
    elif mutation == "wrong_notification":
        events[2]["method"] = "notifications/tools/list_changed"
    else:  # pragma: no cover - parametrization is closed above.
        raise AssertionError(mutation)
    trace = tmp_path / f"{mutation}.jsonl"
    _write_jsonl(trace, events)

    with pytest.raises(gate.GateError, match=message):
        gate._validate_request_trace(trace)


def test_strace_audit_accepts_only_addressless_inet_socket_creation(tmp_path: Path) -> None:
    node = (tmp_path / "node").resolve()
    trace = tmp_path / "inspector.strace.log"
    trace.write_text(
        f'101 execve("{node}", ["{node}", "AF_INET"], 0x0) = 0\n'
        "101 socket(AF_INET, SOCK_DGRAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
        "101 socket(AF_INET6, SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC, IPPROTO_TCP) "
        "= -1 EAFNOSUPPORT (Address family not supported by protocol)\n"
        "101 socket(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0) = 4\n"
        "101 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    assert gate._validate_strace(trace, {node}) == {
        "addressless_inet_socket_creations": 2,
        "execve_count": 1,
        "explicit_local_socket_syscalls": 1,
        "forbidden_network_syscalls": 0,
        "network_syscalls_observed": 3,
        "passive_ipv6_loopback_bind_probes": 0,
        "process_audit_lines": 5,
    }


def test_strace_audit_allows_explicit_unix_and_netlink_control_plane(tmp_path: Path) -> None:
    node = (tmp_path / "node").resolve()
    trace = tmp_path / "inspector.strace.log"
    trace.write_text(
        f'101 execve("{node}", ["{node}"], 0x0) = 0\n'
        "101 socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, [3, 4]) = 0\n"
        "101 setsockopt(3, SOL_SOCKET, SO_RCVBUF, [212992], 4) = 0\n"
        "101 socket(AF_NETLINK, SOCK_RAW|SOCK_CLOEXEC, NETLINK_ROUTE) = 5\n"
        "101 bind(5, {sa_family=AF_NETLINK, nl_pid=0}, 12) = 0\n"
        "101 sendto(5, [{rtm_family=AF_INET}], 20, 0, NULL, 0) = 20\n"
        "101 recvfrom(5, [{ifa_family=AF_INET6}], 48, 0, NULL, NULL) = 48\n",
        encoding="utf-8",
    )
    assert gate._validate_strace(trace, {node}) == {
        "addressless_inet_socket_creations": 0,
        "execve_count": 1,
        "explicit_local_socket_syscalls": 6,
        "forbidden_network_syscalls": 0,
        "network_syscalls_observed": 6,
        "passive_ipv6_loopback_bind_probes": 0,
        "process_audit_lines": 7,
    }


def test_strace_audit_allows_one_urllib3_ipv6_loopback_probe(tmp_path: Path) -> None:
    node = (tmp_path / "node").resolve()
    trace = tmp_path / "inspector.strace.log"
    trace.write_text(
        f'101 execve("{node}", ["{node}"], 0x0) = 0\n'
        "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
        "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
        'sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::1", &sin6_addr), '
        "sin6_scope_id=0}, 28) = 0\n",
        encoding="utf-8",
    )
    assert gate._validate_strace(trace, {node}) == {
        "addressless_inet_socket_creations": 1,
        "execve_count": 1,
        "explicit_local_socket_syscalls": 0,
        "forbidden_network_syscalls": 0,
        "network_syscalls_observed": 2,
        "passive_ipv6_loopback_bind_probes": 1,
        "process_audit_lines": 3,
    }


@pytest.mark.parametrize(
    "network_block",
    [
        (
            "101 socket(AF_INET6, SOCK_DGRAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
            'inet_pton(AF_INET6, "::1", &sin6_addr)}, 28) = 0'
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 setsockopt(3, SOL_IPV6, IPV6_V6ONLY, [1], 4) = 0"
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(443), "
            'inet_pton(AF_INET6, "::1", &sin6_addr)}, 28) = 0'
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
            "sin6_flowinfo=htonl(1), "
            'inet_pton(AF_INET6, "::1", &sin6_addr)}, 28) = 0'
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
            'inet_pton(AF_INET6, "::1", &sin6_addr)}, 28) = 0'
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
            "sin6_flowinfo=htonl(0), "
            'inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0, '
            "unknown=1}, 28) = 0"
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
            'inet_pton(AF_INET6, "2001:db8::1", &sin6_addr)}, 28) = 0'
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(4, {sa_family=AF_INET6, sin6_port=htons(0), "
            'inet_pton(AF_INET6, "::1", &sin6_addr)}, 28) = 0'
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
            'inet_pton(AF_INET6, "::1", &sin6_addr)}, 28) = 0\n'
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
            'inet_pton(AF_INET6, "::1", &sin6_addr)}, 28) = 0'
        ),
        (
            "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
            "101 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
            'inet_pton(AF_INET6, "::1", &sin6_addr)}, 28) = 0\n'
            "101 listen(3, 1) = 0"
        ),
    ],
)
def test_strace_audit_rejects_widened_ipv6_probe(tmp_path: Path, network_block: str) -> None:
    node = (tmp_path / "node").resolve()
    trace = tmp_path / "inspector.strace.log"
    trace.write_text(
        f'101 execve("{node}", ["{node}"], 0x0) = 0\n{network_block}\n',
        encoding="utf-8",
    )
    with pytest.raises(gate.GateError, match="strace"):
        gate._validate_strace(trace, {node})


def test_strace_audit_rejects_cross_pid_fd_identity_collision(tmp_path: Path) -> None:
    node = (tmp_path / "node").resolve()
    trace = tmp_path / "inspector.strace.log"
    trace.write_text(
        f'101 execve("{node}", ["{node}"], 0x0) = 0\n'
        "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\n"
        "102 socket(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0) = 3\n"
        "102 bind(3, {sa_family=AF_INET6, sin6_port=htons(0), "
        'sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::1", &sin6_addr), '
        "sin6_scope_id=0}, 28) = 0\n",
        encoding="utf-8",
    )
    with pytest.raises(gate.GateError, match="strace"):
        gate._validate_strace(trace, {node})


@pytest.mark.parametrize(
    "network_line",
    [
        "101 socket(AF_PACKET, SOCK_RAW|SOCK_CLOEXEC, htons(ETH_P_ALL)) = 3",
        "101 socket(AF_XDP, SOCK_RAW|SOCK_CLOEXEC, 0) = 3",
        "101 socket(2, SOCK_DGRAM|SOCK_CLOEXEC, 0) = 3",
        "101 socket(AF_INET, SOCK_RAW|SOCK_CLOEXEC, IPPROTO_RAW) = 3",
        "101 socket(AF_INET, SOCK_DGRAM|SOCK_CLOEXEC, 253) = 3",
        "101 socket(AF_INET, SOCK_DGRAM|SOCK_CLOEXEC, IPPROTO_TCP) = 3",
        "101 socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_UDP) = 3",
        "101 socket(AF_INET, SOCK_DGRAM|SOCK_CLOEXEC, IPPROTO_IP <unfinished ...>",
        "101 <... connect resumed>{sa_family=AF_INET}, 16) = 0",
        "101 connect(3, {sa_family=AF_INET, sin_port=htons(443)}, 16) = 0",
        "101 connect(3, 0x7fff0000, 16) = -1 EFAULT (Bad address)",
        "101 bind(3, {sa_family=AF_INET, sin_port=htons(0)}, 16) = 0",
        '101 sendto(3, "x", 1, 0, {sa_family=AF_INET6}, 28) = 1',
        '101 sendmsg(3, {msg_name=NULL, msg_iov=[{iov_base="x"}]}, 0) = 1',
        '101 recvfrom(3, "x", 1, 0, {sa_family=AF_INET}, [16]) = 1',
        "101 setsockopt(3, SOL_IP, IP_ADD_MEMBERSHIP, {imr_interface=0}, 8) = 0",
        "101 setsockopt(3, SOL_SOCKET, SO_UNKNOWN_OPTION, [1], 4) = 0",
        "101 listen(3, 128) = 0",
        "101 connect(3, {sa_family=AF_INET}, 16) = 0; socket(AF_INET, SOCK_DGRAM, IPPROTO_IP) = 4",
        "101 socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, [3, 4]) = ???",
        "101 socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, 0x7fff0000) = 0",
        "101 sendto(5, [{rtm_family=AF_INET}], 20, 0, {sa_family=AF_NETLINK}, 12) = ???",
    ],
)
def test_strace_audit_rejects_external_socket_or_traffic(tmp_path: Path, network_line: str) -> None:
    node = (tmp_path / "node").resolve()
    trace = tmp_path / "inspector.strace.log"
    trace.write_text(
        f'101 execve("{node}", ["{node}"], 0x0) = 0\n{network_line}\n',
        encoding="utf-8",
    )
    with pytest.raises(gate.GateError, match="strace"):
        gate._validate_strace(trace, {node})


def test_strace_audit_rejects_non_utf8_trace(tmp_path: Path) -> None:
    node = (tmp_path / "node").resolve()
    trace = tmp_path / "inspector.strace.log"
    trace.write_bytes(f'101 execve("{node}", ["{node}"], 0x0) = 0\n'.encode() + b"\xff")
    with pytest.raises(gate.GateError, match="valid UTF-8"):
        gate._validate_strace(trace, {node})


def test_strace_audit_rejects_unexpected_execve(tmp_path: Path) -> None:
    node = (tmp_path / "node").resolve()
    trace = tmp_path / "inspector.strace.log"
    unexpected = (tmp_path / "unexpected").resolve()
    trace.write_text(
        f'101 execve("{node}", ["{node}"], 0x0) = 0\n'
        f'102 execve("{unexpected}", ["{unexpected}"], 0x0) = 0\n',
        encoding="utf-8",
    )
    with pytest.raises(gate.GateError, match="unexpected executable"):
        gate._validate_strace(trace, {node})


def test_harness_validator_accepts_only_frozen_registry_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = gate._validate_harness_files(MANIFEST, LOCK)
    assert report == {
        "install_script_packages": sorted(gate.EXPECTED_INSTALL_SCRIPT_PACKAGES),
        "lock_package_count": 241,
        "lock_sha256": LOCK_SHA256,
        "package_sha256": MANIFEST_SHA256,
    }

    mutated_lock = json.loads(LOCK.read_text(encoding="utf-8"))
    entry = mutated_lock["packages"]["node_modules/@modelcontextprotocol/inspector"]
    entry["resolved"] = "https://example.invalid/inspector.tgz"
    lock_path = tmp_path / "package-lock.json"
    lock_path.write_text(json.dumps(mutated_lock), encoding="utf-8")
    monkeypatch.setattr(gate, "EXPECTED_LOCK_SHA256", _sha256(lock_path))
    with pytest.raises(gate.GateError, match="public HTTPS registry"):
        gate._validate_harness_files(MANIFEST, lock_path)


def test_runtime_preparation_is_private_sanitized_and_immutable(tmp_path: Path) -> None:
    executable_root = tmp_path / "executables"
    executable_root.mkdir()
    node = executable_root / "node"
    installed_python = executable_root / "python"
    server_command = executable_root / "evidencemesh-mcp"
    for executable in (node, installed_python, server_command):
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o700)
    template_before = DESCRIPTOR.read_bytes()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    runtime = gate._prepare_runtime(
        runtime_root,
        node=node,
        installed_python=installed_python,
        server_command=server_command,
        descriptor_template=DESCRIPTOR,
    )
    descriptor = runtime["descriptor"]
    assert isinstance(descriptor, Path)
    descriptor_bytes = runtime["descriptor_bytes"]
    assert isinstance(descriptor_bytes, bytes)
    assert descriptor.read_bytes() == descriptor_bytes
    assert stat.S_IMODE(descriptor.stat().st_mode) == 0o600
    assert DESCRIPTOR.read_bytes() == template_before
    assert _sha256(DESCRIPTOR) == gate.DESCRIPTOR_TEMPLATE_SHA256

    payload = json.loads(descriptor_bytes)
    assert list(payload["mcpServers"]) == ["evidencemesh"]
    host = payload["mcpServers"]["evidencemesh"]
    template_host = json.loads(template_before)["mcpServers"]["evidencemesh"]
    expected_host = copy.deepcopy(template_host)
    expected_host["command"] = str(server_command.resolve())
    cache_path = runtime["cache_path"]
    assert isinstance(cache_path, Path)
    expected_host["env"]["EVIDENCEMESH_CACHE_PATH"] = str(cache_path.resolve())
    assert host == expected_host

    environment = runtime["environment"]
    assert isinstance(environment, dict)
    assert environment["NODE_OPTIONS"].startswith("--require=")
    assert environment["PYTHONPATH"].endswith("guards")
    assert environment["EVIDENCEMESH_A1_P2_REQUEST_TRACE"].endswith("mcp-request-trace.jsonl")
    assert not any(
        key in environment
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    )
    paths = runtime["paths"]
    assert isinstance(paths, dict)
    server_environment = runtime["server_environment"]
    assert server_environment == [
        f"PYTHONPATH={(runtime_root / 'guards').resolve()}",
        f"EVIDENCEMESH_A1_P2_PYTHON_GUARD_ARMED_LOG={paths['python_armed']}",
        f"EVIDENCEMESH_A1_P2_PYTHON_NETWORK_LOG={paths['python_network']}",
        f"EVIDENCEMESH_A1_P2_REQUEST_TRACE={paths['request_trace']}",
        "PYTHONNOUSERSITE=1",
        "PYTHONDONTWRITEBYTECODE=1",
        f"XDG_CACHE_HOME={(runtime_root / 'readonly-home' / '.cache').resolve()}",
        f"XDG_CONFIG_HOME={(runtime_root / 'readonly-home' / '.config').resolve()}",
        f"XDG_DATA_HOME={(runtime_root / 'readonly-home' / '.local/share').resolve()}",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
    ]
    assert gate._server_environment_arguments(server_environment) == [
        item for override in server_environment for item in ("-e", override)
    ]
    source = (ROOT / "scripts" / "verify_alpha_a1_p2_named_host.py").read_text(encoding="utf-8")
    assert 'runtime["server_environment"]' in source
    assert "_server_environment_arguments(server_environment)" in source
    home = runtime["home"]
    assert isinstance(home, Path)
    assert stat.S_IMODE(home.stat().st_mode) == 0o555
    assert list(home.iterdir()) == []


def test_acquisition_environment_is_registry_only_and_secret_free(tmp_path: Path) -> None:
    node = tmp_path / "bin" / "node"
    node.parent.mkdir()
    acquisition_root = tmp_path / "acquire"
    acquisition_root.mkdir()
    environment, cache = gate._acquisition_environment(acquisition_root, node)

    assert environment["NPM_CONFIG_REGISTRY"] == "https://registry.npmjs.org/"
    assert environment["NPM_CONFIG_FETCH_RETRIES"] == "0"
    assert environment["NPM_CONFIG_IGNORE_SCRIPTS"] == "true"
    assert environment["NPM_CONFIG_AUDIT"] == "false"
    assert environment["NPM_CONFIG_FUND"] == "false"
    assert environment["NPM_CONFIG_UPDATE_NOTIFIER"] == "false"
    assert cache.is_dir()
    assert not any("TOKEN" in key or "SECRET" in key or "KEY" in key for key in environment)


@pytest.mark.parametrize(
    ("stderr", "marker"),
    [
        ("Traceback (most recent call last):\n", "PYTHON_TRACEBACK"),
        ("ERROR failed\n", "ERROR_OR_CRITICAL_LINE"),
        ("critical: failed\n", "ERROR_OR_CRITICAL_LINE"),
        ("UnhandledPromiseRejection: failed\n", "UNHANDLED_REJECTION"),
        ("Unhandled exception in worker\n", "UNHANDLED_EXCEPTION"),
    ],
)
def test_stderr_marker_detection_is_fail_closed(stderr: str, marker: str) -> None:
    assert marker in gate._stderr_error_markers(stderr)


def test_stderr_marker_detection_allows_benign_diagnostics() -> None:
    assert gate._stderr_error_markers("INFO server started\nDEBUG tool call complete\n") == []
