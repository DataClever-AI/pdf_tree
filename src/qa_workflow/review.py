"""Single-reviewer decision persistence and prioritization."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .ai_review import SEVERITIES, FindingDraft
from .findings import findings_csv_text, stable_finding_key
from .models import QA_COLUMNS, QAVersion
from .storage import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    mark_version_edited,
    set_version_status,
    utc_now,
)


def load_findings(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != QA_COLUMNS:
            raise ValueError(f"findings_log.csv must preserve exactly these columns: {QA_COLUMNS}")
        return list(reader)


def load_review_state(qa_version: QAVersion) -> dict[str, Any]:
    if qa_version.review_state_path.exists():
        state = json.loads(qa_version.review_state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("decisions", {}), dict):
            raise ValueError("Invalid review_state.json")
        return state
    return {
        "schema_version": 1,
        "manual_id": qa_version.manual_id,
        "version": qa_version.version,
        "reviewer": qa_version.version_manifest.get("reviewer", ""),
        "updated_at": utc_now(),
        "decisions": {},
    }


def discover_ai_drafts(qa_version: QAVersion) -> list[FindingDraft]:
    drafts: dict[str, FindingDraft] = {}
    exchange = qa_version.root / "agent_exchange"
    for path in sorted(exchange.glob("*/validated_draft.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload.get("findings", []):
            draft = FindingDraft(**raw)
            drafts[draft.stable_key] = draft
    for path in sorted(exchange.glob("*/qwen_state.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload.get("findings", []):
            draft = FindingDraft(**raw)
            drafts[draft.stable_key] = draft
    return list(drafts.values())


def merge_drafts_into_state(
    qa_version: QAVersion, drafts: list[FindingDraft] | None = None
) -> dict[str, Any]:
    state = load_review_state(qa_version)
    changed = False
    for draft in drafts if drafts is not None else discover_ai_drafts(qa_version):
        if draft.stable_key in state["decisions"]:
            continue
        state["decisions"][draft.stable_key] = {
            "original_proposal": asdict(draft),
            "confidence": draft.confidence,
            "provider": draft.provider,
            "approved": False,
            "reviewer": "",
            "current": None,
            "history": [],
        }
        changed = True
    if changed:
        state["updated_at"] = utc_now()
        atomic_write_json(qa_version.review_state_path, state)
    return state


def _validate_decision(result: str, severity: str, evidence: str) -> tuple[str, str]:
    result = result.upper().strip()
    severity = severity.title().strip()
    if result not in {"PASS", "FAIL"}:
        raise ValueError("result must be PASS or FAIL")
    if result == "FAIL" and severity not in SEVERITIES:
        raise ValueError("FAIL requires a valid severity")
    if result == "PASS" and severity:
        raise ValueError("PASS severity must be empty")
    if not evidence.strip():
        raise ValueError("evidence is required")
    return result, severity


def _persist_pair(
    qa_version: QAVersion,
    rows: list[dict[str, str]],
    state: dict[str, Any],
    *,
    backup: bool,
) -> None:
    csv_path, state_path = qa_version.findings_csv, qa_version.review_state_path
    csv_before = csv_path.read_bytes() if csv_path.exists() else None
    state_before = state_path.read_bytes() if state_path.exists() else None
    if backup:
        backup_dir = qa_version.root / "findings" / "backups" / utc_now().replace(":", "-")
        backup_dir.mkdir(parents=True)
        if csv_path.exists():
            shutil.copy2(csv_path, backup_dir / csv_path.name)
        if state_path.exists():
            shutil.copy2(state_path, backup_dir / state_path.name)
    try:
        atomic_write_text(csv_path, findings_csv_text(rows))
        atomic_write_json(state_path, state)
    except Exception:
        if csv_before is None:
            csv_path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(csv_path, csv_before)
        if state_before is None:
            state_path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(state_path, state_before)
        raise


def save_review_decision(
    qa_version: QAVersion,
    stable_key: str,
    *,
    result: str,
    severity: str,
    evidence: str,
    notes: str,
    reviewer: str,
    approved: bool = True,
) -> QAVersion:
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    result, severity = _validate_decision(result, severity, evidence)
    rows = load_findings(qa_version.findings_csv)
    row = next(
        (candidate for candidate in rows if stable_finding_key(candidate) == stable_key), None
    )
    if row is None:
        raise KeyError(f"Finding not found: {stable_key}")
    state = merge_drafts_into_state(qa_version)
    decision = state["decisions"].setdefault(
        stable_key,
        {
            "original_proposal": None,
            "confidence": None,
            "provider": "human",
            "approved": False,
            "reviewer": "",
            "current": None,
            "history": [],
        },
    )
    previous = {field: row.get(field, "") for field in ("result", "severity", "evidence", "notes")}
    if any(previous.values()):
        decision["history"].append({"at": utc_now(), "reviewer": reviewer, **previous})
    row.update(result=result, severity=severity, evidence=evidence.strip(), notes=notes.strip())
    decision.update(
        {
            "approved": approved,
            "reviewer": reviewer.strip(),
            "reviewed_at": utc_now(),
            "current": {field: row[field] for field in ("result", "severity", "evidence", "notes")},
        }
    )
    state["reviewer"] = reviewer.strip()
    state["updated_at"] = utc_now()
    _persist_pair(qa_version, rows, state, backup=False)
    return (
        mark_version_edited(qa_version)
        if qa_version.version_manifest.get("status") == "finalized"
        else qa_version
    )


def restore_original_proposal(
    qa_version: QAVersion, stable_key: str, *, reviewer: str
) -> QAVersion:
    state = merge_drafts_into_state(qa_version)
    proposal = state["decisions"].get(stable_key, {}).get("original_proposal")
    if not proposal:
        raise ValueError("No original AI proposal is available")
    return save_review_decision(
        qa_version,
        stable_key,
        result=proposal["result"],
        severity=proposal["severity"],
        evidence=proposal["evidence"],
        notes=proposal.get("notes", ""),
        reviewer=reviewer,
        approved=False,
    )


def prioritize_findings(
    rows: list[dict[str, str]],
    state: dict[str, Any],
    sections_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []
    pass_candidates = []
    for row in rows:
        key = stable_finding_key(row)
        decision = state.get("decisions", {}).get(key, {})
        proposal = decision.get("original_proposal") or {}
        result = row.get("result") or proposal.get("result", "")
        confidence = decision.get("confidence")
        flagged = bool(sections_by_id.get(row["section_id"], {}).get("flagged_for_review"))
        if result == "FAIL":
            priority, reason = 1, "FAIL"
        elif confidence is not None and confidence < 0.80:
            priority, reason = 2, "Low confidence"
        elif flagged:
            priority, reason = 3, "Section flagged for review"
        else:
            priority, reason = 5, "Standard review"
            if result == "PASS":
                pass_candidates.append(key)
        enriched.append({**row, "stable_key": key, "priority": priority, "priority_reason": reason})

    sample_count = min(len(pass_candidates), max(3, math.ceil(len(pass_candidates) * 0.05)))
    deterministic = set(
        sorted(
            pass_candidates,
            key=lambda key: hashlib.sha256(key.encode("utf-8")).hexdigest(),
        )[:sample_count]
    )
    for item in enriched:
        if item["priority"] == 5 and item["stable_key"] in deterministic:
            item["priority"] = 4
            item["priority_reason"] = "Deterministic 5% PASS audit"
    return sorted(enriched, key=lambda item: (item["priority"], item["stable_key"]))


def unreviewed_without_draft(
    items: list[dict[str, Any]], state: dict[str, Any]
) -> list[dict[str, Any]]:
    """Rows with no result and no AI proposal (e.g. ``DOCUMENT-LEVEL``).

    No bulk action counts them, so the reviewer must open them one by one.
    """
    decisions = state.get("decisions", {})
    return [
        item
        for item in items
        if not item.get("result")
        and not (decisions.get(item["stable_key"], {}).get("original_proposal"))
    ]


def bulk_eligible(
    item: dict[str, Any], state: dict[str, Any], sections_by_id: dict[str, dict[str, Any]]
) -> bool:
    decision = state.get("decisions", {}).get(item["stable_key"], {})
    proposal = decision.get("original_proposal") or {}
    return (
        proposal.get("result") == "PASS"
        and proposal.get("severity", "") == ""
        and bool(proposal.get("evidence", "").strip())
        and float(decision.get("confidence") or 0) >= 0.90
        and not sections_by_id.get(item["section_id"], {}).get("flagged_for_review", False)
        and item.get("priority") == 5
        and not decision.get("approved", False)
    )


def _approved_values(decision: dict[str, Any]) -> dict[str, str] | None:
    """Values to approve: a human edit still pending approval wins over the AI proposal."""
    fields = ("result", "severity", "evidence", "notes")
    source = decision.get("current") or decision.get("original_proposal")
    if not source:
        return None
    values = {field: str(source.get(field, "") or "") for field in fields}
    try:
        values["result"], values["severity"] = _validate_decision(
            values["result"], values["severity"], values["evidence"]
        )
    except ValueError:
        return None
    return values


def pending_approvals(
    state: dict[str, Any], keys: list[str] | None = None
) -> dict[str, list[str]]:
    """Pending AI-backed decisions by the result that would be approved (PASS/FAIL/invalid)."""
    groups: dict[str, list[str]] = {"PASS": [], "FAIL": [], "invalid": []}
    decisions = state.get("decisions", {})
    for key in keys if keys is not None else list(decisions):
        decision = decisions.get(key)
        if not decision or decision.get("approved"):
            continue
        values = _approved_values(decision)
        groups[values["result"] if values else "invalid"].append(key)
    return groups


def _approve_keys(
    qa_version: QAVersion, keys: set[str], *, reviewer: str, mode: str
) -> int:
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    rows = load_findings(qa_version.findings_csv)
    state = merge_drafts_into_state(qa_version)
    count = 0
    for row in rows:
        key = stable_finding_key(row)
        decision = state["decisions"].get(key)
        if key not in keys or decision is None or decision.get("approved"):
            continue
        values = _approved_values(decision)
        if values is None:
            continue
        row.update(values)
        decision.update(
            {
                "approved": True,
                "reviewer": reviewer.strip(),
                "reviewed_at": utc_now(),
                "current": dict(values),
                "approval_mode": mode,
            }
        )
        count += 1
    if count:
        state["reviewer"] = reviewer.strip()
        state["updated_at"] = utc_now()
        _persist_pair(qa_version, rows, state, backup=True)
        if qa_version.version_manifest.get("status") == "finalized":
            mark_version_edited(qa_version)
    return count


def bulk_approve_eligible(qa_version: QAVersion, *, reviewer: str) -> int:
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    rows = load_findings(qa_version.findings_csv)
    sections = json.loads(qa_version.tree_path.read_text(encoding="utf-8"))
    sections_by_id = {section["section_id"]: section for section in sections}
    state = merge_drafts_into_state(qa_version)
    eligible = {
        item["stable_key"]
        for item in prioritize_findings(rows, state, sections_by_id)
        if bulk_eligible(item, state, sections_by_id)
    }
    return _approve_keys(qa_version, eligible, reviewer=reviewer, mode="bulk")


def bulk_approve_all(
    qa_version: QAVersion, *, reviewer: str, keys: list[str] | None = None
) -> int:
    """Approve every pending AI-backed row (PASS and FAIL) in ``keys``, or in the whole version.

    Recorded as ``approval_mode: bulk-all`` so reports can tell these rows were not
    reviewed one by one. A backup of the findings and state is written first.
    """
    state = merge_drafts_into_state(qa_version)
    groups = pending_approvals(state, keys)
    return _approve_keys(
        qa_version, set(groups["PASS"] + groups["FAIL"]), reviewer=reviewer, mode="bulk-all"
    )


def finalize_review(qa_version: QAVersion) -> QAVersion:
    rows = load_findings(qa_version.findings_csv)
    state = load_review_state(qa_version)
    for row in rows:
        _validate_decision(row["result"], row["severity"], row["evidence"])
        decision = state.get("decisions", {}).get(stable_finding_key(row))
        if decision and not decision.get("approved"):
            raise ValueError("Every AI-backed finding must be approved before finalization")
    return set_version_status(qa_version, "finalized")
