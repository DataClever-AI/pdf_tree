# Working structure — QA Sprint (`docs/SPRINT_TASKS_QA.md`)

Local working folder for Story 1 and Story 2 deliverables from the QA backlog.
Not part of the pipeline itself — it's manual-validation evidence and
artifacts. Working branch: `test/docling-accelerator-validation`.

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
| `Philips-MP20-MP90-Manual` | `Philips-MP20-MP90-Manual.pdf` | 496 | 75 | Story 2 — **pipeline run blocked**: `bookmark_sanity: 2 hard failures — aborting` (fitz stage, before Docling ever runs — see `logs/run.log`). Needs a pipeline fix, not just a re-run, before sampling/findings/summary can happen |
| `2002_Service_Manual_TI` | `2002 Service Manual - TI.pdf` | 642 | 97 | Story 2 — not started, no attempt on record (no `run.log` at all — can't say yet whether it hits the same bookmark issue) |

Per Task 2.1, Story 2 execution work is happening in parallel across manuals,
but **Historia 2 cannot be marked done** until Story 1 (`DOC-0136477A`) has
been reviewed and approved by the lead — see the Definition of Done in
`docs/SPRINT_TASKS_QA.md`.

## Índice de Confianza / Confidence Index (Task 2.2)

`Índice = 100 × (1 − Σ(peso_severidad × conteo_FAIL) / total_items_evaluados)`,
capped to `[0, 100]`, and capped at **60** if the automated report shows
`Coverage: FAIL` or `Structure: FAIL` (§Task 2.2 override rule). Weights:
Crítica=8, Alta=4, Media=2, Baja=1.

| Manual | Total Páginas | Ítems evaluados | Veredicto Automático | Índice de Confianza | Crítica | Alta | Media | Baja |
|---|---|---|---|---|---|---|---|---|
| `DOC-0136477A` | 240 | 456 | PASS | **57** | 19 | 0 | 5 | 34 |
| `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | 166 | 265 | PASS | **92** | 2 | 0 | 2 | 0 |
| `LOGIQ_e_R9_General_Service_Manual` | 567 | 539 | PASS | **85** | 6 | 4 | 8 | 1 |
| `LOGIQ_S8` | 916 | 955 | **FAIL** (Coverage) | **60** (capped — raw 88) | 10 | 1 | 7 | 13 |
| `SOMATOM_Force_IFU_VB30` | 467 | 757 | **FAIL** (Coverage + Precision) | **0** (floor — raw weighted fails exceed items evaluated) | 118 | 5 | 18 | 1 |
| `Philips-MP20-MP90-Manual` | TBD | — | — | pending | — | — | — | — |
| `2002_Service_Manual_TI` | TBD | — | — | pending | — | — | — | — |

These 5 numbers are the per-manual inputs to Task 2.2 — `confidence_index/confidence_index_report.md`
(Task 2.4) still needs to be written once all 6 manuals are done, with the
consolidated/deduplicated bug list (Task 2.3) and the stability interpretation
across document types.

## Naming convention

- `manual_id`: same identifier used in `findings_log.csv` (`manual_id` column) and in the Task 2.4 summary table — do not change once assigned, to keep traceability.
- `findings_log.csv` — exact columns: `manual_id, section_id, page_sampled, checklist_ref, result, severity, evidence, notes` (see `docs/SPRINT_TASKS_QA.md` §Task 1.5).
- `consolidated_bugs.csv` — exact columns: `bug_id, title, severity, manuals_affected, sections_affected, suspected_module, escalate` (see §Task 2.3).
