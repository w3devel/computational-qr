/// Core simulation engine: state vector management and gate application.

use crate::gates::{C, Matrix, custom_gate, standard_gate};
use crate::schema::{GateSpec, InitialState, InputSchema, Op, OutputKind, OutputSchema};

// ---- State vector ----------------------------------------------------------

struct StateVec {
    n: usize,   // number of qubits
    dim: usize, // 2^n
    v: Vec<C>,
}

impl StateVec {
    /// Initialise to |0…0⟩.
    fn zero(n: usize) -> Self {
        let dim = 1 << n;
        let mut v = vec![C::zero(); dim];
        v[0] = C::new(1.0, 0.0);
        Self { n, dim, v }
    }

    /// Initialise from user-supplied complex amplitudes (must have length 2^n).
    fn from_amplitudes(n: usize, data: &[[f64; 2]]) -> Result<Self, String> {
        let dim = 1 << n;
        if data.len() != dim {
            return Err(format!(
                "initialState.amplitudes length {} != 2^nQubits = {dim}",
                data.len()
            ));
        }
        let v: Vec<C> = data.iter().map(|&[re, im]| C::new(re, im)).collect();
        let norm_sq: f64 = v.iter().map(|c| c.norm_sq()).sum();
        if norm_sq < 1e-15 {
            return Err("initialState amplitudes have zero norm".into());
        }
        let norm = norm_sq.sqrt();
        let v = v.into_iter().map(|c| C::new(c.re / norm, c.im / norm)).collect();
        Ok(Self { n, dim, v })
    }

    fn probabilities(&self) -> Vec<f64> {
        self.v.iter().map(|c| c.norm_sq()).collect()
    }

    fn amplitudes(&self) -> Vec<[f64; 2]> {
        self.v.iter().map(|c| [c.re, c.im]).collect()
    }

    // ---- Gate application --------------------------------------------------

    /// Apply a k-qubit gate `mat` to qubits `targets` (big-endian qubit 0 = MSB).
    ///
    /// This general implementation works for any k ≥ 1.  It iterates over all
    /// 2^(n-k) "context" combinations for non-target qubits and applies the
    /// k-qubit gate in-place on the relevant 2^k amplitudes.
    fn apply_gate(&mut self, mat: &Matrix, targets: &[usize]) -> Result<(), String> {
        let k = targets.len();
        let local_dim = 1 << k;
        if mat.dim != local_dim {
            return Err(format!(
                "Gate matrix dim {local_dim} != 2^(targets.len()) = {local_dim}"
            ));
        }
        for t in targets {
            if *t >= self.n {
                return Err(format!(
                    "target qubit {t} out of range for {}-qubit register",
                    self.n
                ));
            }
        }

        let n = self.n;

        // Enumerate all 2^n basis indices.  Group them by the bits at
        // non-target positions; within each group collect the 2^k entries
        // corresponding to all combinations of target bits.
        //
        // Strategy: iterate over all 2^(n-k) "context" patterns (the bits of
        // non-target qubits), then for each pattern build the 2^k indices
        // (all combinations of target bits) and apply the gate matrix.

        // Build the list of non-target qubit positions (big-endian).
        let non_targets: Vec<usize> = (0..n).filter(|q| !targets.contains(q)).collect();
        let n_ctx = 1usize << (n - k);

        let mut buf = vec![C::zero(); local_dim];
        let mut out = vec![C::zero(); local_dim];

        for ctx_idx in 0..n_ctx {
            // Decode context bits back into a full state index with target bits = 0.
            let mut base_idx = 0usize;
            for (p, &q) in non_targets.iter().enumerate() {
                let bit = (ctx_idx >> (n - k - 1 - p)) & 1;
                // Qubit q corresponds to bit position (n-1-q) in the index.
                base_idx |= bit << (n - 1 - q);
            }

            // Gather the 2^k amplitudes.
            for local in 0..local_dim {
                let mut idx = base_idx;
                for (p, &t) in targets.iter().enumerate() {
                    let bit = (local >> (k - 1 - p)) & 1;
                    idx |= bit << (n - 1 - t);
                }
                buf[local] = self.v[idx];
            }

            // Multiply by gate matrix.
            mat.apply(&buf, &mut out);

            // Scatter back.
            for local in 0..local_dim {
                let mut idx = base_idx;
                for (p, &t) in targets.iter().enumerate() {
                    let bit = (local >> (k - 1 - p)) & 1;
                    idx |= bit << (n - 1 - t);
                }
                self.v[idx] = out[local];
            }
        }

        Ok(())
    }
}

// ---- Public API ------------------------------------------------------------

/// Resolve an `Op` into a concrete gate matrix.
fn resolve_gate(op: &Op) -> Result<(Matrix, &[usize]), String> {
    let mat = match &op.gate {
        GateSpec::Named(name) => {
            standard_gate(name).ok_or_else(|| format!("Unknown standard gate: {name:?}"))?
        }
        GateSpec::Custom(cg) => custom_gate(cg.matrix.dim, &cg.matrix.data)?,
    };
    let k = mat.dim.ilog2() as usize;
    if op.targets.len() != k {
        return Err(format!(
            "Gate acts on {k} qubit(s) but {} target(s) given",
            op.targets.len()
        ));
    }
    Ok((mat, &op.targets))
}

/// Main simulation entry point (used from both WASM and native tests).
pub fn apply_gate_sequence_str(input_json: &str) -> Result<String, String> {
    let input: InputSchema = serde_json::from_str(input_json)
        .map_err(|e| format!("JSON parse error: {e}"))?;

    if input.n_qubits == 0 {
        return Err("nQubits must be at least 1".into());
    }
    if input.n_qubits > 30 {
        return Err(format!("nQubits {} is too large (max 30)", input.n_qubits));
    }

    let mut state = match &input.initial_state {
        InitialState::Zero => StateVec::zero(input.n_qubits),
        InitialState::Amplitudes { data } => {
            StateVec::from_amplitudes(input.n_qubits, data)?
        }
    };

    for (i, op) in input.ops.iter().enumerate() {
        let (mat, targets) = resolve_gate(op)
            .map_err(|e| format!("op[{i}]: {e}"))?;
        state
            .apply_gate(&mat, targets)
            .map_err(|e| format!("op[{i}]: {e}"))?;
    }

    let output = match input.output {
        OutputKind::Probabilities => OutputSchema::Probabilities {
            probabilities: state.probabilities(),
        },
        OutputKind::Amplitudes => OutputSchema::Amplitudes {
            amplitudes: state.amplitudes(),
        },
    };

    serde_json::to_string(&output).map_err(|e| format!("JSON serialise error: {e}"))
}

// ---- Unit tests (native, not WASM) ----------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn probs(json: &str) -> Vec<f64> {
        let out = apply_gate_sequence_str(json).unwrap();
        let v: serde_json::Value = serde_json::from_str(&out).unwrap();
        v["probabilities"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_f64().unwrap())
            .collect()
    }

    #[test]
    fn hadamard_on_zero_gives_half_half() {
        let p = probs(r#"{"nQubits":1,"ops":[{"gate":"H","targets":[0]}]}"#);
        assert!((p[0] - 0.5).abs() < 1e-12);
        assert!((p[1] - 0.5).abs() < 1e-12);
    }

    #[test]
    fn bell_state_probabilities() {
        let p = probs(
            r#"{"nQubits":2,"ops":[
                {"gate":"H","targets":[0]},
                {"gate":"CNOT","targets":[0,1]}
            ]}"#,
        );
        assert!((p[0] - 0.5).abs() < 1e-12, "p[0]={}", p[0]);
        assert!((p[1]).abs() < 1e-12, "p[1]={}", p[1]);
        assert!((p[2]).abs() < 1e-12, "p[2]={}", p[2]);
        assert!((p[3] - 0.5).abs() < 1e-12, "p[3]={}", p[3]);
    }

    #[test]
    fn custom_hadamard_matches_standard() {
        let inv_sqrt2 = std::f64::consts::FRAC_1_SQRT_2;
        let custom = format!(
            r#"{{"nQubits":1,"ops":[{{"gate":{{"name":"H_custom","matrix":{{"dim":2,"data":[[{s},0],[{s},0],[{s},0],[{neg},{neg}]]}}}},"targets":[0]}}]}}"#,
            s = inv_sqrt2,
            neg = -inv_sqrt2,
        );
        // Note: the above uses the wrong data format; let's fix with a proper JSON string.
        let correct_json = format!(
            r#"{{
                "nQubits": 1,
                "ops": [{{
                    "gate": {{
                        "name": "H_custom",
                        "matrix": {{
                            "dim": 2,
                            "data": [[{s}, 0.0], [{s}, 0.0], [{s}, 0.0], [{neg}, 0.0]]
                        }}
                    }},
                    "targets": [0]
                }}]
            }}"#,
            s = inv_sqrt2,
            neg = -inv_sqrt2,
        );
        let p_custom = probs(&correct_json);
        let p_named = probs(r#"{"nQubits":1,"ops":[{"gate":"H","targets":[0]}]}"#);
        assert!((p_custom[0] - p_named[0]).abs() < 1e-12);
        assert!((p_custom[1] - p_named[1]).abs() < 1e-12);
    }

    #[test]
    fn x_gate_flips_qubit_0_big_endian() {
        // X on qubit 0 of a 2-qubit register: |00⟩ → |10⟩ (index 2)
        let p = probs(r#"{"nQubits":2,"ops":[{"gate":"X","targets":[0]}]}"#);
        assert!((p[2] - 1.0).abs() < 1e-12, "expected prob[2]=1.0, got {:?}", p);
    }

    #[test]
    fn amplitudes_output() {
        let out = apply_gate_sequence_str(
            r#"{"nQubits":1,"ops":[{"gate":"H","targets":[0]}],"output":"amplitudes"}"#,
        )
        .unwrap();
        let v: serde_json::Value = serde_json::from_str(&out).unwrap();
        let amps = v["amplitudes"].as_array().unwrap();
        assert_eq!(amps.len(), 2);
        let a0 = amps[0][0].as_f64().unwrap();
        assert!((a0 - std::f64::consts::FRAC_1_SQRT_2).abs() < 1e-12);
    }

    #[test]
    fn invalid_gate_name_errors() {
        let result = apply_gate_sequence_str(
            r#"{"nQubits":1,"ops":[{"gate":"BOGUS","targets":[0]}]}"#,
        );
        assert!(result.is_err());
    }

    #[test]
    fn target_out_of_range_errors() {
        let result = apply_gate_sequence_str(
            r#"{"nQubits":1,"ops":[{"gate":"X","targets":[5]}]}"#,
        );
        assert!(result.is_err());
    }

    #[test]
    fn initial_state_amplitudes() {
        // Start in |1⟩ and apply X to get |0⟩
        let p = probs(
            r#"{"nQubits":1,"initialState":{"type":"amplitudes","data":[[0.0,0.0],[1.0,0.0]]},"ops":[{"gate":"X","targets":[0]}]}"#,
        );
        assert!((p[0] - 1.0).abs() < 1e-12);
    }
}
