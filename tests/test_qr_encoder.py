"""Tests for computational_qr.core.qr_encoder."""

import json
import pytest

from computational_qr.core.qr_encoder import QRData, QREncoder, PayloadType


class TestQRData:
    def test_text_roundtrip(self):
        data = QRData(payload_type=PayloadType.TEXT, content="hello world")
        restored = QRData.from_json(data.to_json())
        assert restored.payload_type == PayloadType.TEXT
        assert restored.content == "hello world"

    def test_binary_roundtrip(self):
        raw = b"\x00\x01\x02\xff"
        data = QRData(payload_type=PayloadType.AUDIO, content=raw)
        restored = QRData.from_json(data.to_json())
        assert restored.content == raw

    def test_metadata_preserved(self):
        data = QRData(
            payload_type=PayloadType.JSON,
            content="{}",
            metadata={"author": "test", "version": 1},
        )
        restored = QRData.from_json(data.to_json())
        assert restored.metadata["author"] == "test"
        assert restored.metadata["version"] == 1

    def test_fingerprint_deterministic(self):
        data = QRData(payload_type=PayloadType.TEXT, content="abc")
        assert data.fingerprint() == data.fingerprint()

    def test_fingerprint_differs_for_different_content(self):
        d1 = QRData(payload_type=PayloadType.TEXT, content="abc")
        d2 = QRData(payload_type=PayloadType.TEXT, content="xyz")
        assert d1.fingerprint() != d2.fingerprint()

    def test_fingerprint_length(self):
        data = QRData(payload_type=PayloadType.TEXT, content="test")
        assert len(data.fingerprint()) == 16

    def test_json_is_valid_json(self):
        data = QRData(payload_type=PayloadType.PROLOG, content="parent(a, b).")
        json_str = data.to_json()
        parsed = json.loads(json_str)
        assert "t" in parsed
        assert "c" in parsed

    def test_all_payload_types_serialise(self):
        for pt in PayloadType:
            d = QRData(payload_type=pt, content="x")
            restored = QRData.from_json(d.to_json())
            assert restored.payload_type == pt

    def test_repr_contains_type(self):
        data = QRData(payload_type=PayloadType.SVG, content="<svg/>")
        assert "svg" in repr(data)


class TestQREncoder:
    """Test QREncoder without requiring PIL (uses encode_matrix)."""

    def setup_method(self):
        self.encoder = QREncoder(error_correction="M", box_size=4, border=2)

    def test_encode_matrix_returns_2d_list(self):
        data = QRData(payload_type=PayloadType.TEXT, content="hi")
        matrix = self.encoder.encode_matrix(data)
        assert isinstance(matrix, list)
        assert isinstance(matrix[0], list)
        assert isinstance(matrix[0][0], bool)

    def test_encode_matrix_is_square(self):
        data = QRData(payload_type=PayloadType.TEXT, content="square?")
        matrix = self.encoder.encode_matrix(data)
        rows = len(matrix)
        for row in matrix:
            assert len(row) == rows

    def test_encode_matrix_differs_for_different_payloads(self):
        d1 = QRData(payload_type=PayloadType.TEXT, content="aaa")
        d2 = QRData(payload_type=PayloadType.TEXT, content="bbb")
        m1 = self.encoder.encode_matrix(d1)
        m2 = self.encoder.encode_matrix(d2)
        # Matrices should differ (extremely unlikely to be identical)
        assert m1 != m2

    def test_decode_json_roundtrip(self):
        data = QRData(
            payload_type=PayloadType.CYPHER,
            content="MATCH (n) RETURN n",
            metadata={"db": "neo4j"},
        )
        restored = QREncoder.decode_json(data.to_json())
        assert restored.payload_type == PayloadType.CYPHER
        assert restored.content == "MATCH (n) RETURN n"

    def test_error_correction_levels(self):
        for level in ("L", "M", "Q", "H"):
            enc = QREncoder(error_correction=level)
            data = QRData(payload_type=PayloadType.TEXT, content="test")
            matrix = enc.encode_matrix(data)
            assert len(matrix) > 0

    def test_larger_payload_creates_larger_matrix(self):
        short_data = QRData(payload_type=PayloadType.TEXT, content="hi")
        long_data = QRData(
            payload_type=PayloadType.TEXT,
            content="x" * 200,
        )
        m_short = self.encoder.encode_matrix(short_data)
        m_long = self.encoder.encode_matrix(long_data)
        assert len(m_long) >= len(m_short)
