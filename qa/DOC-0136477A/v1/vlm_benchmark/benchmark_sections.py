from __future__ import annotations

# ruff: noqa: E501 -- prompt lines are kept stable for benchmark reproducibility.
import argparse
import json
import os
import resource
import time
from pathlib import Path

from mlx_vlm import generate, load
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config

BASE = Path(os.environ.get("VLM_BENCH_ASSETS", Path(__file__).resolve().parent / "pages"))

SCHEMA = """
Return ONLY valid JSON, without markdown, using exactly this schema:
{
  "section_id": "...",
  "overall_status": "PASS|FAIL|REVIEW",
  "checks": [
    {
      "checklist_ref": "...",
      "result": "PASS|FAIL|REVIEW",
      "severity": "Critical|High|Medium|Low|",
      "evidence": "specific visible evidence",
      "notes": "short reasoning"
    }
  ]
}
Return exactly one entry for every requested checklist_ref, in the requested order.
Preserve the exact section_id supplied in the context. Do not replace it with a title.
Use FAIL only when the supplied images and tree context demonstrate a defect.
Use REVIEW when evidence is insufficient. Never invent visible content.
For PASS or REVIEW, severity must be an empty string. Severity is required only for FAIL.
overall_status is FAIL if any check fails, REVIEW if none fail but one needs review, otherwise PASS.
Write evidence and notes in Spanish.
"""

CHECK_DEFINITIONS = """
Checklist definitions:
- 5.4-hierarchy_level: validate only the numeric nesting level of the heading.
- 5.4-parent_child: validate only parent and child structural relationships.
- 5.4-page_start_end: validate that all content assigned to the section belongs to it and that no visually owned content inside its range was assigned to an adjacent section.
- 5.4-hierarchy_path: validate the path from root to the section.
- 5.4-gaps_duplicates: validate whether visible document sections are absent or duplicated in tree.json.
- 5.6-table_content: validate that a table node represents a genuine table and has real structured content rather than a placeholder. Table placement belongs to 5.4-page_start_end and must not make table_content fail when the table itself is correctly reconstructed.
"""

CASES = [
    {
        "section_id": "sec_0004",
        "kind": "known_defect",
        "images": [BASE / "p17.png"],
        "checks": ["5.4-hierarchy_level", "5.4-page_start_end", "5.6-table_content"],
        "context": """
tree.json section:
- title: 1.2.1 HemoSphere Advanced Monitor with HemoSphere Swan-Ganz Module
- hierarchy_level: 3
- hierarchy_path: /Introduction/1.2 Indications For Use/1.2.1 HemoSphere Advanced Monitor with HemoSphere Swan-Ganz Module
- page_start: 17; page_end: 17; parent: sec_0003 (1.2 Indications For Use)
- section has its own heading, six paragraphs, and one table node.
- table node text begins: Intended Purpose of this Manual ... 17 | Indications For Use ...
- chapter root sec_0001 is Introduction, pages 17-27, and has headings Introduction and Contents.
- table canonical_text is populated, not a placeholder.
Determine whether the table and visible page content assigned to sec_0004 conceptually belong to this subsection.
""",
    },
    {
        "section_id": "sec_0015",
        "kind": "known_defect",
        "images": [BASE / "p26.png", BASE / "p27.png"],
        "checks": ["5.4-parent_child", "5.4-page_start_end", "5.6-table_content"],
        "context": """
tree.json section:
- title: 1.7 Abbreviations Found in This Manual
- hierarchy_level: 2; parent: sec_0001 Introduction; no children
- page_start: 26; page_end: 27
- sec_0015 contains one table node on page 27 beginning LVSWI, MAP, MPAP, OR, PA.
Previous sibling sec_0014 is 1.6 Manual style conventions, page 26.
- sec_0014 contains its conventions table plus two additional tables on page 26 beginning A/D, ART, BSA and Ea dyn, EDV, EDVI.
- all table nodes have populated canonical_text, not placeholders.
Determine visually whether the table ownership across the heading transition on page 26 matches the two sections.
""",
    },
    {
        "section_id": "sec_0279",
        "kind": "known_defect",
        "images": [
            BASE / "end-231.png",
            BASE / "end-232.png",
            BASE / "end-233.png",
            BASE / "p236.png",
            BASE / "p237.png",
            BASE / "p238.png",
            BASE / "p240.png",
        ],
        "checks": ["5.4-page_start_end", "5.4-gaps_duplicates", "5.6-table_content"],
        "context": """
tree.json section:
- title: G.3.6 European Union R&TTE Statements
- hierarchy_level: 3; parent: G.3 Wireless Technology Information
- page_start: 231; page_end: 240; this is the final bookmarked section
- semantic nodes include the G.3.6 heading and regulatory text on pages 231-232.
- semantic nodes later include a Glossary heading on page 233 and many term headings.
- two table nodes on pages 237-238 contain alphabetical terms and page references such as electromagnetic, compatibility, monitoring settings and error messages.
- tree.json contains no separate Glossary or Index sections.
Images are supplied in page order: 231, 232, 233, 236, 237, 238 and 240.
Determine whether pages 231-240 all belong to G.3.6 and whether the two late table nodes are genuine tables from that section.
""",
    },
    {
        "section_id": "sec_0025",
        "kind": "clean_control",
        "images": [BASE / "p41.png"],
        "checks": ["5.4-hierarchy_level", "5.4-page_start_end", "5.6-table_content"],
        "context": """
tree.json section:
- title: 2.6 Applicable Standards
- hierarchy_level: 2; hierarchy_path: /Safety and Symbols/2.6 Applicable Standards
- page_start: 41; page_end: 41; parent: Safety and Symbols; no children
- nodes: heading 2.6 Applicable Standards, caption Table 2-3 Applicable standards, and one populated table grid with Standard and Title columns.
Determine whether the visible page supports these fields and table content.
""",
    },
    {
        "section_id": "sec_0066",
        "kind": "clean_control",
        "images": [BASE / "p69.png", BASE / "p71.png"],
        "checks": ["5.4-parent_child", "5.4-page_start_end", "5.4-hierarchy_path"],
        "context": """
tree.json section:
- title: 5.3.2 Graphical Trend Monitoring View
- hierarchy_level: 3
- hierarchy_path: /Navigating the HemoSphere Advanced Monitor/5.3 Monitor Views/5.3.2 Graphical Trend Monitoring View
- parent: sec_0061, 5.3 Monitor Views
- page_start: 69; page_end: 71
- children: sec_0067, sec_0068, sec_0069
- section nodes describe the graphical trend screen, Figure 5-6, scales and display controls.
Images show the first and last pages of the declared range.
Determine whether the title, nesting and boundaries are visually coherent.
""",
    },
    {
        "section_id": "sec_0243",
        "kind": "clean_control",
        "images": [BASE / "p200.png", BASE / "p205.png"],
        "checks": ["5.4-hierarchy_level", "5.4-page_start_end", "5.6-table_content"],
        "context": """
tree.json section:
- title: Equations for Calculated Patient Parameters
- hierarchy_level: 1; hierarchy_path: /Equations for Calculated Patient Parameters
- page_start: 200; page_end: 205; no parent or children
- nodes include introductory text, Table C-1 Cardiac and oxygenation profile equations, and six populated table nodes across the range.
Images show the first and last pages of the range.
Determine whether this is a coherent root section with correct boundaries and real equation tables.
""",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--section-id", action="append", dest="section_ids")
    parser.add_argument("--eos-token", action="append", type=int, dest="eos_tokens")
    args = parser.parse_args()

    cases = CASES
    if args.section_ids:
        requested = set(args.section_ids)
        cases = [case for case in CASES if case["section_id"] in requested]
        missing = requested - {case["section_id"] for case in cases}
        if missing:
            parser.error(f"unknown section_id: {', '.join(sorted(missing))}")

    load_started = time.perf_counter()
    model, processor = load(args.model)
    config = load_config(args.model)
    load_seconds = time.perf_counter() - load_started

    outputs = []
    for case in cases:
        prompt = (
            "You are validating pdf-tree output against rendered PDF pages. "
            "Follow the requested checklist literally.\n\n"
            + case["context"]
            + "\n"
            + CHECK_DEFINITIONS
            + "\nRequested checklist_ref values: "
            + json.dumps(case["checks"])
            + "\n"
            + SCHEMA
        )
        images = [str(path) for path in case["images"]]
        formatted = apply_chat_template(processor, config, prompt, num_images=len(images))
        started = time.perf_counter()
        generation_options = {
            "max_tokens": args.max_tokens,
            "temperature": 0.0,
            "verbose": False,
        }
        if args.eos_tokens:
            generation_options["eos_tokens"] = args.eos_tokens
        result = generate(
            model,
            processor,
            formatted,
            image=images,
            **generation_options,
        )
        elapsed = time.perf_counter() - started
        outputs.append(
            {
                "section_id": case["section_id"],
                "kind": case["kind"],
                "image_count": len(images),
                "elapsed_seconds": elapsed,
                "prompt_tokens": result.prompt_tokens,
                "generation_tokens": result.generation_tokens,
                "generation_tps": result.generation_tps,
                "peak_memory_gb": result.peak_memory,
                "finish_reason": result.finish_reason,
                "raw_output": result.text,
            }
        )
        print(json.dumps(outputs[-1], ensure_ascii=False), flush=True)

    payload = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "eos_tokens": args.eos_tokens,
        "load_seconds": load_seconds,
        "max_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "cases": outputs,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
