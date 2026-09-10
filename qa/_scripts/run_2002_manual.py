"""
Headless Task 1.1/1.2 runner for `2002_Service_Manual_TI` — invokes the exact
same src.pipeline.pipeline.run_pipeline() call the Streamlit Extraction page
uses (same branch/accelerator config), then writes the same three exports the
Export page offers plus the metrics.json bundle (renamed validation_report.json
per QA_TESTING_WORKFLOW_pdf_tree.md), byte-for-byte in the same shape/field
names. Run via Streamlit UI is impractical here (no browser), so this reuses
the identical pipeline code path instead of re-deriving the logic.

Usage: uv run python qa/_scripts/run_2002_manual.py
"""
from __future__ import annotations

import base64
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.pipeline.pipeline import run_pipeline  # noqa: E402

MANUAL_ID = "2002_Service_Manual_TI"
PDF_PATH = Path("/Users/j/Documents/Dataclever/Manuales técnicos TEST/2002 Service Manual - TI.pdf")
QA_DIR = _PROJECT_ROOT / "qa" / MANUAL_ID
WORK_DIR = _PROJECT_ROOT / "qa" / "_scratch" / MANUAL_ID
WORK_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("pdf_tree.pipeline")
logger.setLevel(logging.INFO)
h = logging.StreamHandler(sys.stdout)
h.setFormatter(logging.Formatter("%(levelname)-8s | %(name)s | %(message)s"))
logger.addHandler(h)


def on_window_complete(idx: int, total: int, elapsed_s: float) -> None:
    logger.info("window %d/%d complete (%.1fs)", idx, total, elapsed_s)


def main() -> None:
    print(f"=== Running pipeline for {MANUAL_ID} ({PDF_PATH.name}) ===", flush=True)
    result = run_pipeline(
        pdf_path=PDF_PATH,
        work_dir=WORK_DIR,
        run_docling=True,
        window_size=120,  # 32GB+ RAM machine — see QA_TESTING_WORKFLOW_pdf_tree.md §1
        window_overlap=6,
        extract_images=True,
        min_image_px=48,
        logger=logger,
        on_window_complete=on_window_complete,
    )

    if result.error:
        print(f"\nPIPELINE FAILED: {result.error}", flush=True)
        sys.exit(1)

    stem = "2002_Service_Manual_TI"

    # --- tree.json (Export page format) ---
    tree_bytes = json.dumps(result.sections, ensure_ascii=False, indent=2).encode()
    (QA_DIR / "exports" / f"{stem}_tree.json").write_bytes(tree_bytes)

    # --- images_v1.json (Export page format) ---
    mapped = [img for img in result.images if img.section_id is not None]
    unmapped = [img for img in result.images if img.section_id is None]
    images_payload = {
        "total": len(result.images),
        "mapped_count": len(mapped),
        "unmapped_count": len(unmapped),
        "images": [
            {
                "section_id": img.section_id,
                "page_no": img.page_no,
                "width_px": img.width_px,
                "height_px": img.height_px,
                "image_b64": base64.b64encode(img.image_bytes).decode(),
            }
            for img in result.images
        ],
    }
    images_bytes = json.dumps(images_payload, ensure_ascii=False, indent=2).encode()
    (QA_DIR / "exports" / f"{stem}_images_v1.json").write_bytes(images_bytes)

    # --- bookmarks.json (Export page format) ---
    bm_payload = [{"level": lvl, "title": title, "page_no": pg} for lvl, title, pg in result.bookmarks]
    bm_bytes = json.dumps(bm_payload, ensure_ascii=False, indent=2).encode()
    (QA_DIR / "exports" / f"{stem}_bookmarks.json").write_bytes(bm_bytes)

    # --- validation_report.json (Metrics page metrics.json bundle, renamed) ---
    metrics_payload = {
        "pdf_name": PDF_PATH.name,
        "summary": {
            "section_count": result.section_count,
            "root_sections": len(result.root_sections),
            "valid": result.valid,
            "docling_text_blocks": result.docling_text_blocks,
            "docling_tables": result.docling_tables,
            "total_pages": result.total_pages,
            "elapsed_s": result.elapsed_s,
            "docling_elapsed_s": result.docling_elapsed_s,
            "fitz_authoritative": result.fitz_authoritative,
            "structural_source": result.structural_source,
        },
        "stage_times": result.stage_times,
        "validation": result.validation.to_dict() if result.validation is not None else None,
    }
    (QA_DIR / "validation_report.json").write_bytes(
        json.dumps(metrics_payload, ensure_ascii=False, indent=2).encode()
    )

    # --- exports_manifest.txt ---
    manifest_lines = [
        f"# exports/ manifest — {MANUAL_ID}",
        "",
        "Not tracked in git (regenerable pipeline output, kept local only —",
        "see qa/README.md for rationale). Files present as of this run:",
        "",
    ]
    for f in sorted((QA_DIR / "exports").iterdir()):
        size = f.stat().st_size
        manifest_lines.append(f"{f.name:<45} {size:>12,} bytes  (~{size / 1024 / 1024:.1f} MB)")
    manifest_lines += [
        "",
        f"To regenerate: uv run python qa/_scripts/run_2002_manual.py",
        "(re-run on the source PDF; batch size 120, overlap 6, images on).",
    ]
    (QA_DIR / "exports_manifest.txt").write_text("\n".join(manifest_lines) + "\n")

    print("\n=== DONE ===", flush=True)
    print(f"total_pages={result.total_pages}", flush=True)
    print(f"sections={result.section_count}", flush=True)
    print(f"structural_source={result.structural_source}", flush=True)
    print(f"fitz_authoritative={result.fitz_authoritative}", flush=True)
    print(f"validation.status={metrics_payload['validation']['status'] if metrics_payload['validation'] else None}", flush=True)
    print(f"images_extracted={len(result.images)}", flush=True)


if __name__ == "__main__":
    main()
