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
- sec_0001 p1 `5.6-numbering_scheme`: approved base = FAIL Medium. Base evidence: section labeled 'arabic' but node text shows roman folios on p3-p16 ('- i', 'ii -', 'iv -', 'viii -', '- xi', ...) and arabic folios from p17. Same nodes in this version. Keep FAIL Medium.
- sec_0001 p24 `5.6-table_content`: also check the Contents tables on p19, p27, p28 (renders in `pages/`). On p19 "and ANSI AAMI" is lost from the 'Patient Environment ...' title; on p27 and p28 page numbers are cut ('7 - 4' -> '7 | -', '7 - 82' -> '7 -'). Navigation table: Low (rule 2 exception). Add these to the evidence.
- sec_0028 p140 `5.5-filters_discarding`: approved base = FAIL Low (NOTICE triangle on p151 not extracted; meaning is in the text). Render p151 in `pages/`. Keep FAIL Low.
- sec_0028 p140 `5.5-filters_passing_noise`: approved base = FAIL Low (img_0119 p149 holds a heading and a caption at its edges; img_0121 p151 holds a step line). Renders p149/p151 in `pages/`. Keep FAIL Low.
- sec_0039 p207 `5.5-filters_passing_noise`: approved base = FAIL Low (img_0198 p210 holds a heading, two cut text lines, a caption and part of the footer). Render p210 in `pages/`. Keep FAIL Low.
- sec_0045 p246 `5.6-table_content`: the lost line "This port is capped with rubber cover." is cell text lost and not elsewhere: Medium by rule 2.
