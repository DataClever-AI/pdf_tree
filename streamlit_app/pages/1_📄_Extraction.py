"""
Extraction page — upload PDF, run Docling Stage00, run full pipeline.
"""
from __future__ import annotations

import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
for _p in [str(_APP_DIR), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

from services.pipeline_service import build_pipeline, setup_logger
from services.qa_ui import init_session_state, qa_settings_sidebar

st.set_page_config(page_title="Extraction · PDF Tree", page_icon="📄", layout="wide")
_CSS = (_APP_DIR / "styles" / "theme.css").read_text()
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
init_session_state()
_qa_settings = qa_settings_sidebar()

# ---------------------------------------------------------------------------
# Check docling availability — cached: import pulls in torch/transformers,
# only pay that cost once per server process, not on every rerun/navigation.
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading Docling engine…")
def _get_docling_engine() -> Any | None:
    try:
        from src.tree_builder.docling_extract import DoclingExtractionEngine as _DE
        engine = _DE()
        return engine if engine.is_available else None
    except Exception:
        return None


_docling_engine = _get_docling_engine()
_DOCLING_AVAILABLE: bool = _docling_engine is not None

# ---------------------------------------------------------------------------
# Section 1 — Upload PDF
# ---------------------------------------------------------------------------
st.markdown("## 📄 Extraction")
st.divider()
st.markdown("### 1 · Select PDF")

_source_mode = st.radio(
    "Source",
    ["Configured source directory", "Temporary upload"],
    horizontal=True,
    help="Only source-directory PDFs can be registered for durable QA review.",
)
uploaded = None
_selected_source: Path | None = None
if _source_mode == "Configured source directory":
    _source_pdfs = sorted(_qa_settings.source_dir.glob("*.pdf")) if _qa_settings.source_dir.is_dir() else []
    if not _source_pdfs:
        st.warning(f"No PDFs found in `{_qa_settings.source_dir}`.")
    else:
        _selected_name = st.selectbox("Source PDF", [path.name for path in _source_pdfs])
        _selected_source = next(path for path in _source_pdfs if path.name == _selected_name)
else:
    uploaded = st.file_uploader(
        "Drop a PDF",
        type=["pdf"],
        accept_multiple_files=False,
        key="pdf_uploader",
    )

if _selected_source and str(_selected_source.resolve()) != st.session_state.get("pdf_path"):
    _work_dir = Path(tempfile.mkdtemp(prefix="pdftree_"))
    import pymupdf as fitz

    _doc = fitz.open(str(_selected_source))
    _n = _doc.page_count
    _toc = _doc.get_toc()
    _doc.close()
    st.session_state.pdf_path = str(_selected_source.resolve())
    st.session_state.pdf_name = _selected_source.name
    st.session_state.work_dir = str(_work_dir)
    st.session_state.fitz_toc = _toc
    st.session_state.fitz_page_count = _n
    st.session_state.pipeline_result = None
    st.session_state.pipeline_log = ""

if uploaded and uploaded.name != st.session_state.get("pdf_name"):
    _work_dir = Path(tempfile.mkdtemp(prefix="pdftree_"))
    _pdf_path = _work_dir / uploaded.name
    _pdf_path.write_bytes(uploaded.getvalue())

    import pymupdf as fitz
    _doc = fitz.open(str(_pdf_path))
    _n = _doc.page_count
    _toc = _doc.get_toc()
    _doc.close()

    st.session_state.pdf_path = str(_pdf_path)
    st.session_state.pdf_name = uploaded.name
    st.session_state.work_dir = str(_work_dir)
    st.session_state.fitz_toc = _toc
    st.session_state.fitz_page_count = _n
    st.session_state.pipeline_result = None
    st.session_state.pipeline_log = ""

if not st.session_state.get("pdf_path"):
    st.info("Upload a PDF to continue.")
    st.stop()

_pdf_path = Path(st.session_state.pdf_path)
_work_dir = Path(st.session_state.work_dir)
_toc = st.session_state.fitz_toc
_n_pages = st.session_state.fitz_page_count

# ---------------------------------------------------------------------------
# Section 2 — Fitz summary
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### 2 · Fitz extraction")
_f1, _f2, _f3 = st.columns(3)
_f1.metric("Pages", _n_pages)
_f2.metric("Embedded bookmarks", len(_toc))
_f3.metric("Mode", "⚡ Fast path" if len(_toc) >= 5 else "📄 Synthetic TOC fallback")

if _toc:
    with st.expander("TOC preview", expanded=False):
        for _lv, _ti, _pg in _toc[:40]:
            indent = "&nbsp;" * (_lv - 1) * 4
            st.markdown(f"{indent}`L{_lv}` **{_ti}** — p.{_pg}", unsafe_allow_html=True)
        if len(_toc) > 40:
            st.caption(f"… {len(_toc) - 40} more entries")

# ---------------------------------------------------------------------------
# Section 3 — Run pipeline
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### 3 · Run Pipeline")

if not _DOCLING_AVAILABLE:
    st.warning(
        "Docling not available. Install: `uv add 'docling[gpu]'` then restart. "
        "Pipeline will run structure-only (no content extraction)."
    )

with st.form("form_pipeline"):
    _pc1, _pc2 = st.columns(2)
    with _pc1:
        _run_docling = st.checkbox(
            "Run Docling extraction",
            value=_DOCLING_AVAILABLE,
            disabled=not _DOCLING_AVAILABLE,
            help="Extracts text blocks and tables for content preview and coverage validation.",
        )
        _extract_images = st.checkbox(
            "Extract embedded images",
            value=True,
            help="Extract raster images embedded in PDF pages, grouped by section.",
        )
    with _pc2:
        _win = st.slider(
            "Docling batch size (pages)",
            8, 120, 60,
            disabled=not _DOCLING_AVAILABLE,
            help="Pages per Docling window. Larger = fewer batches, more memory.",
        )
        _est_windows = max(1, (_n_pages - _win) // max(_win - 6, 1) + 1)
        st.caption(f"≈ {_est_windows} batches for {_n_pages} pages")
        _overlap = st.slider(
            "Overlap (pages)",
            2, 12, 6,
            disabled=not _DOCLING_AVAILABLE,
            help="Pages shared between adjacent batches for continuity.",
        )

    _btn_pipe = st.form_submit_button("▶ Run Pipeline", type="primary")

if _btn_pipe:
    _pipe_log: list[str] = []

    class _LogCapture(logging.Handler):
        def emit(self, r: logging.LogRecord) -> None:
            _pipe_log.append(self.format(r))

    _logger = setup_logger("pipeline_ui")
    _lh = _LogCapture()
    _lh.setFormatter(logging.Formatter("%(levelname)-8s | %(message)s"))
    _logger.addHandler(_lh)

    _prog_bar = st.progress(0, text="Starting pipeline…")
    _prog_status = st.empty()
    _t_start = time.perf_counter()

    def _on_window(w_idx: int, total: int, elapsed: float) -> None:
        frac = w_idx / max(total, 1)
        rate = elapsed / max(w_idx, 1)
        eta = rate * (total - w_idx)
        _prog_bar.progress(
            frac,
            text=f"Docling: batch {w_idx}/{total} · {int(frac * 100)}% · ETA {eta:.0f}s",
        )
        _prog_status.caption(
            f"Elapsed: {elapsed:.1f}s · ~{eta:.0f}s remaining · "
            f"{w_idx * _win} / {_n_pages} pages"
        )

    with st.spinner("Running PDF Tree pipeline…"):
        _result = build_pipeline(
            pdf_path=_pdf_path,
            work_dir=_work_dir,
            run_docling=_run_docling and _DOCLING_AVAILABLE,
            window_size=_win,
            window_overlap=_overlap,
            extract_images=_extract_images,
            logger=_logger,
            on_window_complete=_on_window if (_run_docling and _DOCLING_AVAILABLE) else None,
        )

    _logger.removeHandler(_lh)
    _prog_bar.progress(1.0, text="Pipeline complete")
    _prog_status.empty()
    st.session_state.pipeline_result = _result
    st.session_state.pipeline_log = "\n".join(_pipe_log) + ("\n" if _pipe_log else "")

    if _result.error:
        st.error(f"❌ Pipeline failed: {_result.error}")
    else:
        st.success(
            f"✅ Done in **{_result.elapsed_s:.2f}s** — "
            f"**{_result.section_count} sections** · "
            f"valid={_result.valid}  \n"
            f"Navigate to **🌳 Tree**, **📊 Metrics**, or **📤 Export**."
        )

    if _pipe_log:
        with st.expander("Pipeline log", expanded=False):
            st.code("\n".join(_pipe_log[-300:]), language="text")

# ---------------------------------------------------------------------------
# Result summary (persists across reruns)
# ---------------------------------------------------------------------------
_pipe = st.session_state.pipeline_result
if _pipe is not None and _pipe.error is None:
    st.divider()
    _r1, _r2, _r3, _r4, _r5, _r6 = st.columns(6)
    _r1.metric("Sections", _pipe.section_count)
    _r2.metric("Root sections", len(_pipe.root_sections))
    _r3.metric("Valid", "✓" if _pipe.valid else "✗")
    _r4.metric("Docling blocks", _pipe.docling_text_blocks)
    _r5.metric("Images", len(_pipe.images))
    _r6.metric("Pipeline time", f"{_pipe.elapsed_s:.1f}s")
