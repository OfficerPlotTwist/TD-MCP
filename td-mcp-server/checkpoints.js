/**
 * checkpoints.js — Persistent checkpoint index for TD network state.
 *
 * Manages a JSON index of named .tox snapshots.
 * Actual save/restore is done via TD's Python API through the /execute endpoint.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, unlinkSync } from "fs";
import { join, dirname, resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
export const CHECKPOINTS_DIR = resolve(process.env.TD_CHECKPOINTS_DIR || join(__dirname, "..", "checkpoints"));
const INDEX_PATH = join(CHECKPOINTS_DIR, "index.json");

function ensureDir() {
  mkdirSync(CHECKPOINTS_DIR, { recursive: true });
}

function loadIndex() {
  ensureDir();
  if (!existsSync(INDEX_PATH)) return { checkpoints: [] };
  return JSON.parse(readFileSync(INDEX_PATH, "utf-8"));
}

function saveIndex(index) {
  ensureDir();
  writeFileSync(INDEX_PATH, JSON.stringify(index, null, 2));
}

export function listCheckpoints() {
  return loadIndex().checkpoints;
}

export function getCheckpoint(name) {
  return loadIndex().checkpoints.find((c) => c.name === name) ?? null;
}

/** Add or overwrite a checkpoint entry. Returns the entry. */
export function addCheckpoint(name, opPath, toxPath, description) {
  const index = loadIndex();
  const entry = {
    name,
    op_path: opPath,
    tox_path: toxPath,
    description: description ?? "",
    created_at: new Date().toISOString(),
  };
  const idx = index.checkpoints.findIndex((c) => c.name === name);
  if (idx >= 0) {
    // Remove old tox file if path changed
    const old = index.checkpoints[idx];
    if (old.tox_path !== toxPath && existsSync(old.tox_path)) {
      try { unlinkSync(old.tox_path); } catch (_) {}
    }
    index.checkpoints[idx] = entry;
  } else {
    index.checkpoints.push(entry);
  }
  saveIndex(index);
  return entry;
}

/** Remove a checkpoint entry. Returns the removed entry, or null if not found. */
export function removeCheckpoint(name) {
  const index = loadIndex();
  const entry = index.checkpoints.find((c) => c.name === name);
  if (!entry) return null;
  index.checkpoints = index.checkpoints.filter((c) => c.name !== name);
  saveIndex(index);
  if (existsSync(entry.tox_path)) {
    try { unlinkSync(entry.tox_path); } catch (_) {}
  }
  return entry;
}

// JSON string literals are also valid Python string literals, including escaped quotes.
const pyString = (value) => JSON.stringify(value);

/** Build a COMP snapshot script without interpolating executable path text. */
export function buildSaveScript(opPath, toxPath) {
  return `import os
tox_path = ${pyString(toxPath.replace(/\\/g, "/"))}
o = op(${pyString(opPath)})
if o is None:
    raise ValueError('Operator not found')
if o.family != 'COMP':
    raise ValueError('Checkpoint target must be a COMP')
os.makedirs(os.path.dirname(tox_path), exist_ok=True)
o.save(tox_path)
if not os.path.isfile(tox_path):
    raise RuntimeError('Checkpoint file was not written to the requested path')
print('saved:' + tox_path)
`;
}

/** Load and validate a snapshot before destroying the existing target. */
export function buildRestoreScript(opPath, toxPath) {
  if (opPath === "/" || !opPath.startsWith("/") || opPath.endsWith("/")) {
    throw new Error("Checkpoint restore requires a non-root absolute operator path");
  }
  const parentPath = opPath.substring(0, opPath.lastIndexOf("/")) || "/";
  const name = opPath.substring(opPath.lastIndexOf("/") + 1);
  return `import os
tox_path = ${pyString(toxPath.replace(/\\/g, "/"))}
op_path = ${pyString(opPath)}
parent_path = ${pyString(parentPath)}
if not os.path.isfile(tox_path):
    raise ValueError('Checkpoint file not found')
parent = op(parent_path)
if parent is None:
    raise ValueError('Checkpoint parent not found')
existing = op(op_path)
# Load first: an unreadable snapshot must not destroy the current network.
new_comp = parent.loadTox(tox_path)
if new_comp is None:
    raise RuntimeError('loadTox returned None')
if existing:
    existing.destroy()
new_comp.name = ${pyString(name)}
print('restored:' + new_comp.path)
`;
}
