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
- sec_0066 p355 `5.4-page_start_end`: approved base = FAIL Low (on p350 'Section 7-7' and the running-header lines are not in sec_0066; boilerplate only). Render p350 in `pages/`. Keep FAIL Low.
- sec_0074 p390 `5.5-filters_passing_noise`: approved base = FAIL Low (img_0488 p452 and img_0497 p456 hold the step line '19.) Press Submit.' at the top edge). Render p452 in `pages/`. Keep FAIL Low.
- sec_0083 p491 `5.5-filters_discarding`: approved base = FAIL Critical. Base evidence: on p502 Table 8-39 has a 'Corresponding Graphic' drawing of the arm covers with part numbers 1-6; images.json has no image on p502; the table keeps only '3 2 4 5 6'. Render p502 in `pages/`. The p491 photos are fine, but this is a section-wide finding: keep FAIL Critical unless p502 shows no such drawing.
- sec_0083 p491 `5.5-filters_passing_noise`: approved base = FAIL Low (img_0543 p491 holds the heading '8-15-3-2 Remove Procedure', table header and step text). Keep FAIL Low.
- sec_0104 p686 `5.6-table_content`: check p687 (render in `pages/`). In the tree the Corresponding Graphic label "Unplug the cables" became "cables". Grade by rule 2.
