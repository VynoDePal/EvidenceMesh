"""Runtime configuration with conservative local-first defaults."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeploymentProfile(StrEnum):
    """Named provider bundles; explicit provider configuration still wins."""

    COMMUNITY = "community"
    QUALITY = "quality"


COMMUNITY_PROVIDERS = (
    "searxng",
    "wikipedia",
    "crossref",
    "arxiv",
    "github",
)
QUALITY_PROVIDERS = (
    *COMMUNITY_PROVIDERS,
    "tavily",
)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_profile: DeploymentProfile = DeploymentProfile.COMMUNITY
    enabled_providers: list[str]
    searxng_url: str = "http://127.0.0.1:8888"
    wikipedia_url_template: str = "https://{language}.wikipedia.org/w/api.php"
    crossref_url: str = "https://api.crossref.org/works"
    arxiv_url: str = "https://export.arxiv.org/api/query"
    github_search_url: str = "https://api.github.com/search/repositories"
    openalex_url: str = "https://api.openalex.org/works"
    github_token: str | None = None
    openalex_api_key: str | None = None
    brave_api_key: str | None = None
    tavily_api_key: str | None = None
    exa_api_key: str | None = None
    firecrawl_api_key: str | None = None
    firecrawl_url: str = "https://api.firecrawl.dev"
    cache_path: Path = Path("~/.cache/evidencemesh/cache.sqlite3").expanduser()
    search_cache_ttl_seconds: int = Field(default=3_600, ge=0, le=604_800)
    document_cache_ttl_seconds: int = Field(default=86_400, ge=0, le=2_592_000)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    provider_failure_threshold: int = Field(default=3, ge=1, le=20)
    provider_recovery_seconds: float = Field(default=60.0, ge=1.0, le=3_600.0)
    fetch_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    dns_timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    extraction_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    max_download_bytes: int = Field(default=10_000_000, ge=100_000, le=50_000_000)
    max_pdf_pages: int = Field(default=100, ge=1, le=1_000)
    max_concurrency: int = Field(default=8, ge=1, le=32)
    max_redirects: int = Field(default=5, ge=0, le=10)
    allow_private_networks: bool = False
    allow_nonstandard_ports: bool = False
    respect_robots_txt: bool = True
    user_agent: str = "EvidenceMesh/0.1 (+https://github.com/VynoDePal/EvidenceMesh)"
    crossref_mailto: str | None = None

    @model_validator(mode="before")
    @classmethod
    def apply_profile_defaults(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "enabled_providers" in value:
            return value
        data = dict(value)
        profile = DeploymentProfile(data.get("deployment_profile", DeploymentProfile.COMMUNITY))
        data["enabled_providers"] = list(
            QUALITY_PROVIDERS if profile is DeploymentProfile.QUALITY else COMMUNITY_PROVIDERS
        )
        return data

    @field_validator("enabled_providers")
    @classmethod
    def normalise_providers(cls, values: list[str]) -> list[str]:
        allowed = {
            "arxiv",
            "brave",
            "crossref",
            "ddgs",
            "exa",
            "firecrawl",
            "github",
            "openalex",
            "searxng",
            "tavily",
            "wikipedia",
        }
        normalised = list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))
        unknown = set(normalised) - allowed
        if unknown:
            raise ValueError(f"unknown providers: {sorted(unknown)}")
        return normalised

    @classmethod
    def from_env(cls, **overrides: Any) -> Settings:
        providers = os.getenv("EVIDENCEMESH_PROVIDERS")
        deployment_profile = os.getenv(
            "EVIDENCEMESH_DEPLOYMENT_PROFILE",
            DeploymentProfile.COMMUNITY.value,
        )
        data: dict[str, Any] = {
            "deployment_profile": deployment_profile,
            "searxng_url": os.getenv(
                "EVIDENCEMESH_SEARXNG_URL",
                "http://127.0.0.1:8888",
            ),
            "arxiv_url": os.getenv(
                "EVIDENCEMESH_ARXIV_URL",
                "https://export.arxiv.org/api/query",
            ),
            "github_search_url": os.getenv(
                "EVIDENCEMESH_GITHUB_SEARCH_URL",
                "https://api.github.com/search/repositories",
            ),
            "openalex_url": os.getenv(
                "EVIDENCEMESH_OPENALEX_URL",
                "https://api.openalex.org/works",
            ),
            "github_token": os.getenv("GITHUB_TOKEN"),
            "openalex_api_key": os.getenv("OPENALEX_API_KEY"),
            "brave_api_key": os.getenv("BRAVE_API_KEY"),
            "tavily_api_key": os.getenv("TAVILY_API_KEY"),
            "exa_api_key": os.getenv("EXA_API_KEY"),
            "firecrawl_api_key": os.getenv("FIRECRAWL_API_KEY"),
            "firecrawl_url": os.getenv(
                "EVIDENCEMESH_FIRECRAWL_URL",
                "https://api.firecrawl.dev",
            ),
            "cache_path": Path(
                os.getenv(
                    "EVIDENCEMESH_CACHE_PATH",
                    "~/.cache/evidencemesh/cache.sqlite3",
                )
            ).expanduser(),
            "allow_private_networks": _bool_env(
                "EVIDENCEMESH_ALLOW_PRIVATE_NETWORKS",
                False,
            ),
            "allow_nonstandard_ports": _bool_env(
                "EVIDENCEMESH_ALLOW_NONSTANDARD_PORTS",
                False,
            ),
            "respect_robots_txt": _bool_env(
                "EVIDENCEMESH_RESPECT_ROBOTS_TXT",
                True,
            ),
            "crossref_mailto": os.getenv("CROSSREF_MAILTO"),
        }
        if providers:
            data["enabled_providers"] = providers.split(",")
        numeric_env = {
            "EVIDENCEMESH_SEARCH_CACHE_TTL": ("search_cache_ttl_seconds", int),
            "EVIDENCEMESH_DOCUMENT_CACHE_TTL": ("document_cache_ttl_seconds", int),
            "EVIDENCEMESH_REQUEST_TIMEOUT": ("request_timeout_seconds", float),
            "EVIDENCEMESH_PROVIDER_FAILURE_THRESHOLD": (
                "provider_failure_threshold",
                int,
            ),
            "EVIDENCEMESH_PROVIDER_RECOVERY_SECONDS": (
                "provider_recovery_seconds",
                float,
            ),
            "EVIDENCEMESH_FETCH_TIMEOUT": ("fetch_timeout_seconds", float),
            "EVIDENCEMESH_DNS_TIMEOUT": ("dns_timeout_seconds", float),
            "EVIDENCEMESH_EXTRACTION_TIMEOUT": ("extraction_timeout_seconds", float),
            "EVIDENCEMESH_MAX_DOWNLOAD_BYTES": ("max_download_bytes", int),
            "EVIDENCEMESH_MAX_PDF_PAGES": ("max_pdf_pages", int),
            "EVIDENCEMESH_MAX_CONCURRENCY": ("max_concurrency", int),
        }
        for env_name, (field_name, cast) in numeric_env.items():
            if value := os.getenv(env_name):
                data[field_name] = cast(value)
        data.update(overrides)
        return cls.model_validate(data)
