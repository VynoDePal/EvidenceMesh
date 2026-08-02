"""Verify the Alpha A1-P3.3 Node launcher topology attestation and host gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from scripts import verify_alpha_a1_p3_2_optional_leaf_correction as p32
from scripts import verify_alpha_a1_p3_real_host_offline as p3

BASE_COMMIT = "3cc75a33790be353a74641034a3c5210dfc7bc17"
BASE_TREE = "21abc6024a08a5528710a5fd8e49630c8fca2c9d"
FAILED_P3_COMMIT = "38eb63ade7024ab32963f894c719fa190fe9346a"
FAILED_P3_TREE = "c21496bf690a8c2844a8957b7af12de72cf5b7ad"
FAILED_P3_1_COMMIT = "06b57853332a89e8adf21317e85cc6f91deecacf"
FAILED_P3_1_TREE = "c9f3b9bc7356753f751f9cd2dd32fab08c91d382"
FAILED_P3_2_COMMIT = "d3b3a00427321ca9130797f179edc0302e2b5952"
FAILED_P3_2_TREE = "fe995d124667d1f95b75e9130a59049ce69c1a1d"
FAILED_P3_2_RUN_ID = 30746731127
FAILED_P3_2_JOB_ID = 91493485240

CORRECTIVE_CHANGED_PATHS = {
    ".github/workflows/alpha-a1-p3-3-node-topology-attestation.yml": "A",
    "alpha/alpha_a1_p3_3_node_topology_attestation_policy_v1.json": "A",
    "docs/alpha-a1-p3-3-node-topology-attestation-gate-v1.md": "A",
    "scripts/verify_alpha_a1_p3_3_node_topology_attestation.py": "A",
    "tests/test_alpha_a1_p3_3_node_topology_attestation.py": "A",
}
CUMULATIVE_CHANGED_PATHS = p32.CUMULATIVE_CHANGED_PATHS | set(CORRECTIVE_CHANGED_PATHS)

P3_2_CHECKPOINT_IMMUTABLE_SHA256 = {
    ".github/workflows/alpha-a1-p3-2-optional-leaf-correction.yml": (
        "7caee4a0dd40968836a897fed30ba4c7fb1bf809e9ebeb472e77104106e25cbb"
    ),
    "alpha/alpha_a1_p3_2_optional_leaf_correction_policy_v1.json": (
        "9a810e62416ee36069287a4e041313632640c1172251dd099df509638288abc6"
    ),
    "docs/alpha-a1-p3-2-optional-leaf-correction-gate-v1.md": (
        "3ee123ba9729929c08bbc507c288dc58cba49da17639ddd39aeccd57c7266a09"
    ),
    "scripts/verify_alpha_a1_p3_2_optional_leaf_correction.py": (
        "92d7a3caf038a8c1db37613449bfe52a415ddeff3ce226c0a9c2339619df09c8"
    ),
    "tests/test_alpha_a1_p3_2_optional_leaf_correction.py": (
        "85e1bc61e0f72d0ff069a8d096e9bcb00aa349de4798cc60f4c324fa9803f0c7"
    ),
}

NODE_EVENT_SCHEMA = "evidencemesh.alpha-a1-p3-3-node-topology-event.v1"
NODE_EVENT_KEYS = {
    "argv_sha256",
    "event",
    "exec_argv_kind",
    "exec_path",
    "is_main_thread",
    "pid",
    "ppid",
    "relaunch_child",
    "schema_version",
    "thread_id",
}
MAXIMUM_NODE_GUARD_BYTES = 16_384
EXPECTED_NODE_PROCESSES = 2

_PID_PREFIX = r"(?:\[pid\s+)?(?P<pid>[1-9][0-9]*)(?:\])?"
_EXECVE_RE = re.compile(
    rf'^\s*{_PID_PREFIX}\s+execve\("(?P<path>[^"\n]+)",.*\)\s+=\s+(?P<result>.+?)\s*$'
)
_EXECVE_UNFINISHED_RE = re.compile(
    rf'^\s*{_PID_PREFIX}\s+execve\("(?P<path>[^"\n]+)",.*<unfinished \.\.\.>\s*$'
)
_EXECVE_RESUMED_RE = re.compile(
    rf"^\s*{_PID_PREFIX}\s+<\.\.\. execve resumed>.*\)\s+=\s+(?P<result>.+?)\s*$"
)
_EXECVEAT_RE = re.compile(
    rf'^\s*{_PID_PREFIX}\s+execveat\([^,]+,\s*"(?P<path>[^"\n]*)",.*\)\s+=\s+'
    r"(?P<result>.+?)\s*$"
)
_EXECVEAT_UNFINISHED_RE = re.compile(
    rf'^\s*{_PID_PREFIX}\s+execveat\([^,]+,\s*"(?P<path>[^"\n]*)",.*'
    r"<unfinished \.\.\.>\s*$"
)
_EXECVEAT_RESUMED_RE = re.compile(
    rf"^\s*{_PID_PREFIX}\s+<\.\.\. execveat resumed>.*\)\s+=\s+(?P<result>.+?)\s*$"
)
_SPAWN_RE = re.compile(
    rf"^\s*{_PID_PREFIX}\s+"
    r"(?:(?:clone3|clone|fork|vfork)\(.*|<\.\.\. (?:clone3|clone|fork|vfork) resumed>.*)"
    r"\s+=\s+(?P<child>[1-9][0-9]*)\s*$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _build_node_guard() -> str:
    source = p3.NODE_GUARD
    old_armed = 'fs.appendFileSync(armed, `${process.pid}\\n`, {encoding: "utf8"});'
    new_armed = rf'''const crypto = require("node:crypto");
const workerThreads = require("node:worker_threads");
let execArgvKind = "unexpected";
if (process.execArgv.length === 0) {{
  execArgvKind = "none";
}} else if (
  process.execArgv.length === 1 &&
  /^--max-old-space-size=[1-9][0-9]{{2,8}}$/.test(process.execArgv[0])
) {{
  execArgvKind = "auto_memory";
}}
const topologyEvent = {{
  argv_sha256: crypto.createHash("sha256")
    .update(JSON.stringify(process.argv), "utf8")
    .digest("hex"),
  event: "armed",
  exec_argv_kind: execArgvKind,
  exec_path: process.execPath,
  is_main_thread: workerThreads.isMainThread,
  pid: process.pid,
  ppid: process.ppid,
  relaunch_child: process.env.GEMINI_CLI_NO_RELAUNCH === "true",
  schema_version: "{NODE_EVENT_SCHEMA}",
  thread_id: workerThreads.threadId,
}};
fs.appendFileSync(armed, `${{JSON.stringify(topologyEvent)}}\n`, {{encoding: "utf8"}});'''
    old_deny = r"""function deny(operation, target) {
  fs.appendFileSync(blocked, `${operation}:${String(target)}\n`, {encoding: "utf8"});
  throw new Error("Alpha A1-P3 Node network is disabled");
}"""
    new_deny = rf'''function deny(operation) {{
  const denialEvent = {{
    event: "network_denied",
    operation,
    pid: process.pid,
    schema_version: "{NODE_EVENT_SCHEMA}",
  }};
  fs.appendFileSync(blocked, `${{JSON.stringify(denialEvent)}}\n`, {{encoding: "utf8"}});
  throw new Error("Alpha A1-P3 Node network is disabled");
}}'''
    p3._require(source.count(old_armed) == 1, "Historical Node arming hook drifted")
    p3._require(source.count(old_deny) == 1, "Historical Node denial hook drifted")
    return source.replace(old_armed, new_armed).replace(old_deny, new_deny)


NODE_TOPOLOGY_GUARD = _build_node_guard()


def _git(
    arguments: list[str],
    *,
    repository_root: Path,
    git_executable: Path,
    started_at: float,
    label: str,
) -> str:
    return p32._git(
        arguments,
        repository_root=repository_root,
        git_executable=git_executable,
        started_at=started_at,
        label=label,
    )


def _validate_scope(
    repository_root: Path,
    expected_head: str,
    git_executable: Path,
    started_at: float,
) -> None:
    p3._validate_full_sha(expected_head, "trigger head")
    head = _git(
        ["rev-parse", "HEAD"],
        repository_root=repository_root,
        git_executable=git_executable,
        started_at=started_at,
        label="A1-P3.3 checkout HEAD",
    )
    p3._require(head == expected_head, "Checkout does not match the A1-P3.3 trigger head")

    ancestry = (
        (expected_head, FAILED_P3_2_COMMIT, "A1-P3.3"),
        (FAILED_P3_2_COMMIT, FAILED_P3_1_COMMIT, "failed A1-P3.2"),
        (FAILED_P3_1_COMMIT, FAILED_P3_COMMIT, "failed A1-P3.1"),
        (FAILED_P3_COMMIT, BASE_COMMIT, "failed A1-P3"),
    )
    for commit, parent, label in ancestry:
        tokens = _git(
            ["rev-list", "--parents", "-n", "1", commit],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label=f"{label} parent inspection",
        ).split()
        p3._require(tokens == [commit, parent], f"{label} ancestry drifted")

    trees = (
        (BASE_COMMIT, BASE_TREE, "A1-P3.3 base tree"),
        (FAILED_P3_COMMIT, FAILED_P3_TREE, "failed A1-P3 tree"),
        (FAILED_P3_1_COMMIT, FAILED_P3_1_TREE, "failed A1-P3.1 tree"),
        (FAILED_P3_2_COMMIT, FAILED_P3_2_TREE, "failed A1-P3.2 tree"),
    )
    for commit, expected_tree, label in trees:
        observed = _git(
            ["rev-parse", f"{commit}^{{tree}}"],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label=label,
        )
        p3._require(observed == expected_tree, f"{label} drifted")

    direct = p32._name_status(
        _git(
            ["diff", "--name-status", "--no-renames", FAILED_P3_2_COMMIT, expected_head],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label="A1-P3.3 direct scope inspection",
        ),
        "A1-P3.3 direct scope",
    )
    p3._require(direct == CORRECTIVE_CHANGED_PATHS, "A1-P3.3 direct changed-path scope drifted")
    cumulative = p32._name_status(
        _git(
            ["diff", "--name-status", "--no-renames", BASE_COMMIT, expected_head],
            repository_root=repository_root,
            git_executable=git_executable,
            started_at=started_at,
            label="A1-P3.3 cumulative scope inspection",
        ),
        "A1-P3.3 cumulative scope",
    )
    p3._require(set(cumulative) == CUMULATIVE_CHANGED_PATHS, "A1-P3.3 cumulative scope drifted")
    p3._require(set(cumulative.values()) == {"A"}, "A1-P3.3 cumulative scope is not additive")

    immutable = {
        **p3.IMMUTABLE_SHA256,
        **p32.p31.FAILED_CHECKPOINT_IMMUTABLE_SHA256,
        **p32.P3_1_CHECKPOINT_IMMUTABLE_SHA256,
        **P3_2_CHECKPOINT_IMMUTABLE_SHA256,
    }
    for relative, expected_hash in immutable.items():
        path = repository_root / relative
        p3._require(path.is_file(), f"A1-P3.3 immutable file is missing: {relative}")
        p3._require(
            p3._sha256_file(path) == expected_hash,
            f"A1-P3.3 immutable file drifted: {relative}",
        )


def _parse_strace_topology(path: Path, canonical_node: Path) -> dict[str, Any]:
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise p3.GateError("A1-P3.3 strace log is unreadable") from exc
    p3._require(bool(value), "A1-P3.3 strace log is empty")

    node_execs: Counter[int] = Counter()
    spawn_parents: dict[int, int] = {}
    pending_execs: dict[int, tuple[str, bool]] = {}
    canonical = canonical_node.resolve()

    def record_exec(pid: int, raw_path: str, result: str, *, via_execveat: bool) -> None:
        if result.strip() != "0":
            return
        observed_path = Path(raw_path)
        if via_execveat:
            p3._require(
                bool(raw_path) and observed_path.is_absolute(),
                "A1-P3.3 cannot resolve a successful execveat path",
            )
            p3._require(
                observed_path.name
                in {"evidencemesh-mcp", "git", "node", "python", "python3", "python3.11", "rg"},
                "A1-P3.3 execveat executed an unexpected program",
            )
        if observed_path.name == "node":
            p3._require(
                observed_path.is_absolute() and observed_path.resolve() == canonical,
                "A1-P3.3 traced a non-canonical Node executable",
            )
            node_execs[pid] += 1

    for line_number, line in enumerate(value.splitlines(), start=1):
        if "execveat(" in line:
            unfinished_at = _EXECVEAT_UNFINISHED_RE.fullmatch(line)
            if unfinished_at is not None:
                pid = int(unfinished_at.group("pid"))
                p3._require(pid not in pending_execs, "A1-P3.3 has duplicate pending execve")
                pending_execs[pid] = (unfinished_at.group("path"), True)
                continue
            match_at = _EXECVEAT_RE.fullmatch(line)
            p3._require(
                match_at is not None,
                f"A1-P3.3 strace execveat line {line_number} is ambiguous",
            )
            record_exec(
                int(match_at.group("pid")),
                match_at.group("path"),
                match_at.group("result"),
                via_execveat=True,
            )

        if "execve(" in line:
            unfinished = _EXECVE_UNFINISHED_RE.fullmatch(line)
            if unfinished is not None:
                pid = int(unfinished.group("pid"))
                p3._require(pid not in pending_execs, "A1-P3.3 has duplicate pending execve")
                pending_execs[pid] = (unfinished.group("path"), False)
                continue
            match = _EXECVE_RE.fullmatch(line)
            p3._require(
                match is not None,
                f"A1-P3.3 strace execve line {line_number} is ambiguous",
            )
            record_exec(
                int(match.group("pid")),
                match.group("path"),
                match.group("result"),
                via_execveat=False,
            )

        if "<... execve resumed>" in line:
            resumed = _EXECVE_RESUMED_RE.fullmatch(line)
            p3._require(
                resumed is not None,
                f"A1-P3.3 strace execve line {line_number} is ambiguous",
            )
            pid = int(resumed.group("pid"))
            p3._require(pid in pending_execs, "A1-P3.3 execve resumed without an origin")
            raw_path, via_execveat = pending_execs.pop(pid)
            p3._require(not via_execveat, "A1-P3.3 execve resumed the wrong syscall")
            record_exec(pid, raw_path, resumed.group("result"), via_execveat=via_execveat)

        if "<... execveat resumed>" in line:
            resumed_at = _EXECVEAT_RESUMED_RE.fullmatch(line)
            p3._require(
                resumed_at is not None,
                f"A1-P3.3 strace execveat line {line_number} is ambiguous",
            )
            pid = int(resumed_at.group("pid"))
            p3._require(pid in pending_execs, "A1-P3.3 execveat resumed without an origin")
            raw_path, via_execveat = pending_execs.pop(pid)
            p3._require(via_execveat, "A1-P3.3 execveat resumed the wrong syscall")
            record_exec(pid, raw_path, resumed_at.group("result"), via_execveat=True)

        spawn = _SPAWN_RE.fullmatch(line)
        if spawn is not None:
            parent = int(spawn.group("pid"))
            child = int(spawn.group("child"))
            prior = spawn_parents.setdefault(child, parent)
            p3._require(prior == parent, "A1-P3.3 traced conflicting process parents")

    p3._require(not pending_execs, "A1-P3.3 strace contains an unfinished execve")
    p3._require(sum(node_execs.values()) == EXPECTED_NODE_PROCESSES, "Node exec count drifted")
    p3._require(len(node_execs) == EXPECTED_NODE_PROCESSES, "Node exec PID multiplicity drifted")
    p3._require(set(node_execs.values()) == {1}, "A Node PID was execve'd more than once")
    return {"node_execs": node_execs, "spawn_parents": spawn_parents}


def _expected_argv_sha256(repository_root: Path, runtime_root: Path, node: Path) -> str:
    launcher = (
        runtime_root
        / "gemini-harness"
        / "node_modules"
        / "@google"
        / "gemini-cli"
        / "bundle"
        / "gemini.js"
    )
    fake_responses = repository_root / p3.HARNESS_RELATIVE_PATH / "fake-responses.jsonl"
    argv = [
        str(node.resolve()),
        str(launcher),
        "--prompt",
        p3.PROMPT,
        "--model",
        p3.MODEL_NAME,
        "--approval-mode",
        "default",
        "--allowed-mcp-server-names",
        p3.NAMED_HOST,
        "--output-format",
        "stream-json",
        "--skip-trust",
        "--session-id",
        p3.SESSION_ID,
        "--fake-responses",
        str(fake_responses),
    ]
    encoded = json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_node_events(path: Path) -> list[dict[str, Any]]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise p3.GateError("Node topology guard log is unreadable") from exc
    p3._require(not stat.S_ISLNK(metadata.st_mode), "Node topology guard log is a symlink")
    p3._require(stat.S_ISREG(metadata.st_mode), "Node topology guard log is not regular")
    p3._require(stat.S_IMODE(metadata.st_mode) == 0o600, "Node topology guard mode drifted")
    p3._require(
        0 < metadata.st_size <= MAXIMUM_NODE_GUARD_BYTES,
        "Node topology guard size drifted",
    )
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise p3.GateError("Node topology guard log is unreadable") from exc
    p3._require(value.endswith("\n"), "Node topology guard log is unterminated")
    lines = value.splitlines()
    p3._require(len(lines) == EXPECTED_NODE_PROCESSES, "Node topology event count drifted")
    p3._require(all(lines), "Node topology guard contains a blank line")

    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise p3.GateError(f"Node topology line {line_number} is malformed") from exc
        p3._require(isinstance(event, dict), f"Node topology line {line_number} is not an object")
        p3._require(set(event) == NODE_EVENT_KEYS, f"Node topology line {line_number} keys drifted")
        p3._require(event.get("schema_version") == NODE_EVENT_SCHEMA, "Node event schema drifted")
        p3._require(event.get("event") == "armed", "Node event type drifted")
        pid = event.get("pid")
        ppid = event.get("ppid")
        p3._require(
            isinstance(pid, int) and not isinstance(pid, bool) and pid > 1,
            "Node event PID drifted",
        )
        p3._require(
            isinstance(ppid, int) and not isinstance(ppid, bool) and ppid >= 1,
            "Node event parent PID drifted",
        )
        exec_path = event.get("exec_path")
        p3._require(
            isinstance(exec_path, str) and Path(exec_path).is_absolute(),
            "Node event executable drifted",
        )
        p3._require(
            isinstance(event.get("argv_sha256"), str)
            and _SHA256_RE.fullmatch(event["argv_sha256"]) is not None,
            "Node event argv digest drifted",
        )
        p3._require(
            event.get("exec_argv_kind") in {"none", "auto_memory", "unexpected"},
            "Node event exec argv kind drifted",
        )
        p3._require(type(event.get("relaunch_child")) is bool, "Node event relaunch role drifted")
        p3._require(event.get("is_main_thread") is True, "Node worker thread appeared")
        thread_id = event.get("thread_id")
        p3._require(
            isinstance(thread_id, int) and not isinstance(thread_id, bool) and thread_id == 0,
            "Node thread identity drifted",
        )
        events.append(event)
    return events


def _validate_node_topology(
    path: Path,
    *,
    trace: dict[str, Any],
    repository_root: Path,
    canonical_node: Path,
) -> tuple[set[int], dict[str, Any]]:
    events = _read_node_events(path)
    canonical = canonical_node.resolve()
    expected_argv = _expected_argv_sha256(repository_root, path.parent, canonical)
    guarded: Counter[int] = Counter()
    for event in events:
        p3._require(
            Path(event["exec_path"]).resolve() == canonical,
            "Guarded Node executable drifted",
        )
        p3._require(event["argv_sha256"] == expected_argv, "Guarded Node argv drifted")
        guarded[event["pid"]] += 1
    p3._require(set(guarded.values()) == {1}, "Node guard armed a PID more than once")

    traced = trace.get("node_execs")
    p3._require(isinstance(traced, Counter), "Node trace state is missing")
    p3._require(guarded == traced, "Guarded and traced Node PID coverage differs")

    roots = [event for event in events if event["relaunch_child"] is False]
    children = [event for event in events if event["relaunch_child"] is True]
    p3._require(len(roots) == 1, "Node root launcher count drifted")
    p3._require(len(children) == 1, "Node relaunched child count drifted")
    root = roots[0]
    child = children[0]
    p3._require(root["exec_argv_kind"] == "none", "Node root exec argv drifted")
    p3._require(
        child["exec_argv_kind"] in {"none", "auto_memory"},
        "Node child exec argv drifted",
    )
    p3._require(child["ppid"] == root["pid"], "Node child is not a direct root descendant")
    p3._require(root["ppid"] not in guarded, "Node root has another guarded Node parent")
    spawn_parents = trace.get("spawn_parents")
    p3._require(isinstance(spawn_parents, dict), "Node process-parent trace is missing")
    p3._require(
        spawn_parents.get(child["pid"]) == root["pid"],
        "strace did not attest the direct Node launcher edge",
    )
    return set(guarded), {
        "argv_coverage_exact": True,
        "child_exec_argv_kind": child["exec_argv_kind"],
        "direct_launcher_edge": True,
        "guarded_processes": len(guarded),
        "node_processes": EXPECTED_NODE_PROCESSES,
        "root_launchers": 1,
        "traced_processes": len(traced),
    }


def run_gate(
    *,
    work_root: Path,
    p0_receipt: Path,
    expected_head: str,
    output: Path,
    git_executable: Path,
    node_executable: Path,
    npm_executable: Path,
    strace_executable: Path,
) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[1]
    p3._require(
        Path(p32.__file__).resolve()
        == repository_root / "scripts" / "verify_alpha_a1_p3_2_optional_leaf_correction.py",
        "A1-P3.3 imported P3.2 verifier provenance drifted",
    )
    p32_output = output.parent / ".a1-p3-2-receipt.json"
    p3._require(not output.exists(), "A1-P3.3 output already exists")
    p3._require(not p32_output.exists(), "A1-P3.3 temporary receipt already exists")

    original_scope = p32._validate_scope
    original_strace = p3._validate_strace
    original_pid_reader = p3._read_pid_set
    original_guard = p3.NODE_GUARD
    scope_calls = 0
    strace_calls = 0
    node_reader_calls = 0
    python_reader_calls = 0
    trace_state: dict[str, Any] | None = None
    topology_report: dict[str, Any] | None = None

    def scope_adapter(
        repository_root: Path,
        expected_head: str,
        git_executable: Path,
        started_at: float,
    ) -> None:
        nonlocal scope_calls
        scope_calls += 1
        p3._require(scope_calls == 1, "A1-P3.3 scope adapter was called more than once")
        _validate_scope(repository_root, expected_head, git_executable, started_at)

    def strace_adapter(path: Path) -> dict[str, Any]:
        nonlocal strace_calls, trace_state
        strace_calls += 1
        p3._require(strace_calls == 1, "A1-P3.3 strace adapter was called more than once")
        report = original_strace(path)
        trace_state = _parse_strace_topology(path, node_executable)
        return report

    def pid_reader_adapter(path: Path, label: str) -> set[int]:
        nonlocal node_reader_calls, python_reader_calls, topology_report
        if label == "Node guard":
            node_reader_calls += 1
            p3._require(node_reader_calls == 1, "A1-P3.3 Node reader was called more than once")
            p3._require(trace_state is not None, "Node guard was read before strace attestation")
            node_pids, topology_report = _validate_node_topology(
                path,
                trace=trace_state,
                repository_root=repository_root,
                canonical_node=node_executable,
            )
            return node_pids
        if label == "Python guard":
            python_reader_calls += 1
            p3._require(python_reader_calls == 1, "A1-P3.3 Python reader was called more than once")
            return original_pid_reader(path, label)
        raise p3.GateError("A1-P3.3 received an unknown process guard label")

    p32._validate_scope = scope_adapter
    p3._validate_strace = strace_adapter
    p3._read_pid_set = pid_reader_adapter
    p3.NODE_GUARD = NODE_TOPOLOGY_GUARD
    try:
        report = p32.run_gate(
            work_root=work_root,
            p0_receipt=p0_receipt,
            expected_head=expected_head,
            output=p32_output,
            git_executable=git_executable,
            node_executable=node_executable,
            npm_executable=npm_executable,
            strace_executable=strace_executable,
        )
    finally:
        p32._validate_scope = original_scope
        p3._validate_strace = original_strace
        p3._read_pid_set = original_pid_reader
        p3.NODE_GUARD = original_guard

    p3._require(scope_calls == 1, "A1-P3.3 scope adapter call count drifted")
    p3._require(strace_calls == 1, "A1-P3.3 strace adapter call count drifted")
    p3._require(node_reader_calls == 1, "A1-P3.3 Node reader call count drifted")
    p3._require(python_reader_calls == 1, "A1-P3.3 Python reader call count drifted")
    p3._require(topology_report is not None, "A1-P3.3 topology report is missing")
    p3._require(p32_output.is_file(), "A1-P3.3 temporary P3.2 receipt is missing")
    p32_output.unlink()

    prior_correction = p3._mapping(report.get("correction"), "P3.2 correction receipt is missing")
    report["schema_version"] = "evidencemesh.alpha-a1-p3-3-node-topology-attestation-receipt.v1"
    report["correction"] = {
        "classification": "post_host_node_launcher_topology_attestation",
        "corrective_parent_commit": FAILED_P3_2_COMMIT,
        "failed_p3_2_job_id": FAILED_P3_2_JOB_ID,
        "failed_p3_2_run_id": FAILED_P3_2_RUN_ID,
        "historical_run_rerun": False,
        "module_entrypoint": "scripts.verify_alpha_a1_p3_3_node_topology_attestation",
        "node_reader_calls": node_reader_calls,
        "p3_2_install_adapter_calls": prior_correction.get("install_adapter_calls"),
        "python_reader_calls": python_reader_calls,
        "scope_adapter_calls": scope_calls,
        "strace_adapter_calls": strace_calls,
    }
    report["prerequisite"]["failed_a1_p3_2"] = {
        "commit_sha": FAILED_P3_2_COMMIT,
        "conclusion": "failure",
        "failure_reason": "Node guard arming count drifted",
        "host_executed": True,
        "job_id": FAILED_P3_2_JOB_ID,
        "run_id": FAILED_P3_2_RUN_ID,
        "tree_sha": FAILED_P3_2_TREE,
    }
    report["runtime"]["node_topology"] = topology_report
    report["budgets"].update(
        {
            "corrective_workflow_runs": 1,
            "historical_run_reruns": 0,
            "node_processes": EXPECTED_NODE_PROCESSES,
            "workflow_retries": 0,
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    p3._private_file(output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--p0-receipt", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--git", default="git")
    parser.add_argument("--node", default="node")
    parser.add_argument("--npm", default="npm")
    parser.add_argument("--strace", default="strace")
    args = parser.parse_args()
    try:
        run_gate(
            work_root=args.work_root.resolve(),
            p0_receipt=args.p0_receipt.resolve(),
            expected_head=args.expected_head,
            output=args.output.resolve(),
            git_executable=p3._resolve_executable(args.git, "git"),
            node_executable=p3._resolve_executable(args.node, "node"),
            npm_executable=p3._resolve_executable(args.npm, "npm"),
            strace_executable=p3._resolve_executable(args.strace, "strace"),
        )
    except (p3.GateError, OSError, UnicodeError) as exc:
        print(f"Alpha A1-P3.3 FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
