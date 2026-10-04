#!/usr/bin/env python3
"""Check PDF Tree QA draft findings against deterministic signals.

Read-only. For every draft row, recompute what can be proven from the version's
artifacts (tree.json, images_v1.json and, when PyMuPDF is available, the source
PDF) and compare it with the proposed result and severity:

- CONTRADICTED  the artifacts show a defect but the row says PASS
- SEVERITY      the row is FAIL but its severity does not match the Sprint scale
                for the defect the artifacts show (see references/verification-contract.md)
- UNSUPPORTED   the row is FAIL on a checkable item but no deterministic signal backs it
                (it may still be right on visual grounds; it needs a human look)
- CONFIRMED     the artifacts agree with the row
- VISUAL-ONLY   nothing deterministic to compare (e.g. table fidelity, vector figures)

Run from the pdf_tree root, preferably with the project environment so PyMuPDF
is available:  uv run python pdf-tree-qa-verifier/scripts/verify_claims.py ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
FIGURE_CODE = re.compile(r"\b[A-Z0-9]{1,3}H\d{3,4}[A-Z]?\b")
SLUG = re.compile(r"ページ|午前|午後|\.fm\b")
INDEX_ENTRY = re.compile(r"\s\d{1,3}(,\s*\d{1,3})*\s*$")
INDEX_PAIR = re.compile(r"[A-Za-z\)]\s\d{1,3}(?:,\s?\d{1,3})*(?=\s|$)")
MIN_AREA_FRACTION = 0.02  # mirrors _MIN_AREA_FRAC in src/pipeline/pipeline.py
FIGURE_AREA_FRACTION = 0.01  # smaller dropped rasters are treated as icons


def top(n: dict[str, Any]) -> float:
    return max(n["bbox"]["y0"], n["bbox"]["y1"])


def norm(text: str) -> str:
    """Same normalization as section_matcher._normalize_heading."""
    text = re.sub(r"[^\w\s]", "", text.strip().lower())
    return " ".join(text.split())


@dataclass
class Signals:
    content_misplaced: list[str] = field(default_factory=list)  # Critical
    empty_body: bool = False  # Critical
    tables_misowned: list[str] = field(default_factory=list)  # Critical
    continues_next_page: list[str] = field(default_factory=list)  # Medium (page_end short)
    boilerplate_bleed: list[str] = field(default_factory=list)  # Low
    hierarchy: list[str] = field(default_factory=list)
    placeholder_tables: list[str] = field(default_factory=list)


@dataclass
class PageFacts:
    raster: int = 0
    kept: int = 0
    dropped_figures: list[str] = field(default_factory=list)
    dropped_icons: list[str] = field(default_factory=list)
    vector_suspect: bool = False
    mapped_elsewhere: list[str] = field(default_factory=list)
    misowned_images: list[str] = field(default_factory=list)
    available: bool = False


class Version:
    def __init__(self, root: Path, qa_root: Path, manual_id: str) -> None:
        self.root = root
        self.tree: list[dict[str, Any]] = json.loads((root / "exports/tree.json").read_text())
        images = json.loads((root / "exports/images_v1.json").read_text())
        self.images: list[dict[str, Any]] = (
            images.get("images", images) if isinstance(images, dict) else images
        )
        self.by_id = {s["section_id"]: s for s in self.tree}
        self.order = [s["section_id"] for s in self.tree]
        source = json.loads((qa_root / manual_id / "source_manifest.json").read_text())
        self.pdf_path = Path(source["path"])
        self.pdf = None
        try:
            import pymupdf  # type: ignore[import-not-found]

            if self.pdf_path.is_file():
                self.pdf = pymupdf.open(str(self.pdf_path))
        except ImportError:
            self.pdf = None
        self.owner: dict[str, str] = {}
        self.nodes_by_page: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for s in self.tree:
            for n in s.get("semantic_nodes", []):
                self.owner[n["node_id"]] = s["section_id"]
                self.nodes_by_page[n["page_no"]].append((s["section_id"], n))
        self.boilerplate = self._boilerplate_texts()
        self._xref_pages: Counter[int] | None = None
        self.header_tops = self._header_tops()
        self.title_nodes = self._title_nodes()

    def _boilerplate_texts(self) -> set[str]:
        pages_with: dict[str, set[int]] = defaultdict(set)
        for page, items in self.nodes_by_page.items():
            for _sid, n in items:
                key = re.sub(r"\d+", "#", norm(n["canonical_text"]))
                if key:
                    pages_with[key].add(page)
        n_pages = max(len(self.nodes_by_page), 1)
        return {k for k, pages in pages_with.items() if len(pages) >= max(5, 0.1 * n_pages)}

    def _header_tops(self) -> list[int]:
        """Vertical positions used by running headers: the same top y on many pages."""
        seen: Counter[int] = Counter()
        for items in self.nodes_by_page.values():
            highest = sorted((top(n) for _sid, n in items if n.get("bbox")), reverse=True)[:3]
            seen.update({round(y) for y in highest})
        n_pages = max(len(self.nodes_by_page), 1)
        return [y for y, count in seen.items() if count >= 0.25 * n_pages]

    def is_header(self, n: dict[str, Any]) -> bool:
        if not n.get("bbox") or len(n["canonical_text"].split()) > 14:
            return False
        return any(abs(top(n) - y) <= 2 for y in self.header_tops)

    def is_boilerplate_node(self, n: dict[str, Any]) -> bool:
        return self.is_header(n) or self.is_boilerplate(n["canonical_text"])

    def is_boilerplate(self, text: str) -> bool:
        t = norm(text)
        if not t or t.isdigit() or SLUG.search(text):
            return True
        if len(t) <= 3 and t.replace(" ", "").isdigit():
            return True
        return re.sub(r"\d+", "#", t) in self.boilerplate

    def _title_nodes(self) -> dict[str, list[dict[str, Any]]]:
        """Nodes that print a section's own title on its start page (exact match)."""
        found: dict[str, list[dict[str, Any]]] = {}
        for s in self.tree:
            key = norm(s["title"])
            if not key:
                continue
            found[s["section_id"]] = [
                n
                for _sid, n in self.nodes_by_page.get(s["page_start"], [])
                if norm(n["canonical_text"]).replace(" ", "") == key.replace(" ", "")
                and not self.is_header(n)
            ]
        return found


def section_signals(v: Version, sid: str) -> Signals:
    s = v.by_id[sid]
    sig = Signals()
    nodes = s.get("semantic_nodes", [])
    own_titles = v.title_nodes.get(sid, [])
    if own_titles and not any(v.owner.get(n["node_id"]) == sid for n in own_titles):
        owner = v.owner.get(own_titles[0]["node_id"], "?")
        sig.content_misplaced.append(
            f"own heading '{s['title']}' (node {own_titles[0]['node_id']}, "
            f"p{own_titles[0]['page_no']}) is owned by {owner}"
        )
    for other_id, titles in v.title_nodes.items():
        if other_id == sid:
            continue
        for n in titles:
            if v.owner.get(n["node_id"]) == sid:
                sig.content_misplaced.append(
                    f"holds the heading of {other_id} '{v.by_id[other_id]['title']}' "
                    f"(node {n['node_id']}, p{n['page_no']})"
                )
    title_ids = {n["node_id"] for n in own_titles}
    body = [
        n
        for n in nodes
        if n["node_id"] not in title_ids
        and not v.is_boilerplate_node(n)
        and norm(n["canonical_text"]) != norm(s["title"])
    ]
    if not body and not s.get("child_sections"):
        sig.empty_body = True
    own_top = max(
        (top(n) for n in own_titles if v.owner.get(n["node_id"]) == sid and n.get("bbox")),
        default=None,
    )
    first_on_page = {}
    for page in {n["page_no"] for n in nodes}:
        content = [
            (sec, n) for sec, n in v.nodes_by_page.get(page, []) if not v.is_boilerplate_node(n)
        ]
        first_on_page[page] = (
            min(content, key=lambda x: x[1]["semantic_order"])[0] if content else None
        )
    above = []
    index_pages: Counter[int] = Counter()
    page_totals: Counter[int] = Counter()
    for n in nodes:
        text = n["canonical_text"][:50]
        boiler = v.is_boilerplate_node(n)
        if not boiler:
            page_totals[n["page_no"]] += 1
            if INDEX_ENTRY.search(n["canonical_text"]):
                index_pages[n["page_no"]] += 1
        if (
            own_top is not None
            and n["page_no"] == s["page_start"]
            and n.get("bbox")
            and not boiler
            and n["node_id"] not in title_ids
            and top(n) > own_top + 5
        ):
            words = n["canonical_text"].split()
            # A short caps label that is the first content of the page is the page's
            # running header: the pipeline gives it to the section that owns the
            # page's first content (BUG-022), so it is not bleed.
            leads_page = not any(
                sec != sid and other.get("bbox") and top(other) > top(n)
                and not v.is_boilerplate_node(other)
                for sec, other in v.nodes_by_page.get(n["page_no"], [])
            )
            caps_label = len(words) <= 4 and n["canonical_text"].upper() == n["canonical_text"]
            if caps_label and leads_page:
                pass
            elif caps_label:
                sig.boilerplate_bleed.append(
                    f"p{n['page_no']} '{text}' (short caps label above its heading)"
                )
            else:
                above.append(f"'{text}'")
        if boiler:
            owner = first_on_page.get(n["page_no"]) if v.is_header(n) else None
            if owner and owner != sid and not is_ancestor(v, sid, owner):
                sig.boilerplate_bleed.append(f"p{n['page_no']} '{text}' (page belongs to {owner})")
            elif n["page_no"] > s["page_end"]:
                sig.boilerplate_bleed.append(f"p{n['page_no']} '{text}'")
        elif n["page_no"] > s["page_end"]:
            sig.continues_next_page.append(f"p{n['page_no']} '{text}'")
        elif n["page_no"] < s["page_start"]:
            sig.content_misplaced.append(f"node from p{n['page_no']} before page_start: '{text}'")
        if n["node_type"] == "table":
            if "[Table 0x0]" in n["canonical_text"]:
                sig.placeholder_tables.append(f"p{n['page_no']} {n['node_id']}")
            owner = table_owner(v, n)
            if owner and owner != sid and not is_ancestor(v, sid, owner):
                sig.tables_misowned.append(
                    f"table {n['node_id']} on p{n['page_no']} ('{text}') sits under the "
                    f"heading of {owner} '{v.by_id[owner]['title']}'"
                )
    pos = v.order.index(sid)
    if pos + 1 < len(v.order):
        nxt_id = v.order[pos + 1]
        nxt = v.by_id[nxt_id]
        nxt_titles = [
            n
            for n in v.title_nodes.get(nxt_id, [])
            if v.owner.get(n["node_id"]) == nxt_id and n.get("bbox")
        ]
        if nxt_titles and not is_ancestor(v, nxt_id, sid):
            nt = max(top(n) for n in nxt_titles)
            lost = [
                n
                for n in nxt.get("semantic_nodes", [])
                if n["page_no"] == nxt["page_start"]
                and n.get("bbox")
                and not v.is_boilerplate_node(n)
                and top(n) > nt + 5
                and len(n["canonical_text"].split()) > 4
            ]
            if lost:
                sig.content_misplaced.append(
                    f"{len(lost)} node(s) printed before the next heading '{nxt['title']}' "
                    f"on p{nxt['page_start']} are owned by {nxt_id}: "
                    f"'{lost[0]['canonical_text'][:50]}'"
                )
    if above:
        sig.content_misplaced.append(
            f"{len(above)} content node(s) printed above its own heading "
            f"on p{s['page_start']}: {above[:2]}"
        )
    idx: list[int] = []
    if sid == v.order[-1]:
        for page in sorted({n["page_no"] for n in nodes if n["page_no"] > s["page_start"]}):
            joined = " ".join(n["canonical_text"] for n in nodes if n["page_no"] == page)
            if len(INDEX_PAIR.findall(joined)) >= 25:
                idx.append(page)
    if idx:
        sig.content_misplaced.append(
            f"index-like back-matter pages absorbed: p{min(idx)}-p{max(idx)} ({len(idx)} pages)"
        )
    parent_id = s.get("parent_section_id")
    if parent_id:
        parent = v.by_id.get(parent_id)
        if parent is None:
            sig.hierarchy.append(f"parent {parent_id} does not exist")
        else:
            if parent["hierarchy_level"] >= s["hierarchy_level"]:
                sig.hierarchy.append("level is not deeper than its parent's")
            if s["hierarchy_path"] != f"{parent['hierarchy_path']}/{s['title']}":
                sig.hierarchy.append("hierarchy_path is not parent path + title")
            if sid not in parent.get("child_sections", []):
                sig.hierarchy.append("parent does not list this section as a child")
    return sig


def is_ancestor(v: Version, maybe_child: str, maybe_ancestor: str) -> bool:
    cur = v.by_id[maybe_child].get("parent_section_id")
    while cur:
        if cur == maybe_ancestor:
            return True
        cur = v.by_id.get(cur, {}).get("parent_section_id")
    return False


def heading_above(v: Version, page: int, y_top: float) -> str | None:
    """Section whose own title node is closest above y_top on the page (PDF y grows upward)."""
    best: tuple[float, str] | None = None
    for sid, titles in v.title_nodes.items():
        for n in titles:
            if n["page_no"] != page or not n.get("bbox"):
                continue
            hy = max(n["bbox"]["y0"], n["bbox"]["y1"])
            if hy >= y_top - 1 and (best is None or hy < best[0]):
                best = (hy, sid)
    return best[1] if best else None


def table_owner(v: Version, n: dict[str, Any]) -> str | None:
    if not n.get("bbox"):
        return None
    top = max(n["bbox"]["y0"], n["bbox"]["y1"])
    return heading_above(v, n["page_no"], top)


def is_repeated_decoration(v: Version, xref: int, rect: Any, page_h: float, frac: float) -> bool:
    """The pipeline drops an image shown on 5+ pages in the top/bottom 10% band (BUG-004:
    DOC's footer divider); its absence is not a lost figure."""
    if v._xref_pages is None:
        counts: Counter[int] = Counter()
        for page in v.pdf:
            for info in page.get_images(full=True):
                counts[info[0]] += 1
        v._xref_pages = counts
    if v._xref_pages[xref] < 5:
        return False
    return rect.y1 <= page_h * 0.10 or rect.y0 >= page_h * 0.90


def page_facts(v: Version, page: int, sid: str) -> PageFacts:
    facts = PageFacts()
    kept = [img for img in v.images if img.get("page_no") == page]
    facts.kept = len(kept)
    facts.mapped_elsewhere = [
        f"{img.get('section_id')} ({img.get('width_px')}x{img.get('height_px')})"
        for img in kept
        if img.get("section_id") != sid
    ]
    if v.pdf is None:
        return facts
    facts.available = True
    pg = v.pdf[page - 1]
    area = pg.rect.width * pg.rect.height
    kept_sizes = Counter((img.get("width_px"), img.get("height_px")) for img in kept)
    rasters = pg.get_images(full=True)
    facts.raster = len(rasters)
    for info in rasters:
        xref = info[0]
        rects = pg.get_image_rects(xref)
        if not rects:
            continue
        rect = rects[0]
        size = (info[2], info[3])
        frac = rect.width * rect.height / area if area else 0
        if is_repeated_decoration(v, xref, rect, pg.rect.height, frac):
            continue
        if kept_sizes.get(size, 0) > 0:
            kept_sizes[size] -= 1
            # pdf y grows downward in PyMuPDF rects; tree bboxes grow upward
            owner = heading_above(v, page, pg.rect.height - rect.y0)
            mapped = next(
                (
                    img.get("section_id")
                    for img in kept
                    if (img.get("width_px"), img.get("height_px")) == size
                ),
                None,
            )
            if owner and mapped and owner != mapped and not is_ancestor(v, mapped, owner):
                facts.misowned_images.append(
                    f"image {size[0]}x{size[1]} at y={rect.y0:.0f} sits under {owner} "
                    f"but is mapped to {mapped}"
                )
            continue
        label = (
            f"{size[0]}x{size[1]} px, {rect.width:.0f}x{rect.height:.0f} pt ({frac:.1%} of page)"
        )
        (facts.dropped_figures if frac >= FIGURE_AREA_FRACTION else facts.dropped_icons).append(
            label
        )
    text = pg.get_text()
    facts.vector_suspect = (
        facts.raster == 0 and len(pg.get_drawings()) >= 40 and bool(FIGURE_CODE.search(text))
    )
    return facts


def expectation(ref: str, sig: Signals, pf: PageFacts) -> tuple[str | None, str | None, list[str]]:
    """Return (expected_result, expected_severity, reasons). None means no deterministic view."""
    if ref == "5.4-page_start_end":
        crit = (
            sig.content_misplaced
            + sig.tables_misowned
            + (["section has no body of its own"] if sig.empty_body else [])
        )
        if crit:
            return "FAIL", "Critical", crit
        if sig.continues_next_page:
            return (
                "FAIL",
                "Medium",
                [f"content continues past page_end: {sig.continues_next_page[:3]}"],
            )
        if sig.boilerplate_bleed:
            return (
                "FAIL",
                "Low",
                [f"boilerplate from another section's page: {sig.boilerplate_bleed[:3]}"],
            )
        return "PASS", None, ["no boundary signal"]
    if ref == "5.4-gaps_duplicates":
        if sig.empty_body:
            return "FAIL", "Critical", ["section has no body of its own"]
        if any("index-like" in c for c in sig.content_misplaced):
            return "FAIL", "Critical", [c for c in sig.content_misplaced if "index-like" in c]
        return None, None, []
    if ref in ("5.4-parent_child", "5.4-hierarchy_path", "5.4-hierarchy_level"):
        if sig.hierarchy:
            return "FAIL", "Critical", sig.hierarchy
        return "PASS", None, ["hierarchy fields are consistent"]
    if ref == "5.5-filters_discarding":
        if not pf.available:
            return None, None, ["PDF not available"]
        if pf.dropped_figures:
            return (
                "FAIL",
                "Critical",
                [f"raster figure(s) on the page are not in images_v1.json: {pf.dropped_figures}"],
            )
        if pf.dropped_icons:
            return "FAIL", "Low", [f"small raster(s) dropped: {pf.dropped_icons}"]
        return (
            None,
            None,
            ["every raster image is kept; vector figures can only be judged visually"],
        )
    if ref == "5.5-image_section_mapping":
        if pf.misowned_images:
            return "FAIL", "Medium", pf.misowned_images
        return None, None, []
    if ref == "5.6-table_content" and sig.placeholder_tables:
        return "FAIL", "Low", [f"empty table placeholder(s): {sig.placeholder_tables}"]
    return None, None, []


def keyword_severity(row: dict[str, Any]) -> tuple[str | None, str]:
    """Sprint severity implied by the row's own evidence for visual-only patterns."""
    text = f"{row.get('evidence', '')} {row.get('notes', '')}".lower()
    ref = row["checklist_ref"]
    if ref == "5.5-filters_discarding" and ("vector" in text or "not extracted" in text):
        return "Critical", "evidence describes a figure missing from the output"
    if ref == "5.6-table_content":
        if any(
            k in text
            for k in (
                "false number",
                "can no longer",
                "lost",
                "change meaning",
                "no longer be read",
            )
        ):
            return (
                "Medium",
                "evidence describes table values that change meaning or cannot be attributed",
            )
        if any(k in text for k in ("merged", "shift", "placeholder", "misdetected", "not a table")):
            return "Low", "evidence describes merged cells with values preserved"
    if ref == "5.6-numbering_scheme" and "roman" in text:
        return "Medium", "evidence describes an unrepresented numbering scheme"
    return None, ""


def load_rows(root: Path, batch: str | None) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    batches = (
        [root / "agent_exchange" / batch] if batch else sorted((root / "agent_exchange").glob("*"))
    )
    for b in batches:
        out = b / "output" / "findings_result.json"
        if not out.is_file():
            continue
        payload = json.loads(out.read_text())
        for r in payload.get("findings", payload if isinstance(payload, list) else []):
            key = f"{r['section_id']}|{r['page_sampled']}|{r['checklist_ref']}"
            rows[key] = {**r, "batch": b.name}
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--qa-root", type=Path, required=True)
    ap.add_argument("--manual-id", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument(
        "--batch", help="check one agent_exchange batch (default: all, later batches win)"
    )
    ap.add_argument("--json-out", type=Path, help="write the per-row report as JSON")
    ap.add_argument("--md-out", type=Path, help="write a Markdown report")
    args = ap.parse_args()

    root = args.qa_root / args.manual_id / args.version
    v = Version(root, args.qa_root, args.manual_id)
    rows = load_rows(root, args.batch)
    approved: set[str] = set()
    state_path = root / "findings" / "review_state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text())
        approved = {
            k.split("|", 1)[1] for k, d in state.get("decisions", {}).items() if d.get("approved")
        }

    sig_cache: dict[str, Signals] = {}
    page_cache: dict[tuple[int, str], PageFacts] = {}
    report = []
    for key, row in sorted(rows.items()):
        sid, ref = row["section_id"], row["checklist_ref"]
        if sid not in v.by_id:
            continue
        sig = sig_cache.setdefault(sid, section_signals(v, sid))
        page = (
            int(row["page_sampled"])
            if str(row["page_sampled"]).isdigit()
            else v.by_id[sid]["page_start"]
        )
        pf = page_cache.setdefault((page, sid), page_facts(v, page, sid))
        exp_result, exp_sev, reasons = expectation(ref, sig, pf)
        source = "signals"
        if exp_result is None and row["result"] == "FAIL":
            kw_sev, why = keyword_severity(row)
            if kw_sev:
                exp_result, exp_sev, reasons, source = "FAIL", kw_sev, [why], "evidence"
        if exp_result is None:
            verdict = "VISUAL-ONLY"
        elif exp_result == "FAIL" and row["result"] == "PASS":
            verdict = "CONTRADICTED"
        elif exp_result == "PASS" and row["result"] == "FAIL":
            verdict = "UNSUPPORTED"
        elif exp_result == "FAIL" and row.get("severity") != exp_sev:
            verdict = "SEVERITY"
        else:
            verdict = "CONFIRMED"
        report.append(
            {
                "key": key,
                "section_id": sid,
                "page_sampled": row["page_sampled"],
                "checklist_ref": ref,
                "proposed": f"{row['result']} {row.get('severity', '')}".strip(),
                "expected": f"{exp_result or '-'} {exp_sev or ''}".strip(),
                "verdict": verdict,
                "source": source,
                "reasons": reasons,
                "approved": key in approved,
                "batch": row["batch"],
            }
        )

    counts = Counter(r["verdict"] for r in report)
    print(
        f"{args.manual_id} {args.version}: {len(report)} rows, "
        f"PDF checks {'on' if v.pdf else 'OFF'}"
    )
    for verdict in ("CONFIRMED", "VISUAL-ONLY", "SEVERITY", "UNSUPPORTED", "CONTRADICTED"):
        print(f"  {verdict:13} {counts.get(verdict, 0)}")
    for r in report:
        if r["verdict"] in ("CONTRADICTED", "SEVERITY", "UNSUPPORTED"):
            flag = " [approved]" if r["approved"] else ""
            print(
                f"  - {r['verdict']}{flag} {r['section_id']} p{r['page_sampled']} "
                f"{r['checklist_ref']}: "
                f"proposed {r['proposed']}, expected {r['expected']} — {r['reasons'][0][:160]}"
            )
    if args.json_out:
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if args.md_out:
        lines = [
            f"# Claim check — `{args.manual_id}` `{args.version}`",
            "",
            "| Verdict | Rows |",
            "|---|---:|",
        ]
        lines += [
            f"| {k} | {counts.get(k, 0)} |"
            for k in ("CONFIRMED", "VISUAL-ONLY", "SEVERITY", "UNSUPPORTED", "CONTRADICTED")
        ]
        lines += [
            "",
            "| Verdict | Section | Page | Item | Proposed | Expected | Approved | Reason |",
            "|---|---|---:|---|---|---|---|---|",
        ]
        for r in report:
            if r["verdict"] in ("CONTRADICTED", "SEVERITY", "UNSUPPORTED"):
                reason = r["reasons"][0].replace("|", "/")[:200]
                lines.append(
                    f"| {r['verdict']} | {r['section_id']} | {r['page_sampled']} | "
                    f"{r['checklist_ref']} | "
                    f"{r['proposed']} | {r['expected']} | "
                    f"{'yes' if r['approved'] else ''} | {reason} |"
                )
        args.md_out.write_text("\n".join(lines) + "\n")
    return 1 if counts.get("CONTRADICTED") else 0


if __name__ == "__main__":
    sys.exit(main())
