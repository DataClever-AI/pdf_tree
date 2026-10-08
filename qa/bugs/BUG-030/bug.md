---
bug_id: BUG-030
status: mitigated
finding: H-17
fix_branch: fix/BUG-030-table-lost-lines
fix_commit: 476da09
updated: 2026-10-08
---

# BUG-030 · Printed table text is lost: a line inside the table area is in no cell and in no text node

**Suspected module:** src/tree_builder/docling_extract.py (TableFormer drops the row; fix in src/tree_builder/table_lines.py)

## Description

A printed line inside a table is lost: it is in no table cell and in no text node of the tree. It can be a footnote row that spans all columns, a legend row under the table, a row in the middle of the table, or a line of a cell. A RAG consumer cannot answer questions that need this text.

Examples:

- DOC-0136477A p178, Table 13-7 (sec_0217). The footnote row "* These are latching faults. Touch the silence icon to silence. To clear, restart monitoring." is in no node. The `*` marks in the table point to nothing.
- Philips p443 (sec_0820). The row "Gain 2.0, Range 5.3 to 6.1 seconds, Average 5.7 seconds" is missing in the middle of the table.
- LOGIQ_e p36 (sec_0003). The legend row "Note: X: Support; N: Not Applicable" under Table 1-4 is lost.
- AUTOMATIC p27 and p31 (sec_0015, sec_0016). The row "2-4 brake timing valve A" and its description are lost.

On 2026-10-08 the scope grew from footnote rows to all lost table lines (decision D1 of the reviewer, Oscar Munoz). The four lost-row cases above were first filed under BUG-008.

## Root cause

Confirmed on 2026-10-08. The words are in the PDF text layer, inside the table box. TableFormer makes no cell for them, and Docling keeps no text item for text inside a table area. Both table readers (PyPdfium and docling-parse, see BUG-008) drop the same lines.

Out of scope here: cells that are shifted by one row (AUTOMATIC p27) and deformed text such as "CO 2" or "pres- sure". Those are other causes.

## What was done

- 2026-10-07: found in the final re-measurement (DOC v1.12, agent review). The defect is in the tree since v1; older reviews did not grade it. The reviewer (Oscar Munoz) approved the row as FAIL Critical (lost table row whose text is nowhere else in the tree) and asked for a new bug. Registered in `root_causes.json` with an override for `DOC-0136477A|sec_0217|5.6-table_content`.

## Fix

Branch `fix/BUG-030-table-lost-lines`, commit `476da09`. New step `src/tree_builder/table_lines.py`, called after the docling-parse table re-read:

1. Read the PyMuPDF words inside the table box. Skip words owned by other Docling items and overprinted copies.
2. Split the words into lines and phrases at cell boxes and column gaps.
3. A phrase is lost when its text is not in the cells, its longest run in the cells is under 80 %, and (inside a row) most of its words are missing from that row.
4. A lost phrase goes into the cell of its row and column, or into a new row after the row printed above it.

Simulation on the table pages of the 7 manuals: about 136 lines recovered in 66 of 1,196 tables, including the four examples above. Plan: `../doc/PLAN_FASE3_TABLAS_2026-10-08_pdf_tree.md`.

## Verification

2026-10-08, versions at `476da09`, approved and finalized by the reviewer:

- Critical table rows that were lost now come back: AUTOMATIC p27/p31 (still Medium for the BUG-008 shift), LOGIQ_e p36, DOC p178 and Philips p443 (PASS).
- Philips sec_0846 p469 is a new Critical: those rows were lost before but never graded. Their names come back now, and their values come back with `f8f9c00`.
- Not measured yet (Phase 4): `4d7bebf` (column of a line that starts just before a cell edge), `8701492` (header word of a lost column) and `f8f9c00` (short values of a lost row). The simulation shows they remove the wrong-column Medium rows of DOC p218 and LOGIQ_S8.

## Attempts

| Date | Manual | Version | Commit | Change | Before → After | Regressions | Decision |
|---|---|---|---|---|---|---|---|
| 2026-10-08 | `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | v1.7 | `476da09` fix(docling_extract): recover table lines missing from cells (BUG-030) | New step table_lines puts printed table lines that are in no cell back into the table, in their row and column or in a new row. | 0 → 0 | 2 | The lost row '2-4 brake timing valve A' is back on p27 and p31. These rows are counted under BUG-008 (cells shifted), so 0 → 0 here; see the BUG-008 attempt. The 2 regressions are rule changes, not code: the empty formulas on p148 (BUG-035) and a line-break hyphen row (BUG-036). |
| 2026-10-08 | `LOGIQ_e_R9_General_Service_Manual` | v1.14 | `476da09` fix(docling_extract): recover table lines missing from cells (BUG-030) | New step table_lines puts printed table lines that are in no cell back into the table, in their row and column or in a new row. | 1 → 0 | 2 | Keep. The legend row on p36 (sec_0003) is back; Critical to PASS. |
| 2026-10-08 | `DOC-0136477A` | v1.13 | `476da09` fix(docling_extract): recover table lines missing from cells (BUG-030) | New step table_lines puts printed table lines that are in no cell back into the table, in their row and column or in a new row. | 2 → 3 | 1 | Keep. The footnote row on p178 (sec_0217) is back. The phone on p218 is back in the wrong column (Medium); fixed later in 4d7bebf, measured in Phase 4. Weighted (Critical 8, Medium 2): BUG-030 10 → 5. |
| 2026-10-08 | `Philips-MP20-MP90-Manual` | v2.17 | `476da09` fix(docling_extract): recover table lines missing from cells (BUG-030) | New step table_lines puts printed table lines that are in no cell back into the table, in their row and column or in a new row. | 2 → 4 | 1 | Keep. The row 'Gain 2.0' on p443 is back (Critical to PASS). sec_0846 p469 is a Critical that was never graded before: the country names are back, their values only with f8f9c00 (Phase 4). More rows because sec_0781 and sec_0815 now cite BUG-030 instead of BUG-008. Weighted: BUG-030 9 → 13, BUG-008 18 → 10, together 27 → 23. |
| 2026-10-08 | `LOGIQ_S8` | v1.14 | `476da09` fix(docling_extract): recover table lines missing from cells (BUG-030) | New step table_lines puts printed table lines that are in no cell back into the table, in their row and column or in a new row. | 0 → 3 | 5 | Keep. Lost lines in the parts tables and the EU address on p75 are back. Header words of lost columns went to a neighbour cell (Medium); fixed later in 8701492, measured in Phase 4. Weighted: BUG-030 0 → 6 (3 Medium for wrong placement, a small regression of this commit), BUG-008 43 → 42. |
| 2026-10-08 | `2002_Service_Manual_TI` | v2.12 | `476da09` fix(docling_extract): recover table lines missing from cells (BUG-030) | New step table_lines puts printed table lines that are in no cell back into the table, in their row and column or in a new row. | 0 → 0 | 7 | Keep. Only partial recoveries in 2002 (p51, p110, p254); no row fixed, no regression from the code. |
| 2026-10-08 | `SOMATOM_Force_IFU_VB30` | v1.12 | `476da09` fix(docling_extract): recover table lines missing from cells (BUG-030) | New step table_lines puts printed table lines that are in no cell back into the table, in their row and column or in a new row. | 0 → 0 | 2 | Keep. One line back on p270 (not sampled); no change on paired rows. |

<!-- generated:occurrences:start -->
## Where it was seen

_Generated by `qa/_scripts/build_bug_registry.py`; do not edit this block. Full rows with evidence: [occurrences.csv](occurrences.csv). `draft` rows are unapproved agent drafts._

| Manual | Version | Official FAIL | Draft FAIL | Top severity | Sections (pages sampled) |
|---|---|---:|---:|---|---|
| `DOC-0136477A` | v1.13 | 3 | 0 | Medium | sec_0217 (p177), sec_0261 (p218), sec_0272 (p225) |
| `LOGIQ_S8` | v1.14 | 3 | 0 | Medium | sec_0001 (p24), sec_0012 (p76), sec_0121 (p788) |
| `Philips-MP20-MP90-Manual` | v2.17 | 4 | 0 | Critical | sec_0612 (p320), sec_0781 (p402), sec_0815 (p428), sec_0846 (p469) |
<!-- generated:occurrences:end -->
