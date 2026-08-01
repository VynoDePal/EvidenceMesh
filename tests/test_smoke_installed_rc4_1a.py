from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import smoke_installed_rc4_1a as smoke


def _arm_guard(environment: dict[str, str]) -> None:
    marker = Path(environment[smoke._NETWORK_GUARD_MARKER])
    marker.write_bytes(smoke._NETWORK_GUARD_ARMED)
    marker.chmod(0o600)


def _probe_receipt() -> dict[str, Any]:
    return {
        "governor_environment_match": True,
        "settings_environment_match": True,
        "network_guard": {"loaded": True},
    }


def _health() -> dict[str, Any]:
    return {
        "status": "ready",
        "version": "0.1.0",
        "deployment_profile": "community",
        "providers": [{"name": name} for name in smoke.COMMUNITY_PROVIDERS],
        "reliability": {
            "closed_alpha_governor": {
                "enabled": True,
                "scope": "single_host_shared_sqlite",
                "distributed_global_guarantee": False,
            }
        },
        "safety": {
            "private_networks_allowed": False,
            "dns_pinning": True,
        },
    }


def test_bootstrap_prepares_full_cohort_and_unique_strict_environments(tmp_path: Path) -> None:
    first = smoke._bootstrap_subprocess_environment(
        tmp_path / "first",
        identity_index=1,
        purpose="first",
    )
    second = smoke._bootstrap_subprocess_environment(
        tmp_path / "second",
        identity_index=2,
        purpose="second",
    )

    assert first.ledger != second.ledger
    assert first.session_code != second.session_code
    assert first.environment["EVIDENCEMESH_CLOSED_ALPHA_CONTROL_PLANE"] == "rc4"
    assert first.environment["EVIDENCEMESH_DEPLOYMENT_PROFILE"] == "community"
    assert first.environment["EVIDENCEMESH_PROVIDERS"].split(",") == (smoke.COMMUNITY_PROVIDERS)
    assert not any(
        name in first.environment
        for name in ("GITHUB_TOKEN", "TAVILY_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")
    )
    for fixture in (first, second):
        receipt = smoke._control_plane_receipt(fixture)
        assert receipt["state"] == "prepared"
        assert receipt["control_epoch"] == 2
        assert receipt["admitted_participants"] == 8
        assert receipt["sessions"] == 0
        assert receipt["global_attempts"] == 0
        assert receipt["ledger_directory_mode"] == "0700"
        assert receipt["ledger_file_mode"] == "0600"


def test_sitecustomize_guard_source_compiles_and_arms_marker(tmp_path: Path) -> None:
    compile(smoke._NETWORK_GUARD_SOURCE, "sitecustomize.py", "exec")
    fixture = smoke._bootstrap_subprocess_environment(
        tmp_path / "fixture",
        identity_index=1,
        purpose="guard-arm",
    )
    guarded = smoke._guarded_environment(fixture, purpose="guard-arm")

    completed = subprocess.run(
        [sys.executable, "-c", "pass"],
        cwd=fixture.ledger.parent,
        env=guarded.environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert guarded.marker.read_bytes() == smoke._NETWORK_GUARD_ARMED
    assert smoke._verify_network_guard(guarded.marker)["loaded"] is True


def test_sitecustomize_guard_blocks_af_inet_and_marks_attempt(tmp_path: Path) -> None:
    fixture = smoke._bootstrap_subprocess_environment(
        tmp_path / "fixture",
        identity_index=1,
        purpose="guard-block",
    )
    guarded = smoke._guarded_environment(fixture, purpose="guard-block")

    completed = subprocess.run(
        [sys.executable, "-c", "import socket; socket.getaddrinfo('localhost', 80)"],
        cwd=fixture.ledger.parent,
        env=guarded.environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert guarded.marker.read_bytes().startswith(smoke._NETWORK_GUARD_BLOCKED)
    with pytest.raises(RuntimeError, match="observed network access"):
        smoke._verify_network_guard(guarded.marker)


def test_health_rejects_wrong_package_version() -> None:
    health = _health()
    health["version"] = "0.1.1"

    with pytest.raises(RuntimeError, match="version drifted"):
        smoke._validate_health(health, source="adversarial")


def test_binding_probe_rejects_json_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = smoke._bootstrap_subprocess_environment(
        tmp_path / "fixture",
        identity_index=1,
        purpose="probe-mismatch",
    )

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        _arm_guard(environment)
        payload = {
            "governor_environment_match": False,
            "settings_environment_match": True,
        }
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="binding probe drifted"):
        smoke._run_binding_probe(fixture, Path(sys.executable))


def test_installation_identity_rejects_shadow_package(tmp_path: Path) -> None:
    imported_init = tmp_path / "shadow/evidencemesh/__init__.py"
    installed_init = tmp_path / "installed/evidencemesh/__init__.py"
    imported_init.parent.mkdir(parents=True)
    installed_init.parent.mkdir(parents=True)
    imported_init.write_text("shadow = True\n", encoding="utf-8")
    installed_init.write_text("shadow = False\n", encoding="utf-8")

    class FakeDistribution:
        def locate_file(self, _path: str) -> Path:
            return installed_init

    with pytest.raises(RuntimeError, match="does not belong"):
        smoke._validate_installation_identity(  # type: ignore[arg-type]
            FakeDistribution(),
            imported_init,
            (tmp_path / "evidencemesh", tmp_path / "evidencemesh-mcp"),
        )


def test_cli_uses_distinct_ledgers_for_providers_and_http_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    observed: list[dict[str, str]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        _arm_guard(environment)
        observed.append(environment)
        if args[1:] == ["providers"]:
            return subprocess.CompletedProcess(args, 0, json.dumps(_health()), "")
        assert args[1:] == ["serve", "--transport", "http"]
        return subprocess.CompletedProcess(
            args,
            1,
            "",
            "closed-alpha governor supports one-session-per-process STDIO only",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(smoke, "_run_binding_probe", lambda *_args: _probe_receipt())
    monkeypatch.setattr(smoke, "_inside_prefix", lambda _path: True)
    result = smoke._exercise_cli(work, Path("/installed/bin/evidencemesh"))

    assert result.report["configured_providers"] == smoke.COMMUNITY_PROVIDERS
    assert result.report["http_transport"]["refused"] is True
    assert result.report["provider_requests"] == 0
    assert len(observed) == 2
    assert (
        observed[0]["EVIDENCEMESH_CLOSED_ALPHA_LEDGER"]
        != (observed[1]["EVIDENCEMESH_CLOSED_ALPHA_LEDGER"])
    )
    assert (
        observed[0]["EVIDENCEMESH_CLOSED_ALPHA_SESSION"]
        != (observed[1]["EVIDENCEMESH_CLOSED_ALPHA_SESSION"])
    )


def test_mcp_health_requires_exact_tools_bundle_and_zero_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    observed: dict[str, str] = {}

    async def fake_mcp(
        _root: Path,
        _command: Path,
        environment: dict[str, str],
    ) -> dict[str, Any]:
        _arm_guard(environment)
        observed.update(environment)
        return {
            "health": _health(),
            "tools": list(smoke.EXPECTED_TOOLS),
            "resources": list(smoke.EXPECTED_RESOURCES),
            "prompts": list(smoke.EXPECTED_PROMPTS),
        }

    monkeypatch.setattr(smoke, "_exercise_mcp_async", fake_mcp)
    monkeypatch.setattr(smoke, "_run_binding_probe", lambda *_args: _probe_receipt())
    monkeypatch.setattr(smoke, "_inside_prefix", lambda _path: True)
    result = smoke._exercise_mcp(work, Path("/installed/bin/evidencemesh-mcp"))

    assert result.report["tool_inventory"] == smoke.EXPECTED_TOOLS
    assert result.report["resource_inventory"] == ["evidencemesh://research-guide"]
    assert result.report["prompt_inventory"] == ["evidence_first_research"]
    assert result.report["configured_providers"] == smoke.COMMUNITY_PROVIDERS
    assert result.report["control_plane"]["global_attempts"] == 0
    assert observed["EVIDENCEMESH_CLOSED_ALPHA_CONTROL_PLANE"] == "rc4"


def test_pep610_binds_installed_distribution_to_exact_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "evidencemesh-0.1.0-py3-none-any.whl"
    archive.write_bytes(b"synthetic-installed-wheel")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    class FakeDistribution:
        def read_text(self, filename: str) -> str | None:
            assert filename == "direct_url.json"
            return json.dumps(
                {
                    "url": archive.resolve().as_uri(),
                    "archive_info": {
                        "hash": f"sha256={digest}",
                        "hashes": {"sha256": digest},
                    },
                }
            )

    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda _name: FakeDistribution(),
    )
    installed_distribution = importlib.metadata.distribution("evidencemesh")
    monkeypatch.setattr(smoke, "_critical_package_files", lambda *_args, **_kwargs: {})
    receipt = smoke._source_archive(
        installed_distribution,
        archive,
        label="wheel",
        expected_sha256=digest,
    )

    assert receipt["sha256"] == digest
    assert receipt["independent_sha256_after_install_matches"] is True
    assert receipt["install_to_smoke_toctou_excluded"] is False
    assert receipt["pep610"] == {
        "binding_scope": "url_and_sha256",
        "sha256_status": "matched",
        "url_matches": True,
    }

    archive.write_bytes(b"post-install-tamper")
    with pytest.raises(RuntimeError, match="independent expected SHA-256"):
        smoke._source_archive(
            installed_distribution,
            archive,
            label="wheel",
            expected_sha256=digest,
        )


def test_pep610_missing_hash_uses_independent_expected_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "evidencemesh-0.1.0-py3-none-any.whl"
    archive.write_bytes(b"installer-omits-pep610-hash")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    class FakeDistribution:
        def read_text(self, filename: str) -> str | None:
            assert filename == "direct_url.json"
            return json.dumps(
                {
                    "url": archive.resolve().as_uri(),
                    "archive_info": {},
                }
            )

    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda _name: FakeDistribution(),
    )
    installed_distribution = importlib.metadata.distribution("evidencemesh")
    monkeypatch.setattr(smoke, "_critical_package_files", lambda *_args, **_kwargs: {})
    receipt = smoke._source_archive(
        installed_distribution,
        archive,
        label="wheel",
        expected_sha256=digest,
    )

    assert receipt["independent_sha256_after_install_matches"] is True
    assert receipt["pep610"] == {
        "binding_scope": "url_only",
        "sha256_status": "not_declared_by_installer",
        "url_matches": True,
    }


def test_run_smoke_writes_zero_traffic_report_with_three_isolated_subprocesses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_command = tmp_path / "bin/evidencemesh"
    mcp_command = tmp_path / "bin/evidencemesh-mcp"
    cli_command.parent.mkdir()
    for command in (cli_command, mcp_command):
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o700)
    distribution = tmp_path / "evidencemesh-0.1.0-py3-none-any.whl"
    distribution.write_bytes(b"wheel")

    cli_result = smoke._ExerciseResult(
        report={"provider_requests": 0},
        isolation_keys=(
            (tmp_path / "cli-1.sqlite3", smoke._session(1)),
            (tmp_path / "cli-2.sqlite3", smoke._session(2)),
        ),
    )
    mcp_result = smoke._ExerciseResult(
        report={
            "provider_requests": 0,
            "tool_inventory": smoke.EXPECTED_TOOLS,
            "resource_inventory": smoke.EXPECTED_RESOURCES,
            "prompt_inventory": smoke.EXPECTED_PROMPTS,
        },
        isolation_keys=((tmp_path / "mcp.sqlite3", smoke._session(3)),),
    )
    monkeypatch.setattr(smoke, "_inside_prefix", lambda _path: True)

    class FakeDistribution:
        version = "0.1.0"

    monkeypatch.setattr(importlib.metadata, "distribution", lambda _name: FakeDistribution())
    monkeypatch.setattr(
        smoke,
        "_validate_installation_identity",
        lambda *_args: {
            "distribution_module_samefile": True,
            "entry_points_exact": True,
            "launchers_exact": True,
        },
    )
    monkeypatch.setattr(
        smoke,
        "_source_archive",
        lambda _installed, _path, *, label, expected_sha256: {
            "name": "synthetic",
            "label": label,
            "expected_sha256": expected_sha256,
        },
    )
    monkeypatch.setattr(smoke, "_exercise_cli", lambda _root, _command: cli_result)
    monkeypatch.setattr(smoke, "_exercise_mcp", lambda _root, _command: mcp_result)
    output = tmp_path / "report.json"

    report = smoke.run_smoke(
        label="wheel",
        cli_command=cli_command,
        mcp_command=mcp_command,
        distribution=distribution,
        expected_archive_sha256="a" * 64,
        work_root=tmp_path / "work",
        output=output,
    )

    assert json.loads(output.read_bytes()) == report
    assert report["smoke"] == smoke.SMOKE_ID
    assert report["control_plane"] == {
        "implementation": "SQLiteAlphaControlPlane",
        "profile": "community",
        "admitted_slots": {"community": 6, "quality": 2},
        "prepared_before_subprocess": True,
        "fixture_count": 3,
        "binding_probe_subprocess_count": 3,
        "product_subprocess_count": 3,
        "distinct_ledgers": True,
        "distinct_sessions": True,
    }
    assert all(type(value) is int and value == 0 for value in report["traffic"].values())
    assert report["validation"] == {"errors": [], "passed": True}
