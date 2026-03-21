"""Tests for computational_qr.numberstation.e11_script."""

from __future__ import annotations

import io
import math
import struct
import sys
import wave
from pathlib import Path

import pytest

from computational_qr.numberstation.e11_script import (
    E11Script,
    _seed_from_string,
    generate,
    main,
)
from computational_qr.numberstation.render import (
    DIGIT_FREQS,
    render_wav,
)


# ---------------------------------------------------------------------------
# E11Script.to_text() formatting tests
# ---------------------------------------------------------------------------

class TestE11ScriptFormat:
    def _script(self, station_id: int = 42, group_count: int = 3) -> E11Script:
        return generate(0, group_count=group_count, station_id=station_id)

    def test_exactly_four_lines(self):
        text = self._script().to_text()
        lines = text.split("\n")
        # split by "\n" on "a\nb\nc\nd\n" gives ["a","b","c","d",""]
        assert len(lines) == 5
        assert lines[-1] == ""  # trailing newline produces empty final element

    def test_trailing_newline(self):
        text = self._script().to_text()
        assert text.endswith("\n")

    def test_first_line_is_E11(self):
        text = self._script().to_text()
        assert text.split("\n")[0] == "E11"

    def test_station_id_is_three_digits(self):
        for sid in (0, 7, 42, 100, 999):
            script = generate(0, group_count=1, station_id=sid)
            id_line = script.to_text().split("\n")[1]
            assert len(id_line) == 3, f"station ID line '{id_line}' is not 3 chars"
            assert id_line.isdigit()

    def test_groups_are_five_digits(self):
        script = generate(12345, group_count=10)
        groups_line = script.to_text().split("\n")[3]
        for grp in groups_line.split():
            assert len(grp) == 5, f"group '{grp}' is not 5 chars"
            assert grp.isdigit()

    def test_group_count_line_matches_actual_groups(self):
        for n in (1, 5, 20):
            script = generate("test", group_count=n)
            lines = script.to_text().split("\n")
            declared = int(lines[2])
            actual = len(lines[3].split())
            assert declared == n
            assert actual == n

    def test_leading_zero_station_id(self):
        script = generate(0, group_count=1, station_id=7)
        assert script.to_text().split("\n")[1] == "007"

    def test_leading_zero_groups(self):
        # Force a group value < 10000 to verify zero-padding.
        script = E11Script(station_id=1, group_count=1, groups=[5])
        assert script.to_text().split("\n")[3] == "00005"


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_string_seed_gives_same_output(self):
        s1 = generate("hello world", group_count=15)
        s2 = generate("hello world", group_count=15)
        assert s1.to_text() == s2.to_text()

    def test_same_int_seed_gives_same_output(self):
        s1 = generate(98765, group_count=10)
        s2 = generate(98765, group_count=10)
        assert s1.to_text() == s2.to_text()

    def test_different_string_seeds_give_different_outputs(self):
        s1 = generate("alpha-seed", group_count=20)
        s2 = generate("omega-seed", group_count=20)
        # Extremely unlikely to collide for unrelated seeds.
        assert s1.to_text() != s2.to_text()

    def test_string_and_int_seed_consistency(self):
        """A string seed must hash consistently to the same int."""
        seed_str = "reproducible"
        int_seed = _seed_from_string(seed_str)
        s1 = generate(seed_str, group_count=8)
        s2 = generate(int_seed, group_count=8)
        assert s1.to_text() == s2.to_text()

    def test_different_group_counts_differ(self):
        s1 = generate("fixed", group_count=5)
        s2 = generate("fixed", group_count=10)
        # Different group counts must produce different texts.
        assert s1.to_text() != s2.to_text()


# ---------------------------------------------------------------------------
# _seed_from_string tests
# ---------------------------------------------------------------------------

class TestSeedFromString:
    def test_returns_int(self):
        assert isinstance(_seed_from_string("test"), int)

    def test_stable(self):
        assert _seed_from_string("abc") == _seed_from_string("abc")

    def test_distinct_inputs(self):
        assert _seed_from_string("foo") != _seed_from_string("bar")

    def test_non_negative(self):
        assert _seed_from_string("x") >= 0


# ---------------------------------------------------------------------------
# E11Script.write() helper
# ---------------------------------------------------------------------------

class TestWrite:
    def test_write_creates_file(self, tmp_path: Path):
        script = generate("write-test", group_count=3)
        out = tmp_path / "station.txt"
        script.write(out)
        assert out.exists()

    def test_write_content_matches_to_text(self, tmp_path: Path):
        script = generate("write-test-2", group_count=5)
        out = tmp_path / "station.txt"
        script.write(out)
        content = out.read_text(encoding="utf-8")
        assert content == script.to_text()


# ---------------------------------------------------------------------------
# CLI (main()) tests
# ---------------------------------------------------------------------------

class TestCLI:
    def test_stdout_output(self, capsys):
        main(["--seed", "cli-test", "--groups", "4"])
        out = capsys.readouterr().out
        lines = out.split("\n")
        assert lines[0] == "E11"
        assert len(lines) == 5  # 4 content lines + trailing empty

    def test_file_output(self, tmp_path: Path, capsys):
        out_file = tmp_path / "cli_out.txt"
        main(["--seed", "cli-file-test", "--groups", "3", "--out", str(out_file)])
        captured = capsys.readouterr()
        assert captured.out == ""  # nothing to stdout
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert content.startswith("E11\n")

    def test_numeric_seed_string(self, capsys):
        """Numeric seeds passed as strings on CLI are accepted."""
        main(["--seed", "12345", "--groups", "2"])
        out = capsys.readouterr().out
        assert out.startswith("E11\n")

    def test_determinism_via_cli(self, capsys):
        main(["--seed", "determinism", "--groups", "10"])
        run1 = capsys.readouterr().out
        main(["--seed", "determinism", "--groups", "10"])
        run2 = capsys.readouterr().out
        assert run1 == run2


# ---------------------------------------------------------------------------
# render_wav tests
# ---------------------------------------------------------------------------

class TestRenderWav:
    def _script(self, group_count: int = 2) -> E11Script:
        return generate("render-test", group_count=group_count)

    def test_returns_bytes(self):
        wav = render_wav(self._script())
        assert isinstance(wav, bytes)

    def test_valid_wav_header(self):
        wav = render_wav(self._script())
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"

    def test_sample_rate_in_header(self):
        sr = 22050
        wav = render_wav(self._script(), sample_rate=sr)
        actual_rate = struct.unpack_from("<I", wav, 24)[0]
        assert actual_rate == sr

    def test_pcm_mode_no_riff(self):
        pcm = render_wav(self._script(), as_pcm=True)
        assert pcm[:4] != b"RIFF"

    def test_more_groups_longer_audio(self):
        short = render_wav(self._script(group_count=1))
        longer = render_wav(self._script(group_count=5))
        assert len(longer) > len(short)

    def test_digit_freqs_count(self):
        assert len(DIGIT_FREQS) == 10
        for d in range(10):
            assert d in DIGIT_FREQS
            assert DIGIT_FREQS[d] > 0
