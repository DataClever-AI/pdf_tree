"""
Bookmark sanity pre-check — inspects raw (level, title, page_no) bookmarks
BEFORE section_matcher touches them, and reports (does not silently fix)
structural issues.

Policy (applied by callers, not enforced here):
- negative page_no, out-of-range page_no, empty title: existing clamping in
  section_matcher._compute_page_ranges already handles these safely — warn only.
- duplicate page_no among same-level siblings: warn only. Common and legitimate
  in real manuals (a short section ends and the next heading lands on the same
  page) — section_matcher's reading-order-anchored content assignment already
  handles this correctly (validated against real multi-hundred-section manuals,
  including one with 52 such same-page sibling pairs). It only yields a
  degenerate 1-page range, not a corrupted one.
- out-of-order page_no among same-level siblings: hard failure. Violates
  _compute_page_ranges's monotonicity assumption in a way reading-order
  anchoring cannot compensate for — produces overlapping/inverted ranges,
  not just a narrow one.

repair_bookmarks() is a deterministic recovery pass the pipeline runs only
when the check finds hard failures. It handles two localized defects found in
real manuals, and records every change so QA can audit it:
- orphan front-matter subtree: a bookmark with no destination (page_no < 1)
  whose descendants all point before the first real content bookmark (e.g. a
  cover page inserted after the outline was built) — the subtree is dropped.
- child before parent: a bookmark whose page precedes its parent's page (a
  corrupted link target) — relocated to the page inside the parent's range
  where its title appears as a text line, or dropped (with its subtree) when
  no such page exists.
Anything else (e.g. widespread disorder) is left untouched, so the hard
failure — and the abort — still stand.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from rapidfuzz import fuzz

_HARD_FAILURE_KINDS: frozenset[str] = frozenset({"out_of_order"})

# Minimum fuzz.ratio between a bookmark title and a single page text line for
# the title to count as found on that page during relocation.
_RELOCATE_MIN_SCORE = 90.0

Bookmark = tuple[int, str, int]


@dataclass
class BookmarkIssue:
    kind: str  # "out_of_range" | "negative" | "duplicate_page" | "out_of_order" | "empty_title"
    index: int  # index into the bookmarks list
    detail: str


@dataclass
class BookmarkRepair:
    kind: str  # "dropped_orphan_subtree" | "relocated" | "dropped_unresolvable"
    index: int  # index into the ORIGINAL bookmarks list
    title: str
    original_page: int
    new_page: int | None  # None when the bookmark was dropped
    dropped_count: int  # bookmarks removed (0 for "relocated")
    detail: str


@dataclass
class BookmarkSanityReport:
    issues: list[BookmarkIssue] = field(default_factory=list)
    # Filled only when repair_bookmarks() changed something; `issues` then
    # describes the repaired list, and `original_issues` the list as read.
    repairs: list[BookmarkRepair] = field(default_factory=list)
    original_issues: list[BookmarkIssue] = field(default_factory=list)

    @property
    def has_hard_failures(self) -> bool:
        return any(i.kind in _HARD_FAILURE_KINDS for i in self.issues)


def check_bookmark_sanity(
    bookmarks: list[tuple[int, str, int]],
    total_pages: int,
) -> BookmarkSanityReport:
    """
    Inspect raw bookmarks for structural problems.

    Does not modify bookmarks or apply clamping — that still happens downstream
    in section_matcher._compute_page_ranges. This only detects and reports so
    the caller can decide whether to proceed or abort.
    """
    report = BookmarkSanityReport()
    seen_pages_by_level: dict[int, set[int]] = {}
    prev_page_by_level: dict[int, int] = {}

    for i, (level, title, page_no) in enumerate(bookmarks):
        if page_no < 1:
            report.issues.append(BookmarkIssue(
                "negative", i, f"bookmark[{i}] '{title}' has page_no={page_no} (<1)"
            ))
        elif page_no > total_pages:
            report.issues.append(BookmarkIssue(
                "out_of_range", i,
                f"bookmark[{i}] '{title}' has page_no={page_no} > total_pages={total_pages}"
            ))

        if not title or not title.strip():
            report.issues.append(BookmarkIssue(
                "empty_title", i, f"bookmark[{i}] has empty/whitespace title (page_no={page_no})"
            ))

        siblings = seen_pages_by_level.setdefault(level, set())
        if page_no in siblings:
            report.issues.append(BookmarkIssue(
                "duplicate_page", i,
                f"bookmark[{i}] '{title}' duplicates page_no={page_no} "
                f"at level={level} (already seen at this level)"
            ))
        siblings.add(page_no)

        prev_page = prev_page_by_level.get(level)
        if prev_page is not None and page_no < prev_page:
            report.issues.append(BookmarkIssue(
                "out_of_order", i,
                f"bookmark[{i}] '{title}' page_no={page_no} is before previous "
                f"sibling's page_no={prev_page} at level={level}"
            ))
        prev_page_by_level[level] = page_no

    return report


def _subtree_end(bookmarks: list[Bookmark], index: int) -> int:
    """Exclusive end index of the subtree rooted at bookmarks[index]."""
    level = bookmarks[index][0]
    end = index + 1
    while end < len(bookmarks) and bookmarks[end][0] > level:
        end += 1
    return end


def _parent_index(bookmarks: list[Bookmark], index: int) -> int | None:
    level = bookmarks[index][0]
    for j in range(index - 1, -1, -1):
        if bookmarks[j][0] < level:
            return j
    return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _title_line_score(title: str, page_text: str) -> float:
    """Best fuzz.ratio between the title and any single line of the page."""
    target = _normalize(title)
    if not target:
        return 0.0
    return max(
        (fuzz.ratio(target, _normalize(line)) for line in page_text.splitlines()),
        default=0.0,
    )


def repair_bookmarks(
    bookmarks: list[Bookmark],
    total_pages: int,
    page_text: Callable[[int], str],
) -> tuple[list[Bookmark], list[BookmarkRepair]]:
    """
    Repair the localized defects described in the module docstring.

    `page_text(page_no)` returns the text of a 1-indexed physical page. Returns
    the repaired bookmark list and one BookmarkRepair per change; the input
    list is not modified. Callers must re-run check_bookmark_sanity() on the
    result — this function does not guarantee it is free of hard failures.
    """
    repairs: list[BookmarkRepair] = []
    valid_pages = [p for _, _, p in bookmarks if 1 <= p <= total_pages]
    if not valid_pages:
        return list(bookmarks), repairs

    # Pass 1: drop orphan front-matter subtrees. The first content page is
    # taken from bookmarks outside such subtrees, so compute it iteratively.
    keep = [True] * len(bookmarks)
    for i, (_, title, page_no) in enumerate(bookmarks):
        if page_no >= 1 or not keep[i]:
            continue
        end = _subtree_end(bookmarks, i)
        subtree_pages = [p for _, _, p in bookmarks[i + 1:end] if p >= 1]
        outside_pages = [
            p for j, (_, _, p) in enumerate(bookmarks)
            if not i <= j < end and 1 <= p <= total_pages
        ]
        if not outside_pages:
            continue
        first_content_page = min(outside_pages)
        if all(p < first_content_page for p in subtree_pages):
            for j in range(i, end):
                keep[j] = False
            repairs.append(BookmarkRepair(
                "dropped_orphan_subtree", i, title, page_no, None, end - i,
                f"bookmark[{i}] '{title}' has no destination and its {end - i - 1} "
                f"descendant(s) point before the first content page "
                f"{first_content_page} — dropped as orphan front-matter",
            ))
    kept_idx = [i for i in range(len(bookmarks)) if keep[i]]
    work = [bookmarks[i] for i in kept_idx]

    # Pass 2: relocate (or drop) children whose page precedes their parent's.
    result: list[Bookmark] = []
    i = 0
    while i < len(work):
        level, title, page_no = work[i]
        parent = _parent_index(work, i)
        parent_page = work[parent][2] if parent is not None else None
        if parent_page is None or parent_page < 1 or page_no < 1 or page_no >= parent_page:
            result.append(work[i])
            i += 1
            continue

        # Search window: parent's page up to the next bookmark at this level
        # or shallower that lies at or after the parent's page.
        upper = total_pages
        for j in range(i + 1, len(work)):
            if work[j][0] <= level and work[j][2] >= parent_page:
                upper = work[j][2]
                break
        best_page, best_score = None, 0.0
        for candidate in range(parent_page, min(upper, total_pages) + 1):
            score = _title_line_score(title, page_text(candidate))
            if score > best_score:
                best_page, best_score = candidate, score

        orig = kept_idx[i]
        if best_page is not None and best_score >= _RELOCATE_MIN_SCORE:
            result.append((level, title, best_page))
            repairs.append(BookmarkRepair(
                "relocated", orig, title, page_no, best_page, 0,
                f"bookmark[{orig}] '{title}' page_no={page_no} precedes its parent's "
                f"page_no={parent_page}; title found on page {best_page} "
                f"(score {best_score:.0f}) — relocated, flag for review",
            ))
            i += 1
        else:
            end = _subtree_end(work, i)
            repairs.append(BookmarkRepair(
                "dropped_unresolvable", orig, title, page_no, None, end - i,
                f"bookmark[{orig}] '{title}' page_no={page_no} precedes its parent's "
                f"page_no={parent_page} and its title was not found on pages "
                f"{parent_page}-{upper} — dropped with {end - i - 1} descendant(s)",
            ))
            i = end

    repairs.sort(key=lambda r: r.index)
    return result, repairs
