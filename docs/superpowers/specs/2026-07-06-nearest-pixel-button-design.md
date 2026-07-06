# Design: "TOPs → Nearest Pixel" button

Date: 2026-07-06
Status: Approved (pending spec review)

## Goal

A container COMP living in the TouchDesigner project (`/project1`) that presents a
single clickable button on its surface. One click sets **every TOP under
`/project1`** to Nearest Pixel interpolation for **both** the input filter and the
viewer filter.

## Parameters targeted (verified against the live session)

Every TOP exposes these two Common-page menu parameters:

| Par name          | Label            | Menu options                          | Set to     |
|-------------------|------------------|---------------------------------------|------------|
| `inputfiltertype` | Input Smoothness | `nearest`, `linear`, `mipmap`         | `nearest`  |
| `filtertype`      | Viewer Smoothness| `useinput`, `nearest`, `linear`, `mipmap` | `nearest` |

## Scope

- **Which TOPs:** every TOP under `/project1`, recursively
  (`op('/project1').findChildren(type=TOP, maxDepth=99)` — 111 TOPs at design time).
  Rationale: walking from `root` also picks up TouchDesigner's own system/UI
  template TOPs (e.g. `/local/midi/template/icon`); scoping to `/project1` keeps
  us to the actual project. 111 of 113 project-wide TOPs live here.
- **Behavior:** one-shot per click. No continuous enforcement; TOPs created after
  a click are not auto-converted (another click handles them).
- **Trigger edge:** press-down only. The routine runs once, when the momentary
  button's `Value0` crosses to pressed (`>= 0.5`). The release (`→ 0`) is ignored.
- **No on-panel count report** (kept minimal per user choice).

## Components (4 ops)

1. **`/project1/cont_nearestpixel`** — a `containerCOMP`, ~220×90 px panel,
   node-positioned well clear of the existing node cluster (offset `nodeX/nodeY`).
   `.viewer = True` so the panel is live and clickable in the network.

2. **`btn_apply`** — a Basic Widgets `buttonMomentary.tox` widget, instantiated
   programmatically and lifted clean out of its packaging container (per the
   CLAUDE.md `loadTox` → find `type=='widget'` op → `copyOPs` pattern), sized to
   fill the container. `Widgetlabel = "TOPs → Nearest Pixel"`. This is the
   "button on the exterior."

3. **`params_exec`** — a **Parameter Execute DAT** inside `cont_nearestpixel`,
   watching `btn_apply`'s `Value0`. `onValueChange` guards on `float(newVal) >= 0.5`
   and, on a rising edge, calls the apply routine. Monitors: the widget op; Value0.

4. **Apply routine** (lives in `params_exec`):
   ```python
   def onValueChange(par, prev):
       if float(par.eval()) < 0.5:
           return
       n = 0
       for t in op('/project1').findChildren(type=TOP, maxDepth=99):
           try:
               t.par.inputfiltertype = 'nearest'
               t.par.filtertype = 'nearest'
               n += 1
           except Exception:
               pass
       print(f"[nearest-pixel] set {n} TOPs to Nearest Pixel")
       return
   ```
   Each TOP is wrapped in `try/except` so a locked or expression-driven parameter
   can't abort the whole sweep.

## Build order

1. Restore point first: if the project has a real file path, `project.save()`.
   If it is **untitled**, `project.save()` pops a modal that hangs the bridge —
   use `save_checkpoint` on `/project1` instead. Decide by checking
   `project.name` / `project.saveFile`.
2. Create `cont_nearestpixel` (offset node position), set panel size, `.viewer = True`.
3. Instantiate `buttonMomentary.tox`, lift the widget op, copy in clean, rename
   `btn_apply`, size to fill, set label.
4. Create `params_exec` Parameter Execute DAT, point its monitor at `btn_apply` /
   `Value0`, enable `onValueChange`, and write the callback body.
5. Verify (below).
6. Persist: `project.save()` (or `save_checkpoint`) once verification passes.

## Verification (numeric — panels can't be screenshotted through the bridge)

1. Pick 2–3 sample TOPs under `/project1`, force them to `linear` on both pars.
2. Invoke the apply routine programmatically (call the DAT's `onValueChange`, or
   simulate the press by setting `btn_apply.par.Value0 = 1`).
3. Read those sample TOPs back and confirm both pars now read `nearest`.
4. Confirm the reported count matches the live TOP count.
5. `get_errors` on the container clean.

## Non-goals

- Not touching TOPs outside `/project1` (TD system/UI ops left alone).
- No continuous/timer enforcement.
- No undo of prior filter settings; this is a one-way "force to nearest."

## Risks / notes

- **Never** touch the Start/Restart button on `/project1/TD_MCP` — unrelated here,
  but the sweep will set filter pars on any TOPs inside `TD_MCP`; that is harmless
  (control UI), and matches the "every TOP" intent.
- `execute_script` scoping gotcha: keep helpers inline / iterate with stacks; no
  closures over top-level names when running build scripts through the bridge.
