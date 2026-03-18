"""Tests for computational_qr.prolog – engine and PrologQR."""

import pytest

from computational_qr.prolog.prolog_engine import (
    Atom,
    Variable,
    Compound,
    PrologFact,
    PrologRule,
    PrologQuery,
    PrologEngine,
    parse_fact,
    parse_rule,
    unify,
    substitute,
)
from computational_qr.prolog.prolog_qr import PrologQR
from computational_qr.core.qr_encoder import PayloadType


# ---------------------------------------------------------------------------
# Term helpers
# ---------------------------------------------------------------------------

class TestUnify:
    def test_atoms_equal(self):
        b = unify(Atom("a"), Atom("a"), {})
        assert b == {}

    def test_atoms_unequal(self):
        b = unify(Atom("a"), Atom("b"), {})
        assert b is None

    def test_var_binds_to_atom(self):
        b = unify(Variable("X"), Atom("hello"), {})
        assert b == {"X": Atom("hello")}

    def test_already_bound_var(self):
        b = unify(Variable("X"), Atom("world"), {"X": Atom("world")})
        assert b is not None  # consistent

    def test_bound_var_conflict(self):
        b = unify(Variable("X"), Atom("world"), {"X": Atom("foo")})
        assert b is None

    def test_compound_unification(self):
        t1 = Compound("f", (Variable("X"), Atom("b")))
        t2 = Compound("f", (Atom("a"), Variable("Y")))
        b = unify(t1, t2, {})
        assert b is not None
        assert b["X"] == Atom("a")
        assert b["Y"] == Atom("b")

    def test_compound_arity_mismatch(self):
        t1 = Compound("f", (Atom("a"),))
        t2 = Compound("f", (Atom("a"), Atom("b")))
        assert unify(t1, t2, {}) is None

    def test_occurs_check(self):
        # X = f(X) should fail
        t = Compound("f", (Variable("X"),))
        b = unify(Variable("X"), t, {})
        assert b is None

    def test_substitute_atom(self):
        result = substitute(Atom("a"), {"X": Atom("b")})
        assert result == Atom("a")

    def test_substitute_var(self):
        result = substitute(Variable("X"), {"X": Atom("hello")})
        assert result == Atom("hello")

    def test_substitute_compound(self):
        t = Compound("p", (Variable("X"), Atom("y")))
        result = substitute(t, {"X": Atom("z")})
        assert isinstance(result, Compound)
        assert result.args[0] == Atom("z")


# ---------------------------------------------------------------------------
# PrologFact / PrologRule
# ---------------------------------------------------------------------------

class TestPrologFact:
    def test_to_prolog(self):
        fact = PrologFact("parent", ("tom", "bob"))
        assert fact.to_prolog() == "parent(tom, bob)."

    def test_head_is_compound(self):
        fact = PrologFact("likes", ("alice", "chocolate"))
        head = fact.head
        assert isinstance(head, Compound)
        assert head.functor == "likes"

    def test_zero_arity(self):
        fact = PrologFact("hello", ())
        assert fact.to_prolog() == "hello."


class TestPrologRule:
    def test_rule_to_prolog_no_body(self):
        head = Compound("foo", (Atom("x"),))
        rule = PrologRule(head=head, body=[])
        assert rule.to_prolog() == "foo(x)."

    def test_rule_to_prolog_with_body(self):
        head = Compound("ancestor", (Variable("X"), Variable("Z")))
        body = [
            Compound("parent", (Variable("X"), Variable("Y"))),
            Compound("ancestor", (Variable("Y"), Variable("Z"))),
        ]
        rule = PrologRule(head=head, body=body)
        text = rule.to_prolog()
        assert ":-" in text
        assert "ancestor" in text

    def test_rename_vars(self):
        head = Compound("p", (Variable("X"),))
        rule = PrologRule(head=head, body=[])
        renamed = rule.rename_vars("42")
        assert renamed.head.args[0] == Variable("X_42")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class TestParser:
    def test_parse_fact_simple(self):
        fact = parse_fact("parent(tom, bob).")
        assert fact.functor == "parent"
        assert fact.args == ("tom", "bob")

    def test_parse_fact_zero_arity(self):
        fact = parse_fact("hello.")
        assert fact.functor == "hello"
        assert fact.args == ()

    def test_parse_rule(self):
        rule = parse_rule("ancestor(?X, ?Y) :- parent(?X, ?Y).")
        assert rule.head.functor == "ancestor"
        assert len(rule.body) == 1

    def test_parse_rule_multi_body(self):
        rule = parse_rule(
            "ancestor(?X, ?Z) :- parent(?X, ?Y), ancestor(?Y, ?Z)."
        )
        assert len(rule.body) == 2


# ---------------------------------------------------------------------------
# PrologEngine
# ---------------------------------------------------------------------------

class TestPrologEngine:
    def setup_method(self):
        self.engine = PrologEngine()
        self.engine.assert_fact("parent", ("tom", "bob"))
        self.engine.assert_fact("parent", ("bob", "ann"))
        self.engine.assert_fact("parent", ("ann", "pat"))
        self.engine.add_rule_text(
            "ancestor(?X, ?Y) :- parent(?X, ?Y)."
        )
        self.engine.add_rule_text(
            "ancestor(?X, ?Z) :- parent(?X, ?Y), ancestor(?Y, ?Z)."
        )

    def test_simple_fact_query(self):
        results = list(self.engine.query_text("parent(tom, ?X)"))
        names = [str(b.get("X", "")) for b in results]
        assert "bob" in names

    def test_ancestor_direct(self):
        results = list(self.engine.query_text("ancestor(tom, ?Who)"))
        found = [str(b.get("Who", b.get("Who_1", ""))) for b in results]
        # tom → bob is a direct parent / ancestor
        assert any("bob" in name for name in found)

    def test_ancestor_transitive(self):
        results = list(self.engine.query_text("ancestor(tom, ?Who)"))
        found = {
            str(v) for b in results for v in b.values()
        }
        assert "ann" in found or "pat" in found

    def test_ask_true(self):
        goal = Compound("parent", (Atom("tom"), Atom("bob")))
        assert self.engine.ask(goal) is True

    def test_ask_false(self):
        goal = Compound("parent", (Atom("bob"), Atom("tom")))
        assert self.engine.ask(goal) is False

    def test_retract(self):
        removed = self.engine.retract("parent", 2)
        assert removed == 3  # three parent facts

    def test_dump_program(self):
        prog = self.engine.dump_program()
        assert "parent" in prog

    def test_clauses_for(self):
        clauses = self.engine.clauses_for("parent", 2)
        assert len(clauses) == 3


# ---------------------------------------------------------------------------
# PrologQR
# ---------------------------------------------------------------------------

class TestPrologQR:
    def setup_method(self):
        self.pqr = PrologQR()

    def _make_engine(self) -> PrologEngine:
        e = PrologEngine()
        e.assert_fact("parent", ("tom", "bob"))
        e.assert_fact("parent", ("bob", "ann"))
        e.add_rule_text("ancestor(?X, ?Y) :- parent(?X, ?Y).")
        e.add_rule_text("ancestor(?X, ?Z) :- parent(?X, ?Y), ancestor(?Y, ?Z).")
        return e

    def test_encode_returns_prolog_type(self):
        engine = self._make_engine()
        data = self.pqr.encode_engine(engine)
        assert data.payload_type == PayloadType.PROLOG

    def test_decode_recovers_clauses(self):
        engine = self._make_engine()
        data = self.pqr.encode_engine(engine)
        restored = self.pqr.decode(data)
        # Should have 4 clauses (2 facts + 2 rules)
        assert len(restored._clauses) == 4

    def test_wrong_payload_type_raises(self):
        from computational_qr.core.qr_encoder import QRData, PayloadType
        data = QRData(payload_type=PayloadType.TEXT, content="hello")
        with pytest.raises(ValueError, match="payload type"):
            self.pqr.decode(data)

    def test_execute_from_data(self):
        engine = self._make_engine()
        data = self.pqr.encode_engine(engine)
        results = self.pqr.execute_from_data(data, "parent(tom, ?X)")
        assert len(results) >= 1
        names = [r.get("X", "") for r in results]
        assert "bob" in names

    def test_execute_from_data_no_results(self):
        engine = self._make_engine()
        data = self.pqr.encode_engine(engine)
        results = self.pqr.execute_from_data(data, "parent(nobody, ?X)")
        assert results == []

    def test_encode_program_text(self):
        prog = "parent(alice, bob).\nparent(bob, carol)."
        data = self.pqr.encode_program(prog)
        assert data.payload_type == PayloadType.PROLOG

    def test_encode_to_matrix(self):
        engine = self._make_engine()
        matrix = self.pqr.encode_to_matrix(engine)
        assert isinstance(matrix, list)
        assert isinstance(matrix[0][0], bool)

    def test_metadata_preserved(self):
        engine = self._make_engine()
        data = self.pqr.encode_engine(engine, metadata={"author": "test"})
        assert data.metadata["author"] == "test"

    def test_prolog_executable_outside_database(self):
        """Core requirement: Prolog stored in QR can be executed without DB."""
        prog = (
            "fact(a).\n"
            "fact(b).\n"
            "fact(c).\n"
        )
        data = self.pqr.encode_program(prog)
        # Execute without any database—purely from the QR data object
        results = self.pqr.execute_from_data(data, "fact(?X)")
        values = {r.get("X", "") for r in results}
        assert {"a", "b", "c"} == values
