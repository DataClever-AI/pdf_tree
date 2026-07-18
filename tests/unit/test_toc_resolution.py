"""Tests for toc_resolution — TOC page resolution + calibration + traceability."""
from __future__ import annotations

from src.models.extraction import DoclingDocument, DoclingTextBlock, ExtractionProvenance
from src.tree_builder.toc_resolution import resolve_toc_pages


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


def _doc(blocks: list[DoclingTextBlock], total_pages: int = 30) -> DoclingDocument:
    return DoclingDocument(
        document_id="test",
        source_path="test.pdf",
        total_pages=total_pages,
        text_blocks=blocks,
    )


def test_pure_arabic_fixed_offset() -> None:
    """(a) Pure arabic numbering with a fixed document-wide offset."""
    titles = ["Chapter One", "Chapter Two", "Chapter Three", "Chapter Four", "Chapter Five"]
    blocks = [_block(t, page_no=i + 4, reading_order=i * 2) for i, t in enumerate(titles)]
    doc = _doc(blocks)
    # Claimed pages are 1..5; true physical pages are 4..8 (offset +3).
    bookmarks = [(1, t, i + 1) for i, t in enumerate(titles)]

    resolved, report = resolve_toc_pages(bookmarks, doc)

    assert report.numbering_scheme == "arabic"
    assert report.global_accepted is True
    assert report.global_offset == 3
    assert not report.flagged_for_manual_review
    assert [r.resolved_page for r in resolved] == [4, 5, 6, 7, 8]
    assert all(r.verification.passed for r in resolved)


def test_roman_front_matter_then_arabic_body() -> None:
    """(b) Roman-numeral front matter followed by arabic body, no residual offset."""
    front = [(1, "Preface", "i"), (1, "Foreword", "ii")]
    body = [(1, "Chapter One", 1), (1, "Chapter Two", 2), (1, "Chapter Three", 3)]
    bookmarks = front + body
    titles = [t for _l, t, _p in bookmarks]
    # Normalized sequence is [1, 2, 3, 4, 5] — content sits exactly there.
    blocks = [_block(t, page_no=i + 1, reading_order=i * 2) for i, t in enumerate(titles)]
    doc = _doc(blocks)

    resolved, report = resolve_toc_pages(bookmarks, doc)

    assert report.numbering_scheme == "mixed_roman_arabic"
    assert report.global_accepted is True
    assert report.global_offset == 0
    assert [r.resolved_page for r in resolved] == [1, 2, 3, 4, 5]
    assert all(r.verification.passed for r in resolved)
    schemes = [r.numbering_scheme for r in resolved]
    assert schemes == ["roman", "roman", "arabic", "arabic", "arabic"]


def test_no_offset_needed() -> None:
    """(c) Claimed pages already match extracted pages exactly."""
    titles = ["Intro", "Body", "Conclusion"]
    blocks = [_block(t, page_no=i + 1, reading_order=i * 2) for i, t in enumerate(titles)]
    doc = _doc(blocks)
    bookmarks = [(1, t, i + 1) for i, t in enumerate(titles)]

    resolved, report = resolve_toc_pages(bookmarks, doc)

    assert report.global_offset == 0
    assert report.global_accepted is True
    assert [r.resolved_page for r in resolved] == [1, 2, 3]


def test_calibration_fails_and_flags_for_manual_review() -> None:
    """(d) No offset in range explains the claimed pages — must flag for
    manual review rather than silently applying the least-bad guess."""
    titles = ["Chapter One", "Chapter Two", "Chapter Three"]
    # Extracted content has nothing to do with any of these titles, anywhere.
    blocks = [
        _block("Completely unrelated filler content.", page_no=p, reading_order=p)
        for p in range(1, 20)
    ]
    doc = _doc(blocks)
    bookmarks = [(1, t, i + 1) for i, t in enumerate(titles)]

    resolved, report = resolve_toc_pages(bookmarks, doc)

    assert report.global_accepted is False
    assert report.flagged_for_manual_review is True
    assert all(not r.verification.passed for r in resolved)
    # Never dropped — still present, with their original claimed page (offset 0).
    assert len(resolved) == 3
    assert [r.resolved_page for r in resolved] == [1, 2, 3]


def test_alphanumeric_codes_resolved_via_per_cluster_offset() -> None:
    """(e) Section-relative alphanumeric codes ("A-1", "B-1") aren't coerced
    into a single wrong global integer — each cluster gets calibrated (and
    resolved) independently when a single global offset can't fit both."""
    bookmarks = [
        (2, "Widget Assembly Overview", "A-1"),
        (2, "Widget Torque Specifications", "A-2"),
        (2, "Battery Safety Warnings", "B-1"),
        (2, "Battery Disposal Procedure", "B-2"),
    ]
    # Cluster "A" lives at physical pages 4-5 (local 1,2 + offset 3).
    # Cluster "B" lives at physical pages 1-2 (local 1,2 + offset 0).
    # No single global offset satisfies both clusters at once.
    blocks = [
        _block("Widget Assembly Overview", page_no=4, reading_order=0),
        _block("Widget Torque Specifications", page_no=5, reading_order=1),
        _block("Battery Safety Warnings", page_no=1, reading_order=2),
        _block("Battery Disposal Procedure", page_no=2, reading_order=3),
    ]
    doc = _doc(blocks)

    resolved, report = resolve_toc_pages(bookmarks, doc)

    assert report.numbering_scheme == "alphanumeric"
    assert not report.flagged_for_manual_review
    by_title = {r.title: r for r in resolved}
    assert by_title["Widget Assembly Overview"].resolved_page == 4
    assert by_title["Widget Torque Specifications"].resolved_page == 5
    assert by_title["Battery Safety Warnings"].resolved_page == 1
    assert by_title["Battery Disposal Procedure"].resolved_page == 2
    assert all(r.verification.passed for r in resolved), [r.verification for r in resolved]
    assert all(r.numbering_scheme == "alphanumeric" for r in resolved)

    clusters_by_id = {c.cluster_id: c for c in report.clusters}
    assert clusters_by_id["alnum_A"].accepted is True
    assert clusters_by_id["alnum_B"].accepted is True
    # The whole-document "_preamble" chapter-cluster fallback (everything is
    # level 2 here, so it's a single lumped cluster) is expected to fail —
    # it mixes both alphanumeric groups' local indices, same as the global
    # attempt. What matters is the alphanumeric clusters recovered it.
