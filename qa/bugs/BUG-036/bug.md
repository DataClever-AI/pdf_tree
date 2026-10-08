---
bug_id: BUG-036
status: open
finding:
fix_branch:
fix_commit:
updated: 2026-10-08
---

# BUG-036 · Printed text is deformed in the tree: line-break hyphens kept, split subscripts, spaced degree signs, control characters

**Suspected module:** Docling text cells (PyPdfium/docling-parse); no normalization step yet (planned Phase 4)

## Description

The text is in the tree, but written differently from the PDF. Exact search for the word fails, so a RAG consumer can miss it.

- Line-break hyphens kept in table cells: 'pres- sure' (AUTOMATIC p27), 'emis- sion' (2002 p94), 'auto- matically' (SOMATOM p149). About 130 cases, almost all in tables.
- Split subscripts: 'CO 2', 'SpO 2' instead of 'CO2', 'SpO2' (Philips p83, DOC p200). About 400 cases.
- Spaced degree signs: '45 ° C' instead of '45°C' (Philips p110, LOGIQ_S8 p82). About 150 cases.
- Control characters: 'com\x02 pressor' (2002 p158), 'V\x02 Nav' (LOGIQ_S8 p687). About 210 cases, mostly in text nodes.
- Repeated characters: '1 mVp Vpp ,206 bpm' instead of '1 mVpp, 206 bpm' (Philips p443). Rare.

## Root cause

Not confirmed. The text readers keep the PDF's line-break hyphen and its subscript and degree glyphs as separate runs; Docling joins paragraph lines but not lines inside table cells. The control character is probably a soft hyphen glyph without a Unicode mapping.

## What was done

- 2026-10-08: counted during the Phase 3 analysis (`../doc/PLAN_FASE3_TABLAS_2026-10-08_pdf_tree.md`, decision D2). The reviewer (Oscar Munoz) decided that a line-break hyphen kept in a table cell is FAIL Low in every manual and asked for this bug. The rule in `root_causes.json` matches the rows with that note (`Low by the reviewer rule of 2026-10-08 (line-break hyphens in cells)`).

## Fix

Planned in Phase 4 (deterministic, no AI): a text normalization step for cells and text nodes. Join 'pres- sure' when the joined word is printed on the page; join a subscript digit with its letters; remove the space before '°' and between '°' and C/F; drop control characters. Each rule needs a check that it does not damage real text, such as '2-4 brake' or 'pre- and post-'.

## Verification

Not fixed yet.

## Attempts

| Date | Manual | Version | Commit | Change | Before → After | Regressions | Decision |
|---|---|---|---|---|---|---|---|
