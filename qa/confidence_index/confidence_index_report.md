# Tree Confidence Index Report (Task 2.4)

## Summary table

| Manual | Total Pages | Sample Size | Automated Verdict | Confidence Index | Critical | High | Medium | Low |
|---|---|---|---|---|---|---|---|---|
| `DOC-0136477A` | 240 | 36 (+2) | PASS | **57** | 19 | 0 | 5 | 34 |
| `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | 166 | 25 (+23) | PASS | **92** | 2 | 0 | 2 | 0 |
| `LOGIQ_e_R9_General_Service_Manual` | 567 | 86 (+2) | PASS | **85** | 6 | 4 | 8 | 1 |
| `LOGIQ_S8` | 916 | 138 (+2) | FAIL (Coverage) | **60** (capped — raw 88) | 10 | 1 | 7 | 13 |
| `SOMATOM_Force_IFU_VB30` | 467 | 71 (+3) | FAIL (Coverage + Precision) | **0** (floor) | 118 | 5 | 18 | 1 |
| `Philips-MP20-MP90-Manual` | — | — | — | — | — | — | — | — |
| `2002_Service_Manual_TI` | — | — | — | — | — | — | — | — |

**Pending manuals:** `Philips-MP20-MP90-Manual` and `2002_Service_Manual_TI`
both fail `bookmark_sanity` (fitz stage) before Docling runs, for two
different root causes — see `qa/README.md` for the full diagnosis of each.
No `findings_log.csv` exists for either yet, so they carry no data here.

## Consolidated bug list (Task 2.3)

Full list with `sections_affected` detail: `consolidated_bugs.csv` in this
folder. 254 raw `FAIL` rows across the 5 completed manuals reduce to **18
root-cause bugs**, 2 rows still pending root-cause confirmation, and 1 row
excluded as not a defect (see notes below the table).

| bug_id | Title | Severity | Manuals affected | Sections | Escalate |
|---|---|---|---|---|---|
| BUG-001 | Chapter/appendix-opening Contents-box misplacement | Critical | DOC-0136477A, LOGIQ_S8, SOMATOM_Force_IFU_VB30 | 26 | Yes |
| BUG-002 | Back-matter silently absorbed past last bookmark | Critical | DOC-0136477A, LOGIQ_S8, LOGIQ_e_R9_General_Service_Manual, SOMATOM_Force_IFU_VB30 | 8 | Yes |
| BUG-003 | Sibling image/table mismapping on shared pages | Critical | DOC-0136477A, SOMATOM_Force_IFU_VB30 | 10 | Yes |
| BUG-004 | Decorative footer divider passes image aspect-ratio filter | Low | DOC-0136477A | 34 | No (cosmetic — accounts for ~100% of this manual's Low findings) |
| BUG-005 | Content-stream desync — body text lost/misattributed around a chapter boundary | Critical | SOMATOM_Force_IFU_VB30 | 65 | Yes |
| BUG-006 | Body content extraction gap — section body lost entirely | Critical | SOMATOM_Force_IFU_VB30 | 8 | Yes |
| BUG-007 | Native table extractor captures only the header row for symbol/glyph-marked grids | Medium | AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION | 2 | No |
| BUG-008 | Table header cells merge/reorder, breaking column-to-value attribution | High | LOGIQ_e_R9_General_Service_Manual | 2 | Yes |
| BUG-009 | Table mistyped as paragraph/heading instead of a table node (single instance) | Medium | LOGIQ_e_R9_General_Service_Manual | 1 | No |
| BUG-010 | Vector-drawn diagrams not captured as images — extractor only handles raster XObjects | Critical | AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION, LOGIQ_e_R9_General_Service_Manual | 3 | Yes |
| BUG-011 | Simple line-art/pictogram diagrams missing — mechanism unconfirmed | Medium | LOGIQ_S8 | 2 | No |
| BUG-012 | Sporadic single/partial image omissions from the image index — mechanism unconfirmed | Critical | LOGIQ_e_R9_General_Service_Manual | 5 | Yes |
| BUG-013 | Extracted image asset incorrectly rotated 180° | Medium | LOGIQ_e_R9_General_Service_Manual | 1 | No |
| BUG-014 | Section page_end one page short of true boundary — trailing content bleeds into neighbor | Critical | LOGIQ_S8, SOMATOM_Force_IFU_VB30 | 14 | Yes |
| BUG-015 | Step-illustration photos dropped on pages with multiple table-embedded images | Medium | LOGIQ_S8 | 3 | No |
| BUG-016 | Near-duplicate/overlapping image xrefs cause under-extraction | Medium | SOMATOM_Force_IFU_VB30 | 1 | No |
| BUG-017 | UI reference-icon screenshots discarded by an over-aggressive min-pixel-dimension filter | High | SOMATOM_Force_IFU_VB30 | 1 | Yes |
| BUG-018 | Cross-chapter node swap — content misattributed across non-adjacent boundaries (new, single instance) | Critical | SOMATOM_Force_IFU_VB30 | 1 | Yes |

**Still unconfirmed (2 rows, `TRIAGE-*`):** `LOGIQ_e_R9_General_Service_Manual`
sec_0082 (evidence couldn't confirm vector-vs-raster vs. a genuine gap) and
`LOGIQ_S8` sec_0080 (couldn't confirm whether two visual elements were
merged into one bounding image by Docling, a false positive, or a real
drop). Both explicitly flagged in their own `notes` as needing pipeline-side
investigation, not resolvable from the QA evidence alone.

**Excluded, not a defect:** `SOMATOM_Force_IFU_VB30` sec_0906
(`5.4-flagged_for_review`) — its own `notes` mark it as a positive/control
finding: the `flagged_for_review` mechanism correctly caught a genuine
low-title-match case. Kept out of the bug list rather than forced into a
bucket.

**Escalation rationale:** none of the 18 bugs fall under
`EVALUATION_GUIDE.md` §6 (Out of Scope). The 13 non-Low/non-cosmetic bugs
are reproducible across sections/manuals, satisfying §7 escalation
criterion 3 ("behavior doesn't match §6 and is reproducible") independent
of the automated PASS/FAIL verdict.

## Interpretation

The Confidence Index is not stable across manuals — it ranges from 0
(`SOMATOM_Force_IFU_VB30`) to 92
(`AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION`). Document size
does not explain the spread (`SOMATOM_Force_IFU_VB30`, 467 pages, scores 0;
`LOGIQ_S8`, 916 pages, scores 60): the variance tracks whether a manual
triggers one of a small number of systemic root causes. `BUG-005` alone
(content-stream desync) accounts for 65 of `SOMATOM_Force_IFU_VB30`'s
Critical findings; `BUG-004` (a cosmetic footer-divider filter miss)
accounts for essentially all 34 of `DOC-0136477A`'s Low findings — i.e. a
large share of two manuals' raw FAIL counts trace back to just 2 of the 18
bugs, one Critical and one Low. This means the Index is measuring exposure
to a handful of pipeline defects rather than a uniform quality gradient —
fixing `BUG-001`, `BUG-002`, `BUG-005`, and `BUG-014` (the four bugs
appearing in more than one manual) would move the score on 4 of the 5
manuals measured so far.
