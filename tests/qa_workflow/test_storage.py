from __future__ import annotations

from pathlib import Path

import pytest

from src.qa_workflow.storage import (
    create_qa_version,
    migrate_legacy_layout,
    open_qa_version,
    set_version_status,
    verify_source_pdf,
    write_pipeline_artifacts,
)


def test_create_open_and_never_overwrite(tmp_path: Path, source_pdf: Path) -> None:
    root = tmp_path / "qa"
    created = create_qa_version(root, "manual-1", "v1", source_pdf, "Alice")
    assert created.root == root.resolve() / "manual-1" / "v1"
    assert verify_source_pdf(created).valid
    with pytest.raises(FileExistsError):
        create_qa_version(root, "manual-1", "v1", source_pdf, "Alice")
    opened = open_qa_version(root, "manual-1", "v1")
    assert opened.version_manifest["reviewer"] == "Alice"


def test_source_change_blocks_integrity(qa_version, source_pdf: Path) -> None:
    source_pdf.write_bytes(source_pdf.read_bytes() + b"changed")
    integrity = verify_source_pdf(qa_version)
    assert not integrity.valid
    assert "checksum changed" in integrity.status


def test_artifacts_require_explicit_overwrite(qa_version) -> None:
    with pytest.raises(FileExistsError):
        write_pipeline_artifacts(
            qa_version,
            tree=[{"different": True}],
            images={},
            bookmarks=[],
            validation_report={},
            run_log="changed",
        )
    assert qa_version.tree_path.exists()
    assert qa_version.images_path.exists()
    assert qa_version.bookmarks_path.exists()
    assert qa_version.validation_path.exists()
    assert qa_version.run_log_path.exists()


def test_finalized_version_can_be_reopened(qa_version) -> None:
    final = set_version_status(qa_version, "finalized")
    assert final.version_manifest["status"] == "finalized"
    assert final.version_manifest["finalized_at"]


def test_migration_dry_run_conflict_and_checksums(tmp_path: Path, source_pdf: Path) -> None:
    qa_root = tmp_path / "qa"
    legacy = qa_root / "legacy"
    (legacy / "logs").mkdir(parents=True)
    (legacy / "logs" / "run.log").write_text("blocked")
    dry = migrate_legacy_layout(qa_root, source_dir=source_pdf.parent, dry_run=True)
    assert dry.ok and dry.migrated_manuals == ["legacy"]
    assert not (legacy / "v1").exists()
    result = migrate_legacy_layout(qa_root, source_dir=source_pdf.parent, dry_run=False)
    assert result.ok
    assert (legacy / "v1" / "logs" / "run.log").read_text() == "blocked"
    assert (legacy / "v1" / "version_manifest.json").exists()


@pytest.mark.parametrize("manual_id,version", [("../escape", "v1"), ("good", "one")])
def test_rejects_unsafe_segments(
    tmp_path: Path, source_pdf: Path, manual_id: str, version: str
) -> None:
    with pytest.raises(ValueError):
        create_qa_version(tmp_path / "qa", manual_id, version, source_pdf, "Alice")
