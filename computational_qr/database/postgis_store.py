"""PostGIS-backed spatial intersection / proximity store.

``PostGISIntersectionStore`` accelerates the O(n²) intersection loops in
:class:`~computational_qr.graphs.graph_3d.Graph3D` and
:class:`~computational_qr.core.color_geometry.ColorGeometry` by offloading
proximity detection to the database via PostGIS spatial indexes and functions.

Requires the optional **postgis** extra::

    pip install 'computational-qr[orm,postgres,postgis]'

Usage example::

    import uuid
    from computational_qr.database.postgis_store import PostGISIntersectionStore
    from computational_qr.graphs.graph_3d import Graph3D

    store = PostGISIntersectionStore("postgresql+psycopg://user:pw@localhost/qrdb")

    g = Graph3D(tolerance=1.0)
    g.register_dimension(0, "Temperature")
    g.register_dimension(1, "Pressure")
    g.add_point("T0", 1.0, 2.0, 0.5, value=25.0, dimension=0)
    g.add_point("P0", 1.1, 2.1, 0.4, value=101.3, dimension=1)

    scene = uuid.uuid4()
    store.upsert_scene_points_3d(scene, g.points)
    intersections = store.find_intersections_3d(scene, tolerance=1.0)
    for ix in intersections:
        print(ix.label, ix.distance)

    store.close()
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Sequence

try:
    from geoalchemy2.elements import WKTElement  # type: ignore[import-untyped]

    _GEOALCHEMY2_AVAILABLE = True
except ImportError:
    _GEOALCHEMY2_AVAILABLE = False
    WKTElement = None  # type: ignore[assignment,misc]

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from computational_qr.graphs.graph_3d import DataPoint, Intersection


def _require_postgis() -> None:
    """Raise :exc:`ImportError` if GeoAlchemy2 is not installed."""
    if not _GEOALCHEMY2_AVAILABLE:
        raise ImportError(
            "PostGIS support requires GeoAlchemy2. "
            "Install it with: pip install 'computational-qr[postgis]'"
        )


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _build_find_intersections_3d_sql(different_dimensions_only: bool) -> str:
    """Return the SQL string for a 3-D proximity query.

    Parameters
    ----------
    different_dimensions_only:
        When ``True``, adds ``AND a.dimension <> b.dimension`` to the
        ``WHERE`` clause, mirroring the semantics of
        :meth:`~computational_qr.graphs.graph_3d.Graph3D.find_intersections`.
    """
    dim_filter = "AND a.dimension <> b.dimension" if different_dimensions_only else ""
    return f"""
        SELECT
            a.label     AS label_a,
            a.dimension AS dim_a,
            a.value     AS val_a,
            a.metadata  AS metadata_a,
            b.label     AS label_b,
            b.dimension AS dim_b,
            b.value     AS val_b,
            b.metadata  AS metadata_b,
            ST_3DDistance(a.geom, b.geom)              AS distance,
            (ST_X(a.geom) + ST_X(b.geom)) / 2.0        AS mid_x,
            (ST_Y(a.geom) + ST_Y(b.geom)) / 2.0        AS mid_y,
            (ST_Z(a.geom) + ST_Z(b.geom)) / 2.0        AS mid_z,
            ST_X(a.geom)  AS ax,
            ST_Y(a.geom)  AS ay,
            ST_Z(a.geom)  AS az,
            ST_X(b.geom)  AS bx,
            ST_Y(b.geom)  AS by,
            ST_Z(b.geom)  AS bz
        FROM spatial_points_3d a
        JOIN spatial_points_3d b
          ON a.id < b.id
         AND a.scene_id = b.scene_id
        WHERE a.scene_id = :scene_id
          AND ST_3DDWithin(a.geom, b.geom, :tolerance)
          {dim_filter}
        ORDER BY distance
    """


def _build_find_intersections_2d_sql(different_dimensions_only: bool) -> str:
    """Return the SQL string for a 2-D proximity query.

    Uses ``ST_DWithin`` (2-D distance, ignores the Z ordinate) and
    ``ST_Distance`` for the returned distance value.

    Parameters
    ----------
    different_dimensions_only:
        When ``True``, adds ``AND a.dimension <> b.dimension``.
    """
    dim_filter = "AND a.dimension <> b.dimension" if different_dimensions_only else ""
    return f"""
        SELECT
            a.label     AS label_a,
            a.dimension AS dim_a,
            a.value     AS val_a,
            a.metadata  AS metadata_a,
            b.label     AS label_b,
            b.dimension AS dim_b,
            b.value     AS val_b,
            b.metadata  AS metadata_b,
            ST_Distance(a.geom, b.geom)                AS distance,
            (ST_X(a.geom) + ST_X(b.geom)) / 2.0        AS mid_x,
            (ST_Y(a.geom) + ST_Y(b.geom)) / 2.0        AS mid_y,
            ST_X(a.geom)  AS ax,
            ST_Y(a.geom)  AS ay,
            ST_X(b.geom)  AS bx,
            ST_Y(b.geom)  AS by
        FROM spatial_points_2d a
        JOIN spatial_points_2d b
          ON a.id < b.id
         AND a.scene_id = b.scene_id
        WHERE a.scene_id = :scene_id
          AND ST_DWithin(a.geom, b.geom, :tolerance)
          {dim_filter}
        ORDER BY distance
    """


def _row_to_intersection(row: Any) -> Intersection:
    """Convert a ``find_intersections_3d`` result row to an :class:`Intersection`."""
    point_a = DataPoint(
        label=row.label_a,
        x=float(row.ax),
        y=float(row.ay),
        z=float(row.az),
        value=float(row.val_a) if row.val_a is not None else 0.0,
        dimension=int(row.dim_a) if row.dim_a is not None else 0,
        metadata=row.metadata_a or {},
    )
    point_b = DataPoint(
        label=row.label_b,
        x=float(row.bx),
        y=float(row.by),
        z=float(row.bz),
        value=float(row.val_b) if row.val_b is not None else 0.0,
        dimension=int(row.dim_b) if row.dim_b is not None else 0,
        metadata=row.metadata_b or {},
    )
    midpoint = (float(row.mid_x), float(row.mid_y), float(row.mid_z))
    return Intersection(point_a, point_b, float(row.distance), midpoint)


def _row_to_intersection_2d(row: Any) -> Intersection:
    """Convert a ``find_intersections_2d`` result row to an :class:`Intersection`.

    The Z coordinate is set to ``0.0`` since the 2-D table stores flat points.
    """
    point_a = DataPoint(
        label=row.label_a,
        x=float(row.ax),
        y=float(row.ay),
        z=0.0,
        value=float(row.val_a) if row.val_a is not None else 0.0,
        dimension=int(row.dim_a) if row.dim_a is not None else 0,
        metadata=row.metadata_a or {},
    )
    point_b = DataPoint(
        label=row.label_b,
        x=float(row.bx),
        y=float(row.by),
        z=0.0,
        value=float(row.val_b) if row.val_b is not None else 0.0,
        dimension=int(row.dim_b) if row.dim_b is not None else 0,
        metadata=row.metadata_b or {},
    )
    midpoint = (float(row.mid_x), float(row.mid_y), 0.0)
    return Intersection(point_a, point_b, float(row.distance), midpoint)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class PostGISIntersectionStore:
    """PostGIS-backed store for proximity / intersection queries.

    Parameters
    ----------
    database_url:
        SQLAlchemy connection URL for a PostgreSQL database with the
        PostGIS extension enabled, e.g.
        ``"postgresql+psycopg://user:pw@localhost/qrdb"``.
    echo:
        When ``True`` SQLAlchemy logs all emitted SQL statements (useful for
        debugging).

    Raises
    ------
    ImportError
        If GeoAlchemy2 is not installed.
    """

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        _require_postgis()
        self._engine = create_engine(database_url, echo=echo)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Dispose of the underlying SQLAlchemy engine connection pool."""
        self._engine.dispose()

    def __enter__(self) -> "PostGISIntersectionStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Bulk load – 3-D points
    # ------------------------------------------------------------------

    def upsert_scene_points_3d(
        self,
        scene_id: uuid.UUID,
        points: Sequence[DataPoint],
    ) -> None:
        """Replace all 3-D points for *scene_id* with *points*.

        Existing rows for *scene_id* are deleted before the new rows are
        inserted, making this operation idempotent for the same scene.

        Parameters
        ----------
        scene_id:
            Identifier for the computation scene.
        points:
            Sequence of :class:`~computational_qr.graphs.graph_3d.DataPoint`
            objects to store.
        """
        with Session(self._engine) as session:
            session.execute(
                text(
                    "DELETE FROM spatial_points_3d WHERE scene_id = :scene_id"
                ),
                {"scene_id": str(scene_id)},
            )
            rows = [
                {
                    "id": str(uuid.uuid4()),
                    "scene_id": str(scene_id),
                    "label": pt.label,
                    "dimension": pt.dimension,
                    "value": pt.value,
                    "metadata": json.dumps(pt.metadata) if pt.metadata else None,
                    "wkt": f"POINT Z ({pt.x} {pt.y} {pt.z})",
                }
                for pt in points
            ]
            if rows:
                session.execute(
                    text(
                        """
                        INSERT INTO spatial_points_3d
                            (id, scene_id, label, dimension, value, metadata, geom)
                        VALUES
                            (:id, CAST(:scene_id AS UUID), :label, :dimension,
                             :value, CAST(:metadata AS JSONB),
                             ST_GeomFromText(:wkt, 0))
                        """
                    ),
                    rows,
                )
            session.commit()

    # ------------------------------------------------------------------
    # Bulk load – 2-D points
    # ------------------------------------------------------------------

    def upsert_scene_points_2d(
        self,
        scene_id: uuid.UUID,
        points: Sequence[Any],
    ) -> None:
        """Replace all 2-D points for *scene_id*.

        *points* should be objects with ``label``, ``x``, ``y``,
        ``dimension``, ``value``, and ``metadata`` attributes (e.g.
        :class:`~computational_qr.core.color_geometry.ColorShape` or
        :class:`~computational_qr.graphs.graph_3d.DataPoint`).

        Parameters
        ----------
        scene_id:
            Identifier for the computation scene.
        points:
            Sequence of point-like objects.
        """
        with Session(self._engine) as session:
            session.execute(
                text(
                    "DELETE FROM spatial_points_2d WHERE scene_id = :scene_id"
                ),
                {"scene_id": str(scene_id)},
            )
            rows = [
                {
                    "id": str(uuid.uuid4()),
                    "scene_id": str(scene_id),
                    "label": pt.label,
                    "dimension": getattr(pt, "dimension", None),
                    "value": getattr(pt, "value", None),
                    "metadata": (
                        json.dumps(pt.metadata)
                        if getattr(pt, "metadata", None)
                        else None
                    ),
                    "wkt": f"POINT ({pt.x} {pt.y})",
                }
                for pt in points
            ]
            if rows:
                session.execute(
                    text(
                        """
                        INSERT INTO spatial_points_2d
                            (id, scene_id, label, dimension, value, metadata, geom)
                        VALUES
                            (:id, CAST(:scene_id AS UUID), :label, :dimension,
                             :value, CAST(:metadata AS JSONB),
                             ST_GeomFromText(:wkt, 0))
                        """
                    ),
                    rows,
                )
            session.commit()

    # ------------------------------------------------------------------
    # Intersection queries – 3-D
    # ------------------------------------------------------------------

    def find_intersections_3d(
        self,
        scene_id: uuid.UUID,
        tolerance: float,
        *,
        different_dimensions_only: bool = True,
    ) -> list[Intersection]:
        """Find all intersecting point pairs within *tolerance* using PostGIS.

        Uses ``ST_3DDWithin`` for efficient GiST-indexed proximity filtering
        and ``ST_3DDistance`` for the returned distance value.

        Duplicate pairs are avoided by the ``a.id < b.id`` constraint.

        Parameters
        ----------
        scene_id:
            Scene to query.
        tolerance:
            Maximum 3-D Euclidean distance between two points for them to be
            considered intersecting.
        different_dimensions_only:
            When ``True`` (default) only report intersections between points
            in *different* dimensions—mirrors the semantics of
            :meth:`~computational_qr.graphs.graph_3d.Graph3D.find_intersections`.

        Returns
        -------
        list[Intersection]
            Sorted by ascending distance.
        """
        sql = text(
            _build_find_intersections_3d_sql(different_dimensions_only)
        )
        with Session(self._engine) as session:
            rows = session.execute(
                sql,
                {"scene_id": str(scene_id), "tolerance": float(tolerance)},
            ).fetchall()
        return [_row_to_intersection(r) for r in rows]

    # ------------------------------------------------------------------
    # Intersection queries – 2-D
    # ------------------------------------------------------------------

    def find_intersections_2d(
        self,
        scene_id: uuid.UUID,
        tolerance: float,
        *,
        different_dimensions_only: bool = True,
    ) -> list[Intersection]:
        """Find all intersecting point pairs within *tolerance* using PostGIS.

        Uses ``ST_DWithin`` (2-D distance, Z ordinate ignored) for
        GiST-indexed proximity filtering.

        Parameters
        ----------
        scene_id:
            Scene to query.
        tolerance:
            Maximum 2-D planar distance between two points for them to be
            considered intersecting.
        different_dimensions_only:
            When ``True`` (default) only report intersections between points
            in *different* dimensions.

        Returns
        -------
        list[Intersection]
            Sorted by ascending distance.  The ``z`` coordinate of
            :class:`~computational_qr.graphs.graph_3d.DataPoint` objects and
            the midpoint tuple will always be ``0.0``.
        """
        sql = text(
            _build_find_intersections_2d_sql(different_dimensions_only)
        )
        with Session(self._engine) as session:
            rows = session.execute(
                sql,
                {"scene_id": str(scene_id), "tolerance": float(tolerance)},
            ).fetchall()
        return [_row_to_intersection_2d(r) for r in rows]


__all__ = [
    "PostGISIntersectionStore",
    "_build_find_intersections_3d_sql",
    "_build_find_intersections_2d_sql",
]
