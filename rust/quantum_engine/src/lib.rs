/*!
# quantum_engine

A WebAssembly quantum gate-sequence simulation engine for the
`computational-qr` project.

## Qubit indexing convention

Qubit 0 is the **most-significant** (leftmost) bit, matching the
big-endian convention used by `computational_qr.quantum.quantum_math`.

For an n-qubit register, basis state index k has bit n-1-q set
when qubit q is |1⟩:

```text
index = Σ  bit[q] * 2^(n-1-q)
         q=0..n-1
```

## Primary export

`apply_gate_sequence(input_json: &str) -> Result<String, JsValue>`

See the `InputSchema` / `OutputSchema` types for the JSON contract.
*/

#[cfg(target_arch = "wasm32")]
use wasm_bindgen::prelude::*;

mod schema;
mod gates;
mod engine;

pub use engine::apply_gate_sequence_str;

/// WebAssembly entry point.
///
/// Accepts a JSON string conforming to `InputSchema` and returns a JSON
/// string conforming to `OutputSchema`.  On error returns a descriptive
/// `JsValue` string.
#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn apply_gate_sequence(input_json: &str) -> Result<String, JsValue> {
    apply_gate_sequence_str(input_json)
        .map_err(|e| JsValue::from_str(&e))
}
