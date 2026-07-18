"""
Export page — download tree.json, images JSON, docling merged JSON.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
for _p in [str(_APP_DIR), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

st.set_page_config(page_title="Export · PDF Tree", page_icon="📤", layout="wide")
_CSS = (_APP_DIR / "styles" / "theme.css").read_text()
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

st.markdown("## 📤 Export")
st.divider()

_pipe = st.session_state.get("pipeline_result")
_pdf_name = st.session_state.get("pdf_name", "document")
_work_dir_str = st.session_state.get("work_dir")

if _pipe is None:
    st.info("No pipeline result yet. Run the pipeline on the **📄 Extraction** page.")
    st.stop()

if _pipe.error:
    st.error(f"Pipeline failed: {_pipe.error}")
    st.stop()

_stem = Path(_pdf_name).stem.replace(" ", "_")[:40]

# ---------------------------------------------------------------------------
# Tree JSON
# ---------------------------------------------------------------------------
st.markdown("### tree.json")
st.caption("Flat section list with `semantic_nodes` inline — ready for RAG chunking.")

_tree_bytes = json.dumps(_pipe.sections, ensure_ascii=False, indent=2).encode()
_col1, _col2 = st.columns([2, 1])
with _col1:
    st.metric("Sections", _pipe.section_count)
    _total_content = sum(s.get("node_count", 0) for s in _pipe.sections)
    st.metric("Content nodes", _total_content)
    st.metric("Structural source", _pipe.structural_source)
with _col2:
    st.download_button(
        label="⬇ Download tree.json",
        data=_tree_bytes,
        file_name=f"{_stem}_tree.json",
        mime="application/json",
        type="primary",
    )
    st.caption(f"Size: {len(_tree_bytes) / 1024:.1f} KB")

# ---------------------------------------------------------------------------
# Images JSON
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### images_v1.json")
st.caption("Embedded images with base64 bytes, grouped by section — for downstream multimodal use.")

if _pipe.images:
    _mapped = [img for img in _pipe.images if img.section_id is not None]
    _unmapped = [img for img in _pipe.images if img.section_id is None]

    _images_payload = {
        "total": len(_pipe.images),
        "mapped_count": len(_mapped),
        "unmapped_count": len(_unmapped),
        "images": [
            {
                "section_id": img.section_id,
                "page_no": img.page_no,
                "width_px": img.width_px,
                "height_px": img.height_px,
                "image_b64": base64.b64encode(img.image_bytes).decode(),
            }
            for img in _pipe.images
        ],
    }
    _images_bytes = json.dumps(_images_payload, ensure_ascii=False, indent=2).encode()

    _col_i1, _col_i2 = st.columns([2, 1])
    with _col_i1:
        st.metric("Total images", len(_pipe.images))
        st.metric("Mapped to sections", len(_mapped))
        if _unmapped:
            st.metric("Unmapped", len(_unmapped))
    with _col_i2:
        st.download_button(
            label="⬇ Download images_v1.json",
            data=_images_bytes,
            file_name=f"{_stem}_images_v1.json",
            mime="application/json",
        )
        st.caption(f"Size: {len(_images_bytes) / 1024 / 1024:.1f} MB")
else:
    st.info(
        "No images extracted. Enable 'Extract embedded images' in the pipeline form "
        "and re-run."
    )

# ---------------------------------------------------------------------------
# Docling merged JSON
# ---------------------------------------------------------------------------
if _work_dir_str:
    _merged_path = Path(_work_dir_str) / "tree.json"
    if _merged_path.exists():
        st.divider()
        st.markdown("### tree.json (on-disk)")
        st.caption("File written by the pipeline at work_dir/tree.json.")
        _raw = _merged_path.read_bytes()
        st.download_button(
            label="⬇ Download from disk",
            data=_raw,
            file_name=f"{_stem}_tree_disk.json",
            mime="application/json",
        )
        st.caption(f"Size: {len(_raw) / 1024:.1f} KB")

# ---------------------------------------------------------------------------
# Bookmarks JSON
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### bookmarks.json")
st.caption("Raw fitz TOC bookmarks (level, title, page_no) — used as structure priors.")

_bm_payload = [
    {"level": lvl, "title": title, "page_no": pg}
    for lvl, title, pg in _pipe.bookmarks
]
_bm_bytes = json.dumps(_bm_payload, ensure_ascii=False, indent=2).encode()
_col3, _col4 = st.columns([2, 1])
with _col3:
    st.metric("Bookmarks", len(_pipe.bookmarks))
    st.metric("Structural source", _pipe.structural_source)
with _col4:
    st.download_button(
        label="⬇ Download bookmarks.json",
        data=_bm_bytes,
        file_name=f"{_stem}_bookmarks.json",
        mime="application/json",
    )
    st.caption(f"Size: {len(_bm_bytes) / 1024:.1f} KB")

# ---------------------------------------------------------------------------
# On-disk artifacts
# ---------------------------------------------------------------------------
if _work_dir_str:
    st.divider()
    st.markdown("### On-disk artifacts")
    _wd = Path(_work_dir_str)
    _files = sorted(_wd.rglob("*") if _wd.exists() else [])
    _files = [f for f in _files if f.is_file()]
    if _files:
        for _f in _files:
            size = _f.stat().st_size
            st.code(f"{_f}  ({size / 1024:.1f} KB)", language="text")
    else:
        st.caption("No artifacts on disk yet.")
