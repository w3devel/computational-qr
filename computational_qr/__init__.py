"""
computational_qr – QR as a computational medium.

Modules
-------
core         Color geometry and base QR encoding utilities.
graphs       3D graph visualisation with arbitrary data intersections.
prolog       Prolog logic engine, encoder/decoder, and QR storage.
media        Audio QR and SVG/video QR generation.
quantum      Quantum-math primitives for QR state representation.
database     Neo4j graph-database integration.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("computational-qr")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = [
    "core",
    "graphs",
    "prolog",
    "media",
    "quantum",
    "database",
]
