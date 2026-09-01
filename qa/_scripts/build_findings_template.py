#!/usr/bin/env python3
"""
Build the Task 1.5 findings_log.csv template, pre-populated with one row per
(sampled section x applicable checklist item), so PASS/FAIL/severity/evidence
are the only cells left to fill in during manual inspection.

Reuses stratified_sample.build_sample() (Task 1.3) so the section list and
the triggering page always match sample_selection.md exactly.

Checklist items:
  - Sec 5.4 (structural review, 7 items) — applies to every sampled section.
  - Sec 5.6 numbering_scheme / offset_applied — applies to every section.
  - Sec 5.6 table_content — only if the section has at least one table node.
  - Sec 5.5 (images, 3 items) — only if at least one image (mapped or not)
    falls inside the section's page range.
  - Sec 5.6 sanity_report — one document-level row, not tied to a section.

Usage:
    python3 build_findings_template.py <tree.json> --manual-id ID \
        --total-pages N [--images images_v1.json] --out findings_log.csv \
        [--legend-out checklist_reference.md]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from stratified_sample import build_sample

CHECKLIST_5_4 = [
    ("5.4-hierarchy_level",
     "hierarchy_level matches the bookmark's real nesting level in the PDF."),
    ("5.4-parent_child",
     "parent_section_id / child_sections are structurally coherent."),
    ("5.4-page_start_end",
     "Opened page_start/page_end - section content actually starts/ends there."),
    ("5.4-hierarchy_path",
     "hierarchy_path reflects the real path from the root."),
    ("5.4-gaps_duplicates",
     "No gaps, no duplicates - section appears exactly once, matching the PDF index."),
    ("5.4-flagged_for_review",
     "If flagged_for_review: true, manually confirmed genuinely right/wrong."),
    ("5.4-structural_source",
     "If structural_source is 'inferred', extra scrutiny applied."),
]
CHECKLIST_5_6_ALWAYS = [
    ("5.6-numbering_scheme",
     "numbering_scheme transitions correctly at this section boundary."),
    ("5.6-offset_applied",
     "offset_applied has no large unexplained delta vs. adjacent sections."),
]
CHECKLIST_5_6_TABLE = (
    "5.6-table_content",
    "Table node canonical_text has a real markdown grid, not an empty "
    "'[Table RxC]' placeholder.",
)
CHECKLIST_5_5 = [
    ("5.5-filters_discarding",
     "Relevant diagrams/screenshots are not being discarded by the image filters."),
    ("5.5-filters_passing_noise",
     "Logos/icons are not incorrectly passing the image filters."),
    ("5.5-image_section_mapping",
     "Images map to the correct (deepest) section, especially on pages "
     "shared by sibling sections."),
]
CHECKLIST_5_6_DOC = (
    "5.6-sanity_report",
    "If the pipeline aborted, the cause is recorded in sanity_report "
    "(document-level, not section-level).",
)


def section_has_table(section: dict[str, Any]) -> bool:
    return any(n.get("node_type") == "table" for n in section.get("semantic_nodes", []))


def page_range_has_image(images: list[dict[str, Any]], page_start: int, page_end: int) -> bool:
    return any(page_start <= img.get("page_no", -1) <= page_end for img in images)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tree_json", type=Path)
    ap.add_argument("--manual-id", required=True)
    ap.add_argument("--total-pages", type=int, required=True)
    ap.add_argument("--fraction", type=float, default=0.15)
    ap.add_argument("--images", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--legend-out", type=Path, default=None)
    args = ap.parse_args()

    sections = json.loads(args.tree_json.read_text())
    by_id = {s["section_id"]: s for s in sections}
    result = build_sample(sections, args.total_pages, args.fraction)

    # section_id -> triggering page (first row that references it, in page order)
    trigger_page: dict[str, int] = {}
    for row in result["rows"]:
        if row["section_id"] and row["section_id"] not in trigger_page:
            trigger_page[row["section_id"]] = row["page"]

    images: list[dict[str, Any]] = []
    if args.images and args.images.exists():
        images = json.loads(args.images.read_text()).get("images", [])

    rows_out: list[list[str]] = []
    legend_seen: dict[str, str] = {}

    for section_id in result["distinct_sections"]:
        section = by_id[section_id]
        page = trigger_page.get(section_id, section.get("page_start", ""))
        items = list(CHECKLIST_5_4) + list(CHECKLIST_5_6_ALWAYS)
        if section_has_table(section):
            items.append(CHECKLIST_5_6_TABLE)
        p_start = section.get("page_start")
        p_end = section.get("page_end") or p_start
        if images and p_start is not None and page_range_has_image(images, p_start, p_end):
            items.extend(CHECKLIST_5_5)
        for ref, question in items:
            legend_seen[ref] = question
            rows_out.append([args.manual_id, section_id, str(page), ref, "", "", "", ""])

    # one document-level row, not tied to any section
    ref, question = CHECKLIST_5_6_DOC
    legend_seen[ref] = question
    rows_out.append([args.manual_id, "DOCUMENT-LEVEL", "", ref, "", "", "", ""])

    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "manual_id", "section_id", "page_sampled", "checklist_ref",
            "result", "severity", "evidence", "notes",
        ])
        writer.writerows(rows_out)

    n_secs = len(result["distinct_sections"])
    print(f"Written: {args.out} ({len(rows_out)} rows, {n_secs} sections)")

    if args.legend_out:
        lines = [
            f"# Checklist reference - `{args.manual_id}`",
            "",
            "One question per `checklist_ref` value used in `findings_log.csv`.",
            "",
        ]
        lines.append("| checklist_ref | Question |")
        lines.append("|---|---|")
        for ref in sorted(legend_seen):
            lines.append(f"| `{ref}` | {legend_seen[ref]} |")
        args.legend_out.write_text("\n".join(lines) + "\n")
        print(f"Written: {args.legend_out}")


if __name__ == "__main__":
    main()
