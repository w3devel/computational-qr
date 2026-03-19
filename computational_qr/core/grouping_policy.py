"""Grouping and shape-selection policies for dependency intersections.

Two policy classes are provided:

:class:`DefaultTableGroupingPolicy`
    Maps a collection of input :class:`~computational_qr.graphs.dependency_graph.Reference`
    objects to group IDs, implementing the default rule:

    1. If a :class:`~computational_qr.graphs.dependency_graph.TableRef` is
       present, use the table's ``ref_id`` as the group.
    2. Otherwise group by the normalised range address (sheet + address).
    3. If the sheet has only one table or no official tables, fall back to the
       sheet name as a single group.

    This matches the user-specified default policy: "prefer official Excel
    Table objects and named ranges; otherwise group by referenced range blocks;
    if a sheet has no official tables or only one table, treat the whole sheet
    as a single source group."

:class:`ShapePolicy`
    Maps the number of distinct source groups *k* to a
    (``shape_type``, ``n_sides``) pair, reusing the existing
    :class:`~computational_qr.core.color_geometry.ColorShape` geometry types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from computational_qr.graphs.dependency_graph import (
    CellRef,
    RangeRef,
    Reference,
    SheetRef,
    TableRef,
)


def _default_shape_rules() -> list[tuple[int, str, int]]:
    """Return the built-in (max_k, shape_type, n_sides) rules for ShapePolicy."""
    return [
        (1,  "circle",  36),
        (2,  "polygon", 4),
        (3,  "polygon", 6),
        (4,  "polygon", 8),
        (5,  "polygon", 10),
        (12, "star",    0),
    ]


# ---------------------------------------------------------------------------
# DefaultTableGroupingPolicy
# ---------------------------------------------------------------------------

class DefaultTableGroupingPolicy:
    """Maps input references to source group IDs using a tiered default policy.

    The policy is evaluated in priority order for each reference:

    Priority 1 – **TableRef**
        Use the table's ``ref_id`` directly as the group ID.

    Priority 2 – **RangeRef / CellRef** with a known sheet, where the sheet
        does **not** already have an official table
        Use ``"<sheet>!<address>"`` as the group ID.

    Priority 3 – **Sheet fallback**
        When a sheet has exactly zero or one table entries among the inputs,
        collapse all refs on that sheet into a single ``"sheet:<name>"`` group.

    Parameters
    ----------
    single_table_sheet_fallback:
        When ``True`` (default), sheets that contribute only one or zero table
        refs are collapsed to a sheet-level group.  Set to ``False`` to always
        group by range address.
    """

    def __init__(self, *, single_table_sheet_fallback: bool = True) -> None:
        self.single_table_sheet_fallback = single_table_sheet_fallback

    def assign_groups(self, refs: Iterable[Reference]) -> dict[str, str]:
        """Return a mapping of ``ref_id → group_id`` for each reference.

        Parameters
        ----------
        refs:
            The input references to classify.

        Returns
        -------
        dict[str, str]
            Keys are ``Reference.ref_id`` values; values are group IDs.
        """
        ref_list = list(refs)

        # First pass: separate TableRef objects by sheet
        tables_by_sheet: dict[str, list[TableRef]] = {}
        for ref in ref_list:
            if isinstance(ref, TableRef):
                tables_by_sheet.setdefault(ref.sheet or "__unqualified__", []).append(ref)

        assignment: dict[str, str] = {}

        for ref in ref_list:
            if isinstance(ref, TableRef):
                assignment[ref.ref_id] = ref.ref_id

            elif isinstance(ref, (RangeRef, CellRef)):
                sheet = ref.sheet or "__unqualified__"
                table_count = len(tables_by_sheet.get(sheet, []))
                if self.single_table_sheet_fallback and table_count <= 1:
                    # Collapse to sheet-level group
                    group = f"sheet:{ref.sheet}" if ref.sheet else f"range:{ref.ref_id}"
                else:
                    group = ref.ref_id
                assignment[ref.ref_id] = group

            elif isinstance(ref, SheetRef):
                assignment[ref.ref_id] = ref.ref_id

            else:
                # ExternalRef, WorkbookRef, UnknownRef – keep as-is
                assignment[ref.ref_id] = ref.ref_id

        return assignment

    def group_ids(self, refs: Iterable[Reference]) -> set[str]:
        """Return the *set* of distinct group IDs for *refs*."""
        return set(self.assign_groups(refs).values())


# ---------------------------------------------------------------------------
# ShapePolicy
# ---------------------------------------------------------------------------

@dataclass
class ShapePolicy:
    """Maps the number of distinct source groups *k* to shape geometry.

    The mapping produces ``shape_type`` and ``n_sides`` values compatible with
    :class:`~computational_qr.core.color_geometry.ColorShape`.

    Rules
    -----
    - k ≤ 1  → ``"circle"``  (1 group or fewer; n_sides = 0, use 36 for circle)
    - k = 2  → ``"polygon"`` with 4 sides (square – two sources, square symmetry)
    - k = 3  → ``"polygon"`` with 6 sides (hexagon)
    - k = 4  → ``"polygon"`` with 8 sides (octagon)
    - k = 5  → ``"polygon"`` with 10 sides
    - k ≥ 6  → ``"star"``    with ``2 * k`` points (star with one spike per source)
    - k > 12 → ``"star"``    with 24 points (capped at 24 for visual clarity)

    These can be overridden by providing a custom ``rules`` list of
    ``(max_k, shape_type, n_sides)`` tuples.

    Parameters
    ----------
    rules:
        Optional override list of ``(max_k, shape_type, n_sides)`` tuples,
        evaluated in ascending ``max_k`` order.  The first rule whose
        ``max_k >= k`` is used.  If omitted, the built-in rules above apply.
    """

    rules: list[tuple[int, str, int]] = field(default_factory=list)

    _DEFAULT_RULES: list[tuple[int, str, int]] = field(
        default_factory=_default_shape_rules,
        init=False,
        repr=False,
        compare=False,
    )

    def shape_for(self, k: int) -> tuple[str, int]:
        """Return ``(shape_type, n_sides)`` for *k* distinct source groups.

        Parameters
        ----------
        k:
            Number of distinct source groups (≥ 0).

        Returns
        -------
        tuple[str, int]
            ``shape_type`` is one of ``"circle"``, ``"polygon"``, or
            ``"star"``.  ``n_sides`` is the number of polygon sides / star
            points (0 is not used directly; callers interpret circle as 36
            sides internally).
        """
        effective_rules = self.rules if self.rules else self._DEFAULT_RULES
        k = max(0, k)

        for max_k, shape_type, n_sides in sorted(effective_rules, key=lambda r: r[0]):
            if k <= max_k:
                if shape_type == "star":
                    return ("star", min(max(2 * k, 6), 24))
                return (shape_type, n_sides)

        # Fallback: star with capped sides
        return ("star", 24)
