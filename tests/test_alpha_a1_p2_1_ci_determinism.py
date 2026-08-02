from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "alpha" / "alpha_a1_p2_1_ci_determinism_policy_v1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
ENGINE_TESTS = ROOT / "tests" / "test_engine_query_benchmark.py"

P0_HEAD = "d34abe56b95c9daccf361eb86ff1c19421085f62"
P1_HEAD = "b967114a177eec00a7ff5f03bcf1169e04b2faac"
P2_HEAD = "e33fb3bbfe5278ea30fe568847a1caf263de8c4d"
P2_TREE = "3564672ea1bd1ba6ec0edfd2c7a325d3f033b257"


def _section(source: str, start: str, end: str) -> str:
    return source.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]


def test_policy_preserves_exact_a1_p2_evidence_and_zero_live_budget() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["accepted_a1_p2_checkpoint"] == {
        "commit_sha": P2_HEAD,
        "gate_conclusion": "success",
        "gate_decision": "pass",
        "gate_job_id": 91485918959,
        "global_workflow_conclusion": "failure",
        "tree_sha": P2_TREE,
        "workflow_run_id": 30743849354,
    }
    assert policy["entry"] == {
        "branch": "agent/evidencemesh-v0.1",
        "draft_pull_request": 1,
        "parent_commit_sha": P2_HEAD,
        "repository": "VynoDePal/EvidenceMesh",
    }
    assert policy["historical_gate_execution"] == {
        "a1_job_allowed_head_shas": [P0_HEAD, P1_HEAD, P2_HEAD],
        "a1_p2_rerun_required": False,
        "manual_rerun_allowed": False,
        "p2_inspector_head_sha": P2_HEAD,
    }
    budgets = policy["budgets"]
    assert budgets["canonical_ci_runs"] == 1
    assert budgets["commit_publications"] == 1
    assert budgets["manual_ci_reruns"] == 0
    assert budgets["retries"] == 0
    assert budgets["evidencemesh_runtime_network_requests"] == 0
    assert budgets["live_document_requests"] == 0
    assert budgets["live_provider_calls"] == 0
    assert budgets["model_calls"] == 0
    assert budgets["search_calls"] == 0
    assert not any(policy["authority"].values())


def test_policy_freezes_exact_five_path_scope() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["expected_changed_paths"] == [
        ".github/workflows/ci.yml",
        "alpha/alpha_a1_p2_1_ci_determinism_policy_v1.json",
        "docs/alpha-a1-p2-1-ci-determinism-gate-v1.md",
        "tests/test_alpha_a1_p2_1_ci_determinism.py",
        "tests/test_engine_query_benchmark.py",
    ]
    assert policy["correction"] == {
        "engine_behavior_changed": False,
        "private_engine_members_accessed": False,
        "provider_queue_invariant": (
            "provider adapter is not entered while a public fetch holds shared concurrency"
        ),
        "fetch_queue_invariant": (
            "fetch adapter is not entered while a public provider holds shared concurrency"
        ),
        "strategy": "event_synchronized_cross_api_queue_holders",
        "timing_sleep_used_as_oracle": False,
    }


def test_workflow_seals_the_historical_a1_heads() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = _section(
        workflow,
        "  alpha-a1-p0-installability:",
        "\n  container:",
    )

    for head in (P0_HEAD, P1_HEAD, P2_HEAD):
        assert f"github.event.pull_request.head.sha == '{head}'" in job
    assert job.count(f"github.event.pull_request.head.sha == '{P1_HEAD}'") == 2
    assert job.count(f"github.event.pull_request.head.sha == '{P2_HEAD}'") == 3
    assert "github.event.pull_request.head.sha !=" not in job
    assert job.count("verify_alpha_a1_p2_named_host.py") == 1
    assert "upload-artifact" not in job
    assert "secrets." not in job


def test_provider_queue_test_uses_public_event_synchronization() -> None:
    source = ENGINE_TESTS.read_text(encoding="utf-8")
    test_source = _section(
        source,
        "async def test_provider_deadline_includes_concurrency_queue",
        "\n\nclass AcademicOnlyProvider",
    )

    assert "QueueHoldingFetcher" in test_source
    assert "holder.entered.wait()" in test_source
    assert "holder.release.set()" in test_source
    assert "provider.calls == []" in test_source
    assert '"provider_wall_timeout": 1' in test_source
    assert "asyncio.sleep" not in test_source
    assert "_semaphore" not in test_source


def test_fetch_queue_test_uses_public_event_synchronization() -> None:
    source = ENGINE_TESTS.read_text(encoding="utf-8")
    test_source = _section(
        source,
        "async def test_fetch_deadline_includes_concurrency_queue",
        "\n\n@pytest.mark.asyncio\nasync def test_research_and_claim_review",
    )

    assert "QueueHoldingProvider" in test_source
    assert "holder.entered.wait()" in test_source
    assert "holder.release.set()" in test_source
    assert "fetcher.calls == []" in test_source
    assert 'match="total deadline"' in test_source
    assert "asyncio.sleep" not in test_source
    assert "_semaphore" not in test_source
