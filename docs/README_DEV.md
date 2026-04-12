# Developer Guide – Computational QR Payload + Canonical Graph Hashing

This document describes the **v0 CQR pipeline**: a deterministic, portable
binary payload combined with a canonical NetworkX graph hashing layer.

---

## Table of Contents

1. [Concepts](#1-concepts)
2. [Package layout](#2-package-layout)
3. [Payload specification](#3-payload-specification)
4. [Graph canonicalization](#4-graph-canonicalization)
5. [Compression and CRC](#5-compression-and-crc)
6. [Python API quick-start](#6-python-api-quick-start)
7. [CLI usage](#7-cli-usage)
8. [Running tests](#8-running-tests)
9. [Forward compatibility](#9-forward-compatibility)
10. [Design decisions and trade-offs](#10-design-decisions-and-trade-offs)

---

## 1. Concepts

### Two identities

| Identity | Field | Definition | Primary key when … |
|---|---|---|---|
| `data_hash` | 32 bytes | `BLAKE3(data_bytes)` | glyph is **self-contained** (embeds the raw data) |
| `graph_hash` | 32 bytes | `BLAKE3(canonical_graph_bytes)` | glyph is **DB-referencing** (points to a record) |

Both hashes are **always present** in every payload.  The reader picks the
appropriate one depending on the deployment mode.

**Why two hashes?**

* `data_hash` is stable across graph-algorithm changes.  If the graph
  canonicalization rules evolve (bump `graph_codec_version`), `data_hash`
  still identifies the same original bytes.
* `graph_hash` ties identity to the *graph structure* — useful when you
  want to find records with the same graph regardless of encoding changes.

### Self-contained vs DB-referencing glyphs

| Mode | `has_embedded_data` flag | Primary identity |
|---|---|---|
| Self-contained | 1 | `data_hash` |
| DB-referencing | 0 (+ `has_index_key` = 1) | `graph_hash` |
| Both | 1 + 1 | Both |

---

## 2. Package layout

```
computational_qr/cqr/
├── __init__.py      # Re-exports: data_hash, canonical_graph_bytes, graph_hash, pack, unpack
├── __main__.py      # python -m computational_qr.cqr.cli entry point
├── hashing.py       # data_hash(data_bytes) → 32 bytes
├── graph.py         # canonical_graph_bytes(nx_graph), graph_hash(nx_graph)
├── payload.py       # Payload dataclass, pack(), unpack(), encode_varint(), decode_varint()
└── cli.py           # CLI encode / decode commands
```

---

## 3. Payload specification

All multi-byte integers are **big-endian** except where noted.  The CRC32C
checksum is stored **little-endian** (matching the CRC32C RFC convention).

```
+--------------------+------------+------------------------------------------+
| Field              | Size       | Notes                                    |
+--------------------+------------+------------------------------------------+
| magic              | 4 bytes    | b"CQR\x00"                               |
| version            | 1 byte     | currently 0x01                           |
| flags              | 1 byte     | bit 0: has_embedded_data                 |
|                    |            | bit 1: has_index_key                     |
| data_hash          | 32 bytes   | BLAKE3(data_bytes)                       |
| graph_hash         | 32 bytes   | BLAKE3(canonical_graph_bytes)            |
| graph_codec_id     | 1 byte     | identifies canonicalization algorithm    |
| graph_codec_ver    | 1 byte     | version within that algorithm            |
+--------------------+------------+------------------------------------------+
| [key block]        | variable   | present when has_index_key = 1           |
|   key_type         | 1 byte     | 0=raw, 1=uuid, 2=int, 3=path            |
|   key_len          | varint     | byte length of key_bytes                 |
|   key_bytes        | key_len    |                                          |
+--------------------+------------+------------------------------------------+
| [data block]       | variable   | present when has_embedded_data = 1       |
|   data_codec       | 1 byte     | 0x01=zstd, 0x02=gzip                    |
|   orig_len         | varint     | original (uncompressed) length           |
|   comp_len         | varint     | compressed length                        |
|   comp_bytes       | comp_len   |                                          |
+--------------------+------------+------------------------------------------+
| crc32c             | 4 bytes    | CRC32C of all preceding bytes (LE)       |
+--------------------+------------+------------------------------------------+
```

Minimum payload size (no optional blocks): **4 + 1 + 1 + 32 + 32 + 1 + 1 + 4 = 76 bytes**.

### Varint encoding

Variable-length unsigned integers use **LEB128** (same as Protocol Buffers):

* 7 payload bits per byte, LSB first.
* The MSB of each byte is 1 if more bytes follow, 0 for the last byte.
* Values ≤ 127 fit in one byte.

```python
from computational_qr.cqr.payload import encode_varint, decode_varint

encode_varint(0)    # b'\x00'
encode_varint(128)  # b'\x80\x01'
decode_varint(b'\x80\x01')  # (128, 2)
```

---

## 4. Graph canonicalization

`canonical_graph_bytes(graph)` produces a UTF-8 text representation:

```
GRAPH <directed|undirected> <multi|simple>
GATTR <sorted-json>
NODES <count>
N <node-label> <sorted-json-attrs>
...
EDGES <count>
E <src> <dst> [<key>] <sorted-json-attrs>
...
```

**Rules:**

* Node labels are coerced to `str` and sorted lexicographically.
* For undirected graphs, each edge is normalised so `src ≤ dst` (by string
  comparison).
* Attribute dicts are serialised as compact JSON with **sorted keys**.
* Graph-level attributes (`graph.graph`) are included in `GATTR`.
* Multi-graph edge keys appear between `dst` and the attribute JSON.

**Supported types:** `nx.Graph`, `nx.DiGraph`, `nx.MultiGraph`, `nx.MultiDiGraph`.

**Codec identification:**

| Constant | Value | Description |
|---|---|---|
| `GRAPH_CODEC_ID` | `0x01` | v0 text-based canonicalization |
| `GRAPH_CODEC_VERSION` | `0x01` | first iteration |

---

## 5. Compression and CRC

### Compression

The preferred data codec is **zstandard** (`data_codec = 0x01`, level 3).
If `zstandard` is not installed, the implementation automatically falls back
to **gzip/zlib** (`data_codec = 0x02`).  The codec byte in the payload tells
the decoder which algorithm to use; both codecs are supported on decode
regardless of which was used to encode.

Install `zstandard` for best compression ratios:

```bash
pip install zstandard
```

### CRC32C

Hardware-accelerated CRC32C via the `crc32c` package is tried first.  If
unavailable, a pure-Python lookup-table fallback (Castagnoli polynomial
`0x1EDC6F41`, reflected form `0x82F63B78`) is used automatically.

The checksum covers all payload bytes *except* the trailing 4-byte CRC field.

---

## 6. Python API quick-start

```python
import networkx as nx
from computational_qr.cqr import (
    canonical_graph_bytes,
    data_hash,
    graph_hash,
    pack,
    unpack,
)
from computational_qr.cqr.graph import GRAPH_CODEC_ID, GRAPH_CODEC_VERSION
from computational_qr.cqr.payload import KEY_TYPE_RAW, Payload

# 1. Build a graph
g = nx.Graph()
g.add_node("Alice", role="admin")
g.add_node("Bob",   role="user")
g.add_edge("Alice", "Bob", relation="manages")

# 2. Compute identities
raw_data  = b'{"user": "Alice", "action": "login"}'
d_hash    = data_hash(raw_data)        # 32 bytes – stable identity of raw data
g_hash    = graph_hash(g)              # 32 bytes – identity of the canonical graph

print("data_hash  :", d_hash.hex())
print("graph_hash :", g_hash.hex())

# 3. Pack a self-contained payload (embeds the data)
payload = Payload(
    data_hash=d_hash,
    graph_hash=g_hash,
    graph_codec_id=GRAPH_CODEC_ID,
    graph_codec_version=GRAPH_CODEC_VERSION,
    embedded_data=raw_data,        # optional: embed the raw data
    key_type=KEY_TYPE_RAW,         # optional: include a DB key
    key_bytes=b"rec:0042",
)
payload_bytes = pack(payload)

# 4. Unpack
recovered = unpack(payload_bytes)
assert recovered.embedded_data == raw_data
assert recovered.data_hash == d_hash
assert recovered.graph_hash == g_hash
```

---

## 7. CLI usage

The CLI is invocable as a module:

```bash
python -m computational_qr.cqr.cli <command> [options]
```

### `encode` – graph JSON → Base64 payload

```bash
python -m computational_qr.cqr.cli encode graph.json \
    [--data FILE]  \   # embed raw bytes from FILE
    [--key  KEY]   \   # embed KEY string as index
    [--out  FILE]      # write Base64 to FILE instead of stdout
```

**Example graph JSON (`graph.json`):**

```json
{
    "directed": false,
    "nodes": [
        {"id": "A", "color": "red"},
        {"id": "B", "color": "blue"}
    ],
    "edges": [
        {"src": "A", "dst": "B", "weight": 1.5}
    ],
    "graph_attrs": {"name": "example"}
}
```

**Example output:**

```
data_hash  : af1349b9f5f9a1a6a0404dea36dcc949...
graph_hash : 2c624232cdd221771294dfbb310acbc4...
payload b64: Q1FSAAEBAAAAAAAAAAAAAAAAAAAAAAAAA...
```

### `decode` – Base64 payload → hashes + data

```bash
python -m computational_qr.cqr.cli decode <PAYLOAD_B64> \
    [--out FILE]   # write embedded data bytes to FILE
```

**Example output:**

```
data_hash        : af1349b9f5f9a1a6a0404dea36dcc949...
graph_hash       : 2c624232cdd221771294dfbb310acbc4...
graph_codec_id   : 0x01
graph_codec_ver  : 0x01
key_type         : 0x00
key              : b'my-db-key'
embedded_data_len: 36 bytes
embedded_data    : '{"user": "Alice", "action": "login"}'
```

---

## 8. Running tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run only the CQR tests
pytest tests/test_cqr_hashing.py tests/test_cqr_graph.py \
       tests/test_cqr_payload.py tests/test_cqr_cli.py -v

# Coverage report
pytest --cov=computational_qr/cqr tests/test_cqr_*.py
```

Test coverage includes:

| Test file | What it covers |
|---|---|
| `test_cqr_hashing.py` | `data_hash()` – determinism, length, empty input |
| `test_cqr_graph.py` | Canonicalization – insertion order, edge direction, attributes, types |
| `test_cqr_payload.py` | Varint round-trip, pack/unpack, CRC failure detection |
| `test_cqr_cli.py` | End-to-end encode/decode via the CLI |

---

## 9. Forward compatibility

The `graph_codec_id` / `graph_codec_version` fields in the payload header
allow the canonicalization rules to evolve without breaking existing payloads:

* **Patch-level changes** (e.g., bug-fixes that don't change output for valid
  inputs): increment `graph_codec_version`.
* **Breaking changes** (e.g., different sort order, new wire format):
  increment `graph_codec_id` and reset `graph_codec_version = 0x01`.
* Decoders should check `graph_codec_id` and reject or warn on unknown
  values rather than silently mis-parsing.

Current values:

```
GRAPH_CODEC_ID      = 0x01   # text-line canonicalization (this document)
GRAPH_CODEC_VERSION = 0x01   # first iteration
```

---

## 10. Design decisions and trade-offs

| Decision | Rationale |
|---|---|
| Two hashes (`data_hash` + `graph_hash`) | Stable identity for both "store the raw data" and "store a graph key" use-cases without forcing a choice at encode time. |
| BLAKE3 | Fast (≈ 1 GB/s in Python), 256-bit security, no length-extension vulnerability, deterministic across platforms. |
| LEB128 varints | Compact, self-delimiting, same as Protocol Buffers / WASM – familiar to most ecosystems. |
| Text-based canonical format | Human-readable, easy to audit, no endianness issues.  Performance is not a bottleneck for v0. |
| zstd preferred, gzip fallback | zstd offers better ratios and speed; gzip is stdlib, so the package works without any optional C extension. |
| CRC32C (not SHA-256 MAC) | Corruption detection only (not authentication).  Hardware acceleration makes it nearly free.  Authentication can be added later with a `has_signature` flag. |
| NetworkX as graph object | Widely used in Python, rich algorithm library, easy to extend with custom node/edge types. |
