"""Pure-Python Prolog-style logic engine.

This module implements a minimal Horn-clause resolution engine so that Prolog
facts and rules can be used *without* an external SWI-Prolog installation.
The engine supports:

* Ground facts – ``parent(tom, bob).``
* Rules with variable unification – ``ancestor(X, Z) :- parent(X, Y), ancestor(Y, Z).``
* Simple queries – ``ancestor(tom, ?X)``

Variables begin with ``?`` (to distinguish them from constants without
requiring full Prolog tokenisation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Generator, Iterable


# ---------------------------------------------------------------------------
# Term representation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Atom:
    """A Prolog atom or constant (lowercase name or quoted string)."""
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Variable:
    """A Prolog variable (starts with uppercase or ``?`` in our syntax)."""
    name: str

    def __str__(self) -> str:
        return f"?{self.name}"


@dataclass(frozen=True)
class Compound:
    """A compound term: ``functor(arg1, arg2, …)``."""
    functor: str
    args: tuple["Term", ...]

    def __str__(self) -> str:
        if not self.args:
            return self.functor
        args_str = ", ".join(str(a) for a in self.args)
        return f"{self.functor}({args_str})"


Term = Atom | Variable | Compound

# ---------------------------------------------------------------------------
# Unification
# ---------------------------------------------------------------------------

Bindings = dict[str, Term]


def _occurs(var_name: str, term: Term, bindings: Bindings) -> bool:
    """Occurs check: return True if *var_name* appears in *term*."""
    if isinstance(term, Variable):
        if term.name == var_name:
            return True
        if term.name in bindings:
            return _occurs(var_name, bindings[term.name], bindings)
        return False
    if isinstance(term, Compound):
        return any(_occurs(var_name, a, bindings) for a in term.args)
    return False


def _walk(term: Term, bindings: Bindings) -> Term:
    """Follow variable bindings until a non-variable or unbound variable."""
    while isinstance(term, Variable) and term.name in bindings:
        term = bindings[term.name]
    return term


def unify(a: Term, b: Term, bindings: Bindings) -> Bindings | None:
    """Try to unify *a* and *b* under *bindings*.

    Returns an extended :class:`Bindings` dict on success, or ``None`` on
    failure.  Does *not* mutate the original *bindings*.
    """
    a = _walk(a, bindings)
    b = _walk(b, bindings)

    if a == b:
        return bindings

    if isinstance(a, Variable):
        if _occurs(a.name, b, bindings):
            return None
        return {**bindings, a.name: b}

    if isinstance(b, Variable):
        if _occurs(b.name, a, bindings):
            return None
        return {**bindings, b.name: a}

    if (
        isinstance(a, Compound)
        and isinstance(b, Compound)
        and a.functor == b.functor
        and len(a.args) == len(b.args)
    ):
        result = bindings
        for x, y in zip(a.args, b.args):
            result = unify(x, y, result)  # type: ignore[arg-type]
            if result is None:
                return None
        return result

    return None


def substitute(term: Term, bindings: Bindings) -> Term:
    """Apply all bindings to *term* recursively."""
    term = _walk(term, bindings)
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(substitute(a, bindings) for a in term.args))
    return term


# ---------------------------------------------------------------------------
# Clause model
# ---------------------------------------------------------------------------

@dataclass
class PrologFact:
    """A ground (variable-free) Prolog fact: ``functor(arg1, …).``"""

    functor: str
    args: tuple[str, ...]

    @property
    def head(self) -> Compound:
        return Compound(self.functor, tuple(Atom(a) for a in self.args))

    def to_prolog(self) -> str:
        if not self.args:
            return f"{self.functor}."
        args_str = ", ".join(self.args)
        return f"{self.functor}({args_str})."

    def __str__(self) -> str:
        return self.to_prolog()


@dataclass
class PrologRule:
    """A Prolog rule: ``head :- body1, body2, …``

    Variables are written with a leading ``?`` and are automatically renamed
    per rule application to avoid cross-clause conflicts.
    """

    head: Compound
    body: list[Compound] = field(default_factory=list)

    def to_prolog(self) -> str:
        head_str = str(self.head)
        if not self.body:
            return f"{head_str}."
        body_str = ", ".join(str(b) for b in self.body)
        return f"{head_str} :- {body_str}."

    def __str__(self) -> str:
        return self.to_prolog()

    def rename_vars(self, suffix: str) -> "PrologRule":
        """Return a copy with all variables renamed to avoid conflicts."""

        def _rename(t: Term) -> Term:
            if isinstance(t, Variable):
                return Variable(f"{t.name}_{suffix}")
            if isinstance(t, Compound):
                return Compound(t.functor, tuple(_rename(a) for a in t.args))
            return t

        new_head = _rename(self.head)
        new_body = [_rename(b) for b in self.body]  # type: ignore[misc]
        return PrologRule(head=new_head, body=new_body)  # type: ignore[arg-type]


@dataclass
class PrologQuery:
    """A Prolog query: a conjunction of goals to be proved."""

    goals: list[Compound]

    def to_prolog(self) -> str:
        return "?- " + ", ".join(str(g) for g in self.goals) + "."

    def __str__(self) -> str:
        return self.to_prolog()


# ---------------------------------------------------------------------------
# Prolog parser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[?A-Za-z_][A-Za-z0-9_]*|[(),.]|'[^']*'")


def _tokenise(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.replace(":-", " :- ").replace("\n", " "))


def _parse_term(tokens: list[str], pos: int) -> tuple[Term, int]:
    """Parse a single term starting at *pos* and return (term, new_pos)."""
    tok = tokens[pos]
    if tok.startswith("?") or (tok[0].isupper()):
        name = tok.lstrip("?")
        return Variable(name), pos + 1

    # Functor or atom
    functor = tok.strip("'")
    if pos + 1 < len(tokens) and tokens[pos + 1] == "(":
        args: list[Term] = []
        pos += 2  # skip '('
        while tokens[pos] != ")":
            if tokens[pos] == ",":
                pos += 1
                continue
            t, pos = _parse_term(tokens, pos)
            args.append(t)
        return Compound(functor, tuple(args)), pos + 1  # skip ')'
    return Atom(functor), pos + 1


def _parse_compound(tokens: list[str], pos: int) -> tuple[Compound, int]:
    t, pos = _parse_term(tokens, pos)
    if not isinstance(t, Compound):
        # Wrap bare atom as zero-arity compound
        t = Compound(t.name if isinstance(t, Atom) else str(t), ())  # type: ignore[union-attr]
    return t, pos  # type: ignore[return-value]


def parse_fact(text: str) -> PrologFact:
    """Parse ``functor(a, b).`` into a :class:`PrologFact`."""
    text = text.strip().rstrip(".")
    tokens = _tokenise(text)
    t, _ = _parse_term(tokens, 0)
    if isinstance(t, Compound):
        return PrologFact(
            functor=t.functor,
            args=tuple(str(a) for a in t.args),
        )
    return PrologFact(functor=str(t), args=())


def _split_goals(body_str: str) -> list[str]:
    """Split a Prolog body string into individual goal strings.

    Handles commas that appear *inside* compound term arguments by tracking
    parenthesis depth—only top-level commas are treated as goal separators.
    """
    goals: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in body_str:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            goal = "".join(current).strip()
            if goal:
                goals.append(goal)
            current = []
        else:
            current.append(ch)
    last = "".join(current).strip()
    if last:
        goals.append(last)
    return goals


def parse_rule(text: str) -> PrologRule:
    """Parse ``head :- body1, body2.`` into a :class:`PrologRule`."""
    text = text.strip().rstrip(".")
    if ":-" in text:
        head_str, body_str = text.split(":-", 1)
    else:
        head_str, body_str = text, ""

    tokens_h = _tokenise(head_str.strip())
    head, _ = _parse_compound(tokens_h, 0)

    body: list[Compound] = []
    for goal_str in _split_goals(body_str):
        toks = _tokenise(goal_str)
        g, _ = _parse_compound(toks, 0)
        body.append(g)

    return PrologRule(head=head, body=body)


# ---------------------------------------------------------------------------
# Prolog engine
# ---------------------------------------------------------------------------

class PrologEngine:
    """Minimal Horn-clause resolution engine.

    Usage::

        engine = PrologEngine()
        engine.assert_fact("parent", ("tom", "bob"))
        engine.assert_fact("parent", ("bob", "ann"))
        engine.add_rule_text("ancestor(?X, ?Z) :- parent(?X, ?Y), ancestor(?Y, ?Z).")
        engine.add_rule_text("ancestor(?X, ?Y) :- parent(?X, ?Y).")

        for bindings in engine.query_text("ancestor(tom, ?Who)"):
            print(bindings)  # {'Who': Atom('ann')}
    """

    def __init__(self) -> None:
        self._clauses: list[PrologRule] = []
        self._counter = 0

    # ------------------------------------------------------------------
    # Knowledge base management
    # ------------------------------------------------------------------

    def assert_fact(self, functor: str, args: Iterable[str]) -> PrologFact:
        """Add a ground fact and return the :class:`PrologFact`."""
        fact = PrologFact(functor=functor, args=tuple(args))
        rule = PrologRule(head=fact.head, body=[])
        self._clauses.append(rule)
        return fact

    def add_rule(self, rule: PrologRule) -> None:
        self._clauses.append(rule)

    def add_rule_text(self, text: str) -> PrologRule:
        """Parse and assert a rule or fact from a Prolog text string."""
        if ":-" in text:
            rule = parse_rule(text)
        else:
            fact = parse_fact(text)
            rule = PrologRule(head=fact.head, body=[])
        self._clauses.append(rule)
        return rule

    def retract(self, functor: str, arity: int) -> int:
        """Remove all clauses with the given *functor* and *arity*; return count."""
        before = len(self._clauses)
        self._clauses = [
            c for c in self._clauses
            if not (c.head.functor == functor and len(c.head.args) == arity)
        ]
        return before - len(self._clauses)

    def clauses_for(self, functor: str, arity: int) -> list[PrologRule]:
        return [
            c for c in self._clauses
            if c.head.functor == functor and len(c.head.args) == arity
        ]

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def _resolve(
        self,
        goals: list[Compound],
        bindings: Bindings,
        depth: int = 0,
        max_depth: int = 512,
    ) -> Generator[Bindings, None, None]:
        if depth > max_depth:
            return
        if not goals:
            yield bindings
            return

        goal = goals[0]
        rest = goals[1:]

        # Walk goal with current bindings
        goal_walked = substitute(goal, bindings)
        if not isinstance(goal_walked, Compound):
            return

        for clause in self.clauses_for(goal_walked.functor, len(goal_walked.args)):
            self._counter += 1
            suffix = str(self._counter)
            renamed = clause.rename_vars(suffix)
            b2 = unify(goal_walked, renamed.head, bindings)
            if b2 is None:
                continue
            new_goals = [
                g for g in renamed.body  # type: ignore[union-attr]
                if isinstance(g, Compound)
            ] + rest
            yield from self._resolve(new_goals, b2, depth + 1, max_depth)

    def query(self, *goals: Compound) -> Generator[Bindings, None, None]:
        """Yield all solutions (variable bindings) for the given goals."""
        yield from self._resolve(list(goals), {})

    def query_text(self, text: str) -> Generator[Bindings, None, None]:
        """Parse a query string and yield all solutions.

        Each yielded :class:`Bindings` dict has *original* query variable names
        as keys (not renamed copies) with fully-substituted :class:`Term` values.
        """
        text = text.strip().lstrip("?-").rstrip(".")

        # Collect query variable names *before* resolution so we can return
        # bindings keyed by the original names rather than the renamed copies
        # produced internally by :meth:`rename_vars`.
        query_vars: set[str] = set()
        goals: list[Compound] = []
        for goal_str in _split_goals(text):
            toks = _tokenise(goal_str)
            g, _ = _parse_compound(toks, 0)
            goals.append(g)
            # Collect variable names from the parsed goal
            self._collect_vars(g, query_vars)

        for raw_bindings in self._resolve(goals, {}):
            # Walk each query variable to its fully-resolved value
            clean: Bindings = {}
            for var_name in query_vars:
                val = substitute(Variable(var_name), raw_bindings)
                clean[var_name] = val
            yield clean

    @staticmethod
    def _collect_vars(term, out: set[str]) -> None:
        """Collect variable names from a term into *out*."""
        if isinstance(term, Variable):
            out.add(term.name)
        elif isinstance(term, Compound):
            for a in term.args:
                PrologEngine._collect_vars(a, out)

    def ask(self, *goals: Compound) -> bool:
        """Return ``True`` if the conjunction of *goals* has at least one solution."""
        return next(self.query(*goals), None) is not None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def dump_program(self) -> str:
        """Return all clauses as a Prolog-syntax string."""
        return "\n".join(c.to_prolog() for c in self._clauses)
