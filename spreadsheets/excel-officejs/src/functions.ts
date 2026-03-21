/**
 * functions.ts – Excel OfficeJS Custom Functions for quantum simulation.
 *
 * Custom functions exposed to Excel:
 *
 * - `CQ_QPROBS(nQubits, opsJson, [initialStateJson], [optionsJson])`
 *   Returns a dynamic array of probabilities.
 *
 * - `CQ_QAMPS(nQubits, opsJson, [initialStateJson])`
 *   Returns a 2-column dynamic array [Re, Im] for each basis state.
 *
 * ## Output shape for CQ_QPROBS
 *
 * The optional `optionsJson` parameter accepts a JSON object:
 * ```json
 * {
 *   "shape": "auto" | "row" | "col",
 *   "hasHeader": true | false,
 *   "leftColumnReserved": true | false
 * }
 * ```
 *
 * Auto-shape rule:
 * - **Column vector (N×1)** – when `hasHeader` is `true` AND
 *   `leftColumnReserved` is `false` (or omitted).
 * - **Row vector (1×N)** – when there is no heading row, OR when the
 *   leftmost column is reserved for an index, key, or unit label.
 *
 * Default: `{"shape":"auto","hasHeader":false,"leftColumnReserved":false}`
 * which produces a row vector.  Set `"hasHeader":true` for the column form.
 */

/* global CustomFunctions */

import { GateOp, InitialState, ShapeOptions, loadWasm, qprobs, qamps, shapeResult } from "../../engine/quantumEngine";

// ---- Initialise WASM on add-in load ----------------------------------------

const wasmReady: Promise<void> = loadWasm(
  // Path is relative to where the add-in serves assets.
  // webpack copies the wasm-pack pkg into dist/quantum_engine/.
  "./quantum_engine/quantum_engine.js"
).catch((err: Error) => {
  console.error("CQ: WASM load failed:", err.message);
});

// ---- Helper ----------------------------------------------------------------

function parseOps(opsJson: string): GateOp[] {
  try {
    return JSON.parse(opsJson) as GateOp[];
  } catch {
    throw new CustomFunctions.Error(
      CustomFunctions.ErrorCode.invalidValue,
      `opsJson is not valid JSON: ${opsJson}`
    );
  }
}

function parseInitialState(json: string | undefined): InitialState | undefined {
  if (!json || json.trim() === "") return undefined;
  try {
    return JSON.parse(json) as InitialState;
  } catch {
    throw new CustomFunctions.Error(
      CustomFunctions.ErrorCode.invalidValue,
      `initialStateJson is not valid JSON: ${json}`
    );
  }
}

function parseOptions(json: string | undefined): ShapeOptions {
  if (!json || json.trim() === "") return {};
  try {
    return JSON.parse(json) as ShapeOptions;
  } catch {
    throw new CustomFunctions.Error(
      CustomFunctions.ErrorCode.invalidValue,
      `optionsJson is not valid JSON: ${json}`
    );
  }
}

// ---- CQ_QPROBS -------------------------------------------------------------

/**
 * @customfunction
 * @description Apply a quantum gate sequence and return basis-state probabilities.
 * @param nQubits {number} Number of qubits (1–20 recommended).
 * @param opsJson {string} JSON array of gate ops, e.g. [{"gate":"H","targets":[0]}].
 * @param initialStateJson {string} [optional] JSON for initial state, e.g. {"type":"zero"}.
 * @param optionsJson {string} [optional] JSON shape options, e.g. {"shape":"col","hasHeader":true}.
 * @returns {number[][]} Dynamic array of probabilities (column or row vector depending on options).
 */
export async function CQ_QPROBS(
  nQubits: number,
  opsJson: string,
  initialStateJson?: string,
  optionsJson?: string
): Promise<number[][]> {
  await wasmReady;
  try {
    const ops = parseOps(opsJson);
    const initial = parseInitialState(initialStateJson);
    const options = parseOptions(optionsJson);
    const probs = await qprobs(Math.round(nQubits), ops, initial);
    return shapeResult(probs, options);
  } catch (err) {
    if (err instanceof CustomFunctions.Error) throw err;
    throw new CustomFunctions.Error(
      CustomFunctions.ErrorCode.notAvailable,
      String(err)
    );
  }
}

// ---- CQ_QAMPS --------------------------------------------------------------

/**
 * @customfunction
 * @description Apply a quantum gate sequence and return complex amplitudes.
 * @param nQubits {number} Number of qubits.
 * @param opsJson {string} JSON array of gate ops.
 * @param initialStateJson {string} [optional] JSON for initial state.
 * @returns {number[][]} 2^nQubits × 2 array of [Re, Im] pairs.
 */
export async function CQ_QAMPS(
  nQubits: number,
  opsJson: string,
  initialStateJson?: string
): Promise<number[][]> {
  await wasmReady;
  try {
    const ops = parseOps(opsJson);
    const initial = parseInitialState(initialStateJson);
    const amps = await qamps(Math.round(nQubits), ops, initial);
    // Return as a 2D array: each row is [Re, Im].
    return amps.map(([re, im]) => [re, im]);
  } catch (err) {
    if (err instanceof CustomFunctions.Error) throw err;
    throw new CustomFunctions.Error(
      CustomFunctions.ErrorCode.notAvailable,
      String(err)
    );
  }
}
