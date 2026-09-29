# Versioned semi-automated QA workspace

This directory stores deterministic pipeline evidence, AI drafts, and
human-approved findings. AI does not alter the extraction pipeline and cannot
write the official findings CSV directly.

New and migrated manuals use this contract:

```text
qa/<manual_id>/
├── source_manifest.json             # absolute PDF path + SHA-256; PDF is not copied
└── v1/                              # v2, v3, ... are separate reviews
    ├── version_manifest.json
    ├── artifact_manifest.json
    ├── exports/{tree.json,images_v1.json,bookmarks.json}
    ├── sampling/sample_selection.md
    ├── findings/{findings_log.csv,review_state.json}
    ├── logs/{run.log,ai_review.jsonl}
    ├── agent_exchange/<batch_id>/
    ├── validation_report.json
    └── summary.md
```

`findings_log.csv` always has exactly these columns:
`manual_id,section_id,page_sampled,checklist_ref,result,severity,evidence,notes`.
Provider proposals, confidence, reviewer identity, approvals, and change
history live only in `review_state.json`.

Configure `PDF_TREE_SOURCE_DIR` and `PDF_TREE_QA_DIR` in `.env` or the
Streamlit sidebar. Use `uv run python qa/_scripts/migrate_legacy_layout.py`
for a dry run and add `--apply` only after reviewing conflicts and checksums.

## Historical sprint notes

## Structure

```
qa/
├── README.md                        ← this file
├── <manual_id>/                     ← one folder per manual (Story 1: 1, Story 2: 6)
│   ├── exports/                     ← Task 1.2 — NOT committed, see note below
│   │   ├── tree.json
│   │   ├── images_v1.json
│   │   └── bookmarks.json
│   ├── exports_manifest.txt         ← Task 1.2 — committed: file name + byte size per export (traceability without the weight)
│   ├── logs/
│   │   └── run.log                  ← Task 1.1 — console capture (uv run ... | tee run.log)
│   ├── sampling/
│   │   └── sample_selection.md      ← Task 1.3 — sampled page/section list + calculation
│   ├── findings/
│   │   └── findings_log.csv         ← Task 1.5 — one row per (section × checklist item)
│   ├── validation_report.json       ← Task 1.2/1.6 — copy of the automated report (Metrics page)
│   └── summary.md                   ← Task 1.6 — ≤10-line summary (pass rate, FAIL by severity, etc.)
└── confidence_index/                ← Story 2, once all 6 manuals are done
    ├── confidence_index_report.md   ← Task 2.4 — summary table + interpretation
    └── consolidated_bugs.csv        ← Task 2.3 — bug list deduplicated by root cause
```

**`exports/` is gitignored, not a missing deliverable.** `tree.json` +
`images_v1.json` together run into the hundreds of MB per manual (up to
~150MB for a single `images_v1.json`) — too heavy to version. They stay on
disk locally as evidence and are regenerable at any time by re-running the
pipeline on the source PDF (Task 1.2). `exports_manifest.txt` (file name +
byte size) *is* committed so the export's existence and size are traceable
from git history even without the file itself.

## Manuals in progress

Source PDFs live in `../../Manuales técnicos TEST/` (outside the repo, not committed).

| `manual_id` | Source PDF | Total pages | Sample quota (15%) | Status |
|---|---|---|---|---|
| `DOC-0136477A` | `DOC-0136477A.pdf` | 240 | 36 (+2 mandatory) | Story 1 — Task 1.6 complete, **pending lead review/approval** (blocks Story 2 per Task 2.1) |
| `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | `AUTOMATIC TRANSMISSION MECHANISM AND FUNCTION SECTION.pdf` | 166 | 25 (+23 mandatory) | Story 2 — Task 1.6 complete |
| `LOGIQ_e_R9_General_Service_Manual` | `LOGIQ e R9 General Service Manual_SM_5937432-1EN_5.pdf` | 567 | 86 (+2 mandatory) | Story 2 — Task 1.6 complete |
| `LOGIQ_S8` | `LOGIQ_S8.pdf` | 916 | 138 (+2 mandatory) | Story 2 — Task 1.6 complete |
| `SOMATOM_Force_IFU_VB30` | `SOMATOM_Force_IFU_VB30_SAPEDM_C2-058-C.621.01.01.02_Online.pdf` | 467 | 71 (+3 mandatory) | Story 2 — Task 1.6 complete |
| `Philips-MP20-MP90-Manual` | `Philips-MP20-MP90-Manual.pdf` | 496 | 75 | Story 2 — **unblocked in `v2`** (`fix/bookmark-sanity-recovery`): pipeline completes, 865 sections, automated verdict FAIL (Coverage: 2 orphaned blocks). `v1` kept as the record of the aborted run. Sampling + findings template ready; manual review pending |
| `2002_Service_Manual_TI` | `2002 Service Manual - TI.pdf` | 642 | 97 | Story 2 — **unblocked in `v2`** (`fix/bookmark-sanity-recovery`): pipeline completes, 251 sections, automated verdict FAIL (Precision: 1 misplaced block, p442). `v1` kept as the record of the aborted run. Sampling + findings template ready; manual review pending |

**Both `bookmark_sanity` blockers are localized PDF defects, now repaired
deterministically** by `repair_bookmarks()` in
`src/tree_builder/bookmark_sanity.py` (runs only on hard failures; every change
is logged and recorded in the sanity report):
- `Philips-MP20-MP90-Manual`: **not** two merged documents (earlier diagnosis
  was wrong). Pages 1–2 are the cover of the same manual, inserted after the
  outline was built: the editor appended a destination-less bookmark
  `'M8000-9001K_cover_22sep08.pdf'` (`page_no=-1`) at the end of the outline,
  with a child pointing at page 1. Repair: the orphan front-matter subtree is
  dropped. Note: `v1/logs/run.log` also contains a later `LOGIQ_S8` run from
  the same Streamlit session (lines 15+) — use `v2/logs/run.log`.
- `2002_Service_Manual_TI`: bookmark `'1. General'` uses the named destination
  `G436071`, which resolves to page 3 (Quick Reference Index); the heading is
  on page 22. Repair: relocated to the page in its parent's range where the
  title appears as a text line; the resulting section is `flagged_for_review`.

Structured write-up: `../doc/HALLAZGOS_ESTRUCTURADOS_pdf_tree.md` (H-01..H-03).

Per Task 2.1, Story 2 execution work is happening in parallel across manuals,
but **Historia 2 cannot be marked done** until Story 1 (`DOC-0136477A`) has
been reviewed and approved by the lead — see the Definition of Done in
`docs/SPRINT_TASKS_QA.md`.

## Confidence Index (Task 2.2)

`Index = 100 × (1 − Σ(severity_weight × FAIL_count) / total_items_evaluated)`,
capped to `[0, 100]`, and capped at **60** if the automated report shows
`Coverage: FAIL` or `Structure: FAIL` (§Task 2.2 override rule). Weights:
Critical=8, High=4, Medium=2, Low=1.

| Manual | Total Pages | Items evaluated | Automated Verdict | Confidence Index | Critical | High | Medium | Low |
|---|---|---|---|---|---|---|---|---|
| `DOC-0136477A` | 240 | 456 | PASS | **57** | 19 | 0 | 5 | 34 |
| `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | 166 | 265 | PASS | **92** | 2 | 0 | 2 | 0 |
| `LOGIQ_e_R9_General_Service_Manual` | 567 | 539 | PASS | **85** | 6 | 4 | 8 | 1 |
| `LOGIQ_S8` | 916 | 955 | **FAIL** (Coverage) | **60** (capped — raw 88) | 10 | 1 | 7 | 13 |
| `SOMATOM_Force_IFU_VB30` | 467 | 757 | **FAIL** (Coverage + Precision) | **0** (floor — raw weighted fails exceed items evaluated) | 118 | 5 | 18 | 1 |
| `Philips-MP20-MP90-Manual` | 496 | — | FAIL (Coverage) | pending review (`v2`) | — | — | — | — |
| `2002_Service_Manual_TI` | 642 | — | FAIL (Precision) | pending review (`v2`) | — | — | — | — |

These 5 numbers are the per-manual inputs to Task 2.2 — `confidence_index/confidence_index_report.md`
(Task 2.4) still needs to be written once all 6 manuals are done, with the
consolidated/deduplicated bug list (Task 2.3) and the stability interpretation
across document types.

**Task 2.3 — done for the 5 available manuals** (`qa/_scripts/consolidate_bugs.py`,
output at `confidence_index/consolidated_bugs.csv` and written up in
`confidence_index/confidence_index_report.md`): every one of the 254 raw
`FAIL` rows across the 5 completed findings logs was reviewed —
first an automated pass matching rows against the known §7 patterns, then a
full manual read of the ~82 rows that didn't auto-match, to check whether
each one's `notes`/`evidence` described an already-known root cause in
different words, a new recurring root cause, or was genuinely a one-off.
Result: **18 root-cause bugs** (`BUG-001`..`BUG-018`), **2 rows** still
unresolved (evidence explicitly inconclusive per their own `notes` — needs
pipeline-side investigation, not more QA reading), and **1 row excluded**
as not a defect (a positive/control finding, not a bug). Also fixed along
the way: `severity` values were **not normalized** across manuals —
`AUTOMATIC_TRANSMISSION` and `LOGIQ_e_R9` used Spanish labels
(`Critica/Alta/Media/Baja`) while the other 3 used English; the script
normalizes both to the sprint's English scale before counting. Notable:
`BUG-005` ("content-stream desync") alone covers **65 sections in
`SOMATOM_Force_IFU_VB30`**, and `BUG-004` (footer-divider filter miss)
covers **34 of `DOC-0136477A`'s 34 Low findings** — almost all of two
manuals' raw FAIL counts trace to just those 2 bugs. Excludes
`Philips-MP20-MP90-Manual` and `2002_Service_Manual_TI` (no reviewed findings yet;
`v2` awaiting manual review — see above) — re-run the script once those land.

## Naming convention

- `manual_id`: same identifier used in `findings_log.csv` (`manual_id` column) and in the Task 2.4 summary table — do not change once assigned, to keep traceability.
- `findings_log.csv` — exact columns: `manual_id, section_id, page_sampled, checklist_ref, result, severity, evidence, notes` (see `docs/SPRINT_TASKS_QA.md` §Task 1.5).
- `consolidated_bugs.csv` — exact columns: `bug_id, title, severity, manuals_affected, sections_affected, suspected_module, escalate` (see §Task 2.3).
