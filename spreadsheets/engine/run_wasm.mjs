#!/usr/bin/env node
/**
 * run_wasm.mjs
 *
 * Minimal Node.js runner that loads the compiled quantum_engine WASM
 * module and processes a single gate-sequence JSON request from stdin
 * (or from the first CLI argument), printing the JSON result to stdout.
 *
 * Usage:
 *   node run_wasm.mjs '{"nQubits":1,"ops":[{"gate":"H","targets":[0]}]}'
 *   echo '...' | node run_wasm.mjs
 *
 * The script looks for the WASM package at:
 *   ../../rust/quantum_engine/pkg/quantum_engine.js
 * (relative to this file), which is the default output location of
 * `wasm-pack build --target nodejs`.
 *
 * If the WASM package is not found, exits with code 2 and prints a message
 * suggesting building or installing the native helper.
 */

import { createRequire } from "module";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const require = createRequire(import.meta.url);

// Resolve path to the wasm-pack Node.js output.
const WASM_PKG = path.resolve(
  __dirname,
  "../../rust/quantum_engine/pkg/quantum_engine.js"
);

async function main() {
  // Load input JSON.
  let inputJson;
  if (process.argv[2]) {
    inputJson = process.argv[2];
  } else {
    inputJson = readFileSync("/dev/stdin", "utf8").trim();
  }

  // Try to load the WASM module.
  let engineModule;
  try {
    engineModule = await import(WASM_PKG);
  } catch (err) {
    process.stderr.write(
      `ERROR: Could not load WASM module at ${WASM_PKG}.\n` +
        `Build it first with:\n` +
        `  cd rust/quantum_engine && wasm-pack build --target nodejs\n` +
        `Or install the native helper server:\n` +
        `  cargo install computational-qr-server\n` +
        `Detail: ${err}\n`
    );
    process.exit(2);
  }

  // Call the engine.
  try {
    const result = engineModule.apply_gate_sequence(inputJson);
    process.stdout.write(result + "\n");
  } catch (err) {
    process.stderr.write(`ERROR: engine threw: ${err}\n`);
    process.exit(1);
  }
}

main();
