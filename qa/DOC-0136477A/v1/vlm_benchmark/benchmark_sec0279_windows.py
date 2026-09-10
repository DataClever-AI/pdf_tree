from __future__ import annotations

import argparse
import json
import resource
import time
from pathlib import Path

from benchmark_sections import BASE, CHECK_DEFINITIONS, SCHEMA
from mlx_vlm import generate, load
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config

SECTION_ID = "sec_0279"
CONTEXT = """
tree.json section:
- section_id: sec_0279
- title: G.3.6 European Union R&TTE Statements
- hierarchy_level: 3; parent: G.3 Wireless Technology Information
- page_start: 231; page_end: 240; this is the final bookmarked section
- semantic nodes contain G.3.6 regulatory text on pages 231-232, a Glossary heading
  and terms from page 233, and two table nodes on pages 237-238 with alphabetical
  terms and page references.
- tree.json contains no separate Glossary or Index sections.
Evaluate only the supplied page window. A defect visible in any window is enough to
fail the applicable full-section check. Do not infer that an omitted page is clean.
"""

WINDOWS = [
    {
        "name": "boundary_and_glossary",
        "pages": [231, 232, 233],
        "images": [BASE / "end-231.png", BASE / "end-232.png", BASE / "end-233.png"],
        "checks": ["5.4-page_start_end", "5.4-gaps_duplicates"],
    },
    {
        "name": "index_tables",
        "pages": [236, 237, 238],
        "images": [BASE / "p236.png", BASE / "p237.png", BASE / "p238.png"],
        "checks": ["5.4-gaps_duplicates", "5.6-table_content"],
    },
    {
        "name": "declared_end",
        "pages": [240],
        "images": [BASE / "p240.png"],
        "checks": ["5.4-page_start_end", "5.4-gaps_duplicates"],
    },
]

SEVERITY_RANK = {"": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def combine(windows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for window in windows:
        for check in window["parsed"].get("checks", []):
            grouped.setdefault(check.get("checklist_ref", ""), []).append(
                {**check, "window": window["name"]}
            )

    combined = []
    for ref in ["5.4-page_start_end", "5.4-gaps_duplicates", "5.6-table_content"]:
        observations = grouped.get(ref, [])
        failures = [item for item in observations if item.get("result") == "FAIL"]
        reviews = [item for item in observations if item.get("result") == "REVIEW"]
        if not observations:
            result, severity = "REVIEW", ""
        elif failures:
            result = "FAIL"
            severity = max(
                (item.get("severity", "") for item in failures),
                key=lambda value: SEVERITY_RANK.get(value, -1),
            )
        elif reviews:
            result, severity = "REVIEW", ""
        else:
            result, severity = "PASS", ""
        combined.append(
            {
                "checklist_ref": ref,
                "result": result,
                "severity": severity,
                "observations": observations,
            }
        )
    return combined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=900)
    args = parser.parse_args()

    loaded = time.perf_counter()
    model, processor = load(args.model)
    config = load_config(args.model)
    load_seconds = time.perf_counter() - loaded

    outputs = []
    for window in WINDOWS:
        prompt = (
            "You are validating pdf-tree output against a labeled window of rendered "
            "PDF pages. Follow the requested checklist literally.\n\n"
            + CONTEXT
            + f"\nSupplied PDF page numbers in image order: {window['pages']}\n"
            + CHECK_DEFINITIONS
            + "\nRequested checklist_ref values: "
            + json.dumps(window["checks"])
            + "\n"
            + SCHEMA
        )
        images = [str(path) for path in window["images"]]
        formatted = apply_chat_template(processor, config, prompt, num_images=len(images))
        started = time.perf_counter()
        result = generate(
            model,
            processor,
            formatted,
            image=images,
            max_tokens=args.max_tokens,
            temperature=0.0,
            verbose=False,
        )
        parsed = json.loads(result.text)
        output = {
            "name": window["name"],
            "pages": window["pages"],
            "elapsed_seconds": time.perf_counter() - started,
            "prompt_tokens": result.prompt_tokens,
            "generation_tokens": result.generation_tokens,
            "peak_memory_gb": result.peak_memory,
            "model_section_id": parsed.get("section_id"),
            "parsed": parsed,
        }
        outputs.append(output)
        print(json.dumps(output, ensure_ascii=False), flush=True)

    payload = {
        "model": args.model,
        "section_id": SECTION_ID,
        "load_seconds": load_seconds,
        "max_tokens": args.max_tokens,
        "max_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "total_seconds": sum(item["elapsed_seconds"] for item in outputs),
        "windows": outputs,
        "combined": combine(outputs),
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"combined": payload["combined"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
