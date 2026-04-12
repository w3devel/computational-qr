"""
tests/test_cqr_payload.py – Unit tests for computational_qr.cqr.payload.
"""

import struct

import pytest

from computational_qr.cqr.payload import (
    FLAG_HAS_EMBEDDED_DATA,
    FLAG_HAS_INDEX_KEY,
    KEY_TYPE_RAW,
    MAGIC,
    Payload,
    PayloadError,
    decode_varint,
    encode_varint,
    pack,
    unpack,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_HASH = bytes(range(32))  # 32 bytes of deterministic filler


def _make_payload(**kwargs) -> Payload:
    defaults = dict(
        data_hash=_DUMMY_HASH,
        graph_hash=bytes(reversed(range(32))),
    )
    defaults.update(kwargs)
    return Payload(**defaults)


# ---------------------------------------------------------------------------
# Varint tests
# ---------------------------------------------------------------------------

class TestVarint:
    def test_zero(self):
        assert encode_varint(0) == b"\x00"

    def test_small_value(self):
        assert encode_varint(1) == b"\x01"
        assert encode_varint(127) == b"\x7f"

    def test_two_byte_boundary(self):
        # 128 requires two bytes in LEB128
        encoded = encode_varint(128)
        assert len(encoded) == 2
        assert encoded == b"\x80\x01"

    def test_large_value(self):
        val = 2**21 - 1
        enc = encode_varint(val)
        decoded, _ = decode_varint(enc)
        assert decoded == val

    def test_roundtrip(self):
        for val in [0, 1, 127, 128, 255, 256, 16383, 16384, 2097151, 10_000_000]:
            enc = encode_varint(val)
            dec, end = decode_varint(enc)
            assert dec == val
            assert end == len(enc)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            encode_varint(-1)

    def test_truncated_raises(self):
        with pytest.raises(PayloadError):
            decode_varint(b"\x80")  # MSB set but no next byte

    def test_offset_parameter(self):
        buf = b"\xff" + encode_varint(42)
        val, end = decode_varint(buf, offset=1)
        assert val == 42

    def test_overflow_guard(self):
        # 10 bytes all with MSB set → overflow
        with pytest.raises(PayloadError):
            decode_varint(b"\x80" * 10)


# ---------------------------------------------------------------------------
# Pack / unpack round-trip tests
# ---------------------------------------------------------------------------

class TestPackUnpack:
    def test_minimal_payload_roundtrip(self):
        p = _make_payload()
        raw = pack(p)
        p2 = unpack(raw)
        assert p2.data_hash == p.data_hash
        assert p2.graph_hash == p.graph_hash
        assert p2.embedded_data is None
        assert p2.key_bytes is None

    def test_with_embedded_data(self):
        data = b"Hello, Computational QR!"
        p = _make_payload(embedded_data=data)
        raw = pack(p)
        p2 = unpack(raw)
        assert p2.embedded_data == data

    def test_with_key(self):
        key = b"my-index-key"
        p = _make_payload(key_type=KEY_TYPE_RAW, key_bytes=key)
        raw = pack(p)
        p2 = unpack(raw)
        assert p2.key_bytes == key
        assert p2.key_type == KEY_TYPE_RAW

    def test_with_both_data_and_key(self):
        data = b"payload data"
        key = b"db-key"
        p = _make_payload(embedded_data=data, key_type=KEY_TYPE_RAW, key_bytes=key)
        raw = pack(p)
        p2 = unpack(raw)
        assert p2.embedded_data == data
        assert p2.key_bytes == key

    def test_starts_with_magic(self):
        p = _make_payload()
        raw = pack(p)
        assert raw[:4] == MAGIC

    def test_codec_fields_preserved(self):
        p = _make_payload()
        p.graph_codec_id = 0x02
        p.graph_codec_version = 0x03
        raw = pack(p)
        p2 = unpack(raw)
        assert p2.graph_codec_id == 0x02
        assert p2.graph_codec_version == 0x03

    def test_large_embedded_data(self):
        data = b"x" * 100_000
        p = _make_payload(embedded_data=data)
        raw = pack(p)
        p2 = unpack(raw)
        assert p2.embedded_data == data

    def test_deterministic(self):
        """Same payload → same bytes."""
        p1 = _make_payload(embedded_data=b"same")
        p2 = _make_payload(embedded_data=b"same")
        assert pack(p1) == pack(p2)

    def test_hash_validation_data_hash_too_short(self):
        with pytest.raises(ValueError):
            pack(_make_payload(data_hash=b"\x00" * 16))

    def test_hash_validation_graph_hash_too_long(self):
        with pytest.raises(ValueError):
            pack(_make_payload(graph_hash=b"\x00" * 33))


# ---------------------------------------------------------------------------
# CRC32C failure detection tests
# ---------------------------------------------------------------------------

class TestCRC:
    def test_crc_bad_magic(self):
        with pytest.raises(PayloadError, match="Bad magic"):
            unpack(b"XXXX" + b"\x00" * 76)

    def test_crc_corruption_detected(self):
        p = _make_payload()
        raw = bytearray(pack(p))
        # Flip a bit in the middle of the payload (inside the body)
        raw[20] ^= 0xFF
        with pytest.raises(PayloadError, match="CRC32C mismatch"):
            unpack(bytes(raw))

    def test_crc_last_byte_corruption(self):
        p = _make_payload()
        raw = bytearray(pack(p))
        # Corrupt the CRC itself (last 4 bytes)
        raw[-1] ^= 0x01
        with pytest.raises(PayloadError, match="CRC32C mismatch"):
            unpack(bytes(raw))

    def test_too_short_raises(self):
        with pytest.raises(PayloadError):
            unpack(b"CQ")

    def test_bad_version_raises(self):
        p = _make_payload()
        raw = bytearray(pack(p))
        # Byte 4 is version; patch it to an unsupported value, then fix CRC.
        raw[4] = 0xFF
        # Recompute CRC32C for the patched body
        import crc32c as _c32
        body = bytes(raw[:-4])
        new_crc = _c32.crc32c(body)
        raw[-4:] = struct.pack("<I", new_crc)
        with pytest.raises(PayloadError, match="Unsupported"):
            unpack(bytes(raw))
