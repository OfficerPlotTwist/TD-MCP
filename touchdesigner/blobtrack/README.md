# cont_blobtrack_glsl — GLSL Blob Tracker

A GPU-heavy blob-tracking container for TouchDesigner. Thresholds a single TOP input, labels connected regions via an iterative Jump-Flood-style pass (JFA), and computes per-blob centroids and areas in a GLSL **gather** pass — all on the GPU. Persistent integer IDs are then assigned on the **CPU** by the `script_idtrack` Script TOP (greedy nearest-centroid matching against the previous frame, state held in container storage), which also rebuilds an `(id, cx, cy, valid)` id-texture so the label colorizer can tint each blob by its **persistent ID**.

> **History:** IDs were originally assigned on the GPU via a `glsl_idtrack` ↔ `feedback_id` feedback loop. That was replaced by the CPU tracker because (a) this TD build's Feedback TOP ignores its *Target TOP* parameter (it only frame-delays its wired input), so closing the loop required wiring the loop-end into the feedback input, and (b) the `script_blobs` CPU readback then `numpyArray`-read a node *inside* that loop every frame, which TD flags as a "Cook dependency loop". The CPU tracker has no GPU feedback edge and no script→script cooked reads, so it is loop-free. See Known Limitations.

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
| Match Radius | `Matchradius` | 0.08 | Search radius (in normalized 0–1 centroid distance) for ID-association in the `script_idtrack` CPU tracker. A current blob within this radius of a previous-frame blob inherits its ID. For ghost tracks (see Persist Frames) the effective radius grows with the ghost's age: `Matchradius × min(1 + missed_frames, 4)`. |
| Persist Frames | `Persistframes` | 30 | Ghost-track grace period. A track whose blob disappears is kept as a "ghost" at its last position for up to this many frames; a new blob appearing within the (age-grown) match radius of a ghost **resumes the ghost's ID** instead of getting a fresh one. Set 0 to disable persistence (old immediate-drop behavior). Ghosts are matching candidates only — they are never emitted in `out_blobs` / `out_blob_table`. |
| Max Blobs | `Maxblobs` | 64 | **Currently inert** — reserved for a future bounded track table. The live build dimensions every buffer to `Procres²`, not `Maxblobs`, so changing this has no effect today. |
| Show Overlay | `Showoverlay` | On | When enabled, `out_viz` tints the input frame with the per-blob label colors (60% over labeled regions). Set off for a clean pass-through. (No ID numbers or centroid markers are drawn — see Known Limitations.) |

---

## Outputs

These are **Out operators**, so they appear as wireable connectors on the container's right edge and are also addressable internally by name (`op('.../out_mask')`). TOP outputs: `out_mask`, `out_labels`, `out_viz`. Data outputs: `out_blobs` (CHOP), `out_blob_table` (DAT).

| Output | Operator | Type | Description |
|--------|----------|------|-------------|
| `out_mask` | outTOP ← `glsl_mask` | TOP 128² RGBA32F | Binary foreground mask after thresholding. R channel = 1.0 for foreground, 0.0 for background. Alpha channel is always 1.0. |
| `out_labels` | outTOP ← `glsl_labelviz` | TOP 128² RGBA32F | **Colorized connected components, tinted by persistent ID.** Each blob is rendered in a distinct color = hash of its persistent ID (so a tracked blob keeps the *same* color for its whole lifetime, even as it moves); background is black. The shader reads each fg pixel's JFA root coord from `null_label.rg`, looks up that root slot's ID in the `script_idtrack` id-texture, and hashes it. |
| `out_viz` | outTOP ← `glsl_overlay` | TOP (in1 resolution) RGBA32F | Input frame tinted with the per-blob label colors (60% blend over labeled regions) when `Showoverlay` is on; exact pass-through when off. No ID numbers / centroid markers are drawn. |
| `out_blobs` | outCHOP ← `script_blobs` | CHOP 6 ch × 16384 samples | Per-blob data, one filled sample per blob root slot (see channel contract below). |
| `out_blob_table` | outDAT ← `script_blob_table` | DAT table | **One row per blob** (plus a header row): columns `id  tx  ty  area  w  h` — the same fields as `out_blobs`, deduplicated to a clean table sorted by `id`. Convenient for display, logging, or DAT-based consumers. Empty (header only) when no blobs are present. |

---

## `out_blobs` Channel Contract

Six channels, `Procres²` samples (16384 at the default 128² setting). Most samples are zero-padded — consumers **must** filter on `area > 0`.

| Channel | Range | Description |
|---------|-------|-------------|
| `id` | 1 – 2²³ | Persistent integer blob ID, stored as float32. Assigned by the CPU tracker as a monotonic counter (1, 2, 3, …) that wraps at 2²³ to stay exact in float32. A blob keeps its ID across frames as long as it stays within `Matchradius` of its previous-frame position — and a blob that disappears for up to `Persistframes` frames and reappears near its last position **resumes its old ID** (ghost-track matching). |
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

Or read the deduplicated table (one row per blob) from `out_blob_table`:
```python
dat = op('/project1/cont_blobtrack_glsl/out_blob_table')
for r in range(1, dat.numRows):                 # row 0 is the header
    blob_id = int(dat[r, 'id'])
    tx, ty  = float(dat[r, 'tx']), float(dat[r, 'ty'])
    area    = float(dat[r, 'area'])
```

---

## Internal Pipeline

All stages run at `Procres × Procres` (default 128²) in 32-bit float RGBA textures.

| Stage | Operators | Description |
|-------|-----------|-------------|
| 1 — Threshold mask | `glsl_mask` → `out_mask` | GLSL TOP. Samples `in1` luminance (R channel); writes 1.0 where R > `uThreshold`, else 0.0. |
| 2 — JFA seed | `glsl_seed` | GLSL TOP. Each foreground pixel seeds itself as the root `(px_x, px_y, 1, 1)` in **integer pixel coords**. Background pixels get sentinel `(1e8, 1e8, 0, 1)`. |
| 3 — JFA labeling | `glsl_jfa1` … `glsl_jfa18` → `null_label` | 18 step-1 JFA passes propagate seeds to neighboring foreground pixels. Each pass samples ±1-pixel offsets and adopts the minimum-key valid root. `null_label` holds the final per-pixel root. |
| 3b — Label viz | `null_label`, `script_idtrack` → `glsl_labelviz` → `out_labels` | GLSL TOP. For each fg pixel, reads its JFA root coord from `null_label.rg`, samples the persistent ID at that root slot from the `script_idtrack` id-texture (input 1), and hashes the **ID** to a distinct RGB color (black where background). Color is therefore stable per tracked blob. |
| 4 — Centroid gather | `glsl_centroid` | GLSL TOP reading `null_label`. **Gather** (no scatter, no atomics): each output texel is a candidate root slot; it early-outs unless it is itself a root pixel, then scans all `Procres²` pixels summing those whose root matches, and writes `(cx_norm, cy_norm, area_px, 1)` at that root slot. Output is a `Procres²` RGBA32F texture, not a `Maxblobs`-wide buffer. |
| 5 — ID association (CPU) | `glsl_centroid` → `script_idtrack` | **Script TOP — the sole tracker.** Reads the centroid texture via `numpyArray`, takes the valid root slots as this frame's blobs, and greedy one-to-one matches them by centroid distance (≤ effective match radius) to the tracked blobs held in **container storage** — both live tracks and **ghost tracks** (tracks whose blob vanished ≤ `Persistframes` frames ago, held at their last position). Matched blobs keep (or resume) the track's ID; unmatched blobs get the next counter value; unmatched tracks coast as ghosts until `Persistframes` is exceeded. Writes an `(id, cx, cy, valid)` id-texture (for Stage 3b) and stores the blob list `(slot, id, cx, cy, area, wh)` + track state `(id, cx, cy, miss)` on the container. |
| 6 — Visualization + outputs | `glsl_overlay` → `out_viz`; `script_blobs` → `out_blobs`; `script_blob_table` → `out_blob_table` | `glsl_overlay` tints the input frame with `glsl_labelviz` colors (gated by `Showoverlay`). `script_blobs` (scriptCHOP) and `script_blob_table` (scriptDAT) both read the blob list from **container storage** (`op('cont_blobtrack_glsl').fetch('blobs')`) and emit the CHOP channels / DAT table respectively. Reading shared storage — instead of one script op `numpyArray`-reading another's cooked output — is what keeps the graph free of cook-dependency loops. |

The GPU→CPU boundary is at Stage 5's `script_idtrack` (the only `numpyArray` read of a GPU texture). Stages 1–4 are GPU-resident; Stage 6 consumers read CPU storage, not textures.

---

## Known Limitations

### JFA propagation ceiling (~18 px radius)
Live labeling uses 18 step-1 JFA passes. Each pass propagates a label by ±1 pixel, so a root travels at most ~18 pixels from its seed. This works well for small/marker-sized blobs. **Blobs larger than ~18 px radius will fragment** — a single physical blob becomes several false roots in `out_labels`, producing multiple `out_blobs` entries clustered together.

Fix: raise the step-1 pass count, or re-enable a JFA step schedule (`[64, 32, 16, 8, 4, 2, 1]`) guarded by a mask erosion pass to prevent gap-leak between closely spaced blobs.

### Greedy one-to-one ID association
`script_idtrack` matches by nearest centroid with a greedy **one-to-one** constraint (each track is claimed by at most one current blob, smallest distance first). Better than the old GPU matcher, which let two current blobs claim the same previous ID. Still not globally optimal (no Hungarian assignment); may cause ID swaps in dense or crossing-blob scenarios. Ghost tracks participate in the same greedy pool as live tracks with a larger (age-grown) radius, so in dense scenes an old ghost can occasionally out-compete a live track for a blob if it happens to be closer.

### Tracking advances when `script_idtrack` cooks
The tracker (and its container storage) updates whenever `script_idtrack` cooks — i.e. when its `glsl_centroid` input changes and something pulls the id-texture (normally `out_labels`/`out_viz` being displayed). `script_blobs` / `out_blob_table` then read that storage; if the tracker hasn't cooked on a given frame they serve the previous frame's list (a harmless 1-frame lag). Keep an output displayed (or the container viewer open) so the tracker cooks every frame.

### Why CPU tracking (cook-loop history)
The ID step is on the CPU specifically to avoid cook-dependency loops in this TD build. Two build-specific gotchas drove this:
- **Feedback TOP ignores its Target TOP param here** — it only frame-delays its *wired input*. Closing a GPU feedback loop therefore needs the loop-end wired into the feedback's input, which makes `glsl_idtrack` ↔ `feedback_id` a graph cycle.
- **A script op `numpyArray`-reading another script op's cooked output trips loop detection** — every variant (`scriptCHOP`→`glsl_idtrack`, `scriptCHOP`→`scriptTOP`, `scriptDAT`→`scriptCHOP`) produced a per-frame "Cook dependency loop". The fix is to hand data between script ops through **container storage** (`store`/`fetch`), which is not a cook dependency.

### ID counter wraparound
IDs are a monotonic counter starting at 1, wrapping at 2²³ (8 388 608) to stay exact in float32. At realistic blob-creation rates this effectively never wraps.

### `out_blobs` is a scriptCHOP (CPU)
`script_blobs` is a Script CHOP fed from container storage. A `toptoCHOP` would have removed the Python hop in the old GPU design but did not emit per-pixel samples on this TD build (suspected `singleset`/`crop` issue); it is moot now that IDs are CPU-side and the canonical per-blob output is `out_blob_table`.

### `w`/`h` are area-derived approximations
Width and height channels assume a circular blob: `diameter = 2 * sqrt(area / pi)` (then normalized by `Procres`). They are not true axis-aligned bounding boxes.

### Cost scales with `Procres²`
`glsl_centroid` is a gather/scan shader: each root slot scans the whole `Procres²` field (it early-outs to root slots only). Raising `Procres` increases per-active-slot cost quadratically — profile before going above 256. The CPU tracker cost is `O(blobs_current × blobs_prev)` per frame — trivial for marker-count scenes.

---

## Tuned Parameter Values

Feed state at Task 8 wiring: **OptiTrack feed empty/black** (camera not transmitting). Defaults left in place. Recommended values once OptiTrack is live with IR markers:

| Parameter | Default | Suggested (IR markers) |
|-----------|---------|------------------------|
| Threshold | 0.5 | 0.4 – 0.6 (markers are bright white; adjust to suppress noise floor) |
| Minarea | 8 | 4 – 16 (depends on marker apparent size at 128² resolution) |
| Procres | 128 | 128 (sufficient for marker-count typical of OptiTrack scenes) |
| Matchradius | 0.08 | 0.1 – 0.15 (if markers move fast, increase to avoid ID drops) |
| Persistframes | 30 | 15 – 60 (~0.25–1 s at 60 fps; raise if markers flicker/occlude for long stretches, lower toward 0 if stale IDs get picked up by unrelated new markers) |
| Maxblobs | 64 | 64 (more than enough for typical OptiTrack body marker counts) |
| Showoverlay | On | Off for performance once tuned |
