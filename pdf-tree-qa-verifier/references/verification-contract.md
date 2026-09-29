# PDF Tree QA verification contract

Use this reference after reading the three project documents in `doc/`. It condenses machine-checkable interfaces and judgment boundaries; it does not replace the evaluation guide.

## Official finding identity and columns

`findings/findings_log.csv` must preserve exactly these eight columns and this order:

```text
manual_id,section_id,page_sampled,checklist_ref,result,severity,evidence,notes
```

The stable identity is:

```text
manual_id|section_id|page_sampled|checklist_ref
```

The official CSV stores reviewed findings. Agent and VLM output is always a draft and must not write this file directly.

## Agent result format

Accept either a JSON array or an object with a `findings` array. Each finding must contain:

```json
{
  "section_id": "sec_0001",
  "page_sampled": 10,
  "checklist_ref": "5.4-page_start_end",
  "result": "PASS",
  "severity": "",
  "evidence": "Specific observable evidence in English",
  "notes": "",
  "confidence": 0.93
}
```

Rules:

- `result` is `PASS` or `FAIL`.
- FAIL requires `Critical`, `High`, `Medium`, or `Low` severity.
- PASS requires empty severity.
- Evidence is non-empty, specific, and in English.
- Confidence is numeric from 0 through 1.
- Every row must exist in `input/findings_template.csv`.
- No stable identity may be duplicated or omitted.
- Invalid rows remain pending; never coerce them to PASS.

## Checklist routing

| Reference | Verify |
|---|---|
| `5.4-hierarchy_level` | Visual heading level agrees with `hierarchy_level`. |
| `5.4-parent_child` | Parent and children reflect document structure. |
| `5.4-page_start_end` | Semantic start/end boundaries are correct; no neighboring content is absorbed or lost. |
| `5.4-hierarchy_path` | Full ancestry path is correct and ordered. |
| `5.4-gaps_duplicates` | No missing, duplicated, or overlapping structural coverage. |
| `5.4-flagged_for_review` | The flag correctly represents uncertainty; flag state alone is not a failure. |
| `5.4-structural_source` | TOC/inferred provenance is supported by evidence. |
| `5.6-numbering_scheme` | Printed numbering convention is identified correctly. |
| `5.6-offset_applied` | Printed and physical page mapping is correct. |
| `5.6-table_content` | Extracted table text/structure matches the rendered table. |
| `5.5-filters_discarding` | Meaningful visual content was not incorrectly discarded. |
| `5.5-filters_passing_noise` | Decorative or irrelevant noise was not retained as content. |
| `5.5-image_section_mapping` | Every relevant visual is assigned to its semantic section, including verification when none was extracted. |
| `5.6-sanity_report` | Document-level report counts and conclusions agree with artifacts. |

All sampled sections receive the 5.4 structural checks, numbering/offset checks, and all 5.5 visual checks. `5.6-table_content` applies when a table is present. `5.6-sanity_report` is document-level.

## Evidence quality

Good evidence names the page, visible cue, extracted value, and comparison. For example:

```text
On physical page 17, the subsection heading begins above two indication paragraphs; the following Contents table is a chapter-level navigation element and is not part of subsection 1.2.1.
```

Avoid evidence such as “looks correct,” “the JSON says so,” or a restatement of the result. Do not invent OCR text that cannot be read in the rendering.

For `5.4-page_start_end`, explain both the numeric boundary and semantic ownership. A node on a valid page may still violate the boundary if it belongs to an ancestor, sibling, header/footer, or following section.

## Severity scale (authoritative: `doc/SPRINT_TASKS_QA_pdf_tree.md`)

Use the Sprint's definitional scale. It drives the Confidence Index weights
(Critical 8, High 4, Medium 2, Low 1), so every manual must be graded the same way.
Do not grade by perceived impact; grade by defect type.

| Severity | Definition (Sprint) | Sprint example |
|---|---|---|
| `Critical` | Content is placed in the wrong section, is lost completely, or the hierarchy is broken (cycle, missing parent, wrong nesting) | A subsection's content assigned to its sibling; `parent_section_id` pointing to the wrong chapter |
| `High` | A `flagged_for_review` section is confirmed wrong, or `page_start`/`page_end` is off by more than 1 page | Section boundary two pages off because of offset miscalibration |
| `Medium` | Content is correctly placed but a supporting field is wrong or degraded | Image assigned to the wrong sibling on a shared page; inconsistent `offset_applied` |
| `Low` | Cosmetic or non-blocking defect that does not affect retrieving the correct content | Empty table placeholder whose information survives in surrounding text |

### Mapping of known patterns

| Pattern | Checklist row | Severity |
|---|---|---|
| Section heading or body nodes assigned to another section (parent, sibling or child) | `5.4-page_start_end`, `5.4-gaps_duplicates` | Critical |
| Section left empty (only its heading) because its body went to a neighbour | `5.4-page_start_end`, `5.4-gaps_duplicates` | Critical |
| Table printed under one heading assigned to another section | `5.4-page_start_end` | Critical |
| Unbookmarked back-matter (index, glossary, covers) absorbed into the last section | `5.4-page_start_end`, `5.4-gaps_duplicates` | Critical |
| Meaningful figure missing from the image output (vector-only drawing, or raster dropped by a filter) whose information is not in the text | `5.5-filters_discarding` | Critical |
| Boundary off by more than 1 page | `5.4-page_start_end` | High |
| `page_end` one page short while all nodes are correctly owned | `5.4-page_start_end` | Medium |
| Image mapped to the wrong sibling on a shared page | `5.5-image_section_mapping` | Medium |
| Table text present but cells merged/shifted so that values change meaning or can no longer be attributed to their column | `5.6-table_content` | Medium |
| Printed numbering scheme not represented (e.g. roman index folios inside an arabic section) | `5.6-numbering_scheme` | Medium |
| Only boilerplate crosses a boundary (running headers, chapter numbers, folios, invisible print slugs) | `5.4-page_start_end` | Low |
| Small icon dropped whose meaning is fully stated in the text | `5.5-filters_discarding` | Low |
| Table cells merged but reading order and values preserved; empty `[Table 0x0]` placeholder; header rows misdetected as tables | `5.6-table_content` | Low |
| Decorative element (rule, footer divider, logo) kept as an image | `5.5-filters_passing_noise` | Low |

If a case fits two rows, use the more severe one and say why in `notes`. Consolidate
repeated manifestations under one root cause in Task 2.3, but still grade every row.
Run `scripts/verify_claims.py` on every draft: it recomputes the deterministic
signals behind these patterns and flags severity that does not match this table.

## Source and artifact blockers

Stop visual/AI review when the source PDF is missing or its SHA-256 differs from `source_manifest.json`. Report errors when required files are absent, manifest hashes do not match, official CSV columns change, finding keys duplicate, or finalized findings remain incomplete.

Warnings such as semantic nodes slightly crossing numeric section bounds require review. They are not silently ignored and are not automatically defects.
