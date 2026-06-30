# Five Overlapping Round-Robin Sweeps — Design

**Date:** 2026-06-30
**Location:** live TouchDesigner session, network `/project1`
**Status:** approved, ready for implementation plan

## Goal

Take the existing single "animated ramp on trigger" chain and turn it into **5 independent
sweep units** that fire one at a time via an external round-robin pulse, with envelopes
allowed to **overlap** (a unit can still be releasing when the next fires). All units share
one keyframe definition. Expose a live count of currently-active sweeps.

## Existing chain (the unit being replicated)

In `/project1`, the selected chain works like this:

- `ramp1_keys` (Table DAT, 6×5, header `pos r g b a`) — keyframes. The middle three key
  positions are **expressions**: `op('ramp_control')[0] + .3`, `op('ramp_control')[0]`,
  `op('ramp_control')[0] - .3`. This paints a white band (soft ±0.3 edges) centered on the
  trigger value.
- `eval1` (Evaluate DAT, `output=evaluate`, `xfirstrow=True`) — resolves those expression
  cells into concrete numbers. Header row is preserved (not evaluated).
- `ramp1` (Ramp TOP, `type=vertical`, `period=1`) — `dat` par = `eval1`; renders the gradient
  from the resolved keys. `ramp2` (Ramp TOP) — second ramp.
- `comp2` (Composite TOP) — composites `ramp2` over `ramp1` → `comp3`.
- `ramp_control` (Trigger CHOP) — envelope: attack 1.5s (halfcos) → peak 1.0 → release 0.3s.
  Channel `chan1` (referenced as `op('ramp_control')[0]`) is the 0→1→0 sweep value.

The animation is therefore: **trigger envelope → key positions (via the expression cells) →
Evaluate DAT resolves → Ramp TOP redraws.** Nothing else references the trigger.

## Key constraint

A *single* shared Evaluate DAT cannot drive 5 independently-animating ramps: its output is
one table reflecting one trigger's value at a time. Independent overlap requires each unit to
resolve the keys against **its own** trigger. We honor "share keys + eval" as **the keyframe
template and eval logic are authored once and instantiated per unit** (edit colors/offsets in
one place) — not literally one DAT feeding all five.

This is feasible flat because the Evaluate DAT binds `me` to itself when evaluating input
cells (verified empirically: a cell `me.name` resolves to the eval DAT's own name; `me.path`
to its path; `xfirstrow=True` keeps the header row from being evaluated). So one shared table
can derive each unit's trigger from the evaluating DAT's name.

## Target architecture (flat ops, `_0.._4` suffixes; `_0` = converted existing chain)

### Shared
- **`ramp_keys_master`** (Table DAT) — the current `ramp1_keys`, renamed, with the three
  sweep cells rewritten to be unit-relative:
  - `op('trig_' + me.name.split('_')[-1])[0] + .3`
  - `op('trig_' + me.name.split('_')[-1])[0]`
  - `op('trig_' + me.name.split('_')[-1])[0] - .3`

  Static rows (`0` and `1`) and the header are unchanged. This DAT's output **fans out** to
  all five `eval_N` inputs.

### Per unit `N` in `0..4`
- **`trig_N`** (Trigger CHOP) — clone of `ramp_control`; independent envelope.
- **`eval_N`** (Evaluate DAT) — input wired from `ramp_keys_master`; `output=evaluate`,
  `xfirstrow=True`. Resolves keys against `trig_N` (via the `me.name` derivation).
- **`rampA_N`** (Ramp TOP, was `ramp1`) — `dat` par = `eval_N`.
- **`rampB_N`** (Ramp TOP, was `ramp2`).
- **`comp_N`** (Composite TOP, was `comp2`) — `rampB_N` over `rampA_N`.

Unit `_0` is produced by **renaming/repurposing** the existing ops
(`ramp_control`→`trig_0`, `eval1`→`eval_0`, `ramp1`→`rampA_0`, `ramp2`→`rampB_0`,
`comp2`→`comp_0`, `ramp1_keys`→`ramp_keys_master`). Units `_1.._4` are clones.

### Round-robin sequencer (external pulse advances)
- **`seq_advance`** (Null/Constant CHOP) — the input the user wires their advance pulse into.
- **`seq_exec`** (CHOP Execute DAT) — watches `seq_advance` for an off→on edge. On each pulse:
  1. read current index `i` from op storage (default 0),
  2. pulse `op('trig_'+str(i)).par.trigger`,
  3. store `i = (i + 1) % 5`.

  Index lives in `seq_exec.store/fetch` (no extra CHOP feedback loop — avoids cook-dependency
  loops; consistent with the store/fetch pattern for handing state between script ops).

### Aggregation
- **`comp_all`** (Composite TOP) — composites `comp_0..comp_4` over each other → final output.
- **`master_controls`** (existing Null CHOP bus; currently carries `mask_reset`) — add channel
  **`num_active_sweep`** = count of units whose envelope is currently active:
  - `trig_merge` (Merge CHOP) merges `trig_0[0]..trig_4[0]`,
  - a Logic/Math CHOP computes per-channel `>0` then **sums** → single channel,
  - rename to `num_active_sweep` and merge it into `master_controls`'s input chain
    **alongside** the existing `mask_reset` source (do not drop `mask_reset`).

"Active" = envelope value `> 0`, i.e. from fire through the full attack/peak/release tail.
This is what makes overlap observable: `num_active_sweep` can read 2+ during overlap.

## What stays untouched
`comp3` and any downstream consumers of the old `comp2` are preserved. Because `comp2` becomes
`comp_0`, references to `comp2` must be repointed (checked during implementation). `ramp_control`
becomes `trig_0` — same repoint check.

## Out of scope
- The source of the advance pulse (user wires it into `seq_advance`).
- Any tempo/clock generation (cadence is external by decision).
- Visual restyling of the ramps/colors beyond what already exists.

## Verification (numeric/functional — panels aren't screenshottable via the bridge)
1. Each `trig_N` fires independently; `eval_N` resolves distinct key positions per its own `trig_N`.
2. A sequence of pulses into `seq_advance` fires `trig_0,1,2,3,4,0,…` in order (read storage / channel values).
3. With overlapping fires, `master_controls['num_active_sweep']` reads `>1`.
4. `mask_reset` still present on `master_controls`.
5. No cook-dependency-loop errors (`get_errors`); existing `comp3` path intact.

## Save discipline
- `project.save()` for a restore point before the first mutating edit.
- `save_checkpoint` on `/project1` before the destructive rename/convert of the existing chain.
- Verify, then `project.save()` again. Never combine bulk destroy with force-cook.
