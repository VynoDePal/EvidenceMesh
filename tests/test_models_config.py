from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from evidencemesh.config import Settings
from evidencemesh.models import FetchRequest, ResearchRequest, SearchRequest


def test_search_request_normalises_domains_and_variants() -> None:
    request = SearchRequest(
        query="example query",
        domains=["Example.COM.", "example.com"],
        query_variants=[" second query ", "second query"],
    )
    assert request.domains == ["example.com"]
    assert request.query_variants == ["second query"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("query", "x"),
        ("language", "english"),
        ("domains", ["https://example.com"]),
        ("domains", ["bad..example"]),
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
    settings = Settings.from_env()
    assert settings.enabled_providers == ["ddgs", "wikipedia"]
    assert settings.cache_path == cache_path
    assert settings.allow_private_networks is True
    assert settings.respect_robots_txt is False
    assert settings.max_concurrency == 3


def test_settings_reject_unknown_provider() -> None:
    with pytest.raises(ValidationError, match="unknown providers"):
        Settings(enabled_providers=["unknown"])
