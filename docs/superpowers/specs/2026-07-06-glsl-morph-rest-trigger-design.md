# GLSL Morph-Heuristic Rest Trigger — Design Spec

**Date:** 2026-07-06
**Status:** Approved design, pre-implementation
**Container:** `/project1/cont_rest_trigger` (new)
**Related:** [GLSL Blob Tracker README](../../../touchdesigner/blobtrack/README.md) · [Blob Tracking Design](2026-06-28-glsl-top-blob-tracking-design.md)

---

## 1. Goal

Emit a single CHOP trigger pulse the moment a blob-tracked hand (IR reflective sticker) **comes to rest** on the sticker — captured in `C:\Users\NICKESCHEN\dev\creative\TD_projects\TDMovieOut.0.mov` (128×128, 60 fps): a single small sticker blob whose silhouette deforms as the hand interacts, then stabilizes when the hand settles.

"Comes to rest" is detected as a **shape-morph heuristic**, not centroid velocity: watch how much the blob's *silhouette* is changing frame-to-frame ("morph energy"). When morph energy transitions from **changing → idle**, fire. Small edge occlusions (the strumming hand grazing the sticker edge "just a bit") must stay below the trigger threshold so they neither arm nor block the event.

### Success criteria
1. During hand motion/interaction, `morph_energy` rises measurably above its resting floor.
2. When the hand settles, exactly **one** pulse fires as morph energy decays back through the threshold.
3. A small edge graze (nibble) does **not** produce a pulse.
4. The sticker **leaving frame** (silhouette vanishing) does **not** produce a pulse.
5. The Trigger CHOP configuration matches `/project1/trigger7` verbatim (see §5).

---

## 2. Non-Goals (YAGNI)

- No centroid-velocity path (explicitly rejected in favor of the morph heuristic).
- No multi-blob disambiguation — the scene is a single sticker; whole-frame `out_mask` is the morph source.
- No per-blob region masking of the morph (whole-frame diff is sufficient).
- No GPU feedback *loop* for state (the Trigger CHOP holds the settle state; the only feedback is a plain 1-frame mask delay — acyclic).
- No changes to `cont_blobtrack_glsl` or to `trigger7`/`select2`/`blob_idx0`/`max_biggest_blob` (we read them, we don't modify them).

---

## 3. Inputs & Outputs

`cont_rest_trigger` is a container COMP with:

**Inputs**
| Connector | Type | Source | Purpose |
|-----------|------|--------|---------|
| `in1` (TOP) | TOP 128² | `/project1/cont_blobtrack_glsl/out_mask` | Whole-frame binary silhouette (R=1 foreground). The morph source. |
| `in2` (CHOP) | CHOP | `/project1/blob_idx0` | Primary-blob row `[id,tx,ty,area,w,h]`. Used only for the **blob-present gate** (`area > 0`). Same source `trigger7` consumes. |

**Outputs**
| Connector | Type | Op | Description |
|-----------|------|-----|-------------|
| `out_rest_trigger` | CHOP | outCHOP ← gate | The gated settle pulse. 1-ch envelope pulse (`chan1`), shaped per `trigger7` (§5). This is the deliverable. |
| `out_morph_energy` | CHOP | outCHOP ← reduce | The raw scalar morph energy (0..1), exposed for tuning/monitoring. |
| `out_morph_viz` | TOP | outTOP ← `glsl_morph` | Per-pixel silhouette diff, for visual debugging of what the heuristic "sees." |

---

## 4. Internal Pipeline

All mask-domain TOPs use **Nearest Pixel** filtering (`inputfiltertype=nearest`, `filtertype=nearest`) per project convention, so the binary silhouette is not blurred. The single deliberate exception is the reduction step (§4.4), which must *average*.

### 4.1 Optional edge pre-filter — `top_maskclean` (TOP)
`in1` (out_mask) → optional light **erode** (or 1px box) to strip single-pixel edge shimmer before differencing. Default amount **0** (off): the adaptive threshold (§5) is the primary nibble defense, and pre-filtering is a belt-and-suspenders knob. Nearest filtering.

### 4.2 Previous-frame delay — `feedback_mask` (Feedback TOP)
Input = `top_maskclean`. Output = the mask one frame earlier. This uses Feedback's **reliable behavior — a 1-frame delay of its wired input** — *not* the Target-TOP path the blob-tracker README documents as quirky in this build. The graph stays **acyclic**: `feedback_mask` reads only the upstream mask; the diff (§4.3) reads `(mask_t, mask_{t-1})`; nothing reads the diff back into the mask. No cook-dependency loop.
- **Fallback:** if Feedback misbehaves, a `Cache TOP` (Cache Size 2, read index -1) yields the same 1-frame delay.

### 4.3 Morph diff — `glsl_morph` (GLSL TOP)
Inputs: `in0 = top_maskclean` (mask_t), `in1 = feedback_mask` (mask_{t-1}). Fragment shader, per pixel:
```glsl
float a = texture(sTD2DInputs[0], vUV.st).r;   // mask_t   (0 or 1)
float b = texture(sTD2DInputs[1], vUV.st).r;   // mask_{t-1}
float d = abs(a - b);                          // 1.0 where the silhouette flipped this frame
fragColor = vec4(d, d, d, 1.0);
```
Output = `out_morph_viz`. 128², 32-bit float, nearest.

### 4.4 Reduce to scalar — `morph_energy` (CHOP)
Reduce the diff TOP to a single number = **mean of `d` over all pixels = fraction of silhouette pixels that flipped this frame** (scale-invariant: independent of marker size/distance).
- Recommended: downsample `glsl_morph` to 1×1 with an *averaging* filter (Resolution/box average, i.e. NOT nearest here), then `TOP to CHOP` (single sample) → channel `morph_energy`.
- Fallback: `TOP to CHOP` the 128² diff → `Math CHOP` (sum, then ÷16384).
Exposed as `out_morph_energy`.

### 4.5 Running max — `trail_morph` → `max_morph`
Mirror `trigger7`'s adaptive-threshold chain exactly:
- `trail_morph` (**Trail CHOP**): input `morph_energy`, `wlength = 3.0 seconds`, `capture = timeslice` — matches `trail2`.
- `max_morph` (**Analyze CHOP**): `function = maximum` over the trail — matches `max_biggest_blob`. Yields the running-max of morph energy over the last 3 s.

### 4.6 Trigger — `trigger_rest` (Trigger CHOP)
Input = `morph_energy`. All parameters cloned from `trigger7` (§5). The key ones:
- `threshup = .85 * op('max_morph')[0]` — adaptive threshold at 85% of the running max.
- `triggeron = decrease` — fire when morph energy **falls back through** the threshold (change → idle).
- `clamppeak = on`, `complete = on`; envelope `peak 1 / peaklen 6 samp / decay 4 samp / release 4 frames` (halfcos).

### 4.7 Blob-present gate — `gate_present` → `out_rest_trigger`
Guards against the sticker **leaving frame** reading as a settle (empty mask → energy collapse → false decrease).
- `gate_present`: `1.0` when `op('blob_idx0')['area'] > 0`, else `0.0` (a Logic CHOP on `in2`'s `area`, or an Expression/Math CHOP).
- Final: `out_rest_trigger = trigger_rest.chan1 * gate_present` (Math CHOP multiply). A pulse survives only while a blob is actually present.

### Dataflow summary
```
in1 out_mask ─► top_maskclean ─┬─────────────────► glsl_morph ─► (avg 1x1) ─► morph_energy ─┬─► out_morph_energy
                               │   feedback_mask ──►  (in1)         │                        │
                               └──► feedback_mask ──────────────────┘  out_morph_viz         ├─► trail_morph ─► max_morph
                                                                                             │        └─► trigger_rest.threshup = .85*max_morph[0]
in2 blob_idx0.area ─► gate_present ──────────────────────────────────► trigger_rest ─► × ─► out_rest_trigger
```

---

## 5. `trigger7` Parameter Match (captured 2026-07-06)

`trigger_rest` reproduces these `/project1/trigger7` values verbatim. Only `threshup`'s referenced op changes (`max_biggest_blob` → `max_morph`).

| Param | Value | Param | Value |
|-------|-------|-------|-------|
| `threshold` | on | `triggeron` | `decrease` |
| `threshup` | `.85 * op('max_morph')[0]` (expr) | `multitrigger` | `ignore` |
| `threshdown` | 0.0 | `clamppeak` | on |
| `retrigger` | 0.0 (seconds) | `complete` | on |
| `mintrigger` | 0.0 (seconds) | `updateonce` | off |
| `delay` | 0.0 (samples) | `remainder` | `extend` |
| `attack` | 0.0 (samples) | `ashape` | `halfcos` |
| `peak` | 1.0 | `peaklen` | 6.0 (samples) |
| `decay` | 4.0 (samples) | `dshape` | `halfcos` |
| `sustain` | 0.0 | `release` | 4.0 (frames) |
| `rshape` | `halfcos` | `channame` | `chan1` |
| `rate` | `me.time.rate` (expr) | `timeslice` | on |

---

## 6. Why This Detects "Change → Idle" and Excludes Nibbles

- **Landing:** during the strum/press the silhouette churns → `morph_energy` climbs and sets `max_morph`. When the hand settles, the silhouette freezes → energy collapses toward 0 → it **decreases through `.85 * max_morph`** → `triggeron=decrease` emits one shaped pulse. This is the "morphing goes from change to idle" event.
- **Nibble exclusion (primary):** the `.85 × running-max` threshold is adaptive. A hand grazing the sticker edge produces morph energy far below 85% of the real landing morph's peak, so it neither arms a new cycle nor blocks idle.
- **Nibble exclusion (secondary):** optional `top_maskclean` erode removes 1-px edge flicker before it becomes energy.
- **Vanish rejection:** `gate_present` zeroes the output when `area == 0`, so a sticker leaving frame can't fire.

---

## 7. Custom Parameter Page — "Rest Trigger"

Exposed on `cont_rest_trigger` for tuning (internals set to §5 values):

| Parameter | Internal | Default | Meaning |
|-----------|----------|---------|---------|
| Threshold Frac | `Threshfrac` | 0.85 | The `.85` multiplier on the running max (drives `trigger_rest.threshup`). |
| Window | `Windowsec` | 3.0 | Trail window (seconds) for the running max. Matches `trail2`. |
| Edge Clean | `Edgeclean` | 0 | Erode/box amount on the mask before differencing (nibble pre-filter). 0 = off. |
| Present Gate | `Presentgate` | On | Enable the `blob_idx0.area > 0` gate. |

---

## 8. Placement & Save Discipline

- Create `cont_rest_trigger` in `/project1`, `nodeX/nodeY` set far from the existing node cluster (network position ≠ panel position) so the patch stays readable.
- Follow the bridge save discipline: `save_checkpoint` on `/project1` (or `project.save()` if titled) **before** the first mutating edit; build; **verify** (§9); only then save again. On the untitled session, prefer `save_checkpoint` over `project.save()` (avoids the untitled-save modal that hangs the bridge).
- Do **not** press any server-control button on `/project1/TD_MCP`.

---

## 9. Verification / Testing

1. **Structural:** `get_operator_info` on every new op; confirm wiring matches §4; `get_errors` clean.
2. **Signal sanity (live):** with the blob tracker fed, confirm `out_morph_energy` sits near 0 when still and rises when the silhouette is disturbed; confirm `max_morph` tracks the recent peak; confirm `trigger_rest.threshup` evaluates to `.85 × max_morph`.
3. **Event correctness:** drive motion → rest; confirm exactly one pulse on `out_rest_trigger` as energy decays through threshold. Confirm a small edge graze stays sub-threshold (no pulse). Confirm removing the blob (`area→0`) yields no pulse.
4. **Offline replay:** `TDMovieOut.0.mov` is the *viz* output (red overlay), not raw IR. For an offline sanity pass, threshold its R channel to reconstruct an approximate silhouette and run it through the morph chain to eyeball energy peaks vs. settle points. Authoritative validation is live `out_mask`.
5. Panels/pulses aren't screenshot-able through the bridge — verify numerically (`get_par_value` on `out_rest_trigger`) or ask the user to glance at a CHOP viewer.

---

## 10. Open Risks

- **Feedback TOP delay reliability** in this build — mitigated by the `Cache TOP` fallback (§4.2).
- **Morph energy magnitude** for a *small* sticker: if the silhouette is only a few pixels, whole-frame mean energy is tiny but still scale-consistent; `Threshfrac` on the running max keeps it relative, so absolute smallness is fine. If SNR is poor, `Edgeclean` and/or a longer `Windowsec` help.
- **Double-fire on a bouncy landing** (settle → small rebound → settle): `retrigger`/`mintrigger` are at `trigger7`'s 0 defaults; raise if observed.
