---
bug_id: BUG-008
status: mitigated
finding: H-13
fix_branch: fix/BUG-008-table-text
fix_commit: 076dadd
updated: 2026-10-08
---

# BUG-008 · Table header cells merge/reorder during extraction, breaking column-to-value attribution

**Suspected module:** src/tree_builder/docling_extract.py (PyPdfium text runs + TableFormer cell matching; confirmed)

## Description

Table header cells or adjacent columns are merged or reordered during extraction, which breaks column-to-value attribution (e.g. Philips p363 'Max Wave 1' + 'Max numeric 2' read as '12').

## Root cause

Confirmed (2026-10-06). TableFormer finds the right rows and columns. The text goes wrong after that. The pipeline reads the PDF with `PyPdfiumDocumentBackend`, which gives text as whole line runs. With cell matching, a run that crosses two columns goes into one cell: Philips p363 '1' + '2' becomes '12', DOC p135 bullets of three columns become '•••' in one cell, LOGIQ_e p116 '1 +20V 3 GND' is one cell. The same pages read with Docling's default backend (docling-parse, word-level text) give correct tables (6 of 6 test pages). TableFormer already runs in accurate mode.

## What was done

- 2026-09-04: identified in the v1 QA review of LOGIQ_e_R9 and consolidated by root cause in Task 2.3 (commit `3a4ec7f`).
- 2026-09-28: seen again in the agent review drafts of the v2 runs (2002 and Philips); pending approval by the human reviewer (Oscar Munoz).
- 2026-09-29: registered in the root-cause catalogue `qa/confidence_index/root_causes.json`.
- 2026-10-06: root cause confirmed and fixed (`076dadd`). DOC full run: 164 of 164 tables re-read; p135 correct.

## Fix

`076dadd` (`src/tree_builder/docling_extract.py`): after the windowed PyPdfium conversion, pages with tables are converted again with docling-parse, from an in-memory PDF of those pages only. Each table takes the cell data of the re-read table on the same page and place (IoU >= 0.5); a table without a match keeps its data. The rest of the text is not changed, so the reading-order fixes (BUG-005, 022, 029) are not affected. Cost: about 1.5 s per page with tables. Options not chosen: switching the whole backend (changes all text; an architecture decision) and turning off cell matching with PyPdfium (cuts characters at cell edges).

## Verification

Round one (`076dadd`, versions 2002 v2.8, DOC v1.9, LOGIQ_e v1.10, Philips v2.12, LOGIQ_S8 v1.9): fixed most merged cells but lost words, a spanning column or ° and ± signs in some tables; not approved. Round two with the text guard (`60110fa`, versions 2002 v2.9, DOC v1.10, LOGIQ_e v1.11, Philips v2.13, LOGIQ_S8 v1.10), approved by the reviewer on 2026-10-06: 18 -> 5 FAIL on paired rows, no lost text. Open: LOGIQ_S8 p618 and p798, DOC p27 (text in the wrong cell); Philips p305 row labels; good re-reads rejected by the guard (DOC p205, LOGIQ_e p441, LOGIQ_S8 p367, p28, p832).

## Attempts

| Date | Manual | Version | Commit | Change | Before → After | Regressions | Decision |
|---|---|---|---|---|---|---|---|
| 2026-10-06 | `2002_Service_Manual_TI` | v2.9 | `60110fa` fix(docling_extract): keep the original table when the re-read loses text (BUG-008) | Table pages are read again with docling-parse; a re-read table is used only when it keeps all the text of the original. | 5 → 1 | 0 | Keep: 5 -> 1 on paired rows, no regressions. p51 still lacks the Input/Output signal labels, as in the base. |
| 2026-10-06 | `DOC-0136477A` | v1.10 | `60110fa` fix(docling_extract): keep the original table when the re-read loses text (BUG-008) | Table pages are read again with docling-parse; a re-read table is used only when it keeps all the text of the original. | 1 → 0 | 0 | Keep: 1 -> 0 on paired rows, no regressions. p27 keeps text in the wrong row (Medium). |
| 2026-10-06 | `LOGIQ_e_R9_General_Service_Manual` | v1.11 | `60110fa` fix(docling_extract): keep the original table when the re-read loses text (BUG-008) | Table pages are read again with docling-parse; a re-read table is used only when it keeps all the text of the original. | 6 → 0 | 0 | Keep: 6 -> 0 on paired rows, no regressions. p36 still misses the X/N legend row, as in the base. |
| 2026-10-06 | `Philips-MP20-MP90-Manual` | v2.13 | `60110fa` fix(docling_extract): keep the original table when the re-read loses text (BUG-008) | Table pages are read again with docling-parse; a re-read table is used only when it keeps all the text of the original. | 3 → 1 | 0 | Keep: 3 -> 1 on paired rows, no regressions. The one left is p305 row labels that span rows (Low). |
| 2026-10-06 | `LOGIQ_S8` | v1.10 | `60110fa` fix(docling_extract): keep the original table when the re-read loses text (BUG-008) | Table pages are read again with docling-parse; a re-read table is used only when it keeps all the text of the original. | 3 → 3 | 2 | Keep with open work: 3 -> 3. Two FAILs come from extra pages the base did not grade (p28, p367); p418 adds a NOTE row (Low). |
| 2026-10-07 | `DOC-0136477A` | v1.12 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 6 → 7 | 2 | 6 -> 7 FAIL on paired rows. The lead found no change in the tree; the new rows come from stricter grading. |
| 2026-10-07 | `Philips-MP20-MP90-Manual` | v2.15 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 11 → 12 | 3 | 11 -> 12 FAIL on paired rows. The lead found no change in the tree; the new rows come from stricter grading. |
| 2026-10-07 | `LOGIQ_e_R9_General_Service_Manual` | v1.13 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 3 → 4 | 2 | 3 -> 4 FAIL on paired rows. The lead found no change in the tree; the new rows come from stricter grading. |
| 2026-10-07 | `2002_Service_Manual_TI` | v2.11 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 8 → 8 | 1 | No change: 8 -> 8 FAIL on paired rows. Still open in this manual. |
| 2026-10-07 | `LOGIQ_S8` | v1.12 | `211981b` feat(qa): add --all-fails to check every standing FAIL row in a mitigation version | Final re-measurement with all fixes on the integration branch (pipeline 211981b). The sample has every row that was still FAIL. | 25 → 28 | 7 | 25 -> 28 FAIL on paired rows. The lead found no change in the tree; the new rows come from stricter grading. |
| 2026-10-08 | `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | v1.7 | `476da09` fix(docling_extract): recover table lines missing from cells (BUG-030) | New step table_lines puts printed table lines that are in no cell back into the table, in their row and column or in a new row. (BUG-030) | 2 → 2 | 2 | Keep. sec_0015 p25 and sec_0016 p29 go from Critical to Medium: the lost row is back, the one-row cell shift stays (out of scope). |

<!-- generated:occurrences:start -->
## Where it was seen

_Generated by `qa/_scripts/build_bug_registry.py`; do not edit this block. Full rows with evidence: [occurrences.csv](occurrences.csv). `draft` rows are unapproved agent drafts._

| Manual | Version | Official FAIL | Draft FAIL | Top severity | Sections (pages sampled) |
|---|---|---:|---:|---|---|
| `2002_Service_Manual_TI` | v2.12 | 12 | 0 | Medium | sec_0002 (p1), sec_0004 (p8), sec_0005 (p14), sec_0006 (p21), sec_0011 (p54), sec_0018 (p88), sec_0052 (p141), sec_0084 (p181), sec_0089 (p208), sec_0122 (p253), sec_0188 (p476), sec_0232 (p589) |
| `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | v1.7 | 2 | 0 | Medium | sec_0015 (p25), sec_0016 (p29) |
| `DOC-0136477A` | v1.13 | 8 | 0 | Medium | sec_0008 (p19, 21), sec_0015 (p27), sec_0024 (p39), sec_0068 (p71), sec_0243 (p202), sec_0245 (p206), sec_0252 (p214) |
| `LOGIQ_S8` | v1.14 | 32 | 0 | Medium | sec_0014 (p77), sec_0044 (p239), sec_0060 (p283), sec_0063 (p304), sec_0066 (p360), sec_0072 (p384), sec_0074 (p418), sec_0079 (p478), sec_0086 (p556, 558), sec_0088 (p578), sec_0095 (p618, 629), sec_0104 (p686), sec_0107 (p699), sec_0109 (p712, 721), sec_0110 (p726), sec_0111 (p753, 756, 757), sec_0116 (p774), sec_0122 (p802), sec_0123 (p809), sec_0124 (p817), sec_0125 (p823), sec_0126 (p827, 828), sec_0127 (p830), sec_0128 (p837), sec_0130 (p873), sec_0138 (p909) |
| `LOGIQ_e_R9_General_Service_Manual` | v1.14 | 3 | 0 | Medium | sec_0005 (p43), sec_0063 (p443), sec_0083 (p549) |
| `Philips-MP20-MP90-Manual` | v2.17 | 9 | 0 | Medium | sec_0103 (p68), sec_0527 (p282), sec_0583 (p303), sec_0585 (p305), sec_0646 (p339), sec_0652 (p343), sec_0682 (p359), sec_0690 (p363), sec_0820 (p442) |
| `SOMATOM_Force_IFU_VB30` | v1.12 | 4 | 0 | Medium | sec_0001 (p2), sec_0673 (p329), sec_0710 (p350), sec_0851 (p406) |
<!-- generated:occurrences:end -->
