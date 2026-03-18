"""Color geometry primitives for area shapes, keys, and legends on 3D QR graphs.

Area shapes encode data dimensions using hue, saturation, and lightness so that
keys and legends in a 3D graph can be derived purely from geometry rather than
relying on a separate 2-D colour table.
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Low-level colour helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _hsv_to_rgb_hex(hue: float, saturation: float, value: float) -> str:
    """Return a CSS hex colour string from HSV components (all in [0, 1])."""
    r, g, b = colorsys.hsv_to_rgb(
        _clamp(hue), _clamp(saturation), _clamp(value)
    )
    return "#{:02x}{:02x}{:02x}".format(
        round(r * 255), round(g * 255), round(b * 255)
    )


def _rgb_hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    """Parse a CSS hex colour and return (hue, saturation, value) in [0, 1]."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)


# ---------------------------------------------------------------------------
# ColorShape
# ---------------------------------------------------------------------------

@dataclass
class ColorShape:
    """An area shape that encodes a data value through colour geometry.

    Each shape occupies a region in 3D space (``x``, ``y``, ``z``) and maps a
    scalar ``value`` onto the HSV colour wheel so that colour *directly*
    encodes meaning—hue represents the data dimension, saturation represents
    confidence/weight, and value (brightness) represents magnitude.

    Parameters
    ----------
    label:
        Human-readable identifier for this shape.
    value:
        Scalar data value represented by this shape.
    x, y, z:
        Position in 3D graph space.
    dimension:
        Which data dimension this shape belongs to (0-based index).  The hue
        is derived automatically from the dimension and value together.
    weight:
        Relative weight / confidence in [0, 1]; mapped to saturation.
    shape_type:
        Geometry type: ``"circle"``, ``"polygon"``, ``"rect"``, or ``"star"``.
    """

    label: str
    value: float
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    dimension: int = 0
    weight: float = 1.0
    shape_type: str = "circle"

    # Derived – populated by __post_init__
    hue: float = field(init=False)
    saturation: float = field(init=False)
    brightness: float = field(init=False)
    color: str = field(init=False)

    def __post_init__(self) -> None:
        # Each dimension occupies a 1/8 slice of the hue wheel to keep
        # adjacent dimensions visually distinct.
        base_hue = (self.dimension % 8) / 8.0
        # Fine-tune hue by the normalised value so shapes within a dimension
        # drift slightly across the spectrum.
        value_norm = _clamp(abs(self.value) / (abs(self.value) + 1.0))
        self.hue = (base_hue + value_norm * 0.12) % 1.0
        self.saturation = _clamp(self.weight)
        self.brightness = _clamp(0.4 + value_norm * 0.6)
        self.color = _hsv_to_rgb_hex(self.hue, self.saturation, self.brightness)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def area(self) -> float:
        """Return a normalised area proportional to the data value."""
        return math.pi * (abs(self.value) ** 0.5 + 0.1) ** 2

    def vertices(self, n_sides: int = 6) -> list[tuple[float, float]]:
        """Return polygon vertices projected onto the XY plane.

        For circles/polygons the vertices are evenly spaced around the
        centroid; for rectangles two opposite corners are returned; for
        stars alternating vertices lie on inner/outer radii.
        """
        radius = math.sqrt(self.area() / math.pi)
        if self.shape_type == "rect":
            half = radius / math.sqrt(2)
            return [
                (self.x - half, self.y - half),
                (self.x + half, self.y + half),
            ]
        inner = radius * 0.4 if self.shape_type == "star" else radius
        sides = n_sides if self.shape_type != "circle" else 36
        pts: list[tuple[float, float]] = []
        for i in range(sides):
            angle = 2 * math.pi * i / sides
            r = inner if (self.shape_type == "star" and i % 2 == 1) else radius
            pts.append((self.x + r * math.cos(angle), self.y + r * math.sin(angle)))
        return pts

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary (JSON-safe)."""
        return {
            "label": self.label,
            "value": self.value,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "dimension": self.dimension,
            "weight": self.weight,
            "shape_type": self.shape_type,
            "color": self.color,
            "hue": round(self.hue, 6),
            "saturation": round(self.saturation, 6),
            "brightness": round(self.brightness, 6),
            "area": round(self.area(), 6),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ColorShape":
        return cls(
            label=data["label"],
            value=data["value"],
            x=data.get("x", 0.0),
            y=data.get("y", 0.0),
            z=data.get("z", 0.0),
            dimension=data.get("dimension", 0),
            weight=data.get("weight", 1.0),
            shape_type=data.get("shape_type", "circle"),
        )


# ---------------------------------------------------------------------------
# GeometryKey
# ---------------------------------------------------------------------------

@dataclass
class GeometryKey:
    """A key / legend entry that maps a data dimension to a colour range.

    A ``GeometryKey`` describes what a particular *dimension* of data means
    inside a 3D graph—its human-readable name, the unit of measurement, and
    the colour range used for that dimension.

    Parameters
    ----------
    name:
        Display name for the dimension (e.g. ``"Temperature"``).
    dimension:
        Zero-based index matching ``ColorShape.dimension``.
    unit:
        Unit string (e.g. ``"°C"``).
    min_value, max_value:
        Domain of values for this dimension.
    """

    name: str
    dimension: int
    unit: str = ""
    min_value: float = 0.0
    max_value: float = 1.0

    def color_for(self, value: float) -> str:
        """Return the hex colour that represents *value* within this key."""
        shape = ColorShape(
            label="",
            value=value,
            dimension=self.dimension,
            weight=1.0,
        )
        return shape.color

    def gradient(self, steps: int = 8) -> list[tuple[float, str]]:
        """Return ``steps`` evenly-spaced (value, colour) pairs across the domain."""
        span = self.max_value - self.min_value
        result: list[tuple[float, str]] = []
        for i in range(steps):
            v = self.min_value + span * i / max(steps - 1, 1)
            result.append((round(v, 6), self.color_for(v)))
        return result

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "dimension": self.dimension,
            "unit": self.unit,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "gradient": self.gradient(),
        }


# ---------------------------------------------------------------------------
# ColorGeometry – collection manager
# ---------------------------------------------------------------------------

class ColorGeometry:
    """Manages a collection of :class:`ColorShape` objects and their keys.

    ``ColorGeometry`` is the entry point for building colour-coded 3D graphs.
    It assigns dimensions automatically and keeps an internal
    :class:`GeometryKey` registry so that graph renderers can draw consistent
    legends.

    Example
    -------
    >>> cg = ColorGeometry()
    >>> cg.add_dimension("Temperature", unit="°C", min_value=-20, max_value=40)
    >>> cg.add_shape("T₀", value=22.5, x=1.0, y=2.0, z=0.5, dimension=0)
    """

    def __init__(self) -> None:
        self._shapes: list[ColorShape] = []
        self._keys: dict[int, GeometryKey] = {}

    # ------------------------------------------------------------------
    # Dimension / key management
    # ------------------------------------------------------------------

    def add_dimension(
        self,
        name: str,
        *,
        unit: str = "",
        min_value: float = 0.0,
        max_value: float = 1.0,
    ) -> int:
        """Register a new data dimension and return its index."""
        idx = len(self._keys)
        self._keys[idx] = GeometryKey(
            name=name,
            dimension=idx,
            unit=unit,
            min_value=min_value,
            max_value=max_value,
        )
        return idx

    def key(self, dimension: int) -> GeometryKey:
        if dimension not in self._keys:
            raise KeyError(f"Dimension {dimension} not registered.")
        return self._keys[dimension]

    @property
    def keys(self) -> list[GeometryKey]:
        return list(self._keys.values())

    # ------------------------------------------------------------------
    # Shape management
    # ------------------------------------------------------------------

    def add_shape(
        self,
        label: str,
        *,
        value: float,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        dimension: int = 0,
        weight: float = 1.0,
        shape_type: str = "circle",
    ) -> ColorShape:
        """Create a :class:`ColorShape` and add it to the collection."""
        shape = ColorShape(
            label=label,
            value=value,
            x=x,
            y=y,
            z=z,
            dimension=dimension,
            weight=weight,
            shape_type=shape_type,
        )
        self._shapes.append(shape)
        return shape

    def shapes_for_dimension(self, dimension: int) -> list[ColorShape]:
        return [s for s in self._shapes if s.dimension == dimension]

    @property
    def shapes(self) -> list[ColorShape]:
        return list(self._shapes)

    # ------------------------------------------------------------------
    # Intersection helpers
    # ------------------------------------------------------------------

    def intersecting_shapes(
        self, shapes: Sequence[ColorShape], tolerance: float = 0.5
    ) -> list[tuple[ColorShape, ColorShape]]:
        """Return pairs of shapes whose 3D positions are within *tolerance*.

        This identifies where data from different dimensions *intersects* in
        3D space—a core concept of computational QR where the graph is not
        constrained to 2D rows and columns.
        """
        pairs: list[tuple[ColorShape, ColorShape]] = []
        items = list(shapes)
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                dist = math.sqrt(
                    (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2
                )
                if dist <= tolerance:
                    pairs.append((a, b))
        return pairs

    def find_intersections(
        self, tolerance: float = 0.5
    ) -> list[tuple[ColorShape, ColorShape]]:
        """Find intersecting shapes across *all* registered dimensions."""
        return self.intersecting_shapes(self._shapes, tolerance=tolerance)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "keys": [k.to_dict() for k in self._keys.values()],
            "shapes": [s.to_dict() for s in self._shapes],
        }
