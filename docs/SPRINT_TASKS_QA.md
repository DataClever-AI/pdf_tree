```{=latex}
\begin{center}
\includegraphics[width=0.42\textwidth]{images/logo.png}\\[1.2em]
{\LARGE\bfseries pdf-tree --- QA Sprint Backlog}\\[0.5em]
{\large Manual Validation \& Tree Confidence Index Program}
\end{center}
\vspace{1em}
```

| Field | Value |
|---|---|
| **Document owner** | DataClever AI — Engineering |
| **Architecture designed by** | Jonathan Potes, CTO |
| **Assignee role** | Junior AI / Software Support Engineer |
| **Companion reference** | `docs/EVALUATION_GUIDE.md` (read chapters 4–5 before starting Story 1) |
| **Classification** | Internal — Proprietary. Not for external distribution. See `LICENSE.md`. |

---

## Sprint Goal

Establish a repeatable, evidence-based QA process for `pdf-tree` output: a manually-validated, statistically-sampled inspection procedure for one document, generalized into a **Tree Confidence Index** computed across a 6-manual benchmark set. At sprint close, Engineering receives a scored confidence rating per manual and a consolidated, severity-classified bug list.

This backlog contains two stories. Story 2 depends on Story 1's method being executed correctly at least once — do not start Story 2 until Story 1 has been reviewed and approved by your lead.

---

## Story 1 — Sampled Manual Structural Validation (Single Manual)

**Objective:** manually validate a statistically representative sample of a technical manual's `tree.json` output against the source PDF, following the procedure in `EVALUATION_GUIDE.md` §5.

**Input:** one structured technical manual PDF (e.g. a 280-page document, provided by your lead).

### Task 1.1 — Environment Setup

Follow `EVALUATION_GUIDE.md` §5.1:

```bash
uv sync
uv run streamlit run streamlit_app/app.py
```

Capture the console output to a file for later reference — there is currently no persistent log file (§5.2 gap):

```bash
uv run streamlit run streamlit_app/app.py 2>&1 | tee run.log
```

**Done when:** the app is running locally and `run.log` is being written.

### Task 1.2 — Run the Pipeline

On the **Extraction** page, upload the manual and run the full pipeline with Docling enabled. On completion:

- Record `total_pages` (from the **Metrics** page).
- Export `tree.json`, `images_v1.json`, and `bookmarks.json` from the **Export** page — these are your offline evidence set.
- Note the overall **Coverage / Precision / Structure** verdict from §5.3 (Metrics page). A `FAIL` here does not block sampling — it is itself input to your findings.

**Done when:** `tree.json` + companion exports are saved to your working folder, named `<manual_id>_tree.json` etc.

### Task 1.3 — Compute the Sample

The sample size is **15% of total pages**, rounded up.

| Example | Formula | Result |
|---|---|---|
| 280-page manual | `ceil(280 × 0.15)` | **42 pages** |

**Sampling method — do not simply take the first 15% of pages.** Use stratified sampling so early, middle, and late chapters are all represented, plus mandatory inclusion of the highest-risk sections regardless of quota:

1. From `tree.json`, list all top-level (chapter) sections and their page ranges.
2. Distribute the 42-page quota proportionally across chapters, by each chapter's share of `total_pages` (a 60-page chapter in a 280-page manual gets `round(60/280 × 42)` ≈ 9 sampled pages).
3. Within each chapter, pick pages at even intervals (e.g. every *N*th page) rather than clustering — this maximizes distinct-section coverage per chapter.
4. **Mandatory additions, on top of the 15% quota, not counted against it:**
   - Every section with `flagged_for_review: true`.
   - Every section with `structural_source: "inferred"`.
   - The first and last content section of the document (front-matter and back-matter boundary is the most common miscalibration point — see `EVALUATION_GUIDE.md` §4.2).

Document the final sampled page list and the section each page maps to (via `page_start` / `page_end`) before inspecting anything — this list is a deliverable, not scratch work.

**Done when:** a sample page/section list exists, reviewable independently of your findings (so a second engineer could re-run the same sample).

### Task 1.4 — Manual Inspection

For **every section** touched by your sample (a page may map to only one section — inspect that section once, not once per page), run the full checklist from `EVALUATION_GUIDE.md`:

- §5.4 — Manual Structural Review Checklist (7 items: `hierarchy_level`, `parent_section_id`/`child_sections`, `page_start`/`page_end`, `hierarchy_path`, gaps/duplicates, `flagged_for_review`, `structural_source`).
- §5.5 — Embedded Image Extraction, for any sampled section containing images (3 items).
- §5.6 — Additional Field-Level Checks (`numbering_scheme`, `offset_applied`, table node content, `sanity_report`) (4 items).

For each item, open the source PDF at the relevant page(s) side-by-side and confirm against the checklist question. Record a **PASS** or **FAIL** — do not record "looks fine" without checking the specific page.

**Done when:** every sampled section has a checklist result recorded for every applicable item (not just a subset).

### Task 1.5 — Log Findings

Use this column schema (spreadsheet or CSV) — one row per checklist item evaluated:

| Column | Description |
|---|---|
| `manual_id` | Identifier for the source PDF |
| `section_id` | From `tree.json` |
| `page_sampled` | The page number that triggered inspection of this section |
| `checklist_ref` | e.g. `5.4-page_start_end`, `5.6-numbering_scheme` |
| `result` | `PASS` / `FAIL` |
| `severity` | See §Severity Classification below — required for every `FAIL` |
| `evidence` | Short description or screenshot reference (PDF page vs. `tree.json` field) |
| `notes` | Free text — root-cause hypothesis if apparent (e.g. "offset miscalibration, see `toc_resolution.py`") |

**Done when:** the log has one row per (section × checklist item) evaluated, with zero blank `result` cells.

### Task 1.6 — Story 1 Deliverables

- Sample selection document (Task 1.3).
- Findings log (Task 1.5), all rows complete.
- Copy of the automated validation report (§5.3, Metrics page) for the manual.
- `run.log` console capture.
- Short summary (≤ 10 lines): total items checked, pass rate, count of `FAIL` by severity, and whether the automated `PASS`/`FAIL` verdict agreed with your manual sample.

**Definition of Done:** all five artifacts above exist, and your lead has reviewed the sample list (Task 1.3) and confirmed the methodology was followed before this story is marked complete.

---

## Severity Classification (used in Story 1 and Story 2)

Apply this scale to every `FAIL` logged. This classification also drives the Confidence Index weighting in Story 2 — classify consistently.

| Severity | Definition | Example |
|---|---|---|
| **Critical** | Content is misplaced into the wrong section, lost entirely, or the hierarchy is broken (cycle, missing parent, wrong nesting) | A subsection's content assigned to its sibling; `parent_section_id` pointing at the wrong chapter |
| **High** | A `flagged_for_review` section is confirmed genuinely wrong on manual check, or `page_start`/`page_end` is off by more than 1 page | Section boundary two pages off due to offset miscalibration |
| **Medium** | Content is correctly placed but a supporting field is wrong or degraded | Image assigned to the wrong sibling section on a shared page; `offset_applied` inconsistent between adjacent sections |
| **Low** | Cosmetic or non-blocking defect that does not affect retrievability of the correct content | Empty table `canonical_text` placeholder where the surrounding paragraph text still carries the information |

---

## Story 2 — Tree Confidence Index (6-Manual Benchmark)

**Objective:** repeat Story 1's method across **6 manuals** and produce a single, comparable **Confidence Index** score per manual, plus a consolidated bug report.

**Precondition:** Story 1 completed and approved for at least one manual, using the exact same checklist, severity scale, and sampling method for all 6.

### Task 2.1 — Run Story 1's Full Procedure on Each of the 6 Manuals

Repeat Tasks 1.1–1.5 independently for each manual. Each manual gets its own sample size (`ceil(total_pages × 0.15)`), its own sample list, and its own findings log — do not reuse or pool samples across manuals.

**Done when:** 6 complete findings logs exist, one per manual, each satisfying Story 1's Definition of Done.

### Task 2.2 — Compute the Confidence Index per Manual

**Formula:**

```
Confidence Index = 100 x ( 1 - ( sum(severity_weight x fail_count) / total_items_evaluated ) )
```

clamped to the range **[0, 100]**.

**Severity weights:**

| Severity | Weight |
|---|---|
| Critical | 8 |
| High | 4 |
| Medium | 2 |
| Low | 1 |

**Automated-check override:** if the automated validation report (§5.3) for a manual shows `status: FAIL` on **Coverage** or **Structure** (not Precision alone), cap that manual's Confidence Index at **60**, regardless of the formula result. Rationale: these two checks indicate content loss or a broken hierarchy — a systemic defect the manual sample size may not fully capture, and the score should reflect that risk rather than understate it.

**Worked example:** 42-page sample maps to 30 distinct sections, each checked against 11 checklist items -> `total_items_evaluated = 330`. Findings: 1 Critical, 2 High, 4 Medium, 3 Low.

```
weighted_fails = (1x8) + (2x4) + (4x2) + (3x1) = 8 + 8 + 8 + 3 = 27
Confidence Index = 100 x (1 - 27/330) = 100 x 0.918 = 91.8 -> 92
```

**Done when:** each of the 6 manuals has one computed Confidence Index score, with the calculation shown (not just the final number).

### Task 2.3 — Consolidate the Bug List

Merge all `FAIL` rows across the 6 findings logs into one list. Deduplicate by root cause, not by row — three sections all misplaced by the same offset-calibration bug are **one bug entry** referencing three affected sections, not three separate bugs.

Column schema for the consolidated list:

| Column | Description |
|---|---|
| `bug_id` | Sequential identifier |
| `title` | One-line description |
| `severity` | Highest severity among affected instances |
| `manuals_affected` | Which of the 6 manuals show this bug |
| `sections_affected` | Section IDs / count |
| `suspected_module` | Pipeline module, if identifiable (e.g. `toc_resolution.py`, `section_matcher.py` — see `EVALUATION_GUIDE.md` §4.1) |
| `escalate` | Yes/No per `EVALUATION_GUIDE.md` §7 Escalation Guidance |

**Done when:** every `FAIL` row from all 6 logs is accounted for in exactly one consolidated bug entry.

### Task 2.4 — Sprint Deliverable: Confidence Index Report

One summary table, plus the consolidated bug list:

| Manual | Total Pages | Sample Size | Automated Verdict | Confidence Index | Critical | High | Medium | Low |
|---|---|---|---|---|---|---|---|---|
| Manual 1 | — | — | — | — | — | — | — | — |
| Manual 2 | — | — | — | — | — | — | — | — |
| Manual 3 | — | — | — | — | — | — | — | — |
| Manual 4 | — | — | — | — | — | — | — | — |
| Manual 5 | — | — | — | — | — | — | — | — |
| Manual 6 | — | — | — | — | — | — | — | — |

Plus:
- The consolidated, deduplicated bug list (Task 2.3).
- A one-paragraph interpretation: is the Confidence Index stable across manuals, or does it vary sharply by document type (e.g. lower on manuals with `structural_source: "inferred"`)? This observation is often more actionable to Engineering than the raw scores.

**Definition of Done (Story 2):** the summary table is fully populated, the consolidated bug list references every finding, and the report has been reviewed with your lead before being shared with Engineering.

---

## Overall Sprint Definition of Done

- [ ] Story 1 completed, reviewed, and approved for the pilot manual.
- [ ] Story 2 completed for all 6 manuals using the identical method from Story 1.
- [ ] Confidence Index Report delivered (Task 2.4).
- [ ] Every `Critical` and `High` severity bug has an escalation decision recorded (`EVALUATION_GUIDE.md` §7).
- [ ] All raw artifacts (sample lists, findings logs, `tree.json` exports, `run.log` captures) retained and linked from the final report — the Confidence Index number must be traceable back to the individual checklist rows that produced it.

```{=latex}
\begin{center}
{\small DataClever AI --- Internal Use Only. Copyright (C) 2026 DataClever AI. All rights reserved. See \texttt{LICENSE.md}.}
\end{center}
```
