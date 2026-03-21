# Native Rust Helper Server – Fallback Design

## Overview

The primary delivery mechanism for the quantum engine is **Rust→WASM**, loaded
directly in the browser by the Excel OfficeJS add-in or the LibreOffice/ZetaJS
extension.  No server is required in the typical case.

In some environments, WASM cannot be loaded or executed:

- Very locked-down Office 365 environments that block WASM execution.
- LibreOffice setups where the JS runtime does not support WASM.
- Automated workflows that need server-side batch processing.

For those cases, an **optional native Rust helper server** can be installed.

---

## Detection

The JS wrapper (`spreadsheets/engine/quantumEngine.ts`) catches WASM load
failures and emits a clear message:

```
WASM quantum engine is not available.
If you need server-side computation, install the native Rust helper:
  cargo install computational-qr-server
and start it with:
  computational-qr-server start
See docs/native-server-fallback.md for details.
```

The Excel add-in displays this message in a notification banner.

---

## Native server API (placeholder)

When implemented, the native server would:

1. Listen on `http://127.0.0.1:7878` by default (configurable via env var
   `CQ_SERVER_PORT`).
2. Expose a single POST endpoint:

   ```
   POST /quantum/apply-gate-sequence
   Content-Type: application/json

   { ...same InputSchema as the WASM engine... }

   → 200 OK + OutputSchema JSON
   ```

3. Shut down cleanly when no requests are received for a configurable idle
   period (default 5 minutes).

The JS wrapper would detect unavailable WASM and, if configured, fall back to
`fetch("http://127.0.0.1:7878/quantum/apply-gate-sequence", ...)`.

---

## Placeholder implementation plan

```
rust/
└── quantum_server/          ← future native server crate
    ├── Cargo.toml           (dependencies: axum, tokio, serde_json)
    └── src/
        └── main.rs          (axum router wrapping quantum_engine::apply_gate_sequence_str)
```

The server binary would reuse the same `quantum_engine` crate (compiled as
`rlib` for the native target instead of WASM).

---

## Security considerations

- The server binds to **loopback only** (`127.0.0.1`) so it is not accessible
  from the network.
- No authentication is required for a loopback-only local service.
- The server should validate the `nQubits` parameter to prevent accidental
  very-large state-vector allocations (e.g. cap at 20 qubits).
