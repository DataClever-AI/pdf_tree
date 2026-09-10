"""
Task 2.3 — consolidate FAIL rows from all available findings_log.csv files into
a single deduplicated bug list (by root cause, not by row).

Two tiers:
  1. High-confidence auto-match: rows whose `notes` text explicitly names one
     of the recurring patterns documented in QA_TESTING_WORKFLOW_pdf_tree.md
     §7 (own words: "known pattern", "Recurrence of the known ...",
     "Textbook recurrence", "Matches known pattern") — these get merged into
     one consolidated_bugs.csv row per pattern, spanning every manual/section
     that hit it.
  2. Everything else: grouped by (manual, checklist_ref) as a "needs manual
     triage" placeholder row — NOT claimed as deduplicated by root cause,
     since that requires human judgment this script doesn't have. Flagged
     explicitly via bug_id prefix "TRIAGE-" so it's never confused with a
     reviewed entry.

Also normalizes `severity` across manuals — 2 of the 5 findings_log.csv files
use Spanish labels (Critica/Alta/Media/Baja) instead of the sprint's English
scale (Critical/High/Medium/Low); this was silently inconsistent before.

Usage: uv run python qa/_scripts/consolidate_bugs.py
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent
OUT_PATH = QA_DIR / "confidence_index" / "consolidated_bugs.csv"

# Manuals with a complete findings_log.csv as of this run. Philips-MP20-MP90
# and 2002_Service_Manual_TI are excluded — pipeline blocked, no findings yet.
MANUALS = [
    "DOC-0136477A",
    "AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION",
    "LOGIQ_e_R9_General_Service_Manual",
    "LOGIQ_S8",
    "SOMATOM_Force_IFU_VB30",
]

SEVERITY_MAP = {
    "critical": "Critical", "critica": "Critical", "crítica": "Critical",
    "high": "High", "alta": "High",
    "medium": "Medium", "media": "Medium",
    "low": "Low", "baja": "Low",
}
SEVERITY_WEIGHT = {"Critical": 8, "High": 4, "Medium": 2, "Low": 1}


def normalize_severity(raw: str) -> str:
    key = raw.strip().lower()
    return SEVERITY_MAP.get(key, raw.strip())


# --- Tier 1: known §7 patterns, matched by signature phrases in `notes` ----
# Order matters — first match wins. Each entry: (bug_id, title, suspected_module, regex)
KNOWN_PATTERNS = [
    (
        "BUG-001",
        "Chapter/appendix-opening Contents-box misplacement",
        "section_matcher.py (reading_order)",
        re.compile(r"contents-?box|contents table.*swept|chapter.*opening.*contents", re.I),
    ),
    (
        "BUG-002",
        "Back-matter silently absorbed past last bookmark",
        "section_matcher.py (page_end defaulting to total_pages)",
        re.compile(r"back-?matter|silently absorbed|absorbido", re.I),
    ),
    (
        "BUG-003",
        "Sibling image/table mismapping on shared pages",
        "section_matcher.py / image-to-section mapping",
        re.compile(r"sibling.*mismap|mismapping on shared pages", re.I),
    ),
    (
        "BUG-004",
        "Decorative footer divider passes image aspect-ratio filter",
        "pipeline.py::_extract_embedded_images (§5.5 filter #5)",
        re.compile(r"footer divider|footer-band|aspect-ratio threshold", re.I),
    ),
    (
        "BUG-005",
        "Content-stream desync — body text lost/misattributed around a "
        "chapter boundary (sec_0035 root cause family, SOMATOM)",
        "docling_extract.py or section_matcher.py (reading_order/window merge — unconfirmed)",
        re.compile(r"content-stream desync", re.I),
    ),
    (
        "BUG-006",
        "Body content extraction gap — section body text lost entirely, "
        "only heading (or nothing) survives as a stray node",
        "docling_extract.py (unconfirmed — total content loss per section)",
        re.compile(r"body[- ]content[- ]extraction gap|body-content-extraction-gap", re.I),
    ),
]


# --- Tier 1.5: manually reviewed rows that describe a known/new pattern in
# wording the Tier-1 regexes don't catch, or that are cross-referenced from
# another row's `notes` (e.g. "same family as sec_0005"). Reviewed by reading
# every one of the 82 originally-unmatched rows in full — see conversation
# history / commit message for the reasoning behind each grouping. Keyed by
# (manual_id, section_id, checklist_ref) -> bug_id.
MANUAL_OVERRIDES: dict[tuple[str, str, str], str] = {
    # BUG-001 family (Contents-box / chapter-opening content swept to first
    # child) described without the literal word "contents":
    ("DOC-0136477A", "sec_0004", "5.4-page_start_end"): "BUG-001",
    ("DOC-0136477A", "sec_0015", "5.4-page_start_end"): "BUG-001",
    ("SOMATOM_Force_IFU_VB30", "sec_0746", "5.4-page_start_end"): "BUG-001",
    ("SOMATOM_Force_IFU_VB30", "sec_0746", "5.5-image_section_mapping"): "BUG-001",
    ("SOMATOM_Force_IFU_VB30", "sec_0927", "5.5-image_section_mapping"): "BUG-001",
    # BUG-002 family (back-matter absorbed) — same section already counted
    # via a different checklist_ref row; these are additional confirming
    # angles on the identical defect, not new sections:
    ("DOC-0136477A", "sec_0279", "5.4-gaps_duplicates"): "BUG-002",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0083", "5.4-gaps_duplicates"): "BUG-002",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0083", "5.4-flagged_for_review"): "BUG-002",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0083", "5.6-numbering_scheme"): "BUG-002",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0083", "5.6-offset_applied"): "BUG-002",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0083", "5.5-filters_passing_noise"): "BUG-002",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0083", "5.5-image_section_mapping"): "BUG-002",
    # BUG-003 family (sibling image/table mismapping) described as a
    # "deepest-wins tie-break" variant, cross-referencing sec_0271/sec_0591:
    ("SOMATOM_Force_IFU_VB30", "sec_0807", "5.5-image_section_mapping"): "BUG-003",
    # BUG-004 family (footer divider) — continuation rows saying only "same
    # as prior occurrences" without repeating the trigger phrase:
    ("DOC-0136477A", "sec_0025", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0046", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0047", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0059", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0066", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0076", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0085", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0095", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0098", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0109", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0111", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0123", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0126", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0137", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0148", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0159", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0162", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0176", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0178", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0189", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0198", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0207", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0209", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0231", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0233", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0243", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0245", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0254", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0271", "5.5-filters_passing_noise"): "BUG-004",
    ("DOC-0136477A", "sec_0275", "5.5-filters_passing_noise"): "BUG-004",
    # BUG-005 family (content-stream desync) — cross-referenced without the
    # trigger phrase itself:
    ("SOMATOM_Force_IFU_VB30", "sec_0149", "5.4-flagged_for_review"): "BUG-005",
    ("SOMATOM_Force_IFU_VB30", "sec_0058", "5.4-flagged_for_review"): "BUG-005",
    # New patterns, confirmed via full-text review (2+ occurrences each):
    ("AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION", "sec_0017", "5.6-table_content"): "BUG-007",
    ("AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION", "sec_0018", "5.6-table_content"): "BUG-007",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0069", "5.6-table_content"): "BUG-008",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0072", "5.6-table_content"): "BUG-008",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0078", "5.6-table_content"): "BUG-009",
    ("AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION", "sec_0019", "5.5-filters_discarding"): "BUG-010",
    ("AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION", "sec_0020", "5.5-filters_discarding"): "BUG-010",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0051", "5.5-filters_discarding"): "BUG-010",
    ("LOGIQ_S8", "sec_0135", "5.5-filters_discarding"): "BUG-011",
    ("LOGIQ_S8", "sec_0137", "5.5-filters_discarding"): "BUG-011",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0020", "5.5-filters_discarding"): "BUG-012",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0023", "5.5-filters_discarding"): "BUG-012",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0045", "5.5-filters_discarding"): "BUG-012",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0056", "5.5-filters_discarding"): "BUG-012",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0063", "5.5-filters_discarding"): "BUG-012",
    ("LOGIQ_e_R9_General_Service_Manual", "sec_0028", "5.5-image_section_mapping"): "BUG-013",
    ("LOGIQ_S8", "sec_0072", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0074", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0075", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0076", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0079", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0080", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0083", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0084", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0085", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0130", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0135", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0137", "5.4-page_start_end"): "BUG-014",
    ("SOMATOM_Force_IFU_VB30", "sec_0058", "5.5-image_section_mapping"): "BUG-014",
    ("SOMATOM_Force_IFU_VB30", "sec_0555", "5.4-page_start_end"): "BUG-014",
    ("LOGIQ_S8", "sec_0103", "5.5-filters_discarding"): "BUG-015",
    ("LOGIQ_S8", "sec_0110", "5.5-filters_discarding"): "BUG-015",
    ("LOGIQ_S8", "sec_0111", "5.5-filters_discarding"): "BUG-015",
    ("SOMATOM_Force_IFU_VB30", "sec_0005", "5.5-filters_discarding"): "BUG-016",
    ("SOMATOM_Force_IFU_VB30", "sec_0695", "5.5-filters_discarding"): "BUG-017",
    ("SOMATOM_Force_IFU_VB30", "sec_0874", "5.4-flagged_for_review"): "BUG-018",
    ("LOGIQ_S8", "sec_0138", "5.4-gaps_duplicates"): "BUG-002",
    # Not a defect — positive/control finding (verification mechanism
    # correctly caught a low-title-match case; explicitly informational in
    # its own `notes`). Excluded from the bug list entirely, not merged.
    ("SOMATOM_Force_IFU_VB30", "sec_0906", "5.4-flagged_for_review"): "EXCLUDE-NOT-A-BUG",
}

NEW_BUG_META: dict[str, tuple[str, str]] = {
    # bug_id -> (title, suspected_module)
    "BUG-007": ("Native table extractor captures only the header row for symbol/glyph-marked grids, losing all data rows",
                "docling table structure model (unconfirmed)"),
    "BUG-008": ("Table header cells merge/reorder during extraction, breaking column-to-value attribution",
                "docling table structure model (unconfirmed)"),
    "BUG-009": ("Table mistyped as paragraph/heading node instead of a table node (single instance)",
                "docling table structure model (unconfirmed)"),
    "BUG-010": ("Vector-drawn diagrams not captured as images — extractor only handles raster XObjects",
                "pipeline.py::_extract_embedded_images"),
    "BUG-011": ("Simple line-art/pictogram diagrams missing from image extraction — mechanism unconfirmed (possibly size-filtered)",
                "pipeline.py::_extract_embedded_images (unconfirmed)"),
    "BUG-012": ("Sporadic single/partial image omissions from the image index — mechanism unconfirmed",
                "pipeline.py::_extract_embedded_images (unconfirmed)"),
    "BUG-013": ("Extracted image asset incorrectly rotated 180°",
                "pipeline.py::_extract_embedded_images (unconfirmed)"),
    "BUG-014": ("Section page_end declared one page short of the true content boundary — trailing content (text or images) bleeds into or is misattributed from the neighboring section",
                "section_matcher.py::_compute_page_ranges (unconfirmed)"),
    "BUG-015": ("Step-illustration photos silently dropped on pages that also carry multiple table-embedded images",
                "pipeline.py::_extract_embedded_images (unconfirmed)"),
    "BUG-016": ("Near-duplicate/overlapping embedded image xrefs cause under-extraction on pages with several similar photos",
                "pipeline.py::_extract_embedded_images (unconfirmed)"),
    "BUG-017": ("UI reference-icon screenshots discarded by an over-aggressive minimum-pixel-dimension image filter",
                "pipeline.py::_extract_embedded_images (min_image_px)"),
    "BUG-018": ("Cross-chapter node swap — content misattributed across non-adjacent chapter boundaries (new pattern, single instance so far)",
                "section_matcher.py (unconfirmed)"),
}


def classify(manual_id: str, section_id: str, checklist_ref: str, notes: str, evidence: str) -> str | None:
    override = MANUAL_OVERRIDES.get((manual_id, section_id, checklist_ref))
    if override:
        return override
    text = f"{notes} {evidence}"
    for bug_id, _title, _module, pat in KNOWN_PATTERNS:
        if pat.search(text):
            return bug_id
    return None


def load_fails(manual: str) -> list[dict]:
    path = QA_DIR / manual / "findings" / "findings_log.csv"
    with path.open() as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        if r["result"] != "FAIL":
            continue
        r = dict(r)
        r["manual_id"] = r.get("manual_id") or manual
        r["severity"] = normalize_severity(r["severity"])
        out.append(r)
    return out


KNOWN_META = {bug_id: (title, module) for bug_id, title, module, _pat in KNOWN_PATTERNS}
ALL_META = {**KNOWN_META, **NEW_BUG_META}


def main() -> None:
    all_fails: list[dict] = []
    for m in MANUALS:
        all_fails.extend(load_fails(m))

    known_groups: dict[str, dict] = {}
    unmatched: list[dict] = []
    excluded_not_a_bug: list[dict] = []
    for r in all_fails:
        bug_id = classify(r["manual_id"], r["section_id"], r["checklist_ref"],
                           r.get("notes", ""), r.get("evidence", ""))
        if bug_id == "EXCLUDE-NOT-A-BUG":
            excluded_not_a_bug.append(r)
            continue
        if bug_id is None:
            unmatched.append(r)
            continue
        title, module = ALL_META[bug_id]
        g = known_groups.setdefault(bug_id, {
            "bug_id": bug_id, "title": title, "suspected_module": module,
            "severities": [], "manuals": set(), "sections": set(),
        })
        g["severities"].append(r["severity"])
        g["manuals"].add(r["manual_id"])
        g["sections"].add(r["section_id"])

    # Remaining triage — only rows never reviewed/matched (see script header
    # for the 2 that stayed here after full manual review: evidence was
    # genuinely inconclusive, not just an unmatched keyword).
    triage_groups: dict[tuple[str, str], dict] = {}
    for r in unmatched:
        key = (r["manual_id"], r["checklist_ref"])
        g = triage_groups.setdefault(key, {
            "severities": [], "sections": set(),
        })
        g["severities"].append(r["severity"])
        g["sections"].add(r["section_id"])

    rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    rows_out = []

    for bug_id, g in sorted(known_groups.items()):
        top_sev = sorted(g["severities"], key=lambda s: rank.get(s, 9))[0]
        rows_out.append({
            "bug_id": bug_id,
            "title": g["title"],
            "severity": top_sev,
            "manuals_affected": "; ".join(sorted(g["manuals"])),
            "sections_affected": f"{len(g['sections'])} sections: " + ", ".join(sorted(g["sections"])),
            "suspected_module": g["suspected_module"],
            "escalate": "Yes" if top_sev in ("Critical", "High") else "No",
        })

    i = 1
    for (manual, ref), g in sorted(triage_groups.items()):
        top_sev = sorted(g["severities"], key=lambda s: rank.get(s, 9))[0]
        rows_out.append({
            "bug_id": f"TRIAGE-{i:03d}",
            "title": f"[needs manual root-cause review] {ref} FAILs in {manual}",
            "severity": top_sev,
            "manuals_affected": manual,
            "sections_affected": f"{len(g['sections'])} sections: " + ", ".join(sorted(g["sections"])),
            "suspected_module": "",
            "escalate": "Yes" if top_sev in ("Critical", "High") else "No",
        })
        i += 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "bug_id", "title", "severity", "manuals_affected",
            "sections_affected", "suspected_module", "escalate",
        ])
        w.writeheader()
        w.writerows(rows_out)

    print(f"Wrote {len(rows_out)} rows to {OUT_PATH}")
    print(f"  {len(known_groups)} root-cause bugs (BUG-001..{max(known_groups)})")
    print(f"  {len(triage_groups)} still-unresolved triage groups ({len(unmatched)} raw FAILs)")
    print(f"  {len(excluded_not_a_bug)} row(s) excluded as not-a-defect (positive/control finding)")
    print(f"  Total FAILs reviewed: {len(all_fails)} from {len(MANUALS)} manuals")
    print("  NOTE: Philips-MP20-MP90-Manual and 2002_Service_Manual_TI excluded")
    print("        (pipeline blocked, no findings yet) — this is PRELIMINARY.")


if __name__ == "__main__":
    main()
