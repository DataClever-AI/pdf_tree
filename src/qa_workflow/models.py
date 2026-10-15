"""Shared data contracts for the QA workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

QA_COLUMNS = (
    "manual_id",
    "section_id",
    "page_sampled",
    "checklist_ref",
    "result",
    "severity",
    "evidence",
    "notes",
)


@dataclass(frozen=True)
class QAVersion:
    """Resolved paths and manifest data for one manual review version."""

    qa_root: Path
    manual_id: str
    version: str
    root: Path
    source_manifest: dict[str, Any]
    version_manifest: dict[str, Any]

    @property
    def manual_root(self) -> Path:
        return self.qa_root / self.manual_id

    @property
    def findings_csv(self) -> Path:
        return self.root / "findings" / "findings_log.csv"

    @property
    def review_state_path(self) -> Path:
        return self.root / "findings" / "review_state.json"

    @property
    def tree_path(self) -> Path:
        return self.root / "exports" / "tree.json"

    @property
    def images_path(self) -> Path:
        return self.root / "exports" / "images_v1.json"

    @property
    def bookmarks_path(self) -> Path:
        return self.root / "exports" / "bookmarks.json"

    @property
    def validation_path(self) -> Path:
        return self.root / "validation_report.json"

    @property
    def run_log_path(self) -> Path:
        return self.root / "logs" / "run.log"


@dataclass(frozen=True)
class ArtifactRecord:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ArtifactManifest:
    manual_id: str
    version: str
    artifacts: tuple[ArtifactRecord, ...]
    manifest_path: Path


@dataclass(frozen=True)
class SourceIntegrity:
    valid: bool
    status: str
    source_path: Path | None
    expected_sha256: str | None
    actual_sha256: str | None


@dataclass(frozen=True)
class MigrationAction:
    manual_id: str
    source: str
    destination: str
    status: str
    sha256: str | None = None


@dataclass
class MigrationReport:
    dry_run: bool
    actions: list[MigrationAction] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    migrated_manuals: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts
