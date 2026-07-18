"""
TOC entry classification — identify raw TOC entries that aren't real content
sections (front-matter noise like "Abstract"/"List of Figures", back-matter
like "Bibliography"/"Appendix") before they're treated as hierarchy nodes.

Deterministic, pattern-based — no LLM call, cheap enough to run on every TOC
entry at scale. Patterns are grouped by category and language in
_FRONT_MATTER_PATTERNS / _BACK_MATTER_PATTERNS / _JUDGMENT_PATTERNS below —
add a new language or category there, not inline in the matching logic.

Matching is anchored against the whole (normalized) title, not a fuzzy
substring search — a chapter titled "Introduction to Signal Processing"
must never be excluded just because some unrelated noise pattern shares a
word with it.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

TocCategory = Literal["content_section", "front_matter_noise", "back_matter"]

# Front matter: preamble content that isn't a real section — abstract,
# notation, lists of figures/tables, self-referential "table of contents",
# glossary/nomenclature. Excluded from the hierarchy by default.
_FRONT_MATTER_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("abstract", r"^abstract$"),
        ("summary", r"^summary$"),
        ("table_of_contents", r"^(table of )?contents$"),
        ("list_of_figures", r"^list of figures$"),
        ("list_of_tables", r"^list of tables$"),
        ("notation", r"^notation$"),
        ("list_of_symbols", r"^(list of )?symbols$"),
        ("glossary", r"^glossary$"),
        ("nomenclature", r"^nomenclature$"),
    ],
    "es": [
        ("abstract", r"^resumen$"),
        ("table_of_contents", r"^[ií]ndice$"),
        ("list_of_figures", r"^[ií]ndice de figuras$"),
        ("list_of_tables", r"^[ií]ndice de tablas$"),
        ("notation", r"^notaci[oó]n$"),
        ("list_of_symbols", r"^(lista de )?s[ií]mbolos$"),
        ("glossary", r"^glosario$"),
        ("nomenclature", r"^nomenclatura$"),
    ],
}

# Back matter: structurally valid sections, but not "main body" content —
# tagged distinctly, not discarded (see filter_toc_entries's
# include_back_matter). Appendix/bibliography/references commonly carry a
# trailing label ("Appendix A", "References [1-20]"), so these are
# prefix-anchored (still anchored at the START, so a title merely containing
# the word mid-phrase is never caught) rather than exact.
_BACK_MATTER_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("bibliography", r"^bibliography\b"),
        ("references", r"^references\b"),
        ("index", r"^index$"),
        ("appendix", r"^appendix\b"),
    ],
    "es": [
        ("bibliography", r"^bibliograf[ií]a\b"),
        ("references", r"^referencias\b"),
        ("index", r"^[ií]ndice (alfab[eé]tico|anal[ií]tico|onom[aá]stico)$"),
        ("appendix", r"^(ap[eé]ndice|anexo)\b"),
    ],
}

# Judgment-call entries (see module docstring's problem context): legitimate
# content in some document types, front matter in others. Never hard-excluded
# — kept as content_section, just annotated with `judgment_note` so a caller
# can decide.
_JUDGMENT_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("acknowledgments", r"^acknowledge?ments$"),
        ("preface", r"^preface$"),
        ("foreword", r"^foreword$"),
    ],
    "es": [
        ("acknowledgments", r"^agradecimientos$"),
        ("preface", r"^prefacio$"),
        ("foreword", r"^pr[oó]logo$"),
    ],
}


def _compile_patterns(
    patterns_by_language: dict[str, list[tuple[str, str]]],
) -> list[tuple[str, re.Pattern[str]]]:
    """Flatten + precompile a {language: [(reason, pattern), ...]} config once at import time."""
    return [
        (reason, re.compile(pattern, re.IGNORECASE))
        for patterns in patterns_by_language.values()
        for reason, pattern in patterns
    ]


_COMPILED_FRONT_MATTER = _compile_patterns(_FRONT_MATTER_PATTERNS)
_COMPILED_BACK_MATTER = _compile_patterns(_BACK_MATTER_PATTERNS)
_COMPILED_JUDGMENT = _compile_patterns(_JUDGMENT_PATTERNS)


@dataclass
class TocClassification:
    """Classification outcome for one raw TOC entry's title."""

    category: TocCategory
    # fine-grained pattern id (e.g. "abstract", "appendix"); "" for plain content_section
    reason: str
    # set for acknowledgments/preface/foreword — see module docstring
    judgment_note: str | None = None


def _normalize_title(title: str) -> str:
    """Case-insensitive, whitespace-normalized form used for pattern matching."""
    return " ".join(title.strip().lower().split())


def classify_toc_title(title: str) -> TocClassification:
    """Classify a raw TOC entry's title as content_section, front_matter_noise, or back_matter."""
    normalized = _normalize_title(title)
    if not normalized:
        return TocClassification(category="content_section", reason="")

    for reason, pattern in _COMPILED_FRONT_MATTER:
        if pattern.match(normalized):
            return TocClassification(category="front_matter_noise", reason=reason)

    for reason, pattern in _COMPILED_BACK_MATTER:
        if pattern.match(normalized):
            return TocClassification(category="back_matter", reason=reason)

    for reason, pattern in _COMPILED_JUDGMENT:
        if pattern.match(normalized):
            return TocClassification(category="content_section", reason="", judgment_note=reason)

    return TocClassification(category="content_section", reason="")


@dataclass
class ExcludedTocEntry:
    """A raw TOC entry excluded from the main hierarchy — never dropped, just set aside."""

    level: int
    title: str
    page: int | str
    category: TocCategory  # "front_matter_noise" | "back_matter"
    reason: str


def filter_toc_entries(
    bookmarks: Sequence[tuple[int, str, int | str]],
    *,
    include_back_matter: bool = False,
) -> tuple[list[tuple[int, str, int | str]], list[ExcludedTocEntry]]:
    """
    Split raw TOC entries into (kept, excluded) via classify_toc_title.

    front_matter_noise is always excluded from the main hierarchy.
    back_matter (bibliography/references/index/appendix) is excluded by
    default too, unless include_back_matter=True — either way every excluded
    entry is returned in `excluded`, never silently dropped.
    """
    kept: list[tuple[int, str, int | str]] = []
    excluded: list[ExcludedTocEntry] = []

    for level, title, page in bookmarks:
        classification = classify_toc_title(title)

        if classification.category == "front_matter_noise":
            excluded.append(
                ExcludedTocEntry(level, title, page, "front_matter_noise", classification.reason)
            )
            continue

        if classification.category == "back_matter" and not include_back_matter:
            excluded.append(
                ExcludedTocEntry(level, title, page, "back_matter", classification.reason)
            )
            continue

        kept.append((level, title, page))

    return kept, excluded
