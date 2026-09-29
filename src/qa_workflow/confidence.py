"""Version-aware Confidence Index calculation and report generation."""

from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .review import load_findings
from .root_causes import (
    CATALOGUE_FILENAME,
    EMPTY_CATALOGUE,
    RootCauseCatalogue,
    consolidate,
    load_catalogue,
)
from .storage import (
    atomic_write_json,
    atomic_write_text,
    is_version_name,
    open_qa_version,
    sha256_file,
    utc_now,
    version_label,
    version_sort_key,
)

SEVERITY_WEIGHTS = {"Critical": 8, "High": 4, "Medium": 2, "Low": 1}
BUG_COLUMNS = (
    "bug_id",
    "title",
    "severity",
    "manuals_affected",
    "sections_affected",
    "suspected_module",
    "escalate",
)


def normalize_severity(value: str) -> str:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.strip().lower())
        if not unicodedata.combining(character)
    )
    aliases = {
        "critical": "Critical",
        "critica": "Critical",
        "critico": "Critical",
        "high": "High",
        "alta": "High",
        "alto": "High",
        "medium": "Medium",
        "media": "Medium",
        "medio": "Medium",
        "low": "Low",
        "baja": "Low",
        "bajo": "Low",
    }
    return aliases.get(normalized, value.strip().title())


@dataclass(frozen=True)
class ConfidenceScore:
    manual_id: str
    version: str
    total_items: int
    unevaluated_items: int
    fail_counts: dict[str, int]
    weighted_fails: int
    raw_index: float | None
    cap_applied: bool
    cap_reason: str
    final_index: float | None
    status: str


@dataclass(frozen=True)
class ConfidenceReport:
    selected_versions: dict[str, str]
    scores: tuple[ConfidenceScore, ...]
    bugs: tuple[dict[str, str], ...]
    markdown: str
    bugs_csv: str


@dataclass(frozen=True)
class ReportManifest:
    path: Path
    selected_versions: dict[str, str]
    input_hashes: dict[str, dict[str, str | None]]


def _validation_checks(payload: dict[str, Any]) -> dict[str, Any]:
    validation = payload.get("validation")
    return validation if isinstance(validation, dict) else payload


def calculate_confidence(
    manual_id: str,
    version: str,
    findings: list[dict[str, str]],
    validation_report: dict[str, Any] | None,
) -> ConfidenceScore:
    evaluated = [row for row in findings if row.get("result", "").upper() in {"PASS", "FAIL"}]
    unevaluated = len(findings) - len(evaluated)
    counts = {severity: 0 for severity in SEVERITY_WEIGHTS}
    for row in evaluated:
        if row.get("result", "").upper() != "FAIL":
            continue
        severity = normalize_severity(row.get("severity", ""))
        if severity in counts:
            counts[severity] += 1
    weighted = sum(counts[severity] * weight for severity, weight in SEVERITY_WEIGHTS.items())
    if not evaluated:
        return ConfidenceScore(
            manual_id, version, 0, len(findings), counts, weighted, None, False, "", None, "pending"
        )
    raw = max(0.0, min(100.0, 100 * (1 - weighted / len(evaluated))))
    checks = _validation_checks(validation_report or {})
    failed_caps = [
        name.title()
        for name in ("coverage", "structure")
        if str((checks.get(name) or {}).get("status", "")).upper() == "FAIL"
    ]
    cap_applied = bool(failed_caps and raw > 60)
    final = min(raw, 60.0) if failed_caps else raw
    status = "pending" if unevaluated else "complete"
    return ConfidenceScore(
        manual_id,
        version,
        len(evaluated),
        unevaluated,
        counts,
        weighted,
        raw,
        cap_applied,
        ", ".join(failed_caps),
        final,
        status,
    )


def list_manual_versions(qa_root: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not qa_root.is_dir():
        return result
    for manual_root in sorted(qa_root.iterdir()):
        if (
            not manual_root.is_dir()
            or manual_root.name.startswith((".", "_"))
            or manual_root.name in {"bugs", "confidence_index"}
        ):
            continue
        versions = [
            path.name
            for path in manual_root.iterdir()
            if path.is_dir() and is_version_name(path.name)
        ]
        if versions:
            result[manual_root.name] = sorted(versions, key=version_sort_key)
    return result


def read_version_manifest(qa_root: Path, manual_id: str, version: str) -> dict[str, Any]:
    path = qa_root / manual_id / version / "version_manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def version_display_name(qa_root: Path, manual_id: str, version: str) -> str:
    """Selector label, e.g. ``v2.1 · BUG-019`` for a mitigation version."""
    return version_label(version, read_version_manifest(qa_root, manual_id, version))


def latest_versions(qa_root: Path) -> dict[str, str]:
    """Latest reference version per manual.

    A mitigation version (e.g. ``v2.1``) becomes the reference only once it is finalized;
    before that it is compared against its base on the Version Compare page.
    """
    latest = {}
    for manual, versions in list_manual_versions(qa_root).items():
        eligible = [
            version
            for version in versions
            if "mitigation" not in (manifest := read_version_manifest(qa_root, manual, version))
            or manifest.get("status") == "finalized"
        ]
        latest[manual] = (eligible or versions)[-1]
    return latest


def consolidate_failures(
    selected_rows: dict[str, list[dict[str, str]]],
    catalogue: RootCauseCatalogue = EMPTY_CATALOGUE,
) -> list[dict[str, str]]:
    """Task 2.3 list: one entry per curated root cause; unclassified rows go to TRIAGE."""
    fails = {
        manual_id: [row for row in rows if row.get("result", "").upper() == "FAIL"]
        for manual_id, rows in selected_rows.items()
    }
    return list(consolidate(catalogue, fails, normalize_severity).bugs)


def _bugs_csv(rows: list[dict[str, str]]) -> str:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=BUG_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _report_markdown(scores: list[ConfidenceScore], selected: dict[str, str]) -> str:
    lines = [
        "# PDF Tree Confidence Index",
        "",
        "`raw = 100 x (1 - weighted_fails / evaluated_items)`; "
        "Coverage or Structure FAIL caps the result at 60.",
        "",
        "| Manual | Version | Evaluated | Weighted fails | Raw | Adjustment | Final | Status |",
        "|---|---|---:|---:|---:|---|---:|---|",
    ]
    for score in scores:
        raw = "—" if score.raw_index is None else f"{score.raw_index:.2f}"
        final = "—" if score.final_index is None else f"{score.final_index:.0f}"
        adjustment = f"Capped at 60 ({score.cap_reason})" if score.cap_applied else "None"
        lines.append(
            f"| `{score.manual_id}` | `{selected[score.manual_id]}` | {score.total_items} "
            f"| {score.weighted_fails} | {raw} | {adjustment} | {final} | {score.status} |"
        )
    return "\n".join(lines) + "\n"


def build_confidence_report(qa_root: Path, selected_versions: dict[str, str]) -> ConfidenceReport:
    selected = dict(sorted(selected_versions.items()))
    scores = []
    selected_rows = {}
    for manual_id, version in selected.items():
        qa_version = open_qa_version(qa_root, manual_id, version)
        rows = load_findings(qa_version.findings_csv) if qa_version.findings_csv.exists() else []
        validation = (
            json.loads(qa_version.validation_path.read_text(encoding="utf-8"))
            if qa_version.validation_path.exists()
            else None
        )
        scores.append(calculate_confidence(manual_id, version, rows, validation))
        selected_rows[manual_id] = rows
    catalogue = load_catalogue(qa_root.resolve() / "confidence_index" / CATALOGUE_FILENAME)
    bugs = consolidate_failures(selected_rows, catalogue)
    return ConfidenceReport(
        selected,
        tuple(scores),
        tuple(bugs),
        _report_markdown(scores, selected),
        _bugs_csv(bugs),
    )


def write_confidence_outputs(qa_root: Path, report: ConfidenceReport) -> ReportManifest:
    output_dir = qa_root.resolve() / "confidence_index"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "confidence_index_report.md"
    bugs_path = output_dir / "consolidated_bugs.csv"
    atomic_write_text(report_path, report.markdown)
    atomic_write_text(bugs_path, report.bugs_csv)
    hashes: dict[str, dict[str, str | None]] = {}
    for manual_id, version in report.selected_versions.items():
        qa_version = open_qa_version(qa_root, manual_id, version)
        hashes[manual_id] = {
            "version": version,
            "findings_sha256": sha256_file(qa_version.findings_csv)
            if qa_version.findings_csv.exists()
            else None,
            "validation_sha256": sha256_file(qa_version.validation_path)
            if qa_version.validation_path.exists()
            else None,
        }
    manifest_path = output_dir / "report_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": 1,
            "generated_at": utc_now(),
            "selected_versions": report.selected_versions,
            "input_hashes": hashes,
            "outputs": {
                "confidence_index_report.md": hashlib.sha256(report.markdown.encode()).hexdigest(),
                "consolidated_bugs.csv": hashlib.sha256(report.bugs_csv.encode()).hexdigest(),
            },
        },
    )
    return ReportManifest(manifest_path, report.selected_versions, hashes)
