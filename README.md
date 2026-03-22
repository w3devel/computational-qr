# computational-qr

QR as a computational medium using color geometry, 3D graphs, a graph database, and quantum math.

---

## Overview

**computational-qr** treats a QR code not merely as a URL shortener but as a
*computational artifact*: a self-contained, portable unit of logic, data, and
visualisation.

| Concept | What it means in this project |
|---|---|
| **Colour geometry** | Area shapes (circles, polygons, stars, rectangles) whose hue, saturation, and brightness directly encode data dimensions—no separate colour table needed. |
| **3D graphs with data intersections** | Data points live at arbitrary (x, y, z) co-ordinates. The graph detects where data from *different* dimensions come within a configurable tolerance of each other—not constrained to 2-D rows and columns. |
| **Dependency intersection engine** | Models spreadsheet-style dependency intersections: a computed cell depends on one or more source "tables". The engine groups inputs into source groups, maps the group count to an area-shape geometry (more groups → more sides), and produces a colour-geometry legend. |
| **Audio QR** | A QR module matrix is encoded as a sequence of sine-wave tones (FSK) and wrapped in a WAV container; the matrix can be recovered from the audio later. |
| **Video QR (SVG)** | Multiple QR data frames are composed into an animated, scriptable SVG document served over a network—"scriptable network graphics for video QR". |
| **Quantum math** | QR module matrices are lifted into quantum states (superposition over row bit-strings). Hadamard transforms, Bell states, and interference patterns provide a quantum fingerprint for each code. |
| **Prolog logic** | Facts and rules are serialised as a `PROLOG`-typed QR envelope. The QR code is the *portable program*: load it anywhere, execute it without a database connection. |
| **Neo4j** | QR nodes, Prolog clause nodes, and their `INTERSECTS`/`CONTAINS` relationships are stored in a Neo4j graph database. A mock in-memory backend is provided for testing. |

---

## Package layout

```
computational_qr/
├── core/
│   ├── color_geometry.py   # ColorShape, GeometryKey, ColorGeometry
│   ├── formula_parser.py   # parse_excel_formula_references()
│   ├── grouping_policy.py  # DefaultTableGroupingPolicy, ShapePolicy
│   ├── dependency_viz.py   # DependencyGraph → ColorGeometry / Graph3D helpers
│   └── qr_encoder.py       # QRData (typed envelope), QREncoder
├── graphs/
│   ├── graph_3d.py         # DataPoint, Intersection, Graph3D
│   └── dependency_graph.py # CellRef, RangeRef, TableRef, FormulaNode, DependencyGraph
├── prolog/
│   ├── prolog_engine.py    # Pure-Python Horn-clause resolver
│   └── prolog_qr.py        # Encode/decode/execute Prolog as QR
├── media/
│   ├── audio_qr.py         # FSK audio encoding / WAV output
│   └── video_qr.py         # Animated SVG video QR
├── quantum/
│   └── quantum_math.py     # QuantumState, QuantumGate, QuantumRegister, QuantumMath
├── database/
│   ├── neo4j_store.py      # Neo4jStore with real + mock backends
│   └── relational_store.py # RelationalQRStore: SQLite/Postgres via SQLAlchemy
├── comms/
│   ├── capsule.py          # Versioned Capsule format + serialization
│   ├── qr_transport.py     # Pattern A – multi-frame QR / video-QR framing
│   ├── wifi_transport.py   # Pattern B – Wi-Fi LAN HTTP transport + UDP discovery
│   └── i2p_transport.py    # Pattern C – I2P gateway client
└── numberstation/
    ├── e11_script.py       # E11Script dataclass, generate(), CLI entry point
    ├── render.py           # WAV synthesis from E11Script (stdlib-only)
    └── ffmpeg.py           # Pipe WAV to ffmpeg-qr; auto-select APNG/PNG/WAV output
```

---

## Quick start

```bash
pip install -r requirements.txt
```

### Colour geometry & 3D graph

```python
from computational_qr.core import ColorGeometry
from computational_qr.graphs import Graph3D

cg = ColorGeometry()
temp = cg.add_dimension("Temperature", unit="°C", min_value=0, max_value=100)
pres = cg.add_dimension("Pressure",    unit="Pa", min_value=0, max_value=200)

cg.add_shape("T₀", value=25.0, x=1.0, y=2.0, z=0.0, dimension=temp)
cg.add_shape("P₀", value=101.3, x=1.1, y=2.1, z=0.0, dimension=pres)

pairs = cg.find_intersections(tolerance=0.5)
print(f"{len(pairs)} intersection(s) found")

# 3-D graph
g = Graph3D(tolerance=0.5)
g.register_dimension(0, "Temperature")
g.register_dimension(1, "Pressure")
g.add_point("T₀", 1.0, 2.0, 0.0, value=25.0, dimension=0)
g.add_point("P₀", 1.1, 2.1, 0.0, value=101.3, dimension=1)
print(g.find_intersections())
```

### Prolog stored and executed as QR

```python
from computational_qr.prolog import PrologQR

pqr = PrologQR()

# 1. Encode a program into a QR data envelope
program = """
parent(tom, bob).
parent(bob, ann).
ancestor(?X, ?Y) :- parent(?X, ?Y).
ancestor(?X, ?Z) :- parent(?X, ?Y), ancestor(?Y, ?Z).
"""
qr_data = pqr.encode_program(program)
print("Fingerprint:", qr_data.fingerprint())

# 2. Execute the program from the QR — no database required
results = pqr.execute_from_data(qr_data, "ancestor(tom, ?Who)")
for r in results:
    print("ancestor of tom:", r["Who"])
```

### Audio QR

```python
from computational_qr.core import QREncoder, QRData, PayloadType
from computational_qr.media import AudioQR

encoder = QREncoder()
data = QRData(PayloadType.TEXT, "hello audio")
matrix = encoder.encode_matrix(data)

aqr = AudioQR()
wav_bytes = aqr.encode_matrix_to_wav(matrix)
with open("qr.wav", "wb") as f:
    f.write(wav_bytes)
```

### Video QR (SVG)

```python
from computational_qr.core import QRData, PayloadType
from computational_qr.media import VideoQR

frames = [
    QRData(PayloadType.TEXT, "frame 0 – introduction"),
    QRData(PayloadType.PROLOG, "parent(alice, bob)."),
    QRData(PayloadType.TEXT, "frame 2 – conclusion"),
]
vqr = VideoQR(module_size=6, frame_duration_ms=800)
svg = vqr.encode_video(frames, title="My Video QR")
with open("video_qr.svg", "w") as f:
    f.write(svg)
```

### Quantum math

```python
from computational_qr.quantum import QuantumMath, QuantumRegister, GATE_H, GATE_CNOT

# Quantum fingerprint of a QR matrix
matrix = [[True, False, True], [False, True, False]]
fp = QuantumMath.quantum_fingerprint(matrix)
print("Quantum fingerprint:", fp)

# Bell state
bell = QuantumMath.bell_state(0)
print("|Φ⁺⟩ =", bell.ket_notation())
```

### Neo4j storage

```python
from computational_qr.database import Neo4jStore, QRNode
from computational_qr.core import QRData, PayloadType

# use_mock=True for testing without a running Neo4j instance
with Neo4jStore(use_mock=True) as store:
    data = QRData(PayloadType.TEXT, "hello neo4j")
    fp = store.store_qr(QRNode.from_qr_data(data))
    node = store.get_qr(fp)
    print(node.payload_type)          # "text"

# Real Neo4j connection
# with Neo4jStore("bolt://localhost:7687", "neo4j", "password") as store:
#     store.store_prolog_qr(qr_data, prolog_text)
```

### Relational store (SQLite / PostgreSQL)

```python
from computational_qr.database import RelationalQRStore
from computational_qr.core import QRData, PayloadType

data = QRData(PayloadType.TEXT, "hello relational")

# --- SQLite (portable, no server required) ---
with RelationalQRStore("sqlite:///qr.db") as store:
    # Store with pre-rendered PNG and SVG artifacts
    record = store.store_qr(data, render_png=True, render_svg=True)
    print("UUID:", record.id)
    print("Fingerprint:", record.fingerprint)

    # Fast artifact retrieval (no re-rendering)
    png_bytes = store.get_png(record.id)
    svg_text  = store.get_svg(record.id)

    # Look up by fingerprint
    same = store.get_by_fingerprint(record.fingerprint)
    assert same.id == record.id

    # List (paginated, optional type filter)
    rows = store.list_qr(limit=50, payload_type="text")
    print(f"{len(rows)} text record(s)")

# --- PostgreSQL (server-side) ---
# with RelationalQRStore(
#     "postgresql+psycopg://user:password@localhost/qrdb"
# ) as store:
#     record = store.store_qr(data)
#     png_bytes = store.get_png(record.id)
```

---

## Dependency intersection engine

The dependency intersection engine models spreadsheet formulas as a directed
hypergraph.  A computed cell (the *output*) may depend on one or more source
references (cells, ranges, named tables, or whole sheets).  Those sources are
grouped into "source tables" by a configurable policy, and the number of
distinct groups drives which area shape is used in the graph view.

### How it differs from geometric tolerance intersections

| | Geometric (`Graph3D`) | Dependency (`DependencyGraph`) |
|---|---|---|
| **Trigger** | Two points are within a distance threshold | A formula explicitly references multiple sources |
| **Meaning** | Proximity in coordinate space | Causal / computational dependency |
| **Primary use-case** | Analog / quantum proximity ("close enough") | Spreadsheet cell formulas, lookup chains |

Both models coexist and can be combined: `build_visualization_payload` produces
a single JSON payload containing both a `Graph3D` and a `ColorGeometry` derived
from the dependency structure.

### Minimal example

```python
from computational_qr.graphs.dependency_graph import (
    DependencyGraph, CellRef, RangeRef, TableRef
)
from computational_qr.core.formula_parser import parse_excel_formula_references
from computational_qr.core.dependency_viz import build_visualization_payload

# --- 1. Parse references from a formula string ---
refs = parse_excel_formula_references("=SUM(Sheet1!A1:A10)+VLOOKUP(A1,SalesData,2)")
for r in refs:
    print(r.ref_type, r.ref_id)

# --- 2. Build a dependency graph manually (or via an adapter) ---
g = DependencyGraph()

result = CellRef("C1", sheet="Report")
revenue = TableRef("Revenue", sheet="Sheet1")
costs   = TableRef("Costs",   sheet="Sheet2")
adj     = RangeRef("A1:A5",   sheet="Adjustments")

g.add_formula(result, [revenue, costs, adj],
              formula_text="=Revenue_Total - Costs_Total + SUM(Adjustments!A1:A5)")

# --- 3. Inspect source groups ---
from computational_qr.core.grouping_policy import DefaultTableGroupingPolicy
policy = DefaultTableGroupingPolicy()
groups = policy.group_ids(g.get_inputs(result))
print("Source groups:", groups)
# → {'table:Sheet1!Revenue', 'table:Sheet2!Costs', 'sheet:Adjustments'}
# (3 groups: two explicit tables + one sheet-collapsed range)

# --- 4. Check the shape that represents 3 source groups ---
from computational_qr.core.grouping_policy import ShapePolicy
shape_type, n_sides = ShapePolicy().shape_for(len(groups))
print(f"Shape: {shape_type} with {n_sides} sides")
# → Shape: polygon with 6 sides  (hexagon)

# --- 5. Produce a full visualisation payload ---
payload = build_visualization_payload(g)
import json
print(json.dumps(payload["color_geometry"]["shapes"], indent=2))
```

### Default grouping policy

| Condition | Group ID |
|---|---|
| Input is a `TableRef` | The table's stable `ref_id` (e.g. `table:Sheet1!Revenue`) |
| Input is a `RangeRef`/`CellRef` on a sheet with ≥ 2 tables | The range's `ref_id` |
| Input is a `RangeRef`/`CellRef` on a sheet with 0 or 1 table | `sheet:<SheetName>` (whole-sheet group) |

The policy can be swapped out or configured with `single_table_sheet_fallback=False`
to always group by range instead of collapsing to the sheet level.

### Shape selection (k source groups → geometry)

| Groups (k) | `shape_type` | `n_sides` |
|---|---|---|
| 0–1 | `circle` | 36 (smooth) |
| 2   | `polygon` | 4 (square) |
| 3   | `polygon` | 6 (hexagon) |
| 4   | `polygon` | 8 (octagon) |
| 5   | `polygon` | 10 |
| 6–12 | `star` | `2 × k` (capped at 24) |
| > 12 | `star` | 24 |

---

## Running the tests

```bash
pytest tests/ -v
```

All tests pass with no external services required (Neo4j mock is used
automatically for database tests; comms tests use in-process mock servers).

---

## Communications subsystem (`comms`)

The `comms` package adds three **transport patterns** for moving a shared,
versioned *Capsule* through different communication channels.  All patterns
share the same :class:`Capsule` envelope and are independent of the existing
colour-geometry / audio / video / quantum features.

### The Capsule format

A `Capsule` is a transport-oriented, versioned message envelope:

```python
from computational_qr.comms import Capsule

capsule = Capsule(
    payload=b"hello world",
    content_type="text",
    routing={"topic": "greetings"},
)

# Serialize (canonical JSON – deterministic, sort_keys=True)
json_str = capsule.to_json()
raw_bytes = capsule.to_bytes()

# Deserialize and verify integrity
restored = Capsule.from_bytes(raw_bytes)
assert restored.payload == b"hello world"
assert restored.verify()        # SHA-256 checksum check
```

The serialised form includes `version`, `msg_id` (UUID4), `created_at_ms`
(millisecond timestamp), `routing` dict, `content_type`, `payload_b64`
(base64url), and `checksum` (SHA-256 hex).  Encoding is always
**deterministic**: given identical field values the JSON output is identical
on every platform.

---

### Pattern A – Multi-frame QR / Video-QR

Split a `Capsule` into fixed-size chunks, encode each chunk as a
`QRData` frame, and reassemble in any order.  Compatible with
`QREncoder` (static QR) and `VideoQR` (animated SVG).

```python
from computational_qr.comms import Capsule, QRFramer
from computational_qr.media import VideoQR

capsule = Capsule(payload=b"A" * 600, content_type="bytes")
framer = QRFramer(chunk_size=200)   # max 200 capsule-bytes per QR frame

# Split into QRData envelopes (one per frame)
qr_items = framer.to_qr_data(capsule)
print(f"{len(qr_items)} QR frames needed")

# Animate as a video QR (no real scanner required for this step)
vqr = VideoQR()
svg = vqr.encode_video(qr_items)

# Reassemble from raw QRFrame objects (any order)
frames = framer.split(capsule)
import random; random.shuffle(frames)
restored = framer.reassemble(frames)
assert restored.payload == capsule.payload
```

---

### Pattern B – Wi-Fi LAN transport (gateway concept)

A *gateway node* on the local IP network (Wi-Fi, Ethernet, or any link)
runs a `CapsuleServer`.  Sender devices POST capsules to it over HTTP.
The underlying link does not have to be Wi-Fi 3; the module works on any
IP LAN.

```python
from computational_qr.comms import Capsule, CapsuleServer, WifiGatewayClient

# ── Gateway side ──────────────────────────────────────────────────────────
server = CapsuleServer(host="0.0.0.0", port=8765)   # binds to all interfaces
server.start()

# Optionally persist incoming capsules to disk:
# server = CapsuleServer(host="0.0.0.0", port=8765, spool_dir="/var/spool/cqrc")

# ── Sender side ───────────────────────────────────────────────────────────
client = WifiGatewayClient("http://192.168.1.10:8765/capsule")
capsule = Capsule(payload=b"hello LAN", content_type="text")
result = client.send(capsule)
print(result)   # {"status": "ok", "msg_id": "..."}

# ── Gateway retrieves spooled capsules ────────────────────────────────────
received = server.get_capsules()
server.stop()
```

**Optional UDP gateway discovery** (multicast; can be disabled for tests):

```python
from computational_qr.comms import udp_announce, udp_listen

# Gateway announces itself on the LAN
udp_announce(service_port=8765)

# Sender discovers the gateway
port = udp_listen(timeout=2.0)   # returns None if no announcement received
if port:
    print(f"Gateway found on port {port}")
```

---

### Pattern C – I2P gateway

An *I2P gateway* is a separate process (or remote host) that runs an I2P
router and exposes a small HTTP API.  This module provides a typed client
for that gateway contract; it does **not** implement I2P internals.

```python
from computational_qr.comms import Capsule, I2PGatewayClient

client = I2PGatewayClient("http://localhost:7070")

# Submit a capsule for delivery via I2P
capsule = Capsule(
    payload=b"secret message",
    content_type="otp_ciphertext",
    routing={
        "i2p_dest": "somehash.b32.i2p",   # I2P destination address
        "topic": "inbox_alice",             # mailbox/topic label
    },
)
result = client.submit(capsule)
print(result)   # {"status": "queued", "msg_id": "..."}

# Fetch pending capsules from a mailbox
pending = client.fetch_mailbox("inbox_alice")
for c in pending:
    print(c.text_payload())
```

**Gateway contract** (implement separately or use a community gateway):

| Endpoint | Method | Description |
|---|---|---|
| `/i2p/submit` | POST | Accept a capsule JSON body; returns `{"status":"queued","msg_id":"..."}` |
| `/i2p/mailbox/<topic>` | GET | Return `{"topic":"...","capsules":[...]}` |

---

### Pattern B/C – the "gateway" concept

Both Pattern B and Pattern C rely on a *gateway service*:

* **Pattern B gateway** is a `CapsuleServer` (bundled) running on any LAN
  node.  No external service needed for local delivery.
* **Pattern C gateway** is an I2P-router node with the HTTP API above.
  Devices that cannot run a full I2P router submit capsules to it over the
  local LAN (possibly using Pattern B) and the gateway forwards them via I2P.

The patterns compose: scan a QR code (Pattern A) → upload over Wi-Fi LAN
(Pattern B) → gateway forwards via I2P (Pattern C).

---

---

## Number-station module (`numberstation`)

Generate deterministic **E11 number-station scripts** compatible with the
[ZapdoZ/numberstations](https://github.com/ZapdoZ/numberstations) input
format, render WAV audio from those scripts, and pipe the audio to a custom
`ffmpeg-qr` binary.

### Generating a script

```python
from computational_qr.numberstation import generate

# From a human-readable string seed (SHA-256 derived integer internally):
script = generate("my-secret-seed", group_count=20)
print(script.to_text())
# E11
# 472
# 20
# 03917 48201 … (20 five-digit groups)

# From an integer seed:
script2 = generate(98765, group_count=10)

# Write to a file (compatible with ZapdoZ/numberstations/main.py):
script.write("transmission.txt")
```

### CLI usage

```bash
# Write to stdout:
python -m computational_qr.numberstation.e11_script \
    --seed "my-secret-seed" --groups 20

# Write to a file:
python -m computational_qr.numberstation.e11_script \
    --seed "my-secret-seed" --groups 20 --out transmission.txt

# Fixed station ID:
python -m computational_qr.numberstation.e11_script \
    --seed 12345 --groups 5 --station-id 007
```

### Rendering WAV audio

```python
from computational_qr.numberstation import generate
from computational_qr.numberstation.render import render_wav

script = generate("my-secret-seed", group_count=20)
wav_bytes = render_wav(script, sample_rate=48000)

# Or get raw PCM:
pcm_bytes = render_wav(script, as_pcm=True)
```

### Piping to `ffmpeg-qr`

`ffmpeg-qr` (your custom FFmpeg binary) receives the WAV on stdin.  The output
format is chosen automatically:

| Condition | Output |
|---|---|
| `apngasm` is on PATH | Animated PNG (APNG) |
| `sng` is on PATH | PNG sequence (`frame_%05d.png`) |
| Neither | WAV fallback |

```python
from computational_qr.numberstation import generate
from computational_qr.numberstation.render import render_wav
from computational_qr.numberstation.ffmpeg import transcode, detect_output_format

script = generate("broadcast-2026-03-21", group_count=30)
wav_bytes = render_wav(script)

print("Output format:", detect_output_format())  # "apng", "png_sequence", or "wav"

# Auto-select output format:
transcode(wav_bytes, out_path="output.apng", ffmpeg_qr_path="/path/to/ffmpeg-qr")

# Force a specific format:
transcode(
    wav_bytes,
    out_path="output.apng",
    ffmpeg_qr_path="/path/to/ffmpeg-qr",
    output_format="apng",
    fps=12,
    scale="512:512",
)
```

---

## Spreadsheet integration – quantum gate simulation (WASM)

This repository includes an offline-first quantum gate-sequence simulator
compiled to **WebAssembly** from Rust.  It can be used as:

- **Excel** OfficeJS Custom Functions (`CQ_QPROBS`, `CQ_QAMPS`) that spill
  dynamic arrays directly into worksheet cells.
- **LibreOffice Calc** via a ZetaJS extension that loads the same JS + WASM
  bundle (no macros required).

The Python implementation in `computational_qr/quantum/quantum_math.py`
remains the authoritative reference model.  Parity tests confirm that WASM
results match Python for all supported circuits.

### Repository layout (new additions)

```
rust/
└── quantum_engine/          Rust crate → compiled to WASM by wasm-pack
    ├── Cargo.toml
    └── src/
        ├── lib.rs           WebAssembly entry point (apply_gate_sequence)
        ├── schema.rs        JSON input/output types (serde)
        ├── gates.rs         Standard & custom gate matrices
        └── engine.rs        State-vector simulation + unit tests

spreadsheets/
├── engine/
│   ├── quantumEngine.ts     JS/TS wrapper – loads WASM, exposes qprobs/qamps
│   └── run_wasm.mjs         Node.js runner for Python parity tests
└── excel-officejs/
    ├── manifest.xml         Office Add-in manifest
    ├── package.json
    ├── tsconfig.json
    ├── webpack.config.js
    └── src/
        └── functions.ts     CQ_QPROBS / CQ_QAMPS custom function definitions

docs/
└── native-server-fallback.md  Fallback design when WASM is unavailable

tests/
└── test_wasm_parity.py      WASM-vs-Python parity tests (+ shape-logic tests)
```

### Building the WASM module

Prerequisites: [Rust](https://rustup.rs) + [wasm-pack](https://rustwasm.github.io/wasm-pack/installer/).

```bash
# Install wasm-pack (one-time)
cargo install wasm-pack

# Build the WASM package (Node.js target for parity tests)
cd rust/quantum_engine
wasm-pack build --target nodejs

# Build for browser/bundler (Excel add-in)
wasm-pack build --target bundler
```

The compiled package is emitted to `rust/quantum_engine/pkg/`.

### Running the parity tests

```bash
# After building the WASM Node.js target (above):
pytest tests/test_wasm_parity.py -v
```

WASM tests are automatically **skipped** (not failed) when the WASM package
has not been built, so CI runs without Rust/wasm-pack always succeed.

### Using the Excel add-in

1. Build the WASM bundler package (see above).
2. Install Node.js dependencies and build the add-in:
   ```bash
   cd spreadsheets/excel-officejs
   npm install
   npm run build
   ```
3. Sideload `dist/manifest.xml` into Excel (Insert → Add-ins → Upload My
   Add-in).

#### Custom function examples

```
# 1-qubit Hadamard → [0.5, 0.5] as a row vector (default)
=CQ_QPROBS(1, "[{""gate"":""H"",""targets"":[0]}]")

# Bell state → column vector (with header row)
=CQ_QPROBS(2,
  "[{""gate"":""H"",""targets"":[0]},{""gate"":""CNOT"",""targets"":[0,1]}]",
  ,
  "{""shape"":""col"",""hasHeader"":true}")

# Complex amplitudes (Re/Im two-column spill)
=CQ_QAMPS(1, "[{""gate"":""H"",""targets"":[0]}]")

# Custom matrix gate (Hadamard supplied as explicit 2×2 matrix)
=CQ_QPROBS(1,
  "[{""gate"":{""matrix"":{""dim"":2,""data"":[[0.707,0],[0.707,0],[0.707,0],[-0.707,0]]}},""targets"":[0]}]")
```

### Output shape rules for `CQ_QPROBS`

The optional fourth argument accepts a JSON options object:

```json
{
  "shape": "auto" | "row" | "col",
  "hasHeader": true | false,
  "leftColumnReserved": true | false
}
```

| `shape`  | `hasHeader` | `leftColumnReserved` | Result |
|----------|-------------|----------------------|--------|
| `"col"`  | –           | –                    | N×1 column vector |
| `"row"`  | –           | –                    | 1×N row vector |
| `"auto"` | `true`      | `false`              | N×1 column vector |
| `"auto"` | `false`     | –                    | 1×N row vector |
| `"auto"` | –           | `true`               | 1×N row vector |

**Default** (`"auto"` with no options): row vector.

### JSON API schema

Full input schema accepted by `apply_gate_sequence`:

```json
{
  "nQubits": 2,
  "initialState": { "type": "zero" },
  "ops": [
    { "gate": "H",    "targets": [0] },
    { "gate": "CNOT", "targets": [0, 1] },
    {
      "gate": {
        "name": "U",
        "matrix": { "dim": 2, "data": [[0.707, 0.0], [0.707, 0.0], [0.707, 0.0], [-0.707, 0.0]] }
      },
      "targets": [0]
    }
  ],
  "output": "probabilities"
}
```

- `nQubits`: positive integer (max ~20 for practical use in spreadsheets).
- `initialState`: `{"type":"zero"}` or `{"type":"amplitudes","data":[[re,im],...]}`.
- `ops[].gate`: a string name (`"H"`, `"X"`, `"Y"`, `"Z"`, `"I"`, `"S"`, `"T"`,
  `"CNOT"`, `"SWAP"`) **or** an inline matrix object.
- `ops[].targets`: qubit indices.  **Qubit 0 = leftmost / most-significant bit**
  (big-endian, matching the Python implementation).
- `output`: `"probabilities"` (default) or `"amplitudes"`.

### LibreOffice Calc (ZetaJS – future)

The same `quantumEngine.ts` wrapper and WASM binary can be bundled into a
LibreOffice extension using ZetaJS.  ZetaJS exposes a JS execution environment
that can load WASM, enabling the same `qprobs`/`qamps` functions without
macros.  This integration is planned as a future addition; the engine API
is already compatible.

### Native server fallback

When WASM cannot be loaded (restricted environment, unsupported runtime), the
JS wrapper emits a clear error message suggesting the user install the native
Rust helper server.  See [docs/native-server-fallback.md](docs/native-server-fallback.md)
for the design.

---

## License

GNU Affero General Public License v3 – see [LICENSE](LICENSE).

