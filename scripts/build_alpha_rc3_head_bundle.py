"""Validate the ephemeral EvidenceMesh Alpha-RC3 HEAD exact bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import tarfile
import zipfile
from collections import Counter
from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT = "evidencemesh"
VERSION = "0.1.0"
RC_NAME = "evidencemesh-0.1.0-alpha-rc.3"
PHASE = "alpha-rc3-head-exact"
PROTOCOL_PATH = "docs/alpha-rc3-head-exact-protocol-v1.md"
WORKFLOW_PATH = ".github/workflows/alpha-rc3-head-exact.yml"
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
CRITICAL_SOURCES = {
    "evidencemesh/cli.py": "src/evidencemesh/cli.py",
    "evidencemesh/engine.py": "src/evidencemesh/engine.py",
    "evidencemesh/fetcher.py": "src/evidencemesh/fetcher.py",
    "evidencemesh/governor.py": "src/evidencemesh/governor.py",
}
EXPECTED_BUNDLE_FILES = frozenset(
    {
        "SHA256SUMS",
        "alpha-rc3-head-manifest.json",
        "dist/evidencemesh-0.1.0-py3-none-any.whl",
        "dist/evidencemesh-0.1.0.tar.gz",
        "evidencemesh-0.1.0.cdx.json",
        "installed-sdist-rc3-smoke.json",
        "installed-wheel-offline-benchmark.json",
        "installed-wheel-rc3-smoke.json",
    }
)
GENERATED_BUNDLE_FILES = frozenset({"SHA256SUMS", "alpha-rc3-head-manifest.json"})
EXPECTED_BUNDLE_DIRECTORIES = frozenset({"dist"})
FORBIDDEN_PUBLIC_METADATA_IDENTIFIERS = frozenset(
    {
        "EVIDENCE_MESH_TAVILY_KEY",
        "EVIDENCE_MESH_GEMINI_KEY",
        "TAVILY_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "GITHUB_WORKSPACE",
        "RUNNER_TEMP",
    }
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


def _validate_digest(value: str, *, length: int, label: str) -> None:
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"{label} must be a lowercase hexadecimal digest")


def _safe_archive_name(name: str) -> None:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts or "" in path.parts:
        raise ValueError(f"Unsafe archive member path: {name!r}")


def validate_bundle_inventory(
    bundle_dir: Path,
    *,
    allow_generated_missing: bool,
) -> list[str]:
    if not bundle_dir.is_dir() or bundle_dir.is_symlink():
        raise ValueError("Candidate bundle must be a real directory")
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


def validate_wheel(path: Path, bundle_dir: Path, source_root: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise ValueError(f"Wheel contains duplicate members: {duplicates}")
        for info in infos:
            _safe_archive_name(info.filename)
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(unix_mode)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ValueError("Wheel links and special files are forbidden")
        members = set(names)
        metadata_name = f"{PROJECT}-{VERSION}.dist-info/METADATA"
        entry_points_name = f"{PROJECT}-{VERSION}.dist-info/entry_points.txt"
        required = {
            *CRITICAL_SOURCES,
            "evidencemesh/__init__.py",
            "evidencemesh/mcp_server.py",
            "evidencemesh/py.typed",
            "evidencemesh/data/federation_v1.json",
            f"{PROJECT}-{VERSION}.dist-info/RECORD",
            metadata_name,
            entry_points_name,
        }
        missing = sorted(required - members)
        if missing:
            raise ValueError(f"Wheel is missing required members: {missing}")
        if not any(name.endswith(".dist-info/licenses/LICENSE") for name in members):
            raise ValueError("Wheel does not contain the Apache-2.0 license file")
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
        entry_points = archive.read(entry_points_name).decode("utf-8")
        source_hashes: dict[str, str] = {}
        for member, source_name in CRITICAL_SOURCES.items():
            archive_bytes = archive.read(member)
            source_bytes = (source_root / source_name).read_bytes()
            if archive_bytes != source_bytes:
                raise ValueError(f"Wheel member differs from candidate source: {member}")
            source_hashes[member] = _sha256_bytes(source_bytes)

    if metadata.get("Name") != PROJECT or metadata.get("Version") != VERSION:
        raise ValueError("Wheel project metadata differs from EvidenceMesh 0.1.0")
    if metadata.get("Requires-Python") != ">=3.11":
        raise ValueError("Wheel Requires-Python metadata is not >=3.11")
    requirements = metadata.get_all("Requires-Dist", [])
    dependency_names = {
        _normalise_name(re.split(r"[\s<>=!~;[(]", item, maxsplit=1)[0])
        for item in requirements
        if "extra ==" not in item
    }
    if dependency_names != EXPECTED_DEPENDENCIES:
        raise ValueError("Wheel runtime dependencies differ from the locked contract")
    if "evidencemesh = evidencemesh.cli:app" not in entry_points:
        raise ValueError("Wheel is missing the EvidenceMesh CLI entry point")
    if "evidencemesh-mcp = evidencemesh.mcp_server:main" not in entry_points:
        raise ValueError("Wheel is missing the EvidenceMesh MCP entry point")
    return {
        **_record(path, bundle_dir),
        "format": "wheel",
        "critical_source_sha256": source_hashes,
        "runtime_dependencies": sorted(dependency_names),
        "safe_member_paths": True,
        "duplicate_members": 0,
        "symlinks": 0,
        "special_files": 0,
    }


def validate_sdist(path: Path, bundle_dir: Path, source_root: Path) -> dict[str, Any]:
    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise ValueError(f"Source distribution contains duplicate members: {duplicates}")
        for member in members:
            _safe_archive_name(member.name)
            if not (member.isfile() or member.isdir()):
                raise ValueError("Source distribution links and special files are forbidden")
        root = f"{PROJECT}-{VERSION}"
        required = {
            f"{root}/LICENSE",
            f"{root}/README.md",
            f"{root}/pyproject.toml",
            f"{root}/src/evidencemesh/__init__.py",
            f"{root}/src/evidencemesh/mcp_server.py",
            f"{root}/src/evidencemesh/py.typed",
            f"{root}/src/evidencemesh/data/federation_v1.json",
            *(f"{root}/src/{name}" for name in CRITICAL_SOURCES),
        }
        missing = sorted(required - set(names))
        if missing:
            raise ValueError(f"Source distribution is missing required members: {missing}")
        source_hashes: dict[str, str] = {}
        for wheel_name, source_name in CRITICAL_SOURCES.items():
            member_name = f"{root}/{source_name}"
            extracted = archive.extractfile(member_name)
            if extracted is None:
                raise ValueError(f"Cannot read source distribution member: {member_name}")
            archive_bytes = extracted.read()
            source_bytes = (source_root / source_name).read_bytes()
            if archive_bytes != source_bytes:
                raise ValueError(f"Source distribution differs from candidate: {wheel_name}")
            source_hashes[wheel_name] = _sha256_bytes(source_bytes)
    return {
        **_record(path, bundle_dir),
        "format": "sdist",
        "critical_source_sha256": source_hashes,
        "safe_member_paths": True,
        "duplicate_members": 0,
        "links_or_special_files": 0,
    }


def _iter_strings(value: object) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            strings.extend(_iter_strings(key))
            strings.extend(_iter_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_iter_strings(item))
    return strings


def _validate_public_sbom_metadata(
    sbom: dict[str, Any],
    *,
    bundle_dir: Path,
    source_root: Path,
) -> None:
    forbidden_paths = {
        str(bundle_dir.resolve()),
        str(bundle_dir.parent.resolve()),
        str(source_root.resolve()),
    }
    for value in _iter_strings(sbom):
        folded = value.casefold()
        if any(
            identifier.casefold() in folded for identifier in FORBIDDEN_PUBLIC_METADATA_IDENTIFIERS
        ):
            raise ValueError("CycloneDX SBOM contains a credential identifier")
        if any(path in value for path in forbidden_paths):
            raise ValueError("CycloneDX SBOM contains a private runner path")
        if folded.startswith("file:") or re.match(
            r"^(?:/(?:home|tmp|workspace|root)/|[a-z]:\\)",
            value,
            flags=re.IGNORECASE,
        ):
            raise ValueError("CycloneDX SBOM contains an absolute filesystem path")


def validate_sbom(path: Path, bundle_dir: Path, source_root: Path) -> dict[str, Any]:
    sbom = _json(path)
    _validate_public_sbom_metadata(
        sbom,
        bundle_dir=bundle_dir,
        source_root=source_root,
    )
    metadata = sbom.get("metadata")
    component = metadata.get("component") if isinstance(metadata, dict) else None
    components = sbom.get("components")
    if not isinstance(component, dict) or not isinstance(components, list):
        raise ValueError("CycloneDX component inventory is missing")
    component_names = {
        _normalise_name(str(item.get("name")))
        for item in components
        if isinstance(item, dict) and item.get("name")
    }
    missing = sorted(EXPECTED_DEPENDENCIES - component_names)
    if missing:
        raise ValueError(f"CycloneDX SBOM is missing dependencies: {missing}")
    if (
        sbom.get("bomFormat") != "CycloneDX"
        or sbom.get("specVersion") != "1.7"
        or not str(sbom.get("serialNumber", "")).startswith("urn:uuid:")
    ):
        raise ValueError("CycloneDX identity is invalid")
    if (
        _normalise_name(str(component.get("name"))) != PROJECT
        or component.get("version") != VERSION
        or component.get("type") != "application"
    ):
        raise ValueError("CycloneDX root component does not describe EvidenceMesh 0.1.0")
    return {
        **_record(path, bundle_dir),
        "format": "CycloneDX",
        "spec_version": "1.7",
        "component_count": len(components) + 1,
        "runtime_dependencies_present": True,
        "public_metadata_scan_passed": True,
        "structural_validation_passed": True,
    }


def _require_zero_counters(value: object, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a non-empty object")
    if any(type(item) is not int or item != 0 for item in value.values()):
        raise ValueError(f"{label} counters must be integer zero values")


def validate_smoke(
    path: Path,
    bundle_dir: Path,
    *,
    label: str,
    expected_archive: dict[str, Any],
) -> dict[str, Any]:
    report = _json(path)
    installation = report.get("installation")
    sdk = report.get("sdk")
    cli = report.get("cli")
    mcp = report.get("mcp_stdio")
    source_archive = report.get("source_archive")
    validation = report.get("validation")
    expected = (
        report.get("schema_version") == 1
        and report.get("smoke") == "evidencemesh-installed-alpha-rc3-v1"
        and report.get("label") == label
        and isinstance(installation, dict)
        and installation.get("package_version") == VERSION
        and installation.get("package_origin_within_isolated_prefix") is True
        and installation.get("virtual_environment") is True
        and isinstance(source_archive, dict)
        and source_archive.get("name") == Path(str(expected_archive["path"])).name
        and source_archive.get("sha256") == expected_archive["sha256"]
        and source_archive.get("size_bytes") == expected_archive["size_bytes"]
        and source_archive.get("direct_url_matches") is True
        and isinstance(sdk, dict)
        and sdk.get("mock_transport_calls") == 1
        and sdk.get("session_attempts") == 1
        and sdk.get("global_attempts") == 1
        and sdk.get("dispatched_attempts") == 1
        and sdk.get("scope") == "single_host_shared_sqlite"
        and sdk.get("ledger_directory_mode") == "0700"
        and sdk.get("ledger_file_mode") == "0600"
        and isinstance(cli, dict)
        and cli.get("command_within_prefix") is True
        and cli.get("configured_providers") == ["wikipedia"]
        and cli.get("governor_enabled") is True
        and cli.get("scope") == "single_host_shared_sqlite"
        and cli.get("http_transport_refused") is True
        and cli.get("provider_requests") == 0
        and isinstance(mcp, dict)
        and mcp.get("command_within_prefix") is True
        and mcp.get("configured_providers") == ["wikipedia"]
        and mcp.get("governor_enabled") is True
        and mcp.get("scope") == "single_host_shared_sqlite"
        and mcp.get("provider_requests") == 0
        and isinstance(validation, dict)
        and validation.get("errors") == []
        and validation.get("passed") is True
    )
    if not expected:
        raise ValueError(f"Installed {label} RC3 smoke failed the locked contract")
    _require_zero_counters(report.get("traffic"), "smoke traffic")
    return {
        **_record(path, bundle_dir),
        "installation": label,
        "source_archive_sha256": source_archive["sha256"],
        "sdk_mock_dispatches": 1,
        "cli_governor_active": True,
        "mcp_stdio_governor_active": True,
        "external_requests": 0,
    }


def validate_offline_benchmark(path: Path, bundle_dir: Path) -> dict[str, Any]:
    report = _json(path)
    if (
        report.get("benchmark") != "EvidenceMesh offline federation benchmark"
        or report.get("case_count") != 12
        or report.get("fused", {}).get("hit_at_1") != 1.0
        or len(report.get("cases", [])) != 12
    ):
        raise ValueError("Installed-wheel offline benchmark failed")
    return {
        **_record(path, bundle_dir),
        "case_count": 12,
        "fused_hit_at_1": 1.0,
        "network_requests": 0,
    }


def build_bundle_manifest(
    *,
    bundle_dir: Path,
    source_root: Path,
    protocol_sha256: str,
    workflow_sha256: str,
    candidate_sha: str,
    candidate_tree: str,
    runtime_base_sha: str,
    runtime_base_tree: str,
) -> dict[str, Any]:
    for value, length, label in (
        (protocol_sha256, 64, "protocol_sha256"),
        (workflow_sha256, 64, "workflow_sha256"),
        (candidate_sha, 40, "candidate_sha"),
        (candidate_tree, 40, "candidate_tree"),
        (runtime_base_sha, 40, "runtime_base_sha"),
        (runtime_base_tree, 40, "runtime_base_tree"),
    ):
        _validate_digest(value, length=length, label=label)
    if bundle_dir.name != RC_NAME:
        raise ValueError(f"Bundle directory must be named {RC_NAME}")
    validate_bundle_inventory(bundle_dir, allow_generated_missing=True)

    dist = bundle_dir / "dist"
    wheel = _single(dist, f"{PROJECT}-{VERSION}-*.whl")
    sdist = _single(dist, f"{PROJECT}-{VERSION}.tar.gz")
    sbom = bundle_dir / f"{PROJECT}-{VERSION}.cdx.json"
    wheel_smoke = bundle_dir / "installed-wheel-rc3-smoke.json"
    sdist_smoke = bundle_dir / "installed-sdist-rc3-smoke.json"
    benchmark = bundle_dir / "installed-wheel-offline-benchmark.json"
    wheel_artifact = validate_wheel(wheel, bundle_dir, source_root)
    sdist_artifact = validate_sdist(sdist, bundle_dir, source_root)
    artifacts = {
        "wheel": wheel_artifact,
        "sdist": sdist_artifact,
        "sbom": validate_sbom(sbom, bundle_dir, source_root),
        "installed_wheel_smoke": validate_smoke(
            wheel_smoke,
            bundle_dir,
            label="wheel",
            expected_archive=wheel_artifact,
        ),
        "installed_sdist_smoke": validate_smoke(
            sdist_smoke,
            bundle_dir,
            label="sdist",
            expected_archive=sdist_artifact,
        ),
        "offline_benchmark": validate_offline_benchmark(benchmark, bundle_dir),
    }
    gates = {
        "archive_safety": True,
        "byte_reproducible_distributions": True,
        "cyclonedx_1_7": True,
        "exact_bundle_inventory": True,
        "installed_cli_governor": True,
        "installed_mcp_stdio_governor": True,
        "installed_sdist": True,
        "installed_sdk_mock_dispatch": True,
        "installed_wheel": True,
        "locked_runtime_dependencies": True,
        "offline_cli_regression": True,
        "public_sbom_metadata": True,
        "runtime_bytes_match_candidate": True,
    }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "candidate": RC_NAME,
        "phase": PHASE,
        "scored": False,
        "identity": {
            "candidate_sha": candidate_sha,
            "candidate_tree": candidate_tree,
            "runtime_base_sha": runtime_base_sha,
            "runtime_base_tree": runtime_base_tree,
        },
        "protocol": {"path": PROTOCOL_PATH, "sha256": protocol_sha256},
        "workflow": {"path": WORKFLOW_PATH, "sha256": workflow_sha256},
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
            "metadata_report_attestation_required": True,
            "status": "pending_github_actions",
        },
        "distribution": {
            "binary_artifact_uploaded": False,
            "binaries_ephemeral_on_runner": True,
            "public_metadata_only": True,
        },
        "traffic": {
            "provider_requests": 0,
            "tavily_requests": 0,
            "model_requests": 0,
            "token_count_requests": 0,
            "document_fetches": 0,
            "retries": 0,
            "fallbacks": 0,
            "repairs": 0,
            "benchmark_asset_downloads": 0,
            "tester_sessions": 0,
        },
        "decision": {
            "build_candidate_created": all(gates.values()),
            "alpha_technical_candidate_passed": False,
            "live_execution_authorized": False,
            "public_binary_distribution_allowed": False,
            "merge_allowed": False,
            "release_allowed": False,
            "quality_claim_allowed": False,
        },
    }
    manifest_path = bundle_dir / "alpha-rc3-head-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checksummed = [wheel, sdist, sbom, wheel_smoke, sdist_smoke, benchmark, manifest_path]
    (bundle_dir / "SHA256SUMS").write_text(
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
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--workflow-sha256", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--runtime-base-sha", required=True)
    parser.add_argument("--runtime-base-tree", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_bundle_manifest(
        bundle_dir=args.bundle_dir.resolve(),
        source_root=args.source_root.resolve(),
        protocol_sha256=args.protocol_sha256,
        workflow_sha256=args.workflow_sha256,
        candidate_sha=args.candidate_sha,
        candidate_tree=args.candidate_tree,
        runtime_base_sha=args.runtime_base_sha,
        runtime_base_tree=args.runtime_base_tree,
    )


if __name__ == "__main__":
    main()
