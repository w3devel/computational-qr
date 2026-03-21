"""Parity tests: WASM engine output vs Python quantum_math reference.

These tests verify that the Rust→WASM quantum engine produces results that
match `computational_qr.quantum.quantum_math` for a set of small circuits
(1–2 qubits), including a custom-matrix gate path.

## Running the WASM tests

The tests call `spreadsheets/engine/run_wasm.mjs` via Node.js.  To run
the WASM-backed tests, first build the WASM package:

    cd rust/quantum_engine
    wasm-pack build --target nodejs

Then run the full test suite:

    pytest tests/test_wasm_parity.py -v

If `wasm-pack` output is not available (e.g. in CI without Rust/wasm-pack),
the WASM tests are **skipped** automatically rather than failing.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from computational_qr.quantum.quantum_math import (
    GATE_H,
    GATE_CNOT,
    GATE_X,
    GATE_Y,
    GATE_Z,
    GATE_S,
    GATE_T,
    GATE_SWAP,
    QuantumGate,
    QuantumRegister,
    QuantumState,
    STANDARD_GATES,
)

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
RUNNER_PATH = REPO_ROOT / "spreadsheets" / "engine" / "run_wasm.mjs"
WASM_PKG = REPO_ROOT / "rust" / "quantum_engine" / "pkg" / "quantum_engine.js"


def _wasm_available() -> bool:
    """Return True when the WASM package has been built."""
    return WASM_PKG.exists()


def _run_wasm(input_dict: dict) -> dict:
    """
    Run the WASM engine via Node.js for *input_dict*.

    Returns the parsed JSON output dict.  Raises RuntimeError on failure.
    """
    input_json = json.dumps(input_dict)
    result = subprocess.run(
        ["node", str(RUNNER_PATH), input_json],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"run_wasm.mjs failed (exit {result.returncode}):\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )
    return json.loads(result.stdout)


def _python_probs(n_qubits: int, ops: list[tuple], initial_amplitudes=None) -> np.ndarray:
    """
    Apply *ops* (list of (gate, qubit_indices...) tuples) using the Python
    reference engine and return the probability array.
    """
    if initial_amplitudes is not None:
        init_state = QuantumState(n_qubits, initial_amplitudes)
        reg = QuantumRegister(n_qubits, initial_state=init_state)
    else:
        reg = QuantumRegister(n_qubits)
    for gate, *targets in ops:
        reg.apply(gate, *targets)
    return reg.state.probabilities()


def _python_amps(n_qubits: int, ops: list[tuple], initial_amplitudes=None) -> np.ndarray:
    """Same as _python_probs but returns complex amplitudes."""
    if initial_amplitudes is not None:
        init_state = QuantumState(n_qubits, initial_amplitudes)
        reg = QuantumRegister(n_qubits, initial_state=init_state)
    else:
        reg = QuantumRegister(n_qubits)
    for gate, *targets in ops:
        reg.apply(gate, *targets)
    return reg.state.vector


# Skip marker used on all tests that require the built WASM package.
wasm_required = pytest.mark.skipif(
    not _wasm_available(),
    reason=(
        "WASM package not found. Build with: "
        "cd rust/quantum_engine && wasm-pack build --target nodejs"
    ),
)


# ---------------------------------------------------------------------------
# Helper: build WASM gate-op list from a sequence of (gate_name, targets)
# ---------------------------------------------------------------------------

def _named_ops(pairs: list[tuple[str, list[int]]]) -> list[dict]:
    return [{"gate": name, "targets": targets} for name, targets in pairs]


# ---------------------------------------------------------------------------
# Parity tests
# ---------------------------------------------------------------------------

@wasm_required
class TestWasmParityNamed:
    """Compare named-gate circuits: WASM vs Python."""

    def _compare(
        self,
        n_qubits: int,
        py_ops: list[tuple],
        wasm_op_pairs: list[tuple[str, list[int]]],
        atol: float = 1e-10,
    ) -> None:
        py = _python_probs(n_qubits, py_ops)
        result = _run_wasm(
            {"nQubits": n_qubits, "ops": _named_ops(wasm_op_pairs)}
        )
        wasm = np.array(result["probabilities"])
        np.testing.assert_allclose(wasm, py, atol=atol)

    def test_1q_h_on_zero(self):
        """H|0⟩ → [0.5, 0.5]"""
        self._compare(
            1,
            [(GATE_H, 0)],
            [("H", [0])],
        )

    def test_1q_x_on_zero(self):
        """X|0⟩ → [0, 1]"""
        self._compare(
            1,
            [(GATE_X, 0)],
            [("X", [0])],
        )

    def test_1q_y_on_zero(self):
        self._compare(1, [(GATE_Y, 0)], [("Y", [0])])

    def test_1q_z_on_zero(self):
        self._compare(1, [(GATE_Z, 0)], [("Z", [0])])

    def test_1q_s_on_plus(self):
        """S after H: |+⟩ → |+i⟩ (probs unchanged)."""
        self._compare(
            1,
            [(GATE_H, 0), (GATE_S, 0)],
            [("H", [0]), ("S", [0])],
        )

    def test_1q_t_on_plus(self):
        self._compare(
            1,
            [(GATE_H, 0), (GATE_T, 0)],
            [("H", [0]), ("T", [0])],
        )

    def test_2q_bell_state(self):
        """Bell circuit: H⊗I then CNOT → |Φ⁺⟩.  probs[0]=probs[3]=0.5."""
        py = _python_probs(2, [(GATE_H, 0), (GATE_CNOT, 0, 1)])
        result = _run_wasm(
            {
                "nQubits": 2,
                "ops": _named_ops([("H", [0]), ("CNOT", [0, 1])]),
            }
        )
        wasm = np.array(result["probabilities"])
        np.testing.assert_allclose(wasm, py, atol=1e-10)
        # Explicit acceptance criteria from the problem statement:
        assert abs(wasm[0] - 0.5) < 1e-10
        assert abs(wasm[3] - 0.5) < 1e-10

    def test_2q_x_on_qubit0_big_endian(self):
        """X on qubit 0 of |00⟩ → |10⟩ (index 2 in big-endian)."""
        py = _python_probs(2, [(GATE_X, 0)])
        result = _run_wasm(
            {"nQubits": 2, "ops": _named_ops([("X", [0])])}
        )
        wasm = np.array(result["probabilities"])
        np.testing.assert_allclose(wasm, py, atol=1e-10)
        assert abs(wasm[2] - 1.0) < 1e-10

    def test_2q_swap(self):
        """SWAP: prepare |10⟩ then SWAP → |01⟩."""
        py = _python_probs(2, [(GATE_X, 0), (GATE_SWAP, 0, 1)])
        result = _run_wasm(
            {"nQubits": 2, "ops": _named_ops([("X", [0]), ("SWAP", [0, 1])])}
        )
        wasm = np.array(result["probabilities"])
        np.testing.assert_allclose(wasm, py, atol=1e-10)

    def test_amplitudes_output(self):
        """WASM amplitude output matches Python state vector."""
        reg = QuantumRegister(1)
        reg.apply(GATE_H, 0)
        py_amps = reg.state.vector
        result = _run_wasm(
            {
                "nQubits": 1,
                "ops": _named_ops([("H", [0])]),
                "output": "amplitudes",
            }
        )
        wasm_amps = np.array([complex(a[0], a[1]) for a in result["amplitudes"]])
        np.testing.assert_allclose(np.abs(wasm_amps), np.abs(py_amps), atol=1e-10)


@wasm_required
class TestWasmParityCustomMatrix:
    """Verify that the custom-matrix gate path matches named gates."""

    @staticmethod
    def _hadamard_matrix_ops() -> list[dict]:
        s = math.sqrt(0.5)
        return [
            {
                "gate": {
                    "name": "H_custom",
                    "matrix": {
                        "dim": 2,
                        "data": [[s, 0.0], [s, 0.0], [s, 0.0], [-s, 0.0]],
                    },
                },
                "targets": [0],
            }
        ]

    def test_custom_hadamard_1q(self):
        """Custom 2×2 Hadamard matrix gives same probs as named 'H'."""
        named = _run_wasm(
            {"nQubits": 1, "ops": _named_ops([("H", [0])])}
        )
        custom = _run_wasm(
            {"nQubits": 1, "ops": self._hadamard_matrix_ops()}
        )
        np.testing.assert_allclose(
            custom["probabilities"], named["probabilities"], atol=1e-10
        )

    def test_custom_hadamard_2q_qubit1(self):
        """Custom H on qubit 1 of a 2-qubit register."""
        named = _run_wasm(
            {"nQubits": 2, "ops": _named_ops([("H", [1])])}
        )
        ops = self._hadamard_matrix_ops()
        ops[0]["targets"] = [1]
        custom = _run_wasm({"nQubits": 2, "ops": ops})
        np.testing.assert_allclose(
            custom["probabilities"], named["probabilities"], atol=1e-10
        )

    def test_custom_matrix_matches_python(self):
        """Custom Hadamard matches Python QuantumRegister.apply(GATE_H, 0)."""
        py = _python_probs(1, [(GATE_H, 0)])
        custom = _run_wasm(
            {"nQubits": 1, "ops": self._hadamard_matrix_ops()}
        )
        np.testing.assert_allclose(custom["probabilities"], py, atol=1e-10)

    def test_custom_cnot_4x4(self):
        """Custom 4×4 CNOT matrix matches named CNOT in Bell circuit."""
        # Build the CNOT matrix entries
        cnot_data = [
            [1.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
            [0.0, 0.0], [1.0, 0.0], [0.0, 0.0], [0.0, 0.0],
            [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [1.0, 0.0],
            [0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [0.0, 0.0],
        ]
        custom_bell_ops = [
            {"gate": "H", "targets": [0]},
            {
                "gate": {
                    "name": "CNOT_custom",
                    "matrix": {"dim": 4, "data": cnot_data},
                },
                "targets": [0, 1],
            },
        ]
        named_bell_ops = _named_ops([("H", [0]), ("CNOT", [0, 1])])
        named = _run_wasm({"nQubits": 2, "ops": named_bell_ops})
        custom = _run_wasm({"nQubits": 2, "ops": custom_bell_ops})
        np.testing.assert_allclose(
            custom["probabilities"], named["probabilities"], atol=1e-10
        )


@wasm_required
class TestWasmInitialState:
    """Custom initial states."""

    def test_custom_initial_x_gate(self):
        """Start in |1⟩ (via custom amplitudes) and apply X → |0⟩."""
        result = _run_wasm(
            {
                "nQubits": 1,
                "initialState": {
                    "type": "amplitudes",
                    "data": [[0.0, 0.0], [1.0, 0.0]],
                },
                "ops": _named_ops([("X", [0])]),
            }
        )
        probs = result["probabilities"]
        assert abs(probs[0] - 1.0) < 1e-10
        assert abs(probs[1]) < 1e-10

    def test_custom_initial_matches_python(self):
        """Non-trivial initial state: equal superposition fed through X."""
        s = math.sqrt(0.5)
        initial_amps = np.array([s + 0j, s + 0j])
        py = _python_probs(1, [(GATE_X, 0)], initial_amplitudes=initial_amps)
        result = _run_wasm(
            {
                "nQubits": 1,
                "initialState": {
                    "type": "amplitudes",
                    "data": [[s, 0.0], [s, 0.0]],
                },
                "ops": _named_ops([("X", [0])]),
            }
        )
        np.testing.assert_allclose(result["probabilities"], py, atol=1e-10)


# ---------------------------------------------------------------------------
# Pure-Python unit tests for the shapeResult logic (no WASM needed)
# ---------------------------------------------------------------------------

class TestShapeResultLogic:
    """
    Validate the CQ_QPROBS output-shape rules without loading WASM.

    These tests replicate the TypeScript `shapeResult` logic in Python so
    they can run in CI without Node / wasm-pack.
    """

    @staticmethod
    def _shape_result(values: list[float], options: dict) -> list[list[float]]:
        """Mirror of the TypeScript shapeResult function."""
        shape = options.get("shape", "auto")
        if shape == "col":
            use_col = True
        elif shape == "row":
            use_col = False
        else:
            use_col = bool(options.get("hasHeader", False)) and not bool(
                options.get("leftColumnReserved", False)
            )
        if use_col:
            return [[v] for v in values]
        else:
            return [values]

    def test_default_auto_no_header_is_row(self):
        result = self._shape_result([0.5, 0.5], {})
        assert result == [[0.5, 0.5]]

    def test_auto_with_header_is_col(self):
        result = self._shape_result([0.5, 0.5], {"hasHeader": True})
        assert result == [[0.5], [0.5]]

    def test_auto_header_but_left_reserved_is_row(self):
        result = self._shape_result(
            [0.5, 0.5], {"hasHeader": True, "leftColumnReserved": True}
        )
        assert result == [[0.5, 0.5]]

    def test_explicit_col(self):
        result = self._shape_result([0.25, 0.25, 0.25, 0.25], {"shape": "col"})
        assert result == [[0.25], [0.25], [0.25], [0.25]]

    def test_explicit_row(self):
        result = self._shape_result(
            [0.25, 0.25, 0.25, 0.25],
            {"shape": "row", "hasHeader": True},  # hasHeader ignored when explicit
        )
        assert result == [[0.25, 0.25, 0.25, 0.25]]

    def test_no_header_left_reserved_is_row(self):
        result = self._shape_result(
            [0.1, 0.2, 0.3], {"hasHeader": False, "leftColumnReserved": True}
        )
        assert result == [[0.1, 0.2, 0.3]]
