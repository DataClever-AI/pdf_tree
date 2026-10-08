# Phase 3 context for DOC-0136477A v1.13 (from the lead, not from the PDF)

- v1.13 is a mitigation version of v1.12 (approved and finalized). Pipeline commit 476da09. Targets: BUG-030, BUG-008, BUG-023.
- The template was built with --all-fails: every row that was FAIL in any older version is included. `prior_fails.json` lists the approved FAIL rows of the latest review (mostly v1.12) and older FAILs that later became PASS. Context only: re-check each one on the v1.13 renders and tree.json data. Keep the same grade as v1.12 when the content did not change.
- New in this pipeline (BUG-030, widened): a printed table line inside the table box that Docling put in no cell is recovered. It goes into the cell of its row and column, or into a new row at its height.
- Out of scope (do not expect them fixed): cells shifted by one row (BUG-008); deformed text such as 'CO 2', '45 ° C', 'pres- sure', '\x02' (planned Phase 4); header words of a column Docling lost entirely.
- Tables whose text changed vs v1.12: p177 sec_0217 #/tables/91; p178 sec_0217 #/tables/92; p194 sec_0234 #/tables/119; p218 sec_0261 #/tables/151; p224 sec_0272 #/tables/156; p226 sec_0272 #/tables/158; p228 sec_0273 #/tables/160. For each changed table in your batch, compare it with the rendered page: the recovered text must be printed in that table, not duplicated, and in a sensible row/column. Text added twice or put in the wrong row is a regression: say so in the evidence.
- Nodes that changed section vs v1.12 (Phase 0/2 changes, BUG-023 text above a heading): #/texts/178 p28 sec_0020 -> sec_0019; #/texts/1109 p82 sec_0087 -> sec_0085; #/texts/2208 p144 sec_0176 -> sec_0175 (in v1.12 this fragment of step 4 was a Critical in sec_0176, BUG-023). Check them on the render if they touch your sections.
- Images may differ from v1.12 (Phase 0 image filter, BUG-011/020). New images vs v1.12: p2 (86x42, front matter, no section) and p81 sec_0084 (265x40). No image was removed.

## Grading rules (human reviewer decisions)
- Content in the wrong section = Critical, graded on both sections: the receiver fails 5.4-page_start_end, the owner fails 5.4-gaps_duplicates. A lone label whose box is kept elsewhere = Medium.
- Only boilerplate crossing a boundary (chapter number, tab label, running header, folio) = Low (BUG-022).
- Figure lost = Critical; figure cut or unique info lost = Medium; extra text in a crop = Low.
- A decorative icon not extracted (the 'i' of a note, the triangle beside WARNING/CAUTION) = PASS (noise). An icon with its own meaning (key, button, UI symbol) not extracted = Low (usually BUG-017).
- Decorative element (footer rule, logo) kept as an image = Low (5.5-filters_passing_noise).
- Lost table row whose text is nowhere else = Critical (BUG-030). If a lost line now comes back in a new row of its own table with complete text, the lost-row defect is fixed (PASS for that defect). If it comes back in the wrong column of its table = Medium.
- Values present but not under their column, cells merged or shifted = Medium (BUG-008). Cells merged but values and order kept = Low.
- evidence and notes in simple English (A2-B1): short sentences, one fact per sentence, exact ids and pages, cite the BUG id when known, say "probably" when the cause is not confirmed.
- Extra renders of p223 and p224 (sec_0272 range 222-226) are in input/extra_pages/.
