"""
tests/test_cqr_graph.py – Unit tests for computational_qr.cqr.graph.
"""

import pytest
import networkx as nx

from computational_qr.cqr.graph import canonical_graph_bytes, graph_hash


class TestCanonicalGraphBytes:
    def test_returns_bytes(self):
        g = nx.Graph()
        g.add_node("A")
        result = canonical_graph_bytes(g)
        assert isinstance(result, bytes)

    def test_deterministic_insertion_order(self):
        """Same logical graph inserted in different orders → same canonical bytes."""
        g1 = nx.Graph()
        g1.add_node("A", val=1)
        g1.add_node("B", val=2)
        g1.add_edge("A", "B", w=0.5)

        g2 = nx.Graph()
        g2.add_node("B", val=2)
        g2.add_node("A", val=1)
        g2.add_edge("B", "A", w=0.5)  # reversed edge, undirected

        assert canonical_graph_bytes(g1) == canonical_graph_bytes(g2)

    def test_undirected_edge_direction_invariant(self):
        """A→B and B→A produce the same canonical bytes for undirected graphs."""
        g1 = nx.Graph()
        g1.add_edge("X", "Y")
        g2 = nx.Graph()
        g2.add_edge("Y", "X")
        assert canonical_graph_bytes(g1) == canonical_graph_bytes(g2)

    def test_directed_edge_direction_matters(self):
        """For directed graphs A→B ≠ B→A."""
        g1 = nx.DiGraph()
        g1.add_edge("A", "B")
        g2 = nx.DiGraph()
        g2.add_edge("B", "A")
        assert canonical_graph_bytes(g1) != canonical_graph_bytes(g2)

    def test_different_graphs_differ(self):
        g1 = nx.Graph()
        g1.add_edge("A", "B")

        g2 = nx.Graph()
        g2.add_edge("A", "C")

        assert canonical_graph_bytes(g1) != canonical_graph_bytes(g2)

    def test_node_attributes_included(self):
        g1 = nx.Graph()
        g1.add_node("A", color="red")

        g2 = nx.Graph()
        g2.add_node("A", color="blue")

        assert canonical_graph_bytes(g1) != canonical_graph_bytes(g2)

    def test_edge_attributes_included(self):
        g1 = nx.Graph()
        g1.add_edge("A", "B", weight=1.0)

        g2 = nx.Graph()
        g2.add_edge("A", "B", weight=2.0)

        assert canonical_graph_bytes(g1) != canonical_graph_bytes(g2)

    def test_empty_graph(self):
        g = nx.Graph()
        result = canonical_graph_bytes(g)
        assert b"NODES 0" in result
        assert b"EDGES 0" in result

    def test_digraph(self):
        g = nx.DiGraph()
        g.add_edge("A", "B")
        result = canonical_graph_bytes(g)
        assert b"directed" in result

    def test_multigraph(self):
        g = nx.MultiGraph()
        g.add_edge("A", "B", key="e1")
        g.add_edge("A", "B", key="e2")
        result = canonical_graph_bytes(g)
        assert b"multi" in result

    def test_graph_attrs_included(self):
        g1 = nx.Graph()
        g1.graph["name"] = "alpha"

        g2 = nx.Graph()
        g2.graph["name"] = "beta"

        assert canonical_graph_bytes(g1) != canonical_graph_bytes(g2)

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            canonical_graph_bytes({"nodes": [], "edges": []})  # type: ignore[arg-type]


class TestGraphHash:
    def test_returns_32_bytes(self):
        g = nx.Graph()
        g.add_node("A")
        assert len(graph_hash(g)) == 32

    def test_deterministic(self):
        g1 = nx.Graph()
        g1.add_edge("A", "B")
        g2 = nx.Graph()
        g2.add_edge("A", "B")
        assert graph_hash(g1) == graph_hash(g2)

    def test_distinct_graphs_produce_distinct_hashes(self):
        g1 = nx.Graph()
        g1.add_edge("A", "B")
        g2 = nx.Graph()
        g2.add_edge("A", "C")
        assert graph_hash(g1) != graph_hash(g2)
