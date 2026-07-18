"""
Validation table — renders ValidationReport (coverage, precision, structure).

Adapted from 0.1v_pdf_tree. Uses mvp_v2 ValidationReport from tree_validator.py.
"""
from __future__ import annotations
from typing import Any

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from src.validation.tree_validator import CheckResult, ValidationReport


def render_validation(report: ValidationReport) -> None:
    """Render validation PASS/FAIL with per-check details."""
    if report.status == "PASS":
        st.success("✅ Validation PASSED — tree structure is correct")
    else:
        failed = [
            name for name, chk in [
                ("Coverage", report.coverage),
                ("Precision", report.precision),
                ("Structure", report.structure),
            ]
            if chk.status == "FAIL"
        ]
        st.error(f"❌ Validation FAILED — {', '.join(failed)}")

    c1, c2, c3 = st.columns(3)
    _render_check_metric(c1, "Coverage", report.coverage)
    _render_check_metric(c2, "Precision", report.precision)
    _render_check_metric(c3, "Structure", report.structure)

    st.divider()

    # Coverage details
    _render_check_details("📊 Coverage", report.coverage, {
        "total_docling_blocks": "Docling blocks total",
        "matched_blocks": "Matched to sections",
        "orphaned_count": "Orphaned (unmatched)",
        "duplicate_count": "Duplicate node IDs",
        "expected_front_matter": "Front matter excluded",
    })

    # Precision details
    _render_check_details("🎯 Precision", report.precision, {
        "total_sections": "Total sections",
        "total_nodes_checked": "Nodes checked",
        "page_tolerance": "Page tolerance",
        "misplaced_count": "Misplaced blocks",
    })
    if report.precision.details.get("misplaced_blocks"):
        with st.expander("Misplaced blocks (first 20)", expanded=False):
            for item in report.precision.details["misplaced_blocks"][:20]:
                st.caption(
                    f"`{item.get('node_id', '?')}` page {item.get('page_no')} → "
                    f"section `{item.get('section_id')}` range {item.get('section_range')}"
                )

    # Structure details
    _render_check_details("🏗 Structure", report.structure, {
        "bookmark_count": "Bookmarks",
        "section_count": "Sections",
        "count_match": "Count match",
        "max_depth": "Max depth",
        "root_count": "Root sections",
        "has_cycle": "Has cycle",
    })
    for key, label in [
        ("level_mismatches", "Level mismatches"),
        ("orphan_sections", "Orphan sections"),
        ("missing_parents", "Missing parents"),
        ("invalid_children", "Invalid children"),
    ]:
        items = report.structure.details.get(key, [])
        if items:
            with st.expander(f"{label} ({len(items)})", expanded=False):
                for item in items[:10]:
                    st.caption(str(item))


def _render_check_metric(col: Any, label: str, check: CheckResult) -> None:
    icon = "✅" if check.status == "PASS" else ("⏭" if check.status == "SKIP" else "❌")
    col.metric(label, f"{icon} {check.status}")


def _render_check_details(
    title: str,
    check: CheckResult,
    field_labels: dict[str, str],
) -> None:
    color = "#1b5e20" if check.status == "PASS" else "#b71c1c"
    bg = "#e8f5e9" if check.status == "PASS" else "#ffebee"
    st.markdown(
        f"<div style='background:{bg};border-left:4px solid {color};"
        f"padding:10px 14px;border-radius:0 6px 6px 0;margin:8px 0'>"
        f"<strong style='color:{color}'>{title} — {check.status}</strong>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if check.details:
        cols = st.columns(min(len(field_labels), 4))
        for i, (key, label) in enumerate(field_labels.items()):
            val = check.details.get(key)
            if val is not None:
                cols[i % 4].metric(label, str(val))
