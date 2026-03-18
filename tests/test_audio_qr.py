"""Tests for computational_qr.media.audio_qr."""

import struct
import pytest

from computational_qr.media.audio_qr import AudioQR


class TestAudioQR:
    def setup_method(self):
        # Use small parameters for speed
        self.aqr = AudioQR(
            sample_rate=8000,
            tone_low=500.0,
            tone_high=1000.0,
            module_duration=0.01,
            row_gap_duration=0.002,
        )

    def _small_matrix(self, rows: int = 5, cols: int = 5) -> list[list[bool]]:
        """Create a simple test matrix."""
        return [
            [(r + c) % 2 == 0 for c in range(cols)]
            for r in range(rows)
        ]

    def test_encode_returns_bytes(self):
        matrix = self._small_matrix()
        pcm = self.aqr.encode_matrix(matrix)
        assert isinstance(pcm, bytes)

    def test_encode_length_proportional_to_matrix(self):
        m5 = self._small_matrix(5, 5)
        m10 = self._small_matrix(10, 10)
        pcm5 = self.aqr.encode_matrix(m5)
        pcm10 = self.aqr.encode_matrix(m10)
        # 10x10 should be longer than 5x5
        assert len(pcm10) > len(pcm5)

    def test_encode_16bit_samples(self):
        matrix = self._small_matrix(2, 2)
        pcm = self.aqr.encode_matrix(matrix)
        assert len(pcm) % 2 == 0  # 16-bit = 2 bytes per sample

    def test_encode_wav_header(self):
        matrix = self._small_matrix(3, 3)
        wav = self.aqr.encode_matrix_to_wav(matrix)
        # RIFF header check
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        assert wav[12:16] == b"fmt "

    def test_wav_sample_rate_in_header(self):
        matrix = self._small_matrix(2, 2)
        wav = self.aqr.encode_matrix_to_wav(matrix)
        # Sample rate at byte offset 24 (little-endian uint32)
        rate = struct.unpack_from("<I", wav, 24)[0]
        assert rate == self.aqr.sample_rate

    def test_decode_matrix_shape(self):
        n_rows, n_cols = 4, 4
        matrix = self._small_matrix(n_rows, n_cols)
        pcm = self.aqr.encode_matrix(matrix)
        decoded = self.aqr.decode_matrix(pcm, n_rows, n_cols)
        assert len(decoded) == n_rows
        for row in decoded:
            assert len(row) == n_cols

    def test_decode_high_confidence_modules(self):
        """All-True matrix should decode mostly as True."""
        matrix = [[True] * 4 for _ in range(4)]
        pcm = self.aqr.encode_matrix(matrix)
        decoded = self.aqr.decode_matrix(pcm, 4, 4)
        true_count = sum(cell for row in decoded for cell in row)
        # At least 75% should be True (allowing for edge effects)
        assert true_count >= 12

    def test_decode_low_confidence_modules(self):
        """All-False matrix should decode mostly as False."""
        matrix = [[False] * 4 for _ in range(4)]
        pcm = self.aqr.encode_matrix(matrix)
        decoded = self.aqr.decode_matrix(pcm, 4, 4)
        false_count = sum(not cell for row in decoded for cell in row)
        assert false_count >= 12

    def test_estimated_duration(self):
        dur = self.aqr.estimated_duration(5, 5)
        # 5*5 modules * 0.01s + 5 rows * 0.002s
        expected = 5 * 5 * 0.01 + 5 * 0.002
        assert dur == pytest.approx(expected, rel=1e-6)

    def test_goertzel_energy_positive(self):
        """Goertzel should return positive energy for a matching sine wave."""
        import math
        sr = self.aqr.sample_rate
        freq = self.aqr.tone_high
        dur = self.aqr.module_duration
        n = int(sr * dur)
        samples = [math.sin(2 * math.pi * freq * t / sr) for t in range(n)]
        energy = self.aqr._goertzel_energy(samples, freq)
        assert energy > 0

    def test_goertzel_energy_empty(self):
        assert self.aqr._goertzel_energy([], 1000.0) == 0.0
