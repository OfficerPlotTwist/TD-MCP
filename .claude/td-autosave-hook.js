#!/usr/bin/env node
/**
 * Auto-save the live TouchDesigner project via the TD_MCP WebServer DAT (:9980).
 *
 * The TD MCP bridge mutates an UNSAVED session — edits are lost on crash until
 * project.save(). This hook persists frequently so a crash costs seconds, not work.
 *
 * Modes:
 *   (default) PostToolUse — reads hook JSON on stdin; if the tool was a *mutating*
 *             mcp__touchdesigner__ call AND the debounce window elapsed, POSTs
 *             project.save(). Debounced to avoid Backup/ spam + per-call latency.
 *   --force   Stop — saves unconditionally (end-of-turn flush), ignores debounce.
 *
 * Always prints {"continue":true} and exits 0 — never blocks the agent, even if
 * TD is down. Uses raw HTTP (not the MCP tool) so it can't re-trigger PostToolUse.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

const TD_HOST = process.env.TD_HOST || 'localhost';
const TD_PORT = process.env.TD_PORT || '9980';
const DEBOUNCE_MS = parseInt(process.env.TD_AUTOSAVE_DEBOUNCE_MS || '20000', 10);
const STAMP = path.join(os.tmpdir(), 'td-mcp-autosave.stamp');

// Only these mutate the project; read-only calls never trigger a save.
const MUTATING = new Set([
  'mcp__touchdesigner__execute_script',
  'mcp__touchdesigner__set_par_value',
  'mcp__touchdesigner__create_operator',
  'mcp__touchdesigner__connect_operators',
  'mcp__touchdesigner__disconnect_operators',
  'mcp__touchdesigner__delete_operator',
]);

function pass() {
  process.stdout.write(JSON.stringify({ continue: true }));
  process.exit(0);
}

function save() {
  const body = JSON.stringify({ script: 'project.save()', undo_label: 'auto-save (hook)' });
  const req = http.request(
    {
      host: TD_HOST, port: TD_PORT, path: '/execute', method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    },
    (res) => {
      res.on('data', () => {});
      res.on('end', () => { try { fs.writeFileSync(STAMP, String(Date.now())); } catch {} pass(); });
    }
  );
  req.on('error', pass);                               // TD down → pass through
  req.setTimeout(4000, () => { req.destroy(); pass(); });
  req.write(body);
  req.end();
}

function lastSave() {
  try { return parseInt(fs.readFileSync(STAMP, 'utf8'), 10) || 0; } catch { return 0; }
}

async function main() {
  if (process.argv.includes('--force')) return save();  // Stop: unconditional flush

  let raw = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) raw += chunk;

  let toolName = '';
  try { toolName = JSON.parse(raw.replace(/^﻿/, ''))?.tool_name || ''; } catch { return pass(); }

  if (!MUTATING.has(toolName)) return pass();           // read-only → skip
  if (Date.now() - lastSave() < DEBOUNCE_MS) return pass(); // within window → skip
  save();
}

main().catch(pass);
