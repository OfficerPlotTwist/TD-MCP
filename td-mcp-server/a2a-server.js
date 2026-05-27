/**
 * TouchDesigner A2A Specialty Agent
 * ==================================
 * Exposes the same TD capabilities as the MCP server but over the
 * Agent-to-Agent (A2A) HTTP protocol so any A2A-compatible orchestrator
 * can call it — not just Claude Code's MCP host.
 *
 * Transport: HTTP (default port 3100)
 * Discovery: GET /.well-known/agent.json
 * Protocol:  JSON-RPC 2.0 via POST /
 *
 * Skill dispatch: task message parts carry { skill, params } JSON blobs.
 * This is "structured dispatch" — no LLM inside the agent needed.
 * Each skill maps 1:1 to the original MCP tool implementations.
 *
 * All bridge/checkpoint/validator modules are untouched from the MCP version.
 */

import http from "http";
import { randomUUID } from "crypto";
import { readFileSync, writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

import * as bridge from "./td-bridge.js";
import * as api from "./api-validator.js";
import * as ckpt from "./checkpoints.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RULES_PATH = join(__dirname, "tone-rules.json");
const PORT = parseInt(process.env.A2A_PORT || "3100", 10);
const AGENT_URL = process.env.A2A_URL || `http://localhost:${PORT}`;

// ──────────────────────────────────────────────────────────────────────
// AGENT CARD  (returned at /.well-known/agent.json)
// ──────────────────────────────────────────────────────────────────────

const AGENT_CARD = {
  name: "TouchDesigner Agent",
  description:
    "Controls a live TouchDesigner session — create/connect operators, " +
    "execute Python scripts, analyze visuals, manage checkpoints, and more.",
  url: AGENT_URL,
  version: "1.0.0",
  capabilities: {
    streaming: true,       // supports tasks/sendSubscribe via SSE
    pushNotifications: false,
  },
  // Each skill maps to one structured call; params schema mirrors the MCP tool.
  skills: [
    { id: "execute_script",     name: "Execute Script",       description: "Run a Python script inside TouchDesigner" },
    { id: "validate_script",    name: "Validate Script",      description: "Check a Python script against the TD API without running it" },
    { id: "get_errors",         name: "Get Errors",           description: "Read the current Error DAT from TouchDesigner" },
    { id: "create_operator",    name: "Create Operator",      description: "Create a new operator in a TD network" },
    { id: "delete_operator",    name: "Delete Operator",      description: "Delete an operator from a TD network" },
    { id: "connect_operators",  name: "Connect Operators",    description: "Wire one operator's output to another's input" },
    { id: "disconnect_operators", name: "Disconnect Operators", description: "Remove a wire from an operator connector" },
    { id: "get_operator_info",  name: "Get Operator Info",    description: "Inspect an operator's parameters and connections" },
    { id: "list_operators",     name: "List Operators",       description: "List all children of a network path" },
    { id: "get_par_value",      name: "Get Parameter",        description: "Read a parameter value from an operator" },
    { id: "set_par_value",      name: "Set Parameter",        description: "Write a parameter value on an operator" },
    { id: "analyze_image_tone", name: "Analyze Image Tone",   description: "Compute tone stats and match against configured rules" },
    { id: "set_tone_rule",      name: "Set Tone Rule",        description: "Add or update a tone rule" },
    { id: "list_tone_rules",    name: "List Tone Rules",      description: "List all configured tone rules" },
    { id: "take_screenshot",    name: "Take Screenshot",      description: "Capture a TOP operator output as a PNG image" },
    { id: "save_checkpoint",    name: "Save Checkpoint",      description: "Save a COMP as a named .tox checkpoint" },
    { id: "restore_checkpoint", name: "Restore Checkpoint",   description: "Restore a previously saved checkpoint" },
    { id: "list_checkpoints",   name: "List Checkpoints",     description: "List all saved checkpoints" },
    { id: "delete_checkpoint",  name: "Delete Checkpoint",    description: "Delete a checkpoint and its .tox file" },
  ],
};

// ──────────────────────────────────────────────────────────────────────
// TASK STORE  (in-memory; replace with Redis for multi-process setups)
// ──────────────────────────────────────────────────────────────────────

const tasks = new Map(); // taskId → TaskObject
const sseClients = new Map(); // taskId → res (SSE response stream)

function makeTask(id) {
  return {
    id,
    status: { state: "submitted", timestamp: new Date().toISOString() },
    artifacts: [],
  };
}

function updateTask(taskId, patch) {
  const task = tasks.get(taskId);
  if (!task) return;
  Object.assign(task, patch);
  task.status.timestamp = new Date().toISOString();
  // Push SSE update if a subscriber is waiting
  const client = sseClients.get(taskId);
  if (client) {
    const event = patch.status?.state === "completed" || patch.status?.state === "failed"
      ? "tasks/completed"
      : "tasks/updated";
    client.write(`event: ${event}\ndata: ${JSON.stringify(task)}\n\n`);
    if (["completed", "failed", "canceled"].includes(task.status.state)) {
      client.end();
      sseClients.delete(taskId);
    }
  }
}

// ──────────────────────────────────────────────────────────────────────
// SKILL DISPATCHER  (structured — no embedded LLM needed)
// ──────────────────────────────────────────────────────────────────────

function loadRules() {
  return JSON.parse(readFileSync(RULES_PATH, "utf-8"));
}

function evalRule(rule, overall) {
  return rule.conditions.every((cond) => {
    const stat = overall[cond.channel]?.[cond.stat];
    if (stat === undefined) return false;
    if (cond.min !== undefined && stat < cond.min) return false;
    if (cond.max !== undefined && stat > cond.max) return false;
    return true;
  });
}

async function dispatchSkill(skill, params) {
  switch (skill) {
    case "execute_script": {
      const validation = api.validateScript(params.script);
      const result = await bridge.executeScript(params.script, params.undo_label || "A2A Script");
      return { output: result.output, errors: result.errors, validation_warnings: validation.warnings };
    }
    case "validate_script": {
      return api.validateScript(params.script);
    }
    case "get_errors": {
      return bridge.getErrors();
    }
    case "create_operator": {
      let script = `parent = op('${params.parent_path}')\n`;
      script += `new_op = parent.create(${JSON.stringify(params.op_type)}`;
      if (params.name) script += `, ${JSON.stringify(params.name)}`;
      script += `)\nprint(new_op.path)\n`;
      return bridge.executeScript(script, `Create ${params.op_type}`);
    }
    case "delete_operator": {
      const script = `op('${params.path}').destroy()\nprint('deleted ${params.path}')\n`;
      return bridge.executeScript(script, `Delete ${params.path}`);
    }
    case "connect_operators": {
      const si = params.source_index ?? 0;
      const ti = params.target_index ?? 0;
      const script = `op('${params.source}').outputConnectors[${si}].connect(op('${params.target}').inputConnectors[${ti}])\nprint('connected')\n`;
      return bridge.executeScript(script, `Connect ${params.source} → ${params.target}`);
    }
    case "disconnect_operators": {
      const dir = params.is_input !== false ? "inputConnectors" : "outputConnectors";
      const script = `op('${params.path}').${dir}[${params.connector_index}].disconnect()\nprint('disconnected')\n`;
      return bridge.executeScript(script, `Disconnect ${params.path}`);
    }
    case "get_operator_info": {
      const script = `
import json
o = op('${params.path}')
info = {
    'path': o.path, 'name': o.name, 'type': o.OPType, 'family': o.family,
    'pars': {p.name: {'val': str(p.val), 'mode': str(p.mode)} for p in o.pars()},
    'inputs': [{'name': c.owner.name, 'path': c.owner.path} for c in o.inputConnectors if c.connections],
    'outputs': [{'name': c.owner.name, 'path': c.owner.path} for c in o.outputConnectors if c.connections],
    'num_children': len(o.children) if hasattr(o, 'children') else 0,
}
print(json.dumps(info, indent=2))`;
      return bridge.executeScript(script, "Get operator info");
    }
    case "list_operators": {
      const script = `
import json
parent = op('${params.path}')
children = [{'name': c.name, 'path': c.path, 'type': c.OPType, 'family': c.family} for c in parent.children]
print(json.dumps(children, indent=2))`;
      return bridge.executeScript(script, "List operators");
    }
    case "get_par_value": {
      const script = `print(op('${params.path}').par.${params.par_name}.val)\n`;
      return bridge.executeScript(script, "Get parameter");
    }
    case "set_par_value": {
      const script = `
try:
    op('${params.path}').par.${params.par_name}.val = ${params.value}
except:
    op('${params.path}').par.${params.par_name}.val = ${JSON.stringify(params.value)}
print(op('${params.path}').par.${params.par_name}.val)`;
      return bridge.executeScript(script, `Set ${params.par_name}`);
    }
    case "analyze_image_tone": {
      const stats = await bridge.getImageStats(params.rows_chop, params.cols_chop);
      if (stats.error) return stats;
      const { rules } = loadRules();
      const matched = rules
        .filter((r) => evalRule(r, stats.overall))
        .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
      const o = stats.overall;
      return {
        summary: {
          luminance_mean: o.luminance?.mean?.toFixed(4),
          r_mean: o.r?.mean?.toFixed(4),
          g_mean: o.g?.mean?.toFixed(4),
          b_mean: o.b?.mean?.toFixed(4),
        },
        matched_conditions: matched.map((r) => ({ name: r.name, description: r.description, skill: r.skill, priority: r.priority })),
        top_condition: matched[0] ?? null,
        recommendation: matched[0]
          ? `Apply skill: ${matched[0].skill} — ${matched[0].description}`
          : "No rules matched — image within normal range.",
        raw_stats: stats.overall,
      };
    }
    case "set_tone_rule": {
      const config = loadRules();
      const idx = config.rules.findIndex((r) => r.name === params.name);
      const rule = { name: params.name, description: params.description, skill: params.skill, priority: params.priority ?? 5, conditions: params.conditions };
      idx >= 0 ? (config.rules[idx] = rule) : config.rules.push(rule);
      writeFileSync(RULES_PATH, JSON.stringify(config, null, 2));
      return { ok: true, action: idx >= 0 ? "updated" : "added", rule };
    }
    case "list_tone_rules": {
      return loadRules().rules;
    }
    case "take_screenshot": {
      return bridge.takeScreenshot(params.op_path || "/project1/out1", params.save_dir);
    }
    case "save_checkpoint": {
      const safeName = params.name.replace(/[^a-zA-Z0-9_-]/g, "_");
      const toxPath = `${ckpt.CHECKPOINTS_DIR.replace(/\\/g, "/")}/${safeName}_${Date.now()}.tox`;
      const result = await bridge.executeScript(ckpt.buildSaveScript(params.op_path, toxPath), `Checkpoint: ${params.name}`);
      const errors = await bridge.getErrors();
      if (result.output?.startsWith("ERROR:") || result.errors?.length > 0) {
        return { ok: false, output: result.output, errors: result.errors, td_errors: errors.errors ?? [] };
      }
      return { ok: true, checkpoint: ckpt.addCheckpoint(params.name, params.op_path, toxPath, params.description ?? ""), td_errors: errors.errors ?? [] };
    }
    case "restore_checkpoint": {
      const entry = ckpt.getCheckpoint(params.name);
      if (!entry) return { ok: false, error: `No checkpoint named '${params.name}'` };
      const result = await bridge.executeScript(ckpt.buildRestoreScript(entry.op_path, entry.tox_path), `Restore: ${params.name}`);
      const errors = await bridge.getErrors();
      const ok = result.output?.startsWith("restored:") && !result.errors?.length;
      return { ok, restored_to: ok ? result.output.replace("restored:", "").trim() : null, errors: result.errors, td_errors: errors.errors ?? [], checkpoint: entry };
    }
    case "list_checkpoints": {
      const checkpoints = ckpt.listCheckpoints();
      return { count: checkpoints.length, checkpoints };
    }
    case "delete_checkpoint": {
      const removed = ckpt.removeCheckpoint(params.name);
      return removed ? { ok: true, deleted: removed } : { ok: false, error: `No checkpoint named '${params.name}'` };
    }
    default:
      throw new Error(`Unknown skill: ${skill}`);
  }
}

// ──────────────────────────────────────────────────────────────────────
// TASK RUNNER  (called async; updates task store + SSE subscribers)
// ──────────────────────────────────────────────────────────────────────

async function runTask(taskId, message) {
  updateTask(taskId, { status: { state: "working" } });

  // Extract the structured skill call from the message parts.
  // Expected part shape: { type: "application/json", data: { skill, params } }
  // Falls back to text parsing if the orchestrator sends natural-language parts.
  let skill, params;
  try {
    const jsonPart = message.parts?.find((p) => p.type === "application/json");
    if (jsonPart) {
      ({ skill, params } = jsonPart.data);
    } else {
      // Minimal text fallback: treat the text part as a JSON blob
      const textPart = message.parts?.find((p) => p.type === "text");
      ({ skill, params } = JSON.parse(textPart?.text ?? "{}"));
    }
    if (!skill) throw new Error("No skill specified in task message");
  } catch (err) {
    updateTask(taskId, {
      status: { state: "failed", message: { role: "agent", parts: [{ type: "text", text: `Bad task format: ${err.message}` }] } },
    });
    return;
  }

  try {
    const result = await dispatchSkill(skill, params ?? {});
    updateTask(taskId, {
      status: { state: "completed" },
      artifacts: [{ type: "application/json", data: result }],
    });
  } catch (err) {
    updateTask(taskId, {
      status: { state: "failed", message: { role: "agent", parts: [{ type: "text", text: err.message }] } },
    });
  }
}

// ──────────────────────────────────────────────────────────────────────
// HTTP SERVER
// ──────────────────────────────────────────────────────────────────────

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(payload);
}

function rpcOk(res, id, result) {
  sendJson(res, 200, { jsonrpc: "2.0", id, result });
}

function rpcErr(res, id, code, message) {
  sendJson(res, 200, { jsonrpc: "2.0", id, error: { code, message } });
}

const server = http.createServer(async (req, res) => {
  // ── Agent Card ──────────────────────────────────────────────────────
  if (req.method === "GET" && req.url === "/.well-known/agent.json") {
    sendJson(res, 200, AGENT_CARD);
    return;
  }

  // ── Health check ────────────────────────────────────────────────────
  if (req.method === "GET" && req.url === "/health") {
    const tdUp = await bridge.isConnected();
    sendJson(res, 200, { ok: true, td_connected: tdUp });
    return;
  }

  // ── A2A JSON-RPC endpoint ───────────────────────────────────────────
  if (req.method !== "POST" || req.url !== "/") {
    res.writeHead(404);
    res.end("Not found");
    return;
  }

  let body = "";
  req.on("data", (chunk) => (body += chunk));
  req.on("end", async () => {
    let rpc;
    try {
      rpc = JSON.parse(body);
    } catch {
      rpcErr(res, null, -32700, "Parse error");
      return;
    }

    const { method, params, id } = rpc;

    // tasks/send — fire-and-forget, returns task immediately
    if (method === "tasks/send") {
      const taskId = params?.id ?? randomUUID();
      const task = makeTask(taskId);
      tasks.set(taskId, task);
      runTask(taskId, params?.message).catch(console.error);
      rpcOk(res, id, task);
      return;
    }

    // tasks/sendSubscribe — returns SSE stream, updates pushed as task runs
    if (method === "tasks/sendSubscribe") {
      const taskId = params?.id ?? randomUUID();
      const task = makeTask(taskId);
      tasks.set(taskId, task);

      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });
      res.write(`event: tasks/submitted\ndata: ${JSON.stringify(task)}\n\n`);
      sseClients.set(taskId, res);

      req.on("close", () => sseClients.delete(taskId));
      runTask(taskId, params?.message).catch(console.error);
      return;
    }

    // tasks/get — poll task status
    if (method === "tasks/get") {
      const task = tasks.get(params?.id);
      if (!task) { rpcErr(res, id, -32001, "Task not found"); return; }
      rpcOk(res, id, task);
      return;
    }

    // tasks/cancel
    if (method === "tasks/cancel") {
      const task = tasks.get(params?.id);
      if (!task) { rpcErr(res, id, -32001, "Task not found"); return; }
      updateTask(params.id, { status: { state: "canceled" } });
      rpcOk(res, id, tasks.get(params.id));
      return;
    }

    rpcErr(res, id, -32601, `Method not found: ${method}`);
  });
});

server.listen(PORT, () => {
  console.error(`[TD-A2A] Agent running at ${AGENT_URL}`);
  console.error(`[TD-A2A] Agent Card: ${AGENT_URL}/.well-known/agent.json`);
  console.error(`[TD-A2A] TD bridge:  http://${process.env.TD_HOST || "localhost"}:${process.env.TD_PORT || 9980}`);
});
