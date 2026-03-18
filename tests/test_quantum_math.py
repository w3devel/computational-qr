"""Tests for computational_qr.quantum.quantum_math."""

import math
import pytest
import numpy as np

from computational_qr.quantum.quantum_math import (
    QuantumState,
    QuantumGate,
    QuantumRegister,
    QuantumMath,
    GATE_H,
    GATE_X,
    GATE_Y,
    GATE_Z,
    GATE_I,
    GATE_CNOT,
    GATE_SWAP,
    STANDARD_GATES,
)


# ---------------------------------------------------------------------------
# QuantumState
# ---------------------------------------------------------------------------

class TestQuantumState:
    def test_default_is_zero_ket(self):
        state = QuantumState(2)
        probs = state.probabilities()
        assert probs[0] == pytest.approx(1.0)
        assert sum(probs) == pytest.approx(1.0)

    def test_custom_amplitudes_normalised(self):
        # Provide un-normalised amplitudes; constructor should normalise
        state = QuantumState(1, amplitudes=[3.0, 4.0])
        assert sum(state.probabilities()) == pytest.approx(1.0)

    def test_wrong_amplitude_length_raises(self):
        with pytest.raises(ValueError, match="Amplitudes"):
            QuantumState(2, amplitudes=[1.0, 0.0])  # needs 4

    def test_dim(self):
        assert QuantumState(3).dim == 8  # 2^3

    def test_measure_returns_valid_index(self):
        rng = np.random.default_rng(42)
        state = QuantumState(3)
        idx = state.measure(rng)
        assert 0 <= idx < 8

    def test_measure_as_bits_length(self):
        rng = np.random.default_rng(0)
        state = QuantumState(4)
        bits = state.measure_as_bits(rng)
        assert len(bits) == 4

    def test_measure_as_bits_chars(self):
        rng = np.random.default_rng(0)
        bits = QuantumState(2).measure_as_bits(rng)
        assert set(bits).issubset({"0", "1"})

    def test_entropy_ground_state_zero(self):
        state = QuantumState(2)
        assert state.entropy() == pytest.approx(0.0, abs=1e-9)

    def test_entropy_superposition_positive(self):
        # Equal superposition: |+⟩ has maximum entropy
        state = QuantumState(1, amplitudes=[1/math.sqrt(2), 1/math.sqrt(2)])
        assert state.entropy() == pytest.approx(1.0, abs=1e-6)

    def test_fidelity_self(self):
        state = QuantumState(2)
        assert state.fidelity(state) == pytest.approx(1.0)

    def test_fidelity_orthogonal(self):
        s1 = QuantumState(1, amplitudes=[1.0, 0.0])
        s2 = QuantumState(1, amplitudes=[0.0, 1.0])
        assert s2.fidelity(s1) == pytest.approx(0.0, abs=1e-9)

    def test_fidelity_qubit_mismatch_raises(self):
        with pytest.raises(ValueError):
            QuantumState(1).fidelity(QuantumState(2))

    def test_ket_notation_ground(self):
        ket = QuantumState(1).ket_notation()
        assert "|0" in ket

    def test_repr(self):
        r = repr(QuantumState(2))
        assert "QuantumState" in r


# ---------------------------------------------------------------------------
# QuantumGate
# ---------------------------------------------------------------------------

class TestQuantumGate:
    def test_gate_n_qubits(self):
        assert GATE_H.n_qubits == 1
        assert GATE_CNOT.n_qubits == 2

    def test_invalid_gate_not_square_raises(self):
        with pytest.raises(ValueError):
            QuantumGate("bad", np.array([[1, 0, 0], [0, 1, 0]]))

    def test_invalid_dimension_raises(self):
        with pytest.raises(ValueError):
            QuantumGate("bad", np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]]))  # 3x3

    def test_dagger_of_hadamard_is_hadamard(self):
        hd = GATE_H.dagger()
        assert np.allclose(GATE_H.matrix, hd.matrix, atol=1e-10)

    def test_dagger_name(self):
        assert "†" in GATE_H.dagger().name

    def test_matmul_composition(self):
        composed = GATE_X @ GATE_X  # X^2 = I
        assert np.allclose(composed.matrix, GATE_I.matrix, atol=1e-10)

    def test_standard_gates_dict(self):
        for name in ("H", "X", "Y", "Z", "I", "CNOT", "SWAP"):
            assert name in STANDARD_GATES

    def test_pauli_x_flips(self):
        """X gate flips |0⟩ to |1⟩."""
        reg = QuantumRegister(1)
        reg.apply(GATE_X, 0)
        probs = reg.state.probabilities()
        assert probs[1] == pytest.approx(1.0)

    def test_hadamard_creates_superposition(self):
        reg = QuantumRegister(1)
        reg.apply(GATE_H, 0)
        probs = reg.state.probabilities()
        assert probs[0] == pytest.approx(0.5, abs=1e-6)
        assert probs[1] == pytest.approx(0.5, abs=1e-6)


# ---------------------------------------------------------------------------
# QuantumRegister
# ---------------------------------------------------------------------------

class TestQuantumRegister:
    def test_initial_state_ground(self):
        reg = QuantumRegister(2)
        assert reg.state.probabilities()[0] == pytest.approx(1.0)

    def test_apply_single_qubit_gate(self):
        reg = QuantumRegister(2)
        reg.apply(GATE_X, 0)
        # Qubit 0 flipped: |00⟩ → |10⟩ (index 2 in big-endian)
        probs = reg.state.probabilities()
        assert probs[2] == pytest.approx(1.0, abs=1e-6)

    def test_apply_wrong_qubit_count_raises(self):
        reg = QuantumRegister(2)
        with pytest.raises(ValueError):
            reg.apply(GATE_CNOT, 0)  # CNOT needs 2 qubits

    def test_circuit_description(self):
        reg = QuantumRegister(2)
        reg.apply(GATE_H, 0).apply(GATE_X, 1)
        desc = reg.circuit_description()
        assert len(desc) == 2
        assert "H(0)" in desc
        assert "X(1)" in desc

    def test_measure_result_length(self):
        rng = np.random.default_rng(7)
        reg = QuantumRegister(3)
        bits = reg.measure(rng)
        assert len(bits) == 3

    def test_chaining(self):
        reg = QuantumRegister(2)
        result = reg.apply(GATE_H, 0).apply(GATE_H, 0)
        assert result is reg  # returns self
        # H^2 = I: should be back to |00⟩
        probs = reg.state.probabilities()
        assert probs[0] == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# QuantumMath
# ---------------------------------------------------------------------------

class TestQuantumMath:
    def _simple_matrix(self, rows: int = 4, cols: int = 4) -> list[list[bool]]:
        return [[(r + c) % 2 == 0 for c in range(cols)] for r in range(rows)]

    def test_matrix_to_state_type(self):
        state = QuantumMath.matrix_to_state(self._simple_matrix())
        assert isinstance(state, QuantumState)

    def test_matrix_to_state_n_qubits(self):
        state = QuantumMath.matrix_to_state(self._simple_matrix(rows=3, cols=5))
        assert state.n_qubits == 5

    def test_matrix_to_state_normalised(self):
        state = QuantumMath.matrix_to_state(self._simple_matrix())
        assert sum(state.probabilities()) == pytest.approx(1.0, abs=1e-9)

    def test_matrix_to_state_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            QuantumMath.matrix_to_state([])

    def test_apply_hadamard_transform(self):
        state = QuantumMath.matrix_to_state(self._simple_matrix(rows=2, cols=3))
        transformed = QuantumMath.apply_hadamard_transform(state)
        assert sum(transformed.probabilities()) == pytest.approx(1.0, abs=1e-9)

    def test_interference_pattern_length(self):
        pattern = QuantumMath.interference_pattern(self._simple_matrix(rows=2, cols=4))
        assert len(pattern) == 16  # 2^4

    def test_interference_pattern_sums_to_one(self):
        pattern = QuantumMath.interference_pattern(self._simple_matrix())
        assert sum(pattern) == pytest.approx(1.0, abs=1e-9)

    def test_quantum_fingerprint_is_string(self):
        fp = QuantumMath.quantum_fingerprint(self._simple_matrix())
        assert isinstance(fp, str)

    def test_quantum_fingerprint_differs_for_different_matrices(self):
        m1 = [[True, True], [False, False]]   # rows: |11⟩ and |00⟩
        m2 = [[True, False], [True, False]]   # rows: |10⟩ and |10⟩ (repeated)
        fp1 = QuantumMath.quantum_fingerprint(m1)
        fp2 = QuantumMath.quantum_fingerprint(m2)
        assert fp1 != fp2

    def test_bell_states(self):
        for i in range(4):
            state = QuantumMath.bell_state(i)
            assert state.n_qubits == 2
            # Bell states have exactly 2 non-zero amplitudes of equal magnitude
            nonzero = np.abs(state.vector)
            significant = nonzero[nonzero > 1e-9]
            assert len(significant) == 2
            assert significant[0] == pytest.approx(significant[1], abs=1e-9)

    def test_bell_state_entropy(self):
        # Maximally entangled → entropy = 1 bit (for 2 equally likely outcomes)
        state = QuantumMath.bell_state(0)
        assert state.entropy() == pytest.approx(1.0, abs=1e-6)
