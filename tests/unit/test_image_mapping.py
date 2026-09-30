"""Image-to-section mapping by position on the page (BUG-003)."""

from __future__ import annotations

from src.models.extraction import BoundingBox
from src.pipeline.pipeline import EmbeddedImage, _map_images_to_sections


def _node(order: int, page: int, top: float, node_type: str = "paragraph") -> dict:
    return {
        "node_id": f"#/texts/{order}",
        "semantic_order": order,
        "node_type": node_type,
        "page_no": page,
        "bbox": {"x0": 50, "y0": top, "x1": 550, "y1": top - 10},
    }


def _section(section_id: str, level: int, start: int, end: int, nodes: list[dict]) -> dict:
    return {
        "section_id": section_id,
        "hierarchy_level": level,
        "page_start": start,
        "page_end": end,
        "semantic_nodes": nodes,
    }


def _image(page: int, top: float | None) -> EmbeddedImage:
    bbox = None if top is None else BoundingBox(60, top, 500, top - 150, page, "bottomleft")
    return EmbeddedImage(b"", page, 400, 300, bbox=bbox)


def test_images_follow_the_text_printed_above_them():
    # SOMATOM p46: two weight labels at the top of the page belong to 'Monitor cart'
    # (heading on p45), not to the next sibling whose heading is lower on p46.
    cart = _section("sec_0083", 3, 45, 45, [_node(1, 45, 700, "heading"), _node(2, 45, 600)])
    monitor = _section("sec_0084", 3, 46, 46, [_node(4, 46, 300, "heading")])
    images = [_image(46, 760), _image(46, 280), _image(46, None)]
    mapped = _map_images_to_sections(images, [cart, monitor])
    assert [image.section_id for image in mapped] == ["sec_0083", "sec_0084", "sec_0084"]

    # A running header above the image is in the previous section's reading order.
    cart["semantic_nodes"].append(_node(3, 46, 790))
    mapped = _map_images_to_sections(images, [cart, monitor])
    assert [image.section_id for image in mapped] == ["sec_0083", "sec_0084", "sec_0084"]
