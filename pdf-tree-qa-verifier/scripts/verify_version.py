#!/usr/bin/env python3
"""Read-only integrity and contract audit for one PDF Tree QA version."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.qa_workflow.findings import generate_findings_template  # noqa: E402
from src.qa_workflow.models import QA_COLUMNS  # noqa: E402
from src.qa_workflow.sampling import generate_sample  # noqa: E402

REQUIRED_VERSION_FILES = (
    "version_manifest.json",
    "artifact_manifest.json",
    "exports/tree.json",
    "exports/images_v1.json",
    "exports/bookmarks.json",
    "validation_report.json",
    "logs/run.log",
    "sampling/sample_selection.md",
    "findings/findings_log.csv",
    "summary.md",
)
SEVERITIES = {"Critical", "High", "Medium", "Low"}
LEGACY_SEVERITIES = {
    "Crítica": "Critical",
    "Critica": "Critical",
    "Alta": "High",
    "Media": "Medium",
    "Baja": "Low",
}


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    message: str


class Audit:
    def __init__(self) -> None:
        self.issues: list[Issue] = []

    def error(self, code: str, message: str) -> None:
        self.issues.append(Issue("ERROR", code, message))

    def warning(self, code: str, message: str) -> None:
        self.issues.append(Issue("WARNING", code, message))

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "ERROR"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "WARNING"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, audit: Audit, code: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        audit.error(code, f"cannot read valid JSON from {path}: {exc}")
        return None


def check_required_files(version_root: Path, audit: Audit) -> None:
    for relative in REQUIRED_VERSION_FILES:
        if not (version_root / relative).is_file():
            audit.error("required-file", f"missing {relative}")


def check_source(
    source_manifest: dict[str, Any] | None,
    version_manifest: dict[str, Any] | None,
    manual_id: str,
    version: str,
    audit: Audit,
) -> None:
    if not isinstance(source_manifest, dict) or not isinstance(version_manifest, dict):
        return
    if source_manifest.get("manual_id") != manual_id:
        audit.error("manifest-identity", "source manifest manual_id does not match directory")
    if version_manifest.get("manual_id") != manual_id or version_manifest.get("version") != version:
        audit.error("manifest-identity", "version manifest identity does not match directory")
    expected = str(source_manifest.get("sha256", ""))
    if expected != str(version_manifest.get("source_sha256", "")):
        audit.error("source-hash", "source and version manifests record different PDF hashes")
    source = Path(str(source_manifest.get("path", ""))).expanduser()
    if source_manifest.get("missing") or not source.is_file():
        audit.error(
            "source-missing",
            f"visual and AI review blocked; source PDF is absent: {source}",
        )
        return
    actual = sha256(source)
    if actual != expected:
        audit.error(
            "source-changed",
            f"visual and AI review blocked; PDF SHA-256 is {actual}, expected {expected}",
        )
    recorded_size = source_manifest.get("size_bytes")
    if isinstance(recorded_size, int) and source.stat().st_size != recorded_size:
        audit.error("source-size", "source PDF size differs from source_manifest.json")


def check_artifacts(version_root: Path, manifest: dict[str, Any] | None, audit: Audit) -> None:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("artifacts"), list):
        audit.error("artifact-manifest", "artifact_manifest.json has no artifacts array")
        return
    seen: set[str] = set()
    for item in manifest["artifacts"]:
        if not isinstance(item, dict):
            audit.error("artifact-manifest", "artifact entry is not an object")
            continue
        relative = str(item.get("relative_path", ""))
        if not relative or relative in seen:
            audit.error("artifact-manifest", f"empty or duplicate artifact path: {relative!r}")
            continue
        seen.add(relative)
        path = (version_root / relative).resolve()
        try:
            path.relative_to(version_root.resolve())
        except ValueError:
            audit.error("artifact-path", f"artifact escapes version directory: {relative}")
            continue
        if not path.is_file():
            audit.error("artifact-missing", f"manifest artifact is missing: {relative}")
            continue
        if path.stat().st_size != item.get("size_bytes"):
            audit.error("artifact-size", f"size mismatch for {relative}")
        if sha256(path) != item.get("sha256"):
            audit.error("artifact-hash", f"SHA-256 mismatch for {relative}")


def check_tree(tree: Any, audit: Audit) -> None:
    if not isinstance(tree, list) or not tree:
        audit.error("tree-shape", "tree.json must be a non-empty array")
        return
    by_id: dict[str, dict[str, Any]] = {}
    node_owner: dict[str, str] = {}
    for index, section in enumerate(tree):
        if not isinstance(section, dict):
            audit.error("tree-shape", f"tree row {index} is not an object")
            continue
        section_id = str(section.get("section_id", ""))
        if not section_id or section_id in by_id:
            audit.error("section-id", f"empty or duplicate section_id at tree row {index}")
            continue
        by_id[section_id] = section
        start, end = section.get("page_start"), section.get("page_end")
        if not isinstance(start, int) or not isinstance(end, int) or start > end:
            audit.error("section-range", f"invalid page range for {section_id}: {start}-{end}")
        for node in section.get("semantic_nodes", []):
            if not isinstance(node, dict):
                audit.error("node-shape", f"non-object semantic node in {section_id}")
                continue
            node_id = str(node.get("node_id", ""))
            if node_id and node_id in node_owner:
                audit.error(
                    "duplicate-node",
                    f"{node_id} belongs to both {node_owner[node_id]} and {section_id}",
                )
            elif node_id:
                node_owner[node_id] = section_id

    for section_id, section in by_id.items():
        parent_id = section.get("parent_section_id")
        if parent_id:
            parent = by_id.get(str(parent_id))
            if parent is None:
                audit.error("missing-parent", f"{section_id} references missing parent {parent_id}")
            elif section_id not in parent.get("child_sections", []):
                audit.error("parent-child", f"{parent_id} does not list child {section_id}")
        for child_id in section.get("child_sections", []):
            child = by_id.get(str(child_id))
            if child is None:
                audit.error("missing-child", f"{section_id} references missing child {child_id}")
            elif child.get("parent_section_id") != section_id:
                audit.error(
                    "parent-child",
                    f"{child_id} does not point back to parent {section_id}",
                )


def parse_sample_rows(markdown: str) -> dict[tuple[int, str], set[str]]:
    rows: dict[tuple[int, str], set[str]] = {}
    pattern = re.compile(r"^\|\s*(\d+)\s*\|.*?\(`([^`]+)`\).*?\|\s*([^|]+?)\s*\|$")
    for line in markdown.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        page = int(match.group(1))
        section_id = match.group(2)
        reasons = {item.strip() for item in match.group(3).split(";") if item.strip()}
        rows[(page, section_id)] = reasons
    return rows


def check_sample(
    version_root: Path,
    manual_id: str,
    tree: Any,
    validation: Any,
    audit: Audit,
) -> Any | None:
    if not isinstance(tree, list) or not isinstance(validation, dict):
        return None
    total_pages = validation.get("summary", {}).get("total_pages")
    if not isinstance(total_pages, int) or total_pages <= 0:
        audit.error("sample-pages", "validation report lacks a positive summary.total_pages")
        return None
    try:
        expected = generate_sample(tree, total_pages)
    except ValueError as exc:
        audit.error("sample-generation", str(exc))
        return None
    sample_path = version_root / "sampling" / "sample_selection.md"
    try:
        actual_rows = parse_sample_rows(sample_path.read_text(encoding="utf-8"))
    except OSError as exc:
        audit.error("sample-file", str(exc))
        return expected

    expected_rows = {(row.page, row.section_id): set(row.reasons) for row in expected.rows}
    for row_key in sorted(expected_rows.keys() - actual_rows.keys()):
        audit.error(
            "sample-missing",
            f"deterministic sample row is missing: page {row_key[0]}, {row_key[1]}",
        )
    for row_key in sorted(actual_rows.keys() - expected_rows.keys()):
        audit.error(
            "sample-extra",
            f"sample has non-deterministic row: page {row_key[0]}, {row_key[1]}",
        )
    for row_key in sorted(actual_rows.keys() & expected_rows.keys()):
        if actual_rows[row_key] != expected_rows[row_key]:
            audit.error(
                "sample-reason",
                f"reasons differ for page {row_key[0]}, {row_key[1]}: "
                f"got {sorted(actual_rows[row_key])}, expected {sorted(expected_rows[row_key])}",
            )

    declared_total = re.search(
        r"`total_pages`\s*=\s*(\d+)", sample_path.read_text(encoding="utf-8")
    )
    if not declared_total or int(declared_total.group(1)) != total_pages:
        audit.error("sample-pages", "sample total_pages does not match validation report")
    if expected.quota != min(total_pages, math.ceil(total_pages * 0.15)):
        audit.error("sample-quota", "generated sample does not use the required 15% quota")
    return expected


def check_exports(tree: Any, images: Any, bookmarks: Any, validation: Any, audit: Audit) -> None:
    if isinstance(images, dict) and isinstance(images.get("images"), list):
        if images.get("total") != len(images["images"]):
            audit.error("images-count", "images_v1 total does not match images array length")
    else:
        audit.error("images-shape", "images_v1.json must contain an images array")
    if not isinstance(bookmarks, list):
        audit.error("bookmarks-shape", "bookmarks.json must be an array")
    if isinstance(validation, dict) and isinstance(tree, list):
        summary = validation.get("summary", {})
        if summary.get("section_count") != len(tree):
            audit.error("report-count", "validation section_count does not match tree length")
        structure = validation.get("validation", {}).get("structure", {})
        if isinstance(bookmarks, list) and structure.get("bookmark_count") != len(bookmarks):
            audit.error("report-count", "validation bookmark_count does not match bookmarks length")


def check_findings(
    path: Path,
    manual_id: str,
    tree: Any,
    sample: Any,
    version_manifest: Any,
    audit: Audit,
) -> None:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != tuple(QA_COLUMNS):
                audit.error(
                    "findings-columns",
                    f"official columns must be exactly {list(QA_COLUMNS)}; got {reader.fieldnames}",
                )
                return
            rows = list(reader)
    except OSError as exc:
        audit.error("findings-file", str(exc))
        return

    def finding_key(row: dict[str, Any]) -> str:
        return "|".join(str(row.get(field, "")) for field in QA_COLUMNS[:4])

    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        row_key = finding_key(row)
        if row_key in seen:
            audit.error(
                "finding-duplicate",
                f"duplicate finding key on CSV line {index}: {row_key}",
            )
        seen.add(row_key)
        if row.get("manual_id") != manual_id:
            audit.error("finding-manual", f"CSV line {index} has a different manual_id")
        result = row.get("result", "").strip().upper()
        severity = row.get("severity", "").strip()
        normalized = LEGACY_SEVERITIES.get(severity, severity)
        evidence = row.get("evidence", "").strip()
        if result and result not in {"PASS", "FAIL"}:
            audit.error("finding-result", f"CSV line {index} result must be PASS or FAIL")
        if result == "PASS" and severity:
            audit.error("finding-severity", f"CSV line {index} PASS severity must be empty")
        if result == "FAIL" and normalized not in SEVERITIES:
            audit.error("finding-severity", f"CSV line {index} FAIL severity is invalid")
        if result and not evidence:
            audit.error("finding-evidence", f"CSV line {index} completed result lacks evidence")

    if isinstance(tree, list) and sample is not None:
        expected_rows = generate_findings_template(manual_id, tree, sample)
        expected = {row.stable_key for row in expected_rows}
        actual = {finding_key(row) for row in rows}
        for missing in sorted(expected - actual):
            audit.error("finding-missing", f"required template row is missing: {missing}")
        for extra in sorted(actual - expected):
            audit.error("finding-extra", f"finding is outside the deterministic template: {extra}")

    finalized = isinstance(version_manifest, dict) and version_manifest.get("status") == "finalized"
    if finalized:
        for index, row in enumerate(rows, start=2):
            if row.get("result", "").strip().upper() not in {"PASS", "FAIL"}:
                audit.error("finalized-pending", f"finalized version has pending CSV line {index}")


def run_audit(qa_root: Path, manual_id: str, version: str) -> tuple[Audit, Path]:
    audit = Audit()
    version_root = (qa_root / manual_id / version).resolve()
    if not version_root.is_dir():
        audit.error("version-missing", f"version directory does not exist: {version_root}")
        return audit, version_root
    check_required_files(version_root, audit)

    source_manifest = load_json(
        qa_root / manual_id / "source_manifest.json", audit, "source-manifest"
    )
    version_manifest = load_json(version_root / "version_manifest.json", audit, "version-manifest")
    artifact_manifest = load_json(
        version_root / "artifact_manifest.json", audit, "artifact-manifest"
    )
    tree = load_json(version_root / "exports" / "tree.json", audit, "tree-json")
    images = load_json(version_root / "exports" / "images_v1.json", audit, "images-json")
    bookmarks = load_json(version_root / "exports" / "bookmarks.json", audit, "bookmarks-json")
    validation = load_json(version_root / "validation_report.json", audit, "validation-json")

    check_source(source_manifest, version_manifest, manual_id, version, audit)
    check_artifacts(version_root, artifact_manifest, audit)
    check_tree(tree, audit)
    check_exports(tree, images, bookmarks, validation, audit)
    sample = check_sample(version_root, manual_id, tree, validation, audit)
    check_findings(
        version_root / "findings" / "findings_log.csv",
        manual_id,
        tree,
        sample,
        version_manifest,
        audit,
    )
    return audit, version_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-root", type=Path, default=Path("qa"))
    parser.add_argument("--manual-id", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    audit, version_root = run_audit(args.qa_root.resolve(), args.manual_id, args.version)
    status = "PASS" if not audit.errors else "FAIL"
    if args.json_output:
        print(
            json.dumps(
                {
                    "status": status,
                    "version_root": str(version_root),
                    "error_count": len(audit.errors),
                    "warning_count": len(audit.warnings),
                    "issues": [asdict(issue) for issue in audit.issues],
                },
                indent=2,
            )
        )
    else:
        print(
            f"{status}: {version_root} "
            f"({len(audit.errors)} error(s), {len(audit.warnings)} warning(s))"
        )
        for issue in audit.issues:
            print(f"- {issue.level} [{issue.code}] {issue.message}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
