# cont_blobtrack_glsl — GLSL Blob Tracker

A pure-GPU blob-tracking container for TouchDesigner. Thresholds a single TOP input, labels connected regions via an iterative Jump-Flood-style pass (JFA), computes per-blob centroids and areas in a GLSL **gather** pass, and assigns persistent integer IDs across frames via GPU feedback. The only CPU crossing is the final `script_blobs` scriptCHOP that reads the ID + centroid textures back to CHOP channels.

Cross-reference: [GLSL TOP Blob Tracking Design Spec](../../docs/superpowers/specs/2026-06-28-glsl-top-blob-tracking-design.md)

---

## Input

| Connector | Description |
|-----------|-------------|
| `in1` (input 0) | Grayscale or luminance-bearing TOP (any resolution). The pipeline internally resamples to `Procres × Procres` for all GPU stages. The dev-regression source `glsl_synth` is left inside the container but **disconnected** — it can be rewired to `in1` manually for offline testing. |

The live feed is `/project1/null_optitrack_cam` (128 × 128, connected to the container's external input 0).

---

## Parameter Page: "Blob Track"

| Parameter | Internal name | Default | Meaning |
|-----------|--------------|---------|---------|
| Threshold | `Threshold` | 0.5 | Luminance threshold (0–1). Pixels with R channel above this value are treated as foreground. For OptiTrack IR markers (bright white dots on near-black background), 0.4–0.6 works well; lower if markers appear dim, higher to suppress noise. |
| Min Area | `Minarea` | 8 | Minimum blob area in pixels (at processing resolution `Procres`). Blobs smaller than this are discarded in the centroid gather pass. Increase to suppress noise specks; decrease to catch small markers. |
| Proc Res | `Procres` | 128 | Side length (pixels) of the square processing texture. All GPU stages run at this resolution. Changing this also affects the area units reported in `out_blobs`. |
| Match Radius | `Matchradius` | 0.08 | Fraction of processing resolution used as the search radius for ID-association in `glsl_idtrack`. A new blob within this radius (in normalized 0–1 coords) of a previous-frame blob inherits its ID. |
| Max Blobs | `Maxblobs` | 64 | **Currently inert** — reserved for a future bounded track table. The live build dimensions every buffer to `Procres²`, not `Maxblobs`, so changing this has no effect today. |
| Show Overlay | `Showoverlay` | On | When enabled, `out_viz` tints the input frame with the per-blob label colors (60% over labeled regions). Set off for a clean pass-through. (No ID numbers or centroid markers are drawn — see Known Limitations.) |

---

## Outputs

These are **Out operators**, so they appear as wireable connectors on the container's right edge (3 TOP outputs, 1 CHOP output) and are also addressable internally by name (`op('.../out_mask')`). Connector order: `out_mask`, `out_labels`, `out_viz` (TOP), `out_blobs` (CHOP).

| Output | Operator | Type | Description |
|--------|----------|------|-------------|
| `out_mask` | outTOP ← `glsl_mask` | TOP 128² RGBA32F | Binary foreground mask after thresholding. R channel = 1.0 for foreground, 0.0 for background. Alpha channel is always 1.0. |
| `out_labels` | outTOP ← `glsl_labelviz` | TOP 128² RGBA32F | **Colorized connected components**. Each blob is rendered in a distinct hash-derived RGB color; background is black. This is a visualization, not raw label data — the underlying root coordinates live in the internal `null_label` TOP (pixel coords in `.rg`, fg flag in `.b`, sentinel `1e8` background), not here. |
| `out_viz` | outTOP ← `glsl_overlay` | TOP (in1 resolution) RGBA32F | Input frame tinted with the per-blob label colors (60% blend over labeled regions) when `Showoverlay` is on; exact pass-through when off. No ID numbers / centroid markers are drawn. |
| `out_blobs` | outCHOP ← `script_blobs` | CHOP 6 ch × 16384 samples | Per-blob centroid data (see channel contract below). |

---

## `out_blobs` Channel Contract

Six channels, `Procres²` samples (16384 at the default 128² setting). Most samples are zero-padded — consumers **must** filter on `area > 0`.

| Channel | Range | Description |
|---------|-------|-------------|
| `id` | 0 – 2²⁴−1 | Persistent integer blob ID, stored as float32. New-blob ID = `(frame mod 1024) * 16384 + slotIndex`. Generation cycles every 1024 frames; max value bounded below 2²⁴ for exact float32 representation. |
| `tx` | 0.0 – 1.0 | Normalized horizontal centroid. Origin is **bottom-left** (row 0 of `numpyArray` = bottom of frame). |
| `ty` | 0.0 – 1.0 | Normalized vertical centroid. Origin is **bottom-left**. |
| `area` | ≥ 0 | Blob area in pixels at `Procres` resolution. Zero means the slot is unused — filter on `area > 0`. |
| `w` | 0.0 – 1.0 | Approximate blob width, **normalized** like `tx`/`ty`. **Derived from area** as `2 * sqrt(area / pi) / Procres` (circular-equivalent diameter ÷ processing resolution). Not a true bounding box. |
| `h` | 0.0 – 1.0 | Approximate blob height, normalized. Same formula as `w` — equal to `w` (circular equivalence assumption). |

Minimal consumer pattern:
```python
chop = op('/project1/cont_blobtrack_glsl/out_blobs')
for s in range(chop.numSamples):
    if chop['area'][s] > 0:
        blob_id = int(chop['id'][s])
        tx, ty   = chop['tx'][s], chop['ty'][s]
        area     = chop['area'][s]
```

---

## Internal Pipeline

All stages run at `Procres × Procres` (default 128²) in 32-bit float RGBA textures.

| Stage | Operators | Description |
|-------|-----------|-------------|
| 1 — Threshold mask | `glsl_mask` → `out_mask` | GLSL TOP. Samples `in1` luminance (R channel); writes 1.0 where R > `uThreshold`, else 0.0. |
| 2 — JFA seed | `glsl_seed` | GLSL TOP. Each foreground pixel seeds itself as the root `(px_x, px_y, 1, 1)` in **integer pixel coords**. Background pixels get sentinel `(1e8, 1e8, 0, 1)`. |
| 3 — JFA labeling | `glsl_jfa1` … `glsl_jfa18` → `null_label` | 18 step-1 JFA passes propagate seeds to neighboring foreground pixels. Each pass samples ±1-pixel offsets and adopts the minimum-key valid root. `null_label` holds the final per-pixel root. |
| 3b — Label viz | `null_label` → `glsl_labelviz` → `out_labels` | GLSL TOP. Hashes each pixel's root coordinate to a distinct RGB color (black where background). |
| 4 — Centroid gather | `glsl_centroid` | GLSL TOP reading `null_label`. **Gather** (no scatter, no atomics): each output texel is a candidate root slot; it early-outs unless it is itself a root pixel, then scans all `Procres²` pixels summing those whose root matches, and writes `(cx_norm, cy_norm, area_px, 1)` at that root slot. Output is a `Procres²` RGBA32F texture, not a `Maxblobs`-wide buffer. |
| 5 — ID association + feedback | `glsl_idtrack` ↔ `feedback_id` | GLSL TOP. Compares current centroid texture against previous-frame ID texture (via a feedback TOP). Each new blob inherits the nearest old blob's ID within `uMatchRadius`; new blobs get a fresh generation-stamped ID. |
| 6 — Visualization + CHOP readback | `glsl_overlay` → `out_viz`; `script_blobs` → `out_blobs` | `glsl_overlay` tints the input frame with `glsl_labelviz` colors (gated by `Showoverlay`). `script_blobs` (scriptCHOP) reads back the `glsl_idtrack` (id/cx/cy) and `glsl_centroid` (area) textures via `numpyArray` and emits the six CHOP channels. |

The GPU→CPU boundary is only at Stage 6's `script_blobs`. Stages 1–5 are fully GPU-resident.

---

## Known Limitations

### JFA propagation ceiling (~18 px radius)
Live labeling uses 18 step-1 JFA passes. Each pass propagates a label by ±1 pixel, so a root travels at most ~18 pixels from its seed. This works well for small/marker-sized blobs. **Blobs larger than ~18 px radius will fragment** — a single physical blob becomes several false roots in `out_labels`, producing multiple `out_blobs` entries clustered together.

Fix: raise the step-1 pass count, or re-enable a JFA step schedule (`[64, 32, 16, 8, 4, 2, 1]`) guarded by a mask erosion pass to prevent gap-leak between closely spaced blobs.

### Greedy nearest-match ID association
`glsl_idtrack` uses a simple nearest-previous-centroid match. Two current blobs equidistant from one previous blob can both claim that ID (no bipartite / Hungarian assignment). Acceptable for sparse scenes; may cause ID confusion in dense or crossing-blob scenarios.

### Feedback IDs require an active cook path
`glsl_idtrack`/`feedback_id` feedback requires the container (or a downstream consumer) to be in an active display/cook path. If nothing downstream forces a cook, the feedback goes stale and IDs reset. Open the container viewer or wire an output into a displayed network to keep the feedback alive.

### Feedback wiring (Feedback TOP must use its Target param)
The ID feedback loop is `glsl_idtrack` → `feedback_id` (input 1 of `glsl_idtrack`). `feedback_id` reads the **previous** frame of `glsl_idtrack` via its **Target TOP parameter** (`top = glsl_idtrack`) — a frame-delayed edge that breaks the cook cycle. Its wired **input 0** is `glsl_centroid`, used only for first-frame init / resolution (it is *not* in the cycle). Do **not** wire `glsl_idtrack` into `feedback_id`'s input — that makes a same-frame cycle and TD raises a real "Cook dependency loop" warning (and the feedback stops delivering correct previous-frame data). This was a build-time misconfiguration that has been corrected.

### ID generation wraparound
New-blob IDs = `(frame mod 1024) * 16384 + slotIndex`. The generation counter wraps every 1024 frames (~17 s at 60 fps). IDs stay below 2²⁴ (16 777 216) for exact float32 representation.

### `out_blobs` is a scriptCHOP (CPU readback)
`script_blobs` uses `numpyArray` readback because `toptoCHOP` would not emit per-pixel samples on this TD build (suspected `singleset`/`crop` parameter issue). To remove the Python hop, investigate those parameters on a `toptoCHOP` referencing `glsl_centroid`.

### `w`/`h` are area-derived approximations
Width and height channels assume a circular blob: `diameter = 2 * sqrt(area / pi)` (then normalized by `Procres`). They are not true axis-aligned bounding boxes.

### Cost scales with `Procres²`
`glsl_centroid` and `glsl_idtrack` are gather/scan shaders: each active blob slot scans the whole `Procres²` field. At the default 128² with a handful of markers this is cheap (centroid early-outs to root slots only, idtrack early-outs to active slots only). Raising `Procres` increases per-active-slot cost quadratically — profile before going above 256.

---

## Tuned Parameter Values

Feed state at Task 8 wiring: **OptiTrack feed empty/black** (camera not transmitting). Defaults left in place. Recommended values once OptiTrack is live with IR markers:

| Parameter | Default | Suggested (IR markers) |
|-----------|---------|------------------------|
| Threshold | 0.5 | 0.4 – 0.6 (markers are bright white; adjust to suppress noise floor) |
| Minarea | 8 | 4 – 16 (depends on marker apparent size at 128² resolution) |
| Procres | 128 | 128 (sufficient for marker-count typical of OptiTrack scenes) |
| Matchradius | 0.08 | 0.1 – 0.15 (if markers move fast, increase to avoid ID drops) |
| Maxblobs | 64 | 64 (more than enough for typical OptiTrack body marker counts) |
| Showoverlay | On | Off for performance once tuned |
