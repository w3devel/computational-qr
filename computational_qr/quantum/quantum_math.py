"""Quantum-math primitives for QR state representation.

This module provides a pure-NumPy quantum computing layer that can represent
QR data as quantum states, apply quantum gates, and measure the resulting
probability distributions.

Key concepts
------------
* **QuantumState** – a normalised complex vector of length 2^n (n qubits).
* **QuantumGate**  – a unitary 2D matrix operating on one or more qubits.
* **QuantumRegister** – a multi-qubit register supporting gate application and
  partial measurement.
* **QuantumMath** – high-level helpers for encoding QR module matrices as
  quantum states and computing interference patterns.

These primitives enable "quantum superposition" encoding where a QR code's
entire module matrix is represented as a single quantum state—different
bitstrings (QR patterns) exist in superposition until measured.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# QuantumState
# ---------------------------------------------------------------------------

class QuantumState:
    """A normalised quantum state vector for *n_qubits* qubits.

    The state is stored as a complex NumPy array of length 2^n.  Basis states
    are indexed in big-endian order: index 0 = |00…0⟩, index 1 = |00…1⟩, etc.

    Parameters
    ----------
    n_qubits:
        Number of qubits.
    amplitudes:
        Optional initial amplitude vector.  Must have length 2^n_qubits.
        If omitted the state is initialised to |0…0⟩.
    """

    def __init__(
        self,
        n_qubits: int,
        amplitudes: Sequence[complex] | np.ndarray | None = None,
    ) -> None:
        self.n_qubits = n_qubits
        dim = 1 << n_qubits  # 2^n_qubits
        if amplitudes is not None:
            arr = np.array(amplitudes, dtype=complex)
            if arr.shape != (dim,):
                raise ValueError(
                    f"Amplitudes length {len(arr)} != 2^{n_qubits} = {dim}"
                )
            self._vec: np.ndarray = arr / np.linalg.norm(arr)
        else:
            self._vec = np.zeros(dim, dtype=complex)
            self._vec[0] = 1.0

    @property
    def vector(self) -> np.ndarray:
        return self._vec.copy()

    @property
    def dim(self) -> int:
        return len(self._vec)

    # ------------------------------------------------------------------
    # Probabilities and measurement
    # ------------------------------------------------------------------

    def probabilities(self) -> np.ndarray:
        """Return probability for each basis state: P(|i⟩) = |α_i|²."""
        return (np.abs(self._vec) ** 2).real

    def measure(self, rng: np.random.Generator | None = None) -> int:
        """Simulate a projective measurement; collapse to one basis state.

        Returns
        -------
        int
            The measured basis-state index.
        """
        rng = rng or np.random.default_rng()
        probs = self.probabilities()
        return int(rng.choice(self.dim, p=probs))

    def measure_as_bits(self, rng: np.random.Generator | None = None) -> str:
        """Measure and return the result as a bit-string of length *n_qubits*."""
        idx = self.measure(rng)
        return format(idx, f"0{self.n_qubits}b")

    # ------------------------------------------------------------------
    # Entanglement metrics
    # ------------------------------------------------------------------

    def entropy(self) -> float:
        """Von Neumann entropy (Shannon entropy of probabilities, base 2)."""
        probs = self.probabilities()
        nonzero = probs[probs > 0]
        return float(-np.sum(nonzero * np.log2(nonzero)))

    def fidelity(self, other: "QuantumState") -> float:
        """Return the fidelity F = |⟨ψ|φ⟩|² between self and *other*."""
        if self.n_qubits != other.n_qubits:
            raise ValueError("Qubit counts must match for fidelity calculation.")
        overlap = np.dot(self._vec.conj(), other._vec)
        return float(abs(overlap) ** 2)

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------

    def ket_notation(self, threshold: float = 1e-6) -> str:
        """Return a Dirac ket-notation string, omitting near-zero terms."""
        terms: list[str] = []
        for i, amp in enumerate(self._vec):
            if abs(amp) < threshold:
                continue
            basis = format(i, f"0{self.n_qubits}b")
            r, im = amp.real, amp.imag
            if abs(im) < threshold:
                coeff = f"{r:.3f}"
            elif abs(r) < threshold:
                coeff = f"{im:.3f}i"
            else:
                sign = "+" if im >= 0 else "-"
                coeff = f"({r:.3f}{sign}{abs(im):.3f}i)"
            terms.append(f"{coeff}|{basis}⟩")
        return " + ".join(terms) if terms else "0"

    def __repr__(self) -> str:
        return f"QuantumState(n={self.n_qubits}, |ψ⟩={self.ket_notation()[:60]})"


# ---------------------------------------------------------------------------
# QuantumGate
# ---------------------------------------------------------------------------

@dataclass
class QuantumGate:
    """A named unitary matrix gate.

    Parameters
    ----------
    name:
        Human-readable name (e.g. ``"H"``, ``"CNOT"``).
    matrix:
        Complex unitary numpy array of shape (2^k, 2^k) for a k-qubit gate.
    """

    name: str
    matrix: np.ndarray

    def __post_init__(self) -> None:
        m = self.matrix
        if m.ndim != 2 or m.shape[0] != m.shape[1]:
            raise ValueError("Gate matrix must be square.")
        n = m.shape[0]
        if n == 0 or (n & (n - 1)) != 0:
            raise ValueError("Gate matrix dimension must be a power of 2.")

    @property
    def n_qubits(self) -> int:
        return int(math.log2(self.matrix.shape[0]))

    def dagger(self) -> "QuantumGate":
        """Return the Hermitian conjugate (adjoint) of this gate."""
        return QuantumGate(name=f"{self.name}†", matrix=self.matrix.conj().T)

    def __matmul__(self, other: "QuantumGate") -> "QuantumGate":
        """Compose two gates: (self @ other) applies *other* first."""
        return QuantumGate(
            name=f"{self.name}·{other.name}",
            matrix=self.matrix @ other.matrix,
        )


# ---------------------------------------------------------------------------
# Standard gates
# ---------------------------------------------------------------------------

def _gate(name: str, data: list) -> QuantumGate:
    return QuantumGate(name=name, matrix=np.array(data, dtype=complex))


_INV_SQRT2 = 1.0 / math.sqrt(2)

GATE_I  = _gate("I",  [[1, 0], [0, 1]])
GATE_X  = _gate("X",  [[0, 1], [1, 0]])          # Pauli-X (NOT)
GATE_Y  = _gate("Y",  [[0, -1j], [1j, 0]])        # Pauli-Y
GATE_Z  = _gate("Z",  [[1, 0], [0, -1]])           # Pauli-Z
GATE_H  = _gate("H",  [[_INV_SQRT2, _INV_SQRT2],  # Hadamard
                        [_INV_SQRT2, -_INV_SQRT2]])
GATE_S  = _gate("S",  [[1, 0], [0, 1j]])           # Phase
GATE_T  = _gate("T",  [[1, 0], [0, cmath.exp(1j * math.pi / 4)]])  # π/8

GATE_CNOT = _gate("CNOT", [
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1],
    [0, 0, 1, 0],
])  # 2-qubit controlled-NOT

GATE_SWAP = _gate("SWAP", [
    [1, 0, 0, 0],
    [0, 0, 1, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1],
])

STANDARD_GATES = {
    "I": GATE_I, "X": GATE_X, "Y": GATE_Y, "Z": GATE_Z,
    "H": GATE_H, "S": GATE_S, "T": GATE_T,
    "CNOT": GATE_CNOT, "SWAP": GATE_SWAP,
}


# ---------------------------------------------------------------------------
# QuantumRegister
# ---------------------------------------------------------------------------

class QuantumRegister:
    """Multi-qubit quantum register supporting gate application and measurement.

    Parameters
    ----------
    n_qubits:
        Number of qubits in the register.
    initial_state:
        Optional initial :class:`QuantumState`.  Defaults to |0…0⟩.
    """

    def __init__(
        self,
        n_qubits: int,
        initial_state: QuantumState | None = None,
    ) -> None:
        self.n_qubits = n_qubits
        self.state = initial_state or QuantumState(n_qubits)
        self._circuit: list[tuple[str, tuple[int, ...]]] = []

    # ------------------------------------------------------------------
    # Gate application
    # ------------------------------------------------------------------

    def apply(self, gate: QuantumGate, *qubit_indices: int) -> "QuantumRegister":
        """Apply *gate* to the specified qubits and return self (chainable).

        For single-qubit gates: ``reg.apply(GATE_H, 0)``
        For two-qubit gates:   ``reg.apply(GATE_CNOT, 0, 1)``
        """
        k = gate.n_qubits
        if len(qubit_indices) != k:
            raise ValueError(
                f"Gate {gate.name!r} acts on {k} qubit(s) but "
                f"{len(qubit_indices)} index(es) were given."
            )
        full = self._expand_gate(gate, qubit_indices)
        self.state = QuantumState(
            self.n_qubits,
            amplitudes=full @ self.state._vec,
        )
        self._circuit.append((gate.name, qubit_indices))
        return self

    def _expand_gate(
        self, gate: QuantumGate, qubit_indices: tuple[int, ...]
    ) -> np.ndarray:
        """Expand a local gate matrix to act on the full register Hilbert space."""
        n = self.n_qubits
        k = gate.n_qubits
        dim = 1 << n
        full = np.zeros((dim, dim), dtype=complex)

        for i in range(dim):
            bits_i = [(i >> (n - 1 - q)) & 1 for q in range(n)]
            for j in range(dim):
                bits_j = [(j >> (n - 1 - q)) & 1 for q in range(n)]
                # Check non-target qubits match
                match = all(
                    bits_i[q] == bits_j[q]
                    for q in range(n)
                    if q not in qubit_indices
                )
                if not match:
                    continue
                # Local sub-indices
                row_sub = sum(bits_i[q] << (k - 1 - p) for p, q in enumerate(qubit_indices))
                col_sub = sum(bits_j[q] << (k - 1 - p) for p, q in enumerate(qubit_indices))
                full[i, j] = gate.matrix[row_sub, col_sub]
        return full

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def measure(self, rng: np.random.Generator | None = None) -> str:
        """Measure the full register; return bit-string result."""
        return self.state.measure_as_bits(rng)

    # ------------------------------------------------------------------
    # Circuit description
    # ------------------------------------------------------------------

    def circuit_description(self) -> list[str]:
        return [
            f"{name}({', '.join(str(q) for q in qubits)})"
            for name, qubits in self._circuit
        ]


# ---------------------------------------------------------------------------
# QuantumMath – high-level utilities
# ---------------------------------------------------------------------------

class QuantumMath:
    """High-level quantum math utilities for QR encoding.

    These methods bridge the gap between classical QR bit matrices and quantum
    state representations, enabling "quantum superposition" of QR data.
    """

    # ------------------------------------------------------------------
    # Encoding QR matrices as quantum states
    # ------------------------------------------------------------------

    @staticmethod
    def matrix_to_state(matrix: Sequence[Sequence[bool]]) -> QuantumState:
        """Encode a boolean QR matrix as a quantum superposition state.

        Each row of the matrix is treated as a bitstring.  The state is a
        uniform superposition over all distinct row bitstrings, weighted by
        their frequency of occurrence.

        Parameters
        ----------
        matrix:
            2D boolean QR module grid.

        Returns
        -------
        QuantumState
            A state whose number of qubits equals the number of columns.
        """
        if not matrix:
            raise ValueError("Matrix must not be empty.")
        n_cols = max(len(r) for r in matrix)
        dim = 1 << n_cols
        amplitudes = np.zeros(dim, dtype=complex)
        for row in matrix:
            # Convert row to integer index (big-endian)
            idx = 0
            for bit in row:
                idx = (idx << 1) | (1 if bit else 0)
            amplitudes[idx] += 1.0
        norm = np.linalg.norm(amplitudes)
        if norm == 0:
            amplitudes[0] = 1.0
        return QuantumState(n_cols, amplitudes)

    @staticmethod
    def apply_hadamard_transform(state: QuantumState) -> QuantumState:
        """Apply a Hadamard gate to every qubit of *state* (quantum Fourier hint).

        This transforms the state into the Hadamard basis, which reveals the
        frequency structure of the QR pattern.
        """
        reg = QuantumRegister(state.n_qubits, initial_state=state)
        for q in range(state.n_qubits):
            reg.apply(GATE_H, q)
        return reg.state

    @staticmethod
    def interference_pattern(matrix: Sequence[Sequence[bool]]) -> np.ndarray:
        """Compute the quantum interference pattern of a QR matrix.

        Encodes the matrix as a state, applies the Hadamard transform, and
        returns the resulting probability distribution.  The interference
        pattern can be used as a quantum fingerprint of the QR code.

        Returns
        -------
        numpy.ndarray
            Probability array of length 2^n_cols.
        """
        state = QuantumMath.matrix_to_state(matrix)
        transformed = QuantumMath.apply_hadamard_transform(state)
        return transformed.probabilities()

    @staticmethod
    def quantum_fingerprint(matrix: Sequence[Sequence[bool]]) -> str:
        """Return a hex string derived from the quantum interference pattern."""
        pattern = QuantumMath.interference_pattern(matrix)
        # Hash the dominant amplitudes
        top_k = np.argsort(pattern)[-8:][::-1]
        parts = [f"{i:04x}{int(pattern[i]*65535):04x}" for i in top_k]
        return "".join(parts)

    # ------------------------------------------------------------------
    # Bell-state generation (entanglement demo)
    # ------------------------------------------------------------------

    @staticmethod
    def bell_state(which: int = 0) -> QuantumState:
        """Return one of the four 2-qubit Bell (maximally entangled) states.

        Parameters
        ----------
        which:
            0 → |Φ⁺⟩, 1 → |Φ⁻⟩, 2 → |Ψ⁺⟩, 3 → |Ψ⁻⟩
        """
        reg = QuantumRegister(2)
        if which in (1, 3):
            reg.apply(GATE_Z, 0)
        if which in (2, 3):
            reg.apply(GATE_X, 1)
        reg.apply(GATE_H, 0)
        reg.apply(GATE_CNOT, 0, 1)
        return reg.state
