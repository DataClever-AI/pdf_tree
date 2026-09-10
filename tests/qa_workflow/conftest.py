from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from src.qa_workflow.findings import FindingRow, write_findings_template
from src.qa_workflow.storage import create_qa_version, write_pipeline_artifacts


@pytest.fixture
def source_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "source.pdf"
    document = pymupdf.open()
    for number in range(1, 5):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {number}")
    document.save(path)
    document.close()
    return path


@pytest.fixture
def qa_version(tmp_path: Path, source_pdf: Path):
    version = create_qa_version(tmp_path / "qa", "manual", "v1", source_pdf, "Reviewer")
    tree = [
        {
            "section_id": "sec_0001",
            "title": "Intro",
            "hierarchy_level": 1,
            "hierarchy_path": "/Intro",
            "page_start": 1,
            "page_end": 4,
            "parent_section_id": None,
            "child_sections": [],
            "flagged_for_review": False,
            "structural_source": "toc",
            "semantic_nodes": [{"node_type": "text", "page_no": 1, "canonical_text": "Intro"}],
        }
    ]
    write_pipeline_artifacts(
        version,
        tree=tree,
        images={"images": []},
        bookmarks=[(1, "Intro", 1)],
        validation_report={
            "validation": {
                "coverage": {"status": "PASS"},
                "precision": {"status": "PASS"},
                "structure": {"status": "PASS"},
            }
        },
        run_log="complete\n",
    )
    rows = [
        FindingRow("manual", "sec_0001", "1", "5.4-page_start_end"),
        FindingRow("manual", "sec_0001", "1", "5.5-filters_discarding"),
    ]
    write_findings_template(version.findings_csv, rows)
    return version
