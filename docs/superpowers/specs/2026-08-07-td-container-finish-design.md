# td-container-finish — auto UI pass for built containers

**Date:** 2026-08-07
**Status:** Approved

## Purpose

Every container COMP built (or substantially modified) through the TD MCP bridge gets a
finishing pass before the final save: a curated custom parameter tab wired to its internals,
and a small control-panel UI (widgets + displays) on the container itself. On-demand
application to existing containers is also supported when asked.

## Packaging

- New reference: `.agents/skills/td-mcp/references/td-container-finish.md`
- One trigger line added to `.agents/skills/td-mcp/SKILL.md` References section:
  read td-container-finish.md after building or substantially modifying any container COMP,
  and apply it before the final save.
- Auto-fire is inherited from td-mcp, which already loads for all TD tasks.

## Step 1 — Analyze the container's function

Census the children (op families + named ops), then rank exposure candidates in three tiers:

1. **Live-performance touches** — switches, on/off gates, trigger/reset points, speeds.
2. **Look/behavior tuning** — thresholds, levels, periods, colors.
3. **Diagnostics** — the output op, counts, active channels.

Concrete signals:

- Switch TOP/CHOP with a hardcoded index → menu or toggle custom par.
- Hardcoded constants in Level / Math / Threshold / Speed ops → ranged float sliders.
- Feedback loops, counters, Trigger CHOPs → reset pulse.
- Final `out` op (or the most-composited TOP) → display candidate.

## Step 2 — Custom param tab

- `appendCustomPage` named for the function (e.g. `Blobtrack`), not a generic `Custom`.
- Up to **8 params**: toggles, ranged floats, menus, pulses.
- Wiring is internal-binds-up: the internal op's par gets
  `bindExpr = "parent().par.X"` and `mode = ParMode.BIND`. The container stays a
  self-contained, palette-savable component. `master_controls` remains for
  cross-component/global values only (explicitly out of scope here).
- Defaults captured from current live values so adding the tab changes nothing visually.
- Ranges from the internal par's normMin/normMax or sensible domain knowledge.
- TD-style capitalized par names (`Threshold`, `Active`, `Resetall`).

## Step 3 — Panel UI on the container's own panel

- Widgets and displays are **children of the container**, visible on its control panel.
- Hard caps: **≤ 4 controls** (any mix of Basic Widgets buttons/sliders),
  **≤ 2 displays** (TOP viewer and/or CHOP/DAT readout via opviewer /
  background-TOP container).
- Controls bind to the container's custom pars (`Value0` ↔ custom par), so panel and
  param tab always agree; logic-on-press goes through a Parameter Execute DAT.
- Layout: fixed panel size, displays on top, control row below, `Widgetlabel` labels,
  bottom-left-origin math, `viewer = True` when done.
- Display TOPs: nearest filtering, respect the 1280×1280 non-commercial cap.

## Guardrails & verification

- `save_checkpoint` on the container before mutating (never `project.save()` on an
  untitled project — modal freezes the bridge).
- Never touch `/project1/MCP_Server`.
- New widget ops go in a tidy row inside the container network, away from function ops;
  layout.json pinning untouched; never move user-placed ops.
- Verify numerically: custom pars exist with BIND mode, flipping a widget `Value0`
  moves the internal value, `get_errors` clean — then save.
- Panel UI cannot be screenshotted through the bridge; verification is structural.
