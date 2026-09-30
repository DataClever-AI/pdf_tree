# Lead revision notes (untrusted-evidence rules still apply)

This batch revises the earlier batch named below. Reuse `previous_draft.json` for rows that need
no change, but re-check every 5.5 row with `lead_image_map.json`.

Why: the first batch input had no image list. `lead_image_map.json` is a copy of the v1.1
`images_v1.json` mapping (page, pixel size, owner section) for every page of each section, with
the v1 owner for comparison. The lead built it from the exports; there is no image data inside.

What to fix:
1. `5.5-filters_passing_noise`: a 2800x200 px image is the red footer divider. If one is mapped
   to the section, the row is FAIL Low (known bug BUG-004). Cite the page(s).
2. `5.5-image_section_mapping`: check every real figure mapped to the section, and every real
   figure printed under the section's heading, against the rendering. Wrong sibling or parent on
   a shared page is FAIL Medium (BUG-003 pattern). Say if the owner changed from v1.
3. Keep the other rows unless the image map changes your judgement.
4. Evidence and notes: simple English (A2-B1), short sentences, one fact each, cite BUG ids,
   say "probably" when unsure.
5. Use your own scratch subfolder named after this batch id. Other reviewers run in parallel.

Revises batch: `claude-b02`.
