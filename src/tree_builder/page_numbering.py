"""
Page-numbering scheme detection and normalization — handles TOC sources whose
claimed "page number" isn't a plain 1-indexed arabic integer matching the
extracted document's physical page index: roman-numeral front matter, and
alphanumeric/section-relative codes (e.g. "A-1", "3-12").

Roman + arabic entries get rebased into one monotonic sequential index space
(matching physical page order) so offset calibration can run on a single
coherent axis. Alphanumeric/section-relative codes are never coerced into
that space — they're tagged with their own scheme and grouped into clusters
by prefix, for per-cluster calibration instead of one global offset
(see toc_resolution.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

NumberingScheme = Literal["arabic", "roman", "alphanumeric", "unknown"]

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
_ROMAN_RE = re.compile(r"^[ivxlcdm]+$")
_ALPHANUMERIC_RE = re.compile(r"^[A-Za-z]+-?\d+$|^\d+-\d+$")


@dataclass
class PageToken:
    """Classification of one raw claimed-page value from a TOC entry."""

    raw: int | str
    scheme: NumberingScheme
    value: int | None
    # Grouping key for alphanumeric codes (e.g. "A-1" -> "A", "3-12" -> "3").
    # `value` for these is the local (within-cluster) numeric suffix only —
    # never a global page index.
    cluster_key: str | None


def _int_to_roman(n: int) -> str:
    """Encode int as lowercase roman numeral — used to validate round-trips."""
    if n <= 0:
        return ""
    table = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    ]
    parts = []
    for value, symbol in table:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return "".join(parts)


def _roman_to_int(text: str) -> int | None:
    """Parse a roman numeral string to int, or None if not a valid roman numeral."""
    s = text.lower()
    if not s or not _ROMAN_RE.match(s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN_VALUES[ch]
        total += val if val >= prev else -val
        prev = max(prev, val)
    # Round-trip check rejects non-canonical strings that matched the
    # char-set regex but aren't real roman numerals (e.g. "iiii", "vv").
    if _int_to_roman(total) != s:
        return None
    return total


def _alphanumeric_prefix(text: str) -> str:
    """Cluster key for an alphanumeric code — the part before the local index."""
    if "-" in text:
        return text.split("-", 1)[0]
    match = re.match(r"^[A-Za-z]+", text)
    return match.group(0) if match else text


def classify_page_token(raw: int | str) -> PageToken:
    """Classify a raw claimed-page value into a numbering scheme."""
    if isinstance(raw, int):
        return PageToken(raw=raw, scheme="arabic", value=raw, cluster_key=None)

    text = raw.strip()
    if text.isdigit():
        return PageToken(raw=raw, scheme="arabic", value=int(text), cluster_key=None)

    roman_value = _roman_to_int(text)
    if roman_value is not None:
        return PageToken(raw=raw, scheme="roman", value=roman_value, cluster_key=None)

    if _ALPHANUMERIC_RE.match(text):
        prefix = _alphanumeric_prefix(text)
        suffix_digits = re.search(r"\d+$", text)
        local_value = int(suffix_digits.group(0)) if suffix_digits else None
        return PageToken(raw=raw, scheme="alphanumeric", value=local_value, cluster_key=prefix)

    return PageToken(raw=raw, scheme="unknown", value=None, cluster_key=None)


def detect_numbering_scheme(raw_pages: list[int | str]) -> str:
    """
    Summarize the numbering scheme(s) seen across a whole TOC, for traceability.

    Returns "arabic" | "roman" | "mixed_roman_arabic" | "alphanumeric" | "mixed" | "unknown".
    """
    schemes = {classify_page_token(p).scheme for p in raw_pages}
    schemes.discard("unknown")
    if not schemes:
        return "unknown"
    if schemes == {"arabic"}:
        return "arabic"
    if schemes == {"roman"}:
        return "roman"
    if schemes == {"roman", "arabic"}:
        return "mixed_roman_arabic"
    if schemes == {"alphanumeric"}:
        return "alphanumeric"
    return "mixed"


def normalize_page_sequence(raw_pages: list[int | str]) -> list[int | None]:
    """
    Rebase roman-then-arabic (or arabic-only) claimed pages into one monotonic
    sequential index space matching physical page order — e.g. roman front
    matter "i, ii, iii" (1, 2, 3) followed by arabic body restarting at "1"
    becomes (1, 2, 3, 4, 5, ...) instead of a numbering discontinuity.

    Alphanumeric/section-relative codes (e.g. "A-1") normalize to None —
    callers must resolve those via per-cluster calibration (see
    PageToken.cluster_key) instead of this single global sequence.
    """
    normalized: list[int | None] = []
    scheme_base = 0
    running_max = 0
    prev_scheme: NumberingScheme | None = None

    for raw in raw_pages:
        token = classify_page_token(raw)
        if token.scheme not in ("arabic", "roman") or token.value is None:
            normalized.append(None)
            prev_scheme = token.scheme
            continue

        if prev_scheme is not None and token.scheme != prev_scheme:
            scheme_base = running_max

        value = scheme_base + token.value
        normalized.append(value)
        running_max = max(running_max, value)
        prev_scheme = token.scheme

    return normalized
