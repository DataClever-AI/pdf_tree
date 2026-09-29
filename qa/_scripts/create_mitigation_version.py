"""
Create a mitigation version (e.g. v2.1) of one manual after a bug fix: run the current
pipeline on the source PDF recorded by the base version and write a new QA version whose
manifest names the target bugs and the pipeline commit. The base version is not modified.

The sample is the official 15 % sample of the new tree plus check rows: every pair the base
version reviewed, the pairs where the target bugs were seen, and a few random pages.

Usage:
  uv run python qa/_scripts/create_mitigation_version.py \\
      --manual 2002_Service_Manual_TI --base v2 --version v2.1 --bugs BUG-019
"""

from __future__ import annotations

import argparse
import io
import logging
import subprocess
import sys
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = QA_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.qa_workflow.mitigation import (  # noqa: E402
    PipelineInfo,
    create_mitigation_version,
    validate_mitigation_name,
)
from src.qa_workflow.root_causes import (  # noqa: E402
    CATALOGUE_FILENAME,
    classify,
    load_catalogue,
    load_version_rows,
)
from src.qa_workflow.storage import open_qa_version  # noqa: E402


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def pipeline_info() -> PipelineInfo:
    dirty = bool(_git("status", "--porcelain", "--", "src"))
    return PipelineInfo(_git("rev-parse", "HEAD"), _git("log", "-1", "--format=%s"), dirty)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manual", required=True)
    parser.add_argument("--base", required=True, help="base version, e.g. v2")
    parser.add_argument("--version", required=True, help="new version, e.g. v2.1")
    parser.add_argument("--bugs", nargs="+", required=True, help="target bug ids")
    parser.add_argument("--extra-pages", type=int, default=5)
    parser.add_argument("--window-size", type=int, default=120)
    parser.add_argument("--window-overlap", type=int, default=6)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="run with uncommitted changes in src/ (recorded as pipeline_dirty)",
    )
    args = parser.parse_args()

    validate_mitigation_name(args.base, args.version)
    catalogue = load_catalogue(QA_DIR / "confidence_index" / CATALOGUE_FILENAME)
    unknown = sorted(set(args.bugs) - set(catalogue.bugs))
    if unknown:
        sys.exit(f"Unknown bug ids: {', '.join(unknown)}")
    if (QA_DIR / args.manual / args.version).exists():
        sys.exit(f"{args.manual}/{args.version} already exists; versions are never overwritten")
    info = pipeline_info()
    if info.dirty and not args.allow_dirty:
        sys.exit("src/ has uncommitted changes; commit the fix first (or use --allow-dirty)")

    base = open_qa_version(QA_DIR, args.manual, args.base)
    occurrences = {
        (row["section_id"], int(row["page_sampled"]))
        for row in load_version_rows(base.root, include_drafts=True)
        if row.get("result", "").upper() == "FAIL"
        and str(row.get("page_sampled", "")).isdigit()
        and classify(catalogue, args.manual, row) in args.bugs
    }

    from src.pipeline.pipeline import run_pipeline

    log_buffer = io.StringIO()
    logger = logging.getLogger("pdf_tree.pipeline")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(levelname)-8s | %(name)s | %(message)s")
    for handler in (logging.StreamHandler(sys.stdout), logging.StreamHandler(log_buffer)):
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    pdf_path = Path(base.source_manifest["path"])
    print(f"Running pipeline for {args.manual} ({pdf_path.name}) at {info.commit[:7]}", flush=True)
    result = run_pipeline(
        pdf_path=pdf_path,
        work_dir=QA_DIR / "_scratch" / args.manual,
        run_docling=True,
        window_size=args.window_size,
        window_overlap=args.window_overlap,
        extract_images=True,
        min_image_px=48,
        logger=logger,
    )
    if result.error:
        sys.exit(f"Pipeline failed: {result.error}")

    validation = {
        "pdf_name": pdf_path.name,
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
    qa_version, plan, rows = create_mitigation_version(
        QA_DIR,
        args.manual,
        args.base,
        args.version,
        targets=args.bugs,
        pipeline=info,
        sections=result.sections,
        total_pages=result.total_pages,
        images=result.images,
        bookmarks=result.bookmarks,
        validation_report=validation,
        run_log=log_buffer.getvalue(),
        occurrence_pairs=occurrences,
        extra_pages=args.extra_pages,
    )
    print(f"\nCreated {qa_version.root.relative_to(PROJECT_ROOT)}")
    print(f"  targets: {', '.join(sorted(args.bugs))}; base {args.base}")
    print(f"  official sample: {plan.sample.quota} pages; check rows: {len(plan.check_rows)}")
    print(f"  findings template: {rows} rows ({len(occurrences)} bug occurrence pairs)")
    print("Next: review the version (agents + reviewer), then compare it on the Version Compare")
    print("page and record the attempt with qa/_scripts/record_attempt.py.")


if __name__ == "__main__":
    main()
