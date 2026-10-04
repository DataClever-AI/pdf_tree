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
