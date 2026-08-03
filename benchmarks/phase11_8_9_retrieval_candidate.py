"""Deterministic, answer-blind Phase 11.8.9 retrieval candidate.

This engineering-only module operates on provider results that have already
been obtained.  It performs no I/O and imports only the Python standard
library.  Query-derived lexical anchors, reciprocal-rank fusion and a bounded
diversity-aware selector are intentionally transparent and reproducible.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import TypeAlias
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CANDIDATE_FAMILY = "query_anchor_diversity_rrf_v3"
BASELINE_FAMILY = "uniform_lexical_rrf_v1"
FUNNEL_SCHEMA = "phase11.8.9-funnel-v1"
PROJECTION_FAMILY = "source_preserving_anchor_pack_v3"
PROJECTION_SCHEMA = "phase11.8.9-projection-v1"
OMISSION_SEPARATOR = " … "

MetadataScalar: TypeAlias = str | int | bool | None
FrozenMetadata: TypeAlias = tuple[tuple[str, MetadataScalar], ...]

_TOKEN = re.compile(r"[\w]+(?:[.+/#\N{HYPHEN-MINUS}][\w]+)*", re.UNICODE)
_TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref_src",
    }
)
_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "after",
        "an",
        "and",
        "are",
        "as",
        "at",
        "au",
        "aux",
        "avec",
        "be",
        "before",
        "by",
        "ce",
        "ces",
        "dans",
        "de",
        "des",
        "do",
        "does",
        "du",
        "en",
        "est",
        "et",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "la",
        "le",
        "les",
        "of",
        "on",
        "or",
        "par",
        "pour",
        "que",
        "quel",
        "quelle",
        "qui",
        "sur",
        "the",
        "to",
        "un",
        "une",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
    }
)
_MULTIPART_SUFFIXES = frozenset(
    {
        "ac.uk",
        "co.jp",
        "co.uk",
        "com.au",
        "com.br",
        "com.ng",
        "gov.uk",
        "org.uk",
    }
)


@dataclass(frozen=True, slots=True)
class RawResult:
    """Immutable provider observation used by the offline candidate."""

    result_id: str
    title: str
    url: str
    snippet: str
    provider: str
    rank: int
    query: str
    source_type: str = "web"
    provider_score_micros: int | None = None
    metadata: FrozenMetadata = ()


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    """Lossless provider lineage, retained in original arrival order."""

    result_id: str
    provider: str
    rank: int
    query: str
    source_type: str
    provider_score_micros: int | None
    metadata: FrozenMetadata
    input_order: int


@dataclass(frozen=True, slots=True)
class FusedResult:
    """One canonical document with ordered, immutable provider lineage."""

    canonical_url: str
    domain: str
    title: str
    url: str
    snippet: str
    source_type: str
    representative_result_id: str
    raw_result_ids: tuple[str, ...]
    providers: tuple[str, ...]
    provider_ranks: tuple[tuple[str, int], ...]
    matched_queries: tuple[str, ...]
    observations: tuple[ProviderObservation, ...]
    first_input_order: int


@dataclass(frozen=True, slots=True)
class FunnelMetrics:
    """Aggregate-only stage measurements safe for public reporting."""

    raw_pool: int
    valid_raw: int
    fused: int
    eligible: int
    selected: int
    invalid_raw: int
    collapsed_duplicates: int
    selected_distinct_domains: int
    selected_distinct_providers: int
    selected_distinct_source_types: int
    query_terms: int
    protected_query_terms: int
    protected_terms_present_in_eligible: int
    protected_terms_present_in_selected: int


@dataclass(frozen=True, slots=True)
class SelectionOutcome:
    """Selected documents plus a privacy-safe aggregate funnel."""

    family: str
    selected: tuple[FusedResult, ...]
    funnel: FunnelMetrics


@dataclass(frozen=True, slots=True)
class ProjectedEvidence:
    """One source-preserving prompt block with a stable local citation."""

    citation_id: str
    title: str
    url: str
    text: str
    providers: tuple[str, ...]
    provider_ranks: tuple[tuple[str, int], ...]
    source_type: str


@dataclass(frozen=True, slots=True)
class ProjectionMetrics:
    """Aggregate-only measurements for the selected-to-projected funnel."""

    selected_input_documents: int
    nonempty_source_documents: int
    projected_documents: int
    documents_with_nonzero_text: int
    dropped_for_header_budget: int
    documents_with_query_anchor: int
    rendered_chars: int
    budget_chars: int
    unused_budget_chars: int


@dataclass(frozen=True, slots=True)
class ProjectionOutcome:
    """Projected prompt evidence plus aggregate public metrics."""

    family: str
    evidence: tuple[ProjectedEvidence, ...]
    metrics: ProjectionMetrics


@dataclass(frozen=True, slots=True)
class _QueryTerm:
    value: str
    weight: int
    protected: bool
    document_frequency: int


@dataclass(frozen=True, slots=True)
class _ScoredResult:
    result: FusedResult
    score: int
    covered_terms: frozenset[str]
    title_terms: frozenset[str]


@dataclass(slots=True)
class _MutableAggregate:
    canonical_url: str
    domain: str
    observations: list[ProviderObservation]
    raw_results: list[tuple[int, RawResult]]


def freeze_metadata(value: object) -> FrozenMetadata:
    """Convert a flat JSON-style mapping into an ordered immutable tuple."""

    if value is None:
        return ()
    if not isinstance(value, dict):
        raise TypeError("metadata must be a mapping")
    frozen: list[tuple[str, MetadataScalar]] = []
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("metadata keys must be strings")
        if item is not None and not isinstance(item, (str, int, bool)):
            raise TypeError("metadata values must be scalar")
        frozen.append((key, item))
    return tuple(frozen)


def _normalise_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _text_or_empty(value: object) -> str:
    """Return text unchanged and treat malformed non-text content as empty."""

    return value if isinstance(value, str) else ""


def _well_formed_content(value: object) -> bool:
    """Accept non-empty Unicode text without embedded control/surrogate codepoints."""

    if not isinstance(value, str) or not value.strip():
        return False
    return all(
        character in "\t\n\r" or unicodedata.category(character) not in {"Cc", "Cs"}
        for character in value
    )


def _raw_tokens(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(unicodedata.normalize("NFKC", value)))


def _normalised_tokens(value: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in _raw_tokens(value))


def _canonicalize_url(value: str) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.casefold()
    hostname = (parts.hostname or "").casefold().rstrip(".")
    if scheme not in {"http", "https"} or not hostname:
        return None
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return None

    host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query_pairs = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_pairs))
    canonical = urlunsplit((scheme, netloc, path, query, ""))
    return canonical, hostname


def _domain_key(hostname: str) -> str:
    labels = [label for label in hostname.split(".") if label]
    if len(labels) <= 2:
        return hostname
    final_two = ".".join(labels[-2:])
    if final_two in _MULTIPART_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return final_two


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def _query_seed_terms(query: str) -> tuple[tuple[str, bool], ...]:
    terms: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for raw in _raw_tokens(query):
        value = raw.casefold()
        contains_digit = any(character.isdigit() for character in raw)
        acronym = len(raw) >= 2 and raw.isupper() and any(character.isalpha() for character in raw)
        proper_case = (
            len(raw) >= 3
            and raw[:1].isupper()
            and any(character.islower() for character in raw[1:])
        )
        if value in seen or value in _STOPWORDS:
            continue
        if len(value) < 2 and not contains_digit and not acronym:
            continue
        seen.add(value)
        terms.append((value, contains_digit or acronym or proper_case))
    return tuple(terms)


def _contains_term(value: str, term: str) -> bool:
    return _term_pattern(term).search(_normalise_text(value)) is not None


def _representative_score(result: RawResult, query_terms: tuple[str, ...]) -> tuple[int, ...]:
    raw_title = _text_or_empty(result.title)
    raw_snippet = _text_or_empty(result.snippet)
    title = _normalise_text(raw_title)
    snippet = _normalise_text(raw_snippet)
    title_hits = sum(_contains_term(title, term) for term in query_terms)
    snippet_hits = sum(_contains_term(snippet, term) for term in query_terms)
    return (
        title_hits,
        snippet_hits,
        len(raw_snippet.strip()),
        -result.rank,
    )


def _validate_raw_results(raw_results: tuple[RawResult, ...], query: str) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty")
    identifiers = [result.result_id for result in raw_results]
    if any(not isinstance(identifier, str) or not identifier.strip() for identifier in identifiers):
        raise ValueError("result identifiers must be non-empty")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("result identifiers must be unique")
    for result in raw_results:
        if not isinstance(result.provider, str) or not result.provider.strip():
            raise ValueError("providers must be non-empty")
        if isinstance(result.rank, bool) or not isinstance(result.rank, int) or result.rank < 1:
            raise ValueError("provider ranks must be positive")
        if not isinstance(result.query, str) or not result.query.strip():
            raise ValueError("provider queries must be non-empty")


def _fuse_with_counts(
    raw_results: tuple[RawResult, ...],
    query: str,
) -> tuple[tuple[FusedResult, ...], int]:
    _validate_raw_results(raw_results, query)
    aggregates: dict[str, _MutableAggregate] = {}
    invalid_raw = 0
    for input_order, result in enumerate(raw_results):
        canonical = _canonicalize_url(result.url)
        if canonical is None:
            invalid_raw += 1
            continue
        canonical_url, hostname = canonical
        observation = ProviderObservation(
            result_id=result.result_id,
            provider=result.provider,
            rank=result.rank,
            query=result.query,
            source_type=result.source_type,
            provider_score_micros=result.provider_score_micros,
            metadata=result.metadata,
            input_order=input_order,
        )
        aggregate = aggregates.get(canonical_url)
        if aggregate is None:
            aggregate = _MutableAggregate(
                canonical_url=canonical_url,
                domain=_domain_key(hostname),
                observations=[],
                raw_results=[],
            )
            aggregates[canonical_url] = aggregate
        aggregate.observations.append(observation)
        aggregate.raw_results.append((input_order, result))

    query_terms = tuple(value for value, _protected in _query_seed_terms(query))
    fused: list[FusedResult] = []
    for aggregate in aggregates.values():
        representative_order, representative = max(
            aggregate.raw_results,
            key=lambda item: (*_representative_score(item[1], query_terms), -item[0]),
        )
        del representative_order
        representative_title = _text_or_empty(representative.title)
        representative_snippet = _text_or_empty(representative.snippet)
        providers: list[str] = []
        provider_ranks: dict[str, int] = {}
        matched_queries: list[str] = []
        source_types: list[str] = []
        for observation in aggregate.observations:
            if observation.provider not in providers:
                providers.append(observation.provider)
            provider_ranks[observation.provider] = min(
                provider_ranks.get(observation.provider, observation.rank),
                observation.rank,
            )
            if observation.query not in matched_queries:
                matched_queries.append(observation.query)
            if observation.source_type not in source_types:
                source_types.append(observation.source_type)
        source_type = representative.source_type or source_types[0]
        fused.append(
            FusedResult(
                canonical_url=aggregate.canonical_url,
                domain=aggregate.domain,
                title=representative_title.strip(),
                url=representative.url,
                snippet=representative_snippet.strip(),
                source_type=source_type,
                representative_result_id=representative.result_id,
                raw_result_ids=tuple(item.result_id for _order, item in aggregate.raw_results),
                providers=tuple(providers),
                provider_ranks=tuple(
                    (provider, provider_ranks[provider]) for provider in providers
                ),
                matched_queries=tuple(matched_queries),
                observations=tuple(aggregate.observations),
                first_input_order=aggregate.observations[0].input_order,
            )
        )
    return tuple(fused), invalid_raw


def fuse_results(raw_results: tuple[RawResult, ...], query: str) -> tuple[FusedResult, ...]:
    """Fuse canonical duplicates while retaining ordered provider observations."""

    fused, _invalid_raw = _fuse_with_counts(raw_results, query)
    return fused


def _build_query_model(
    query: str,
    fused_results: tuple[FusedResult, ...],
) -> tuple[_QueryTerm, ...]:
    seeds = _query_seed_terms(query)
    document_frequencies: Counter[str] = Counter()
    for result in fused_results:
        searchable = f"{result.title}\n{result.snippet}"
        document_frequencies.update(
            value for value, _protected in seeds if _contains_term(searchable, value)
        )

    document_count = max(1, len(fused_results))
    terms: list[_QueryTerm] = []
    for value, structural_protection in seeds:
        frequency = document_frequencies[value]
        rare = frequency > 0 and (frequency * 4 <= document_count)
        rarity_weight = ((document_count + 1) * 4_096) // (frequency + 1)
        weight = 1_024 + rarity_weight
        if structural_protection:
            weight += 5_120
        elif rare:
            weight += 3_072
        terms.append(
            _QueryTerm(
                value=value,
                weight=weight,
                protected=structural_protection or rare,
                document_frequency=frequency,
            )
        )
    return tuple(terms)


def _ordered_pair_hits(value: str, terms: tuple[_QueryTerm, ...]) -> int:
    tokens = _normalised_tokens(value)
    positions: dict[str, list[int]] = {term.value: [] for term in terms}
    for index, token in enumerate(tokens):
        if token in positions:
            positions[token].append(index)
    hits = 0
    for left, right in pairwise(terms):
        if any(
            0 < right_position - left_position <= 4
            for left_position in positions[left.value]
            for right_position in positions[right.value]
        ):
            hits += 1
    return hits


def _score_result(result: FusedResult, terms: tuple[_QueryTerm, ...]) -> _ScoredResult:
    title_terms = frozenset(
        term.value for term in terms if _contains_term(result.title, term.value)
    )
    snippet_terms = frozenset(
        term.value for term in terms if _contains_term(result.snippet, term.value)
    )
    covered = title_terms | snippet_terms
    lexical = sum(
        term.weight
        * ((4 if term.value in title_terms else 0) + (2 if term.value in snippet_terms else 0))
        for term in terms
    )
    protected = sum(term.weight for term in terms if term.protected and term.value in covered)
    total_weight = sum(term.weight for term in terms)
    covered_weight = sum(term.weight for term in terms if term.value in covered)
    coverage = (covered_weight * 80_000 // total_weight) if total_weight else 0
    pair_bonus = 8_000 * (
        _ordered_pair_hits(result.title, terms) + _ordered_pair_hits(result.snippet, terms)
    )
    reciprocal_rank = sum(
        1_000_000 // (60 + min(rank, 10_000)) for _provider, rank in result.provider_ranks
    )
    provider_corroboration = max(0, len(result.providers) - 1) * 4_000
    score = (
        (lexical * 6)
        + (protected * 4)
        + coverage
        + pair_bonus
        + reciprocal_rank
        + provider_corroboration
    )
    return _ScoredResult(
        result=result,
        score=score,
        covered_terms=covered,
        title_terms=title_terms,
    )


def _baseline_score(result: FusedResult, query: str) -> int:
    query_terms = frozenset(
        token for token in _normalised_tokens(query) if token not in _STOPWORDS and len(token) >= 2
    )
    title_terms = frozenset(_normalised_tokens(result.title))
    snippet_terms = frozenset(_normalised_tokens(result.snippet))
    if query_terms:
        title_overlap = len(query_terms & title_terms) * 65_000 // len(query_terms)
        snippet_overlap = len(query_terms & snippet_terms) * 35_000 // len(query_terms)
    else:
        title_overlap = 0
        snippet_overlap = 0
    reciprocal_rank = sum(
        1_000_000 // (60 + min(rank, 10_000)) for _provider, rank in result.provider_ranks
    )
    return title_overlap + snippet_overlap + reciprocal_rank


def _title_similarity(left: str, right: str) -> int:
    left_tokens = frozenset(_normalised_tokens(left))
    right_tokens = frozenset(_normalised_tokens(right))
    union = left_tokens | right_tokens
    return (len(left_tokens & right_tokens) * 1_000 // len(union)) if union else 0


def _validate_selection_arguments(limit: int, max_per_domain: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    if (
        isinstance(max_per_domain, bool)
        or not isinstance(max_per_domain, int)
        or max_per_domain < 1
    ):
        raise ValueError("max_per_domain must be positive")


def _eligible(results: tuple[FusedResult, ...]) -> tuple[FusedResult, ...]:
    return tuple(
        result
        for result in results
        if _well_formed_content(result.title)
        and _well_formed_content(result.snippet)
        and bool(result.providers)
    )


def _funnel(
    *,
    raw_results: tuple[RawResult, ...],
    invalid_raw: int,
    fused: tuple[FusedResult, ...],
    eligible: tuple[FusedResult, ...],
    selected: tuple[FusedResult, ...],
    terms: tuple[_QueryTerm, ...],
) -> FunnelMetrics:
    protected = frozenset(term.value for term in terms if term.protected)
    eligible_text = "\n".join(f"{result.title}\n{result.snippet}" for result in eligible)
    selected_text = "\n".join(f"{result.title}\n{result.snippet}" for result in selected)
    selected_providers = {provider for result in selected for provider in result.providers}
    return FunnelMetrics(
        raw_pool=len(raw_results),
        valid_raw=len(raw_results) - invalid_raw,
        fused=len(fused),
        eligible=len(eligible),
        selected=len(selected),
        invalid_raw=invalid_raw,
        collapsed_duplicates=max(0, len(raw_results) - invalid_raw - len(fused)),
        selected_distinct_domains=len({result.domain for result in selected}),
        selected_distinct_providers=len(selected_providers),
        selected_distinct_source_types=len({result.source_type for result in selected}),
        query_terms=len(terms),
        protected_query_terms=len(protected),
        protected_terms_present_in_eligible=sum(
            _contains_term(eligible_text, term) for term in protected
        ),
        protected_terms_present_in_selected=sum(
            _contains_term(selected_text, term) for term in protected
        ),
    )


def select_baseline(
    raw_results: tuple[RawResult, ...],
    query: str,
    *,
    limit: int,
    max_per_domain: int,
) -> SelectionOutcome:
    """Select with a uniform lexical/RRF baseline and a hard domain cap."""

    _validate_selection_arguments(limit, max_per_domain)
    fused, invalid_raw = _fuse_with_counts(raw_results, query)
    eligible = _eligible(fused)
    ordered = sorted(
        eligible,
        key=lambda result: (
            -_baseline_score(result, query),
            result.first_input_order,
            result.canonical_url,
        ),
    )
    selected: list[FusedResult] = []
    domain_counts: Counter[str] = Counter()
    for result in ordered:
        if domain_counts[result.domain] >= max_per_domain:
            continue
        selected.append(result)
        domain_counts[result.domain] += 1
        if len(selected) >= limit:
            break
    terms = _build_query_model(query, fused)
    selected_tuple = tuple(selected)
    return SelectionOutcome(
        family=BASELINE_FAMILY,
        selected=selected_tuple,
        funnel=_funnel(
            raw_results=raw_results,
            invalid_raw=invalid_raw,
            fused=fused,
            eligible=eligible,
            selected=selected_tuple,
            terms=terms,
        ),
    )


def select_candidate_v3(
    raw_results: tuple[RawResult, ...],
    query: str,
    *,
    limit: int,
    max_per_domain: int,
) -> SelectionOutcome:
    """Select query-anchored evidence with bounded source/domain diversity."""

    _validate_selection_arguments(limit, max_per_domain)
    fused, invalid_raw = _fuse_with_counts(raw_results, query)
    eligible = _eligible(fused)
    terms = _build_query_model(query, fused)
    remaining = [_score_result(result, terms) for result in eligible]
    selected: list[_ScoredResult] = []
    domain_counts: Counter[str] = Counter()
    selected_providers: set[str] = set()
    selected_source_types: set[str] = set()
    covered_terms: set[str] = set()
    term_weights = {term.value: term.weight for term in terms}

    while remaining and len(selected) < limit:
        feasible = [
            item for item in remaining if domain_counts[item.result.domain] < max_per_domain
        ]
        if not feasible:
            break

        def marginal_score(item: _ScoredResult) -> tuple[int, int, int, str]:
            unseen_terms = item.covered_terms - covered_terms
            anchor_gain = sum(term_weights[term] for term in unseen_terms) * 5
            new_providers = set(item.result.providers) - selected_providers
            provider_gain = min(2, len(new_providers)) * 6_000
            source_gain = 7_000 if item.result.source_type not in selected_source_types else 0
            domain_gain = 18_000 if domain_counts[item.result.domain] == 0 else 0
            domain_penalty = domain_counts[item.result.domain] * 115_000
            similarity_penalty = max(
                (
                    _title_similarity(item.result.title, chosen.result.title) * 24
                    for chosen in selected
                ),
                default=0,
            )
            marginal = (
                item.score
                + anchor_gain
                + provider_gain
                + source_gain
                + domain_gain
                - domain_penalty
                - similarity_penalty
            )
            return (
                marginal,
                item.score,
                -item.result.first_input_order,
                item.result.canonical_url,
            )

        chosen = max(feasible, key=marginal_score)
        selected.append(chosen)
        remaining.remove(chosen)
        domain_counts[chosen.result.domain] += 1
        selected_providers.update(chosen.result.providers)
        selected_source_types.add(chosen.result.source_type)
        covered_terms.update(chosen.covered_terms)

    selected_tuple = tuple(item.result for item in selected)
    return SelectionOutcome(
        family=CANDIDATE_FAMILY,
        selected=selected_tuple,
        funnel=_funnel(
            raw_results=raw_results,
            invalid_raw=invalid_raw,
            fused=fused,
            eligible=eligible,
            selected=selected_tuple,
            terms=terms,
        ),
    )


def canonical_funnel_json(outcome: SelectionOutcome) -> str:
    """Serialize only aggregate funnel data in a canonical public form."""

    payload = {
        "family": outcome.family,
        "funnel": asdict(outcome.funnel),
        "schema": FUNNEL_SCHEMA,
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_funnel_sha256(outcome: SelectionOutcome) -> str:
    """Hash the canonical aggregate funnel serialization."""

    return hashlib.sha256(canonical_funnel_json(outcome).encode("utf-8")).hexdigest()


def evidence_header(evidence: ProjectedEvidence) -> str:
    """Render the immutable header used for exact prompt budgeting."""

    return f"[{evidence.citation_id}] {evidence.title}\nURL: {evidence.url}\nEvidence: "


def rendered_projection_chars(evidence: tuple[ProjectedEvidence, ...]) -> int:
    """Return exact rendered characters, including inter-document separators."""

    if not evidence:
        return 0
    citation_ids = tuple(item.citation_id for item in evidence)
    if any(not citation_id.strip() for citation_id in citation_ids):
        raise ValueError("projection citation identifiers must be non-empty")
    if len(citation_ids) != len(set(citation_ids)):
        raise ValueError("projection citation identifiers must be unique")
    return sum(len(evidence_header(item)) + len(item.text) for item in evidence) + (
        2 * (len(evidence) - 1)
    )


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _window_around(text_length: int, focus: int, width: int) -> tuple[int, int]:
    width = min(text_length, max(1, width))
    start = min(max(0, focus - (width // 2)), text_length - width)
    return start, start + width


def _best_anchor_focus(text: str, query: str) -> int | None:
    seed_terms = tuple(value for value, _protected in _query_seed_terms(query))
    positions: list[tuple[int, str]] = []
    normalised = _normalise_text(text)
    for term in seed_terms:
        positions.extend(
            (match.start(), term) for match in _term_pattern(term).finditer(normalised)
        )
    if not positions:
        return None
    positions.sort()
    best_position = positions[0][0]
    best_score = (-1, -1, 0)
    radius = max(48, min(256, len(text) // 3))
    for position, _term in positions:
        left = max(0, position - radius)
        right = min(len(text), position + radius)
        window_terms = {term for item_position, term in positions if left <= item_position < right}
        occurrences = sum(left <= item_position < right for item_position, _term in positions)
        score = (len(window_terms), occurrences, -position)
        if score > best_score:
            best_position = position
            best_score = score
    return best_position


def _range_cost(ranges: list[tuple[int, int]]) -> int:
    merged = _merge_ranges(ranges)
    return sum(end - start for start, end in merged) + (
        len(OMISSION_SEPARATOR) * max(0, len(merged) - 1)
    )


def _compact_source_text(text: str, query: str, cap_chars: int) -> str:
    clean = text.strip()
    if cap_chars <= 0 or not clean:
        return ""
    if len(clean) <= cap_chars:
        return clean
    if cap_chars < 24:
        return clean[:cap_chars]

    separator_budget = 2 * len(OMISSION_SEPARATOR)
    usable = max(1, cap_chars - separator_budget)
    head_width = max(1, usable * 30 // 100)
    tail_width = max(1, usable * 20 // 100)
    focus_width = max(1, usable - head_width - tail_width)
    focus = _best_anchor_focus(clean, query)
    if focus is None:
        focus = len(clean) // 2
    ranges = [
        (0, head_width),
        _window_around(len(clean), focus, focus_width),
        (len(clean) - tail_width, len(clean)),
    ]
    while _range_cost(ranges) > cap_chars and focus_width > 1:
        focus_width -= 1
        ranges[1] = _window_around(len(clean), focus, focus_width)
    segments = [
        clean[start:end].strip() for start, end in _merge_ranges(ranges) if clean[start:end].strip()
    ]
    compacted = OMISSION_SEPARATOR.join(segments)
    if len(compacted) > cap_chars:
        raise AssertionError("source-preserving compaction exceeded its assigned cap")
    return compacted


def _projection_header_chars(
    selected: tuple[FusedResult, ...],
) -> int:
    headers = sum(
        len(f"[S{index}] {result.title}\nURL: {result.url}\nEvidence: ")
        for index, result in enumerate(selected, start=1)
    )
    return headers + (2 * max(0, len(selected) - 1))


def _projection_caps(
    selected: tuple[FusedResult, ...],
    text_budget: int,
    *,
    min_document_chars: int,
    max_document_chars: int,
) -> list[int]:
    desired = [min(len(result.snippet.strip()), max_document_chars) for result in selected]
    if not desired:
        return []
    floor = max(1, min(min_document_chars, text_budget // len(selected)))
    caps = [min(item, floor) for item in desired]
    remaining = text_budget - sum(caps)
    while remaining > 0:
        eligible = [index for index, cap in enumerate(caps) if cap < desired[index]]
        if not eligible:
            break
        for index in eligible:
            grant = min(64, desired[index] - caps[index], remaining)
            caps[index] += grant
            remaining -= grant
            if remaining == 0:
                break
    return caps


def project_selected_v3(
    selected: tuple[FusedResult, ...],
    query: str,
    *,
    budget_chars: int,
    max_document_chars: int,
    min_document_chars: int = 96,
) -> ProjectionOutcome:
    """Project selected snippets under an exact, answer-blind character budget."""

    if not query.strip():
        raise ValueError("query must be non-empty")
    if budget_chars < 1:
        raise ValueError("budget_chars must be positive")
    if max_document_chars < 1:
        raise ValueError("max_document_chars must be positive")
    if min_document_chars < 1 or min_document_chars > max_document_chars:
        raise ValueError(
            "min_document_chars must be positive and no larger than max_document_chars"
        )

    nonempty = tuple(result for result in selected if result.snippet.strip())
    projectable = nonempty
    while projectable and (_projection_header_chars(projectable) + len(projectable) > budget_chars):
        projectable = projectable[:-1]

    header_chars = _projection_header_chars(projectable)
    caps = _projection_caps(
        projectable,
        max(0, budget_chars - header_chars),
        min_document_chars=min_document_chars,
        max_document_chars=max_document_chars,
    )
    evidence = tuple(
        ProjectedEvidence(
            citation_id=f"S{index}",
            title=result.title,
            url=result.url,
            text=_compact_source_text(result.snippet, query, cap),
            providers=result.providers,
            provider_ranks=result.provider_ranks,
            source_type=result.source_type,
        )
        for index, (result, cap) in enumerate(
            zip(projectable, caps, strict=True),
            start=1,
        )
    )
    rendered_chars = rendered_projection_chars(evidence)
    if rendered_chars > budget_chars:
        raise AssertionError("v3 projection exceeded its exact rendered budget")
    metrics = ProjectionMetrics(
        selected_input_documents=len(selected),
        nonempty_source_documents=len(nonempty),
        projected_documents=len(evidence),
        documents_with_nonzero_text=sum(bool(item.text) for item in evidence),
        dropped_for_header_budget=len(nonempty) - len(projectable),
        documents_with_query_anchor=sum(
            any(_contains_term(item.text, term) for term, _protected in _query_seed_terms(query))
            for item in evidence
        ),
        rendered_chars=rendered_chars,
        budget_chars=budget_chars,
        unused_budget_chars=budget_chars - rendered_chars,
    )
    return ProjectionOutcome(
        family=PROJECTION_FAMILY,
        evidence=evidence,
        metrics=metrics,
    )


def canonical_projection_json(outcome: ProjectionOutcome) -> str:
    """Serialize projection metrics without titles, URLs, snippets or query terms."""

    payload = {
        "family": outcome.family,
        "metrics": asdict(outcome.metrics),
        "schema": PROJECTION_SCHEMA,
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_projection_sha256(outcome: ProjectionOutcome) -> str:
    """Hash the canonical aggregate projection serialization."""

    return hashlib.sha256(canonical_projection_json(outcome).encode("utf-8")).hexdigest()
