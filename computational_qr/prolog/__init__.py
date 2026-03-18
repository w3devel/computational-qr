"""computational_qr.prolog – Prolog logic engine, QR encoding and execution."""

from .prolog_engine import PrologFact, PrologRule, PrologQuery, PrologEngine
from .prolog_qr import PrologQR

__all__ = [
    "PrologFact",
    "PrologRule",
    "PrologQuery",
    "PrologEngine",
    "PrologQR",
]
