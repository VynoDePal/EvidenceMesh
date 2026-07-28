"""Runtime configuration with conservative local-first defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled_providers: list[str] = Field(
        default_factory=lambda: ["searxng", "ddgs", "wikipedia", "crossref"]
    )
    searxng_url: str = "http://127.0.0.1:8888"
    wikipedia_url_template: str = "https://{language}.wikipedia.org/w/api.php"
    crossref_url: str = "https://api.crossref.org/works"
    brave_api_key: str | None = None
    tavily_api_key: str | None = None
    exa_api_key: str | None = None
    firecrawl_api_key: str | None = None
    firecrawl_url: str = "https://api.firecrawl.dev"
    cache_path: Path = Path("~/.cache/evidencemesh/cache.sqlite3").expanduser()
    search_cache_ttl_seconds: int = Field(default=3_600, ge=0, le=604_800)
    document_cache_ttl_seconds: int = Field(default=86_400, ge=0, le=2_592_000)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    fetch_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    max_download_bytes: int = Field(default=10_000_000, ge=100_000, le=50_000_000)
    max_concurrency: int = Field(default=8, ge=1, le=32)
    max_redirects: int = Field(default=5, ge=0, le=10)
    allow_private_networks: bool = False
    allow_nonstandard_ports: bool = False
    respect_robots_txt: bool = True
    user_agent: str = "EvidenceMesh/0.1 (+https://github.com/VynoDePal/EvidenceMesh)"
    crossref_mailto: str | None = None

    @field_validator("enabled_providers")
    @classmethod
    def normalise_providers(cls, values: list[str]) -> list[str]:
        allowed = {
            "brave",
            "crossref",
            "ddgs",
            "exa",
            "firecrawl",
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
        data: dict[str, Any] = {
            "enabled_providers": (
                providers.split(",") if providers else ["searxng", "ddgs", "wikipedia", "crossref"]
            ),
            "searxng_url": os.getenv(
                "EVIDENCEMESH_SEARXNG_URL",
                "http://127.0.0.1:8888",
            ),
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
        numeric_env = {
            "EVIDENCEMESH_SEARCH_CACHE_TTL": ("search_cache_ttl_seconds", int),
            "EVIDENCEMESH_DOCUMENT_CACHE_TTL": ("document_cache_ttl_seconds", int),
            "EVIDENCEMESH_REQUEST_TIMEOUT": ("request_timeout_seconds", float),
            "EVIDENCEMESH_FETCH_TIMEOUT": ("fetch_timeout_seconds", float),
            "EVIDENCEMESH_MAX_DOWNLOAD_BYTES": ("max_download_bytes", int),
            "EVIDENCEMESH_MAX_CONCURRENCY": ("max_concurrency", int),
        }
        for env_name, (field_name, cast) in numeric_env.items():
            if value := os.getenv(env_name):
                data[field_name] = cast(value)
        data.update(overrides)
        return cls.model_validate(data)
