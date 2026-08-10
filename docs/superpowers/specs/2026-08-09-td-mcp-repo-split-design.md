# TD_MCP repo split — universal plumbing vs. components and projects

**Date:** 2026-08-09
**Status:** implemented — see "Implementation notes" for deviations

## Problem

`TD-MCP` holds two unrelated kinds of thing. The MCP bridge — a general-purpose
TouchDesigner control surface reusable on any TD project — sits in the same repo
as the specific artefacts of one installation: blob trackers, colour masks,
shader pipelines, tutorial captures, render output. Starting a second TD project
today means cloning all of it, and the bridge cannot be shared without dragging
along a particular show's assets.

The split also fixes a live defect. `.mcp.json` carries an absolute path to
`td_python_api.json` from a machine that no longer exists
(`c:/Users/nik/Documents/AI/MCP/TD MCP/...`), and `checkpoints.js` writes project
checkpoints into the bridge's own directory. Both assume one repo is one project.

## Goals

- The bridge is usable from any working directory with one environment variable set.
- A new TD project starts by cloning one small repo, not a 400 MB one.
- Nothing is deleted from `TD-MCP` until the new repos are proven to work.

## Non-goals

- Purging the 414 MB of `.toe`/`.tox` blobs still in `TD-MCP`'s history. Those
  files are untracked as of `ed723ce` but remain in past commits. Removing them
  needs `git filter-repo` and a force push across 90+ commits; that is a separate
  decision.
- Preserving git history for the moved files. The new repos start fresh (one
  initial commit). History for those paths stays reachable in `TD-MCP`.
- Publishing `td-mcp-server` to npm.

## The three repos

### 1. `TD-MCP` — the bridge (existing repo, keeps its history and remote)

Universal plumbing only. Everything here is true of any TouchDesigner project.

| Path | Why it is universal |
| --- | --- |
| `td-mcp-server/` (incl. `hooks/`) | The MCP server, TD HTTP bridge, API validator, checkpoint store, A2A layer |
| `td_python_api.json`, `td_operators.json` | The TouchDesigner API database the validator checks calls against |
| `scraper/` | `scrape_td_api.py` / `scrape_td_operators.py` regenerate the two JSON files above |
| `touchdesigner/webserver_callbacks.py` | The in-TD half of the bridge. Routes are `/health`, `/execute`, `/errors`, `/operator`, `/chop`, `/screenshot`, `/image_stats` — no component-specific routes |
| `touchdesigner/LAYOUT.md` | The layout convention (the pinned data in `layout.json` is project-specific and moves) |
| `.agents/skills/td-mcp/` minus `references/shadergrid.md` | Bridge safety, crash recovery, verification discipline, POP maths, container finish, approval boundaries, TD UI |
| `.claude/commands/td-pop-attribute-math.md` | Generic TD technique |
| `.mcp.json`, `.gitignore`, `README.md` | Repo config, rewritten to bridge scope |
| `CLAUDE.md`, `AGENTS.md` | Bridge half only — see "Documentation split" |

Deleted from `TD-MCP` as part of this work:

- `Touchdesigner Cline Workflow/` (10 files) — superseded by the MCP bridge.
- `mcp_config.json` — a stale duplicate of `.mcp.json` still pointing at the dead
  `c:/Users/nik/...` paths.

### 2. `TD_Components` — https://github.com/OfficerPlotTwist/TD_Components

Already created, empty, reachable. Receives:

- `touchdesigner/blobtrack/`, `colormask/`, `maskcombiner/`, `resttrigger/`
- `touchdesigner/layout.json` (pinned node positions for this project's network)
- `touchdesigner/assets/` (currently untracked; ~8 MB of mask PNGs and source photos)
- `shaders/`, `shader_pipeline/`, `uiborder_pipeline/`, `crowd-control/`
- `scripts/` (shader grid builder, `looksgood`, APC40 HTML generator, TD queue sync)
- `docs/superpowers/` — plans and specs, all of which describe specific builds
- `screenshots/`, `renders/`, `toe/`, `checkpoints/index.json`
- Root files: `apc40_midi_map.json`, `apc40_monitor.html`, `chop_monitor.py`,
  `td_pointcloud_guide.md`, `threshold_method_report.md`,
  `video_processor_overview.txt`
- `.claude/commands/shadergrid.md` and `.agents/skills/td-mcp/references/shadergrid.md`
  — both document the shader review pipeline, which lives here now
- Project half of `CLAUDE.md` / `AGENTS.md`

This spec is the exception among `docs/superpowers/specs/`: it describes the
bridge repo's own structure, so it stays in `TD-MCP`.

### 3. `TD_TutorialScraping` — to be created

`gh repo create OfficerPlotTwist/TD_TutorialScraping --private`. Receives:

- `.claude/skills/attention-handoff-td/` (14 files: `SKILL.md`, capture server,
  `matching.py`, `rebuild_plan.py`, the browser capture/approve/evidence app, tests)
- `tutorials/` and its `.gitignore`

The existing `tutorials/.gitignore` excludes `video.*`, so the 285 MB
`eTSKz_iiFOY/video.mp4` stays on disk and out of git. The repo lands at roughly
5 MB.

## Coupling: sibling clones

The three repos are peers on disk under `C:\Users\NICKESCHEN\dev\`. Neither
project repo vendors, submodules, or npm-installs the bridge. They locate it
through one user environment variable:

```
TD_MCP_HOME = C:\Users\NICKESCHEN\dev\TD-MCP
```

Each project repo carries its own `.mcp.json`:

```json
{
  "mcpServers": {
    "touchdesigner": {
      "command": "node",
      "args": ["../TD-MCP/td-mcp-server/index.js"],
      "env": {
        "TD_HOST": "127.0.0.1",
        "TD_PORT": "9980",
        "TD_CHECKPOINTS_DIR": "checkpoints"
      }
    }
  }
}
```

Rejected alternatives: a git submodule (painful on Windows, and the bridge is
edited daily, so every bridge change would become a submodule commit plus a
pointer bump) and an npm dependency (needs a `bin` entry and packaging work
before it buys anything, with only two consumers).

### Two bridge changes this requires

**`TD_API_DB` is removed from `.mcp.json`, not relocated.** The API database
stays in `TD-MCP` and is owned by `TD-MCP`. `api-validator.js:20` already reads:

```js
process.env.TD_API_DB || resolve(__dirname, "..", "td_python_api.json")
```

so with the environment variable unset, the bridge resolves the database relative
to its own file. The absolute path in `.mcp.json` was never needed; it is what
broke when the repo moved between machines. Dropping it also means a project repo
cannot point the bridge at a different database.

**`checkpoints.js:13` gains an override.** Today:

```js
export const CHECKPOINTS_DIR = join(__dirname, "..", "checkpoints");
```

This writes a project's `.tox` checkpoints into the bridge repo. Change to:

```js
export const CHECKPOINTS_DIR = process.env.TD_CHECKPOINTS_DIR
  ? resolve(process.cwd(), process.env.TD_CHECKPOINTS_DIR)
  : join(__dirname, "..", "checkpoints");
```

`TD_CHECKPOINTS_DIR` is resolved against the server's working directory, which
Claude Code sets to the project root. A bare `"checkpoints"` in `.mcp.json`
therefore means "this project's checkpoints directory" without either repo
naming an absolute path. An absolute value still works, since `resolve` returns
it unchanged. The fallback keeps existing behaviour when the variable is unset.

Note that `${PWD}` is deliberately not used in `.mcp.json`: `PWD` is set by Git
Bash but not by `cmd.exe` or PowerShell, so it cannot be relied on here.

Two mechanical details: `resolve` must be added to the existing
`import { join, dirname } from "path"` on line 9, and no directory-creation work
is needed — `ensureDir()` already calls `mkdirSync(CHECKPOINTS_DIR, { recursive:
true })` before every read and write, so a fresh project repo gets its
`checkpoints/` created on first use.

## Documentation split

`CLAUDE.md` and `AGENTS.md` currently mix bridge rules with project conventions.

Stays in `TD-MCP`: the live-bridge description and port, the MCP call log table,
save discipline, the never-restart-the-WebServer-DAT rule, the widget/UI
construction guidance, the `execute_script` scoping gotcha, panel coordinates,
and the layout-authority rule.

Moves to `TD_Components`: the master-controls parameter convention
(`/project1/master_controls` is this project's bus), the component copies and My
Components palette workflow, the Non-Commercial 1280×1280 note as it applies to
this installation, and the POP attribute maths notes that reference
`tile_chain_0_0` and `circle_point_render` by name.

Each repo gets a `README.md` describing what it is and, for the project repos,
the `TD_MCP_HOME` prerequisite.

## Migration order

Deletion is last. Nothing leaves `TD-MCP` until the new repos are verified.

1. **Bridge fixes.** Remove `TD_API_DB` from `.mcp.json`; add the
   `TD_CHECKPOINTS_DIR` override to `checkpoints.js`. Verify against the live TD
   session: `save_checkpoint` then `list_checkpoints`, and confirm the `.tox`
   lands in the directory the variable names.
2. **Create `TD_TutorialScraping`** via `gh repo create`.
3. **Populate the two new repos.** Copy each file set into a fresh working
   directory (`dev/TD_Components`, `dev/TD_TutorialScraping`), add a `.gitignore`
   and `README.md`, `git init`, one initial commit, push.
4. **Verify.** Set `TD_MCP_HOME`. From `dev/TD_Components`, confirm the MCP
   bridge connects to the running TD session and a component test suite still
   runs (`pytest touchdesigner/colormask/tests`). From
   `dev/TD_TutorialScraping`, confirm the attention-handoff server starts and
   its tests pass.
5. **Prune `TD-MCP`.** `git rm -r` the moved paths, delete
   `Touchdesigner Cline Workflow/` and `mcp_config.json`, rewrite `CLAUDE.md`,
   `AGENTS.md` and `README.md` to bridge scope, commit, push.
6. **Re-verify `TD-MCP`.** Bridge still connects from the pruned repo; hooks in
   `td-mcp-server/hooks/` still run.

## Success criteria

- `TD-MCP` working tree contains only the files listed in its table above.
- With `TD_MCP_HOME` set and nothing else configured, the MCP bridge connects to
  the live TD session from all three repo directories.
- `save_checkpoint` invoked from `TD_Components` writes into
  `TD_Components/checkpoints/`, not into `TD-MCP/checkpoints/`.
- The colormask test suite and the attention-handoff test suite pass from their
  new homes.
- `TD_Components` and `TD_TutorialScraping` each clone in under 30 seconds on a
  normal connection.

## Risks

- **Untracked working files.** `touchdesigner/assets/`, `crowd-control/`, and the
  tutorial captures exist on disk but are partly untracked. Step 3 copies from
  the working tree, not from git, so these come across — but they must be
  inventoried before step 5 deletes anything.
- **Hidden path assumptions.** Scripts under `scripts/` and the pipelines may
  reference repo-relative paths that change when they move. Step 4's verification
  should run at least `build_shader_grid.py` and `looksgood.py` far enough to see
  them resolve their inputs.
- **Two `.mcp.json` files drifting.** Both project repos carry near-identical
  config. If a third project appears, revisit the npm packaging option.

## Implementation notes

Executed 2026-08-09. Six deviations from the design above, all deliberate.

1. **Sibling-relative path instead of `TD_MCP_HOME`.** Project repos use
   `"args": ["../TD-MCP/td-mcp-server/index.js"]`. Node resolving a relative
   argument against the host's working directory was verified directly; whether
   this Claude Code build expands `${VAR}` inside `.mcp.json` could not be
   verified without restarting the MCP host mid-task, and a failed expansion
   would have broken the bridge on next launch. The relative form needs no
   environment variable at all, and "clone them as siblings" was already the
   design. No `TD_MCP_HOME` variable was created.
2. **`touchdesigner/LAYOUT.md` moved to `TD_Components`** rather than staying.
   On reading it, roughly 90% is project-specific — the seven-band `/project1`
   arrangement, `cont_colormask`, `cont_blobtrack_glsl`. `reorganize.mjs` reads
   `layout.json` via `join(projectDir, "touchdesigner", "layout.json")`, so the
   hook follows whichever project it runs in. `TD-MCP/CLAUDE.md` keeps the
   project-agnostic rules and points at the project repo for the rest.
3. **The attention-handoff spec and plan went to `TD_TutorialScraping`**, not
   `TD_Components`. `SKILL.md` references its design spec by relative path, so
   the docs had to travel with the skill.
4. **`checkpoints/index.json` stayed in `TD-MCP`.** It indexes the `.tox`
   snapshots physically present in `TD-MCP/checkpoints/`, which remains the
   bridge's default store when `TD_CHECKPOINTS_DIR` is unset. Removing it would
   have orphaned them.
5. **Three tracked `.pyc` files were dropped, not moved**
   (`scripts/__pycache__/*`, `shader_pipeline/__pycache__/_db.*`). Compiled
   bytecode should never have been tracked; the new repos gitignore
   `__pycache__/`.
6. **Binaries were left in place.** `TD-MCP/toe/` still holds 414 MB of `.toe`
   files and `tutorials/eTSKz_iiFOY/video.mp4` is still 285 MB on disk, because
   TouchDesigner may have one of those projects open. Untracked
   `screenshots/` and `touchdesigner/assets/` copies also remain. These are
   gitignored everywhere and need a manual move with TD closed.

### Verification performed

Before anything was deleted from `TD-MCP`:

- Every one of the 241 pruned files was SHA256-compared against its copy in the
  new repos. 227 matched byte-for-byte; 11 were the intentional deletions
  (`Touchdesigner Cline Workflow/`, `mcp_config.json`); 3 were the dropped
  `.pyc` files.
- `CHECKPOINTS_DIR` resolution checked in all three cases from a foreign working
  directory: unset → bridge directory, relative → working directory, absolute →
  passthrough.
- API database loads with `TD_API_DB` unset (87 classes).
- The server boots over the sibling-relative path from both new repo
  directories.
- Test suites pass from their new homes: colormask 27, attention-handoff 34,
  blobtrack 8, maskcombiner 1.
- The live TD session was reachable throughout (`list_operators` on
  `/project1/MCP_Server`).

The bridge fixes only take effect when the MCP host restarts the server; the
session that made them ran the previous code the whole time.
