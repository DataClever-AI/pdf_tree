# Lead notes: BUG-008 round two (Philips-MP20-MP90-Manual v2.13)

v2.13 is a mitigation version for BUG-008 (pipeline commit 60110fa). Base = v2.11
(human-approved rows). Round one = v2.12 (drafts only, not approved).

What changed: tables are re-read with docling-parse. A re-read table is used only if it
keeps every letter, digit and sign (° ± % < > = + √) of the original table. Otherwise the
original table stays. Cell text is whitespace-normalized. The lead checked that all
non-table nodes, images and section ranges are byte-identical to v2.11 and v2.12.

This batch is focused. `findings_template.csv` has only the rows in scope: every
`5.6-table_content` row and every row the human approved in v2.11. Answer exactly these rows.

`reference_rows.json` has, for each row: `base_approved` (the approved v2.11 decision),
`round_one_draft` (the v2.12 AI draft), and for table rows `pages_to_check` and `tables`
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

- `sec_0585|305|5.6-table_content`: p305: Row-spanning labels: check that each label (written once for several rows in the PDF) is kept and the values stay in their rows. Base was FAIL Medium.
- `sec_0607|315|5.6-table_content`: p316: Round one fixed this table (base FAIL Medium on p315 row). Must still be fixed.

## Revision (r2)

Start from `previous_draft.json` (the claude-b02 draft for the same rows). Keep every row unless
it is listed below or you see a clear error on the page. Then validate as usual.

### Rows to fix

- `sec_0585|305|5.6-table_content`: grade **Low**, not Medium. The lead checked the p305 render: the multi-line labels ('Average trend / 20 minutes, five samples per minute', 'HiResTrnd / Four minutes, ...', 'Realtime Wave Snapshot / 15 seconds') are split line by line over the rows next to them, in the same visual order as the page. All Pre-time and Post-time values are in the right column and row. This is "cells merged or split, values and order kept" = Low, as round one graded it. Keep `CASE: still wrong` only if you still see a defect; otherwise write `CASE: fixed` relative to the base Medium (Pre/Post are now separate). If `verify_claims.py` flags SEVERITY, justify Low in notes with this reason.
- Keep every other row as in `previous_draft.json`.
