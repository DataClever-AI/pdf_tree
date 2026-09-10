# Summary — `SOMATOM_Force_IFU_VB30`

**Automated validation:** FAIL (Coverage FAIL: 8 orphaned blocks; Precision FAIL: 7964/10010 nodes misplaced; Structure PASS). **Confidence Index: 0** (floor — weighted fails 1001 vs 757 items evaluated; also capped at 60 by Coverage FAIL regardless).

**Task 1.4 (72/72 sampled sections inspected):** 142/757 checklist items FAIL (118 Critical). Dominant root cause: a **content-stream desync** — `sec_0035` ("Protective measures", p23) absorbed 2221 nodes (semantic_order 336–2556, pages 24–120) meant for dozens of downstream sections, at least 2 more such events recur later in the document. 62/72 sampled sections carry a stray/misplaced node from this family. A second, distinct defect — **body-content extraction gap** — leaves several sections (mostly near doc end) with 0 real nodes despite substantial visible text (worst: `sec_0899`, `sec_0914`, `sec_0938`). The known §7 patterns (chapter-opening sweep, sibling image mismap, back-matter absorption) all recurred; back-matter absorption confirmed exactly as predicted on the mandatory last-section sample (`sec_0951` absorbed the entire Index + back cover, p463–467). New: 3+ instances of meaningful UI icons over-filtered as decorative (p340, p378, p414).

Full evidence: `findings/findings_log.csv` (757 rows) + `findings/checklist_reference.md`.
