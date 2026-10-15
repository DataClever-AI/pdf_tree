"""Shared Streamlit configuration for versioned QA pages."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class QASettings:
    source_dir: Path
    qa_dir: Path
    manual_id: str
    version: str
    reviewer: str


def init_session_state() -> None:
    defaults = {
        "pdf_path": None,
        "pdf_name": None,
        "work_dir": None,
        "fitz_toc": [],
        "fitz_page_count": 0,
        "pipeline_result": None,
        "pipeline_log": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def qa_settings_sidebar() -> QASettings:
    default_source = _PROJECT_ROOT.parent / "Manuales técnicos TEST"
    default_qa = _PROJECT_ROOT / "qa"
    with st.sidebar.expander("QA workspace", expanded=True):
        source_dir = Path(
            st.text_input(
                "PDF_TREE_SOURCE_DIR",
                value=os.getenv("PDF_TREE_SOURCE_DIR", str(default_source)),
                help="PDFs remain here and are referenced by absolute path and SHA-256.",
            )
        ).expanduser()
        qa_dir = Path(
            st.text_input(
                "PDF_TREE_QA_DIR",
                value=os.getenv("PDF_TREE_QA_DIR", str(default_qa)),
            )
        ).expanduser()
        manual_id = st.text_input("Manual ID", value=st.session_state.get("qa_manual_id", "manual"))
        version = st.text_input("Version", value=st.session_state.get("qa_version", "v1"))
        reviewer = st.text_input(
            "Reviewer",
            value=st.session_state.get("qa_reviewer", os.getenv("PDF_TREE_REVIEWER", "")),
        )
    st.session_state.qa_manual_id = manual_id
    st.session_state.qa_version = version
    st.session_state.qa_reviewer = reviewer
    return QASettings(source_dir.resolve(), qa_dir.resolve(), manual_id, version, reviewer)


def configured_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, os.getenv(name, default))
    except (FileNotFoundError, KeyError):
        value = os.getenv(name, default)
    return str(value or "")
