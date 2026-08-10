#!/usr/bin/env node
/**
 * check-wires.mjs — Stop hook: validate left→right wire flow among PINNED ops.
 *
 * SINGLE SOURCE OF TRUTH: touchdesigner/LAYOUT.md + touchdesigner/layout.json.
 * Only wires whose BOTH endpoints are pinned in layout.json are checked — those
 * positions are sanctioned, so a violation means layout.json itself encodes a
 * backward wire and must be fixed THERE. Unpinned (user-placed) ops are user
 * territory: their wire direction is advisory only and never blocks (policy
 * rule 1/4 in LAYOUT.md).
 *
 * Safeguards:
 *   - no-op silently if the TD bridge is unreachable (TD not running)
 *   - guard against infinite loops via stop_hook_active
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
let spec = null;
try {
  spec = JSON.parse(readFileSync(join(projectDir, "touchdesigner", "layout.json"), "utf8"));
} catch {
  process.exit(0); // no layout spec — nothing sanctioned to check
}
const pinned = {};
for (const [path, entry] of Object.entries(spec)) {
  if (path.startsWith("_") || !entry || !entry.ops) continue;
  pinned[path] = Object.keys(entry.ops);
}
if (Object.keys(pinned).length === 0) process.exit(0);

// --- health check: silent no-op if TD isn't up -----------------------------
try {
  const h = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(2000) });
  if (!h.ok) process.exit(0);
} catch {
  process.exit(0);
}

// --- scan pinned wires for backward flow ------------------------------------
const PY = `
def go():
    import json as _json
    pinned = _json.loads(${JSON.stringify(JSON.stringify(pinned))})
    viol = []
    for path in pinned:
        comp = op(path)
        if comp is None:
            continue
        names = set(pinned[path])
        for nm in names:
            ch = comp.op(nm)
            if ch is None:
                continue
            for ic in ch.inputConnectors:
                for cn in ic.connections:
                    src = cn.owner
                    if src.name in names and src.parent() == comp and src.nodeX >= ch.nodeX:
                        viol.append(src.path + '  ->  ' + ch.path)
    for v in viol:
        print(v)
    print('VIOLCOUNT ' + str(len(viol)))
go()
`;

let out = "";
try {
  const resp = await fetch(`${BASE}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script: PY, undo_label: "wire-check" }),
    signal: AbortSignal.timeout(8000),
  });
  if (!resp.ok) process.exit(0); // bridge hiccup — don't block the user
  const data = await resp.json();
  out = data.output || "";
} catch {
  process.exit(0);
}

const m = out.match(/VIOLCOUNT (\d+)/);
const count = m ? parseInt(m[1], 10) : 0;
if (count === 0) process.exit(0); // clean — allow the stop silently

const lines = out
  .split("\n")
  .map((l) => l.trim())
  .filter((l) => l && !l.startsWith("VIOLCOUNT"));
const shown = lines.slice(0, 30);
const extra = count > shown.length ? `\n…and ${count - shown.length} more.` : "";

const reason =
  `TD layout: ${count} PINNED wire(s) run right→left. Layout policy: ` +
  `touchdesigner/LAYOUT.md (single source of truth). These ops are pinned in ` +
  `touchdesigner/layout.json, so fix the positions THERE (then the reorganize ` +
  `hook applies them) — do NOT hand-move nodes, and NEVER move unpinned ` +
  `user-placed ops:\n` +
  shown.join("\n") +
  extra;

process.stdout.write(JSON.stringify({ decision: "block", reason }));
process.exit(0);
