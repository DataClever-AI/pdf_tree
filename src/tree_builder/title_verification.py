"""
Title verification — confirm a candidate bookmark title actually appears in
extracted text at (or near) its claimed page, BEFORE it's trusted as a
structural boundary (PageIndex-style verification).

Deterministic and cheap: rapidfuzz fuzzy matching against a small window of
text near the claimed page. No LLM call — must stay cheap enough to run on
every candidate header at scale.

Failing bookmarks are never dropped here — callers (section_matcher) must
keep them, flagged for review, so a bad match doesn't silently erase content.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from src.models.extraction import DoclingDocument

DEFAULT_SCORE_THRESHOLD = 85.0
DEFAULT_PAGE_WINDOW = 1
DEFAULT_OFFSET_RANGE = (-5, 5)
DEFAULT_CALIBRATION_SAMPLE = 5
DEFAULT_MIN_MATCH_RATE = 0.6


@dataclass
class TitleVerification:
    """Verification outcome for one bookmark's claimed title/page."""

    bookmark_index: int
    title: str
    claimed_page: int
    verified_page: int | None  # page the best match was found on, if any
    score: float
    passed: bool
    offset_applied: int
    reason: str  # "" if passed


@dataclass
class CalibrationResult:
    """
    Outcome of testing candidate offsets against a bookmark sample.

    accepted=False means the best offset found still didn't clear
    min_match_rate — callers must NOT apply it blindly (that's a guess, not a
    calibration); they should fall back to a narrower cluster or flag for
    manual review instead.
    """

    offset: int
    match_rate: float  # fraction of the sample that passed score_threshold at `offset`
    accepted: bool


def _page_text_map(doc: DoclingDocument) -> dict[int, str]:
    """Concatenate all block text per page_no, for cheap substring/fuzzy search."""
    pages: dict[int, list[str]] = {}
    for block in doc.text_blocks:
        pages.setdefault(block.page_no, []).append(block.text)
    return {page: " ".join(texts) for page, texts in pages.items()}


def _best_score_near(
    title: str,
    page_texts: dict[int, str],
    page_no: int,
    page_window: int,
) -> tuple[float, int | None]:
    """Best fuzz.partial_ratio for `title` among pages [page_no-window, page_no+window]."""
    norm_title = title.strip().lower()
    if not norm_title:
        return 0.0, None

    best_score = 0.0
    best_page: int | None = None
    for page in range(page_no - page_window, page_no + page_window + 1):
        text = page_texts.get(page)
        if not text:
            continue
        score = fuzz.partial_ratio(norm_title, text.lower())
        if score > best_score:
            best_score = score
            best_page = page
    return best_score, best_page


def calibrate_page_offset(
    bookmarks: list[tuple[int, str, int]],
    doc: DoclingDocument,
    *,
    offset_range: tuple[int, int] = DEFAULT_OFFSET_RANGE,
    sample_size: int = DEFAULT_CALIBRATION_SAMPLE,
) -> int:
    """
    Test a small range of page-number offsets against the first few bookmarks
    and return the offset with the best aggregate match score.

    Handles a document-wide page-numbering mismatch (roman vs arabic
    front-matter, off-by-N cover pages) between the claimed TOC page and the
    extracted document's page numbers.
    """
    if not bookmarks:
        return 0

    page_texts = _page_text_map(doc)
    sample = bookmarks[:sample_size]
    low, high = offset_range

    best_offset = 0
    best_aggregate = -1.0
    for offset in range(low, high + 1):
        total = 0.0
        for _level, title, page_no in sample:
            score, _ = _best_score_near(title, page_texts, page_no + offset, page_window=0)
            total += score
        aggregate = total / len(sample)
        if aggregate > best_aggregate:
            best_aggregate = aggregate
            best_offset = offset

    return best_offset


def calibrate_and_check(
    bookmarks: list[tuple[int, str, int]],
    doc: DoclingDocument,
    *,
    offset_range: tuple[int, int] = DEFAULT_OFFSET_RANGE,
    sample_size: int = DEFAULT_CALIBRATION_SAMPLE,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    min_match_rate: float = DEFAULT_MIN_MATCH_RATE,
) -> CalibrationResult:
    """
    Calibrate an offset (see calibrate_page_offset) and check whether it's
    actually good enough to trust — i.e. whether at least min_match_rate of
    the sample bookmarks verify at that offset. If not, accepted=False: the
    caller must not apply this offset, only report it as an attempt.
    """
    if not bookmarks:
        return CalibrationResult(offset=0, match_rate=0.0, accepted=False)

    offset = calibrate_page_offset(
        bookmarks, doc, offset_range=offset_range, sample_size=sample_size
    )

    page_texts = _page_text_map(doc)
    sample = bookmarks[:sample_size]
    passes = 0
    for _level, title, page_no in sample:
        score, _ = _best_score_near(title, page_texts, page_no + offset, page_window=0)
        if score >= score_threshold:
            passes += 1
    match_rate = passes / len(sample)

    accepted = match_rate >= min_match_rate
    return CalibrationResult(offset=offset, match_rate=match_rate, accepted=accepted)


def score_titles_at_pages(
    bookmarks: list[tuple[int, str, int]],
    doc: DoclingDocument,
    *,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    page_window: int = DEFAULT_PAGE_WINDOW,
) -> list[TitleVerification]:
    """
    Score each bookmark's title against text at its page AS-IS — no offset
    calibration. For bookmarks whose page has already been resolved/corrected
    upstream (see toc_resolution.resolve_toc_pages), so offset_applied=0 here
    always means "no further correction was attempted at this step", not
    "no correction happened".
    """
    if not bookmarks:
        return []

    page_texts = _page_text_map(doc)
    results: list[TitleVerification] = []
    for i, (_level, title, page_no) in enumerate(bookmarks):
        score, matched_page = _best_score_near(title, page_texts, page_no, page_window)
        passed = score >= score_threshold
        reason = "" if passed else (
            f"best match score {score:.1f} below threshold {score_threshold} "
            f"(page={page_no}, window=±{page_window})"
        )
        results.append(
            TitleVerification(
                bookmark_index=i,
                title=title,
                claimed_page=page_no,
                verified_page=matched_page,
                score=score,
                passed=passed,
                offset_applied=0,
                reason=reason,
            )
        )
    return results


def verify_titles(
    bookmarks: list[tuple[int, str, int]],
    doc: DoclingDocument,
    *,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    page_window: int = DEFAULT_PAGE_WINDOW,
    offset_range: tuple[int, int] = DEFAULT_OFFSET_RANGE,
    calibration_sample_size: int = DEFAULT_CALIBRATION_SAMPLE,
) -> list[TitleVerification]:
    """
    Verify each bookmark's title actually appears in extracted text at (or
    near) its claimed page, before it's trusted as a structural boundary.

    Runs an automatic offset calibration pass first (see calibrate_page_offset),
    then checks every bookmark against its (possibly offset-corrected) page,
    ± page_window pages.

    Returns one TitleVerification per bookmark, same order as input — callers
    must not drop failing entries, only flag them.
    """
    if not bookmarks:
        return []

    if not doc.text_blocks:
        return [
            TitleVerification(
                bookmark_index=i,
                title=title,
                claimed_page=page_no,
                verified_page=None,
                score=0.0,
                passed=False,
                offset_applied=0,
                reason="no extracted text available to verify against",
            )
            for i, (_level, title, page_no) in enumerate(bookmarks)
        ]

    page_texts = _page_text_map(doc)
    offset = calibrate_page_offset(
        bookmarks, doc, offset_range=offset_range, sample_size=calibration_sample_size
    )

    results: list[TitleVerification] = []
    for i, (_level, title, page_no) in enumerate(bookmarks):
        target_page = page_no + offset
        score, matched_page = _best_score_near(title, page_texts, target_page, page_window)
        passed = score >= score_threshold
        reason = "" if passed else (
            f"best match score {score:.1f} below threshold {score_threshold} "
            f"(claimed_page={page_no}, offset_applied={offset}, window=±{page_window})"
        )
        results.append(
            TitleVerification(
                bookmark_index=i,
                title=title,
                claimed_page=page_no,
                verified_page=matched_page,
                score=score,
                passed=passed,
                offset_applied=offset,
                reason=reason,
            )
        )
    return results
