# GLSL TOP Blob Tracking — Design Spec

**Date:** 2026-06-28
**Status:** Approved (architecture); pending spec review
**Target:** A self-contained TouchDesigner container `cont_blobtrack_glsl` implementing
pure-GPU blob detection + tracking, built live via the TD_MCP bridge.

> **⚠️ Superseded in places by the as-built component.** During implementation several
> approaches in this design changed for TD-build reasons. The authoritative description of
> what was actually built is [`touchdesigner/blobtrack/README.md`](../../../touchdesigner/blobtrack/README.md).
> Key deviations: §3 Stage 4 GPU **scatter** (GLSL MAT → Render TOP additive) became a GLSL
> **gather** (TD's convertSOP couldn't emit GL_POINTS); the §6 **TOP-to-CHOP** output became a
> **scriptCHOP** (`numpyArray` readback); `out_viz` draws **no ID numbers / markers** (tinted label
> colors only); and `Maxblobs` is currently **inert** (buffers are `Procres²`). This document is kept
> as the original design record.

---

## 1. Goal

Build a reusable container component that takes any TOP image input and produces, **entirely on
the GPU** (GLSL TOPs + a GLSL MAT scatter render; no Python in the per-frame hot path):

- a clean binary blob **mask**,
- **connected-component labels** (each blob gets a distinct label),
- per-blob **centroid + area** (and bounding box where cheap),
- frame-to-frame **persistent IDs**, and
- a downstream-usable **CHOP** of blob data (`id, tx, ty, area, w, h`).

Approach chosen: **Pure GPU** (jump-flood connected-component labeling + GPU centroid reduction +
feedback-based ID association). Python/CHOP-CPU readback is explicitly avoided in the tracking path;
the only CHOP conversion is a standard `TOP to CHOP` at the very end for downstream consumption.

---

## 2. Public interface (container as a black box)

The container is the single unit consumers interact with. Internals can change without breaking
consumers as long as this interface holds.

### Input
- One **TOP input** on the container, realized by an `In TOP` (`in1`) inside. Any source (the
  existing `null_optitrack_cam`, a camera, a movie) wires into the container's input connector.
  Nothing about the source is hardcoded.

### Custom parameters — page "Blob Track"
| Par | Type | Default | Purpose |
|-----|------|---------|---------|
| `Threshold` | float 0–1 | 0.5 | Luminance cutoff for foreground. |
| `Minarea` | int (px) | 8 | Blobs below this pixel count are discarded. |
| `Procres` | int (menu) | 128 | Working/downscale resolution (square). Drives JFA pass count and scatter buffer size. |
| `Matchradius` | float (norm) | 0.08 | Max centroid distance (normalized) to carry an ID forward. |
| `Maxblobs` | int | 64 | Track-table slot count / max simultaneously tracked blobs. |
| `Showoverlay` | toggle | On | Whether `out_viz` composites markers/IDs over the input. |

### Outputs (each a `Null TOP`/CHOP at the container edge)
- `out_mask` — binary foreground mask (working res).
- `out_labels` — colorized connected components (hash(label)→color), for visual debugging.
- `out_viz` — full-res input with blob markers + ID numbers overlaid (gated by `Showoverlay`).
- `out_blobs` — **CHOP** with one sample per active blob: channels `id, tx, ty, area, w, h`.
  `tx/ty` normalized 0–1 in input space, origin bottom-left (TD panel convention).

---

## 3. Internal GPU pipeline

All per-frame stages are fragment shaders (GLSL TOP) except Stage 4, which is a vertex-scatter
(GLSL MAT → Render TOP additive). Data textures are **32-bit float** (RG32F / RGBA32F) so labels
and coordinate sums are exact.

### Stage 1 — Mask (`glsl_mask`, GLSL TOP)
- Downscale input to `Procres` (a `Resolution`/`Fit` upstream or set the GLSL TOP resolution).
- Compute luminance, threshold at `Threshold` → binary foreground.
- Output: R = 1.0 foreground / 0.0 background (RG32F; G reserved).

### Stage 2 — Seed (`glsl_seed`, GLSL TOP)
- For each foreground pixel, label = its own integer coordinate `(x, y)` written to RG (the blob's
  "root" candidate). Background = sentinel (e.g. a large value / `-1` sentinel encoded so `min`
  comparisons treat it as +inf).
- Output: RG32F label field.

### Stage 3 — Labeling: Jump-Flood CCL (`glsl_jfa` ×N, unrolled chain)
- An **unrolled chain** of GLSL TOPs, one per pass. Step sizes `uStep = Procres/2, /4, …, 1`
  (≈log₂(Procres) passes), then **2–3 additional `uStep = 1` relaxation passes** to repair
  gap-leak (JFA at large steps can bridge across background gaps; 1-ring relaxation corrects it).
- Each pass: for the 8 neighbors at distance `uStep`, if that neighbor is foreground and connected,
  adopt the **minimum root label**. Background pixels stay sentinel and never propagate.
- All passes share **one Text DAT** as their pixel-shader source; each GLSL TOP differs only by its
  `uStep` uniform. Unrolled (not a feedback loop) → deterministic, no temporal lag, easy to verify
  pass-by-pass.
- Output of the final pass: every foreground pixel carries its blob's stable root coordinate; pixels
  sharing a root belong to one component.

### Stage 4 — Centroid/area reduction via GPU scatter
GLSL TOPs gather only; to reduce *by label* we scatter on the vertex side.
- `grid1` (**Grid SOP**): one point per working pixel (`Procres × Procres` points).
- `geo_scatter` (**Geometry COMP**) rendered by `glsl_scatter` (**GLSL MAT**):
  - Vertex shader samples the final label texture at the point's pixel. If foreground, it sets the
    point's clip position to the **root label's slot** (root linear index → 2D slot in a
    `Procres × Procres` buffer) and emits color `(x, y, 1, 0)`.
  - Background points are discarded (moved off-screen / zero contribution).
- `render_centroid` (**Render TOP**), ortho camera, **additive blending**, 32-bit float,
  resolution = slot space. Result per occupied slot: `(Σx, Σy, count, –)`.
- `glsl_centroid` (GLSL TOP): centroid = `(Σx/count, Σy/count)`, area = `count`; zero out slots with
  `count < Minarea`. Output: occupied slots hold `(cx, cy, area, valid)`.

Note: with label = root coordinate, distinct blobs occupy distinct slots; slot collisions are only
possible if two roots share a linear index, which cannot happen (roots are unique pixel coords).

### Stage 5 — ID association (`glsl_idtrack` + Feedback TOP)
The one inherently-serial part, done on GPU via a small feedback-held **track table**
(`Maxblobs × 1` texture; each texel = `id, cx, cy, age`).
- Each frame, for every current centroid slot, find the nearest previous-track within `Matchradius`:
  carry that track's `id` forward and update its centroid/age.
- Unmatched current blobs mint a **new id** from a GPU-held monotonic counter (a 1-px feedback
  texel). Unmatched previous tracks age out after a small grace count.
- Output: updated track table (→ Feedback TOP for next frame) and a current-frame
  `(id, cx, cy, area)` table texture.

### Stage 6 — Visualization + CHOP out
- `glsl_labelviz` (GLSL TOP): hash(label)→color over the mask → `out_labels`.
- `glsl_overlay` (GLSL TOP): composite blob markers (and, if cheap, ID-tinted dots) over the
  full-res input, gated by `Showoverlay` → `out_viz`.
- `topto_blobs` (**TOP to CHOP**) on the Stage-5 table texture → renamed channels
  `id, tx, ty, area, w, h` → `out_blobs`. (`w/h` from bbox if computed in Stage 4; otherwise derived
  from area as a circular-equivalent radius and flagged in the spec as approximate.)

---

## 4. Data flow summary

```
in1 (TOP) ──> glsl_mask ──> glsl_seed ──> glsl_jfa×N ──┬─> glsl_labelviz ─> out_labels
                                                        │
                                  grid1 ─> geo_scatter ─┴─> render_centroid ─> glsl_centroid
                                                                                   │
                                                                 glsl_idtrack <────┤
                                                                   │   ↑           │
                                                              feedback_id          │
                                                                   │               │
                                                                   ├─> topto_blobs ─> out_blobs
                                                                   └─> glsl_overlay <── in1
                                                                            └─> out_viz
glsl_mask ─> out_mask
```

---

## 5. Build & verification order (incremental, bridge-safe)

Build in stage order; verify each before the next. This guarantees a working GPU blob **detector**
(stages 1–4) even if **ID stability** (stage 5) needs iteration.

1. Scaffold container + `in1` + custom par page + a test source wired in (use `null_optitrack_cam`
   or a temporary Movie/Noise source for development).
2. Stage 1 mask — verify visually (`take_screenshot` on `out_mask`) and numerically.
3. Stage 2 seed — verify label field is sane (sample a few foreground texels via TOP-to-CHOP).
4. Stage 3 JFA chain — verify each pass converges; final pass: pixels in one blob share one root
   (sample with a known synthetic input of 2–3 separated blobs).
5. Stage 4 scatter reduction — verify centroid/area against the synthetic input (known positions).
6. Stage 5 ID association — verify IDs persist as a synthetic blob translates across frames; tune
   `Matchradius`.
7. Stage 6 viz + `out_blobs` CHOP — verify channel values downstream.

### Bridge / TD discipline (from CLAUDE.md, do not skip)
- `save_checkpoint` on the new container before any bulk-destructive edit; never combine bulk
  destroy with force-cook in one script.
- `execute_script("project.save()")` only after a stage verifies — but note: an **untitled** project
  pops a modal that hangs the bridge, so use `save_checkpoint` for snapshots if the project is
  untitled.
- **Never** press Start/Restart on `/project1/TD_MCP`.
- New top-level container gets `nodeX/nodeY` set far from the existing cluster.
- `execute_script` runs in a wrapper where nested `def`s can't see top-level names — walk op trees
  **iteratively**, keep helpers inline.
- Panels/control UI can't be screenshotted; TOP outputs (`out_mask`, `out_labels`, `out_viz`) **can**
  be via `take_screenshot`. Verify data outputs numerically via TOP-to-CHOP.

---

## 6. Risks & tradeoffs

- **JFA gap-leak:** large-step JFA can bridge separate blobs. Mitigated by 1-ring relaxation passes
  and modest `Procres`. If leak persists on real footage, fall back to pure iterative 1-ring label
  propagation (more passes, slower, but leak-free).
- **ID churn (Stage 5):** the highest-risk component. Pure-GPU association via feedback is finicky;
  `Matchradius`, age-out grace, and centroid stability all interact. Built last so 1–4 remain usable
  regardless.
- **Resolution tradeoff:** `Procres` 128 keeps JFA passes (~7) and the scatter buffer cheap.
  Higher res = finer blobs but more passes and a larger scatter buffer. Input stays full-res for
  display; only the tracking math is downscaled.
- **bbox (`w/h`):** exact min/max bbox per label needs a second scatter reduction (min/max blend).
  v1 may approximate `w/h` from area; spec flags it. Add the bbox reduction later if needed.

---

## 7. Out of scope (YAGNI for v1)

- Multi-class / color-based blob separation (foreground is luminance-thresholded only).
- Kalman/velocity prediction for occlusion-robust IDs (nearest-neighbor association only).
- Sub-pixel centroid refinement beyond the scatter mean.
- Recording / logging blob tracks to disk.
