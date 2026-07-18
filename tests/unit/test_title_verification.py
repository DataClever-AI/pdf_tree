"""Tests for title_verification — fuzzy title-vs-text verification + offset calibration."""
from __future__ import annotations

from src.models.extraction import DoclingDocument, DoclingTextBlock, ExtractionProvenance
from src.tree_builder.title_verification import calibrate_page_offset, verify_titles


def _block(text: str, page_no: int, reading_order: int) -> DoclingTextBlock:
    return DoclingTextBlock(
        block_id=f"blk_{reading_order}",
        text=text,
        label="section_header" if reading_order % 2 == 0 else "text",
        page_no=page_no,
        reading_order=reading_order,
        depth=0,
        provenance=ExtractionProvenance(source="docling", page_no=page_no),
    )


def _doc(blocks: list[DoclingTextBlock], total_pages: int = 20) -> DoclingDocument:
    return DoclingDocument(
        document_id="test",
        source_path="test.pdf",
        total_pages=total_pages,
        text_blocks=blocks,
    )


def test_title_verified_at_claimed_page() -> None:
    """A bookmark whose title genuinely appears on its claimed page passes."""
    doc = _doc([
        _block("Introduction", page_no=5, reading_order=0),
        _block("Some intro body text.", page_no=5, reading_order=1),
    ])
    bookmarks = [(1, "Introduction", 5)]

    results = verify_titles(bookmarks, doc)

    assert len(results) == 1
    result = results[0]
    assert result.passed is True
    assert result.verified_page == 5
    assert result.score >= 85.0
    assert result.reason == ""


def test_title_fails_verification_on_wrong_claimed_page() -> None:
    """A bookmark whose claimed page is simply wrong (title nowhere nearby) fails,
    and is reported with a score/reason rather than silently accepted."""
    doc = _doc([
        _block("Introduction", page_no=5, reading_order=0),
        _block("Unrelated appendix content about calibration.", page_no=14, reading_order=1),
    ])
    # Claimed page 14 for a title that's actually nowhere near page 14.
    bookmarks = [(1, "Introduction", 14)]

    results = verify_titles(bookmarks, doc, page_window=1)

    assert len(results) == 1
    result = results[0]
    assert result.passed is False
    assert result.score < 85.0
    assert "below threshold" in result.reason


def test_offset_calibration_recovers_shifted_headers() -> None:
    """When every bookmark's claimed page is off by a constant amount (e.g. a
    front-matter/roman-numeral offset), calibration finds that offset and the
    header is recovered as verified rather than left failing."""
    doc = _doc([
        _block("Chapter One", page_no=8, reading_order=0),
        _block("Chapter Two", page_no=12, reading_order=1),
        _block("Chapter Three", page_no=16, reading_order=2),
    ])
    # Every claimed page is 3 less than the true page (e.g. roman-numeral
    # front matter not counted in the claimed numbering).
    bookmarks = [
        (1, "Chapter One", 5),
        (1, "Chapter Two", 9),
        (1, "Chapter Three", 13),
    ]

    offset = calibrate_page_offset(bookmarks, doc)
    assert offset == 3

    results = verify_titles(bookmarks, doc)

    assert all(r.passed for r in results)
    assert all(r.offset_applied == 3 for r in results)
    assert [r.verified_page for r in results] == [8, 12, 16]
