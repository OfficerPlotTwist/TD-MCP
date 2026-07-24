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
