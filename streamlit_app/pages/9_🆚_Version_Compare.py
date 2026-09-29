"""Compare a mitigation version (v2.1, v2.2, ...) with its base version."""

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
from src.qa_workflow.compare import compare_versions
from src.qa_workflow.confidence import (
    list_manual_versions,
    read_version_manifest,
    version_display_name,
)
from src.qa_workflow.root_causes import CATALOGUE_FILENAME, load_catalogue

st.set_page_config(page_title="Version Compare · PDF Tree", page_icon="🆚", layout="wide")
st.markdown(
    f"<style>{(_APP_DIR / 'styles' / 'theme.css').read_text()}</style>", unsafe_allow_html=True
)
init_session_state()
_settings = qa_settings_sidebar()

st.markdown("## 🆚 Version Compare")
st.caption(
    "Compare a mitigation version with its base. Counts use paired rows: the same section, "
    "page and check reviewed in both versions. Draft rows are AI proposals until approved."
)
st.divider()

_catalog = list_manual_versions(_settings.qa_dir)
_mitigated = {
    manual: [
        version
        for version in versions
        if "mitigation" in read_version_manifest(_settings.qa_dir, manual, version)
    ]
    for manual, versions in _catalog.items()
}
_mitigated = {manual: versions for manual, versions in _mitigated.items() if versions}
if not _mitigated:
    st.info(
        "No mitigation versions yet. Create one after a fix with "
        "`uv run python qa/_scripts/create_mitigation_version.py --manual <id> --base v2 "
        "--version v2.1 --bugs BUG-019`."
    )
    st.stop()

_col_manual, _col_candidate, _col_base = st.columns(3)
_manual_id = _col_manual.selectbox("Manual", list(_mitigated))
_candidate = _col_candidate.selectbox(
    "Mitigation version",
    _mitigated[_manual_id],
    index=len(_mitigated[_manual_id]) - 1,
    format_func=lambda version: version_display_name(_settings.qa_dir, _manual_id, version),
)
_default_base = read_version_manifest(_settings.qa_dir, _manual_id, _candidate)["mitigation"].get(
    "base_version"
)
_bases = [version for version in _catalog[_manual_id] if version != _candidate]
_base = _col_base.selectbox(
    "Compare against",
    _bases,
    index=_bases.index(_default_base) if _default_base in _bases else 0,
    format_func=lambda version: version_display_name(_settings.qa_dir, _manual_id, version),
)
_include_drafts = st.toggle("Include AI drafts not yet approved", value=True)

try:
    _catalogue = load_catalogue(_settings.qa_dir / "confidence_index" / CATALOGUE_FILENAME)
    _cmp = compare_versions(
        _settings.qa_dir, _manual_id, _base, _candidate, _catalogue, include_drafts=_include_drafts
    )
except Exception as exc:
    st.error(str(exc))
    st.stop()

st.markdown(f"### {_cmp.candidate_label} vs {_base}")
if _cmp.pipeline_commit:
    st.caption(f"Pipeline commit `{_cmp.pipeline_commit[:7]}` — {_cmp.pipeline_subject}")

_m1, _m2, _m3, _m4 = st.columns(4)
_m1.metric("Candidate rows reviewed", f"{_cmp.candidate_reviewed} / {_cmp.candidate_rows}")
_m2.metric("Paired rows", _cmp.paired_rows)


def _index(score) -> str:  # type: ignore[no-untyped-def]
    return "—" if score.final_index is None else f"{score.final_index:.0f}"


_delta_index = (
    None
    if _cmp.base_score.final_index is None or _cmp.candidate_score.final_index is None
    else round(_cmp.candidate_score.final_index - _cmp.base_score.final_index, 1)
)
_m3.metric(
    f"Confidence index, paired rows ({_candidate})",
    _index(_cmp.candidate_score),
    delta=_delta_index,
    help=f"{_base}: {_index(_cmp.base_score)}. Both use paired rows only. "
    "Provisional while rows are pending or drafts.",
)
_regressions = sum(1 for change in _cmp.row_changes if change.kind == "regression")
_m4.metric("Regressions", _regressions, delta=-_regressions or None, delta_color="inverse")

if _cmp.candidate_reviewed == 0:
    st.warning(
        f"{_candidate} has no reviewed rows yet. Review it on the QA Review page (agents + "
        "reviewer); until then only the tree changes below are available."
    )

st.markdown("#### Target bugs")
for _bug in _cmp.target_deltas:
    _c1, _c2 = st.columns([3, 1])
    _c1.markdown(f"**{_bug.bug_id}** — {_bug.title}")
    _c2.metric(
        "Paired FAIL rows",
        _bug.candidate_paired,
        delta=_bug.change or None,
        delta_color="inverse",
        help=f"{_base}: {_bug.base_paired} paired ({_bug.base_total} total); "
        f"{_candidate}: {_bug.candidate_total} total.",
    )

st.markdown("#### All bugs")
st.dataframe(
    [
        {
            "bug": bug.bug_id,
            "target": "yes" if bug.targeted else "",
            f"{_base} (paired)": bug.base_paired,
            f"{_candidate} (paired)": bug.candidate_paired,
            "change": bug.change,
            f"{_base} (all rows)": bug.base_total,
            f"{_candidate} (all rows)": bug.candidate_total,
            "title": bug.title,
        }
        for bug in _cmp.bugs
    ],
    hide_index=True,
    width="stretch",
)

st.markdown("#### Row changes")
if _cmp.row_changes:
    st.dataframe(
        [
            {
                "kind": change.kind,
                "section": change.section_id,
                "page": change.page_sampled,
                "check": change.checklist_ref,
                _base: f"{change.base_result} {change.base_bug}".strip(),
                _candidate: f"{change.candidate_result} {change.candidate_bug}".strip(),
                "evidence": change.candidate_evidence,
            }
            for change in sorted(_cmp.row_changes, key=lambda item: item.kind != "regression")
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.caption("No paired row changed result or bug.")

st.markdown("#### Tree changes")
if _cmp.tree_changes is None:
    st.caption("tree.json is missing for one of the versions (exports are local only).")
elif not _cmp.tree_changes:
    st.caption("The section tree is identical.")
else:
    _changed_sections = len({change.section_id for change in _cmp.tree_changes})
    st.caption(f"{_changed_sections} section(s) changed.")
    st.dataframe(
        [
            {
                "section": change.section_id,
                "field": change.field,
                _base: change.base_value,
                _candidate: change.candidate_value,
            }
            for change in _cmp.tree_changes
        ],
        hide_index=True,
        width="stretch",
    )
