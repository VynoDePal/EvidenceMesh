"""Extraction, evidence selection and untrusted-content risk labelling."""

from __future__ import annotations

import hashlib
import io
import re
from contextlib import suppress
from html.parser import HTMLParser
from urllib.parse import urlsplit

from pypdf import PdfReader
from trafilatura import extract as trafilatura_extract

from evidencemesh.errors import UnsupportedContentError

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"\bignore (all|any|the|your)?\s*(previous|prior|above) instructions?\b", re.I),
    re.compile(r"\b(system|developer) (message|prompt|instructions?)\b", re.I),
    re.compile(r"\breveal (your|the) (prompt|instructions?|secrets?)\b", re.I),
    re.compile(r"\b(exfiltrate|send|upload) .{0,40}\b(secret|token|credential|api key)\b", re.I),
    re.compile(r"<\|(?:system|assistant|developer)\|>", re.I),
    re.compile(r"\bBEGIN (?:SYSTEM|DEVELOPER) (?:PROMPT|MESSAGE)\b", re.I),
]
_HIDDEN_HTML = re.compile(
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0|hidden\s*=)",
    re.I,
)
_SCRIPT_OR_IFRAME = re.compile(r"<(?:script|iframe|object|embed)\b", re.I)
_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)


class _HTMLMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if not self._ignored_depth:
            self.text_parts.append(data)


def normalise_text(text: str) -> str:
    lines = [_WHITESPACE.sub(" ", line).strip() for line in text.replace("\x00", "").splitlines()]
    return _BLANK_LINES.sub("\n\n", "\n".join(line for line in lines if line)).strip()


def detect_risk_flags(raw: str, *, is_html: bool = False) -> list[str]:
    sample = raw[:250_000]
    flags: list[str] = []
    if any(pattern.search(sample) for pattern in _PROMPT_INJECTION_PATTERNS):
        flags.append("possible_prompt_injection")
    if is_html and _HIDDEN_HTML.search(sample):
        flags.append("hidden_content")
    if is_html and _SCRIPT_OR_IFRAME.search(sample):
        flags.append("active_content_removed")
    if "\u202e" in sample or "\u2066" in sample or "\u2067" in sample:
        flags.append("bidirectional_text_controls")
    return flags


def _decode_html(data: bytes, media_type: str) -> str:
    charset_match = re.search(r"charset=([\w-]+)", media_type, re.I)
    encodings = [charset_match.group(1)] if charset_match else []
    encodings.extend(["utf-8", "windows-1252"])
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _extract_html(data: bytes, media_type: str, url: str) -> tuple[str, str, list[str]]:
    raw = _decode_html(data, media_type)
    parser = _HTMLMetadataParser()
    # Malformed HTML should not prevent the conservative fallback.
    with suppress(Exception):
        parser.feed(raw)
    title = normalise_text(" ".join(parser.title_parts))
    extracted = trafilatura_extract(
        raw,
        url=url,
        output_format="txt",
        include_comments=False,
        include_links=False,
        include_images=False,
        favor_precision=True,
        no_fallback=False,
    )
    text = normalise_text(extracted or " ".join(parser.text_parts))
    return title, text, detect_risk_flags(raw, is_html=True)


def _extract_pdf(
    data: bytes,
    *,
    max_pages: int,
    max_chars: int,
) -> tuple[str, str, list[str]]:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception as exc:
        raise UnsupportedContentError("PDF could not be parsed") from exc
    title = ""
    if reader.metadata and reader.metadata.title:
        title = normalise_text(str(reader.metadata.title))
    pages: list[str] = []
    flags: list[str] = []
    extraction_limit = max_chars + 1
    extracted_chars = 0
    for index, page in enumerate(reader.pages):
        if index >= max_pages:
            flags.append("pdf_page_limit_reached")
            break
        try:
            page_text = page.extract_text() or ""
        except Exception:
            if "pdf_page_extraction_failed" not in flags:
                flags.append("pdf_page_extraction_failed")
            continue
        remaining = extraction_limit - extracted_chars
        if remaining <= 0:
            flags.append("pdf_extraction_budget_reached")
            break
        pages.append(page_text[:remaining])
        extracted_chars += len(pages[-1])
        if len(page_text) > remaining or extracted_chars >= extraction_limit:
            flags.append("pdf_extraction_budget_reached")
            break
    text = normalise_text("\n\n".join(pages))
    return title, text, [*detect_risk_flags(text), *flags]


def extract_content(
    data: bytes,
    *,
    media_type: str,
    url: str,
    max_chars: int,
    max_pdf_pages: int = 100,
) -> tuple[str, str, list[str], bool]:
    lowered_type = media_type.lower()
    path = urlsplit(url).path.lower()
    if "pdf" in lowered_type or path.endswith(".pdf"):
        title, text, flags = _extract_pdf(
            data,
            max_pages=max_pdf_pages,
            max_chars=max_chars,
        )
    elif (
        "html" in lowered_type
        or "xhtml" in lowered_type
        or lowered_type.startswith("text/")
        or not lowered_type
    ):
        title, text, flags = _extract_html(data, media_type, url)
    else:
        raise UnsupportedContentError(f"unsupported media type: {media_type or 'unknown'}")
    if not text:
        raise UnsupportedContentError("no readable text was extracted")
    truncated = len(text) > max_chars or any(
        flag in {"pdf_page_limit_reached", "pdf_extraction_budget_reached"} for flag in flags
    )
    return title, text[:max_chars], flags, truncated


def content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_excerpt(text: str, query: str, *, max_chars: int = 1_200) -> str:
    """Select a compact, query-relevant quotation without using an LLM."""

    if len(text) <= max_chars:
        return text
    query_tokens = {token.lower() for token in _TOKEN.findall(query) if len(token) > 1}
    units = [unit.strip() for unit in re.split(r"\n{2,}", text) if unit.strip()]
    if len(units) < 2:
        units = [unit.strip() for unit in _SENTENCE_SPLIT.split(text) if unit.strip()]
    scored: list[tuple[float, int, str]] = []
    for index, unit in enumerate(units):
        unit_tokens = {token.lower() for token in _TOKEN.findall(unit)}
        overlap = len(query_tokens & unit_tokens) / max(1, len(query_tokens))
        density = len(query_tokens & unit_tokens) / max(1, len(unit_tokens))
        scored.append((0.8 * overlap + 0.2 * density, -index, unit))
    scored.sort(reverse=True)
    best = scored[0][2] if scored else text
    if len(best) > max_chars:
        clipped = best[: max_chars - 1].rsplit(" ", 1)[0]
        return f"{clipped}…"
    return best
