from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.build_alpha_rc_bundle import RC_NAME as HISTORICAL_RC_NAME
from scripts.build_alpha_rc_head_bundle import (
    EXPECTED_BUNDLE_FILES,
    EXPECTED_DEPENDENCIES,
    RC_NAME,
    build_bundle_manifest,
)
from scripts.finalize_alpha_rc_head_report import finalize_report

PROTOCOL_SHA256 = "41c86a73a2d3e0a4f4225d0574a2d145650cb73eca14a9d61e1391bcbab76f3c"
ACCEPTED_RC2_SHA = "81b5f8a8abd4302b27ad123bd5505e1757eadc7f"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _add_tar_text(archive: tarfile.TarFile, name: str) -> None:
    payload = b"test"
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    archive.addfile(member, io.BytesIO(payload))


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
        archive.writestr("evidencemesh-0.1.0.dist-info/METADATA", metadata)
        archive.writestr(
            "evidencemesh-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\n"
            "evidencemesh = evidencemesh.cli:app\n"
            "evidencemesh-mcp = evidencemesh.mcp_server:main\n",
        )

    sdist = dist / "evidencemesh-0.1.0.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        for member in (
            "LICENSE",
            "README.md",
            "pyproject.toml",
            "src/evidencemesh/__init__.py",
            "src/evidencemesh/mcp_server.py",
            "src/evidencemesh/py.typed",
            "src/evidencemesh/data/federation_v1.json",
        ):
            _add_tar_text(archive, f"evidencemesh-0.1.0/{member}")

    _write_json(
        bundle / "evidencemesh-0.1.0.cdx.json",
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.7",
            "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000002",
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
        bundle / "installed-wheel-mcp-stdio.json",
        {
            "smoke": "evidencemesh-installed-wheel-mcp-stdio-v1",
            "installation": {
                "package_version": "0.1.0",
                "package_origin_within_isolated_prefix": True,
                "virtual_environment": True,
            },
            "initialization": {
                "server_name": "EvidenceMesh",
                "server_version": "0.1.0",
            },
            "contract": {
                "tools": [
                    "search_web",
                    "deep_research",
                    "fetch_url",
                    "batch_search",
                    "verify_claim",
                    "health",
                ],
                "resources": ["evidencemesh://research-guide"],
                "prompts": ["evidence_first_research"],
                "health_status": "ready",
                "configured_providers": ["wikipedia"],
            },
            "traffic": {"provider_http_requests": 0, "model_requests": 0},
            "validation": {"passed": True},
        },
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


def test_alpha_rc_head_protocol_is_frozen_and_keeps_quality_separate() -> None:
    root = Path(__file__).parents[1]
    protocol_path = root / "docs" / "alpha-rc-head-protocol-v1.md"
    protocol = protocol_path.read_text(encoding="utf-8")
    normalized = " ".join(protocol.split())

    assert hashlib.sha256(protocol_path.read_bytes()).hexdigest() == PROTOCOL_SHA256
    assert RC_NAME in protocol
    assert "must execute every candidate step" in normalized
    assert "Tavily or other search-provider requests | 0" in protocol
    assert "Gemini or other model requests | 0" in protocol
    assert "the pull request remains a draft" in normalized
    assert "public distribution, PyPI and GitHub Release remain blocked" in normalized
    assert "no quality, “best”, superior or state-of-the-art claim is allowed" in normalized


def test_alpha_rc_head_bundle_and_result_bind_the_fresh_identity(tmp_path: Path) -> None:
    assert HISTORICAL_RC_NAME == "evidencemesh-0.1.0-alpha-rc.1"
    bundle = _synthetic_bundle(tmp_path)
    commit_sha = "b" * 40
    manifest = build_bundle_manifest(
        bundle_dir=bundle,
        protocol_sha256=PROTOCOL_SHA256,
        commit_sha=commit_sha,
    )

    assert manifest["candidate"] == RC_NAME
    assert manifest["phase"] == "alpha-rc-head"
    assert manifest["environment"]["commit_sha"] == commit_sha
    assert manifest["protocol"] == {
        "path": "docs/alpha-rc-head-protocol-v1.md",
        "sha256": PROTOCOL_SHA256,
    }
    assert set(manifest["inventory"]["files"]) == EXPECTED_BUNDLE_FILES
    assert all(value == 0 for value in manifest["traffic"].values())

    result = finalize_report(
        bundle_dir=bundle,
        output=tmp_path / "alpha-rc-head-result.json",
        repository="VynoDePal/EvidenceMesh",
        commit_sha=commit_sha,
        run_id="456",
        run_attempt="1",
        artifact_name=f"alpha-rc-head-{commit_sha}",
        provenance_attestation_id="21",
        provenance_attestation_url="https://github.com/example/provenance-head",
        sbom_attestation_id="22",
        sbom_attestation_url="https://github.com/example/sbom-head",
    )
    assert result["candidate"]["name"] == RC_NAME
    assert result["evaluation"] == "evidencemesh-alpha-rc-head-v1"
    assert result["phase"] == "alpha-rc-head"
    assert result["environment"]["commit_sha"] == commit_sha
    assert result["decision"]["alpha_technical_candidate_passed"] is True
    assert result["decision"]["quality_benchmark_passed"] is False
    assert result["decision"]["public_distribution_allowed"] is False
    assert result["decision"]["merge_allowed"] is False


def test_alpha_rc_head_rejects_extra_file_and_wrong_sha(tmp_path: Path) -> None:
    bundle = _synthetic_bundle(tmp_path)
    (bundle / "unexpected.log").write_text("not allowed", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected files"):
        build_bundle_manifest(
            bundle_dir=bundle,
            protocol_sha256=PROTOCOL_SHA256,
            commit_sha="b" * 40,
        )

    (bundle / "unexpected.log").unlink()
    build_bundle_manifest(
        bundle_dir=bundle,
        protocol_sha256=PROTOCOL_SHA256,
        commit_sha="b" * 40,
    )
    with pytest.raises(ValueError, match="commit SHAs differ"):
        finalize_report(
            bundle_dir=bundle,
            output=tmp_path / "wrong.json",
            repository="VynoDePal/EvidenceMesh",
            commit_sha="c" * 40,
            run_id="456",
            run_attempt="1",
            artifact_name="wrong",
            provenance_attestation_id="21",
            provenance_attestation_url="https://github.com/example/provenance",
            sbom_attestation_id="22",
            sbom_attestation_url="https://github.com/example/sbom",
        )


def test_alpha_rc_head_workflow_is_permanently_limited_to_the_accepted_rc2() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "alpha-rc-head.yml").read_text(encoding="utf-8")

    assert PROTOCOL_SHA256 in workflow
    assert RC_NAME in workflow
    assert "  push:" in workflow
    assert "      - agent/evidencemesh-v0.1" in workflow
    assert "    paths:" not in workflow
    assert "pull_request:" not in workflow
    assert "workflow_dispatch:" not in workflow
    assert "cancel-in-progress: true" in workflow
    assert f"EXPECTED_SHA: {ACCEPTED_RC2_SHA}" in workflow
    assert "EXPECTED_SHA: ${{ github.sha }}" not in workflow
    assert "github.repository == 'VynoDePal/EvidenceMesh'" in workflow
    assert "github.ref == 'refs/heads/agent/evidencemesh-v0.1'" in workflow
    assert f"github.sha == '{ACCEPTED_RC2_SHA}'" in workflow
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"' in workflow
    assert "candidate-state" not in workflow
    assert "Reuse the committed candidate decision" not in workflow
    assert workflow.count("actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26") == 2
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "scripts/build_alpha_rc_head_bundle.py" in workflow
    assert "scripts/finalize_alpha_rc_head_report.py" in workflow
    assert 'done < "$RC_BUNDLE/SHA256SUMS"' in workflow
    assert workflow.count('--source-digest "$EXPECTED_SHA"') == 2
    assert workflow.count('--source-ref "$GITHUB_REF"') == 2
    assert workflow.count('--signer-digest "$EXPECTED_SHA"') == 2
    assert "path: ${{ env.UPLOAD_ROOT }}" in workflow
    assert "artifact-metadata: write" in workflow
    assert "persist-credentials: false" in workflow
    assert "secrets." not in workflow
    assert "pypi publish" not in workflow.lower()
    assert "gh release create" not in workflow.lower()
    assert 'quality_benchmark_passed"] is False' in workflow
    assert 'public_distribution_allowed"] is False' in workflow
    assert 'merge_allowed"] is False' in workflow
