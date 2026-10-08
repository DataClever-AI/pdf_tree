"""Recover printed table lines that Docling left out of every cell (BUG-030).

TableFormer can drop a row in the middle of a table (Philips p443 'Gain 2.0, ...'), a
full-width footnote row (DOC p178 '* These latching faults ...') or a legend row (LOGIQ_e p36
'Note: X: Support ...'). The words are in the PDF text layer, inside the table box, but in
no cell and in no other Docling item. This step works on the merged Docling dict, before the
cells are rendered to text: each missing line goes into the cell of the row and column it is
printed in, or into a new row at its height when no row is there.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import pairwise
from typing import Any

from src.tree_builder.fitz_toc import Word

_MIN_LOST_CHARS = 6  # letters and digits; shorter pieces are too often split subscripts or signs
_PHRASE_GAP = 0.8  # a horizontal gap wider than this x word height splits a line into phrases
_COLUMN_GAP = 2.0  # x the line's usual word space: a gap this wide at a column border splits
_ROW_TOLERANCE = 2.0  # pt a line may stick out of a row band and still belong to that row
_NEW_ROW_GAP = 1.5  # x line height: lines closer than this to the previous lost line join its row
_MIN_AGREEMENT = 0.5  # share of the cell words that must be printed inside the table box
_ROW_MISSING_SHARE = 0.5  # share of a line's words missing from its row's cells to be lost
_KEPT_SHARE = 0.8  # a line whose longest run in the cells covers this share is kept, only shifted
_LEADER = re.compile(r"^[.…·]+$")  # dot leaders of a contents table

_Box = tuple[float, float, float, float]  # left, top, right, bottom in top-left coordinates


def _letters(text: str) -> str:
    return "".join(char for char in text.lower() if char.isalnum())


def _top_left(bbox: dict[str, Any], page_height: float) -> _Box:
    left, right = float(bbox.get("l") or 0), float(bbox.get("r") or 0)
    top, bottom = float(bbox.get("t") or 0), float(bbox.get("b") or 0)
    if str(bbox.get("coord_origin", "")).upper() == "BOTTOMLEFT":
        top, bottom = page_height - top, page_height - bottom
    return (left, min(top, bottom), right, max(top, bottom))


def _center_in(word: Word, box: _Box) -> bool:
    x, y = (word[0] + word[2]) / 2, (word[1] + word[3]) / 2
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


@dataclass
class _Phrase:
    top: float
    bottom: float
    left: float
    text: str

    @property
    def middle(self) -> float:
        return (self.top + self.bottom) / 2


def _phrases(
    words: list[Word], columns: dict[int, tuple[float, float]], cell_boxes: list[_Box]
) -> list[_Phrase]:
    """
    Group words into printed lines, then split each line at cell borders: where the next word
    is in another Docling cell box (Philips p79: two-line headers 'Pause Al.' side by side),
    at a wide gap, or where the next word is in another column after a gap wider than the
    line's usual space (Philips p83: 6.7 pt between columns, 1.7 pt between words).
    """

    cell_of = {
        word: next((i for i, box in enumerate(cell_boxes) if _center_in(word, box)), None)
        for word in words
    }

    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        middle = (word[1] + word[3]) / 2
        if lines and abs(middle - (lines[-1][0][1] + lines[-1][0][3]) / 2) <= (
            (lines[-1][0][3] - lines[-1][0][1]) / 2
        ):
            lines[-1].append(word)
        else:
            lines.append([word])
    phrases: list[_Phrase] = []
    for line in lines:
        line.sort(key=lambda w: w[0])
        gaps = sorted(b[0] - a[2] for a, b in pairwise(line))
        space = gaps[len(gaps) // 2] if gaps else 0.0
        current = [line[0]]
        for word in line[1:]:
            gap = word[0] - current[-1][2]
            new_column = _column_of((word[0] + word[2]) / 2, columns) != _column_of(
                (current[-1][0] + current[-1][2]) / 2, columns
            )
            if (
                cell_of[word] != cell_of[current[-1]]
                or gap > _PHRASE_GAP * (word[3] - word[1])
                or (new_column and gap > _COLUMN_GAP * max(space, 0.5))
            ):
                phrases.append(_phrase(current))
                current = [word]
            else:
                current.append(word)
        phrases.append(_phrase(current))
    return [phrase for phrase in phrases if phrase.text]


def _phrase(words: list[Word]) -> _Phrase:
    text = " ".join(word[4] for word in words if not _LEADER.match(word[4]))
    return _Phrase(
        top=min(word[1] for word in words),
        bottom=max(word[3] for word in words),
        left=words[0][0],
        text=text,
    )


def _bands(
    cells: list[dict[str, Any]], page_height: float, start: str, end: str, low: int, high: int
) -> dict[int, tuple[float, float]]:
    """Extent of each single-span row or column, from its cells: index -> (low, high)."""
    bands: dict[int, tuple[float, float]] = {}
    for cell in cells:
        index = int(cell.get(start) or 0)
        if not cell.get("bbox") or int(cell.get(end) or 0) - index != 1:
            continue
        box = _top_left(cell["bbox"], page_height)
        old = bands.get(index, (box[low], box[high]))
        bands[index] = (min(old[0], box[low]), max(old[1], box[high]))
    return bands


def _column_of(x: float, columns: dict[int, tuple[float, float]]) -> int:
    """
    The column whose band holds x, else the last column that starts before x. Bands are built
    from the cell boxes, which hug left-aligned text, so a phrase is placed by its left edge.
    A band that starts up to _ROW_TOLERANCE after x still holds it (DOC p218: 'Phone' at
    405.0 pt under an address cell that starts at 405.6 pt); of the bands that hold x, the
    one that starts last wins.
    """
    holding = [
        index
        for index, (left, right) in columns.items()
        if left - _ROW_TOLERANCE <= x <= right + _ROW_TOLERANCE
    ]
    if holding:
        return max(holding, key=lambda index: columns[index][0])
    started = [index for index, (left, _) in columns.items() if left <= x]
    return max(started, key=lambda index: columns[index][0]) if started else min(columns)


def _in_a_column(x: float, columns: dict[int, tuple[float, float]]) -> bool:
    return any(
        left - _ROW_TOLERANCE <= x <= right + _ROW_TOLERANCE for left, right in columns.values()
    )


def _row_of(phrase: _Phrase, rows: dict[int, tuple[float, float]]) -> int | None:
    """
    The row printed at the phrase's height. Docling row bands often overlap or nest
    (LOGIQ_S8 p28): of the bands that hold the phrase, the one whose middle is nearest wins.
    """
    holding = [
        index
        for index, (top, bottom) in rows.items()
        if top - _ROW_TOLERANCE <= phrase.middle <= bottom + _ROW_TOLERANCE
    ]
    return min(
        holding,
        key=lambda index: (
            not rows[index][0] <= phrase.middle <= rows[index][1],
            abs(phrase.middle - sum(rows[index]) / 2),
        ),
        default=None,
    )


def _owned_boxes(
    merged: dict[str, Any], page_no: int, page_height: float, table: Any
) -> list[_Box]:
    """Boxes of the other Docling items on the page; words inside them already have an owner."""
    boxes = []
    for collection in ("texts", "tables", "pictures"):
        for node in merged.get(collection) or []:
            if node is table:
                continue
            prov = (node.get("prov") or [{}])[0]
            if prov.get("page_no") == page_no and prov.get("bbox"):
                boxes.append(_top_left(prov["bbox"], page_height))
    return boxes


def _unique(words: list[Word]) -> list[Word]:
    """Drop overprinted copies: the same word drawn again at the same place (LOGIQ_S8 p59)."""
    seen: set[tuple[str, int, int]] = set()
    kept = []
    for word in words:
        key = (word[4], round(word[0]), round(word[1]))
        if key not in seen:
            seen.add(key)
            kept.append(word)
    return kept


def _row_words(cells: list[dict[str, Any]]) -> dict[int, Counter[str]]:
    """Words (letters and digits) of the cells of each row, a spanning cell in every row."""
    words: dict[int, Counter[str]] = {}
    for cell in cells:
        tokens = [token for part in (cell.get("text") or "").split() if (token := _letters(part))]
        start = int(cell.get("start_row_offset_idx") or 0)
        for row in range(start, int(cell.get("end_row_offset_idx") or start + 1)):
            words.setdefault(row, Counter()).update(tokens)
    return words


def _lost_phrases(
    free: list[_Phrase],
    inside: list[_Phrase],
    cell_letters: str,
    page_letters: str,
    rows: dict[int, tuple[float, float]],
    row_words: dict[int, Counter[str]],
) -> list[_Phrase]:
    """
    Free phrases whose text is missing from the cells.

    - A text that is not in the cells as a whole is missing only if most of it is not there
      either: in a table whose rows are shifted, a cell can hold the line without its first
      word (AUTOMATIC p27 '1st reducing valve').
    - A line printed inside a row is missing only if it is not in the cells and most of its
      words are not in that row's cells: a mixed-up cell can hold them in another order
      (LOGIQ_S8 p304).
    - A line printed outside every row is missing when it is printed more often than the
      cells have it (AUTOMATIC p27: the lost row name '2-4 brake timing valve A' is also
      quoted in the next row, 'Returns the 2-4 brake timing valve A ...').
    """
    printed = "\n".join(_letters(phrase.text) for phrase in inside)
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(cell_letters)
    taken: Counter[str] = Counter()
    lost = []
    for phrase in free:
        key = _letters(phrase.text)
        if len(key) < _MIN_LOST_CHARS or key in page_letters:
            continue
        in_cells = cell_letters.count(key)
        if not in_cells:
            matcher.set_seq1(key)
            run = matcher.find_longest_match(0, len(key), 0, len(cell_letters)).size
            if run >= _KEPT_SHARE * len(key):
                continue
        row = _row_of(phrase, rows)
        if row is not None:
            tokens = [token for part in phrase.text.split() if (token := _letters(part))]
            missing = Counter(tokens) - row_words.get(row, Counter())
            if in_cells or missing.total() < _ROW_MISSING_SHARE * len(tokens):
                continue
        if printed.count(key) - in_cells - taken[key] > 0:
            taken[key] += 1
            lost.append(phrase)
    return lost


def _recover_table(
    table: dict[str, Any], merged: dict[str, Any], words: list[Word], page_height: float
) -> list[str]:
    """Add the lost lines of one table to its cells; return the recovered texts."""
    data = table.get("data") or {}
    cells: list[dict[str, Any]] = data.get("table_cells") or []
    prov = (table.get("prov") or [{}])[0]
    if not cells or not prov.get("bbox"):
        return []
    page_no = prov.get("page_no")
    box = _top_left(prov["bbox"], page_height)
    owned = _owned_boxes(merged, page_no, page_height, table)
    inside = _unique([word for word in words if _center_in(word, box)])
    # One line per cell or item, so that a text is never found across two of them.
    cell_letters = "\n".join(_letters(cell.get("text") or "") for cell in cells)
    # The words and the box must agree (same page geometry): most cell words are printed there.
    cell_words = {key for cell in cells for part in (cell.get("text") or "").split()
                  if len(key := _letters(part)) >= 3}
    printed = {_letters(word[4]) for word in inside}
    if not cell_words or len(cell_words & printed) < _MIN_AGREEMENT * len(cell_words):
        return []
    page_letters = "\n".join(
        _letters(node.get("text") or "")
        for node in merged.get("texts") or []
        if ((node.get("prov") or [{}])[0]).get("page_no") == page_no
    )
    free = [word for word in inside if not any(_center_in(word, other) for other in owned)]
    rows = _bands(cells, page_height, "start_row_offset_idx", "end_row_offset_idx", 1, 3)
    columns = _bands(cells, page_height, "start_col_offset_idx", "end_col_offset_idx", 0, 2)
    if not rows or not columns:
        return []
    cell_boxes = [_top_left(cell["bbox"], page_height) for cell in cells if cell.get("bbox")]
    lost = _lost_phrases(
        _phrases(free, columns, cell_boxes),
        _phrases(inside, columns, cell_boxes),
        cell_letters,
        page_letters,
        rows,
        _row_words(cells),
    )
    # A line inside a row but outside every column belongs to a column Docling lost entirely
    # (LOGIQ_S8 p817: the header 'Description'); joined to a neighbour cell it would read
    # as part of that cell ('Part Number Description'), so it is left out.
    lost = [
        phrase
        for phrase in lost
        if _row_of(phrase, rows) is None or _in_a_column(phrase.left, columns)
    ]
    if not lost:
        return []
    _place(data, cells, lost, rows, columns, page_height)
    return [phrase.text for phrase in lost]


def _place(
    data: dict[str, Any],
    cells: list[dict[str, Any]],
    lost: list[_Phrase],
    rows: dict[int, tuple[float, float]],
    columns: dict[int, tuple[float, float]],
    page_height: float,
) -> None:
    by_position = {
        (
            int(cell.get("start_row_offset_idx") or 0),
            int(cell.get("start_col_offset_idx") or 0),
        ): cell
        for cell in cells
    }
    new_rows: list[list[_Phrase]] = []
    for phrase in sorted(lost, key=lambda p: (p.top, p.left)):
        row = _row_of(phrase, rows)
        if row is not None:
            column = _column_of(phrase.left, columns)
            cell = by_position.get((row, column))
            if cell is None:
                cell = _new_cell(row, column)
                cells.append(cell)
                by_position[(row, column)] = cell
            text = (cell.get("text") or "").strip()
            above = cell.get("bbox") and phrase.middle < _top_left(cell["bbox"], page_height)[1]
            cell["text"] = f"{phrase.text} {text}" if above else f"{text} {phrase.text}"
            cell["text"] = cell["text"].strip()
            continue
        last = new_rows[-1][-1] if new_rows else None
        height = phrase.bottom - phrase.top
        same_gap = last is not None and phrase.top - last.bottom <= _NEW_ROW_GAP * height
        if last is not None and same_gap and _slot(last, rows) == _slot(phrase, rows):
            new_rows[-1].append(phrase)
        else:
            new_rows.append([phrase])
    if not new_rows:
        return
    new_rows.sort(key=lambda group: _slot(group[0], rows))
    slots = [_slot(group[0], rows) for group in new_rows]
    old_rows = int(data.get("num_rows") or 0)

    def shifted(row: int) -> int:
        return row + sum(1 for slot in slots if slot <= row)

    for cell in cells:
        start = int(cell.get("start_row_offset_idx") or 0)
        end = int(cell.get("end_row_offset_idx") or start + 1)
        cell["start_row_offset_idx"] = shifted(start)
        cell["end_row_offset_idx"] = shifted(end - 1) + 1
        cell["row_span"] = cell["end_row_offset_idx"] - cell["start_row_offset_idx"]
    # Slots are sorted, so every earlier new row is inserted before this one. A new row inside
    # a row-spanning cell widens that span; the cell keeps its start (renderer collapses spans).
    for order, (slot, group) in enumerate(zip(slots, new_rows, strict=True)):
        index = slot + order
        texts: dict[int, list[str]] = {}
        for phrase in group:
            texts.setdefault(_column_of(phrase.left, columns), []).append(phrase.text)
        for column, parts in texts.items():
            cell = _new_cell(index, column)
            cell["text"] = " ".join(parts)
            cells.append(cell)
    data["num_rows"] = old_rows + len(new_rows)


def _slot(phrase: _Phrase, rows: dict[int, tuple[float, float]]) -> int:
    """
    Index the new row takes among the old rows: one after the row printed nearest above it.
    Row indices do not always follow the page (AUTOMATIC p27: rows 17 and 18 are swapped).
    """
    above = [index for index, (top, _) in rows.items() if top < phrase.middle]
    return max(above, key=lambda index: (rows[index][0], index)) + 1 if above else 0


def _new_cell(row: int, column: int) -> dict[str, Any]:
    return {
        "text": "",
        "row_span": 1,
        "col_span": 1,
        "start_row_offset_idx": row,
        "end_row_offset_idx": row + 1,
        "start_col_offset_idx": column,
        "end_col_offset_idx": column + 1,
        "column_header": False,
        "row_header": False,
        "row_section": False,
    }


def recover_table_lines(
    merged: dict[str, Any],
    page_words: Callable[[int], list[Word]],
    logger: logging.Logger,
) -> int:
    """
    Put the printed lines of each table that are in no cell and in no other Docling item
    back into the table (``merged`` is changed in place). ``page_words`` is
    fitz_toc.page_words_reader. Returns the number of lines recovered.
    """
    recovered = changed = 0
    for index, table in enumerate(merged.get("tables") or []):
        page_no = ((table.get("prov") or [{}])[0]).get("page_no")
        size = ((merged.get("pages") or {}).get(str(page_no)) or {}).get("size") or {}
        page_height = float(size.get("height") or 0)
        if not page_no or page_height <= 0:
            continue
        texts = _recover_table(table, merged, page_words(int(page_no)), page_height)
        if texts:
            changed += 1
            recovered += len(texts)
            for text in texts:
                logger.debug("table line recovered p%s #/tables/%d: %s", page_no, index, text[:80])
    logger.info("table lines recovered: %d in %d tables", recovered, changed)
    return recovered
