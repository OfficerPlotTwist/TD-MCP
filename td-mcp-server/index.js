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
 *         get_operator_info, list_operators, get_par_value, set_par_value
 *
 * Resources: td://api/classes, td://api/class/{name}
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import * as bridge from "./td-bridge.js";
import * as api from "./api-validator.js";

const server = new McpServer({
  name: "touchdesigner",
  version: "1.0.0",
});

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
