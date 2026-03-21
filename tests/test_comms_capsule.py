"""Tests for computational_qr.comms.capsule."""

import json
import time

import pytest

from computational_qr.comms.capsule import (
    Capsule,
    _b64u_decode,
    _b64u_encode,
    _canonical,
    _checksum,
)


class TestB64uHelpers:
    def test_roundtrip_empty(self):
        assert _b64u_decode(_b64u_encode(b"")) == b""

    def test_roundtrip_bytes(self):
        data = bytes(range(256))
        assert _b64u_decode(_b64u_encode(data)) == data

    def test_no_padding_chars(self):
        encoded = _b64u_encode(b"hello")
        assert "=" not in encoded

    def test_decode_with_or_without_padding(self):
        # decode should accept strings with or without padding
        raw = b"test data"
        encoded = _b64u_encode(raw)
        # add padding back manually
        padding = "=" * ((4 - len(encoded) % 4) % 4)
        assert _b64u_decode(encoded + padding) == raw
        assert _b64u_decode(encoded) == raw


class TestCanonical:
    def test_keys_sorted(self):
        obj = {"z": 1, "a": 2, "m": 3}
        result = json.loads(_canonical(obj))
        assert list(result.keys()) == ["a", "m", "z"]

    def test_no_whitespace(self):
        s = _canonical({"k": "v"})
        assert " " not in s

    def test_deterministic(self):
        obj = {"b": [1, 2], "a": {"x": 1}}
        assert _canonical(obj) == _canonical(obj)


class TestChecksum:
    def test_hex_string(self):
        cs = _checksum({"a": 1})
        assert isinstance(cs, str)
        assert len(cs) == 64
        int(cs, 16)  # must be valid hex

    def test_deterministic(self):
        obj = {"a": 1, "b": "hello"}
        assert _checksum(obj) == _checksum(obj)

    def test_differs_for_different_content(self):
        assert _checksum({"a": 1}) != _checksum({"a": 2})


class TestCapsule:
    def test_create_defaults(self):
        c = Capsule(payload=b"hello")
        assert c.version == 1
        assert c.content_type == "bytes"
        assert c.routing == {}
        assert len(c.msg_id) == 36  # UUID4 format
        assert c.created_at_ms > 0

    def test_create_with_text_content(self):
        c = Capsule(payload=b"world", content_type="text")
        assert c.content_type == "text"

    def test_text_payload_helper(self):
        c = Capsule(payload=b"hello world", content_type="text")
        assert c.text_payload() == "hello world"

    def test_to_dict_has_required_keys(self):
        c = Capsule(payload=b"data")
        d = c.to_dict()
        for key in ("version", "msg_id", "created_at_ms", "routing",
                    "content_type", "payload_b64", "checksum"):
            assert key in d

    def test_to_json_is_valid_json(self):
        c = Capsule(payload=b"x")
        parsed = json.loads(c.to_json())
        assert "checksum" in parsed

    def test_to_json_is_canonical(self):
        c = Capsule(payload=b"x")
        j1 = c.to_json()
        j2 = c.to_json()
        assert j1 == j2

    def test_to_bytes_is_utf8_json(self):
        c = Capsule(payload=b"abc")
        raw = c.to_bytes()
        assert isinstance(raw, bytes)
        json.loads(raw.decode())

    def test_roundtrip_bytes(self):
        original = Capsule(
            payload=b"\x00\x01\x02\xff",
            content_type="bytes",
            routing={"topic": "test"},
        )
        restored = Capsule.from_bytes(original.to_bytes())
        assert restored.payload == original.payload
        assert restored.content_type == original.content_type
        assert restored.routing == original.routing
        assert restored.msg_id == original.msg_id
        assert restored.created_at_ms == original.created_at_ms

    def test_roundtrip_json(self):
        original = Capsule(payload=b"hello", content_type="text")
        restored = Capsule.from_json(original.to_json())
        assert restored.payload == b"hello"
        assert restored.content_type == "text"

    def test_roundtrip_dict(self):
        original = Capsule(
            payload=b"test",
            content_type="otp_ciphertext",
            routing={"i2p_dest": "abc.b32.i2p", "topic": "inbox"},
        )
        d = original.to_dict()
        restored = Capsule.from_dict(d)
        assert restored.payload == b"test"
        assert restored.routing["topic"] == "inbox"
        assert restored.routing["i2p_dest"] == "abc.b32.i2p"

    def test_verify_returns_true_for_valid(self):
        c = Capsule(payload=b"valid")
        assert c.verify() is True

    def test_from_dict_raises_on_missing_checksum(self):
        c = Capsule(payload=b"x")
        d = c.to_dict()
        del d["checksum"]
        with pytest.raises(ValueError, match="missing 'checksum'"):
            Capsule.from_dict(d)

    def test_from_dict_raises_on_bad_checksum(self):
        c = Capsule(payload=b"x")
        d = c.to_dict()
        d["checksum"] = "0" * 64
        with pytest.raises(ValueError, match="checksum mismatch"):
            Capsule.from_dict(d)

    def test_deterministic_encoding(self):
        """Two capsules with identical fields must produce identical JSON."""
        kwargs = dict(
            payload=b"deterministic",
            content_type="text",
            routing={"topic": "a"},
            msg_id="00000000-0000-0000-0000-000000000001",
            created_at_ms=1700000000000,
        )
        c1 = Capsule(**kwargs)
        c2 = Capsule(**kwargs)
        assert c1.to_json() == c2.to_json()

    def test_repr_contains_msg_id_prefix(self):
        c = Capsule(payload=b"x")
        r = repr(c)
        assert c.msg_id[:8] in r

    def test_routing_dict_preserved(self):
        routing = {"i2p_dest": "dest123", "topic": "news", "extra": 42}
        c = Capsule(payload=b"y", routing=routing)
        restored = Capsule.from_json(c.to_json())
        assert restored.routing == routing

    def test_version_preserved(self):
        c = Capsule(payload=b"z", version=2)
        restored = Capsule.from_json(c.to_json())
        assert restored.version == 2

    def test_empty_payload(self):
        c = Capsule(payload=b"")
        restored = Capsule.from_json(c.to_json())
        assert restored.payload == b""

    def test_large_payload(self):
        data = bytes(range(256)) * 100  # 25600 bytes
        c = Capsule(payload=data, content_type="bytes")
        restored = Capsule.from_json(c.to_json())
        assert restored.payload == data
