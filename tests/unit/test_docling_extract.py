"""Tests for the reading order of Docling texts (BUG-005)."""

from src.tree_builder.docling_extract import _in_reading_order


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
