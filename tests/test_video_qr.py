"""Tests for computational_qr.media.video_qr."""

import json
import re
import pytest

from computational_qr.core.qr_encoder import QRData, PayloadType
from computational_qr.media.video_qr import VideoQR


def _simple_matrix(size: int = 5) -> list[list[bool]]:
    return [[(r + c) % 2 == 0 for c in range(size)] for r in range(size)]


def _text_data(content: str) -> QRData:
    return QRData(payload_type=PayloadType.TEXT, content=content)


class TestVideoQR:
    def setup_method(self):
        self.vqr = VideoQR(module_size=4, frame_duration_ms=200)

    # ------------------------------------------------------------------
    # matrix_to_svg
    # ------------------------------------------------------------------

    def test_matrix_to_svg_returns_string(self):
        matrix = _simple_matrix(5)
        svg = self.vqr.matrix_to_svg(matrix)
        assert isinstance(svg, str)

    def test_matrix_to_svg_contains_svg_tag(self):
        svg = self.vqr.matrix_to_svg(_simple_matrix(3))
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_matrix_to_svg_dimensions(self):
        n = 5
        matrix = _simple_matrix(n)
        svg = self.vqr.matrix_to_svg(matrix)
        ms = self.vqr.module_size
        expected_dim = str(n * ms)
        assert f'width="{expected_dim}"' in svg
        assert f'height="{expected_dim}"' in svg

    def test_matrix_to_svg_contains_rects(self):
        svg = self.vqr.matrix_to_svg(_simple_matrix(3))
        assert "<rect" in svg

    def test_matrix_to_svg_rect_count(self):
        n = 4
        matrix = _simple_matrix(n)
        svg = self.vqr.matrix_to_svg(matrix)
        rect_count = svg.count("<rect")
        assert rect_count == n * n

    def test_matrix_to_svg_with_title(self):
        svg = self.vqr.matrix_to_svg(_simple_matrix(3), title="Test QR")
        assert "<title>Test QR</title>" in svg

    def test_matrix_to_svg_colors(self):
        vqr = VideoQR(module_size=4, color_on="#112233", color_off="#aabbcc")
        svg = vqr.matrix_to_svg(_simple_matrix(3))
        assert "#112233" in svg
        assert "#aabbcc" in svg

    def test_matrix_to_svg_on_and_off_classes(self):
        svg = self.vqr.matrix_to_svg([[True, False]])
        assert 'class="on"' in svg
        assert 'class="off"' in svg

    # ------------------------------------------------------------------
    # data_to_svg
    # ------------------------------------------------------------------

    def test_data_to_svg(self):
        data = _text_data("hello")
        svg = self.vqr.data_to_svg(data)
        assert "<svg" in svg

    # ------------------------------------------------------------------
    # encode_video
    # ------------------------------------------------------------------

    def test_encode_video_empty_frames(self):
        svg = self.vqr.encode_video([])
        assert "<svg" in svg

    def test_encode_video_single_frame(self):
        frames = [_text_data("frame0")]
        svg = self.vqr.encode_video(frames)
        assert 'id="frame-0"' in svg

    def test_encode_video_multiple_frames(self):
        frames = [_text_data(f"frame{i}") for i in range(3)]
        svg = self.vqr.encode_video(frames)
        for i in range(3):
            assert f'id="frame-{i}"' in svg

    def test_encode_video_contains_script(self):
        frames = [_text_data("a"), _text_data("b")]
        svg = self.vqr.encode_video(frames)
        assert "<script" in svg

    def test_encode_video_frame_count_in_script(self):
        frames = [_text_data(f"x{i}") for i in range(4)]
        svg = self.vqr.encode_video(frames)
        assert "var frames = 4" in svg

    def test_encode_video_loop_false(self):
        frames = [_text_data("a"), _text_data("b")]
        svg = self.vqr.encode_video(frames, loop=False)
        assert "looping = false" in svg

    def test_encode_video_loop_true(self):
        frames = [_text_data("a"), _text_data("b")]
        svg = self.vqr.encode_video(frames, loop=True)
        assert "looping = true" in svg

    def test_encode_video_first_frame_active(self):
        frames = [_text_data("a"), _text_data("b")]
        svg = self.vqr.encode_video(frames)
        # First frame should have "active" class, second should not
        assert 'class="qr-frame active"' in svg

    def test_encode_video_contains_duration(self):
        vqr = VideoQR(module_size=4, frame_duration_ms=750)
        frames = [_text_data("x")]
        svg = vqr.encode_video(frames)
        assert "750" in svg

    def test_encode_video_data_type_attribute(self):
        frames = [
            QRData(payload_type=PayloadType.PROLOG, content="parent(a,b)."),
        ]
        svg = self.vqr.encode_video(frames)
        assert 'data-type="prolog"' in svg

    def test_encode_video_fingerprint_attribute(self):
        data = _text_data("unique")
        frames = [data]
        svg = self.vqr.encode_video(frames)
        assert f'data-fp="{data.fingerprint()}"' in svg

    # ------------------------------------------------------------------
    # network_descriptor
    # ------------------------------------------------------------------

    def test_network_descriptor_structure(self):
        frames = [_text_data("a"), _text_data("b")]
        desc = self.vqr.network_descriptor(frames)
        assert desc["frame_count"] == 2
        assert len(desc["frames"]) == 2

    def test_network_descriptor_json(self):
        frames = [_text_data("x")]
        js = self.vqr.network_descriptor_json(frames)
        parsed = json.loads(js)
        assert parsed["frame_count"] == 1
        assert parsed["frames"][0]["type"] == "text"

    def test_network_descriptor_fingerprints(self):
        d1 = _text_data("alpha")
        d2 = _text_data("beta")
        desc = self.vqr.network_descriptor([d1, d2])
        fps = [f["fingerprint"] for f in desc["frames"]]
        assert fps[0] == d1.fingerprint()
        assert fps[1] == d2.fingerprint()
