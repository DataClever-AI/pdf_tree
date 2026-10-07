# AI review batch instructions

Read only files inside `input/`. Write exactly one file: `output/findings_result.json`.
Each job is one complete section; return every question in that job. Do not edit
`findings_template.csv` or any official QA artifact. The result must be a JSON object
with a `findings` array. Every row must contain section_id, page_sampled,
checklist_ref, result (PASS/FAIL), severity (required for FAIL, empty for PASS),
specific English evidence, notes, and confidence (0..1). Do not omit uncertain rows;
use a low confidence and explain the uncertainty.

`images.json` lists the extracted images of these sections and of the pages in `pages/`,
with the section each one is mapped to; the PNG files are in `images/`. An image with
`"origin": "vector"` is a figure drawn with vector paths that the pipeline rendered from
the page region. Use it for the image checks (`5.5-*`).

## Lead notes for this batch (DOC-0136477A v1.12, final re-measurement)

This version is a re-measurement with all fixes applied (pipeline commit 211981b).

- `prior_fails.json` lists every row whose latest reviewed result in an older version
  was FAIL, mapped to the section ids of this tree, with the old evidence, severity and
  BUG id. For each of these rows (same section, page_sampled, checklist_ref), say plainly
  in `notes` whether the old problem is **still there** or is **now fixed**
  (for example: "Old FAIL (v1, BUG-001) is now fixed: the Contents table stays in sec_0001.").
  Judge from the rendered page and this tree, not from the old text.
- `mitigation_check_rows` explains why extra pages were added (base-pair, bug-occurrence,
  random-check).
- Write `evidence` and `notes` in simple English (A2-B1): short sentences, one fact each,
  exact ids and pages. `evidence` = what you see. `notes` = cause (BUG id if known, see
  `qa/confidence_index/root_causes.json` and `qa/bugs/BUG-NNN/bug.md`; say "probably"
  if not confirmed) and impact in one sentence.
- Agreed severity rules:
  - Images: Critical = a meaningful figure is lost (not in the image output and its
    information is not in the text). Medium = a figure is cut, or unique information is lost.
    Low = extra text inside a crop, or small/unreadable icons dropped or kept.
  - Tables: a lost table row whose text is nowhere else in the tree = Critical.
  - Everything else: Sprint scale in `pdf-tree-qa-verifier/references/verification-contract.md`.
- A new FAIL that did not exist in older versions is a possible regression: describe it
  carefully and say "possible regression" in `notes`.

## Lead review of the first draft (round 2)

`previous_draft.json` is the first draft for this batch. Start from it. Keep every row that
the lead does not mention, unless you find a clear error on the rendered page. Fix the rows
listed below, then run both validation tools again.

Lead rulings (apply them to every row of this batch, for consistency across batches):

1. **Chapter number or Appendix label in another section (BUG-022).** On a chapter-opening
   page, the big chapter number ("1", "6", "13") or the tab label ("A"/"B"/... and "Appendix")
   is stored in the first subsection or in the previous section. Grade `5.4-page_start_end`
   **FAIL Low** and cite **BUG-022**. The lead checked older trees: the owner of these nodes
   is the same since v1.8 (most since v1). So this is **not a regression**. Write "Present
   since v1 (or v1.8); not a regression." Do not write "possible regression" for these rows.
2. **Running header or folio at the top of a page** whose first real content belongs to the
   same section is **not** a boundary crossing. Grade PASS if nothing else is wrong.
3. **Small inline icons dropped** whose names are in the text: FAIL Low, cite **BUG-017**
   ("probably"). Icons that are printed in a neighbour section are not graded in this section.
4. Write "possible regression" only when the lead confirms it below. If a defect is old but
   was not graded before, write "Old defect, first graded in v1.12; not a regression."
5. For every row in `prior_fails.json`, keep a plain sentence: "Old FAIL (<version>, <BUG>)
   is now fixed" or "... is still there".

### Rows to fix in this batch
- sec_0098 p90 `5.4-page_start_end`: keep FAIL Low, cite BUG-022, and remove "possible regression" (ruling 1: chapter number "6" sits in sec_0098 since v1).
- The icon rows without an old FAIL: keep Low (BUG-017, ruling 3). Write "Old defect, first graded in v1.12; not a regression" instead of "grading difference".
- The lead confirmed img_0056/img_0057 (p85) and img_0064 (p89) exist as vector renders, so your Low grades for sec_0090 and sec_0095 stand.
