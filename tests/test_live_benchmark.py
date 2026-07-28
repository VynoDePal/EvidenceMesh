from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from benchmarks.run_live_retrieval import (
    BenchmarkRow,
    Profile,
    ProviderSnapshot,
    aggregate_profile,
    answer_covered,
    extract_source_urls,
    first_answer_rank,
    first_gold_domain_rank,
    first_gold_url_rank,
    normalise,
    outcome_from_snapshots,
    paired_comparisons,
    parse_jsonl,
    parse_profiles,
    parse_simpleqa,
    provider_endpoint_manifest,
    rate_metric,
    select_sample,
    stable_row_id,
    url_identity,
)
from evidencemesh.config import Settings
from evidencemesh.models import ProviderResult, SearchHit, SourceType


def hit(rank: int, url: str, title: str = "", snippet: str = "") -> SearchHit:
    return SearchHit(
        citation_id=f"S{rank}",
        title=title or f"Result {rank}",
        url=url,
        canonical_url=url,
        snippet=snippet,
        domain=url.split("/")[2],
        providers=["stub"],
        provider_ranks={"stub": rank},
        matched_queries=["question"],
        published_at=datetime(2025, 1, 1, tzinfo=UTC),
        source_type=SourceType.WEB,
        fusion_score=1.0,
        relevance_score=0.5,
        source_signal_score=0.5,
        final_score=0.7,
    )


def outcome(
    profile: str,
    row_id: str,
    *,
    answer_rank: int | None,
    gold_url_rank: int | None,
    gold_domain_rank: int | None,
) -> dict[str, object]:
    return {
        "id": row_id,
        "profile": profile,
        "latency_ms": 10.0,
        "result_count": 2,
        "unique_domains": 2,
        "provider_call_count": 2,
        "provider_failure_count": 0,
        "answer_rank": answer_rank,
        "gold_url_rank": gold_url_rank,
        "gold_domain_rank": gold_domain_rank,
        "has_gold_urls": True,
        "results": [],
        "error": None,
    }


def test_normalisation_and_coverage() -> None:
    assert normalise("  Évidence—Mesh! ") == "evidence mesh"
    assert answer_covered(["Open standard"], ["An OPEN-standard for agents"])
    assert not answer_covered(["closed protocol"], ["An open standard"])


def test_extract_source_urls_handles_duplicates_and_malformed_suffix() -> None:
    metadata = {
        "urls": [
            "https://www.example.com/a\nhttps://example.com/a",
            "https://docs.example.org/page)",
            12,
        ]
    }
    assert extract_source_urls(metadata) == (
        "https://example.com/a",
        "https://docs.example.org/page",
    )
    assert extract_source_urls("not a dictionary") == ()
    assert url_identity("http://www.example.com/a") == url_identity("https://example.com/a")


def test_parse_simpleqa_and_deterministic_sample() -> None:
    payload = (
        b"metadata,problem,answer\n"
        b"\"{'topic': 'Science', 'answer_type': 'Person', "
        b"'urls': ['https://example.com/source']}\",Who discovered it?,Ada\n"
        b"\"{'topic': 'Art', 'answer_type': 'Place', 'urls': []}\",Where is it?,Paris\n"
    )
    rows = parse_simpleqa(payload)
    assert rows[0].id == stable_row_id("Who discovered it?")
    assert rows[0].gold_domains == ("example.com",)
    assert rows[0].topic == "Science"
    assert select_sample(rows, sample_size=1, seed=0) == select_sample(rows, sample_size=1, seed=0)
    with pytest.raises(ValueError, match="sample size exceeds"):
        select_sample(rows, sample_size=3, seed=0)


def test_parse_jsonl_validates_and_canonicalises() -> None:
    payload = (
        json.dumps(
            {
                "id": "q1",
                "question": "What is it?",
                "answer": ["Alpha", "A"],
                "gold_urls": ["https://www.example.com/a?utm_source=test"],
            }
        )
        + "\n"
    ).encode()
    rows = parse_jsonl(payload)
    assert rows == [
        BenchmarkRow(
            id="q1",
            question="What is it?",
            answers=("Alpha", "A"),
            gold_urls=("https://example.com/a",),
        )
    ]
    with pytest.raises(ValueError, match="string or string-list"):
        parse_jsonl(b'{"question":"What?","answer":[]}\n')
    with pytest.raises(ValueError, match="unique"):
        parse_jsonl(
            b'{"id":"same","question":"One?","answer":"1"}\n'
            b'{"id":"same","question":"Two?","answer":"2"}\n'
        )


def test_profile_parser_defaults_and_rejects_duplicates() -> None:
    profiles = parse_profiles(None)
    assert profiles[0] == Profile("federated", ("ddgs", "wikipedia"))
    assert parse_profiles(["custom=wikipedia,ddgs,wikipedia"])[0].providers == (
        "wikipedia",
        "ddgs",
    )
    with pytest.raises(ValueError, match="unique"):
        parse_profiles(["same=ddgs", "same=wikipedia"])
    with pytest.raises(ValueError, match="syntax"):
        parse_profiles(["broken"])


def test_provider_endpoint_manifest_is_explicit_and_secret_free() -> None:
    settings = Settings(
        enabled_providers=["ddgs", "wikipedia"],
        wikipedia_url_template="https://{language}.wikipedia.test/w/api.php",
    )
    manifest = provider_endpoint_manifest(settings, ("ddgs", "wikipedia"))
    assert manifest["wikipedia"] == "https://{language}.wikipedia.test/w/api.php"
    assert "runtime" in manifest["ddgs"]


def test_rank_metrics() -> None:
    hits = [
        hit(1, "https://other.example/page", snippet="nothing"),
        hit(2, "https://www.example.com/a", title="The Évidence answer"),
    ]
    assert first_answer_rank(("evidence",), hits) == 2
    assert first_gold_url_rank(("http://example.com/a",), hits) == 2
    assert first_gold_domain_rank(("example.com",), hits) == 2


def test_profiles_share_provider_snapshots() -> None:
    row = BenchmarkRow(
        id="q1",
        question="What is the answer?",
        answers=("Alpha",),
        gold_urls=("https://example.com/a",),
    )
    raw = ProviderResult(
        title="Alpha",
        url="https://example.com/a",
        snippet="The answer is Alpha.",
        provider="stub",
        rank=1,
        query=row.question,
    )
    snapshot = ProviderSnapshot(
        row_id=row.id,
        provider="stub",
        latency_ms=12.0,
        results=(raw,),
        error=None,
    )
    result = outcome_from_snapshots(
        row,
        Profile("only-stub", ("stub",)),
        {"stub": snapshot},
        max_results=10,
    )
    assert result["answer_rank"] == 1
    assert result["gold_url_rank"] == 1
    assert result["provider_call_count"] == 1
    assert result["latency_ms"] == 12.0


def test_rate_and_profile_aggregation() -> None:
    values = [
        outcome(
            "federated",
            "q1",
            answer_rank=1,
            gold_url_rank=2,
            gold_domain_rank=1,
        ),
        outcome(
            "federated",
            "q2",
            answer_rank=None,
            gold_url_rank=None,
            gold_domain_rank=2,
        ),
    ]
    metrics = aggregate_profile(values, max_results=2)
    assert metrics["answer_coverage_at_2"]["rate"] == 0.5
    assert metrics["gold_url_hit_at_2"]["rate"] == 0.5
    assert metrics["gold_domain_hit_at_2"]["rate"] == 1.0
    assert metrics["gold_url_mrr"] == 0.25
    assert rate_metric([])["rate"] is None


def test_paired_comparison_reports_wins_and_losses() -> None:
    profiles = [Profile("federated", ("ddgs", "wikipedia")), Profile("ddgs", ("ddgs",))]
    values = [
        outcome(
            "federated",
            "q1",
            answer_rank=1,
            gold_url_rank=1,
            gold_domain_rank=1,
        ),
        outcome(
            "ddgs",
            "q1",
            answer_rank=None,
            gold_url_rank=None,
            gold_domain_rank=None,
        ),
        outcome(
            "federated",
            "q2",
            answer_rank=None,
            gold_url_rank=None,
            gold_domain_rank=None,
        ),
        outcome(
            "ddgs",
            "q2",
            answer_rank=1,
            gold_url_rank=None,
            gold_domain_rank=1,
        ),
    ]
    comparison = paired_comparisons(profiles, values, max_results=10)[0]
    assert comparison["answer"]["left_only_hits"] == 1
    assert comparison["answer"]["right_only_hits"] == 1
    assert comparison["gold_url"]["left_only_hits"] == 1
