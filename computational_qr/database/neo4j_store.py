"""Neo4j graph-database integration for computational QR.

``Neo4jStore`` stores and retrieves:

* **QR nodes** – individual :class:`~computational_qr.core.qr_encoder.QRData`
  envelopes identified by their fingerprint.
* **Prolog nodes** – individual Prolog clauses (facts and rules) with
  relationships to the QR codes that contain them.
* **Intersection relationships** – links between QR/data nodes that represent
  where data intersects in 3D graph space.

The driver is lazy-imported so that the rest of the package works without a
live Neo4j instance.  Use :meth:`connect` to open a session and
:meth:`close` to release resources.

For testing without a running Neo4j server, set ``use_mock=True`` in the
constructor.  The mock backend stores everything in memory using the same
API surface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

@dataclass
class QRNode:
    """Represents a single QR code stored in the graph database.

    Parameters
    ----------
    fingerprint:
        SHA-256-derived identifier (from :meth:`~QRData.fingerprint`).
    payload_type:
        String label for the payload type (``"prolog"``, ``"audio"``, etc.).
    content:
        The serialised JSON payload.
    metadata:
        Arbitrary key-value properties.
    """

    fingerprint: str
    payload_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "payload_type": self.payload_type,
            "content": self.content,
            "metadata": json.dumps(self.metadata),
        }

    @classmethod
    def from_qr_data(cls, qr_data) -> "QRNode":
        """Construct a :class:`QRNode` from a
        :class:`~computational_qr.core.qr_encoder.QRData` object."""
        return cls(
            fingerprint=qr_data.fingerprint(),
            payload_type=qr_data.payload_type.value,
            content=qr_data.to_json(),
            metadata=qr_data.metadata,
        )


@dataclass
class PrologNode:
    """Represents a single Prolog clause (fact or rule) in the graph database.

    Parameters
    ----------
    clause_id:
        Unique identifier for this clause within the knowledge base.
    functor:
        The head functor of the clause.
    arity:
        Number of arguments in the head.
    prolog_text:
        The clause in Prolog syntax (``"parent(tom, bob)."``).
    is_rule:
        ``True`` if this is a rule (has a body), ``False`` for a plain fact.
    qr_fingerprint:
        Fingerprint of the QR code that *contains* this clause.
    """

    clause_id: str
    functor: str
    arity: int
    prolog_text: str
    is_rule: bool = False
    qr_fingerprint: str = ""

    def to_dict(self) -> dict:
        return {
            "clause_id": self.clause_id,
            "functor": self.functor,
            "arity": self.arity,
            "prolog_text": self.prolog_text,
            "is_rule": self.is_rule,
            "qr_fingerprint": self.qr_fingerprint,
        }


# ---------------------------------------------------------------------------
# In-memory mock backend
# ---------------------------------------------------------------------------

class _MockDriver:
    """Minimal in-memory Neo4j driver mock for testing."""

    def __init__(self) -> None:
        self._qr: dict[str, dict] = {}          # fingerprint → props
        self._prolog: dict[str, dict] = {}       # clause_id → props
        self._intersects: list[tuple[str, str, dict]] = []  # (fp_a, fp_b, props)
        self._contains: list[tuple[str, str]] = []          # (fp, clause_id)

    def store_qr(self, props: dict) -> None:
        self._qr[props["fingerprint"]] = props

    def get_qr(self, fingerprint: str) -> dict | None:
        return self._qr.get(fingerprint)

    def list_qr(self, payload_type: str | None = None) -> list[dict]:
        nodes = list(self._qr.values())
        if payload_type:
            nodes = [n for n in nodes if n["payload_type"] == payload_type]
        return nodes

    def store_prolog(self, props: dict) -> None:
        self._prolog[props["clause_id"]] = props

    def get_prolog(self, clause_id: str) -> dict | None:
        return self._prolog.get(clause_id)

    def list_prolog(self, functor: str | None = None) -> list[dict]:
        clauses = list(self._prolog.values())
        if functor:
            clauses = [c for c in clauses if c["functor"] == functor]
        return clauses

    def store_intersection(
        self, fp_a: str, fp_b: str, props: dict | None = None
    ) -> None:
        self._intersects.append((fp_a, fp_b, props or {}))

    def list_intersections(self) -> list[tuple[str, str, dict]]:
        return list(self._intersects)

    def link_contains(self, qr_fp: str, clause_id: str) -> None:
        self._contains.append((qr_fp, clause_id))

    def clauses_in_qr(self, qr_fp: str) -> list[str]:
        return [cid for fp, cid in self._contains if fp == qr_fp]

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Neo4jStore
# ---------------------------------------------------------------------------

class Neo4jStore:
    """High-level interface for storing computational QR data in Neo4j.

    Parameters
    ----------
    uri:
        Bolt URI of the Neo4j instance, e.g. ``"bolt://localhost:7687"``.
    user, password:
        Authentication credentials.
    database:
        Name of the Neo4j database.  Defaults to ``"neo4j"``.
    use_mock:
        If ``True`` the store uses an in-memory mock backend instead of a
        real Neo4j connection.  Useful for unit-testing.
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
        use_mock: bool = False,
    ) -> None:
        self.uri = uri
        self.user = user
        self.database = database
        self._use_mock = use_mock
        self._driver: Any = None
        self._mock: _MockDriver | None = None

        if use_mock:
            self._mock = _MockDriver()
        else:
            self._driver = None  # Opened lazily in connect()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "Neo4jStore":
        """Open a connection to the Neo4j database (no-op for mock)."""
        if self._use_mock:
            return self
        try:
            from neo4j import GraphDatabase  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "The 'neo4j' package is required. "
                "Install it with: pip install neo4j"
            ) from exc
        self._driver = GraphDatabase.driver(
            self.uri, auth=(self.user, self.password)
        )
        self._ensure_schema()
        return self

    def _ensure_schema(self) -> None:
        """Create indexes / constraints on first use (idempotent)."""
        if self._use_mock:
            return
        with self._driver.session(database=self.database) as session:
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (q:QRCode) "
                "REQUIRE q.fingerprint IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (p:PrologClause) "
                "REQUIRE p.clause_id IS UNIQUE"
            )

    def close(self) -> None:
        """Release database resources."""
        if self._driver:
            self._driver.close()
        if self._mock:
            self._mock.close()

    def __enter__(self) -> "Neo4jStore":
        return self.connect()

    def __exit__(self, *args) -> None:
        self.close()

    # ------------------------------------------------------------------
    # QR node operations
    # ------------------------------------------------------------------

    def store_qr(self, node: QRNode) -> str:
        """Upsert a :class:`QRNode` and return its fingerprint."""
        props = node.to_dict()
        if self._use_mock:
            self._mock.store_qr(props)  # type: ignore[union-attr]
            return node.fingerprint
        with self._driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (q:QRCode {fingerprint: $fingerprint})
                SET q.payload_type = $payload_type,
                    q.content      = $content,
                    q.metadata     = $metadata
                """,
                **props,
            )
        return node.fingerprint

    def get_qr(self, fingerprint: str) -> QRNode | None:
        """Retrieve a :class:`QRNode` by its fingerprint."""
        if self._use_mock:
            d = self._mock.get_qr(fingerprint)  # type: ignore[union-attr]
            if d is None:
                return None
            meta = json.loads(d.get("metadata", "{}"))
            return QRNode(
                fingerprint=d["fingerprint"],
                payload_type=d["payload_type"],
                content=d["content"],
                metadata=meta,
            )
        with self._driver.session(database=self.database) as session:
            result = session.run(
                "MATCH (q:QRCode {fingerprint: $fp}) RETURN q",
                fp=fingerprint,
            )
            record = result.single()
            if record is None:
                return None
            props = dict(record["q"])
            meta = json.loads(props.get("metadata", "{}"))
            return QRNode(
                fingerprint=props["fingerprint"],
                payload_type=props["payload_type"],
                content=props["content"],
                metadata=meta,
            )

    def list_qr(self, payload_type: str | None = None) -> list[QRNode]:
        """List all stored QR nodes, optionally filtered by *payload_type*."""
        if self._use_mock:
            items = self._mock.list_qr(payload_type)  # type: ignore[union-attr]
            return [
                QRNode(
                    fingerprint=d["fingerprint"],
                    payload_type=d["payload_type"],
                    content=d["content"],
                    metadata=json.loads(d.get("metadata", "{}")),
                )
                for d in items
            ]
        query = "MATCH (q:QRCode)"
        params: dict[str, Any] = {}
        if payload_type:
            query += " WHERE q.payload_type = $pt"
            params["pt"] = payload_type
        query += " RETURN q"
        with self._driver.session(database=self.database) as session:
            result = session.run(query, **params)
            nodes: list[QRNode] = []
            for record in result:
                props = dict(record["q"])
                meta = json.loads(props.get("metadata", "{}"))
                nodes.append(
                    QRNode(
                        fingerprint=props["fingerprint"],
                        payload_type=props["payload_type"],
                        content=props["content"],
                        metadata=meta,
                    )
                )
            return nodes

    # ------------------------------------------------------------------
    # Prolog node operations
    # ------------------------------------------------------------------

    def store_prolog(self, node: PrologNode) -> str:
        """Upsert a :class:`PrologNode` and return its clause ID."""
        props = node.to_dict()
        if self._use_mock:
            self._mock.store_prolog(props)  # type: ignore[union-attr]
            if node.qr_fingerprint:
                self._mock.link_contains(node.qr_fingerprint, node.clause_id)  # type: ignore[union-attr]
            return node.clause_id
        with self._driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (p:PrologClause {clause_id: $clause_id})
                SET p.functor     = $functor,
                    p.arity       = $arity,
                    p.prolog_text = $prolog_text,
                    p.is_rule     = $is_rule,
                    p.qr_fingerprint = $qr_fingerprint
                """,
                **props,
            )
            if node.qr_fingerprint:
                session.run(
                    """
                    MATCH (q:QRCode {fingerprint: $fp})
                    MATCH (p:PrologClause {clause_id: $cid})
                    MERGE (q)-[:CONTAINS]->(p)
                    """,
                    fp=node.qr_fingerprint,
                    cid=node.clause_id,
                )
        return node.clause_id

    def get_prolog(self, clause_id: str) -> PrologNode | None:
        """Retrieve a :class:`PrologNode` by its ID."""
        if self._use_mock:
            d = self._mock.get_prolog(clause_id)  # type: ignore[union-attr]
            if d is None:
                return None
            return PrologNode(**d)
        with self._driver.session(database=self.database) as session:
            result = session.run(
                "MATCH (p:PrologClause {clause_id: $cid}) RETURN p",
                cid=clause_id,
            )
            record = result.single()
            if record is None:
                return None
            return PrologNode(**dict(record["p"]))

    def list_prolog(self, functor: str | None = None) -> list[PrologNode]:
        """List all stored Prolog nodes, optionally filtered by *functor*."""
        if self._use_mock:
            items = self._mock.list_prolog(functor)  # type: ignore[union-attr]
            return [PrologNode(**d) for d in items]
        query = "MATCH (p:PrologClause)"
        params: dict[str, Any] = {}
        if functor:
            query += " WHERE p.functor = $fn"
            params["fn"] = functor
        query += " RETURN p"
        with self._driver.session(database=self.database) as session:
            result = session.run(query, **params)
            return [PrologNode(**dict(r["p"])) for r in result]

    # ------------------------------------------------------------------
    # Intersection relationships
    # ------------------------------------------------------------------

    def store_intersection(
        self,
        fp_a: str,
        fp_b: str,
        props: dict | None = None,
    ) -> None:
        """Create an ``INTERSECTS`` relationship between two QR nodes."""
        if self._use_mock:
            self._mock.store_intersection(fp_a, fp_b, props)  # type: ignore[union-attr]
            return
        with self._driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (a:QRCode {fingerprint: $fp_a})
                MATCH (b:QRCode {fingerprint: $fp_b})
                MERGE (a)-[r:INTERSECTS]->(b)
                SET r += $props
                """,
                fp_a=fp_a,
                fp_b=fp_b,
                props=props or {},
            )

    def list_intersections(self) -> list[tuple[str, str, dict]]:
        """Return all ``INTERSECTS`` relationships as (fp_a, fp_b, props)."""
        if self._use_mock:
            return self._mock.list_intersections()  # type: ignore[union-attr]
        with self._driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (a:QRCode)-[r:INTERSECTS]->(b:QRCode)
                RETURN a.fingerprint AS fp_a, b.fingerprint AS fp_b,
                       properties(r) AS props
                """
            )
            return [
                (record["fp_a"], record["fp_b"], dict(record["props"]))
                for record in result
            ]

    # ------------------------------------------------------------------
    # Convenience: store an entire PrologQR session
    # ------------------------------------------------------------------

    def store_prolog_qr(self, qr_data, prolog_text: str) -> str:
        """Store a Prolog QR code together with all its individual clauses.

        Parameters
        ----------
        qr_data:
            A :class:`~computational_qr.core.qr_encoder.QRData` with
            ``payload_type == "prolog"``.
        prolog_text:
            The original Prolog source text (used to extract clause nodes).

        Returns
        -------
        str
            The fingerprint of the stored QR node.
        """
        qr_node = QRNode.from_qr_data(qr_data)
        fp = self.store_qr(qr_node)

        for i, line in enumerate(prolog_text.splitlines()):
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            is_rule = ":-" in line
            functor = line.split("(")[0].strip()
            arity = line.count(",") + 1 if "(" in line else 0
            clause_id = f"{fp}_{i}"
            p_node = PrologNode(
                clause_id=clause_id,
                functor=functor,
                arity=arity,
                prolog_text=line.rstrip("."),
                is_rule=is_rule,
                qr_fingerprint=fp,
            )
            self.store_prolog(p_node)
        return fp
