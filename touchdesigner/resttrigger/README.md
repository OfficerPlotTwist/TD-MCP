# cont_rest_trigger — GLSL Morph Rest Trigger

Fires a single CHOP trigger pulse the moment a blob-tracked hand (IR reflective sticker) **comes to rest** on the sticker. Instead of centroid velocity, it watches how much the blob's **silhouette shape** is changing frame-to-frame ("morph energy"): when the shape stops deforming (change → idle), it fires. The trigger stage is a verbatim clone of `/project1/trigger7` (adaptive `.85×running-max` threshold, `triggeron=decrease`).

Lives at `/project1/cont_rest_trigger`.

Cross-reference: [GLSL Morph Rest Trigger Design Spec](../../docs/superpowers/specs/2026-07-06-glsl-morph-rest-trigger-design.md) · [Implementation Plan](../../docs/superpowers/plans/2026-07-06-glsl-morph-rest-trigger.md) · [Blob Tracker README](../blobtrack/README.md)

---

## Inputs

| Connector | Type | Source | Purpose |
|-----------|------|--------|---------|
| `in1` | TOP 128² | `/project1/cont_blobtrack_glsl/out_mask` | Whole-frame binary silhouette (R=1 foreground). The morph source. |
| `in2` | CHOP | `/project1/blob_idx0` | Primary-blob row `[id,tx,ty,area,w,h]`. Only `area` is used — for the blob-present gate. Same source `trigger7` consumes. |

## Outputs

| Connector | Type | Op | Description |
|-----------|------|-----|-------------|
| `out_rest_trigger` | CHOP | outCHOP ← `math_gate` | **The deliverable.** 1-ch (`chan1`) shaped pulse (`trigger7` envelope: peak 1, peaklen 6 samp, decay 4 samp, release 4 frames), gated to 0 when no blob is present or the blob is smaller than `Minblobarea`. |
| `out_morph_energy` | CHOP | outCHOP ← `script_morph_energy` | Raw scalar morph energy (0..1), for tuning/monitoring. |
| `out_morph_viz` | TOP | outTOP ← `glsl_morph` | Per-pixel silhouette diff — what the heuristic "sees." |

---

## Morph energy

`morph_energy` = **mean of `|mask_t − mask_{t-1}|` over all pixels** = the fraction of silhouette pixels that flipped this frame. Scale-invariant (independent of marker size/distance). High while the shape deforms (hand moving/pressing/occluding), → 0 when the silhouette freezes.

The previous frame comes from a **Feedback TOP** (1-frame delay of its wired input — the reliable mode, not the Target-param path the blob tracker warns about; the graph is acyclic, so no cook loop). The diff is computed in `glsl_morph` (see `morph.frag`) and reduced to a scalar by `script_morph_energy`, a Script CHOP that `numpyArray`-reads the diff and returns its R-channel mean. (This reuses the blob tracker's GPU→CPU `numpyArray` idiom; `TOP to CHOP` is avoided because it does not reliably emit per-pixel samples in this build.)

## Trigger (clone of `trigger7`)

`morph_energy` → `trail_morph` (Trail CHOP, 3 s window) → `max_morph` (Analyze CHOP, maximum) gives the running max. `trigger_rest` (Trigger CHOP) uses `threshup = Threshfrac * op('max_morph')[0]` and `triggeron = decrease`: during the strum/press the silhouette churns and energy sets `max_morph`; when the hand settles, energy collapses and **decreases through 0.85×max** → one shaped pulse. All other params (`clamppeak`, `complete`, the peak/decay/release envelope, `rate=me.time.rate`, …) match `/project1/trigger7` verbatim.

`trigger_rest` names its output channel after its **input** (`morph_energy`), so a `rename_trig` Rename CHOP renames it to `chan1` before the gate — this is why `trigger_rest` stays a faithful `trigger7` clone rather than using its `renameto` param.

## Blob-present / min-size gate

`select_area` picks `area` from `in2` (renamed to `chan1`); `gate_present` (Expression CHOP) outputs `1.0` when a blob is present (`area>0` **or** the gate is disabled) **and** `area ≥ Minblobarea`, else `0.0`; `math_gate` (Math CHOP, combine=`mul`, input 2 ← `gate_present`) multiplies `trigger_rest × gate_present`. This suppresses a false "settle" when the sticker **leaves frame** (empty mask → energy collapse → spurious decrease) and rejects noise-sized blobs that would otherwise cause false triggers.

> **Wiring fix (2026-07-14):** `gate_present` was previously dangling (computed but wired to nothing), so neither gate had any effect on the output. It is now wired into `math_gate`'s second input with combine=`mul`, as originally intended.

### Nibble exclusion
- **Primary:** the `.85×running-max` adaptive threshold — a hand grazing the sticker edge produces energy far below 85% of the real landing morph's peak, so it can't arm a spurious cycle.
- **Secondary:** `Edgeclean` softens 1-px edge shimmer before differencing (off by default).
- **Vanish rejection:** the blob-present gate.
- **Noise-blob rejection:** `Minblobarea` hard-gates the output when the tracked blob is smaller than the configured area.

---

## Parameter Page: "Rest Trigger"

| Parameter | Internal | Default | Meaning |
|-----------|----------|---------|---------|
| Threshold Frac | `Threshfrac` | 0.85 | Multiplier on the running max → `trigger_rest.threshup`. |
| Window | `Windowsec` | 3.0 | Trail window (seconds) for the running max. Matches `trail2`. |
| Edge Clean | `Edgeclean` | 0 | Blur radius applied to the mask before differencing (nibble pre-filter). **0 = off**, enforced by `switch_clean` (selects the raw mask, true passthrough) — the Blur TOP's `size` clamps to a 1-px minimum, so bypass is done via the switch, not `size=0`. |
| Present Gate | `Presentgate` | On | Enable the `blob_idx0.area>0` gate. |
| Min Blob Area | `Minblobarea` | 0 (set to 4 live) | Minimum blob `area` (pixels at blobtrack `Procres`) required for the trigger output to pass. Blobs smaller than this hard-gate `out_rest_trigger` to 0 — rejects noise specks that cause false triggers. 0 = off. |

---

## Parameter Page: "Trigger"

The `trigger_rest` Trigger CHOP's envelope params are exposed on the container as a **Trigger** tab, two-way **bound** to the internal op (edit either side). `threshup` is *not* exposed — it stays expression-driven by `Threshfrac × running-max` (the adaptive threshold).

| Parameter | Internal (`trigger_rest`) | Default |
|-----------|---------------------------|---------|
| Release Threshold | `threshdown` | 0.0 |
| Re-Trigger Delay (s) | `retrigger` | 0.0 |
| Min Trigger Length (s) | `mintrigger` | 0.0 |
| Trigger On | `triggeron` | decrease |
| Manual Trigger | `trigger` (pulse) | — |
| Delay (samples) | `delay` | 0.0 |
| Attack (samples) | `attack` | 0.0 |
| Attack Shape | `ashape` | halfcos |
| Peak Level | `peak` | 1.0 |
| Peak Length (samples) | `peaklen` | 6.0 |
| Decay (samples) | `decay` | 4.0 |
| Decay Shape | `dshape` | halfcos |
| Sustain Level | `sustain` | 0.0 |
| Min Sustain (s) | `minsustain` | 0.0 |
| Release (frames) | `release` | 4.0 |
| Release Shape | `rshape` | halfcos |

> **Manual Trigger is a parexec, not a bind:** binding a container pulse to a Momentary par does **not** forward pulses in this build. `parexec_trigpulse` (Parameter Execute DAT watching `..`/`Trigpulse`, `onPulse`) calls `op('trigger_rest').par.trigger.pulse()` instead. Useful for testing the envelope and downstream consumers without a live settle event.

---

## Internal Pipeline

```
in1 out_mask ─► switch_clean ─┬───────────────► glsl_morph ─► script_morph_energy ─┬─► out_morph_energy
              (0=raw / 1=blur) │  feedback_mask ─►  (in1)      (numpyArray mean)     │
   top_maskclean(blur)◄─in1    └─► feedback_mask ─┘   └► out_morph_viz               ├─► trail_morph ─► max_morph
                                                                                     │        └─► trigger_rest.threshup = Threshfrac*max_morph[0]
in2 blob_idx0.area ─► select_area ─► gate_present ──────────────────────────────────────┐ (mul)
                                              trigger_rest ─► rename_trig ─► math_gate ─┴─► out_rest_trigger
```

Mask-domain TOPs use **Nearest Pixel** filtering. The Script CHOP reduction is the one deliberate *averaging* step.

---

## Known Limitations / Risks

- **Feedback TOP 1-frame delay** — relied on for `mask_{t-1}`. If it misbehaves in a future build, a `Cache TOP` (size 2, index -1) is the drop-in fallback.
- **Tiny sticker SNR** — if the silhouette is only a few pixels, absolute energy is small but scale-consistent; `Threshfrac` on the running max keeps it relative. Raise `Edgeclean` and/or `Windowsec` if noisy.
- **Bouncy landing** — a settle → small rebound → settle could double-fire; `retrigger`/`mintrigger` are at `trigger7`'s 0 defaults, raise if observed.
- **Morph responsiveness needs a moving feed** — frame-differencing a static image is 0 by definition, so the dynamic firing behavior is validated live (see below), not from an idle feed.

## Verification status

Structural + per-stage numerical checks pass (op wiring, shader compile, `numpyArray` reduce, running-max, `trigger7` param match `== []`, gate logic, custom-par binding, `switch_clean` passthrough). **Pending live behavioral check** (feed running): confirm `morph_energy` rises during motion, one pulse fires on settle, a small edge graze does not fire, and removing the blob does not fire.
