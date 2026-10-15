# VLM benchmark replication and integration decision

Date: 2026-09-09

## Outcome

The original benchmark is reproducible. Qwen3-VL 8B is materially better than 4B
for visual defect discovery on this sample, but neither model is safe as an
automatic source of final findings. The approved use for the current QA workflow is
therefore **8B as a draft-only, human-reviewed provider**. The 4B model is rejected
for this role.

Qwen drafts must not be eligible for bulk approval until semantic consistency and
provider-aware review rules are added. Deterministic checks remain the authority for
identifiers, section ranges, gaps, duplicates, and severity policy.

## Independent replication

The same 15 PDF pages were rendered at 160 DPI with Poppler. Both cached MLX models
were run at temperature 0 against the six original cases (18 checklist decisions).

| Metric | 4B rerun | 8B rerun | Original 4B | Original 8B |
|---|---:|---:|---:|---:|
| Result accuracy | 13/18 (72.2%) | 14/18 (77.8%) | 13/18 | 14/18 |
| Defect sections detected | 0/3 | 2/3 | 0/3 | 2/3 |
| Clean-section false positives | 0/3 | 0/3 | 0/3 | 0/3 |
| Exact `section_id` | 2/6 | 2/6 | 2/6 | 2/6 |
| Valid JSON | 6/6 | 6/6 | 6/6 | 6/6 |
| Exact check order | 6/6 | 6/6 | 6/6 | 6/6 |
| Severity accuracy | 13/18 (72.2%) | 12/18 (66.7%) | 13/18 | 12/18 |
| Total generation time | 275.26 s | 467.23 s | 301.33 s | 509.46 s |
| Peak MLX memory | 7.05 GB | 10.02 GB | 7.05 GB | 10.02 GB |

The model decisions and structural metrics reproduced exactly. Runtime varied by
about 8%, which is normal machine-load variation and does not change the conclusion.

## Manual result audit

- 4B missed all three known-defect sections. In `sec_0279`, its evidence said the
  section ended on page 232 while returning `PASS` for the declared end on page 240.
- 8B detected the boundary defect in `sec_0004` and the three structural problems in
  `sec_0279`, but missed the Critical boundary defect in `sec_0015`.
- In `sec_0004`, 8B returned three FAILs even though two evidence strings explicitly
  said the structure was correct. The failures were attached to the wrong criteria.
- In `sec_0279`, 8B correctly identified the Glossary/Index omission but inflated a
  Medium severity to Critical and returned `REVIEW` instead of the expected Medium
  table-content failure.
- Both models replaced the supplied stable ID in four of six cases.
- All three clean controls remained free of result-level false positives. However,
  the `sec_0066` PASS evidence contradicted the declared page range, so result-only
  accuracy understates the consistency problem.

## `max_tokens=900`

The complete 8B benchmark was repeated with 900 instead of 1800 output tokens.
Results were unchanged: 14/18 accuracy, 2/3 defect sections, 0/3 clean false
positives, and 2/6 exact IDs. Total generation time was 467.52 s and peak memory was
10.02 GB. The longest answer used 721 tokens, so no answer was truncated.

Decision: use `max_tokens=900` as the default cap. It prevents unexpectedly long
answers but does not improve accuracy or materially reduce image-processing cost.

## Windowed `sec_0279` experiment

The seven-page case was split into windows of pages 231-233, 236-238, and 240. The
window runner preserved the canonical section ID outside model output and combined
FAIL/REVIEW observations conservatively.

| Configuration | Time | Peak memory | Completeness |
|---|---:|---:|---|
| One seven-image request | 202.91 s | 10.02 GB | 3/3 checks returned |
| Three windows | 187.65 s | 7.92 GB | two requested checks omitted |

The windows correctly found the bad boundary, Glossary, and Index. However, the first
two windows each omitted their second requested check, leaving `table_content`
without an observation. Missing observations are treated as `REVIEW`, never PASS.

Decision: do not make windowing the default yet. It saves about 7.5% runtime and 21%
peak memory, but needs per-check completeness validation and targeted retry before it
is reliable. It is suitable only as a resumable experimental path for unusually long
sections.

## Fit with the implemented QA workflow

Existing protections already block several observed failures:

- a returned row must match an official template key;
- only PASS/FAIL are accepted, so `REVIEW` remains pending;
- duplicate, missing, invalid-severity, evidence-free, and invalid-confidence rows
  remain pending;
- provider output is stored as a draft and never writes directly to
  `findings_log.csv`.

Two important gaps remain:

1. Validation checks schema but not whether evidence logically supports the result.
2. Bulk approval is provider-agnostic. A high-confidence Qwen PASS can currently be
   eligible even though the benchmark contains a missed Critical defect.

## Integration decision

Before enabling Qwen3-VL in routine review:

1. Run deterministic rules first and do not ask the VLM to decide stable IDs,
   mechanical ranges, gaps, duplicates, or severities that rules can derive.
2. Use only Qwen3-VL 8B, with `max_tokens=900`, for ambiguous visual evidence.
3. Assign `manual_id`, `section_id`, page, and checklist reference from the request;
   never trust model-returned identifiers.
4. Reject or prioritize any result whose evidence contradicts its PASS/FAIL verdict.
5. Exclude all Qwen drafts from bulk approval until a larger benchmark demonstrates
   acceptable Critical-defect recall. FAIL, REVIEW, contradictions, and all structural
   boundary checks require individual human review.
6. Keep severities policy-driven and human-editable; do not accept model severity as
   authoritative.
7. Expand the benchmark before promotion, especially with more Critical boundary
   defects and genuine table/non-table controls.

Promotion criterion proposed for automatic PASS assistance: zero missed Critical
defects in the validation set, exact row completeness, no identifier dependence, and
no evidence/result contradictions. This six-section benchmark does not meet it.

## Additional large-model spot check

Two additional MLX models were downloaded and tested on the rendered page 17 and the
known-defect `sec_0004`. This is a targeted comparison, not a replacement for the
six-section benchmark above. The requested `pagina_10_9.png` was not present in the
workspace, so `pages/p17.png` was used because it has an existing human reference.

| Model | Cache size | `sec_0004` result | Generation | Peak MLX memory | Contract |
|---|---:|---|---:|---:|---|
| Qwen3-VL 8B | 5.4 GB | detected section FAIL, but wrong per-check logic | 44.82 s | 7.06 GB | valid JSON |
| Qwen3-VL 30B-A3B | 17 GB | missed Critical defect; three PASS | 29.63 s | 19.36 GB | Markdown-fenced JSON |
| Kimi-VL A3B Thinking | 9.2 GB | missed Critical defect; three PASS | 27.04 s | 12.19 GB | thinking preamble before JSON |

The qualitative 30B command with a 300-token limit was truncated mid-answer. More
importantly, it claimed that the extracted text had no omissions or OCR errors even
though no extracted text was supplied to the prompt. This is an unsupported
comparison rather than evidence of correctness.

Kimi's first run returned no text. The model conversion declares the assistant-start
token as an EOS token, so generation stopped after one token. It generated normally
only when EOS was overridden to the tokenizer's real `[EOS]` ID (`163594`). With that
workaround it used 526 tokens: a 300-token cap would have ended during reasoning,
before the final JSON. The output still failed the QA contract because it exposed the
thinking block, used English evidence despite the Spanish instruction, and missed the
known Critical boundary defect.

The historical Kimi compatibility report is valid for older 8-bit/bfloat16 variants,
but the suggested `transformers==4.46.3` pin is not compatible with current
`mlx-vlm`: version 0.7.0 requires Transformers 5.14 or newer. Kimi was therefore
isolated in `/Users/j/Models/kimi-vl-validator/.venv` with `mlx-vlm 0.7.0` and
Transformers 5.17.0. It loads successfully, but requires the EOS workaround above.

Decision after the spot check: keep Qwen3-VL 8B as the only pilot QA provider. Keep
Kimi temporarily only if further parser/EOS experiments are desired. Recommend
deleting Qwen3-VL 30B-A3B after user approval: it occupies the most storage and
memory, missed the same defect as Kimi, violated the output contract, and showed no
quality advantage over 8B.

## Artifacts

- `rerun_results_4b.json`, `rerun_score_4b.json`
- `rerun_results_8b.json`, `rerun_score_8b.json`
- `rerun_results_8b_900.json`, `rerun_score_8b_900.json`
- `rerun_results_8b_sec0279_windows.json`
- `rerun_results_30b_sec0004.json`
- `rerun_results_kimi_sec0004.json`
- `benchmark_sec0279_windows.py`
