from __future__ import annotations

import pytest

from benchmarks.target_identity import (
    identities_for_url,
    target_matches_url,
    validate_target_identity,
)


@pytest.mark.parametrize(
    ("url", "identity"),
    [
        ("https://github.com/FastAPI/FastAPI/", "github:fastapi/fastapi"),
        ("https://github.com/fastapi/fastapi.git", "github:fastapi/fastapi"),
        ("https://en.wikipedia.org/wiki/Katherine_Johnson", "wikipedia:en:katherine_johnson"),
        ("http://arxiv.org/abs/2103.00020v1", "arxiv:2103.00020"),
        ("https://arxiv.org/pdf/2103.00020.pdf", "arxiv:2103.00020"),
        ("https://doi.org/10.48550/arXiv.2103.00020", "arxiv:2103.00020"),
    ],
)
def test_identities_for_url_recognises_source_aliases(url: str, identity: str) -> None:
    assert identity in identities_for_url(url)


def test_target_matches_url_accepts_subdomains_for_domain_identity() -> None:
    assert target_matches_url(
        ["domain:noaa.gov"],
        "https://www.noaa.gov/climate",
    )


def test_target_matches_url_rejects_near_matches() -> None:
    assert not target_matches_url(
        ["github:fastapi/fastapi"],
        "https://github.com/fastapi/typer",
    )
    assert not target_matches_url(
        ["domain:noaa.gov"],
        "https://noaa.gov.example.com/",
    )


@pytest.mark.parametrize(
    "identity",
    [
        "unknown:value",
        "domain:https://example.com",
        "github:missing-repository",
        "arxiv:",
        "wikipedia:en",
    ],
)
def test_validate_target_identity_rejects_invalid_values(identity: str) -> None:
    with pytest.raises(ValueError):
        validate_target_identity(identity)
