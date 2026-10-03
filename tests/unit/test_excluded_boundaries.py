"""Excluded TOC entries as section boundaries (BUG-002)."""

from __future__ import annotations

from src.pipeline.pipeline import _with_excluded_boundaries
from src.tree_builder.toc_classification import filter_toc_entries


def test_top_level_excluded_entries_come_back_in_toc_order() -> None:
    raw = [
        (1, "Legend", 2),
        (1, "Table of contents", 4),
        (1, "Introduction", 10),
        (2, "Symbols", 11),
        (1, "Index", 463),
    ]
    kept, excluded = filter_toc_entries(raw)

    entries, boundaries = _with_excluded_boundaries(kept, excluded, len(raw))

    # 'Symbols' sits inside a chapter: it stays out, as before.
    assert entries == [raw[0], raw[1], raw[2], raw[4]]
    assert boundaries == [False, True, False, True]
