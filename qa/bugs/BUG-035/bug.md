---
bug_id: BUG-035
status: open
finding:
fix_branch:
fix_commit:
updated: 2026-10-08
---

# BUG-035 · A formula printed as text is extracted as an empty node: the formula text is lost

**Suspected module:** Docling layout (formula items keep no text); src/tree_builder/docling_extract.py

## Description

AUTOMATIC p147–p149 print formulas as real text, for example "TR = 0.545 × Ti − TC" and "TF = 0.455 × Ti + TC". In the tree their nodes are empty (for example `#/texts/38494` on p148). The formula text is in no other node, so a RAG consumer cannot answer questions that need it.

## Root cause

Not confirmed. Probably Docling labels the block as a formula and keeps no text for it (formula enrichment is off). The nodes were already empty in v1.6, where the row was approved PASS.

## What was done

- 2026-10-08: found by the QA lead in the Phase 3 review of AUTOMATIC v1.7 (`sec_0021|148|5.5-filters_discarding`). The reviewer (Oscar Munoz) chose Medium and asked for a new bug. Registered in `root_causes.json` with a page override for that row.

## Fix

Proposed (deterministic, no AI): when a text item has an empty text, fill it with the PyMuPDF words inside its box, as the table step does for lost table lines (BUG-030). Check first how many empty formula nodes exist in the 7 manuals.

## Verification

Not fixed yet.

## Attempts

| Date | Manual | Version | Commit | Change | Before → After | Regressions | Decision |
|---|---|---|---|---|---|---|---|
