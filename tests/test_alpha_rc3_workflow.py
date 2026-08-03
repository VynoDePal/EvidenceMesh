from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from evidencemesh.governor import ClosedAlphaPolicy

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/alpha-rc3-governor-protocol-v1.md"
POLICY = ROOT / "alpha/closed_alpha_rc3_governor_policy_v1.json"
WORKFLOW = ROOT / ".github/workflows/alpha-rc3-governor-offline.yml"
RC2_WORKFLOW = ROOT / ".github/workflows/alpha-rc-head.yml"
A0_WORKFLOW = ROOT / ".github/workflows/closed-alpha-a0-preflight.yml"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
LIVE_11_8_8_WORKFLOW = ROOT / ".github/workflows/phase11-8-8-live-projection-calibration.yml"
SNAPSHOT = ROOT / "benchmarks/fixtures/phase11_8_7_engine_rc2.py"

PROTOCOL_SHA256 = "e436fdb3e971e8eda0e0b835268f0b4a65ed7b9e2c48dbfc841e037c0933ff71"
POLICY_SHA256 = "92d7dca1ddb0c091b948b19529ad0eaac8e41fda3aa536b87766e397f56bff8a"
RC2_ENGINE_SHA256 = "8e0d9003ee38c2f776547913ce8ddfeb7d80e334b5eb210e124b78eafdd57795"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_policy_matches_runtime_defaults_and_keeps_live_blocked() -> None:
    policy = json.loads(POLICY.read_bytes())
    assert policy["schema_version"] == "evidencemesh.closed-alpha-rc3-governor-policy.v1"
    assert policy["budget"] == asdict(ClosedAlphaPolicy())
    assert policy["enforcement"] == {
        "automatic_fallbacks_allowed": False,
        "automatic_repairs_allowed": False,
        "automatic_retries_allowed": False,
        "cache_allowed": False,
        "ledger_scope": "single_host_shared_sqlite",
        "permits": "pre_dispatch_single_use",
        "remote_coordinator_implemented": False,
    }
    assert policy["decision"] == {
        "distributed_global_budget_enforcement_ready": False,
        "live_execution_authorized": False,
        "merge_authorized": False,
        "model_or_provider_traffic_authorized": False,
        "public_release_authorized": False,
        "single_host_budget_enforcement_ready": True,
        "tester_contact_authorized": False,
    }
    assert all(value == 0 for value in policy["traffic"].values())


def test_protocol_and_policy_are_hash_locked_and_explicit_about_scope() -> None:
    assert _sha256(PROTOCOL) == PROTOCOL_SHA256
    assert _sha256(POLICY) == POLICY_SHA256
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())
    for marker in (
        "sends no research, provider, Tavily or model request",
        "A rejected batch spends nothing",
        "DDGS is refused before `asyncio.to_thread`",
        "MCP HTTP is refused",
        "a permit refused there is consumed without reaching transport",
        "host monotonic clock",
        "global means all processes sharing one ledger on one host",
        "distributed_global_budget_enforcement_ready=false",
        "zero provider requests and zero model requests",
        "live remains blocked",
    ):
        assert marker in protocol


def test_offline_workflow_is_read_only_secret_free_and_network_isolated() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    lowered = workflow.lower()
    assert "permissions:\n  contents: read\n" in workflow
    assert "workflow_dispatch" not in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-depth: 0" in workflow
    assert "github.event.pull_request.number == 1" in workflow
    assert "github.event.pull_request.head.sha" in workflow
    assert ".github/workflows/ci.yml" in workflow
    assert ".github/workflows/phase11-8-8-live-projection-calibration.yml" in workflow
    assert PROTOCOL_SHA256 in workflow
    assert POLICY_SHA256 in workflow
    assert "/usr/bin/unshare --net" in workflow
    assert "/usr/bin/setpriv" in workflow
    assert "runner_uid=$(id -u)" in workflow
    assert '--reuid="$runner_uid"' in workflow
    assert "--regid=nogroup" in workflow
    assert "runner_gid" not in workflow
    assert '"${run_isolated[@]}" /usr/bin/test ! -w /var/run/docker.sock' in workflow
    assert "--no-new-privs" in workflow
    assert "sudo env -i" in workflow
    assert 'MYPY_CACHE_DIR="$private_root/mypy-cache"' in workflow
    assert 'COVERAGE_FILE="$private_root/.coverage"' in workflow
    assert "-m pytest" in workflow
    assert "--cov=evidencemesh" in workflow
    assert "-m mypy src" in workflow
    assert "-m ruff format --check ." in workflow
    assert "-m ruff check ." in workflow
    assert "-m hatchling build" in workflow
    assert "--target wheel" in workflow
    assert "--target sdist" in workflow
    assert "evidencemesh/governor.py" in workflow
    assert 'sudo find "$private_root/dist"' in workflow
    assert '"$private_root"/dist/*.whl' not in workflow
    for forbidden in (
        "secrets.",
        "github.token",
        "upload-artifact",
        "actions/attest",
        "curl ",
        "wget ",
        "gh release",
        "tavily_api_key",
        "gemini_api_key",
    ):
        assert forbidden not in lowered
    action_lines = [line.strip() for line in workflow.splitlines() if "uses:" in line]
    assert action_lines
    assert all(
        "@" in line and not line.rsplit("@", 1)[1].split()[0].startswith("v")
        for line in action_lines
    )


def test_generic_ci_external_searxng_job_is_skipped_for_exact_alpha_pr() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "searxng-integration:" in workflow
    assert "github.event.pull_request.number != 1" in workflow
    assert "github.event.pull_request.head.repo.full_name != 'VynoDePal/EvidenceMesh'" in workflow
    assert "github.event.pull_request.head.ref != 'agent/evidencemesh-v0.1'" in workflow


def test_historical_live_lock_reproduces_rc2_without_authorizing_live() -> None:
    workflow = LIVE_11_8_8_WORKFLOW.read_text(encoding="utf-8")
    assert "HISTORICAL_RC2_SHA: 81b5f8a8abd4302b27ad123bd5505e1757eadc7f" in workflow
    assert "fetch-depth: 0" in workflow
    assert 'git worktree add --detach "$historical_root" "$HISTORICAL_RC2_SHA"' in workflow
    assert 'PYTHONPATH="$historical_root/src:$historical_root" "$current_python"' in workflow
    assert "github.event.before == 'd91f8a85f6e2770ecd83ca95cbc7112803d683cb'" in workflow


def test_historical_rc2_and_a0_workflows_are_retired_or_frozen() -> None:
    rc2 = RC2_WORKFLOW.read_text(encoding="utf-8")
    a0 = A0_WORKFLOW.read_text(encoding="utf-8")
    rc2_sha = "81b5f8a8abd4302b27ad123bd5505e1757eadc7f"
    a0_sha = "540eca26ffb97908320a5ecea5f1bf3fb4f0247a"
    assert f"EXPECTED_SHA: {rc2_sha}" in rc2
    assert f"github.sha == '{rc2_sha}'" in rc2
    assert f"A0_SHA: {a0_sha}" in a0
    assert 'git merge-base --is-ancestor "$A0_SHA" HEAD' in a0
    assert 'git diff --quiet "$A0_SHA" HEAD -- "${immutable_artifacts[@]}"' in a0
    assert _sha256(SNAPSHOT) == RC2_ENGINE_SHA256
