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
  4. Assign tables by page_no (Docling doesn't give tables a reading_order,
     so this is a known coarser fallback — acceptable since tables are a
     small fraction of content and rarely collide within a shared page).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.models.extraction import DoclingDocument, DoclingTable, DoclingTextBlock
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

        section_id = f"sec_{i + 1:04d}"
        result.append((section_id, title, level, page_start, page_end))

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
) -> list[tuple[int, int]]:
    """
    Compute (reading_order_start, reading_order_end) per bookmark.

    Anchor = reading_order of the bookmark's own matched heading block, or —
    if no heading text match is found on its page — the first block on that
    page, or — if the page has no content at all — the previous section's
    anchor + 1. The max() clamp keeps anchors monotonic non-decreasing so
    ranges never invert even if a heading match lands out of expected order.
    """
    blocks_by_page: dict[int, list[DoclingTextBlock]] = {}
    for b in doc.text_blocks:
        blocks_by_page.setdefault(b.page_no, []).append(b)
    for page_blocks in blocks_by_page.values():
        page_blocks.sort(key=lambda b: b.reading_order)

    anchors: list[int] = []
    prev_anchor = -1
    for _section_id, title, _level, page_start, _page_end in page_ranges:
        anchor = _find_heading_anchor(title, page_start, blocks_by_page, after=prev_anchor)
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


def _assign_content(
    sections: list[MatchedSection],
    reading_order_ranges: dict[str, tuple[int, int]],
    doc: DoclingDocument,
) -> None:
    """
    Assign text_blocks by reading-order interval containment (the section
    with the tightest/most specific containing interval wins — equivalent
    to "deepest" without relying on level matching exactly).

    Assign tables by page_no (see module docstring — known coarser fallback).
    """
    def _tightest(containing: list[MatchedSection]) -> MatchedSection:
        return min(
            containing,
            key=lambda s: reading_order_ranges[s.section_id][1]
            - reading_order_ranges[s.section_id][0],
        )

    for block in doc.text_blocks:
        containing = [
            s
            for s in sections
            if reading_order_ranges[s.section_id][0]
            <= block.reading_order
            <= reading_order_ranges[s.section_id][1]
        ]
        if containing:
            _tightest(containing).text_blocks.append(block)

    page_sections: dict[int, list[MatchedSection]] = {}
    for sec in sections:
        for p in range(sec.page_start, sec.page_end + 1):
            page_sections.setdefault(p, []).append(sec)
    for p in page_sections:
        page_sections[p].sort(key=lambda s: s.level, reverse=True)

    for table in doc.tables:
        candidates = page_sections.get(table.page_no, [])
        if candidates:
            candidates[0].tables.append(table)


def match_content_to_sections(
    bookmarks: list[tuple[int, str, int]],
    doc: DoclingDocument,
    total_pages: int,
    verifications: list[TitleVerification] | None = None,
    numbering_schemes: list[str] | None = None,
    offsets_applied: list[int] | None = None,
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

    Returns:
        list of MatchedSection, one per bookmark, with content assigned.
    """
    if not bookmarks:
        return []

    ranges = _compute_page_ranges(bookmarks, total_pages)
    hierarchy = _build_hierarchy(ranges)
    reading_order_ranges = dict(
        zip(
            (section_id for section_id, *_ in ranges),
            _compute_reading_order_ranges(bookmarks, ranges, doc),
            strict=True,
        )
    )

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

    return sections
