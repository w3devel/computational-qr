"""Tests for computational_qr.core.color_geometry."""

import math
import pytest

from computational_qr.core.color_geometry import (
    ColorShape,
    ColorGeometry,
    GeometryKey,
    _clamp,
    _hsv_to_rgb_hex,
    _rgb_hex_to_hsv,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestClamp:
    def test_within_range(self):
        assert _clamp(0.5) == 0.5

    def test_below_min(self):
        assert _clamp(-1.0) == 0.0

    def test_above_max(self):
        assert _clamp(2.0) == 1.0

    def test_custom_bounds(self):
        assert _clamp(5.0, 0.0, 10.0) == 5.0
        assert _clamp(-5.0, 0.0, 10.0) == 0.0
        assert _clamp(15.0, 0.0, 10.0) == 10.0


class TestColorConversion:
    def test_hsv_to_rgb_hex_black(self):
        assert _hsv_to_rgb_hex(0.0, 0.0, 0.0) == "#000000"

    def test_hsv_to_rgb_hex_white(self):
        assert _hsv_to_rgb_hex(0.0, 0.0, 1.0) == "#ffffff"

    def test_hsv_to_rgb_hex_red(self):
        hex_color = _hsv_to_rgb_hex(0.0, 1.0, 1.0)
        assert hex_color.startswith("#")
        assert len(hex_color) == 7

    def test_rgb_hex_to_hsv_roundtrip(self):
        original = "#3a7bf4"
        h, s, v = _rgb_hex_to_hsv(original)
        result = _hsv_to_rgb_hex(h, s, v)
        # Allow ±1 per channel due to integer rounding
        def parse(hex_str):
            hex_str = hex_str.lstrip("#")
            return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
        orig_rgb = parse(original)
        result_rgb = parse(result)
        for o, r in zip(orig_rgb, result_rgb):
            assert abs(o - r) <= 1

    def test_short_hex(self):
        h, s, v = _rgb_hex_to_hsv("#fff")
        assert v == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# ColorShape
# ---------------------------------------------------------------------------

class TestColorShape:
    def test_default_construction(self):
        shape = ColorShape(label="A", value=5.0)
        assert shape.label == "A"
        assert shape.value == 5.0
        assert shape.x == 0.0
        assert shape.y == 0.0
        assert shape.z == 0.0
        assert shape.dimension == 0
        assert shape.weight == 1.0
        assert shape.shape_type == "circle"

    def test_color_derived(self):
        shape = ColorShape(label="B", value=10.0)
        assert shape.color.startswith("#")
        assert len(shape.color) == 7

    def test_different_dimensions_different_hues(self):
        s0 = ColorShape(label="X", value=5.0, dimension=0)
        s1 = ColorShape(label="Y", value=5.0, dimension=1)
        # Hues should differ by approximately 1/8 of the wheel
        diff = abs(s0.hue - s1.hue)
        assert diff > 0.05

    def test_area_positive(self):
        shape = ColorShape(label="C", value=4.0)
        assert shape.area() > 0

    def test_area_zero_value(self):
        shape = ColorShape(label="D", value=0.0)
        assert shape.area() > 0  # radius includes + 0.1 offset

    def test_area_scales_with_value(self):
        s1 = ColorShape(label="E", value=1.0)
        s2 = ColorShape(label="F", value=4.0)
        assert s2.area() > s1.area()

    def test_vertices_circle(self):
        shape = ColorShape(label="G", value=1.0, shape_type="circle")
        verts = shape.vertices()
        assert len(verts) == 36

    def test_vertices_polygon(self):
        shape = ColorShape(label="H", value=1.0, shape_type="polygon")
        verts = shape.vertices(n_sides=6)
        assert len(verts) == 6

    def test_vertices_rect(self):
        shape = ColorShape(label="I", value=1.0, shape_type="rect")
        verts = shape.vertices()
        assert len(verts) == 2
        # Two corners opposite each other
        (x0, y0), (x1, y1) = verts
        assert x1 > x0
        assert y1 > y0

    def test_vertices_star(self):
        shape = ColorShape(label="J", value=1.0, shape_type="star")
        verts = shape.vertices(n_sides=10)
        assert len(verts) == 10

    def test_to_dict_keys(self):
        shape = ColorShape(label="K", value=3.0, x=1.0, y=2.0, z=0.5)
        d = shape.to_dict()
        for key in ("label", "value", "x", "y", "z", "dimension", "color", "area"):
            assert key in d

    def test_from_dict_roundtrip(self):
        original = ColorShape(
            label="L", value=7.5, x=1.0, y=-1.0, z=2.0,
            dimension=2, weight=0.8, shape_type="polygon"
        )
        restored = ColorShape.from_dict(original.to_dict())
        assert restored.label == original.label
        assert restored.value == original.value
        assert restored.dimension == original.dimension
        assert restored.color == original.color

    def test_brightness_between_0_and_1(self):
        for v in (0.0, 0.1, 1.0, 10.0, 100.0):
            s = ColorShape(label="", value=v)
            assert 0.0 <= s.brightness <= 1.0


# ---------------------------------------------------------------------------
# GeometryKey
# ---------------------------------------------------------------------------

class TestGeometryKey:
    def test_color_for(self):
        key = GeometryKey(name="Temp", dimension=0, unit="°C", min_value=-10, max_value=40)
        color = key.color_for(20.0)
        assert color.startswith("#")

    def test_gradient_length(self):
        key = GeometryKey(name="Speed", dimension=1, unit="m/s")
        grad = key.gradient(steps=5)
        assert len(grad) == 5

    def test_gradient_values_in_range(self):
        key = GeometryKey(name="P", dimension=0, min_value=0.0, max_value=100.0)
        grad = key.gradient(steps=4)
        values = [v for v, _ in grad]
        assert values[0] == pytest.approx(0.0, abs=1e-6)
        assert values[-1] == pytest.approx(100.0, abs=1e-6)

    def test_to_dict(self):
        key = GeometryKey(name="X", dimension=0)
        d = key.to_dict()
        assert "gradient" in d
        assert d["name"] == "X"


# ---------------------------------------------------------------------------
# ColorGeometry
# ---------------------------------------------------------------------------

class TestColorGeometry:
    def setup_method(self):
        self.cg = ColorGeometry()
        self.dim0 = self.cg.add_dimension("Temperature", unit="°C", min_value=0, max_value=100)
        self.dim1 = self.cg.add_dimension("Pressure", unit="Pa", min_value=0, max_value=200)

    def test_add_dimension_returns_index(self):
        assert self.dim0 == 0
        assert self.dim1 == 1

    def test_keys_registered(self):
        assert len(self.cg.keys) == 2

    def test_key_lookup(self):
        k = self.cg.key(0)
        assert k.name == "Temperature"

    def test_key_not_found(self):
        with pytest.raises(KeyError):
            self.cg.key(99)

    def test_add_shape(self):
        s = self.cg.add_shape("T1", value=25.0, x=1.0, y=2.0, z=0.0, dimension=0)
        assert s.label == "T1"
        assert len(self.cg.shapes) == 1

    def test_shapes_for_dimension(self):
        self.cg.add_shape("T1", value=25.0, dimension=0)
        self.cg.add_shape("P1", value=100.0, dimension=1)
        self.cg.add_shape("T2", value=30.0, dimension=0)
        assert len(self.cg.shapes_for_dimension(0)) == 2
        assert len(self.cg.shapes_for_dimension(1)) == 1

    def test_find_intersections_no_intersections(self):
        self.cg.add_shape("A", value=1.0, x=0.0, y=0.0, z=0.0, dimension=0)
        self.cg.add_shape("B", value=2.0, x=10.0, y=10.0, z=10.0, dimension=1)
        assert self.cg.find_intersections(tolerance=1.0) == []

    def test_find_intersections_with_intersection(self):
        self.cg.add_shape("A", value=1.0, x=0.0, y=0.0, z=0.0, dimension=0)
        self.cg.add_shape("B", value=2.0, x=0.1, y=0.1, z=0.0, dimension=1)
        pairs = self.cg.find_intersections(tolerance=1.0)
        assert len(pairs) == 1

    def test_same_dimension_no_intersection_pair(self):
        # By default intersecting_shapes finds pairs regardless of dimension
        self.cg.add_shape("A", value=1.0, x=0.0, y=0.0, z=0.0, dimension=0)
        self.cg.add_shape("B", value=2.0, x=0.1, y=0.0, z=0.0, dimension=0)
        pairs = self.cg.find_intersections(tolerance=1.0)
        # Same dimension – still reported at the ColorGeometry level
        assert len(pairs) == 1

    def test_to_dict(self):
        self.cg.add_shape("X", value=5.0, dimension=0)
        d = self.cg.to_dict()
        assert "keys" in d
        assert "shapes" in d
        assert len(d["shapes"]) == 1
