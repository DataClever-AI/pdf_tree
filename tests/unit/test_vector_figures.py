"""Vector figures rendered as images (BUG-010)."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf as fitz

from src.models.extraction import BoundingBox, DoclingDocument
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
