# Phase 3 context for this batch (from the lead; evidence rules, not new checklist items)

Version v2.12 is a mitigation of BUG-030 and BUG-008 on base v2.11 (approved, finalized).
Pipeline commit 476da09. The only code change: a printed table line inside the table box that
Docling put in no cell is now recovered. It goes into the cell of its row and column, or into a
new row at its height.

What changed against v2.11 (checked by the lead with a full diff):
- 0 nodes moved between sections. 0 nodes added or removed.
- images_v1.json is byte-identical to v2.11 (487 images, same pages, sections and pixels).
- Only 4 table nodes changed their text in the whole tree: p17 sec_0005 #/tables/27,
  p51 sec_0011 #/tables/32, p110 sec_0030 #/tables/40 (not sampled), p254 sec_0122 #/tables/55.
So for every other row, v2.11 is the expected baseline. Still check the rendered pages.
`prior_v2.11.json` lists the v2.11 FAIL rows of your sections and the keys that are new in
this template (no v2.11 row). All other v2.11 rows of your sections were PASS.

Extra rendered pages: `pages/` also has every page of your sections that holds a table node,
so you can judge `5.6-table_content` on the real page.

Out of scope for this fix (do not expect them fixed; grade them as before):
- cells shifted by one row, merged cells, values under the wrong column (BUG-008);
- deformed text: 'CO 2', '45 ° C', 'pres- sure', 'com\x02 pressor' (planned Phase 4);
- header words of a column that Docling lost entirely.

Grading rules (human reviewer decisions; GUIA_EVALUACION 5.4, RESUMEN_SESION_MITIGACION 6-6i):
- Content in the wrong section = Critical, graded on both sections (receiver fails
  5.4-page_start_end, owner fails 5.4-gaps_duplicates). A lone label whose box is kept
  elsewhere = Medium.
- Figure lost = Critical. Figure cut, or unique info lost = Medium. Extra text in a crop = Low.
- Decorative icon not extracted (the 'i' of a note, the triangle beside WARNING/CAUTION) = PASS
  (noise, rule 6i). This applies now even if v2.11 graded it Low: say so in notes.
  An icon with its own meaning (key, button, UI symbol) not extracted = Low.
- Lost table row whose text is nowhere else in the tree = Critical (BUG-030 if the text is
  printed in the table but is in no cell and no node).
- Values present but not under their column, cells merged or shifted = Medium if meaning or
  column attribution is lost; Low if order and values are still readable (BUG-008).
- If a lost line now comes back in a new row of its own table, with its text complete, the
  lost-row problem is fixed (PASS for that defect). If it comes back in the wrong column of
  its table = Medium.
- Recovered text must be printed in that table, not duplicated, and in a sensible row and
  column. Text added twice or put in the wrong row is a regression: say so clearly.
- Keep grades consistent with the approved v2.11 rows when the content did not change.
  If you keep a v2.11 FAIL, start notes with "Old FAIL (BUG-NNN, v2.11): still present." 

Writing: simple English (A2-B1), short sentences, one fact per sentence. Keep exact ids
(sec_0011, #/tables/32, p51). evidence = what you see. notes = why (BUG id if known, say
"probably" if not confirmed) and impact in one sentence.

No changed table in this batch.
