"""Tests for computational_qr.database.postgis_store and spatial_models.

These tests are split into two groups:

1. **Offline tests** (always run) – validate SQL construction, module imports,
   and the ``POSTGIS_AVAILABLE`` flag without requiring a live database or the
   *geoalchemy2* package to be installed.

2. **Integration tests** (skipped by default) – require a PostGIS-enabled
   PostgreSQL database.  Set the ``CQ_TEST_DATABASE_URL`` environment variable
   to a valid connection string to enable them, e.g.::

       CQ_TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost/testdb pytest

"""

from __future__ import annotations

import os
import uuid

import pytest

from computational_qr.database.postgis_store import (
    _build_find_intersections_3d_sql,
    _build_find_intersections_2d_sql,
)
from computational_qr.database.spatial_models import POSTGIS_AVAILABLE


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

_CQ_DB_URL = os.environ.get("CQ_TEST_DATABASE_URL")

integration = pytest.mark.skipif(
    not _CQ_DB_URL,
    reason="Set CQ_TEST_DATABASE_URL to run PostGIS integration tests",
)

postgis_pkg = pytest.mark.skipif(
    not POSTGIS_AVAILABLE,
    reason="geoalchemy2 not installed; skipping PostGIS model tests",
)


# ===========================================================================
# Offline tests – SQL construction
# ===========================================================================

class TestBuildIntersections3dSql:
    """Validate the SQL string returned by ``_build_find_intersections_3d_sql``."""

    def test_contains_st_3ddwithin(self):
        sql = _build_find_intersections_3d_sql(True)
        assert "ST_3DDWithin" in sql

    def test_contains_st_3ddistance(self):
        sql = _build_find_intersections_3d_sql(True)
        assert "ST_3DDistance" in sql

    def test_contains_table_name(self):
        sql = _build_find_intersections_3d_sql(True)
        assert "spatial_points_3d" in sql

    def test_deduplication_predicate(self):
        sql = _build_find_intersections_3d_sql(True)
        assert "a.id < b.id" in sql

    def test_scene_id_parameter(self):
        sql = _build_find_intersections_3d_sql(True)
        assert ":scene_id" in sql

    def test_tolerance_parameter(self):
        sql = _build_find_intersections_3d_sql(True)
        assert ":tolerance" in sql

    def test_dimension_filter_present_when_true(self):
        sql = _build_find_intersections_3d_sql(True)
        assert "dimension" in sql and "<>" in sql

    def test_dimension_filter_absent_when_false(self):
        sql = _build_find_intersections_3d_sql(False)
        # The dimension filter must not appear when different_dimensions_only=False
        assert "a.dimension <> b.dimension" not in sql

    def test_midpoint_expressions(self):
        sql = _build_find_intersections_3d_sql(True)
        assert "mid_x" in sql
        assert "mid_y" in sql
        assert "mid_z" in sql

    def test_coordinate_extraction(self):
        sql = _build_find_intersections_3d_sql(True)
        assert "ST_X" in sql
        assert "ST_Y" in sql
        assert "ST_Z" in sql

    def test_ordered_by_distance(self):
        sql = _build_find_intersections_3d_sql(True)
        assert "ORDER BY" in sql and "distance" in sql


class TestBuildIntersections2dSql:
    """Validate the SQL string returned by ``_build_find_intersections_2d_sql``."""

    def test_contains_st_dwithin(self):
        sql = _build_find_intersections_2d_sql(True)
        assert "ST_DWithin" in sql

    def test_contains_st_distance(self):
        sql = _build_find_intersections_2d_sql(True)
        assert "ST_Distance" in sql

    def test_contains_table_name(self):
        sql = _build_find_intersections_2d_sql(True)
        assert "spatial_points_2d" in sql

    def test_deduplication_predicate(self):
        sql = _build_find_intersections_2d_sql(True)
        assert "a.id < b.id" in sql

    def test_scene_id_parameter(self):
        sql = _build_find_intersections_2d_sql(True)
        assert ":scene_id" in sql

    def test_tolerance_parameter(self):
        sql = _build_find_intersections_2d_sql(True)
        assert ":tolerance" in sql

    def test_dimension_filter_present_when_true(self):
        sql = _build_find_intersections_2d_sql(True)
        assert "dimension" in sql and "<>" in sql

    def test_dimension_filter_absent_when_false(self):
        sql = _build_find_intersections_2d_sql(False)
        assert "a.dimension <> b.dimension" not in sql

    def test_no_3d_functions(self):
        """2-D query must not reference 3-D PostGIS functions."""
        sql = _build_find_intersections_2d_sql(True)
        assert "ST_3D" not in sql

    def test_midpoint_expressions(self):
        sql = _build_find_intersections_2d_sql(True)
        assert "mid_x" in sql
        assert "mid_y" in sql


# ===========================================================================
# Offline tests – POSTGIS_AVAILABLE flag
# ===========================================================================

class TestPostgisAvailableFlag:
    def test_flag_is_bool(self):
        assert isinstance(POSTGIS_AVAILABLE, bool)

    def test_models_none_when_unavailable(self):
        if not POSTGIS_AVAILABLE:
            from computational_qr.database.spatial_models import (
                SpatialPoint2D,
                SpatialPoint3D,
            )
            assert SpatialPoint2D is None
            assert SpatialPoint3D is None

    @postgis_pkg
    def test_models_defined_when_available(self):
        from computational_qr.database.spatial_models import (
            SpatialPoint2D,
            SpatialPoint3D,
        )
        assert SpatialPoint2D is not None
        assert SpatialPoint3D is not None


# ===========================================================================
# Offline tests – PostGISIntersectionStore without geoalchemy2
# ===========================================================================

class TestPostGISStoreImportError:
    def test_raises_import_error_when_unavailable(self):
        if POSTGIS_AVAILABLE:
            pytest.skip("geoalchemy2 is installed; skipping import-error test")

        from computational_qr.database.postgis_store import PostGISIntersectionStore

        with pytest.raises(ImportError, match="GeoAlchemy2"):
            PostGISIntersectionStore("postgresql+psycopg://localhost/test")


# ===========================================================================
# Offline tests – model table/column metadata (only when geoalchemy2 present)
# ===========================================================================

@postgis_pkg
class TestSpatialModelMetadata:
    def test_2d_table_name(self):
        from computational_qr.database.spatial_models import SpatialPoint2D

        assert SpatialPoint2D.__tablename__ == "spatial_points_2d"

    def test_3d_table_name(self):
        from computational_qr.database.spatial_models import SpatialPoint3D

        assert SpatialPoint3D.__tablename__ == "spatial_points_3d"

    def test_2d_has_geom_column(self):
        from computational_qr.database.spatial_models import SpatialPoint2D

        cols = {c.name for c in SpatialPoint2D.__table__.columns}
        assert "geom" in cols

    def test_3d_has_geom_column(self):
        from computational_qr.database.spatial_models import SpatialPoint3D

        cols = {c.name for c in SpatialPoint3D.__table__.columns}
        assert "geom" in cols

    def test_2d_has_required_columns(self):
        from computational_qr.database.spatial_models import SpatialPoint2D

        cols = {c.name for c in SpatialPoint2D.__table__.columns}
        for expected in ("id", "scene_id", "label", "dimension", "value", "metadata"):
            assert expected in cols, f"Missing column: {expected}"

    def test_3d_has_required_columns(self):
        from computational_qr.database.spatial_models import SpatialPoint3D

        cols = {c.name for c in SpatialPoint3D.__table__.columns}
        for expected in ("id", "scene_id", "label", "dimension", "value", "metadata"):
            assert expected in cols, f"Missing column: {expected}"

    def test_2d_gist_index(self):
        from computational_qr.database.spatial_models import SpatialPoint2D

        index_names = {idx.name for idx in SpatialPoint2D.__table__.indexes}
        assert "idx_spatial_points_2d_geom" in index_names

    def test_3d_gist_index(self):
        from computational_qr.database.spatial_models import SpatialPoint3D

        index_names = {idx.name for idx in SpatialPoint3D.__table__.indexes}
        assert "idx_spatial_points_3d_geom" in index_names


# ===========================================================================
# Integration tests – require CQ_TEST_DATABASE_URL
# ===========================================================================

@integration
class TestPostGISIntegration:
    """Live PostGIS integration tests.

    Skipped unless ``CQ_TEST_DATABASE_URL`` is set to a PostGIS-enabled
    PostgreSQL connection string.
    """

    def setup_method(self):
        from computational_qr.database.postgis_store import PostGISIntersectionStore

        self.store = PostGISIntersectionStore(_CQ_DB_URL)
        self.scene_id = uuid.uuid4()

    def teardown_method(self):
        self.store.close()

    # ------------------------------------------------------------------
    # 3-D integration
    # ------------------------------------------------------------------

    def test_upsert_and_find_3d_no_intersections(self):
        from computational_qr.graphs.graph_3d import DataPoint

        pts = [
            DataPoint("A", 0.0, 0.0, 0.0, value=1.0, dimension=0),
            DataPoint("B", 100.0, 0.0, 0.0, value=2.0, dimension=1),
        ]
        self.store.upsert_scene_points_3d(self.scene_id, pts)
        result = self.store.find_intersections_3d(self.scene_id, tolerance=1.0)
        assert result == []

    def test_upsert_and_find_3d_with_intersection(self):
        from computational_qr.graphs.graph_3d import DataPoint

        pts = [
            DataPoint("A", 0.0, 0.0, 0.0, value=1.0, dimension=0),
            DataPoint("B", 0.5, 0.0, 0.0, value=2.0, dimension=1),
        ]
        self.store.upsert_scene_points_3d(self.scene_id, pts)
        result = self.store.find_intersections_3d(self.scene_id, tolerance=1.0)
        assert len(result) == 1
        ix = result[0]
        assert ix.distance == pytest.approx(0.5, abs=1e-6)
        assert ix.midpoint[0] == pytest.approx(0.25, abs=1e-6)

    def test_3d_cross_dimension_filter(self):
        """Same-dimension points must not appear when different_dimensions_only=True."""
        from computational_qr.graphs.graph_3d import DataPoint

        pts = [
            DataPoint("A", 0.0, 0.0, 0.0, value=1.0, dimension=0),
            DataPoint("B", 0.1, 0.0, 0.0, value=2.0, dimension=0),  # same dim
        ]
        self.store.upsert_scene_points_3d(self.scene_id, pts)
        result = self.store.find_intersections_3d(
            self.scene_id, tolerance=1.0, different_dimensions_only=True
        )
        assert result == []

    def test_3d_same_dimension_included_when_filter_off(self):
        from computational_qr.graphs.graph_3d import DataPoint

        pts = [
            DataPoint("A", 0.0, 0.0, 0.0, value=1.0, dimension=0),
            DataPoint("B", 0.1, 0.0, 0.0, value=2.0, dimension=0),
        ]
        self.store.upsert_scene_points_3d(self.scene_id, pts)
        result = self.store.find_intersections_3d(
            self.scene_id, tolerance=1.0, different_dimensions_only=False
        )
        assert len(result) == 1

    def test_3d_deduplication(self):
        """Each pair should appear exactly once (no reversed duplicates)."""
        from computational_qr.graphs.graph_3d import DataPoint

        pts = [
            DataPoint("A", 0.0, 0.0, 0.0, value=1.0, dimension=0),
            DataPoint("B", 0.2, 0.0, 0.0, value=2.0, dimension=1),
            DataPoint("C", 0.4, 0.0, 0.0, value=3.0, dimension=0),
        ]
        self.store.upsert_scene_points_3d(self.scene_id, pts)
        result = self.store.find_intersections_3d(self.scene_id, tolerance=1.0)
        labels = [(ix.point_a.label, ix.point_b.label) for ix in result]
        # No reversed duplicates
        for la, lb in labels:
            assert (lb, la) not in labels, f"Duplicate pair ({la},{lb}) found"

    def test_3d_matches_python_reference(self):
        """PostGIS results must match the pure-Python O(n²) reference."""
        from computational_qr.graphs.graph_3d import DataPoint, Graph3D

        pts = [
            DataPoint("A", 0.0, 0.0, 0.0, value=1.0, dimension=0),
            DataPoint("B", 0.5, 0.0, 0.0, value=2.0, dimension=1),
            DataPoint("C", 1.5, 0.0, 0.0, value=3.0, dimension=0),
            DataPoint("D", 0.6, 0.0, 0.0, value=4.0, dimension=1),
        ]
        tolerance = 1.0

        # Python reference
        g = Graph3D(tolerance=tolerance)
        g.add_points(pts)
        ref = g.find_intersections(cross_dimension_only=True)

        # PostGIS result
        self.store.upsert_scene_points_3d(self.scene_id, pts)
        db_result = self.store.find_intersections_3d(
            self.scene_id, tolerance=tolerance, different_dimensions_only=True
        )

        assert len(db_result) == len(ref)

    def test_upsert_is_idempotent(self):
        """Calling upsert twice for the same scene should not double the points."""
        from computational_qr.graphs.graph_3d import DataPoint

        pts = [
            DataPoint("A", 0.0, 0.0, 0.0, value=1.0, dimension=0),
            DataPoint("B", 0.5, 0.0, 0.0, value=2.0, dimension=1),
        ]
        self.store.upsert_scene_points_3d(self.scene_id, pts)
        self.store.upsert_scene_points_3d(self.scene_id, pts)  # second call
        result = self.store.find_intersections_3d(self.scene_id, tolerance=1.0)
        assert len(result) == 1  # still only one pair

    # ------------------------------------------------------------------
    # 2-D integration
    # ------------------------------------------------------------------

    def test_upsert_and_find_2d_with_intersection(self):
        from computational_qr.graphs.graph_3d import DataPoint

        pts = [
            DataPoint("A", 0.0, 0.0, 0.0, value=1.0, dimension=0),
            DataPoint("B", 0.3, 0.0, 0.0, value=2.0, dimension=1),
        ]
        self.store.upsert_scene_points_2d(self.scene_id, pts)
        result = self.store.find_intersections_2d(self.scene_id, tolerance=1.0)
        assert len(result) == 1
        assert result[0].distance == pytest.approx(0.3, abs=1e-6)
        assert result[0].midpoint[2] == pytest.approx(0.0)

    def test_context_manager(self):
        from computational_qr.database.postgis_store import PostGISIntersectionStore

        with PostGISIntersectionStore(_CQ_DB_URL) as store:
            assert store is not None
