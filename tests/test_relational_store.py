"""Tests for computational_qr.database.relational_store (SQLite in-memory)."""

from __future__ import annotations

import uuid

import pytest

from computational_qr.core.qr_encoder import QRData, PayloadType
from computational_qr.database.relational_store import RelationalQRStore, QRRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_data(content: str) -> QRData:
    return QRData(payload_type=PayloadType.TEXT, content=content)


def _prolog_data(content: str) -> QRData:
    return QRData(payload_type=PayloadType.PROLOG, content=content)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# RelationalQRStore – basic CRUD
# ---------------------------------------------------------------------------

class TestRelationalQRStoreBasic:
    """Tests that run entirely against SQLite in-memory – no external services."""

    def setup_method(self):
        self.store = RelationalQRStore("sqlite:///:memory:")
        self.store.connect()

    def teardown_method(self):
        self.store.close()

    # ------------------------------------------------------------------
    # store / get by UUID
    # ------------------------------------------------------------------

    def test_store_returns_qr_record(self):
        data = _text_data("hello")
        record = self.store.store_qr(data, render_png=False, render_svg=False)
        assert isinstance(record, QRRecord)
        assert isinstance(record.id, uuid.UUID)

    def test_store_and_get_by_uuid(self):
        data = _text_data("hello world")
        stored = self.store.store_qr(data, render_png=False, render_svg=False)
        retrieved = self.store.get_qr(stored.id)
        assert retrieved is not None
        assert retrieved.id == stored.id
        assert retrieved.qr_data.content == "hello world"

    def test_get_qr_not_found_returns_none(self):
        assert self.store.get_qr(uuid.uuid4()) is None

    # ------------------------------------------------------------------
    # fingerprint lookup
    # ------------------------------------------------------------------

    def test_fingerprint_lookup_returns_same_uuid(self):
        data = _text_data("fingerprint test")
        stored = self.store.store_qr(data, render_png=False, render_svg=False)
        by_fp = self.store.get_by_fingerprint(stored.fingerprint)
        assert by_fp is not None
        assert by_fp.id == stored.id

    def test_get_by_fingerprint_not_found_returns_none(self):
        assert self.store.get_by_fingerprint("nonexistent") is None

    # ------------------------------------------------------------------
    # explicit UUID
    # ------------------------------------------------------------------

    def test_store_with_explicit_uuid(self):
        my_id = uuid.uuid4()
        data = _text_data("explicit id")
        record = self.store.store_qr(data, qr_id=my_id, render_png=False, render_svg=False)
        assert record.id == my_id

    # ------------------------------------------------------------------
    # upsert / idempotency
    # ------------------------------------------------------------------

    def test_store_same_fingerprint_twice_upserts(self):
        data = _text_data("dup")
        r1 = self.store.store_qr(data, render_png=False, render_svg=False)
        r2 = self.store.store_qr(data, render_png=False, render_svg=False)
        assert r1.id == r2.id
        assert len(self.store.list_qr()) == 1

    # ------------------------------------------------------------------
    # list_qr
    # ------------------------------------------------------------------

    def test_list_qr_empty(self):
        assert self.store.list_qr() == []

    def test_list_qr_returns_all(self):
        for i in range(3):
            self.store.store_qr(_text_data(f"item{i}"), render_png=False, render_svg=False)
        assert len(self.store.list_qr()) == 3

    def test_list_qr_filtered_by_payload_type(self):
        self.store.store_qr(_text_data("a"), render_png=False, render_svg=False)
        self.store.store_qr(_prolog_data("fact(x)."), render_png=False, render_svg=False)
        text = self.store.list_qr(payload_type="text")
        prolog = self.store.list_qr(payload_type="prolog")
        assert len(text) == 1
        assert len(prolog) == 1

    def test_list_qr_limit_offset(self):
        for i in range(5):
            self.store.store_qr(_text_data(f"page{i}"), render_png=False, render_svg=False)
        page1 = self.store.list_qr(limit=3, offset=0)
        page2 = self.store.list_qr(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 2

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def test_delete_qr(self):
        data = _text_data("to delete")
        record = self.store.store_qr(data, render_png=False, render_svg=False)
        assert self.store.delete_qr(record.id) is True
        assert self.store.get_qr(record.id) is None

    def test_delete_nonexistent_returns_false(self):
        assert self.store.delete_qr(uuid.uuid4()) is False

    # ------------------------------------------------------------------
    # payload_type stored correctly
    # ------------------------------------------------------------------

    def test_payload_type_stored(self):
        data = _prolog_data("parent(a, b).")
        record = self.store.store_qr(data, render_png=False, render_svg=False)
        retrieved = self.store.get_qr(record.id)
        assert retrieved.payload_type == "prolog"
        assert retrieved.qr_data.payload_type == PayloadType.PROLOG

    # ------------------------------------------------------------------
    # timestamps
    # ------------------------------------------------------------------

    def test_created_at_is_set(self):
        record = self.store.store_qr(_text_data("ts"), render_png=False, render_svg=False)
        assert record.created_at is not None


# ---------------------------------------------------------------------------
# RelationalQRStore – artifacts
# ---------------------------------------------------------------------------

class TestRelationalQRStoreArtifacts:
    """Tests for PNG/SVG artifact rendering and retrieval."""

    def setup_method(self):
        self.store = RelationalQRStore("sqlite:///:memory:")
        self.store.connect()

    def teardown_method(self):
        self.store.close()

    def test_store_with_png_artifact(self):
        data = _text_data("png test")
        record = self.store.store_qr(data, render_png=True, render_svg=False)
        assert record.png_bytes is not None
        assert record.png_bytes[:8] == PNG_SIGNATURE

    def test_store_with_svg_artifact(self):
        data = _text_data("svg test")
        record = self.store.store_qr(data, render_png=False, render_svg=True)
        assert record.svg_text is not None
        assert "<svg" in record.svg_text.lower()

    def test_get_png_returns_bytes(self):
        data = _text_data("get png")
        record = self.store.store_qr(data, render_png=True, render_svg=False)
        png = self.store.get_png(record.id)
        assert png is not None
        assert png[:8] == PNG_SIGNATURE

    def test_get_svg_returns_string(self):
        data = _text_data("get svg")
        record = self.store.store_qr(data, render_png=False, render_svg=True)
        svg = self.store.get_svg(record.id)
        assert svg is not None
        assert "<svg" in svg.lower()

    def test_get_png_not_rendered_returns_none(self):
        data = _text_data("no png")
        record = self.store.store_qr(data, render_png=False, render_svg=False)
        assert self.store.get_png(record.id) is None

    def test_get_svg_not_rendered_returns_none(self):
        data = _text_data("no svg")
        record = self.store.store_qr(data, render_png=False, render_svg=False)
        assert self.store.get_svg(record.id) is None

    def test_get_png_nonexistent_id_returns_none(self):
        assert self.store.get_png(uuid.uuid4()) is None

    def test_get_svg_nonexistent_id_returns_none(self):
        assert self.store.get_svg(uuid.uuid4()) is None

    def test_render_spec_stored(self):
        data = _text_data("render spec")
        record = self.store.store_qr(
            data,
            render_png=True,
            render_svg=False,
            fill_color="blue",
            back_color="white",
            error_correction="H",
            box_size=8,
            border=2,
        )
        spec = record.render_spec
        assert spec["fill_color"] == "blue"
        assert spec["error_correction"] == "H"
        assert spec["box_size"] == 8
        assert spec["border"] == 2

    def test_upsert_updates_artifact(self):
        """Re-storing the same fingerprint with render_png=True should update artifacts."""
        data = _text_data("upsert artifact")
        r1 = self.store.store_qr(data, render_png=False, render_svg=False)
        assert r1.png_bytes is None

        r2 = self.store.store_qr(data, render_png=True, render_svg=False)
        assert r2.id == r1.id
        assert r2.png_bytes is not None
        assert r2.png_bytes[:8] == PNG_SIGNATURE


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestRelationalQRStoreContextManager:
    def test_context_manager_store_and_retrieve(self):
        with RelationalQRStore("sqlite:///:memory:") as store:
            data = _text_data("ctx manager")
            record = store.store_qr(data, render_png=False, render_svg=False)
            retrieved = store.get_qr(record.id)
            assert retrieved is not None
            assert retrieved.id == record.id

    def test_error_without_connect(self):
        store = RelationalQRStore("sqlite:///:memory:")
        with pytest.raises(RuntimeError, match="not connected"):
            store.list_qr()
