"""Compare a mitigation version with its base: bug counts, index, row changes, tree diff."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .confidence import ConfidenceScore, calculate_confidence, normalize_severity
from .root_causes import RootCauseCatalogue, classify, load_version_rows
from .storage import open_qa_version, version_label

TREE_FIELDS = ("title", "page_start", "page_end", "parent_section_id", "node_count")


@dataclass(frozen=True)
class BugDelta:
    bug_id: str
    title: str
    targeted: bool
    base_paired: int
    candidate_paired: int
    base_total: int
    candidate_total: int

    @property
    def change(self) -> int:
        return self.candidate_paired - self.base_paired


@dataclass(frozen=True)
class RowChange:
    section_id: str
    page_sampled: str
    checklist_ref: str
    base_result: str
    candidate_result: str
    base_bug: str
    candidate_bug: str
    candidate_evidence: str

    @property
    def kind(self) -> str:
        if self.base_result == "FAIL" and self.candidate_result == "PASS":
            return "improved"
        if self.base_result == "PASS" and self.candidate_result == "FAIL":
            return "regression"
        return "changed"


@dataclass(frozen=True)
class SectionChange:
    section_id: str
    field: str
    base_value: str
    candidate_value: str


@dataclass(frozen=True)
class VersionComparison:
    manual_id: str
    base_version: str
    candidate_version: str
    candidate_label: str
    targets: tuple[str, ...]
    pipeline_commit: str
    pipeline_subject: str
    candidate_reviewed: int
    candidate_rows: int
    paired_rows: int
    base_score: ConfidenceScore
    candidate_score: ConfidenceScore
    bugs: tuple[BugDelta, ...]
    row_changes: tuple[RowChange, ...]
    tree_changes: tuple[SectionChange, ...] | None

    @property
    def target_deltas(self) -> tuple[BugDelta, ...]:
        return tuple(bug for bug in self.bugs if bug.targeted)


def _key(row: dict[str, str]) -> tuple[str, str, str]:
    return row.get("section_id", ""), str(row.get("page_sampled", "")), row.get("checklist_ref", "")


def _bug_of(catalogue: RootCauseCatalogue, manual_id: str, row: dict[str, str]) -> str:
    if row.get("result", "").upper() != "FAIL":
        return ""
    return classify(catalogue, manual_id, row) or "TRIAGE"


def _load_tree(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else None


def tree_changes(
    base: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> tuple[SectionChange, ...]:
    """Field-level differences per section id (added and removed sections included)."""
    base_by_id = {section["section_id"]: section for section in base}
    candidate_by_id = {section["section_id"]: section for section in candidate}
    changes = []
    for section_id in sorted(base_by_id.keys() | candidate_by_id.keys()):
        old = base_by_id.get(section_id)
        new = candidate_by_id.get(section_id)
        if old is None or new is None:
            changes.append(
                SectionChange(
                    section_id,
                    "section",
                    "absent" if old is None else "present",
                    "absent" if new is None else "present",
                )
            )
            continue
        for field in TREE_FIELDS:
            if old.get(field) != new.get(field):
                changes.append(
                    SectionChange(section_id, field, str(old.get(field)), str(new.get(field)))
                )
    return tuple(changes)


def compare_versions(
    qa_root: Path,
    manual_id: str,
    base_version: str,
    candidate_version: str,
    catalogue: RootCauseCatalogue,
    *,
    include_drafts: bool = True,
) -> VersionComparison:
    """Paired counts and both scores use only rows reviewed in both versions (same section,
    page, check), so a partial re-review is compared with the same rows of the base."""
    base = open_qa_version(qa_root, manual_id, base_version)
    candidate = open_qa_version(qa_root, manual_id, candidate_version)
    mitigation = candidate.version_manifest.get("mitigation") or {}
    targets = tuple(mitigation.get("targets") or ())
    base_rows = load_version_rows(base.root, include_drafts)
    candidate_rows = load_version_rows(candidate.root, include_drafts)

    def reviewed(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], dict[str, str]]:
        return {_key(row): row for row in rows if row.get("result", "").upper() in {"PASS", "FAIL"}}

    base_reviewed = reviewed(base_rows)
    candidate_reviewed = reviewed(candidate_rows)
    paired = base_reviewed.keys() & candidate_reviewed.keys()

    counts: dict[str, list[int]] = {}
    for rows, offset in ((base_reviewed, 0), (candidate_reviewed, 1)):
        for key, row in rows.items():
            bug_id = _bug_of(catalogue, manual_id, row)
            if not bug_id:
                continue
            bucket = counts.setdefault(bug_id, [0, 0, 0, 0])
            bucket[2 + offset] += 1
            if key in paired:
                bucket[offset] += 1
    for bug_id in targets:
        counts.setdefault(bug_id, [0, 0, 0, 0])
    bugs = tuple(
        BugDelta(
            bug_id,
            catalogue.bugs[bug_id].title if bug_id in catalogue.bugs else "Unclassified FAIL",
            bug_id in targets,
            values[0],
            values[1],
            values[2],
            values[3],
        )
        for bug_id, values in sorted(
            counts.items(), key=lambda item: (item[0] not in targets, item[0])
        )
    )

    changes = []
    for key in sorted(paired):
        old, new = base_reviewed[key], candidate_reviewed[key]
        old_bug, new_bug = (
            _bug_of(catalogue, manual_id, old),
            _bug_of(catalogue, manual_id, new),
        )
        old_result, new_result = old["result"].upper(), new["result"].upper()
        if old_result != new_result or old_bug != new_bug:
            changes.append(
                RowChange(*key, old_result, new_result, old_bug, new_bug, new.get("evidence", ""))
            )

    def score(version: str, rows: dict[tuple[str, str, str], dict[str, str]]) -> ConfidenceScore:
        qa_version = base if version == base_version else candidate
        validation = (
            json.loads(qa_version.validation_path.read_text(encoding="utf-8"))
            if qa_version.validation_path.exists()
            else None
        )
        normalized = [
            {**row, "severity": normalize_severity(row.get("severity", ""))}
            for row in rows.values()
        ]
        return calculate_confidence(manual_id, version, normalized, validation)

    base_tree = _load_tree(base.tree_path)
    candidate_tree = _load_tree(candidate.tree_path)
    return VersionComparison(
        manual_id,
        base_version,
        candidate_version,
        version_label(candidate_version, candidate.version_manifest),
        targets,
        str(mitigation.get("pipeline_commit", "")),
        str(mitigation.get("pipeline_subject", "")),
        len(candidate_reviewed),
        len(candidate_rows),
        len(paired),
        score(base_version, {key: base_reviewed[key] for key in paired}),
        score(candidate_version, {key: candidate_reviewed[key] for key in paired}),
        bugs,
        tuple(changes),
        tree_changes(base_tree, candidate_tree)
        if base_tree is not None and candidate_tree is not None
        else None,
    )
