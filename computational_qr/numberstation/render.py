"""WAV rendering for E11 number-station scripts.

Synthesises a mono, 16-bit PCM WAV file from an :class:`E11Script` by
assigning each digit (0-9) a unique sine-wave tone.  No external dependencies
are required—only the Python standard library (``math``, ``struct``,
``wave``).

The tone table is inspired by DTMF but uses a simpler linear spacing so that
no actual telephony frequencies are reproduced.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .e11_script import E11Script

# ---------------------------------------------------------------------------
# Tone table  (digit → frequency in Hz)
# ---------------------------------------------------------------------------
# 10 distinct tones, one per digit, linearly spaced between 800 Hz and 1700 Hz.
_BASE_FREQ = 800.0
_STEP_FREQ = 90.0  # 800, 890, 980, … 1610 Hz
DIGIT_FREQS: dict[int, float] = {d: _BASE_FREQ + d * _STEP_FREQ for d in range(10)}

# ---------------------------------------------------------------------------
# Rendering parameters (can be overridden per call)
# ---------------------------------------------------------------------------
DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_DIGIT_DURATION = 0.08   # seconds per digit tone
DEFAULT_GAP_DURATION = 0.02     # silence between digits
DEFAULT_GROUP_GAP = 0.10        # extra silence between groups
DEFAULT_AMPLITUDE = 0.7         # 0.0 – 1.0


def _sine_samples(
    freq: float,
    duration: float,
    sample_rate: int,
    amplitude: float,
) -> bytes:
    """Return 16-bit PCM bytes for a pure sine tone."""
    n = int(sample_rate * duration)
    samples = bytearray()
    for i in range(n):
        t = i / sample_rate
        val = amplitude * math.sin(2.0 * math.pi * freq * t)
        sample = int(val * 32767)
        samples += struct.pack("<h", max(-32768, min(32767, sample)))
    return bytes(samples)


def _silence_samples(duration: float, sample_rate: int) -> bytes:
    """Return 16-bit PCM bytes of silence."""
    n = int(sample_rate * duration)
    return b"\x00\x00" * n


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM bytes in a RIFF/WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def render_wav(
    script: "E11Script",
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    digit_duration: float = DEFAULT_DIGIT_DURATION,
    gap_duration: float = DEFAULT_GAP_DURATION,
    group_gap: float = DEFAULT_GROUP_GAP,
    amplitude: float = DEFAULT_AMPLITUDE,
    as_pcm: bool = False,
) -> bytes:
    """Render *script* as a WAV (or raw PCM) byte string.

    Parameters
    ----------
    script:
        The :class:`~computational_qr.numberstation.e11_script.E11Script`
        to render.
    sample_rate:
        Audio sample rate in Hz.
    digit_duration:
        Duration of each digit tone in seconds.
    gap_duration:
        Silence inserted between consecutive digits.
    group_gap:
        Additional silence inserted between 5-digit groups.
    amplitude:
        Sine-wave amplitude in the range [0, 1].
    as_pcm:
        When *True*, return raw 16-bit mono PCM instead of a RIFF/WAV
        container.

    Returns
    -------
    bytes
        WAV container bytes (default) or raw PCM bytes when *as_pcm* is
        ``True``.
    """
    pcm_parts: list[bytes] = []

    gap = _silence_samples(gap_duration, sample_rate)
    group_silence = _silence_samples(group_gap, sample_rate)

    for group_idx, group in enumerate(script.groups):
        digits = f"{group:05d}"
        for char_idx, ch in enumerate(digits):
            freq = DIGIT_FREQS[int(ch)]
            pcm_parts.append(_sine_samples(freq, digit_duration, sample_rate, amplitude))
            if char_idx < len(digits) - 1:
                pcm_parts.append(gap)
        # Gap after the group (shorter for last group)
        if group_idx < len(script.groups) - 1:
            pcm_parts.append(group_silence)

    pcm = b"".join(pcm_parts)

    if as_pcm:
        return pcm
    return _pcm_to_wav(pcm, sample_rate)
