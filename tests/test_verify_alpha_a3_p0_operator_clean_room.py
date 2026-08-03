from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import verify_alpha_a3_p0_operator_clean_room as gate


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _health() -> dict[str, Any]:
    return {
        "configuration_warnings": [],
        "deployment_profile": "community",
        "providers": [{"name": "wikipedia"}],
        "reliability": {"closed_alpha_governor": {"enabled": False}},
        "safety": {
            "dns_pinning": True,
            "nonstandard_ports_allowed": False,
            "private_networks_allowed": False,
            "robots_txt_respected": True,
        },
        "status": "ready",
        "version": "0.1.0",
    }


def _readonly_handoff(tmp_path: Path) -> tuple[Path, str, int, Path, Path]:
    root = tmp_path / "handoff"
    wheelhouse = root / "wheelhouse"
    bin_root = root / "bin"
    wheelhouse.mkdir(parents=True)
    bin_root.mkdir()
    project = wheelhouse / "evidencemesh-0.1.0-py3-none-any.whl"
    dependency = wheelhouse / "httpx-0.28.1-py3-none-any.whl"
    project.write_bytes(b"canonical project wheel")
    dependency.write_bytes(b"locked dependency wheel")
    project_digest = _digest(project)
    dependency_digest = _digest(dependency)
    requirements = root / gate.HANDOFF_REQUIREMENTS
    requirements.write_text(
        "\n".join(
            (
                "evidencemesh==0.1.0 \\",
                f"    --hash=sha256:{project_digest}",
                "httpx==0.28.1 \\",
                f"    --hash=sha256:{dependency_digest}",
                "",
            )
        ),
        encoding="utf-8",
    )
    descriptor = root / gate.HANDOFF_DESCRIPTOR
    descriptor.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "evidencemesh": {
                        "args": [],
                        "command": gate.TEMPLATE_COMMAND,
                        "env": {
                            **gate.EXPECTED_DESCRIPTOR_ENV,
                            gate.DESCRIPTOR_CACHE_KEY: gate.TEMPLATE_CACHE,
                        },
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    driver = root / gate.HANDOFF_DRIVER
    driver.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    uv = root / gate.HANDOFF_UV
    uv.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    manifest = root / gate.HANDOFF_MANIFEST
    included = (requirements, descriptor, driver, uv, project, dependency)
    manifest.write_text(
        "".join(f"{_digest(path)}  {path.relative_to(root).as_posix()}\n" for path in included),
        encoding="utf-8",
    )
    for path in (*included, manifest):
        path.chmod(0o444)
    uv.chmod(0o555)
    bin_root.chmod(0o555)
    wheelhouse.chmod(0o555)
    root.chmod(0o555)
    return root.resolve(), project_digest, project.stat().st_size, uv, driver


def test_constants_lock_four_local_requests_and_restartability_only() -> None:
    assert gate.SCHEMA_VERSION == "evidencemesh.alpha-a3-p0-operator-clean-room-receipt.v1"
    assert gate.EXPECTED_LOGICAL_MCP_REQUESTS == 4
    assert gate.EXPECTED_MCP_HEALTH_CALLS == 2
    assert gate.EXPECTED_MCP_SERVER_LAUNCHES == 2
    assert set(gate.EXPECTED_ENTRY_POINTS) == {"evidencemesh", "evidencemesh-mcp"}


def test_toolchain_identity_locks_uv_target_and_python_3_11(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observations = iter(
        (
            subprocess.CompletedProcess([], 0, "uv 0.11.33 (x86_64-unknown-linux-gnu)\n", ""),
            subprocess.CompletedProcess([], 0, "[3, 11, 12]\n", ""),
        )
    )
    monkeypatch.setattr(gate, "_run", lambda *_args, **_kwargs: next(observations))

    assert gate._validate_toolchain(
        uv=tmp_path / "uv",
        python_base=tmp_path / "python",
        cwd=tmp_path,
        environment={},
        timeout_seconds=1,
    ) == {"python": "3.11.12", "uv": "0.11.33"}

    monkeypatch.setattr(
        gate,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "uv 0.11.33\n", ""),
    )
    with pytest.raises(gate.OperatorGateError, match="uv version drifted"):
        gate._validate_toolchain(
            uv=tmp_path / "uv",
            python_base=tmp_path / "python",
            cwd=tmp_path,
            environment={},
            timeout_seconds=1,
        )


def test_readonly_handoff_manifest_and_hashed_requirements_pass(tmp_path: Path) -> None:
    root, digest, size, uv, driver = _readonly_handoff(tmp_path)

    report = gate._validate_handoff(
        root,
        expected_version="0.1.0",
        expected_wheel_sha256=digest,
        expected_wheel_size=size,
        expected_uv=uv,
        running_driver=driver,
        expected_owner_uid=os.getuid(),
        expected_owner_gid=os.getgid(),
    )

    assert report["manifest_entries"] == 6
    assert report["wheel_count"] == 2
    assert report["requirements_report"] == {
        "all_requirements_hash_pinned": True,
        "package_requirements": 2,
        "project_requirement_unique": True,
    }


def test_handoff_rejects_writable_or_unmanifested_file(tmp_path: Path) -> None:
    root, digest, size, uv, driver = _readonly_handoff(tmp_path)
    requirements = root / gate.HANDOFF_REQUIREMENTS
    requirements.chmod(0o644)
    with pytest.raises(gate.OperatorGateError, match="writable"):
        gate._validate_handoff(
            root,
            expected_version="0.1.0",
            expected_wheel_sha256=digest,
            expected_wheel_size=size,
            expected_uv=uv,
            running_driver=driver,
            expected_owner_uid=os.getuid(),
            expected_owner_gid=os.getgid(),
        )

    requirements.chmod(0o444)
    root.chmod(0o755)
    extra = root / "unmanifested.txt"
    extra.write_text("unexpected", encoding="utf-8")
    extra.chmod(0o444)
    root.chmod(0o555)
    with pytest.raises(gate.OperatorGateError, match="inventory drifted"):
        gate._validate_handoff(
            root,
            expected_version="0.1.0",
            expected_wheel_sha256=digest,
            expected_wheel_size=size,
            expected_uv=uv,
            running_driver=driver,
            expected_owner_uid=os.getuid(),
            expected_owner_gid=os.getgid(),
        )


def test_handoff_rejects_sdist_in_wheelhouse(tmp_path: Path) -> None:
    root, digest, size, uv, driver = _readonly_handoff(tmp_path)
    root.chmod(0o755)
    wheelhouse = root / gate.HANDOFF_WHEELHOUSE
    wheelhouse.chmod(0o755)
    sdist = wheelhouse / "dependency-1.0.tar.gz"
    sdist.write_bytes(b"source archive")
    sdist.chmod(0o444)
    manifest = root / gate.HANDOFF_MANIFEST
    manifest.chmod(0o644)
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + f"{_digest(sdist)}  {sdist.relative_to(root).as_posix()}\n",
        encoding="utf-8",
    )
    manifest.chmod(0o444)
    wheelhouse.chmod(0o555)
    root.chmod(0o555)

    with pytest.raises(gate.OperatorGateError, match="wheels-only"):
        gate._validate_handoff(
            root,
            expected_version="0.1.0",
            expected_wheel_sha256=digest,
            expected_wheel_size=size,
            expected_uv=uv,
            running_driver=driver,
            expected_owner_uid=os.getuid(),
            expected_owner_gid=os.getgid(),
        )


@pytest.mark.parametrize(
    "requirements,match",
    [
        ("evidencemesh==0.1.0\n", "no SHA-256"),
        (
            f"evidencemesh @ https://example.invalid/e.whl --hash=sha256:{'a' * 64}\n",
            "URL|exactly pinned",
        ),
        (
            f"evidencemesh==0.1.0 --hash=sha256:{'b' * 64}\n",
            "canonical wheel",
        ),
    ],
)
def test_requirements_fail_closed(requirements: str, match: str) -> None:
    with pytest.raises(gate.OperatorGateError, match=match):
        gate._validate_hashed_requirements(
            requirements,
            expected_version="0.1.0",
            expected_wheel_sha256="a" * 64,
        )


def test_environment_rejects_secret_and_proxy_shaped_names() -> None:
    environment = {
        "HOME": "/private/home",
        "GITHUB_TOKEN": "redacted",
        "HTTPS_PROXY": "http://proxy.invalid",
        "SSH_AUTH_SOCK": "/run/user/1000/agent.sock",
    }

    assert gate._forbidden_environment_names(environment) == [
        "GITHUB_TOKEN",
        "HTTPS_PROXY",
        "SSH_AUTH_SOCK",
    ]


def test_private_environment_paths_are_exact_and_distinct(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    paths = [tmp_path / name for name in ("home", "cache", "config", "data", "tmp")]
    for path in paths:
        path.mkdir(mode=0o700)
    home, cache, config, data, temporary = paths
    environment = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(temporary),
        "TZ": "UTC",
        "XDG_CACHE_HOME": str(cache),
        "XDG_CONFIG_HOME": str(config),
        "XDG_DATA_HOME": str(data),
    }

    report = gate._validate_environment(
        environment=environment,
        expected_uid=os.getuid(),
        producer_uid=os.getuid() + 1,
        work_root=work,
        home=home,
        xdg_cache=cache,
        xdg_config=config,
        xdg_data=data,
        tmp=temporary,
        cwd=work,
    )

    assert report == {
        "forbidden_environment_names": 0,
        "operator_uid_distinct": True,
        "private_directory_count": 6,
    }


def test_health_accepts_only_offline_wikipedia_without_governor() -> None:
    assert gate._validate_health(_health(), expected_version="0.1.0") == {
        "configuration_warnings": 0,
        "deployment_profile": "community",
        "dns_pinning": True,
        "governor_enabled": False,
        "private_networks_allowed": False,
        "provider_count": 1,
        "status": "ready",
        "version": "0.1.0",
    }

    invalid = _health()
    invalid["reliability"] = {"closed_alpha_governor": {"enabled": True}}
    with pytest.raises(gate.OperatorGateError, match="unexpectedly activated"):
        gate._validate_health(invalid, expected_version="0.1.0")


def test_mcp_session_requires_natural_exit_and_exact_two_requests() -> None:
    payload = {
        "children_after_exit": 0,
        "fallback_calls": 0,
        "health": _health(),
        "logical_requests": 2,
        "pid": 1234,
        "pid_gone": True,
        "protocol_version": "2025-11-25",
        "returncode": 0,
        "server_name": "EvidenceMesh",
        "server_version": "0.1.0",
    }

    assert gate._validate_mcp_session(payload, expected_version="0.1.0")["natural_exit"] is True
    payload["fallback_calls"] = 1
    with pytest.raises(gate.OperatorGateError, match="fallback"):
        gate._validate_mcp_session(payload, expected_version="0.1.0")


def test_mcp_probe_builds_closed_private_server_environment() -> None:
    source = gate._MCP_SESSION_PROBE

    for name in gate.OPERATOR_ENV_ALLOWLIST:
        assert f'"{name}"' in source
    for token in gate.FORBIDDEN_ENV_TOKENS:
        assert f'"{token}"' in source
    assert 'server_environment = build_server_environment(os.environ, server["env"])' in source
    assert 'name.startswith("A3_")' in source
    assert '"SSH_AUTH_SOCK" not in environment' in source
    assert "set(descriptor_environment) == descriptor_environment_names" in source
    assert "env=server_environment" in source
    assert 'env=server["env"]' not in source


def test_network_trace_allows_local_ipc_and_rejects_internet_socket() -> None:
    local = """
123 socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, [3, 4]) = 0
123 connect(3, {sa_family=AF_UNIX, sun_path=\"/tmp/local.sock\"}, 110) = 0
"""
    assert gate._validate_network_trace(local) == {
        "external_network_calls": 0,
        "local_ipc_calls": 2,
        "trace_network_syscalls": 2,
        "validated": True,
    }

    with pytest.raises(gate.OperatorGateError, match="Internet socket"):
        gate._validate_network_trace(
            "123 socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_TCP) = 3\n"
        )


def test_orphan_parser_accepts_empty_and_rejects_children() -> None:
    assert gate._parse_child_pids("") == ()
    assert gate._parse_child_pids("17 23\n") == (17, 23)
    gate._require_no_orphans("")
    with pytest.raises(gate.OperatorGateError, match="retained a child"):
        gate._require_no_orphans("17")


def test_operator_journey_has_one_providers_cli_invocation_only() -> None:
    source = inspect.getsource(gate.run_gate)

    assert source.count('[str(cli_command), "providers"]') == 1
    assert "benchmark-offline" not in source
    assert '[str(cli_command), "--help"]' not in source
    assert gate.EXPECTED_DESCRIPTOR_ENV["EVIDENCEMESH_PROVIDERS"] == "wikipedia"


def test_descriptor_requires_absolute_installed_command_and_private_cache(tmp_path: Path) -> None:
    prefix = tmp_path / "venv"
    command = prefix / "bin" / "evidencemesh-mcp"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    command.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    cache = state / "cache.sqlite3"
    template = tmp_path / "descriptor-template.json"
    template.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "evidencemesh": {
                        "args": [],
                        "command": gate.TEMPLATE_COMMAND,
                        "env": {
                            **gate.EXPECTED_DESCRIPTOR_ENV,
                            gate.DESCRIPTOR_CACHE_KEY: gate.TEMPLATE_CACHE,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    descriptor = tmp_path / "descriptor.json"

    assert gate._render_descriptor(
        template,
        descriptor,
        expected_command=command,
        expected_cache=cache,
    ) == {
        "environment_keys": 10,
        "mode": "0600",
        "template_fields_modified": 2,
        "validated": True,
    }
    rendered = json.loads(descriptor.read_text(encoding="utf-8"))
    server = rendered["mcpServers"]["evidencemesh"]
    assert server["command"] == str(command.resolve())
    assert server["env"][gate.DESCRIPTOR_CACHE_KEY] == str(cache.resolve())
    assert descriptor.stat().st_mode & 0o777 == 0o600


def test_record_paths_must_all_disappear_after_uninstall(tmp_path: Path) -> None:
    install = tmp_path / "venv"
    install.mkdir()
    removed = [install / "package.py", install / "entrypoint"]
    assert (
        gate._require_record_paths_absent(
            [str(path.resolve()) for path in removed],
            install_root=install,
        )
        == 2
    )
    removed[0].write_text("leftover", encoding="utf-8")
    with pytest.raises(gate.OperatorGateError, match="left a RECORD path"):
        gate._require_record_paths_absent(
            [str(path.resolve()) for path in removed],
            install_root=install,
        )


def test_cli_parser_exposes_exact_operator_inputs(tmp_path: Path) -> None:
    arguments = [
        "--uv",
        "/usr/bin/uv",
        "--python-base",
        "/usr/bin/python3.11",
        "--handoff-root",
        str(tmp_path / "handoff"),
        "--home",
        str(tmp_path / "home"),
        "--xdg-cache",
        str(tmp_path / "cache"),
        "--xdg-config",
        str(tmp_path / "config"),
        "--xdg-data",
        str(tmp_path / "data"),
        "--tmp",
        str(tmp_path / "tmp"),
        "--work-root",
        str(tmp_path / "work"),
        "--state-root",
        str(tmp_path / "state"),
        "--install-root",
        str(tmp_path / "install"),
        "--forbidden-workspace",
        "/workspace/source",
        "--expected-wheel-sha256",
        "a" * 64,
        "--expected-wheel-size",
        "146492",
        "--expected-operator-uid",
        "65534",
        "--producer-uid",
        "1001",
        "--parent-net-namespace",
        "net:[1]",
        "--parent-mount-namespace",
        "mnt:[1]",
        "--receipt",
        str(tmp_path / "receipt.json"),
    ]

    parsed = gate.parse_args(arguments)

    assert parsed.expected_wheel_size == 146492
    assert parsed.expected_operator_uid == 65534
    assert parsed.expected_version == "0.1.0"
    assert parsed.timeout_seconds == 300.0
