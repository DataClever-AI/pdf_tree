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
- sec_0005 p14 `5.6-table_content`: check Table on p15 (`pages/sec_0005_p15.png`). In the tree the row-group label "Final reduction" (two times) is missing, so "Type of gear Hypoid" rows look like part of "1st reduction"/"Transfer reduction". Grade by rule 2 (expected Medium: values can no longer be attributed to their group).
- sec_0011 p57 / sec_0018 p88 `5.6-table_content`: renders of p51 and p84 are now in `pages/`. Confirm the lost "Signal" column ("Input signals"/"Output signals") on the page and raise confidence if confirmed.
- sec_0065 p159 `5.6-table_content`: TOC page number lost = navigation table, keep Low (rule 2 exception); say so in notes.
