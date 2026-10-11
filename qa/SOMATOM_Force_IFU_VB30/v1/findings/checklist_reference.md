# Checklist reference - `SOMATOM_Force_IFU_VB30`

One question per `checklist_ref` value used in `findings_log.csv`.

| checklist_ref | Question |
|---|---|
| `5.4-flagged_for_review` | If flagged_for_review: true, manually confirmed genuinely right/wrong. |
| `5.4-gaps_duplicates` | No gaps, no duplicates - section appears exactly once, matching the PDF index. |
| `5.4-hierarchy_level` | hierarchy_level matches the bookmark's real nesting level in the PDF. |
| `5.4-hierarchy_path` | hierarchy_path reflects the real path from the root. |
| `5.4-page_start_end` | Opened page_start/page_end - section content actually starts/ends there. |
| `5.4-parent_child` | parent_section_id / child_sections are structurally coherent. |
| `5.4-structural_source` | If structural_source is 'inferred', extra scrutiny applied. |
| `5.5-filters_discarding` | Relevant diagrams/screenshots are not being discarded by the image filters. |
| `5.5-filters_passing_noise` | Logos/icons are not incorrectly passing the image filters. |
| `5.5-image_section_mapping` | Images map to the correct (deepest) section, especially on pages shared by sibling sections. |
| `5.6-numbering_scheme` | numbering_scheme transitions correctly at this section boundary. |
| `5.6-offset_applied` | offset_applied has no large unexplained delta vs. adjacent sections. |
| `5.6-sanity_report` | If the pipeline aborted, the cause is recorded in sanity_report (document-level, not section-level). |
| `5.6-table_content` | Table node canonical_text has a real markdown grid, not an empty '[Table RxC]' placeholder. |
