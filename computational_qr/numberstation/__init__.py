"""computational_qr.numberstation – Number-station script generation and rendering.

Provides deterministic generation of E11 number-station scripts compatible
with the ``ZapdoZ/numberstations`` input format, plus WAV synthesis,
``ffmpeg-qr`` integration, and the profile-agnostic v2 capsule schema.

Submodules
----------
e11_script
    Build and serialise E11 transmission scripts.
render
    Synthesise WAV audio from an E11 script (stdlib-only).
ffmpeg
    Pipe WAV bytes to a ``ffmpeg-qr`` binary; auto-selects APNG, PNG
    sequence, or WAV output based on installed tools.
capsule
    V2 capsule dataclasses, JSON loader, v1→v2 migration, and
    capsule→E11Script conversion.
"""

from .e11_script import E11Script, generate
from .capsule import (
    CapsuleV2,
    CapsuleProfile,
    CapsuleContent,
    CapsuleMeta,
    CapsuleRender,
    RenderText,
    RenderAudio,
    RenderAudioTTS,
    RenderAudioSamples,
    RepeatPolicy,
    ContentTokens,
    load_capsule,
    upgrade_e11_v1_to_capsule_v2,
    capsule_to_e11_script,
)

__all__ = [
    # Legacy E11
    "E11Script",
    "generate",
    # Capsule v2 – dataclasses
    "CapsuleV2",
    "CapsuleProfile",
    "CapsuleContent",
    "CapsuleMeta",
    "CapsuleRender",
    "RenderText",
    "RenderAudio",
    "RenderAudioTTS",
    "RenderAudioSamples",
    "RepeatPolicy",
    "ContentTokens",
    # Capsule v2 – functions
    "load_capsule",
    "upgrade_e11_v1_to_capsule_v2",
    "capsule_to_e11_script",
]
