"""computational_qr.core – colour geometry and base QR encoding."""

from .color_geometry import ColorShape, GeometryKey, ColorGeometry
from .qr_encoder import QREncoder, QRData

__all__ = [
    "ColorShape",
    "GeometryKey",
    "ColorGeometry",
    "QREncoder",
    "QRData",
]
