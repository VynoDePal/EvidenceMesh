from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from scripts import verify_alpha_a1_p0_installability as gate

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "alpha" / "alpha_a1_p0_installability_policy_v1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CURRENT_ALPHA_SOURCE_COMMIT = "41e0d18e1801cbde0bae61dfd85877fddbc64e4d"


def test_gate_pins_exact_public_candidate_and_budgets() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert gate.REPOSITORY_URL == "https://github.com/VynoDePal/EvidenceMesh.git"
    assert gate.BRANCH == "agent/evidencemesh-v0.1"
    assert gate.SOURCE_COMMIT == "145f5f923825ffeaeb485bd680bc79410ab290d1"
    assert gate.SOURCE_TREE == "3b36c2d3970a5e3c325a2b20260daabf23d33a29"
    assert gate.EXPECTED_VERSION == "0.1.0"
    assert gate.MAXIMUM_ELAPSED_SECONDS == 900
    assert gate.INSTALL_ATTEMPTS_MAX == 1
    assert policy["candidate"] == {
        "branch": gate.BRANCH,
        "commit_sha": gate.SOURCE_COMMIT,
        "repository": "VynoDePal/EvidenceMesh",
        "tree_sha": gate.SOURCE_TREE,
    }
    assert policy["budgets"] == {
        "document_requests": 0,
        "install_attempts": 1,
        "maximum_elapsed_seconds": 900,
        "model_calls": 0,
        "provider_calls": 0,
        "public_clone_attempts": 1,
        "retries": 0,
        "runtime_network_requests": 0,
    }
    assert not any(policy["authority"].values())


def test_runner_has_one_fail_closed_locked_install_plan() -> None:
    source = (ROOT / "scripts" / "verify_alpha_a1_p0_installability.py").read_text(encoding="utf-8")

    assert source.count('"sync",') == 1
    assert '"--locked"' in source
    assert '"--frozen"' not in source
    assert '"--no-dev"' in source
    assert '"--no-editable"' in source
    assert '"--no-cache"' in source
    assert '"--no-python-downloads"' in source
    assert '"--no-config"' in source
    assert "uv run" not in source
    assert '"UV_HTTP_RETRIES": "0"' in source
    assert '"UV_PROJECT_ENVIRONMENT"' in source
    assert '"merge-base", "--is-ancestor"' in source
    assert '"checkout", "--detach", SOURCE_COMMIT' in source


def test_acquisition_environment_does_not_inherit_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-propagate")
    monkeypatch.setenv("PIP_INDEX_URL", "https://credential.invalid/simple")

    env = gate._acquisition_environment(tmp_path)

    assert "GITHUB_TOKEN" not in env
    assert "PIP_INDEX_URL" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["UV_HTTP_RETRIES"] == "0"
    assert env["UV_NO_PYTHON_DOWNLOADS"] == "1"


def test_runtime_environment_is_explicit_readonly_and_guarded(tmp_path: Path) -> None:
    venv = tmp_path / "candidate" / ".venv"
    env, home, network_log = gate._runtime_environment(tmp_path, venv)

    assert stat.S_IMODE(home.stat().st_mode) == 0o555
    assert list(home.iterdir()) == []
    assert Path(env["EVIDENCEMESH_CACHE_PATH"]).is_relative_to(tmp_path / "runtime" / "state")
    assert not Path(env["EVIDENCEMESH_CACHE_PATH"]).is_relative_to(home)
    assert env["EVIDENCEMESH_PROVIDERS"] == "wikipedia"
    assert env["FASTMCP_CHECK_FOR_UPDATES"] == "off"
    assert env["FASTMCP_SHOW_SERVER_BANNER"] == "false"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["EVIDENCEMESH_NETWORK_GUARD_LOG"] == str(network_log.resolve())
    guard = Path(env["PYTHONPATH"]) / "sitecustomize.py"
    guard_source = guard.read_text(encoding="utf-8")
    assert "socket.socket.connect = _connect" in guard_source
    assert "socket.create_connection = _create_connection" in guard_source
    assert "socket.getaddrinfo = _getaddrinfo" in guard_source


def test_installed_package_probe_requires_noneditable_exact_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    venv = source / ".venv"
    origin = venv / "lib" / "python3.11" / "site-packages" / "evidencemesh"
    (venv / "bin").mkdir(parents=True)
    origin.mkdir(parents=True)
    for executable in gate.EXPECTED_ENTRY_POINTS:
        launcher = venv / "bin" / executable
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
    payload = {
        "base_prefix": "/opt/python",
        "data_hashes": gate.EXPECTED_PACKAGE_DATA,
        "direct_url": {"url": source.resolve().as_uri(), "dir_info": {}},
        "direct_url_present": True,
        "entry_points": gate.EXPECTED_ENTRY_POINTS,
        "package_origin": str(origin),
        "prefix": str(venv),
        "python_version": [3, 11, 15],
        "version": "0.1.0",
    }

    gate._validate_package_probe(payload, source, venv)
    payload["direct_url"] = {"url": (tmp_path / "other").resolve().as_uri(), "dir_info": {}}
    with pytest.raises(gate.GateError, match="cloned source"):
        gate._validate_package_probe(payload, source, venv)
    payload["direct_url"] = {"url": source.resolve().as_uri(), "dir_info": {"editable": True}}
    with pytest.raises(gate.GateError, match="editable"):
        gate._validate_package_probe(payload, source, venv)


def test_cli_benchmark_and_mcp_validators_fail_closed() -> None:
    providers = {
        "status": "ready",
        "version": "0.1.0",
        "providers": [{"name": "wikipedia"}],
        "configuration_warnings": [],
        "safety": {"private_networks_allowed": False, "dns_pinning": True},
    }
    benchmark = {
        "benchmark": "EvidenceMesh offline federation benchmark",
        "fixture_version": 1,
        "case_count": 12,
        "fused": {
            "hit_at_1": 1.0,
            "hit_at_5": 1.0,
            "mrr_at_10": 1.0,
            "ndcg_at_10": 1.0,
            "duplicate_rate": 0.0,
        },
    }
    mcp = {
        "validation": {"errors": [], "passed": True},
        "contract": {
            "tools": gate.EXPECTED_TOOLS,
            "resources": ["evidencemesh://research-guide"],
            "prompts": ["evidence_first_research"],
            "health_status": "ready",
            "configured_providers": ["wikipedia"],
        },
        "traffic": {
            "mcp_tool_calls": 1,
            "model_requests": 0,
            "provider_http_requests": 0,
            "provider_search_calls": 0,
        },
    }

    gate._validate_providers(providers)
    gate._validate_benchmark(benchmark)
    gate._validate_mcp(mcp)
    benchmark["case_count"] = 11
    with pytest.raises(gate.GateError, match="case count"):
        gate._validate_benchmark(benchmark)


def test_ci_runs_one_canonical_gate_without_publication() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow.split("  alpha-a1-p0-installability:", maxsplit=1)[1].split(
        "\n  container:", maxsplit=1
    )[0]

    assert workflow.count("alpha-a1-p0-installability:") == 1
    assert "name: Alpha A1-P0 installability" in job
    assert "github.event.pull_request.number == 1" in job
    assert "github.event.pull_request.draft == true" in job
    assert "github.event.pull_request.head.ref == 'agent/evidencemesh-v0.1'" in job
    assert "runs-on: ubuntu-24.04" in job
    assert "timeout-minutes: 18" in job
    assert "persist-credentials: false" in job
    assert 'version: "0.11.33"' in job
    assert "enable-cache: false" in job
    assert job.count("verify_alpha_a1_p0_installability.py") == 1
    assert "upload-artifact" not in job
    assert "secrets." not in job
    assert "release" not in job.lower()
    assert "git tag" not in job


def test_quick_start_is_pinned_offline_and_platform_honest() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start", maxsplit=1)[1].split("## MCP setup", maxsplit=1)[0]
    normalized_quick_start = " ".join(quick_start.split())

    assert gate.BRANCH in quick_start
    assert gate.SOURCE_COMMIT != CURRENT_ALPHA_SOURCE_COMMIT
    assert gate.SOURCE_COMMIT not in quick_start
    assert quick_start.count(f"ALPHA_SHA={CURRENT_ALPHA_SOURCE_COMMIT}") == 1
    assert "uv sync --locked --no-dev --no-editable --python 3.11" in quick_start
    assert "EVIDENCEMESH_CACHE_PATH" in quick_start
    assert ".venv/bin/evidencemesh providers" in quick_start
    assert ".venv/bin/evidencemesh benchmark-offline" in quick_start
    assert "automated Ubuntu 24.04/Python 3.11 simulation" in normalized_quick_start
    assert "macOS has not been validated" in normalized_quick_start
    assert "native windows is not supported" in normalized_quick_start.lower()
    assert quick_start.index("benchmark-offline") < quick_start.index("docker compose")
