"""Add PostGIS spatial tables for intersection/proximity queries.

Revision ID: 3a9f2b8c1d4e
Revises:
Create Date: 2026-03-23 20:41:13.961000

Applies to **PostgreSQL + PostGIS only**.

Upgrade steps
-------------
1. Enables the ``postgis`` extension (idempotent).
2. Creates ``spatial_points_2d`` with a GiST index on the geometry column.
3. Creates ``spatial_points_3d`` with a GiST index on the geometry column.

Downgrade steps
---------------
Drops both spatial tables (the ``postgis`` extension is left in place as it may
be shared with other schemas).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "3a9f2b8c1d4e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create PostGIS extension and spatial tables."""

    # ------------------------------------------------------------------ #
    # Extension                                                            #
    # ------------------------------------------------------------------ #
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ------------------------------------------------------------------ #
    # spatial_points_2d                                                    #
    # ------------------------------------------------------------------ #
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS spatial_points_2d (
            id        UUID            PRIMARY KEY,
            scene_id  UUID            NOT NULL,
            label     TEXT            NOT NULL,
            dimension INTEGER,
            value     DOUBLE PRECISION,
            metadata  JSONB,
            geom      geometry(POINT, 0) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_spatial_points_2d_scene_id "
        "ON spatial_points_2d (scene_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_spatial_points_2d_geom "
        "ON spatial_points_2d USING GIST (geom)"
    )

    # ------------------------------------------------------------------ #
    # spatial_points_3d                                                    #
    # ------------------------------------------------------------------ #
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS spatial_points_3d (
            id        UUID             PRIMARY KEY,
            scene_id  UUID             NOT NULL,
            label     TEXT             NOT NULL,
            dimension INTEGER,
            value     DOUBLE PRECISION,
            metadata  JSONB,
            geom      geometry(POINTZ, 0) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_spatial_points_3d_scene_id "
        "ON spatial_points_3d (scene_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_spatial_points_3d_geom "
        "ON spatial_points_3d USING GIST (geom)"
    )


def downgrade() -> None:
    """Drop spatial tables (PostGIS extension is left installed)."""
    op.execute("DROP TABLE IF EXISTS spatial_points_3d")
    op.execute("DROP TABLE IF EXISTS spatial_points_2d")
