---
name: td-mcp
description: Work with this repository's TouchDesigner MCP bridge and live TD project. Use for tasks involving TouchDesigner MCP tools, creating or editing TD operators, building TD UI/widgets, saving/checkpointing live TD sessions, expressive tone-driven controls, shader review grids, or porting workflows from the previous Claude TD MCP setup.
---

# TD MCP

Use this skill when a task will mutate or inspect the live TouchDesigner project through the TouchDesigner MCP server.

## Core Workflow

1. Confirm the live bridge is responsive with a read-only call such as `list_operators('/project1')` when the task depends on live TD state.
2. Before the first mutating edit, save the project with `execute_script("project.save()")` or create a checkpoint for larger experiments.
3. Make small, scoped changes with the MCP tools.
4. Verify with `get_operator_info`, `get_par_value`, `get_errors`, and TOP screenshots where applicable.
5. Save again only after verification passes.

Never press or pulse Start, Restart, or other server-control buttons on `/project1/TD_MCP`. Those controls can sever the MCP connection.

## References

- Read `references/touchdesigner-ui.md` before creating UI, controls, panels, or widgets.
- Read `references/td-container-finish.md` after building or substantially modifying any container COMP, and apply it before the final save. It defines the required finishing pass: a curated custom param tab plus a capped control panel (max 4 buttons/sliders, 1–2 displays).
- Read `references/live-bridge-safety.md` before destructive edits, checkpointing, save/restore work, or server-control changes.
- Read `references/expressive-controls.md` before adding controls that should react to tone/image-analysis thresholds.
- Read `references/shadergrid.md` when the user asks for shader candidate review grids or approval workflow.
- Read `references/td-pop-attribute-math.md` before editing POP point attributes with Attribute Combine, Math Combine, POP-to-CHOP inspection, or brightness/color-driven point displacement.
- Read `references/td-crash-recovery.md` when the user reopens TD after a crash, freeze, or restart, or says "reopened td", "we crashed", "check project state".
- Read `references/td-approval-boundaries.md` when deciding whether to ask for approval on a parameter change or just execute it.
- Read `references/td-verification-discipline.md` before claiming any visual output (tiled renders, composed TOPs, shader output, diffusion results) is correct.

## Local Context

- MCP server code: `td-mcp-server/`
- TouchDesigner Python API snapshot: `td_python_api.json`
- TouchDesigner operator reference snapshot: `td_operators.json`
- Checkpoints: `checkpoints/`
- Shader candidate pipeline: `shader_pipeline/` and `scripts/build_shader_grid.py`
- UI border pipeline: `uiborder_pipeline/`

## Verification Bias

Prefer structural and numeric verification over asking the user to inspect TD manually. When panel UI cannot be captured through the MCP because it is not a TOP, explain that limitation and verify operator state instead.
