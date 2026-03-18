"""Base QR encoder/decoder that supports arbitrary payload types.

``QRData`` is an envelope that carries a typed payload (text, Prolog code,
audio metadata, SVG markup, quantum state, or a Neo4j Cypher query).  The
envelope is serialised to a compact JSON string which is then encoded as a
standard QR symbol via the ``qrcode`` library.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PayloadType(str, Enum):
    """The kind of data carried by a :class:`QRData` envelope."""

    TEXT = "text"
    PROLOG = "prolog"
    AUDIO = "audio"
    SVG = "svg"
    QUANTUM = "quantum"
    CYPHER = "cypher"
    JSON = "json"


@dataclass
class QRData:
    """Typed payload container for a single QR code.

    Parameters
    ----------
    payload_type:
        Semantic type of the payload (see :class:`PayloadType`).
    content:
        The actual payload.  For binary payloads (e.g. ``audio``) pass a
        ``bytes`` object—it will be base-64 encoded automatically.
    metadata:
        Optional dict of key/value annotations stored alongside the payload.
    """

    payload_type: PayloadType
    content: str | bytes
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """Serialise the envelope to a compact JSON string."""
        raw = self.content
        if isinstance(raw, (bytes, bytearray)):
            encoded = base64.b64encode(raw).decode()
            binary = True
        else:
            encoded = raw
            binary = False
        obj = {
            "t": self.payload_type.value,
            "c": encoded,
            "b": binary,
            "m": self.metadata,
        }
        return json.dumps(obj, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> "QRData":
        """Deserialise a JSON string produced by :meth:`to_json`."""
        obj = json.loads(text)
        content: str | bytes = obj["c"]
        if obj.get("b"):
            content = base64.b64decode(content)
        return cls(
            payload_type=PayloadType(obj["t"]),
            content=content,
            metadata=obj.get("m", {}),
        )

    # ------------------------------------------------------------------
    # Fingerprint
    # ------------------------------------------------------------------

    def fingerprint(self) -> str:
        """SHA-256 hex digest of the serialised envelope (first 16 hex chars)."""
        raw = self.to_json().encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def __repr__(self) -> str:
        snip = str(self.content)[:40]
        return (
            f"QRData(type={self.payload_type.value!r}, "
            f"content={snip!r}..., fp={self.fingerprint()!r})"
        )


# ---------------------------------------------------------------------------
# QREncoder
# ---------------------------------------------------------------------------

class QREncoder:
    """Encode :class:`QRData` objects as QR symbols (images or SVG strings).

    Parameters
    ----------
    error_correction:
        QR error-correction level: ``"L"`` (7 %), ``"M"`` (15 %),
        ``"Q"`` (25 %), or ``"H"`` (30 %).  Defaults to ``"M"``.
    box_size:
        Pixel size of each QR module.  Defaults to 10.
    border:
        Quiet-zone width in QR modules.  Defaults to 4.
    """

    _EC_MAP = {"L": 1, "M": 0, "Q": 3, "H": 2}

    def __init__(
        self,
        error_correction: str = "M",
        box_size: int = 10,
        border: int = 4,
    ) -> None:
        self.error_correction = error_correction.upper()
        self.box_size = box_size
        self.border = border

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_qr(self, data: QRData):  # type: ignore[return]
        """Return a ``qrcode.QRCode`` instance loaded with *data*."""
        try:
            import qrcode  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "The 'qrcode[pil]' package is required for image encoding. "
                "Install it with: pip install qrcode[pil]"
            ) from exc

        ec_map = {
            "L": qrcode.constants.ERROR_CORRECT_L,
            "M": qrcode.constants.ERROR_CORRECT_M,
            "Q": qrcode.constants.ERROR_CORRECT_Q,
            "H": qrcode.constants.ERROR_CORRECT_H,
        }
        qr = qrcode.QRCode(
            error_correction=ec_map.get(self.error_correction, qrcode.constants.ERROR_CORRECT_M),
            box_size=self.box_size,
            border=self.border,
        )
        qr.add_data(data.to_json())
        qr.make(fit=True)
        return qr

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode_image(self, data: QRData, fill_color: str = "black", back_color: str = "white"):
        """Encode *data* as a PIL Image.

        Returns
        -------
        PIL.Image.Image
            A greyscale QR code image.
        """
        qr = self._make_qr(data)
        return qr.make_image(fill_color=fill_color, back_color=back_color)

    def encode_svg(self, data: QRData) -> str:
        """Encode *data* as an inline SVG string.

        Returns
        -------
        str
            A complete ``<svg>`` element suitable for embedding in HTML.
        """
        try:
            import qrcode.image.svg as qr_svg  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "SVG output requires 'qrcode[pil]'. "
                "Install it with: pip install qrcode[pil]"
            ) from exc

        import io

        qr = self._make_qr(data)
        factory = qr_svg.SvgPathImage
        img = qr.make_image(image_factory=factory)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode()

    def encode_matrix(self, data: QRData) -> list[list[bool]]:
        """Return the raw boolean matrix of QR modules.

        Useful for custom renderers (3D, audio, quantum) that need access to
        the underlying QR grid without depending on PIL or SVG.
        """
        qr = self._make_qr(data)
        return [list(row) for row in qr.get_matrix()]

    @staticmethod
    def decode_json(text: str) -> QRData:
        """Reconstruct a :class:`QRData` from the JSON string stored in a QR code."""
        return QRData.from_json(text)
