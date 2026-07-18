"""
Tree page — navigate document hierarchy.
"""
from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
for _p in [str(_APP_DIR), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

from components.tree_view import render_tree

st.set_page_config(page_title="Tree · PDF Tree", page_icon="🌳", layout="wide")
_CSS = (_APP_DIR / "styles" / "theme.css").read_text()
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

st.markdown("## 🌳 Document Tree")
st.divider()

_pipe = st.session_state.get("pipeline_result")

if _pipe is None:
    st.info("No pipeline result yet. Run the pipeline on the **📄 Extraction** page.")
    st.stop()

if _pipe.error:
    st.error(f"Pipeline failed: {_pipe.error}")
    st.stop()

if not _pipe.sections:
    st.warning("Empty tree — no sections extracted.")
    st.stop()

# Summary bar
_c1, _c2, _c3, _c4 = st.columns(4)
_c1.metric("Total sections", _pipe.section_count)
_c2.metric("Root sections", len(_pipe.root_sections))
_c3.metric("Valid", "✓" if _pipe.valid else "✗")
_c4.metric("Document", st.session_state.get("pdf_name", "—"))

st.divider()

# Controls
_col_ctrl, _col_tree = st.columns([1, 4])
with _col_ctrl:
    st.markdown("**View options**")
    _max_nodes = st.slider("Max sections", 50, 2000, 500, step=50)
    _expand_depth = st.slider("Auto-expand depth", 0, 4, 1)
    _show_content = st.checkbox("Show content blocks", value=True)
    _max_content = st.slider(
        "Content items per section", 1, 20, 8, disabled=not _show_content
    )

    _n_images = len(_pipe.images)
    _show_images = st.checkbox(
        f"Show images ({_n_images})",
        value=False,
        disabled=_n_images == 0,
    )

    st.divider()
    st.markdown("**Legend**")
    st.markdown("""
| Symbol | Source |
|--------|--------|
| 📎 | fitz bookmark |
| 📄 | docling inferred |
| 🔍 | implicit |
    """)

_pdf_path_str = st.session_state.get("pdf_path")
_work_dir_str = st.session_state.get("work_dir")
_pdf_path = Path(_pdf_path_str) if _pdf_path_str else None
_page_render_dir = Path(_work_dir_str) / "page_renders" if _work_dir_str else None

with _col_tree:
    render_tree(
        _pipe.sections,
        max_nodes=_max_nodes,
        auto_expand_depth=_expand_depth,
        show_content=_show_content,
        max_content_items=_max_content,
        images=_pipe.images if _pipe.images else None,
        show_images=_show_images,
        pdf_path=_pdf_path,
        page_render_dir=_page_render_dir,
    )
