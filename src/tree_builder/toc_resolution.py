"""
TOC resolution — turn raw claimed TOC pages (arabic, roman, or alphanumeric/
section-relative) into concrete physical page numbers the rest of the
pipeline can use, with an auditable record of how each one got there.

Ties together:
  - page_numbering: scheme detection + roman/alphanumeric normalization
  - title_verification: fuzzy title-vs-text checking + offset calibration

Strategy:
  1. Classify + normalize every claimed page into one sequential index space
     (roman + arabic). Alphanumeric/section-relative codes are grouped into
     clusters by prefix instead (e.g. "A-1", "A-2" -> cluster "A").
  2. Try one global offset first (cheap, works for the common case).
  3. If the global offset doesn't clear min_match_rate, fall back to
     per-chapter / per-cluster offsets — each chapter or alphanumeric cluster
     gets calibrated independently, so a reset/non-uniform numbering scheme
     can still be resolved locally even when no single global offset fits.
  4. Anything that still doesn't clear the bar is NOT guessed at — it keeps
     its original claimed page (never dropped) and is flagged for review.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from src.models.extraction import DoclingDocument
from src.tree_builder.page_numbering import (
    classify_page_token,
    detect_numbering_scheme,
    normalize_page_sequence,
)
from src.tree_builder.title_verification import (
    DEFAULT_CALIBRATION_SAMPLE,
    DEFAULT_MIN_MATCH_RATE,
    DEFAULT_OFFSET_RANGE,
    DEFAULT_PAGE_WINDOW,
    DEFAULT_SCORE_THRESHOLD,
    TitleVerification,
    calibrate_and_check,
    score_titles_at_pages,
)

DEFAULT_MIN_CLUSTER_SIZE = 2


@dataclass
class ClusterOffset:
    """Offset calibration outcome for one chapter/alphanumeric cluster."""

    cluster_id: str
    bookmark_indices: list[int]
    offset: int
    match_rate: float
    accepted: bool


@dataclass
class NumberingReport:
    """
    Document-level traceability record — what numbering scheme this TOC used,
    what offset(s) were applied, and how confident the resolution is.
    Inspectable after the fact, not just an internal calculation.
    """

    numbering_scheme: str
    global_offset: int
    global_match_rate: float
    global_accepted: bool
    clusters: list[ClusterOffset] = field(default_factory=list)
    flagged_for_manual_review: bool = False


@dataclass
class ResolvedBookmark:
    """One TOC entry resolved to a concrete physical page, with provenance."""

    level: int
    title: str
    claimed_page: int | str
    resolved_page: int
    numbering_scheme: str
    offset_applied: int
    verification: TitleVerification


def _chapter_clusters(bookmarks: Sequence[tuple[int, str, int | str]]) -> dict[str, list[int]]:
    """Group bookmark indices by their nearest preceding level==1 ancestor (chapter)."""
    clusters: dict[str, list[int]] = {}
    current = "_preamble"
    for i, (level, _title, _page) in enumerate(bookmarks):
        if level == 1:
            current = f"chapter_{i}"
        clusters.setdefault(current, []).append(i)
    return clusters


def _alphanumeric_clusters(bookmarks: Sequence[tuple[int, str, int | str]]) -> dict[str, list[int]]:
    """Group bookmark indices by their alphanumeric page-code prefix (e.g. "A-1" -> "A")."""
    clusters: dict[str, list[int]] = {}
    for i, (_level, _title, page) in enumerate(bookmarks):
        token = classify_page_token(page)
        if token.scheme == "alphanumeric" and token.cluster_key is not None:
            clusters.setdefault(f"alnum_{token.cluster_key}", []).append(i)
    return clusters


def resolve_toc_pages(
    bookmarks: Sequence[tuple[int, str, int | str]],
    doc: DoclingDocument,
    *,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    page_window: int = DEFAULT_PAGE_WINDOW,
    offset_range: tuple[int, int] = DEFAULT_OFFSET_RANGE,
    calibration_sample_size: int = DEFAULT_CALIBRATION_SAMPLE,
    min_match_rate: float = DEFAULT_MIN_MATCH_RATE,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
) -> tuple[list[ResolvedBookmark], NumberingReport]:
    """
    Resolve raw claimed TOC pages to concrete physical pages + a traceability
    report. Never drops an entry — unresolved ones keep their claimed page,
    flagged for review, rather than being silently guessed at.
    """
    if not bookmarks:
        return [], NumberingReport(
            numbering_scheme="unknown", global_offset=0, global_match_rate=0.0,
            global_accepted=False,
        )

    raw_pages = [p for _l, _t, p in bookmarks]
    scheme = detect_numbering_scheme(raw_pages)
    normalized = normalize_page_sequence(raw_pages)
    tokens = [classify_page_token(p) for p in raw_pages]

    # Homogeneous int-paged bookmarks for calibration:
    #   - roman/arabic: the normalized global sequential index
    #   - alphanumeric: its local (within-cluster) index, e.g. "A-3" -> 3 —
    #     meaningless globally, but exactly what per-cluster calibration
    #     below needs to find that cluster's own offset
    #   - anything else unresolvable: claimed page as-is, else 0
    base_pages: list[int] = []
    for (_level, _title, raw_page), norm, token in zip(bookmarks, normalized, tokens, strict=True):
        if norm is not None:
            base_pages.append(norm)
        elif token.value is not None:
            base_pages.append(token.value)
        elif isinstance(raw_page, int):
            base_pages.append(raw_page)
        else:
            base_pages.append(0)
    int_bookmarks: list[tuple[int, str, int]] = [
        (level, title, base_pages[i]) for i, (level, title, _page) in enumerate(bookmarks)
    ]

    global_calibration = calibrate_and_check(
        int_bookmarks, doc,
        offset_range=offset_range,
        sample_size=calibration_sample_size,
        score_threshold=score_threshold,
        min_match_rate=min_match_rate,
    )

    report = NumberingReport(
        numbering_scheme=scheme,
        global_offset=global_calibration.offset,
        global_match_rate=global_calibration.match_rate,
        global_accepted=global_calibration.accepted,
    )

    offset_by_index: dict[int, int] = {}
    if global_calibration.accepted:
        offset_by_index = dict.fromkeys(range(len(bookmarks)), global_calibration.offset)
    else:
        # Global offset didn't clear the bar — try per-chapter and
        # per-alphanumeric-cluster offsets before giving up on any of them.
        candidate_clusters = _chapter_clusters(bookmarks)
        candidate_clusters.update(_alphanumeric_clusters(bookmarks))

        for cluster_id, indices in candidate_clusters.items():
            if len(indices) < min_cluster_size:
                continue
            cluster_bookmarks = [int_bookmarks[i] for i in indices]
            calib = calibrate_and_check(
                cluster_bookmarks, doc,
                offset_range=offset_range,
                sample_size=min(calibration_sample_size, len(cluster_bookmarks)),
                score_threshold=score_threshold,
                min_match_rate=min_match_rate,
            )
            report.clusters.append(ClusterOffset(
                cluster_id=cluster_id,
                bookmark_indices=indices,
                offset=calib.offset,
                match_rate=calib.match_rate,
                accepted=calib.accepted,
            ))
            if calib.accepted:
                for i in indices:
                    offset_by_index[i] = calib.offset

    # Anything covered by neither an accepted global nor cluster offset falls
    # back to +0 — score_titles_at_pages below will catch and flag it rather
    # than let a bad guess through silently.
    for i in range(len(bookmarks)):
        offset_by_index.setdefault(i, 0)

    report.flagged_for_manual_review = (
        not global_calibration.accepted and not any(c.accepted for c in report.clusters)
    )

    resolved_pages: list[int] = [base_pages[i] + offset_by_index[i] for i in range(len(bookmarks))]
    scored_bookmarks = [
        (bookmarks[i][0], bookmarks[i][1], resolved_pages[i]) for i in range(len(bookmarks))
    ]
    verifications = score_titles_at_pages(
        scored_bookmarks, doc, score_threshold=score_threshold, page_window=page_window
    )

    resolved: list[ResolvedBookmark] = []
    for i, (level, title, _page) in enumerate(bookmarks):
        resolved.append(
            ResolvedBookmark(
                level=level,
                title=title,
                claimed_page=bookmarks[i][2],
                resolved_page=resolved_pages[i],
                numbering_scheme=tokens[i].scheme,
                offset_applied=offset_by_index[i],
                verification=verifications[i],
            )
        )

    return resolved, report
