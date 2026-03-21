/// JSON schema types for the quantum engine API.
///
/// Input:
/// ```json
/// {
///   "nQubits": 2,
///   "initialState": {"type": "zero"}
///     | {"type": "amplitudes", "data": [[re, im], ...]},
///   "ops": [
///     {"gate": "H",    "targets": [0]},
///     {"gate": "CNOT", "targets": [0, 1]},
///     {"gate": {"name": "U", "matrix": {"dim": 2, "data": [[re, im], ...]}},
///      "targets": [0]}
///   ],
///   "output": "probabilities" | "amplitudes"
/// }
/// ```
///
/// Output (probabilities):
/// ```json
/// {"probabilities": [0.5, 0.0, 0.0, 0.5]}
/// ```
///
/// Output (amplitudes):
/// ```json
/// {"amplitudes": [[0.707, 0.0], [0.0, 0.0], [0.0, 0.0], [0.707, 0.0]]}
/// ```

use serde::{Deserialize, Serialize};

// ---- Input schema ----------------------------------------------------------

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InputSchema {
    pub n_qubits: usize,
    #[serde(default)]
    pub initial_state: InitialState,
    pub ops: Vec<Op>,
    #[serde(default)]
    pub output: OutputKind,
}

#[derive(Deserialize, Default)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum InitialState {
    #[default]
    Zero,
    Amplitudes {
        data: Vec<[f64; 2]>,
    },
}

#[derive(Deserialize)]
pub struct Op {
    pub gate: GateSpec,
    pub targets: Vec<usize>,
}

/// A gate is either a named standard gate (string) or an inline custom matrix.
#[derive(Deserialize)]
#[serde(untagged)]
pub enum GateSpec {
    Named(String),
    Custom(CustomGate),
}

#[derive(Deserialize)]
pub struct CustomGate {
    pub name: Option<String>,
    pub matrix: CustomMatrix,
}

#[derive(Deserialize)]
pub struct CustomMatrix {
    /// Number of rows/cols (must be a power of two).
    pub dim: usize,
    /// Flat row-major list of complex entries as [re, im] pairs.
    pub data: Vec<[f64; 2]>,
}

#[derive(Deserialize, Default, PartialEq)]
#[serde(rename_all = "camelCase")]
pub enum OutputKind {
    #[default]
    Probabilities,
    Amplitudes,
}

// ---- Output schema ---------------------------------------------------------

#[derive(Serialize)]
#[serde(untagged)]
pub enum OutputSchema {
    Probabilities {
        probabilities: Vec<f64>,
    },
    Amplitudes {
        amplitudes: Vec<[f64; 2]>,
    },
}
