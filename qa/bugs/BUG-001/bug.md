---
bug_id: BUG-001
status: mitigated
finding: H-05
fix_branch: fix/BUG-001-positional-placement
fix_commit: fa0bc0b, 4bff4c2
updated: 2026-10-07
---

# BUG-001 · Chapter/appendix-opening Contents-box misplacement

**Suspected module:** section_matcher.py (reading_order)

## Description

At a chapter or appendix opening, the 'Contents' box printed on the chapter's first page is assigned to the first child section instead of the chapter section.

## Root cause

Hypothesis: `section_matcher` assigns content by reading order only; the contents box comes after the first child heading in Docling's reading order.

## What was done

- 2026-09-04: identified in the v1 QA review of DOC-0136477A, LOGIQ_S8 and SOMATOM_Force_IFU_VB30 and consolidated by root cause in Task 2.3 (commit `3a4ec7f`).
- 2026-09-29: registered in the root-cause catalogue `qa/confidence_index/root_causes.json`.
- 2026-09-29: cause confirmed. Tables and images were placed by page only: the deepest section on the page got them. Fixed in `fa0bc0b` (same change for BUG-001 and BUG-003). Mitigation versions: `DOC-0136477A` v1.1, `Philips-MP20-MP90-Manual` v2.3, `SOMATOM_Force_IFU_VB30` v1.1, `LOGIQ_S8` v1.1.
- 2026-09-29: agent review (drafts, not approved) of the paired rows. DOC-0136477A v1.1 and Philips v2.3: most target rows pass or drop to Low. LOGIQ_S8 v1.1: the Contents box is printed under its own numbered heading in Section N-1, so it probably stays there by design. SOMATOM v1.1: most rows are not fixed, because the text on those pages is in the wrong section (BUG-005). New image regressions came from full-width running headers and margin headings. Fixed in `4bff4c2`; it needs new mitigation versions (v1.2, v2.4).
- 2026-09-30: `4bff4c2` measured in DOC-0136477A v1.2, SOMATOM v1.2, LOGIQ_S8 v1.2 and Philips v2.4 (agent drafts, not approved). The image regressions are fixed: LOGIQ_S8 11 rows, Philips p27 and p354, SOMATOM p125 and p315. No text or table node changed section. SOMATOM still has wrong images where the text above them is in the wrong section (BUG-005): p16, p110, p132 and p283.

## Fix

`section_matcher` places a table after the nearest text block printed above it on the same page (a block in the same column first). `pipeline._map_images_to_sections` does the same for images, with the text nodes of the tree. A table or image above every block of its page continues the previous content. A heading reaches to the right edge of the page and counts when it starts level with the item (margin headings), so a full-width running header does not win (`4bff4c2`). If the chosen section is more than one page away from the item's page (reading order out of sync, BUG-005), or there is no bbox, the old page-based placement is kept.

## Verification

Pending.

## Attempts

| Date | Manual | Version | Commit | Change | Before → After | Regressions | Decision |
|---|---|---|---|---|---|---|---|
| 2026-10-03 | `Philips-MP20-MP90-Manual` | v2.4 | `04e1345` fix(section_matcher): extend page_end to the next page when the section owns body content there (BUG-014) | Tables and images placed by position on the page (BUG-001/003); page_end extended by one page for owned content (BUG-014) | 0 → 0 | 8 | Approved rows; no BUG-001 rows in Philips |
| 2026-10-03 | `SOMATOM_Force_IFU_VB30` | v1.2 | `04e1345` fix(section_matcher): extend page_end to the next page when the section owns body content there (BUG-014) | Tables and images placed by position on the page (BUG-001/003); page_end extended by one page for owned content (BUG-014) | 4 → 5 | 16 | Approved rows; limited by BUG-005 (window desync), fixed later in 360cf01 |
| 2026-10-06 | `DOC-0136477A` | v1.2 | `04e1345` fix(section_matcher): extend page_end to the next page when the section owns body content there (BUG-014) | Tables and images are placed by their position on the page, and page_end covers trailing content. | 1 → 1 | 1 | Keep: 1 -> 1 on 87 paired rows (base = drafts). No change for BUG-001 in DOC. |
| 2026-10-07 | `DOC-0136477A` | v1.12 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 19 → 2 | 11 | Better: 19 -> 2 FAIL on paired rows. The rest is still open. |
| 2026-10-07 | `SOMATOM_Force_IFU_VB30` | v1.9 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 5 → 0 | 0 | Fixed in this manual: 5 -> 0 FAIL on paired rows. |
| 2026-10-07 | `LOGIQ_S8` | v1.12 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 7 → 3 | 58 | Better: 7 -> 3 FAIL on paired rows. The rest is still open. |

<!-- generated:occurrences:start -->
## Where it was seen

_Generated by `qa/_scripts/build_bug_registry.py`; do not edit this block. Full rows with evidence: [occurrences.csv](occurrences.csv). `draft` rows are unapproved agent drafts._

| Manual | Version | Official FAIL | Draft FAIL | Top severity | Sections (pages sampled) |
|---|---|---:|---:|---|---|
| `DOC-0136477A` | v1.13 | 1 | 0 | Low | sec_0004 (p17) |
<!-- generated:occurrences:end -->
