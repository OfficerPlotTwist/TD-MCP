# TD-MCP — project guidance for agents

This repo hosts the TouchDesigner MCP bridge and nothing else. The MCP server
(`td-mcp-server/`) talks to a **live, unsaved** TouchDesigner session via an in-TD
WebServer DAT on port **9980** (inside `/project1/MCP_Server`). Edits made through
the MCP mutate the running project immediately but are not on disk until
`project.save()`.

Project work lives in sibling repos — `../TD_Components` (installation
components) and `../TD_TutorialScraping` (tutorial rebuild pipeline). Each has
its own `CLAUDE.md` with project conventions, and its own `.mcp.json` pointing
back at this bridge. Keep this repo free of project-specific content: if
something is only true of one installation, it belongs in that project's repo.

Every MCP call is logged to `/project1/MCP_Server/table_mcp_log` (`time | frame |
method | uri | label | status`, newest last, capped at 1000, `/health` excluded)
— check it to reconstruct what the bridge did and when.

---

## Creating UI inside the TouchDesigner project (read this before adding any UI)

### 1. Use Widget palette components — NOT bare `sliderCOMP` / `buttonCOMP`
Bare slider/button COMPs render as tiny low-contrast nubs and aren't real "container UI." Use the **Basic Widgets** palette components (styled, bind-ready, expose a clean `Value0` + callbacks).

Location (derive the version at runtime, don't hardcode):
```python
import os
bw = os.path.join(app.installFolder, "Samples/Palette/UI/Basic Widgets")
# sliderHorz.tox, sliderVert.tox, buttonMomentary.tox, buttonToggle.tox,
# knobFixed.tox, fieldString.tox, float1.tox, dropDownMenu.tox, ... etc.
```

Instantiate **programmatically** (never ask the user to drag from the Palette). `loadTox` lands the tox as a CHILD wrapped in packaging containers, so lift the native `widget`-type op out and copy it in clean:
```python
parent_comp = op('/project1/cont_uidemo')
holder = parent_comp.create(containerCOMP, '__tmp')
holder.loadTox(os.path.join(bw, 'sliderHorz.tox'))
widget_op = None                      # find the type=='widget' op (iterative — see gotcha #5)
stack = list(holder.children)
while stack:
    o = stack.pop()
    if o.type == 'widget': widget_op = o; break
    stack.extend(o.children)
w = parent_comp.copyOPs([widget_op])[0]   # single clean node
holder.destroy()
w.name = 'slider_period'
```

The widget exposes `Value0` (normalized 0..1), `Widgetlabel`, and rich styling pars: `Sliderbgcolor*`, `Sliderknobcolor*`, `Sliderindicatorcolor*`, `Labelfontcolor*`, `Rollovercolor*`, `Font`/`Fontfile`. For non-flat looks, feed a TOP into `Sliderbgtop` / `Sliderknobtop` (TOP-typed pars) — the whole UI is composited through the TOP pipeline, so you can also post-process the assembled panel.

### 2. Wire a control to a parameter
- **Value copy → Bind** (two-way): `t.par.X.bindExpr = "op('slider_period').par.Value0"; t.par.X.mode = ParMode.BIND`
- **Logic on change/press** → a **Parameter Execute DAT** watching the widget, with `onValueChange`/`onPulse`.

### 3. Panel coordinates: origin is BOTTOM-LEFT
`(0,0)` is the bottom-left corner; `y` grows upward. A "missing" widget is almost always parked at `(0,0)`. Parent `align='none'` → children use their own `x/y`; a layout value → children are auto-arranged (their `x/y` ignored).

### 4. A container only SHOWS its UI when its panel is DISPLAYED ← most common confusion
Putting widgets inside a `containerCOMP` is **not** enough to see them. The panel renders only when something displays it:
- `comp.viewer = True` (activates the node viewer), and/or `comp.openViewer(unique=True, borders=True)` (floating window), and/or
- a `windowCOMP` / the Perform window targets it (`/perform.par.winop = <comp>`), and/or it is nested inside a displayed ancestor.

`.viewer` is an **op attribute, not a parameter** — diffing two containers' parameters will NOT reveal why one shows UI and another doesn't.

### 5. `execute_script` scoping gotcha
Code runs in a wrapper where nested `def`s can't see top-level names — **recursion and closures over outer locals fail**. Walk trees iteratively (stack/queue), keep helpers inline.

---

## Save discipline & the live bridge (do not skip)
1. **Before** the first mutating edit of a task: `execute_script("project.save()")` for a known-good restore point (or `project.saveBackup()` for a timestamped copy).
2. Make scoped changes; **verify** (`get_operator_info` / `get_par_value` / `get_errors`).
3. Only **after** verification passes: `project.save()` again.

- Bulk-destructive ops (mass delete / containerize / mass param rewrite): `save_checkpoint` on the parent COMP first, and **never combine bulk destroy with force-cook in one script** (freezes TD).
- **NEVER press the Start/Restart (or any server-control) button on `/project1/MCP_Server`** — it re-inits the WebServer DAT and severs the live MCP bridge mid-task. Editing `webserver1_callbacks` text is safe **only if** you `compile()` the new text first and swap it in one script; a syntax error there kills the bridge on the next request. Build/verify such controls **structurally only**; a real restart is the user's to do at the keyboard.
- **Network layout is owned by the project repo**, not by this one. Each project keeps `touchdesigner/LAYOUT.md` + `touchdesigner/layout.json`; the Stop hooks in `td-mcp-server/hooks/` read `layout.json` relative to whichever project directory they run in. Core rules regardless of project: never move user-placed operators unless explicitly asked; only pinned ops are managed; change layout by editing `layout.json`, never by ad-hoc node moves. (Network position ≠ panel `x/y`.)
- Panels can't be screenshotted through this bridge (`take_screenshot` is TOP-only; control panels aren't TOP-renderable). Verify UI numerically/functionally, or ask the user to glance at the viewer.

---

## Checkpoints

`save_checkpoint` writes to `TD_CHECKPOINTS_DIR` when set (relative values resolve
against the MCP host's working directory), otherwise to this repo's
`checkpoints/`. Project repos set it so their snapshots stay with the project.

## The API database

`td_python_api.json` and `td_operators.json` belong to this repo and are
regenerated by `scraper/`. `api-validator.js` resolves the database from its own
directory, so leave `TD_API_DB` unset — a project repo should never point the
bridge at a different database.
