#!/usr/bin/env node
/**
 * check-errors.mjs — Stop hook: after a turn's network operations are done,
 * sweep the LIVE TD project for erroring operators and block only on NEW ones.
 *
 * Live means op.errors() + op.warnings() per operator — NOT the bridge's
 * get_errors / /execute "errors" list, which is a sticky historical log that
 * keeps rows long after the underlying fault is fixed (see memory:
 * td-get-errors-rows-are-sticky). Warnings are included because this TD build
 * reports most real breakage as warnings (GLSL compile failures, missing
 * movie files, missing channels are all warnings, not errors).
 *
 * Baseline: errors-baseline.json (next to this file) maps op path → first
 * error line. Errors present there are accepted (pre-existing or intentional)
 * and never block. First run with no baseline grandfathers everything current.
 * Paths whose errors clear are pruned from the baseline automatically; NEW
 * erroring paths block the stop and are NOT auto-added — fix the op, or add
 * the path to the baseline deliberately if it is expected.
 *
 * Safeguards (same as check-wires.mjs):
 *   - no-op silently if the TD bridge is unreachable (TD not running)
 *   - guard against infinite loops via stop_hook_active
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HOST = process.env.TD_HOST || "127.0.0.1";
const PORT = process.env.TD_PORT || "9980";
const BASE = `http://${HOST}:${PORT}`;
const BASELINE = join(dirname(fileURLToPath(import.meta.url)), "errors-baseline.json");

// --- read hook stdin (JSON) for the loop guard -----------------------------
let raw = "";
try {
  for await (const chunk of process.stdin) raw += chunk;
} catch {}
let hookInput = {};
try {
  hookInput = JSON.parse(raw.replace(/^﻿/, "") || "{}"); // strip BOM (PowerShell pipes add one)
} catch {}
if (hookInput.stop_hook_active) process.exit(0); // already re-fired once — don't loop

// --- health check: silent no-op if TD isn't up -----------------------------
try {
  const h = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(2000) });
  if (!h.ok) process.exit(0);
} catch {
  process.exit(0);
}

// --- sweep live per-op errors under /project1 ------------------------------
const PY = `
def go():
    import json as _json
    rows = []
    root = op('/project1')
    if root is None:
        print('ERRJSON []')
        return
    stack = [root]
    while stack:
        o = stack.pop()
        try:
            e = o.errors()
        except Exception:
            e = ''
        w = ''
        if not e:
            try:
                w = o.warnings()
            except Exception:
                w = ''
        if e:
            rows.append([o.path, 'E: ' + e.strip().splitlines()[0][:200]])
        elif w:
            rows.append([o.path, 'W: ' + w.strip().splitlines()[0][:200]])
        if o.isCOMP:
            try:
                stack.extend(o.children)
            except Exception:
                pass
    print('ERRJSON ' + _json.dumps(rows))
go()
`;

let out = "";
try {
  const resp = await fetch(`${BASE}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script: PY, undo_label: "error-check" }),
    signal: AbortSignal.timeout(10000),
  });
  if (!resp.ok) process.exit(0); // bridge hiccup — don't block the user
  const data = await resp.json();
  out = data.output || "";
} catch {
  process.exit(0);
}

const m = out.match(/ERRJSON (\[.*\])/s);
if (!m) process.exit(0); // sweep failed — don't block on our own breakage
let current = [];
try {
  current = JSON.parse(m[1]); // [[path, firstErrorLine], ...]
} catch {
  process.exit(0);
}
const currentMap = Object.fromEntries(current);

// --- baseline: load / bootstrap / prune ------------------------------------
let baseline = null;
try {
  baseline = JSON.parse(readFileSync(BASELINE, "utf8"));
} catch {
  baseline = null;
}
if (!baseline || typeof baseline.paths !== "object") {
  // First run: grandfather everything currently erroring, never block.
  writeFileSync(
    BASELINE,
    JSON.stringify({ _comment: "Accepted/pre-existing TD op errors (path -> first error line). check-errors.mjs blocks only on erroring ops NOT listed here. Delete an entry to re-arm it; entries auto-prune when the op stops erroring.", paths: currentMap }, null, 2) + "\n",
  );
  process.exit(0);
}

const accepted = baseline.paths;
const fresh = current.filter(([p]) => !(p in accepted));

// prune baseline entries whose ops no longer error (or no longer exist)
const prunedPaths = Object.fromEntries(
  Object.entries(accepted).filter(([p]) => p in currentMap),
);
if (Object.keys(prunedPaths).length !== Object.keys(accepted).length) {
  writeFileSync(
    BASELINE,
    JSON.stringify({ _comment: baseline._comment, paths: prunedPaths }, null, 2) + "\n",
  );
}

if (fresh.length === 0) process.exit(0); // nothing new — allow the stop silently

const shown = fresh.slice(0, 20).map(([p, e]) => `${p}  —  ${e}`);
const extra = fresh.length > shown.length ? `\n…and ${fresh.length - shown.length} more.` : "";

const reason =
  `TD error check: ${fresh.length} operator(s) have NEW live errors/warnings ` +
  `(op.errors()/op.warnings(), not the sticky get_errors log). Fix them, or if one is expected/user-owned, ` +
  `add its path to td-mcp-server/hooks/errors-baseline.json under "paths" ` +
  `(never auto-fix user-placed ops — surface instead):\n` +
  shown.join("\n") +
  extra;

process.stdout.write(JSON.stringify({ decision: "block", reason }));
process.exit(0);
