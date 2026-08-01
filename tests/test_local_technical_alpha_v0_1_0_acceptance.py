from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).parents[1]
ACCEPTANCE = ROOT / "alpha/local_technical_alpha_v0_1_0_acceptance_v1.json"
PROTOCOL = ROOT / "docs/local-technical-alpha-v0.1.0-acceptance-protocol-v1.md"
WHEEL_REPORT = ROOT / "alpha/local_technical_alpha_v0_1_0_wheel_smoke_v1.json"
SDIST_REPORT = ROOT / "alpha/local_technical_alpha_v0_1_0_sdist_smoke_v1.json"
PROJECTION = ROOT / "alpha/local_technical_alpha_v0_1_0_public_projection_v1.json"

HISTORICAL_RELOCATIONS = {
    ".github/workflows/alpha-rc4-1a-provider-policy-session-fail-closed-offline.yml": (
        "docs/workflow-archive/alpha-rc4-1a-provider-policy-session-fail-closed-offline.yml"
    )
}

TAG = "v0.1.0-alpha.local"
TAG_OBJECT = "196cfaca0458f81d4d5cd7de54f7adbf80ad1e57"
CANDIDATE_SHA = "644064b5fa097bbf7055f3bf4335ea613afb6387"
CANDIDATE_TREE = "7a774664442caa9201b419fb219d47c6113a52a3"
CANDIDATE_PARENT = "61a58660cb77ba160e8ecfed53d09fdcd1d60c57"
PUBLIC_SOURCE_SHA = "8026ace0f8c48abf9f9a5664d31d1e9cc66bdf2e"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(ACCEPTANCE.read_bytes()))


def _git(*args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git executable and test arguments.
        ["/usr/bin/git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_succeeds(*args: str) -> bool:
    completed = subprocess.run(  # noqa: S603 - fixed git executable and test arguments.
        ["/usr/bin/git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def test_acceptance_binds_exact_annotated_tag_commit_tree_and_parent() -> None:
    record = _record()
    candidate = record["candidate"]

    assert record["schema_version"] == ("evidencemesh.local-technical-alpha-v0.1.0-acceptance.v1")
    assert record["acceptance"] == {
        "decision": "go",
        "package_version": "0.1.0",
        "scope": "single_host_local_offline_technical_alpha_only",
        "scored": False,
        "status": "accepted",
    }
    assert candidate == {
        "commit_sha": CANDIDATE_SHA,
        "current_head_is_candidate": False,
        "parent_sha": CANDIDATE_PARENT,
        "repository": "VynoDePal/EvidenceMesh",
        "source_date_epoch": 1785577726,
        "tag_annotated": True,
        "tag_name": TAG,
        "tag_object_sha": TAG_OBJECT,
        "tag_signed": False,
        "tree_sha": CANDIDATE_TREE,
    }
    tag_ref = f"refs/tags/{TAG}"
    if _git_succeeds("show-ref", "--verify", "--quiet", tag_ref):
        assert _git("rev-parse", tag_ref) == TAG_OBJECT
        assert _git("rev-parse", f"{tag_ref}^{{}}") == CANDIDATE_SHA
        assert _git("rev-parse", f"{tag_ref}^{{}}^{{tree}}") == CANDIDATE_TREE
        assert _git("rev-parse", f"{tag_ref}^{{}}^") == CANDIDATE_PARENT
    else:
        projection = json.loads(PROJECTION.read_bytes())
        assert projection["local_acceptance"]["local_identity_resolution_required_in_ci"] is False


def test_every_immutable_input_digest_matches() -> None:
    for relative_path, expected in _record()["immutable_inputs"].items():
        current_path = HISTORICAL_RELOCATIONS.get(relative_path, relative_path)
        assert _sha256(ROOT / current_path) == expected, relative_path


def test_reproducible_distribution_subjects_are_exact() -> None:
    distributions = _record()["distributions"]

    assert distributions["reproducible_build_count"] == 2
    assert distributions["source_date_epoch"] == 1785577726
    assert distributions["subjects"] == {
        "dist/evidencemesh-0.1.0-py3-none-any.whl": {
            "sha256": "857d9f363b76a77000506ac17084c49fa553f76ff881fcb0646c975058af7313",
            "size_bytes": 118395,
        },
        "dist/evidencemesh-0.1.0.tar.gz": {
            "sha256": "6da7a48b8374f7b19fcac00e316ab3f3d279babb25e799060d103b9107210840",
            "size_bytes": 1241308,
        },
    }


def test_installed_reports_bind_runtime_and_expose_installer_hash_gap() -> None:
    record = _record()
    reports = record["smoke_reports"]
    harness = ROOT / reports["harness"]["path"]
    assert reports["harness"]["sha256"] == _sha256(harness)
    loaded = {
        "wheel": json.loads(WHEEL_REPORT.read_bytes()),
        "sdist": json.loads(SDIST_REPORT.read_bytes()),
    }

    for label, path in (("wheel", WHEEL_REPORT), ("sdist", SDIST_REPORT)):
        assert _sha256(path) == reports[label]["sha256"]
        assert path.stat().st_size == reports[label]["size_bytes"]
        report = loaded[label]
        assert report["label"] == label
        assert report["validation"] == {"errors": [], "passed": True}
        assert report["installation"] == {
            "distribution_module_samefile": True,
            "entry_points_exact": True,
            "launchers_exact": True,
            "package_origin_within_isolated_prefix": True,
            "package_version": "0.1.0",
            "virtual_environment": True,
        }
        archive = report["source_archive"]
        assert archive["critical_package_files"] == {
            "archive_record_installed_match": True,
            "critical_file_count": 6,
        }
        assert archive["independent_sha256_after_install_matches"] is True
        assert archive["install_to_smoke_toctou_excluded"] is False
        assert archive["pep610"] == {
            "binding_scope": "url_only",
            "sha256_status": "not_declared_by_installer",
            "url_matches": True,
        }
        assert report["network_guard"] == {
            "binding_probe_markers_verified": 3,
            "dependency_update_checks_disabled": True,
            "implementation": "sitecustomize_python_socket_guard_v1",
            "network_access_observed": False,
            "os_network_namespace_enforced": False,
            "product_markers_verified": 3,
            "scope": "python_socket_api_only_not_os_network_namespace",
        }
        assert all(type(value) is int and value == 0 for value in report["traffic"].values())


def test_smokes_bind_exact_rc4_control_cli_and_mcp_contract() -> None:
    expected_providers = ["arxiv", "crossref", "github", "searxng", "wikipedia"]
    expected_tools = [
        "search_web",
        "deep_research",
        "fetch_url",
        "batch_search",
        "verify_claim",
        "health",
    ]

    for path in (WHEEL_REPORT, SDIST_REPORT):
        report = json.loads(path.read_bytes())
        assert report["control_plane"] == {
            "admitted_slots": {"community": 6, "quality": 2},
            "binding_probe_subprocess_count": 3,
            "distinct_ledgers": True,
            "distinct_sessions": True,
            "fixture_count": 3,
            "implementation": "SQLiteAlphaControlPlane",
            "prepared_before_subprocess": True,
            "product_subprocess_count": 3,
            "profile": "community",
        }
        assert report["cli"]["configured_providers"] == expected_providers
        assert report["cli"]["http_transport"]["refused"] is True
        assert report["mcp_stdio"]["configured_providers"] == expected_providers
        assert report["mcp_stdio"]["health_status"] == "ready"
        assert report["mcp_stdio"]["tool_inventory"] == expected_tools
        assert report["mcp_stdio"]["resource_inventory"] == ["evidencemesh://research-guide"]
        assert report["mcp_stdio"]["prompt_inventory"] == ["evidence_first_research"]
        for control in (
            report["cli"]["providers_command"]["control_plane"],
            report["cli"]["http_transport"]["control_plane"],
            report["mcp_stdio"]["control_plane"],
        ):
            assert control["schema_version"] == "evidencemesh.closed-alpha-control-plane.v2"
            assert control["state"] == "prepared"
            assert control["admitted_participants"] == 8
            assert control["sessions"] == 0
            assert control["global_attempts"] == 0
            assert control["privacy_fault"] is False
        for probe in (
            report["cli"]["providers_command"]["binding_probe"],
            report["cli"]["http_transport"]["binding_probe"],
            report["mcp_stdio"]["binding_probe"],
        ):
            assert probe["governor_environment_match"] is True
            assert probe["settings_environment_match"] is True
            assert probe["network_guard"]["network_access_observed"] is False


def test_engineering_gates_and_zero_request_budget_are_exact() -> None:
    record = _record()
    verification = record["verification"]

    assert verification == {
        "branch_coverage_percent": 87,
        "branch_coverage_required_percent": 85,
        "candidate_files_formatted": 225,
        "clean_tag_exports_built": 2,
        "dependency_acquisition_before_offline_window_performed": True,
        "focused_rc4_tests_passed": 99,
        "full_candidate_tests_passed": 885,
        "installed_smoke_critical_files_bound": 6,
        "installed_smoke_dependency_update_checks_disabled": True,
        "installed_smoke_guarded_subprocesses_per_distribution": 6,
        "installed_smoke_python_socket_access_observed": False,
        "installed_sdist_smoke_passed": True,
        "installed_wheel_smoke_passed": True,
        "mypy_source_files_passed": 38,
        "offline_build_and_smoke_network_access_performed": False,
        "research_network_access_performed": False,
        "ruff_format_passed": True,
        "ruff_lint_passed": True,
        "seal_head_files_formatted": 252,
        "seal_head_mypy_source_files_passed": 39,
        "seal_head_tests_passed": 985,
        "validation_date": "2026-08-01",
    }
    assert (
        verification["branch_coverage_percent"]
        >= (verification["branch_coverage_required_percent"])
    )
    assert all(type(value) is int and value == 0 for value in record["request_budget"].values())


def test_external_silence_and_downstream_boundaries_remain_closed() -> None:
    record = _record()
    external = record["external_benchmarks"]

    assert external == {
        "bright": "blocked_unadmitted",
        "browsecomp_plus": "blocked_unadmitted",
        "response_required_for_local_acceptance": False,
        "response_state_ingested": False,
        "silence_forever_preserves_acceptance": True,
    }
    assert not any(record["downstream_authority"].values())
    assert record["limitations"] == {
        "complete_git_history_verified": False,
        "continuous_retention_supervisor_present": False,
        "install_to_smoke_toctou_excluded": False,
        "os_network_namespace_enforced": False,
        "pep610_archive_sha256_declared_by_installer": False,
        "public_provenance_established": False,
        "python_socket_guard_scope": "python_socket_api_only_not_os_network_namespace",
        "tag_signed": False,
    }


def test_synthetic_identity_record_is_explicitly_not_acceptance_evidence() -> None:
    excluded = _record()["excluded_evidence"]["rc4_1a_synthetic_identity_record"]

    assert excluded == {
        "acceptance_evidence": False,
        "attestation_ids_real": False,
        "sha256": "69cc7de538067358506be5af7bb9dc81bb71bc4bb5416666e9303f562deb3d4d",
        "scope": "rc4_1a_offline_wheel_smoke_only",
    }


def test_protocol_and_seal_state_are_narrow_and_honest() -> None:
    record = _record()
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())

    for marker in (
        "local-only technical alpha",
        "pending forever",
        "hard stop for closed-alpha adoption",
        "did not permit creation of a separate empty network namespace",
        "private `sitecustomize` guard",
        "exact PEP 610 source-archive URL but no archive SHA-256",
        "Provider or search requests | 0",
        "Stop without retry",
        "non-runtime commit containing that record",
    ):
        assert marker in protocol
    assert record["seal"] == {
        "candidate_tag_moved": False,
        "completed": True,
        "public_attestation_created": False,
        "runtime_source_changed_after_candidate": False,
        "distributions_published": False,
        "seal_commit_identity": "the commit containing this record",
    }
    assert _git("rev-parse", f"{PUBLIC_SOURCE_SHA}^{{tree}}") == CANDIDATE_TREE
    assert _git_succeeds("merge-base", "--is-ancestor", PUBLIC_SOURCE_SHA, "HEAD")
    assert (
        _git(
            "diff",
            "--name-only",
            PUBLIC_SOURCE_SHA,
            "HEAD",
            "--",
            "src",
            "pyproject.toml",
            "uv.lock",
        )
        == ""
    )
