"""
cli.py – Command-line interface for the Computational QR pipeline.

Usage
-----
Encode a graph from a JSON adjacency list and emit the payload as Base64::

    python -m computational_qr.cqr.cli encode graph.json [--data FILE] [--key KEY]

Decode a Base64 payload and print hashes / optionally dump embedded data::

    python -m computational_qr.cqr.cli decode PAYLOAD_B64 [--out FILE]

JSON adjacency-list format
--------------------------
The encoder accepts a simple JSON file with the following structure::

    {
        "directed": false,
        "nodes": [
            {"id": "A", "color": "red"},
            {"id": "B"}
        ],
        "edges": [
            {"src": "A", "dst": "B", "weight": 1.0}
        ],
        "graph_attrs": {"name": "example"}
    }

All fields except ``"nodes"`` and ``"edges"`` are optional.
Node ``"id"`` is the only required node field; it becomes the NetworkX node
label.  All other node/edge fields become attributes.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Optional

import networkx as nx

from .graph import canonical_graph_bytes, graph_hash as _graph_hash, GRAPH_CODEC_ID, GRAPH_CODEC_VERSION
from .hashing import data_hash as _data_hash
from .payload import KEY_TYPE_RAW, Payload, pack, unpack


# ---------------------------------------------------------------------------
# Graph loader
# ---------------------------------------------------------------------------

def _load_graph(path: Path) -> nx.Graph:
    """Load a NetworkX graph from a JSON adjacency-list file."""
    with path.open("r", encoding="utf-8") as fh:
        spec = json.load(fh)

    directed: bool = spec.get("directed", False)
    g: nx.Graph = nx.DiGraph() if directed else nx.Graph()

    graph_attrs = spec.get("graph_attrs", {})
    g.graph.update(graph_attrs)

    for node in spec.get("nodes", []):
        node = dict(node)
        node_id = node.pop("id")
        g.add_node(node_id, **node)

    for edge in spec.get("edges", []):
        edge = dict(edge)
        src = edge.pop("src")
        dst = edge.pop("dst")
        g.add_edge(src, dst, **edge)

    return g


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_encode(args: argparse.Namespace) -> None:
    """Encode: graph → payload bytes → Base64."""
    graph = _load_graph(Path(args.graph))

    raw_data: Optional[bytes] = None
    if args.data:
        raw_data = Path(args.data).read_bytes()

    key_bytes_val: Optional[bytes] = None
    key_type_val: Optional[int] = None
    if args.key:
        key_bytes_val = args.key.encode("utf-8")
        key_type_val = KEY_TYPE_RAW

    canon = canonical_graph_bytes(graph)
    d_hash = _data_hash(raw_data) if raw_data is not None else b"\x00" * 32
    g_hash = _graph_hash(graph)

    p = Payload(
        data_hash=d_hash,
        graph_hash=g_hash,
        graph_codec_id=GRAPH_CODEC_ID,
        graph_codec_version=GRAPH_CODEC_VERSION,
        key_type=key_type_val,
        key_bytes=key_bytes_val,
        embedded_data=raw_data,
    )
    raw = pack(p)
    b64 = base64.b64encode(raw).decode("ascii")

    print(f"data_hash  : {d_hash.hex()}")
    print(f"graph_hash : {g_hash.hex()}")
    print(f"payload b64: {b64}")

    if args.out:
        Path(args.out).write_text(b64, encoding="ascii")
        print(f"Written to : {args.out}")


def cmd_decode(args: argparse.Namespace) -> None:
    """Decode: Base64 → payload → print hashes / dump data."""
    raw = base64.b64decode(args.payload_b64)
    p = unpack(raw)

    print(f"data_hash        : {p.data_hash.hex()}")
    print(f"graph_hash       : {p.graph_hash.hex()}")
    print(f"graph_codec_id   : {p.graph_codec_id:#04x}")
    print(f"graph_codec_ver  : {p.graph_codec_version:#04x}")
    if p.key_bytes is not None:
        print(f"key_type         : {p.key_type:#04x}")
        print(f"key              : {p.key_bytes!r}")
    if p.embedded_data is not None:
        print(f"embedded_data_len: {len(p.embedded_data)} bytes")
        if args.out:
            Path(args.out).write_bytes(p.embedded_data)
            print(f"Written to       : {args.out}")
        else:
            try:
                print(f"embedded_data    : {p.embedded_data.decode('utf-8')!r}")
            except UnicodeDecodeError:
                print(f"embedded_data    : <binary, {len(p.embedded_data)} bytes>")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m computational_qr.cqr.cli",
        description="Computational QR – payload encode / decode CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    enc = sub.add_parser("encode", help="Build a payload from a graph JSON file")
    enc.add_argument("graph", metavar="GRAPH_JSON", help="Path to graph JSON file")
    enc.add_argument("--data", metavar="FILE", help="Optional file whose bytes to embed")
    enc.add_argument("--key", metavar="KEY", help="Optional key/index string to embed")
    enc.add_argument("--out", metavar="FILE", help="Write Base64 payload to this file")

    dec = sub.add_parser("decode", help="Decode a Base64 payload")
    dec.add_argument("payload_b64", metavar="PAYLOAD_B64", help="Base64-encoded payload string")
    dec.add_argument(
        "--out",
        metavar="FILE",
        help="Write embedded data bytes to this file (if present)",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    from .payload import PayloadError  # local import to avoid circular reference at module level

    try:
        if args.command == "encode":
            cmd_encode(args)
        elif args.command == "decode":
            cmd_decode(args)
    except (PayloadError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
