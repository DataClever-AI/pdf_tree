"""Tests for page_numbering — roman/arabic/alphanumeric page-token classification."""
from __future__ import annotations

from src.tree_builder.page_numbering import (
    classify_page_token,
    detect_numbering_scheme,
    normalize_page_sequence,
)


def test_classify_arabic_int_and_string() -> None:
    assert classify_page_token(5).scheme == "arabic"
    assert classify_page_token(5).value == 5
    assert classify_page_token("12").scheme == "arabic"
    assert classify_page_token("12").value == 12


def test_classify_roman_numerals() -> None:
    assert classify_page_token("iv").value == 4
    assert classify_page_token("IX").value == 9
    assert classify_page_token("xiv").value == 14


def test_classify_invalid_roman_numeral_is_not_coerced() -> None:
    """Non-canonical roman-looking strings (e.g. "iiii") must not silently
    parse to a wrong number — they fall through to "unknown"."""
    token = classify_page_token("iiii")
    assert token.scheme == "unknown"
    assert token.value is None


def test_classify_alphanumeric_section_relative_codes() -> None:
    """Section-relative codes like "A-1" must never be coerced into a plain
    int — they get their own scheme + a cluster key for grouping."""
    a1 = classify_page_token("A-1")
    assert a1.scheme == "alphanumeric"
    assert a1.cluster_key == "A"
    assert a1.value == 1  # local index within cluster "A", not a global page

    chapter = classify_page_token("3-12")
    assert chapter.scheme == "alphanumeric"
    assert chapter.cluster_key == "3"
    assert chapter.value == 12


def test_detect_numbering_scheme_pure_arabic() -> None:
    assert detect_numbering_scheme([1, 2, 3, 4]) == "arabic"


def test_detect_numbering_scheme_mixed_roman_arabic() -> None:
    assert detect_numbering_scheme(["i", "ii", "iii", 1, 2, 3]) == "mixed_roman_arabic"


def test_detect_numbering_scheme_alphanumeric() -> None:
    assert detect_numbering_scheme(["A-1", "A-2", "B-1"]) == "alphanumeric"


def test_normalize_page_sequence_pure_arabic_is_unchanged() -> None:
    assert normalize_page_sequence([1, 2, 3, 4]) == [1, 2, 3, 4]


def test_normalize_page_sequence_roman_then_arabic_is_monotonic() -> None:
    """Roman front matter (i, ii, iii) followed by arabic body restarting at 1
    must rebase into one continuous sequential index, not reset."""
    normalized = normalize_page_sequence(["i", "ii", "iii", 1, 2, 3])
    assert normalized == [1, 2, 3, 4, 5, 6]


def test_normalize_page_sequence_alphanumeric_is_not_coerced() -> None:
    """Alphanumeric codes can't be placed on the global sequential axis —
    they normalize to None rather than a guessed integer."""
    normalized = normalize_page_sequence(["A-1", "A-2", "B-1"])
    assert normalized == [None, None, None]
