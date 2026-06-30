# TD MCP Project Guidance

This repo hosts the TouchDesigner MCP bridge. The MCP server in `td-mcp-server/` talks to a live, usually unsaved TouchDesigner session through the in-TD WebServer DAT on port `9980`, inside `/project1/TD_MCP`.

Edits made through MCP mutate the running TouchDesigner project immediately. They are not durable on disk until `project.save()` runs.

## TouchDesigner MCP Discipline

- Before the first mutating TouchDesigner edit in a task, run `execute_script("project.save()")` or save a checkpoint for a known restore point.
- Make scoped changes, then verify with `get_operator_info`, `get_par_value`, `get_errors`, and TOP screenshots when relevant.
- After verification passes, run `execute_script("project.save()")` again.
- For bulk destructive work, save a checkpoint on the parent COMP first.
- Never combine bulk destroy operations with force-cooking in one script; this can freeze TouchDesigner.
- Never press Start, Restart, or other server-control buttons on `/project1/TD_MCP`; that can reinitialize the WebServer DAT and sever the live MCP bridge.
- Build or verify server controls structurally only. A real restart is the user's action at the keyboard.
- Place new disconnected or top-level COMPs away from the existing node cluster with `nodeX` and `nodeY` so the network stays readable.

## Network Hygiene

- Pull a Null operator (`nullCHOP`, `nullTOP`, `nullDAT`, etc.) off the end of each logical subsection of the network, and reference that Null downstream instead of reaching into the subsection's internals. This gives a stable tap/pull point: you can rewire or rebuild the subsection behind the Null without touching every consumer, and the Null is the obvious place to probe values during debugging. Do this often — after control buses, after a generator stage, after any cluster whose output other parts depend on. Example in this project: `key_vals` (Constant CHOP, editable) → `key_vals_null` (the shared pull point that the ramp key tables reference).

## UI In TouchDesigner

- Use Basic Widgets palette components for UI, not bare `sliderCOMP` or `buttonCOMP`.
- Derive the Basic Widgets path at runtime from `app.installFolder`; do not hardcode a TouchDesigner install version.
- Instantiate widgets programmatically with `loadTox`, then copy out the native `widget` operator from the temporary holder.
- Panel coordinates use bottom-left origin. A missing widget is often at `(0, 0)`.
- A container only shows its panel UI when its panel is displayed, for example through `comp.viewer = True`, `openViewer`, a `windowCOMP`, the Perform window, or a displayed ancestor.
- `viewer` is an operator attribute, not a parameter.
- `take_screenshot` captures TOP output only; it cannot directly screenshot panels.

## Scripting Gotchas

- `execute_script` runs code in a wrapper where nested functions cannot reliably close over top-level locals.
- Prefer iterative tree walks with explicit stacks or queues inside TouchDesigner scripts.
- When creating controls meant to react to image-analysis or tone thresholds, route them through `/project1/null_expressive` rather than hardwiring values.

## Codex Skill

Use the repo-local `$td-mcp` skill for deeper TouchDesigner MCP workflows, including widget creation patterns, expressive-control conventions, shader review grids, and conversion notes from the previous Claude setup.
