"""
computational_qr.cqr – Computational QR payload + canonical graph hashing.

Submodules
----------
hashing     BLAKE3-based data_hash and graph_hash helpers.
graph       Deterministic NetworkX graph canonicalization.
payload     Binary payload pack/unpack (magic, flags, hashes, CRC32C, …).
cli         Command-line encode/decode interface.
"""

from .hashing import data_hash
from .graph import canonical_graph_bytes, graph_hash
from .payload import pack, unpack, PayloadError

__all__ = [
    "data_hash",
    "canonical_graph_bytes",
    "graph_hash",
    "pack",
    "unpack",
    "PayloadError",
]
