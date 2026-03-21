"""Tests for computational_qr.comms.qr_transport."""

import json
import random

import pytest

from computational_qr.comms.capsule import Capsule
from computational_qr.comms.qr_transport import QRFrame, QRFramer, _chunk_checksum
from computational_qr.core.qr_encoder import PayloadType, QRData


class TestQRFrame:
    def setup_method(self):
        self.chunk = b"hello chunk"
        self.frame = QRFrame(
            msg_id="test-msg-id",
            frame_no=0,
            frame_total=3,
            chunk=self.chunk,
        )

    def test_to_dict_has_required_keys(self):
        d = self.frame.to_dict()
        for key in ("msg_id", "frame_no", "frame_total", "chunk_checksum", "chunk_b64"):
            assert key in d

    def test_to_dict_msg_id(self):
        assert self.frame.to_dict()["msg_id"] == "test-msg-id"

    def test_to_dict_frame_numbers(self):
        d = self.frame.to_dict()
        assert d["frame_no"] == 0
        assert d["frame_total"] == 3

    def test_to_json_is_valid_json(self):
        j = self.frame.to_json()
        parsed = json.loads(j)
        assert "chunk_b64" in parsed

    def test_to_json_is_canonical(self):
        assert self.frame.to_json() == self.frame.to_json()

    def test_roundtrip(self):
        d = self.frame.to_dict()
        restored = QRFrame.from_dict(d)
        assert restored.chunk == self.chunk
        assert restored.msg_id == "test-msg-id"
        assert restored.frame_no == 0
        assert restored.frame_total == 3

    def test_from_json_roundtrip(self):
        restored = QRFrame.from_json(self.frame.to_json())
        assert restored.chunk == self.chunk

    def test_from_dict_raises_on_bad_chunk_checksum(self):
        d = self.frame.to_dict()
        d["chunk_checksum"] = "0" * 64
        with pytest.raises(ValueError, match="chunk_checksum mismatch"):
            QRFrame.from_dict(d)

    def test_to_qr_data_returns_qr_data(self):
        qr = self.frame.to_qr_data()
        assert isinstance(qr, QRData)

    def test_to_qr_data_payload_type_is_json(self):
        qr = self.frame.to_qr_data()
        assert qr.payload_type == PayloadType.JSON

    def test_to_qr_data_metadata(self):
        qr = self.frame.to_qr_data()
        assert qr.metadata["msg_id"] == "test-msg-id"
        assert qr.metadata["frame_no"] == 0
        assert qr.metadata["frame_total"] == 3

    def test_to_qr_data_content_parseable(self):
        qr = self.frame.to_qr_data()
        parsed = json.loads(qr.content)
        assert "chunk_b64" in parsed

    def test_repr_contains_msg_id_prefix(self):
        assert "test-msg" in repr(self.frame)


class TestQRFramer:
    def setup_method(self):
        self.framer = QRFramer(chunk_size=50)

    def _make_capsule(self, payload: bytes, **kwargs) -> Capsule:
        return Capsule(payload=payload, content_type="text", **kwargs)

    def test_split_single_frame_small_payload(self):
        capsule = self._make_capsule(b"hi")
        frames = self.framer.split(capsule)
        assert len(frames) >= 1
        for f in frames:
            assert f.msg_id == capsule.msg_id

    def test_split_multiple_frames_large_payload(self):
        capsule = self._make_capsule(b"x" * 500)
        framer = QRFramer(chunk_size=50)
        frames = framer.split(capsule)
        assert len(frames) > 1

    def test_split_frame_total_consistent(self):
        capsule = self._make_capsule(b"y" * 200)
        framer = QRFramer(chunk_size=30)
        frames = framer.split(capsule)
        totals = {f.frame_total for f in frames}
        assert len(totals) == 1
        assert totals.pop() == len(frames)

    def test_split_frame_numbers_sequential(self):
        capsule = self._make_capsule(b"z" * 300)
        framer = QRFramer(chunk_size=40)
        frames = framer.split(capsule)
        numbers = [f.frame_no for f in frames]
        assert numbers == list(range(len(frames)))

    def test_reassemble_in_order(self):
        capsule = self._make_capsule(b"hello world chunked")
        framer = QRFramer(chunk_size=10)
        frames = framer.split(capsule)
        restored = framer.reassemble(frames)
        assert restored.payload == b"hello world chunked"

    def test_reassemble_out_of_order(self):
        capsule = self._make_capsule(b"out of order test " * 5)
        framer = QRFramer(chunk_size=20)
        frames = framer.split(capsule)
        shuffled = frames[:]
        random.shuffle(shuffled)
        restored = framer.reassemble(shuffled)
        assert restored.payload == capsule.payload

    def test_reassemble_preserves_routing(self):
        capsule = Capsule(
            payload=b"routed",
            content_type="text",
            routing={"topic": "news"},
        )
        framer = QRFramer(chunk_size=30)
        frames = framer.split(capsule)
        restored = framer.reassemble(frames)
        assert restored.routing == {"topic": "news"}

    def test_reassemble_raises_on_empty(self):
        with pytest.raises(ValueError, match="No frames"):
            self.framer.reassemble([])

    def test_reassemble_raises_on_mixed_msg_ids(self):
        c1 = self._make_capsule(b"aaa")
        c2 = self._make_capsule(b"bbb")
        frames = self.framer.split(c1) + self.framer.split(c2)
        with pytest.raises(ValueError, match="multiple messages"):
            self.framer.reassemble(frames)

    def test_reassemble_raises_on_incomplete(self):
        capsule = self._make_capsule(b"x" * 200)
        framer = QRFramer(chunk_size=20)
        frames = framer.split(capsule)
        incomplete = frames[:-1]  # drop last frame
        with pytest.raises(ValueError):
            framer.reassemble(incomplete)

    def test_chunk_size_validation(self):
        with pytest.raises(ValueError):
            QRFramer(chunk_size=0)

    def test_to_qr_data_list(self):
        capsule = self._make_capsule(b"qrdata test " * 3)
        framer = QRFramer(chunk_size=20)
        items = framer.to_qr_data(capsule)
        assert all(isinstance(item, QRData) for item in items)
        assert len(items) == len(framer.split(capsule))

    def test_large_payload_roundtrip(self):
        data = bytes(range(256)) * 50  # 12800 bytes
        capsule = Capsule(payload=data, content_type="bytes")
        framer = QRFramer(chunk_size=200)
        frames = framer.split(capsule)
        restored = framer.reassemble(frames)
        assert restored.payload == data

    def test_empty_payload_roundtrip(self):
        capsule = Capsule(payload=b"")
        frames = self.framer.split(capsule)
        restored = self.framer.reassemble(frames)
        assert restored.payload == b""

    def test_default_chunk_size(self):
        framer = QRFramer()
        assert framer.chunk_size == 300
