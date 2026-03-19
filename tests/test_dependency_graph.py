"""Tests for the dependency-intersection engine.

Covers:
- Reference types and stable ref_id generation
- DependencyGraph (add_formula, get_inputs, get_outputs, transitive closure)
- Formula reference parsing
- DefaultTableGroupingPolicy (table / range / sheet fallback rules)
- ShapePolicy (k → shape_type, n_sides)
- Visualization payload generation (ColorGeometry keys + Graph3D points)
"""

from __future__ import annotations

import json
import pytest

from computational_qr.graphs.dependency_graph import (
    CellRef,
    DependencyGraph,
    ExternalRef,
    FormulaNode,
    RangeRef,
    Reference,
    SheetRef,
    TableRef,
    UnknownRef,
    WorkbookRef,
)
from computational_qr.core.formula_parser import parse_excel_formula_references
from computational_qr.core.grouping_policy import DefaultTableGroupingPolicy, ShapePolicy
from computational_qr.core.dependency_viz import (
    build_visualization_payload,
    dependency_to_color_geometry,
    dependency_to_graph3d,
)


# ===========================================================================
# Reference types
# ===========================================================================

class TestCellRef:
    def test_basic(self):
        ref = CellRef("A1")
        assert ref.ref_id == "A1"
        assert ref.ref_type == "cell"

    def test_with_sheet(self):
        ref = CellRef("B3", sheet="Sheet1")
        assert ref.ref_id == "Sheet1!B3"

    def test_dollar_stripped(self):
        ref = CellRef("$B$3", sheet="Sheet1")
        assert ref.ref_id == "Sheet1!B3"

    def test_workbook_and_sheet(self):
        ref = CellRef("C5", sheet="Data", workbook="Book1.xlsx")
        assert "[Book1.xlsx]" in ref.ref_id
        assert "Data!" in ref.ref_id
        assert "C5" in ref.ref_id

    def test_equality_and_hash(self):
        a = CellRef("A1", sheet="Sheet1")
        b = CellRef("A1", sheet="Sheet1")
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality(self):
        a = CellRef("A1", sheet="Sheet1")
        b = CellRef("A2", sheet="Sheet1")
        assert a != b

    def test_to_dict(self):
        ref = CellRef("A1", sheet="S")
        d = ref.to_dict()
        assert d["ref_type"] == "cell"
        assert d["address"] == "A1"
        assert d["sheet"] == "S"


class TestRangeRef:
    def test_basic(self):
        ref = RangeRef("A1:B5")
        assert ref.ref_id == "A1:B5"
        assert ref.ref_type == "range"

    def test_with_sheet(self):
        ref = RangeRef("A1:B5", sheet="Sheet2")
        assert ref.ref_id == "Sheet2!A1:B5"

    def test_normalised_uppercase(self):
        ref = RangeRef("a1:b5", sheet="sheet1")
        assert ref.ref_id == "sheet1!A1:B5"


class TestTableRef:
    def test_basic(self):
        ref = TableRef("SalesData", sheet="Sheet1")
        assert "SalesData" in ref.ref_id
        assert ref.ref_type == "table"

    def test_prefix(self):
        ref = TableRef("Prices", sheet="Catalog")
        assert ref.ref_id.startswith("table:")

    def test_equality(self):
        a = TableRef("T1", sheet="S1")
        b = TableRef("T1", sheet="S1")
        assert a == b


class TestSheetRef:
    def test_basic(self):
        ref = SheetRef("Sheet1")
        assert ref.ref_id == "sheet:Sheet1"
        assert ref.ref_type == "sheet"

    def test_with_workbook(self):
        ref = SheetRef("Summary", workbook="Annual.xlsx")
        assert "Annual.xlsx" in ref.ref_id


class TestWorkbookRef:
    def test_basic(self):
        ref = WorkbookRef("Book1.xlsx")
        assert ref.ref_id == "workbook:Book1.xlsx"
        assert ref.ref_type == "workbook"


class TestExternalRef:
    def test_basic(self):
        ref = ExternalRef(raw="[Book2.xlsx]Sheet1!A1")
        assert ref.ref_type == "external"
        assert "[Book2.xlsx]Sheet1!A1" in ref.ref_id

    def test_to_dict(self):
        ref = ExternalRef(raw="[X.xlsx]Y!Z1")
        d = ref.to_dict()
        assert d["raw"] == "[X.xlsx]Y!Z1"


class TestUnknownRef:
    def test_basic(self):
        ref = UnknownRef(raw="Table1[Amount]")
        assert ref.ref_type == "unknown"
        assert "Table1[Amount]" in ref.ref_id


# ===========================================================================
# FormulaNode
# ===========================================================================

class TestFormulaNode:
    def test_basic_construction(self):
        out = CellRef("C1", sheet="Sheet3")
        inp = RangeRef("A1:A10", sheet="Sheet1")
        node = FormulaNode(output=out, inputs=[inp], operation="SUM")
        assert node.output == out
        assert len(node.inputs) == 1
        assert node.operation == "SUM"

    def test_node_id_derived_from_output(self):
        out = CellRef("C1", sheet="Sheet3")
        node = FormulaNode(output=out)
        assert out.ref_id in node.node_id

    def test_explicit_node_id(self):
        out = CellRef("A1")
        node = FormulaNode(output=out, node_id="my_node")
        assert node.node_id == "my_node"

    def test_to_dict(self):
        out = CellRef("C1", sheet="Sheet3")
        inp = RangeRef("A1:A10", sheet="Sheet1")
        node = FormulaNode(output=out, inputs=[inp], formula_text="=SUM(Sheet1!A1:A10)")
        d = node.to_dict()
        assert d["operation"] == ""
        assert d["formula_text"] == "=SUM(Sheet1!A1:A10)"
        assert len(d["inputs"]) == 1
        # Verify expected top-level keys are present
        for key in ("node_id", "output", "inputs", "operation", "formula_text"):
            assert key in d
        assert d["output"]["ref_id"] == out.ref_id


# ===========================================================================
# DependencyGraph
# ===========================================================================

class TestDependencyGraph:
    def setup_method(self):
        self.g = DependencyGraph()
        self.result = CellRef("C1", sheet="Sheet3")
        self.src_a = RangeRef("A1:A10", sheet="Sheet1")
        self.src_b = TableRef("SalesData", sheet="Sheet2")
        self.g.add_formula(
            self.result,
            [self.src_a, self.src_b],
            formula_text="=SUM(Sheet1!A1:A10)+VLOOKUP(A1,SalesData,2)",
        )

    def test_add_formula_creates_node(self):
        nodes = self.g.formula_nodes()
        assert len(nodes) == 1

    def test_get_inputs_direct(self):
        inputs = self.g.get_inputs(self.result)
        assert len(inputs) == 2
        ids = {r.ref_id for r in inputs}
        assert self.src_a.ref_id in ids
        assert self.src_b.ref_id in ids

    def test_get_inputs_no_formula(self):
        unknown = CellRef("Z99")
        assert self.g.get_inputs(unknown) == []

    def test_get_outputs(self):
        outputs = self.g.get_outputs(self.src_a)
        assert len(outputs) == 1
        assert outputs[0].ref_id == self.result.ref_id

    def test_get_outputs_no_dependents(self):
        assert self.g.get_outputs(self.result) == []

    def test_source_groups(self):
        groups = self.g.source_groups(self.result)
        assert self.src_a.ref_id in groups
        assert self.src_b.ref_id in groups

    def test_references_registered(self):
        refs = self.g.references()
        ids = {r.ref_id for r in refs}
        assert self.result.ref_id in ids
        assert self.src_a.ref_id in ids
        assert self.src_b.ref_id in ids

    def test_transitive_inputs(self):
        """Transitive closure: result ← intermediate ← raw_source"""
        g = DependencyGraph()
        raw = CellRef("A1", sheet="Raw")
        mid = CellRef("B1", sheet="Calc")
        out = CellRef("C1", sheet="Report")
        g.add_formula(mid, [raw])
        g.add_formula(out, [mid])
        all_inputs = g.get_all_inputs(out)
        ids = {r.ref_id for r in all_inputs}
        assert mid.ref_id in ids
        assert raw.ref_id in ids

    def test_transitive_inputs_no_cycle_infinite_loop(self):
        """Graph with no transitive inputs returns only direct inputs."""
        g = DependencyGraph()
        src = CellRef("A1")
        out = CellRef("B1")
        g.add_formula(out, [src])
        # src has no inputs – transitive should still terminate
        all_inputs = g.get_all_inputs(out)
        assert len(all_inputs) == 1
        assert all_inputs[0].ref_id == src.ref_id

    def test_transitive_outputs(self):
        g = DependencyGraph()
        src = CellRef("A1", sheet="Data")
        mid = CellRef("B1", sheet="Calc")
        out = CellRef("C1", sheet="Report")
        g.add_formula(mid, [src])
        g.add_formula(out, [mid])
        all_outputs = g.get_all_outputs(src)
        ids = {r.ref_id for r in all_outputs}
        assert mid.ref_id in ids
        assert out.ref_id in ids

    def test_to_dict_structure(self):
        d = self.g.to_dict()
        assert "references" in d
        assert "formula_nodes" in d
        assert len(d["formula_nodes"]) == 1

    def test_to_json_is_valid(self):
        json_str = self.g.to_json()
        parsed = json.loads(json_str)
        assert "references" in parsed

    def test_multiple_formulas(self):
        g = DependencyGraph()
        a = CellRef("A1")
        b = CellRef("B1")
        c = CellRef("C1")
        g.add_formula(c, [a, b])
        g.add_formula(b, [a])
        assert len(g.formula_nodes()) == 2

    def test_operation_stored(self):
        g = DependencyGraph()
        out = CellRef("Z1")
        g.add_formula(out, [CellRef("A1")], operation="VLOOKUP")
        assert g.formula_nodes()[0].operation == "VLOOKUP"


# ===========================================================================
# Formula parser
# ===========================================================================

class TestFormulaParser:
    def test_bare_cell(self):
        refs = parse_excel_formula_references("=A1+B2")
        ids = [r.ref_id for r in refs]
        assert "A1" in ids
        assert "B2" in ids

    def test_bare_range(self):
        refs = parse_excel_formula_references("=SUM(A1:B5)")
        ids = [r.ref_id for r in refs]
        assert any("A1:B5" in rid for rid in ids)

    def test_sheet_qualified_cell(self):
        refs = parse_excel_formula_references("=Sheet1!A1")
        assert len(refs) >= 1
        ids = [r.ref_id for r in refs]
        assert any("Sheet1" in rid and "A1" in rid for rid in ids)

    def test_sheet_qualified_range(self):
        refs = parse_excel_formula_references("=SUM(Sheet2!A1:B10)")
        ids = [r.ref_id for r in refs]
        assert any("Sheet2" in rid for rid in ids)
        assert any("A1:B10" in rid for rid in ids)

    def test_quoted_sheet_name(self):
        refs = parse_excel_formula_references("='My Sheet'!C3")
        ids = [r.ref_id for r in refs]
        # Sheet name should be unquoted in ref_id
        assert any("My Sheet" in rid and "C3" in rid for rid in ids)

    def test_mixed_formula(self):
        formula = "=SUM(Sheet1!A1:A10)+Sheet2!B5+C3"
        refs = parse_excel_formula_references(formula)
        types = {type(r).__name__ for r in refs}
        assert "RangeRef" in types or "CellRef" in types

    def test_external_ref(self):
        formula = "=[Book2.xlsx]Sheet1!A1"
        refs = parse_excel_formula_references(formula)
        assert any(r.ref_type == "external" for r in refs)

    def test_structured_ref_captured_as_unknown(self):
        formula = "=SUM(Table1[Amount])"
        refs = parse_excel_formula_references(formula)
        assert any(r.ref_type == "unknown" for r in refs)

    def test_deduplication(self):
        refs = parse_excel_formula_references("=A1+A1")
        ids = [r.ref_id for r in refs]
        assert ids.count("A1") == 1

    def test_empty_formula(self):
        refs = parse_excel_formula_references("")
        assert refs == []

    def test_no_refs(self):
        refs = parse_excel_formula_references("=42")
        assert refs == []

    def test_absolute_refs_normalised(self):
        refs = parse_excel_formula_references("=$A$1:$B$3")
        ids = [r.ref_id for r in refs]
        # Dollar signs stripped in ref_id
        assert any("A1:B3" in rid for rid in ids)

    def test_cell_ref_type(self):
        refs = parse_excel_formula_references("=A1")
        assert len(refs) >= 1
        assert refs[0].ref_type == "cell"

    def test_range_ref_type(self):
        refs = parse_excel_formula_references("=A1:B5")
        types = {r.ref_type for r in refs}
        assert "range" in types

    def test_sheet_range_produces_range_ref(self):
        refs = parse_excel_formula_references("=Sheet1!A1:B5")
        types = {r.ref_type for r in refs}
        assert "range" in types

    def test_formula_without_equals(self):
        refs = parse_excel_formula_references("SUM(A1:B2)")
        ids = [r.ref_id for r in refs]
        assert any("A1:B2" in rid for rid in ids)


# ===========================================================================
# DefaultTableGroupingPolicy
# ===========================================================================

class TestDefaultTableGroupingPolicy:
    def setup_method(self):
        self.policy = DefaultTableGroupingPolicy()

    def test_table_ref_groups_by_table_id(self):
        t = TableRef("Sales", sheet="Sheet1")
        groups = self.policy.group_ids([t])
        assert t.ref_id in groups

    def test_multiple_tables_separate_groups(self):
        t1 = TableRef("Sales", sheet="Sheet1")
        t2 = TableRef("Costs", sheet="Sheet1")
        groups = self.policy.group_ids([t1, t2])
        assert len(groups) == 2

    def test_ranges_only_collapse_to_sheet_when_no_tables(self):
        r1 = RangeRef("A1:A10", sheet="Sheet1")
        r2 = RangeRef("B1:B10", sheet="Sheet1")
        groups = self.policy.group_ids([r1, r2])
        # Both on Sheet1 with no tables → collapse to sheet group
        assert len(groups) == 1
        assert "sheet:Sheet1" in groups

    def test_ranges_stay_separate_when_multiple_tables_present(self):
        t1 = TableRef("T1", sheet="Sheet1")
        t2 = TableRef("T2", sheet="Sheet1")
        r = RangeRef("C1:C10", sheet="Sheet1")
        policy = DefaultTableGroupingPolicy()
        groups = policy.group_ids([t1, t2, r])
        # 2 tables on Sheet1 → range should keep its own group
        assert len(groups) >= 3

    def test_sheet_fallback_disabled(self):
        policy = DefaultTableGroupingPolicy(single_table_sheet_fallback=False)
        r1 = RangeRef("A1:A10", sheet="Sheet1")
        r2 = RangeRef("B1:B10", sheet="Sheet1")
        groups = policy.group_ids([r1, r2])
        # Should produce 2 groups (no sheet collapse)
        assert len(groups) == 2

    def test_mixed_refs_with_one_table_collapses_ranges(self):
        t = TableRef("Sales", sheet="Sheet1")
        r = RangeRef("A1:A5", sheet="Sheet1")
        groups = self.policy.group_ids([t, r])
        # 1 table on Sheet1 → range collapses to sheet group, table keeps its own
        assert t.ref_id in groups
        assert "sheet:Sheet1" in groups

    def test_assign_groups_returns_mapping(self):
        t = TableRef("T1", sheet="S1")
        r = RangeRef("A1:A5", sheet="S1")
        mapping = self.policy.assign_groups([t, r])
        assert t.ref_id in mapping
        assert r.ref_id in mapping

    def test_external_ref_stays_as_is(self):
        ext = ExternalRef(raw="[Book2.xlsx]Sheet1!A1")
        groups = self.policy.group_ids([ext])
        assert ext.ref_id in groups

    def test_unqualified_range_uses_range_group(self):
        r = RangeRef("A1:B5")  # no sheet
        groups = self.policy.group_ids([r])
        # No sheet → uses range: prefix fallback
        assert len(groups) == 1


# ===========================================================================
# ShapePolicy
# ===========================================================================

class TestShapePolicy:
    def setup_method(self):
        self.policy = ShapePolicy()

    def test_zero_groups_circle(self):
        shape_type, n_sides = self.policy.shape_for(0)
        assert shape_type == "circle"

    def test_one_group_circle(self):
        shape_type, n_sides = self.policy.shape_for(1)
        assert shape_type == "circle"

    def test_two_groups_polygon(self):
        shape_type, n_sides = self.policy.shape_for(2)
        assert shape_type == "polygon"
        assert n_sides == 4

    def test_three_groups_hexagon(self):
        shape_type, n_sides = self.policy.shape_for(3)
        assert shape_type == "polygon"
        assert n_sides == 6

    def test_four_groups_octagon(self):
        shape_type, n_sides = self.policy.shape_for(4)
        assert shape_type == "polygon"
        assert n_sides == 8

    def test_five_groups_ten_sides(self):
        shape_type, n_sides = self.policy.shape_for(5)
        assert shape_type == "polygon"
        assert n_sides == 10

    def test_six_groups_star(self):
        shape_type, n_sides = self.policy.shape_for(6)
        assert shape_type == "star"
        assert n_sides >= 6

    def test_star_sides_scale_with_k(self):
        _, sides_6 = self.policy.shape_for(6)
        _, sides_8 = self.policy.shape_for(8)
        assert sides_8 >= sides_6

    def test_star_sides_capped_at_24(self):
        _, n = self.policy.shape_for(100)
        assert n <= 24

    def test_custom_rules(self):
        custom = ShapePolicy(rules=[(2, "rect", 4), (10, "polygon", 12)])
        shape_type, _ = custom.shape_for(1)
        assert shape_type == "rect"
        shape_type2, n = custom.shape_for(5)
        assert shape_type2 == "polygon"
        assert n == 12

    def test_negative_k_treated_as_zero(self):
        shape_type, _ = self.policy.shape_for(-5)
        assert shape_type == "circle"


# ===========================================================================
# Visualization payload helpers
# ===========================================================================

class TestDependencyToColorGeometry:
    def _build_graph(self):
        g = DependencyGraph()
        out = CellRef("C1", sheet="Report")
        t1 = TableRef("Revenue", sheet="Sheet1")
        t2 = TableRef("Costs", sheet="Sheet2")
        g.add_formula(out, [t1, t2], formula_text="=Revenue_Total - Costs_Total")
        return g, out

    def test_produces_color_geometry(self):
        g, out = self._build_graph()
        cg = dependency_to_color_geometry(g)
        assert len(cg.shapes) >= 1

    def test_dimensions_match_source_groups(self):
        g, out = self._build_graph()
        cg = dependency_to_color_geometry(g)
        # Two source groups → two dimensions
        assert len(cg.keys) == 2

    def test_shape_type_determined_by_policy(self):
        g, out = self._build_graph()
        cg = dependency_to_color_geometry(g)
        # 2 source groups → polygon (4 sides by default)
        shape = cg.shapes[0]
        assert shape.shape_type == "polygon"

    def test_geometry_key_names_match_group_ids(self):
        g, out = self._build_graph()
        cg = dependency_to_color_geometry(g)
        key_names = {k.name for k in cg.keys}
        # Key names should contain the table ref IDs
        t1 = TableRef("Revenue", sheet="Sheet1")
        t2 = TableRef("Costs", sheet="Sheet2")
        assert t1.ref_id in key_names
        assert t2.ref_id in key_names

    def test_explicit_outputs_parameter(self):
        g, out = self._build_graph()
        cg = dependency_to_color_geometry(g, [out])
        assert len(cg.shapes) == 1


class TestDependencyToGraph3D:
    def _build_graph(self):
        g = DependencyGraph()
        out = CellRef("C1", sheet="Report")
        t1 = TableRef("Revenue", sheet="Sheet1")
        t2 = TableRef("Costs", sheet="Sheet2")
        g.add_formula(out, [t1, t2])
        return g, out

    def test_produces_graph3d(self):
        g, out = self._build_graph()
        g3d = dependency_to_graph3d(g)
        assert len(g3d.points) >= 1

    def test_z_encodes_source_group_count(self):
        g, out = self._build_graph()
        g3d = dependency_to_graph3d(g)
        # 2 source groups → z should be 2.0
        assert g3d.points[0].z == pytest.approx(2.0)

    def test_point_metadata_has_source_groups(self):
        g, out = self._build_graph()
        g3d = dependency_to_graph3d(g)
        pt = g3d.points[0]
        assert "source_groups" in pt.metadata
        assert len(pt.metadata["source_groups"]) == 2

    def test_dimensions_registered(self):
        g, out = self._build_graph()
        g3d = dependency_to_graph3d(g)
        # At least one dimension registered
        assert len(g3d._dimension_labels) >= 1


class TestBuildVisualizationPayload:
    def _build_graph(self):
        g = DependencyGraph()
        out1 = CellRef("C1", sheet="Report")
        out2 = CellRef("D1", sheet="Report")
        t1 = TableRef("Revenue", sheet="Sheet1")
        t2 = TableRef("Costs", sheet="Sheet2")
        r1 = RangeRef("A1:A10", sheet="Sheet3")
        g.add_formula(out1, [t1, t2])
        g.add_formula(out2, [t1, r1])
        return g

    def test_payload_has_all_sections(self):
        g = self._build_graph()
        payload = build_visualization_payload(g)
        assert "dependency_graph" in payload
        assert "color_geometry" in payload
        assert "graph_3d" in payload

    def test_payload_json_serialisable(self):
        g = self._build_graph()
        payload = build_visualization_payload(g)
        json_str = json.dumps(payload)
        parsed = json.loads(json_str)
        assert "color_geometry" in parsed

    def test_color_geometry_has_keys_and_shapes(self):
        g = self._build_graph()
        payload = build_visualization_payload(g)
        cg = payload["color_geometry"]
        assert "keys" in cg
        assert "shapes" in cg
        assert len(cg["shapes"]) >= 1

    def test_graph3d_has_points(self):
        g = self._build_graph()
        payload = build_visualization_payload(g)
        g3d = payload["graph_3d"]
        assert "points" in g3d
        assert len(g3d["points"]) >= 1

    def test_dependency_graph_section_has_formula_nodes(self):
        g = self._build_graph()
        payload = build_visualization_payload(g)
        dg = payload["dependency_graph"]
        assert len(dg["formula_nodes"]) == 2

    def test_dimension_indices_in_shapes(self):
        g = self._build_graph()
        payload = build_visualization_payload(g)
        shapes = payload["color_geometry"]["shapes"]
        for shape in shapes:
            assert "dimension" in shape
            assert shape["dimension"] >= 0

    def test_single_output_formula(self):
        g = DependencyGraph()
        out = CellRef("Z1", sheet="Summary")
        g.add_formula(out, [CellRef("A1", sheet="Raw")], formula_text="=Raw!A1*2")
        payload = build_visualization_payload(g)
        assert len(payload["color_geometry"]["shapes"]) == 1
        shape = payload["color_geometry"]["shapes"][0]
        # 1 source group → circle
        assert shape["shape_type"] == "circle"
