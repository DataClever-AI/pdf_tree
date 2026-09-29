from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.qa_workflow.confidence import consolidate_failures, normalize_severity
from src.qa_workflow.root_causes import (
    classify,
    consolidate,
    load_catalogue,
    parse_catalogue,
)

CATALOGUE = {
    "schema_version": 1,
    "bugs": [
        {"bug_id": "BUG-001", "title": "Header bleed", "suspected_module": "section_matcher.py"},
        {"bug_id": "BUG-002", "title": "Vector figures dropped", "suspected_module": "pipeline.py"},
    ],
    "rules": [
        {"bug_id": "BUG-002", "regex": r"vector paths"},
        {"bug_id": "BUG-001", "regex": r"running header"},
    ],
    "overrides": {"m1|sec_0009|5.4-page_start_end": "BUG-002"},
    "exclusions": {"m1|sec_0010|5.4-flagged_for_review": "Control finding"},
}


def _fail(section, ref="5.4-page_start_end", severity="Low", notes=""):
    return {
        "section_id": section,
        "page_sampled": "1",
        "checklist_ref": ref,
        "result": "FAIL",
        "severity": severity,
        "evidence": "",
        "notes": notes,
    }


def test_classify_prefers_override_then_rule_order():
    catalogue = parse_catalogue(CATALOGUE)
    assert classify(catalogue, "m1", _fail("sec_0009", notes="running header")) == "BUG-002"
    assert classify(catalogue, "m1", _fail("sec_0001", notes="Running header p2")) == "BUG-001"
    both = "running header and figures drawn with vector paths"
    assert classify(catalogue, "m1", _fail("sec_0001", notes=both)) == "BUG-002"
    assert classify(catalogue, "m1", _fail("sec_0001", notes="something new")) is None


def test_classify_uses_bug_id_cited_in_notes():
    catalogue = parse_catalogue(CATALOGUE)
    row = _fail("sec_0010", notes="The heading is in sec_0008. Cause: BUG-002.")
    assert classify(catalogue, "m1", row) == "BUG-002"
    ruled = _fail("sec_0010", notes="Cause: BUG-002. Running header bleed.")
    assert classify(catalogue, "m1", ruled) == "BUG-001"  # curated rules win
    assert classify(catalogue, "m1", _fail("sec_0010", notes="Cause: BUG-999.")) is None


def test_consolidate_groups_by_root_cause_and_traces_every_row():
    catalogue = parse_catalogue(CATALOGUE)
    rows = {
        "m1": [
            _fail("sec_0001", notes="running header", severity="Baja"),
            _fail("sec_0002", notes="running header", severity="Media"),
            _fail("sec_0010", ref="5.4-flagged_for_review"),
            _fail("sec_0011", ref="5.6-table_content", notes="unknown", severity="High"),
        ],
        "m2": [_fail("sec_0005", notes="figures drawn with vector paths", severity="Critical")],
    }
    result = consolidate(catalogue, rows, normalize_severity)
    by_id = {bug["bug_id"]: bug for bug in result.bugs}
    assert by_id["BUG-001"]["severity"] == "Medium"
    assert by_id["BUG-001"]["sections_affected"] == "2 sections: m1:sec_0001, m1:sec_0002"
    assert by_id["BUG-001"]["escalate"] == "No"
    assert by_id["BUG-002"]["manuals_affected"] == "m2"
    assert by_id["BUG-002"]["escalate"] == "Yes"
    assert by_id["TRIAGE-001"]["title"].endswith("5.6-table_content FAILs in m1")
    assert [row["section_id"] for row in result.excluded] == ["sec_0010"]
    assert len(result.assignments) == 4


def test_undefined_bug_id_is_rejected():
    payload = {**CATALOGUE, "overrides": {"m1|sec_0001|5.4-page_start_end": "BUG-999"}}
    with pytest.raises(ValueError, match="BUG-999"):
        parse_catalogue(payload)


def test_confidence_consolidation_uses_catalogue_not_notes(tmp_path: Path):
    path = tmp_path / "root_causes.json"
    path.write_text(json.dumps(CATALOGUE), encoding="utf-8")
    catalogue = load_catalogue(path)
    rows = {
        "m1": [
            _fail("sec_0001", notes="Running header bleed, first wording"),
            _fail("sec_0002", notes="A different sentence about the running header"),
            {**_fail("sec_0003"), "result": "PASS"},
        ]
    }
    bugs = consolidate_failures(rows, catalogue)
    assert [bug["bug_id"] for bug in bugs] == ["BUG-001"]
    assert bugs[0]["title"] == "Header bleed"


def test_missing_catalogue_sends_everything_to_triage(tmp_path: Path):
    catalogue = load_catalogue(tmp_path / "missing.json")
    bugs = consolidate_failures({"m1": [_fail("sec_0001"), _fail("sec_0002")]}, catalogue)
    assert [bug["bug_id"] for bug in bugs] == ["TRIAGE-001"]
    assert bugs[0]["sections_affected"] == "2 sections: m1:sec_0001, m1:sec_0002"


def test_repository_catalogue_is_valid():
    path = Path(__file__).resolve().parents[2] / "qa" / "confidence_index" / "root_causes.json"
    catalogue = load_catalogue(path)
    assert catalogue.bugs
    assert all(bug_id in catalogue.bugs for bug_id in catalogue.overrides.values())
