"""computational_qr.numberstation – Number-station script generation and rendering.

Provides deterministic generation of E11 number-station scripts compatible
with the ``ZapdoZ/numberstations`` input format, plus WAV synthesis and
``ffmpeg-qr`` integration.

Submodules
----------
e11_script
    Build and serialise E11 transmission scripts.
render
    Synthesise WAV audio from an E11 script (stdlib-only).
ffmpeg
    Pipe WAV bytes to a ``ffmpeg-qr`` binary; auto-selects APNG, PNG
    sequence, or WAV output based on installed tools.
"""

from .e11_script import E11Script, generate

__all__ = [
    "E11Script",
    "generate",
]
