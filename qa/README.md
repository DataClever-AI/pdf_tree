# Working structure — QA Sprint (`docs/SPRINT_TASKS_QA.md`)

Local working folder for Story 1 and Story 2 deliverables from the QA backlog.
Not part of the pipeline itself — it's manual-validation evidence and
artifacts. Working branch: `test/docling-accelerator-validation`.

## Structure

```
qa/
├── README.md                        ← this file
├── <manual_id>/                     ← one folder per manual (Story 1: 1, Story 2: 6)
│   ├── exports/
│   │   ├── tree.json                ← Task 1.2 — export from the Export page
│   │   ├── images_v1.json           ← Task 1.2
│   │   └── bookmarks.json           ← Task 1.2
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

## Manuals in progress

Source PDFs live in `../../Manuales técnicos TEST/` (outside the repo, not committed).

| `manual_id` | Source PDF | Total pages | Status |
|---|---|---|---|
| `DOC-0136477A` | `DOC-0136477A.pdf` | 240 | Story 1 — pilot, in progress |
| `2002_Service_Manual_TI` | `2002 Service Manual - TI.pdf` | TBD | Story 2 — not started |
| `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION` | `AUTOMATIC TRANSMISSION MECHANISM AND FUNCTION SECTION.pdf` | TBD | Story 2 — not started |
| `LOGIQ_e_R9_General_Service_Manual` | `LOGIQ e R9 General Service Manual_SM_5937432-1EN_5.pdf` | TBD | Story 2 — not started |
| `LOGIQ_S8` | `LOGIQ_S8.pdf` | TBD | Story 2 — not started |
| `Philips-MP20-MP90-Manual` | `Philips-MP20-MP90-Manual.pdf` | TBD | Story 2 — not started |
| `SOMATOM_Force_IFU_VB30` | `SOMATOM_Force_IFU_VB30_SAPEDM_C2-058-C.621.01.01.02_Online.pdf` | TBD | Story 2 — not started |

Per Task 2.1, Story 2 does not start until Story 1 is completed and approved
for `DOC-0136477A`.

## Naming convention

- `manual_id`: same identifier used in `findings_log.csv` (`manual_id` column) and in the Task 2.4 summary table — do not change once assigned, to keep traceability.
- `findings_log.csv` — exact columns: `manual_id, section_id, page_sampled, checklist_ref, result, severity, evidence, notes` (see `docs/SPRINT_TASKS_QA.md` §Task 1.5).
- `consolidated_bugs.csv` — exact columns: `bug_id, title, severity, manuals_affected, sections_affected, suspected_module, escalate` (see §Task 2.3).
