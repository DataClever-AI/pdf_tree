"""section_matcher tests: heading anchors (BUG-019) and table placement (BUG-001, BUG-003)."""

from __future__ import annotations

from src.models.extraction import (
    BoundingBox,
    DoclingDocument,
    DoclingPage,
    DoclingTable,
    DoclingTextBlock,
    ExtractionProvenance,
)
from src.tree_builder.section_matcher import (
    _find_heading_anchor,
    _is_partial_match,
    _split_merged_margin_headings,
    find_unbookmarked_index,
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


def test_table_right_of_a_left_aligned_heading_follows_the_heading():
    blocks = [
        _block(0, "Previous", 1, "section_header", top=700),
        _block(1, "Running header", 2, top=780),
        DoclingTextBlock(
            "b2", "Power Cord", "section_header", 2, 2, 0,
            ExtractionProvenance(source="docling", page_no=2),
            bbox=_box(2, 720, 700, x0=36, x1=118),
        ),
    ]
    bookmarks = [(2, "Previous", 1), (2, "Power Cord", 2)]
    tables = [DoclingTable(
        "cords", 2, ExtractionProvenance(source="docling", page_no=2),
        bbox=_box(2, 680, 300, x0=300, x1=550),
    )]
    previous, power_cord = match_content_to_sections(bookmarks, _doc(blocks, 2, tables), 2)
    assert _table_ids(previous) == []
    assert _table_ids(power_cord) == ["cords"]


def _paged_doc(
    blocks: list[DoclingTextBlock], pages: int, tables: list[DoclingTable] | None = None
) -> DoclingDocument:
    return DoclingDocument(
        "doc",
        "doc.pdf",
        pages,
        pages={n: DoclingPage(n, 612, 792) for n in range(1, pages + 1)},
        text_blocks=blocks,
        tables=tables or [],
    )


def test_page_end_includes_the_page_where_owned_content_continues():
    # DOC p180: 'Table 13-9 (continued)' at the top of the next section's page stays
    # with its section; page_end must include that page (BUG-014).
    blocks = [
        _block(0, "13.5.3 Faults", 1, "section_header", top=700),
        _block(1, "Faults text.", 1, top=650),
        _block(2, "HemoSphere Advanced Monitor", 2, top=770),  # running header band
        _block(3, "13.5.4 SVR Faults", 2, "section_header", top=400),
    ]
    bookmarks = [(1, "Chapter", 1), (2, "13.5.3 Faults", 1), (2, "13.5.4 SVR Faults", 2)]
    blocks = [_block(0, "Chapter", 1, "section_header", top=750)] + [
        DoclingTextBlock(b.block_id, b.text, b.label, b.page_no, i + 1, 0, b.provenance,
                         bbox=b.bbox)
        for i, b in enumerate(blocks)
    ]
    tables = [_table("continued", 2, top=740, bottom=500)]
    chapter, faults, svr = match_content_to_sections(
        bookmarks, _paged_doc(blocks, 2, tables), 2
    )
    assert _table_ids(faults) == ["continued"]
    assert (faults.page_start, faults.page_end) == (1, 2)
    assert (svr.page_start, svr.page_end) == (2, 2)
    assert chapter.page_end == 2


def test_page_end_ignores_running_headers_on_the_next_page():
    blocks = [
        _block(0, "Faults", 1, "section_header", top=700),
        _block(1, "Faults text.", 1, top=650),
        _block(2, "HemoSphere Advanced Monitor", 2, top=770),
        _block(3, "Chapter 2", 2, "page_header", top=500),
        _block(4, "SVR Faults", 2, "section_header", top=400),
    ]
    bookmarks = [(2, "Faults", 1), (2, "SVR Faults", 2)]
    faults, svr = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    # The running headers of p2 go with the section that starts there (BUG-022).
    assert _texts(faults) == ["Faults", "Faults text."]
    assert _texts(svr)[:2] == ["HemoSphere Advanced Monitor", "Chapter 2"]
    assert faults.page_end == 1


def test_page_end_grows_by_one_page_at_most():
    # BUG-005: text read out of order far away never stretches the range.
    blocks = [
        _block(0, "Operating elements", 1, "section_header", top=700),
        _block(1, "Text from page 5.", 5, top=500),
        _block(2, "Cushions", 2, "section_header", top=700),
    ]
    bookmarks = [(2, "Operating elements", 1), (2, "Cushions", 2)]
    elements, _cushions = match_content_to_sections(bookmarks, _paged_doc(blocks, 5), 5)
    assert elements.page_end == 1


def test_page_end_ignores_a_split_heading_of_the_next_section():
    # LOGIQ_S8 p73: 'Section 1-9' is read before the rest of the title, so the previous
    # section owns it; that alone must not extend its page_end.
    blocks = [
        _block(0, "Section 1-8 Returning", 1, "section_header", top=700),
        _block(1, "Shipping text.", 1, top=650),
        _block(2, "Section 1-9", 2, "section_header", top=726),
        _block(3, "Electromagnetic Compatibility", 2, "section_header", top=712),
        _block(4, "EMC text.", 2, top=680),
    ]
    bookmarks = [
        (2, "Section 1-8 Returning", 1),
        (2, "Electromagnetic Compatibility", 2),
    ]
    returning, _emc = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert "Section 1-9" in _texts(returning)
    assert returning.page_end == 1


def test_page_end_ignores_chapter_numbers_and_margin_labels_on_the_next_page():
    # Philips p321: the last section of chapter 24 owns only the chapter-tab number '25'
    # and a margin label of the next chapter; its page_end must stay on p320.
    blocks = [
        _block(0, "Care and Cleaning", 1, "section_header", top=700),
        _block(1, "Clean the monitor with a soft cloth.", 1, top=650),
        _block(2, "25", 2, top=680),
        _block(3, "MP40/MP50/ MP60/MP70/ MP90", 2, top=600),
        _block(4, "Maintenance", 2, "section_header", top=560),
        _block(5, "Check the monitor every year.", 2, top=520),
    ]
    bookmarks = [(2, "Care and Cleaning", 1), (2, "Maintenance", 2)]
    care, maintenance = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    # The chapter number and margin label go with the next chapter (BUG-022).
    assert _texts(care) == ["Care and Cleaning", "Clean the monitor with a soft cloth."]
    assert _texts(maintenance)[:2] == ["25", "MP40/MP50/ MP60/MP70/ MP90"]
    assert care.page_end == 1


def test_excluded_index_bookmark_ends_the_last_section():
    # LOGIQ_e p563: the 'Index' bookmark is excluded from the tree; its pages must not
    # be absorbed by the last section (BUG-002).
    blocks = [
        _block(0, "Care & Maintenance", 1, "section_header"),
        _block(1, "Inspection paper work.", 1),
        _block(2, "probe, cleaning 11-52", 2),
        _block(3, "Index", 2, "section_header"),  # the title comes after the columns
    ]
    bookmarks = [(1, "Care & Maintenance", 1), (1, "Index", 2)]
    (care,) = match_content_to_sections(
        bookmarks, _paged_doc(blocks, 3), 3, boundaries=[False, True]
    )
    assert care.section_id == "sec_0001"
    assert care.page_end == 1
    assert _texts(care) == ["Care & Maintenance", "Inspection paper work."]


def test_section_ids_skip_the_boundary_entries():
    blocks = [
        _block(0, "Legend", 1, "section_header"),
        _block(1, "Table of contents", 2, "section_header"),
        _block(2, "Introduction", 3, "section_header"),
    ]
    bookmarks = [(1, "Legend", 1), (1, "Table of contents", 2), (1, "Introduction", 3)]
    legend, intro = match_content_to_sections(
        bookmarks, _paged_doc(blocks, 3), 3, boundaries=[False, True, False]
    )
    assert (legend.section_id, legend.page_end) == ("sec_0001", 1)
    assert (intro.section_id, intro.page_start) == ("sec_0002", 3)


_INDEX_LINES = " ".join(f"probe term{n} {n}, {n + 3}" for n in range(1, 21))  # 40 words, 40 refs


def test_unbookmarked_index_starts_at_the_marked_page():
    # LOGIQ_S8 p911: 'INDEX' and letter headings, entries with page references.
    blocks = [
        _block(0, "Real text " * 20, 1),
        _block(1, "INDEX", 2, "section_header"),
        _block(2, "A", 2, "section_header"),
        _block(3, _INDEX_LINES, 2),
        _block(4, _INDEX_LINES, 3),
        _block(5, "Index - 2", 3, "page_footer"),
        _block(6, "(c) 2012 General Electric", 4),  # back cover: almost no text
    ]
    assert find_unbookmarked_index(_paged_doc(blocks, 4), after_page=1) == 2


def test_no_index_without_a_marker_or_before_the_last_bookmark():
    # A table of contents is also dense with page numbers but has no index marker.
    contents = [_block(0, _INDEX_LINES, 1), _block(1, _INDEX_LINES, 2)]
    assert find_unbookmarked_index(_paged_doc(contents, 2), after_page=0) is None
    marked = [_block(0, "#", 2, "section_header"), _block(1, _INDEX_LINES, 2)]
    assert find_unbookmarked_index(_paged_doc(marked, 2), after_page=2) is None


def test_running_header_stays_with_the_section_that_continues_on_the_page():
    # 2002 p8: the page continues the previous section, so its running header stays there.
    blocks = [
        _block(0, "Specifications", 1, "section_header", top=700),
        _block(1, "Steering ratio is given in the table.", 1, top=650),
        _block(2, "Specifications", 2, "page_header", top=770),
        _block(3, "Capacity of the fuel tank is given here.", 2, top=650),
        _block(4, "Outback", 2, "section_header", top=400),
    ]
    bookmarks = [(2, "Specifications", 1), (2, "Outback", 2)]
    specs, outback = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert "Specifications" == _texts(specs)[2]
    assert _texts(outback) == ["Outback"]


def test_short_text_that_continues_a_list_is_not_furniture():
    # SOMATOM p393: 'Table joystick' and 'Mouse joystick' end the previous section's
    # list at the top of the page; they are not running headers.
    blocks = [
        _block(0, "Joysticks", 1, "section_header", top=700),
        _block(1, "Use one of these joysticks:", 1, top=650),
        _block(2, "SOMATOM header", 2, "page_header", top=780),
        _block(3, "Table joystick", 2, "list_item", top=600),
        _block(4, "Scrolling", 2, "section_header", top=500),
    ]
    bookmarks = [(2, "Joysticks", 1), (2, "Scrolling", 2)]
    joysticks, scrolling = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert _texts(joysticks)[-2:] == ["SOMATOM header", "Table joystick"]
    assert _texts(scrolling) == ["Scrolling"]


def _side(order: int, text: str, page: int, label: str, top: float, x0: float, x1: float):  # type: ignore[no-untyped-def]
    return DoclingTextBlock(
        block_id=f"b{order}", text=text, label=label, page_no=page, reading_order=order,
        depth=0, provenance=ExtractionProvenance(source="docling", page_no=page),
        bbox=_box(page, top, top - 10, x0, x1),
    )


def test_margin_headings_get_the_text_beside_and_below_them():
    # SOMATOM p393: Docling reads every margin heading first, then the whole body
    # (BUG-029). Each heading must get the text level with it and below it.
    blocks = [
        _side(0, "Previous step text.", 1, "text", 700, 199, 538),
        _side(1, "Scrolling", 2, "section_header", 536, 96, 184),
        _side(2, "Toggling", 2, "section_header", 308, 109, 184),
        _side(3, "Box text printed above the first heading.", 2, "text", 572, 199, 400),
        _side(4, "Image segment is selected.", 2, "text", 536, 199, 400),
        _side(5, "Move the joystick up or down.", 2, "text", 452, 199, 500),
        _side(6, "Toggle between the image segments.", 2, "text", 278, 199, 500),
    ]
    bookmarks = [(2, "Previous", 1), (2, "Scrolling", 2), (2, "Toggling", 2)]
    previous, scrolling, toggling = match_content_to_sections(
        bookmarks, _paged_doc(blocks, 2), 2
    )
    assert _texts(previous)[-1] == "Box text printed above the first heading."
    assert _texts(scrolling) == [
        "Scrolling", "Image segment is selected.", "Move the joystick up or down."
    ]
    assert _texts(toggling) == ["Toggling", "Toggle between the image segments."]


def test_margin_heading_merged_with_its_note_is_an_anchor():
    # SOMATOM p295: the heading and the margin note below it are one 'text' block.
    blocks = [
        _side(0, "Previous", 1, "section_header", 700, 199, 538),
        _side(1, "Step two of the previous task.", 2, "text", 627, 199, 517),
        _side(2, "Planning the scan ranges The body landmarks", 2, "text", 567, 80, 184),
        _side(3, "You can modify the scan ranges.", 2, "text", 567, 198, 495),
    ]
    bookmarks = [(2, "Previous", 1), (2, "Planning the scan ranges", 2)]
    previous, planning = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert _texts(previous)[-1] == "Step two of the previous task."
    assert _texts(planning) == [
        "Planning the scan ranges The body landmarks", "You can modify the scan ranges."
    ]


def test_margin_heading_read_after_the_body_below_it():
    # SOMATOM p315: Docling reads the margin heading after the text printed below it,
    # and there is no body block exactly level with the heading.
    blocks = [
        _side(0, "Acquiring", 1, "section_header", 700, 157, 320),
        _side(1, "Steps of a sequence scan.", 2, "text", 580, 199, 402),
        _side(2, "Examination direction and range.", 2, "list_item", 344, 199, 301),
        _side(3, "Checking", 2, "section_header", 518, 64, 184),
    ]
    bookmarks = [(2, "Acquiring", 1), (2, "Checking", 2)]
    acquiring, checking = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert _texts(acquiring)[-1] == "Steps of a sequence scan."
    # The tree export lists a section's blocks in reading order.
    in_order = sorted(checking.text_blocks, key=lambda block: block.reading_order)
    assert [block.text for block in in_order] == ["Checking", "Examination direction and range."]


def test_running_header_goes_with_a_table_printed_first_on_the_page():
    # Philips p428: the page starts with the previous section's weights table, so the
    # running header goes with that section, not with the heading below the table.
    blocks = [
        _block(0, "Weights", 1, "section_header", top=700),
        _block(1, "The weights of the parts are given here.", 1, top=650),
        _block(2, "38 Installation", 2, "page_header", top=780),
        _block(3, "Environment", 2, "section_header", top=400),
    ]
    tables = [_table("weights", 2, top=740, bottom=450)]
    weights, environment = match_content_to_sections(
        [(2, "Weights", 1), (2, "Environment", 2)], _paged_doc(blocks, 2, tables), 2
    )
    assert _table_ids(weights) == ["weights"]
    assert "38 Installation" in _texts(weights)
    assert _texts(environment) == ["Environment"]


def test_page_title_read_last_comes_first():
    # LOGIQ_e p111: the right-aligned title at the top is read after the Contents box
    # printed below it; the box belongs to the new section.
    blocks = [
        _block(0, "Setup", 1, "section_header", top=700),
        _block(1, "Setup text on the first page.", 1, top=650),
        _block(2, "Contents in this Section", 2, "section_header", top=554),
        _block(3, "'LOGIQ e configuration' on page 3-24", 2, "list_item", top=530),
        _block(4, "System Configuration", 2, "section_header", top=656),
    ]
    setup, config = match_content_to_sections(
        [(1, "Setup", 1), (1, "System Configuration", 2)], _paged_doc(blocks, 2), 2
    )
    assert _texts(setup) == ["Setup", "Setup text on the first page."]
    assert sorted(_texts(config)) == sorted(
        ["System Configuration", "Contents in this Section", "'LOGIQ e configuration' on page 3-24"]
    )


def test_a_heading_with_a_subscript_anchors_its_section():
    # Philips p482: 'SO2 Default Settings' is printed 'SO 2 Default Settings'.
    blocks = {
        482: [
            _block(0, "39 Default Settings Appendix SO2 Default Settings", 482, "page_header"),
            _block(1, "SO 2 Default Settings", 482, "section_header"),
            _block(2, "SvO 2 Default Settings", 482, "section_header"),
        ]
    }
    assert _find_heading_anchor("SO2 Default Settings", 482, blocks) == 1
    assert _find_heading_anchor("SvO2 Default Settings", 482, blocks, after=1) == 2


def _line(text: str, x0: float, top: float, width: float = 30) -> list:  # type: ignore[type-arg]
    """Text-layer words in top-left coordinates, one fixed-width word after another."""
    return [
        (x0 + i * width, top, x0 + (i + 1) * width - 2, top + 10, word)
        for i, word in enumerate(text.split())
    ]


def test_margin_heading_merged_with_text_printed_above_is_split():
    # SOMATOM p102: Docling merges the margin heading 'Touch Panel' with the last
    # paragraph of 'Laser lightmarkers', printed at the top of the page, and the block
    # keeps only the heading's bbox (BUG-029).
    blocks = [
        _side(0, "Laser lightmarkers", 1, "section_header", 700, 96, 184),
        _side(1, "Touch Panel The laser lightmarkers are laser beams.", 2, "text", 520, 134, 184),
        _side(2, "The laser lightmarkers indicate the scan center.", 2, "text", 650, 199, 538),
        _side(3, "The Touch Panel is part of the panel.", 2, "text", 520, 199, 538),
    ]
    words = {
        2: _line("Touch", 134, 272, 24)
        + _line("Panel", 160, 272, 24)
        + _line("The laser lightmarkers are laser beams.", 199, 92)
        + _line("The laser lightmarkers indicate the scan center.", 199, 142)
        + _line("The Touch Panel is part of the panel.", 199, 272)
    }
    bookmarks = [(2, "Laser lightmarkers", 1), (2, "Touch Panel", 2)]
    laser, touch = match_content_to_sections(
        bookmarks, _paged_doc(blocks, 2), 2, page_words=lambda page: words.get(page, [])
    )
    assert _texts(laser)[1:] == [
        "The laser lightmarkers are laser beams.",
        "The laser lightmarkers indicate the scan center.",
    ]
    in_order = sorted(touch.text_blocks, key=lambda block: block.reading_order)
    assert [block.text for block in in_order] == [
        "Touch Panel", "The Touch Panel is part of the panel."
    ]
    assert [block.block_id for block in laser.text_blocks][1] == "b1-tail"


def test_margin_heading_merged_with_its_note_below_keeps_the_note():
    # SOMATOM p295 with the text layer: the merged note is printed below the heading,
    # so it stays in the new section.
    blocks = [
        _side(0, "Previous", 1, "section_header", 700, 199, 538),
        _side(1, "Step two of the previous task.", 2, "text", 627, 199, 517),
        _side(2, "Planning the scan ranges The body landmarks", 2, "text", 567, 80, 184),
        _side(3, "You can modify the scan ranges.", 2, "text", 567, 198, 495),
    ]
    words = {
        2: _line("Step two of the previous task.", 199, 165)
        + _line("Planning the scan ranges", 80, 225, 26)
        + _line("The body landmarks", 80, 250, 26)
        + _line("You can modify the scan ranges.", 198, 225)
    }
    bookmarks = [(2, "Previous", 1), (2, "Planning the scan ranges", 2)]
    previous, planning = match_content_to_sections(
        bookmarks, _paged_doc(blocks, 2), 2, page_words=lambda page: words.get(page, [])
    )
    assert _texts(previous)[-1] == "Step two of the previous task."
    assert sorted(_texts(planning)) == sorted(
        ["Planning the scan ranges", "The body landmarks", "You can modify the scan ranges."]
    )


def test_margin_heading_wins_over_a_body_list_item_with_the_same_text():
    # SOMATOM p138: the body lists 'Flat cushions' as a "section_header" item above the
    # real margin heading, which Docling labels as plain text (BUG-019).
    blocks = [
        _side(0, "Cushions", 1, "section_header", 700, 96, 184),
        _side(1, "Flat cushions", 1, "section_header", 530, 199, 260),
        _side(2, "Wedge shaped cushions", 1, "section_header", 512, 199, 303),
        _side(3, "Flat cushions", 1, "text", 451, 130, 184),
        _side(4, "Flat cushions are used for positioning.", 1, "text", 451, 199, 538),
    ]
    bookmarks = [(2, "Cushions", 1), (3, "Flat cushions", 1)]
    cushions, flat = match_content_to_sections(bookmarks, _paged_doc(blocks, 1), 1)
    assert "Wedge shaped cushions" in _texts(cushions)
    assert _texts(flat)[0] == "Flat cushions"
    assert flat.text_blocks[0].block_id == "b3"


def test_split_keeps_reading_order_consecutive():
    # SOMATOM p114: sections whose heading is not found fall back to the previous
    # anchor + 1, which must be the next block, so reading orders stay 0, 1, 2, ...
    blocks = [
        _side(0, "Laser lightmarkers", 1, "section_header", 700, 96, 184),
        _side(1, "Touch Panel The laser lightmarkers are laser beams.", 1, "text", 520, 134, 184),
        _side(2, "The Touch Panel is part of the panel.", 1, "text", 520, 199, 538),
    ]
    words = {
        1: _line("Touch", 134, 272, 24)
        + _line("Panel", 160, 272, 24)
        + _line("The laser lightmarkers are laser beams.", 199, 150)
    }
    ranges = [("s0", "Laser lightmarkers", 2, 1, 1), ("s1", "Touch Panel", 2, 1, 1)]
    doc = _split_merged_margin_headings(_paged_doc(blocks, 1), ranges, words.get)
    assert sorted(block.reading_order for block in doc.text_blocks) == [0, 1, 2, 3]
    assert [b.text for b in sorted(doc.text_blocks, key=lambda b: b.reading_order)][1:3] == [
        "The laser lightmarkers are laser beams.", "Touch Panel"
    ]


def test_running_header_with_the_title_is_not_a_margin_heading():
    # Philips p273: the running header repeats 'BIS Window' at the top-left edge; the
    # text above the real heading stays with the previous section.
    blocks = [
        _side(0, "Stopping a Cyclic Impedance Check", 1, "section_header", 164, 71, 250),
        _side(1, "BIS Window", 2, "text", 776, 75, 130),
        _side(2, "If you stop a check, no values are shown.", 2, "text", 723, 137, 540),
        _side(3, "BIS Window", 2, "section_header", 686, 71, 130),
        _side(4, "To open the BIS window, select Show Sensor.", 2, "text", 652, 137, 540),
    ]
    bookmarks = [(2, "Stopping a Cyclic Impedance Check", 1), (2, "BIS Window", 2)]
    stopping, window = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert "If you stop a check, no values are shown." in _texts(stopping)
    assert _texts(window)[0] == "BIS Window"
    assert window.text_blocks[0].block_id == "b3"


def _merged_page(tail: str, words: list) -> tuple:  # type: ignore[type-arg]
    blocks = [
        _side(0, "Laser lightmarkers", 1, "section_header", 700, 96, 184),
        _side(1, f"Touch Panel {tail}", 1, "text", 520, 134, 184),
        _side(2, "The Touch Panel is part of the panel.", 1, "text", 520, 199, 538),
    ]
    heading = _line("Touch", 134, 272, 24) + _line("Panel", 160, 272, 24)
    ranges = [("s0", "Laser lightmarkers", 2, 1, 1), ("s1", "Touch Panel", 2, 1, 1)]
    doc = _split_merged_margin_headings(_paged_doc(blocks, 1), ranges, {1: heading + words}.get)
    return {block.block_id: block for block in doc.text_blocks}


def test_merged_block_is_kept_when_its_tail_is_not_in_the_text_layer():
    blocks = _merged_page("The laser beams cross here.", _line("Other words only.", 199, 150))
    assert "b1-tail" not in blocks
    assert blocks["b1"].text == "Touch Panel The laser beams cross here."


def test_a_short_tail_is_not_split():
    # Two tokens could match a running footer or a repeated label.
    blocks = _merged_page("See note.", _line("See note.", 199, 760))
    assert "b1-tail" not in blocks


def test_a_tail_printed_twice_takes_the_copy_nearest_the_heading():
    words = _line("Clean the panel daily.", 199, 60) + _line("Clean the panel daily.", 199, 250)
    blocks = _merged_page("Clean the panel daily.", words)
    tail = blocks["b1-tail"]
    assert tail.bbox is not None and round(792 - tail.bbox.y0) == 250


def test_a_tail_copy_inside_another_block_is_skipped():
    # SOMATOM p209: the sentence is printed twice; the copy near the heading is already
    # its own Docling block, so the tail is the other copy (no duplicated text).
    blocks = [
        _side(0, "Laser lightmarkers", 1, "section_header", 700, 96, 184),
        _side(1, "Touch Panel Clean the panel daily.", 1, "text", 520, 134, 184),
        _side(2, "Clean the panel daily.", 1, "text", 542, 199, 538),
    ]
    heading = _line("Touch", 134, 272, 24) + _line("Panel", 160, 272, 24)
    words = heading + _line("Clean the panel daily.", 199, 60) + _line(
        "Clean the panel daily.", 199, 250
    )
    ranges = [("s0", "Laser lightmarkers", 2, 1, 1), ("s1", "Touch Panel", 2, 1, 1)]
    doc = _split_merged_margin_headings(_paged_doc(blocks, 1), ranges, {1: words}.get)
    tail = next(block for block in doc.text_blocks if block.block_id == "b1-tail")
    assert tail.bbox is not None and round(792 - tail.bbox.y0) == 60


def test_the_longest_matching_copy_wins():
    # SOMATOM p36: two sentences start with the same six words; the full match wins.
    words = _line("Observe the safety information when using the foot switch.", 199, 60)
    words += _line("Observe the safety information when using the trolley.", 199, 400)
    blocks = _merged_page("Observe the safety information when using the trolley.", words)
    tail = blocks["b1-tail"]
    assert tail.bbox is not None and round(792 - tail.bbox.y0) == 400


def test_a_tail_level_with_the_heading_stays_with_it():
    # SOMATOM p152: the tail is printed on the heading's own line, 2 pt higher; it is the
    # new section's first sentence, so it must not go to the previous section.
    blocks = [
        _side(0, "Previous", 1, "section_header", 700, 96, 184),
        _side(1, "Body text of the previous section.", 2, "text", 700, 199, 538),
        _side(
            2, "Scan ranges The different distance enlargements decrease.", 2, "text", 520, 80, 184
        ),
    ]
    words = {
        2: _line("Body text of the previous section.", 199, 92)
        + _line("Scan", 80, 272, 50)
        + _line("ranges", 132, 272, 50)
        + _line("The different distance enlargements decrease.", 199, 270)
    }
    bookmarks = [(2, "Previous", 1), (2, "Scan ranges", 2)]
    previous, scan = match_content_to_sections(
        bookmarks, _paged_doc(blocks, 2), 2, page_words=lambda page: words.get(page, [])
    )
    assert _texts(previous) == ["Previous", "Body text of the previous section."]
    in_order = sorted(scan.text_blocks, key=lambda block: block.reading_order)
    assert [block.text for block in in_order] == [
        "Scan ranges", "The different distance enlargements decrease."
    ]


def test_figure_text_printed_above_a_heading_but_read_last_goes_to_the_previous_section():
    # Philips p41: Docling reads the 'Change Screen' dialog labels, printed above the
    # next heading, after that heading's text (BUG-023).
    blocks = [
        _side(0, "Changing a Screen", 1, "section_header", 700, 72, 300),
        _side(1, "Connecting Displays 1 Basic Operation", 2, "page_header", 754, 75, 548),
        _side(2, "In the Change Screen menu, the Screen is marked.", 2, "text", 709, 138, 364),
        _side(3, "Connecting Displays", 2, "section_header", 402, 72, 508),
        _side(4, "A second display shows the same Screen.", 2, "text", 371, 137, 523),
        _side(5, "Change Screen", 2, "text", 708, 394, 475),
        _side(6, "Vital Signs A", 2, "text", 563, 390, 472),
    ]
    bookmarks = [(2, "Changing a Screen", 1), (2, "Connecting Displays", 2)]
    changing, connecting = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    # 'Change Screen' has only the running header above it but is on the same printed
    # line as the previous section's text.
    assert _texts(changing)[-2:] == ["Change Screen", "Vital Signs A"]
    assert _texts(connecting) == ["Connecting Displays", "A second display shows the same Screen."]


def test_a_legend_above_the_heading_moves_and_the_one_below_stays():
    # Philips p26: the legend of the second figure is printed below its heading; it is
    # read last but belongs to that section.
    blocks = [
        _side(0, "Controls", 1, "section_header", 706, 74, 225),
        _side(1, "2", 1, "text", 379, 72, 76),
        _side(2, "Connectors", 1, "section_header", 313, 74, 266),
        _side(3, "Showing symbols version.", 1, "text", 297, 74, 364),
        _side(4, "1 On/Standby switch", 1, "text", 689, 379, 472),
        _side(5, "1 Pressure (option)", 1, "text", 264, 379, 473),
    ]
    bookmarks = [(2, "Controls", 1), (2, "Connectors", 1)]
    controls, connectors = match_content_to_sections(bookmarks, _paged_doc(blocks, 1), 1)
    assert _texts(controls)[-1] == "1 On/Standby switch"
    assert "1 Pressure (option)" in _texts(connectors)


def test_a_fallback_anchor_does_not_move_text():
    # A section whose heading is not found anchors on its page's first block; that block
    # is not a heading, so text above it keeps the reading-order owner.
    blocks = [
        _side(0, "Previous", 1, "section_header", 700, 72, 300),
        _side(1, "Body of the next section.", 2, "text", 400, 72, 500),
        _side(2, "Caption printed higher.", 2, "text", 700, 72, 500),
    ]
    bookmarks = [(2, "Previous", 1), (2, "Missing heading", 2)]
    _previous, missing = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert "Caption printed higher." in _texts(missing)


def test_labels_above_the_heading_of_a_chapter_opening_page_stay():
    # 2002 p125: the chapter tab code 'IN' is printed above the chapter heading and read
    # after it; nothing of the previous chapter is on the page, so it stays.
    blocks = [
        _side(0, "Exhaust", 1, "section_header", 700, 72, 300),
        _side(1, "Exhaust body text on its own page.", 1, "text", 650, 72, 500),
        _side(2, "INTAKE (INDUCTION)", 2, "section_header", 697, 251, 502),
        _side(3, "Intake body text.", 2, "text", 600, 72, 500),
        _side(4, "IN", 2, "text", 716, 530, 584),
    ]
    bookmarks = [(1, "Exhaust", 1), (1, "INTAKE (INDUCTION)", 2)]
    _exhaust, intake = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert "IN" in _texts(intake)


def test_a_label_with_nothing_above_it_keeps_its_owner():
    # DOC p198: the 'Appendix B' tab at the top of the page is read after the B.1
    # heading lower on the page; nothing is printed above it, so it stays.
    blocks = [
        _side(0, "A.6 Cable", 1, "section_header", 700, 55, 300),
        _side(1, "Accessories", 2, "section_header", 663, 54, 230),
        _side(2, "Contents of this appendix.", 2, "text", 604, 55, 500),
        _side(3, "B.1 Accessories List", 2, "section_header", 526, 55, 211),
        _side(4, "Only use approved accessories.", 2, "text", 483, 174, 540),
        _side(5, "Appendix", 2, "section_header", 719, 328, 476),
    ]
    bookmarks = [(1, "A.6 Cable", 1), (1, "Accessories", 2), (2, "B.1 Accessories List", 2)]
    cable, _accessories, _b1 = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert "Appendix" not in _texts(cable)


def _tall(  # type: ignore[no-untyped-def]
    order: int, text: str, page: int, top: float, bottom: float, x0: float, x1: float
):
    return DoclingTextBlock(
        block_id=f"b{order}", text=text, label="text", page_no=page, reading_order=order,
        depth=0, provenance=ExtractionProvenance(source="docling", page_no=page),
        bbox=_box(page, top, bottom, x0, x1),
    )


def test_the_top_of_a_right_hand_text_column_stays_with_the_new_section():
    # Two text columns: the left column ends with the next heading, and the right column
    # continues that section from the top of the page (only a running header above it).
    blocks = [
        _side(0, "Previous", 1, "section_header", 700, 50, 290),
        _side(1, "Running header", 2, "page_header", 770, 50, 560),
        _tall(2, "Previous body text at the top of the left column.", 2, 700, 640, 50, 290),
        _side(3, "Next", 2, "section_header", 300, 50, 290),
        _side(4, "Next body text below its heading.", 2, "text", 280, 50, 290),
        _tall(5, "Next body continues in the right column here.", 2, 700, 620, 310, 560),
    ]
    bookmarks = [(2, "Previous", 1), (2, "Next", 2)]
    _previous, nxt = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert "Next body continues in the right column here." in _texts(nxt)


def test_a_table_under_a_moved_block_follows_it():
    # Philips p358: a screenshot's text and the table printed under it belong to the
    # section above the next heading.
    blocks = [
        _side(0, "Using the Table", 1, "section_header", 700, 71, 305),
        _side(1, "Use the table to see the doses.", 1, "text", 466, 136, 258),
        _side(2, "Documenting", 1, "section_header", 202, 71, 371),
        _side(3, "Select the pop-up key.", 1, "text", 171, 136, 552),
        _side(4, "Titration Table", 1, "text", 470, 345, 425),
    ]
    tables = [_table("t1", 1, 440, 380)]
    tables[0] = DoclingTable(
        table_id="t1",
        page_no=1,
        provenance=ExtractionProvenance(source="docling", page_no=1),
        bbox=_box(1, 440, 380, 345, 520),
    )
    bookmarks = [(2, "Using the Table", 1), (2, "Documenting", 1)]
    using, documenting = match_content_to_sections(
        bookmarks, _paged_doc(blocks, 1, tables), 1
    )
    assert "Titration Table" in _texts(using)
    assert _table_ids(using) == ["t1"]
    assert _table_ids(documenting) == []


def test_the_end_of_a_line_split_by_an_icon_follows_its_line():
    # DOC p144: step 4 is split by an inline icon; its end is read after the next heading
    # and has only the running header above it.
    blocks = [
        _side(0, "10.6.2 Pressure-Out", 1, "section_header", 700, 105, 284),
        _side(1, "Running header", 2, "page_header", 764, 56, 553),
        _side(2, "4 Touch the pressure signal icon", 2, "text", 738, 134, 281),
        _side(3, "10.6.3 Waveform Confirmation", 2, "section_header", 712, 105, 284),
        _side(4, "The Zero and Waveform screen shows the pressure.", 2, "text", 690, 104, 504),
        _side(5, "to begin pressure signal output.", 2, "text", 738, 316, 545),
    ]
    bookmarks = [(3, "10.6.2 Pressure-Out", 1), (3, "10.6.3 Waveform Confirmation", 2)]
    pressure, _waveform = match_content_to_sections(bookmarks, _paged_doc(blocks, 2), 2)
    assert _texts(pressure)[-1] == "to begin pressure signal output."
