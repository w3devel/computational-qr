"""Audio QR: encode QR data as audible / machine-readable audio signals.

Each QR module (black or white square) is mapped to a distinct frequency tone.
The resulting audio waveform can be:

* Saved as a raw PCM ``bytes`` object.
* Played back and re-decoded to recover the original QR matrix.
* Stored as a ``PayloadType.AUDIO`` QR envelope (meta-QR: a QR that carries an
  audio representation of another QR).

Encoding scheme
---------------
The QR matrix is scanned row-by-row, left-to-right.  Each module is encoded
as a short sine-wave tone:

* **Black module** (``True``) → ``tone_high`` Hz
* **White module** (``False``) → ``tone_low``  Hz

The duration of each tone is ``module_duration`` seconds.  A short silence gap
separates rows for easier boundary detection.
"""

from __future__ import annotations

import struct
import math
from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class AudioQR:
    """Encodes and decodes QR matrices as audio waveforms.

    Parameters
    ----------
    sample_rate:
        Audio sample rate in Hz.  Defaults to 44100.
    tone_low:
        Frequency (Hz) for a white (0) QR module.  Defaults to 1000 Hz.
    tone_high:
        Frequency (Hz) for a black (1) QR module.  Defaults to 2000 Hz.
    module_duration:
        Duration of each module tone in seconds.  Defaults to 0.02 s (20 ms).
    row_gap_duration:
        Silence between rows in seconds.  Defaults to 0.005 s (5 ms).
    amplitude:
        Sine wave amplitude in [0, 1].  Defaults to 0.8.
    """

    sample_rate: int = 44100
    tone_low: float = 1000.0
    tone_high: float = 2000.0
    module_duration: float = 0.02
    row_gap_duration: float = 0.005
    amplitude: float = 0.8

    # ------------------------------------------------------------------
    # Waveform primitives
    # ------------------------------------------------------------------

    def _sine_tone(self, frequency: float, duration: float) -> list[float]:
        """Generate a sine-wave tone and return samples as floats in [-1, 1]."""
        n = int(self.sample_rate * duration)
        return [
            self.amplitude * math.sin(2 * math.pi * frequency * t / self.sample_rate)
            for t in range(n)
        ]

    def _silence(self, duration: float) -> list[float]:
        return [0.0] * int(self.sample_rate * duration)

    # ------------------------------------------------------------------
    # Encode
    # ------------------------------------------------------------------

    def encode_matrix(self, matrix: Sequence[Sequence[bool]]) -> bytes:
        """Encode a boolean QR matrix as raw 16-bit signed PCM audio bytes.

        Parameters
        ----------
        matrix:
            2D boolean matrix where ``True`` = black module.

        Returns
        -------
        bytes
            Raw PCM audio data (16-bit signed, little-endian, mono).
        """
        samples: list[float] = []
        for row in matrix:
            for module in row:
                freq = self.tone_high if module else self.tone_low
                samples.extend(self._sine_tone(freq, self.module_duration))
            samples.extend(self._silence(self.row_gap_duration))

        # Convert to 16-bit PCM
        pcm = bytearray()
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            val = int(clamped * 32767)
            pcm.extend(struct.pack("<h", val))
        return bytes(pcm)

    def encode_matrix_to_wav(self, matrix: Sequence[Sequence[bool]]) -> bytes:
        """Encode a QR matrix and wrap the PCM data in a minimal WAV container.

        Returns
        -------
        bytes
            A complete, playable WAV file as bytes.
        """
        pcm_data = self.encode_matrix(matrix)
        return self._wrap_wav(pcm_data)

    def _wrap_wav(self, pcm_data: bytes) -> bytes:
        """Wrap raw 16-bit mono PCM data in a RIFF/WAV header."""
        num_channels = 1
        bits_per_sample = 16
        byte_rate = self.sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(pcm_data)
        chunk_size = 36 + data_size

        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            chunk_size,
            b"WAVE",
            b"fmt ",
            16,            # PCM chunk size
            1,             # Audio format (PCM)
            num_channels,
            self.sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b"data",
            data_size,
        )
        return header + pcm_data

    # ------------------------------------------------------------------
    # Decode
    # ------------------------------------------------------------------

    def decode_matrix(
        self,
        pcm_data: bytes,
        n_rows: int,
        n_cols: int,
    ) -> list[list[bool]]:
        """Decode raw PCM audio bytes back into a boolean QR matrix.

        The decoder analyses the dominant frequency of each expected module
        slot using a simple Goertzel-like energy comparison.

        Parameters
        ----------
        pcm_data:
            Raw 16-bit signed little-endian mono PCM bytes.
        n_rows, n_cols:
            Dimensions of the expected QR matrix.

        Returns
        -------
        list[list[bool]]
        """
        samples_per_module = int(self.sample_rate * self.module_duration)
        samples_per_gap = int(self.sample_rate * self.row_gap_duration)
        samples_per_row = n_cols * samples_per_module + samples_per_gap

        # Unpack PCM
        n_samples = len(pcm_data) // 2
        samples = [
            struct.unpack_from("<h", pcm_data, i * 2)[0] / 32768.0
            for i in range(n_samples)
        ]

        matrix: list[list[bool]] = []
        offset = 0
        for _row in range(n_rows):
            row: list[bool] = []
            for _col in range(n_cols):
                chunk = samples[offset : offset + samples_per_module]
                offset += samples_per_module
                energy_low = self._goertzel_energy(chunk, self.tone_low)
                energy_high = self._goertzel_energy(chunk, self.tone_high)
                row.append(energy_high > energy_low)
            matrix.append(row)
            offset += samples_per_gap  # skip row gap
        return matrix

    def _goertzel_energy(self, samples: list[float], target_freq: float) -> float:
        """Return the Goertzel energy at *target_freq* for the given samples."""
        n = len(samples)
        if n == 0:
            return 0.0
        k = round(n * target_freq / self.sample_rate)
        omega = 2 * math.pi * k / n
        coeff = 2.0 * math.cos(omega)
        s_prev, s_prev2 = 0.0, 0.0
        for x in samples:
            s = x + coeff * s_prev - s_prev2
            s_prev2 = s_prev
            s_prev = s
        return s_prev ** 2 + s_prev2 ** 2 - coeff * s_prev * s_prev2

    # ------------------------------------------------------------------
    # Duration metadata
    # ------------------------------------------------------------------

    def estimated_duration(self, n_rows: int, n_cols: int) -> float:
        """Return the total audio duration in seconds for a given matrix size."""
        return (
            n_rows * n_cols * self.module_duration
            + n_rows * self.row_gap_duration
        )
