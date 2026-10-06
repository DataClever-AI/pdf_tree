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
- sec_0121 p788 `5.5-filters_passing_noise`: approved base = FAIL Low (vector crops on p789 and p792 overlap or hold parts of a neighbour figure). Renders p789/p792 in `pages/`. Keep FAIL Low.
- sec_0122 p802 `5.6-table_content`: renders of p798 and p806 are now in `pages/`. Confirm the p798 Qty problem. Also on p806 (Table 9-7) the Description cell lost "Kit including DVD" and "Printer USB cable," (tree: 'SATA signal cable and power cable, as well as dual printer power cable'). Medium by rule 2.
- sec_0128 p837 `5.6-table_content`: check p838 (render in `pages/`). In the tree the row 'Option | 5756406 | Fibroscan Probe Holder | Active ...' is missing, and 'Replace with 5761961' sits on the 5761961 row instead of the 5409146 row. Medium by rule 2.
- sec_0126 p827 `5.6-table_content`: p826 render is in `pages/`; keep your Biopsy finding if confirmed.
