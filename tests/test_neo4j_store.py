"""Tests for computational_qr.database.neo4j_store (mock backend)."""

import json
import pytest

from computational_qr.database.neo4j_store import Neo4jStore, QRNode, PrologNode
from computational_qr.core.qr_encoder import QRData, PayloadType


def _text_data(content: str) -> QRData:
    return QRData(payload_type=PayloadType.TEXT, content=content)


def _prolog_data(content: str) -> QRData:
    return QRData(payload_type=PayloadType.PROLOG, content=content)


# ---------------------------------------------------------------------------
# QRNode
# ---------------------------------------------------------------------------

class TestQRNode:
    def test_from_qr_data(self):
        data = _text_data("hello")
        node = QRNode.from_qr_data(data)
        assert node.fingerprint == data.fingerprint()
        assert node.payload_type == "text"

    def test_to_dict_keys(self):
        data = _text_data("test")
        node = QRNode.from_qr_data(data)
        d = node.to_dict()
        assert "fingerprint" in d
        assert "payload_type" in d
        assert "content" in d
        assert "metadata" in d

    def test_metadata_json_serialised(self):
        data = QRData(payload_type=PayloadType.TEXT, content="x",
                      metadata={"key": "value"})
        node = QRNode.from_qr_data(data)
        d = node.to_dict()
        # metadata is stored as a JSON string
        meta = json.loads(d["metadata"])
        assert meta["key"] == "value"


# ---------------------------------------------------------------------------
# PrologNode
# ---------------------------------------------------------------------------

class TestPrologNode:
    def test_construction(self):
        node = PrologNode(
            clause_id="c1",
            functor="parent",
            arity=2,
            prolog_text="parent(tom, bob)",
            is_rule=False,
            qr_fingerprint="fp123",
        )
        assert node.functor == "parent"
        assert not node.is_rule

    def test_to_dict(self):
        node = PrologNode(
            clause_id="c2",
            functor="likes",
            arity=2,
            prolog_text="likes(alice, bob)",
        )
        d = node.to_dict()
        assert d["functor"] == "likes"
        assert d["arity"] == 2


# ---------------------------------------------------------------------------
# Neo4jStore – mock backend
# ---------------------------------------------------------------------------

class TestNeo4jStoreMock:
    def setup_method(self):
        self.store = Neo4jStore(use_mock=True)

    # ------------------------------------------------------------------
    # QR nodes
    # ------------------------------------------------------------------

    def test_store_and_get_qr(self):
        data = _text_data("hello")
        node = QRNode.from_qr_data(data)
        fp = self.store.store_qr(node)
        retrieved = self.store.get_qr(fp)
        assert retrieved is not None
        assert retrieved.fingerprint == fp

    def test_get_qr_not_found(self):
        assert self.store.get_qr("nonexistent") is None

    def test_list_qr_empty(self):
        assert self.store.list_qr() == []

    def test_list_qr_returns_all(self):
        for i in range(3):
            node = QRNode.from_qr_data(_text_data(f"item{i}"))
            self.store.store_qr(node)
        assert len(self.store.list_qr()) == 3

    def test_list_qr_filtered_by_type(self):
        self.store.store_qr(QRNode.from_qr_data(_text_data("a")))
        self.store.store_qr(QRNode.from_qr_data(_prolog_data("parent(x,y).")))
        text_nodes = self.store.list_qr(payload_type="text")
        prolog_nodes = self.store.list_qr(payload_type="prolog")
        assert len(text_nodes) == 1
        assert len(prolog_nodes) == 1

    def test_store_idempotent(self):
        data = _text_data("dup")
        node = QRNode.from_qr_data(data)
        self.store.store_qr(node)
        self.store.store_qr(node)  # second upsert
        # Mock replaces, so still just one entry
        assert len(self.store.list_qr()) == 1

    # ------------------------------------------------------------------
    # Prolog nodes
    # ------------------------------------------------------------------

    def test_store_and_get_prolog(self):
        p = PrologNode(
            clause_id="p1",
            functor="parent",
            arity=2,
            prolog_text="parent(tom, bob)",
        )
        self.store.store_prolog(p)
        retrieved = self.store.get_prolog("p1")
        assert retrieved is not None
        assert retrieved.functor == "parent"

    def test_get_prolog_not_found(self):
        assert self.store.get_prolog("missing") is None

    def test_list_prolog(self):
        for i in range(4):
            self.store.store_prolog(PrologNode(
                clause_id=f"c{i}", functor="fact", arity=1,
                prolog_text=f"fact(x{i})"
            ))
        assert len(self.store.list_prolog()) == 4

    def test_list_prolog_filtered_by_functor(self):
        self.store.store_prolog(PrologNode("a1", "parent", 2, "parent(a,b)"))
        self.store.store_prolog(PrologNode("a2", "likes", 2, "likes(a,b)"))
        parents = self.store.list_prolog(functor="parent")
        assert len(parents) == 1
        assert parents[0].functor == "parent"

    # ------------------------------------------------------------------
    # Intersections
    # ------------------------------------------------------------------

    def test_store_intersection(self):
        d1 = _text_data("a")
        d2 = _text_data("b")
        n1, n2 = QRNode.from_qr_data(d1), QRNode.from_qr_data(d2)
        fp1 = self.store.store_qr(n1)
        fp2 = self.store.store_qr(n2)
        self.store.store_intersection(fp1, fp2, {"distance": 0.3})
        ixs = self.store.list_intersections()
        assert len(ixs) == 1
        assert ixs[0][0] == fp1
        assert ixs[0][1] == fp2
        assert ixs[0][2]["distance"] == pytest.approx(0.3)

    def test_list_intersections_empty(self):
        assert self.store.list_intersections() == []

    # ------------------------------------------------------------------
    # store_prolog_qr
    # ------------------------------------------------------------------

    def test_store_prolog_qr_creates_qr_node(self):
        from computational_qr.prolog.prolog_qr import PrologQR
        pqr = PrologQR()
        prog = "parent(tom, bob).\nparent(bob, ann)."
        data = pqr.encode_program(prog)
        fp = self.store.store_prolog_qr(data, prog)
        node = self.store.get_qr(fp)
        assert node is not None
        assert node.payload_type == "prolog"

    def test_store_prolog_qr_creates_clause_nodes(self):
        from computational_qr.prolog.prolog_qr import PrologQR
        pqr = PrologQR()
        prog = "fact(a).\nfact(b).\nfact(c)."
        data = pqr.encode_program(prog)
        self.store.store_prolog_qr(data, prog)
        clauses = self.store.list_prolog()
        assert len(clauses) == 3

    def test_store_prolog_qr_skips_comments(self):
        from computational_qr.prolog.prolog_qr import PrologQR
        pqr = PrologQR()
        prog = "% This is a comment\nfact(a)."
        data = pqr.encode_program(prog)
        self.store.store_prolog_qr(data, prog)
        clauses = self.store.list_prolog()
        assert len(clauses) == 1

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def test_context_manager(self):
        with Neo4jStore(use_mock=True) as store:
            node = QRNode.from_qr_data(_text_data("ctx"))
            fp = store.store_qr(node)
            assert store.get_qr(fp) is not None
