"""
payload.py – Binary payload pack / unpack for the Computational QR format.

Payload layout
--------------
::

    +-----------+-------+---------------------------------------------+
    | Field             | Size       | Notes                           |
    +-------------------+------------+---------------------------------+
    | magic             | 4 bytes    | b"CQR\\x00"                     |
    | version           | 1 byte     | currently 0x01                  |
    | flags             | 1 byte     | bit 0: has_embedded_data        |
    |                   |            | bit 1: has_index_key            |
    | data_hash         | 32 bytes   | BLAKE3(data_bytes)              |
    | graph_hash        | 32 bytes   | BLAKE3(canonical_graph_bytes)   |
    | graph_codec_id    | 1 byte     | identifies canonicalization algo|
    | graph_codec_ver   | 1 byte     | version within that algo        |
    | [key block]       | variable   | present when has_index_key=1    |
    |   key_type        | 1 byte     | 0=raw, 1=uuid, 2=int, 3=path   |
    |   key_len         | varint     | byte length of key_bytes        |
    |   key_bytes       | key_len    |                                 |
    | [data block]      | variable   | present when has_embedded_data=1|
    |   data_codec      | 1 byte     | 1=zstd, 2=gzip                  |
    |   orig_len        | varint     | original (uncompressed) length  |
    |   comp_len        | varint     | compressed length               |
    |   comp_bytes      | comp_len   |                                 |
    | crc32c            | 4 bytes    | CRC32C of all preceding bytes   |
    +-------------------+------------+---------------------------------+

Compression
-----------
The preferred codec is **zstandard** (``data_codec = 0x01``).  If
``zstandard`` is not importable at runtime, the implementation falls back
to **gzip / zlib** (``data_codec = 0x02``).  Both codecs are auto-detected
during unpack.

CRC32C
------
``crc32c`` (hardware-accelerated) is tried first; the implementation falls
back to a pure-Python CRC32C implementation derived from the standard
``binascii.crc32`` polynomial adapted to the Castagnoli (0x1EDC6F41)
polynomial using a precomputed lookup table.

Varint encoding
---------------
Variable-length unsigned integers use the same encoding as Protocol Buffers
/ LEB128: 7 payload bits per byte, MSB = "more bytes follow".  The encoding
supports arbitrary non-negative integers; values ≤ 127 fit in one byte.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Optional dependencies with fallbacks
# ---------------------------------------------------------------------------

try:
    import crc32c as _crc32c_mod

    def _crc32c(data: bytes) -> int:
        return _crc32c_mod.crc32c(data)

except ImportError:
    # Pure-Python CRC32C (Castagnoli, poly=0x1EDC6F41) lookup table.
    def _build_crc32c_table() -> list[int]:
        poly = 0x82F63B78  # reflected form of 0x1EDC6F41
        tbl: list[int] = []
        for i in range(256):
            crc = i
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ poly
                else:
                    crc >>= 1
            tbl.append(crc)
        return tbl

    _CRC32C_TABLE = _build_crc32c_table()

    def _crc32c(data: bytes) -> int:  # type: ignore[misc]
        crc = 0xFFFFFFFF
        for byte in data:
            crc = (crc >> 8) ^ _CRC32C_TABLE[(crc ^ byte) & 0xFF]
        return crc ^ 0xFFFFFFFF


try:
    import zstandard as _zstd

    def _compress(data: bytes) -> tuple[int, bytes]:
        """Return (codec_byte, compressed_bytes)."""
        return 0x01, _zstd.ZstdCompressor(level=3).compress(data)

    def _decompress_zstd(comp: bytes) -> bytes:
        return _zstd.ZstdDecompressor().decompress(comp)

except ImportError:
    _zstd = None  # type: ignore[assignment]

    def _compress(data: bytes) -> tuple[int, bytes]:  # type: ignore[misc]
        return 0x02, zlib.compress(data, level=6)

    def _decompress_zstd(comp: bytes) -> bytes:  # type: ignore[misc]
        raise NotImplementedError("zstandard not installed")


def _decompress_gzip(comp: bytes) -> bytes:
    return zlib.decompress(comp)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAGIC = b"CQR\x00"
VERSION = 0x01

FLAG_HAS_EMBEDDED_DATA: int = 0x01
FLAG_HAS_INDEX_KEY: int = 0x02

DATA_CODEC_ZSTD: int = 0x01
DATA_CODEC_GZIP: int = 0x02

KEY_TYPE_RAW: int = 0x00
KEY_TYPE_UUID: int = 0x01
KEY_TYPE_INT: int = 0x02
KEY_TYPE_PATH: int = 0x03


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PayloadError(Exception):
    """Raised when payload parsing fails (bad magic, CRC mismatch, …)."""


# ---------------------------------------------------------------------------
# Varint (LEB128-style unsigned)
# ---------------------------------------------------------------------------

def encode_varint(value: int) -> bytes:
    """Encode a non-negative integer as an unsigned LEB128 varint.

    Parameters
    ----------
    value:
        Non-negative integer to encode.

    Returns
    -------
    bytes
        Between 1 and 10 bytes.

    Raises
    ------
    ValueError
        If *value* is negative.
    """
    if value < 0:
        raise ValueError(f"varint value must be non-negative, got {value}")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def decode_varint(data: bytes | memoryview, offset: int = 0) -> tuple[int, int]:
    """Decode an unsigned LEB128 varint.

    Parameters
    ----------
    data:
        Bytes to decode from.
    offset:
        Starting position within *data*.

    Returns
    -------
    (value, new_offset)
        The decoded integer and the offset of the first byte *after* the
        varint.

    Raises
    ------
    PayloadError
        If the varint is truncated or exceeds 10 bytes (overflow guard).
    """
    result = 0
    shift = 0
    for i in range(10):
        pos = offset + i
        if pos >= len(data):
            raise PayloadError("Truncated varint")
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            return result, pos + 1
    raise PayloadError("Varint too long (overflow guard)")


# ---------------------------------------------------------------------------
# Payload dataclass
# ---------------------------------------------------------------------------

@dataclass
class Payload:
    """Decoded representation of a CQR binary payload.

    Attributes
    ----------
    data_hash:
        32-byte BLAKE3 digest of the original data bytes.
    graph_hash:
        32-byte BLAKE3 digest of the canonical graph bytes.
    graph_codec_id:
        Identifier for the graph canonicalization algorithm (default: 1).
    graph_codec_version:
        Version within that algorithm (default: 1).
    key_type:
        How to interpret *key_bytes* (``KEY_TYPE_*`` constants), or
        ``None`` when no key is present.
    key_bytes:
        Optional raw key / index bytes.
    embedded_data:
        Optional raw (decompressed) data bytes.
    """

    data_hash: bytes
    graph_hash: bytes
    graph_codec_id: int = 0x01
    graph_codec_version: int = 0x01
    key_type: Optional[int] = None
    key_bytes: Optional[bytes] = None
    embedded_data: Optional[bytes] = None


# ---------------------------------------------------------------------------
# Pack / unpack
# ---------------------------------------------------------------------------

def pack(payload: Payload) -> bytes:
    """Serialise *payload* to bytes.

    The CRC32C is computed over all bytes *before* the checksum field and
    appended as the final 4 bytes (little-endian).

    Parameters
    ----------
    payload:
        Populated :class:`Payload` instance.

    Returns
    -------
    bytes
        The complete, framed payload bytes including magic, header, optional
        blocks, and CRC32C trailer.

    Raises
    ------
    ValueError
        If required hash fields are not exactly 32 bytes.
    """
    if len(payload.data_hash) != 32:
        raise ValueError("data_hash must be exactly 32 bytes")
    if len(payload.graph_hash) != 32:
        raise ValueError("graph_hash must be exactly 32 bytes")

    flags = 0
    has_key = payload.key_bytes is not None and payload.key_type is not None
    has_data = payload.embedded_data is not None
    if has_data:
        flags |= FLAG_HAS_EMBEDDED_DATA
    if has_key:
        flags |= FLAG_HAS_INDEX_KEY

    buf = bytearray()

    # Fixed header
    buf += MAGIC
    buf += struct.pack("BB", VERSION, flags)
    buf += payload.data_hash
    buf += payload.graph_hash
    buf += struct.pack("BB", payload.graph_codec_id, payload.graph_codec_version)

    # Optional key block
    if has_key:
        buf += struct.pack("B", payload.key_type)
        buf += encode_varint(len(payload.key_bytes))
        buf += payload.key_bytes

    # Optional data block
    if has_data:
        codec_byte, comp_bytes = _compress(payload.embedded_data)
        buf += struct.pack("B", codec_byte)
        buf += encode_varint(len(payload.embedded_data))
        buf += encode_varint(len(comp_bytes))
        buf += comp_bytes

    # CRC32C trailer
    crc = _crc32c(bytes(buf))
    buf += struct.pack("<I", crc)

    return bytes(buf)


def unpack(data: bytes) -> Payload:
    """Deserialise *data* into a :class:`Payload` instance.

    Parameters
    ----------
    data:
        Raw bytes as produced by :func:`pack`.

    Returns
    -------
    Payload
        The decoded payload.

    Raises
    ------
    PayloadError
        On bad magic, unsupported version, CRC mismatch, truncated data,
        or unknown codec.
    """
    if len(data) < 4:
        raise PayloadError("Data too short to contain magic bytes")

    if data[:4] != MAGIC:
        raise PayloadError(f"Bad magic: {data[:4]!r}")

    # Verify CRC32C (covers all bytes except the last 4)
    if len(data) < 8:
        raise PayloadError("Data too short for header")
    body, crc_bytes = data[:-4], data[-4:]
    expected_crc = struct.unpack("<I", crc_bytes)[0]
    actual_crc = _crc32c(body)
    if actual_crc != expected_crc:
        raise PayloadError(
            f"CRC32C mismatch: expected {expected_crc:#010x}, got {actual_crc:#010x}"
        )

    offset = 4  # past magic

    # Version + flags (1 byte each)
    if offset + 2 > len(body):
        raise PayloadError("Truncated header (version/flags)")
    version, flags = struct.unpack_from("BB", body, offset)
    offset += 2

    if version != VERSION:
        raise PayloadError(f"Unsupported payload version: {version}")

    has_data = bool(flags & FLAG_HAS_EMBEDDED_DATA)
    has_key = bool(flags & FLAG_HAS_INDEX_KEY)

    # data_hash (32 bytes)
    if offset + 32 > len(body):
        raise PayloadError("Truncated data_hash")
    d_hash = bytes(body[offset:offset + 32])
    offset += 32

    # graph_hash (32 bytes)
    if offset + 32 > len(body):
        raise PayloadError("Truncated graph_hash")
    g_hash = bytes(body[offset:offset + 32])
    offset += 32

    # codec id + version (1 byte each)
    if offset + 2 > len(body):
        raise PayloadError("Truncated codec fields")
    codec_id, codec_ver = struct.unpack_from("BB", body, offset)
    offset += 2

    # Optional key block
    key_type: Optional[int] = None
    key_bytes: Optional[bytes] = None
    if has_key:
        if offset + 1 > len(body):
            raise PayloadError("Truncated key_type")
        key_type = body[offset]
        offset += 1
        key_len, offset = decode_varint(body, offset)
        if offset + key_len > len(body):
            raise PayloadError("Truncated key_bytes")
        key_bytes = bytes(body[offset:offset + key_len])
        offset += key_len

    # Optional data block
    embedded_data: Optional[bytes] = None
    if has_data:
        if offset + 1 > len(body):
            raise PayloadError("Truncated data_codec")
        data_codec = body[offset]
        offset += 1
        orig_len, offset = decode_varint(body, offset)
        comp_len, offset = decode_varint(body, offset)
        if offset + comp_len > len(body):
            raise PayloadError("Truncated comp_bytes")
        comp_bytes = bytes(body[offset:offset + comp_len])
        offset += comp_len

        if data_codec == DATA_CODEC_ZSTD:
            if _zstd is None:
                raise PayloadError(
                    "Payload uses zstd compression but 'zstandard' is not installed"
                )
            embedded_data = _decompress_zstd(comp_bytes)
        elif data_codec == DATA_CODEC_GZIP:
            embedded_data = _decompress_gzip(comp_bytes)
        else:
            raise PayloadError(f"Unknown data_codec: {data_codec:#04x}")

        if len(embedded_data) != orig_len:
            raise PayloadError(
                f"Decompressed length mismatch: expected {orig_len}, got {len(embedded_data)}"
            )

    return Payload(
        data_hash=d_hash,
        graph_hash=g_hash,
        graph_codec_id=codec_id,
        graph_codec_version=codec_ver,
        key_type=key_type,
        key_bytes=key_bytes,
        embedded_data=embedded_data,
    )
