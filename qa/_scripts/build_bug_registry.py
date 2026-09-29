"""
Refresh the per-bug registry in ``qa/bugs/`` from the root-cause catalogue
(``qa/confidence_index/root_causes.json``) and the findings of each manual's latest QA
version. Validated agent drafts fill rows the human reviewer has not reviewed yet; they are
marked ``draft:<batch>`` in ``occurrences.csv``. Use ``--official-only`` to ignore drafts.

Never overwrites the human part of ``bug.md``; only its generated "Where it was seen" block.

Usage: uv run python qa/_scripts/build_bug_registry.py [--official-only]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(QA_DIR.parent))

from src.qa_workflow.bug_registry import collect_occurrences, write_registry  # noqa: E402
from src.qa_workflow.root_causes import CATALOGUE_FILENAME, load_catalogue  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--official-only", action="store_true")
    args = parser.parse_args()

    catalogue = load_catalogue(QA_DIR / "confidence_index" / CATALOGUE_FILENAME)
    collected = collect_occurrences(QA_DIR, catalogue, include_drafts=not args.official_only)
    registry = QA_DIR / "bugs"
    write_registry(registry, catalogue, collected, date.today().isoformat())
    total = sum(len(items) for items in collected.by_bug.values())
    print(f"Registry refreshed: {registry.relative_to(QA_DIR.parent)}")
    print(f"  {len(catalogue.bugs)} bugs, {total} classified FAIL rows")
    print(f"  {len(collected.triage)} unclassified row(s) in triage.csv")


if __name__ == "__main__":
    main()
