"""3D graph visualisation with non-2D data intersections.

``Graph3D`` places :class:`~computational_qr.core.ColorShape` objects at
arbitrary (x, y, z) co-ordinates and detects where data from different
dimensions *intersects* in 3D space—going beyond a flat 2-D grid of rows and
columns.  Optionally, the graph can be rendered to a Matplotlib figure or
exported as a QR-embeddable JSON descriptor.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class DataPoint:
    """A single datum placed in 3D graph space.

    Parameters
    ----------
    label:
        Human-readable identifier.
    x, y, z:
        Co-ordinates in graph space (not constrained to integer rows/cols).
    value:
        Scalar magnitude of the data point.
    dimension:
        Data dimension (maps to a colour via :class:`~computational_qr.core.ColorGeometry`).
    metadata:
        Arbitrary key-value annotations.
    """

    label: str
    x: float
    y: float
    z: float
    value: float
    dimension: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def distance_to(self, other: "DataPoint") -> float:
        """Euclidean distance in 3D space to *other*."""
        return math.sqrt(
            (self.x - other.x) ** 2
            + (self.y - other.y) ** 2
            + (self.z - other.z) ** 2
        )

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "value": self.value,
            "dimension": self.dimension,
            "metadata": self.metadata,
        }


@dataclass
class Intersection:
    """A point where two :class:`DataPoint` objects from different dimensions meet.

    Parameters
    ----------
    point_a, point_b:
        The two intersecting data points.
    distance:
        The actual 3D distance between them (≤ the tolerance threshold).
    midpoint:
        The geometric midpoint between the two points.
    """

    point_a: DataPoint
    point_b: DataPoint
    distance: float
    midpoint: tuple[float, float, float]

    @property
    def label(self) -> str:
        return f"{self.point_a.label}∩{self.point_b.label}"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "point_a": self.point_a.to_dict(),
            "point_b": self.point_b.to_dict(),
            "distance": round(self.distance, 6),
            "midpoint": {
                "x": round(self.midpoint[0], 6),
                "y": round(self.midpoint[1], 6),
                "z": round(self.midpoint[2], 6),
            },
        }


class Graph3D:
    """3D graph that holds :class:`DataPoint` objects at arbitrary positions.

    Unlike a traditional 2-D grid the points are free to occupy any
    (x, y, z) co-ordinate.  :meth:`find_intersections` identifies where data
    from *different* dimensions comes within a configurable *tolerance* of each
    other—these intersections are the computational events that a QR code in
    this system can represent.

    Parameters
    ----------
    tolerance:
        Maximum 3D Euclidean distance between two points for them to be
        considered intersecting.  Defaults to 1.0.
    """

    def __init__(self, tolerance: float = 1.0) -> None:
        self.tolerance = tolerance
        self._points: list[DataPoint] = []
        self._dimension_labels: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Dimension registration
    # ------------------------------------------------------------------

    def register_dimension(self, index: int, label: str) -> None:
        """Associate a human-readable *label* with a dimension *index*."""
        self._dimension_labels[index] = label

    def dimension_label(self, index: int) -> str:
        return self._dimension_labels.get(index, f"dim_{index}")

    # ------------------------------------------------------------------
    # Data management
    # ------------------------------------------------------------------

    def add_point(
        self,
        label: str,
        x: float,
        y: float,
        z: float,
        value: float,
        *,
        dimension: int = 0,
        metadata: dict | None = None,
    ) -> DataPoint:
        """Add a :class:`DataPoint` to the graph and return it."""
        pt = DataPoint(
            label=label,
            x=x,
            y=y,
            z=z,
            value=value,
            dimension=dimension,
            metadata=metadata or {},
        )
        self._points.append(pt)
        return pt

    def add_points(self, points: Sequence[DataPoint]) -> None:
        """Bulk-add an iterable of :class:`DataPoint` objects."""
        self._points.extend(points)

    @property
    def points(self) -> list[DataPoint]:
        return list(self._points)

    def points_in_dimension(self, dimension: int) -> list[DataPoint]:
        return [p for p in self._points if p.dimension == dimension]

    # ------------------------------------------------------------------
    # Intersection detection
    # ------------------------------------------------------------------

    def find_intersections(
        self, cross_dimension_only: bool = True
    ) -> list[Intersection]:
        """Find all pairs of points within :attr:`tolerance` of each other.

        Parameters
        ----------
        cross_dimension_only:
            When ``True`` (default) only report intersections between points
            belonging to *different* dimensions—this is the core non-2D
            intersection concept.  Set to ``False`` to also include same-
            dimension proximity.

        Returns
        -------
        list[Intersection]
            Sorted by ascending distance.
        """
        results: list[Intersection] = []
        pts = self._points
        for i, a in enumerate(pts):
            for b in pts[i + 1 :]:
                if cross_dimension_only and a.dimension == b.dimension:
                    continue
                dist = a.distance_to(b)
                if dist <= self.tolerance:
                    mid = (
                        (a.x + b.x) / 2,
                        (a.y + b.y) / 2,
                        (a.z + b.z) / 2,
                    )
                    results.append(Intersection(a, b, dist, mid))
        results.sort(key=lambda ix: ix.distance)
        return results

    # ------------------------------------------------------------------
    # Visualisation (optional – requires matplotlib)
    # ------------------------------------------------------------------

    def render(
        self,
        title: str = "Computational QR – 3D Graph",
        show_intersections: bool = True,
        figsize: tuple[float, float] = (10.0, 8.0),
    ):
        """Render the graph with Matplotlib and return the ``Figure``.

        Requires ``matplotlib``.  Each dimension gets a distinct marker colour
        derived from its index.  Intersections are highlighted with a red 'X'.

        Returns
        -------
        matplotlib.figure.Figure
        """
        try:
            import matplotlib.pyplot as plt  # type: ignore
            from mpl_toolkits.mplot3d import Axes3D  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Rendering requires matplotlib: pip install matplotlib"
            ) from exc

        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111, projection="3d")

        # Collect unique dimensions
        dims = sorted({p.dimension for p in self._points})
        cmap = plt.cm.get_cmap("tab10", max(len(dims), 1))

        for dim_idx, dim in enumerate(dims):
            pts = self.points_in_dimension(dim)
            xs = [p.x for p in pts]
            ys = [p.y for p in pts]
            zs = [p.z for p in pts]
            sizes = [max(20, abs(p.value) * 10) for p in pts]
            color = cmap(dim_idx)
            dim_label = self.dimension_label(dim)
            ax.scatter(xs, ys, zs, s=sizes, c=[color] * len(pts), label=dim_label, alpha=0.8)
            for p in pts:
                ax.text(p.x, p.y, p.z, p.label, fontsize=7, color=color)

        if show_intersections:
            ixs = self.find_intersections()
            for ix in ixs:
                mx, my, mz = ix.midpoint
                ax.scatter([mx], [my], [mz], s=60, c="red", marker="X", zorder=5)

        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.set_title(title)
        ax.legend(loc="upper left", fontsize=8)
        return fig

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "tolerance": self.tolerance,
            "dimensions": self._dimension_labels,
            "points": [p.to_dict() for p in self._points],
            "intersections": [i.to_dict() for i in self.find_intersections()],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
