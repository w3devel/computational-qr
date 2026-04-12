"""
hashing.py – BLAKE3-based hash helpers.

Two identities are distinguished throughout the CQR pipeline:

* ``data_hash``   – BLAKE3 digest of the raw *data bytes*.  This is the
  stable, canonical identity of a self-contained glyph (one that embeds
  the data directly in the payload).  It does not change as graph-codec
  rules evolve.

* ``graph_hash``  – lives in ``graph.py``.  It is the BLAKE3 digest of
  the *canonical graph bytes* (the serialised NetworkX graph after
  deterministic canonicalisation).  This is the primary key when the
  glyph is DB-referencing rather than self-contained.

Both always appear in every payload so that decoders can choose which
identity to use without having to re-encode.
"""

from __future__ import annotations

import blake3 as _blake3


def data_hash(data_bytes: bytes) -> bytes:
    """Return the 32-byte BLAKE3 digest of *data_bytes*.

    Parameters
    ----------
    data_bytes:
        The raw bytes whose identity you want to capture.

    Returns
    -------
    bytes
        32-byte (256-bit) BLAKE3 digest.
    """
    return _blake3.blake3(data_bytes).digest()
