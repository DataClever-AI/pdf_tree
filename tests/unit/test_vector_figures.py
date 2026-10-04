"""Vector figures rendered as images (BUG-010)."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf as fitz

from src.models.extraction import DoclingDocument
from src.pipeline.pipeline import _extract_vector_figures
from src.qa_workflow.storage import serialize_images


def _pdf(tmp_path: Path) -> Path:
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    # A line drawing of 60 strokes in one area (2002 p175 spark plug, Philips p363).
    for i in range(60):
        page.draw_line((150 + i * 3, 200), (180 + i * 3, 330), width=0.6)
    # A caution bar: a thin wide box with many short strokes (SOMATOM).
    for i in range(50):
        page.draw_line((200 + i * 6, 600), (203 + i * 6, 612), width=0.5)
    path = tmp_path / "vector.pdf"
    pdf.save(path)
    return path


def test_a_line_drawing_is_rendered_and_a_caution_bar_is_not(tmp_path: Path) -> None:
    doc = DoclingDocument("d", "d.pdf", 1)

    images = _extract_vector_figures(_pdf(tmp_path), 1, doc, logging.getLogger("test"))

    assert len(images) == 1
    image = images[0]
    assert image.origin == "vector"
    assert image.bbox is not None and image.bbox.coordinate_origin == "bottomleft"
    assert 140 <= image.bbox.x0 <= 160 and image.bbox.y0 > image.bbox.y1
    assert image.image_bytes.startswith(b"\x89PNG")


def test_only_vector_figures_carry_an_origin_in_images_v1(tmp_path: Path) -> None:
    doc = DoclingDocument("d", "d.pdf", 1)
    images = _extract_vector_figures(_pdf(tmp_path), 1, doc, logging.getLogger("test"))

    record = serialize_images(images)["images"][0]

    assert record["origin"] == "vector"
