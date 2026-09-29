"""
Task 2.3 — consolidate FAIL rows from every manual's latest QA version into one list
deduplicated by root cause, using the curated catalogue
``qa/confidence_index/root_causes.json`` (overrides first, then ordered regex rules on
notes/evidence; unmatched rows become TRIAGE entries). The catalogue is edited by the QA
reviewer; this script only reads it.

Outputs (in ``qa/confidence_index/``):
  consolidated_bugs.csv              Task 2.3 list from the official findings_log.csv files
  consolidated_bugs_assignments.csv  one line per FAIL row -> bug_id (traceability)

With ``--include-drafts``, rows not yet reviewed in findings_log.csv are filled from the
validated agent drafts (latest batch wins, as in page 7) and the outputs are written as
``*_draft.csv`` instead. Draft results are provisional until the human reviewer approves.

Usage: uv run python qa/_scripts/consolidate_bugs.py [--include-drafts]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(QA_DIR.parent))

from src.qa_workflow.confidence import latest_versions, normalize_severity  # noqa: E402
from src.qa_workflow.root_causes import (  # noqa: E402
    CATALOGUE_FILENAME,
    consolidate,
    load_catalogue,
    load_version_rows,
)

OUT_DIR = QA_DIR / "confidence_index"
BUG_FIELDS = [
    "bug_id",
    "title",
    "severity",
    "manuals_affected",
    "sections_affected",
    "suspected_module",
    "escalate",
]
ASSIGNMENT_FIELDS = [
    "bug_id",
    "manual_id",
    "section_id",
    "page_sampled",
    "checklist_ref",
    "severity",
]


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--include-drafts", action="store_true")
    args = parser.parse_args()

    catalogue = load_catalogue(OUT_DIR / CATALOGUE_FILENAME)
    versions = latest_versions(QA_DIR)
    fails: dict[str, list[dict[str, str]]] = {}
    pending: dict[str, int] = {}
    for manual_id, version in versions.items():
        rows = load_version_rows(QA_DIR / manual_id / version, args.include_drafts)
        fails[manual_id] = [row for row in rows if row.get("result", "").upper() == "FAIL"]
        pending[manual_id] = sum(1 for row in rows if not row.get("result", "").strip())
    result = consolidate(catalogue, fails, normalize_severity)

    suffix = "_draft" if args.include_drafts else ""
    bugs_path = OUT_DIR / f"consolidated_bugs{suffix}.csv"
    assignments_path = OUT_DIR / f"consolidated_bugs_assignments{suffix}.csv"
    _write(bugs_path, BUG_FIELDS, list(result.bugs))
    _write(assignments_path, ASSIGNMENT_FIELDS, list(result.assignments))

    total = sum(len(rows) for rows in fails.values())
    root_causes = [bug for bug in result.bugs if bug["bug_id"].startswith("BUG-")]
    triage = [bug for bug in result.bugs if bug["bug_id"].startswith("TRIAGE-")]
    print(f"Wrote {bugs_path.relative_to(QA_DIR.parent)} and {assignments_path.name}")
    print(f"  {total} FAIL rows from {len(versions)} manuals -> {len(root_causes)} root causes")
    print(f"  {len(triage)} TRIAGE groups, {len(result.excluded)} row(s) excluded as not a defect")
    for manual_id, version in versions.items():
        note = f", {pending[manual_id]} rows still unreviewed" if pending[manual_id] else ""
        print(f"  {manual_id} {version}: {len(fails[manual_id])} FAIL{note}")


if __name__ == "__main__":
    main()
