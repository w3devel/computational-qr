"""Prolog-as-QR: encode Prolog programs into QR codes and execute them.

This module is the bridge between the logic engine
(:mod:`computational_qr.prolog.prolog_engine`) and the QR encoder
(:mod:`computational_qr.core.qr_encoder`).

Key ideas
---------
* A Prolog **program** (facts + rules) is serialised to a compact JSON
  representation and stored as a ``PayloadType.PROLOG`` QR data envelope.
* The QR code can be stored in Neo4j (or any external store) alongside its
  fingerprint.  When retrieved it is *executed* by a local :class:`PrologEngine`
  without requiring the original database connection—the QR itself is the
  portable unit of executable logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from computational_qr.core.qr_encoder import QRData, QREncoder, PayloadType
from computational_qr.prolog.prolog_engine import (
    PrologEngine,
    PrologFact,
    PrologRule,
    PrologQuery,
    Compound,
    Atom,
    Variable,
    Bindings,
    substitute,
)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _term_to_dict(term) -> dict:
    if isinstance(term, Atom):
        return {"type": "atom", "name": term.name}
    if isinstance(term, Variable):
        return {"type": "var", "name": term.name}
    if isinstance(term, Compound):
        return {
            "type": "compound",
            "functor": term.functor,
            "args": [_term_to_dict(a) for a in term.args],
        }
    raise TypeError(f"Unknown term type: {type(term)}")


def _dict_to_term(d: dict):
    t = d["type"]
    if t == "atom":
        return Atom(d["name"])
    if t == "var":
        return Variable(d["name"])
    if t == "compound":
        return Compound(d["functor"], tuple(_dict_to_term(a) for a in d["args"]))
    raise ValueError(f"Unknown term type: {t!r}")


def _rule_to_dict(rule: PrologRule) -> dict:
    return {
        "head": _term_to_dict(rule.head),
        "body": [_term_to_dict(b) for b in rule.body],
    }


def _dict_to_rule(d: dict) -> PrologRule:
    head = _dict_to_term(d["head"])
    body = [_dict_to_term(b) for b in d.get("body", [])]
    return PrologRule(head=head, body=body)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# PrologQR
# ---------------------------------------------------------------------------

@dataclass
class PrologQR:
    """Manages encoding and executing Prolog programs as QR codes.

    Parameters
    ----------
    encoder:
        A :class:`~computational_qr.core.qr_encoder.QREncoder` instance.
        Defaults to a new encoder with ``error_correction="H"`` (the highest
        level, appropriate for executable code payloads).
    """

    encoder: QREncoder = field(
        default_factory=lambda: QREncoder(error_correction="H")
    )

    # ------------------------------------------------------------------
    # Encoding (Prolog → QR)
    # ------------------------------------------------------------------

    def encode_engine(
        self,
        engine: PrologEngine,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> QRData:
        """Serialise all clauses in *engine* into a :class:`QRData` envelope.

        The resulting ``QRData`` can be stored as-is (e.g. in Neo4j) or
        rendered to an image / SVG via :attr:`encoder`.
        """
        clauses = [_rule_to_dict(r) for r in engine._clauses]
        payload = json.dumps({"clauses": clauses}, separators=(",", ":"))
        return QRData(
            payload_type=PayloadType.PROLOG,
            content=payload,
            metadata=metadata or {},
        )

    def encode_program(
        self,
        prolog_text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> QRData:
        """Parse *prolog_text* (one clause per line) and encode as QR data."""
        engine = PrologEngine()
        for line in prolog_text.splitlines():
            line = line.strip()
            if line and not line.startswith("%"):
                engine.add_rule_text(line)
        return self.encode_engine(engine, metadata=metadata)

    # ------------------------------------------------------------------
    # Decoding (QR → Prolog engine)
    # ------------------------------------------------------------------

    def decode(self, qr_data: QRData) -> PrologEngine:
        """Reconstruct a :class:`PrologEngine` from a ``PROLOG`` QR envelope.

        The engine is fully self-contained and can be queried immediately
        without any database connection.
        """
        if qr_data.payload_type != PayloadType.PROLOG:
            raise ValueError(
                f"Expected payload type 'prolog', got {qr_data.payload_type!r}"
            )
        content = qr_data.content
        if isinstance(content, (bytes, bytearray)):
            content = content.decode()
        obj = json.loads(content)
        engine = PrologEngine()
        for clause_dict in obj.get("clauses", []):
            engine.add_rule(_dict_to_rule(clause_dict))
        return engine

    # ------------------------------------------------------------------
    # Convenience: round-trip through the QR matrix
    # ------------------------------------------------------------------

    def encode_to_matrix(self, engine: PrologEngine) -> list[list[bool]]:
        """Encode *engine* to a boolean QR matrix (no image dependency)."""
        data = self.encode_engine(engine)
        return self.encoder.encode_matrix(data)

    def execute_from_data(
        self, qr_data: QRData, query_text: str
    ) -> list[dict[str, str]]:
        """Decode *qr_data*, run *query_text*, and return binding dicts.

        This is the primary "execute Prolog outside the database" entry point.
        The QR data carries the program; the caller supplies only the query.
        The returned bindings use the original query variable names as keys
        with their fully-resolved string values.

        Example
        -------
        >>> pqr = PrologQR()
        >>> data = pqr.encode_program("parent(tom, bob).\\nparent(bob, ann).")
        >>> results = pqr.execute_from_data(data, "parent(tom, ?X)")
        >>> [r["X"] for r in results]
        ['bob']
        """
        engine = self.decode(qr_data)
        solutions: list[dict[str, str]] = []
        for bindings in engine.query_text(query_text):
            row: dict[str, str] = {k: str(v) for k, v in bindings.items()}
            solutions.append(row)
        return solutions

    # ------------------------------------------------------------------
    # Prolog text ↔ QR image (convenience wrappers)
    # ------------------------------------------------------------------

    def program_to_image(self, prolog_text: str):
        """Encode *prolog_text* and return a PIL Image."""
        data = self.encode_program(prolog_text)
        return self.encoder.encode_image(data)

    def program_to_svg(self, prolog_text: str) -> str:
        """Encode *prolog_text* and return an SVG string."""
        data = self.encode_program(prolog_text)
        return self.encoder.encode_svg(data)
