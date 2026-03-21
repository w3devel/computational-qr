"""Versioned message capsule – the shared transport-oriented envelope.

A :class:`Capsule` is the fundamental unit of the ``comms`` subsystem.  It is:

* **versioned** – carries a ``version`` field for forward compatibility,
* **chunkable** – the raw bytes can be split into frames by
  :mod:`~computational_qr.comms.qr_transport`,
* **replay-safe** – carries a UUID ``msg_id`` and millisecond timestamp,
* **integrity-checked** – a SHA-256 ``checksum`` covers all header + payload
  bytes.

Serialisation uses canonical JSON (``sort_keys=True``, no extra whitespace) so
that the checksum is deterministic across platforms.

Capsule JSON schema
-------------------

.. code-block:: json

    {
        "version": 1,
        "msg_id": "<uuid4>",
        "created_at_ms": 1700000000000,
        "routing": {},
        "content_type": "text",
        "payload_b64": "<base64url>",
        "checksum": "<sha256 hex>"
    }

The ``checksum`` field is computed over the canonical JSON of all *other*
fields (i.e. the document without the ``checksum`` key).
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


_CAPSULE_VERSION = 1


def _b64u_encode(data: bytes) -> str:
    """URL-safe base64 encode *data* without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_decode(text: str) -> bytes:
    """URL-safe base64 decode *text* (padding optional)."""
    padding = (4 - len(text) % 4) % 4
    return base64.urlsafe_b64decode(text + "=" * padding)


def _canonical(obj: dict) -> str:
    """Return a canonical (sorted-key, compact) JSON string."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _checksum(header_plus_payload: dict) -> str:
    """Compute SHA-256 hex digest over the canonical JSON of *header_plus_payload*."""
    raw = _canonical(header_plus_payload).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass
class Capsule:
    """Transport-oriented versioned message capsule.

    Parameters
    ----------
    payload:
        Raw bytes to transmit.
    content_type:
        Logical type string, e.g. ``"text"``, ``"bytes"``, ``"otp_ciphertext"``.
    routing:
        Optional routing hints dict.  Keys recognised by transports include
        ``"i2p_dest"`` (I2P destination string) and ``"topic"``
        (mailbox/topic label).
    msg_id:
        UUID4 string.  Auto-generated if ``None``.
    created_at_ms:
        Unix timestamp in milliseconds.  Defaults to *now*.
    version:
        Capsule format version.  Defaults to :data:`_CAPSULE_VERSION`.
    """

    payload: bytes
    content_type: str = "bytes"
    routing: dict[str, Any] = field(default_factory=dict)
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    version: int = _CAPSULE_VERSION

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def _header_dict(self) -> dict:
        """Return the header fields (without checksum) as a plain dict."""
        return {
            "version": self.version,
            "msg_id": self.msg_id,
            "created_at_ms": self.created_at_ms,
            "routing": self.routing,
            "content_type": self.content_type,
            "payload_b64": _b64u_encode(self.payload),
        }

    def to_dict(self) -> dict:
        """Serialise to a dict suitable for JSON encoding.

        The ``checksum`` is computed over the canonical form of all other
        fields so that it is deterministic.
        """
        hdr = self._header_dict()
        hdr["checksum"] = _checksum(hdr)
        return hdr

    def to_json(self) -> str:
        """Serialise to a canonical JSON string."""
        return _canonical(self.to_dict())

    def to_bytes(self) -> bytes:
        """Serialise to UTF-8 bytes (canonical JSON)."""
        return self.to_json().encode()

    @classmethod
    def from_dict(cls, obj: dict) -> "Capsule":
        """Deserialise from a dict (e.g. parsed JSON).

        Raises
        ------
        ValueError
            If the checksum is missing or does not match the content.
        """
        stored_checksum = obj.get("checksum")
        if stored_checksum is None:
            raise ValueError("Capsule dict missing 'checksum' field")

        hdr = {k: v for k, v in obj.items() if k != "checksum"}
        expected = _checksum(hdr)
        if stored_checksum != expected:
            raise ValueError(
                f"Capsule checksum mismatch: stored={stored_checksum!r} "
                f"expected={expected!r}"
            )

        return cls(
            payload=_b64u_decode(hdr["payload_b64"]),
            content_type=hdr.get("content_type", "bytes"),
            routing=hdr.get("routing", {}),
            msg_id=hdr["msg_id"],
            created_at_ms=hdr["created_at_ms"],
            version=hdr.get("version", _CAPSULE_VERSION),
        )

    @classmethod
    def from_json(cls, text: str) -> "Capsule":
        """Deserialise from a canonical JSON string."""
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_bytes(cls, data: bytes) -> "Capsule":
        """Deserialise from UTF-8 encoded canonical JSON bytes."""
        return cls.from_json(data.decode())

    # ------------------------------------------------------------------
    # Integrity helpers
    # ------------------------------------------------------------------

    def verify(self) -> bool:
        """Return ``True`` if the stored checksum matches the computed one."""
        hdr = self._header_dict()
        return _checksum(hdr) == self.to_dict()["checksum"]

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def text_payload(self, encoding: str = "utf-8") -> str:
        """Decode ``payload`` as a text string."""
        return self.payload.decode(encoding)

    def __repr__(self) -> str:
        snip = self.msg_id[:8]
        return (
            f"Capsule(id={snip!r}..., type={self.content_type!r}, "
            f"bytes={len(self.payload)}, v={self.version})"
        )
