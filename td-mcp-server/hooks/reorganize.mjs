#!/usr/bin/env node
/**
 * reorganize.mjs — Stop hook: apply the PINNED layout from touchdesigner/layout.json.
 *
 * SINGLE SOURCE OF TRUTH: touchdesigner/LAYOUT.md + touchdesigner/layout.json.
 * This hook applies the pinned positions ONLY — ops not listed in layout.json are
 * user territory and are never touched (policy rule 1: never move user-placed
 * operators). The old depth-based auto-layout is gone: it restacked the whole
 * project every Stop (including user-placed ops and the bridge COMP) and mis-read
 * COMP-fed wires as sourceless, creating the very backward wires check-wires.mjs
 * then blocked on.
 *
 * Safeguards:
 *   - silent no-op if the TD bridge is unreachable (TD not running)
 *   - guard against infinite loops via stop_hook_active
 *   - only ops named in layout.json are ever repositioned
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const HOST = process.env.TD_HOST || "127.0.0.1";
const PORT = process.env.TD_PORT || "9980";
const BASE = `http://${HOST}:${PORT}`;

// --- read hook stdin (JSON) for the loop guard -----------------------------
let raw = "";
try {
  for await (const chunk of process.stdin) raw += chunk;
} catch {}
let hookInput = {};
try {
  hookInput = JSON.parse(raw || "{}");
} catch {}
if (hookInput.stop_hook_active) process.exit(0); // already re-fired once — don't loop

// --- load the single source of truth ---------------------------------------
const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
let specText = "";
try {
  specText = readFileSync(join(projectDir, "touchdesigner", "layout.json"), "utf8");
  JSON.parse(specText); // validate before shipping to TD
} catch {
  process.exit(0); // no/invalid layout spec — nothing to apply
}

// --- health check: silent no-op if TD isn't up -----------------------------
try {
  const h = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(2000) });
  if (!h.ok) process.exit(0);
} catch {
  process.exit(0);
}

// --- apply pinned positions -------------------------------------------------
// Wrapped in a function: TD's executeScript runs with split globals/locals, so
// names used inside comprehensions/nested funcs must live in a real function scope.
const PY = `
def go():
    import json as _json
    spec = _json.loads(${JSON.stringify(specText)})
    applied = 0
    for path in spec:
        if path.startswith('_'):
            continue
        comp = op(path)
        if comp is None:
            continue
        entry = spec[path]
        for nm, xy in entry.get('ops', {}).items():
            o = comp.op(nm)
            if o is None:
                continue
            if o.nodeX != xy[0] or o.nodeY != xy[1]:
                o.nodeX = xy[0]; o.nodeY = xy[1]; applied += 1
        for nm, box in entry.get('annotates', {}).items():
            a = comp.op(nm)
            if a is None:
                continue
            a.nodeX = box[0]; a.nodeY = box[1]
            a.nodeWidth = box[2]; a.nodeHeight = box[3]
        if entry.get('parkDocked'):
            for o in comp.children:
                if o.dock is not None and o.dock.parent() == comp:
                    o.nodeX = o.dock.nodeX; o.nodeY = o.dock.nodeY - 140
    print('APPLIED ' + str(applied))
go()
`;

try {
  await fetch(`${BASE}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script: PY, undo_label: "apply-pinned-layout" }),
    signal: AbortSignal.timeout(10000),
  });
} catch {
  // bridge hiccup — never block the user
}
process.exit(0);
