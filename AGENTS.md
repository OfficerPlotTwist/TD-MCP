# TD MCP agent guidance

This repository provides a general-purpose stdio MCP server and a portable TouchDesigner WebServer DAT component. It does not require a particular creative project, controller, AI provider, external account, or local workflow manager.

Read `.agents/skills/td-mcp/SKILL.md` for live work and `docs/SESSION_LEARNINGS.md` for session-derived troubleshooting. Repository code and an installed live component can differ; inspect the running callbacks before assuming a source edit is deployed.

## Live bridge discipline

- Use MCP for live edits and inspection. First confirm the intended project and bridge with a read-only request. Example operator paths are illustrative; discover actual paths.
- Before mutating, create a known restore point: checkpoint the affected COMP or save to a NEW unused versioned project path. Never overwrite the last known-good project. Before bulk destruction, checkpoint the parent COMP.
- Make scoped edits, verify with `get_operator_info`, `get_par_value`, `get_errors`, and relevant TOP screenshots, then save a new unused version. A COMP checkpoint is not a whole-project save.
- Derive project destinations from `project.folder` or explicit user configuration. `project.saveBackup()` is absent in some builds. TouchDesigner may increment even an explicit filename: verify `project.name` and actual file existence after every save.
- Never pulse Start/Restart or deactivate, replace, or destroy the serving bridge through its own connection. Inspect controls structurally. The operator activates or restarts the server outside MCP.
- A timeout has an unknown mutation outcome. Reconnect and inspect before retrying; a listening port alone does not establish bridge health.
- Never combine bulk destruction and force-cooking in one script. Keep long GPU jobs bounded, checkpoint between stages, and preserve existing unsaved work.
- Place new disconnected COMPs away from existing nodes with `nodeX`/`nodeY`.

## Network conventions learned in practice

- Use role-named Null operators at meaningful branch boundaries, before composites/shared effects, and before paths referenced by expressions, exports, lookups, or driver parameters.
- For generated TOPs, set `filtertype` and `inputfiltertype` to `nearest` wherever supported, unless the task requests interpolation. This is an authoring convention, not a requirement for the bridge.
- For UI, prefer Basic Widgets palette components over bare slider/button COMPs. Resolve palette paths from `app.installFolder`; load into a temporary holder and copy the native `widget` out.
- Panel coordinates start at bottom-left. `viewer` is an operator attribute. A panel needs a displayed ancestor/viewer/window to be visible. TOP screenshots do not capture arbitrary panels.
- Verify runtime menu values, parameter existence, and sequence block counts instead of assuming another TD build's API. `COMP.children` is a list, not a function.
- Older callback deployments used separate `exec` scopes, breaking nested functions that reference script variables/imports. This source uses one isolated namespace per request; prefer iterative walks for compatibility with older deployments.
- Tone analysis and shared control Nulls are optional project patterns. Discover or create a scoped handoff with user intent; never require a fixed `/project1/null_expressive` path.

## Save names and verification

Use short semantic component/project filenames such as `role.variant.vN.YYYYMMDD.tox` and `role.vN.YYYYMMDD.toe`, with the actual local date and an unused revision. Keep live operator paths stable. Do not assume a numeric suffix remains unchanged after a TD project save.

Source inspection, automated tests, live operator inspection, rendered visual inspection, and physical hardware tests are separate evidence. State which was actually performed. Save standalone review images when requested so review does not require rerunning processing. Preserve unresolved human choices; background task completion is not approval.

## Repository scope

Keep bridge source, generic setup, API snapshots/scrapers, tests, and reusable agent lessons tracked. Keep project binaries, screenshots/renders, checkpoints, creative scripts/pipelines, private host settings, and workflow hooks local and ignored. Keep the npm lockfile tracked. Never delete local project work to clean the repository; use index-only removal. Git ignore rules do not remove old files from Git history.
