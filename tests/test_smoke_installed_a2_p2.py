from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import io
import json
import socket
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

from scripts import smoke_installed_a2_p2 as smoke


def _runtime_payloads() -> dict[str, bytes]:
    return {
        relative: f"# installed fixture: {relative}\n".encode() for relative in smoke.RUNTIME_FILES
    }


def _wheel(path: Path, payloads: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, mode="w") as archive:
        for relative, payload in payloads.items():
            archive.writestr(relative, payload)


def _sdist(path: Path, payloads: dict[str, bytes]) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for relative, payload in payloads.items():
            info = tarfile.TarInfo(f"evidencemesh-0.1.0/src/{relative}")
            info.size = len(payload)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(payload))


@pytest.mark.parametrize("label", ["wheel", "sdist"])
def test_archive_reader_binds_every_a2_runtime_file(tmp_path: Path, label: str) -> None:
    payloads = _runtime_payloads()
    archive = tmp_path / (
        "evidencemesh-0.1.0-py3-none-any.whl" if label == "wheel" else "evidencemesh-0.1.0.tar.gz"
    )
    (_wheel if label == "wheel" else _sdist)(archive, payloads)

    assert {
        relative: smoke._archive_runtime_bytes(
            archive,
            label=label,
            relative_path=relative,
        )
        for relative in smoke.RUNTIME_FILES
    } == payloads


def test_archive_reader_rejects_duplicate_and_unsafe_members(tmp_path: Path) -> None:
    duplicate = tmp_path / "evidencemesh-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(duplicate, mode="w") as archive:
        archive.writestr(smoke.RUNTIME_FILES[0], b"first")
        archive.writestr(smoke.RUNTIME_FILES[0], b"second")
    with pytest.raises(RuntimeError, match="not unique"):
        smoke._archive_runtime_bytes(
            duplicate,
            label="wheel",
            relative_path=smoke.RUNTIME_FILES[0],
        )

    unsafe = tmp_path / "unsafe.tar.gz"
    with tarfile.open(unsafe, mode="w:gz") as archive:
        info = tarfile.TarInfo("../src/evidencemesh/__init__.py")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(RuntimeError, match="escapes"):
        smoke._archive_runtime_bytes(
            unsafe,
            label="sdist",
            relative_path=smoke.RUNTIME_FILES[0],
        )


def test_record_sha256_requires_urlsafe_sha256() -> None:
    payload = b"installed runtime bytes"
    encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")

    assert smoke._record_sha256(f"sha256={encoded}") == hashlib.sha256(payload).digest()
    with pytest.raises(RuntimeError, match="not SHA-256"):
        smoke._record_sha256(f"sha512={encoded}")
    with pytest.raises(RuntimeError, match="invalid"):
        smoke._record_sha256("sha256=!")


class _DirectUrlDistribution:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read_text(self, filename: str) -> str | None:
        assert filename == "direct_url.json"
        return json.dumps(self.payload)


def test_direct_url_requires_exact_sha256_fragment_and_accepts_empty_archive_info(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidencemesh-0.1.0-py3-none-any.whl"
    digest = "a" * 64
    distribution = cast(
        importlib.metadata.Distribution,
        _DirectUrlDistribution(
            {
                "archive_info": {},
                "url": f"{archive.as_uri()}#sha256={digest}",
            }
        ),
    )

    assert smoke._direct_url_binding(distribution, archive, digest) == {
        "archive_sha256_exact": True,
        "binding_scope": "url_and_sha256",
        "sha256_location": "url_fragment",
        "url_exact": True,
    }


@pytest.mark.parametrize(
    "url",
    [
        "plain",
        "wrong-hash",
    ],
)
def test_direct_url_refuses_url_only_and_wrong_fragment(tmp_path: Path, url: str) -> None:
    archive = tmp_path / "evidencemesh-0.1.0.tar.gz"
    digest = "b" * 64
    supplied_url = archive.as_uri()
    if url == "wrong-hash":
        supplied_url = f"{supplied_url}#sha256={'c' * 64}"
    distribution = cast(
        importlib.metadata.Distribution,
        _DirectUrlDistribution({"archive_info": {}, "url": supplied_url}),
    )

    with pytest.raises(RuntimeError, match="hashed archive URL drifted"):
        smoke._direct_url_binding(distribution, archive, digest)


def test_v2_refusal_preserves_bytes_and_directory_entries(tmp_path: Path) -> None:
    result = smoke._v2_refusal(tmp_path, smoke._HostClock())

    assert result == {
        "directory_entries_unchanged": True,
        "ledger_bytes_unchanged": True,
        "refused": True,
    }


def test_network_guard_counts_and_restores_denied_calls() -> None:
    original = socket.getaddrinfo
    with smoke._deny_real_network() as attempts:
        with pytest.raises(RuntimeError, match="DNS access"):
            socket.getaddrinfo("offline.invalid", 443)
        assert attempts == {"dns_resolution": 1, "socket_connect": 0}
    assert socket.getaddrinfo is original


def test_sys_path_cleanup_removes_only_harness_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = Path(smoke.__file__).resolve().parent
    nested_site_packages = harness / "venv/lib/python3.11/site-packages"
    independent = Path("/isolated/site-packages")
    monkeypatch.setattr(
        sys,
        "path",
        [str(harness), str(nested_site_packages), str(independent), ""],
    )

    smoke._remove_harness_paths_from_sys_path()

    assert sys.path == [str(nested_site_packages), str(independent), ""]


def test_run_smoke_composes_stable_report_and_removes_ephemeral_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "evidencemesh-0.1.0-py3-none-any.whl"
    archive.write_bytes(b"fixture archive")
    archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    work_root = tmp_path / "ephemeral"
    output = tmp_path / "report.json"
    runtime_sha256 = dict.fromkeys(smoke.RUNTIME_FILES, "a" * 64)

    def fake_rc4(**_kwargs: Any) -> dict[str, Any]:
        return {
            "cli_health_ready": True,
            "composite_passed": True,
            "distinct_subprocess_ledgers": True,
            "distinct_subprocess_sessions": True,
            "mcp_health_ready": True,
            "smoke": "evidencemesh-installed-alpha-rc4.1a-v1",
        }

    def fake_installation(**_kwargs: Any) -> dict[str, Any]:
        return {
            "archive_name": archive.name,
            "archive_sha256": archive_sha256,
            "entry_points_exact": True,
            "module_origins": {
                "evidencemesh": "__init__.py",
                "evidencemesh.alpha_liveness": "alpha_liveness.py",
                "evidencemesh.closed_alpha_feedback": "closed_alpha_feedback.py",
                "evidencemesh.engine": "engine.py",
                "evidencemesh.fetcher": "fetcher.py",
            },
            "package_origin_within_prefix": True,
            "package_version": "0.1.0",
            "pep610": {
                "archive_sha256_exact": True,
                "binding_scope": "url_and_sha256",
                "sha256_location": "url_fragment",
                "url_exact": True,
            },
            "dist_info_within_prefix": True,
            "record_inventory_exact": True,
            "runtime_archive_record_install_exact": True,
            "runtime_file_count": 5,
            "runtime_sha256": runtime_sha256,
            "virtual_environment": True,
        }

    async def fake_a2(_root: Path, _sha256: str, _label: str) -> dict[str, Any]:
        return {
            "network": {
                "dns_resolution_attempts": 0,
                "mock_transport_only": True,
                "real_socket_attempts": 0,
            }
        }

    monkeypatch.setattr(smoke, "_run_rc4_compatibility", fake_rc4)
    monkeypatch.setattr(smoke, "_validate_installed_identity_and_runtime_files", fake_installation)
    monkeypatch.setattr(smoke, "_exercise_a2", fake_a2)

    report = smoke.run_smoke(
        label="wheel",
        cli_command=tmp_path / "bin/evidencemesh",
        mcp_command=tmp_path / "bin/evidencemesh-mcp",
        distribution=archive,
        expected_archive_sha256=archive_sha256,
        work_root=work_root,
        output=output,
    )

    assert report["smoke"] == smoke.SMOKE_ID
    assert report["installation"]["runtime_sha256"] == runtime_sha256
    assert report["rc4_1a_compatibility"] == {
        "cli_health_ready": True,
        "composite_passed": True,
        "distinct_subprocess_ledgers": True,
        "distinct_subprocess_sessions": True,
        "mcp_health_ready": True,
        "smoke": "evidencemesh-installed-alpha-rc4.1a-v1",
    }
    assert report["traffic"] == {
        "document_requests": 0,
        "model_requests": 0,
        "provider_requests": 0,
        "real_network_requests": 0,
        "retries": 0,
    }
    assert report["validation"] == {"errors": [], "passed": True}
    assert json.loads(output.read_bytes()) == report
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert not work_root.exists()


@pytest.mark.asyncio
async def test_primary_v3_close_mints_authority_and_withdrawal_cleans(tmp_path: Path) -> None:
    primary_root = tmp_path / "primary"
    assert not primary_root.exists()
    result = await smoke._exercise_primary_v3(primary_root, "a" * 64, "wheel")

    assert result["closed_session_authority_created"] is True
    assert result["feedback_published_then_withdrawn"] is True
    assert result["mock_transport_delegations"] == 1
    assert result["permit_replay_refused"] is True
    assert result["shutdown_paused"] is True
    assert result["supervisor_revoked"] is True


@pytest.mark.asyncio
async def test_exact_session_expiry_requires_then_resolves_recovery(tmp_path: Path) -> None:
    recovery_root = tmp_path / "recovery"
    assert not recovery_root.exists()
    result = await smoke._exercise_recovery(recovery_root, "b" * 64, "sdist")

    assert result == {
        "expired_close_refused": True,
        "explicit_recovery_closed_session": True,
        "reserved_permit_denied": True,
        "session_quarantined": True,
    }


def test_run_smoke_rejects_output_inside_ephemeral_root(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="output must be outside"):
        smoke.run_smoke(
            label="wheel",
            cli_command=tmp_path / "cli",
            mcp_command=tmp_path / "mcp",
            distribution=tmp_path / "evidencemesh-0.1.0-py3-none-any.whl",
            expected_archive_sha256="0" * 64,
            work_root=tmp_path / "work",
            output=tmp_path / "work/report.json",
        )


def test_cli_contract_is_exact() -> None:
    parsed = smoke.parse_args(
        [
            "--label",
            "sdist",
            "--cli-command",
            "/venv/bin/evidencemesh",
            "--mcp-command",
            "/venv/bin/evidencemesh-mcp",
            "--distribution",
            "/dist/evidencemesh-0.1.0.tar.gz",
            "--expected-archive-sha256",
            "a" * 64,
            "--work-root",
            "/private/a2-p2",
            "--output",
            "/private/a2-p2-report.json",
        ]
    )

    assert parsed.label == "sdist"
    assert parsed.expected_archive_sha256 == "a" * 64
    assert parsed.cli_command == Path("/venv/bin/evidencemesh")
    assert parsed.mcp_command == Path("/venv/bin/evidencemesh-mcp")


def test_source_keeps_installed_and_mock_transport_boundaries() -> None:
    source = Path(smoke.__file__).read_text(encoding="utf-8")

    assert "sys.prefix != sys.base_prefix" in source
    assert "distribution.locate_file(relative_path)" in source
    assert '"binding_scope": "url_and_sha256"' in source
    assert "_installed_module_origins()" in source
    assert "set(rows) == {str(path) for path in declared_files}" in source
    assert "httpx.MockTransport(inner)" in source
    assert "A2SQLiteAlphaControlPlane(" in source
    assert "A2SQLiteAlphaControlPlane.bootstrap(" in source
    assert "run_session_heartbeat" in source
    assert "resolve_recovery" in source
    assert "_run_rc4_compatibility(" in source
    assert "shutil.rmtree(resolved_root)" in source
    assert '"all_hashed_entries_reverified": True' in source
    assert "_validate_archive_inventory(archive, label=label)" in source
    assert "httpx.AsyncHTTPTransport" not in source
    assert "requests." not in source
