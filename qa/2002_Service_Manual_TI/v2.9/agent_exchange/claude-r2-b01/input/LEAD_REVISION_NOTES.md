# Lead notes: BUG-008 round two (2002_Service_Manual_TI v2.9)

v2.9 is a mitigation version for BUG-008 (pipeline commit 60110fa). Base = v2.7
(human-approved rows). Round one = v2.8 (drafts only, not approved).

What changed: tables are re-read with docling-parse. A re-read table is used only if it
keeps every letter, digit and sign (° ± % < > = + √) of the original table. Otherwise the
original table stays. Cell text is whitespace-normalized. The lead checked that all
non-table nodes, images and section ranges are byte-identical to v2.7 and v2.8.

This batch is focused. `findings_template.csv` has only the rows in scope: every
`5.6-table_content` row and every row the human approved in v2.7. Answer exactly these rows.

`reference_rows.json` has, for each row: `base_approved` (the approved v2.7 decision),
`round_one_draft` (the v2.8 AI draft), and for table rows `pages_to_check` and `tables`
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

- `sec_0005|14|5.6-table_content`: p15: Round one lost the row-group label 'Final reduction' (two times). Expected now: back to the original table (#/tables/21) with 'Final reduction'. Also check #/tables/20 on the same page (kept re-read).
- `sec_0011|54|5.6-table_content`: p51: Round one: the Signal column labels ('Input signals' / 'Output signals') are missing. The table text is the same as round one, because the base table also missed them (the guard compares with the base). Check if 'Input signals'/'Output signals' are anywhere in the section nodes. If not, words are lost: Medium.
- `sec_0018|88|5.6-table_content`: p84: Round one lost the Signal column ('Input signals'/'Output signals'). Expected now: back to the original table with these labels. Confirm.
- `sec_0089|208|5.6-table_content`: p209: Round one lost text in this table. Expected now: back to the original table (all text kept, cells may be merged). Confirm every word on the page is in the table.

## Revision (r2)

Start from `previous_draft.json` (the claude-b01 draft for the same rows). Keep every row unless
it is listed below or you see a clear error on the page. Then validate as usual.

### Rows to fix

- `sec_0004|8|5.6-table_content`: grade **Low**, not Medium. The option circles on p9-p12 are vector drawings, not text (the PDF page text has no circle characters), so they are not "lost words". In `#/tables/12`-`#/tables/15` the weights, dashes and values stay in reading order inside merged cells: rule 3 Low (cells merged, values and order kept). Round one also graded this row Low. Say in notes that the circles are drawings and that the tables are back to the original (base) text.
- `sec_0005|14|5.6-table_content`: grade **Low**, not Medium, for the same reason (circles on p17-p18 are drawings; `#/tables/27`, `#/tables/28` keep values and order in merged cells). Keep the note start `CASE: back to original` ('Final reduction' is back in `#/tables/21`).
- Keep every other row as in `previous_draft.json`.
