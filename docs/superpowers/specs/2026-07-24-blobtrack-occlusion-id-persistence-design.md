# Blob Tracker: Occlusion-Proof ID Persistence — Design

**Date:** 2026-07-24
**Component:** `/project1/cont_blobtrack_glsl/script_idtrack` (CPU tracker, Script TOP callbacks)
**Related:** [GLSL TOP Blob Tracking Design Spec](2026-06-28-glsl-top-blob-tracking-design.md), `touchdesigner/blobtrack/README.md`

## Problem

Blob IDs do not survive real-world occlusion: when a marker is fully covered, or a dark
object passes over it, the reappearing marker gets a fresh ID instead of resuming its old one.

Live-session investigation (2026-07-24) established that the existing ghost-track mechanism
**works in the clean case** — a full-frame 15-frame blackout (threshold blanking) resumed all
14 live IDs with zero new IDs minted. The real-world failure comes from four concrete holes:

1. **Hard 0.5 s cap.** `Persistframes` = 30 at 60 fps; the miss counter advances every cook
   (verified live: miss = 10 after 10 frames of blank input). Any cover longer than 0.5 s
   drops the track. A person walking past a marker typically occludes it for 1–2 s.
2. **Ghost ID theft.** A ghost's match radius grows to `Matchradius × 4` = 0.33 normalized
   (≈ 42 px at 128²). Any transient blob inside that huge radius — occluder-edge glints, or
   JFA fragments (live scene: a 51 px blob shedding 1–4 px satellite roots, with `Minarea`
   set to 0 so nothing is filtered) — claims the ghost's ID and carries it away.
3. **No motion prediction.** Ghosts are pinned at the last seen centroid. Progressive
   occlusion also drags the centroid toward the occluder edge before the blob vanishes, so
   the ghost is parked at a stale, shifted position; a marker moving while hidden re-emerges
   outside the search area.
4. **No matching priority.** Ghosts compete in the same greedy pool as live tracks, so a
   stale ghost can outbid a live track for a blob in dense scenes.

Evidence of churn in practice: live `next_id` = 5251 with only 14 markers in scene.

## Goals

- A marker that is fully covered (dark occluder) and reappears at ~its old position within
  2 s resumes its old ID.
- A marker that moves behind an occluder and re-emerges along its path resumes its old ID.
- Transient noise blobs / JFA fragments must not steal a ghost's ID.
- No changes to output contracts (`out_blobs`, `out_blob_table`, id-texture) or to the GPU
  pipeline. All changes confined to `script_idtrack` callbacks + two container par values.

## Non-Goals

- Appearance-based re-identification or Hungarian assignment (IR dots are featureless;
  greedy-with-priority is sufficient at marker counts).
- Fixing JFA fragmentation of large blobs (separate known limitation; the area gate makes
  the tracker robust *against* its fragments).
- Cross-camera or 3D persistence.

## Design

All in `script_idtrack_callbacks` `onCook`. Chosen over "tuning only" (leaves theft and
stale-position holes) and "full re-ID" (unwarranted complexity).

### Track state

`tracks` container-storage tuples grow from `(id, cx, cy, miss)` to
`(id, cx, cy, vx, vy, area, miss)`. Old shorter tuples are tolerated on read (missing
fields default to `vx = vy = 0`, `area = 0` meaning "gate disabled for that track once",
`miss = 0`), matching the existing tolerant-read pattern.

### Matching: two passes, greedy nearest one-to-one in each

1. **Pass 1 — live tracks** (`miss == 0`): current blobs vs live tracks within strict
   `Matchradius`. Greedy by distance, one-to-one (today's algorithm, restricted to live
   tracks). A ghost can never outbid a live track.
2. **Pass 2 — ghosts** (`miss > 0`): only blobs left unmatched by pass 1, against ghosts,
   subject to both:
   - **Radius**: distance from the ghost's *predicted* position ≤
     `Matchradius × min(1 + 0.25 × miss, 2.5)`.
   - **Area gate**: `0.4 ≤ blob_area / max(track_area, 1) ≤ 2.5`. Blocks 1 px fragments
     from inheriting a marker-sized track's ID. If the stored track area is 0 (legacy
     tuple), the gate passes.

Unmatched blobs mint new IDs (unchanged counter, wrap at 2²³). Unmatched tracks coast as
ghosts until `miss > Persistframes`.

### Velocity + ghost coasting

- On match: `v ← 0.5 × (p_now − p_prev) + 0.5 × v_old`, then magnitude-capped at
  0.05 normalized/frame so a glitch match cannot launch a ghost across the frame.
  Track area updates to the matched blob's area.
- While ghosting (each cook the track goes unmatched): `p ← p + v`, then `v ← 0.9 × v`,
  with `p` clamped to [0, 1]. A stationary marker's ghost stays put; a moving marker's
  ghost coasts along its path and slows to a stop (~10-frame effective travel).

### Parameter values

- `Persistframes`: live value and documented default 30 → **120** (2 s at 60 fps). The
  age-grown radius is now capped at 2.5× and only reaches it at miss = 6, so long
  persistence no longer means a frame-third search radius.
- `Minarea`: live value 0 → **4** so sub-marker noise specks never enter the matcher.
  (User-approved; README suggested range already 4–16.)

Both are existing custom pars on `cont_blobtrack_glsl` — the component's established
interface — set directly, not routed through `master_controls` (they are component-internal
tuning, not show-control parameters).

### Error handling

- Legacy track tuples: tolerated as above.
- Division guards: `max(track_area, 1)` in the area gate.
- Velocity cap and position clamp bound all coasting math.
- Empty input / no blobs / no tracks paths unchanged.

## Testing

In-TD harness (no pipeline mutation; same technique as the investigation):

1. **Full-cover resume**: snapshot live IDs, set `Threshold` to 1.5 for N frames via
   delayed `run()`, restore, compare ID sets. Must pass for N = 15, 45, 90.
   N = 45 and 90 fail on the current build (30-frame cap) — proving the fix.
2. **Theft resistance** (pure-Python simulation of the matching logic, executed via
   `execute_script` against a copy of the algorithm with synthetic centroid data):
   marker track ghosts at t=0; transient 1 px blob appears 0.1 away at t=3 for one frame;
   marker returns at t=10 at its original position ⇒ must resume its original ID and the
   fragment must have minted a new one.
3. **Moving-marker resume** (same simulation): track with velocity 0.01/frame ghosts;
   blob re-appears 8 frames later along the path ⇒ resumes ID.
4. **Live verification**: user waves a dark object across markers while watching
   `out_blob_table` — IDs must hold; `next_id` must stay flat during the test.

Save discipline: `save_checkpoint` on `cont_blobtrack_glsl` before editing the callbacks
DAT; verify via harness before any project save. The callbacks swap must be
compile-checked before install (live-bridge rule).

## Documentation

`touchdesigner/blobtrack/README.md`: parameter table (`Persistframes` default/meaning,
ghost radius formula), Stage 5 description (two-pass + prediction + area gate), Known
Limitations (greedy section updated; theft mitigation noted), tuned-values table.
