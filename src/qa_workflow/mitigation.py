"""Mitigation versions (``v2.1``, ``v2.2``, ...): re-run a manual after a bug fix and check it.

A mitigation version keeps the official deterministic 15 % sample of the new tree, plus
check rows so the result can be compared with its base version:

- ``base-pair``: every (section, page) the base version reviewed, so each row has a pair;
- ``bug-occurrence``: the (section, page) pairs where the target bugs were seen;
- ``random-check``: a few extra random pages (seeded by manual and version) to catch
  regressions elsewhere.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .findings import (
    FindingRow,
    checklist_reference_markdown,
    generate_findings_template,
    section_checklist_rows,
    write_findings_template,
)
from .models import QAVersion
from .sampling import (
    SampleResult,
    deepest_section_for_page,
    generate_sample,
    render_sample_markdown,
)
from .storage import (
    atomic_write_text,
    create_qa_version,
    is_version_name,
    open_qa_version,
    utc_now,
    write_pipeline_artifacts,
)

MITIGATION_REASONS = frozenset({"base-pair", "bug-occurrence", "random-check"})
MITIGATION_HEADING = "## Mitigation check rows"


@dataclass(frozen=True)
class CheckRow:
    page: int
    section_id: str
    title: str
    hierarchy_path: str
    page_range: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MitigationSample:
    sample: SampleResult
    check_rows: tuple[CheckRow, ...]


@dataclass(frozen=True)
class PipelineInfo:
    commit: str
    subject: str
    dirty: bool


def validate_mitigation_name(base_version: str, version: str) -> None:
    major = base_version.split(".")[0]
    valid = is_version_name(base_version) and is_version_name(version)
    if not valid or not version.startswith(f"{major}.") or version == base_version:
        raise ValueError(
            f"Mitigation version must be {major}.N (e.g. {major}.1); got {version!r} "
            f"for base {base_version!r}"
        )


def _check_row(section: dict[str, Any], page: int, reasons: set[str]) -> CheckRow:
    start = section.get("page_start")
    end = section.get("page_end") or start
    return CheckRow(
        page,
        section["section_id"],
        str(section.get("title", section["section_id"])),
        str(section.get("hierarchy_path", "")),
        f"{start}-{end}",
        tuple(sorted(reasons)),
    )


def plan_mitigation_sample(
    sections: list[dict[str, Any]],
    total_pages: int,
    base_pairs: set[tuple[str, int]],
    occurrence_pairs: set[tuple[str, int]],
    *,
    extra_pages: int,
    seed: str,
) -> MitigationSample:
    """Official sample of the new tree plus paired, occurrence and random check rows.

    Pairs are ``(section_id, page)``. A pair already in the official sample is not repeated.
    A base section that no longer exists is re-mapped to the deepest section on its page.
    """
    sample = generate_sample(sections, total_pages)
    by_id = {section["section_id"]: section for section in sections}
    official = {(section_id, page) for section_id, page in sample.section_pages.items()}
    reasons: dict[tuple[str, int], set[str]] = {}
    for pairs, reason in ((base_pairs, "base-pair"), (occurrence_pairs, "bug-occurrence")):
        for section_id, page in pairs:
            section = by_id.get(section_id) or deepest_section_for_page(sections, page)
            if section is None:
                continue
            reasons.setdefault((section["section_id"], page), set()).add(reason)
    used_pages = {page for _section_id, page in official | set(reasons)}
    candidates = [page for page in range(1, total_pages + 1) if page not in used_pages]
    for page in sorted(random.Random(seed).sample(candidates, min(extra_pages, len(candidates)))):
        section = deepest_section_for_page(sections, page)
        if section is not None:
            reasons.setdefault((section["section_id"], page), set()).add("random-check")
    check_rows = tuple(
        _check_row(by_id[section_id], page, pair_reasons)
        for (section_id, page), pair_reasons in sorted(
            reasons.items(), key=lambda item: (item[0][1], item[0][0])
        )
        if (section_id, page) not in official
    )
    return MitigationSample(sample, check_rows)


def render_mitigation_markdown(
    manual_id: str, plan: MitigationSample, base_version: str, targets: list[str]
) -> str:
    lines = [
        render_sample_markdown(manual_id, plan.sample).rstrip("\n"),
        "",
        MITIGATION_HEADING,
        "",
        f"Mitigation of {', '.join(targets)} against base `{base_version}`. These rows are "
        "added to the official sample so the result can be compared with the base version.",
        "",
        "| Page | Section | Hierarchy path | Range | Reason |",
        "|---:|---|---|---|---|",
    ]
    for row in plan.check_rows:
        lines.append(
            f"| {row.page} | {row.title} (`{row.section_id}`) | {row.hierarchy_path} "
            f"| {row.page_range} | {'; '.join(row.reasons)} |"
        )
    return "\n".join(lines) + "\n"


def mitigation_findings_template(
    manual_id: str, sections: list[dict[str, Any]], plan: MitigationSample
) -> list[FindingRow]:
    rows = generate_findings_template(manual_id, sections, plan.sample)
    seen = {row.stable_key for row in rows}
    by_id = {section["section_id"]: section for section in sections}
    for check in plan.check_rows:
        for row in section_checklist_rows(manual_id, by_id[check.section_id], check.page):
            if row.stable_key not in seen:
                seen.add(row.stable_key)
                rows.append(row)
    return rows


def reviewed_pairs(findings_csv: Path) -> set[tuple[str, int]]:
    """(section_id, page) pairs listed in a findings log (reviewed or not)."""
    if not findings_csv.exists():
        return set()
    with findings_csv.open(encoding="utf-8", newline="") as handle:
        return {
            (row["section_id"], int(row["page_sampled"]))
            for row in csv.DictReader(handle)
            if str(row.get("page_sampled", "")).isdigit()
        }


def create_mitigation_version(
    qa_root: Path,
    manual_id: str,
    base_version: str,
    version: str,
    *,
    targets: list[str],
    pipeline: PipelineInfo,
    sections: list[dict[str, Any]],
    total_pages: int,
    images: Any,
    bookmarks: Any,
    validation_report: dict[str, Any],
    run_log: str,
    occurrence_pairs: set[tuple[str, int]],
    extra_pages: int = 5,
    reviewer: str | None = None,
) -> tuple[QAVersion, MitigationSample, int]:
    """Create ``version`` from a fresh pipeline run; never touches the base version."""
    validate_mitigation_name(base_version, version)
    if not targets:
        raise ValueError("At least one target bug id is required")
    base = open_qa_version(qa_root, manual_id, base_version)
    source_pdf = base.source_manifest.get("path")
    if not source_pdf:
        raise ValueError(f"Base version {base_version} has no recorded source PDF")
    mitigation = {
        "base_version": base_version,
        "targets": sorted(targets),
        "pipeline_commit": pipeline.commit,
        "pipeline_subject": pipeline.subject,
        "pipeline_dirty": pipeline.dirty,
        "created_at": utc_now(),
    }
    qa_version = create_qa_version(
        qa_root,
        manual_id,
        version,
        Path(source_pdf),
        reviewer or str(base.version_manifest.get("reviewer", "")),
        mitigation=mitigation,
    )
    write_pipeline_artifacts(
        qa_version,
        tree=sections,
        images=images,
        bookmarks=bookmarks,
        validation_report=validation_report,
        run_log=run_log,
    )
    plan = plan_mitigation_sample(
        sections,
        total_pages,
        reviewed_pairs(base.findings_csv),
        occurrence_pairs,
        extra_pages=extra_pages,
        seed=f"{manual_id}:{version}",
    )
    atomic_write_text(
        qa_version.root / "sampling" / "sample_selection.md",
        render_mitigation_markdown(manual_id, plan, base_version, sorted(targets)),
    )
    rows = mitigation_findings_template(manual_id, sections, plan)
    write_findings_template(qa_version.findings_csv, rows)
    atomic_write_text(
        qa_version.root / "findings" / "checklist_reference.md",
        checklist_reference_markdown(manual_id),
    )
    atomic_write_text(
        qa_version.root / "summary.md",
        f"# QA summary — `{manual_id}` `{version}`\n\n"
        f"Status: in_review\n\nMitigation of {', '.join(sorted(targets))} against "
        f"`{base_version}` (pipeline commit `{pipeline.commit[:7]}`: {pipeline.subject}).\n\n"
        f"Official sample: {plan.sample.quota} quota pages; check rows: "
        f"{len(plan.check_rows)}; {len(rows)} findings.\n",
    )
    return qa_version, plan, len(rows)
