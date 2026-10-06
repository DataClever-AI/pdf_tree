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

Read `LEAD_REVISION_NOTES.md` and `reference_rows.json` first. This batch is focused: answer exactly the rows in `findings_template.csv`.
