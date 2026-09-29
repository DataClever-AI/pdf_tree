from __future__ import annotations

from pathlib import Path

import pytest

from src.qa_workflow.ai_review import FindingDraft
from src.qa_workflow.confidence import (
    build_confidence_report,
    calculate_confidence,
    normalize_severity,
)
from src.qa_workflow.findings import FindingRow, stable_finding_key, write_findings_template
from src.qa_workflow.review import (
    bulk_approve_all,
    bulk_approve_eligible,
    finalize_review,
    load_findings,
    load_review_state,
    merge_drafts_into_state,
    pending_approvals,
    prioritize_findings,
    save_review_decision,
)
from src.qa_workflow.storage import (
    create_qa_version,
    open_qa_version,
    set_version_status,
    write_pipeline_artifacts,
)


def _draft(row, *, result="PASS", confidence=0.95):
    return FindingDraft(
        row["manual_id"],
        row["section_id"],
        row["page_sampled"],
        row["checklist_ref"],
        result,
        "High" if result == "FAIL" else "",
        "Specific source evidence",
        "",
        confidence,
        "test",
    )


def test_editing_finalized_version_reopens_it(qa_version) -> None:
    row = load_findings(qa_version.findings_csv)[0]
    final = set_version_status(qa_version, "finalized")
    save_review_decision(
        final,
        stable_finding_key(row),
        result="PASS",
        severity="",
        evidence="Human evidence",
        notes="",
        reviewer="Alice",
    )
    opened = open_qa_version(final.qa_root, final.manual_id, final.version)
    assert opened.version_manifest["status"] == "in_review"


def test_bulk_approval_excludes_priority_sample(qa_version) -> None:
    rows = load_findings(qa_version.findings_csv)
    merge_drafts_into_state(qa_version, [_draft(row) for row in rows])
    count = bulk_approve_eligible(qa_version, reviewer="Alice")
    assert count == 0  # minimum-three PASS audit covers this two-row fixture


def test_bulk_approve_all_includes_fail_rows_and_respects_keys(qa_version) -> None:
    rows = load_findings(qa_version.findings_csv)
    keys = [stable_finding_key(row) for row in rows]
    state = merge_drafts_into_state(
        qa_version, [_draft(rows[0], result="FAIL", confidence=0.5), _draft(rows[1])]
    )
    assert pending_approvals(state) == {"PASS": [keys[1]], "FAIL": [keys[0]], "invalid": []}

    assert bulk_approve_all(qa_version, reviewer="Alice", keys=[keys[0]]) == 1
    state = load_review_state(qa_version)
    assert state["decisions"][keys[0]]["approval_mode"] == "bulk-all"
    assert not state["decisions"][keys[1]]["approved"]
    assert load_findings(qa_version.findings_csv)[0]["result"] == "FAIL"

    assert bulk_approve_all(qa_version, reviewer="Alice") == 1
    assert bulk_approve_all(qa_version, reviewer="Alice") == 0
    assert list((qa_version.root / "findings" / "backups").iterdir())
    finalize_review(qa_version)


def test_priority_order_fail_low_confidence_flag_and_pass_audit(qa_version) -> None:
    rows = load_findings(qa_version.findings_csv)
    state = merge_drafts_into_state(
        qa_version,
        [
            _draft(rows[0], result="FAIL"),
            _draft(rows[1], confidence=0.5),
        ],
    )
    ordered = prioritize_findings(rows, state, {"sec_0001": {"flagged_for_review": False}})
    assert [item["priority"] for item in ordered] == [1, 2]


@pytest.mark.parametrize(
    "value,expected",
    [("Crítica", "Critical"), ("Alta", "High"), ("Media", "Medium"), ("Baja", "Low")],
)
def test_spanish_severity_aliases(value: str, expected: str) -> None:
    assert normalize_severity(value) == expected


def test_confidence_formula_caps_only_coverage_or_structure() -> None:
    rows = [
        {"result": "FAIL", "severity": "Crítica"},
        *({"result": "PASS", "severity": ""} for _ in range(99)),
    ]
    precision_only = calculate_confidence(
        "m", "v1", rows, {"validation": {"precision": {"status": "FAIL"}}}
    )
    coverage = calculate_confidence(
        "m", "v1", rows, {"validation": {"coverage": {"status": "FAIL"}}}
    )
    assert precision_only.raw_index == 92
    assert precision_only.final_index == 92
    assert coverage.final_index == 60
    assert coverage.cap_applied


def test_incomplete_findings_are_pending() -> None:
    score = calculate_confidence("m", "v2", [{"result": "", "severity": ""}], None)
    assert score.status == "pending"
    assert score.final_index is None


def test_invalid_csv_header_is_rejected(qa_version) -> None:
    qa_version.findings_csv.write_text("wrong,columns\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly"):
        load_findings(qa_version.findings_csv)


def test_selecting_one_version_does_not_count_another(qa_version) -> None:
    source = qa_version.source_manifest["path"]
    v2 = create_qa_version(qa_version.qa_root, "manual", "v2", Path(source), "Reviewer")
    write_pipeline_artifacts(
        v2,
        tree=[],
        images={},
        bookmarks=[],
        validation_report={},
        run_log="",
    )
    write_findings_template(
        v2.findings_csv,
        [
            FindingRow(
                "manual",
                "sec_0001",
                "1",
                "5.4-page_start_end",
                "FAIL",
                "Low",
                "Mismatch",
                "",
            )
        ],
    )
    report = build_confidence_report(qa_version.qa_root, {"manual": "v2"})
    assert len(report.scores) == 1
    assert report.scores[0].version == "v2"
    assert report.scores[0].weighted_fails == 1
