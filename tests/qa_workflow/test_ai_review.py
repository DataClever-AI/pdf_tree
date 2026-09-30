from __future__ import annotations

import base64
import json
import urllib.error

from src.qa_workflow.ai_review import (
    detect_agent_batch,
    prepare_agent_batch,
    run_qwen_batch,
    validate_findings_result,
)
from src.qa_workflow.review import load_findings


def _valid_rows(template):
    return [
        {
            "section_id": row["section_id"],
            "page_sampled": int(row["page_sampled"]),
            "checklist_ref": row["checklist_ref"],
            "result": "PASS",
            "severity": "",
            "evidence": "The rendered page matches the declared section boundary.",
            "notes": "",
            "confidence": 0.95,
        }
        for row in template
    ]


def test_schema_rejects_invalid_and_duplicate_rows(qa_version) -> None:
    template = load_findings(qa_version.findings_csv)
    invalid = _valid_rows(template)
    invalid[0]["result"] = "FAIL"
    invalid[0]["severity"] = ""
    invalid.append(invalid[1])
    checked = validate_findings_result({"findings": invalid}, template, provider="test")
    assert not checked.is_valid
    assert any("FAIL requires" in error for error in checked.errors)
    assert any("duplicate" in error for error in checked.errors)


def test_batch_lists_the_images_of_its_sections(qa_version) -> None:
    tree = json.loads(qa_version.tree_path.read_text())
    section = next(row["section_id"] for row in load_findings(qa_version.findings_csv))
    page = next(s["page_start"] for s in tree if s["section_id"] == section)
    png = base64.b64encode(b"png-bytes").decode()
    qa_version.images_path.write_text(json.dumps({"images": [
        {"section_id": section, "page_no": 999, "width_px": 10, "height_px": 20, "image_b64": png},
        {"section_id": "sec_other", "page_no": page, "width_px": 30, "height_px": 40,
         "image_b64": png},
        {"section_id": "sec_other", "page_no": 998, "width_px": 1, "height_px": 1,
         "image_b64": png},
    ]}))
    batch = prepare_agent_batch(qa_version, "images", section_ids=[section])
    listed = json.loads((batch.input_dir / "images.json").read_text())["images"]
    assert [(image["image_id"], image["section_id"]) for image in listed] == [
        ("img_0000", section),
        ("img_0001", "sec_other"),
    ]
    assert (batch.input_dir / "images" / "img_0001.png").read_bytes() == b"png-bytes"


def test_shared_folder_progress_and_draft(qa_version) -> None:
    batch = prepare_agent_batch(qa_version, "batch-1")
    assert detect_agent_batch(batch).stage == "Waiting for agent"
    template = load_findings(batch.input_dir / "findings_template.csv")
    (batch.output_dir / "findings_result.json").write_text(
        json.dumps({"findings": _valid_rows(template)})
    )
    progress = detect_agent_batch(batch, provider="codex")
    assert progress.stage == "Draft ready"
    assert not qa_version.findings_csv.read_text().count("PASS")
    draft = batch.root / "validated_draft.json"
    before = draft.read_bytes()
    assert detect_agent_batch(batch).stage == "Draft ready"  # page 7 opens the batch again
    assert draft.read_bytes() == before
    assert json.loads(before)["provider"] == "codex"


def test_qwen_resume_skips_completed_sections(qa_version) -> None:
    batch = prepare_agent_batch(qa_version, "qwen")
    template = load_findings(batch.input_dir / "findings_template.csv")

    def transport(_url, _headers, _payload, _timeout):
        return {
            "choices": [{"message": {"content": json.dumps({"findings": _valid_rows(template)})}}]
        }

    first = run_qwen_batch(
        batch,
        endpoint_url="http://127.0.0.1:8000/v1/chat/completions",
        model="Qwen/Qwen3-VL",
        transport=transport,
    )
    second = run_qwen_batch(
        batch,
        endpoint_url="http://127.0.0.1:8000/v1/chat/completions",
        model="Qwen/Qwen3-VL",
        transport=lambda *_args: (_ for _ in ()).throw(AssertionError("must not rerun")),
    )
    assert first.completed_sections == ["sec_0001"]
    assert second.skipped_sections == ["sec_0001"]


def test_qwen_timeout_remains_pending_and_can_resume(qa_version) -> None:
    batch = prepare_agent_batch(qa_version, "qwen-timeout")
    template = load_findings(batch.input_dir / "findings_template.csv")
    failed = run_qwen_batch(
        batch,
        endpoint_url="http://127.0.0.1:8000/v1/chat/completions",
        model="Qwen/Qwen3-VL",
        max_retries=0,
        transport=lambda *_args: (_ for _ in ()).throw(urllib.error.URLError("timeout")),
    )
    assert "sec_0001" in failed.failed_sections

    def recovered(_url, _headers, _payload, _timeout):
        content = json.dumps({"findings": _valid_rows(template)})
        return {"choices": [{"message": {"content": content}}]}

    resumed = run_qwen_batch(
        batch,
        endpoint_url="http://127.0.0.1:8000/v1/chat/completions",
        model="Qwen/Qwen3-VL",
        transport=recovered,
    )
    assert resumed.completed_sections == ["sec_0001"]
