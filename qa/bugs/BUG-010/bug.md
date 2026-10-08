---
bug_id: BUG-010
status: mitigated
finding: H-10
fix_branch: 
fix_commit: 
updated: 2026-10-07
---

# BUG-010 · Vector-drawn diagrams not captured as images — extractor only handles raster XObjects

**Suspected module:** pipeline.py::_extract_embedded_images

## Description

Diagrams drawn with PDF vector paths are not exported as images; only their text labels survive.

## Root cause

`pipeline.py::_extract_embedded_images` only reads raster XObjects (`page.get_images`).

## What was done

- 2026-09-04: identified in the v1 QA review of AUTOMATIC_TRANSMISSION and LOGIQ_e_R9 and consolidated by root cause in Task 2.3 (commit `3a4ec7f`).
- 2026-09-28: seen again in the agent review drafts of the v2 runs (2002 (13 figures) and Philips); pending approval by the human reviewer (Oscar Munoz).
- 2026-09-29: registered in the root-cause catalogue `qa/confidence_index/root_causes.json`.

## Fix

Proposed: rasterize the drawing region from `page.get_drawings()` when a figure has no raster image. New feature; lower priority.

## Verification

Pending.

## Attempts

| Date | Manual | Version | Commit | Change | Before → After | Regressions | Decision |
|---|---|---|---|---|---|---|---|
| 2026-10-06 | `2002_Service_Manual_TI` | v2.7 | `2b58bb4` fix(pipeline): do not take headings as vector figure labels (BUG-010) | Round 3: callout labels are short text blocks, a figure over 75% of the page is the whole page, and nested figures are dropped. | 4 → 1 | 1 | Keep: 4 -> 1 on paired rows (base = round-2 drafts). The one left is the folio 'AT-7' inside the p283 image (Low). |
| 2026-10-06 | `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | v1.4 | `2b58bb4` fix(pipeline): do not take headings as vector figure labels (BUG-010) | Round 3: callout labels are short text blocks, a figure over 75% of the page is the whole page, and nested figures are dropped. | 5 → 2 | 0 | Keep: 5 -> 2. Titles are no longer cut; 10 rotated plates still lose the drawing number (graded Low, agreed rule says Medium). |
| 2026-10-06 | `DOC-0136477A` | v1.8 | `2b58bb4` fix(pipeline): do not take headings as vector figure labels (BUG-010) | Round 3: callout labels are short text blocks, a figure over 75% of the page is the whole page, and nested figures are dropped. | 0 → 0 | 0 | Keep: 0 -> 0 on paired rows. Long callout labels on p63, p68, p88 and p89 are now complete. |
| 2026-10-06 | `LOGIQ_S8` | v1.8 | `2b58bb4` fix(pipeline): do not take headings as vector figure labels (BUG-010) | Round 3: callout labels are short text blocks, a figure over 75% of the page is the whole page, and nested figures are dropped. | 3 → 8 | 6 | Keep with open work: 3 -> 8. The new rows are Low crop noise (extra text, neighbour photo slivers); p502 is still missing (Critical). |
| 2026-10-06 | `LOGIQ_e_R9_General_Service_Manual` | v1.9 | `2b58bb4` fix(pipeline): do not take headings as vector figure labels (BUG-010) | Round 3: callout labels are short text blocks, a figure over 75% of the page is the whole page, and nested figures are dropped. | 1 → 1 | 2 | Keep: 1 -> 1. The step line on p96 is still inside a crop (Low); the other regressions are table grading, not BUG-010. |
| 2026-10-06 | `Philips-MP20-MP90-Manual` | v2.11 | `2b58bb4` fix(pipeline): do not take headings as vector figure labels (BUG-010) | Round 3: callout labels are short text blocks, a figure over 75% of the page is the whole page, and nested figures are dropped. | 4 → 0 | 1 | Keep: 4 -> 0. Labels on p216, p305 and p354 are complete; p184 has body text in its crop (Low, not in the sample). |
| 2026-10-06 | `LOGIQ_S8` | v1.11 | `6eddaf1` fix(section_matcher): match headings with subscripts by text without spaces (BUG-019) | Drawings in table cells are kept (only straight grid lines are dropped); marks drawn on a photo are rendered with the photo. | 2 → 0 | 0 | Keep: the p502 cover drawing is back (Critical row now PASS). New Low: a strip of marks on p613. |
| 2026-10-07 | `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | v1.6 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 2 → 2 | 0 | No change: 2 -> 2 FAIL on paired rows. Still open in this manual. |
| 2026-10-07 | `DOC-0136477A` | v1.12 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 1 → 1 | 0 | No change: 1 -> 1 FAIL on paired rows. Still open in this manual. |
| 2026-10-07 | `Philips-MP20-MP90-Manual` | v2.15 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 4 → 3 | 9 | Better: 4 -> 3 FAIL on paired rows. The rest is still open. |
| 2026-10-07 | `LOGIQ_e_R9_General_Service_Manual` | v1.13 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 1 → 2 | 2 | 1 -> 2 FAIL on paired rows. The lead found no change in the tree; the new rows come from stricter grading. |
| 2026-10-07 | `2002_Service_Manual_TI` | v2.11 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 12 → 1 | 13 | Better: 12 -> 1 FAIL on paired rows. The rest is still open. |
| 2026-10-07 | `LOGIQ_S8` | v1.12 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 8 → 6 | 7 | Better: 8 -> 6 FAIL on paired rows. The rest is still open. |

<!-- generated:occurrences:start -->
## Where it was seen

_Generated by `qa/_scripts/build_bug_registry.py`; do not edit this block. Full rows with evidence: [occurrences.csv](occurrences.csv). `draft` rows are unapproved agent drafts._

| Manual | Version | Official FAIL | Draft FAIL | Top severity | Sections (pages sampled) |
|---|---|---:|---:|---|---|
| `2002_Service_Manual_TI` | v2.12 | 3 | 0 | Low | sec_0002 (p1), sec_0145 (p288), sec_0180 (p435) |
| `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | v1.7 | 3 | 0 | Low | sec_0019 (p77), sec_0020 (p109, 126) |
| `DOC-0136477A` | v1.13 | 2 | 0 | Medium | sec_0024 (p39), sec_0279 (p240) |
| `LOGIQ_S8` | v1.14 | 25 | 0 | Low | sec_0001 (p1), sec_0026 (p126), sec_0028 (p140), sec_0029 (p160), sec_0038 (p198), sec_0039 (p207), sec_0074 (p390), sec_0083 (p491), sec_0084 (p504, 510), sec_0086 (p555), sec_0087 (p572), sec_0088 (p576, 578), sec_0092 (p598), sec_0093 (p612), sec_0095 (p618, 629), sec_0097 (p639), sec_0099 (p659), sec_0104 (p686), sec_0110 (p726), sec_0121 (p788), sec_0135 (p880) |
| `LOGIQ_e_R9_General_Service_Manual` | v1.14 | 5 | 0 | Medium | sec_0015 (p82), sec_0020 (p96), sec_0051 (p383), sec_0074 (p492), sec_0082 (p540) |
| `Philips-MP20-MP90-Manual` | v2.17 | 9 | 0 | Medium | sec_0026 (p31), sec_0245 (p161), sec_0623 (p327), sec_0634 (p333), sec_0668 (p351), sec_0731 (p381), sec_0733 (p383), sec_0807 (p420) |
<!-- generated:occurrences:end -->
