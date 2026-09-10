"""Deterministic stratified sampling for manual QA."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SampleRow:
    page: int
    section_id: str
    title: str
    hierarchy_path: str
    page_range: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ChapterAllocation:
    section_id: str
    title: str
    page_start: int
    page_end: int
    pages_in_chapter: int
    share: float
    allocated: int
    sampled_pages: tuple[int, ...]


@dataclass(frozen=True)
class SampleResult:
    total_pages: int
    fraction: float
    quota: int
    quota_pages: tuple[int, ...]
    mandatory_extra_pages: tuple[int, ...]
    chapters: tuple[ChapterAllocation, ...]
    rows: tuple[SampleRow, ...]
    distinct_sections: tuple[str, ...]
    section_pages: dict[str, int]

    @property
    def mandatory_page_count(self) -> int:
        return len(self.mandatory_extra_pages)


def largest_remainder_allocate(weights: list[float], quota: int) -> list[int]:
    if quota < 0:
        raise ValueError("quota cannot be negative")
    if not weights:
        return []
    total = sum(max(weight, 0) for weight in weights)
    if total == 0:
        weights = [1.0] * len(weights)
        total = float(len(weights))
    raw = [max(weight, 0) / total * quota for weight in weights]
    floors = [math.floor(value) for value in raw]
    remainder = quota - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - floors[i], -i), reverse=True)
    allocation = floors[:]
    for index in order[:remainder]:
        allocation[index] += 1
    return allocation


def even_interval_pages(start: int, end: int, count: int) -> list[int]:
    if count <= 0 or end < start:
        return []
    count = min(count, end - start + 1)
    if count == 1:
        return [start]
    pages = []
    for index in range(count):
        position = start + (end - start) * index / (count - 1)
        candidate = round(position)
        if pages and candidate <= pages[-1]:
            candidate = pages[-1] + 1
        pages.append(min(candidate, end))
    return pages


def deepest_section_for_page(sections: list[dict[str, Any]], page: int) -> dict[str, Any] | None:
    candidates = [
        section
        for section in sections
        if isinstance(section.get("page_start"), int)
        and section["page_start"] <= page <= (section.get("page_end") or section["page_start"])
    ]
    return (
        max(candidates, key=lambda section: section.get("hierarchy_level", 0))
        if candidates
        else None
    )


def _chapter_ranges(sections: list[dict[str, Any]], total_pages: int) -> list[dict[str, Any]]:
    chapters = [
        section
        for section in sections
        if section.get("hierarchy_level") == 1 and isinstance(section.get("page_start"), int)
    ]
    chapters.sort(key=lambda section: (section["page_start"], section.get("section_id", "")))
    if chapters:
        return chapters
    with_pages = [section for section in sections if isinstance(section.get("page_start"), int)]
    if not with_pages:
        return []
    return [
        {
            "section_id": "DOCUMENT",
            "title": "Document",
            "page_start": max(1, min(section["page_start"] for section in with_pages)),
            "page_end": min(
                total_pages,
                max(section.get("page_end") or section["page_start"] for section in with_pages),
            ),
        }
    ]


def _allocate_with_capacity(capacities: list[int], quota: int) -> list[int]:
    allocation = largest_remainder_allocate([float(value) for value in capacities], quota)
    overflow = 0
    for index, capacity in enumerate(capacities):
        if allocation[index] > capacity:
            overflow += allocation[index] - capacity
            allocation[index] = capacity
    while overflow:
        candidates = [i for i, capacity in enumerate(capacities) if allocation[i] < capacity]
        if not candidates:
            break
        for index in candidates:
            if overflow == 0:
                break
            allocation[index] += 1
            overflow -= 1
    return allocation


def generate_sample(
    sections: list[dict[str, Any]], total_pages: int, fraction: float = 0.15
) -> SampleResult:
    if total_pages <= 0:
        raise ValueError("total_pages must be positive")
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be between 0 and 1")
    if not sections:
        raise ValueError("sections cannot be empty")
    quota = min(total_pages, math.ceil(total_pages * fraction))
    chapters = _chapter_ranges(sections, total_pages)
    capacities = [
        max(
            0,
            min(total_pages, chapter.get("page_end") or chapter["page_start"])
            - max(1, chapter["page_start"])
            + 1,
        )
        for chapter in chapters
    ]
    allocations = _allocate_with_capacity(capacities, min(quota, sum(capacities)))

    quota_reasons: dict[int, set[str]] = {}
    chapter_rows = []
    total_capacity = sum(capacities) or 1
    for chapter, capacity, allocated in zip(chapters, capacities, allocations, strict=True):
        start = max(1, chapter["page_start"])
        end = min(total_pages, chapter.get("page_end") or start)
        pages = even_interval_pages(start, end, allocated)
        for page in pages:
            quota_reasons.setdefault(page, set()).add(f"quota:{chapter['section_id']}")
        chapter_rows.append(
            ChapterAllocation(
                str(chapter["section_id"]),
                str(chapter.get("title", chapter["section_id"])),
                start,
                end,
                capacity,
                capacity / total_capacity,
                allocated,
                tuple(pages),
            )
        )

    if len(quota_reasons) < quota:
        for page in even_interval_pages(1, total_pages, quota):
            quota_reasons.setdefault(page, set()).add("quota:document-fill")
    if len(quota_reasons) < quota:
        for page in range(1, total_pages + 1):
            quota_reasons.setdefault(page, set()).add("quota:document-fill")
            if len(quota_reasons) == quota:
                break
    if len(quota_reasons) > quota:
        keep = set(even_interval_pages(1, len(quota_reasons), quota))
        ordered = sorted(quota_reasons)
        quota_reasons = {
            page: quota_reasons[page] for i, page in enumerate(ordered, 1) if i in keep
        }

    targeted: list[tuple[int, str, str]] = []
    with_pages = [section for section in sections if isinstance(section.get("page_start"), int)]
    if not with_pages:
        raise ValueError("at least one section must have a page_start")
    for section in with_pages:
        page = min(total_pages, max(1, section["page_start"]))
        if section.get("flagged_for_review"):
            targeted.append(
                (page, section["section_id"], f"flagged_for_review:{section['section_id']}")
            )
        if section.get("structural_source") == "inferred":
            targeted.append((page, section["section_id"], f"inferred:{section['section_id']}"))
    first = min(
        with_pages, key=lambda section: (section["page_start"], section.get("section_id", ""))
    )
    last = max(
        with_pages,
        key=lambda section: (
            section.get("page_end") or section["page_start"],
            section.get("section_id", ""),
        ),
    )
    targeted.append(
        (max(1, first["page_start"]), first["section_id"], f"first_section:{first['section_id']}")
    )
    targeted.append(
        (
            min(total_pages, last.get("page_end") or last["page_start"]),
            last["section_id"],
            f"last_section:{last['section_id']}",
        )
    )

    by_id = {section["section_id"]: section for section in sections}
    row_reasons: dict[tuple[int, str], set[str]] = {}
    section_pages: dict[str, int] = {}
    for page, reasons in quota_reasons.items():
        section = deepest_section_for_page(sections, page)
        if section:
            key = (page, section["section_id"])
            row_reasons.setdefault(key, set()).update(reasons)
            section_pages.setdefault(section["section_id"], page)
    for page, section_id, reason in targeted:
        row_reasons.setdefault((page, section_id), set()).add(reason)
        section_pages.setdefault(section_id, page)

    rows = []
    for (page, section_id), reasons in sorted(row_reasons.items()):
        section = by_id[section_id]
        start = section.get("page_start")
        end = section.get("page_end") or start
        rows.append(
            SampleRow(
                page,
                section_id,
                str(section.get("title", section_id)),
                str(section.get("hierarchy_path", "")),
                f"{start}-{end}",
                tuple(sorted(reasons)),
            )
        )
    quota_pages = tuple(sorted(quota_reasons))
    all_pages = {row.page for row in rows}
    mandatory_extra_pages = tuple(sorted(all_pages - set(quota_pages)))
    distinct = tuple(
        sorted(section_pages, key=lambda section_id: (section_pages[section_id], section_id))
    )
    return SampleResult(
        total_pages,
        fraction,
        quota,
        quota_pages,
        mandatory_extra_pages,
        tuple(chapter_rows),
        tuple(rows),
        distinct,
        section_pages,
    )


def render_sample_markdown(manual_id: str, result: SampleResult) -> str:
    lines = [
        f"# Sample selection — `{manual_id}`",
        "",
        f"- `total_pages` = {result.total_pages}",
        f"- quota = `ceil({result.total_pages} x {result.fraction})` = **{result.quota} pages**",
        f"- mandatory additions outside quota = **{result.mandatory_page_count} pages**",
        f"- distinct sections touched = **{len(result.distinct_sections)}**",
        "",
        "## Per-chapter quota allocation",
        "",
        "| Chapter | Pages | Share | Allocated | Sampled pages |",
        "|---|---:|---:|---:|---|",
    ]
    for chapter in result.chapters:
        lines.append(
            f"| {chapter.title} (`{chapter.section_id}`, p{chapter.page_start}-{chapter.page_end}) "
            f"| {chapter.pages_in_chapter} | {chapter.share:.1%} | {chapter.allocated} "
            f"| {', '.join(map(str, chapter.sampled_pages)) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Final sampled page and section list",
            "",
            "| Page | Section | Hierarchy path | Range | Reason |",
            "|---:|---|---|---|---|",
        ]
    )
    for row in result.rows:
        lines.append(
            f"| {row.page} | {row.title} (`{row.section_id}`) | {row.hierarchy_path} "
            f"| {row.page_range} | {'; '.join(row.reasons)} |"
        )
    lines.extend(["", "## Distinct sections to inspect", ""])
    lines.extend(f"- `{section_id}`" for section_id in result.distinct_sections)
    return "\n".join(lines) + "\n"
