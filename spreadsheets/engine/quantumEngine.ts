/**
 * quantumEngine.ts
 *
 * JavaScript/TypeScript wrapper for the Rust→WASM quantum gate-sequence
 * simulation engine (`quantum_engine`).
 *
 * ## Usage
 *
 * ```ts
 * import { qprobs, qamps, isWasmAvailable } from "./quantumEngine";
 *
 * const probs = await qprobs(2, [
 *   { gate: "H",    targets: [0] },
 *   { gate: "CNOT", targets: [0, 1] },
 * ]);
 * // probs ≈ [0.5, 0, 0, 0.5]
 * ```
 *
 * ## WASM unavailability
 *
 * If the WASM module cannot be loaded (e.g. missing file, restricted
 * environment), all functions throw a descriptive error that includes a
 * suggestion to install the native helper server.
 *
 * ## Output shape for `CQ_QPROBS`
 *
 * The `shapeResult` helper implements the spreadsheet output-shape rules:
 *
 * | `options.shape` | `hasHeader` | `leftColumnReserved` | Result shape |
 * |---|---|---|---|
 * | `"col"` | any | any | N×1 column vector |
 * | `"row"` | any | any | 1×N row vector |
 * | `"auto"` (default) | `true` | `false` | N×1 column vector |
 * | `"auto"` | `false` | any | 1×N row vector |
 * | `"auto"` | any | `true` | 1×N row vector |
 *
 * Rule summary: prefer a **column vector** when there is a headings row and
 * the leftmost column is not reserved (index/key/units).  In all other cases
 * use a **row vector**.
 */

// ---- Types -----------------------------------------------------------------

export interface GateOp {
  gate:
    | string
    | { name?: string; matrix: { dim: number; data: [number, number][] } };
  targets: number[];
}

export interface InitialState {
  type: "zero" | "amplitudes";
  data?: [number, number][];
}

export interface EngineInput {
  nQubits: number;
  initialState?: InitialState;
  ops: GateOp[];
  output?: "probabilities" | "amplitudes";
}

export interface ShapeOptions {
  /** "auto" | "row" | "col" – default "auto" */
  shape?: "auto" | "row" | "col";
  /** Does the spreadsheet region have a heading row? (auto-mode only) */
  hasHeader?: boolean;
  /** Is the leftmost column reserved for an index/key/units column? (auto-mode only) */
  leftColumnReserved?: boolean;
}

// ---- WASM loader -----------------------------------------------------------

let _wasmModule: {
  apply_gate_sequence: (json: string) => string;
} | null = null;
let _wasmLoadError: string | null = null;
let _wasmLoadAttempted = false;

const WASM_UNAVAILABLE_MESSAGE =
  "WASM quantum engine is not available. " +
  'If you need server-side computation, install the native Rust helper: ' +
  '"cargo install computational-qr-server" and start it with ' +
  '"computational-qr-server start". ' +
  "See docs/native-server-fallback.md for details.";

/**
 * Attempt to load the WASM module.  Resolves immediately if already loaded.
 * Rejects with a helpful message if the WASM cannot be loaded.
 */
export async function loadWasm(wasmUrl?: string): Promise<void> {
  if (_wasmModule) return;
  if (_wasmLoadAttempted && _wasmLoadError) {
    throw new Error(_wasmLoadError);
  }
  _wasmLoadAttempted = true;

  try {
    // Dynamic import – bundlers (webpack, vite, etc.) can tree-shake this.
    // Falls back to the standard pkg path emitted by wasm-pack.
    const url =
      wasmUrl ??
      (typeof __WASM_URL__ !== "undefined"
        ? __WASM_URL__
        : "./quantum_engine/quantum_engine.js");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mod: any = await import(/* webpackIgnore: true */ url);
    if (typeof mod.default === "function") {
      // wasm-pack "bundler" target wraps init() as the default export.
      await mod.default();
    }
    _wasmModule = mod;
  } catch (err) {
    _wasmLoadError =
      `Failed to load WASM module: ${err}. ` + WASM_UNAVAILABLE_MESSAGE;
    throw new Error(_wasmLoadError);
  }
}

/** Returns true when the WASM module has been successfully loaded. */
export function isWasmAvailable(): boolean {
  return _wasmModule !== null;
}

// ---- Core call -------------------------------------------------------------

function callEngine(input: EngineInput): string {
  if (!_wasmModule) {
    throw new Error(
      "WASM module not loaded. Call loadWasm() first. " +
        WASM_UNAVAILABLE_MESSAGE
    );
  }
  const json = JSON.stringify(input);
  return _wasmModule.apply_gate_sequence(json);
}

// ---- Public API ------------------------------------------------------------

/**
 * Apply a gate sequence and return the probability distribution.
 *
 * @param nQubits   Number of qubits.
 * @param ops       Array of gate operations.
 * @param initial   Optional initial state (defaults to |0…0⟩).
 * @returns         Float array of length 2^nQubits.
 */
export async function qprobs(
  nQubits: number,
  ops: GateOp[],
  initial?: InitialState
): Promise<number[]> {
  await loadWasm();
  const raw = callEngine({ nQubits, ops, initialState: initial, output: "probabilities" });
  const parsed = JSON.parse(raw) as { probabilities: number[] };
  return parsed.probabilities;
}

/**
 * Apply a gate sequence and return the complex amplitudes.
 *
 * @param nQubits   Number of qubits.
 * @param ops       Array of gate operations.
 * @param initial   Optional initial state.
 * @returns         Array of [re, im] pairs, length 2^nQubits.
 */
export async function qamps(
  nQubits: number,
  ops: GateOp[],
  initial?: InitialState
): Promise<[number, number][]> {
  await loadWasm();
  const raw = callEngine({ nQubits, ops, initialState: initial, output: "amplitudes" });
  const parsed = JSON.parse(raw) as { amplitudes: [number, number][] };
  return parsed.amplitudes;
}

// ---- Output shape helper ---------------------------------------------------

/**
 * Shape a flat probability array into a 2-D dynamic array suitable for
 * an Excel Custom Function return value, according to `ShapeOptions`.
 *
 * Default rule (`shape: "auto"`):
 * - Use a **column vector** (N×1) when `hasHeader` is true AND
 *   `leftColumnReserved` is false.
 * - Use a **row vector** (1×N) in all other cases.
 *
 * The caller can override with `shape: "row"` or `shape: "col"`.
 */
export function shapeResult(
  values: number[],
  options?: ShapeOptions
): number[][] {
  const shape = options?.shape ?? "auto";

  let useCol: boolean;
  if (shape === "col") {
    useCol = true;
  } else if (shape === "row") {
    useCol = false;
  } else {
    // auto: column when there is a heading row and the leftmost column is free
    useCol =
      (options?.hasHeader ?? false) &&
      !(options?.leftColumnReserved ?? false);
  }

  if (useCol) {
    // N×1
    return values.map((v) => [v]);
  } else {
    // 1×N
    return [values];
  }
}

// ---- Module augmentation for bundlers --------------------------------------

// Allow build tools to inject the WASM URL at compile time.
declare const __WASM_URL__: string | undefined;
