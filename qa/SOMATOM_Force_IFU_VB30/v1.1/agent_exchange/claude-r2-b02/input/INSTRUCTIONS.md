# AI review batch instructions

Read only files inside `input/`. Write exactly one file: `output/findings_result.json`.
Each job is one complete section; return every question in that job. Do not edit
`findings_template.csv` or any official QA artifact. The result must be a JSON object
with a `findings` array. Every row must contain section_id, page_sampled,
checklist_ref, result (PASS/FAIL), severity (required for FAIL, empty for PASS),
specific English evidence, notes, and confidence (0..1). Do not omit uncertain rows;
use a low confidence and explain the uncertainty.
