from __future__ import annotations

import hashlib
import io
import json
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.build_alpha_rc3_head_bundle import (
    CRITICAL_SOURCES,
    EXPECTED_BUNDLE_FILES,
    EXPECTED_DEPENDENCIES,
    RC_NAME,
    build_bundle_manifest,
)
from scripts.finalize_alpha_rc3_head_report import finalize_report

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "docs/alpha-rc3-head-exact-protocol-v1.md"
WORKFLOW = ROOT / ".github/workflows/alpha-rc3-head-exact.yml"
ACCEPTANCE = ROOT / "alpha/alpha_rc3_head_acceptance_v1.json"
SMOKE = ROOT / "scripts/smoke_installed_rc3.py"
PROTOCOL_SHA256 = "5363531629e09fd43b41e17b2f9ad4dc631d8548b308728471e6363c81198456"
BASE_SHA = "710739311af1c11504e647e94026f13d3dfb221f"
BASE_TREE = "70d75d4eddef8654e850215d9b3eb6abd778ecdf"
CANDIDATE_SHA = "c1e0be437442b0d97da26f2c9085067a8c09955e"
CANDIDATE_TREE = "44bb1df79b6026c1fc1c2a40218c7347117697a0"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _add_tar_bytes(archive: tarfile.TarFile, name: str, payload: bytes = b"test") -> None:
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    archive.addfile(member, io.BytesIO(payload))


def _smoke_payload(label: str, archive: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "smoke": "evidencemesh-installed-alpha-rc3-v1",
        "label": label,
        "installation": {
            "package_version": "0.1.0",
            "package_origin_within_isolated_prefix": True,
            "virtual_environment": True,
        },
        "source_archive": {
            "name": archive.name,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "size_bytes": archive.stat().st_size,
            "direct_url_matches": True,
        },
        "sdk": {
            "mock_transport_calls": 1,
            "session_attempts": 1,
            "global_attempts": 1,
            "dispatched_attempts": 1,
            "governor_enabled": True,
            "scope": "single_host_shared_sqlite",
            "ledger_directory_mode": "0700",
            "ledger_file_mode": "0600",
        },
        "cli": {
            "command_within_prefix": True,
            "configured_providers": ["wikipedia"],
            "governor_enabled": True,
            "scope": "single_host_shared_sqlite",
            "http_transport_refused": True,
            "provider_requests": 0,
        },
        "mcp_stdio": {
            "command_within_prefix": True,
            "configured_providers": ["wikipedia"],
            "governor_enabled": True,
            "scope": "single_host_shared_sqlite",
            "tool_inventory": [
                "search_web",
                "deep_research",
                "fetch_url",
                "batch_search",
                "verify_claim",
                "health",
            ],
            "provider_requests": 0,
        },
        "traffic": {
            "provider_requests": 0,
            "tavily_requests": 0,
            "model_requests": 0,
            "document_fetches": 0,
            "retries": 0,
            "fallbacks": 0,
            "repairs": 0,
        },
        "validation": {"errors": [], "passed": True},
    }


def _synthetic_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / RC_NAME
    dist = bundle / "dist"
    dist.mkdir(parents=True)
    wheel = dist / "evidencemesh-0.1.0-py3-none-any.whl"
    requirements = "".join(f"Requires-Dist: {name}>=1\n" for name in sorted(EXPECTED_DEPENDENCIES))
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: evidencemesh\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.11\n"
        f"{requirements}\n"
    )
    with zipfile.ZipFile(wheel, mode="w") as archive:
        for member in (
            "evidencemesh/__init__.py",
            "evidencemesh/mcp_server.py",
            "evidencemesh/py.typed",
            "evidencemesh/data/federation_v1.json",
            "evidencemesh-0.1.0.dist-info/RECORD",
            "evidencemesh-0.1.0.dist-info/licenses/LICENSE",
        ):
            archive.writestr(member, "test")
        for member, source_name in CRITICAL_SOURCES.items():
            archive.writestr(member, (ROOT / source_name).read_bytes())
        archive.writestr("evidencemesh-0.1.0.dist-info/METADATA", metadata)
        archive.writestr(
            "evidencemesh-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\n"
            "evidencemesh = evidencemesh.cli:app\n"
            "evidencemesh-mcp = evidencemesh.mcp_server:main\n",
        )

    sdist = dist / "evidencemesh-0.1.0.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        for name in (
            "LICENSE",
            "README.md",
            "pyproject.toml",
            "src/evidencemesh/__init__.py",
            "src/evidencemesh/mcp_server.py",
            "src/evidencemesh/py.typed",
            "src/evidencemesh/data/federation_v1.json",
        ):
            _add_tar_bytes(archive, f"evidencemesh-0.1.0/{name}")
        for source_name in CRITICAL_SOURCES.values():
            _add_tar_bytes(
                archive,
                f"evidencemesh-0.1.0/{source_name}",
                (ROOT / source_name).read_bytes(),
            )

    _write_json(
        bundle / "evidencemesh-0.1.0.cdx.json",
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.7",
            "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000003",
            "metadata": {
                "component": {
                    "name": "evidencemesh",
                    "version": "0.1.0",
                    "type": "application",
                }
            },
            "components": [
                {"name": name, "version": "1.0", "type": "library"}
                for name in sorted(EXPECTED_DEPENDENCIES)
            ],
        },
    )
    _write_json(
        bundle / "installed-wheel-rc3-smoke.json",
        _smoke_payload("wheel", wheel),
    )
    _write_json(
        bundle / "installed-sdist-rc3-smoke.json",
        _smoke_payload("sdist", sdist),
    )
    _write_json(
        bundle / "installed-wheel-offline-benchmark.json",
        {
            "benchmark": "EvidenceMesh offline federation benchmark",
            "case_count": 12,
            "fused": {"hit_at_1": 1.0},
            "cases": [{"id": f"case-{index}"} for index in range(12)],
        },
    )
    return bundle


def _build(bundle: Path) -> dict[str, object]:
    return build_bundle_manifest(
        bundle_dir=bundle,
        source_root=ROOT,
        protocol_sha256=PROTOCOL_SHA256,
        workflow_sha256="a" * 64,
        candidate_sha="b" * 40,
        candidate_tree="c" * 40,
        runtime_base_sha=BASE_SHA,
        runtime_base_tree=BASE_TREE,
    )


def test_protocol_freezes_metadata_only_exact_head_acceptance() -> None:
    protocol = " ".join(PROTOCOL.read_text(encoding="utf-8").split())
    assert hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() == PROTOCOL_SHA256
    for marker in (
        "evidencemesh-0.1.0-alpha-rc.3",
        "first direct child",
        "never claims a retrospective attestation",
        "No bundle file is uploaded",
        "Search or provider requests | 0",
        "The pull request remains draft",
        "single-host technical candidate",
        "metadata-only sealing commit",
    ):
        assert marker in protocol


def test_bundle_and_report_bind_candidate_without_binary_upload(tmp_path: Path) -> None:
    bundle = _synthetic_bundle(tmp_path)
    manifest = _build(bundle)
    assert manifest["candidate"] == RC_NAME
    assert set(manifest["inventory"]["files"]) == EXPECTED_BUNDLE_FILES
    assert all(type(value) is bool and value for value in manifest["gates"].values())
    assert all(type(value) is int and value == 0 for value in manifest["traffic"].values())
    assert manifest["distribution"] == {
        "binary_artifact_uploaded": False,
        "binaries_ephemeral_on_runner": True,
        "public_metadata_only": True,
    }

    result = finalize_report(
        bundle_dir=bundle,
        output=tmp_path / "result.json",
        repository="VynoDePal/EvidenceMesh",
        candidate_sha="b" * 40,
        candidate_tree="c" * 40,
        run_id="123",
        run_attempt="1",
        provenance_attestation_id="31",
        provenance_attestation_url="https://github.com/example/provenance",
        sbom_attestation_id="32",
        sbom_attestation_url="https://github.com/example/sbom",
    )
    assert result["decision"]["alpha_technical_candidate_passed"] is True
    assert result["decision"]["live_execution_authorized"] is False
    assert result["decision"]["public_binary_distribution_allowed"] is False
    assert result["distribution"]["github_actions_artifact_created"] is False
    assert result["candidate"]["parent_sha"] == BASE_SHA
    assert result["candidate"]["parent_tree"] == BASE_TREE
    assert all(type(value) is int and value == 0 for value in result["traffic"].values())


def test_bundle_rejects_duplicate_wheel_member_and_unsafe_sdist(tmp_path: Path) -> None:
    duplicate = _synthetic_bundle(tmp_path / "duplicate")
    wheel = duplicate / "dist/evidencemesh-0.1.0-py3-none-any.whl"
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(wheel, mode="a") as archive,
    ):
        archive.writestr(
            "evidencemesh/governor.py",
            (ROOT / "src/evidencemesh/governor.py").read_bytes(),
        )
    with pytest.raises(ValueError, match="duplicate members"):
        _build(duplicate)

    unsafe = _synthetic_bundle(tmp_path / "unsafe")
    sdist = unsafe / "dist/evidencemesh-0.1.0.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        member = tarfile.TarInfo("../escape")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="Unsafe archive member"):
        _build(unsafe)


def test_bundle_rejects_boolean_zero_and_post_validation_tampering(tmp_path: Path) -> None:
    invalid = _synthetic_bundle(tmp_path / "invalid")
    smoke_path = invalid / "installed-wheel-rc3-smoke.json"
    smoke = json.loads(smoke_path.read_bytes())
    smoke["traffic"]["provider_requests"] = False
    _write_json(smoke_path, smoke)
    with pytest.raises(ValueError, match="integer zero"):
        _build(invalid)

    tampered = _synthetic_bundle(tmp_path / "tampered")
    _build(tampered)
    (tampered / "alpha-rc3-head-manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after bundle validation"):
        finalize_report(
            bundle_dir=tampered,
            output=tmp_path / "tampered.json",
            repository="VynoDePal/EvidenceMesh",
            candidate_sha="b" * 40,
            candidate_tree="c" * 40,
            run_id="123",
            run_attempt="1",
            provenance_attestation_id="31",
            provenance_attestation_url="https://github.com/example/provenance",
            sbom_attestation_id="32",
            sbom_attestation_url="https://github.com/example/sbom",
        )

    extra = _synthetic_bundle(tmp_path / "extra")
    _build(extra)
    (extra / "unexpected.txt").write_text("not closed", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected files"):
        finalize_report(
            bundle_dir=extra,
            output=tmp_path / "extra.json",
            repository="VynoDePal/EvidenceMesh",
            candidate_sha="b" * 40,
            candidate_tree="c" * 40,
            run_id="123",
            run_attempt="1",
            provenance_attestation_id="31",
            provenance_attestation_url="https://github.com/example/provenance",
            sbom_attestation_id="32",
            sbom_attestation_url="https://github.com/example/sbom",
        )


def test_bundle_rejects_special_wheel_and_private_sbom_metadata(tmp_path: Path) -> None:
    special = _synthetic_bundle(tmp_path / "special")
    wheel = special / "dist/evidencemesh-0.1.0-py3-none-any.whl"
    fifo = zipfile.ZipInfo("evidencemesh/special")
    fifo.create_system = 3
    fifo.external_attr = (stat.S_IFIFO | 0o600) << 16
    with zipfile.ZipFile(wheel, mode="a") as archive:
        archive.writestr(fifo, b"")
    with pytest.raises(ValueError, match="special files"):
        _build(special)

    private = _synthetic_bundle(tmp_path / "private")
    sbom_path = private / "evidencemesh-0.1.0.cdx.json"
    sbom = json.loads(sbom_path.read_bytes())
    sbom["metadata"]["properties"] = [{"name": "source", "value": "/home/runner/work/EvidenceMesh"}]
    _write_json(sbom_path, sbom)
    with pytest.raises(ValueError, match="filesystem path"):
        _build(private)


def test_bundle_rejects_distribution_smoke_digest_drift(tmp_path: Path) -> None:
    bundle = _synthetic_bundle(tmp_path)
    smoke_path = bundle / "installed-wheel-rc3-smoke.json"
    smoke = json.loads(smoke_path.read_bytes())
    smoke["source_archive"]["sha256"] = "0" * 64
    _write_json(smoke_path, smoke)
    with pytest.raises(ValueError, match="smoke failed"):
        _build(bundle)


def test_installed_smoke_is_governed_and_contains_no_live_provider_path() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")
    assert "httpx.MockTransport" in smoke
    assert '"dispatched_attempts": snapshot["dispatched_attempts"]' in smoke
    assert '"EVIDENCEMESH_CLOSED_ALPHA_LEDGER"' in smoke
    assert '"EVIDENCEMESH_CLOSED_ALPHA_PROFILE": "community"' in smoke
    assert '"serve", "--transport", "http"' in smoke
    assert "closed-alpha governor supports one-session-per-process STDIO only" in smoke
    assert 'read_text("direct_url.json")' in smoke
    assert '"direct_url_matches": True' in smoke
    assert 'client.call_tool("health", {})' in smoke
    assert "single_host_shared_sqlite" in smoke
    assert "TAVILY_API_KEY" not in smoke
    assert "GEMINI_API_KEY" not in smoke


def test_one_shot_workflow_is_retired_by_deletion() -> None:
    assert not WORKFLOW.exists()


def test_metadata_only_seal_records_public_evidence_and_keeps_live_blocked() -> None:
    record = json.loads(ACCEPTANCE.read_bytes())
    assert record["schema_version"] == 1
    assert record["acceptance"] == {
        "scope": "single_host_technical_alpha_only",
        "scored": False,
        "status": "accepted",
    }
    assert record["candidate"]["sha"] == CANDIDATE_SHA
    assert record["candidate"]["tree"] == CANDIDATE_TREE
    assert record["candidate"]["parent_sha"] == BASE_SHA
    assert record["candidate"]["parent_tree"] == BASE_TREE
    assert len(record["candidate"]["subjects"]) == 7
    assert record["run"] == {
        "attempt": 1,
        "conclusion": "success",
        "id": 30643865155,
        "job_id": 91200262890,
        "seal_emitted_at_utc": "2026-07-31T15:42:50Z",
        "url": "https://github.com/VynoDePal/EvidenceMesh/actions/runs/30643865155",
    }
    assert record["attestations"] == {
        "provenance": {
            "id": 38206529,
            "url": "https://github.com/VynoDePal/EvidenceMesh/attestations/38206529",
        },
        "result": {
            "id": 38206635,
            "url": "https://github.com/VynoDePal/EvidenceMesh/attestations/38206635",
        },
        "sbom": {
            "id": 38206541,
            "url": "https://github.com/VynoDePal/EvidenceMesh/attestations/38206541",
        },
    }
    assert record["distribution"]["github_actions_artifact_count"] == 0
    assert record["distribution"]["binary_artifact_uploaded"] is False
    assert record["distribution"]["unpublished_distributions"] is True
    assert record["decision"]["alpha_technical_candidate_passed"] is True
    assert record["decision"]["sealing_commit_required"] is True
    for blocked in (
        "closed_alpha_adoption_authorized",
        "live_execution_authorized",
        "merge_allowed",
        "public_binary_distribution_allowed",
        "release_allowed",
        "tester_contact_authorized",
    ):
        assert record["decision"][blocked] is False
    assert all(type(value) is int and value == 0 for value in record["traffic"].values())
    assert record["seal"]["completed"] is True
    assert record["seal"]["workflow_retired"] is True
    assert record["seal"]["retired_workflow_path"] == str(WORKFLOW.relative_to(ROOT))
    assert record["seal"]["workflow_retirement_method"] == "deleted_in_sealing_commit"
    assert not WORKFLOW.exists()
    assert record["workflow"]["sha256"] == (
        "92c856ae22987016d513c74c04259257bbc5ba0c6561a8727e334dd21c31c9a2"
    )
    assert record["protocol"]["sha256"] == PROTOCOL_SHA256
