"""Safe filesystem storage, versioning, artifact export, and legacy migration."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Any

from .models import (
    ArtifactManifest,
    ArtifactRecord,
    MigrationAction,
    MigrationReport,
    QAVersion,
    SourceIntegrity,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_VERSION = re.compile(r"^v[1-9][0-9]*(?:\.[1-9][0-9]*)?$")
_VERSION_DIRS = ("exports", "sampling", "findings", "logs", "agent_exchange")
_RESERVED_QA_DIRS = {"_scripts", "bugs", "confidence_index", "__pycache__"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_segment(value: str, *, version: bool = False) -> str:
    pattern = _VERSION if version else _SAFE_ID
    if not pattern.fullmatch(value):
        kind = "version (expected v1, v2, v2.1, ...)" if version else "manual_id"
        raise ValueError(f"Invalid {kind}: {value!r}")
    return value


def is_version_name(value: str) -> bool:
    return bool(_VERSION.fullmatch(value))


def version_sort_key(version: str) -> tuple[int, int]:
    """``v2`` -> (2, 0), ``v2.1`` -> (2, 1); mitigation versions sort after their base."""
    major, _, minor = version[1:].partition(".")
    return int(major), int(minor or 0)


def version_label(version: str, manifest: dict[str, Any] | None) -> str:
    """Display name for a version, e.g. ``v2.1 · BUG-019`` for a mitigation version."""
    targets = (manifest or {}).get("mitigation", {}).get("targets") or []
    return f"{version} · {', '.join(targets)}" if targets else version


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object at {path}")
    return payload


def _version_paths(qa_root: Path, manual_id: str, version: str) -> tuple[Path, Path]:
    _validate_segment(manual_id)
    _validate_segment(version, version=True)
    manual_root = qa_root.resolve() / manual_id
    return manual_root, manual_root / version


def create_qa_version(
    qa_root: Path,
    manual_id: str,
    version: str,
    source_pdf: Path,
    reviewer: str,
    *,
    mitigation: dict[str, Any] | None = None,
) -> QAVersion:
    """Create a new version exclusively; an existing directory is an error.

    ``mitigation`` (base version, target bug ids, pipeline commit) is stored in the version
    manifest of a mitigation version such as ``v2.1``.
    """
    manual_root, root = _version_paths(qa_root, manual_id, version)
    source_pdf = source_pdf.expanduser().resolve()
    if not source_pdf.is_file():
        raise FileNotFoundError(f"Source PDF not found: {source_pdf}")
    if source_pdf.suffix.lower() != ".pdf":
        raise ValueError("source_pdf must point to a PDF")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    if root.exists():
        raise FileExistsError(f"QA version already exists: {root}")

    source_hash = sha256_file(source_pdf)
    manual_root.mkdir(parents=True, exist_ok=True)
    source_manifest_path = manual_root / "source_manifest.json"
    if source_manifest_path.exists():
        current = _load_json(source_manifest_path)
        if current.get("sha256") != source_hash or current.get("path") != str(source_pdf):
            raise ValueError(
                "The manual already points to a different PDF path or checksum; use a new manual_id"
            )
        source_manifest = current
    else:
        source_manifest = {
            "schema_version": 1,
            "manual_id": manual_id,
            "path": str(source_pdf),
            "sha256": source_hash,
            "size_bytes": source_pdf.stat().st_size,
            "recorded_at": utc_now(),
        }
        atomic_write_json(source_manifest_path, source_manifest)

    root.mkdir()
    for name in _VERSION_DIRS:
        (root / name).mkdir()
    now = utc_now()
    version_manifest = {
        "schema_version": 1,
        "manual_id": manual_id,
        "version": version,
        "reviewer": reviewer.strip(),
        "status": "in_review",
        "source_sha256": source_hash,
        "created_at": now,
        "updated_at": now,
        "finalized_at": None,
    }
    if mitigation is not None:
        version_manifest["mitigation"] = mitigation
    atomic_write_json(root / "version_manifest.json", version_manifest)
    return QAVersion(qa_root.resolve(), manual_id, version, root, source_manifest, version_manifest)


def open_qa_version(qa_root: Path, manual_id: str, version: str) -> QAVersion:
    manual_root, root = _version_paths(qa_root, manual_id, version)
    source_path = manual_root / "source_manifest.json"
    version_path = root / "version_manifest.json"
    if not root.is_dir() or not version_path.is_file():
        raise FileNotFoundError(f"QA version not found: {root}")
    source_manifest = (
        _load_json(source_path)
        if source_path.exists()
        else {
            "schema_version": 1,
            "manual_id": manual_id,
            "path": None,
            "sha256": None,
            "missing": True,
        }
    )
    version_manifest = _load_json(version_path)
    if version_manifest.get("manual_id") != manual_id or version_manifest.get("version") != version:
        raise ValueError(f"Version manifest identity mismatch: {version_path}")
    return QAVersion(qa_root.resolve(), manual_id, version, root, source_manifest, version_manifest)


def set_version_status(qa_version: QAVersion, status: str) -> QAVersion:
    if status not in {"in_review", "finalized"}:
        raise ValueError("status must be 'in_review' or 'finalized'")
    manifest = dict(qa_version.version_manifest)
    manifest["status"] = status
    manifest["updated_at"] = utc_now()
    manifest["finalized_at"] = utc_now() if status == "finalized" else None
    atomic_write_json(qa_version.root / "version_manifest.json", manifest)
    return open_qa_version(qa_version.qa_root, qa_version.manual_id, qa_version.version)


def mark_version_edited(qa_version: QAVersion) -> QAVersion:
    """Editing a finalized version deliberately reopens its review."""
    return set_version_status(qa_version, "in_review")


def verify_source_pdf(qa_version: QAVersion) -> SourceIntegrity:
    raw_path = qa_version.source_manifest.get("path")
    expected = qa_version.source_manifest.get("sha256")
    if not raw_path:
        return SourceIntegrity(False, "Source PDF path is not recorded", None, expected, None)
    source_path = Path(raw_path).expanduser()
    if not source_path.is_file():
        return SourceIntegrity(False, "Source PDF is missing", source_path, expected, None)
    actual = sha256_file(source_path)
    if not expected:
        return SourceIntegrity(
            False, "Source PDF checksum is not recorded", source_path, None, actual
        )
    if actual != expected or qa_version.version_manifest.get("source_sha256") != expected:
        return SourceIntegrity(False, "Source PDF checksum changed", source_path, expected, actual)
    return SourceIntegrity(True, "Source PDF verified", source_path, expected, actual)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def serialize_images(images: Any) -> dict[str, Any]:
    if isinstance(images, dict):
        return images
    records = []
    for image in images or []:
        raw = image.image_bytes if hasattr(image, "image_bytes") else image.get("image_bytes", b"")
        record = {
            "section_id": getattr(image, "section_id", None),
            "page_no": getattr(image, "page_no", 0),
            "width_px": getattr(image, "width_px", 0),
            "height_px": getattr(image, "height_px", 0),
            "image_b64": base64.b64encode(raw).decode("ascii"),
        }
        if getattr(image, "origin", "raster") != "raster":
            record["origin"] = image.origin  # a rendered vector figure (BUG-010)
        records.append(record)
    return {
        "total": len(records),
        "mapped_count": sum(1 for record in records if record["section_id"] is not None),
        "unmapped_count": sum(1 for record in records if record["section_id"] is None),
        "images": records,
    }


def serialize_bookmarks(bookmarks: Any) -> list[dict[str, Any]]:
    records = []
    for bookmark in bookmarks or []:
        if isinstance(bookmark, dict):
            records.append(bookmark)
        else:
            level, title, page_no = bookmark
            records.append({"level": level, "title": title, "page_no": page_no})
    return records


def write_pipeline_artifacts(
    qa_version: QAVersion,
    *,
    tree: Any,
    images: Any,
    bookmarks: Any,
    validation_report: Any,
    run_log: str,
    overwrite: bool = False,
) -> ArtifactManifest:
    """Write the five official artifacts and a checksum manifest."""
    payloads = {
        qa_version.tree_path: _json_bytes(tree),
        qa_version.images_path: _json_bytes(serialize_images(images)),
        qa_version.bookmarks_path: _json_bytes(serialize_bookmarks(bookmarks)),
        qa_version.validation_path: _json_bytes(validation_report),
        qa_version.run_log_path: run_log.encode("utf-8"),
    }
    for path, data in payloads.items():
        if path.exists() and path.read_bytes() != data and not overwrite:
            raise FileExistsError(f"Artifact exists with different content: {path}")
    records = []
    for path, data in payloads.items():
        if not path.exists() or path.read_bytes() != data:
            atomic_write_bytes(path, data)
        records.append(
            ArtifactRecord(str(path.relative_to(qa_version.root)), _sha256_bytes(data), len(data))
        )
    manifest_path = qa_version.root / "artifact_manifest.json"
    manifest_payload = {
        "schema_version": 1,
        "manual_id": qa_version.manual_id,
        "version": qa_version.version,
        "generated_at": utc_now(),
        "artifacts": [asdict(record) for record in records],
    }
    atomic_write_json(manifest_path, manifest_payload)
    return ArtifactManifest(qa_version.manual_id, qa_version.version, tuple(records), manifest_path)


def build_artifact_zip(qa_version: QAVersion, *, include_images: bool = False) -> bytes:
    """Return the official version artifacts as a download-ready ZIP."""
    candidates = [
        qa_version.tree_path,
        qa_version.bookmarks_path,
        qa_version.validation_path,
        qa_version.run_log_path,
        qa_version.root / "artifact_manifest.json",
        qa_version.root / "version_manifest.json",
        qa_version.root / "sampling" / "sample_selection.md",
        qa_version.findings_csv,
    ]
    if include_images:
        candidates.append(qa_version.images_path)
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in candidates:
            if path.is_file():
                archive.writestr(str(path.relative_to(qa_version.root)), path.read_bytes())
    return output.getvalue()


def index_existing_artifacts(qa_version: QAVersion) -> ArtifactManifest:
    """Checksum official artifacts already present, including migrated legacy evidence."""
    candidates = [
        qa_version.tree_path,
        qa_version.images_path,
        qa_version.bookmarks_path,
        qa_version.validation_path,
        qa_version.run_log_path,
    ]
    records = tuple(
        ArtifactRecord(
            str(path.relative_to(qa_version.root)), sha256_file(path), path.stat().st_size
        )
        for path in candidates
        if path.is_file()
    )
    manifest_path = qa_version.root / "artifact_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": 1,
            "manual_id": qa_version.manual_id,
            "version": qa_version.version,
            "generated_at": utc_now(),
            "artifacts": [asdict(record) for record in records],
        },
    )
    return ArtifactManifest(qa_version.manual_id, qa_version.version, records, manifest_path)


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _find_source_pdf(manual_id: str, source_dir: Path | None) -> Path | None:
    if source_dir is None or not source_dir.is_dir():
        return None
    pdfs = sorted(source_dir.glob("*.pdf"))
    if not pdfs:
        return None
    needle = _normalized(manual_id)
    exact = [pdf for pdf in pdfs if _normalized(pdf.stem) == needle]
    if exact:
        return exact[0].resolve()
    scored = sorted(
        ((SequenceMatcher(None, needle, _normalized(pdf.stem)).ratio(), pdf) for pdf in pdfs),
        reverse=True,
    )
    return scored[0][1].resolve() if scored[0][0] >= 0.45 else None


def _migration_destination(relative: Path) -> Path:
    if relative.parts[0] == "exports" and relative.suffix == ".json":
        name = relative.name
        if name.endswith("_images_v1.json"):
            return Path("exports/images_v1.json")
        if name.endswith("_bookmarks.json"):
            return Path("exports/bookmarks.json")
        if name.endswith("_tree.json"):
            return Path("exports/tree.json")
    if relative.name == "exports_manifest.txt":
        return Path("legacy_exports_manifest.txt")
    return relative


def migrate_legacy_layout(
    qa_root: Path,
    *,
    source_dir: Path | None = None,
    reviewer: str = "legacy-migration",
    dry_run: bool = True,
) -> MigrationReport:
    """Move pre-versioned manual contents into v1 after a conflict/checksum audit."""
    qa_root = qa_root.resolve()
    report = MigrationReport(dry_run=dry_run)
    if not qa_root.is_dir():
        return report
    for manual_root in sorted(path for path in qa_root.iterdir() if path.is_dir()):
        manual_id = manual_root.name
        if manual_id in _RESERVED_QA_DIRS or manual_id.startswith((".", "_")):
            continue
        legacy = [
            path
            for path in manual_root.rglob("*")
            if path.is_file()
            and not any(part.startswith(".") for part in path.relative_to(manual_root).parts)
            and "v1" not in path.relative_to(manual_root).parts
            and path.name not in {"source_manifest.json"}
        ]
        if not legacy:
            continue
        version_root = manual_root / "v1"
        if version_root.exists():
            report.conflicts.append(f"{manual_id}: {version_root} already exists")
            continue
        destinations: dict[Path, Path] = {}
        collision = False
        for source in legacy:
            relative = source.relative_to(manual_root)
            destination = version_root / _migration_destination(relative)
            if destination in destinations or destination.exists():
                report.conflicts.append(f"{manual_id}: destination conflict at {destination}")
                collision = True
                break
            destinations[destination] = source
        if collision:
            continue
        for destination, source in destinations.items():
            report.actions.append(
                MigrationAction(
                    manual_id,
                    str(source),
                    str(destination),
                    "planned" if dry_run else "migrated",
                    sha256_file(source),
                )
            )
        report.migrated_manuals.append(manual_id)
        if dry_run:
            continue

        source_pdf = _find_source_pdf(manual_id, source_dir)
        source_manifest = {
            "schema_version": 1,
            "manual_id": manual_id,
            "path": str(source_pdf) if source_pdf else None,
            "sha256": sha256_file(source_pdf) if source_pdf else None,
            "size_bytes": source_pdf.stat().st_size if source_pdf else None,
            "recorded_at": utc_now(),
            "missing": source_pdf is None,
        }
        atomic_write_json(manual_root / "source_manifest.json", source_manifest)
        for name in _VERSION_DIRS:
            (version_root / name).mkdir(parents=True, exist_ok=True)
        for destination, source in destinations.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            if sha256_file(destination) != next(
                action.sha256
                for action in report.actions
                if action.source == str(source) and action.destination == str(destination)
            ):
                raise OSError(f"Checksum mismatch after migrating {source}")
        now = utc_now()
        status = (
            "finalized" if (version_root / "findings/findings_log.csv").exists() else "in_review"
        )
        version_manifest = {
            "schema_version": 1,
            "manual_id": manual_id,
            "version": "v1",
            "reviewer": reviewer,
            "status": status,
            "source_sha256": source_manifest["sha256"],
            "created_at": now,
            "updated_at": now,
            "finalized_at": now if status == "finalized" else None,
            "migrated_from_legacy": True,
        }
        atomic_write_json(version_root / "version_manifest.json", version_manifest)
        migrated_version = open_qa_version(qa_root, manual_id, "v1")
        index_existing_artifacts(migrated_version)
        for child in sorted(manual_root.iterdir(), reverse=True):
            if child.is_dir() and child.name != "v1":
                try:
                    child.rmdir()
                except OSError:
                    pass
    return report
