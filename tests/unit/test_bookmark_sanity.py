"""Tests for bookmark_sanity — detection and deterministic repair of bookmark defects."""
from __future__ import annotations

from collections.abc import Callable

from src.tree_builder.bookmark_sanity import check_bookmark_sanity, repair_bookmarks


def _pages(texts: dict[int, str]) -> Callable[[int], str]:
    return lambda page_no: texts.get(page_no, "")


def test_clean_bookmarks_have_no_hard_failures() -> None:
    bookmarks = [(1, "Chapter 1", 5), (2, "Intro", 5), (2, "Setup", 7), (1, "Chapter 2", 10)]

    report = check_bookmark_sanity(bookmarks, total_pages=20)

    assert not report.has_hard_failures


def test_orphan_cover_subtree_is_dropped() -> None:
    """Shape of Philips-MP20-MP90: a destination-less cover bookmark appended
    after the outline, whose child points at the cover page."""
    bookmarks = [
        (1, "Basic Operation", 13),
        (2, "Introducing the Family", 13),
        (2, "Default Settings", 484),
        (1, "M8000-9001K_cover.pdf", -1),
        (2, "IntelliVue Patient Monitor", 1),
    ]
    assert check_bookmark_sanity(bookmarks, total_pages=496).has_hard_failures

    repaired, repairs = repair_bookmarks(bookmarks, 496, _pages({}))

    assert repaired == bookmarks[:3]
    assert [(r.kind, r.index, r.dropped_count) for r in repairs] == [
        ("dropped_orphan_subtree", 3, 2)
    ]
    assert not check_bookmark_sanity(repaired, 496).has_hard_failures


def test_destinationless_container_with_content_children_is_kept() -> None:
    """A page-less bookmark whose children point into the body is a normal
    container, not orphan front-matter."""
    bookmarks = [(1, "Part A", -1), (2, "Section 1", 10), (2, "Section 2", 12)]

    repaired, repairs = repair_bookmarks(bookmarks, 20, _pages({}))

    assert repaired == bookmarks
    assert repairs == []


def test_child_before_parent_is_relocated_to_title_line() -> None:
    """Shape of 2002_Service_Manual_TI: '1. General' links to page 3 although
    its parent chapter starts on page 21 and the heading is on page 22."""
    bookmarks = [
        (3, "SPECIFICATIONS", 5),
        (4, "2. OUTBACK", 14),
        (3, "FUEL INJECTION (FUEL SYSTEM)", 21),
        (4, "1. General", 3),
        (4, "2. Air Line", 23),
    ]
    texts = {
        3: "QUICK REFERENCE INDEX\nFOREWORD",
        21: "Page\n1.\nGeneral ........................ 2\n2.\nAir Line ........ 3",
        22: "Fuel Injection (Fuel System)\nGENERAL\nFU-2\n1. General\nThe MFI system...",
        23: "Fuel Injection (Fuel System)\nAIR LINE\n2. Air Line",
    }
    assert check_bookmark_sanity(bookmarks, total_pages=642).has_hard_failures

    repaired, repairs = repair_bookmarks(bookmarks, 642, _pages(texts))

    assert repaired[3] == (4, "1. General", 22)
    assert [(r.kind, r.original_page, r.new_page) for r in repairs] == [("relocated", 3, 22)]
    assert not check_bookmark_sanity(repaired, 642).has_hard_failures


def test_child_before_parent_without_title_match_is_dropped_with_subtree() -> None:
    bookmarks = [
        (1, "Chapter 1", 5),
        (1, "Chapter 2", 20),
        (2, "Lost section", 2),
        (3, "Lost subsection", 2),
        (2, "Kept section", 22),
    ]

    repaired, repairs = repair_bookmarks(bookmarks, 30, _pages({}))

    assert repaired == [(1, "Chapter 1", 5), (1, "Chapter 2", 20), (2, "Kept section", 22)]
    assert [(r.kind, r.index, r.dropped_count) for r in repairs] == [
        ("dropped_unresolvable", 2, 2)
    ]


def test_sibling_disorder_is_not_repaired() -> None:
    """Widespread sibling disorder is outside the repair scope: the hard
    failure must survive so the pipeline still aborts."""
    bookmarks = [(1, "Chapter 1", 10), (1, "Chapter 2", 4), (1, "Chapter 3", 15)]

    repaired, repairs = repair_bookmarks(bookmarks, 20, _pages({}))

    assert repairs == []
    assert check_bookmark_sanity(repaired, 20).has_hard_failures
