"""Spreadsheet-style dependency intersection model.

Models "intersection" as Excel-style dependency intersections: a computed
cell or range depends on one or more source groups ("tables").  This is
distinct from—but coexists with—the geometric tolerance intersections in
:mod:`~computational_qr.graphs.graph_3d` and the colour geometry primitives in
:mod:`~computational_qr.core.color_geometry`.

Key concepts
------------
- **Reference** – an immutable identifier for a cell, range, table, sheet, or
  workbook.  References carry a stable string ``ref_id`` that is safe to use as
  a dict key or set member.
- **FormulaNode** – connects one or more input :class:`Reference` objects to a
  single output :class:`Reference`, optionally capturing the raw formula text
  and the operation name.
- **DependencyGraph** – a directed hypergraph whose nodes are references and
  whose hyperedges are :class:`FormulaNode` objects.  Supports transitive
  closure queries via :meth:`~DependencyGraph.get_all_inputs`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Reference types
# ---------------------------------------------------------------------------

class Reference:
    """Base class for all spreadsheet reference types.

    Sub-classes must set ``ref_id`` – a stable, unique string identifier.
    """

    ref_id: str
    ref_type: str  # "cell" | "range" | "table" | "sheet" | "workbook"
                   # | "external" | "unknown"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Reference):
            return NotImplemented
        return self.ref_id == other.ref_id

    def __hash__(self) -> int:
        return hash(self.ref_id)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.ref_id!r})"

    def to_dict(self) -> dict:
        return {"ref_id": self.ref_id, "ref_type": self.ref_type}


@dataclass(eq=False)
class CellRef(Reference):
    """A single cell reference, optionally sheet-qualified.

    Parameters
    ----------
    address:
        Cell address string, e.g. ``"A1"``, ``"$B$3"``.
    sheet:
        Sheet name (empty string if unqualified).
    workbook:
        Workbook identifier (empty string if local).
    """

    address: str
    sheet: str = ""
    workbook: str = ""
    ref_type: str = field(default="cell", init=False)

    def __post_init__(self) -> None:
        parts = []
        if self.workbook:
            parts.append(f"[{self.workbook}]")
        if self.sheet:
            parts.append(f"{self.sheet}!")
        parts.append(self.address.upper().replace("$", ""))
        self.ref_id = "".join(parts)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"address": self.address, "sheet": self.sheet, "workbook": self.workbook})
        return d


@dataclass(eq=False)
class RangeRef(Reference):
    """A rectangular cell range reference, optionally sheet-qualified.

    Parameters
    ----------
    address:
        Range address string, e.g. ``"A1:B5"``, ``"$A$1:$B$5"``.
    sheet:
        Sheet name (empty string if unqualified).
    workbook:
        Workbook identifier (empty string if local).
    """

    address: str
    sheet: str = ""
    workbook: str = ""
    ref_type: str = field(default="range", init=False)

    def __post_init__(self) -> None:
        parts = []
        if self.workbook:
            parts.append(f"[{self.workbook}]")
        if self.sheet:
            parts.append(f"{self.sheet}!")
        parts.append(self.address.upper().replace("$", ""))
        self.ref_id = "".join(parts)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"address": self.address, "sheet": self.sheet, "workbook": self.workbook})
        return d


@dataclass(eq=False)
class TableRef(Reference):
    """A named Excel Table (structured table) reference.

    Parameters
    ----------
    name:
        Table name, e.g. ``"SalesData"``.
    sheet:
        Sheet the table lives on (empty string if unknown).
    workbook:
        Workbook identifier (empty string if local).
    """

    name: str
    sheet: str = ""
    workbook: str = ""
    ref_type: str = field(default="table", init=False)

    def __post_init__(self) -> None:
        parts = []
        if self.workbook:
            parts.append(f"[{self.workbook}]")
        if self.sheet:
            parts.append(f"{self.sheet}!")
        parts.append(self.name)
        self.ref_id = "table:" + "".join(parts)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"name": self.name, "sheet": self.sheet, "workbook": self.workbook})
        return d


@dataclass(eq=False)
class SheetRef(Reference):
    """A whole-sheet reference.

    Parameters
    ----------
    name:
        Sheet name.
    workbook:
        Workbook identifier (empty string if local).
    """

    name: str
    workbook: str = ""
    ref_type: str = field(default="sheet", init=False)

    def __post_init__(self) -> None:
        prefix = f"[{self.workbook}]" if self.workbook else ""
        self.ref_id = f"sheet:{prefix}{self.name}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"name": self.name, "workbook": self.workbook})
        return d


@dataclass(eq=False)
class WorkbookRef(Reference):
    """A whole-workbook reference.

    Parameters
    ----------
    name:
        Workbook identifier / filename.
    """

    name: str
    ref_type: str = field(default="workbook", init=False)

    def __post_init__(self) -> None:
        self.ref_id = f"workbook:{self.name}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"name": self.name})
        return d


@dataclass(eq=False)
class ExternalRef(Reference):
    """An external workbook reference that was captured but not fully parsed.

    Parameters
    ----------
    raw:
        The raw reference text as it appeared in the formula.
    """

    raw: str
    ref_type: str = field(default="external", init=False)

    def __post_init__(self) -> None:
        self.ref_id = f"external:{self.raw}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"raw": self.raw})
        return d


@dataclass(eq=False)
class UnknownRef(Reference):
    """A reference that could not be fully parsed (e.g. structured references).

    Parameters
    ----------
    raw:
        The raw reference text as it appeared in the formula.
    """

    raw: str
    ref_type: str = field(default="unknown", init=False)

    def __post_init__(self) -> None:
        self.ref_id = f"unknown:{self.raw}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"raw": self.raw})
        return d


# ---------------------------------------------------------------------------
# FormulaNode
# ---------------------------------------------------------------------------

@dataclass
class FormulaNode:
    """A directed hyperedge connecting input references to an output reference.

    Each ``FormulaNode`` represents *one formula*: the cell at ``output``
    depends on all references in ``inputs``.

    Parameters
    ----------
    node_id:
        Stable string identifier for this node.  If not supplied it is derived
        from the output reference.
    output:
        The computed cell / range that this formula produces.
    inputs:
        The references consumed by the formula.
    operation:
        Human-readable operation name (e.g. ``"SUM"``, ``"VLOOKUP"``).
    formula_text:
        The raw formula string (e.g. ``"=SUM(Sheet2!A1:A10)"``).
    """

    output: Reference
    inputs: list[Reference] = field(default_factory=list)
    operation: str = ""
    formula_text: str = ""
    node_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"fn:{self.output.ref_id}"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "output": self.output.to_dict(),
            "inputs": [r.to_dict() for r in self.inputs],
            "operation": self.operation,
            "formula_text": self.formula_text,
        }


# ---------------------------------------------------------------------------
# DependencyGraph
# ---------------------------------------------------------------------------

class DependencyGraph:
    """A directed dependency hypergraph for spreadsheet formulas.

    Each formula node records ``output → f(input₁, input₂, …)``.
    The graph supports forward queries (what does a cell depend on?) and
    reverse queries (what cells depend on a given source?).

    Example
    -------
    >>> from computational_qr.graphs.dependency_graph import (
    ...     DependencyGraph, CellRef, RangeRef, TableRef
    ... )
    >>> g = DependencyGraph()
    >>> result = CellRef("C1", sheet="Sheet3")
    >>> src_a = RangeRef("A1:A10", sheet="Sheet1")
    >>> src_b = TableRef("SalesData", sheet="Sheet2")
    >>> g.add_formula(result, [src_a, src_b], formula_text="=SUM(Sheet1!A1:A10)+VLOOKUP(A1,SalesData,2)")
    >>> groups = g.source_groups(result)
    >>> print(sorted(groups))
    ['Sheet1!A1:A10', 'table:Sheet2!SalesData']
    """

    def __init__(self) -> None:
        # ref_id → Reference object
        self._refs: dict[str, Reference] = {}
        # output ref_id → list of FormulaNode
        self._by_output: dict[str, list[FormulaNode]] = {}
        # input ref_id → list of FormulaNode
        self._by_input: dict[str, list[FormulaNode]] = {}
        # all formula nodes
        self._nodes: list[FormulaNode] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def _register_ref(self, ref: Reference) -> None:
        self._refs.setdefault(ref.ref_id, ref)

    def add_formula(
        self,
        output: Reference,
        inputs: Iterable[Reference],
        *,
        operation: str = "",
        formula_text: str = "",
        node_id: str = "",
    ) -> FormulaNode:
        """Record that *output* is computed from *inputs*.

        Parameters
        ----------
        output:
            The computed reference.
        inputs:
            Iterable of source references.
        operation:
            Optional operation name.
        formula_text:
            Optional raw formula text.
        node_id:
            Optional explicit node identifier; auto-derived if omitted.

        Returns
        -------
        FormulaNode
            The newly created node.
        """
        input_list = list(inputs)
        node = FormulaNode(
            output=output,
            inputs=input_list,
            operation=operation,
            formula_text=formula_text,
            node_id=node_id,
        )
        self._register_ref(output)
        for ref in input_list:
            self._register_ref(ref)
        self._nodes.append(node)
        self._by_output.setdefault(output.ref_id, []).append(node)
        for ref in input_list:
            self._by_input.setdefault(ref.ref_id, []).append(node)
        return node

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_inputs(self, output: Reference) -> list[Reference]:
        """Return direct inputs of *output* (one hop)."""
        nodes = self._by_output.get(output.ref_id, [])
        seen: set[str] = set()
        result: list[Reference] = []
        for node in nodes:
            for ref in node.inputs:
                if ref.ref_id not in seen:
                    seen.add(ref.ref_id)
                    result.append(ref)
        return result

    def get_outputs(self, source: Reference) -> list[Reference]:
        """Return the references that directly depend on *source* (one hop)."""
        nodes = self._by_input.get(source.ref_id, [])
        seen: set[str] = set()
        result: list[Reference] = []
        for node in nodes:
            out = node.output
            if out.ref_id not in seen:
                seen.add(out.ref_id)
                result.append(out)
        return result

    def get_all_inputs(self, output: Reference, _visited: set[str] | None = None) -> list[Reference]:
        """Return all transitive inputs of *output* (multi-hop closure).

        Parameters
        ----------
        output:
            Starting reference.

        Returns
        -------
        list[Reference]
            All reachable predecessors in dependency order (breadth-first).
        """
        if _visited is None:
            _visited = set()
        result: list[Reference] = []
        queue: list[Reference] = list(self.get_inputs(output))
        while queue:
            ref = queue.pop(0)
            if ref.ref_id in _visited:
                continue
            _visited.add(ref.ref_id)
            result.append(ref)
            queue.extend(self.get_inputs(ref))
        return result

    def get_all_outputs(self, source: Reference, _visited: set[str] | None = None) -> list[Reference]:
        """Return all transitive dependents of *source* (multi-hop closure)."""
        if _visited is None:
            _visited = set()
        result: list[Reference] = []
        queue: list[Reference] = list(self.get_outputs(source))
        while queue:
            ref = queue.pop(0)
            if ref.ref_id in _visited:
                continue
            _visited.add(ref.ref_id)
            result.append(ref)
            queue.extend(self.get_outputs(ref))
        return result

    def source_groups(self, output: Reference) -> set[str]:
        """Return the set of distinct source group IDs for *output*.

        A "source group" is the stable ``ref_id`` of each *direct* input.
        For table / named-range aware grouping use
        :class:`~computational_qr.core.grouping_policy.DefaultTableGroupingPolicy`
        on top of this.
        """
        return {ref.ref_id for ref in self.get_inputs(output)}

    def formula_nodes(self) -> list[FormulaNode]:
        """Return all :class:`FormulaNode` objects in insertion order."""
        return list(self._nodes)

    def references(self) -> list[Reference]:
        """Return all registered :class:`Reference` objects."""
        return list(self._refs.values())

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "references": [r.to_dict() for r in self._refs.values()],
            "formula_nodes": [n.to_dict() for n in self._nodes],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
