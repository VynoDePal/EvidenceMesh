from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/phase11-8-8-live-projection-calibration.yml"
HISTORY_STEP = "      - name: Fail closed if an authorization-shaped run already exists"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def history_guard_namespace() -> dict[str, Any]:
    history_section = workflow_text().split(HISTORY_STEP, 1)[1]
    match = re.search(
        r"        run: \|\n"
        r"          python - <<'PY'\n"
        r"(?P<source>.*?)"
        r"\n          PY",
        history_section,
        flags=re.DOTALL,
    )
    assert match is not None
    source = textwrap.dedent(match.group("source"))
    namespace: dict[str, Any] = {
        "__name__": "phase11_8_8_history_guard_test",
    }
    exec(compile(source, str(WORKFLOW), "exec"), namespace)  # noqa: S102
    return namespace


def test_live_workflow_has_no_dispatch_target_or_label_trigger() -> None:
    text = workflow_text()

    assert "workflow_dispatch" not in text
    assert "pull_request_target" not in text
    assert "labeled" not in text
    assert "github.event.action == 'synchronize'" in text


def test_live_workflow_requires_the_exact_one_shot_marker_commit() -> None:
    text = workflow_text()

    assert "github.run_attempt == 1" in text
    assert "github.event.pull_request.number == 1" in text
    assert "github.event.pull_request.head.repo.full_name == github.repository" in text
    assert "github.event.pull_request.head.ref == 'agent/evidencemesh-v0.1'" in text
    assert "github.event.before == '__FROZEN_LOCK_COMMIT_SHA__'" in text or re.search(
        r"github\.event\.before == '[0-9a-f]{40}'",
        text,
    )
    assert (".github/authorizations/phase11-8-8-live-projection-calibration-once.json") in text
    assert "chore(benchmarks): authorize Phase 11.8.8 live once" in text
    assert "assert sorted(changed) == sorted((workflow_path, marker_path))" in text
    assert '"maximum_tavily_requests": 24' in text
    assert '"maximum_model_requests": 0' in text
    assert '"retry_policy": "none"' in text
    assert '"fallback_policy": "none"' in text
    assert '"repair_policy": "none"' in text
    assert '"one_shot": True' in text
    assert '"rerun_policy": "forbidden"' in text


def test_live_workflow_is_read_only_and_binds_only_the_tavily_secret() -> None:
    text = workflow_text()
    secret_references = re.findall(r"secrets\.([A-Z0-9_]+)", text)
    authorization_job = text.split("  one-shot-authorization:", 1)[1].split(
        "\n  live-projection-calibration:",
        1,
    )[0]

    assert "permissions:\n  contents: read" in text
    assert "    permissions:\n      actions: read\n      contents: read" in authorization_job
    assert "actions: write" not in text
    assert secret_references == ["EVIDENCE_MESH_TAVILY_KEY"]
    assert text.count("TAVILY_API_KEY: ${{ secrets.EVIDENCE_MESH_TAVILY_KEY }}") == 1
    assert "secrets." not in authorization_job
    assert authorization_job.count("GITHUB_TOKEN: ${{ github.token }}") == 1
    assert "EVIDENCE_MESH_GEMINI_KEY" not in text
    assert "GEMINI_API_KEY" not in text
    assert "gemini-" not in text.lower()


def test_live_workflow_checks_complete_actions_history_before_secret_use() -> None:
    text = workflow_text()
    history_position = text.index(HISTORY_STEP)
    secret_position = text.index("TAVILY_API_KEY: ${{ secrets.EVIDENCE_MESH_TAVILY_KEY }}")

    assert history_position < secret_position
    assert "/actions/workflows/" in text
    assert "/git/commits/" in text
    assert '"per_page": str(PAGE_SIZE)' in text
    assert "workflow-run history changed during pagination" in text
    assert "workflow-run history is incomplete" in text
    assert "current run is absent from GitHub Actions history" in text
    assert "if run_id == current_run_id:" in text
    assert "one-shot authorization was already consumed" in text
    assert "no_prior_authorization_run_verified: ${" in text
    assert '"no_prior_authorization_run_verified": True' in text


def test_history_guard_detects_b1_when_current_authorization_is_recreated_b2() -> None:
    namespace = history_guard_namespace()
    find_prior = namespace["find_prior_authorization_run_ids"]
    subject = namespace["AUTHORIZATION_SUBJECT"]
    commit_a = "a" * 40
    commit_b1 = "b" * 40
    commit_b2 = "c" * 40
    commits = {
        commit_b1: {
            "sha": commit_b1,
            "message": f"{subject}\n\nfirst authorization",
            "parents": [{"sha": commit_a}],
        },
        commit_b2: {
            "sha": commit_b2,
            "message": subject,
            "parents": [{"sha": commit_a}],
        },
    }

    first_run = [{"id": 101, "head_sha": commit_b1}]
    assert (
        find_prior(
            first_run,
            current_run_id=101,
            frozen_lock_commit=commit_a,
            load_commit=commits.__getitem__,
        )
        == ()
    )

    recreated_run = [
        {"id": 202, "head_sha": commit_b2},
        {"id": 150, "head_sha": commit_a},
        {"id": 101, "head_sha": commit_b1},
    ]
    commits[commit_a] = {
        "sha": commit_a,
        "message": "chore: restore the frozen lock",
        "parents": [{"sha": "d" * 40}],
    }
    assert find_prior(
        recreated_run,
        current_run_id=202,
        frozen_lock_commit=commit_a,
        load_commit=commits.__getitem__,
    ) == (101,)


def test_history_guard_requires_exact_subject_parent_and_current_run_witness() -> None:
    namespace = history_guard_namespace()
    find_prior = namespace["find_prior_authorization_run_ids"]
    error = namespace["HistoryVerificationError"]
    subject = namespace["AUTHORIZATION_SUBJECT"]
    commit_a = "a" * 40
    different_subject = "d" * 40
    merge_commit = "e" * 40
    commits = {
        different_subject: {
            "sha": different_subject,
            "message": f"{subject} again",
            "parents": [{"sha": commit_a}],
        },
        merge_commit: {
            "sha": merge_commit,
            "message": subject,
            "parents": [{"sha": commit_a}, {"sha": "f" * 40}],
        },
    }
    runs = [
        {"id": 303, "head_sha": "c" * 40},
        {"id": 302, "head_sha": merge_commit},
        {"id": 301, "head_sha": different_subject},
    ]
    assert (
        find_prior(
            runs,
            current_run_id=303,
            frozen_lock_commit=commit_a,
            load_commit=commits.__getitem__,
        )
        == ()
    )

    try:
        find_prior(
            runs[1:],
            current_run_id=303,
            frozen_lock_commit=commit_a,
            load_commit=commits.__getitem__,
        )
    except error as exc:
        assert "current run is absent" in str(exc)
    else:
        raise AssertionError("missing current-run history did not fail closed")


def test_live_workflow_pins_actions_source_and_frozen_checkout() -> None:
    text = workflow_text()

    action_uses = re.findall(r"uses: ([^\s#]+)", text)
    assert action_uses
    assert all(re.search(r"@[0-9a-f]{40}$", item) for item in action_uses)
    assert (
        "https://openaipublic.blob.core.windows.net/simple-evals/simple_qa_test_set.csv"
    ) in text
    assert "feee3f7e7db3617e94e8fcf1977b756ec420ef8568f4e0fcbbe0e92e9d5fc032" in text
    assert "ref: __FROZEN_LOCK_COMMIT_SHA__" in text or re.search(
        r"ref: [0-9a-f]{40}",
        text,
    )


def test_live_workflow_caps_traffic_and_keeps_quality_nonfatal() -> None:
    text = workflow_text()

    assert "benchmarks/run_phase11_8_8_live_projection_calibration.py" in text
    assert "phase11_8_8_live_projection_dependency_locks_v1.json" in text
    assert "--authorization-verified" in text
    assert "--authorization-attestation" in text
    assert 'traffic["logical_operations_planned"] == 24' in text
    assert 'traffic["tavily_http_attempts_maximum"] == 24' in text
    assert 'traffic["retries"] == 0' in text
    assert 'traffic["fallback_requests"] == 0' in text
    assert 'traffic["repair_requests"] == 0' in text
    assert '"passed": True' in text
    assert 'decision["projection_candidate_passed"], bool' in text
    assert 'decision["projection_candidate_passed"] is True' not in text


def test_aborted_provider_failure_validates_completed_cases_then_reaches_upload() -> None:
    text = workflow_text()
    validation_start = text.index("      - name: Validate privacy, traffic and decision boundaries")
    upload_start = text.index("      - name: Prepare an exact one-file public artifact")
    validation = text[validation_start:upload_start]

    assert 'if report["run_status"] == "aborted_provider_failure":' in validation
    assert 'scored = projection["scored_case_count"]' in validation
    assert "assert scored == logical_completed" in validation
    assert "assert scored == logical_started" not in validation
    assert "exit 1" not in validation
    assert validation_start < upload_start


def test_live_workflow_validates_only_aggregate_public_results() -> None:
    text = workflow_text()

    assert 'suite["case_ids"]' not in text
    assert '"projection_outcomes"' not in text
    assert '"outcomes"' not in text
    assert 'decision["gate_count"] == 13' in text
    assert '"public_privacy_and_governance_boundaries"' in text


def test_live_workflow_uploads_exactly_one_public_file() -> None:
    text = workflow_text()

    assert "Prepare an exact one-file public artifact" in text
    assert 'find "$ARTIFACT_DIR" -mindepth 1 -maxdepth 1 -type f' in text
    assert 'find "$ARTIFACT_DIR" -mindepth 1 -maxdepth 1 | wc -l' in text
    assert text.count("actions/upload-artifact@") == 1
