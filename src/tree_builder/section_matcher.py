"""
Section matcher — assign docling content blocks to bookmark sections.

Algorithm:
  1. Compute page ranges from bookmarks (page_start → next bookmark page - 1)
  2. Build hierarchy via level stack (parent/child from bookmark levels)
  3. Assign text blocks by reading-order interval, anchored to each bookmark's
     own heading text block — NOT by page_no alone. Page_no can't disambiguate
     sibling sections that share a page (common for short subsections): if
     three headings land on the same page, page-based assignment sends every
     block on that page to whichever section sorts first, starving the rest
     (node_count=0). Reading order — Docling's global sequential block index —
     pins each section's true start regardless of page-sharing.
  4. Assign tables by their position on the page: a table gets the reading
     order of the nearest text block printed above it (Docling doesn't give
     tables a reading_order). A table at the top of a page continues the
     previous content. Tables without a bbox, or whose position points to a
     section more than one page away from its page range (reading order out
     of sync, BUG-005), fall back to page_no (deepest section on the page).
     Chapter 'Contents' boxes and tables on pages shared by sibling sections
     depend on this (BUG-001, BUG-003).
  5. Extend page_end by one page when the section owns body content (not page
     furniture) on the page where the next section starts (BUG-014).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from src.models.extraction import BoundingBox, DoclingDocument, DoclingTable, DoclingTextBlock
from src.tree_builder.title_verification import TitleVerification


@dataclass
class MatchedSection:
    """A bookmark section with its matched content blocks."""

    section_id: str
    title: str
    level: int
    page_start: int
    page_end: int
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)
    text_blocks: list[DoclingTextBlock] = field(default_factory=list)
    tables: list[DoclingTable] = field(default_factory=list)
    # Title verification (see title_verification.py) — a bookmark whose title
    # wasn't found near its claimed page is kept, not dropped, but flagged.
    flagged_for_review: bool = False
    verification_score: float | None = None
    verification_reason: str = ""
    # Page-numbering provenance (see toc_resolution.py) — what scheme this
    # bookmark's claimed page used and what offset (global or per-cluster)
    # was applied to resolve it to a physical page.
    numbering_scheme: str = "arabic"
    offset_applied: int = 0


def _section_id(index: int) -> str:
    return f"sec_{index + 1:04d}"


def _compute_page_ranges(
    bookmarks: list[tuple[int, str, int]],
    total_pages: int,
) -> list[tuple[str, str, int, int, int]]:
    """
    Compute (section_id, title, level, page_start, page_end) for each bookmark.

    page_end for bookmark[i] = bookmark[i+1].page_no - 1 for next same-or-higher level.
    Last bookmark gets page_end = total_pages.

    Bookmarks with page_no < 1 are clamped to 1.
    Bookmarks with page_no > total_pages are clamped to total_pages.
    """
    result: list[tuple[str, str, int, int, int]] = []

    for i, (level, title, page_no) in enumerate(bookmarks):
        page_start = max(1, min(page_no, total_pages))

        # Find next bookmark at same or higher level to determine page_end
        page_end = total_pages
        for j in range(i + 1, len(bookmarks)):
            next_level, _, next_page = bookmarks[j]
            if next_level <= level:
                page_end = max(page_start, next_page - 1)
                break

        result.append((_section_id(i), title, level, page_start, page_end))

    return result


def _build_hierarchy(
    ranges: list[tuple[str, str, int, int, int]],
) -> dict[str, tuple[str | None, list[str]]]:
    """
    Build parent_id and child_ids from bookmark levels using a stack.

    Returns dict[section_id -> (parent_id, child_ids)].
    """
    hierarchy: dict[str, tuple[str | None, list[str]]] = {}
    # Stack of (level, section_id) — tracks current ancestor at each level
    stack: list[tuple[int, str]] = []

    for section_id, _title, level, _ps, _pe in ranges:
        # Pop stack until we find a parent (level < current)
        while stack and stack[-1][0] >= level:
            stack.pop()

        parent_id = stack[-1][1] if stack else None
        hierarchy[section_id] = (parent_id, [])

        # Register as child of parent
        if parent_id is not None and parent_id in hierarchy:
            hierarchy[parent_id][1].append(section_id)

        stack.append((level, section_id))

    return hierarchy


def _normalize_heading(text: str) -> str:
    """Normalize heading text for tolerant matching (case/whitespace/punctuation)."""
    text = re.sub(r"[^\w\s]", "", text.strip().lower())
    return " ".join(text.split())


def _strip_numbering(norm: str) -> str:
    """Drop leading numbering tokens ('12 engine' -> 'engine') from a normalized heading."""
    tokens = norm.split()
    while len(tokens) > 1 and any(char.isdigit() for char in tokens[0]):
        tokens.pop(0)
    return " ".join(tokens)


# A partial match is accepted only when the heading text covers most of the
# title (or the reverse). Short or glyph-only headings never anchor a section:
# '!' normalizes to '' and 'Trends' is contained in 'Viewing Trends' (BUG-019).
_MIN_PARTIAL_CHARS = 3
_MIN_PARTIAL_RATIO = 0.8


def _is_partial_match(norm_title: str, norm_text: str) -> bool:
    shorter, longer = sorted((norm_title, norm_text), key=len)
    if len(shorter) < _MIN_PARTIAL_CHARS or shorter not in longer:
        return False
    return len(shorter) / len(longer) >= _MIN_PARTIAL_RATIO


def _find_heading_anchor(
    title: str,
    page_no: int,
    blocks_by_page: dict[int, list[DoclingTextBlock]],
    after: int = -1,
) -> int | None:
    """
    Find the reading_order of the text block that IS this bookmark's own
    heading, by matching normalized text among blocks on the bookmark's page.

    Only blocks after ``after`` (the previous section's anchor) are candidates,
    so two bookmarks never anchor on the same heading. Match tiers, first hit
    wins: exact text on a "section_header" block; then the first
    "section_header" in reading order that matches without leading numbering,
    starts with the title (Docling merges a heading with its sub-heading) or
    covers most of it; then exact text on any block (headings are sometimes
    mislabeled as body text). Figure labels can repeat a title later in
    reading order, so the near-match tier keeps reading order, not match type.
    """
    norm_title = _normalize_heading(title)
    if not norm_title:
        return None
    core_title = _strip_numbering(norm_title)
    candidates = [
        (block, _normalize_heading(block.text))
        for block in blocks_by_page.get(page_no, [])
        if block.reading_order > after
    ]
    headers = [(block, text) for block, text in candidates if block.label == "section_header"]
    def near_match(text: str) -> bool:
        if not text:
            return False
        return (
            _strip_numbering(text) == core_title
            or text.startswith(norm_title + " ")
            or _is_partial_match(norm_title, text)
        )

    tiers = (
        (headers, lambda text: text == norm_title),
        (headers, near_match),
        (candidates, lambda text: text == norm_title),
    )
    for blocks, matches in tiers:
        for block, text in blocks:
            if matches(text):
                return block.reading_order
    return None


def _compute_reading_order_ranges(
    bookmarks: list[tuple[int, str, int]],
    page_ranges: list[tuple[str, str, int, int, int]],
    doc: DoclingDocument,
    boundaries: list[bool] | None = None,
) -> list[tuple[int, int]]:
    """
    Compute (reading_order_start, reading_order_end) per bookmark.

    Anchor = reading_order of the bookmark's own matched heading block, or —
    if no heading text match is found on its page — the first block on that
    page, or — if the page has no content at all — the previous section's
    anchor + 1. The max() clamp keeps anchors monotonic non-decreasing so
    ranges never invert even if a heading match lands out of expected order.
    A boundary (an excluded Index or Table of contents) starts on a page of its
    own, so it anchors on the first block of its page: its title can come late
    in reading order (LOGIQ_e p563, after the index columns).
    """
    blocks_by_page: dict[int, list[DoclingTextBlock]] = {}
    for b in doc.text_blocks:
        blocks_by_page.setdefault(b.page_no, []).append(b)
    for page_blocks in blocks_by_page.values():
        page_blocks.sort(key=lambda b: b.reading_order)

    anchors: list[int] = []
    prev_anchor = -1
    for i, (_section_id, title, _level, page_start, _page_end) in enumerate(page_ranges):
        anchor = (
            None
            if boundaries and boundaries[i]
            else _find_heading_anchor(title, page_start, blocks_by_page, after=prev_anchor)
        )
        if anchor is None:
            page_blocks = blocks_by_page.get(page_start, [])
            anchor = page_blocks[0].reading_order if page_blocks else prev_anchor + 1
        anchor = max(anchor, prev_anchor + 1)
        anchors.append(anchor)
        prev_anchor = anchor

    max_reading_order = max((b.reading_order for b in doc.text_blocks), default=0)

    ranges: list[tuple[int, int]] = []
    for i, (level, _title, _page) in enumerate(bookmarks):
        end = max_reading_order
        for j in range(i + 1, len(bookmarks)):
            next_level = bookmarks[j][0]
            if next_level <= level:
                end = anchors[j] - 1
                break
        ranges.append((anchors[i], max(anchors[i], end)))

    return ranges


# A block counts as "above" a table or image when its bottom is at most this many
# points below the table's top edge (bboxes of adjacent items can touch or overlap).
_ABOVE_TOLERANCE = 2.0
# A heading counts as "above" when its top is at most this many points below the item's
# top edge: side headings in the left margin start level with their content (SOMATOM).
_SIDE_HEADING_TOLERANCE = 12.0


def vertical_span(bbox: BoundingBox) -> tuple[float, float]:
    """
    (top, bottom) of a bbox, with larger values higher on the page for either origin.

    Only bboxes in the same coordinate frame can be compared.
    """
    if bbox.coordinate_origin == "bottomleft":
        return max(bbox.y0, bbox.y1), min(bbox.y0, bbox.y1)
    return -min(bbox.y0, bbox.y1), -max(bbox.y0, bbox.y1)


def nearest_above[T](
    target: BoundingBox, items: list[tuple[BoundingBox, bool, T]]
) -> T | None:
    """
    Payload of the item printed closest above ``target`` on the same page.

    Items are ``(bbox, is_heading, payload)``. Items that overlap the target horizontally
    win over items in another column. A heading reaches to the right edge of the page
    and also counts when it starts level with the target: content under a left-aligned
    or margin heading is often indented or in a column to its right (LOGIQ_S8 part
    photos, SOMATOM side headings); otherwise a full-width running header above the
    heading counts as "same column" and wins. None when nothing is above the target.
    """
    top, _bottom = vertical_span(target)
    above: list[tuple[bool, float, T]] = []
    for bbox, is_heading, payload in items:
        item_top, item_bottom = vertical_span(bbox)
        beside = is_heading and item_top >= top - _SIDE_HEADING_TOLERANCE
        if item_bottom < top - _ABOVE_TOLERANCE and not beside:
            continue
        right = math.inf if is_heading else bbox.x1
        overlaps = min(right, target.x1) > max(bbox.x0, target.x0)
        above.append((overlaps, item_bottom - top, payload))
    if not above:
        return None
    same_column = [item for item in above if item[0]] or above
    return min(same_column, key=lambda item: item[1])[2]


def _table_position(
    table: DoclingTable, blocks_by_page: dict[int, list[DoclingTextBlock]]
) -> int | None:
    """
    Reading order of the text block the table follows, or None when it can't be placed.

    That is the nearest block above the table; for a table above every block of its
    page, the block just before the page (the table continues the previous content).
    """
    page_blocks = blocks_by_page.get(table.page_no, [])
    if table.bbox is None or not page_blocks:
        return None
    placed = [
        (block.bbox, block.label == "section_header", block)
        for block in page_blocks
        if block.bbox is not None
    ]
    block = nearest_above(table.bbox, placed)
    if block is not None:
        return block.reading_order
    previous = page_blocks[0].reading_order - 1
    return previous if previous >= 0 else None


def _assign_content(
    sections: list[MatchedSection],
    reading_order_ranges: dict[str, tuple[int, int]],
    doc: DoclingDocument,
) -> None:
    """
    Assign text_blocks by reading-order interval containment (the section
    with the tightest/most specific containing interval wins — equivalent
    to "deepest" without relying on level matching exactly).

    Assign tables by their position on the page (see module docstring); tables
    without a bbox fall back to the deepest section on their page.
    """
    def _tightest(containing: list[MatchedSection]) -> MatchedSection:
        return min(
            containing,
            key=lambda s: reading_order_ranges[s.section_id][1]
            - reading_order_ranges[s.section_id][0],
        )

    def _owner(position: int) -> MatchedSection | None:
        containing = [
            s
            for s in sections
            if reading_order_ranges[s.section_id][0]
            <= position
            <= reading_order_ranges[s.section_id][1]
        ]
        return _tightest(containing) if containing else None

    blocks_by_page: dict[int, list[DoclingTextBlock]] = {}
    for block in doc.text_blocks:
        blocks_by_page.setdefault(block.page_no, []).append(block)
        owner = _owner(block.reading_order)
        if owner is not None:
            owner.text_blocks.append(block)
    for page_blocks in blocks_by_page.values():
        page_blocks.sort(key=lambda b: b.reading_order)

    page_sections: dict[int, list[MatchedSection]] = {}
    for sec in sections:
        for p in range(sec.page_start, sec.page_end + 1):
            page_sections.setdefault(p, []).append(sec)
    for p in page_sections:
        page_sections[p].sort(key=lambda s: s.level, reverse=True)

    for table in doc.tables:
        position = _table_position(table, blocks_by_page)
        owner = _owner(position) if position is not None else None
        # Reading order can be out of sync with the pages (BUG-005): only trust an
        # owner whose page range contains the table or ends on the page before it
        # (a table continued at the top of the next page).
        if owner is None or not owner.page_start <= table.page_no <= owner.page_end + 1:
            candidates = page_sections.get(table.page_no, [])
            owner = candidates[0] if candidates else None
        if owner is not None:
            owner.tables.append(table)


# Docling labels for page furniture, and the top/bottom band of a page where running
# headers, footers, folios and chapter tabs sit when Docling labels them as body text.
_FURNITURE_LABELS = frozenset({"page_header", "page_footer"})
_FURNITURE_BAND = 0.08
# Body text needs at least this many alphabetic words: chapter-tab numbers ('25'),
# margin labels ('MP40/MP50/ MP60') and lone 'WARNING' labels on the next chapter's
# opening page are not content that continues there (Philips v2.4).
_MIN_BODY_WORDS = 3
_WORD = re.compile(r"^[^\W\d_][^\W\d_'\u2019-]*[.,:;!?)]?$")


def _is_body_on_page(block: DoclingTextBlock, doc: DoclingDocument) -> bool:
    """
    True unless the block is page furniture (label, or fully inside the top/bottom band),
    a heading, or shorter than three words. A heading alone on the next page is usually
    the first part of the next section's split title ('Section 1-9' +
    'Electromagnetic Compatibility', LOGIQ_S8).
    """
    if block.label in _FURNITURE_LABELS or block.label == "section_header":
        return False
    words = sum(1 for token in block.text.split() if _WORD.match(token.strip("(\"'")))
    if words < _MIN_BODY_WORDS:
        return False
    page = doc.pages.get(block.page_no)
    if block.bbox is None or page is None or page.height <= 0:
        return True
    top, bottom = vertical_span(block.bbox)
    if block.bbox.coordinate_origin != "bottomleft":
        top, bottom = page.height + top, page.height + bottom
    band = page.height * _FURNITURE_BAND
    return not (bottom >= page.height - band or top <= band)


def _extend_page_ends(sections: list[MatchedSection], doc: DoclingDocument) -> None:
    """
    Extend page_end by one page when the section owns body content on that page.

    page_end comes from the next bookmark's page, so a section whose content runs onto
    the page where the next section starts mid-page ended one page short (BUG-014,
    H-15). Positional table placement (BUG-001/003) makes this more common: a table
    continued at the top of the next page stays with its section. Only one page is
    added, so content far away (reading order out of sync, BUG-005) never stretches a
    range. Parents are then widened to contain their children.
    """
    for section in sections:
        next_page = section.page_end + 1
        owns_body = any(table.page_no == next_page for table in section.tables) or any(
            block.page_no == next_page and _is_body_on_page(block, doc)
            for block in section.text_blocks
        )
        if owns_body:
            section.page_end = next_page
    by_id = {section.section_id: section for section in sections}
    for section in reversed(sections):
        parent = by_id.get(section.parent_id) if section.parent_id else None
        if parent is not None and parent.page_end < section.page_end:
            parent.page_end = section.page_end


# An index page has an index marker (an 'Index' or '#' heading, letter headings, or an
# 'Index - 2' running header or footer) and many page references among its words.
_INDEX_HEADINGS = frozenset({"index", "#"})
_INDEX_FURNITURE = re.compile(r"^index\b", re.IGNORECASE)
_PAGE_REF = re.compile(r"^\(?(?:[ivxlc]+[-\u2013])?\d{1,4}(?:[-\u2013]\d{1,4})?[,;.)]?$", re.I)
_LETTERS = re.compile(r"[A-Za-z]{2,}")
_INDEX_MIN_WORDS = 30
_INDEX_MIN_REF_SHARE = 0.25


def find_unbookmarked_index(doc: DoclingDocument, after_page: int) -> int | None:
    """
    First page of an alphabetical index at the end of the document that has no
    bookmark (Philips p485, LOGIQ_S8 p911), or None (BUG-002).

    Walks back from the last page while pages are index pages or have almost no
    text (blank pages, the back cover), and stops at the first page of real text.
    The index starts at the earliest index page of that run with an index marker,
    and must start after ``after_page`` (the last bookmark's page).
    """
    words: dict[int, list[str]] = {}
    marked: set[int] = set()
    for block in doc.text_blocks:
        text = block.text.strip()
        if block.label in _FURNITURE_LABELS:
            if _INDEX_FURNITURE.match(text):
                marked.add(block.page_no)
            continue
        if block.label in {"section_header", "title"} and (
            text.lower() in _INDEX_HEADINGS or (len(text) == 1 and text.isalpha())
        ):
            marked.add(block.page_no)
        words.setdefault(block.page_no, []).extend(text.split())

    start = None
    for page in sorted(words, reverse=True):
        if page <= after_page:
            break
        tokens = words[page]
        word_count = sum(1 for token in tokens if _LETTERS.search(token))
        if word_count < _INDEX_MIN_WORDS:
            continue
        refs = sum(1 for token in tokens if _PAGE_REF.match(token))
        if refs / word_count < _INDEX_MIN_REF_SHARE:
            break
        if page in marked:
            start = page
    return start


def match_content_to_sections(
    bookmarks: list[tuple[int, str, int]],
    doc: DoclingDocument,
    total_pages: int,
    verifications: list[TitleVerification] | None = None,
    numbering_schemes: list[str] | None = None,
    offsets_applied: list[int] | None = None,
    boundaries: list[bool] | None = None,
) -> list[MatchedSection]:
    """
    Match docling content blocks to bookmark sections.

    Args:
        bookmarks: list of (level, title, page_no) from fitz.get_toc() — page_no
            here is expected to already be resolved to a physical page (see
            toc_resolution.resolve_toc_pages).
        doc: DoclingDocument with text_blocks and tables
        total_pages: total page count of the PDF
        verifications: optional per-bookmark verification results, same
            order/length as bookmarks. When provided, a bookmark that failed
            verification is still built into a section (never dropped) but
            flagged_for_review=True with its score/reason attached.
        numbering_schemes: optional per-bookmark numbering scheme labels
            ("arabic" | "roman" | "alphanumeric" | "unknown"), same order as
            bookmarks — see toc_resolution.ResolvedBookmark.numbering_scheme.
        offsets_applied: optional per-bookmark offset (global or per-cluster)
            that was applied to resolve this bookmark's page.
        boundaries: optional flags, same order as bookmarks. A flagged entry (an
            excluded Index or Table of contents bookmark) ends the sections before
            it but builds no section, so its pages stay outside the tree (BUG-002).
            verifications, numbering_schemes and offsets_applied list only the
            entries that are not flagged.

    Returns:
        list of MatchedSection, one per bookmark that is not a boundary, with
        content assigned.
    """
    if not bookmarks:
        return []

    all_ranges = _compute_page_ranges(bookmarks, total_pages)
    all_reading_order = _compute_reading_order_ranges(bookmarks, all_ranges, doc, boundaries)
    kept = [i for i in range(len(bookmarks)) if not (boundaries and boundaries[i])]
    ranges = [(_section_id(n), *all_ranges[i][1:]) for n, i in enumerate(kept)]
    hierarchy = _build_hierarchy(ranges)
    reading_order_ranges = {
        ranges[n][0]: all_reading_order[i] for n, i in enumerate(kept)
    }

    sections: list[MatchedSection] = []
    for i, (section_id, title, level, page_start, page_end) in enumerate(ranges):
        parent_id, child_ids = hierarchy[section_id]
        verification = verifications[i] if verifications is not None else None
        sections.append(
            MatchedSection(
                section_id=section_id,
                title=title,
                level=level,
                page_start=page_start,
                page_end=page_end,
                parent_id=parent_id,
                child_ids=list(child_ids),
                flagged_for_review=(verification is not None and not verification.passed),
                verification_score=verification.score if verification is not None else None,
                verification_reason=verification.reason if verification is not None else "",
                numbering_scheme=(
                    numbering_schemes[i] if numbering_schemes is not None else "arabic"
                ),
                offset_applied=offsets_applied[i] if offsets_applied is not None else 0,
            )
        )

    _assign_content(sections, reading_order_ranges, doc)
    _extend_page_ends(sections, doc)

    return sections
