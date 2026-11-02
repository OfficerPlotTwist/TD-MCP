---
name: td-mcp
description: Install, inspect, and use the general-purpose TouchDesigner MCP bridge; safely edit and verify live TD operators, checkpoint networks, recover sessions, and build native UI.
---

# TD MCP

1. Read `AGENTS.md` and `docs/SESSION_LEARNINGS.md`.
2. For installation, use `README.md` and `touchdesigner/install_bridge.py`. It creates an inactive, self-contained COMP; activation happens outside the bridge.
3. For live work, confirm connectivity and project identity with a read-only call. Preserve a known-good restore point before mutation.
4. Make scoped changes and verify operator/parameter/error state and relevant TOP output. Save to a new unused versioned path and verify the actual saved filename.
5. On timeouts or crashes, inspect current state and checkpoints before retrying or rebuilding. Never restart the serving bridge through MCP.

References:
- `references/live-bridge-safety.md`: saving, checkpointing, execution scope, and server controls.
- `references/touchdesigner-ui.md`: native widgets, panel coordinates, and visibility.
- `references/expressive-controls.md`: optional shared image-analysis controls.
- `references/shadergrid.md`: generic candidate grids and durable review images.
- `references/td-pop-attribute-math.md`: native POP displacement and numeric inspection.
- `references/td-crash-recovery.md`: artifact discovery and safe recovery.
- `references/td-approval-boundaries.md`: acting within authorized scope and preserving unresolved choices.
- `references/td-verification-discipline.md`: visual evidence and intermediate output checks.

Bridge code lives in `td-mcp-server/`; embedded TD callbacks and installer in `touchdesigner/`; API snapshots in `td_python_api.json` and `td_operators.json`. Runtime checkpoints are ignored and may be configured with `TD_CHECKPOINTS_DIR`. No creative pipeline or named project is required.
