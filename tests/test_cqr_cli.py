"""
tests/test_cqr_cli.py – Integration tests for computational_qr.cqr.cli.
"""

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

from computational_qr.cqr.cli import main
from computational_qr.cqr.payload import unpack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_graph_json(tmp_path: Path, spec: dict) -> Path:
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return p


_SIMPLE_GRAPH = {
    "directed": False,
    "nodes": [{"id": "A"}, {"id": "B"}],
    "edges": [{"src": "A", "dst": "B"}],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEncodeCLI:
    def test_encode_minimal(self, tmp_path, capsys):
        gfile = _write_graph_json(tmp_path, _SIMPLE_GRAPH)
        main(["encode", str(gfile)])
        out = capsys.readouterr().out
        assert "data_hash" in out
        assert "graph_hash" in out
        assert "payload b64" in out

    def test_encode_with_key(self, tmp_path, capsys):
        gfile = _write_graph_json(tmp_path, _SIMPLE_GRAPH)
        main(["encode", str(gfile), "--key", "my-db-key"])
        out = capsys.readouterr().out
        assert "payload b64" in out

    def test_encode_with_data(self, tmp_path, capsys):
        gfile = _write_graph_json(tmp_path, _SIMPLE_GRAPH)
        dfile = tmp_path / "data.bin"
        dfile.write_bytes(b"test data content")
        main(["encode", str(gfile), "--data", str(dfile)])
        out = capsys.readouterr().out
        assert "payload b64" in out

    def test_encode_writes_output_file(self, tmp_path, capsys):
        gfile = _write_graph_json(tmp_path, _SIMPLE_GRAPH)
        out_file = tmp_path / "payload.b64"
        main(["encode", str(gfile), "--out", str(out_file)])
        assert out_file.exists()
        content = out_file.read_text(encoding="ascii")
        # Verify the written content is valid base64 and unpacks cleanly
        raw = base64.b64decode(content)
        p = unpack(raw)
        assert len(p.data_hash) == 32
        assert len(p.graph_hash) == 32

    def test_encode_deterministic(self, tmp_path, capsys):
        """Two encode calls on the same graph produce the same payload."""
        gfile = _write_graph_json(tmp_path, _SIMPLE_GRAPH)
        out1 = tmp_path / "p1.b64"
        out2 = tmp_path / "p2.b64"
        main(["encode", str(gfile), "--out", str(out1)])
        main(["encode", str(gfile), "--out", str(out2)])
        assert out1.read_text() == out2.read_text()


class TestDecodeCLI:
    def _encode_payload(self, tmp_path: Path) -> str:
        gfile = _write_graph_json(tmp_path, _SIMPLE_GRAPH)
        out_file = tmp_path / "payload.b64"
        main(["encode", str(gfile), "--out", str(out_file)])
        return out_file.read_text(encoding="ascii").strip()

    def test_decode_prints_hashes(self, tmp_path, capsys):
        b64 = self._encode_payload(tmp_path)
        main(["decode", b64])
        out = capsys.readouterr().out
        assert "data_hash" in out
        assert "graph_hash" in out

    def test_decode_roundtrip_with_data(self, tmp_path, capsys):
        gfile = _write_graph_json(tmp_path, _SIMPLE_GRAPH)
        dfile = tmp_path / "data.txt"
        dfile.write_bytes(b"roundtrip content")
        out_enc = tmp_path / "payload.b64"
        main(["encode", str(gfile), "--data", str(dfile), "--out", str(out_enc)])

        b64 = out_enc.read_text(encoding="ascii").strip()
        out_dec = tmp_path / "recovered.txt"
        main(["decode", b64, "--out", str(out_dec)])

        assert out_dec.read_bytes() == b"roundtrip content"
