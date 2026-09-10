# Summary — DOC-0136477A (Story 1)

- **456 checklist items evaluated** across 36 sampled sections (15% stratified sample + mandatory additions), 240-page manual.
- **Pass rate: 87.3%** (398 PASS / 58 FAIL). Automated validation (Coverage/Precision/Structure) was PASS, but manual sampling still surfaced real defects — confirming §5.3's warning that PASS is structural, not semantic.
- **FAIL by severity:** 19 Critical, 0 High, 5 Medium, 34 Low.
- **Top finding (escalate):** chapter/appendix-opening "Contents" boxes get misassigned to the first subsection instead of the chapter root — 17 occurrences, 100% of chapter openings touched by the sample. Root cause: `section_matcher.py` reading_order places the table after the first subsection's own content despite being visually first on the page.
- **2nd finding (escalate):** back-matter after the last bookmark (Glossary + Index, 8 pages) silently absorbed into the last bookmarked section (`sec_0279`) with no flag — `page_end` defaults to `total_pages` when there's no next bookmark. Structurally invisible in `tree.json`.
- **3rd finding:** images/tables on shared pages sometimes map to the wrong sibling section (4 occurrences) — same reading_order-adjacency root cause as the Contents-box bug, generalized.
- **Minor:** a decorative footer divider line passes the image aspect-ratio filter (>15:1 threshold, actual ~14:1) in every section with an image — Low severity, cosmetic.
- Automated `PASS`/`FAIL` verdict **agreed** with the manual sample on Coverage/Precision/Structure at the section level, but did not catch the content-misplacement or back-matter-absorption defects, both invisible to those 3 checks by design.
