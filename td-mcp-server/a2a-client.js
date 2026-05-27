/**
 * TD A2A CLI Orchestrator
 * =======================
 * Natural-language CLI that uses Claude to dispatch structured skill calls
 * to the running TD A2A server, then returns the result.
 *
 * Usage:
 *   node a2a-client.js "list operators in /project1"
 *   node a2a-client.js --sse "create a noise TOP in /project1"
 *
 * Env:
 *   ANTHROPIC_API_KEY  — required
 *   A2A_URL            — TD agent URL (default: http://localhost:3100)
 *   A2A_MODEL          — override Claude model for dispatch
 */

import Anthropic from "@anthropic-ai/sdk";
import { randomUUID } from "crypto";
import EventSource from "eventsource";

const A2A_URL = process.env.A2A_URL || "http://localhost:3100";
const MODEL   = process.env.A2A_MODEL || "claude-opus-4-7";

// ──────────────────────────────────────────────────────────────────────
// SKILLS REFERENCE  (stable — cached across calls)
// ──────────────────────────────────────────────────────────────────────

const SKILLS_REF = `
SKILL ID              REQUIRED PARAMS
execute_script        script:str, undo_label?:str
validate_script       script:str
get_errors            (none)
create_operator       parent_path:str, op_type:str, name?:str
delete_operator       path:str
connect_operators     source:str, target:str, source_index?:int, target_index?:int
disconnect_operators  path:str, connector_index:int, is_input?:bool
get_operator_info     path:str
list_operators        path:str
get_par_value         path:str, par_name:str
set_par_value         path:str, par_name:str, value:str
analyze_image_tone    rows_chop:str, cols_chop:str
set_tone_rule         name:str, description:str, skill:str, conditions:[{channel,stat,min?,max?}], priority?:int
list_tone_rules       (none)
take_screenshot       op_path?:str, save_dir?:str
save_checkpoint       name:str, op_path:str, description?:str
restore_checkpoint    name:str
list_checkpoints      (none)
delete_checkpoint     name:str

operator paths use full TD paths like /project1/myOp
op_type examples: noise, constant, blur, baseCOMP, moviefilein, moviefileout
channel for tone rules: r|g|b|a|luminance  stat: mean|min|max
`.trim();

const SYSTEM_PROMPT =
  `You dispatch commands to a live TouchDesigner session via an A2A agent.\n` +
  `Given the user request, respond with ONLY valid JSON: {"skill":"<id>","params":{...}}\n` +
  `Use exactly the skill IDs and param names listed below. Omit optional params unless needed.\n\n` +
  SKILLS_REF;

// ──────────────────────────────────────────────────────────────────────
// CLAUDE DISPATCH  (uses prompt caching on the stable system prompt)
// ──────────────────────────────────────────────────────────────────────

async function dispatch(client, userPrompt) {
  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 512,
    system: [
      {
        type: "text",
        text: SYSTEM_PROMPT,
        cache_control: { type: "ephemeral" }, // stable — cache it
      },
    ],
    messages: [{ role: "user", content: userPrompt }],
  });

  const raw = response.content.find((b) => b.type === "text")?.text ?? "";
  try {
    // Strip any markdown code fences if the model wraps the JSON
    const json = raw.replace(/^```[a-z]*\n?/i, "").replace(/\n?```$/i, "").trim();
    return JSON.parse(json);
  } catch {
    throw new Error(`Claude returned unparseable dispatch:\n${raw}`);
  }
}

// ──────────────────────────────────────────────────────────────────────
// A2A HELPERS
// ──────────────────────────────────────────────────────────────────────

function buildRpc(method, params) {
  return JSON.stringify({ jsonrpc: "2.0", id: 1, method, params });
}

function taskMessage(skill, params) {
  return {
    message: {
      role: "user",
      parts: [{ type: "application/json", data: { skill, params } }],
    },
  };
}

async function rpc(method, params) {
  const res = await fetch(A2A_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: buildRpc(method, params),
  });
  if (!res.ok) throw new Error(`A2A HTTP ${res.status}: ${await res.text()}`);
  const { result, error } = await res.json();
  if (error) throw new Error(`A2A RPC error: ${JSON.stringify(error)}`);
  return result;
}

// ──────────────────────────────────────────────────────────────────────
// MODE 1 — POLL  (fire-and-forget + poll until done)
// ──────────────────────────────────────────────────────────────────────

async function sendAndPoll(skill, params) {
  const taskId = randomUUID();
  let task = await rpc("tasks/send", { id: taskId, ...taskMessage(skill, params) });

  const POLL_INTERVAL_MS = 250;
  const MAX_WAIT_MS = 30_000;
  const deadline = Date.now() + MAX_WAIT_MS;

  while (["submitted", "working"].includes(task.status?.state)) {
    if (Date.now() > deadline) throw new Error("Timed out waiting for task");
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    task = await rpc("tasks/get", { id: taskId });
  }

  if (task.status?.state === "failed") {
    const msg = task.status?.message?.parts?.[0]?.text ?? "unknown error";
    throw new Error(`Task failed: ${msg}`);
  }

  return task.artifacts?.[0]?.data ?? task;
}

// ──────────────────────────────────────────────────────────────────────
// MODE 2 — SSE  (tasks/sendSubscribe — live event stream)
// ──────────────────────────────────────────────────────────────────────

function sendAndSubscribe(skill, params) {
  return new Promise((resolve, reject) => {
    const taskId = randomUUID();
    const sseUrl = A2A_URL; // POST to same endpoint; EventSource only does GET

    // We need to POST to open the SSE stream. The A2A server handles
    // tasks/sendSubscribe as a POST that returns text/event-stream.
    // Node's built-in EventSource only handles GET, so we use a raw fetch
    // and manually parse the SSE stream.

    fetch(sseUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: buildRpc("tasks/sendSubscribe", { id: taskId, ...taskMessage(skill, params) }),
    })
      .then(async (res) => {
        if (!res.ok) {
          reject(new Error(`SSE connect failed: HTTP ${res.status}`));
          return;
        }

        let lastTask = null;
        let buffer = "";

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        const pump = async () => {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? ""; // keep incomplete last line

            for (const line of lines) {
              if (!line.startsWith("data:")) continue;
              const raw = line.slice(5).trim();
              if (!raw) continue;
              try {
                const task = JSON.parse(raw);
                lastTask = task;
                const state = task.status?.state;
                process.stderr.write(`  [${state}]\n`);
                if (state === "completed" || state === "failed" || state === "canceled") {
                  reader.cancel();
                  if (state === "failed") {
                    const msg = task.status?.message?.parts?.[0]?.text ?? "unknown";
                    reject(new Error(`Task failed: ${msg}`));
                  } else {
                    resolve(task.artifacts?.[0]?.data ?? task);
                  }
                  return;
                }
              } catch {
                // ignore non-JSON SSE lines (e.g. event: type lines)
              }
            }
          }
          // Stream ended without a terminal state — return last known task
          resolve(lastTask?.artifacts?.[0]?.data ?? lastTask);
        };

        pump().catch(reject);
      })
      .catch(reject);
  });
}

// ──────────────────────────────────────────────────────────────────────
// MAIN
// ──────────────────────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);
  const useSSE = args.includes("--sse");
  const words = args.filter((a) => !a.startsWith("--"));
  const userPrompt = words.join(" ").trim();

  if (!userPrompt) {
    console.error(
      "Usage: node a2a-client.js [--sse] \"<natural language prompt>\"\n" +
      "\nExamples:\n" +
      "  node a2a-client.js \"list operators in /project1\"\n" +
      "  node a2a-client.js \"create a noise TOP named my_noise in /project1\"\n" +
      "  node a2a-client.js --sse \"take a screenshot of /project1/out1\"\n"
    );
    process.exit(1);
  }

  // Check A2A server health
  try {
    const health = await fetch(`${A2A_URL}/health`);
    if (!health.ok) throw new Error(`health check HTTP ${health.status}`);
    const { td_connected } = await health.json();
    if (!td_connected) process.stderr.write("[warn] TD is not connected to the A2A server\n");
  } catch (err) {
    console.error(`[error] A2A server not reachable at ${A2A_URL}: ${err.message}`);
    process.exit(1);
  }

  const client = new Anthropic();

  // Step 1: Claude picks the skill
  process.stderr.write(`Dispatching: "${userPrompt}"\n`);
  const { skill, params } = await dispatch(client, userPrompt);
  process.stderr.write(`→ skill=${skill} params=${JSON.stringify(params)}\n`);

  // Step 2: Call the A2A agent
  const result = useSSE
    ? await sendAndSubscribe(skill, params)
    : await sendAndPoll(skill, params);

  console.log(JSON.stringify(result, null, 2));
}

main().catch((err) => {
  console.error("[fatal]", err.message);
  process.exit(1);
});
