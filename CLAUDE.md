# TD_MCP — project guidance for agents

This repo hosts the TouchDesigner MCP bridge. The MCP server (`td-mcp-server/`) talks to a **live, unsaved** TouchDesigner session via an in-TD WebServer DAT on port **9980** (inside `/project1/TD_MCP`). Edits made through the MCP mutate the running project immediately but are not on disk until `project.save()`.

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

`.viewer` is an **op attribute, not a parameter** — diffing two containers' parameters will NOT reveal why one shows UI and another doesn't. (This cost a whole debugging loop: a widget was correctly parented in `cont_uidemo`, but `cont_uidemo.viewer=False` while `/project1.viewer=True`, so it only appeared nested in `/project1`'s panel.)

### 5. `execute_script` scoping gotcha
Code runs in a wrapper where nested `def`s can't see top-level names — **recursion and closures over outer locals fail**. Walk trees iteratively (stack/queue), keep helpers inline.

---

## Save discipline & the live bridge (do not skip)
1. **Before** the first mutating edit of a task: `execute_script("project.save()")` for a known-good restore point (or `project.saveBackup()` for a timestamped copy).
2. Make scoped changes; **verify** (`get_operator_info` / `get_par_value` / `get_errors`).
3. Only **after** verification passes: `project.save()` again.

- Bulk-destructive ops (mass delete / containerize / mass param rewrite): `save_checkpoint` on the parent COMP first, and **never combine bulk destroy with force-cook in one script** (freezes TD).
- **NEVER press the Start/Restart (or any server-control) button on `/project1/TD_MCP`** — it re-inits the WebServer DAT and severs the live MCP bridge mid-task. Build/verify such controls **structurally only**; a real restart is the user's to do at the keyboard.
- New disconnected/top-level COMPs: set `nodeX/nodeY` far from the existing node cluster so the patch stays readable. (Network position ≠ panel `x/y`.)
- Panels can't be screenshotted through this bridge (`take_screenshot` is TOP-only; control panels aren't TOP-renderable). Verify UI numerically/functionally, or ask the user to glance at the viewer.

---

## POP attribute math notes

Before adjusting POP point positions with Attribute Combine POP, Math Combine POP, or POP-to-CHOP inspection, read:

```text
.agents/skills/td-mcp/references/td-pop-attribute-math.md
```

The current `tile_chain_0_0` displacement is upstream in the POP chain, not inside `circle_point_render`: `attcombine1 -> mathcombine1 -> out1`. `circle_point_render/pop_attrs` now reads `out1` and uses `P Color height brightness`; Z displacement is baked into `P_2`, not driven by the old render-local `PointScale` attempt.
