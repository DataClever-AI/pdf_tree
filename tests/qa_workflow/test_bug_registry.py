from __future__ import annotations

import csv
import json
from pathlib import Path

from src.qa_workflow.bug_registry import (
    GENERATED_END,
    GENERATED_START,
    collect_occurrences,
    parse_front_matter,
    refresh_generated_block,
    write_registry,
)
from src.qa_workflow.root_causes import parse_catalogue

CATALOGUE = parse_catalogue(
    {
        "bugs": [
            {"bug_id": "BUG-001", "title": "Header bleed", "suspected_module": "matcher"},
            {"bug_id": "BUG-002", "title": "Pipeline abort", "suspected_module": "sanity"},
        ],
        "rules": [{"bug_id": "BUG-001", "regex": "running header"}],
        "overrides": {},
        "exclusions": {},
    }
)
COLUMNS = [
    "manual_id",
    "section_id",
    "page_sampled",
    "checklist_ref",
    "result",
    "severity",
    "evidence",
    "notes",
]


def _qa_root(tmp_path: Path) -> Path:
    version = tmp_path / "qa" / "m1" / "v1"
    (version / "findings").mkdir(parents=True)
    rows = [
        ["m1", "sec_0001", "3", "5.4-page_start_end", "FAIL", "Baja", "e1", "running header"],
        ["m1", "sec_0002", "5", "5.4-page_start_end", "PASS", "", "e2", ""],
        ["m1", "sec_0003", "7", "5.4-page_start_end", "", "", "", ""],
        ["m1", "sec_0004", "9", "5.6-table_content", "FAIL", "High", "e4", "unknown"],
    ]
    with (version / "findings" / "findings_log.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    batch = version / "agent_exchange" / "b01"
    batch.mkdir(parents=True)
    draft = dict(zip(COLUMNS, rows[2], strict=True))
    draft.update(result="FAIL", severity="Medium", notes="running header of next page")
    (batch / "validated_draft.json").write_text(json.dumps({"findings": [draft]}))
    return tmp_path / "qa"


def test_collect_marks_official_and_draft_rows(tmp_path: Path):
    collected = collect_occurrences(_qa_root(tmp_path), CATALOGUE)
    sources = sorted(item.source for item in collected.by_bug["BUG-001"])
    assert sources == ["draft:b01", "official"]
    assert collected.by_bug["BUG-001"][0].severity in {"Low", "Medium"}
    assert [item.section_id for item in collected.triage] == ["sec_0004"]
    official = collect_occurrences(tmp_path / "qa", CATALOGUE, include_drafts=False)
    assert [item.source for item in official.by_bug["BUG-001"]] == ["official"]


def test_registry_keeps_human_text_and_refreshes_occurrences(tmp_path: Path):
    qa_root = _qa_root(tmp_path)
    registry = qa_root / "bugs"
    write_registry(registry, CATALOGUE, collect_occurrences(qa_root, CATALOGUE), "2026-09-29")
    record = registry / "BUG-001" / "bug.md"
    text = record.read_text().replace("status: open", "status: fixed")
    text = text.replace("Proposed or applied change", "Fixed in commit abc123")
    record.write_text(text)

    write_registry(registry, CATALOGUE, collect_occurrences(qa_root, CATALOGUE), "2026-10-01")
    refreshed = record.read_text()
    assert "Fixed in commit abc123" in refreshed
    assert parse_front_matter(refreshed)["status"] == "fixed"
    assert "sec_0001 (p3)" in refreshed and "sec_0003 (p7)" in refreshed
    rows = list(csv.DictReader((registry / "BUG-001" / "occurrences.csv").open()))
    assert len(rows) == 2
    assert "No QA FAIL rows" in (registry / "BUG-002" / "bug.md").read_text()
    index = (registry / "README.md").read_text()
    assert "| [BUG-001](BUG-001/bug.md) | Header bleed | Medium | fixed |" in index
    assert "triage.csv" in index


def test_refresh_appends_block_when_markers_are_missing():
    block = f"{GENERATED_START}\nnew\n{GENERATED_END}"
    assert refresh_generated_block("# Title\n", block).endswith(block + "\n")
    existing = f"# Title\n\n{GENERATED_START}\nold\n{GENERATED_END}\n"
    assert refresh_generated_block(existing, block) == f"# Title\n\n{block}\n"
