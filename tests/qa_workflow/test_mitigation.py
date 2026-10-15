from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pymupdf
import pytest

from src.qa_workflow.bug_registry import (
    Attempt,
    append_attempt,
    bug_template,
    ensure_attempts_section,
    last_attempt,
)
from src.qa_workflow.compare import compare_versions, tree_changes
from src.qa_workflow.confidence import (
    latest_reviewed_versions,
    latest_versions,
    list_manual_versions,
)
from src.qa_workflow.findings import generate_findings_template, write_findings_template
from src.qa_workflow.mitigation import (
    PipelineInfo,
    create_mitigation_version,
    plan_mitigation_sample,
    standing_fail_pairs,
    validate_mitigation_name,
)
from src.qa_workflow.models import QA_COLUMNS
from src.qa_workflow.root_causes import RootCause, parse_catalogue
from src.qa_workflow.sampling import generate_sample, render_sample_markdown
from src.qa_workflow.storage import (
    create_qa_version,
    set_version_status,
    version_label,
    version_sort_key,
    write_pipeline_artifacts,
)

PAGES = 40
CATALOGUE = parse_catalogue(
    {
        "bugs": [
            {"bug_id": "BUG-019", "title": "Heading anchor", "suspected_module": "matcher"},
            {"bug_id": "BUG-022", "title": "Header bleed", "suspected_module": "matcher"},
        ],
        "rules": [
            {"bug_id": "BUG-019", "regex": "anchor"},
            {"bug_id": "BUG-022", "regex": "running header"},
        ],
    }
)


def _tree(split: int = 20) -> list[dict]:
    def section(section_id: str, title: str, start: int, end: int, level: int, parent=None):
        return {
            "section_id": section_id,
            "title": title,
            "hierarchy_level": level,
            "hierarchy_path": f"/{title}",
            "page_start": start,
            "page_end": end,
            "parent_section_id": parent,
            "child_sections": [],
            "node_count": 3,
            "flagged_for_review": False,
            "structural_source": "toc",
            "semantic_nodes": [{"node_type": "text", "page_no": start, "canonical_text": title}],
        }

    root = section("sec_0001", "Manual", 1, PAGES, 1)
    first = section("sec_0002", "Part A", 1, split, 2, "sec_0001")
    second = section("sec_0003", "Part B", split + 1, PAGES, 2, "sec_0001")
    root["child_sections"] = ["sec_0002", "sec_0003"]
    return [root, first, second]


def _validation(tree: list[dict]) -> dict:
    return {
        "summary": {"total_pages": PAGES, "section_count": len(tree)},
        "validation": {"structure": {"status": "PASS", "bookmark_count": 3}},
    }


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    path = tmp_path / "manual.pdf"
    document = pymupdf.open()
    for number in range(1, PAGES + 1):
        document.new_page().insert_text((72, 72), f"Page {number}")
    document.save(path)
    document.close()
    return path


@pytest.fixture
def base(tmp_path: Path, pdf: Path):
    version = create_qa_version(tmp_path / "qa", "manual", "v2", pdf, "Reviewer")
    tree = _tree()
    write_pipeline_artifacts(
        version,
        tree=tree,
        images=[],
        bookmarks=[(2, "Part A", 1), (2, "Part B", 21), (1, "Manual", 1)],
        validation_report=_validation(tree),
        run_log="ok\n",
    )
    sample = generate_sample(tree, PAGES)
    (version.root / "sampling" / "sample_selection.md").write_text(
        render_sample_markdown("manual", sample)
    )
    write_findings_template(
        version.findings_csv, generate_findings_template("manual", tree, sample)
    )
    return version


def _fill(findings_csv: Path, failing: dict[tuple[str, str], str]) -> None:
    """Mark every row PASS except the (section, ref) pairs in ``failing`` (value = notes)."""
    with findings_csv.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        notes = failing.get((row["section_id"], row["checklist_ref"]))
        row.update(
            result="FAIL" if notes else "PASS",
            severity="Medium" if notes else "",
            evidence="Seen on the page.",
            notes=notes or "",
        )
    with findings_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QA_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _create_candidate(base, tree: list[dict], occurrences=frozenset()):
    return create_mitigation_version(
        base.qa_root,
        "manual",
        "v2",
        "v2.1",
        targets=["BUG-019"],
        pipeline=PipelineInfo("a1b2c3d4e5", "fix(section_matcher): exact heading match", False),
        sections=tree,
        total_pages=PAGES,
        images=[],
        bookmarks=[(2, "Part A", 1), (2, "Part B", 21), (1, "Manual", 1)],
        validation_report=_validation(tree),
        run_log="ok\n",
        occurrence_pairs=set(occurrences),
        extra_pages=3,
    )


def test_version_names_sort_and_label():
    assert sorted(["v2.1", "v10", "v2", "v1"], key=version_sort_key) == ["v1", "v2", "v2.1", "v10"]
    assert version_label("v2.1", {"mitigation": {"targets": ["BUG-019"]}}) == "v2.1 · BUG-019"
    assert version_label("v2", {}) == "v2"
    validate_mitigation_name("v2", "v2.1")
    validate_mitigation_name("v2.1", "v2.2")
    for bad in ("v3", "v2", "v2.1.1x"):
        with pytest.raises(ValueError):
            validate_mitigation_name("v2", bad)


def test_plan_keeps_base_pairs_and_is_deterministic():
    tree = _tree(split=22)
    base_pairs = {("sec_0002", 5), ("sec_0003", 33), ("sec_9999", 30)}
    plan = plan_mitigation_sample(
        tree, PAGES, base_pairs, {("sec_0002", 5)}, extra_pages=3, seed="manual:v2.1"
    )
    again = plan_mitigation_sample(
        tree, PAGES, base_pairs, {("sec_0002", 5)}, extra_pages=3, seed="manual:v2.1"
    )
    assert plan.check_rows == again.check_rows
    reasons = {(row.section_id, row.page): set(row.reasons) for row in plan.check_rows}
    official = set(plan.sample.section_pages.items())
    for pair in base_pairs - {("sec_9999", 30)}:
        assert pair in official or "base-pair" in reasons[pair]
    assert ("sec_0003", 30) in reasons or ("sec_0003", 30) in official
    if ("sec_0002", 5) in reasons:
        assert reasons[("sec_0002", 5)] == {"base-pair", "bug-occurrence"}
    assert sum("random-check" in value for value in reasons.values()) <= 3


def test_mitigation_version_passes_verifier_and_keeps_base(base):
    base_before = base.findings_csv.read_bytes()
    candidate, _plan, _rows = _create_candidate(base, _tree(split=22), {("sec_0002", 5)})
    manifest = json.loads((candidate.root / "version_manifest.json").read_text())
    assert manifest["mitigation"]["base_version"] == "v2"
    assert manifest["mitigation"]["targets"] == ["BUG-019"]
    assert manifest["mitigation"]["pipeline_commit"] == "a1b2c3d4e5"
    assert base.findings_csv.read_bytes() == base_before
    assert (
        "## Mitigation check rows"
        in (candidate.root / "sampling" / "sample_selection.md").read_text()
    )

    script = Path(__file__).resolve().parents[2] / "pdf-tree-qa-verifier/scripts/verify_version.py"
    spec = importlib.util.spec_from_file_location("verify_version", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["verify_version"] = module
    spec.loader.exec_module(module)
    audit, _root = module.run_audit(base.qa_root, "manual", "v2.1")
    assert not audit.errors, audit.errors

    with pytest.raises(FileExistsError):
        _create_candidate(base, _tree())


def test_latest_version_ignores_unfinalized_mitigation(base):
    candidate, _plan, _rows = _create_candidate(base, _tree())
    qa_root = base.qa_root
    assert list_manual_versions(qa_root)["manual"] == ["v2", "v2.1"]
    assert latest_versions(qa_root)["manual"] == "v2"
    set_version_status(candidate, "finalized")
    assert latest_versions(qa_root)["manual"] == "v2.1"


def test_confidence_page_opens_the_newest_version_with_approved_rows(base):
    candidate, _plan, _rows = _create_candidate(base, _tree())
    qa_root = base.qa_root
    assert latest_reviewed_versions(qa_root)["manual"] == "v2"  # v2.1 has no approved rows
    _fill(candidate.findings_csv, {})
    assert latest_reviewed_versions(qa_root)["manual"] == "v2.1"


def test_compare_counts_paired_rows_and_regressions(base):
    candidate, _plan, _rows = _create_candidate(base, _tree(split=22))
    _fill(
        base.findings_csv,
        {
            ("sec_0002", "5.4-page_start_end"): "Wrong anchor on the heading.",
            ("sec_0003", "5.4-page_start_end"): "Wrong anchor again.",
        },
    )
    _fill(
        candidate.findings_csv,
        {("sec_0003", "5.5-filters_discarding"): "running header in the image list"},
    )
    result = compare_versions(base.qa_root, "manual", "v2", "v2.1", CATALOGUE)
    target = result.target_deltas[0]
    assert (target.bug_id, target.base_paired, target.candidate_paired) == ("BUG-019", 2, 0)
    kinds = sorted(change.kind for change in result.row_changes)
    assert kinds == ["improved", "improved", "regression"]
    assert result.candidate_label == "v2.1 · BUG-019"
    assert {change.section_id for change in result.tree_changes or ()} == {
        "sec_0002",
        "sec_0003",
    }


def test_tree_changes_reports_added_sections():
    changes = tree_changes(_tree()[:2], _tree())
    assert [(change.section_id, change.field) for change in changes] == [("sec_0003", "section")]


def test_attempts_table_append_and_last_attempt():
    text = bug_template(RootCause("BUG-019", "Heading anchor", "matcher"), "2026-09-29")
    attempt = Attempt(
        "2026-10-01", "manual", "v2.1", "`a1b2c3d` fix: exact match", "Ignore '!'", 7, 0, 0, "Keep"
    )
    updated = append_attempt(text, attempt)
    second = append_attempt(updated, Attempt("2026-10-02", "m2", "v1.1", "—", "x", 5, 1, 1, "Keep"))
    assert (
        "| 2026-10-01 | `manual` | v2.1 | `a1b2c3d` fix: exact match | Ignore '!' | 7 → 0 |"
        in second
    )
    assert second.index("2026-10-01 |") < second.index("2026-10-02 |")
    assert "updated: 2026-10-02" in second
    assert last_attempt(second) == "v1.1: 5 → 1"
    pending = Attempt("2026-10-03", "m", "v2.2", "—", "x", 0, 0, 0, "Wait", reviewed=False)
    assert last_attempt(append_attempt(second, pending)) == "v2.2: not reviewed"
    legacy = "# BUG\n\n<!-- generated:occurrences:start -->\n<!-- generated:occurrences:end -->\n"
    assert ensure_attempts_section(legacy).index("## Attempts") < legacy.find("<!--") + 20


def test_random_checks_never_repeat_an_official_row():
    # 2002 v2.3: quota page 388 of sec_0172 (not its first sampled page) came back as a
    # random check, so the template had the same rows twice.
    tree = _tree(split=22)
    plan = plan_mitigation_sample(tree, PAGES, set(), set(), extra_pages=PAGES, seed="m:v2.1")
    official = {(row.section_id, row.page) for row in plan.sample.rows}
    assert not {(row.section_id, row.page) for row in plan.check_rows} & official


def _reviewed_version(root: Path, version: str, tree: list[dict], rows: list[tuple]) -> None:
    (root / version / "exports").mkdir(parents=True)
    (root / version / "findings").mkdir(parents=True)
    (root / version / "exports" / "tree.json").write_text(json.dumps(tree))
    with (root / version / "findings" / "findings_log.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(QA_COLUMNS)
        for section_id, page, ref, result in rows:
            writer.writerow(["M", section_id, page, ref, result, "Low", "", ""])


def test_standing_fails_follow_titles_and_newest_result(tmp_path):
    def section(section_id, title, start, end, level=1):
        return {
            "section_id": section_id,
            "title": title,
            "page_start": start,
            "page_end": end,
            "hierarchy_level": level,
        }

    old_tree = [section("sec_0001", "Intro", 1, 2), section("sec_0002", "Setup", 3, 5)]
    _reviewed_version(
        tmp_path / "M",
        "v1",
        old_tree,
        [
            ("sec_0002", 4, "5.1-a", "FAIL"),
            ("sec_0001", 1, "5.1-a", "FAIL"),
            ("sec_0002", 5, "5.1-a", "FAIL"),
        ],
    )
    # v1.1 fixes p1; v1.2 ids shift because a section was added before "Setup".
    _reviewed_version(tmp_path / "M", "v1.1", old_tree, [("sec_0001", 1, "5.1-a", "PASS")])
    new_tree = [
        section("sec_0001", "Intro", 1, 2),
        section("sec_0002", "Notes", 3, 3),
        section("sec_0003", "Setup", 3, 5),
    ]
    assert standing_fail_pairs(tmp_path, "M", new_tree) == {("sec_0003", 4), ("sec_0003", 5)}
