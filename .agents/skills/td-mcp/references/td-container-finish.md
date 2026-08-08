# Container Finishing Pass — param tab + panel UI

Apply this after building or substantially modifying any container COMP, before the final save. Also applies on request to an existing container ("give X a UI").

The finished container has exactly two surfaces, built in this order:

1. A **custom parameter tab** — the full curated control set (up to 8 params).
2. A **control panel** — a small performer-facing subset: 1–2 displays on top, 2–4 controls below.

The panel is a curated excerpt of the tab, never a mirror of it. If you find yourself giving every custom par a widget, you skipped the ranking step.

## Step 1 — Analyze the container's function

Census the children (op families + named ops). Rank exposure candidates in three tiers:

1. **Live-performance touches** — switches, on/off gates, trigger/reset points, speeds.
2. **Look/behavior tuning** — thresholds, levels, periods, colors.
3. **Diagnostics** — the output op, counts, active channels.

Concrete signals:

| Found in network | Expose as |
|---|---|
| Switch TOP/CHOP with hardcoded index | Menu (3+ inputs) or Toggle (2 inputs) |
| Hardcoded constant in Level / Math / Threshold / Speed / LFO | Ranged float |
| Feedback loop, counter, Trigger CHOP | Pulse (reset) |
| Final `out` TOP (or most-composited TOP) | Panel display #1 |
| Count / level / analysis CHOP or status DAT | Panel display #2 |

## Step 2 — Custom parameter tab (up to 8 params)

- `appendCustomPage` named for the function (`Blobtrack`, `Particles`) — never generic `Custom`.
- TD-style capitalized names (`Threshold`, `Active`, `Resetall`).
- Wiring is **internal-binds-up**: the internal op's par gets
  `bindExpr = "parent().par.X"` and `mode = ParMode.BIND`. The container stays a
  self-contained, palette-savable component.
- **Do not add master_controls channels in this pass.** The bus is for cross-component
  and global wiring, which is a separate, explicitly requested task. The repo's
  "params go through master_controls" rule governs project-scope value changes,
  not a component's own encapsulation.
- Defaults = current live values (read them first), so adding the tab changes nothing.
- Ranges from the internal par's normMin/normMax or domain knowledge; clamp where
  the internal op clamps (e.g. Blur size min 1).
- Pulses are never bound — BIND silently drops pulses. Route them through a
  Parameter Execute DAT on the container (`onPulse` → `internal.par.resetpulse.pulse()`).

## Step 3 — Control panel

The panel contains, top to bottom:

1. **Displays (1–2).** The main output TOP is always display #1 when the container
   has visual output — a performer needs to see what they're steering. Display #2,
   if earned, is the most informative CHOP/DAT readout (count, level, status).
   Build displays as opviewer COMPs (or a containerCOMP with a background TOP).
   Display TOPs: nearest filtering, and stay within the 1280×1280 non-commercial
   cap (add a Fit/Resolution TOP if the source is larger).
2. **Control row (2–4 controls).** Any mix of Basic Widgets buttons and sliders,
   bound to the top-ranked tier-1 custom pars. Four is the ceiling, not the target —
   a container with one meaningful live control gets one widget.

Rules:

- Widgets and displays are **children of the container**, laid out on its own panel
  (auto-layout `align` beats hand-placed bottom-left-origin math when the stack is simple).
- Instantiate from the Basic Widgets palette via the holder/loadTox/copyOPs lift
  pattern in `touchdesigner-ui.md` — never bare sliderCOMP/buttonCOMP.
- Widgets bind `Value0` to the **container's custom pars** (`parent().par.X` from the
  widget, BIND mode), so panel and tab always agree. Momentary buttons go through a
  Parameter Execute DAT (`onValueChange` rising edge → `parent().par.Xpulse.pulse()`).
- Label everything via `Widgetlabel`.
- Finish with `viewer = True` on the container (op attribute, not a par) so the
  panel actually renders.

## Guardrails

- `save_checkpoint` on the container before mutating. `project.save()` only if the
  project has a real on-disk file — on an untitled project it pops a modal that
  freezes the bridge.
- Never touch `/project1/MCP_Server`.
- New ops (widgets, opviewers, parexecs) go in a tidy row inside the container,
  away from the function chain; never move user-placed ops; layout.json pinning
  is untouched unless asked.
- Scope: this is a finishing pass, not a refactor. No palette re-saves, no
  layout.json edits, no preset systems unless explicitly requested — park those.

## Verification (numeric — panels can't be screenshotted)

1. Custom pars exist; internal pars report `ParMode.BIND` with the right bindExpr.
2. Set a custom par via `set_par_value`, read the internal par back — it follows.
   Restore the original value after each probe.
3. Set a widget's `Value0`, confirm the internal par follows (proves the full chain).
4. Pulse path: pulse the custom par, verify the effect numerically (e.g. a stored
   counter incremented by the parexec).
5. `get_errors` on the container matches the pre-pass baseline.
6. Only after all checks pass: checkpoint/save.
