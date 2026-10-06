"""Tests for the reading order of Docling texts (BUG-005)."""

import logging

from src.tree_builder.docling_extract import (
    _in_reading_order,
    _refill_tables,
    _render_table_markdown,
)


def _text(text: str) -> dict:
    return {"text": text, "children": []}


def _texts(doc: dict) -> list[str]:
    return [item["text"] for item in _in_reading_order(doc)["texts"]]


def test_heading_inside_a_list_group_keeps_its_place_in_reading_order() -> None:
    # Docling appends the heading inside the list group after the rest of the window.
    doc = {
        "body": {
            "children": [{"$ref": "#/texts/0"}, {"$ref": "#/groups/0"}, {"$ref": "#/texts/1"}]
        },
        "groups": [{"children": [{"$ref": "#/texts/3"}, {"$ref": "#/texts/2"}]}],
        "texts": [
            _text("p130 body"), _text("p132 body"), _text("p131 item"), _text("p131 heading")
        ],
    }

    assert _texts(doc) == ["p130 body", "p131 heading", "p131 item", "p132 body"]


def test_text_outside_the_body_stays_after_the_text_before_it() -> None:
    doc = {
        "body": {"children": [{"$ref": "#/texts/2"}, {"$ref": "#/texts/0"}]},
        "texts": [_text("first"), _text("running header"), _text("lead")],
    }

    assert _texts(doc) == ["lead", "first", "running header"]


def test_input_is_not_modified() -> None:
    texts = [_text("b"), _text("a")]
    doc = {"body": {"children": [{"$ref": "#/texts/1"}, {"$ref": "#/texts/0"}]}, "texts": texts}

    _in_reading_order(doc)

    assert [item["text"] for item in doc["texts"]] == ["b", "a"]


def _table(page: int, left: float, cells: str) -> dict:
    box = {"l": left, "t": 500.0, "r": left + 200.0, "b": 400.0, "coord_origin": "BOTTOMLEFT"}
    return {"prov": [{"page_no": page, "bbox": box}], "data": {"cells": cells}}


def test_tables_take_the_cells_of_the_re_read_table_at_the_same_place() -> None:
    # BUG-008: Philips p363 '1' + '2' read as '12' with the PyPdfium backend.
    merged = {"tables": [_table(363, 50, "12"), _table(363, 300, "kept"), _table(365, 50, "x")]}
    calls: list[list[int]] = []

    def convert_pages(pages: list[int]) -> dict:
        calls.append(pages)  # the re-read subset numbers its pages 1, 2, ...
        return {"tables": [_table(1, 55, "1 | 2"), _table(2, 50, "y")]}

    replaced = _refill_tables(merged, convert_pages, logging.getLogger("test"))

    assert replaced == 2
    assert [table["data"]["cells"] for table in merged["tables"]] == ["1 | 2", "kept", "y"]
    assert calls == [[363, 365]]


def test_cell_text_is_kept_on_one_line_in_the_table_text() -> None:
    data = {
        "num_rows": 1,
        "num_cols": 2,
        "table_cells": [
            {"text": "Max \nWave", "start_row_offset_idx": 0, "start_col_offset_idx": 0},
            {"text": "1", "start_row_offset_idx": 0, "start_col_offset_idx": 1},
        ],
    }

    assert _render_table_markdown(data) == "Max Wave | 1"
