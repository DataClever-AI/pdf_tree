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


def test_ui_icons_and_unique_thin_screenshots_are_kept(tmp_path: Path) -> None:
    # SOMATOM p340: UI icons of 58x58 px; LOGIQ_S8 p679: a 231x79 px screenshot strip.
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    page.insert_image(fitz.Rect(100, 100, 140, 140), stream=_png(58, 58))
    page.insert_image(fitz.Rect(100, 300, 400, 330), stream=_png(1600, 100))
    rule_xref = 0
    for page_no in range(2):  # a thin rule shown on two pages is decoration
        target = page if page_no == 0 else pdf.new_page(width=612, height=792)
        rule = fitz.Rect(70, 500, 542, 506)
        if rule_xref:
            target.insert_image(rule, xref=rule_xref)
        else:
            rule_xref = target.insert_image(rule, stream=_png(1600, 20))
    path = tmp_path / "icons.pdf"
    pdf.save(path)

    images = _extract_embedded_images(path, 2, 48, logging.getLogger("test"))

    assert sorted((image.width_px, image.height_px) for image in images) == [
        (58, 58), (1600, 100)
    ]


def test_repeated_key_picture_in_the_body_and_a_thin_unique_figure_are_kept(tmp_path: Path) -> None:
    # SOMATOM: the Move key picture is shown on 8 pages inside the body (content);
    # LOGIQ_e p274: a unique 1600x35 px figure strip is under the 48 px floor.
    pdf = fitz.open()
    key_xref = 0
    for _ in range(6):
        page = pdf.new_page(width=612, height=792)
        key = fitz.Rect(300, 400, 350, 450)  # 0.5% of the page
        if key_xref:
            page.insert_image(key, xref=key_xref)
        else:
            key_xref = page.insert_image(key, stream=_png(177, 177))
    pdf[0].insert_image(fitz.Rect(60, 200, 560, 240), stream=_png(1600, 35))
    path = tmp_path / "repeat.pdf"
    pdf.save(path)

    images = _extract_embedded_images(path, 6, 48, logging.getLogger("test"))

    sizes = [(image.width_px, image.height_px) for image in images]
    assert sizes.count((177, 177)) == 6
    assert (1600, 35) in sizes
