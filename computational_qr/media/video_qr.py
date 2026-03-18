"""Video QR via Scriptable Network Graphics (SVG).

``VideoQR`` generates an animated SVG document where each QR module is drawn
as a coloured rectangle.  The animation cycles through multiple QR data frames
so that a *sequence* of QR codes (i.e. video) is embedded in a single SVG
file—hence "scriptable network graphics for video QR".

The SVG is human-readable, editable, and can be served as a network resource
(``image/svg+xml``).  JavaScript ``<script>`` blocks inside the SVG allow
interactive frame navigation.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from typing import Sequence

from computational_qr.core.qr_encoder import QRData, QREncoder


@dataclass
class VideoQR:
    """Generate animated / interactive SVG documents from QR data frames.

    Parameters
    ----------
    module_size:
        Pixel size of each QR module in the SVG canvas.  Defaults to 8.
    frame_duration_ms:
        Duration of each animation frame in milliseconds.  Defaults to 500 ms.
    color_on:
        CSS colour for black (1) QR modules.  Defaults to ``"#000000"``.
    color_off:
        CSS colour for white (0) QR modules.  Defaults to ``"#ffffff"``.
    border_modules:
        Quiet-zone width in QR modules.  Defaults to 4.
    encoder:
        QR encoder used to convert :class:`~computational_qr.core.QRData`
        objects into boolean matrices.
    """

    module_size: int = 8
    frame_duration_ms: int = 500
    color_on: str = "#000000"
    color_off: str = "#ffffff"
    border_modules: int = 4
    encoder: QREncoder = field(
        default_factory=lambda: QREncoder(box_size=8, border=4)
    )

    # ------------------------------------------------------------------
    # Single-frame SVG
    # ------------------------------------------------------------------

    def matrix_to_svg(
        self,
        matrix: Sequence[Sequence[bool]],
        *,
        title: str = "",
        extra_css: str = "",
    ) -> str:
        """Render a single boolean QR *matrix* as an SVG string.

        Parameters
        ----------
        matrix:
            2D boolean grid (True = black module).
        title:
            Optional ``<title>`` element for accessibility.
        extra_css:
            Additional CSS rules injected into the ``<style>`` block.

        Returns
        -------
        str
            A standalone SVG document.
        """
        n_rows = len(matrix)
        n_cols = max((len(r) for r in matrix), default=0)
        ms = self.module_size
        width = n_cols * ms
        height = n_rows * ms

        parts: list[str] = []
        parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        )
        if title:
            parts.append(f"  <title>{html.escape(title)}</title>")
        parts.append("  <style>")
        parts.append(f"    rect.on  {{ fill: {self.color_on}; }}")
        parts.append(f"    rect.off {{ fill: {self.color_off}; }}")
        if extra_css:
            parts.append(f"    {extra_css}")
        parts.append("  </style>")

        for r, row in enumerate(matrix):
            for c, module in enumerate(row):
                cls = "on" if module else "off"
                x, y = c * ms, r * ms
                parts.append(
                    f'  <rect class="{cls}" x="{x}" y="{y}" '
                    f'width="{ms}" height="{ms}"/>'
                )
        parts.append("</svg>")
        return "\n".join(parts)

    def data_to_svg(self, data: QRData, *, title: str = "") -> str:
        """Convert a :class:`~computational_qr.core.QRData` to a single-frame SVG."""
        matrix = self.encoder.encode_matrix(data)
        return self.matrix_to_svg(matrix, title=title or data.payload_type.value)

    # ------------------------------------------------------------------
    # Multi-frame animated SVG (video QR)
    # ------------------------------------------------------------------

    def encode_video(
        self,
        frames: Sequence[QRData],
        *,
        title: str = "Computational QR – Video",
        loop: bool = True,
    ) -> str:
        """Encode multiple :class:`~computational_qr.core.QRData` frames as an
        animated SVG (video QR).

        Each frame is rendered as a ``<g>`` layer.  A ``<script>`` block
        provides interactive play/pause/seek controls.  The animation advances
        via CSS ``@keyframes`` combined with JavaScript timer control for
        better browser compatibility.

        Parameters
        ----------
        frames:
            Ordered sequence of QR data frames.
        title:
            SVG title element.
        loop:
            Whether the animation loops.  Defaults to ``True``.

        Returns
        -------
        str
            A fully self-contained SVG document with embedded script.
        """
        if not frames:
            return '<svg xmlns="http://www.w3.org/2000/svg"/>'

        matrices = [self.encoder.encode_matrix(f) for f in frames]
        n_rows = len(matrices[0])
        n_cols = max(len(r) for r in matrices[0])
        ms = self.module_size
        width = n_cols * ms
        height = n_rows * ms
        n_frames = len(matrices)
        dur_s = self.frame_duration_ms / 1000.0
        total_dur = dur_s * n_frames

        parts: list[str] = []
        parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        )
        parts.append(f"  <title>{html.escape(title)}</title>")
        parts.append("  <style>")
        parts.append(f"    .qr-frame {{ display: none; }}")
        parts.append(f"    .qr-frame.active {{ display: block; }}")
        parts.append(f"    rect.on  {{ fill: {self.color_on}; }}")
        parts.append(f"    rect.off {{ fill: {self.color_off}; }}")
        parts.append("  </style>")

        for fi, matrix in enumerate(matrices):
            frame_data = frames[fi]
            parts.append(
                f'  <g id="frame-{fi}" class="qr-frame{" active" if fi == 0 else ""}" '
                f'data-type="{html.escape(frame_data.payload_type.value)}" '
                f'data-fp="{frame_data.fingerprint()}">'
            )
            for r, row in enumerate(matrix):
                for c, module in enumerate(row):
                    cls = "on" if module else "off"
                    x, y = c * ms, r * ms
                    parts.append(
                        f'    <rect class="{cls}" x="{x}" y="{y}" '
                        f'width="{ms}" height="{ms}"/>'
                    )
            parts.append("  </g>")

        # Embedded JavaScript for frame animation and control
        loop_js = "true" if loop else "false"
        script = f"""
  <script type="text/javascript">
  /* Computational QR – video frame controller */
  (function() {{
    var frames = {n_frames};
    var current = 0;
    var interval = null;
    var looping = {loop_js};
    var duration = {self.frame_duration_ms};

    function showFrame(n) {{
      document.querySelectorAll('.qr-frame').forEach(function(el, i) {{
        el.classList.toggle('active', i === n);
      }});
      current = n;
    }}

    function next() {{
      var n = current + 1;
      if (n >= frames) {{
        if (!looping) {{ stop(); return; }}
        n = 0;
      }}
      showFrame(n);
    }}

    function play() {{
      if (!interval) interval = setInterval(next, duration);
    }}

    function stop() {{
      if (interval) {{ clearInterval(interval); interval = null; }}
    }}

    /* Auto-play on load */
    document.addEventListener('DOMContentLoaded', play);

    /* Expose API on window for external control */
    window.computationalQR = {{ play: play, stop: stop, showFrame: showFrame,
                                frameCount: frames }};
  }})();
  </script>"""
        parts.append(script)
        parts.append("</svg>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Network-graphics descriptor
    # ------------------------------------------------------------------

    def network_descriptor(self, frames: Sequence[QRData]) -> dict:
        """Return a JSON-serialisable descriptor of the video QR sequence.

        This descriptor acts as a "scriptable network graphics" manifest: it
        lists frame fingerprints, types, and timing so that clients can request
        individual frames by fingerprint from a server.
        """
        return {
            "frame_count": len(frames),
            "frame_duration_ms": self.frame_duration_ms,
            "module_size": self.module_size,
            "frames": [
                {
                    "index": i,
                    "type": f.payload_type.value,
                    "fingerprint": f.fingerprint(),
                    "metadata": f.metadata,
                }
                for i, f in enumerate(frames)
            ],
        }

    def network_descriptor_json(self, frames: Sequence[QRData]) -> str:
        return json.dumps(self.network_descriptor(frames), indent=2)
