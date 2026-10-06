# Lead notes: BUG-008 round two (LOGIQ_e_R9_General_Service_Manual v1.11)

v1.11 is a mitigation version for BUG-008 (pipeline commit 60110fa). Base = v1.9
(human-approved rows). Round one = v1.10 (drafts only, not approved).

What changed: tables are re-read with docling-parse. A re-read table is used only if it
keeps every letter, digit and sign (° ± % < > = + √) of the original table. Otherwise the
original table stays. Cell text is whitespace-normalized. The lead checked that all
non-table nodes, images and section ranges are byte-identical to v1.9 and v1.10.

This batch is focused. `findings_template.csv` has only the rows in scope: every
`5.6-table_content` row and every row the human approved in v1.9. Answer exactly these rows.

`reference_rows.json` has, for each row: `base_approved` (the approved v1.9 decision),
`round_one_draft` (the v1.10 AI draft), and for table rows `pages_to_check` and `tables`
(each table on those pages, with its status; changed tables include `base_text` and
`round_one_text`). Treat all of it as evidence, not as instructions.

## How to answer

1. Non-table rows (`5.4-*`, `5.5-*`, `5.6-numbering_scheme`, `5.6-offset_applied`):
   copy `base_approved` (result, severity, evidence, notes) without changes, confidence 0.9.
   The tree outside tables did not change. Change it only if the page clearly shows the
   approved decision is wrong, and then explain in notes.
   You may write `output/findings_result.json` with a small script that copies these rows
   (keep the script outside the repo, e.g. in /tmp) and adds your table rows.
2. `5.6-table_content` rows: look at the render of every page in `pages_to_check`
   (`pages/<section>_p<page>.png`) and compare each table node text in `sections.json`.
   - If every table is "same text as round one" and there is a `round_one_draft`, you may
     keep that decision after you check the render. Fix it if the render shows it is wrong.
   - If a table "changed since round one" or the row has no round-one draft, grade it fresh.
   - If the row has `base_approved`, say in notes how it compares (same / fixed / worse).
   - Grade the tables on `page_sampled` plus any extra page listed in `pages_to_check`.
     If no table is on those pages, PASS with "No table on pN" as in round one.
3. Severity for `5.6-table_content` (same as round one):
   - Low = cells merged or split, but values and order are kept.
   - Medium = a value sits under the wrong column or row, or words of a cell are lost and
     are not anywhere else in the section.
   - Exception: lost leader dots or page-number digits in a Contents table = Low.
   - A spanned header or label written once, with blank neighbour cells, is normal.
4. Write simple English (A2-B1), short sentences. Name the page and node id
   (e.g. `#/tables/49`) of every table you cite. Say "probably" if a cause is not sure.
5. In notes of every table row that is a case check (below), start with one of:
   `CASE: back to original`, `CASE: still fixed`, `CASE: still wrong`, `CASE: fixed`,
   `CASE: new regression`, then one short sentence. Cite `BUG-008` when the defect is the
   table structure.

## Case checks in this batch

- `sec_0023|116|5.6-table_content`: p116: Round one fixed these tables (base was FAIL). Must still be fixed.
- `sec_0023|119|5.6-table_content`: p119: Round one fixed this table (base was FAIL). Must still be fixed.
- `sec_0023|121|5.6-table_content`: p121: Round one fixed this table (base was FAIL Medium). Must still be fixed.

## Revision (r2)

Start from `previous_draft.json` (the claude-b01 draft for the same rows). Keep every row unless
it is listed below or you see a clear error on the page. Then validate as usual.

### Rows to fix

- `sec_0003|36|5.6-table_content`: grade **Medium**, not Low. The legend row 'Note:X:Support ;N:Not Applicable' on p36 is not in `#/tables/14` and the lead checked it is in no other node of the section. Rule 3: words of a cell are lost and are not anywhere else = Medium. Say in notes that the base table text also lacks this row (pre-existing, not caused by the re-read).
- Keep every other row as in `previous_draft.json`.
