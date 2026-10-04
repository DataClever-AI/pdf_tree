"""Embedded-image filters: small meaningful rasters and repeated decoration (BUG-020, BUG-004)."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf as fitz

from src.pipeline.pipeline import _extract_embedded_images


def _png(width: int, height: int) -> bytes:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
    pixmap.set_rect(pixmap.irect, (200, 30, 30))
    return pixmap.tobytes("png")


def test_small_photo_is_kept_and_repeated_footer_divider_is_dropped(tmp_path: Path) -> None:
    pdf = fitz.open()
    divider_xref = 0
    for page_no in range(6):
        page = pdf.new_page(width=612, height=792)
        divider = fitz.Rect(70, 730, 542, 760)  # inside the bottom 10% band, not the 5%
        if divider_xref:
            page.insert_image(divider, xref=divider_xref)
        else:
            divider_xref = page.insert_image(divider, stream=_png(1400, 100))
        if page_no == 0:
            # Philips p199: a module photo of 52x120 pt covers about 1.3% of the page.
            page.insert_image(fitz.Rect(100, 200, 152, 320), stream=_png(104, 240))
    path = tmp_path / "images.pdf"
    pdf.save(path)

    images = _extract_embedded_images(path, 6, 48, logging.getLogger("test"))

    assert [(image.page_no, image.width_px, image.height_px) for image in images] == [
        (1, 104, 240)
    ]
