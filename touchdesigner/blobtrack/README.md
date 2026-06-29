# cont_blobtrack_glsl — GLSL Blob Tracker

A pure-GPU blob-tracking container for TouchDesigner. Thresholds a single TOP input, labels connected regions via Jump-Flood Algorithm (JFA), gathers per-blob centroids and areas in a GLSL scatter pass, and assigns persistent integer IDs across frames via GPU feedback. The only CPU crossing is the final `script_blobs` scriptCHOP that reads the centroid texture back to CHOP channels.

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
| Max Blobs | `Maxblobs` | 64 | Upper bound on the number of blobs tracked. The JFA label space and centroid scatter buffer are dimensioned to `Maxblobs`. |
| Show Overlay | `Showoverlay` | On | When enabled, `out_viz` composites blob-ID labels and centroid markers over the input frame. Set off for a clean pass-through. |

---

## Outputs

| Output | Operator | Type | Description |
|--------|----------|------|-------------|
| `out_mask` | nullTOP | TOP 128² RGBA32F | Binary foreground mask after thresholding. R channel = 1.0 for foreground, 0.0 for background. Alpha channel is always 1.0. |
| `out_labels` | nullTOP | TOP 128² RGBA32F | JFA label texture. Each foreground pixel holds `(root_x_norm, root_y_norm, fg_flag, 1.0)` — the normalized position of its blob's seed/root pixel. Background pixels hold `(sentinel, sentinel, 0, 1)`. |
| `out_viz` | nullTOP | TOP 128² RGBA32F | Debug visualization. Input frame with blob ID overlays (colored per-blob regions + centroid markers) when `Showoverlay` is on. |
| `out_blobs` | nullCHOP (follows `script_blobs` scriptCHOP) | CHOP 6 ch × 16384 samples | Per-blob centroid data (see channel contract below). |

---

## `out_blobs` Channel Contract

Six channels, `Procres²` samples (16384 at the default 128² setting). Most samples are zero-padded — consumers **must** filter on `area > 0`.

| Channel | Range | Description |
|---------|-------|-------------|
| `id` | 0 – 2²⁴−1 | Persistent integer blob ID, stored as float32. New-blob ID = `(frame mod 1024) * 16384 + slotIndex`. Generation cycles every 1024 frames; max value bounded below 2²⁴ for exact float32 representation. |
| `tx` | 0.0 – 1.0 | Normalized horizontal centroid. Origin is **bottom-left** (row 0 of `numpyArray` = bottom of frame). |
| `ty` | 0.0 – 1.0 | Normalized vertical centroid. Origin is **bottom-left**. |
| `area` | ≥ 0 | Blob area in pixels at `Procres` resolution. Zero means the slot is unused — filter on `area > 0`. |
| `w` | ≥ 0 | Approximate blob width. **Derived from area** as `sqrt(area / pi) * 2` (circular-equivalent diameter). Not a true bounding box. |
| `h` | ≥ 0 | Approximate blob height. Same formula as `w` — equal to `w` (circular equivalence assumption). |

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
| 2 — JFA seed | `glsl_seed` | GLSL TOP. Each foreground pixel seeds itself as the root `(x_norm, y_norm, 1, 1)`. Background pixels get sentinel `(2,2,0,1)`. |
| 3 — JFA labeling | `glsl_jfa1` … `glsl_jfa18` → `null_label` → `out_labels` | 18 step-1 JFA passes propagate seeds to neighboring foreground pixels. Each pass samples ±1-pixel offsets and adopts the nearest valid root. |
| 4 — Centroid scatter/gather | `glsl_centroid` | GLSL TOP reading `null_label`. For each foreground pixel, atomically accumulates `(cx_sum, cy_sum, area, valid)` per unique root into a `Maxblobs`-wide 1D texture. |
| 5 — ID association + feedback | `glsl_idtrack` ↔ `feedback_id` | GLSL TOP. Compares current centroid texture against previous-frame ID texture (via a feedback TOP). Each new blob inherits the nearest old blob's ID within `uMatchRadius`; new blobs get a fresh generation-stamped ID. |
| 6 — Visualization + CHOP readback | `glsl_overlay`, `out_viz`, `script_blobs`, `out_blobs` | Overlay composites ID labels onto the input frame. `script_blobs` (scriptCHOP) reads back the centroid/ID texture via `numpyArray` and emits the six CHOP channels. |

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

### cook-loop log entry (benign)
TD logs a "Cook dependency loop" warning for `glsl_idtrack ↔ feedback_id`. This is intentional — the feedback TOP creates a one-frame-delayed self-loop. TD handles it via its delayed-feedback mechanism; the log entry is informational, not an error.

### ID generation wraparound
New-blob IDs = `(frame mod 1024) * 16384 + slotIndex`. The generation counter wraps every 1024 frames (~17 s at 60 fps). IDs stay below 2²⁴ (16 777 216) for exact float32 representation.

### `out_blobs` is a scriptCHOP (CPU readback)
`script_blobs` uses `numpyArray` readback because `toptoCHOP` would not emit per-pixel samples on this TD build (suspected `singleset`/`crop` parameter issue). To remove the Python hop, investigate those parameters on a `toptoCHOP` referencing `glsl_centroid`.

### `w`/`h` are area-derived approximations
Width and height channels assume a circular blob: `diameter = 2 * sqrt(area / pi)`. They are not true axis-aligned bounding boxes.

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
