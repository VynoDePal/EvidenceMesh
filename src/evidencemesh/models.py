"""Typed public contracts shared by the SDK, CLI and MCP server."""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchProfile(StrEnum):
    WEB = "web"
    REFERENCE = "reference"
    NEWS = "news"
    ACADEMIC = "academic"
    CODE = "code"


class SearchDepth(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class SafeSearch(StrEnum):
    OFF = "off"
    MODERATE = "moderate"
    STRICT = "strict"


class TimeRange(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class SourceType(StrEnum):
    WEB = "web"
    NEWS = "news"
    ACADEMIC = "academic"
    CODE = "code"
    REFERENCE = "reference"
    PDF = "pdf"


class SourceFamilyStatus(StrEnum):
    """Outcome of the source family required by a search profile."""

    SATISFIED = "satisfied"
    EMPTY = "empty"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


Domain = Annotated[str, Field(min_length=1, max_length=253)]
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _normalise_domain(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if "://" in value or "/" in value or "@" in value:
        raise ValueError("domains must be hostnames without a scheme, path or user information")
    if not value or any(not part for part in value.split(".")):
        raise ValueError("invalid domain")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        try:
            value = value.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("invalid internationalized domain") from exc
        if len(value) > 253 or any(not _DOMAIN_LABEL.fullmatch(part) for part in value.split(".")):
            raise ValueError("invalid domain") from None
        return value
    if isinstance(address, ipaddress.IPv6Address):
        raise ValueError("IPv6 addresses are not accepted as domain filters")
    return address.compressed


class SearchRequest(StrictModel):
    query: Annotated[str, Field(min_length=2, max_length=512)]
    limit: Annotated[int, Field(ge=1, le=50)] = 10
    profile: SearchProfile = SearchProfile.WEB
    language: Annotated[str, Field(pattern=r"^[A-Za-z]{2,3}(-[A-Za-z]{2})?$")] = "en"
    safe_search: SafeSearch = SafeSearch.MODERATE
    time_range: TimeRange | None = None
    domains: list[Domain] = Field(default_factory=list, max_length=20)
    exclude_domains: list[Domain] = Field(default_factory=list, max_length=20)
    query_variants: list[Annotated[str, Field(min_length=2, max_length=512)]] = Field(
        default_factory=list,
        max_length=8,
    )
    fetch_content: bool = False
    content_budget_chars: Annotated[int, Field(ge=1_000, le=200_000)] = 30_000
    max_per_domain: Annotated[int, Field(ge=1, le=10)] = 3
    use_cache: bool = True

    @field_validator("domains", "exclude_domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_normalise_domain(value) for value in values))

    @field_validator("query_variants")
    @classmethod
    def deduplicate_variants(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values))

    @model_validator(mode="after")
    def validate_domain_sets(self) -> SearchRequest:
        overlap = set(self.domains) & set(self.exclude_domains)
        if overlap:
            raise ValueError(f"domains cannot be both included and excluded: {sorted(overlap)}")
        return self


class ResearchRequest(StrictModel):
    question: Annotated[str, Field(min_length=4, max_length=2_000)]
    depth: SearchDepth = SearchDepth.STANDARD
    profile: SearchProfile = SearchProfile.WEB
    language: Annotated[str, Field(pattern=r"^[A-Za-z]{2,3}(-[A-Za-z]{2})?$")] = "en"
    safe_search: SafeSearch = SafeSearch.MODERATE
    max_sources: Annotated[int, Field(ge=3, le=50)] = 12
    content_budget_chars: Annotated[int, Field(ge=3_000, le=300_000)] = 60_000
    domains: list[Domain] = Field(default_factory=list, max_length=20)
    exclude_domains: list[Domain] = Field(default_factory=list, max_length=20)
    subqueries: list[Annotated[str, Field(min_length=2, max_length=512)]] = Field(
        default_factory=list,
        max_length=12,
    )
    use_cache: bool = True

    @field_validator("domains", "exclude_domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_normalise_domain(value) for value in values))

    @field_validator("subqueries")
    @classmethod
    def deduplicate_subqueries(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values))

    @model_validator(mode="after")
    def validate_domain_sets(self) -> ResearchRequest:
        overlap = set(self.domains) & set(self.exclude_domains)
        if overlap:
            raise ValueError(f"domains cannot be both included and excluded: {sorted(overlap)}")
        return self


class FetchRequest(StrictModel):
    url: HttpUrl
    max_chars: Annotated[int, Field(ge=500, le=200_000)] = 30_000
    use_cache: bool = True


class ProviderResult(StrictModel):
    """Provider-neutral result before fusion and citation assignment."""

    title: Annotated[str, Field(max_length=1_000)]
    url: Annotated[str, Field(min_length=1, max_length=8_192)]
    snippet: Annotated[str, Field(max_length=12_000)] = ""
    provider: Annotated[str, Field(min_length=1, max_length=64)]
    rank: Annotated[int, Field(ge=1)]
    query: Annotated[str, Field(min_length=1, max_length=512)]
    published_at: datetime | None = None
    source_type: SourceType = SourceType.WEB
    provider_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchHit(StrictModel):
    citation_id: str
    title: str
    url: str
    canonical_url: str
    snippet: str = ""
    domain: str
    providers: list[str]
    provider_ranks: dict[str, int]
    matched_queries: list[str]
    published_at: datetime | None = None
    source_type: SourceType = SourceType.WEB
    fusion_score: float = Field(ge=0.0, le=1.0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    source_signal_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    risk_flags: list[str] = Field(default_factory=list)


class FetchedDocument(StrictModel):
    url: str
    canonical_url: str
    title: str
    media_type: str
    text: str
    retrieved_at: datetime
    content_sha256: str
    content_chars: int
    truncated: bool = False
    risk_flags: list[str] = Field(default_factory=list)


class EvidenceItem(StrictModel):
    citation_id: str
    title: str
    url: str
    canonical_url: str
    quote: str
    providers: list[str]
    retrieved_at: datetime
    published_at: datetime | None = None
    content_sha256: str
    source_type: SourceType
    risk_flags: list[str] = Field(default_factory=list)


class SearchMetadata(StrictModel):
    query: str
    queries_executed: list[str]
    providers_requested: list[str]
    providers_succeeded: list[str]
    provider_failures: dict[str, str]
    deployment_profile: str = "custom"
    provider_query_counts: dict[str, int] = Field(default_factory=dict)
    provider_source_families: dict[str, str] = Field(default_factory=dict)
    required_source_family: str = SourceType.WEB.value
    required_source_family_status: SourceFamilyStatus = SourceFamilyStatus.NOT_CONFIGURED
    source_family_call_counts: dict[str, int] = Field(default_factory=dict)
    source_family_success_counts: dict[str, int] = Field(default_factory=dict)
    source_family_failure_counts: dict[str, int] = Field(default_factory=dict)
    source_family_result_counts: dict[str, int] = Field(default_factory=dict)
    degraded_source_families: list[str] = Field(default_factory=list)
    failed_source_families: list[str] = Field(default_factory=list)
    raw_result_count: int
    deduplicated_result_count: int
    elapsed_ms: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    generated_at: datetime


class SearchResponse(StrictModel):
    results: list[SearchHit]
    evidence: list[EvidenceItem]
    metadata: SearchMetadata
    warnings: list[str] = Field(default_factory=list)


class CoverageReport(StrictModel):
    unique_sources: int = Field(ge=0)
    unique_domains: int = Field(ge=0)
    queries_with_results: int = Field(ge=0)
    total_queries: int = Field(ge=1)
    extracted_sources: int = Field(ge=0)
    flagged_sources: int = Field(ge=0)


class ResearchPacket(StrictModel):
    question: str
    subqueries: list[str]
    evidence: list[EvidenceItem]
    sources: list[SearchHit]
    coverage: CoverageReport
    synthesis_protocol: list[str]
    metadata: SearchMetadata
    warnings: list[str] = Field(default_factory=list)


class ClaimReviewPacket(StrictModel):
    claim: str
    evidence: list[EvidenceItem]
    sources: list[SearchHit]
    status: str
    review_protocol: list[str]
    warnings: list[str] = Field(default_factory=list)


class BatchSearchResponse(StrictModel):
    responses: list[SearchResponse]
    failures: dict[str, str] = Field(default_factory=dict)
