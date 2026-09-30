"""Image-to-section mapping by position on the page (BUG-003)."""

from __future__ import annotations

from src.models.extraction import BoundingBox
from src.pipeline.pipeline import EmbeddedImage, _map_images_to_sections


def _node(
    order: int, page: int, top: float, node_type: str = "paragraph", x0: float = 50,
    x1: float = 550,
) -> dict:
    return {
        "node_id": f"#/texts/{order}",
        "semantic_order": order,
        "node_type": node_type,
        "page_no": page,
        "bbox": {"x0": x0, "y0": top, "x1": x1, "y1": top - 10},
    }


def _section(section_id: str, level: int, start: int, end: int, nodes: list[dict]) -> dict:
    return {
        "section_id": section_id,
        "hierarchy_level": level,
        "page_start": start,
        "page_end": end,
        "semantic_nodes": nodes,
    }


def _image(page: int, top: float | None, x0: float = 60, x1: float = 500) -> EmbeddedImage:
    bbox = None if top is None else BoundingBox(x0, top, x1, top - 150, page, "bottomleft")
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


def test_image_right_of_a_left_aligned_heading_follows_the_heading():
    # LOGIQ_S8 p830: part photos in the right column of Table 9-13; the heading
    # 'Section 9-15 Power Cord' is at the left margin, the running header spans the page.
    previous = _section("sec_0126", 2, 820, 829, [_node(1, 830, 759, x0=36, x1=557)])
    power_cord = _section(
        "sec_0127", 2, 830, 830, [_node(2, 830, 726, "heading", x0=36, x1=118)]
    )
    mapped = _map_images_to_sections([_image(830, 630, x0=337, x1=484)], [previous, power_cord])
    assert mapped[0].section_id == "sec_0127"


def test_image_level_with_a_margin_heading_follows_the_heading():
    # SOMATOM p125: side heading 'Operating elements' (top 741) in the left margin,
    # the photo to its right starts at 743; the chapter tab above belongs to the parent.
    parent = _section("sec_0213", 3, 124, 127, [_node(1, 125, 815, x0=472, x1=563)])
    elements = _section(
        "sec_0214", 4, 125, 125, [_node(2, 125, 741, "heading", x0=101, x1=184)]
    )
    mapped = _map_images_to_sections([_image(125, 743, x0=198, x1=539)], [parent, elements])
    assert mapped[0].section_id == "sec_0214"
