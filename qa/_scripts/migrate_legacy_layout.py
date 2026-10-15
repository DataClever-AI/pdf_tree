#!/usr/bin/env python3
"""Safely migrate pre-versioned QA manual folders into v1."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.qa_workflow.storage import migrate_legacy_layout  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-dir", type=Path, default=PROJECT_ROOT / "qa")
    parser.add_argument(
        "--source-dir", type=Path, default=PROJECT_ROOT.parent / "Manuales técnicos TEST"
    )
    parser.add_argument("--reviewer", default="legacy-migration")
    parser.add_argument("--apply", action="store_true", help="Apply after reviewing the dry run")
    args = parser.parse_args()
    report = migrate_legacy_layout(
        args.qa_dir,
        source_dir=args.source_dir,
        reviewer=args.reviewer,
        dry_run=not args.apply,
    )
    print(
        json.dumps(
            {
                "dry_run": report.dry_run,
                "ok": report.ok,
                "migrated_manuals": report.migrated_manuals,
                "conflicts": report.conflicts,
                "actions": [asdict(action) for action in report.actions],
            },
            indent=2,
        )
    )
    if report.conflicts:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
