"""Heading anchor tests for section_matcher (BUG-019)."""

from __future__ import annotations

from src.models.extraction import DoclingDocument, DoclingTextBlock, ExtractionProvenance
from src.tree_builder.section_matcher import (
    _find_heading_anchor,
    _is_partial_match,
    match_content_to_sections,
)


def _block(order: int, text: str, page: int, label: str = "text") -> DoclingTextBlock:
    return DoclingTextBlock(
        block_id=f"b{order}",
        text=text,
        label=label,
        page_no=page,
        reading_order=order,
        depth=0,
        provenance=ExtractionProvenance(source="docling", page_no=page),
    )


def _doc(blocks: list[DoclingTextBlock], pages: int) -> DoclingDocument:
    return DoclingDocument("doc", "doc.pdf", pages, text_blocks=blocks)


def _texts(section) -> list[str]:  # type: ignore[no-untyped-def]
    return [block.text for block in section.text_blocks]


def test_glyph_only_header_never_anchors():
    # 2002 FU chapters: a bullet '!' labelled section_header came before the real heading.
    blocks = {1: [_block(0, "3. Fuel Line", 1), _block(1, "!", 1, "section_header")]}
    assert _find_heading_anchor("3. Fuel Line", 1, blocks) == 0


def test_contained_short_header_does_not_anchor_longer_title():
    blocks = {
        283: [
            _block(10, "Trends", 283, "section_header"),
            _block(11, "Trends are patient data collected over time.", 283),
            _block(12, "Viewing Trends", 283, "section_header"),
        ]
    }
    assert _find_heading_anchor("Viewing Trends", 283, blocks) == 12
    assert _find_heading_anchor("Trends Pop-Up Keys", 283, blocks) is None
    # Philips p294: each sibling has its own header; the shorter one must not take the longer.
    horizon = {
        294: [
            _block(20, "Setting the Horizon", 294, "section_header"),
            _block(21, "The horizon is the reference value.", 294),
            _block(22, "Setting the Horizon Trend Scale", 294, "section_header"),
        ]
    }
    assert _find_heading_anchor("Setting the Horizon", 294, horizon) == 20
    assert _find_heading_anchor("Setting the Horizon Trend Scale", 294, horizon, after=20) == 22


def test_exact_match_wins_over_earlier_partial_match():
    blocks = {
        5: [
            _block(0, "Installing the Pump Assembly", 5, "section_header"),
            _block(1, "Installing the Pump", 5, "section_header"),
        ]
    }
    assert _find_heading_anchor("Installing the Pump", 5, blocks) == 1


def test_numbering_and_long_partial_matches_still_anchor():
    blocks = {7: [_block(3, "1.2 Engine Removal", 7, "section_header")]}
    assert _find_heading_anchor("Engine Removal", 7, blocks) == 3
    blocks = {8: [_block(4, "Engine Removal Procedure", 8, "section_header")]}
    assert _find_heading_anchor("Engine Removal Procedures", 8, blocks) == 4
    assert _is_partial_match("engine removal", "engine removal procedure") is False


def test_anchor_skips_blocks_before_previous_anchor():
    blocks = {9: [_block(0, "Setup", 9, "section_header"), _block(5, "Setup", 9, "section_header")]}
    assert _find_heading_anchor("Setup", 9, blocks, after=0) == 5


def test_philips_trends_sections_get_their_own_content():
    blocks = [
        _block(0, "Trends", 1, "section_header"),
        _block(1, "Trends are patient data collected over time.", 1),
        _block(2, "Viewing Trends", 1, "section_header"),
        _block(3, "Embedded trends appear next to the waves.", 1),
        _block(4, "Trends Pop-Up Keys", 1, "section_header"),
        _block(5, "A selection of trend pop-up keys appears.", 1),
    ]
    bookmarks = [(1, "Trends", 1), (2, "Viewing Trends", 1), (2, "Trends Pop-Up Keys", 1)]
    trends, viewing, keys = match_content_to_sections(bookmarks, _doc(blocks, 1), 1)
    assert _texts(trends) == ["Trends", "Trends are patient data collected over time."]
    assert _texts(viewing) == ["Viewing Trends", "Embedded trends appear next to the waves."]
    assert _texts(keys) == ["Trends Pop-Up Keys", "A selection of trend pop-up keys appears."]


def test_2002_bullet_glyph_does_not_steal_the_heading():
    blocks = [
        _block(0, "FUEL INJECTION (FUEL SYSTEMS)", 1, "section_header"),
        _block(1, "Contents", 1),
        # Real v2 run: the heading is labelled as body text, the bullet as section_header.
        _block(2, "1. General", 2),
        _block(3, "!", 2, "section_header"),
        _block(4, "Fuel is pumped from the tank.", 2),
    ]
    bookmarks = [(1, "FUEL INJECTION (FUEL SYSTEMS)", 1), (2, "1. General", 2)]
    chapter, general = match_content_to_sections(bookmarks, _doc(blocks, 2), 2)
    assert _texts(chapter) == ["FUEL INJECTION (FUEL SYSTEMS)", "Contents"]
    assert _texts(general) == ["1. General", "!", "Fuel is pumped from the tank."]


def test_merged_heading_wins_over_later_figure_label():
    # 2002 p442: heading merged with its sub-heading; a figure label repeats the title later.
    blocks = {
        442: [
            _block(0, "1. Tilt Steering Column A: TILT MECHANISM", 442, "section_header"),
            _block(1, "The steering wheel vertical position can be adjusted.", 442),
            _block(90, "Tilt steering column", 442, "section_header"),
        ]
    }
    assert _find_heading_anchor("1. Tilt Steering Column", 442, blocks) == 0
    assert _find_heading_anchor("1. Tilt Steering", 442, blocks) == 0
    assert _find_heading_anchor("Tilt Steering Column Removal and Setup", 442, blocks) is None
