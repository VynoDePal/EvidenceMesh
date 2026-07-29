from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from evidencemesh.config import DeploymentProfile, Settings
from evidencemesh.models import (
    FetchRequest,
    ResearchRequest,
    SearchProfile,
    SearchRequest,
)


def test_search_request_normalises_domains_and_variants() -> None:
    request = SearchRequest(
        query="example query",
        domains=["Example.COM.", "example.com", "Café.example"],
        query_variants=[" second query ", "second query"],
    )
    assert request.domains == ["example.com", "xn--caf-dma.example"]
    assert request.query_variants == ["second query"]


@pytest.mark.parametrize(
    ("profile", "limit", "expected"),
    [
        (SearchProfile.WEB, 10, 3),
        (SearchProfile.NEWS, 10, 3),
        (SearchProfile.REFERENCE, 10, 10),
        (SearchProfile.ACADEMIC, 7, 7),
        (SearchProfile.CODE, 20, 10),
    ],
)
def test_search_request_uses_profile_aware_domain_cap(
    profile: SearchProfile,
    limit: int,
    expected: int,
) -> None:
    request = SearchRequest(query="example query", profile=profile, limit=limit)
    assert request.max_per_domain is None
    assert request.effective_max_per_domain == expected
    assert request.max_per_domain_policy == "profile_default"


def test_search_request_explicit_domain_cap_overrides_profile_default() -> None:
    request = SearchRequest(
        query="example query",
        profile=SearchProfile.ACADEMIC,
        limit=5,
        max_per_domain=2,
    )
    assert request.effective_max_per_domain == 2
    assert request.max_per_domain_policy == "request_override"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("query", "x"),
        ("language", "english"),
        ("domains", ["https://example.com"]),
        ("domains", ["bad..example"]),
        ("domains", ["bad_domain.example"]),
        ("domains", ["-bad.example"]),
        ("exclude_domains", ["name@example.com"]),
        ("limit", 51),
        ("content_budget_chars", 999),
    ],
)
def test_search_request_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"query": "valid query", field: value})


def test_search_request_rejects_domain_overlap() -> None:
    with pytest.raises(ValidationError, match="both included and excluded"):
        SearchRequest(
            query="valid query",
            domains=["example.com"],
            exclude_domains=["example.com"],
        )


def test_research_request_deduplicates_subqueries() -> None:
    request = ResearchRequest(
        question="What is deterministic retrieval?",
        subqueries=["source material", " source material "],
    )
    assert request.subqueries == ["source material"]


def test_strict_models_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"query": "valid query", "surprise": True})


def test_fetch_request_accepts_http_and_rejects_file() -> None:
    assert str(FetchRequest(url="https://example.com/a").url) == "https://example.com/a"
    with pytest.raises(ValidationError):
        FetchRequest(url="file:///etc/passwd")


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "env-cache.sqlite3"
    monkeypatch.setenv("EVIDENCEMESH_PROVIDERS", " DDGS,wikipedia,ddgs ")
    monkeypatch.setenv("EVIDENCEMESH_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("EVIDENCEMESH_ALLOW_PRIVATE_NETWORKS", "yes")
    monkeypatch.setenv("EVIDENCEMESH_RESPECT_ROBOTS_TXT", "off")
    monkeypatch.setenv("EVIDENCEMESH_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("EVIDENCEMESH_PROVIDER_FAILURE_THRESHOLD", "4")
    monkeypatch.setenv("EVIDENCEMESH_PROVIDER_RECOVERY_SECONDS", "45")
    monkeypatch.setenv("EVIDENCEMESH_DNS_TIMEOUT", "4")
    monkeypatch.setenv("EVIDENCEMESH_MAX_PDF_PAGES", "25")
    monkeypatch.setenv(
        "EVIDENCEMESH_SEARXNG_FALLBACK_URLS",
        "https://one.example/, https://two.example,https://one.example",
    )
    monkeypatch.setenv("EVIDENCEMESH_QUALITY_PRIMARY_PROVIDER_SHARE", "0.6")
    settings = Settings.from_env()
    assert settings.enabled_providers == ["ddgs", "wikipedia"]
    assert settings.cache_path == cache_path
    assert settings.allow_private_networks is True
    assert settings.respect_robots_txt is False
    assert settings.max_concurrency == 3
    assert settings.provider_failure_threshold == 4
    assert settings.provider_recovery_seconds == 45
    assert settings.dns_timeout_seconds == 4
    assert settings.max_pdf_pages == 25
    assert settings.searxng_fallback_urls == [
        "https://one.example",
        "https://two.example",
    ]
    assert settings.quality_primary_provider_share == 0.6


def test_settings_reject_unknown_provider() -> None:
    with pytest.raises(ValidationError, match="unknown providers"):
        Settings(enabled_providers=["unknown"])


def test_settings_default_to_self_hosted_zero_key_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVIDENCEMESH_PROVIDERS", raising=False)
    assert Settings.from_env().enabled_providers == [
        "searxng",
        "ddgs",
        "wikipedia",
        "crossref",
        "arxiv",
        "github",
    ]


def test_settings_quality_profile_adds_optional_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVIDENCEMESH_PROVIDERS", raising=False)
    monkeypatch.setenv("EVIDENCEMESH_DEPLOYMENT_PROFILE", "quality")
    settings = Settings.from_env()
    assert settings.deployment_profile is DeploymentProfile.QUALITY
    assert settings.enabled_providers == [
        "searxng",
        "ddgs",
        "wikipedia",
        "crossref",
        "arxiv",
        "github",
        "tavily",
    ]


def test_explicit_provider_list_overrides_deployment_profile() -> None:
    settings = Settings(
        deployment_profile=DeploymentProfile.QUALITY,
        enabled_providers=["github"],
    )
    assert settings.enabled_providers == ["github"]


def test_settings_reject_invalid_boolean_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVIDENCEMESH_RESPECT_ROBOTS_TXT", "treu")
    with pytest.raises(ValueError, match="must be a boolean"):
        Settings.from_env()
