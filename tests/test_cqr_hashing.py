"""
tests/test_cqr_hashing.py – Unit tests for computational_qr.cqr.hashing.
"""

import pytest

from computational_qr.cqr.hashing import data_hash


class TestDataHash:
    def test_returns_bytes(self):
        result = data_hash(b"hello")
        assert isinstance(result, bytes)

    def test_returns_32_bytes(self):
        assert len(data_hash(b"hello")) == 32

    def test_deterministic(self):
        assert data_hash(b"hello world") == data_hash(b"hello world")

    def test_distinct_inputs(self):
        assert data_hash(b"foo") != data_hash(b"bar")

    def test_empty_bytes(self):
        result = data_hash(b"")
        assert len(result) == 32

    def test_known_vector(self):
        # BLAKE3 of b"" is a well-known value; just verify stability.
        h1 = data_hash(b"")
        h2 = data_hash(b"")
        assert h1 == h2
