"""Tests for toc_classification — front/back-matter pattern classification + filtering."""
from __future__ import annotations

import pytest

from src.tree_builder.toc_classification import classify_toc_title, filter_toc_entries


@pytest.mark.parametrize("title", [
    "Abstract",
    "Resumen",
    "List of Figures",
    "Índice de Figuras",
    "List of Tables",
    "Índice de Tablas",
    "Notation",
    "Notación",
    "Glossary",
    "Glosario",
    "Nomenclature",
    "Nomenclatura",
    "Contents",
    "Table of Contents",
    "Índice",
])
def test_front_matter_noise_detected_english_and_spanish(title: str) -> None:
    result = classify_toc_title(title)
    assert result.category == "front_matter_noise"
    assert result.reason


@pytest.mark.parametrize("title", [
    "Bibliography",
    "Bibliografía",
    "References",
    "Referencias",
    "Appendix A",
    "Apéndice B",
    "Anexo 1",
    "Index",
    "Índice Alfabético",
])
def test_back_matter_detected_english_and_spanish(title: str) -> None:
    result = classify_toc_title(title)
    assert result.category == "back_matter"
    assert result.reason


@pytest.mark.parametrize("title", [
    "Introduction to Signal Processing",
    "Summary of Findings",
    "Resumen Ejecutivo",
    "The Index of Refraction in Optical Fibers",
    "Appendicitis: A Clinical Review",
    "Notation Conventions in Category Theory",
])
def test_legitimate_content_sharing_noise_vocabulary_is_not_excluded(title: str) -> None:
    """A real chapter that happens to share a word with a noise pattern must
    stay content_section — matching is whole-title, not fuzzy substring."""
    result = classify_toc_title(title)
    assert result.category == "content_section"


@pytest.mark.parametrize("title,expected_note", [
    ("Acknowledgments", "acknowledgments"),
    ("Acknowledgements", "acknowledgments"),
    ("Agradecimientos", "acknowledgments"),
    ("Preface", "preface"),
    ("Prefacio", "preface"),
    ("Foreword", "foreword"),
    ("Prólogo", "foreword"),
])
def test_judgment_call_entries_kept_as_content_but_flagged(title: str, expected_note: str) -> None:
    """Acknowledgments/Preface/Foreword are never hard-excluded — kept as
    content_section, just annotated for a human/downstream judgment call."""
    result = classify_toc_title(title)
    assert result.category == "content_section"
    assert result.judgment_note == expected_note


def test_case_and_whitespace_normalization() -> None:
    assert classify_toc_title("  ABSTRACT  ").category == "front_matter_noise"
    assert classify_toc_title("list   of\tfigures").category == "front_matter_noise"


def test_filter_toc_entries_excludes_front_matter_and_back_matter_by_default() -> None:
    bookmarks: list[tuple[int, str, int | str]] = [
        (1, "Abstract", 1),
        (1, "Chapter One", 3),
        (1, "Chapter Two", 10),
        (1, "Bibliography", 20),
    ]

    kept, excluded = filter_toc_entries(bookmarks)

    assert [b[1] for b in kept] == ["Chapter One", "Chapter Two"]
    excluded_by_title = {e.title: e for e in excluded}
    assert excluded_by_title["Abstract"].category == "front_matter_noise"
    assert excluded_by_title["Bibliography"].category == "back_matter"


def test_back_matter_is_tagged_not_discarded() -> None:
    """Back-matter entries are set aside, not lost — full entry + reason preserved."""
    bookmarks: list[tuple[int, str, int | str]] = [
        (1, "Chapter One", 1),
        (1, "Appendix A", 50),
    ]

    kept, excluded = filter_toc_entries(bookmarks)

    assert len(kept) == 1
    assert len(excluded) == 1
    entry = excluded[0]
    assert entry.title == "Appendix A"
    assert entry.page == 50
    assert entry.category == "back_matter"
    assert entry.reason == "appendix"


def test_include_back_matter_flag_keeps_it_in_main_hierarchy() -> None:
    bookmarks: list[tuple[int, str, int | str]] = [
        (1, "Chapter One", 1),
        (1, "Appendix A", 50),
    ]

    kept, excluded = filter_toc_entries(bookmarks, include_back_matter=True)

    assert [b[1] for b in kept] == ["Chapter One", "Appendix A"]
    assert excluded == []


def test_mixed_language_toc_filters_both_english_and_spanish_noise() -> None:
    """A TOC mixing English and Spanish noise patterns (bilingual document,
    or a document where front matter was translated) must filter both."""
    bookmarks: list[tuple[int, str, int | str]] = [
        (1, "Abstract", 1),
        (1, "Resumen", 2),
        (1, "Introduction", 3),
        (1, "Índice de Tablas", 4),
        (1, "List of Figures", 5),
        (1, "Chapter One", 6),
        (1, "Bibliografía", 20),
        (1, "References", 21),
    ]

    kept, excluded = filter_toc_entries(bookmarks)

    assert [b[1] for b in kept] == ["Introduction", "Chapter One"]
    excluded_titles = {e.title for e in excluded}
    assert excluded_titles == {
        "Abstract", "Resumen", "Índice de Tablas", "List of Figures",
        "Bibliografía", "References",
    }
