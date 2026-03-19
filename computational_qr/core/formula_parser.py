"""Minimal viable Excel-formula reference parser.

Extracts cell, range, and sheet-qualified references from Excel-like formula
strings.  Structured references (``Table[Column]``) are captured as
:class:`~computational_qr.graphs.dependency_graph.UnknownRef`; external
workbook references are captured as
:class:`~computational_qr.graphs.dependency_graph.ExternalRef`.

Public API
----------
.. code-block:: python

    from computational_qr.core.formula_parser import parse_excel_formula_references

    refs = parse_excel_formula_references("=SUM(Sheet1!A1:B10)+Sheet2!C5")
    for r in refs:
        print(r.ref_id, r.ref_type)
"""

from __future__ import annotations

import re
from typing import Sequence

from computational_qr.graphs.dependency_graph import (
    CellRef,
    ExternalRef,
    RangeRef,
    Reference,
    UnknownRef,
)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Column letters (one or more A-Z, case-insensitive)
_COL = r"[A-Za-z]{1,3}"
# Row number (one or more digits)
_ROW = r"[0-9]+"
# Optional dollar signs for absolute refs
_CELL_ADDR = rf"\$?{_COL}\$?{_ROW}"
# Range address  A1:B5 (no sheet prefix here)
_RANGE_ADDR = rf"{_CELL_ADDR}:{_CELL_ADDR}"

# Sheet name: either bare word or single-quoted (may contain spaces/special chars)
_SHEET_BARE = r"[A-Za-z0-9_\.]+"
_SHEET_QUOTED = r"'[^']+'"
_SHEET = rf"(?:{_SHEET_QUOTED}|{_SHEET_BARE})"

# External workbook prefix:  [WorkbookName.xlsx]SheetName!  or  [Book1]Sheet1!
_EXTERNAL_PREFIX = rf"\[[^\]]+\]{_SHEET}"

# Structured reference stub: TableName[...] – capture as UnknownRef
_STRUCTURED = r"[A-Za-z_][A-Za-z0-9_\.]*\[[^\]]*\]"

# Full patterns (order matters – try most specific first)

# External workbook range or cell
_PAT_EXTERNAL_RANGE = re.compile(
    rf"({_EXTERNAL_PREFIX})!({_RANGE_ADDR})", re.IGNORECASE
)
_PAT_EXTERNAL_CELL = re.compile(
    rf"({_EXTERNAL_PREFIX})!({_CELL_ADDR})", re.IGNORECASE
)

# Sheet-qualified range or cell  (local workbook)
_PAT_SHEET_RANGE = re.compile(
    rf"({_SHEET})!({_RANGE_ADDR})", re.IGNORECASE
)
_PAT_SHEET_CELL = re.compile(
    rf"({_SHEET})!({_CELL_ADDR})", re.IGNORECASE
)

# Bare range (no sheet prefix)
_PAT_BARE_RANGE = re.compile(rf"(?<![!\w])({_RANGE_ADDR})(?!\w)", re.IGNORECASE)

# Bare cell (no sheet prefix)
_PAT_BARE_CELL = re.compile(
    rf"(?<![!\w\$])(\$?{_COL}\$?{_ROW})(?!\w)", re.IGNORECASE
)

# Structured reference stub
_PAT_STRUCTURED = re.compile(_STRUCTURED, re.IGNORECASE)


def _strip_quotes(sheet: str) -> str:
    """Remove surrounding single quotes from a sheet name if present."""
    if sheet.startswith("'") and sheet.endswith("'"):
        return sheet[1:-1]
    return sheet


def _consume(text: str, spans: list[tuple[int, int]]) -> str:
    """Replace already-matched spans with spaces so later patterns do not re-match."""
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


def parse_excel_formula_references(formula: str) -> list[Reference]:
    """Extract all references from an Excel-like *formula* string.

    The parser recognises:

    - Sheet-qualified cell and range references:
      ``Sheet1!A1``, ``'My Sheet'!A1:B5``
    - Bare cell and range references: ``A1``, ``B2:C10``
    - External workbook references: ``[Book1.xlsx]Sheet1!A1`` (captured as
      :class:`~computational_qr.graphs.dependency_graph.ExternalRef`)
    - Structured table references: ``Table1[Column]`` (captured as
      :class:`~computational_qr.graphs.dependency_graph.UnknownRef`)

    Parameters
    ----------
    formula:
        Raw formula text, with or without a leading ``=``.

    Returns
    -------
    list[Reference]
        Deduplicated list of references in order of first appearance.
    """
    # Strip leading "=" if present
    text = formula.lstrip("=").strip() if formula else ""

    seen_ids: set[str] = set()
    results: list[Reference] = []
    consumed_spans: list[tuple[int, int]] = []

    def _add(ref: Reference) -> None:
        if ref.ref_id not in seen_ids:
            seen_ids.add(ref.ref_id)
            results.append(ref)

    # 1) Structured references (highest priority – consume before bare cell match)
    for m in _PAT_STRUCTURED.finditer(text):
        _add(UnknownRef(raw=m.group(0)))
        consumed_spans.append(m.span())
    text_pass2 = _consume(text, consumed_spans)

    # 2) External workbook ranges & cells
    ext_spans: list[tuple[int, int]] = []
    for m in _PAT_EXTERNAL_RANGE.finditer(text_pass2):
        _add(ExternalRef(raw=m.group(0)))
        ext_spans.append(m.span())
    for m in _PAT_EXTERNAL_CELL.finditer(text_pass2):
        # Avoid double-matching spans already consumed by range pattern
        span = m.span()
        if not any(s <= span[0] < e for s, e in ext_spans):
            _add(ExternalRef(raw=m.group(0)))
            ext_spans.append(span)
    consumed_spans.extend(ext_spans)
    text_pass3 = _consume(text, consumed_spans)

    # 3) Sheet-qualified ranges
    sheet_spans: list[tuple[int, int]] = []
    for m in _PAT_SHEET_RANGE.finditer(text_pass3):
        sheet = _strip_quotes(m.group(1))
        addr = m.group(2)
        _add(RangeRef(address=addr, sheet=sheet))
        sheet_spans.append(m.span())
    consumed_spans.extend(sheet_spans)
    text_pass4 = _consume(text, consumed_spans)

    # 4) Sheet-qualified cells
    cell_spans: list[tuple[int, int]] = []
    for m in _PAT_SHEET_CELL.finditer(text_pass4):
        sheet = _strip_quotes(m.group(1))
        addr = m.group(2)
        _add(CellRef(address=addr, sheet=sheet))
        cell_spans.append(m.span())
    consumed_spans.extend(cell_spans)
    text_pass5 = _consume(text, consumed_spans)

    # 5) Bare ranges
    bare_range_spans: list[tuple[int, int]] = []
    for m in _PAT_BARE_RANGE.finditer(text_pass5):
        _add(RangeRef(address=m.group(1)))
        bare_range_spans.append(m.span())
    consumed_spans.extend(bare_range_spans)
    text_pass6 = _consume(text, consumed_spans)

    # 6) Bare cells
    for m in _PAT_BARE_CELL.finditer(text_pass6):
        raw = m.group(1)
        # Skip pure-number captures (shouldn't happen with the pattern, but guard)
        if raw.lstrip("$").isdigit():
            continue
        _add(CellRef(address=raw))

    return results
