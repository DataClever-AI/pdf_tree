"""
Pipeline orchestrator — pdf_tree_0.1v.

Steps:
  1. fitz_toc      → bookmarks + page count
  2. bookmark_sanity → pre-check bookmark quality
  3. docling_extract → DoclingDocument (optional)
  4. synthetic_toc  → fallback bookmarks from Docling headers (if no embedded TOC)
  5. toc_classification → drop front-matter noise (Abstract, List of Figures, ...)
                       and set aside back-matter (Bibliography, Appendix, ...)
                       before either pollutes the hierarchy or the offset
                       calibration sample in the next step
  6. toc_resolution → detect numbering scheme (arabic/roman/alphanumeric),
                       calibrate offset(s) (global, falling back to
                       per-chapter/per-cluster), and verify each bookmark's
                       title actually appears near its resolved page before
                       it's trusted as a structural boundary
  7. section_matcher → MatchedSection list (failed verifications flagged, not dropped)
  8. tree_export    → tree.json sections (flat list of dicts)
  9. tree_validator → ValidationReport (coverage, precision, structure)

Returns PipelineResult — clean interface for Streamlit UI.
Merge path: pipeline.py is the only file that needs to integrate into mvp_v2/src/app.py.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from src.models.extraction import BoundingBox, DoclingDocument
from src.tree_builder.bookmark_sanity import (
    BookmarkSanityReport,
    check_bookmark_sanity,
    repair_bookmarks,
)
from src.tree_builder.fitz_toc import get_embedded_toc, page_count, page_text_reader
from src.tree_builder.section_matcher import (
    MatchedSection,
    find_unbookmarked_index,
    match_content_to_sections,
    nearest_above,
)
from src.tree_builder.synthetic_toc import synthesize_toc
from src.tree_builder.toc_classification import ExcludedTocEntry, filter_toc_entries
from src.tree_builder.toc_resolution import NumberingReport, resolve_toc_pages
from src.tree_builder.tree_export import build_tree_json
from src.validation.tree_validator import ValidationReport, validate_tree


@dataclass
class EmbeddedImage:
    """Embedded raster image extracted from a PDF page."""

    image_bytes: bytes
    page_no: int
    width_px: int
    height_px: int
    section_id: str | None = None  # assigned after pipeline by position on the page
    bbox: BoundingBox | None = None  # bottom-left origin, same frame as Docling bboxes
    origin: str = "raster"  # "vector": a figure drawn with paths, rendered (BUG-010)


@dataclass
class PipelineResult:
    """Full pipeline output — drives all Streamlit pages."""

    # Core outputs
    sections: list[dict[str, Any]]              # tree.json flat list
    bookmarks: list[tuple[int, str, int]]       # (level, title, page_no) from fitz
    structural_source: str                       # "toc" | "inferred"
    sanity_report: BookmarkSanityReport

    # Extraction metadata
    total_pages: int
    fitz_authoritative: bool                    # True = embedded TOC used
    docling_doc: DoclingDocument | None         # None if docling not run

    # Validation
    validation: ValidationReport | None

    # Timing
    elapsed_s: float
    stage_times: dict[str, float] = field(default_factory=dict)

    # Page-numbering traceability (see toc_resolution.py) — None only if
    # bookmarks were empty (nothing to resolve).
    numbering_report: NumberingReport | None = None

    # Raw TOC entries excluded from the hierarchy (see toc_classification.py)
    # — front matter noise (Abstract, List of Figures, ...) and back matter
    # (Bibliography, Appendix, ...) unless include_back_matter=True. Never
    # silently dropped — inspectable here.
    excluded_toc_entries: list[ExcludedTocEntry] = field(default_factory=list)

    # Images (embedded per section)
    images: list[EmbeddedImage] = field(default_factory=list)

    # Error
    error: str | None = None

    # ---- convenience properties ----

    @property
    def section_count(self) -> int:
        return len(self.sections)

    @property
    def root_sections(self) -> list[dict[str, Any]]:
        return [s for s in self.sections if s.get("parent_section_id") is None]

    @property
    def valid(self) -> bool:
        if self.validation is None:
            return False
        return self.validation.status == "PASS"

    @property
    def docling_text_blocks(self) -> int:
        return len(self.docling_doc.text_blocks) if self.docling_doc else 0

    @property
    def docling_tables(self) -> int:
        return len(self.docling_doc.tables) if self.docling_doc else 0

    @property
    def docling_elapsed_s(self) -> float:
        return self.docling_doc.extraction_elapsed_s if self.docling_doc else 0.0

    def sections_by_id(self) -> dict[str, dict[str, Any]]:
        return {s["section_id"]: s for s in self.sections}


def _node_bbox(node: dict[str, Any]) -> BoundingBox | None:
    raw = node.get("bbox")
    if not raw:
        return None
    return BoundingBox(
        x0=raw["x0"],
        y0=raw["y0"],
        x1=raw["x1"],
        y1=raw["y1"],
        page_no=node.get("page_no", 0),
        coordinate_origin="bottomleft",
    )


def _map_images_to_sections(
    images: list[EmbeddedImage],
    sections: list[dict[str, Any]],
) -> list[EmbeddedImage]:
    """
    Assign section_id to each image by its position on the page.

    The image goes to the section of the nearest text node printed above it; an image
    above every text node of its page continues the previous page's content (BUG-003).
    Images without a bbox, on pages without placed text, or placed in a section more
    than one page away from its page range (reading order out of sync, BUG-005), fall
    back to the deepest section on the page.
    """
    if not images or not sections:
        return images

    # Build page → sections map (sorted by level descending so deepest wins)
    page_sections: dict[int, list[dict[str, Any]]] = {}
    for sec in sections:
        for pg in range(sec.get("page_start", 0), sec.get("page_end", 0) + 1):
            page_sections.setdefault(pg, []).append(sec)
    for pg in page_sections:
        page_sections[pg].sort(key=lambda s: s.get("hierarchy_level", 0), reverse=True)

    by_id = {sec["section_id"]: sec for sec in sections}
    # Text nodes in document order, and the placed ones per page.
    ordered: list[tuple[int, str]] = []
    page_nodes: dict[int, list[tuple[BoundingBox, bool, tuple[int, str]]]] = {}
    for sec in sections:
        for node in sec.get("semantic_nodes", []):
            if node.get("node_type") == "table":
                continue
            key = (node.get("semantic_order", 0), sec["section_id"])
            ordered.append(key)
            bbox = _node_bbox(node)
            if bbox is not None:
                heading = node.get("node_type") == "heading"
                page_nodes.setdefault(node.get("page_no", 0), []).append((bbox, heading, key))
    ordered.sort()
    position = {key: index for index, key in enumerate(ordered)}

    def _by_position(img: EmbeddedImage) -> str | None:
        nodes = page_nodes.get(img.page_no)
        if img.bbox is None or not nodes:
            return None
        key = nearest_above(img.bbox, nodes)
        if key is not None:
            return key[1]
        first = position[min(key for _bbox, _heading, key in nodes)]
        return ordered[first - 1][1] if first > 0 else None

    result: list[EmbeddedImage] = []
    for img in images:
        section_id = _by_position(img)
        # Reading order can be out of sync with the pages (BUG-005): only trust a
        # section whose page range contains the image or ends on the page before it.
        if section_id is None or not (
            by_id[section_id].get("page_start", 0)
            <= img.page_no
            <= by_id[section_id].get("page_end", 0) + 1
        ):
            candidates = page_sections.get(img.page_no, [])
            section_id = candidates[0]["section_id"] if candidates else None
        result.append(replace(img, section_id=section_id))
    return result


def _with_excluded_boundaries(
    bookmarks: list[tuple[int, str, int]],
    excluded: list[ExcludedTocEntry],
    raw_toc_size: int,
) -> tuple[list[tuple[int, str, int]], list[bool]]:
    """
    Put the excluded top-level TOC entries (Index, Table of contents, Glossary) back
    in TOC order as boundaries, so the section before them ends where they start
    instead of absorbing their pages (BUG-002). Deeper excluded entries (Philips
    'Symbols' inside a chapter) are left out as before. fitz bookmark pages are
    physical pages, so an excluded entry's page needs no resolution.
    """
    top_level = min(
        [level for level, _, _ in bookmarks] + [e.level for e in excluded], default=1
    )
    by_position = {e.position: e for e in excluded}
    kept = iter(bookmarks)
    entries: list[tuple[int, str, int]] = []
    boundaries: list[bool] = []
    for position in range(raw_toc_size):
        entry = by_position.get(position)
        if entry is None:
            entries.append(next(kept))
            boundaries.append(False)
        elif entry.level == top_level and isinstance(entry.page, int):
            entries.append((entry.level, entry.title, entry.page))
            boundaries.append(True)
    return entries, boundaries


# Vector figures (BUG-010): drawing paths are grouped when they lie within _VECTOR_GAP
# points of each other; a group with enough path segments and area is a figure.
_VECTOR_GAP = 12.0
_VECTOR_MIN_SEGMENTS = 40
_VECTOR_MIN_AREA_FRAC = 0.01
_VECTOR_BAND = 0.08            # running header/footer rules
_VECTOR_DPI = 150


def _extract_vector_figures(
    pdf_path: Path, n_pages: int, doc: DoclingDocument, logger: logging.Logger
) -> list[EmbeddedImage]:
    """
    Render figures drawn with vector paths (2002 schematics, LOGIQ_e flowcharts, Philips
    module drawings) that the raster extraction cannot see. Skipped: paths in the
    header/footer band, page frames, Docling table grids, thin caution/warning bars,
    groups mostly covered by raster images (annotations on a photo that is already
    kept) and straight-line grids around raster photos (step tables).
    """
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore[no-redef]

    tables_by_page: dict[int, list[Any]] = {}
    for table in doc.tables:
        if table.bbox is not None:
            tables_by_page.setdefault(table.page_no, []).append(table.bbox)

    result: list[EmbeddedImage] = []
    pdf = fitz.open(str(pdf_path))
    for page_no in range(1, n_pages + 1):
        page = pdf[page_no - 1]
        width, height = page.rect.width, page.rect.height
        tables = [
            fitz.Rect(b.x0, height - b.y0, b.x1, height - b.y1)
            for b in tables_by_page.get(page_no, [])
        ]
        paths = []
        for drawing in page.get_drawings():
            rect = fitz.Rect(drawing["rect"])
            if rect.y1 < height * _VECTOR_BAND or rect.y0 > height * (1 - _VECTOR_BAND):
                continue
            if rect.width > width * 0.85 and rect.height > height * 0.85:
                continue  # page frame or background
            if any(
                (table & rect).get_area() >= 0.8 * max(rect.get_area(), 1.0)
                or table.contains(rect)
                for table in tables
            ):
                continue
            items = drawing["items"]
            straight = sum(
                1
                for item in items
                if item[0] == "re"
                or (
                    item[0] == "l"
                    and (abs(item[1].x - item[2].x) < 0.5 or abs(item[1].y - item[2].y) < 0.5)
                )
            )
            paths.append((rect, len(items), straight))
        if not paths:
            continue

        groups: list[list[Any]] = []  # [rect, segments, straight segments]
        for rect, segments, straight in sorted(paths, key=lambda p: (p[0].y0, p[0].x0)):
            reach = fitz.Rect(rect.x0 - _VECTOR_GAP, rect.y0 - _VECTOR_GAP,
                              rect.x1 + _VECTOR_GAP, rect.y1 + _VECTOR_GAP)
            hits = [group for group in groups if group[0].intersects(reach)]
            if not hits:
                groups.append([fitz.Rect(rect), segments, straight])
                continue
            first = hits[0]
            first[0] |= rect
            first[1] += segments
            first[2] += straight
            for group in hits[1:]:
                first[0] |= group[0]
                first[1] += group[1]
                first[2] += group[2]
                groups.remove(group)

        rasters = [
            rects[0]
            for info in page.get_images(full=True)
            if (rects := page.get_image_rects(info[0]))
        ]
        for box, segments, straight in groups:
            box = box & page.rect
            if segments < _VECTOR_MIN_SEGMENTS:
                continue
            if box.get_area() < _VECTOR_MIN_AREA_FRAC * width * height:
                continue
            if box.height < 25 and box.width > 8 * box.height:
                continue  # caution/warning bar (SOMATOM)
            if sum((box & raster).get_area() for raster in rasters) >= 0.3 * box.get_area():
                continue  # annotations on a raster photo that is already kept
            if straight >= 0.8 * segments and any(box.contains(r) for r in rasters):
                continue  # step-table grid around photos (LOGIQ_S8)
            pixmap = page.get_pixmap(clip=box, dpi=_VECTOR_DPI)
            result.append(EmbeddedImage(
                image_bytes=pixmap.tobytes("png"),
                page_no=page_no,
                width_px=pixmap.width,
                height_px=pixmap.height,
                bbox=BoundingBox(
                    x0=box.x0, y0=height - box.y0, x1=box.x1, y1=height - box.y1,
                    page_no=page_no, coordinate_origin="bottomleft",
                ),
                origin="vector",
            ))
    pdf.close()
    logger.info("images: %d vector figures rendered", len(result))
    return result


def _flag_relocated_sections(sections: list[dict[str, Any]], sanity: BookmarkSanityReport) -> None:
    """Force flagged_for_review on sections built from a relocated bookmark."""
    for repair in sanity.repairs:
        if repair.kind != "relocated":
            continue
        for section in sections:
            same_title = section.get("title") == repair.title
            if same_title and section.get("page_start") == repair.new_page:
                section["flagged_for_review"] = True


def run_pipeline(
    pdf_path: Path,
    work_dir: Path,
    *,
    run_docling: bool = True,
    window_size: int = 60,
    window_overlap: int = 6,
    extract_images: bool = True,
    min_image_px: int = 48,
    include_back_matter: bool = False,
    logger: logging.Logger | None = None,
    on_window_complete: Any | None = None,
) -> PipelineResult:
    """
    Full tree-building pipeline for a PDF.

    Args:
        pdf_path: Path to PDF file.
        work_dir: Temp directory for artifacts (tree.json written here).
        run_docling: Whether to run Docling content extraction.
        window_size: Docling batch size in pages.
        window_overlap: Docling page overlap between batches.
        extract_images: Whether to extract embedded images from PDF pages.
        min_image_px: Minimum image width and height in pixels (filters tiny decoration).
        include_back_matter: Whether Bibliography/References/Appendix/Index
            entries are kept in the main hierarchy (see toc_classification.py).
            Default False — they're set aside in excluded_toc_entries instead.
        logger: Optional logger. Defaults to module logger.
        on_window_complete: Callback(window_idx, total, elapsed_s) per Docling window.

    Returns:
        PipelineResult with all outputs for UI inspection.
    """
    if logger is None:
        logger = logging.getLogger("pdf_tree.pipeline")

    t0 = time.perf_counter()
    stage_times: dict[str, float] = {}

    def _lap(name: str, ts: float) -> float:
        elapsed = time.perf_counter() - ts
        stage_times[name] = round(elapsed, 4)
        logger.info("%-25s %.3fs", name, elapsed)
        return time.perf_counter()

    try:
        # ── Step 1: fitz ──────────────────────────────────────────────────────
        ts = time.perf_counter()
        bookmarks = get_embedded_toc(pdf_path)
        n_pages = page_count(pdf_path)
        logger.info("fitz: %d bookmarks, %d pages", len(bookmarks), n_pages)
        ts = _lap("fitz", ts)

        # ── Step 2: bookmark sanity ───────────────────────────────────────────
        sanity = check_bookmark_sanity(bookmarks, n_pages)
        if sanity.has_hard_failures:
            repaired, repairs = repair_bookmarks(
                bookmarks, n_pages, page_text_reader(pdf_path)
            )
            if repairs:
                original_issues = sanity.issues
                sanity = check_bookmark_sanity(repaired, n_pages)
                sanity.repairs = repairs
                sanity.original_issues = original_issues
                bookmarks = repaired
                for repair in repairs:
                    logger.warning("bookmark_sanity repair [%s]: %s", repair.kind, repair.detail)
        if sanity.has_hard_failures:
            logger.error(
                "bookmark_sanity: %d hard failures — aborting",
                sum(1 for i in sanity.issues if i.kind == "out_of_order"),
            )
            return PipelineResult(
                sections=[],
                bookmarks=bookmarks,
                structural_source="toc",
                sanity_report=sanity,
                total_pages=n_pages,
                fitz_authoritative=bool(bookmarks),
                docling_doc=None,
                validation=None,
                elapsed_s=time.perf_counter() - t0,
                stage_times=stage_times,
                error="Bookmark sanity check failed: out-of-order bookmarks detected",
            )
        ts = _lap("bookmark_sanity", ts)

        # ── Step 3: Docling extraction (optional) ─────────────────────────────
        doc: DoclingDocument | None = None
        if run_docling:
            try:
                from src.tree_builder.docling_extract import DoclingExtractionEngine
                engine = DoclingExtractionEngine()
                if engine.is_available:
                    doc = engine.extract(
                        pdf_path,
                        logger,
                        window_size=window_size,
                        window_overlap=window_overlap,
                        on_window_complete=on_window_complete,
                    )
                    logger.info(
                        "docling: %d blocks, %d tables, %d pages",
                        len(doc.text_blocks),
                        len(doc.tables),
                        len(doc.pages),
                    )
                else:
                    logger.warning("docling: not installed — skipping")
            except Exception as exc:
                logger.warning("docling: extraction failed — %s", exc)
        ts = _lap("docling_extract", ts)

        if doc is None:
            doc = DoclingDocument(
                document_id="empty",
                source_path=str(pdf_path),
                total_pages=n_pages,
            )

        # ── Step 4: TOC path ──────────────────────────────────────────────────
        fitz_authoritative = bool(bookmarks)
        structural_source = "toc"

        if not bookmarks:
            # Synthetic TOC fallback from Docling section_headers
            bookmarks = synthesize_toc(doc)
            structural_source = "inferred"
            logger.info("synthetic_toc: %d headers", len(bookmarks))
            if not bookmarks:
                return PipelineResult(
                    sections=[],
                    bookmarks=[],
                    structural_source=structural_source,
                    sanity_report=sanity,
                    total_pages=n_pages,
                    fitz_authoritative=False,
                    docling_doc=doc if doc.total_pages > 0 else None,
                    validation=None,
                    elapsed_s=time.perf_counter() - t0,
                    stage_times=stage_times,
                    error=(
                        "No embedded bookmarks and Docling found no section headers. "
                        "Cannot build tree structure."
                    ),
                )
        ts = _lap("toc_path", ts)

        # ── Step 5: TOC classification ────────────────────────────────────────
        # Drop front-matter noise (Abstract, List of Figures, ...) and set
        # aside back-matter (Bibliography, Appendix, ...) BEFORE toc_resolution
        # runs its offset calibration — noise entries are often among the
        # first few bookmarks, exactly where calibration samples from.
        raw_toc_size = len(bookmarks)
        content_bookmarks, excluded_toc_entries = filter_toc_entries(
            bookmarks, include_back_matter=include_back_matter
        )
        if excluded_toc_entries:
            logger.info(
                "toc_classification: %d/%d bookmarks excluded (%s)",
                len(excluded_toc_entries), len(bookmarks),
                ", ".join(sorted({e.reason for e in excluded_toc_entries})),
            )
        # fitz/synthetic_toc bookmarks are always int-paged at this point in
        # the pipeline — filter_toc_entries's int|str page type exists for
        # future non-fitz TOC sources (VLM/LLM), not this call site.
        bookmarks = content_bookmarks  # type: ignore[assignment]
        if not bookmarks:
            return PipelineResult(
                sections=[],
                bookmarks=[],
                structural_source=structural_source,
                sanity_report=sanity,
                total_pages=n_pages,
                fitz_authoritative=fitz_authoritative,
                docling_doc=doc if doc.total_pages > 0 else None,
                validation=None,
                elapsed_s=time.perf_counter() - t0,
                stage_times=stage_times,
                excluded_toc_entries=excluded_toc_entries,
                error=(
                    "All TOC entries were classified as front/back matter noise. "
                    "Cannot build tree structure."
                ),
            )
        ts = _lap("toc_classification", ts)

        # ── Step 6: TOC resolution ────────────────────────────────────────────
        # Resolve claimed TOC pages (arabic/roman/alphanumeric) to physical
        # pages via offset calibration, then replace `bookmarks` with the
        # resolved pages — every downstream step (section ranges, validation,
        # image mapping) must build against the corrected pages, not the
        # claimed ones, or a "recovered" bookmark would still build a
        # misplaced section.
        resolved, numbering_report = resolve_toc_pages(bookmarks, doc)
        bookmarks = [(r.level, r.title, r.resolved_page) for r in resolved]
        verifications = [r.verification for r in resolved]
        numbering_schemes = [r.numbering_scheme for r in resolved]
        offsets_applied = [r.offset_applied for r in resolved]

        n_flagged = sum(1 for v in verifications if not v.passed)
        logger.info(
            "toc_resolution: scheme=%s global_offset=%d (match_rate=%.2f, accepted=%s) "
            "%d/%d bookmarks flagged_for_review",
            numbering_report.numbering_scheme, numbering_report.global_offset,
            numbering_report.global_match_rate, numbering_report.global_accepted,
            n_flagged, len(verifications),
        )
        if numbering_report.flagged_for_manual_review:
            logger.warning(
                "toc_resolution: no offset (global or per-cluster) cleared the match-rate "
                "threshold — document flagged for manual review"
            )
        ts = _lap("toc_resolution", ts)

        # ── Step 7: section matcher ───────────────────────────────────────────
        entries, boundaries = _with_excluded_boundaries(
            bookmarks, excluded_toc_entries, raw_toc_size
        )
        index_page = find_unbookmarked_index(doc, after_page=max(p for _, _, p in entries))
        if index_page is not None:
            logger.info("section_matcher: unbookmarked index from page %d", index_page)
            entries.append((min(level for level, _, _ in entries), "Index", index_page))
            boundaries.append(True)
        matched: list[MatchedSection] = match_content_to_sections(
            entries, doc, n_pages,
            verifications=verifications,
            numbering_schemes=numbering_schemes,
            offsets_applied=offsets_applied,
            boundaries=boundaries,
        )
        logger.info("section_matcher: %d sections", len(matched))
        ts = _lap("section_matcher", ts)

        # ── Step 8: tree export ───────────────────────────────────────────────
        sections = build_tree_json(matched, structural_source=structural_source)
        _flag_relocated_sections(sections, sanity)
        logger.info("tree_export: %d sections", len(sections))
        ts = _lap("tree_export", ts)

        # ── Step 9: validation ────────────────────────────────────────────────
        # Write tree.json temporarily for validator
        tree_json_path = work_dir / "tree.json"
        tree_json_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(tree_json_path, "w") as f:
            json.dump(sections, f, indent=2, ensure_ascii=False)

        # Blocks on pages no section covers (cover, the manual's own TOC, an excluded
        # Index) are correctly outside the tree, not coverage gaps.
        covered = {p for s in matched for p in range(s.page_start, s.page_end + 1)}
        expected_front_matter = (
            sum(1 for b in doc.text_blocks if b.page_no not in covered)
            + sum(1 for t in doc.tables if t.page_no not in covered)
        ) if doc else 0
        total_blocks = len(doc.text_blocks) + len(doc.tables) if doc else 0
        validation = validate_tree(
            tree_json_path=tree_json_path,
            bookmarks=bookmarks,
            total_docling_blocks=total_blocks,
            pdf_name=pdf_path.name,
            page_tolerance=1,
            expected_front_matter=expected_front_matter,
        )
        logger.info("validation: %s", validation.status)
        _lap("validation", ts)

        # ── Step 10: image extraction (optional) ───────────────────────────────
        images: list[EmbeddedImage] = []
        if extract_images:
            try:
                images = _extract_embedded_images(pdf_path, n_pages, min_image_px, logger)
                images += _extract_vector_figures(pdf_path, n_pages, doc, logger)
                images = _map_images_to_sections(images, sections)
                logger.info("images: %d extracted", len(images))
            except Exception as exc:
                logger.warning("image extraction failed — %s", exc)
        _lap("image_extraction", time.perf_counter())

        return PipelineResult(
            sections=sections,
            bookmarks=bookmarks,
            structural_source=structural_source,
            sanity_report=sanity,
            total_pages=n_pages,
            fitz_authoritative=fitz_authoritative,
            docling_doc=doc,
            validation=validation,
            elapsed_s=time.perf_counter() - t0,
            stage_times=stage_times,
            numbering_report=numbering_report,
            excluded_toc_entries=excluded_toc_entries,
            images=images,
        )

    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        return PipelineResult(
            sections=[],
            bookmarks=[],
            structural_source="toc",
            sanity_report=BookmarkSanityReport(),
            total_pages=0,
            fitz_authoritative=False,
            docling_doc=None,
            validation=None,
            elapsed_s=time.perf_counter() - t0,
            stage_times=stage_times,
            error=str(exc),
        )


def _extract_embedded_images(
    pdf_path: Path,
    n_pages: int,
    min_image_px: int,
    logger: logging.Logger,
) -> list[EmbeddedImage]:
    import io
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore[no-reattr]
    try:
        from PIL import Image
        _pil_available = True
    except ImportError:
        _pil_available = False

    _MIN_PX        = min_image_px           # UI icons of 48-80 px are content (BUG-017)
    _MIN_AREA_FRAC = 0.003                  # bbox must cover ≥0.3% of page area (BUG-020)
    _HEADER_FRAC   = 0.05                   # skip images fully in top 5%
    _FOOTER_FRAC   = 0.95                   # skip images fully in bottom 5%
    # Ultra-wide/tall strips are rules and nav bars when repeated or tiny; a unique strip
    # covering 1%+ of the page is a thin screenshot (LOGIQ_S8 p679, 231x79 px).
    _MAX_ASPECT    = 15.0
    _STRIP_MIN_AREA_FRAC = 0.01
    _STRIP_MIN_PX  = 20                     # a unique strip may be under _MIN_PX (35 px high)
    # An image shown on many pages in the top/bottom 10% band is page decoration (BUG-004:
    # DOC's footer divider on 210 pages). A repeated key picture or icon inside the page
    # body is content (SOMATOM's Move key on 8 pages).
    _REPEAT_PAGES  = 5
    _REPEAT_BAND   = 0.10

    result: list[EmbeddedImage] = []
    doc = fitz.open(str(pdf_path))
    pages_of: dict[int, set[int]] = {}
    for page_no in range(1, n_pages + 1):
        for img_info in doc[page_no - 1].get_images(full=True):
            pages_of.setdefault(img_info[0], set()).add(page_no)

    for page_no in range(1, n_pages + 1):
        page = doc[page_no - 1]
        page_h    = page.rect.height
        page_area = page.rect.width * page_h
        header_cut = page_h * _HEADER_FRAC
        footer_cut = page_h * _FOOTER_FRAC

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue

            w = base_image.get("width", 0)
            h = base_image.get("height", 0)

            strip = max(w, h) / max(min(w, h), 1) > _MAX_ASPECT
            small = w < _MIN_PX or h < _MIN_PX
            if small and not strip:
                continue  # filter 1: pixel dimensions (no rect lookup for tiny images)
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            bbox = rects[0] if rects else None
            # filter 5: aspect ratio. A strip is a rule or nav bar unless it is shown once
            # and covers 1%+ of the page: then it is a thin screenshot (LOGIQ_e p274, p417).
            unique_strip = (
                strip
                and bbox is not None
                and len(pages_of.get(xref, ())) == 1
                and page_area > 0
                and (bbox.width * bbox.height) / page_area >= _STRIP_MIN_AREA_FRAC
                and min(w, h) >= _STRIP_MIN_PX
            )
            if strip and not unique_strip:
                continue
            if small and not unique_strip:
                continue  # filter 1: a strip under the pixel floor must be a unique screenshot

            # filters 2-4, 6: page-coordinate bbox checks
            if bbox is not None:
                # filter 2: area fraction
                if page_area > 0 and (bbox.width * bbox.height) / page_area < _MIN_AREA_FRAC:
                    continue
                # filters 3-4: header / footer zone
                if bbox.y1 <= header_cut or bbox.y0 >= footer_cut:
                    continue
                # filter 6: repeated decoration in the top/bottom band
                if len(pages_of.get(xref, ())) >= _REPEAT_PAGES and (
                    bbox.y1 <= page_h * _REPEAT_BAND
                    or bbox.y0 >= page_h * (1 - _REPEAT_BAND)
                ):
                    continue

            raw_bytes = base_image.get("image")
            img_ext   = base_image.get("ext", "")
            if not raw_bytes:
                continue

            if img_ext.lower() == "png":
                png_bytes = raw_bytes
            elif _pil_available:
                try:
                    pil_img   = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                    buf       = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    png_bytes = buf.getvalue()
                except Exception:
                    continue
            else:
                continue

            result.append(EmbeddedImage(
                image_bytes=png_bytes,
                page_no=page_no,
                width_px=w,
                height_px=h,
                bbox=None if bbox is None else BoundingBox(
                    x0=bbox.x0,
                    y0=page_h - bbox.y0,
                    x1=bbox.x1,
                    y1=page_h - bbox.y1,
                    page_no=page_no,
                    coordinate_origin="bottomleft",
                ),
            ))

    doc.close()
    logger.debug("_extract_embedded_images: %d after heuristic filtering", len(result))
    return result
