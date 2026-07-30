"""Deterministic, offline-only Phase 11.8.8 evidence projection candidate.

The projector receives only a question and already-selected evidence blocks.
It performs no I/O, imports no model or provider SDK, and copies source
substrings without paraphrasing them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Protocol, TypeVar

PROJECTION_FAMILY = "fair_prefix_rarity_passage_pack_v2"
OMISSION_SEPARATOR = " … "

_WORD = re.compile(
    r"[\w]+(?:['\N{RIGHT SINGLE QUOTATION MARK}-][\w]+)*",
    re.UNICODE,
)
_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "according",
        "after",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "before",
        "by",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whose",
        "why",
        "with",
        "would",
    }
)
_MAX_MATCHES_PER_TERM = 8
_PASSAGE_TARGET_CHARS = 360
_PASSAGE_BOUNDARY_LOOKAROUND = 72
_MIN_PASSAGE_CHARS = 40
_ALLOCATION_QUANTUM = 64


class EvidenceBlockLike(Protocol):
    citation_id: str
    title: str
    url: str
    text: str
    providers: tuple[str, ...]


BlockT = TypeVar("BlockT", bound=EvidenceBlockLike)


@dataclass(frozen=True, slots=True)
class _QuestionModel:
    terms: tuple[str, ...]
    weights: dict[str, int]
    ordered_pairs: tuple[tuple[str, str], ...]
    patterns: dict[str, re.Pattern[str]]


@dataclass(frozen=True, slots=True)
class _Passage:
    start: int
    end: int
    focus: int
    score: int
    anchored: bool


def evidence_header(block: EvidenceBlockLike) -> str:
    return f"[{block.citation_id}] {block.title}\nURL: {block.url}\nEvidence: "


def rendered_evidence_chars(blocks: tuple[EvidenceBlockLike, ...]) -> int:
    if not blocks:
        return 0
    return sum(len(evidence_header(block)) + len(block.text) for block in blocks) + (
        2 * (len(blocks) - 1)
    )


def _replace_text(block: BlockT, text: str) -> BlockT:
    return replace(block, text=text)  # type: ignore[return-value, type-var]


def significant_query_terms_v2(question: str) -> tuple[str, ...]:
    """Return stable, unique lexical anchors without language-model inference."""

    terms: list[str] = []
    for raw_token in _WORD.findall(question):
        token = raw_token.casefold()
        contains_digit = any(character.isdigit() for character in token)
        is_short_acronym = len(raw_token) >= 2 and raw_token.isupper()
        if (
            token in _STOPWORDS
            or token in terms
            or (len(token) < 3 and not contains_digit and not is_short_acronym)
        ):
            continue
        terms.append(token)
    return tuple(terms)


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def _bounded_matches(pattern: re.Pattern[str], text: str) -> tuple[int, ...]:
    """Sample matches across a document so repetitions have bounded influence."""

    positions = [match.start() for match in pattern.finditer(text)]
    if len(positions) <= _MAX_MATCHES_PER_TERM:
        return tuple(positions)
    last_index = len(positions) - 1
    sampled = {
        positions[(offset * last_index) // (_MAX_MATCHES_PER_TERM - 1)]
        for offset in range(_MAX_MATCHES_PER_TERM)
    }
    return tuple(sorted(sampled))


def _document_frequency(
    blocks: tuple[EvidenceBlockLike, ...],
    terms: tuple[str, ...],
    patterns: dict[str, re.Pattern[str]],
) -> dict[str, int]:
    frequencies = dict.fromkeys(terms, 0)
    for block in blocks:
        searchable = f"{block.title}\n{block.text}"
        for term in terms:
            if patterns[term].search(searchable):
                frequencies[term] += 1
    return frequencies


def _question_model(
    question: str,
    blocks: tuple[EvidenceBlockLike, ...],
) -> _QuestionModel:
    terms = significant_query_terms_v2(question)
    patterns = {term: _term_pattern(term) for term in terms}
    frequencies = _document_frequency(blocks, terms, patterns)
    block_count = max(1, len(blocks))
    weights = {
        term: 1_024 + ((block_count + 1) * 4_096 // (frequencies[term] + 1)) for term in terms
    }
    return _QuestionModel(
        terms=terms,
        weights=weights,
        ordered_pairs=tuple(pairwise(terms)),
        patterns=patterns,
    )


def _token_positions(value: str, wanted: frozenset[str]) -> dict[str, list[int]]:
    positions: dict[str, list[int]] = {term: [] for term in wanted}
    for index, raw_token in enumerate(_WORD.findall(value)):
        token = raw_token.casefold()
        if token in wanted and len(positions[token]) < 2:
            positions[token].append(index)
    return positions


def _ordered_pair_score(value: str, model: _QuestionModel) -> int:
    if not model.ordered_pairs:
        return 0
    positions = _token_positions(value, frozenset(model.terms))
    score = 0
    for left, right in model.ordered_pairs:
        if any(
            0 < right_position - left_position <= 4
            for left_position in positions[left]
            for right_position in positions[right]
        ):
            score += min(model.weights[left], model.weights[right])
    return score


def _lexical_score(value: str, model: _QuestionModel) -> int:
    """Saturate repeated terms so keyword stuffing cannot monopolize budget."""

    unique_score = 0
    capped_repeat_score = 0
    for term in model.terms:
        matches = _bounded_matches(model.patterns[term], value)
        if not matches:
            continue
        weight = model.weights[term]
        unique_score += weight
        capped_repeat_score += weight * min(2, len(matches))
    pair_score = _ordered_pair_score(value, model)
    density = min(1_000, unique_score * 32 // max(1, len(value)))
    return (unique_score * 16) + (pair_score * 8) + capped_repeat_score + density


def _block_relevance(
    block: EvidenceBlockLike,
    model: _QuestionModel,
    index: int,
    block_count: int,
) -> int:
    title_score = _lexical_score(block.title, model)
    text_score = _lexical_score(block.text, model)
    rank_prior = max(1, block_count - index)
    return (title_score * 4) + text_score + rank_prior


def _aligned_window(text: str, focus: int, width: int) -> tuple[int, int]:
    if width >= len(text):
        return 0, len(text)
    start = min(max(0, focus - (width // 3)), len(text) - width)
    end = start + width

    left_floor = max(0, start - _PASSAGE_BOUNDARY_LOOKAROUND)
    left_boundary = max(
        (text.rfind(boundary, left_floor, start) for boundary in ".!?\n"),
        default=-1,
    )
    if left_boundary >= left_floor:
        aligned_start = left_boundary + 1
        while aligned_start < end and text[aligned_start].isspace():
            aligned_start += 1
        if end - aligned_start >= _MIN_PASSAGE_CHARS:
            start = aligned_start

    right_ceiling = min(len(text), end + _PASSAGE_BOUNDARY_LOOKAROUND)
    candidates = [
        position
        for boundary in ".!?\n"
        if (position := text.find(boundary, end, right_ceiling)) >= 0
    ]
    if candidates:
        aligned_end = min(candidates) + 1
        if aligned_end - start <= width + (2 * _PASSAGE_BOUNDARY_LOOKAROUND):
            end = aligned_end
    return start, end


def _passage_candidates(
    text: str,
    title: str,
    model: _QuestionModel,
    width: int,
) -> tuple[_Passage, ...]:
    raw_ranges: dict[tuple[int, int], tuple[int, bool]] = {}
    for term in model.terms:
        for position in _bounded_matches(model.patterns[term], text):
            start, end = _aligned_window(text, position, width)
            raw_ranges[(start, end)] = (position, True)

    fallback_focuses = (
        0,
        len(text) // 5,
        len(text) // 4,
        (2 * len(text)) // 5,
        len(text) // 2,
        (3 * len(text)) // 5,
        (3 * len(text)) // 4,
        (4 * len(text)) // 5,
        max(0, len(text) - 1),
    )
    for focus in fallback_focuses:
        start, end = _aligned_window(text, focus, width)
        raw_ranges.setdefault((start, end), (focus, False))

    title_score = _lexical_score(title, model)
    candidates = [
        _Passage(
            start=start,
            end=end,
            focus=focus,
            score=(_lexical_score(text[start:end], model) * 8) + (title_score * 3),
            anchored=anchored,
        )
        for (start, end), (focus, anchored) in raw_ranges.items()
        if start < end
    ]
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                -item.score,
                -int(item.anchored),
                item.start,
                item.end,
            ),
        )
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


def _range_cost(ranges: list[tuple[int, int]]) -> int:
    merged = _merge_ranges(ranges)
    return sum(end - start for start, end in merged) + (
        len(OMISSION_SEPARATOR) * max(0, len(merged) - 1)
    )


def _fit_around_focus(text_length: int, focus: int, width: int) -> tuple[int, int]:
    width = min(width, text_length)
    start = min(max(0, focus - (width // 3)), text_length - width)
    return start, start + width


def compact_evidence_text_v2(
    text: str,
    title: str,
    model: _QuestionModel,
    cap_chars: int,
) -> str:
    """Pack a fair prefix and several source passages inside one exact cap."""

    clean = text.strip()
    if cap_chars <= 0 or not clean:
        return ""
    if len(clean) <= cap_chars:
        return clean
    if cap_chars < _MIN_PASSAGE_CHARS:
        return clean[:cap_chars]

    prefix_chars = min(cap_chars, max(_MIN_PASSAGE_CHARS, cap_chars // 2))
    ranges: list[tuple[int, int]] = [(0, prefix_chars)]
    passage_width = min(
        _PASSAGE_TARGET_CHARS,
        max(_MIN_PASSAGE_CHARS, (2 * (cap_chars - prefix_chars)) // 3),
    )
    candidates = _passage_candidates(clean, title, model, passage_width)

    for candidate in candidates:
        if len(_merge_ranges(ranges)) >= 4:
            break
        remaining = cap_chars - _range_cost(ranges)
        if remaining < _MIN_PASSAGE_CHARS:
            break
        disjoint_cost = len(OMISSION_SEPARATOR)
        grant = min(
            candidate.end - candidate.start,
            remaining,
            max(_MIN_PASSAGE_CHARS, passage_width),
        )
        proposed = (candidate.start, candidate.end)
        if all(proposed[1] <= start or proposed[0] >= end for start, end in ranges):
            grant = min(grant, remaining - disjoint_cost)
        if grant < _MIN_PASSAGE_CHARS:
            continue
        proposed = _fit_around_focus(len(clean), candidate.focus, grant)
        merged_before = _merge_ranges(ranges)
        merged_after = _merge_ranges([*ranges, proposed])
        new_source_chars = sum(end - start for start, end in merged_after) - sum(
            end - start for start, end in merged_before
        )
        if new_source_chars < _MIN_PASSAGE_CHARS // 2:
            continue
        if _range_cost([*ranges, proposed]) <= cap_chars:
            ranges.append(proposed)

    segments = [
        clean[start:end].strip() for start, end in _merge_ranges(ranges) if clean[start:end].strip()
    ]
    compacted = OMISSION_SEPARATOR.join(segments)
    if len(compacted) > cap_chars:
        raise AssertionError("v2 block compaction exceeded its assigned cap")
    return compacted


def _select_blocks(
    blocks: tuple[BlockT, ...],
    model: _QuestionModel,
    budget_chars: int,
    min_block_chars: int,
) -> tuple[tuple[BlockT, int, int], ...]:
    scored = [
        (
            block,
            index,
            _block_relevance(block, model, index, len(blocks)),
        )
        for index, block in enumerate(blocks)
    ]
    floor = min(min_block_chars, 96)

    def required(items: list[tuple[BlockT, int, int]]) -> int:
        return sum(len(evidence_header(block)) + floor for block, _index, _score in items) + (
            2 * max(0, len(items) - 1)
        )

    while scored and required(scored) > budget_chars:
        remove_index = min(
            range(len(scored)),
            key=lambda offset: (
                scored[offset][2],
                -scored[offset][1],
            ),
        )
        del scored[remove_index]
    return tuple(sorted(scored, key=lambda item: item[1]))


def _allocate_caps(
    selected: tuple[tuple[BlockT, int, int], ...],
    text_budget: int,
    *,
    min_block_chars: int,
    max_block_chars: int,
) -> list[int]:
    desired = [min(len(block.text.strip()), max_block_chars) for block, _index, _score in selected]
    if not desired:
        return []

    fair_target = min(min_block_chars, text_budget // len(selected))
    caps = [min(item, fair_target) for item in desired]
    remaining = text_budget - sum(caps)
    extra_steps = [0 for _item in selected]

    while remaining > 0:
        eligible = [index for index, cap in enumerate(caps) if cap < desired[index]]
        if not eligible:
            break
        chosen = max(
            eligible,
            key=lambda index: (
                selected[index][2] // (1 + extra_steps[index]),
                -extra_steps[index],
                -selected[index][1],
            ),
        )
        grant = min(
            _ALLOCATION_QUANTUM,
            desired[chosen] - caps[chosen],
            remaining,
        )
        caps[chosen] += grant
        extra_steps[chosen] += 1
        remaining -= grant
    return caps


def candidate_project_blocks_v2(
    blocks: tuple[BlockT, ...],
    question: str,
    budget_chars: int,
    max_block_chars: int,
    *,
    min_block_chars: int = 192,
) -> tuple[BlockT, ...]:
    """Project evidence with deterministic fair-prefix and multi-passage packing."""

    if budget_chars <= 0:
        raise ValueError("budget_chars must be positive")
    if max_block_chars <= 0:
        raise ValueError("max_block_chars must be positive")
    if min_block_chars <= 0 or min_block_chars > max_block_chars:
        raise ValueError("min_block_chars must be positive and no larger than max_block_chars")

    citation_ids = [block.citation_id for block in blocks]
    if any(not citation_id for citation_id in citation_ids):
        raise ValueError("citation identifiers must be non-empty")
    if len(citation_ids) != len(set(citation_ids)):
        raise ValueError("citation identifiers must be unique")

    nonempty = tuple(block for block in blocks if block.text.strip())
    if not nonempty:
        return ()
    model = _question_model(question, nonempty)
    selected = _select_blocks(nonempty, model, budget_chars, min_block_chars)
    if not selected:
        return ()

    overhead = sum(len(evidence_header(block)) for block, _index, _score in selected) + (
        2 * (len(selected) - 1)
    )
    caps = _allocate_caps(
        selected,
        budget_chars - overhead,
        min_block_chars=min_block_chars,
        max_block_chars=max_block_chars,
    )
    projected = tuple(
        _replace_text(
            block,
            compact_evidence_text_v2(
                block.text,
                block.title,
                model,
                cap,
            ),
        )
        for (block, _index, _score), cap in zip(selected, caps, strict=True)
    )
    if any(len(block.text) > max_block_chars for block in projected):
        raise AssertionError("v2 projection exceeded its per-block cap")
    if rendered_evidence_chars(projected) > budget_chars:
        raise AssertionError("v2 projection exceeded its exact rendered budget")
    return projected
