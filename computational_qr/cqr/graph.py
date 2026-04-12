"""
graph.py – Deterministic NetworkX graph canonicalization and hashing.

Supported graph types
---------------------
* ``networkx.Graph``        – undirected, no parallel edges.
* ``networkx.DiGraph``      – directed, no parallel edges.
* ``networkx.MultiGraph``   – undirected, parallel edges allowed.
* ``networkx.MultiDiGraph`` – directed, parallel edges allowed.

Canonicalization rules
----------------------
1.  **Node labels** are coerced to ``str`` and sorted lexicographically to
    produce a stable node ordering.  Nodes may carry arbitrary attributes;
    attribute dicts are serialised as sorted JSON.
2.  **Edges** are emitted in (source, target[, key]) order, where source <
    target for undirected graphs (edge direction is not canonical for
    undirected edges).  Edge attribute dicts are serialised as sorted JSON.
3.  **Graph-level attributes** are serialised as sorted JSON and included
    in the canonical bytes.
4.  The wire format is pure UTF-8 text lines (``\\n``-delimited), so the
    output is human-readable and cross-platform.

Wire format (one line per record)::

    GRAPH <"directed"|"undirected"> <"multi"|"simple">
    GATTR <sorted-json>
    NODES <count>
    N <node-label-str> <sorted-json-attrs>
    ...
    EDGES <count>
    E <src-str> <dst-str> [<edge-key-str>] <sorted-json-attrs>
    ...

Forward-compatibility note
--------------------------
``graph_codec_id = 0x01`` and ``graph_codec_version = 0x01`` identify this
canonicalization scheme in the payload header.  When the scheme changes,
increment ``GRAPH_CODEC_VERSION`` and bump ``GRAPH_CODEC_ID`` only when the
change is backward-incompatible.

GRAPH_CODEC_ID      = 0x01
GRAPH_CODEC_VERSION = 0x01
"""

from __future__ import annotations

import json
from typing import Any

import networkx as nx

import blake3 as _blake3

GRAPH_CODEC_ID: int = 0x01
GRAPH_CODEC_VERSION: int = 0x01


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _attrs_to_json(attrs: dict[str, Any]) -> str:
    """Serialise an attribute dict as compact, key-sorted JSON."""
    return json.dumps(attrs, sort_keys=True, separators=(",", ":"), default=str)


def _node_label(n: Any) -> str:
    return str(n)


def _edge_record(
    src: Any,
    dst: Any,
    attrs: dict[str, Any],
    is_directed: bool,
    edge_key: Any | None = None,
) -> str:
    """Return the canonical edge line for one edge."""
    s = _node_label(src)
    d = _node_label(dst)
    if not is_directed and s > d:
        s, d = d, s
    attr_str = _attrs_to_json(attrs)
    if edge_key is not None:
        return f"E {s} {d} {edge_key!s} {attr_str}"
    return f"E {s} {d} {attr_str}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def canonical_graph_bytes(
    graph: nx.Graph | nx.DiGraph | nx.MultiGraph | nx.MultiDiGraph,
) -> bytes:
    """Return a deterministic byte representation of *graph*.

    The same logical graph (same nodes, edges, and attributes) always
    produces the same bytes, regardless of the order in which nodes/edges
    were inserted.

    Parameters
    ----------
    graph:
        Any NetworkX graph object.

    Returns
    -------
    bytes
        UTF-8-encoded canonical representation.

    Raises
    ------
    TypeError
        If *graph* is not a recognised NetworkX graph type.
    """
    if not isinstance(graph, nx.Graph):
        raise TypeError(f"Expected a NetworkX graph, got {type(graph)!r}")

    is_directed = graph.is_directed()
    is_multi = graph.is_multigraph()

    graph_type = "directed" if is_directed else "undirected"
    multi_type = "multi" if is_multi else "simple"

    lines: list[str] = []

    # Header line
    lines.append(f"GRAPH {graph_type} {multi_type}")

    # Graph-level attributes
    lines.append(f"GATTR {_attrs_to_json(dict(graph.graph))}")

    # Nodes (sorted by string label)
    sorted_nodes = sorted(graph.nodes(data=True), key=lambda n: _node_label(n[0]))
    lines.append(f"NODES {len(sorted_nodes)}")
    for node, attrs in sorted_nodes:
        lines.append(f"N {_node_label(node)} {_attrs_to_json(attrs)}")

    # Edges
    if is_multi:
        raw_edges = list(graph.edges(data=True, keys=True))
        if not is_directed:
            # Normalise direction for undirected: sort (src, dst) pair
            def _norm_multi(u: Any, v: Any, k: Any, d: dict) -> tuple:
                s, t = _node_label(u), _node_label(v)
                return (s, t, k, d) if s <= t else (t, s, k, d)

            raw_edges = [_norm_multi(u, v, k, d) for u, v, k, d in raw_edges]
            raw_edges.sort(key=lambda e: (e[0], e[1], str(e[2])))
        else:
            raw_edges.sort(key=lambda e: (_node_label(e[0]), _node_label(e[1]), str(e[2])))
        lines.append(f"EDGES {len(raw_edges)}")
        for src, dst, key, attrs in raw_edges:
            lines.append(_edge_record(src, dst, attrs, is_directed, edge_key=key))
    else:
        raw_edges = list(graph.edges(data=True))
        if not is_directed:
            def _norm_simple(u: Any, v: Any, d: dict) -> tuple:
                s, t = _node_label(u), _node_label(v)
                return (s, t, d) if s <= t else (t, s, d)

            raw_edges = [_norm_simple(u, v, d) for u, v, d in raw_edges]
            raw_edges.sort(key=lambda e: (e[0], e[1]))
        else:
            raw_edges.sort(key=lambda e: (_node_label(e[0]), _node_label(e[1])))
        lines.append(f"EDGES {len(raw_edges)}")
        for src, dst, attrs in raw_edges:
            lines.append(_edge_record(src, dst, attrs, is_directed))

    return "\n".join(lines).encode("utf-8")


def graph_hash(
    graph: nx.Graph | nx.DiGraph | nx.MultiGraph | nx.MultiDiGraph,
) -> bytes:
    """Return the 32-byte BLAKE3 digest of ``canonical_graph_bytes(graph)``.

    Parameters
    ----------
    graph:
        Any NetworkX graph object.

    Returns
    -------
    bytes
        32-byte (256-bit) BLAKE3 digest.
    """
    return _blake3.blake3(canonical_graph_bytes(graph)).digest()
