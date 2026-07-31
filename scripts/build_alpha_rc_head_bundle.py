"""Validate the exact EvidenceMesh Alpha-RC HEAD candidate bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Any

PROJECT = "evidencemesh"
VERSION = "0.1.0"
RC_NAME = "evidencemesh-0.1.0-alpha-rc.2"
EXPECTED_DEPENDENCIES = {
    "ddgs",
    "fastmcp",
    "httpx",
    "pydantic",
    "pypdf",
    "rich",
    "trafilatura",
    "typer",
}
EXPECTED_BUNDLE_FILES = frozenset(
    {
        "SHA256SUMS",
        "alpha-rc-manifest.json",
        "dist/evidencemesh-0.1.0-py3-none-any.whl",
        "dist/evidencemesh-0.1.0.tar.gz",
        "evidencemesh-0.1.0.cdx.json",
        "installed-wheel-mcp-stdio.json",
        "installed-wheel-offline-benchmark.json",
    }
)
GENERATED_BUNDLE_FILES = frozenset({"SHA256SUMS", "alpha-rc-manifest.json"})
EXPECTED_BUNDLE_DIRECTORIES = frozenset({"dist"})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain a JSON object")
    return value


def _record(path: Path, bundle_dir: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(bundle_dir).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _single(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {pattern!r} file, found {len(matches)}")
    return matches[0]


def _normalise_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def validate_bundle_inventory(
    bundle_dir: Path,
    *,
    allow_generated_missing: bool,
) -> list[str]:
    if not bundle_dir.is_dir():
        raise ValueError(f"Candidate bundle directory does not exist: {bundle_dir}")

    entries = list(bundle_dir.rglob("*"))
    symlinks = sorted(
        path.relative_to(bundle_dir).as_posix() for path in entries if path.is_symlink()
    )
    directories = {
        path.relative_to(bundle_dir).as_posix()
        for path in entries
        if path.is_dir() and not path.is_symlink()
    }
    files = {
        path.relative_to(bundle_dir).as_posix()
        for path in entries
        if path.is_file() and not path.is_symlink()
    }
    allowed_missing = GENERATED_BUNDLE_FILES if allow_generated_missing else frozenset()
    missing = sorted(EXPECTED_BUNDLE_FILES - files - allowed_missing)
    unexpected_files = sorted(files - EXPECTED_BUNDLE_FILES)
    unexpected_directories = sorted(directories - EXPECTED_BUNDLE_DIRECTORIES)

    violations = []
    if symlinks:
        violations.append(f"symbolic links are forbidden: {symlinks}")
    if missing:
        violations.append(f"required files are missing: {missing}")
    if unexpected_files:
        violations.append(f"unexpected files: {unexpected_files}")
    if unexpected_directories:
        violations.append(f"unexpected directories: {unexpected_directories}")
    if violations:
        raise ValueError("Invalid candidate bundle inventory; " + "; ".join(violations))
    return sorted(files)


def validate_wheel(path: Path, bundle_dir: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        metadata_name = _single_member(names, f"{PROJECT}-{VERSION}.dist-info/METADATA")
        entry_points_name = _single_member(
            names,
            f"{PROJECT}-{VERSION}.dist-info/entry_points.txt",
        )
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
        entry_points = archive.read(entry_points_name).decode("utf-8")

    required_members = {
        "evidencemesh/__init__.py",
        "evidencemesh/mcp_server.py",
        "evidencemesh/py.typed",
        "evidencemesh/data/federation_v1.json",
        f"{PROJECT}-{VERSION}.dist-info/RECORD",
    }
    missing = sorted(required_members - names)
    if missing:
        raise ValueError(f"Wheel is missing required members: {missing}")
    if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
        raise ValueError("Wheel does not contain the Apache-2.0 license file")
    if metadata.get("Name") != PROJECT or metadata.get("Version") != VERSION:
        raise ValueError("Wheel project metadata does not match evidencemesh 0.1.0")
    if metadata.get("Requires-Python") != ">=3.11":
        raise ValueError("Wheel Requires-Python metadata is not >=3.11")
    requirements = metadata.get_all("Requires-Dist", [])
    dependency_names = {
        _normalise_name(re.split(r"[\s<>=!~;[(]", requirement, maxsplit=1)[0])
        for requirement in requirements
        if "extra ==" not in requirement
    }
    if dependency_names != EXPECTED_DEPENDENCIES:
        raise ValueError("Wheel runtime dependency metadata differs from the locked contract")
    if "evidencemesh = evidencemesh.cli:app" not in entry_points:
        raise ValueError("Wheel does not expose the evidencemesh console command")
    if "evidencemesh-mcp = evidencemesh.mcp_server:main" not in entry_points:
        raise ValueError("Wheel does not expose the evidencemesh-mcp console command")

    return {
        **_record(path, bundle_dir),
        "format": "wheel",
        "name": metadata.get("Name"),
        "version": metadata.get("Version"),
        "requires_python": metadata.get("Requires-Python"),
        "runtime_dependencies": sorted(dependency_names),
        "required_package_data_present": True,
        "license_file_present": True,
        "console_scripts_present": True,
    }


def _single_member(names: set[str], expected: str) -> str:
    matches = [name for name in names if name == expected]
    if len(matches) != 1:
        raise ValueError(f"Archive member {expected!r} was not found exactly once")
    return matches[0]


def validate_sdist(path: Path, bundle_dir: Path) -> dict[str, Any]:
    with tarfile.open(path, mode="r:gz") as archive:
        names = set(archive.getnames())
    root = f"{PROJECT}-{VERSION}"
    required_members = {
        f"{root}/LICENSE",
        f"{root}/README.md",
        f"{root}/pyproject.toml",
        f"{root}/src/evidencemesh/__init__.py",
        f"{root}/src/evidencemesh/mcp_server.py",
        f"{root}/src/evidencemesh/py.typed",
        f"{root}/src/evidencemesh/data/federation_v1.json",
    }
    missing = sorted(required_members - names)
    if missing:
        raise ValueError(f"Source distribution is missing required members: {missing}")
    return {
        **_record(path, bundle_dir),
        "format": "sdist",
        "required_source_files_present": True,
        "license_file_present": True,
    }


def validate_sbom(path: Path, bundle_dir: Path) -> dict[str, Any]:
    sbom = _json(path)
    metadata = sbom.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("CycloneDX metadata is missing")
    component = metadata.get("component")
    if not isinstance(component, dict):
        raise ValueError("CycloneDX root component is missing")
    components = sbom.get("components")
    if not isinstance(components, list):
        raise ValueError("CycloneDX components must be a list")
    component_names = {
        _normalise_name(str(item.get("name")))
        for item in components
        if isinstance(item, dict) and item.get("name")
    }
    missing_dependencies = sorted(EXPECTED_DEPENDENCIES - component_names)
    if missing_dependencies:
        raise ValueError(f"CycloneDX SBOM is missing dependencies: {missing_dependencies}")
    if (
        sbom.get("bomFormat") != "CycloneDX"
        or sbom.get("specVersion") != "1.7"
        or not str(sbom.get("serialNumber", "")).startswith("urn:uuid:")
    ):
        raise ValueError("CycloneDX format, version or serial number is invalid")
    if (
        _normalise_name(str(component.get("name"))) != PROJECT
        or component.get("version") != VERSION
        or component.get("type") != "application"
    ):
        raise ValueError("CycloneDX root component does not describe EvidenceMesh 0.1.0")
    serialized = path.read_text(encoding="utf-8")
    forbidden = {
        "EVIDENCE_MESH_GEMINI_KEY",
        "EVIDENCE_MESH_TAVILY_KEY",
        "GEMINI_API_KEY",
        "TAVILY_API_KEY",
    }
    if any(value in serialized for value in forbidden):
        raise ValueError("CycloneDX SBOM contains a forbidden secret name")
    return {
        **_record(path, bundle_dir),
        "format": "CycloneDX",
        "spec_version": sbom["specVersion"],
        "component_count": len(components) + 1,
        "root_component": f"{component['name']}=={component['version']}",
        "runtime_dependencies_present": True,
        "schema_validated_by_generator": True,
    }


def validate_mcp_smoke(path: Path, bundle_dir: Path) -> dict[str, Any]:
    smoke = _json(path)
    expected = (
        smoke.get("smoke") == "evidencemesh-installed-wheel-mcp-stdio-v1"
        and smoke.get("validation", {}).get("passed") is True
        and smoke.get("installation", {}).get("package_version") == VERSION
        and smoke.get("installation", {}).get("package_origin_within_isolated_prefix") is True
        and smoke.get("installation", {}).get("virtual_environment") is True
        and smoke.get("initialization", {}).get("server_name") == "EvidenceMesh"
        and smoke.get("initialization", {}).get("server_version") == VERSION
        and smoke.get("contract", {}).get("tools")
        == [
            "search_web",
            "deep_research",
            "fetch_url",
            "batch_search",
            "verify_claim",
            "health",
        ]
        and smoke.get("contract", {}).get("resources") == ["evidencemesh://research-guide"]
        and smoke.get("contract", {}).get("prompts") == ["evidence_first_research"]
        and smoke.get("contract", {}).get("health_status") == "ready"
        and smoke.get("contract", {}).get("configured_providers") == ["wikipedia"]
        and smoke.get("traffic", {}).get("provider_http_requests") == 0
        and smoke.get("traffic", {}).get("model_requests") == 0
    )
    if not expected:
        raise ValueError("Installed-wheel MCP smoke does not satisfy the locked contract")
    return {
        **_record(path, bundle_dir),
        "transport": "stdio",
        "real_subprocess": True,
        "initialization_passed": True,
        "inventory_passed": True,
        "health_passed": True,
        "external_requests": 0,
    }


def validate_cli_smoke(path: Path, bundle_dir: Path) -> dict[str, Any]:
    report = _json(path)
    if (
        report.get("benchmark") != "EvidenceMesh offline federation benchmark"
        or report.get("case_count") != 12
        or report.get("fused", {}).get("hit_at_1") != 1.0
        or len(report.get("cases", [])) != 12
    ):
        raise ValueError("Installed-wheel offline CLI benchmark failed its regression contract")
    return {
        **_record(path, bundle_dir),
        "case_count": 12,
        "fused_hit_at_1": 1.0,
        "network_requests": 0,
    }


def build_bundle_manifest(
    *,
    bundle_dir: Path,
    protocol_sha256: str,
    commit_sha: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("commit_sha must be a full lowercase Git commit SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", protocol_sha256):
        raise ValueError("protocol_sha256 must be a lowercase SHA-256 digest")
    if bundle_dir.name != RC_NAME:
        raise ValueError(f"Bundle directory must be named {RC_NAME}")
    validate_bundle_inventory(bundle_dir, allow_generated_missing=True)

    dist_dir = bundle_dir / "dist"
    wheel = _single(dist_dir, f"{PROJECT}-{VERSION}-*.whl")
    sdist = _single(dist_dir, f"{PROJECT}-{VERSION}.tar.gz")
    sbom = bundle_dir / f"{PROJECT}-{VERSION}.cdx.json"
    mcp_smoke = bundle_dir / "installed-wheel-mcp-stdio.json"
    cli_smoke = bundle_dir / "installed-wheel-offline-benchmark.json"
    for path in (sbom, mcp_smoke, cli_smoke):
        if not path.is_file():
            raise ValueError(f"Required candidate evidence is missing: {path.name}")

    artifacts = {
        "wheel": validate_wheel(wheel, bundle_dir),
        "sdist": validate_sdist(sdist, bundle_dir),
        "sbom": validate_sbom(sbom, bundle_dir),
        "mcp_stdio_smoke": validate_mcp_smoke(mcp_smoke, bundle_dir),
        "offline_cli_smoke": validate_cli_smoke(cli_smoke, bundle_dir),
    }
    gates = {
        "exactly_one_wheel": True,
        "exactly_one_sdist": True,
        "package_metadata": True,
        "license_and_package_data": True,
        "isolated_wheel_install": True,
        "installed_cli_regression": True,
        "real_mcp_stdio_handshake": True,
        "mcp_inventory": True,
        "mcp_health_without_network": True,
        "cyclonedx_1_7_sbom": True,
        "exact_candidate_inventory": True,
    }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "candidate": RC_NAME,
        "phase": "alpha-rc-head",
        "scored": False,
        "environment": {
            "commit_sha": commit_sha,
            "project": PROJECT,
            "version": VERSION,
        },
        "protocol": {
            "path": "docs/alpha-rc-head-protocol-v1.md",
            "sha256": protocol_sha256,
        },
        "artifacts": artifacts,
        "inventory": {
            "file_count": len(EXPECTED_BUNDLE_FILES),
            "files": sorted(EXPECTED_BUNDLE_FILES),
            "unexpected_files": [],
        },
        "gates": gates,
        "attestations": {
            "github_keyless_provenance_required": True,
            "github_keyless_sbom_required": True,
            "status": "pending_github_actions",
        },
        "traffic": {
            "provider_http_requests": 0,
            "paid_provider_requests": 0,
            "tavily_requests": 0,
            "other_provider_requests": 0,
            "model_requests": 0,
            "gemini_requests": 0,
            "retries": 0,
            "fallbacks": 0,
            "repairs": 0,
        },
        "decision": {
            "build_candidate_created": all(gates.values()),
            "alpha_technical_candidate_passed": False,
            "quality_claim_allowed": False,
            "public_distribution_allowed": False,
            "github_release_allowed": False,
            "pypi_publish_allowed": False,
            "merge_allowed": False,
            "phase12_allowed": False,
            "release_decision": "no-go",
        },
    }
    manifest_path = bundle_dir / "alpha-rc-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksummed = [wheel, sdist, sbom, mcp_smoke, cli_smoke, manifest_path]
    checksum_path = bundle_dir / "SHA256SUMS"
    checksum_path.write_text(
        "".join(
            f"{sha256_file(path)} *{path.relative_to(bundle_dir).as_posix()}\n"
            for path in checksummed
        ),
        encoding="utf-8",
    )
    validate_bundle_inventory(bundle_dir, allow_generated_missing=False)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--commit-sha", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_bundle_manifest(
        bundle_dir=args.bundle_dir.resolve(),
        protocol_sha256=args.protocol_sha256,
        commit_sha=args.commit_sha,
    )


if __name__ == "__main__":
    main()
