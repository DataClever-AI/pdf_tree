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

## Severity guidance

- `Critical`: systemic corruption that makes retrieval, citations, safety-critical meaning, or broad document structure unreliable.
- `High`: major content or structural loss/misassignment with substantial downstream impact.
- `Medium`: localized but meaningful ownership, hierarchy, OCR, table, or image error.
- `Low`: limited noise or presentation defect with little semantic impact.

Severity follows impact and scope, not how many times the same symptom appears. Consolidate repeated manifestations under a root cause and retain representative examples.

## Source and artifact blockers

Stop visual/AI review when the source PDF is missing or its SHA-256 differs from `source_manifest.json`. Report errors when required files are absent, manifest hashes do not match, official CSV columns change, finding keys duplicate, or finalized findings remain incomplete.

Warnings such as semantic nodes slightly crossing numeric section bounds require review. They are not silently ignored and are not automatically defects.
