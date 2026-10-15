"""Coverage: text before the first section is front matter, not an orphan block."""

from __future__ import annotations

from src.models.extraction import DoclingDocument, DoclingTextBlock, ExtractionProvenance
from src.pipeline.pipeline import _front_matter_count, _split_tail_count
from src.tree_builder.section_matcher import MatchedSection


def _block(order: int, page: int) -> DoclingTextBlock:
    return DoclingTextBlock(
        block_id=f"#/texts/{order}",
        text=f"text {order}",
        label="text",
        page_no=page,
        reading_order=order,
        depth=0,
        provenance=ExtractionProvenance(source="docling", page_no=page),
    )


def test_cover_title_before_the_first_section_counts_as_front_matter() -> None:
    # LOGIQ_S8 p1: the cover title is read before the "Service Manual" heading that
    # anchors the first section, which also starts on p1.
    blocks = [_block(order, 1) for order in range(5)] + [_block(5, 2), _block(6, 9)]
    doc = DoclingDocument("d", "d.pdf", 9, text_blocks=blocks)
    first = MatchedSection("sec_0001", "Service Manual", 1, 1, 2, text_blocks=blocks[3:6])

    # #/texts/0-2 come before the anchor; #/texts/6 is on a page no section covers.
    assert _front_matter_count(doc, [first]) == 4


def test_split_tails_count_as_blocks_and_keep_docling_orders() -> None:
    # SOMATOM p102: the matcher splits a merged margin heading and renumbers reading
    # orders; front matter is still found with Docling's own orders (BUG-029).
    blocks = [_block(order, 1) for order in range(4)]
    doc = DoclingDocument("d", "d.pdf", 1, text_blocks=blocks)
    tail = _block(9, 1)
    tail = DoclingTextBlock(
        block_id="#/texts/2-tail",
        text=tail.text,
        label="text",
        page_no=1,
        reading_order=2,
        depth=0,
        provenance=tail.provenance,
    )
    renumbered = [
        DoclingTextBlock(
            block_id=b.block_id,
            text=b.text,
            label="text",
            page_no=1,
            reading_order=b.reading_order - 1,
            depth=0,
            provenance=b.provenance,
        )
        for b in blocks[2:]
    ]
    first = MatchedSection("sec_0001", "Title", 1, 1, 1, text_blocks=[tail, *renumbered])

    assert _split_tail_count(doc, [first]) == 1
    assert _front_matter_count(doc, [first]) == 2
