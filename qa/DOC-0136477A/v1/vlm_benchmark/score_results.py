from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED = {
    "sec_0004": {
        "5.4-hierarchy_level": ("PASS", ""),
        "5.4-page_start_end": ("FAIL", "Critical"),
        "5.6-table_content": ("PASS", ""),
    },
    "sec_0015": {
        "5.4-parent_child": ("PASS", ""),
        "5.4-page_start_end": ("FAIL", "Critical"),
        "5.6-table_content": ("PASS", ""),
    },
    "sec_0279": {
        "5.4-page_start_end": ("FAIL", "Critical"),
        "5.4-gaps_duplicates": ("FAIL", "Medium"),
        "5.6-table_content": ("FAIL", "Medium"),
    },
    "sec_0025": {
        "5.4-hierarchy_level": ("PASS", ""),
        "5.4-page_start_end": ("PASS", ""),
        "5.6-table_content": ("PASS", ""),
    },
    "sec_0066": {
        "5.4-parent_child": ("PASS", ""),
        "5.4-page_start_end": ("PASS", ""),
        "5.4-hierarchy_path": ("PASS", ""),
    },
    "sec_0243": {
        "5.4-hierarchy_level": ("PASS", ""),
        "5.4-page_start_end": ("PASS", ""),
        "5.6-table_content": ("PASS", ""),
    },
}


def score(path: Path) -> dict:
    data = json.loads(path.read_text())
    result_correct = 0
    severity_correct = 0
    valid_json = 0
    exact_section_id = 0
    exact_check_order = 0
    pass_severity_blank = 0
    pass_count = 0
    defect_detected = 0
    defect_total = 0
    clean_false_positive = 0
    details = []

    for case in data["cases"]:
        expected = EXPECTED[case["section_id"]]
        try:
            parsed = json.loads(case["raw_output"])
            valid_json += 1
        except json.JSONDecodeError:
            details.append({"section_id": case["section_id"], "parse_error": True})
            continue

        exact_section_id += parsed.get("section_id") == case["section_id"]
        checks = parsed.get("checks", [])
        got_order = [check.get("checklist_ref") for check in checks]
        exact_check_order += got_order == list(expected)
        got = {check.get("checklist_ref"): check for check in checks}

        case_expected_fail = any(v[0] == "FAIL" for v in expected.values())
        case_got_fail = any(check.get("result") == "FAIL" for check in checks)
        if case_expected_fail:
            defect_total += 1
            defect_detected += case_got_fail
        elif case_got_fail:
            clean_false_positive += 1

        row_details = []
        for ref, (expected_result, expected_severity) in expected.items():
            check = got.get(ref, {})
            got_result = check.get("result")
            got_severity = check.get("severity", "")
            result_correct += got_result == expected_result
            severity_correct += got_severity == expected_severity
            if expected_result == "PASS":
                pass_count += 1
                pass_severity_blank += got_severity == ""
            row_details.append(
                {
                    "ref": ref,
                    "expected": expected_result,
                    "got": got_result,
                    "expected_severity": expected_severity,
                    "got_severity": got_severity,
                    "evidence": check.get("evidence", ""),
                }
            )
        details.append(
            {
                "section_id": case["section_id"],
                "overall_status": parsed.get("overall_status"),
                "rows": row_details,
            }
        )

    return {
        "model": data["model"],
        "total_seconds": sum(c["elapsed_seconds"] for c in data["cases"]),
        "avg_seconds": sum(c["elapsed_seconds"] for c in data["cases"]) / len(data["cases"]),
        "peak_memory_gb": max(c["peak_memory_gb"] for c in data["cases"]),
        "valid_json": valid_json,
        "exact_section_id": exact_section_id,
        "exact_check_order": exact_check_order,
        "result_accuracy": result_correct / 18,
        "severity_accuracy": severity_correct / 18,
        "pass_severity_blank": pass_severity_blank,
        "pass_count": pass_count,
        "defect_sections_detected": defect_detected,
        "defect_sections_total": defect_total,
        "clean_false_positive_sections": clean_false_positive,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = score(args.input)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "details"},
            ensure_ascii=False,
            indent=2,
        )
    )
    print("MISMATCHES")
    for section in report["details"]:
        for row in section.get("rows", []):
            if (
                row["expected"] != row["got"]
                or row["expected_severity"] != row["got_severity"]
            ):
                print(section["section_id"], json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
