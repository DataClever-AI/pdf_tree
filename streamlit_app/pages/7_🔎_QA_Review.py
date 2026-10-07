"""Versioned AI-assisted, human-approved QA review."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
for _path in (str(_APP_DIR), str(_PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import streamlit as st

from services.qa_ui import configured_secret, init_session_state, qa_settings_sidebar
from src.qa_workflow.ai_review import (
    AgentBatch,
    detect_agent_batch,
    prepare_agent_batch,
    render_pdf_page,
    run_qwen_batch,
)
from src.qa_workflow.confidence import list_manual_versions, version_display_name
from src.qa_workflow.findings import CHECKLIST
from src.qa_workflow.review import (
    bulk_approve_all,
    bulk_approve_eligible,
    bulk_eligible,
    finalize_review,
    load_findings,
    merge_drafts_into_state,
    pending_approvals,
    prioritize_findings,
    restore_original_proposal,
    save_review_decision,
    unreviewed_without_draft,
)
from src.qa_workflow.storage import open_qa_version, verify_source_pdf

st.set_page_config(page_title="QA Review · PDF Tree", page_icon="🔎", layout="wide")
st.markdown(
    f"<style>{(_APP_DIR / 'styles' / 'theme.css').read_text()}</style>", unsafe_allow_html=True
)
init_session_state()
_settings = qa_settings_sidebar()


@st.cache_data(show_spinner=False)
def _render_page(path: str, modified_ns: int, page_no: int, zoom: float) -> bytes:
    del modified_ns
    return render_pdf_page(Path(path), page_no, zoom)


@st.cache_data(show_spinner="Loading extracted-image index…")
def _load_images(path: str, modified_ns: int) -> list[dict]:
    del modified_ns
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload.get("images", []) if isinstance(payload, dict) else payload


st.markdown("## 🔎 Human QA Review")
st.caption("AI results are drafts. Only an explicit human approval updates findings_log.csv.")
st.divider()

_catalog = list_manual_versions(_settings.qa_dir)
if not _catalog:
    st.info("No QA versions exist. Create one from the Export page.")
    st.stop()

_manual_options = list(_catalog)
_default_manual = (
    _manual_options.index(_settings.manual_id) if _settings.manual_id in _manual_options else 0
)
_manual_id = st.selectbox("Manual", _manual_options, index=_default_manual)
_versions = _catalog[_manual_id]
# Open the latest version of the manual; the sidebar version is the Export target, not this.
_version_name = st.selectbox(
    "Version",
    _versions,
    index=len(_versions) - 1,
    format_func=lambda version: version_display_name(_settings.qa_dir, _manual_id, version),
)
_qa_version = open_qa_version(_settings.qa_dir, _manual_id, _version_name)
_integrity = verify_source_pdf(_qa_version)

_m1, _m2, _m3 = st.columns(3)
_m1.metric("Status", _qa_version.version_manifest["status"])
_m2.metric("Reviewer", _qa_version.version_manifest.get("reviewer") or "—")
_m3.metric("Source", "Verified" if _integrity.valid else "Blocked")
if not _integrity.valid:
    st.error(
        f"Visual and AI review are blocked: {_integrity.status}. Expected SHA-256: "
        f"`{_integrity.expected_sha256 or 'not recorded'}`."
    )

if not _qa_version.tree_path.exists() or not _qa_version.findings_csv.exists():
    st.warning("This version is pending pipeline output and has no reviewable tree/findings yet.")
    if _qa_version.run_log_path.exists():
        st.code(_qa_version.run_log_path.read_text(encoding="utf-8"), language="text")
    st.stop()

_sections = json.loads(_qa_version.tree_path.read_text(encoding="utf-8"))
_sections_by_id = {section["section_id"]: section for section in _sections}
_rows = load_findings(_qa_version.findings_csv)

_tab_agent, _tab_review = st.tabs(["AI draft preparation", "Human review"])

with _tab_agent:
    if not _integrity.valid:
        st.warning("Restore the exact source PDF before preparing or running AI batches.")
    else:
        _sampled_sections = sorted(
            {row["section_id"] for row in _rows if row["section_id"] != "DOCUMENT-LEVEL"}
        )
        _selected_sections = st.multiselect(
            "Sections in new batch",
            _sampled_sections,
            default=_sampled_sections[: min(5, len(_sampled_sections))],
        )
        _batch_id = st.text_input("Batch ID", value=f"{_version_name}-batch-001")
        if st.button("Prepare shared-folder batch", disabled=not _selected_sections):
            try:
                _batch = prepare_agent_batch(_qa_version, _batch_id, section_ids=_selected_sections)
                st.success(f"Prepared `{_batch.root}`")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        _batch_roots = sorted(
            path
            for path in (_qa_version.root / "agent_exchange").glob("*")
            if path.is_dir() and (path / "input").is_dir()
        )
        if _batch_roots:
            _selected_batch_root = st.selectbox(
                "Existing batch", _batch_roots, format_func=lambda p: p.name
            )
            _batch_manifest = json.loads(
                (_selected_batch_root / "batch_manifest.json").read_text(encoding="utf-8")
            )
            _batch = AgentBatch(
                _selected_batch_root.name,
                _selected_batch_root,
                _selected_batch_root / "input",
                _selected_batch_root / "output",
                tuple(_batch_manifest.get("section_ids", [])),
            )
            _progress = detect_agent_batch(_batch)
            _stages = [
                "Prepared",
                "Waiting for agent",
                "Output detected",
                "Validated",
                "Draft ready",
            ]
            _active_index = _stages.index(_progress.stage)
            _stage_cols = st.columns(5)
            for _index, (_column, _stage) in enumerate(zip(_stage_cols, _stages, strict=True)):
                _column.markdown(f"{'✅' if _index <= _active_index else '○'} **{_stage}**")
            if _progress.validation and _progress.validation.errors:
                st.error("\n".join(_progress.validation.errors))
                st.caption(f"Pending rows: {len(_progress.validation.pending_keys)}")
            if st.button("Refresh agent results"):
                st.rerun()

            st.markdown("#### Qwen3-VL endpoint")
            _endpoint = st.text_input(
                "POST endpoint",
                value=configured_secret(
                    "QWEN3_VL_URL", "http://127.0.0.1:8000/v1/chat/completions"
                ),
            )
            _model = st.text_input(
                "Model", value=configured_secret("QWEN3_VL_MODEL", "Qwen/Qwen3-VL")
            )
            _token = st.text_input(
                "Token", value=configured_secret("QWEN3_VL_TOKEN"), type="password"
            )
            _timeout = st.number_input("Timeout per request (seconds)", 10, 3600, 120)
            _remote = not any(host in _endpoint for host in ("127.0.0.1", "localhost", "::1"))
            st.caption(
                "Remote endpoint: PDF pages leave this machine." if _remote else "Local endpoint"
            )
            if st.button("Run/resume Qwen3-VL batch"):
                try:
                    with st.spinner("Running pending sections and checkpointing each result…"):
                        _run = run_qwen_batch(
                            _batch,
                            endpoint_url=_endpoint,
                            model=_model,
                            token=_token,
                            timeout=float(_timeout),
                        )
                    st.success(
                        f"Completed {len(_run.completed_sections)}; skipped "
                        f"{len(_run.skipped_sections)}; failed {len(_run.failed_sections)}."
                    )
                    if _run.failed_sections:
                        st.json(_run.failed_sections)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

with _tab_review:
    _state = merge_drafts_into_state(_qa_version)
    _prioritized = prioritize_findings(_rows, _state, _sections_by_id)
    _priority_filter = st.multiselect(
        "Priority",
        [1, 2, 3, 4, 5],
        default=[1, 2, 3, 4, 5],
        format_func=lambda value: {
            1: "1 — FAIL",
            2: "2 — Confidence < 0.80",
            3: "3 — Flagged section",
            4: "4 — Deterministic 5% PASS audit",
            5: "5 — Remaining",
        }[value],
    )
    _visible = [item for item in _prioritized if item["priority"] in _priority_filter]
    _eligible_count = sum(bulk_eligible(item, _state, _sections_by_id) for item in _prioritized)
    _bulk_col, _finish_col = st.columns(2)
    if _bulk_col.button(f"Approve eligible high-confidence PASS ({_eligible_count})"):
        try:
            _count = bulk_approve_eligible(_qa_version, reviewer=_settings.reviewer)
            st.success(f"Approved {_count} findings; backup created before the bulk write.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    _pending = pending_approvals(_state, [item["stable_key"] for item in _visible])
    _pending_total = len(_pending["PASS"]) + len(_pending["FAIL"])
    with st.expander(
        f"Approve all pending in the current filter ({_pending_total}: "
        f"{len(_pending['PASS'])} PASS, {len(_pending['FAIL'])} FAIL)"
    ):
        st.caption(
            "Approves every pending AI proposal shown by the Priority filter, FAIL rows "
            "included, without opening them one by one. Use it for quick tests. A backup is "
            "written first and each row is saved with approval_mode = bulk-all."
        )
        if _pending["invalid"]:
            st.caption(
                f"{len(_pending['invalid'])} pending row(s) have an invalid proposal and "
                "are skipped; review them one by one."
            )
        _confirm = st.checkbox(
            f"I approve these {_pending_total} rows as reviewer {_settings.reviewer or '—'}"
        )
        if st.button(
            "Approve all pending",
            type="primary",
            disabled=not (_confirm and _pending_total),
        ):
            try:
                _count = bulk_approve_all(
                    _qa_version,
                    reviewer=_settings.reviewer,
                    keys=[item["stable_key"] for item in _visible],
                )
                st.success(f"Approved {_count} findings; backup created before the bulk write.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    if _finish_col.button("Finalize version"):
        try:
            finalize_review(_qa_version)
            st.success("Version finalized.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if not _visible:
        st.info("No findings match the selected priorities.")
        st.stop()
    _without_draft = unreviewed_without_draft(_visible, _state)
    if _without_draft:
        _first = _without_draft[0]
        st.warning(
            f"{len(_without_draft)} row(s) have no AI draft and are not reviewed yet; "
            "no approval button counts them. First: "
            f"{_first['section_id']} · {_first['checklist_ref']}."
        )
        if st.button("Open the first unreviewed row"):
            st.session_state.qa_review_cursor = _visible.index(_first)
            st.rerun()
    _cursor = min(st.session_state.get("qa_review_cursor", 0), len(_visible) - 1)
    _labels = [
        f"P{item['priority']} · {item['section_id']} · {item['checklist_ref']} · "
        f"{item['priority_reason']}"
        for item in _visible
    ]
    _selected_label = st.selectbox("Finding", _labels, index=_cursor)
    _index = _labels.index(_selected_label)
    st.session_state.qa_review_cursor = _index
    _item = _visible[_index]
    _key = _item["stable_key"]
    _section = _sections_by_id.get(_item["section_id"], {})
    _section_index = _sections.index(_section) if _section else -1

    _left, _right = st.columns(2)
    with _left:
        st.markdown("### Structure and extracted content")
        st.markdown(
            f"**Question:** {CHECKLIST.get(_item['checklist_ref'], _item['checklist_ref'])}"
        )
        if _section:
            st.write(
                {
                    "title": _section.get("title"),
                    "hierarchy_level": _section.get("hierarchy_level"),
                    "parent": _section.get("parent_section_id"),
                    "children": _section.get("child_sections", []),
                    "range": f"{_section.get('page_start')}-{_section.get('page_end')}",
                }
            )
            with st.expander("Full section JSON"):
                st.json(_section)
            _page_sampled = int(_item["page_sampled"] or _section.get("page_start") or 1)
            _node_types = sorted(
                {node.get("node_type", "unknown") for node in _section.get("semantic_nodes", [])}
            )
            _selected_types = st.multiselect(
                "Semantic node types", _node_types, default=_node_types
            )
            _nodes = [
                node
                for node in _section.get("semantic_nodes", [])
                if node.get("page_no") == _page_sampled
                and node.get("node_type", "unknown") in _selected_types
            ]
            st.caption(f"{len(_nodes)} nodes on sampled page {_page_sampled}")
            st.json(_nodes)
            with st.expander("Neighbor sections"):
                st.json(
                    {
                        "previous": _sections[_section_index - 1] if _section_index > 0 else None,
                        "next": _sections[_section_index + 1]
                        if 0 <= _section_index < len(_sections) - 1
                        else None,
                    }
                )
        else:
            _page_sampled = 1
            st.info("Document-level checklist item")

    with _right:
        st.markdown("### Exact source page")
        if not _integrity.valid or _integrity.source_path is None:
            st.error("PDF rendering is blocked until source integrity is restored.")
        else:
            _page_options = sorted(
                {
                    int(_section.get("page_start") or _page_sampled),
                    _page_sampled,
                    int(_section.get("page_end") or _page_sampled),
                }
            )
            _page = st.selectbox("Page", _page_options, index=_page_options.index(_page_sampled))
            _zoom = st.slider("Zoom", 1.0, 3.0, 1.0, 0.25, help="1.0 fits the column width.")
            # Render sharp enough for the shown size; the zoom enlarges the page inside a
            # scrollable frame instead of being stretched back to the column width.
            _png = _render_page(
                str(_integrity.source_path),
                _integrity.source_path.stat().st_mtime_ns,
                _page,
                min(2.0 * _zoom, 5.0),
            )
            st.html(
                '<div style="overflow:auto;max-height:80vh;border:1px solid #ddd;">'
                f'<img src="data:image/png;base64,{base64.b64encode(_png).decode()}" '
                f'style="width:{_zoom * 100:.0f}%;max-width:none;display:block;" '
                f'alt="PDF page {_page}"></div>'
            )
            st.caption(f"PDF page {_page}")
            st.download_button(
                "Download page PNG", _png, file_name=f"page_{_page}.png", mime="image/png"
            )
            if _qa_version.images_path.exists() and st.checkbox(
                "Load extracted images on this page"
            ):
                with st.container(border=True):
                    for _image in _load_images(
                        str(_qa_version.images_path), _qa_version.images_path.stat().st_mtime_ns
                    ):
                        if int(_image.get("page_no", -1)) == _page:
                            st.image(base64.b64decode(_image["image_b64"]))

    st.divider()
    st.markdown("### Human decision")
    _decision = _state["decisions"].get(_key, {})
    _proposal = _decision.get("original_proposal") or {}
    if _proposal:
        st.info(
            f"Original {_decision.get('provider')} proposal · confidence "
            f"{float(_decision.get('confidence') or 0):.2f}: "
            f"{_proposal.get('result')} {_proposal.get('severity')} — {_proposal.get('evidence')}"
        )
    else:
        st.caption("No AI proposal; this is a human-only or historical finding.")
    _current_result = _item.get("result") or _proposal.get("result") or "PASS"
    _current_severity = _item.get("severity") or _proposal.get("severity") or ""
    with st.form("review_editor"):
        _result = st.selectbox(
            "Result", ["PASS", "FAIL"], index=0 if _current_result == "PASS" else 1
        )
        _severity_options = ["", "Critical", "High", "Medium", "Low"]
        _severity = st.selectbox(
            "Severity",
            _severity_options,
            index=_severity_options.index(_current_severity)
            if _current_severity in _severity_options
            else 0,
            disabled=_result == "PASS",
        )
        _evidence = st.text_area(
            "Evidence", value=_item.get("evidence") or _proposal.get("evidence", "")
        )
        _notes = st.text_area("Notes", value=_item.get("notes") or _proposal.get("notes", ""))
        _save = st.form_submit_button("Approve, save and next", type="primary")
    if _save:
        try:
            save_review_decision(
                _qa_version,
                _key,
                result=_result,
                severity=_severity if _result == "FAIL" else "",
                evidence=_evidence,
                notes=_notes,
                reviewer=_settings.reviewer,
                approved=True,
            )
            st.session_state.qa_review_cursor = min(_index + 1, len(_visible) - 1)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if st.button("Restore original AI proposal", disabled=not bool(_proposal)):
        try:
            restore_original_proposal(_qa_version, _key, reviewer=_settings.reviewer)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
