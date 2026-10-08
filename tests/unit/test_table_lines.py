"""Printed table lines that are in no Docling cell are put back into the table (BUG-030)."""

from __future__ import annotations

import logging
from typing import Any

from src.tree_builder.docling_extract import _render_table_markdown
from src.tree_builder.fitz_toc import Word
from src.tree_builder.table_lines import recover_table_lines

_HEIGHT = 792.0
_COLUMNS = ((60.0, 180.0), (190.0, 540.0))  # left and right edge of each column


def _cell(row: int, column: int, text: str, top: float, bottom: float) -> dict[str, Any]:
    left, right = _COLUMNS[column]
    return {
        "text": text,
        "bbox": {"l": left, "t": top, "r": right, "b": bottom, "coord_origin": "TOPLEFT"},
        "row_span": 1,
        "col_span": 1,
        "start_row_offset_idx": row,
        "end_row_offset_idx": row + 1,
        "start_col_offset_idx": column,
        "end_col_offset_idx": column + 1,
    }


def _rows(*rows: tuple[str, str, float]) -> list[dict[str, Any]]:
    """Two-column rows (name, value, top), each 10 pt high."""
    cells = []
    for index, (name, value, top) in enumerate(rows):
        cells.append(_cell(index, 0, name, top, top + 10))
        cells.append(_cell(index, 1, value, top, top + 10))
    return cells


def _words(text: str, left: float, top: float) -> list[Word]:
    """One printed line: words 5 pt per letter wide, 1 space apart, 8 pt high."""
    words: list[Word] = []
    for part in text.split():
        right = left + 5 * len(part)
        words.append((left, top, right, top + 8, part))
        left = right + 2
    return words


def _printed(cells: list[dict[str, Any]]) -> list[Word]:
    """The words of every cell, printed at the top of the cell."""
    words: list[Word] = []
    for cell in cells:
        box = cell["bbox"]
        words += _words(cell["text"], box["l"], box["t"] + 1)
    return words


def _document(
    cells: list[dict[str, Any]],
    top: float,
    bottom: float,
    texts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = max(cell["end_row_offset_idx"] for cell in cells)
    return {
        "pages": {"1": {"size": {"width": 612.0, "height": _HEIGHT}}},
        "texts": texts or [],
        "pictures": [],
        "tables": [
            {
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 55.0,
                            "t": _HEIGHT - top,
                            "r": 545.0,
                            "b": _HEIGHT - bottom,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
                "data": {"num_rows": rows, "num_cols": 2, "table_cells": cells},
            }
        ],
    }


def _recover(document: dict[str, Any], words: list[Word]) -> list[str]:
    recover_table_lines(document, lambda page: words, logging.getLogger("test"))
    return _render_table_markdown(document["tables"][0]["data"]).split("\n")


def test_lost_footnote_row_becomes_the_last_row() -> None:
    # DOC p178: the full-width row '* These latching faults ...' is under the last row.
    cells = _rows(("Message", "Possible causes", 100), ("Fault: CO", "Thermistor lost", 120))
    words = _printed(cells) + _words("* These latching faults. Touch silence icon", 60, 141)
    document = _document(cells, 95, 155)

    assert _recover(document, words) == [
        "Message | Possible causes",
        "Fault: CO | Thermistor lost",
        "* These latching faults. Touch silence icon | ",
    ]
    assert document["tables"][0]["data"]["num_rows"] == 3


def test_lost_middle_row_goes_back_in_its_place() -> None:
    # Philips p443: the row 'Gain 2.0, ...' between two kept rows was dropped.
    cells = _rows(
        ("Gain 0.5", "Range 5.4 to 6.2 seconds", 100),
        ("Gain 1.0", "Range 5.7 to 6.5 seconds", 115),
        ("Tall T-Wave", "Exceeds 1.2 mV", 145),
    )
    words = _printed(cells) + _words("Gain 2.0", 60, 131) + _words("Range 5.3 to 6.1", 190, 131)
    document = _document(cells, 95, 160)

    lines = _recover(document, words)

    assert lines[2] == "Gain 2.0 | Range 5.3 to 6.1"
    assert lines[3] == "Tall T-Wave | Exceeds 1.2 mV"
    starts = sorted(c["start_row_offset_idx"] for c in document["tables"][0]["data"]["table_cells"])
    assert starts == [0, 0, 1, 1, 2, 2, 3, 3]


def test_lines_of_one_lost_row_join_in_one_cell() -> None:
    # AUTOMATIC p27: a lost row whose description is printed on three lines.
    cells = _rows(
        ("Pilot valve", "Reduces the line pressure", 100), ("Shift valve", "Changes", 150)
    )
    words = (
        _printed(cells)
        + _words("Timing valve A", 60, 116)
        + _words("Switches the passages when", 190, 116)
        + _words("the clutch pressure rises", 190, 125)
        + _words("during upshifting", 190, 134)
    )
    document = _document(cells, 95, 165)

    assert _recover(document, words)[1] == (
        "Timing valve A | Switches the passages when the clutch pressure rises during upshifting"
    )


def test_lost_line_inside_a_kept_row_is_added_to_its_cell() -> None:
    cells = [
        _cell(0, 0, "Pilot valve", 100, 125),
        _cell(0, 1, "Reduces the line pressure", 100, 125),
    ]
    words = _printed(cells) + _words("for the lock-up clutch", 190, 112)
    document = _document(cells, 95, 130)

    assert _recover(document, words) == [
        "Pilot valve | Reduces the line pressure for the lock-up clutch"
    ]


def test_text_of_another_docling_item_is_not_taken() -> None:
    # A caption printed inside the table box already belongs to a Docling text item.
    cells = _rows(("Message", "Possible causes", 100), ("Fault: CO", "Thermistor lost", 120))
    words = _printed(cells) + _words("Table 13-7 Cardiac output faults", 60, 141)
    caption = {
        "text": "Table 13-7 Cardiac output faults",
        "prov": [{"page_no": 1, "bbox": {
            "l": 58.0, "t": _HEIGHT - 140, "r": 400.0, "b": _HEIGHT - 150,
            "coord_origin": "BOTTOMLEFT",
        }}],
    }
    document = _document(cells, 95, 155, texts=[caption])

    assert len(_recover(document, words)) == 2


def test_text_already_on_the_page_is_not_added_again() -> None:
    cells = _rows(("Message", "Possible causes", 100), ("Fault: CO", "Thermistor lost", 120))
    words = _printed(cells) + _words("Restart monitoring now", 60, 141)
    elsewhere = {"text": "Restart monitoring now.", "prov": [{"page_no": 1, "bbox": {
        "l": 60.0, "t": 100.0, "r": 300.0, "b": 90.0, "coord_origin": "BOTTOMLEFT",
    }}]}
    document = _document(cells, 95, 155, texts=[elsewhere])

    assert len(_recover(document, words)) == 2


def test_split_subscripts_and_short_pieces_are_not_lost_lines() -> None:
    # Philips: the cell has 'CO 2' while the page prints 'CO2'; '(2)' alone is too short.
    cells = _rows(("CO 2 , Resp", "Apnea alarm", 100), ("SpO 2", "Desat alarm", 120))
    words = _printed([cell for cell in cells if cell["start_col_offset_idx"] == 1])
    words += _words("CO2, Resp", 60, 101) + _words("SpO2", 60, 121) + _words("(2)", 60, 141)
    document = _document(cells, 95, 155)

    assert _recover(document, words) == ["CO 2 , Resp | Apnea alarm", "SpO 2 | Desat alarm"]


def test_dot_leaders_are_dropped_from_a_recovered_line() -> None:
    cells = _rows(("General", "1-1", 100), ("Engine", "2-1", 120))
    words = _printed(cells) + _words("Combination Meter . . . . . . 3-7", 60, 141)
    document = _document(cells, 95, 155)

    assert _recover(document, words)[-1] == "Combination Meter 3-7 | "


def test_line_crossing_a_column_border_stays_in_its_first_column() -> None:
    cells = _rows(("Message", "Possible causes", 100), ("Fault: CO", "Thermistor lost", 120))
    words = _printed(cells) + _words("Note: X Support and N Not Applicable", 150, 141)
    document = _document(cells, 95, 155)

    assert _recover(document, words)[-1] == "Note: X Support and N Not Applicable | "


def test_nothing_changes_when_the_words_do_not_match_the_table() -> None:
    # Different page geometry (rotation or crop): the cell text is not printed in the box.
    cells = _rows(("Message", "Possible causes", 100), ("Fault: CO", "Thermistor lost", 120))
    words = _words("Completely different words printed here", 60, 101)
    document = _document(cells, 95, 155)

    assert _recover(document, words) == [
        "Message | Possible causes",
        "Fault: CO | Thermistor lost",
    ]


def test_row_name_also_quoted_in_another_cell_is_recovered() -> None:
    # AUTOMATIC p27: 'Timing valve A' is lost but also quoted in the next row's description.
    cells = _rows(
        ("Pilot valve", "Reduces the line pressure", 100),
        ("Timing valve B", "Returns the Timing valve A to its place", 130),
    )
    words = _printed(cells) + _words("Timing valve A", 60, 116) + _words("Drains it", 190, 116)
    document = _document(cells, 95, 145)

    assert _recover(document, words)[1] == "Timing valve A | Drains it"


def test_line_of_a_shifted_row_is_not_added_twice() -> None:
    # AUTOMATIC p27: rows are shifted, so a cell holds the line without its first word.
    cells = _rows(
        ("Reverse valve", "Reduces when changing range", 100),
        ("Reducing valve", "the low-reverse brake pressure to reduce shock", 120),
    )
    words = _printed([cells[0], cells[1], cells[2]])
    words += _words("Reduces the low-reverse brake pressure to reduce shock", 190, 121)
    document = _document(cells, 95, 135)

    assert _recover(document, words)[1] == (
        "Reducing valve | the low-reverse brake pressure to reduce shock"
    )


def test_narrow_gap_at_a_column_border_splits_the_line() -> None:
    # Philips p83: a few pt between two columns, 1.7 pt between words; the kept cells must
    # not come back joined as one 'lost' phrase.
    cells = [
        _cell(0, 0, "Alarm", 100, 110),
        _cell(0, 1, "The rate has dropped", 100, 110),
    ]
    cells[1]["bbox"]["r"] = 282.0
    cells.append({**_cell(0, 1, "numeric flashes", 100, 110), "start_col_offset_idx": 2,
                  "end_col_offset_idx": 3})
    cells[2]["bbox"].update({"l": 284.0, "r": 540.0})
    words = _words("Alarm", 60, 101)
    left = 190.0
    for part in ("The", "rate", "has", "dropped", "numeric", "flashes"):
        if part == "numeric":
            left += 5.0 - 1.7  # 5 pt: under the 6.4 pt wide gap, over twice the word space
        words.append((left, 101.0, left + 5 * len(part), 109.0, part))
        left += 5 * len(part) + 1.7
    cells.reverse()  # Docling order: the joined text is not found across two cells
    document = _document(cells, 95, 115)
    document["tables"][0]["data"]["num_cols"] = 3

    assert _recover(document, words) == ["Alarm | The rate has dropped | numeric flashes"]


def test_first_lines_of_two_header_cells_are_not_joined() -> None:
    # Philips p79: two-line headers 'Pause Al. / 5 Min.' and 'Pause Al. / 10 Min.' side by
    # side; their first lines are printed on one line only a little apart.
    cells = [
        _cell(0, 0, "Pause Al. 5 Min.", 100, 120),
        _cell(0, 1, "Pause Al. 10 Min.", 100, 120),
    ]
    cells[0]["bbox"]["r"] = 186.0
    words = [
        (150.0, 101.0, 175.0, 109.0, "Pause"), (177.0, 101.0, 186.0, 109.0, "Al."),
        (190.0, 101.0, 215.0, 109.0, "Pause"), (217.0, 101.0, 226.0, 109.0, "Al."),
    ]
    words += _words("5 Min.", 150, 111) + _words("10 Min.", 190, 111)
    document = _document(cells, 95, 125)

    assert _recover(document, words) == ["Pause Al. 5 Min. | Pause Al. 10 Min."]


def test_overprinted_words_are_read_once() -> None:
    # LOGIQ_S8 p59: each 'WARNING' label is drawn twice at the same place.
    cells = _rows(("WARNING", "Turn the system off", 100), ("WARNING", "Unplug the cord", 120))
    words = _printed(cells) + _printed(cells)
    document = _document(cells, 95, 135)

    assert _recover(document, words) == [
        "WARNING | Turn the system off",
        "WARNING | Unplug the cord",
    ]


def test_line_whose_words_are_in_a_mixed_up_cell_is_not_added() -> None:
    # LOGIQ_S8 p304: the cell holds 'Options and its expiration' and 'Enabled date' apart.
    cells = _rows(("Options Installed", "Options and its expiration Enabled date", 100))
    cells[1]["bbox"]["b"] = 125.0
    words = _words("Options Installed", 60, 101) + _words("Enabled Options and its", 190, 101)
    words += _words("expiration date", 190, 111)
    document = _document(cells, 95, 130)

    assert _recover(document, words) == [
        "Options Installed | Options and its expiration Enabled date"
    ]


def test_line_in_nested_row_bands_goes_to_the_nearest_row() -> None:
    # LOGIQ_S8 p28: row 0's band (100-130) holds row 1's band (118-128).
    cells = [
        _cell(0, 0, "Tall name", 100, 130),
        _cell(0, 1, "First value", 100, 110),
        _cell(1, 0, "Short", 118, 128),
        _cell(1, 1, "Second value", 118, 128),
    ]
    words = _printed(cells) + _words("plus a lost note", 260, 119)
    document = _document(cells, 95, 135)

    assert _recover(document, words)[1] == "Short | Second value plus a lost note"


def test_new_rows_before_the_first_row_and_between_rows() -> None:
    cells = _rows(("Alpha row", "Alpha value", 110), ("Gamma row", "Gamma value", 140))
    words = _printed(cells) + _words("Heading line", 60, 98) + _words("Beta row", 60, 126)
    document = _document(cells, 95, 155)

    assert _recover(document, words) == [
        "Heading line | ",
        "Alpha row | Alpha value",
        "Beta row | ",
        "Gamma row | Gamma value",
    ]


def test_new_row_inside_a_row_spanning_cell_widens_its_span() -> None:
    cells = _rows(("Alpha row", "Alpha value", 100), ("Gamma row", "Gamma value", 130))
    spanning = _cell(0, 1, "Shared value", 100, 140)
    spanning["end_row_offset_idx"], spanning["row_span"] = 2, 2
    cells = [cells[0], cells[2], spanning]
    words = _printed(cells) + _words("Beta row", 60, 116)
    document = _document(cells, 95, 145)

    _recover(document, words)

    cell = next(c for c in document["tables"][0]["data"]["table_cells"] if c is spanning)
    assert (cell["start_row_offset_idx"], cell["end_row_offset_idx"], cell["row_span"]) == (0, 3, 3)


def test_lost_first_line_of_a_cell_is_put_before_its_text() -> None:
    cells = [_cell(0, 0, "Pilot valve", 100, 125), _cell(0, 1, "the line pressure", 110, 125)]
    words = _printed(cells) + _words("Reduces quickly", 190, 101)
    document = _document(cells, 95, 130)

    assert _recover(document, words) == ["Pilot valve | Reduces quickly the line pressure"]


def test_text_split_over_two_page_items_does_not_hide_a_lost_line() -> None:
    # 'Gain 2.0' must not be found across 'Range ... Gain' and '2.0 ...' of two other items.
    cells = _rows(("Message", "Possible causes", 100), ("Fault: CO", "Thermistor lost", 120))
    words = _printed(cells) + _words("Gain 2.0", 60, 141)
    items = [
        {"text": text, "prov": [{"page_no": 1, "bbox": {
            "l": 60.0, "t": 50.0 + i, "r": 300.0, "b": 40.0 + i, "coord_origin": "BOTTOMLEFT",
        }}]}
        for i, text in enumerate(("Range low Gain", "2.0 is the default"))
    ]
    document = _document(cells, 95, 155, texts=items)

    assert _recover(document, words)[-1] == "Gain 2.0 | "


def test_new_row_follows_the_row_printed_above_when_indices_are_swapped() -> None:
    # AUTOMATIC p27: Docling numbered two rows against the page order.
    cells = _rows(
        ("Alpha row", "Alpha value", 100), ("Delta row", "Delta value", 160),
        ("Gamma row", "Gamma value", 130),
    )
    words = _printed(cells) + _words("Beta row lost", 60, 116)
    document = _document(cells, 95, 175)

    lines = _recover(document, words)

    assert lines[1] == "Beta row lost | "
    assert sorted(lines) == sorted(
        ["Alpha row | Alpha value", "Beta row lost | ", "Delta row | Delta value",
         "Gamma row | Gamma value"]
    )


def test_line_starting_just_before_a_cell_edge_goes_to_that_column() -> None:
    # DOC p218: 'Phone ...' starts 0.6 pt left of the address cell, inside the label band.
    cells = [_cell(0, 0, "India:", 100, 110), _cell(0, 1, "Edwards Lifesciences India", 100, 110)]
    cells[0]["bbox"]["r"] = 200.0
    words = _printed(cells) + _words("Phone +91.022.66935701 04", 189.4, 121)
    document = _document(cells, 95, 135)

    assert _recover(document, words)[-1] == " | Phone +91.022.66935701 04"


def test_header_word_of_a_lost_column_is_not_joined_to_a_neighbour_cell() -> None:
    # LOGIQ_S8 p817: Docling lost the 'Description' column; its header word is printed
    # between the 'Part Number' and 'Qty' columns.
    cells = [
        _cell(0, 0, "Part Number", 100, 110),
        {**_cell(0, 1, "Qty", 100, 110), "bbox": {
            "l": 500.0, "t": 100.0, "r": 540.0, "b": 110.0, "coord_origin": "TOPLEFT"}},
        _cell(1, 0, "5763099", 115, 125),
        {**_cell(1, 1, "1", 115, 125), "bbox": {
            "l": 500.0, "t": 115.0, "r": 540.0, "b": 125.0, "coord_origin": "TOPLEFT"}},
    ]
    words = _printed(cells) + _words("Description", 300, 101)
    document = _document(cells, 95, 130)

    assert _recover(document, words) == ["Part Number | Qty", "5763099 | 1"]
