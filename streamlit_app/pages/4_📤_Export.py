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

from services.qa_ui import init_session_state, qa_settings_sidebar
from src.qa_workflow.findings import (
    checklist_reference_markdown,
    generate_findings_template,
    write_findings_template,
)
from src.qa_workflow.sampling import generate_sample, render_sample_markdown
from src.qa_workflow.storage import (
    atomic_write_text,
    build_artifact_zip,
    create_qa_version,
    open_qa_version,
    verify_source_pdf,
    write_pipeline_artifacts,
)

st.set_page_config(page_title="Export · PDF Tree", page_icon="📤", layout="wide")
_CSS = (_APP_DIR / "styles" / "theme.css").read_text()
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
init_session_state()
_qa_settings = qa_settings_sidebar()

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
                **({"origin": img.origin} if img.origin != "raster" else {}),
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

# ---------------------------------------------------------------------------
# Versioned QA workspace
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### Versioned QA workspace")
st.caption(
    "Create is exclusive and never overwrites an existing version. Open continues an existing review."
)

_source_path = Path(st.session_state.get("pdf_path", ""))
try:
    _durable_source = _source_path.is_file() and _source_path.resolve().is_relative_to(
        _qa_settings.source_dir
    )
except (OSError, ValueError):
    _durable_source = False
if not _durable_source:
    st.warning(
        "This PDF is not inside PDF_TREE_SOURCE_DIR. Select it from the configured source "
        "directory on the Extraction page before creating a durable QA version."
    )

_qa_col1, _qa_col2 = st.columns(2)
with _qa_col1:
    _create = st.button(
        "Create version and save all artifacts",
        type="primary",
        disabled=not _durable_source or not _qa_settings.reviewer.strip(),
    )
with _qa_col2:
    _open = st.button("Open existing version")

if _create:
    try:
        _qa_version = create_qa_version(
            _qa_settings.qa_dir,
            _qa_settings.manual_id,
            _qa_settings.version,
            _source_path,
            _qa_settings.reviewer,
        )
        _validation_payload = {
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
            "validation": _pipe.validation.to_dict() if _pipe.validation else None,
        }
        write_pipeline_artifacts(
            _qa_version,
            tree=_pipe.sections,
            images=_pipe.images,
            bookmarks=_pipe.bookmarks,
            validation_report=_validation_payload,
            run_log=st.session_state.get("pipeline_log", ""),
        )
        _sample = generate_sample(_pipe.sections, _pipe.total_pages)
        atomic_write_text(
            _qa_version.root / "sampling" / "sample_selection.md",
            render_sample_markdown(_qa_version.manual_id, _sample),
        )
        _finding_rows = generate_findings_template(_qa_version.manual_id, _pipe.sections, _sample)
        write_findings_template(_qa_version.findings_csv, _finding_rows)
        atomic_write_text(
            _qa_version.root / "findings" / "checklist_reference.md",
            checklist_reference_markdown(_qa_version.manual_id),
        )
        atomic_write_text(
            _qa_version.root / "summary.md",
            f"# QA summary — `{_qa_version.manual_id}` `{_qa_version.version}`\n\n"
            f"Status: in_review\n\nSample quota: {_sample.quota} pages; "
            f"{len(_sample.distinct_sections)} sections; {len(_finding_rows)} findings.\n",
        )
        st.session_state.qa_active = (_qa_version.manual_id, _qa_version.version)
        st.success(
            f"Saved {_qa_version.manual_id}/{_qa_version.version}: {_sample.quota} quota pages, "
            f"{len(_sample.distinct_sections)} sections, {len(_finding_rows)} checklist rows."
        )
    except Exception as exc:
        st.error(str(exc))

if _open:
    try:
        _qa_version = open_qa_version(
            _qa_settings.qa_dir, _qa_settings.manual_id, _qa_settings.version
        )
        st.session_state.qa_active = (_qa_version.manual_id, _qa_version.version)
    except Exception as exc:
        st.error(str(exc))

_active = st.session_state.get("qa_active")
if _active:
    try:
        _qa_version = open_qa_version(_qa_settings.qa_dir, *_active)
        _integrity = verify_source_pdf(_qa_version)
        st.info(
            f"Open: `{_qa_version.manual_id}/{_qa_version.version}` · "
            f"status `{_qa_version.version_manifest['status']}` · {_integrity.status}"
        )
        _include_images = st.checkbox("Include images_v1.json in QA ZIP", value=False)
        st.download_button(
            "Download QA artifact ZIP",
            data=build_artifact_zip(_qa_version, include_images=_include_images),
            file_name=f"{_qa_version.manual_id}_{_qa_version.version}_qa.zip",
            mime="application/zip",
        )
    except Exception as exc:
        st.error(str(exc))
