"""Provider-neutral AI draft exchange and Qwen3-VL endpoint adapter."""

from __future__ import annotations

import base64
import csv
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .findings import CHECKLIST, findings_csv_text, stable_finding_key
from .models import QA_COLUMNS, QAVersion
from .storage import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    utc_now,
    verify_source_pdf,
)

SEVERITIES = {"Critical", "High", "Medium", "Low"}


@dataclass(frozen=True)
class FindingDraft:
    manual_id: str
    section_id: str
    page_sampled: int | str
    checklist_ref: str
    result: str
    severity: str
    evidence: str
    notes: str
    confidence: float
    provider: str

    @property
    def stable_key(self) -> str:
        return stable_finding_key(asdict(self))


@dataclass(frozen=True)
class ValidationResult:
    valid: tuple[FindingDraft, ...]
    errors: tuple[str, ...]
    pending_keys: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors and not self.pending_keys


@dataclass(frozen=True)
class AgentBatch:
    batch_id: str
    root: Path
    input_dir: Path
    output_dir: Path
    section_ids: tuple[str, ...]


@dataclass(frozen=True)
class BatchProgress:
    stage: str
    completed_steps: int
    total_steps: int = 5
    validation: ValidationResult | None = None


@dataclass
class BatchRunResult:
    completed_sections: list[str] = field(default_factory=list)
    skipped_sections: list[str] = field(default_factory=list)
    failed_sections: dict[str, str] = field(default_factory=dict)
    drafts: list[FindingDraft] = field(default_factory=list)


def _read_findings(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != QA_COLUMNS:
            raise ValueError(f"Invalid findings columns in {path}")
        return list(reader)


def _response_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("findings"), list):
        return payload["findings"]
    raise ValueError("Response must be a JSON array or an object with a findings array")


def validate_findings_result(
    payload: Any,
    template_rows: list[dict[str, Any]],
    *,
    provider: str,
) -> ValidationResult:
    template = {stable_finding_key(row): row for row in template_rows}
    valid: list[FindingDraft] = []
    errors: list[str] = []
    seen: set[str] = set()
    try:
        rows = _response_rows(payload)
    except ValueError as exc:
        return ValidationResult((), (str(exc),), tuple(template))
    for index, raw in enumerate(rows):
        prefix = f"row {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix}: expected an object")
            continue
        merged = dict(raw)
        if "manual_id" not in merged and template_rows:
            merged["manual_id"] = template_rows[0].get("manual_id", "")
        key = stable_finding_key(merged)
        if key not in template:
            errors.append(f"{prefix}: row does not exist in the template ({key})")
            continue
        if key in seen:
            errors.append(f"{prefix}: duplicate row ({key})")
            continue
        seen.add(key)
        result = str(raw.get("result", "")).upper()
        severity = str(raw.get("severity", "")).strip().title()
        evidence = str(raw.get("evidence", "")).strip()
        notes = str(raw.get("notes", "")).strip()
        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError):
            confidence = -1
        row_errors = []
        if result not in {"PASS", "FAIL"}:
            row_errors.append("result must be PASS or FAIL")
        if result == "FAIL" and severity not in SEVERITIES:
            row_errors.append("FAIL requires Critical, High, Medium, or Low severity")
        if result == "PASS" and severity:
            row_errors.append("PASS severity must be empty")
        if not evidence:
            row_errors.append("evidence is required")
        if not 0 <= confidence <= 1:
            row_errors.append("confidence must be between 0 and 1")
        if row_errors:
            errors.append(f"{prefix}: " + "; ".join(row_errors))
            continue
        expected = template[key]
        valid.append(
            FindingDraft(
                str(expected["manual_id"]),
                str(expected["section_id"]),
                str(expected["page_sampled"]),
                str(expected["checklist_ref"]),
                result,
                severity,
                evidence,
                notes,
                confidence,
                provider,
            )
        )
    pending = tuple(key for key in template if key not in {draft.stable_key for draft in valid})
    return ValidationResult(tuple(valid), tuple(errors), pending)


def render_pdf_page(pdf_path: Path, page_no: int, zoom: float = 1.5) -> bytes:
    import pymupdf

    with pymupdf.open(str(pdf_path)) as document:
        if page_no < 1 or page_no > document.page_count:
            raise ValueError(f"Page {page_no} is outside 1-{document.page_count}")
        pixmap = document[page_no - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")


def _section_jobs(
    sections: list[dict[str, Any]], template: list[dict[str, str]], selected: set[str]
) -> list[dict[str, Any]]:
    def structural_context(section: dict[str, Any] | None) -> dict[str, Any] | None:
        if section is None:
            return None
        return {key: value for key, value in section.items() if key != "semantic_nodes"}

    by_id = {section["section_id"]: section for section in sections}
    ordered = [section for section in sections if section["section_id"] in selected]
    jobs = []
    for section in ordered:
        index = sections.index(section)
        questions = [
            {**row, "question": CHECKLIST.get(row["checklist_ref"], row["checklist_ref"])}
            for row in template
            if row["section_id"] == section["section_id"]
        ]
        jobs.append(
            {
                "section": section,
                "parent": structural_context(by_id.get(section.get("parent_section_id"))),
                "children": [
                    structural_context(by_id[child])
                    for child in section.get("child_sections", [])
                    if child in by_id
                ],
                "previous_section": structural_context(sections[index - 1]) if index > 0 else None,
                "next_section": structural_context(sections[index + 1])
                if index + 1 < len(sections)
                else None,
                "questions": questions,
            }
        )
    return jobs


def prepare_agent_batch(
    qa_version: QAVersion,
    batch_id: str,
    *,
    section_ids: list[str] | None = None,
) -> AgentBatch:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", batch_id):
        raise ValueError("Invalid batch_id")
    integrity = verify_source_pdf(qa_version)
    if not integrity.valid or integrity.source_path is None:
        raise ValueError(integrity.status)
    if not qa_version.tree_path.exists() or not qa_version.findings_csv.exists():
        raise FileNotFoundError("tree.json and findings_log.csv are required")
    root = qa_version.root / "agent_exchange" / batch_id
    if root.exists():
        raise FileExistsError(f"Agent batch already exists: {root}")
    input_dir, output_dir = root / "input", root / "output"
    pages_dir = input_dir / "pages"
    pages_dir.mkdir(parents=True)
    output_dir.mkdir()
    sections = json.loads(qa_version.tree_path.read_text(encoding="utf-8"))
    template = _read_findings(qa_version.findings_csv)
    available = {row["section_id"] for row in template if row["section_id"] != "DOCUMENT-LEVEL"}
    selected = set(section_ids or available)
    unknown = selected - available
    if unknown:
        raise ValueError(f"Unknown or unsampled section IDs: {sorted(unknown)}")
    selected_template = [row for row in template if row["section_id"] in selected]
    jobs = _section_jobs(sections, selected_template, selected)
    atomic_write_json(
        input_dir / "sections.json",
        {
            "schema_version": 1,
            "manual_id": qa_version.manual_id,
            "version": qa_version.version,
            "jobs": jobs,
        },
    )
    atomic_write_text(input_dir / "findings_template.csv", findings_csv_text(selected_template))
    instructions = """# AI review batch instructions

Read only files inside `input/`. Write exactly one file: `output/findings_result.json`.
Each job is one complete section; return every question in that job. Do not edit
`findings_template.csv` or any official QA artifact. The result must be a JSON object
with a `findings` array. Every row must contain section_id, page_sampled,
checklist_ref, result (PASS/FAIL), severity (required for FAIL, empty for PASS),
specific English evidence, notes, and confidence (0..1). Do not omit uncertain rows;
use a low confidence and explain the uncertainty.

`images.json` lists the extracted images of these sections and of the pages in `pages/`,
with the section each one is mapped to; the PNG files are in `images/`. Use it for the
image checks (`5.5-*`).
"""
    atomic_write_text(input_dir / "INSTRUCTIONS.md", instructions)
    rendered: set[int] = set()
    for job in jobs:
        section = job["section"]
        pages = {
            int(section["page_start"]),
            int(section.get("page_end") or section["page_start"]),
            *(
                int(question["page_sampled"])
                for question in job["questions"]
                if question["page_sampled"]
            ),
        }
        rendered |= pages
        for page in sorted(pages):
            target = pages_dir / f"{section['section_id']}_p{page}.png"
            atomic_write_bytes(target, render_pdf_page(integrity.source_path, page))
    _write_batch_images(qa_version, input_dir, selected, rendered)
    atomic_write_json(
        root / "batch_manifest.json",
        {
            "schema_version": 1,
            "batch_id": batch_id,
            "manual_id": qa_version.manual_id,
            "version": qa_version.version,
            "provider_mode": "shared-folder",
            "section_ids": sorted(selected),
            "prepared_at": utc_now(),
            "status": "Prepared",
        },
    )
    return AgentBatch(batch_id, root, input_dir, output_dir, tuple(sorted(selected)))


def _write_batch_images(
    qa_version: QAVersion, input_dir: Path, sections: set[str], pages: set[int]
) -> None:
    """Images mapped to the batch sections or printed on its rendered pages, with their PNGs."""
    records = []
    if qa_version.images_path.exists():
        images = json.loads(qa_version.images_path.read_text(encoding="utf-8"))
        for index, image in enumerate(images.get("images", [])):
            if image.get("section_id") not in sections and image.get("page_no") not in pages:
                continue
            image_id = f"img_{index:04d}"
            records.append(
                {
                    "image_id": image_id,
                    "section_id": image.get("section_id"),
                    "page_no": image.get("page_no"),
                    "width_px": image.get("width_px"),
                    "height_px": image.get("height_px"),
                    "file": f"images/{image_id}.png",
                }
            )
            atomic_write_bytes(
                input_dir / "images" / f"{image_id}.png",
                base64.b64decode(image.get("image_b64", "")),
            )
    atomic_write_json(input_dir / "images.json", {"schema_version": 1, "images": records})


def detect_agent_batch(batch: AgentBatch, *, provider: str = "external-agent") -> BatchProgress:
    output = batch.output_dir / "findings_result.json"
    if not output.exists():
        return BatchProgress("Waiting for agent", 1)
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return BatchProgress("Output detected", 2, validation=ValidationResult((), (str(exc),), ()))
    template = _read_findings(batch.input_dir / "findings_template.csv")
    validation = validate_findings_result(payload, template, provider=provider)
    if not validation.is_valid:
        return BatchProgress("Output detected", 2, validation=validation)
    draft_path = batch.root / "validated_draft.json"
    if draft_path.exists():
        # Opening the batch again must not rewrite the draft: keep its provider and time.
        existing = json.loads(draft_path.read_text(encoding="utf-8"))
        findings = [
            {key: value for key, value in finding.items() if key != "provider"}
            for finding in existing.get("findings", [])
        ]
        new = [
            {key: value for key, value in asdict(draft).items() if key != "provider"}
            for draft in validation.valid
        ]
        if findings == new:
            return BatchProgress("Draft ready", 5, validation=validation)
    atomic_write_json(
        draft_path,
        {
            "schema_version": 1,
            "provider": provider,
            "validated_at": utc_now(),
            "findings": [asdict(draft) for draft in validation.valid],
        },
    )
    return BatchProgress("Draft ready", 5, validation=validation)


def _extract_json_text(content: str) -> Any:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return json.loads(stripped)


def _default_transport(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _qwen_content(job: dict[str, Any], page_paths: list[Path]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for path in page_paths:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
        )
    content.append(
        {
            "type": "text",
            "text": (
                "Review this complete section and return only JSON with a findings array. "
                "Evaluate every supplied question. Context:\n" + json.dumps(job, ensure_ascii=False)
            ),
        }
    )
    return content


def run_qwen_batch(
    batch: AgentBatch,
    *,
    endpoint_url: str,
    model: str,
    token: str = "",
    timeout: float = 120.0,
    max_retries: int = 1,
    transport: Callable[[str, dict[str, str], dict[str, Any], float], Any] | None = None,
) -> BatchRunResult:
    """Run pending sections and checkpoint after each response for safe resume."""
    if not endpoint_url.rstrip("/").endswith("/v1/chat/completions"):
        raise ValueError("endpoint_url must end with /v1/chat/completions")
    if urlparse(endpoint_url).scheme not in {"http", "https"}:
        raise ValueError("endpoint_url must use http or https")
    data = json.loads((batch.input_dir / "sections.json").read_text(encoding="utf-8"))
    template = _read_findings(batch.input_dir / "findings_template.csv")
    state_path = batch.root / "qwen_state.json"
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else {
            "schema_version": 1,
            "provider": "qwen3-vl",
            "completed_section_ids": [],
            "findings": [],
            "errors": [],
        }
    )
    completed = set(state["completed_section_ids"])
    result = BatchRunResult()
    sender = transport or _default_transport
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for job in data["jobs"]:
        section_id = job["section"]["section_id"]
        if section_id in completed:
            result.skipped_sections.append(section_id)
            continue
        section_template = [row for row in template if row["section_id"] == section_id]
        pages = sorted((batch.input_dir / "pages").glob(f"{section_id}_p*.png"))
        request_payload = {
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": _qwen_content(job, pages)}],
        }
        error = ""
        validation = None
        for _attempt in range(max_retries + 1):
            try:
                response = sender(endpoint_url, headers, request_payload, timeout)
                content = response["choices"][0]["message"]["content"]
                validation = validate_findings_result(
                    _extract_json_text(content), section_template, provider="qwen3-vl"
                )
                if validation.is_valid:
                    break
                error = "; ".join(validation.errors) or "response omitted template rows"
            except (KeyError, IndexError, TypeError, ValueError, urllib.error.URLError) as exc:
                error = str(exc)
        if validation is None or not validation.is_valid:
            result.failed_sections[section_id] = error
            state["errors"].append({"section_id": section_id, "error": error, "at": utc_now()})
        else:
            drafts = list(validation.valid)
            result.completed_sections.append(section_id)
            result.drafts.extend(drafts)
            completed.add(section_id)
            state["completed_section_ids"] = sorted(completed)
            state["findings"].extend(asdict(draft) for draft in drafts)
        atomic_write_json(state_path, state)
        log_path = batch.root.parent.parent / "logs" / "ai_review.jsonl"
        line = json.dumps(
            {
                "at": utc_now(),
                "batch_id": batch.batch_id,
                "section_id": section_id,
                "status": "completed" if section_id in completed else "error",
                "error": result.failed_sections.get(section_id, ""),
            }
        )
        previous = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        atomic_write_text(log_path, previous + line + "\n")
    return result
