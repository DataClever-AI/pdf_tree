from __future__ import annotations

import csv
from io import StringIO

import pytest

from src.qa_workflow.findings import VISUAL_ALWAYS, findings_csv_text, generate_findings_template
from src.qa_workflow.models import QA_COLUMNS
from src.qa_workflow.sampling import generate_sample


def _sections() -> list[dict]:
    return [
        {
            "section_id": "a",
            "title": "A",
            "hierarchy_level": 1,
            "page_start": 1,
            "page_end": 50,
            "hierarchy_path": "/A",
            "flagged_for_review": False,
            "structural_source": "toc",
            "semantic_nodes": [],
        },
        {
            "section_id": "a1",
            "title": "A1",
            "hierarchy_level": 2,
            "page_start": 2,
            "page_end": 20,
            "hierarchy_path": "/A/A1",
            "flagged_for_review": True,
            "structural_source": "toc",
            "semantic_nodes": [],
        },
        {
            "section_id": "b",
            "title": "B",
            "hierarchy_level": 1,
            "page_start": 51,
            "page_end": 100,
            "hierarchy_path": "/B",
            "flagged_for_review": False,
            "structural_source": "inferred",
            "semantic_nodes": [{"node_type": "table"}],
        },
    ]


def test_sample_is_exact_deterministic_and_keeps_mandatory_sections() -> None:
    first = generate_sample(_sections(), 100)
    second = generate_sample(_sections(), 100)
    assert first == second
    assert first.quota == 15
    assert len(first.quota_pages) == 15
    assert {"a", "a1", "b"} <= set(first.distinct_sections)


def test_sample_falls_back_without_level_one() -> None:
    section = _sections()[1]
    result = generate_sample([section], 20)
    assert len(result.quota_pages) == 3
    assert result.distinct_sections == ("a1",)


def test_sample_rejects_empty_tree() -> None:
    with pytest.raises(ValueError):
        generate_sample([], 10)


def test_template_has_exact_columns_and_visual_checks_without_images() -> None:
    sections = _sections()
    sample = generate_sample(sections, 100)
    rows = generate_findings_template("manual", sections, sample)
    parsed = list(csv.DictReader(StringIO(findings_csv_text(rows))))
    assert tuple(parsed[0]) == QA_COLUMNS
    for section_id in sample.distinct_sections:
        refs = {row["checklist_ref"] for row in parsed if row["section_id"] == section_id}
        assert set(VISUAL_ALWAYS) <= refs
    assert any(row["checklist_ref"] == "5.6-table_content" for row in parsed)
