from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

from scripts.build_alpha_rc_bundle import (
    EXPECTED_DEPENDENCIES,
    RC_NAME,
    build_bundle_manifest,
)
from scripts.finalize_alpha_rc_report import finalize_report
from scripts.smoke_installed_mcp import (
    EXPECTED_PROMPTS,
    EXPECTED_RESOURCES,
    EXPECTED_TOOLS,
    _validation_errors,
)

PROTOCOL_SHA256 = "560e3e0932863ba78c4b5432af78b8dd47e0cdfe80c9e8ff5be9fcb1c2107ed5"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _add_tar_text(archive: tarfile.TarFile, name: str, text: str = "test") -> None:
    payload = text.encode()
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    archive.addfile(member, io.BytesIO(payload))


def _synthetic_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / RC_NAME
    dist = bundle / "dist"
    dist.mkdir(parents=True)

    wheel = dist / "evidencemesh-0.1.0-py3-none-any.whl"
    requires = "".join(f"Requires-Dist: {name}>=1\n" for name in sorted(EXPECTED_DEPENDENCIES))
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: evidencemesh\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.11\n"
        f"{requires}\n"
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
        root = "evidencemesh-0.1.0"
        for member in (
            "LICENSE",
            "README.md",
            "pyproject.toml",
            "src/evidencemesh/__init__.py",
            "src/evidencemesh/mcp_server.py",
            "src/evidencemesh/py.typed",
            "src/evidencemesh/data/federation_v1.json",
        ):
            _add_tar_text(archive, f"{root}/{member}")

    _write_json(
        bundle / "evidencemesh-0.1.0.cdx.json",
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.7",
            "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000001",
            "version": 1,
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
                "tools": EXPECTED_TOOLS,
                "resources": EXPECTED_RESOURCES,
                "prompts": EXPECTED_PROMPTS,
                "health_status": "ready",
                "configured_providers": ["wikipedia"],
            },
            "traffic": {
                "provider_http_requests": 0,
                "model_requests": 0,
            },
            "validation": {"errors": [], "passed": True},
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


def test_phase11_4_protocol_is_frozen_and_keeps_release_separate() -> None:
    root = Path(__file__).parents[1]
    protocol_path = root / "docs" / "alpha-rc-protocol-v1.md"
    protocol = protocol_path.read_text(encoding="utf-8")
    assert hashlib.sha256(protocol_path.read_bytes()).hexdigest() == PROTOCOL_SHA256
    assert "real subprocess through FastMCP's STDIO transport" in protocol
    assert "provider search or fetch requests: 0" in protocol
    assert "actions/attest" in protocol
    assert "CycloneDX JSON 1.7" in protocol
    assert "PyPI and GitHub Release publication remain blocked" in protocol
    assert "Phase 12 remains blocked" in protocol
    assert "no superiority or “best open-source search” claim is allowed" in protocol


def test_phase11_4_bundle_manifest_and_final_decision_are_separate(tmp_path: Path) -> None:
    bundle = _synthetic_bundle(tmp_path)
    commit_sha = "a" * 40
    manifest = build_bundle_manifest(
        bundle_dir=bundle,
        protocol_sha256=PROTOCOL_SHA256,
        commit_sha=commit_sha,
    )
    assert all(manifest["gates"].values())
    assert manifest["decision"]["build_candidate_created"] is True
    assert manifest["decision"]["alpha_technical_candidate_passed"] is False
    assert manifest["decision"]["public_distribution_allowed"] is False
    checksum_lines = (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(checksum_lines) == 6
    assert all(" *" in line for line in checksum_lines)

    result = finalize_report(
        bundle_dir=bundle,
        output=tmp_path / "result.json",
        repository="VynoDePal/EvidenceMesh",
        commit_sha=commit_sha,
        run_id="123",
        run_attempt="1",
        artifact_name=f"phase11-4-alpha-rc-{commit_sha}",
        provenance_attestation_id="11",
        provenance_attestation_url="https://github.com/example/provenance",
        sbom_attestation_id="12",
        sbom_attestation_url="https://github.com/example/sbom",
    )
    assert result["decision"]["alpha_technical_candidate_passed"] is True
    assert result["decision"]["quality_benchmark_passed"] is False
    assert result["decision"]["public_distribution_allowed"] is False
    assert result["decision"]["release_ready"] is False
    assert result["decision"]["release_decision"] == "no-go"
    assert result["supply_chain"]["provenance"]["verified_by_github_cli"] is True
    assert result["supply_chain"]["sbom"]["predicate_type"] == "https://cyclonedx.org/bom"


def test_installed_mcp_validation_rejects_source_or_contract_drift() -> None:
    report = {
        "installation": {
            "package_version": "0.1.0",
            "package_origin_within_isolated_prefix": True,
            "virtual_environment": True,
        },
        "initialization": {
            "protocol_version": "2025-11-25",
            "server_name": "EvidenceMesh",
            "server_version": "0.1.0",
        },
        "contract": {
            "tools": EXPECTED_TOOLS,
            "resources": EXPECTED_RESOURCES,
            "prompts": EXPECTED_PROMPTS,
            "health_status": "ready",
            "configured_providers": ["wikipedia"],
            "configuration_warnings": [],
            "private_networks_allowed": False,
            "dns_pinning": True,
        },
    }
    assert _validation_errors(report, "0.1.0") == []
    report["installation"]["package_origin_within_isolated_prefix"] = False
    report["contract"]["tools"] = [*EXPECTED_TOOLS, "unexpected"]
    assert _validation_errors(report, "0.1.0") == [
        "package_origin",
        "tool_inventory",
    ]


def test_phase11_4_workflow_locks_supply_chain_and_zero_research_traffic() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "phase11-4-alpha-rc.yml").read_text(
        encoding="utf-8"
    )
    assert PROTOCOL_SHA256 in workflow
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert workflow.count("actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26") == 2
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    assert "artifact-metadata: write" in workflow
    assert "persist-credentials: false" in workflow
    assert "--from cyclonedx-bom==7.3.0" in workflow
    assert "--predicate-type https://cyclonedx.org/bom" in workflow
    assert "scripts/smoke_installed_mcp.py" in workflow
    assert "EVIDENCE_MESH_TAVILY_KEY" not in workflow
    assert "EVIDENCE_MESH_GEMINI_KEY" not in workflow
    assert "TAVILY_API_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert "pypi publish" not in workflow.lower()
    assert "gh release create" not in workflow.lower()


def test_permanent_ci_installs_wheel_and_runs_real_stdio_smoke() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "uv pip install --python" in workflow
    assert '"$install_env/bin/evidencemesh" benchmark-offline' in workflow
    assert '--command "$install_env/bin/evidencemesh-mcp"' in workflow
    assert "--output /tmp/evidencemesh-installed-wheel-mcp.json" in workflow


def test_alpha_distribution_guide_does_not_imply_publication() -> None:
    root = Path(__file__).parents[1]
    guide = (root / "docs" / "alpha-release-v0.1.md").read_text(encoding="utf-8")
    assert "not yet a published PyPI package or GitHub Release" in " ".join(guide.split())
    assert "sha256sum --check SHA256SUMS" in guide
    assert guide.count("gh attestation verify") == 2
    assert "--predicate-type https://cyclonedx.org/bom" in guide
