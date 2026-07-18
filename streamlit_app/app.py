"""
PDF Tree Inspector — home page.

Run:
  uv run streamlit run streamlit_app/app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

_APP_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _APP_DIR.parent
for _p in [str(_APP_DIR), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

st.set_page_config(
    page_title="PDF Tree Inspector",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CSS = (_APP_DIR / "styles" / "theme.css").read_text()
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

for _k, _v in {
    "pdf_path": None,
    "pdf_name": None,
    "work_dir": None,
    "fitz_toc": [],
    "fitz_page_count": 0,
    "pipeline_result": None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    "<h1 style='margin-top:14px;'>🌳 PDF Tree Inspector</h1>",
    unsafe_allow_html=True,
)
st.caption("Semantic Hierarchy Reconstruction · mvp_v2 engine · 0.1v interface")
st.divider()

# ---------------------------------------------------------------------------
# Introduction
# ---------------------------------------------------------------------------
st.markdown("## What this app does")
st.markdown("""
**PDF Tree Inspector** extracts and reconstructs the semantic structure of PDF documents —
turning flat pages into a navigable, validated document tree ready for RAG indexing.

The pipeline uses two extraction layers:

- **Fitz (PyMuPDF)** — reads embedded PDF bookmarks. Fast, authoritative, zero GPU.
- **Docling** — deep layout analysis using neural models. Extracts text blocks, tables,
  and reading order from any PDF — including documents with no bookmarks.

Both signals feed into a **section matching engine** that produces a flat-list `tree.json`:
a typed, validated hierarchy of sections and content nodes.

**Use this app to:**
- Inspect the document hierarchy of any technical manual, report, or specification
- Validate structural integrity before downstream RAG indexing
- Download `tree.json` ready for semantic search pipelines
""")

st.divider()

# ---------------------------------------------------------------------------
# Pipeline stages diagram
# ---------------------------------------------------------------------------
st.markdown("## Pipeline stages")

_PIPELINE_HTML = """
<style>
.pipe-row {
    display: flex; align-items: stretch; gap: 0; margin-bottom: 0;
}
.pipe-card {
    flex: 1; background: #ffffff; border: 1.5px solid #e2e8f0;
    border-radius: 12px; padding: 16px 12px 14px; text-align: center;
    position: relative; transition: box-shadow 0.2s;
}
.pipe-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.10); border-color: #c5cfe8; }
.pipe-badge {
    display: inline-block; font-size: 0.60rem; font-weight: 800;
    text-transform: uppercase; letter-spacing: 0.08em;
    padding: 2px 8px; border-radius: 20px; margin-bottom: 8px;
}
.pipe-icon { font-size: 1.5rem; display: block; margin-bottom: 6px; }
.pipe-title { font-size: 0.82rem; font-weight: 700; color: #1a1f2e; line-height: 1.25; margin-bottom: 4px; }
.pipe-desc { font-size: 0.68rem; color: #888; line-height: 1.35; }
.pipe-arrow {
    display: flex; align-items: center; justify-content: center;
    padding: 0 4px; color: #c5cfe8; font-size: 1.1rem; flex-shrink: 0; font-weight: 700;
}
.pipe-section-label {
    font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.10em; color: #aab; margin: 0 0 8px 2px;
}
</style>

<div style="background:#f7f9fc;border-radius:16px;padding:20px 16px 16px;border:1px solid #e8ecf4;">

  <div class="pipe-section-label">&#9655; Extraction</div>
  <div class="pipe-row">
    <div class="pipe-card">
      <span class="pipe-badge" style="background:#e0f4f1;color:#0e7c6b;">Fitz</span>
      <span class="pipe-icon">📎</span>
      <div class="pipe-title">Bookmark Extraction</div>
      <div class="pipe-desc">Embedded TOC + page count</div>
    </div>
    <div class="pipe-arrow">&#8594;</div>
    <div class="pipe-card">
      <span class="pipe-badge" style="background:#e8f0fe;color:#1a56db;">Sanity</span>
      <span class="pipe-icon">🔍</span>
      <div class="pipe-title">Bookmark Sanity</div>
      <div class="pipe-desc">Pre-check order + page ranges</div>
    </div>
    <div class="pipe-arrow">&#8594;</div>
    <div class="pipe-card">
      <span class="pipe-badge" style="background:#ede9fe;color:#6d28d9;">Docling</span>
      <span class="pipe-icon">📄</span>
      <div class="pipe-title">Content Extraction</div>
      <div class="pipe-desc">Text blocks, tables, reading order</div>
    </div>
  </div>

  <div style="height:10px;"></div>

  <div class="pipe-section-label">&#9655; Reconstruction &amp; Export</div>
  <div class="pipe-row">
    <div class="pipe-card">
      <span class="pipe-badge" style="background:#e8f5e9;color:#2e7d32;">Matcher</span>
      <span class="pipe-icon">🏗</span>
      <div class="pipe-title">Section Matching</div>
      <div class="pipe-desc">Assign content to sections via reading-order</div>
    </div>
    <div class="pipe-arrow">&#8594;</div>
    <div class="pipe-card">
      <span class="pipe-badge" style="background:#fff3e0;color:#e65100;">Export</span>
      <span class="pipe-icon">📤</span>
      <div class="pipe-title">Tree Export</div>
      <div class="pipe-desc">tree.json with semantic_nodes inline</div>
    </div>
    <div class="pipe-arrow">&#8594;</div>
    <div class="pipe-card">
      <span class="pipe-badge" style="background:#fce4ec;color:#c62828;">Validate</span>
      <span class="pipe-icon">✅</span>
      <div class="pipe-title">Validation</div>
      <div class="pipe-desc">Coverage · Precision · Structure</div>
    </div>
  </div>

</div>
"""

st.html(_PIPELINE_HTML)
st.divider()

# ---------------------------------------------------------------------------
# Current document status
# ---------------------------------------------------------------------------
_pipe = st.session_state.pipeline_result
_pdf = st.session_state.pdf_name

if _pdf is None:
    st.info("No document loaded. Navigate to **📄 Extraction** in the sidebar to upload a PDF.")
else:
    st.markdown(f"### Current document: `{_pdf}`")
    _c1, _c2, _c3, _c4, _c5, _c6 = st.columns(6)
    _c1.metric("Pages", st.session_state.fitz_page_count)
    _c2.metric("Fitz bookmarks", len(st.session_state.fitz_toc))
    _c3.metric("Sections", len(_pipe.sections) if _pipe and not _pipe.error else "—")
    _c4.metric("Docling blocks", _pipe.docling_text_blocks if _pipe and not _pipe.error else "—")
    _c5.metric("Valid", ("✓" if _pipe.valid else "✗") if _pipe and not _pipe.error else "—")
    _c6.metric("Pipeline", f"{_pipe.elapsed_s:.1f}s" if _pipe and not _pipe.error else "—")

st.divider()

st.markdown(
    "<div style='text-align:center;padding:16px 0 8px;font-size:0.70rem;color:#999;'>"
    "PDF Tree Inspector · mvp_v2 engine · 0.1v interface"
    "</div>",
    unsafe_allow_html=True,
)
