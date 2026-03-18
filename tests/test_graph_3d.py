"""Tests for computational_qr.graphs.graph_3d."""

import math
import pytest

from computational_qr.graphs.graph_3d import DataPoint, Graph3D, Intersection


class TestDataPoint:
    def test_construction(self):
        p = DataPoint(label="A", x=1.0, y=2.0, z=3.0, value=5.0, dimension=0)
        assert p.label == "A"
        assert p.x == 1.0

    def test_distance_to_self(self):
        p = DataPoint(label="A", x=0.0, y=0.0, z=0.0, value=1.0)
        assert p.distance_to(p) == pytest.approx(0.0)

    def test_distance_to_unit(self):
        p1 = DataPoint(label="A", x=0.0, y=0.0, z=0.0, value=1.0)
        p2 = DataPoint(label="B", x=1.0, y=0.0, z=0.0, value=1.0)
        assert p1.distance_to(p2) == pytest.approx(1.0)

    def test_distance_3d(self):
        p1 = DataPoint(label="A", x=0.0, y=0.0, z=0.0, value=1.0)
        p2 = DataPoint(label="B", x=1.0, y=1.0, z=1.0, value=1.0)
        assert p1.distance_to(p2) == pytest.approx(math.sqrt(3))

    def test_to_dict(self):
        p = DataPoint(label="X", x=1.0, y=2.0, z=3.0, value=4.0, dimension=1,
                      metadata={"info": "test"})
        d = p.to_dict()
        assert d["label"] == "X"
        assert d["x"] == 1.0
        assert d["metadata"]["info"] == "test"


class TestGraph3D:
    def setup_method(self):
        self.g = Graph3D(tolerance=1.0)
        self.g.register_dimension(0, "Temperature")
        self.g.register_dimension(1, "Pressure")

    def test_add_point(self):
        p = self.g.add_point("A", 0.0, 0.0, 0.0, value=5.0, dimension=0)
        assert len(self.g.points) == 1
        assert p.label == "A"

    def test_add_points_bulk(self):
        pts = [
            DataPoint(label="X", x=0.0, y=0.0, z=0.0, value=1.0, dimension=0),
            DataPoint(label="Y", x=1.0, y=0.0, z=0.0, value=2.0, dimension=1),
        ]
        self.g.add_points(pts)
        assert len(self.g.points) == 2

    def test_dimension_label(self):
        assert self.g.dimension_label(0) == "Temperature"
        assert self.g.dimension_label(99) == "dim_99"

    def test_points_in_dimension(self):
        self.g.add_point("A", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        self.g.add_point("B", 1.0, 0.0, 0.0, value=2.0, dimension=1)
        self.g.add_point("C", 2.0, 0.0, 0.0, value=3.0, dimension=0)
        assert len(self.g.points_in_dimension(0)) == 2
        assert len(self.g.points_in_dimension(1)) == 1

    def test_no_intersections_when_far_apart(self):
        self.g.add_point("A", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        self.g.add_point("B", 100.0, 0.0, 0.0, value=2.0, dimension=1)
        assert self.g.find_intersections() == []

    def test_intersection_found_when_close(self):
        self.g.add_point("A", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        self.g.add_point("B", 0.5, 0.0, 0.0, value=2.0, dimension=1)
        ixs = self.g.find_intersections()
        assert len(ixs) == 1
        assert ixs[0].point_a.label in ("A", "B")

    def test_cross_dimension_only_excludes_same(self):
        self.g.add_point("A", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        self.g.add_point("B", 0.1, 0.0, 0.0, value=2.0, dimension=0)
        # Both in dim 0 – should be excluded with cross_dimension_only=True
        ixs = self.g.find_intersections(cross_dimension_only=True)
        assert ixs == []

    def test_cross_dimension_false_includes_same(self):
        self.g.add_point("A", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        self.g.add_point("B", 0.1, 0.0, 0.0, value=2.0, dimension=0)
        ixs = self.g.find_intersections(cross_dimension_only=False)
        assert len(ixs) == 1

    def test_intersection_sorted_by_distance(self):
        self.g.add_point("A", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        self.g.add_point("B", 0.3, 0.0, 0.0, value=2.0, dimension=1)
        self.g.add_point("C", 0.1, 0.0, 0.0, value=3.0, dimension=1)
        ixs = self.g.find_intersections()
        distances = [ix.distance for ix in ixs]
        assert distances == sorted(distances)

    def test_intersection_midpoint(self):
        self.g.add_point("A", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        self.g.add_point("B", 2.0, 0.0, 0.0, value=2.0, dimension=1)
        # Not within default tolerance of 1.0 – use wider tolerance
        g2 = Graph3D(tolerance=3.0)
        g2.add_point("A", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        g2.add_point("B", 2.0, 0.0, 0.0, value=2.0, dimension=1)
        ixs = g2.find_intersections()
        assert len(ixs) == 1
        assert ixs[0].midpoint == pytest.approx((1.0, 0.0, 0.0))

    def test_intersection_label(self):
        self.g.add_point("Alpha", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        self.g.add_point("Beta", 0.5, 0.0, 0.0, value=2.0, dimension=1)
        ixs = self.g.find_intersections()
        assert "∩" in ixs[0].label

    def test_to_dict_structure(self):
        self.g.add_point("X", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        d = self.g.to_dict()
        assert "points" in d
        assert "intersections" in d
        assert "tolerance" in d

    def test_to_json_is_valid(self):
        import json
        self.g.add_point("J", 0.0, 0.0, 0.0, value=1.0, dimension=0)
        json_str = self.g.to_json()
        parsed = json.loads(json_str)
        assert "points" in parsed

    def test_not_constrained_to_2d(self):
        """Data points can occupy arbitrary (x, y, z) – not forced to int rows/cols."""
        self.g.add_point("A", 1.5, 2.7, -0.3, value=1.0, dimension=0)
        self.g.add_point("B", 1.6, 2.8, -0.2, value=2.0, dimension=1)
        assert self.g.points[0].x == 1.5
        assert self.g.points[0].z == pytest.approx(-0.3)
        ixs = self.g.find_intersections()
        assert len(ixs) == 1
