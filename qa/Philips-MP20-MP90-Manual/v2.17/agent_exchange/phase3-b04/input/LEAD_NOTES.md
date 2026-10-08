# Lead notes for this batch (Philips v2.17, Phase 3)

These notes come from the lead. They describe the version and the grading rules the human
reviewer already decided. They are context, not a reason to skip the visual check.

## What changed vs v2.16 (the approved, finalized base)

- Pipeline change (BUG-030, widened): a printed table line inside the table box that Docling
  put in no cell is now recovered. It goes into the cell of its row and column, or into a new
  row at its height.
- Out of scope, do not expect them fixed: cells shifted by one row (BUG-008); deformed text
  such as 'CO 2', '45 ° C', 'pres- sure', 'mVp Vpp', '\x02' (planned Phase 4); header words of
  a column that Docling lost entirely.
- The lead checked the trees: 0 nodes moved to another section, no section field changed,
  images_v1.json is identical to v2.16. Only the text of 14 tables changed.
- Changed tables in this batch (renders of their pages are in `pages/` or `extra_pages/`):

- `sec_0140` p101 `#/tables/40`
- `sec_0140` p109 `#/tables/48`

```text
== #/tables/40
@@ -8,2 +8,3 @@
 NBP MEASURE FAILED Numeric may be displayed with a -?- INOP tone. | NBP | Check that you are using the correct cuff size and placement, and that the correct patient category is selected. Try restarting the measurement. You can silence this INOP, but the INOP message remains visible until the next measurement is started or the Stop All SmartKey is selected. Check the condition and suitability of t
+ |  | monitoring. Use another cuff to continue measuring.
 No Central Monit. INOP tone | Monitor | There is a problem with the communication to the network. Central monitoring is currently not possible (no patient alarms or information). Check the connection. Contact your service personnel.
== #/tables/48
@@ -12,2 +12,3 @@
 <Temp label> DEACTIVATED INOP tone | TEMP | A Temp measurement label in the measurement device has been deactivated, either by connecting a Pressure transducer in the shared Press/Temp socket, or by deactivating the label in the Measurement Selection window. The measurement automatically disappears from the display. To switch the measurement on again, either reconnect a Temp transducer or reactiv
+ |  | Measurement Selection window.
 <Temp label> EQUIP MALF Numeric is replaced by -?- INOP tone. | TEMP | Contact your service personnel. The temperature hardware is faulty.
```

## How to use `base_v2.16_approved_findings.csv`

It has the human-approved v2.16 rows for the same keys as your template (rows that are new in
v2.17 are not in it). Check every row again on the rendered page. If the content did not
change, keep the same result and severity as v2.16, unless you see clear visible evidence that
v2.16 was wrong (then explain it in `notes`). Write your own evidence; do not copy blindly.
For a changed table, say in `notes` what changed vs v2.16 (fixed / still present / new).

## Grading rules (human reviewer decisions)

- Content in the wrong section = Critical, graded on both sections: the receiving section
  fails `5.4-page_start_end`, the owner fails `5.4-gaps_duplicates`.
- A lone label (for example 'WARNING') whose box is kept elsewhere = Medium.
- Figure lost = Critical. Figure cut, or unique info lost = Medium. Extra text in a crop = Low.
- A decorative icon not extracted (the 'i' of a note, the triangle beside WARNING/CAUTION) =
  PASS (noise). An icon with its own meaning (key, button, UI symbol) not extracted = Low.
- Lost table row whose text is nowhere else = Critical (BUG-030 when the line is printed in the
  table box but is in no cell and no node).
- Values present but not under their column, or cells shifted / merged so a value cannot be
  tied to its row or column = Medium (BUG-008). Merged cells with order and values kept = Low.
- If a lost line now comes back in a new row of its own table, with its text complete, the
  lost-row problem is fixed (PASS for that defect). If it comes back in the wrong column of its
  table = Medium.
- Recovered text that is duplicated, put in the wrong row, or not printed in that table is a
  regression: grade it (Low if only cosmetic, Medium if a value is no longer tied to its row).
- `5.6-table_content` covers every table node of the section, also on pages that are not the
  sampled page.

## Writing style (mandatory)

Simple technical English (A2-B1). Short sentences, one fact each, about 20 words or less.
Keep exact names (`sec_0820`, `#/tables/216`, p443). `evidence` = what you see and what is
right or wrong. `notes` = probable cause with the BUG id (for example BUG-030, BUG-008) and
the impact in one sentence. Say "probably" when the cause is not confirmed.
