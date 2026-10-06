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
- sec_0145 p288 `5.5-filters_passing_noise`: approved base = FAIL Low. Base evidence: vector img_0188 (p283) holds the page folio "AT-7" and code "B3H2271A" under the diagram; graded once for the section. Render p283 is in `pages/`. Same image in this version, so keep FAIL Low unless the image clearly has no folio.
- sec_0146 p300 `5.6-table_content`: check the p299 table (`pages/sec_0146_p299.png`). In the tree the group label "AWD transfer clutch control" is missing, so "Ordinary transfer control" etc. look like "Oil pressure control" items. Grade by rule 2 (expected Medium) and keep the p303 placeholder point too.
