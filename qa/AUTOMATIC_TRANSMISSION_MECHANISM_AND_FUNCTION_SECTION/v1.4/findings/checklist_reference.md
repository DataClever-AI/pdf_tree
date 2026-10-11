# Checklist reference — `AUTOMATIC_TRANSMISSION_MECHANISM_AND_FUNCTION_SECTION`

| checklist_ref | Plain-language question |
|---|---|
| `5.4-hierarchy_level` | Does hierarchy_level match the bookmark nesting in the PDF? |
| `5.4-parent_child` | Are parent_section_id and child_sections structurally coherent? |
| `5.4-page_start_end` | Does the section content actually start and end on the declared pages? |
| `5.4-hierarchy_path` | Does hierarchy_path reflect the real path from the root? |
| `5.4-gaps_duplicates` | Does the section appear exactly once, without gaps or duplicates? |
| `5.4-flagged_for_review` | When flagged, is the inferred boundary or title actually correct? |
| `5.4-structural_source` | When inferred, does extra visual scrutiny confirm the structure? |
| `5.6-numbering_scheme` | Is the numbering scheme correct at this section boundary? |
| `5.6-offset_applied` | Is the applied page offset plausible compared with neighboring sections? |
| `5.6-table_content` | Does every table node contain the real grid content? |
| `5.5-filters_discarding` | Are all relevant diagrams or screenshots present, including when none were extracted? |
| `5.5-filters_passing_noise` | Are logos, rules, or decorative icons excluded from extracted images? |
| `5.5-image_section_mapping` | Do visible/extracted images belong to the correct deepest section? |
| `5.6-sanity_report` | If the pipeline aborted, is the cause recorded in the sanity report? |
