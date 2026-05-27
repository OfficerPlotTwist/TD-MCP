/**
 * TouchDesigner MCP Server
 * ========================
 * Bridges AI agents (Antigravity/Gemini) to TouchDesigner via WebServer DAT.
 *
 * Transport: stdio (spawned by the AI host)
 * Bridge:    HTTP → TD WebServer DAT (localhost:9980)
 *
 * Tools:  execute_script, validate_script, get_errors,
 *         create_operator, delete_operator, connect_operators, disconnect_operators,
 *         get_operator_info, list_operators, get_par_value, set_par_value,
 *         analyze_image_tone, set_tone_rule, list_tone_rules, take_screenshot,
 *         save_checkpoint, restore_checkpoint, list_checkpoints, delete_checkpoint
 *
 * Resources: td://api/classes, td://api/class/{name}
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFileSync, writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

import * as bridge from "./td-bridge.js";
import * as api from "./api-validator.js";
import * as ckpt from "./checkpoints.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RULES_PATH = join(__dirname, "tone-rules.json");

function loadRules() {
  return JSON.parse(readFileSync(RULES_PATH, "utf-8"));
}

/** Evaluate a single rule's conditions against overall stats. Returns true if all conditions pass. */
function evalRule(rule, overall) {
  return rule.conditions.every((cond) => {
    const stat = overall[cond.channel]?.[cond.stat];
    if (stat === undefined) return false;
    if (cond.min !== undefined && stat < cond.min) return false;
    if (cond.max !== undefined && stat > cond.max) return false;
    return true;
  });
}

const server = new McpServer(
  {
    name: "touchdesigner",
    version: "1.0.0",
  },
  {
    instructions: [
      "This server bridges to a live, unsaved TouchDesigner session. Edits made via execute_script / set_par_value / create_operator mutate the running project immediately but are NOT persisted to the .toe on disk until the project is saved.",
      "",
      "Project save discipline (follow this around every editing task):",
      "1. BEFORE you make the first mutating edit of a task, save the open project so there is a known-good restore point on disk:",
      "     execute_script(\"project.save()\")",
      "   (For a non-destructive snapshot, use project.saveBackup() which writes a timestamped copy without overwriting the live .toe.)",
      "2. Make the scoped changes.",
      "3. VERIFY the changes are complete and correct (get_operator_info / get_par_value / get_errors / take_screenshot as appropriate).",
      "4. ONLY AFTER verification passes, save again to persist the finished work:",
      "     execute_script(\"project.save()\")",
      "   If verification fails, do NOT save over the good state — fix or revert first.",
      "",
      "For bulk-destructive operations (mass delete, containerize, mass param rewrite), additionally use save_checkpoint on the parent COMP before the destructive step, and never combine bulk destroy with force-cook in one script (it can freeze TD).",
    ].join("\n"),
  }
);

// ──────────────────────────────────────────────────────────────────────
// TOOLS
// ──────────────────────────────────────────────────────────────────────

// 1. execute_script
server.tool(
  "execute_script",
  "Execute a Python script inside TouchDesigner. The script is wrapped in an undo block so the user can Ctrl+Z. Returns stdout output and any errors from the Error DAT.",
  {
    script: z.string().describe("Python script to execute in TouchDesigner"),
    undo_label: z
      .string()
      .optional()
      .describe("Label for the undo block (default: MCP Script)"),
  },
  async ({ script, undo_label }) => {
    // Pre-validate
    const validation = api.validateScript(script);
    const result = await bridge.executeScript(script, undo_label || "MCP Script");
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            {
              output: result.output,
              errors: result.errors,
              validation_warnings: validation.warnings,
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// 2. validate_script
server.tool(
  "validate_script",
  "Validate a Python script against the TouchDesigner API database without executing it. Checks for unnecessary imports and invalid API usage.",
  {
    script: z.string().describe("Python script to validate"),
  },
  async ({ script }) => {
    const result = api.validateScript(script);
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  }
);

// 3. get_errors
server.tool(
  "get_errors",
  "Read the current Error DAT table from TouchDesigner. Returns all recent Python errors.",
  {},
  async () => {
    const result = await bridge.getErrors();
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 4. create_operator
server.tool(
  "create_operator",
  "Create a new operator in TouchDesigner.",
  {
    parent_path: z
      .string()
      .describe("Path to the parent COMP (e.g. '/project1')"),
    op_type: z
      .string()
      .describe(
        "Operator type to create (e.g. 'chopexec', 'constant', 'noise', 'baseCOMP', 'text', 'geo')"
      ),
    name: z
      .string()
      .optional()
      .describe("Optional name for the new operator"),
  },
  async ({ parent_path, op_type, name }) => {
    let script = `parent = op('${parent_path}')\n`;
    script += `new_op = parent.create(${JSON.stringify(op_type)}`;
    if (name) script += `, ${JSON.stringify(name)}`;
    script += `)\n`;
    script += `print(new_op.path)\n`;
    const result = await bridge.executeScript(script, `Create ${op_type}`);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 5. delete_operator
server.tool(
  "delete_operator",
  "Delete an operator from TouchDesigner.",
  {
    path: z.string().describe("Path to the operator to delete"),
  },
  async ({ path }) => {
    const script = `op('${path}').destroy()\nprint('deleted ${path}')\n`;
    const result = await bridge.executeScript(script, `Delete ${path}`);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 6. connect_operators
server.tool(
  "connect_operators",
  "Wire the output of one operator to the input of another. Works for both regular operator connections and COMP (parent-child) connections.",
  {
    source: z.string().describe("Path to the source operator"),
    target: z.string().describe("Path to the target operator"),
    source_index: z
      .number()
      .optional()
      .describe("Output connector index on source (default: 0)"),
    target_index: z
      .number()
      .optional()
      .describe("Input connector index on target (default: 0)"),
  },
  async ({ source, target, source_index, target_index }) => {
    const si = source_index ?? 0;
    const ti = target_index ?? 0;
    const script = `op('${source}').outputConnectors[${si}].connect(op('${target}').inputConnectors[${ti}])\nprint('connected ${source}[${si}] -> ${target}[${ti}]')\n`;
    const result = await bridge.executeScript(
      script,
      `Connect ${source} → ${target}`
    );
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 7. disconnect_operators
server.tool(
  "disconnect_operators",
  "Disconnect a wire from an operator's connector.",
  {
    path: z.string().describe("Path to the operator"),
    connector_index: z
      .number()
      .describe("Index of the connector to disconnect"),
    is_input: z
      .boolean()
      .optional()
      .describe("True for input connector, false for output (default: true)"),
  },
  async ({ path, connector_index, is_input }) => {
    const dir = is_input !== false ? "inputConnectors" : "outputConnectors";
    const script = `op('${path}').${dir}[${connector_index}].disconnect()\nprint('disconnected ${path} ${dir}[${connector_index}]')\n`;
    const result = await bridge.executeScript(script, `Disconnect ${path}`);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 8. get_operator_info
server.tool(
  "get_operator_info",
  "Get detailed info about an operator: name, type, parameters, connections, and children.",
  {
    path: z.string().describe("Path to the operator"),
  },
  async ({ path }) => {
    const script = `
import json
o = op('${path}')
info = {
    'path': o.path,
    'name': o.name,
    'type': o.OPType,
    'family': o.family,
    'pars': {p.name: {'val': str(p.val), 'mode': str(p.mode)} for p in o.pars()},
    'inputs': [{'name': c.owner.name, 'path': c.owner.path} for c in o.inputConnectors if c.connections],
    'outputs': [{'name': c.owner.name, 'path': c.owner.path} for c in o.outputConnectors if c.connections],
    'num_children': len(o.children) if hasattr(o, 'children') else 0,
}
print(json.dumps(info, indent=2))
`;
    const result = await bridge.executeScript(script, "Get operator info");
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 9. list_operators
server.tool(
  "list_operators",
  "List all child operators in a network path.",
  {
    path: z.string().describe("Path to the parent COMP (e.g. '/project1')"),
  },
  async ({ path }) => {
    const script = `
import json
parent = op('${path}')
children = [{'name': c.name, 'path': c.path, 'type': c.OPType, 'family': c.family} for c in parent.children]
print(json.dumps(children, indent=2))
`;
    const result = await bridge.executeScript(script, "List operators");
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 10. get_par_value
server.tool(
  "get_par_value",
  "Get the current value of a parameter on an operator.",
  {
    path: z.string().describe("Path to the operator"),
    par_name: z.string().describe("Parameter name"),
  },
  async ({ path, par_name }) => {
    const script = `print(op('${path}').par.${par_name}.val)\n`;
    const result = await bridge.executeScript(script, "Get parameter");
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 11. set_par_value
server.tool(
  "set_par_value",
  "Set a parameter value on an operator.",
  {
    path: z.string().describe("Path to the operator"),
    par_name: z.string().describe("Parameter name"),
    value: z.string().describe("New value for the parameter (as a string)"),
  },
  async ({ path, par_name, value }) => {
    // Try to set as number if possible, otherwise string
    const script = `
try:
    op('${path}').par.${par_name}.val = ${value}
except:
    op('${path}').par.${par_name}.val = ${JSON.stringify(value)}
print(op('${path}').par.${par_name}.val)
`;
    const result = await bridge.executeScript(
      script,
      `Set ${par_name} on ${path}`
    );
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  }
);

// 12. analyze_image_tone
server.tool(
  "analyze_image_tone",
  "Read row/column average CHOPs from TouchDesigner, compute R,G,B,A and luminance stats, evaluate tone rules, and return matched conditions with the skill to apply for each. Use this to decide how to approach the current visual output.",
  {
    rows_chop: z.string().describe("Path to the rows-average CHOP (e.g. '/project1/analyze_rows')"),
    cols_chop: z.string().describe("Path to the cols-average CHOP (e.g. '/project1/analyze_cols')"),
  },
  async ({ rows_chop, cols_chop }) => {
    const stats = await bridge.getImageStats(rows_chop, cols_chop);
    if (stats.error) {
      return { content: [{ type: "text", text: JSON.stringify(stats, null, 2) }] };
    }

    const { rules } = loadRules();
    const matched = rules
      .filter((r) => evalRule(r, stats.overall))
      .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));

    const overall = stats.overall;
    const summary = {
      luminance_mean: overall.luminance?.mean?.toFixed(4),
      luminance_min: overall.luminance?.min?.toFixed(4),
      luminance_max: overall.luminance?.max?.toFixed(4),
      r_mean: overall.r?.mean?.toFixed(4),
      g_mean: overall.g?.mean?.toFixed(4),
      b_mean: overall.b?.mean?.toFixed(4),
      a_mean: overall.a?.mean?.toFixed(4),
    };

    const result = {
      summary,
      matched_conditions: matched.map((r) => ({
        name: r.name,
        description: r.description,
        skill: r.skill,
        priority: r.priority,
      })),
      top_condition: matched[0] ?? null,
      recommendation: matched[0]
        ? `Apply skill: ${matched[0].skill} — ${matched[0].description}`
        : "No rules matched — image appears within normal range. Use fine_tune_details.",
      raw_stats: stats.overall,
    };

    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

// 13. set_tone_rule
server.tool(
  "set_tone_rule",
  "Add or update a tone rule in tone-rules.json. Use this to configure custom thresholds and skills for different image states.",
  {
    name: z.string().describe("Rule name (snake_case identifier, e.g. 'near_white')"),
    description: z.string().describe("Human-readable description of when this rule fires"),
    skill: z.string().describe("Skill/approach to apply when this rule matches (e.g. 'reduce_brightness')"),
    priority: z.number().optional().describe("Higher priority rules are recommended first (default: 5)"),
    conditions: z.array(
      z.object({
        channel: z.enum(["r", "g", "b", "a", "luminance"]).describe("Which channel to test"),
        stat: z.enum(["mean", "min", "max"]).describe("Which aggregate stat to test"),
        min: z.number().optional().describe("Value must be >= this (0.0–1.0)"),
        max: z.number().optional().describe("Value must be <= this (0.0–1.0)"),
      })
    ).describe("All conditions must be true for the rule to match"),
  },
  async ({ name, description, skill, priority, conditions }) => {
    const config = loadRules();
    const idx = config.rules.findIndex((r) => r.name === name);
    const rule = { name, description, skill, priority: priority ?? 5, conditions };
    if (idx >= 0) {
      config.rules[idx] = rule;
    } else {
      config.rules.push(rule);
    }
    writeFileSync(RULES_PATH, JSON.stringify(config, null, 2));
    return {
      content: [{
        type: "text",
        text: JSON.stringify({ ok: true, action: idx >= 0 ? "updated" : "added", rule }, null, 2),
      }],
    };
  }
);

// 14. list_tone_rules
server.tool(
  "list_tone_rules",
  "List all configured tone rules and their thresholds from tone-rules.json.",
  {},
  async () => {
    const config = loadRules();
    return {
      content: [{ type: "text", text: JSON.stringify(config.rules, null, 2) }],
    };
  }
);

// 16. take_screenshot
server.tool(
  "take_screenshot",
  "Capture a TOP operator's current output as a PNG image. Returns the image so you can see the visual output directly. Defaults to /project1/out1 if no path given.",
  {
    op_path: z
      .string()
      .optional()
      .describe("Path to the TOP operator to capture (default: /project1/out1)"),
    save_dir: z
      .string()
      .optional()
      .describe("Directory to save screenshots on the TD machine (default: C:/Users/nik/Documents/AI/MCP/TD MCP/screenshots)"),
  },
  async ({ op_path, save_dir }) => {
    const result = await bridge.takeScreenshot(
      op_path || "/project1/out1",
      save_dir
    );
    if (result.error) {
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    }
    return {
      content: [
        {
          type: "image",
          data: result.image_b64,
          mimeType: result.mime_type || "image/png",
        },
        {
          type: "text",
          text: `Screenshot saved to: ${result.saved_to}`,
        },
      ],
    };
  }
);

// ──────────────────────────────────────────────────────────────────────
// CHECKPOINT TOOLS
// ──────────────────────────────────────────────────────────────────────

// 17. save_checkpoint
server.tool(
  "save_checkpoint",
  "Save the current state of a TouchDesigner COMP operator as a named .tox checkpoint. Use this before experiments so you can restore a known-good state. The op_path must be a COMP (baseCOMP, container, etc.).",
  {
    name: z.string().describe("Checkpoint name (e.g. 'pre_blur_experiment'). Overwrites any existing checkpoint with the same name."),
    op_path: z.string().describe("TD path to the COMP to snapshot (e.g. '/project1/myComp')"),
    description: z.string().optional().describe("What state this captures and why"),
  },
  async ({ name, op_path, description }) => {
    const safeName = name.replace(/[^a-zA-Z0-9_-]/g, "_");
    const timestamp = Date.now();
    const toxPath = `${ckpt.CHECKPOINTS_DIR.replace(/\\/g, "/")}/${safeName}_${timestamp}.tox`;

    const script = ckpt.buildSaveScript(op_path, toxPath);
    const result = await bridge.executeScript(script, `Checkpoint: ${name}`);

    const errors = await bridge.getErrors();
    const tdErrors = errors.errors ?? [];

    if (result.output?.startsWith("ERROR:") || result.errors?.length > 0) {
      return {
        content: [{
          type: "text",
          text: JSON.stringify({ ok: false, output: result.output, errors: result.errors, td_errors: tdErrors }, null, 2),
        }],
      };
    }

    const entry = ckpt.addCheckpoint(name, op_path, toxPath, description ?? "");
    return {
      content: [{
        type: "text",
        text: JSON.stringify({ ok: true, checkpoint: entry, td_errors: tdErrors }, null, 2),
      }],
    };
  }
);

// 18. restore_checkpoint
server.tool(
  "restore_checkpoint",
  "Restore a previously saved checkpoint. Destroys the current operator at the saved path and loads the .tox back into its parent. The restored op will have the same name it had when saved.",
  {
    name: z.string().describe("Name of the checkpoint to restore"),
  },
  async ({ name }) => {
    const entry = ckpt.getCheckpoint(name);
    if (!entry) {
      return {
        content: [{
          type: "text",
          text: JSON.stringify({ ok: false, error: `No checkpoint named '${name}'. Use list_checkpoints to see available checkpoints.` }, null, 2),
        }],
      };
    }

    const script = ckpt.buildRestoreScript(entry.op_path, entry.tox_path);
    const result = await bridge.executeScript(script, `Restore checkpoint: ${name}`);

    const errors = await bridge.getErrors();
    const tdErrors = errors.errors ?? [];

    const ok = result.output?.startsWith("restored:") && !result.errors?.length;
    return {
      content: [{
        type: "text",
        text: JSON.stringify({
          ok,
          restored_to: ok ? result.output.replace("restored:", "").trim() : null,
          output: result.output,
          errors: result.errors,
          td_errors: tdErrors,
          checkpoint: entry,
        }, null, 2),
      }],
    };
  }
);

// 19. list_checkpoints
server.tool(
  "list_checkpoints",
  "List all saved checkpoints with their names, operator paths, descriptions, and creation timestamps.",
  {},
  async () => {
    const checkpoints = ckpt.listCheckpoints();
    return {
      content: [{
        type: "text",
        text: JSON.stringify({ count: checkpoints.length, checkpoints }, null, 2),
      }],
    };
  }
);

// 20. delete_checkpoint
server.tool(
  "delete_checkpoint",
  "Delete a saved checkpoint and its .tox file from disk.",
  {
    name: z.string().describe("Name of the checkpoint to delete"),
  },
  async ({ name }) => {
    const removed = ckpt.removeCheckpoint(name);
    if (!removed) {
      return {
        content: [{
          type: "text",
          text: JSON.stringify({ ok: false, error: `No checkpoint named '${name}'` }, null, 2),
        }],
      };
    }
    return {
      content: [{
        type: "text",
        text: JSON.stringify({ ok: true, deleted: removed }, null, 2),
      }],
    };
  }
);

// ──────────────────────────────────────────────────────────────────────
// RESOURCES
// ──────────────────────────────────────────────────────────────────────

// td://api/classes — full class list
server.resource("api-classes", "td://api/classes", async (uri) => {
  const classes = api.listClasses();
  const meta = api.getMetadata();
  return {
    contents: [
      {
        uri: uri.href,
        mimeType: "application/json",
        text: JSON.stringify({ metadata: meta, classes }, null, 2),
      },
    ],
  };
});

// td://api/class/{name} — resolved class info
server.resource(
  "api-class",
  "td://api/class/{name}",
  async (uri, { name }) => {
    const resolved = api.resolveClassAPI(name);
    if (!resolved) {
      return {
        contents: [
          {
            uri: uri.href,
            mimeType: "application/json",
            text: JSON.stringify({ error: `Class '${name}' not found` }),
          },
        ],
      };
    }
    return {
      contents: [
        {
          uri: uri.href,
          mimeType: "application/json",
          text: JSON.stringify(resolved, null, 2),
        },
      ],
    };
  }
);

// ──────────────────────────────────────────────────────────────────────
// START
// ──────────────────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[TD-MCP] Server started on stdio");
}

main().catch((err) => {
  console.error("[TD-MCP] Fatal:", err);
  process.exit(1);
});
