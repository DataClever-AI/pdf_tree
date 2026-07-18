"""
View page — load exported tree.json (+ images_v1.json, bookmarks.json) and
inspect without running the pipeline.

Accepts any tree.json produced by this app (flat section list format).
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
for _p in [str(_APP_DIR), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

from components.tree_view import render_tree
from src.pipeline.pipeline import EmbeddedImage

st.set_page_config(page_title="View · PDF Tree", page_icon="👁", layout="wide")
_CSS = (_APP_DIR / "styles" / "theme.css").read_text()
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

st.markdown("## 👁 View — Load Exported Artifacts")
st.caption("Inspect any exported tree/images/toc without re-running Docling or the pipeline.")
st.divider()

_col_upload, _col_info = st.columns([2, 1])

with _col_upload:
    st.markdown("### Load files")
    _tree_file = st.file_uploader(
        "tree.json (flat section list) — required",
        type=["json"],
        key="view_tree",
    )
    _images_file = st.file_uploader(
        "images_v1.json — optional",
        type=["json"],
        key="view_images",
    )
    _bookmarks_file = st.file_uploader(
        "bookmarks.json — optional",
        type=["json"],
        key="view_bookmarks",
    )

with _col_info:
    st.markdown("### File formats")
    st.markdown("""
**tree.json** — flat list of section dicts:
`section_id`, `title`, `hierarchy_level`, `page_start`, `page_end`,
`parent_section_id`, `child_sections`, `semantic_nodes`, `node_count`

**images_v1.json** — `{"images": [{"section_id", "page_no", "width_px",
"height_px", "image_b64"}, ...]}`

**bookmarks.json** — `[{"level", "title", "page_no"}, ...]`
    """)
    st.info("All three are produced by **📤 Export** after running the pipeline.")

st.divider()

_images: list[EmbeddedImage] = []
if _images_file is not None:
    try:
        _images_payload = json.loads(_images_file.read())
        _raw_images = _images_payload.get("images", []) if isinstance(_images_payload, dict) else _images_payload
        for _img in _raw_images:
            _images.append(
                EmbeddedImage(
                    image_bytes=base64.b64decode(_img["image_b64"]),
                    page_no=_img.get("page_no", 0),
                    width_px=_img.get("width_px", 0),
                    height_px=_img.get("height_px", 0),
                    section_id=_img.get("section_id"),
                )
            )
    except Exception as exc:
        st.error(f"Failed to parse images_v1.json: {exc}")
        _images = []

_bookmarks: list[dict[str, Any]] = []
if _bookmarks_file is not None:
    try:
        _bm_raw = json.loads(_bookmarks_file.read())
        _bookmarks = _bm_raw if isinstance(_bm_raw, list) else []
    except Exception as exc:
        st.error(f"Failed to parse bookmarks.json: {exc}")
        _bookmarks = []

_sections: list[dict[str, Any]] | None = None
_meta: dict[str, Any] = {}

if _tree_file is not None:
    try:
        _sections = json.loads(_tree_file.read())
        if not isinstance(_sections, list):
            st.error("tree.json must be a JSON array of section dicts.")
            _sections = None
        else:
            _roots = [s for s in _sections if s.get("parent_section_id") is None]
            _total_nodes = sum(s.get("node_count", 0) for s in _sections)
            _levels = sorted({s.get("hierarchy_level", 1) for s in _sections})
            _meta = {
                "sections": len(_sections),
                "roots": len(_roots),
                "total_nodes": _total_nodes,
                "max_level": max(_levels) if _levels else 0,
            }
    except Exception as exc:
        st.error(f"Failed to parse tree.json: {exc}")
        _sections = None

if _sections is None:
    st.info("Upload a `tree.json` file above to inspect the document tree.")
    st.stop()

# Summary
st.markdown(f"### {_tree_file.name}")
_m1, _m2, _m3, _m4, _m5 = st.columns(5)
_m1.metric("Sections", _meta.get("sections", "—"))
_m2.metric("Root sections", _meta.get("roots", "—"))
_m3.metric("Content nodes", _meta.get("total_nodes", "—"))
_m4.metric("Max depth", _meta.get("max_level", "—"))
_m5.metric("Images loaded", len(_images))

if _bookmarks:
    st.divider()
    with st.expander(f"📎 TOC bookmarks ({len(_bookmarks)})", expanded=False):
        st.dataframe(_bookmarks, hide_index=True, use_container_width=True)

st.divider()
st.markdown("### Document Tree")

_ctrl, _tree_col = st.columns([1, 5])
with _ctrl:
    st.markdown("**View options**")
    _max_nodes = st.slider("Max sections", 50, 5000, 1000, step=50, key="view_max")
    _expand_depth = st.slider("Auto-expand depth", 0, 4, 1, key="view_expand")
    _show_content = st.checkbox("Show content blocks", value=False, key="view_content")
    _show_images = st.checkbox(
        "Show images", value=bool(_images), key="view_show_images",
        disabled=not _images,
    )

with _tree_col:
    render_tree(
        _sections,
        max_nodes=_max_nodes,
        auto_expand_depth=_expand_depth,
        show_content=_show_content,
        images=_images,
        show_images=_show_images,
    )
