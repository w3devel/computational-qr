"""Pattern A – multi-frame QR / video-QR transport.

This module converts a :class:`~computational_qr.comms.capsule.Capsule` into a
sequence of fixed-size **frames** that can each be encoded as a standard QR
symbol (or as a frame in an animated Video-QR).  Frames can be reassembled
in *any order* once all of them are received.

Frame format (canonical JSON per frame)
----------------------------------------

.. code-block:: json

    {
        "msg_id":        "<capsule uuid4>",
        "frame_no":      0,
        "frame_total":   3,
        "chunk_checksum": "<sha256 hex of chunk bytes>",
        "chunk_b64":     "<base64url encoded chunk bytes>"
    }

Usage
-----

.. code-block:: python

    from computational_qr.comms.capsule import Capsule
    from computational_qr.comms.qr_transport import QRFramer

    capsule = Capsule(payload=b"hello world", content_type="text")
    framer = QRFramer(chunk_size=200)

    # Split capsule into QR-friendly frames
    frames = framer.split(capsule)

    # Reassemble (any order)
    restored = framer.reassemble(frames)
    assert restored.payload == b"hello world"

    # Get QRData objects ready for QREncoder / VideoQR
    qr_items = framer.to_qr_data(capsule)
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from computational_qr.comms.capsule import Capsule
from computational_qr.core.qr_encoder import PayloadType, QRData


_DEFAULT_CHUNK_SIZE = 300  # bytes – conservative QR capacity at error-level M


def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_decode(text: str) -> bytes:
    padding = (4 - len(text) % 4) % 4
    return base64.urlsafe_b64decode(text + "=" * padding)


def _chunk_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class QRFrame:
    """A single chunk-frame ready for QR encoding.

    Parameters
    ----------
    msg_id:
        UUID of the originating :class:`~computational_qr.comms.capsule.Capsule`.
    frame_no:
        Zero-based index of this frame within the message.
    frame_total:
        Total number of frames for this message.
    chunk:
        Raw bytes of the payload chunk.
    """

    def __init__(self, msg_id: str, frame_no: int, frame_total: int, chunk: bytes) -> None:
        self.msg_id = msg_id
        self.frame_no = frame_no
        self.frame_total = frame_total
        self.chunk = chunk

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "frame_no": self.frame_no,
            "frame_total": self.frame_total,
            "chunk_checksum": _chunk_checksum(self.chunk),
            "chunk_b64": _b64u_encode(self.chunk),
        }

    def to_json(self) -> str:
        return _canonical(self.to_dict())

    @classmethod
    def from_dict(cls, obj: dict) -> "QRFrame":
        """Deserialise a :class:`QRFrame` from a dict.

        Raises
        ------
        ValueError
            If the ``chunk_checksum`` does not match the decoded chunk.
        """
        chunk = _b64u_decode(obj["chunk_b64"])
        stored = obj.get("chunk_checksum", "")
        expected = _chunk_checksum(chunk)
        if stored != expected:
            raise ValueError(
                f"QRFrame chunk_checksum mismatch: "
                f"stored={stored!r} expected={expected!r}"
            )
        return cls(
            msg_id=obj["msg_id"],
            frame_no=obj["frame_no"],
            frame_total=obj["frame_total"],
            chunk=chunk,
        )

    @classmethod
    def from_json(cls, text: str) -> "QRFrame":
        return cls.from_dict(json.loads(text))

    def to_qr_data(self) -> QRData:
        """Wrap this frame as a :class:`~computational_qr.core.qr_encoder.QRData`
        envelope with ``PayloadType.JSON``.

        The resulting object can be passed directly to
        :class:`~computational_qr.core.qr_encoder.QREncoder` or
        :class:`~computational_qr.media.video_qr.VideoQR`.
        """
        return QRData(
            payload_type=PayloadType.JSON,
            content=self.to_json(),
            metadata={
                "msg_id": self.msg_id,
                "frame_no": self.frame_no,
                "frame_total": self.frame_total,
            },
        )

    def __repr__(self) -> str:
        return (
            f"QRFrame(msg={self.msg_id[:8]!r}..., "
            f"{self.frame_no}/{self.frame_total}, "
            f"bytes={len(self.chunk)})"
        )


class QRFramer:
    """Split a :class:`~computational_qr.comms.capsule.Capsule` into
    :class:`QRFrame` objects and reassemble them.

    Parameters
    ----------
    chunk_size:
        Maximum number of *capsule bytes* per frame.  Defaults to
        :data:`_DEFAULT_CHUNK_SIZE` (300 bytes).
    """

    def __init__(self, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        self.chunk_size = chunk_size

    def split(self, capsule: Capsule) -> list[QRFrame]:
        """Split *capsule* into a list of :class:`QRFrame` objects.

        The capsule is first serialised to bytes (canonical JSON), then
        divided into chunks of at most :attr:`chunk_size` bytes.
        """
        data = capsule.to_bytes()
        chunks = [
            data[i : i + self.chunk_size]
            for i in range(0, max(len(data), 1), self.chunk_size)
        ]
        total = len(chunks)
        return [
            QRFrame(
                msg_id=capsule.msg_id,
                frame_no=idx,
                frame_total=total,
                chunk=chunk,
            )
            for idx, chunk in enumerate(chunks)
        ]

    def reassemble(self, frames: list[QRFrame]) -> Capsule:
        """Reassemble *frames* (in any order) back into a :class:`Capsule`.

        Raises
        ------
        ValueError
            If frames belong to more than one ``msg_id``, if there are
            duplicate frame numbers, or if the frame set is incomplete.
        """
        if not frames:
            raise ValueError("No frames provided")

        msg_ids = {f.msg_id for f in frames}
        if len(msg_ids) > 1:
            raise ValueError(
                f"Frames belong to multiple messages: {msg_ids!r}"
            )

        total = frames[0].frame_total
        if len(frames) != total:
            raise ValueError(
                f"Incomplete frame set: got {len(frames)}, expected {total}"
            )

        ordered = sorted(frames, key=lambda f: f.frame_no)
        seen = {f.frame_no for f in ordered}
        expected_set = set(range(total))
        if seen != expected_set:
            missing = expected_set - seen
            raise ValueError(f"Missing frame numbers: {missing!r}")

        data = b"".join(f.chunk for f in ordered)
        return Capsule.from_bytes(data)

    def to_qr_data(self, capsule: Capsule) -> list[QRData]:
        """Convenience method: split *capsule* and return a list of
        :class:`~computational_qr.core.qr_encoder.QRData` envelopes,
        one per frame.

        These can be passed directly to
        :class:`~computational_qr.media.video_qr.VideoQR` to create a
        multi-frame animated QR.
        """
        return [frame.to_qr_data() for frame in self.split(capsule)]
