"""
Metrics page — stage timing, tree stats, validation results.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
for _p in [str(_APP_DIR), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

from components.telemetry_cards import render_telemetry
from components.validation_table import render_validation

st.set_page_config(page_title="Metrics · PDF Tree", page_icon="📊", layout="wide")
_CSS = (_APP_DIR / "styles" / "theme.css").read_text()
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

st.markdown("## 📊 Metrics")
st.divider()

_pipe = st.session_state.get("pipeline_result")
_pdf_name = st.session_state.get("pdf_name", "document")

if _pipe is None:
    st.info("No pipeline result yet. Run the pipeline on the **📄 Extraction** page.")
    st.stop()

if _pipe.error:
    st.error(f"Pipeline failed: {_pipe.error}")
    st.stop()

# Top summary
_c1, _c2, _c3, _c4, _c5, _c6 = st.columns(6)
_c1.metric("Sections", _pipe.section_count)
_c2.metric("Root sections", len(_pipe.root_sections))
_c3.metric("Valid", "✓" if _pipe.valid else "✗")
_c4.metric("Docling blocks", _pipe.docling_text_blocks)
_c5.metric("Pipeline time", f"{_pipe.elapsed_s:.1f}s")
_c6.metric("Fitz TOC", "✓" if _pipe.fitz_authoritative else "Synthetic")

_stem = Path(_pdf_name).stem.replace(" ", "_")[:40]
_metrics_payload = {
    "pdf_name": _pdf_name,
    "summary": {
        "section_count": _pipe.section_count,
        "root_sections": len(_pipe.root_sections),
        "valid": _pipe.valid,
        "docling_text_blocks": _pipe.docling_text_blocks,
        "docling_tables": _pipe.docling_tables,
        "total_pages": _pipe.total_pages,
        "elapsed_s": _pipe.elapsed_s,
        "docling_elapsed_s": _pipe.docling_elapsed_s,
        "fitz_authoritative": _pipe.fitz_authoritative,
        "structural_source": _pipe.structural_source,
    },
    "stage_times": _pipe.stage_times,
    "validation": _pipe.validation.to_dict() if _pipe.validation is not None else None,
}
_metrics_bytes = json.dumps(_metrics_payload, ensure_ascii=False, indent=2).encode()
st.download_button(
    label="⬇ Download validation_report.json",
    data=_metrics_bytes,
    file_name="validation_report.json",
    mime="application/json",
    help="Summary + stage_times + validation report — for QA evidence (EVALUATION_GUIDE.md §5.2).",
)

st.divider()

# Stage timing + telemetry
st.markdown("### Stage timing")
render_telemetry(_pipe)

# Docling stats
if _pipe.docling_doc is not None:
    st.divider()
    st.markdown("### Docling extraction")
    _e1, _e2, _e3, _e4 = st.columns(4)
    _e1.metric("Pages", _pipe.total_pages)
    _e2.metric("Text blocks", _pipe.docling_text_blocks)
    _e3.metric("Tables", _pipe.docling_tables)
    _e4.metric("Docling time", f"{_pipe.docling_elapsed_s:.1f}s")

# Validation
st.divider()
st.markdown("### Validation")
if _pipe.validation is not None:
    render_validation(_pipe.validation)
else:
    st.info("No validation report. Pipeline may have failed before validation step.")
