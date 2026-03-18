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
│   └── qr_encoder.py       # QRData (typed envelope), QREncoder
├── graphs/
│   └── graph_3d.py         # DataPoint, Intersection, Graph3D
├── prolog/
│   ├── prolog_engine.py    # Pure-Python Horn-clause resolver
│   └── prolog_qr.py        # Encode/decode/execute Prolog as QR
├── media/
│   ├── audio_qr.py         # FSK audio encoding / WAV output
│   └── video_qr.py         # Animated SVG video QR
├── quantum/
│   └── quantum_math.py     # QuantumState, QuantumGate, QuantumRegister, QuantumMath
└── database/
    └── neo4j_store.py      # Neo4jStore with real + mock backends
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

---

## Running the tests

```bash
pytest tests/ -v
```

All 203 tests pass with no external services required (Neo4j mock is used
automatically for database tests).

---

## License

GNU Affero General Public License v3 – see [LICENSE](LICENSE).

