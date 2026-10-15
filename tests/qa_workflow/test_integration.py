from __future__ import annotations

import json

from src.qa_workflow.ai_review import detect_agent_batch, prepare_agent_batch
from src.qa_workflow.confidence import build_confidence_report, write_confidence_outputs
from src.qa_workflow.findings import stable_finding_key
from src.qa_workflow.review import (
    finalize_review,
    load_findings,
    merge_drafts_into_state,
    save_review_decision,
)


def test_artifacts_agent_human_report_flow(qa_version) -> None:
    batch = prepare_agent_batch(qa_version, "integration")
    template = load_findings(batch.input_dir / "findings_template.csv")
    proposed = [
        {
            "section_id": row["section_id"],
            "page_sampled": int(row["page_sampled"]),
            "checklist_ref": row["checklist_ref"],
            "result": "PASS",
            "severity": "",
            "evidence": "The rendered PDF page agrees with the extracted structure.",
            "notes": "",
            "confidence": 0.91,
        }
        for row in template
    ]
    (batch.output_dir / "findings_result.json").write_text(
        json.dumps({"findings": proposed}), encoding="utf-8"
    )
    progress = detect_agent_batch(batch, provider="codex")
    assert progress.validation and progress.validation.is_valid
    state = merge_drafts_into_state(qa_version)
    assert len(state["decisions"]) == len(template)
    for row in load_findings(qa_version.findings_csv):
        proposal = state["decisions"][stable_finding_key(row)]["original_proposal"]
        save_review_decision(
            qa_version,
            stable_finding_key(row),
            result=proposal["result"],
            severity=proposal["severity"],
            evidence=proposal["evidence"],
            notes=proposal["notes"],
            reviewer="Reviewer",
        )
    final = finalize_review(qa_version)
    assert final.version_manifest["status"] == "finalized"
    report = build_confidence_report(qa_version.qa_root, {qa_version.manual_id: "v1"})
    assert report.scores[0].final_index == 100
    manifest = write_confidence_outputs(qa_version.qa_root, report)
    assert manifest.path.exists()
    assert manifest.input_hashes[qa_version.manual_id]["findings_sha256"]
