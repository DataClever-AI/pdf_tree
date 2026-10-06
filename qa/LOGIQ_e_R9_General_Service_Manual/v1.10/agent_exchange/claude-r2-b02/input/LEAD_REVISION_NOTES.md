# Lead revision notes (r2)

Start from `previous_draft.json` (the r1 draft for the same sections). Keep every row
unless it is listed below or you see a clear error on the page. Then validate as usual.

Rules for every manual in this review (so grades are the same everywhere):
1. This version changes only table cell text. `images_v1.json`, section page ranges and
   non-table nodes are identical to the approved base version. For a non-table row, the
   approved base decision quoted below stands unless the page clearly shows otherwise.
   A section-wide finding (seen on another page of the same section) is graded once, on
   the first sampled row of that section, as the base did.
2. `5.6-table_content` severity: Low = cells merged or split, values and order kept.
   Medium = a value sits under the wrong column or row, or words of a cell are lost and
   are not anywhere else. Exception: lost leader dots or page-number digits in a Contents
   (navigation) table = Low. A spanned header or label written once, with blank
   neighbour cells, is normal (not a defect).
3. Name the page of every table you cite. Simple English (A2-B1).

## Rows to fix
- sec_0051 p383 `5.4-page_start_end`: approved base = FAIL Low. Base evidence: node #/texts/4297 'Chapter 8' is on p397 (render now in `pages/`) and is owned by sec_0051; it is the chapter number of the next chapter. Only boilerplate crosses: Low.
- sec_0037 p248 `5.4-page_start_end`: same pattern ('Chapter 6' on p257, render in `pages/`). Grade it the same way as sec_0051 (FAIL Low) if the node is the chapter-number label.
