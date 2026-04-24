/**
 * checkpoints.js — Persistent checkpoint index for TD network state.
 *
 * Manages a JSON index of named .tox snapshots.
 * Actual save/restore is done via TD's Python API through the /execute endpoint.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, unlinkSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
export const CHECKPOINTS_DIR = join(__dirname, "..", "checkpoints");
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

/** Build the Python script that saves a COMP as a .tox file. */
export function buildSaveScript(opPath, toxPath) {
  // Use raw string to avoid backslash issues in Python
  const safeToxPath = toxPath.replace(/\\/g, "/");
  return `\
import os
tox_path = '${safeToxPath}'
os.makedirs(os.path.dirname(tox_path), exist_ok=True)
o = op('${opPath}')
if o is None:
    print('ERROR: operator not found: ${opPath}')
elif o.family not in ('COMP',):
    o.save(tox_path)
    print('saved:' + tox_path)
else:
    o.save(tox_path)
    print('saved:' + tox_path)
`;
}

/** Build the Python script that restores a .tox into the parent of op_path. */
export function buildRestoreScript(opPath, toxPath) {
  const safeToxPath = toxPath.replace(/\\/g, "/");
  // Derive parent path: '/project1/myComp' → '/project1'
  const parentPath = opPath.substring(0, opPath.lastIndexOf("/")) || "/";
  return `\
import os
tox_path = '${safeToxPath}'
op_path = '${opPath}'
parent_path = '${parentPath}'
if not os.path.exists(tox_path):
    print('ERROR: checkpoint file not found: ' + tox_path)
else:
    existing = op(op_path)
    if existing:
        existing.destroy()
    parent = op(parent_path)
    if parent is None:
        print('ERROR: parent not found: ${parentPath}')
    else:
        new_comp = parent.loadTox(tox_path)
        if new_comp:
            print('restored:' + new_comp.path)
        else:
            print('ERROR: loadTox returned None')
`;
}
