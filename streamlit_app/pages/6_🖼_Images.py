"""
Images page — embedded document images grouped by section.
"""
from __future__ import annotations

import base64
import sys
from collections import defaultdict
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
for _p in [str(_APP_DIR), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

st.set_page_config(page_title="Images · PDF Tree", page_icon="🖼", layout="wide")
_CSS = (_APP_DIR / "styles" / "theme.css").read_text()
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

st.markdown("## 🖼 Document Images")
st.divider()

_pipe = st.session_state.get("pipeline_result")

if _pipe is None:
    st.info("No pipeline result yet. Run the pipeline on the **📄 Extraction** page.")
    st.stop()

if _pipe.error:
    st.error(f"Pipeline failed: {_pipe.error}")
    st.stop()

_images = _pipe.images

if not _images:
    st.warning(
        "No images extracted. Enable 'Extract embedded images' in the pipeline form "
        "on the **📄 Extraction** page and re-run."
    )
    st.stop()

# Summary bar
_mapped = [img for img in _images if img.section_id is not None]
_unmapped = [img for img in _images if img.section_id is None]
_c1, _c2, _c3, _c4 = st.columns(4)
_c1.metric("Total images", len(_images))
_c2.metric("Mapped to sections", len(_mapped))
_c3.metric("Unmapped", len(_unmapped))
_c4.metric("Document", st.session_state.get("pdf_name", "—"))

st.divider()

# Controls
_col_ctrl, _col_main = st.columns([1, 5])
with _col_ctrl:
    st.markdown("**Filters**")
    _cols_per_row = st.slider("Columns", 1, 6, 3)
    _show_unmapped = st.checkbox("Show unmapped images", value=True)
    _min_px = st.slider("Min size (px)", 16, 256, 64,
                         help="Filter out tiny images smaller than this threshold.")

# Build section lookup
_sections_by_id = _pipe.sections_by_id()

# Group by section_id
_by_section: dict[str | None, list] = defaultdict(list)
for _img in _images:
    if _img.width_px >= _min_px and _img.height_px >= _min_px:
        _by_section[_img.section_id].append(_img)


def _render_image_grid(imgs: list, cols: int) -> None:
    if not imgs:
        st.caption("No images match the filter.")
        return
    rows = [imgs[i:i + cols] for i in range(0, len(imgs), cols)]
    for row in rows:
        row_cols = st.columns(cols)
        for col, img in zip(row_cols, row, strict=False):
            with col:
                try:
                    b64 = base64.b64encode(img.image_bytes).decode()
                    st.markdown(
                        f'<img src="data:image/png;base64,{b64}" '
                        f'style="width:100%;border-radius:6px;border:1px solid #e2e8f0;" />',
                        unsafe_allow_html=True,
                    )
                except Exception:
                    st.warning("Failed to render image.")
                st.caption(f"p.{img.page_no} · {img.width_px}×{img.height_px}px")


with _col_main:
    # Sorted by section order (hierarchy_level then page_start)
    _sorted_sids = sorted(
        [sid for sid in _by_section if sid is not None],
        key=lambda sid: (
            _sections_by_id.get(sid, {}).get("page_start", 9999),
        ),
    )

    for _sid in _sorted_sids:
        _sec = _sections_by_id.get(_sid, {})
        _title = _sec.get("title", _sid)
        _lvl = _sec.get("hierarchy_level", "?")
        _ps = _sec.get("page_start")
        _pe = _sec.get("page_end")
        _page_range = f"p.{_ps}–{_pe}" if _ps is not None else ""
        _imgs = _by_section[_sid]
        with st.expander(
            f"L{_lvl} · **{_title}** {_page_range} · {len(_imgs)} image(s)",
            expanded=len(_imgs) <= 4,
        ):
            _render_image_grid(_imgs, _cols_per_row)

    # Unmapped
    if _show_unmapped and _by_section.get(None):
        st.divider()
        with st.expander(
            f"⚠ Unmapped — {len(_by_section[None])} image(s) (no matching section)",
            expanded=False,
        ):
            _render_image_grid(_by_section[None], _cols_per_row)
