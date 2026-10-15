"""Task 2.3 root-cause consolidation driven by a curated, human-edited catalogue.

The catalogue (``qa/confidence_index/root_causes.json``) is read-only for code: the
Streamlit app and the scripts derive ``consolidated_bugs.csv`` from it and never write it.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATALOGUE_FILENAME = "root_causes.json"
SEVERITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
# Notes written with the A2-B1 rule cite the cause as "Cause: BUG-019".
_BUG_ID = re.compile(r"\bBUG-\d{3}\b")


@dataclass(frozen=True)
class RootCause:
    bug_id: str
    title: str
    suspected_module: str


@dataclass(frozen=True)
class MatchRule:
    bug_id: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class RootCauseCatalogue:
    bugs: dict[str, RootCause]
    rules: tuple[MatchRule, ...]
    overrides: dict[tuple[str, str, str], str]
    exclusions: dict[tuple[str, str, str], str]
    # 'manual|section|page|checklist_ref': one sampled page, when the rows of a section
    # differ in cause (Philips sec_0820: p443 lost row BUG-030, p442 split cells BUG-008).
    page_overrides: dict[tuple[str, str, str, str], str] = field(default_factory=dict)


@dataclass(frozen=True)
class Consolidation:
    bugs: tuple[dict[str, str], ...]
    assignments: tuple[dict[str, str], ...]
    excluded: tuple[dict[str, str], ...]


EMPTY_CATALOGUE = RootCauseCatalogue({}, (), {}, {})


def _row_key(key: str) -> tuple[str, str, str]:
    parts = key.split("|")
    if len(parts) != 3:
        raise ValueError(f"Catalogue key must be 'manual|section|checklist_ref': {key!r}")
    return parts[0], parts[1], parts[2]


def _page_key(key: str) -> tuple[str, str, str, str]:
    manual, section, page, ref = key.split("|")
    return manual, section, page, ref


def parse_catalogue(payload: dict[str, Any]) -> RootCauseCatalogue:
    bugs = {
        item["bug_id"]: RootCause(item["bug_id"], item["title"], item.get("suspected_module", ""))
        for item in payload.get("bugs", [])
    }
    rules = tuple(
        MatchRule(
            rule["bug_id"],
            re.compile(rule["regex"], re.IGNORECASE if rule.get("ignore_case", True) else 0),
        )
        for rule in payload.get("rules", [])
    )
    raw_overrides = payload.get("overrides", {})
    overrides = {
        _row_key(key): value for key, value in raw_overrides.items() if key.count("|") != 3
    }
    page_overrides = {
        _page_key(key): value for key, value in raw_overrides.items() if key.count("|") == 3
    }
    exclusions = {_row_key(key): value for key, value in payload.get("exclusions", {}).items()}
    referenced = (
        {rule.bug_id for rule in rules} | set(overrides.values()) | set(page_overrides.values())
    )
    unknown = sorted(referenced - set(bugs))
    if unknown:
        raise ValueError(f"Catalogue references undefined bug ids: {', '.join(unknown)}")
    return RootCauseCatalogue(bugs, rules, overrides, exclusions, page_overrides)


def load_catalogue(path: Path) -> RootCauseCatalogue:
    if not path.exists():
        return EMPTY_CATALOGUE
    return parse_catalogue(json.loads(path.read_text(encoding="utf-8")))


def classify(catalogue: RootCauseCatalogue, manual_id: str, row: dict[str, str]) -> str | None:
    """Override (page, then section), then the ordered rules, then the first BUG-NNN in notes."""
    key = (manual_id, row.get("section_id", ""), row.get("checklist_ref", ""))
    page_key = (key[0], key[1], str(row.get("page_sampled", "")), key[2])
    if page_key in catalogue.page_overrides:
        return catalogue.page_overrides[page_key]
    if key in catalogue.overrides:
        return catalogue.overrides[key]
    text = f"{row.get('notes', '')} {row.get('evidence', '')}".strip()
    for rule in catalogue.rules:
        if rule.pattern.search(text):
            return rule.bug_id
    for bug_id in _BUG_ID.findall(row.get("notes", "")):
        if bug_id in catalogue.bugs:
            return bug_id
    return None


def _top_severity(severities: list[str]) -> str:
    return sorted(severities, key=lambda value: SEVERITY_RANK.get(value, 99))[0]


def _sections_cell(sections: set[str]) -> str:
    return f"{len(sections)} sections: " + ", ".join(sorted(sections))


def consolidate(
    catalogue: RootCauseCatalogue,
    fail_rows: dict[str, list[dict[str, str]]],
    normalize: Callable[[str], str] = str.strip,
) -> Consolidation:
    """Group FAIL rows by root cause; every row lands in exactly one entry or is excluded.

    ``fail_rows`` maps manual id to its FAIL rows; ``normalize`` maps raw severity labels
    to the English Sprint scale.
    """
    groups: dict[str, dict[str, Any]] = {}
    triage: dict[tuple[str, str], dict[str, Any]] = {}
    assignments: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for manual_id, rows in sorted(fail_rows.items()):
        for row in rows:
            key = (manual_id, row.get("section_id", ""), row.get("checklist_ref", ""))
            if key in catalogue.exclusions:
                excluded.append(
                    {**row, "manual_id": manual_id, "reason": catalogue.exclusions[key]}
                )
                continue
            severity = normalize(row.get("severity", ""))
            bug_id = classify(catalogue, manual_id, row)
            if bug_id is None:
                group = triage.setdefault(
                    (manual_id, key[2]), {"severities": [], "sections": set(), "rows": []}
                )
            else:
                group = groups.setdefault(
                    bug_id, {"severities": [], "manuals": set(), "sections": set(), "rows": []}
                )
                group["manuals"].add(manual_id)
            group["severities"].append(severity)
            group["sections"].add(f"{manual_id}:{key[1]}")
            group["rows"].append((manual_id, row, severity))
    bugs: list[dict[str, str]] = []
    for bug_id in sorted(groups):
        group = groups[bug_id]
        cause = catalogue.bugs[bug_id]
        severity = _top_severity(group["severities"])
        bugs.append(
            {
                "bug_id": bug_id,
                "title": cause.title,
                "severity": severity,
                "manuals_affected": "; ".join(sorted(group["manuals"])),
                "sections_affected": _sections_cell(group["sections"]),
                "suspected_module": cause.suspected_module,
                "escalate": "Yes" if severity in {"Critical", "High"} else "No",
            }
        )
        assignments.extend(_assignments(bug_id, group["rows"]))
    for index, ((manual_id, checklist_ref), group) in enumerate(sorted(triage.items()), 1):
        bug_id = f"TRIAGE-{index:03d}"
        severity = _top_severity(group["severities"])
        bugs.append(
            {
                "bug_id": bug_id,
                "title": f"[needs manual root-cause review] {checklist_ref} FAILs in {manual_id}",
                "severity": severity,
                "manuals_affected": manual_id,
                "sections_affected": _sections_cell(group["sections"]),
                "suspected_module": "",
                "escalate": "Yes" if severity in {"Critical", "High"} else "No",
            }
        )
        assignments.extend(_assignments(bug_id, group["rows"]))
    return Consolidation(tuple(bugs), tuple(assignments), tuple(excluded))


def _assignments(bug_id: str, rows: list[tuple[str, dict[str, str], str]]) -> list[dict[str, str]]:
    return [
        {
            "bug_id": bug_id,
            "manual_id": manual_id,
            "section_id": row.get("section_id", ""),
            "page_sampled": row.get("page_sampled", ""),
            "checklist_ref": row.get("checklist_ref", ""),
            "severity": severity,
        }
        for manual_id, row, severity in rows
    ]


def load_version_rows(version_dir: Path, include_drafts: bool) -> list[dict[str, str]]:
    """Rows of one QA version; each carries ``_source`` = ``official`` or ``draft:<batch>``.

    With ``include_drafts``, rows not yet reviewed in ``findings_log.csv`` are filled from the
    validated agent drafts (later batches override earlier ones, as in page 7).
    """
    findings = version_dir / "findings" / "findings_log.csv"
    rows: list[dict[str, str]] = []
    if findings.exists():
        with findings.open(encoding="utf-8", newline="") as handle:
            rows = [{**row, "_source": "official"} for row in csv.DictReader(handle)]
    if not include_drafts:
        return rows
    drafts: dict[tuple[str, str, str], dict[str, str]] = {}
    for path in sorted((version_dir / "agent_exchange").glob("*/validated_draft.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("findings", []):
            row = {key: str(value) for key, value in item.items()}
            row["_source"] = f"draft:{path.parent.name}"
            drafts[(row["section_id"], row["page_sampled"], row["checklist_ref"])] = row
    merged = []
    for row in rows:
        key = (row["section_id"], row["page_sampled"], row["checklist_ref"])
        merged.append(row if row.get("result", "").strip() else drafts.get(key, row))
    return merged
