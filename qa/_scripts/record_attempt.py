"""
Record one mitigation attempt in qa/bugs/<bug_id>/bug.md: compares the candidate version
(e.g. v2.1) with its base and appends a row to the Attempts table with the date, commit,
paired FAIL count before -> after, regressions and the decision. Then refreshes the registry.

Only --change and --decision are written by hand; keep them to one or two plain sentences.

Usage:
  uv run python qa/_scripts/record_attempt.py --bug BUG-019 \\
      --manual 2002_Service_Manual_TI --candidate v2.1 \\
      --change "Ignore empty headings; prefer exact title match." \\
      --decision "Keep: 7 -> 0 on paired rows, no regressions." --status mitigated
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(QA_DIR.parent))

from src.qa_workflow.bug_registry import (  # noqa: E402
    STATUSES,
    Attempt,
    append_attempt,
    collect_occurrences,
    set_front_matter_field,
    write_registry,
)
from src.qa_workflow.compare import compare_versions  # noqa: E402
from src.qa_workflow.root_causes import CATALOGUE_FILENAME, load_catalogue  # noqa: E402
from src.qa_workflow.storage import atomic_write_text, open_qa_version  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bug", required=True)
    parser.add_argument("--manual", required=True)
    parser.add_argument("--candidate", required=True, help="mitigation version, e.g. v2.1")
    parser.add_argument("--base", help="defaults to the candidate's base_version")
    parser.add_argument("--change", required=True)
    parser.add_argument("--decision", required=True)
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--official-only", action="store_true")
    parser.add_argument("--qa-root", type=Path, default=QA_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args()
    qa_dir: Path = args.qa_root

    catalogue = load_catalogue(qa_dir / "confidence_index" / CATALOGUE_FILENAME)
    if args.bug not in catalogue.bugs:
        sys.exit(f"Unknown bug id: {args.bug}")
    candidate = open_qa_version(qa_dir, args.manual, args.candidate)
    mitigation = candidate.version_manifest.get("mitigation") or {}
    base = args.base or mitigation.get("base_version")
    if not base:
        sys.exit(f"{args.candidate} has no base_version; pass --base")
    comparison = compare_versions(
        qa_dir,
        args.manual,
        base,
        args.candidate,
        catalogue,
        include_drafts=not args.official_only,
    )
    delta = next((bug for bug in comparison.bugs if bug.bug_id == args.bug), None)
    before, after = (delta.base_paired, delta.candidate_paired) if delta else (0, 0)
    regressions = sum(1 for change in comparison.row_changes if change.kind == "regression")
    commit = mitigation.get("pipeline_commit", "")
    attempt = Attempt(
        date.today().isoformat(),
        args.manual,
        args.candidate,
        f"`{commit[:7]}` {mitigation.get('pipeline_subject', '')}".strip() if commit else "—",
        args.change,
        before,
        after,
        regressions,
        args.decision,
    )
    record = qa_dir / "bugs" / args.bug / "bug.md"
    text = append_attempt(record.read_text(encoding="utf-8"), attempt)
    if args.status:
        text = set_front_matter_field(text, "status", args.status)
    atomic_write_text(record, text)
    write_registry(qa_dir / "bugs", catalogue, collect_occurrences(qa_dir, catalogue), attempt.date)
    reviewed = f"{comparison.candidate_reviewed}/{comparison.candidate_rows}"
    print(f"Recorded in {record.relative_to(qa_dir.parent)}")
    print(f"  {args.bug}: {before} -> {after} on {comparison.paired_rows} paired rows")
    print(f"  regressions: {regressions}; candidate rows reviewed: {reviewed}")


if __name__ == "__main__":
    main()
