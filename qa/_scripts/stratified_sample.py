#!/usr/bin/env python3
"""
Stratified page/section sampler for pdf-tree manual QA.

Implements SPRINT_TASKS_QA.md Task 1.3:
  1. List top-level (chapter) sections and their page ranges.
  2. Distribute the 15%-of-pages quota proportionally by each chapter's
     share of total_pages.
  3. Within each chapter, sample pages at even intervals (not clustered).
  4. Add mandatory extras on top of the quota (not counted against it):
       - every section with flagged_for_review: true
       - every section with structural_source: "inferred"
       - the first and last content section of the document

Deterministic — same tree.json + same total_pages always produces the same
sample, so a second engineer can re-run and get an identical list.

Usage:
    python3 stratified_sample.py <tree.json> --manual-id ID --total-pages N \
        [--fraction 0.15] [--out sample_selection.md]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def largest_remainder_allocate(weights: list[float], quota: int) -> list[int]:
    """Integer-allocate `quota` across `weights` (proportions), summing exactly to quota."""
    raw = [w * quota for w in weights]
    floors = [math.floor(x) for x in raw]
    remainder = quota - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
    alloc = floors[:]
    for i in order[:remainder]:
        alloc[i] += 1
    return alloc


def even_interval_pages(start: int, end: int, count: int) -> list[int]:
    """Pick `count` pages spread evenly across [start, end], not clustered."""
    if count <= 0:
        return []
    if count == 1 or end <= start:
        return [start]
    step = (end - start) / (count - 1)
    pages = sorted({round(start + i * step) for i in range(count)})
    return [max(start, min(end, p)) for p in pages]


def deepest_section_for_page(sections: list[dict[str, Any]], page: int) -> dict[str, Any] | None:
    """The most specific (highest hierarchy_level) section whose page range contains `page`."""
    candidates = [
        s for s in sections
        if s.get("page_start") is not None
        and s["page_start"] <= page <= (s.get("page_end") or s["page_start"])
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.get("hierarchy_level", 0))


def build_sample(
    sections: list[dict[str, Any]], total_pages: int, fraction: float
) -> dict[str, Any]:
    quota = math.ceil(total_pages * fraction)

    chapters = [
        s for s in sections
        if s.get("hierarchy_level") == 1 and s.get("page_start") is not None
    ]
    chapters.sort(key=lambda s: s["page_start"])

    weights = [((c.get("page_end") or c["page_start"]) - c["page_start"] + 1) for c in chapters]
    total_w = sum(weights) or 1
    norm_weights = [w / total_w for w in weights]
    allocations = largest_remainder_allocate(norm_weights, quota)

    quota_pages: dict[int, set[str]] = {}
    chapter_rows = []
    for chapter, weight, alloc in zip(chapters, weights, allocations, strict=True):
        c_start, c_end = chapter["page_start"], chapter.get("page_end") or chapter["page_start"]
        pages = even_interval_pages(c_start, c_end, alloc)
        for p in pages:
            quota_pages.setdefault(p, set()).add(f"quota:{chapter['section_id']}")
        chapter_rows.append({
            "section_id": chapter["section_id"],
            "title": chapter["title"],
            "page_start": c_start,
            "page_end": c_end,
            "pages_in_chapter": weight,
            "share": weight / total_w,
            "allocated": alloc,
            "sampled_pages": pages,
        })

    mandatory: dict[int, set[str]] = {}
    for s in sections:
        p = s.get("page_start")
        if p is None:
            continue
        if s.get("flagged_for_review"):
            mandatory.setdefault(p, set()).add(f"flagged_for_review:{s['section_id']}")
        if s.get("structural_source") == "inferred":
            mandatory.setdefault(p, set()).add(f"inferred:{s['section_id']}")

    with_pages = [s for s in sections if s.get("page_start") is not None]
    first_sec = min(with_pages, key=lambda s: s["page_start"])
    last_sec = max(with_pages, key=lambda s: (s.get("page_end") or s["page_start"]))
    mandatory.setdefault(first_sec["page_start"], set()).add(
        f"first_section:{first_sec['section_id']}"
    )
    last_page = last_sec.get("page_end") or last_sec["page_start"]
    mandatory.setdefault(last_page, set()).add(f"last_section:{last_sec['section_id']}")

    all_pages: dict[int, set[str]] = {p: set(r) for p, r in quota_pages.items()}
    for p, reasons in mandatory.items():
        all_pages.setdefault(p, set()).update(reasons)

    rows = []
    for p in sorted(all_pages):
        sec = deepest_section_for_page(sections, p)
        reasons = sorted(all_pages[p])
        rows.append({
            "page": p,
            "section_id": sec["section_id"] if sec else None,
            "title": sec["title"] if sec else None,
            "hierarchy_path": sec.get("hierarchy_path") if sec else None,
            "page_range": f"{sec['page_start']}-{sec.get('page_end')}" if sec else None,
            "reasons": reasons,
        })

    distinct_sections = sorted({r["section_id"] for r in rows if r["section_id"]})

    return {
        "quota": quota,
        "chapters": chapter_rows,
        "rows": rows,
        "distinct_sections": distinct_sections,
        "mandatory_page_count": len(mandatory),
    }


def render_markdown(
    manual_id: str, total_pages: int, fraction: float, result: dict[str, Any]
) -> str:
    lines = []
    lines.append(f"# Sample selection — `{manual_id}` (Task 1.3)")
    lines.append("")
    lines.append(f"- `total_pages` = {total_pages}")
    lines.append(f"- quota = `ceil({total_pages} x {fraction})` = **{result['quota']} pages**")
    lines.append(
        f"- mandatory additions (not counted against quota): "
        f"**{result['mandatory_page_count']} extra pages**"
    )
    lines.append(f"- distinct sections touched: **{len(result['distinct_sections'])}**")
    lines.append("")
    lines.append("## Step 1-2 - per-chapter quota allocation")
    lines.append("")
    lines.append("| Chapter | Pages | Share | Sampled pages | Sampled page list |")
    lines.append("|---|---|---|---|---|")
    for c in result["chapters"]:
        lines.append(
            f"| {c['title']} (`{c['section_id']}`, p{c['page_start']}-{c['page_end']}) "
            f"| {c['pages_in_chapter']} | {c['share']:.1%} | {c['allocated']} "
            f"| {', '.join(str(p) for p in c['sampled_pages']) or '-'} |"
        )
    lines.append("")
    lines.append("## Step 3-4 - final sampled page list (quota + mandatory)")
    lines.append("")
    lines.append("| Page | Section | Hierarchy path | Section page range | Reason |")
    lines.append("|---|---|---|---|---|")
    for r in result["rows"]:
        reason_str = "; ".join(r["reasons"])
        lines.append(
            f"| {r['page']} | {r['title']} (`{r['section_id']}`) | {r['hierarchy_path']} "
            f"| {r['page_range']} | {reason_str} |"
        )
    lines.append("")
    lines.append(
        f"## Distinct sections to inspect in Task 1.4 "
        f"({len(result['distinct_sections'])})"
    )
    lines.append("")
    for sid in result["distinct_sections"]:
        lines.append(f"- `{sid}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tree_json", type=Path)
    ap.add_argument("--manual-id", required=True)
    ap.add_argument("--total-pages", type=int, required=True)
    ap.add_argument("--fraction", type=float, default=0.15)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    sections = json.loads(args.tree_json.read_text())
    result = build_sample(sections, args.total_pages, args.fraction)
    md = render_markdown(args.manual_id, args.total_pages, args.fraction, result)

    if args.out:
        args.out.write_text(md)
        n_rows = len(result["rows"])
        n_secs = len(result["distinct_sections"])
        print(f"Written: {args.out} ({n_rows} sampled pages, {n_secs} sections)")
    else:
        print(md)


if __name__ == "__main__":
    main()
