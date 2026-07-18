"""
Telemetry cards — stage timing + tree stats.

Adapted from 0.1v_pdf_tree. Uses PipelineResult from src.pipeline.pipeline.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from src.pipeline.pipeline import PipelineResult

_STAGE_LABELS = {
    "fitz": "Fitz · TOC + page count",
    "bookmark_sanity": "Sanity · Bookmark check",
    "docling_extract": "Docling · Content extraction",
    "toc_path": "TOC · Path selection",
    "section_matcher": "Matcher · Content → sections",
    "tree_export": "Export · Build tree.json",
    "validation": "Validation · Tree checks",
    "image_extraction": "Images · Embedded extraction",
}


def render_telemetry(result: PipelineResult) -> None:
    """Render pipeline telemetry: timing + tree metrics."""
    st.subheader("Pipeline Summary")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Time", f"{result.elapsed_s:.2f}s")
    c2.metric("Pages", result.total_pages)
    c3.metric("Bookmarks", len(result.bookmarks))
    c4.metric("Sections", result.section_count)
    c5.metric("Fitz TOC", "✓" if result.fitz_authoritative else "Inferred")

    st.divider()
    st.subheader("Stage Timing")

    if result.stage_times:
        total_stage_time = sum(result.stage_times.values())
        cols = st.columns(min(len(result.stage_times), 4))
        for i, (key, elapsed) in enumerate(result.stage_times.items()):
            label = _STAGE_LABELS.get(key, key)
            pct = elapsed / max(total_stage_time, 0.001) * 100
            cols[i % 4].metric(
                label,
                f"{elapsed:.3f}s",
                delta=f"{pct:.0f}% of stages",
                delta_color="off",
            )
    else:
        st.info("No stage timing data.")

    st.divider()
    st.subheader("Tree Metrics")
    stats = _tree_stats(result)
    if stats:
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        r1c1.metric("Total Sections", stats["total_sections"])
        r1c2.metric("Root Sections", stats["root_sections"])
        r1c3.metric("Max Depth", stats["max_depth"])
        r1c4.metric("Leaf Sections", stats["leaf_sections"])

        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        r2c1.metric("Total Content Nodes", stats["total_nodes"])
        r2c2.metric("Avg Nodes/Section", f"{stats['avg_nodes']:.1f}")
        r2c3.metric("Structural Source", result.structural_source)
        r2c4.metric("Images Extracted", len(result.images))

        if stats.get("level_dist"):
            st.markdown("**Level Distribution**")
            try:
                import pandas as pd
                df = pd.DataFrame(
                    [{"Level": f"L{k}", "Sections": v} for k, v in sorted(stats["level_dist"].items())]
                )
                st.bar_chart(df.set_index("Level"))
            except Exception:
                st.write(stats["level_dist"])
    else:
        st.warning("Empty tree — no metrics.")

    # Bookmark sanity
    st.divider()
    st.subheader("Bookmark Sanity")
    sanity = result.sanity_report
    issues = sanity.issues
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Issues", len(issues))
    sc2.metric("Hard Failures", sum(1 for i in issues if i.kind == "out_of_order"))
    sc3.metric("Warnings", sum(1 for i in issues if i.kind != "out_of_order"))
    if issues:
        with st.expander(f"Sanity issues ({len(issues)})", expanded=False):
            for issue in issues:
                color = "#f44336" if issue.kind == "out_of_order" else "#ff9800"
                st.markdown(
                    f"<div style='background:#1a1a2e;border-left:3px solid {color};"
                    f"padding:4px 8px;margin:2px 0;border-radius:0 3px 3px 0;"
                    f"font-family:monospace;font-size:0.80em;color:#fff'>"
                    f"[{issue.kind}] {issue.detail}"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def _tree_stats(result: PipelineResult) -> dict[str, Any]:
    sections = result.sections
    if not sections:
        return {}
    total_nodes = sum(s.get("node_count", 0) for s in sections)
    roots = [s for s in sections if s.get("parent_section_id") is None]
    leaves = [s for s in sections if not s.get("child_sections")]
    levels = [s.get("hierarchy_level", 1) for s in sections]
    max_depth = max(levels) if levels else 0
    level_dist: dict[int, int] = {}
    for lvl in levels:
        level_dist[lvl] = level_dist.get(lvl, 0) + 1
    return {
        "total_sections": len(sections),
        "root_sections": len(roots),
        "leaf_sections": len(leaves),
        "max_depth": max_depth,
        "total_nodes": total_nodes,
        "avg_nodes": total_nodes / max(len(sections), 1),
        "level_dist": level_dist,
    }
