# Blob Tracker Occlusion-Proof ID Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Blob IDs survive real occlusion (dark object covering a marker up to 2 s, including markers that move while hidden) without being stolen by noise blobs or JFA fragments.

**Architecture:** All tracking logic moves into a pure-Python function `step_tracks()` kept in a repo file `touchdesigner/blobtrack/idtrack_callbacks.py`, which is also the verbatim text installed into the live `script_idtrack_callbacks` DAT. The function implements two-pass greedy matching (live tracks first, then ghosts), an area-similarity gate on ghost resumption, and velocity-coasted ghost positions. The Script TOP `onCook` is a thin adapter (texture read → `step_tracks` → texture/storage write). Spec: `docs/superpowers/specs/2026-07-24-blobtrack-occlusion-id-persistence-design.md`.

**Tech Stack:** TouchDesigner MCP bridge (localhost:9980, same machine as this repo), Python (pure logic testable locally with no TD and no numpy), numpy inside TD only.

## Global Constraints

- The MCP bridge talks to a **live, unsaved** TD session. NEVER press Start/Restart on `/project1/MCP_Server`.
- Do NOT call `project.save()` — this TD project is untitled and `project.save()` opens a modal file dialog that hangs the entire bridge. Use `save_checkpoint` (MCP tool) for restore points.
- Callbacks DAT swap: `compile()` the new text and assign `.text` in ONE `execute_script` call. A syntax error in that DAT kills the tracker on the next cook.
- `execute_script` wrapper scoping: nested `def`s / comprehensions cannot see outer script-local names. Keep harness scripts flat (no helper defs; loops not comprehensions where they capture locals).
- Do not move any operators; no layout changes are involved (layout SSOT is `touchdesigner/LAYOUT.md`).
- Output contracts must NOT change: `blobs` storage stays `(slot, id, cx, cy, area, wh)` 6-tuples; id-texture stays `(id, cx, cy, valid)` at root slots; `out_blobs`/`out_blob_table` untouched.
- Git: run git through PowerShell. Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Tuning constants (exact values from spec): `VEL_ALPHA = 0.5`, `VEL_CAP = 0.05`, `VEL_DECAY = 0.9`, `GHOST_GROW = 0.25`, `GHOST_GROW_MAX = 2.5`, `AREA_GATE_LO = 0.4`, `AREA_GATE_HI = 2.5`, `ID_WRAP = 1 << 23`. Live par values: `Persistframes` → 120, `Minarea` → 4.

---

### Task 1: Pure tracking logic + local tests

**Files:**
- Create: `touchdesigner/blobtrack/idtrack_callbacks.py`
- Test: `touchdesigner/blobtrack/test_idtrack_logic.py`

**Interfaces:**
- Produces: `step_tracks(cur, tracks, radius, persist, next_id) -> (blobs, new_tracks, next_id)` where
  - `cur`: list of `(slot:int, cx:float, cy:float, area:float)` current-frame blobs
  - `tracks`: list of track tuples, tolerated shapes `(id, cx, cy, miss)` legacy or `(id, cx, cy, vx, vy, area, miss)`
  - `radius`: strict match radius, normalized 0–1; `persist`: max missed frames; `next_id`: fresh-ID counter
  - returns `blobs`: list of `(slot, id, cx, cy, area)`; `new_tracks`: list of `(id, cx, cy, vx, vy, area, miss)` (matched tracks have `miss=0` and updated velocity; ghosts have coasted position, decayed velocity, `miss` incremented; tracks past `persist` dropped); `next_id`: updated counter.
- Produces (for Task 2): module-level `onCook(scriptOp)` / `onGetCookLevel(scriptOp)` — the DAT entry points.

- [ ] **Step 1: Write the failing test file**

Write `touchdesigner/blobtrack/test_idtrack_logic.py` exactly:

```python
"""Local tests for step_tracks() — pure Python, no TD, no numpy required.

Run:  python touchdesigner/blobtrack/test_idtrack_logic.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from idtrack_callbacks import step_tracks

R = 0.08      # Matchradius used throughout
P = 30        # Persistframes used unless a test overrides


def step_empty(tracks, next_id, n):
    """Run n steps with no current blobs (full occlusion)."""
    for _ in range(n):
        blobs, tracks, next_id = step_tracks([], tracks, R, P, next_id)
    return tracks, next_id


def test_stationary_resume():
    # Marker tracked, fully covered 10 frames, returns at same spot -> same ID.
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], [], R, P, 1)
    assert blobs[0][1] == 1
    tracks, nid = step_empty(tracks, nid, 10)
    assert len(tracks) == 1 and tracks[0][6] == 10          # ghost, miss=10
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], tracks, R, P, nid)
    assert blobs[0][1] == 1, "stationary marker must resume its ID"
    assert tracks[0][6] == 0


def test_timeout_drop():
    # Ghost past Persistframes is dropped; return mints a fresh ID.
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], [], R, 5, 1)
    for _ in range(6):                                      # persist=5, 6th miss drops
        blobs, tracks, nid = step_tracks([], tracks, R, 5, nid)
    assert tracks == [], "ghost must drop after persist frames"
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], tracks, R, 5, nid)
    assert blobs[0][1] == 2, "expired track must NOT resume"


def test_fragment_cannot_steal():
    # 1 px fragment near a marker-sized ghost must not inherit its ID,
    # and the real marker must still resume afterwards.
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 51.0)], [], R, P, 1)
    tracks, nid = step_empty(tracks, nid, 2)                # ghost, miss=2
    blobs, tracks, nid = step_tracks([(200, 0.52, 0.5, 1.0)], tracks, R, P, nid)
    frag_ids = [b[1] for b in blobs]
    assert frag_ids == [2], "fragment must mint a new ID, not steal (got %s)" % frag_ids
    # fragment vanishes, marker returns
    blobs, tracks, nid = step_tracks([], tracks, R, P, nid)
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 50.0)], tracks, R, P, nid)
    ids = sorted(b[1] for b in blobs)
    assert 1 in ids, "marker must resume ID 1 (got %s)" % ids
    # symmetric gate: marker must not have taken the fragment's ghost either
    assert ids == [1]


def test_live_track_beats_ghost():
    # A blob near both its own live track and a big-radius ghost matches the live track.
    tracks = [
        (1, 0.50, 0.5, 0.0, 0.0, 20.0, 0),   # live
        (2, 0.52, 0.5, 0.0, 0.0, 20.0, 6),   # ghost with grown radius
    ]
    blobs, tracks2, nid = step_tracks([(100, 0.51, 0.5, 20.0)], tracks, R, P, 10)
    assert blobs[0][1] == 1, "live track must win over ghost"
    ghost = [t for t in tracks2 if t[0] == 2]
    assert ghost and ghost[0][6] == 7


def test_moving_marker_predicted_resume():
    # Track with velocity ghosts; blob re-appears along its path -> resumes.
    tracks = [(1, 0.5, 0.5, 0.01, 0.0, 20.0, 0)]
    tracks, nid = step_empty(tracks, 2, 8)
    ghost = tracks[0]
    assert ghost[1] > 0.54, "ghost must coast along +x (at %.4f)" % ghost[1]
    blobs, tracks, nid = step_tracks([(100, 0.55, 0.5, 20.0)], tracks, R, P, nid)
    assert blobs[0][1] == 1, "moving marker must resume via predicted position"


def test_velocity_cap():
    # A big correction on ghost resumption cannot produce runaway velocity.
    # Ghost at miss=2 -> radius 0.08*1.5 = 0.12; blob 0.11 away -> raw v = 0.055.
    tracks = [(1, 0.1, 0.1, 0.0, 0.0, 20.0, 2)]
    blobs, tracks, nid = step_tracks([(100, 0.21, 0.1, 20.0)], tracks, R, P, 2)
    assert blobs[0][1] == 1
    vx, vy = tracks[0][3], tracks[0][4]
    assert (vx * vx + vy * vy) ** 0.5 <= 0.05 + 1e-9, "velocity must be capped"


def test_legacy_tuple_tolerated():
    # Old (id, cx, cy, miss) storage tuples must still work; area gate disabled for them.
    tracks = [(9, 0.3, 0.3, 2)]
    blobs, tracks2, nid = step_tracks([(100, 0.31, 0.3, 1.0)], tracks, R, P, 10)
    assert blobs[0][1] == 9, "legacy ghost (area 0) must resume without area gate"
    assert len(tracks2[0]) == 7


def test_id_wrap():
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], [], R, P, 1 << 23)
    assert blobs[0][1] == 1 << 23 and nid == 1


if __name__ == '__main__':
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('PASS  %s' % name)
            except AssertionError as e:
                print('FAIL  %s: %s' % (name, e))
                fails += 1
    sys.exit(1 if fails else 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (PowerShell): `python touchdesigner/blobtrack/test_idtrack_logic.py`
Expected: `ModuleNotFoundError: No module named 'idtrack_callbacks'` (or ImportError).

- [ ] **Step 3: Write the implementation**

Write `touchdesigner/blobtrack/idtrack_callbacks.py` exactly:

```python
# script_idtrack = SOLE CPU blob tracker.
# This file is BOTH the repo source of truth AND the verbatim text of the
# /project1/cont_blobtrack_glsl/script_idtrack_callbacks DAT. Edit here,
# then reinstall into the DAT (compile-check + .text swap in one script).
#
# Reads glsl_centroid (GLSL TOP), assigns persistent integer IDs, outputs an
# (id, cx, cy, valid) texture for glsl_labelviz, and stores the blob list on
# the CONTAINER so script_blobs / out_blob_table can read it without a
# script->script cooked read (cook-loop workaround, see README).
#
# ID persistence (occlusion-proof, spec 2026-07-24):
#   * Two-pass greedy nearest one-to-one matching:
#       pass 1: live tracks (miss == 0) at strict Matchradius
#       pass 2: ghosts (miss > 0) at Matchradius * min(1 + 0.25*miss, 2.5),
#               measured from the ghost's COASTED (predicted) position, and
#               gated on area similarity 0.4 <= blob/track <= 2.5.
#     So a ghost can never outbid a live track, and a noise speck / JFA
#     fragment cannot inherit a marker-sized track's ID.
#   * Velocity: EMA (alpha 0.5) of matched position deltas, capped at
#     0.05/frame. Ghosts coast p += v with v decaying 10%/frame, clamped
#     to [0,1]. Stationary ghosts stay put; moving ones are searched for
#     along their path.
#   * Unmatched tracks are kept as ghosts for up to Persistframes frames.
#     Ghosts are matching candidates only; never emitted in blobs.

try:
    import numpy
except ImportError:          # local test runs import this module without TD
    numpy = None

VEL_ALPHA = 0.5       # EMA weight of the newest velocity sample
VEL_CAP = 0.05        # max |v| in normalized units per frame
VEL_DECAY = 0.9       # ghost velocity decay per missed frame
GHOST_GROW = 0.25     # ghost radius growth per missed frame
GHOST_GROW_MAX = 2.5  # cap on ghost radius growth factor
AREA_GATE_LO = 0.4    # ghost resumption: min blob/track area ratio
AREA_GATE_HI = 2.5    # ghost resumption: max blob/track area ratio
ID_WRAP = 1 << 23     # keep IDs exact in float32


def step_tracks(cur, tracks, radius, persist, next_id):
    """One tracker step. Pure Python - unit-tested locally.

    cur:     [(slot, cx, cy, area)] current-frame blobs
    tracks:  [(id, cx, cy, miss)] legacy or [(id, cx, cy, vx, vy, area, miss)]
    returns: (blobs [(slot, id, cx, cy, area)],
              new_tracks [(id, cx, cy, vx, vy, area, miss)],
              next_id)
    """
    prev = []
    for t in tracks:
        if len(t) >= 7:
            prev.append((int(t[0]), float(t[1]), float(t[2]), float(t[3]),
                         float(t[4]), float(t[5]), int(t[6])))
        else:
            miss = int(t[3]) if len(t) > 3 else 0
            prev.append((int(t[0]), float(t[1]), float(t[2]), 0.0, 0.0, 0.0, miss))

    n_cur = len(cur)
    cur_id = [0] * n_cur
    ct = [False] * n_cur
    pt = [False] * len(prev)
    assign = [-1] * n_cur

    # pass 1: live tracks, strict radius
    pairs = []
    for ci in range(n_cur):
        cx = cur[ci][1]; cy = cur[ci][2]
        for pi in range(len(prev)):
            if prev[pi][6] != 0:
                continue
            dx = prev[pi][1] - cx; dy = prev[pi][2] - cy
            dd = dx * dx + dy * dy
            if dd <= radius * radius:
                pairs.append((dd, ci, pi))
    pairs.sort(key=lambda t: t[0])
    for dd, ci, pi in pairs:
        if ct[ci] or pt[pi]:
            continue
        ct[ci] = True; pt[pi] = True
        cur_id[ci] = prev[pi][0]; assign[ci] = pi

    # pass 2: ghosts, grown radius from coasted position + area gate
    pairs = []
    for ci in range(n_cur):
        if ct[ci]:
            continue
        cx = cur[ci][1]; cy = cur[ci][2]; area = cur[ci][3]
        for pi in range(len(prev)):
            if pt[pi] or prev[pi][6] == 0:
                continue
            grow = 1.0 + GHOST_GROW * prev[pi][6]
            if grow > GHOST_GROW_MAX:
                grow = GHOST_GROW_MAX
            eff = radius * grow
            dx = prev[pi][1] - cx; dy = prev[pi][2] - cy
            dd = dx * dx + dy * dy
            if dd > eff * eff:
                continue
            ta = prev[pi][5]
            if ta > 0.0:
                ratio = area / (ta if ta > 1.0 else 1.0)
                if ratio < AREA_GATE_LO or ratio > AREA_GATE_HI:
                    continue
            pairs.append((dd, ci, pi))
    pairs.sort(key=lambda t: t[0])
    for dd, ci, pi in pairs:
        if ct[ci] or pt[pi]:
            continue
        ct[ci] = True; pt[pi] = True
        cur_id[ci] = prev[pi][0]; assign[ci] = pi

    # emit current blobs; mint IDs for unmatched; update velocities
    blobs = []
    new_tracks = []
    for ci in range(n_cur):
        s, cx, cy, area = cur[ci]
        if cur_id[ci] == 0:
            cur_id[ci] = next_id
            next_id += 1
            if next_id > ID_WRAP:
                next_id = 1
            vx = 0.0; vy = 0.0
        else:
            pi = assign[ci]
            vx = VEL_ALPHA * (cx - prev[pi][1]) + (1.0 - VEL_ALPHA) * prev[pi][3]
            vy = VEL_ALPHA * (cy - prev[pi][2]) + (1.0 - VEL_ALPHA) * prev[pi][4]
            m = (vx * vx + vy * vy) ** 0.5
            if m > VEL_CAP:
                vx *= VEL_CAP / m; vy *= VEL_CAP / m
        blobs.append((s, cur_id[ci], cx, cy, area))
        new_tracks.append((cur_id[ci], cx, cy, vx, vy, area, 0))

    # unmatched tracks coast as ghosts until persist is exceeded
    for pi in range(len(prev)):
        if pt[pi]:
            continue
        tid, cx, cy, vx, vy, area, miss = prev[pi]
        miss += 1
        if miss > persist:
            continue
        cx = cx + vx; cy = cy + vy
        if cx < 0.0: cx = 0.0
        if cx > 1.0: cx = 1.0
        if cy < 0.0: cy = 0.0
        if cy > 1.0: cy = 1.0
        vx *= VEL_DECAY; vy *= VEL_DECAY
        new_tracks.append((tid, cx, cy, vx, vy, area, miss))

    return blobs, new_tracks, next_id


def onCook(scriptOp):
    inp = scriptOp.inputs[0] if len(scriptOp.inputs) else None
    if inp is None:
        scriptOp.copyNumpyArray(numpy.zeros((128, 128, 4), dtype=numpy.float32))
        return
    cont = op('/project1/cont_blobtrack_glsl')
    cen = inp.numpyArray()                         # (H, W, 4) = (cx, cy, area, valid)
    H = cen.shape[0]; W = cen.shape[1]; n = H * W
    cenf = cen.reshape(n, 4)
    slots = numpy.nonzero(cenf[:, 3] > 0.5)[0]

    cur = []
    for k in range(len(slots)):
        s = int(slots[k])
        cur.append((s, float(cenf[s, 0]), float(cenf[s, 1]), float(cenf[s, 2])))

    try:
        radius = float(cont.par.Matchradius)
    except Exception:
        radius = 0.08
    try:
        persist = int(cont.par.Persistframes)
    except Exception:
        persist = 120
    try:
        procres = float(cont.par.Procres)
    except Exception:
        procres = float(W)

    next_id = int(cont.fetch('next_id', 1))
    raw, tracks, next_id = step_tracks(cur, cont.fetch('tracks', []),
                                       radius, persist, next_id)

    out = numpy.zeros((H, W, 4), dtype=numpy.float32)
    blobs = []
    for b in raw:
        s, bid, cx, cy, area = b
        y = s // W; x = s % W
        out[y, x, 0] = float(bid); out[y, x, 1] = cx
        out[y, x, 2] = cy; out[y, x, 3] = 1.0
        wh = 2.0 * ((max(area, 0.0) / 3.14159) ** 0.5) / procres
        blobs.append((s, int(bid), cx, cy, area, wh))

    cont.store('tracks', tracks); cont.store('next_id', next_id)
    cont.store('blobs', blobs); cont.store('dims', (H, W))
    scriptOp.copyNumpyArray(out)
    return


def onGetCookLevel(scriptOp):
    return CookLevel.AUTOMATIC
```

- [ ] **Step 4: Run tests to verify they pass**

Run (PowerShell): `python touchdesigner/blobtrack/test_idtrack_logic.py`
Expected: `PASS` for all 8 tests, exit code 0.

- [ ] **Step 5: Commit**

PowerShell:
```powershell
git add touchdesigner/blobtrack/idtrack_callbacks.py touchdesigner/blobtrack/test_idtrack_logic.py
git commit -m @'
feat(blobtrack): occlusion-proof ID tracking logic with local tests

Two-pass greedy matching (live tracks first), area-similarity gate on
ghost resumption, velocity-coasted ghost positions. Pure step_tracks()
is the repo source of truth for the script_idtrack_callbacks DAT.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 2: Baseline failing evidence + install into the live TD session

**Files:**
- Modify (live TD, not repo): `/project1/cont_blobtrack_glsl/script_idtrack_callbacks` DAT text; container pars `Persistframes`, `Minarea`.

**Interfaces:**
- Consumes: `touchdesigner/blobtrack/idtrack_callbacks.py` from Task 1 (read from disk by TD — same machine).
- Produces: live tracker running the new logic; `tracks` storage becomes 7-tuples. Harness storage keys `_dbg_*` on the container (Task 3 reuses them).

- [ ] **Step 1: Capture baseline failure (45-frame cover loses IDs on current build)**

MCP `execute_script` (script A — schedule):
```python
c = op('/project1/cont_blobtrack_glsl')
orig = float(c.par.Threshold)
c.store('_dbg_pre', [tuple(b) for b in c.fetch('blobs', [])])
c.store('_dbg_pre_nextid', c.fetch('next_id', 0))
c.store('_dbg_post', None)
c.par.Threshold = 1.5
run("op('/project1/cont_blobtrack_glsl').par.Threshold = " + repr(orig), delayFrames=45)
run("c = op('/project1/cont_blobtrack_glsl'); c.store('_dbg_post', [tuple(b) for b in c.fetch('blobs', [])]); c.store('_dbg_post_nextid', c.fetch('next_id', 0))", delayFrames=135)
print('scheduled 45f cover')
```
Wait ~3 s, then MCP `execute_script` (script B — read):
```python
import json
c = op('/project1/cont_blobtrack_glsl')
post = c.fetch('_dbg_post', None)
out = {'ready': post is not None, 'thresh': float(c.par.Threshold)}
if post is not None:
    pre_ids = set(int(b[1]) for b in c.fetch('_dbg_pre', []))
    post_ids = set(int(b[1]) for b in post)
    out['kept'] = len(pre_ids & post_ids)
    out['pre_n'] = len(pre_ids); out['post_n'] = len(post_ids)
    out['minted'] = c.fetch('_dbg_post_nextid', 0) - c.fetch('_dbg_pre_nextid', 0)
print(json.dumps(out))
```
Expected on CURRENT build: `kept == 0`, `minted == post_n` (45 > Persistframes 30 → every ID lost). Record the output. If markers are not currently visible (`pre_n == 0`), pause and ask the user to get the OptiTrack feed live before continuing.

- [ ] **Step 2: Save a checkpoint of the container**

MCP `save_checkpoint` on `/project1/cont_blobtrack_glsl`, label `pre-occlusion-idtrack`.

- [ ] **Step 3: Install new callbacks text (compile-check + swap in ONE script) and set pars**

MCP `execute_script`:
```python
path = r'C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\blobtrack\idtrack_callbacks.py'
f = open(path, 'r')
txt = f.read()
f.close()
compile(txt, 'idtrack_callbacks', 'exec')     # raises BEFORE touching the DAT on any syntax error
dat = op('/project1/cont_blobtrack_glsl/script_idtrack_callbacks')
dat.text = txt
c = op('/project1/cont_blobtrack_glsl')
c.par.Persistframes = 120
c.par.Persistframes.default = 120
c.par.Minarea = 4
print('installed', len(txt), 'chars; Persistframes', int(c.par.Persistframes), 'Minarea', int(c.par.Minarea))
```

- [ ] **Step 4: Verify the tracker is alive and upgraded**

Wait ~2 s (let frames cook), then MCP `execute_script`:
```python
import json
c = op('/project1/cont_blobtrack_glsl')
st = op('/project1/cont_blobtrack_glsl/script_idtrack')
tr = c.fetch('tracks', [])
out = {
 'errors': st.errors(), 'warnings': st.warnings(),
 'blobs_n': len(c.fetch('blobs', [])),
 'track_len': len(tr[0]) if tr else 0,
 'tracks_n': len(tr),
}
print(json.dumps(out, default=str))
```
Expected: `errors` empty, `blobs_n` > 0 (with live markers), `track_len == 7`. If errors are non-empty: restore the checkpoint (`restore_checkpoint`) and stop — do not iterate blind on the live DAT.

---

### Task 3: Live occlusion verification

**Files:** none (live TD harness only, reuses `_dbg_*` storage keys from Task 2).

**Interfaces:**
- Consumes: installed tracker from Task 2.

- [ ] **Step 1: Full-cover resume at N = 15, 45, 90 frames**

For each N in (15, 45, 90): run Task 2 Step 1's script A with `delayFrames=N` on the restore line and `delayFrames=N+90` on the capture line, wait ~ (N+90)/60 + 1 seconds, then run script B.
Expected each time: `kept == pre_n` (all IDs resumed) and `minted == 0`. N = 45 and 90 were losses on the old build — passing now proves the fix.

- [ ] **Step 2: Stability soak**

MCP `execute_script`: snapshot `next_id`, wait ~10 s, snapshot again.
```python
c = op('/project1/cont_blobtrack_glsl')
print('next_id', c.fetch('next_id', 0), 'blobs', len(c.fetch('blobs', [])))
```
Expected: `next_id` unchanged across the 10 s (no churn with a static scene).

- [ ] **Step 3: Clean up debug keys**

MCP `execute_script`:
```python
c = op('/project1/cont_blobtrack_glsl')
for k in list(c.storage.keys()):
    if k.startswith('_dbg_'):
        c.unstore(k)
print('cleaned', c.storage.keys())
```

- [ ] **Step 4: Ask the user for the physical test**

Report results and ask the user to wave a dark object across markers while watching `out_blob_table` — IDs should hold through the pass. (Panels can't be screenshotted through the bridge; this is the user-at-the-keyboard check.)

---

### Task 4: Documentation update

**Files:**
- Modify: `touchdesigner/blobtrack/README.md`

**Interfaces:**
- Consumes: final behavior/values from Tasks 1–3.

- [ ] **Step 1: Update README**

Make these edits (keep surrounding text intact):
1. Header paragraph: mention the tracker text's repo source of truth `idtrack_callbacks.py` (edit file → reinstall into the DAT).
2. Parameter table: `Matchradius` row — ghost radius formula is now `Matchradius × min(1 + 0.25·missed, 2.5)` measured from the ghost's predicted (velocity-coasted) position, and only blobs unmatched by live tracks may resume a ghost, gated on area similarity (0.4×–2.5× of the track's last area). `Persistframes` row — default 120 (2 s at 60 fps).
3. `out_blobs` `id` channel row: same ghost-resumption description update.
4. Stage 5 row of Internal Pipeline: describe two-pass matching, velocity coasting, area gate; track state `(id, cx, cy, vx, vy, area, miss)`.
5. Known Limitations → "Greedy one-to-one ID association": rewrite the ghost-vs-live sentence — ghosts can no longer out-compete live tracks (two-pass); note remaining limitation: no Hungarian assignment, ID swaps still possible between crossing *live* blobs; fragment theft mitigated by the area gate but two similar-area markers crossing can still swap.
6. Tuned Parameter Values table: `Minarea` suggested 4–16 with live value 4; `Persistframes` default/live 120, suggested 60–180.

- [ ] **Step 2: Commit**

PowerShell:
```powershell
git add touchdesigner/blobtrack/README.md
git commit -m @'
docs(blobtrack): document occlusion-proof ID persistence

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```
