"""section_matcher tests: heading anchors (BUG-019) and table placement (BUG-001, BUG-003)."""

from __future__ import annotations

from src.models.extraction import (
    BoundingBox,
    DoclingDocument,
    DoclingTable,
    DoclingTextBlock,
    ExtractionProvenance,
)
from src.tree_builder.section_matcher import (
    _find_heading_anchor,
    _is_partial_match,
    match_content_to_sections,
)


def _box(page: int, top: float, bottom: float, x0: float = 50, x1: float = 550) -> BoundingBox:
    return BoundingBox(x0, top, x1, bottom, page, coordinate_origin="bottomleft")


def _block(
    order: int, text: str, page: int, label: str = "text", top: float | None = None
) -> DoclingTextBlock:
    return DoclingTextBlock(
        block_id=f"b{order}",
        text=text,
        label=label,
        page_no=page,
        reading_order=order,
        depth=0,
        provenance=ExtractionProvenance(source="docling", page_no=page),
        bbox=None if top is None else _box(page, top, top - 10),
    )


def _table(table_id: str, page: int, top: float | None, bottom: float = 0) -> DoclingTable:
    return DoclingTable(
        table_id=table_id,
        page_no=page,
        provenance=ExtractionProvenance(source="docling", page_no=page),
        bbox=None if top is None else _box(page, top, bottom),
    )


def _doc(
    blocks: list[DoclingTextBlock], pages: int, tables: list[DoclingTable] | None = None
) -> DoclingDocument:
    return DoclingDocument("doc", "doc.pdf", pages, text_blocks=blocks, tables=tables or [])


def _table_ids(section) -> list[str]:  # type: ignore[no-untyped-def]
    return [table.table_id for table in section.tables]


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


def test_chapter_contents_table_stays_with_the_chapter():
    # DOC-0136477A p17: the 'Contents' box is printed above '1.1', the deepest section
    # on the page is 1.2.1; page-based placement gave the box to 1.2.1 (BUG-001).
    blocks = [
        _block(0, "Introduction", 17, "section_header", top=665),
        _block(1, "Contents", 17, "section_header", top=608),
        _block(2, "1.1 Intended Purpose of this Manual", 17, "section_header", top=435),
        _block(3, "This manual describes the monitor.", 17, top=407),
        _block(4, "1.2 Indications For Use", 17, "section_header", top=289),
        _block(5, "1.2.1 Swan-Ganz Module", 17, "section_header", top=257),
        _block(6, "The monitor is used with the module.", 17, top=235),
    ]
    bookmarks = [
        (1, "Introduction", 17),
        (2, "1.1 Intended Purpose of this Manual", 17),
        (2, "1.2 Indications For Use", 17),
        (3, "1.2.1 Swan-Ganz Module", 17),
    ]
    tables = [_table("#/tables/15", 17, top=596, bottom=456)]
    chapter, purpose, _uses, module = match_content_to_sections(
        bookmarks, _doc(blocks, 17, tables), 17
    )
    assert _table_ids(chapter) == ["#/tables/15"]
    assert _table_ids(purpose) == _table_ids(module) == []


def test_tables_follow_the_heading_printed_above_them():
    # Philips p411: the charger table is under 'Battery Accessories' (was left empty),
    # and the table at the top of the page continues the previous section (BUG-003).
    blocks = [
        _block(0, "Cable Accessories", 1, "section_header", top=700),
        _block(1, "Use these cables.", 1, top=680),
        _block(2, "Patient Monitor", 2, top=790),  # running header
        _block(3, "Battery Accessories", 2, "section_header", top=400),
    ]
    bookmarks = [(2, "Cable Accessories", 1), (2, "Battery Accessories", 2)]
    tables = [
        _table("top_of_p2", 2, top=770, bottom=500),
        _table("charger", 2, top=380, bottom=300),
        _table("no_bbox", 2, top=None),
    ]
    cables, battery = match_content_to_sections(bookmarks, _doc(blocks, 2, tables), 2)
    assert _table_ids(cables) == ["top_of_p2"]
    assert _table_ids(battery) == ["charger", "no_bbox"]


def test_table_prefers_the_block_in_its_own_column():
    blocks = [
        _block(0, "Left Topic", 1, "section_header", top=700),
        _block(1, "Right Topic", 1, "section_header", top=500),
    ]
    blocks[1] = DoclingTextBlock(
        "b1", "Right Topic", "section_header", 1, 1, 0,
        ExtractionProvenance(source="docling", page_no=1),
        bbox=_box(1, 500, 490, x0=320, x1=550),
    )
    bookmarks = [(2, "Left Topic", 1), (2, "Right Topic", 1)]
    tables = [DoclingTable(
        "left", 1, ExtractionProvenance(source="docling", page_no=1),
        bbox=_box(1, 480, 300, x0=50, x1=280),
    )]
    left, right = match_content_to_sections(bookmarks, _doc(blocks, 1, tables), 1)
    assert _table_ids(left) == ["left"]
    assert _table_ids(right) == []


def test_table_keeps_page_placement_when_reading_order_is_out_of_sync():
    # SOMATOM (BUG-005): the text printed above the table on p5 was read right after the
    # p1 heading, so it belongs to a section whose pages end long before p5.
    blocks = [
        _block(0, "Operating elements", 1, "section_header", top=700),
        _block(1, "Text read out of order.", 5, top=650),
        _block(2, "Cushions", 2, "section_header", top=700),
        _block(3, "Quality of bonding", 5, "section_header", top=750),
    ]
    bookmarks = [
        (2, "Operating elements", 1),
        (2, "Cushions", 2),
        (2, "Quality of bonding", 5),
    ]
    tables = [_table("t", 5, top=600, bottom=500)]
    elements, _cushions, bonding = match_content_to_sections(
        bookmarks, _doc(blocks, 5, tables), 5
    )
    assert _texts(elements) == ["Operating elements", "Text read out of order."]
    assert _table_ids(elements) == []
    assert _table_ids(bonding) == ["t"]
