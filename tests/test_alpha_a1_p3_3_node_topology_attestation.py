from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from scripts import verify_alpha_a1_p3_3_node_topology_attestation as gate

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "alpha" / "alpha_a1_p3_3_node_topology_attestation_policy_v1.json"
PROTOCOL = ROOT / "docs" / "alpha-a1-p3-3-node-topology-attestation-gate-v1.md"
WORKFLOW = ROOT / ".github" / "workflows" / "alpha-a1-p3-3-node-topology-attestation.yml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _node(tmp_path: Path) -> Path:
    node = tmp_path / "bin" / "node"
    node.parent.mkdir(parents=True, exist_ok=True)
    node.write_text("node", encoding="utf-8")
    return node


def _trace_file(tmp_path: Path, node: Path, root: int = 101, child: int = 202) -> Path:
    path = tmp_path / "gemini.strace.log"
    path.write_text(
        f'{root} execve("{node}", ["node"], 0x0) = 0\n'
        f"{root} clone3({{flags=CLONE_VM|CLONE_VFORK}}, 88) = {child}\n"
        f'{child} execve("{node}", ["node"], 0x0) = 0\n',
        encoding="utf-8",
    )
    return path


def _events(
    runtime_root: Path,
    node: Path,
    *,
    repository_root: Path = ROOT,
    root: int = 101,
    child: int = 202,
    child_kind: str = "auto_memory",
) -> list[dict[str, object]]:
    digest = gate._expected_argv_sha256(repository_root, runtime_root, node)
    common: dict[str, object] = {
        "argv_sha256": digest,
        "event": "armed",
        "exec_path": str(node.resolve()),
        "is_main_thread": True,
        "schema_version": gate.NODE_EVENT_SCHEMA,
        "thread_id": 0,
    }
    return [
        {
            **common,
            "exec_argv_kind": "none",
            "pid": root,
            "ppid": 9,
            "relaunch_child": False,
        },
        {
            **common,
            "exec_argv_kind": child_kind,
            "pid": child,
            "ppid": root,
            "relaunch_child": True,
        },
    ]


def _write_events(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    path.chmod(0o600)


def test_policy_freezes_topology_oracle_and_one_shot_budget() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["schema_version"] == (
        "evidencemesh.alpha-a1-p3-3-node-topology-attestation-policy.v1"
    )
    assert policy["entry_criteria"]["exact_parent_commit"] == gate.FAILED_P3_2_COMMIT
    assert policy["entry_criteria"]["exact_parent_tree"] == gate.FAILED_P3_2_TREE
    oracle = policy["node_topology_oracle"]
    assert oracle["node_processes_exact"] == 2
    assert oracle["host_root_processes_exact"] == 1
    assert oracle["direct_child_processes_exact"] == 1
    assert oracle["guard_pid_multiset_equals_traced_node_execution_pid_multiset"] is True
    assert oracle["count_only_relaxation_forbidden"] is True
    budgets = policy["budgets"]
    assert budgets["corrective_commit_publications"] == 1
    assert budgets["corrective_workflow_runs"] == 1
    assert budgets["dependency_install_attempts"] == 1
    assert budgets["host_invocations"] == 1
    assert budgets["logical_mcp_requests_expected"] == 5
    assert budgets["historical_run_reruns"] == 0
    assert budgets["runtime_network_requests"] == 0
    assert budgets["workflow_retries"] == 0
    assert not any(policy["authority"].values())


def test_corrective_and_cumulative_scope_are_exact() -> None:
    assert gate.FAILED_P3_2_COMMIT == "d3b3a00427321ca9130797f179edc0302e2b5952"
    assert gate.FAILED_P3_2_TREE == "fe995d124667d1f95b75e9130a59049ce69c1a1d"
    assert gate.CORRECTIVE_CHANGED_PATHS == {
        ".github/workflows/alpha-a1-p3-3-node-topology-attestation.yml": "A",
        "alpha/alpha_a1_p3_3_node_topology_attestation_policy_v1.json": "A",
        "docs/alpha-a1-p3-3-node-topology-attestation-gate-v1.md": "A",
        "scripts/verify_alpha_a1_p3_3_node_topology_attestation.py": "A",
        "tests/test_alpha_a1_p3_3_node_topology_attestation.py": "A",
    }
    assert len(gate.CUMULATIVE_CHANGED_PATHS) == 23


def test_prior_p3_p3_1_and_p3_2_files_remain_byte_identical() -> None:
    immutable = {
        **gate.p32.p31.FAILED_CHECKPOINT_IMMUTABLE_SHA256,
        **gate.p32.P3_1_CHECKPOINT_IMMUTABLE_SHA256,
        **gate.P3_2_CHECKPOINT_IMMUTABLE_SHA256,
    }
    assert len(immutable) == 18
    for relative, expected in immutable.items():
        assert _sha256(ROOT / relative) == expected


def test_node_guard_is_topology_aware_and_does_not_log_raw_targets_or_argv() -> None:
    guard = gate.NODE_TOPOLOGY_GUARD

    assert gate.NODE_EVENT_SCHEMA in guard
    assert "argv_sha256" in guard
    assert "ppid: process.ppid" in guard
    assert "relaunch_child" in guard
    assert "auto_memory" in guard
    assert "String(target)" not in guard
    assert "`${operation}:" not in guard
    assert "JSON.stringify(process.argv)" in guard
    assert "argv: process.argv" not in guard
    assert "env:" not in guard


def test_node_guard_emits_bounded_json_and_redacts_denied_target(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    guard = tmp_path / "node-network-guard.cjs"
    armed = tmp_path / "node-guard-armed.log"
    network = tmp_path / "node-network-attempts.log"
    guard.write_text(gate.NODE_TOPOLOGY_GUARD, encoding="utf-8")
    for path in (guard, armed, network):
        if not path.exists():
            path.write_text("", encoding="utf-8")
        path.chmod(0o600)
    environment = {
        "EVIDENCEMESH_A1_P3_NODE_GUARD_ARMED_LOG": str(armed),
        "EVIDENCEMESH_A1_P3_NODE_NETWORK_LOG": str(network),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NODE_OPTIONS": f"--require={guard}",
        "PATH": str(Path(node).resolve().parent),
    }
    completed = subprocess.run(  # noqa: S603 - executable is resolved by shutil.which.
        [node, "-e", 'process.stdout.write("ok")'],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout == "ok"
    event = json.loads(armed.read_text(encoding="utf-8"))
    assert set(event) == gate.NODE_EVENT_KEYS
    assert event["event"] == "armed"
    assert event["exec_path"] == str(Path(node).resolve())
    assert network.read_text(encoding="utf-8") == ""

    forbidden_target = "A1P33_TARGET_MUST_NOT_APPEAR.invalid"
    denied = subprocess.run(  # noqa: S603 - executable is resolved by shutil.which.
        [node, "-e", f'require("node:https").request("https://{forbidden_target}")'],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert denied.returncode != 0
    denial_text = network.read_text(encoding="utf-8")
    assert forbidden_target not in denial_text
    denial = json.loads(denial_text)
    assert set(denial) == {"event", "operation", "pid", "schema_version"}
    assert denial["event"] == "network_denied"
    assert denial["operation"] == "https.request"


def test_workflow_uses_new_label_exact_module_and_no_publication() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Alpha A1-P3.3 Node topology attestation" in workflow
    assert "types: [labeled]" in workflow
    assert "github.event.label.name == 'alpha-a1-p3-3-authorized'" in workflow
    assert "github.event.label.name == 'alpha-a1-p3-2-authorized'" not in workflow
    assert '"$python_path" -m scripts.verify_alpha_a1_p3_3_node_topology_attestation' in workflow
    assert "fetch-depth: 5" in workflow
    assert "upload-artifact" not in workflow
    assert "workflow_dispatch" not in workflow
    assert "npm publish" not in workflow


def test_exact_module_entrypoint_imports_from_repository_root() -> None:
    environment = {
        "HOME": os.devnull,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "PYTHONNOUSERSITE": "1",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_alpha_a1_p3_3_node_topology_attestation",
            "--help",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0
    assert "Alpha A1-P3.3 Node launcher topology attestation" in completed.stdout
    assert completed.stderr == ""


def test_scope_validator_locks_four_checkpoint_ancestors(monkeypatch) -> None:
    expected_head = "a" * 40
    direct = "\n".join(
        f"{status}\t{path}" for path, status in gate.CORRECTIVE_CHANGED_PATHS.items()
    )
    cumulative = "\n".join(f"A\t{path}" for path in gate.CUMULATIVE_CHANGED_PATHS)

    def fake_git(arguments, **_kwargs) -> str:
        table = {
            ("rev-parse", "HEAD"): expected_head,
            ("rev-list", "--parents", "-n", "1", expected_head): (
                f"{expected_head} {gate.FAILED_P3_2_COMMIT}"
            ),
            ("rev-list", "--parents", "-n", "1", gate.FAILED_P3_2_COMMIT): (
                f"{gate.FAILED_P3_2_COMMIT} {gate.FAILED_P3_1_COMMIT}"
            ),
            ("rev-list", "--parents", "-n", "1", gate.FAILED_P3_1_COMMIT): (
                f"{gate.FAILED_P3_1_COMMIT} {gate.FAILED_P3_COMMIT}"
            ),
            ("rev-list", "--parents", "-n", "1", gate.FAILED_P3_COMMIT): (
                f"{gate.FAILED_P3_COMMIT} {gate.BASE_COMMIT}"
            ),
            ("rev-parse", f"{gate.BASE_COMMIT}^{{tree}}"): gate.BASE_TREE,
            ("rev-parse", f"{gate.FAILED_P3_COMMIT}^{{tree}}"): gate.FAILED_P3_TREE,
            ("rev-parse", f"{gate.FAILED_P3_1_COMMIT}^{{tree}}"): gate.FAILED_P3_1_TREE,
            ("rev-parse", f"{gate.FAILED_P3_2_COMMIT}^{{tree}}"): gate.FAILED_P3_2_TREE,
            (
                "diff",
                "--name-status",
                "--no-renames",
                gate.FAILED_P3_2_COMMIT,
                expected_head,
            ): direct,
            (
                "diff",
                "--name-status",
                "--no-renames",
                gate.BASE_COMMIT,
                expected_head,
            ): cumulative,
        }
        return table[tuple(arguments)]

    monkeypatch.setattr(gate, "_git", fake_git)
    gate._validate_scope(ROOT, expected_head, Path("/usr/bin/git"), 0.0)


def test_strace_parser_accepts_exact_two_node_execs_and_direct_edge(tmp_path: Path) -> None:
    node = _node(tmp_path)
    trace = gate._parse_strace_topology(_trace_file(tmp_path, node), node)

    assert trace["node_execs"] == Counter({101: 1, 202: 1})
    assert trace["spawn_parents"][202] == 101


@pytest.mark.parametrize(
    "spawn_lines",
    [
        ["[pid 101] clone(NULL, SIGCHLD) = 202"],
        ["[pid 101] fork() = 202"],
        ["[pid 101] vfork() = 202"],
        [
            "[pid 101] clone3({flags=CLONE_VM|CLONE_VFORK}, 88 <unfinished ...>",
            "[pid 101] <... clone3 resumed>) = 202",
        ],
    ],
)
def test_strace_parser_accepts_ubuntu_pid_and_spawn_forms(
    tmp_path: Path, spawn_lines: list[str]
) -> None:
    node = _node(tmp_path)
    path = tmp_path / "gemini.strace.log"
    lines = [f'[pid 101] execve("{node}", ["node"], 0x0) = 0']
    lines.extend(spawn_lines)
    lines.append(f'[pid 202] execve("{node}", ["node"], 0x0) = 0')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    trace = gate._parse_strace_topology(path, node)
    assert trace["node_execs"] == Counter({101: 1, 202: 1})
    assert trace["spawn_parents"][202] == 101


def test_strace_parser_ignores_failed_path_lookup_execs(tmp_path: Path) -> None:
    node = _node(tmp_path)
    path = _trace_file(tmp_path, node)
    original = path.read_text(encoding="utf-8")
    path.write_text(
        '77 execve("/usr/local/bin/node", ["node"], 0x0) = -1 ENOENT (No such file)\n' + original,
        encoding="utf-8",
    )
    trace = gate._parse_strace_topology(path, node)
    assert trace["node_execs"] == Counter({101: 1, 202: 1})


def test_strace_parser_pairs_unfinished_and_resumed_execve(tmp_path: Path) -> None:
    node = _node(tmp_path)
    path = tmp_path / "gemini.strace.log"
    path.write_text(
        f'101 execve("{node}", ["node"], 0x0) = 0\n'
        "101 clone3({flags=CLONE_VM|CLONE_VFORK}, 88) = 202\n"
        f'202 execve("{node}", ["node"], 0x0 <unfinished ...>\n'
        "202 <... execve resumed>) = 0\n",
        encoding="utf-8",
    )
    trace = gate._parse_strace_topology(path, node)
    assert trace["node_execs"] == Counter({101: 1, 202: 1})


def test_strace_parser_counts_execveat_and_rejects_a_third_node(tmp_path: Path) -> None:
    node = _node(tmp_path)
    path = _trace_file(tmp_path, node)
    path.write_text(
        path.read_text(encoding="utf-8")
        + f'303 execveat(AT_FDCWD, "{node}", ["node"], 0x0, 0) = 0\n',
        encoding="utf-8",
    )
    with pytest.raises(gate.p3.GateError, match="Node exec count drifted"):
        gate._parse_strace_topology(path, node)


def test_strace_parser_accepts_absolute_canonical_node_execveat(tmp_path: Path) -> None:
    node = _node(tmp_path)
    path = tmp_path / "gemini.strace.log"
    path.write_text(
        f'101 execve("{node}", ["node"], 0x0) = 0\n'
        "101 clone3({flags=CLONE_VM|CLONE_VFORK}, 88) = 202\n"
        f'202 execveat(AT_FDCWD, "{node}", ["node"], 0x0, 0) = 0\n',
        encoding="utf-8",
    )
    trace = gate._parse_strace_topology(path, node)
    assert trace["node_execs"] == Counter({101: 1, 202: 1})


def test_strace_parser_rejects_unresolvable_successful_execveat(tmp_path: Path) -> None:
    node = _node(tmp_path)
    path = _trace_file(tmp_path, node)
    path.write_text(
        path.read_text(encoding="utf-8")
        + '303 execveat(4, "", ["node"], 0x0, AT_EMPTY_PATH) = 0\n',
        encoding="utf-8",
    )
    with pytest.raises(gate.p3.GateError, match="cannot resolve a successful execveat path"):
        gate._parse_strace_topology(path, node)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ('202 execve("/other/node", ["node"], 0x0) = 0', "non-canonical"),
        ('101 execve("{node}", ["node"], 0x0) = 0', "exec PID multiplicity"),
        ('202 execve("{node}", ["node"], 0x0 <unfinished ...>', "unfinished execve"),
    ],
)
def test_strace_parser_rejects_node_drift(tmp_path: Path, replacement: str, message: str) -> None:
    node = _node(tmp_path)
    path = _trace_file(tmp_path, node)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[-1] = replacement.format(node=node)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(gate.p3.GateError, match=message):
        gate._parse_strace_topology(path, node)


@pytest.mark.parametrize("child_kind", ["none", "auto_memory"])
def test_topology_oracle_accepts_only_the_two_normalized_child_variants(
    tmp_path: Path, child_kind: str
) -> None:
    node = _node(tmp_path)
    runtime_root = tmp_path / "runtime"
    log = runtime_root / "node-guard-armed.log"
    _write_events(log, _events(runtime_root, node, child_kind=child_kind))
    trace = gate._parse_strace_topology(_trace_file(tmp_path, node), node)

    pids, report = gate._validate_node_topology(
        log,
        trace=trace,
        repository_root=ROOT,
        canonical_node=node,
    )

    assert pids == {101, 202}
    assert report["node_processes"] == 2
    assert report["direct_launcher_edge"] is True
    assert report["child_exec_argv_kind"] == child_kind


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda events: events.__setitem__(1, {**events[1], "pid": 303}), "coverage differs"),
        (
            lambda events: events.__setitem__(1, {**events[1], "ppid": 77}),
            "not a direct root descendant",
        ),
        (
            lambda events: events.__setitem__(1, {**events[1], "relaunch_child": False}),
            "root launcher count",
        ),
        (
            lambda events: events.__setitem__(1, {**events[1], "exec_argv_kind": "unexpected"}),
            "child exec argv",
        ),
        (
            lambda events: events.__setitem__(1, {**events[1], "is_main_thread": False}),
            "worker thread",
        ),
        (
            lambda events: events.__setitem__(1, {**events[1], "argv_sha256": "0" * 64}),
            "argv drifted",
        ),
        (
            lambda events: events.__setitem__(1, {**events[1], "thread_id": False}),
            "thread identity",
        ),
        (
            lambda events: events.__setitem__(1, {**events[1], "exec_path": "bin/node"}),
            "executable drifted",
        ),
    ],
)
def test_topology_oracle_rejects_adversarial_roles(tmp_path: Path, mutation, message: str) -> None:
    node = _node(tmp_path)
    runtime_root = tmp_path / "runtime"
    events = _events(runtime_root, node)
    mutation(events)
    log = runtime_root / "node-guard-armed.log"
    _write_events(log, events)
    trace = gate._parse_strace_topology(_trace_file(tmp_path, node), node)
    with pytest.raises(gate.p3.GateError, match=message):
        gate._validate_node_topology(
            log,
            trace=trace,
            repository_root=ROOT,
            canonical_node=node,
        )


def test_topology_oracle_rejects_missing_strace_edge(tmp_path: Path) -> None:
    node = _node(tmp_path)
    runtime_root = tmp_path / "runtime"
    log = runtime_root / "node-guard-armed.log"
    _write_events(log, _events(runtime_root, node))
    trace = {"node_execs": Counter({101: 1, 202: 1}), "spawn_parents": {202: 77}}
    with pytest.raises(gate.p3.GateError, match="direct Node launcher edge"):
        gate._validate_node_topology(
            log,
            trace=trace,
            repository_root=ROOT,
            canonical_node=node,
        )


def test_guard_reader_rejects_duplicate_pid_extra_key_and_bad_mode(tmp_path: Path) -> None:
    node = _node(tmp_path)
    runtime_root = tmp_path / "runtime"
    log = runtime_root / "node-guard-armed.log"
    events = _events(runtime_root, node)
    events[1]["pid"] = events[0]["pid"]
    _write_events(log, events)
    with pytest.raises(gate.p3.GateError, match="more than once"):
        gate._validate_node_topology(
            log,
            trace={"node_execs": Counter({101: 2}), "spawn_parents": {}},
            repository_root=ROOT,
            canonical_node=node,
        )

    events = _events(runtime_root, node)
    events[0]["target"] = "forbidden"
    _write_events(log, events)
    with pytest.raises(gate.p3.GateError, match="keys drifted"):
        gate._read_node_events(log)

    _write_events(log, _events(runtime_root, node))
    log.chmod(0o644)
    with pytest.raises(gate.p3.GateError, match="mode drifted"):
        gate._read_node_events(log)


def test_guard_reader_rejects_symlink_malformed_and_unterminated_logs(tmp_path: Path) -> None:
    target = tmp_path / "target.log"
    target.write_text("{}\n", encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "node-guard-armed.log"
    link.symlink_to(target)
    with pytest.raises(gate.p3.GateError, match="symlink"):
        gate._read_node_events(link)

    link.unlink()
    link.write_text("not-json\nnot-json\n", encoding="utf-8")
    link.chmod(0o600)
    with pytest.raises(gate.p3.GateError, match="line 1 is malformed"):
        gate._read_node_events(link)

    link.write_text("{}\n{}", encoding="utf-8")
    link.chmod(0o600)
    with pytest.raises(gate.p3.GateError, match="unterminated"):
        gate._read_node_events(link)


def test_wrapper_adapters_are_counted_and_restored(monkeypatch, tmp_path: Path) -> None:
    node = _node(tmp_path)
    runtime_root = tmp_path / "p3-runtime"
    guard_log = runtime_root / "node-guard-armed.log"
    python_log = runtime_root / "python-guard-armed.log"
    _write_events(guard_log, _events(runtime_root, node))
    python_log.write_text("303\n", encoding="utf-8")
    trace_path = _trace_file(tmp_path, node)
    original_scope = gate.p32._validate_scope
    original_guard = gate.p3.NODE_GUARD

    monkeypatch.setattr(gate, "_validate_scope", lambda *_args: None)
    monkeypatch.setattr(gate.p3, "_validate_strace", lambda _path: {"network_calls": 0})
    monkeypatch.setattr(gate.p3, "_read_pid_set", lambda _path, _label: {303})

    def fake_p32_run_gate(**kwargs):
        gate.p32._validate_scope(ROOT, "a" * 40, Path("/usr/bin/git"), 0.0)
        gate.p3._validate_strace(trace_path)
        assert gate.p3._read_pid_set(guard_log, "Node guard") == {101, 202}
        assert gate.p3._read_pid_set(python_log, "Python guard") == {303}
        kwargs["output"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output"].write_text("{}\n", encoding="utf-8")
        return {
            "budgets": {},
            "correction": {"install_adapter_calls": 1},
            "prerequisite": {},
            "runtime": {},
        }

    monkeypatch.setattr(gate.p32, "run_gate", fake_p32_run_gate)
    patched_strace = gate.p3._validate_strace
    patched_reader = gate.p3._read_pid_set
    output = runtime_root / "gate-receipt.json"
    report = gate.run_gate(
        work_root=tmp_path,
        p0_receipt=tmp_path / "receipt.json",
        expected_head="a" * 40,
        output=output,
        git_executable=Path("/usr/bin/git"),
        node_executable=node,
        npm_executable=Path("/usr/bin/npm"),
        strace_executable=Path("/usr/bin/strace"),
    )

    assert gate.p32._validate_scope is original_scope
    assert gate.p3._validate_strace is patched_strace
    assert gate.p3._read_pid_set is patched_reader
    assert gate.p3.NODE_GUARD is original_guard
    assert report["correction"]["scope_adapter_calls"] == 1
    assert report["correction"]["strace_adapter_calls"] == 1
    assert report["correction"]["node_reader_calls"] == 1
    assert report["correction"]["python_reader_calls"] == 1
    assert report["runtime"]["node_topology"]["node_processes"] == 2
    assert not (runtime_root / ".a1-p3-2-receipt.json").exists()
    assert output.is_file()


def test_wrapper_restores_every_adapter_after_failure(monkeypatch, tmp_path: Path) -> None:
    original_scope = gate.p32._validate_scope
    original_strace = gate.p3._validate_strace
    original_reader = gate.p3._read_pid_set
    original_guard = gate.p3.NODE_GUARD
    monkeypatch.setattr(gate, "_validate_scope", lambda *_args: None)

    def failing_p32_run_gate(**_kwargs):
        gate.p32._validate_scope(ROOT, "a" * 40, Path("/usr/bin/git"), 0.0)
        raise gate.p3.GateError("synthetic failure")

    monkeypatch.setattr(gate.p32, "run_gate", failing_p32_run_gate)
    with pytest.raises(gate.p3.GateError, match="synthetic failure"):
        gate.run_gate(
            work_root=tmp_path,
            p0_receipt=tmp_path / "receipt.json",
            expected_head="a" * 40,
            output=tmp_path / "p3-runtime" / "gate-receipt.json",
            git_executable=Path("/usr/bin/git"),
            node_executable=Path("/usr/bin/node"),
            npm_executable=Path("/usr/bin/npm"),
            strace_executable=Path("/usr/bin/strace"),
        )

    assert gate.p32._validate_scope is original_scope
    assert gate.p3._validate_strace is original_strace
    assert gate.p3._read_pid_set is original_reader
    assert gate.p3.NODE_GUARD is original_guard


def test_protocol_preserves_failure_and_authority_boundary() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    assert "A1-P3.2 remains failed" in protocol
    assert "Node guard arming count drifted" in protocol
    assert "does not replace the failed cardinality rule with `>= 1`" in protocol
    assert "guard PID multiset must equal that traced Node multiset exactly" in protocol
    assert "External model, provider, search, document" in protocol
    assert "authorizes neither merge, Phase 12" in protocol
