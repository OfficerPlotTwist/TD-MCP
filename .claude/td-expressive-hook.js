#!/usr/bin/env node
/**
 * Expressive-control convention reminder for the TD_MCP bridge.
 *
 * PreToolUse hook: before a *mutating* mcp__touchdesigner__ call, inject a one-time
 * reminder that any "Expressive" project control (one meant to react to the
 * image-analysis / tone pipeline crossing a threshold) must be driven by a parameter
 * REFERENCE to the single aggregating CHOP at /project1/null_expressive — never hardwired.
 *
 * Token economy: a context-injecting hook costs (reminder size x times it fires), so this
 * is lazy + debounced — it fires at most ONCE per session, on the first matching tool call.
 * Sessions that never touch TD pay zero tokens. Debounce is keyed by session_id via a
 * marker file; if session_id is absent it falls back to a ~30 min time window.
 *
 * Always prints {"continue":true} and exits 0 — fail-open, never blocks the agent. NOT async
 * (its stdout must be read synchronously so additionalContext is consumed before the tool runs).
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

const REARM_MS = parseInt(process.env.TD_EXPRESSIVE_REARM_MS || '1800000', 10); // 30 min fallback

// Only param-setting tools warrant the reminder; connect/disconnect/delete don't set values.
const RELEVANT = new Set([
  'mcp__touchdesigner__set_par_value',
  'mcp__touchdesigner__create_operator',
  'mcp__touchdesigner__execute_script',
]);

const REMINDER =
  "TD Expressive-control convention: if this edit creates or sets a project control that is " +
  "'Expressive' — any control meant to react to the image-analysis (tone) pipeline crossing a " +
  "threshold (see analyze_image_tone / td-mcp-server/tone-rules.json) — do NOT hardwire its value. " +
  "Drive it by parameter reference to a channel of the single project CHOP " +
  "op('/project1/null_expressive'), which aggregates every Expressive control " +
  "(e.g. t.par.X.expr = \"op('/project1/null_expressive')['<chan>']\", or bindExpr to it). " +
  "Name each channel descriptively after the PURPOSE of the operator-tree subsection it drives, " +
  "not the raw op/par name (e.g. a control on an op inside a feedback-bloom subnetwork -> channel " +
  "'feedbackbloom_threshold'), so channels are self-documenting. " +
  "Bias INCLUSIVE for now: when unsure, treat the control as Expressive and route it through " +
  "null_expressive — over-routing is cheap to undo, bypassing the CHOP is not.";

function pass() {
  process.stdout.write(JSON.stringify({ continue: true }));
  process.exit(0);
}

function remind() {
  process.stdout.write(JSON.stringify({
    continue: true,
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: REMINDER,
    },
  }));
  process.exit(0);
}

// Returns true if the reminder should fire now, and arms the marker so it won't fire again.
function shouldFire(sessionId) {
  const safe = String(sessionId || '').replace(/[^A-Za-z0-9_-]/g, '') || 'nosession';
  const marker = path.join(os.tmpdir(), 'td-expressive-' + safe + '.marker');
  try {
    if (sessionId) {
      if (fs.existsSync(marker)) return false;            // already reminded this session
    } else {
      // No session id: fall back to a time window so it re-arms but never floods.
      const last = (() => { try { return parseInt(fs.readFileSync(marker, 'utf8'), 10) || 0; } catch { return 0; } })();
      if (Date.now() - last < REARM_MS) return false;
    }
    fs.writeFileSync(marker, String(Date.now()));
  } catch {
    // Can't read/write the marker — fire once rather than risk never reminding.
  }
  return true;
}

async function main() {
  let raw = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) raw += chunk;

  let input = {};
  try { input = JSON.parse(raw.replace(/^﻿/, '')) || {}; } catch { return pass(); }

  if (!RELEVANT.has(input.tool_name)) return pass();      // non param-setting → skip
  if (!shouldFire(input.session_id)) return pass();       // already reminded → skip
  remind();
}

main().catch(pass);
