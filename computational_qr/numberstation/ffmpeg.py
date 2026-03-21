"""FFmpeg-qr integration: pipe WAV bytes to a custom ``ffmpeg-qr`` binary.

The output format is selected automatically based on what is installed on
the system:

1. **APNG** – if ``apngasm`` is available (``apngasm --version`` succeeds).
2. **PNG sequence** – if the ``sng`` tool is available (``sng --version`` or
   the ``sng`` package provides the ``sng`` binary).
3. **WAV fallback** – if neither helper tool is available, the WAV bytes are
   written as-is (or piped back to the caller).

All input is piped to ``ffmpeg-qr`` via *stdin*; no temporary files are
written unless an explicit output path is provided.

Usage example
-------------
>>> from computational_qr.numberstation.ffmpeg import transcode
>>> wav_bytes = b"..."   # produced by render.render_wav()
>>> transcode(wav_bytes, out_path="output.apng")
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence, Union


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------

def _tool_available(name: str) -> bool:
    """Return *True* if *name* resolves to an executable on PATH."""
    return shutil.which(name) is not None


def detect_output_format() -> str:
    """Return the preferred output format string based on installed tools.

    Returns
    -------
    str
        One of ``"apng"``, ``"png_sequence"``, or ``"wav"``.
    """
    if _tool_available("apngasm"):
        return "apng"
    if _tool_available("sng"):
        return "png_sequence"
    return "wav"


# ---------------------------------------------------------------------------
# Core transcoding helper
# ---------------------------------------------------------------------------

def transcode(
    wav_bytes: bytes,
    out_path: Union[str, Path, None] = None,
    *,
    ffmpeg_qr_path: str = "ffmpeg-qr",
    output_format: Union[str, None] = None,
    extra_args: Union[Sequence[str], None] = None,
    fps: int = 12,
    scale: Union[str, None] = "512:512",
) -> bytes:
    """Pipe *wav_bytes* to ``ffmpeg-qr`` and return the output as bytes.

    Parameters
    ----------
    wav_bytes:
        A RIFF/WAV byte string (e.g. produced by
        :func:`~computational_qr.numberstation.render.render_wav`).
    out_path:
        Path for the output file.  When *None* the output is captured and
        returned as ``bytes``.
    ffmpeg_qr_path:
        Path to (or name of) the ``ffmpeg-qr`` binary.
    output_format:
        Override the output format.  One of ``"apng"``, ``"png_sequence"``,
        or ``"wav"``.  When *None* (default), :func:`detect_output_format`
        is used.
    extra_args:
        Additional command-line tokens appended after the output arguments.
    fps:
        Frames per second for animated output.
    scale:
        ``WxH`` string for ``-vf scale``.  Pass *None* to skip scaling.
        Uses nearest-neighbour interpolation.

    Returns
    -------
    bytes
        The binary content of the output.  Empty bytes when *out_path* is
        given and the output was written to disk.

    Raises
    ------
    RuntimeError
        If ``ffmpeg-qr`` exits with a non-zero return code.
    FileNotFoundError
        If the ``ffmpeg-qr`` binary is not found.
    """
    fmt = output_format or detect_output_format()
    out = Path(out_path) if out_path else None

    # Build per-format output arguments.
    output_tokens: list[str] = _build_output_tokens(fmt, out, fps=fps, scale=scale)

    if extra_args:
        output_tokens += list(extra_args)

    args = [
        ffmpeg_qr_path,
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
    ] + output_tokens

    proc = subprocess.run(
        args,
        input=wav_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg-qr exited with code {proc.returncode}\n"
            f"cmd: {args}\n"
            f"stderr:\n{proc.stderr.decode('utf-8', errors='replace')}"
        )

    return proc.stdout if out is None else b""


def _build_output_tokens(
    fmt: str,
    out: Union[Path, None],
    *,
    fps: int,
    scale: Union[str, None],
) -> list[str]:
    """Return the list of ffmpeg output tokens for the given format."""
    vf_parts: list[str] = []
    if scale:
        vf_parts.append(f"scale={scale}:flags=neighbor")
    vf_parts.append(f"fps={fps}")

    vf_flag = ["-vf", ",".join(vf_parts)] if vf_parts else []

    if fmt == "apng":
        target = str(out) if out else "pipe:1"
        return vf_flag + ["-pix_fmt", "rgba", "-f", "apng", target]

    if fmt == "png_sequence":
        # For a PNG sequence, out must be a pattern like "frames_%05d.png".
        if out is None:
            target = "frame_%05d.png"
        elif out.suffix.lower() == ".png" and "%" not in str(out):
            # Auto-derive a pattern from the stem.
            target = str(out.parent / (out.stem + "_%05d.png"))
        else:
            target = str(out)
        return vf_flag + ["-pix_fmt", "rgb24", target]

    # WAV fallback – no video processing.
    target = str(out) if out else "pipe:1"
    return ["-f", "wav", target]


# ---------------------------------------------------------------------------
# Streaming variant (for large audio)
# ---------------------------------------------------------------------------

def stream_transcode(
    wav_chunks: "Iterable[bytes]",
    out_path: Union[str, Path],
    *,
    ffmpeg_qr_path: str = "ffmpeg-qr",
    output_format: Union[str, None] = None,
    extra_args: Union[Sequence[str], None] = None,
    fps: int = 12,
    scale: Union[str, None] = "512:512",
) -> None:
    """Stream *wav_chunks* to ``ffmpeg-qr`` without buffering the entire WAV.

    Parameters
    ----------
    wav_chunks:
        An iterable of ``bytes`` chunks that together form a valid WAV
        stream (header first).
    out_path:
        Destination file path.
    ffmpeg_qr_path, output_format, extra_args, fps, scale:
        Same as :func:`transcode`.
    """
    fmt = output_format or detect_output_format()
    out = Path(out_path)
    output_tokens = _build_output_tokens(fmt, out, fps=fps, scale=scale)
    if extra_args:
        output_tokens += list(extra_args)

    args = [
        ffmpeg_qr_path,
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
    ] + output_tokens

    with subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as proc:
        try:
            for chunk in wav_chunks:
                assert proc.stdin is not None
                proc.stdin.write(chunk)
            assert proc.stdin is not None
            proc.stdin.close()
        except BrokenPipeError:
            pass

        assert proc.stderr is not None
        stderr = proc.stderr.read()
        rc = proc.wait()

    if rc != 0:
        raise RuntimeError(
            f"ffmpeg-qr exited with code {rc}\n"
            f"cmd: {args}\n"
            f"stderr:\n{stderr.decode('utf-8', errors='replace')}"
        )
