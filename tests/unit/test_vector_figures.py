"""Vector figures rendered as images (BUG-010)."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf as fitz

from src.models.extraction import (
    BoundingBox,
    DoclingDocument,
    DoclingTable,
    ExtractionProvenance,
)
from src.pipeline.pipeline import EmbeddedImage, _extract_vector_figures
from src.qa_workflow.storage import serialize_images

_LOG = logging.getLogger("test")


def _doc() -> DoclingDocument:
    return DoclingDocument("d", "d.pdf", 1)


def _drawing(page: fitz.Page, x: float, y: float) -> None:
    # A line drawing of 60 strokes (2002 p175 spark plug, Philips p363).
    for i in range(60):
        page.draw_line((x + i * 3, y), (x + 30 + i * 3, y + 130), width=0.6)


def _save(pdf: fitz.Document, tmp_path: Path) -> Path:
    path = tmp_path / "vector.pdf"
    pdf.save(path)
    return path


def _vectors(images: list[EmbeddedImage]) -> list[EmbeddedImage]:
    return [image for image in images if image.origin == "vector"]


def test_a_line_drawing_is_rendered_and_a_caution_bar_is_not(tmp_path: Path) -> None:
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    _drawing(page, 150, 200)
    for i in range(50):  # a caution bar: a thin wide box with many short strokes (SOMATOM)
        page.draw_line((200 + i * 6, 600), (203 + i * 6, 612), width=0.5)

    images = _vectors(_extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [], _LOG))

    assert len(images) == 1
    bbox = images[0].bbox
    assert bbox is not None and bbox.coordinate_origin == "bottomleft"
    assert 140 <= bbox.x0 <= 160 and 580 <= bbox.y0 <= 600  # top 200 pt from the page top
    assert images[0].image_bytes.startswith(b"\x89PNG")


def test_a_drawing_on_a_rotated_page_is_cropped_where_it_is_shown(tmp_path: Path) -> None:
    # AUTOMATIC pages have /Rotate 180: drawing coordinates are in unrotated space.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    _drawing(page, 150, 100)  # near the top before rotation
    page.set_rotation(180)

    (image,) = _vectors(_extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [], _LOG))

    assert image.bbox is not None and image.bbox.y0 < 300  # shown near the bottom


def test_a_figure_around_a_raster_icon_replaces_the_icon(tmp_path: Path) -> None:
    # LOGIQ_S8 p893: a wiring drawing with a small raster icon inside it.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    _drawing(page, 150, 200)
    icon = EmbeddedImage(b"png", 1, 193, 192, bbox=BoundingBox(250, 560, 280, 530, 1, "bottomleft"))

    images = _extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [icon], _LOG)

    assert [image.origin for image in images] == ["vector"]


def test_callout_labels_at_the_edge_are_inside_the_crop(tmp_path: Path) -> None:
    # Philips p245: callout letters sit just left of the drawing.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    _drawing(page, 150, 200)
    page.insert_text((138, 260), "a", fontsize=9)

    (image,) = _vectors(_extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [], _LOG))

    assert image.bbox is not None and image.bbox.x0 < 140


def test_only_vector_figures_carry_an_origin_in_images_v1(tmp_path: Path) -> None:
    pdf = fitz.open()
    _drawing(pdf.new_page(width=612, height=792), 150, 200)
    images = _extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [], _LOG)

    assert serialize_images(images)["images"][0]["origin"] == "vector"


def test_a_word_label_is_inside_the_crop_and_a_body_sentence_is_not(tmp_path: Path) -> None:
    # DOC p88: 'backspace' sits right of the keypad; the sentence above is body text.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    _drawing(page, 150, 200)
    page.insert_text((365, 260), "backspace", fontsize=9)
    sentence = "Touch the keys on the keypad to enter numeric data now."
    page.insert_text((100, 192), sentence, fontsize=9)

    (image,) = _vectors(_extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [], _LOG))

    assert image.bbox is not None
    assert image.bbox.x1 > 400  # the label is kept
    assert image.bbox.y0 < 792 - 195  # the sentence top (y 183) is left out


def test_a_drawing_over_most_of_the_page_is_rendered_as_the_whole_page(tmp_path: Path) -> None:
    # AUTOMATIC plates: the title and drawing number sit outside the paths.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    for i in range(60):
        page.draw_line((25 + i * 9.6, 70), (30 + i * 9.6, 730), width=0.6)

    (image,) = _vectors(_extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [], _LOG))

    assert image.bbox is not None
    assert (image.bbox.x0, image.bbox.x1, image.bbox.y1, image.bbox.y0) == (0, 612, 0, 792)


def test_a_figure_inside_a_larger_figure_is_not_rendered_twice(tmp_path: Path) -> None:
    # LOGIQ_S8 p794: a photo absorbed by the large figure covers a smaller drawing.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    _drawing(page, 150, 200)  # x 150..357, y 200..330; the photo grows it to y 392
    for i in range(60):  # a second, separate drawing below it, inside the photo
        page.draw_line((150 + i * 3, 345), (180 + i * 3, 388), width=0.6)
    bbox = BoundingBox(140, 600, 370, 400, 1, "bottomleft")
    photo = EmbeddedImage(b"png", 1, 400, 400, bbox=bbox)

    images = _extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [photo], _LOG)

    assert [image.origin for image in images] == ["vector"]


def test_a_heading_next_to_a_figure_is_not_a_label(tmp_path: Path) -> None:
    # Philips p216: the page heading sits 2 pt above the drawing.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    _drawing(page, 300, 200)
    page.insert_text((60, 196), "Setting Up the Measurement", fontsize=14)
    for i in range(4):
        page.insert_text((60, 300 + i * 12), f"Body line {i} of the steps.", fontsize=9)

    (image,) = _vectors(_extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [], _LOG))

    assert image.bbox is not None and image.bbox.x0 > 280


def _doc_with_table(x0: float, top: float, x1: float, bottom: float) -> DoclingDocument:
    bbox = BoundingBox(x0, 792 - top, x1, 792 - bottom, 1, "bottomleft")
    table = DoclingTable("#/tables/0", 1, ExtractionProvenance("docling", 1, bbox), bbox)
    return DoclingDocument("d", "d.pdf", 1, tables=[table])


def test_a_drawing_in_a_table_cell_is_kept_and_the_grid_is_not(tmp_path: Path) -> None:
    # LOGIQ_S8 p502: the cover drawing sits in the 'Corresponding Graphic' cell.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    for x in (40, 300, 570):  # table grid lines, a little longer than the table box
        page.draw_line((x, 95), (x, 405), width=0.5)
    _drawing(page, 320, 200)

    doc = _doc_with_table(40, 100, 570, 400)
    (image,) = _vectors(_extract_vector_figures(_save(pdf, tmp_path), 1, doc, [], _LOG))

    assert image.bbox is not None and image.bbox.x0 > 300  # the drawing, not the grid


def test_marks_drawn_on_a_photo_are_rendered_with_the_photo(tmp_path: Path) -> None:
    # LOGIQ_S8 p608: a circle and arrow drawn on a step photo.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    _drawing(page, 200, 250)  # x 200..407, y 250..380
    photo_bbox = BoundingBox(150, 792 - 200, 500, 792 - 420, 1, "bottomleft")
    photo = EmbeddedImage(b"png", 1, 700, 440, bbox=photo_bbox)

    images = _extract_vector_figures(_save(pdf, tmp_path), 1, _doc(), [photo], _LOG)

    assert [image.origin for image in images] == ["vector"]  # replaces the photo
    assert images[0].bbox is not None and images[0].bbox.x0 <= 150 and images[0].bbox.x1 >= 500
