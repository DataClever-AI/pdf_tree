---
bug_id: BUG-019
status: mitigated
finding: H-08, H-14
fix_branch: fix/BUG-019-heading-anchor
fix_commit: 3497934, d19c4ab
updated: 2026-10-07
---

# BUG-019 · Heading anchor accepts a contained or empty normalized heading: a short or glyph-only section_header (e.g. '!' or 'Trends') anchors the wrong section, shifting its content to the parent or a sibling

**Suspected module:** section_matcher.py::_find_heading_anchor (confirmed in code: `norm_title in norm_text or norm_text in norm_title`)

## Description

A section anchors on the wrong heading when the heading text is contained in another title or normalizes to an empty string. In 2002 a bullet glyph '!' labelled `section_header` anchors the section, and its real title stays in the previous section. In Philips 'Trends' anchors on 'Viewing Trends' and 'Setting the Horizon' on 'Setting the Horizon Trend Scale', shifting content by one section and leaving sections empty.

## Root cause

Confirmed in code: `src/tree_builder/section_matcher.py:139` accepts `norm_title in norm_text or norm_text in norm_title`. `_normalize_heading('!')` returns `''`, and the empty string is contained in every title.

## What was done

- 2026-09-28: identified in the agent review drafts of the v2 runs (2002 p21, p22, p28, p54, p61, p68, p88; Philips p283, p294, p295, p303); pending approval by the human reviewer (Oscar Munoz).
- 2026-09-29: root cause confirmed by reading `_find_heading_anchor`.
- 2026-09-29: registered in the root-cause catalogue `qa/confidence_index/root_causes.json`.
- 2026-09-29: fix committed in `3497934` on `fix/BUG-019-heading-anchor`. Tests: `tests/unit/test_section_matcher.py` (6 of 7 fail on the old code).
- 2026-09-29: attempt 1 (`v2.1`, commit `3497934`) was rejected before review. In 2002, sec_0184 anchored on a figure label and sec_0185 lost its heading.
- 2026-09-29: attempt 2 in `d19c4ab`: a merged heading like '1. Tilt Steering Column A: TILT MECHANISM' now anchors before a later figure label. Versions `v2.2` created for 2002 and Philips.

- 2026-10-07: status set back from fixed-pending-merge to mitigated. Philips and 2002 are at 0, but the final SOMATOM version v1.9 still has 4 FAIL rows (sec_0225 and sec_0244, 3 Critical). These rows were BUG-005 before; BUG-005 is fixed and the same sections now show this anchor problem.

## Fix

Done in `3497934` and `d19c4ab`. A section heading must match in this order: 1) exact `section_header`; 2) the first `section_header` in reading order that matches without leading numbers, starts with the title, or covers 80% of it; 3) exact text on any block. Headers shorter than 3 characters (like '!') never match. Blocks before the previous section's heading are skipped.

First proposal: ignore headings whose normalized text is empty or shorter than 3 characters; prefer an exact match among all `section_header` blocks of the page; accept a partial match only when it covers most of the title (length ratio >= 0.8 or rapidfuzz ratio >= 90). Add unit tests for '!', 'Trends'/'Viewing Trends' and exact-over-partial.

## Verification

Pending.

## Attempts

| Date | Manual | Version | Commit | Change | Before → After | Regressions | Decision |
|---|---|---|---|---|---|---|---|
| 2026-09-29 | `2002_Service_Manual_TI` | v2.1 | `3497934` fix(section_matcher): require exact or near-full heading match for section anchors (BUG-019) | Exact heading match first; ignore '!' and short contained headers. | not reviewed | — | Rejected before review. Tree check: 5 more sections start at their heading, but sec_0184 anchors on a figure label and sec_0185 loses its heading. Replaced by v2.2. |
| 2026-09-29 | `Philips-MP20-MP90-Manual` | v2.1 | `3497934` fix(section_matcher): require exact or near-full heading match for section anchors (BUG-019) | Exact heading match first; ignore '!' and short contained headers. | not reviewed | — | Not reviewed. Tree check: 12 more sections start at their heading, none lost. Same commit as the 2002 attempt, so replaced by v2.2. |
| 2026-09-30 | `2002_Service_Manual_TI` | v2.2 | `d19c4ab` fix(section_matcher): anchor merged headings by reading order before exact body text (BUG-019) | Exact heading match first; ignore '!' and short contained headers; a merged heading wins over a later figure label. | 7 → 0 | 3 | Keep. All 7 paired BUG-019 rows now pass; the reviewer approved v2.2. The 3 regressions are 5.6-table_content rows on tables that are the same in v2 and v2.2 (grading difference). Philips v2.2 is still a draft. |
| 2026-10-06 | `Philips-MP20-MP90-Manual` | v2.14 | `6eddaf1` fix(section_matcher): match headings with subscripts by text without spaces (BUG-019) | Section headers also match the bookmark title with all spaces removed, for subscripts such as 'SO 2'. | 0 → 0 | 0 | Keep: p482 Critical fixed; 31 nodes moved back to their sections (p134, p406-p410, p451, p482), all checked correct. |
| 2026-10-07 | `Philips-MP20-MP90-Manual` | v2.15 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 6 → 0 | 9 | Fixed in this manual: 6 -> 0 FAIL on paired rows. |

<!-- generated:occurrences:start -->
## Where it was seen

_Generated by `qa/_scripts/build_bug_registry.py`; do not edit this block. Full rows with evidence: [occurrences.csv](occurrences.csv). `draft` rows are unapproved agent drafts._

| Manual | Version | Official FAIL | Draft FAIL | Top severity | Sections (pages sampled) |
|---|---|---:|---:|---|---|
| `SOMATOM_Force_IFU_VB30` | v1.9 | 4 | 0 | Critical | sec_0225 (p131), sec_0244 (p138) |
<!-- generated:occurrences:end -->
