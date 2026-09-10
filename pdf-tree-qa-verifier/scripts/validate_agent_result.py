#!/usr/bin/env python3
"""Validate a PDF Tree agent draft without modifying QA artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

OFFICIAL_COLUMNS = [
    "manual_id",
    "section_id",
    "page_sampled",
    "checklist_ref",
    "result",
    "severity",
    "evidence",
    "notes",
]
SEVERITIES = {"Critical", "High", "Medium", "Low"}


def key(row: dict[str, Any], default_manual: str = "") -> tuple[str, str, int, str]:
    manual = str(row.get("manual_id") or default_manual).strip()
    try:
        page = int(row.get("page_sampled"))
    except (TypeError, ValueError) as exc:
        raise ValueError("page_sampled must be an integer") from exc
    return (
        manual,
        str(row.get("section_id", "")).strip(),
        page,
        str(row.get("checklist_ref", "")).strip(),
    )


def load_template(path: Path) -> tuple[dict[tuple[str, str, int, str], dict[str, str]], str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != OFFICIAL_COLUMNS:
            raise ValueError(
                f"template columns must be exactly {OFFICIAL_COLUMNS}; got {reader.fieldnames}"
            )
        rows = list(reader)
    if not rows:
        raise ValueError("template has no rows")
    manuals = {row["manual_id"].strip() for row in rows}
    if len(manuals) != 1 or "" in manuals:
        raise ValueError("template must contain exactly one non-empty manual_id")
    manual = next(iter(manuals))
    indexed: dict[tuple[str, str, int, str], dict[str, str]] = {}
    for row in rows:
        row_key = key(row)
        if row_key in indexed:
            raise ValueError(f"duplicate template row: {'|'.join(map(str, row_key))}")
        indexed[row_key] = row
    return indexed, manual


def load_result(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        payload = payload.get("findings")
    if not isinstance(payload, list):
        raise ValueError("result must be a JSON array or an object with a findings array")
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError("every finding must be a JSON object")
    return payload


def validate(batch_root: Path) -> list[str]:
    template_path = batch_root / "input" / "findings_template.csv"
    result_path = batch_root / "output" / "findings_result.json"
    if not template_path.is_file():
        return [f"missing template: {template_path}"]
    if not result_path.is_file():
        return [f"missing result: {result_path}"]

    try:
        template, manual = load_template(template_path)
        rows = load_result(result_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    errors: list[str] = []
    seen: set[tuple[str, str, int, str]] = set()
    for index, row in enumerate(rows, start=1):
        prefix = f"row {index}"
        try:
            row_key = key(row, manual)
        except ValueError as exc:
            errors.append(f"{prefix}: {exc}")
            continue
        label = "|".join(map(str, row_key))
        if row_key in seen:
            errors.append(f"{prefix}: duplicate finding {label}")
            continue
        seen.add(row_key)
        if row_key not in template:
            errors.append(f"{prefix}: finding is not present in template: {label}")

        result = str(row.get("result", "")).strip().upper()
        severity = str(row.get("severity", "")).strip()
        evidence = str(row.get("evidence", "")).strip()
        if result not in {"PASS", "FAIL"}:
            errors.append(f"{prefix}: result must be PASS or FAIL")
        elif result == "PASS" and severity:
            errors.append(f"{prefix}: PASS severity must be empty")
        elif result == "FAIL" and severity not in SEVERITIES:
            errors.append(f"{prefix}: FAIL severity must be one of {sorted(SEVERITIES)}")
        if not evidence:
            errors.append(f"{prefix}: evidence is required")
        confidence = row.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            errors.append(f"{prefix}: confidence must be numeric")
        elif not 0 <= float(confidence) <= 1:
            errors.append(f"{prefix}: confidence must be between 0 and 1")

    missing = sorted(set(template) - seen)
    for row_key in missing:
        errors.append(f"missing finding: {'|'.join(map(str, row_key))}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", required=True, type=Path)
    args = parser.parse_args()
    errors = validate(args.batch_root.resolve())
    if errors:
        print(f"FAIL: {len(errors)} validation error(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: agent result matches the template and schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
