"""Version-specific confidence index and consolidated bug report."""

from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
for _path in (str(_APP_DIR), str(_PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import streamlit as st

from services.qa_ui import init_session_state, qa_settings_sidebar
from src.qa_workflow.confidence import (
    build_confidence_report,
    latest_versions,
    list_manual_versions,
    write_confidence_outputs,
)

st.set_page_config(page_title="Confidence Index · PDF Tree", page_icon="📈", layout="wide")
st.markdown(
    f"<style>{(_APP_DIR / 'styles' / 'theme.css').read_text()}</style>", unsafe_allow_html=True
)
init_session_state()
_settings = qa_settings_sidebar()

st.markdown("## 📈 Confidence Index")
st.caption(
    "Scores and bugs use exactly one selected version per manual. Historical severity labels "
    "are normalized in memory and source files are not rewritten."
)
st.divider()

_catalog = list_manual_versions(_settings.qa_dir)
if not _catalog:
    st.info("No versioned QA manuals are available.")
    st.stop()

_defaults = latest_versions(_settings.qa_dir)
_selected: dict[str, str] = {}
with st.expander("Manual and version selection", expanded=True):
    for _manual_id, _versions in _catalog.items():
        _include_col, _version_col = st.columns([1, 3])
        _include = _include_col.checkbox(
            "Include", value=True, key=f"confidence_include_{_manual_id}"
        )
        _version = _version_col.selectbox(
            _manual_id,
            _versions,
            index=_versions.index(_defaults[_manual_id]),
            key=f"confidence_version_{_manual_id}",
        )
        if _include:
            _selected[_manual_id] = _version

if not _selected:
    st.warning("Select at least one manual.")
    st.stop()

try:
    _report = build_confidence_report(_settings.qa_dir, _selected)
except Exception as exc:
    st.error(str(exc))
    st.stop()

_score_rows = []
for _score in _report.scores:
    _score_rows.append(
        {
            "manual_id": _score.manual_id,
            "version": _score.version,
            "status": _score.status,
            "evaluated": _score.total_items,
            "unevaluated": _score.unevaluated_items,
            "weighted_fails": _score.weighted_fails,
            "raw_index": None if _score.raw_index is None else round(_score.raw_index, 2),
            "adjustment": f"Cap 60: {_score.cap_reason}" if _score.cap_applied else "None",
            "final_index": None if _score.final_index is None else round(_score.final_index),
        }
    )
st.dataframe(_score_rows, hide_index=True, width="stretch")

_complete = [score for score in _report.scores if score.final_index is not None]
_pending = [score for score in _report.scores if score.status == "pending"]
_c1, _c2, _c3 = st.columns(3)
_c1.metric("Selected manuals", len(_report.scores))
_c2.metric("Pending", len(_pending))
_c3.metric(
    "Mean final index",
    f"{sum(score.final_index or 0 for score in _complete) / len(_complete):.1f}"
    if _complete
    else "—",
)

st.markdown("### Consolidated bugs")
st.dataframe(list(_report.bugs), hide_index=True, width="stretch")

if st.button("Save report and reproducibility manifest", type="primary"):
    _manifest = write_confidence_outputs(_settings.qa_dir, _report)
    st.success(f"Saved report, consolidated CSV, and `{_manifest.path}`")

_download_md, _download_csv = st.columns(2)
_download_md.download_button(
    "Download confidence_index_report.md",
    _report.markdown,
    file_name="confidence_index_report.md",
    mime="text/markdown",
)
_download_csv.download_button(
    "Download consolidated_bugs.csv",
    _report.bugs_csv,
    file_name="consolidated_bugs.csv",
    mime="text/csv",
)

with st.expander("Calculation detail"):
    st.code(
        "weighted_fails = Critical*8 + High*4 + Medium*2 + Low*1\n"
        "raw_index = clamp(100 * (1 - weighted_fails / evaluated_items), 0, 100)\n"
        "final_index = min(raw_index, 60) only when Coverage or Structure FAILs",
        language="text",
    )
    st.markdown(_report.markdown)
