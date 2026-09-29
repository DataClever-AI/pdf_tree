"""Official checklist and findings template generation."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import QA_COLUMNS
from .sampling import SampleResult
from .storage import atomic_write_text

CHECKLIST: dict[str, str] = {
    "5.4-hierarchy_level": "Does hierarchy_level match the bookmark nesting in the PDF?",
    "5.4-parent_child": "Are parent_section_id and child_sections structurally coherent?",
    "5.4-page_start_end": "Does the section content actually start and end on the declared pages?",
    "5.4-hierarchy_path": "Does hierarchy_path reflect the real path from the root?",
    "5.4-gaps_duplicates": "Does the section appear exactly once, without gaps or duplicates?",
    "5.4-flagged_for_review": "When flagged, is the inferred boundary or title actually correct?",
    "5.4-structural_source": "When inferred, does extra visual scrutiny confirm the structure?",
    "5.6-numbering_scheme": "Is the numbering scheme correct at this section boundary?",
    "5.6-offset_applied": (
        "Is the applied page offset plausible compared with neighboring sections?"
    ),
    "5.6-table_content": "Does every table node contain the real grid content?",
    "5.5-filters_discarding": (
        "Are all relevant diagrams or screenshots present, including when none were extracted?"
    ),
    "5.5-filters_passing_noise": (
        "Are logos, rules, or decorative icons excluded from extracted images?"
    ),
    "5.5-image_section_mapping": (
        "Do visible/extracted images belong to the correct deepest section?"
    ),
    "5.6-sanity_report": "If the pipeline aborted, is the cause recorded in the sanity report?",
}

SECTION_ALWAYS = (
    *(ref for ref in CHECKLIST if ref.startswith("5.4-")),
    "5.6-numbering_scheme",
    "5.6-offset_applied",
)
VISUAL_ALWAYS = (
    "5.5-filters_discarding",
    "5.5-filters_passing_noise",
    "5.5-image_section_mapping",
)


@dataclass(frozen=True)
class FindingRow:
    manual_id: str
    section_id: str
    page_sampled: str
    checklist_ref: str
    result: str = ""
    severity: str = ""
    evidence: str = ""
    notes: str = ""

    @property
    def stable_key(self) -> str:
        return stable_finding_key(asdict(self))


def stable_finding_key(row: dict[str, Any]) -> str:
    return "|".join(
        str(row.get(field, ""))
        for field in ("manual_id", "section_id", "page_sampled", "checklist_ref")
    )


def _has_table(section: dict[str, Any]) -> bool:
    return any(node.get("node_type") == "table" for node in section.get("semantic_nodes", []))


def section_checklist_rows(
    manual_id: str, section: dict[str, Any], page: int
) -> list[FindingRow]:
    """Checklist rows for one sampled (section, page) pair."""
    refs = list(SECTION_ALWAYS)
    if _has_table(section):
        refs.append("5.6-table_content")
    refs.extend(VISUAL_ALWAYS)
    return [FindingRow(manual_id, section["section_id"], str(page), ref) for ref in refs]


def generate_findings_template(
    manual_id: str,
    sections: list[dict[str, Any]],
    sample: SampleResult,
) -> list[FindingRow]:
    by_id = {section["section_id"]: section for section in sections}
    rows = []
    for section_id in sample.distinct_sections:
        rows.extend(
            section_checklist_rows(manual_id, by_id[section_id], sample.section_pages[section_id])
        )
    rows.append(FindingRow(manual_id, "DOCUMENT-LEVEL", "", "5.6-sanity_report"))
    return rows


def findings_csv_text(rows: list[FindingRow] | list[dict[str, Any]]) -> str:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=QA_COLUMNS, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        payload = asdict(row) if isinstance(row, FindingRow) else row
        writer.writerow({field: payload.get(field, "") for field in QA_COLUMNS})
    return output.getvalue()


def write_findings_template(path: Path, rows: list[FindingRow]) -> None:
    if path.exists():
        raise FileExistsError(f"Findings file already exists: {path}")
    atomic_write_text(path, findings_csv_text(rows))


def checklist_reference_markdown(manual_id: str, refs: set[str] | None = None) -> str:
    selected = refs or set(CHECKLIST)
    lines = [
        f"# Checklist reference — `{manual_id}`",
        "",
        "| checklist_ref | Plain-language question |",
        "|---|---|",
    ]
    lines.extend(f"| `{ref}` | {CHECKLIST[ref]} |" for ref in CHECKLIST if ref in selected)
    return "\n".join(lines) + "\n"
