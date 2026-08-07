# Mask Combiner v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/project1/cont_mask_combiner` — a TD container serving a canvas webapp (port 9981) where mask pieces are click/lasso-selected, edited (fill voids, knife loop, additive loop, outset/inset, Ctrl+Z), and sent back as named out TOPs.

**Architecture:** Pure bitmap math lives in `maskops.mjs` (shared by browser and node tests). A WebServer DAT inside the container serves the app and two endpoints (`GET /mask` snapshot, `POST /send` bake). Each send writes a never-overwritten PNG and creates a `moviefilein → out` pair named by the user.

**Tech Stack:** Vanilla JS (ES modules, canvas 2D), node for tests, TD WebServer DAT callbacks in Python, TD bridge (MCP) for network construction.

**Spec:** `docs/superpowers/specs/2026-08-07-mask-combiner-webapp-design.md`

## Global Constraints

- All TOPs created get nearest filtering: set `filtertype` and `inputfiltertype` to `'nearest'` wherever the parameter exists.
- Webapp port is **9981**. `/project1/MCP_Server` is never touched, its server buttons never pressed.
- Sent PNGs go to `touchdesigner/assets/sent_masks/` and are **never overwritten** (timestamp in filename).
- TD op names: `[A-Za-z][A-Za-z0-9_]*`; collisions get `_2`, `_3`, … suffixes.
- Bridge discipline: `save_checkpoint` on `/project1` before first mutation and after verification. Do NOT call `project.save()` — the project may be untitled and the save dialog freezes the bridge.
- `execute_script` scripts: no recursion, no closures over outer locals — iterate with stacks, keep helpers inline.
- Display of the mask is ONE flat composite (white = any piece, black = background). No per-piece tinting, no grid of pieces.
- Repo paths hardcoded in callbacks: `APP_DIR = C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\maskcombiner`, `SENT_DIR = C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\assets\sent_masks`.
- Git via PowerShell tool (repo convention).
- The mask render in the webapp reconstructs from current piece bitmaps each edit (the raw label PNG is near-black IDs, not displayable as-is).

---

### Task 1: maskops.mjs — core bitmap ops

**Files:**
- Create: `touchdesigner/maskcombiner/maskops.mjs`
- Test: `touchdesigner/maskcombiner/test_maskops.mjs`

**Interfaces:**
- Produces (used by Tasks 2, 5, 6): `makeBitmap(w,h)`, `cloneBitmap(bm)`, `extractPieces(ids: Uint8Array, w, h) -> Map<int, Bitmap>`, `union(a,b)`, `subtract(a,b)`, `countPixels(bm)`, `fillVoids(bm)`, `dilate(bm)`, `erode(bm)`. A `Bitmap` is `{ w, h, data: Uint8Array }` with values 0/1. All ops return NEW bitmaps (inputs untouched).

- [ ] **Step 1: Write the failing test**

```js
// touchdesigner/maskcombiner/test_maskops.mjs
import assert from 'node:assert/strict';
import {
  makeBitmap, cloneBitmap, extractPieces, union, subtract, countPixels,
  fillVoids, dilate, erode,
} from './maskops.mjs';

function bmFromRows(rows) {
  const h = rows.length, w = rows[0].length;
  const bm = makeBitmap(w, h);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++)
      bm.data[y * w + x] = rows[y][x] === '#' ? 1 : 0;
  return bm;
}
function rowsFromBm(bm) {
  const out = [];
  for (let y = 0; y < bm.h; y++) {
    let s = '';
    for (let x = 0; x < bm.w; x++) s += bm.data[y * bm.w + x] ? '#' : '.';
    out.push(s);
  }
  return out;
}

// extractPieces: two ids -> two bitmaps, 0 is background
{
  const ids = new Uint8Array([0, 3, 3, 0, 7, 0]);
  const pieces = extractPieces(ids, 3, 2);
  assert.equal(pieces.size, 2);
  assert.deepEqual(Array.from(pieces.get(3).data), [0, 1, 1, 0, 0, 0]);
  assert.deepEqual(Array.from(pieces.get(7).data), [0, 0, 0, 0, 1, 0]);
}

// union / subtract / countPixels / clone independence
{
  const a = bmFromRows(['##.', '...']);
  const b = bmFromRows(['.#.', '..#']);
  assert.deepEqual(rowsFromBm(union(a, b)), ['##.', '..#']);
  assert.deepEqual(rowsFromBm(subtract(a, b)), ['#..', '...']);
  assert.equal(countPixels(a), 2);
  const c = cloneBitmap(a);
  c.data[0] = 0;
  assert.equal(a.data[0], 1);
}

// fillVoids: donut hole fills, border-open bay does not
{
  const donut = bmFromRows([
    '#####',
    '#...#',
    '#.#.#',
    '#...#',
    '#####',
  ]);
  assert.deepEqual(rowsFromBm(fillVoids(donut)), [
    '#####', '#####', '#####', '#####', '#####',
  ]);
  const bay = bmFromRows([
    '#####',
    '#...#',
    '#####',
    '.....',
    '.....',
  ]);
  // hole in bay is enclosed -> fills; open bottom rows stay empty
  assert.deepEqual(rowsFromBm(fillVoids(bay)), [
    '#####', '#####', '#####', '.....', '.....',
  ]);
}

// dilate / erode, 8-neighbor, border-safe
{
  const dot = bmFromRows(['.....', '..#..', '.....']);
  assert.deepEqual(rowsFromBm(dilate(dot)), ['.###.', '.###.', '.###.']);
  const block = bmFromRows(['###', '###', '###']);
  assert.deepEqual(rowsFromBm(erode(block)), ['...', '.#.', '...']);
  // erode below 3x3 -> empty, never throws
  assert.equal(countPixels(erode(dot)), 0);
}

console.log('task1 ok');
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node touchdesigner/maskcombiner/test_maskops.mjs`
Expected: FAIL — `Cannot find module ... maskops.mjs`

- [ ] **Step 3: Write minimal implementation**

```js
// touchdesigner/maskcombiner/maskops.mjs
// Pure bitmap ops shared by the webapp and node tests.
// A Bitmap is { w, h, data: Uint8Array } with values 0/1. Ops return new bitmaps.

export function makeBitmap(w, h) {
  return { w, h, data: new Uint8Array(w * h) };
}

export function cloneBitmap(bm) {
  return { w: bm.w, h: bm.h, data: new Uint8Array(bm.data) };
}

export function extractPieces(ids, w, h) {
  const pieces = new Map();
  for (let i = 0; i < w * h; i++) {
    const id = ids[i];
    if (id === 0) continue;
    let bm = pieces.get(id);
    if (!bm) { bm = makeBitmap(w, h); pieces.set(id, bm); }
    bm.data[i] = 1;
  }
  return pieces;
}

export function union(a, b) {
  const out = makeBitmap(a.w, a.h);
  for (let i = 0; i < out.data.length; i++) out.data[i] = a.data[i] | b.data[i];
  return out;
}

export function subtract(a, b) {
  const out = makeBitmap(a.w, a.h);
  for (let i = 0; i < out.data.length; i++) out.data[i] = a.data[i] & (b.data[i] ? 0 : 1);
  return out;
}

export function countPixels(bm) {
  let n = 0;
  for (let i = 0; i < bm.data.length; i++) n += bm.data[i];
  return n;
}

export function fillVoids(bm) {
  const { w, h, data } = bm;
  const outside = new Uint8Array(w * h);
  const stack = [];
  const seed = (i) => {
    if (!data[i] && !outside[i]) { outside[i] = 1; stack.push(i); }
  };
  for (let x = 0; x < w; x++) { seed(x); seed((h - 1) * w + x); }
  for (let y = 0; y < h; y++) { seed(y * w); seed(y * w + w - 1); }
  while (stack.length) {
    const i = stack.pop();
    const x = i % w, y = (i - x) / w;
    if (x > 0) seed(i - 1);
    if (x < w - 1) seed(i + 1);
    if (y > 0) seed(i - w);
    if (y < h - 1) seed(i + w);
  }
  const out = makeBitmap(w, h);
  for (let i = 0; i < w * h; i++) out.data[i] = outside[i] ? 0 : 1;
  return out;
}

export function dilate(bm) {
  const { w, h, data } = bm;
  const out = makeBitmap(w, h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let v = 0;
      for (let dy = -1; dy <= 1 && !v; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= h) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= w) continue;
          if (data[ny * w + nx]) { v = 1; break; }
        }
      }
      out.data[y * w + x] = v;
    }
  }
  return out;
}

export function erode(bm) {
  const { w, h, data } = bm;
  const out = makeBitmap(w, h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let v = 1;
      for (let dy = -1; dy <= 1 && v; dy++) {
        const ny = y + dy;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= w || ny < 0 || ny >= h || !data[ny * w + nx]) { v = 0; break; }
        }
      }
      out.data[y * w + x] = v;
    }
  }
  return out;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node touchdesigner/maskcombiner/test_maskops.mjs`
Expected: `task1 ok`

- [ ] **Step 5: Commit**

```powershell
git add touchdesigner/maskcombiner/maskops.mjs touchdesigner/maskcombiner/test_maskops.mjs
git commit -m "feat(maskcombiner): core bitmap ops with node tests"
```

---

### Task 2: maskops.mjs — loop geometry, lasso test, history

**Files:**
- Modify: `touchdesigner/maskcombiner/maskops.mjs` (append)
- Test: `touchdesigner/maskcombiner/test_maskops.mjs` (append)

**Interfaces:**
- Consumes: Task 1 exports.
- Produces (used by Tasks 5, 6): `rasterizeLoop(points: {x,y}[], w, h) -> Bitmap` (closed even-odd interior fill), `fractionInside(piece, region) -> number` (0 for empty piece), `pointNearPiece(bm, x, y, tol) -> boolean`, `makeHistory(limit=50) -> { push(pieceId, bitmap), pop() -> {pieceId, bitmap}|null, length }` (push stores a clone; over limit drops oldest).

- [ ] **Step 1: Append failing tests**

```js
// append to test_maskops.mjs (before the final console.log; adjust import line)
import {
  rasterizeLoop, fractionInside, pointNearPiece, makeHistory,
} from './maskops.mjs';

// rasterizeLoop: axis-aligned square, closed implicitly
{
  const loop = rasterizeLoop(
    [{ x: 1, y: 1 }, { x: 4, y: 1 }, { x: 4, y: 4 }, { x: 1, y: 4 }], 6, 6);
  assert.deepEqual(rowsFromBm(loop), [
    '......',
    '.###..',
    '.###..',
    '.###..',
    '......',
    '......',
  ]);
  // degenerate stroke (<3 points) rasterizes to empty
  assert.equal(countPixels(rasterizeLoop([{ x: 1, y: 1 }, { x: 3, y: 3 }], 6, 6)), 0);
}

// fractionInside
{
  const piece = bmFromRows(['##..', '##..']);
  const region = bmFromRows(['#...', '#...']);
  assert.equal(fractionInside(piece, region), 0.5);
  assert.equal(fractionInside(makeBitmap(4, 2), region), 0);
}

// pointNearPiece: tolerance window
{
  const bm = bmFromRows(['.....', '..#..', '.....']);
  assert.equal(pointNearPiece(bm, 2, 1, 0), true);
  assert.equal(pointNearPiece(bm, 4, 1, 1), false);
  assert.equal(pointNearPiece(bm, 4, 1, 2), true);
  assert.equal(pointNearPiece(bm, -1, -1, 3), true); // window clamps to bounds
}

// history: clone-on-push, LIFO, cap
{
  const h = makeHistory(2);
  const bm = bmFromRows(['#.']);
  h.push(5, bm);
  bm.data[0] = 0;
  h.push(6, bmFromRows(['.#']));
  h.push(7, bmFromRows(['##'])); // evicts pieceId 5
  assert.equal(h.length, 2);
  assert.equal(h.pop().pieceId, 7);
  const last = h.pop();
  assert.equal(last.pieceId, 6);
  assert.equal(h.pop(), null);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node touchdesigner/maskcombiner/test_maskops.mjs`
Expected: FAIL — `rasterizeLoop` not exported

- [ ] **Step 3: Append implementation to maskops.mjs**

```js
// Even-odd scanline fill of the polygon formed by closing points end->start.
export function rasterizeLoop(points, w, h) {
  const out = makeBitmap(w, h);
  if (!points || points.length < 3) return out;
  for (let y = 0; y < h; y++) {
    const yc = y + 0.5;
    const xs = [];
    for (let i = 0; i < points.length; i++) {
      const a = points[i], b = points[(i + 1) % points.length];
      if ((a.y <= yc && b.y > yc) || (b.y <= yc && a.y > yc)) {
        xs.push(a.x + ((yc - a.y) / (b.y - a.y)) * (b.x - a.x));
      }
    }
    xs.sort((p, q) => p - q);
    for (let k = 0; k + 1 < xs.length; k += 2) {
      const x0 = Math.max(0, Math.ceil(xs[k] - 0.5));
      const x1 = Math.min(w - 1, Math.floor(xs[k + 1] - 0.5));
      for (let x = x0; x <= x1; x++) out.data[y * w + x] = 1;
    }
  }
  return out;
}

export function fractionInside(piece, region) {
  let total = 0, inside = 0;
  for (let i = 0; i < piece.data.length; i++) {
    if (piece.data[i]) { total++; if (region.data[i]) inside++; }
  }
  return total === 0 ? 0 : inside / total;
}

export function pointNearPiece(bm, x, y, tol) {
  const x0 = Math.max(0, Math.round(x) - tol), x1 = Math.min(bm.w - 1, Math.round(x) + tol);
  const y0 = Math.max(0, Math.round(y) - tol), y1 = Math.min(bm.h - 1, Math.round(y) + tol);
  for (let yy = y0; yy <= y1; yy++)
    for (let xx = x0; xx <= x1; xx++)
      if (bm.data[yy * bm.w + xx]) return true;
  return false;
}

export function makeHistory(limit = 50) {
  const stack = [];
  return {
    push(pieceId, bitmap) {
      stack.push({ pieceId, bitmap: cloneBitmap(bitmap) });
      if (stack.length > limit) stack.shift();
    },
    pop() { return stack.pop() || null; },
    get length() { return stack.length; },
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node touchdesigner/maskcombiner/test_maskops.mjs`
Expected: `task1 ok`

- [ ] **Step 5: Commit**

```powershell
git add touchdesigner/maskcombiner/maskops.mjs touchdesigner/maskcombiner/test_maskops.mjs
git commit -m "feat(maskcombiner): loop rasterize, lasso fraction, history"
```

---

### Task 3: WebServer callbacks source + name-logic tests

**Files:**
- Create: `touchdesigner/maskcombiner/webserver_callbacks.py`
- Test: `touchdesigner/maskcombiner/test_callbacks.py`

**Interfaces:**
- Produces: `sanitize_name(raw) -> str` (valid TD op name or `''`), `unique_name(base, existing: set) -> str`. `onHTTPRequest` handling `GET /`, `GET /maskops.mjs`, `GET /mask`, `POST /send` per spec. Module top-level imports only stdlib (importable outside TD; all `op()`/`parent()` calls stay inside handlers).
- Consumes: Task 6's client POSTs `{"name": str, "png_base64": str}` to `/send` and receives `{"ok": true, "out_path": str, "file": str}` or `{"ok": false, "error": str}`.

- [ ] **Step 1: Write the failing test**

```python
# touchdesigner/maskcombiner/test_callbacks.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from webserver_callbacks import sanitize_name, unique_name

assert sanitize_name('Third Eye!') == 'Third_Eye'
assert sanitize_name('  hat  ') == 'hat'
assert sanitize_name('9lives') == 'Mask_9lives'
assert sanitize_name('___') == ''
assert sanitize_name('') == ''
assert sanitize_name('a' * 100) == 'a' * 64
assert unique_name('hat', {'in1'}) == 'hat'
assert unique_name('hat', {'hat'}) == 'hat_2'
assert unique_name('hat', {'hat', 'hat_2'}) == 'hat_3'
print('task3 ok')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python touchdesigner/maskcombiner/test_callbacks.py`
Expected: FAIL — no module `webserver_callbacks`

- [ ] **Step 3: Write the callbacks module**

```python
# touchdesigner/maskcombiner/webserver_callbacks.py
"""Callbacks for cont_mask_combiner/webserver_mask (port 9981).

Serves the mask-combiner webapp and bakes sent masks into named out TOPs.
Source of truth is this repo file; the in-TD textDAT is loaded from it.
Only stdlib at module import time so tests can import it outside TD.
"""

import base64
import json
import os
import re
import tempfile
import time

APP_DIR = r'C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\maskcombiner'
SENT_DIR = r'C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\assets\sent_masks'
MAX_BODY = 32 * 1024 * 1024


def sanitize_name(raw):
    s = re.sub(r'[^A-Za-z0-9_]', '_', str(raw).strip())
    s = s.strip('_')
    if not s:
        return ''
    if not s[0].isalpha():
        s = 'Mask_' + s
    return s[:64]


def unique_name(base, existing):
    if base not in existing:
        return base
    i = 2
    while '%s_%d' % (base, i) in existing:
        i += 1
    return '%s_%d' % (base, i)


def onHTTPRequest(webServerDAT, request, response):
    try:
        return _dispatch(webServerDAT, request, response)
    except Exception as e:
        response['statusCode'] = 500
        response['statusReason'] = 'Internal Server Error'
        response['data'] = json.dumps({'ok': False, 'error': str(e)})
        return response


def _dispatch(webServerDAT, request, response):
    uri = request['uri']
    method = request['method']
    if method == 'GET' and uri == '/':
        return _serve_file(os.path.join(APP_DIR, 'index.html'),
                           'text/html; charset=utf-8', response)
    if method == 'GET' and uri == '/maskops.mjs':
        return _serve_file(os.path.join(APP_DIR, 'maskops.mjs'),
                           'text/javascript; charset=utf-8', response)
    if method == 'GET' and uri == '/mask':
        return _serve_mask(webServerDAT, response)
    if method == 'POST' and uri == '/send':
        return _handle_send(webServerDAT, request, response)
    response['statusCode'] = 404
    response['statusReason'] = 'Not Found'
    response['data'] = json.dumps({'ok': False, 'error': 'unknown endpoint %s %s' % (method, uri)})
    return response


def _serve_file(path, ctype, response):
    with open(path, 'rb') as f:
        response['data'] = f.read()
    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['content-type'] = ctype
    response['Cache-Control'] = 'no-store'
    return response


def _serve_mask(webServerDAT, response):
    src = webServerDAT.parent().op('in1')
    if src is None:
        response['statusCode'] = 500
        response['data'] = json.dumps({'ok': False, 'error': 'in1 missing'})
        return response
    tmp = os.path.join(tempfile.gettempdir(), 'maskcombiner_in1.png')
    src.save(tmp)
    with open(tmp, 'rb') as f:
        response['data'] = f.read()
    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['content-type'] = 'image/png'
    response['Cache-Control'] = 'no-store'
    return response


def _handle_send(webServerDAT, request, response):
    body = request.get('data', b'')
    if isinstance(body, bytes):
        body = body.decode('utf-8')
    if len(body) > MAX_BODY:
        return _err(response, 400, 'body too large')
    payload = json.loads(body)
    name = sanitize_name(payload.get('name', ''))
    if not name:
        return _err(response, 400, 'invalid name')
    try:
        png = base64.b64decode(payload.get('png_base64', ''), validate=True)
    except Exception:
        return _err(response, 400, 'bad png_base64')
    if not png.startswith(b'\x89PNG'):
        return _err(response, 400, 'not a png')

    comp = webServerDAT.parent()
    existing = set(c.name for c in comp.children)
    name = unique_name(name, existing)

    os.makedirs(SENT_DIR, exist_ok=True)
    fp = os.path.join(SENT_DIR, '%s_%d.png' % (name, int(time.time() * 1000)))
    while os.path.exists(fp):  # never overwrite
        fp = os.path.join(SENT_DIR, '%s_%d.png' % (name, int(time.time() * 1000) + 1))
    with open(fp, 'wb') as f:
        f.write(png)

    n_sent = len([c for c in comp.children if 'sentmask' in c.tags and c.type == 'out'])
    mfi = comp.create(moviefileinTOP, 'mfi_' + name)
    mfi.par.file = fp.replace('\\', '/')
    for pname in ('filtertype', 'inputfiltertype'):
        if hasattr(mfi.par, pname):
            getattr(mfi.par, pname).val = 'nearest'
    mfi.tags.add('sentmask')
    mfi.nodeX, mfi.nodeY = 400, -300 - 200 * n_sent

    out_op = comp.create(outTOP, name)
    out_op.tags.add('sentmask')
    out_op.nodeX, out_op.nodeY = 700, -300 - 200 * n_sent
    out_op.inputConnectors[0].connect(mfi)

    src = comp.op('in1')
    if src is not None and (mfi.width != src.width or mfi.height != src.height):
        mfi.destroy()
        out_op.destroy()
        try:
            os.remove(fp)
        except OSError:
            pass
        return _err(response, 400, 'png dimensions do not match in1 (%dx%d)' % (src.width, src.height))

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['content-type'] = 'application/json'
    response['data'] = json.dumps({'ok': True, 'out_path': out_op.path, 'file': fp.replace('\\', '/')})
    return response


def _err(response, code, msg):
    response['statusCode'] = code
    response['statusReason'] = 'Bad Request'
    response['content-type'] = 'application/json'
    response['data'] = json.dumps({'ok': False, 'error': msg})
    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python touchdesigner/maskcombiner/test_callbacks.py`
Expected: `task3 ok`

- [ ] **Step 5: Commit**

```powershell
git add touchdesigner/maskcombiner/webserver_callbacks.py touchdesigner/maskcombiner/test_callbacks.py
git commit -m "feat(maskcombiner): webserver callbacks with sanitized no-overwrite sends"
```

---

### Task 4: Build the TD container over the bridge

**Files:**
- None in repo (live TD network). Uses `touchdesigner/maskcombiner/webserver_callbacks.py` from Task 3.

**Interfaces:**
- Consumes: Task 3 callbacks file on disk.
- Produces: `/project1/cont_mask_combiner` with `in1` (wired from `/project1/moviefilein3`), `webserver_mask` (port 9981, active), `webserver_mask_callbacks` textDAT. Serving `GET /` and `GET /mask`.

- [ ] **Step 1: Checkpoint before mutating**

Bridge: `save_checkpoint` with comp path `/project1`, name `pre-mask-combiner`, description `before building cont_mask_combiner webapp container`.

- [ ] **Step 2: Create container + internals via execute_script**

```python
proj = op('/project1')
ref = op('/project1/cont_region_split2')
c = proj.create(containerCOMP, 'cont_mask_combiner')
c.nodeX = ref.nodeX if ref else 0
c.nodeY = (ref.nodeY - 300) if ref else 0

i1 = c.create(inTOP, 'in1')
i1.nodeX, i1.nodeY = 0, 0
for pname in ('filtertype', 'inputfiltertype'):
    if hasattr(i1.par, pname):
        getattr(i1.par, pname).val = 'nearest'

cb = c.create(textDAT, 'webserver_mask_callbacks')
cb.nodeX, cb.nodeY = 0, -200
src_path = r'C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\maskcombiner\webserver_callbacks.py'
with open(src_path, encoding='utf-8') as f:
    code = f.read()
compile(code, 'webserver_mask_callbacks', 'exec')  # syntax gate before it goes live
cb.text = code

ws = c.create(webserverDAT, 'webserver_mask')
ws.nodeX, ws.nodeY = 200, -200
ws.par.port = 9981
ws.par.callbacks = 'webserver_mask_callbacks'
ws.par.active = True

src = op('/project1/moviefilein3')
c.inputConnectors[0].connect(src)
print('built', c.path, 'in1 wired:', bool(i1.inputs))
```

Send via bridge `execute_script`, undo_label `build cont_mask_combiner`.

- [ ] **Step 3: Verify server + errors**

- Bridge `get_errors` → expect no new errors from `/project1/cont_mask_combiner`.
- PowerShell: `(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9981/mask).RawContentLength` → non-zero; first bytes are PNG (`(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9981/mask).Content[0..3]` → `137 80 78 71`).
- `GET /` returns 404-free HTML only after Task 5; at this point expect a 500/`FileNotFoundError` JSON for `/` — that is acceptable, `/mask` working is the gate.

- [ ] **Step 4: Checkpoint after verification**

Bridge: `save_checkpoint` on `/project1`, name `post-mask-combiner-shell`, description `cont_mask_combiner container + webserver serving /mask`.

---

### Task 5: index.html — load, render, click select, stripes, outline, hover

**Files:**
- Create: `touchdesigner/maskcombiner/index.html`

**Interfaces:**
- Consumes: `GET /mask` (PNG, R channel = piece ID), `/maskops.mjs` exports from Tasks 1–2.
- Produces: global app state used by Task 6 — `pieces: Map<int, Bitmap>`, `selected: number[]` (order = selection order, last = active), `hoverId`, `markDirty(id)` cache invalidation, `pieceAt(ix, iy) -> id|0`, `setStatus(msg)`, `history = makeHistory(50)`, and `tool` state machine with `currentTool` (`'select' | 'lasso' | 'knife' | 'addloop'`) plus stroke capture arrays. Toolbar button ids: `tool-select`, `tool-lasso`, `tool-fill`, `tool-knife`, `tool-addloop`, `tool-outset`, `tool-inset`, `send-name`, `send-btn`, `status`.

- [ ] **Step 1: Write index.html (structure + rendering + click selection)**

```html
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mask Combiner</title>
<style>
  html, body { margin: 0; height: 100%; background: #111; color: #ddd;
               font: 13px system-ui, sans-serif; }
  #toolbar { display: flex; gap: 6px; align-items: center; padding: 8px;
             background: #1c1c1c; flex-wrap: wrap; }
  #toolbar button { background: #2a2a2a; color: #ddd; border: 1px solid #444;
                    padding: 6px 10px; cursor: pointer; }
  #toolbar button.active-tool { border-color: #4caf50; color: #4caf50; }
  #toolbar input { background: #222; color: #ddd; border: 1px solid #444; padding: 6px; }
  #status { margin-left: auto; opacity: 0.8; }
  #stage { position: relative; width: 100%; height: calc(100% - 46px); overflow: hidden; }
  canvas { position: absolute; left: 0; top: 0; image-rendering: pixelated; }
</style>
</head>
<body>
<div id="toolbar">
  <button id="tool-select">Select</button>
  <button id="tool-lasso">Lasso</button>
  <span style="border-left:1px solid #444; height:20px"></span>
  <button id="tool-fill">Fill Voids</button>
  <button id="tool-knife">Knife</button>
  <button id="tool-addloop">Add Loop</button>
  <button id="tool-outset">Outset</button>
  <button id="tool-inset">Inset</button>
  <span style="border-left:1px solid #444; height:20px"></span>
  <input id="send-name" placeholder="mask name" size="14">
  <button id="send-btn">Send Mask</button>
  <span id="status">loading mask…</span>
</div>
<div id="stage">
  <canvas id="base"></canvas>
  <canvas id="overlay"></canvas>
</div>
<script type="module">
import {
  makeBitmap, cloneBitmap, extractPieces, union, subtract, countPixels,
  fillVoids, dilate, erode, rasterizeLoop, fractionInside, pointNearPiece,
  makeHistory,
} from './maskops.mjs';

const state = {
  w: 0, h: 0,
  pieces: new Map(),      // id -> Bitmap (editable)
  selected: [],           // ids in selection order; last = active
  hoverId: 0,
  history: makeHistory(50),
  currentTool: 'select',
  stroke: null,           // [{x,y}] in image coords while dragging
  baseDirty: true,
  pieceCanvases: new Map(),  // id -> offscreen canvas (white where piece)
  edgeCanvases: new Map(),   // id -> offscreen canvas (green edge pixels)
  scale: 1,
};

const baseCv = document.getElementById('base');
const overlayCv = document.getElementById('overlay');
const statusEl = document.getElementById('status');
const setStatus = (m) => { statusEl.textContent = m; };

function activeId() { return state.selected.length ? state.selected[state.selected.length - 1] : 0; }

function pieceAt(ix, iy) {
  if (ix < 0 || iy < 0 || ix >= state.w || iy >= state.h) return 0;
  const i = iy * state.w + ix;
  const act = activeId();
  if (act && state.pieces.get(act).data[i]) return act;
  for (const [id, bm] of state.pieces) if (bm.data[i]) return id;
  return 0;
}

function markDirty(id) {
  state.baseDirty = true;
  state.pieceCanvases.delete(id);
  state.edgeCanvases.delete(id);
  if (id && countPixels(state.pieces.get(id) || makeBitmap(1, 1)) === 0) {
    state.pieces.delete(id);
    state.selected = state.selected.filter((s) => s !== id);
  }
}

function pieceCanvas(id) {
  let cv = state.pieceCanvases.get(id);
  if (cv) return cv;
  const bm = state.pieces.get(id);
  cv = document.createElement('canvas');
  cv.width = state.w; cv.height = state.h;
  const ctx = cv.getContext('2d');
  const img = ctx.createImageData(state.w, state.h);
  for (let i = 0; i < bm.data.length; i++) {
    if (bm.data[i]) { const o = i * 4; img.data[o] = img.data[o+1] = img.data[o+2] = 255; img.data[o+3] = 255; }
  }
  ctx.putImageData(img, 0, 0);
  state.pieceCanvases.set(id, cv);
  return cv;
}

function edgeCanvas(id) {
  let cv = state.edgeCanvases.get(id);
  if (cv) return cv;
  const bm = state.pieces.get(id);
  cv = document.createElement('canvas');
  cv.width = state.w; cv.height = state.h;
  const ctx = cv.getContext('2d');
  const img = ctx.createImageData(state.w, state.h);
  const { w, h, data } = bm;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x;
    if (!data[i]) continue;
    const edge = (x === 0 || !data[i-1]) || (x === w-1 || !data[i+1]) ||
                 (y === 0 || !data[i-w]) || (y === h-1 || !data[i+w]);
    if (edge) { const o = i * 4; img.data[o] = 40; img.data[o+1] = 255; img.data[o+2] = 90; img.data[o+3] = 255; }
  }
  ctx.putImageData(img, 0, 0);
  state.edgeCanvases.set(id, cv);
  return cv;
}

// stripe pattern tile (drawn once)
const stripeTile = document.createElement('canvas');
stripeTile.width = stripeTile.height = 16;
{
  const ctx = stripeTile.getContext('2d');
  ctx.strokeStyle = 'rgba(255, 210, 60, 0.85)';
  ctx.lineWidth = 3;
  for (let k = -16; k <= 32; k += 8) {
    ctx.beginPath(); ctx.moveTo(k, 16); ctx.lineTo(k + 16, 0); ctx.stroke();
  }
}

function redrawBase() {
  const ctx = baseCv.getContext('2d');
  const img = ctx.createImageData(state.w, state.h);
  for (const [, bm] of state.pieces) {
    for (let i = 0; i < bm.data.length; i++) {
      if (bm.data[i]) { const o = i * 4; img.data[o] = img.data[o+1] = img.data[o+2] = 230; }
    }
  }
  for (let i = 0; i < state.w * state.h; i++) img.data[i * 4 + 3] = 255;
  ctx.putImageData(img, 0, 0);
  state.baseDirty = false;
}

const scratch = document.createElement('canvas');
function drawFrame(t) {
  if (state.w) {
    if (state.baseDirty) redrawBase();
    const ctx = overlayCv.getContext('2d');
    ctx.clearRect(0, 0, state.w, state.h);
    // hover
    if (state.hoverId && !state.selected.includes(state.hoverId)) {
      ctx.globalAlpha = 0.18;
      ctx.drawImage(pieceCanvas(state.hoverId), 0, 0);
      ctx.globalAlpha = 1;
    }
    // animated stripes on every selected piece
    scratch.width = state.w; scratch.height = state.h;
    const sctx = scratch.getContext('2d');
    const off = (t / 40) % 16;
    for (const id of state.selected) {
      sctx.clearRect(0, 0, state.w, state.h);
      sctx.drawImage(pieceCanvas(id), 0, 0);
      sctx.globalCompositeOperation = 'source-in';
      sctx.save();
      sctx.translate(off, 0);
      sctx.fillStyle = sctx.createPattern(stripeTile, 'repeat');
      sctx.fillRect(-16, -16, state.w + 32, state.h + 32);
      sctx.restore();
      sctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 0.55;
      ctx.drawImage(scratch, 0, 0);
      ctx.globalAlpha = 1;
    }
    // green outline on active piece
    if (activeId()) ctx.drawImage(edgeCanvas(activeId()), 0, 0);
    // live stroke preview
    if (state.stroke && state.stroke.length > 1) {
      ctx.strokeStyle = state.currentTool === 'knife' ? '#ff5252'
        : state.currentTool === 'addloop' ? '#4caf50' : '#4fc3f7';
      ctx.lineWidth = Math.max(1, 1.5 / state.scale);
      ctx.beginPath();
      ctx.moveTo(state.stroke[0].x, state.stroke[0].y);
      for (const p of state.stroke) ctx.lineTo(p.x, p.y);
      ctx.stroke();
    }
  }
  requestAnimationFrame(drawFrame);
}
requestAnimationFrame(drawFrame);

function fitCanvases() {
  const stage = document.getElementById('stage');
  const sw = stage.clientWidth, sh = stage.clientHeight;
  state.scale = Math.min(sw / state.w, sh / state.h);
  for (const cv of [baseCv, overlayCv]) {
    cv.style.width = `${state.w * state.scale}px`;
    cv.style.height = `${state.h * state.scale}px`;
  }
}
window.addEventListener('resize', () => state.w && fitCanvases());

function eventToImage(ev) {
  const r = baseCv.getBoundingClientRect();
  return {
    x: Math.floor((ev.clientX - r.left) / r.width * state.w),
    y: Math.floor((ev.clientY - r.top) / r.height * state.h),
  };
}

async function loadMask() {
  const img = new Image();
  img.src = '/mask?ts=' + Date.now();
  await img.decode();
  state.w = img.naturalWidth; state.h = img.naturalHeight;
  baseCv.width = overlayCv.width = state.w;
  baseCv.height = overlayCv.height = state.h;
  const cv = document.createElement('canvas');
  cv.width = state.w; cv.height = state.h;
  const ctx = cv.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  const px = ctx.getImageData(0, 0, state.w, state.h).data;
  const ids = new Uint8Array(state.w * state.h);
  for (let i = 0; i < ids.length; i++) ids[i] = px[i * 4]; // R channel
  state.pieces = extractPieces(ids, state.w, state.h);
  state.baseDirty = true;
  fitCanvases();
  setStatus(`${state.pieces.size} pieces — click or lasso to select`);
}
loadMask().catch((e) => {
  setStatus('failed to load /mask — is TD running?');
  const b = document.createElement('button');
  b.textContent = 'Retry';
  b.onclick = () => location.reload();
  statusEl.appendChild(document.createTextNode(' '));
  statusEl.appendChild(b);
});

// ---- selection (click) + hover ----
function toggleSelect(id) {
  const i = state.selected.indexOf(id);
  if (i >= 0) state.selected.splice(i, 1);
  else state.selected.push(id);
}

overlayCv.addEventListener('pointermove', (ev) => {
  if (state.stroke) {
    state.stroke.push(eventToImage(ev));
    return;
  }
  const p = eventToImage(ev);
  state.hoverId = pieceAt(p.x, p.y);
});

overlayCv.addEventListener('pointerdown', (ev) => {
  const p = eventToImage(ev);
  if (state.currentTool === 'select') {
    const id = pieceAt(p.x, p.y);
    if (id) {
      toggleSelect(id);
      setStatus(`${state.selected.length} selected` +
        (activeId() ? ` — active: ${activeId()}` : ''));
    }
  } else {
    state.stroke = [p];
    overlayCv.setPointerCapture(ev.pointerId);
  }
});

// pointerup / tool actions arrive in Task 6; keep a stub that just clears strokes
overlayCv.addEventListener('pointerup', () => { state.stroke = null; });

// ---- toolbar tool switching ----
const toolButtons = { select: 'tool-select', lasso: 'tool-lasso', knife: 'tool-knife', addloop: 'tool-addloop' };
function setTool(name) {
  state.currentTool = name;
  for (const [t, idBtn] of Object.entries(toolButtons)) {
    document.getElementById(idBtn).classList.toggle('active-tool', t === name);
  }
}
for (const [t, idBtn] of Object.entries(toolButtons)) {
  document.getElementById(idBtn).onclick = () => setTool(t);
}
setTool('select');

// Task 6 wires: tool-fill, tool-outset, tool-inset, send-btn, Ctrl+Z,
// and replaces the pointerup stub with lasso/knife/addloop application.
window.__app = { state, setStatus, markDirty, pieceAt, activeId, toggleSelect, setTool,
                 maskops: { makeBitmap, cloneBitmap, union, subtract, countPixels,
                            fillVoids, dilate, erode, rasterizeLoop, fractionInside,
                            pointNearPiece } };
</script>
</body>
</html>
```

- [ ] **Step 2: Verify serving + rendering**

- Run: `node touchdesigner/maskcombiner/test_maskops.mjs` (still passes; app imports same module).
- PowerShell: `(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9981/).StatusCode` → 200, content contains `Mask Combiner`; `/maskops.mjs` → 200.
- Manual gate (user glance or screenshot in browser): mask appears as flat white-on-black composite; hovering highlights a piece; clicking toggles animated stripes; last-clicked shows green outline; clicking again deselects.

- [ ] **Step 3: Commit**

```powershell
git add touchdesigner/maskcombiner/index.html
git commit -m "feat(maskcombiner): webapp shell — flat composite render, click select, stripes + outline"
```

---

### Task 6: index.html — lasso, modify tools, undo, send

**Files:**
- Modify: `touchdesigner/maskcombiner/index.html` (replace the pointerup stub and the `Task 6 wires` comment block)

**Interfaces:**
- Consumes: `window.__app`-exposed state from Task 5 (same script scope — the code below lives inside the same `<script type="module">`), `POST /send` from Task 3.
- Produces: complete tool behavior per spec.

- [ ] **Step 1: Replace the pointerup stub with tool application**

Delete the line `overlayCv.addEventListener('pointerup', () => { state.stroke = null; });` and the trailing `Task 6 wires` comment + `window.__app` block, then add:

```js
function pushHistory(id) { state.history.push(id, state.pieces.get(id)); }

function applyToActive(fn, label) {
  const id = activeId();
  if (!id) { setStatus(`select a piece first (${label})`); return; }
  pushHistory(id);
  state.pieces.set(id, fn(state.pieces.get(id)));
  markDirty(id);
  setStatus(label);
}

overlayCv.addEventListener('pointerup', () => {
  const stroke = state.stroke;
  state.stroke = null;
  if (!stroke || stroke.length < 3) return;

  if (state.currentTool === 'lasso') {
    const region = rasterizeLoop(stroke, state.w, state.h);
    let lastOn = 0;
    for (const [id, bm] of state.pieces) {
      if (fractionInside(bm, region) >= 0.5) {
        toggleSelect(id);
        if (state.selected.includes(id)) lastOn = id;
      }
    }
    if (lastOn) { // toggled-on piece becomes active
      state.selected.splice(state.selected.indexOf(lastOn), 1);
      state.selected.push(lastOn);
    }
    setStatus(`${state.selected.length} selected`);
  } else if (state.currentTool === 'knife') {
    applyToActive((bm) => subtract(bm, rasterizeLoop(stroke, state.w, state.h)),
      'knife: loop interior removed');
  } else if (state.currentTool === 'addloop') {
    const id = activeId();
    if (!id) { setStatus('select a piece first (add loop)'); return; }
    const bm = state.pieces.get(id);
    const a = stroke[0], b = stroke[stroke.length - 1];
    if (!pointNearPiece(bm, a.x, a.y, 3) || !pointNearPiece(bm, b.x, b.y, 3)) {
      setStatus('add loop: both ends must touch the active piece');
      return;
    }
    applyToActive((cur) => union(cur, rasterizeLoop(stroke, state.w, state.h)),
      'add loop: region added');
  }
});

document.getElementById('tool-fill').onclick = () => applyToActive(fillVoids, 'voids filled');
document.getElementById('tool-outset').onclick = () => applyToActive(dilate, 'outset 1px');
document.getElementById('tool-inset').onclick = () => applyToActive(erode, 'inset 1px');

window.addEventListener('keydown', (ev) => {
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') {
    ev.preventDefault();
    const entry = state.history.pop();
    if (!entry) { setStatus('nothing to undo'); return; }
    state.pieces.set(entry.pieceId, entry.bitmap);
    markDirty(entry.pieceId);
    setStatus(`undid edit on piece ${entry.pieceId}`);
  }
});

document.getElementById('send-btn').onclick = async () => {
  const name = document.getElementById('send-name').value.trim();
  if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(name)) {
    setStatus('name must match [A-Za-z][A-Za-z0-9_]*'); return;
  }
  if (!state.selected.length) { setStatus('nothing selected'); return; }
  let combined = makeBitmap(state.w, state.h);
  for (const id of state.selected) combined = union(combined, state.pieces.get(id));
  const cv = document.createElement('canvas');
  cv.width = state.w; cv.height = state.h;
  const ctx = cv.getContext('2d');
  const img = ctx.createImageData(state.w, state.h);
  for (let i = 0; i < combined.data.length; i++) {
    const v = combined.data[i] ? 255 : 0, o = i * 4;
    img.data[o] = img.data[o+1] = img.data[o+2] = v;
    img.data[o+3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  const b64 = cv.toDataURL('image/png').split(',')[1];
  setStatus('sending…');
  try {
    const res = await fetch('/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, png_base64: b64 }),
    });
    const j = await res.json();
    setStatus(j.ok ? `sent -> ${j.out_path}` : `send failed: ${j.error}`);
  } catch (e) {
    setStatus(`send failed: ${e}`);
  }
};
```

- [ ] **Step 2: Verify logic via node + browser**

- Run: `node touchdesigner/maskcombiner/test_maskops.mjs` → passes (tool math unchanged, all covered).
- Manual gate in browser: lasso around two pieces toggles both; knife loop inside active piece cuts a hole (base render updates); add-loop with both ends on the piece bulges it, with ends off-piece shows the refusal message; Fill Voids closes the knife hole; Outset/Inset grow/shrink 1px; Ctrl+Z steps each edit back; Send with a name reports `sent -> /project1/cont_mask_combiner/<name>`.

- [ ] **Step 3: Commit**

```powershell
git add touchdesigner/maskcombiner/index.html
git commit -m "feat(maskcombiner): lasso, knife/add loops, fill voids, outset/inset, undo, send"
```

---

### Task 7: End-to-end verification, README, final checkpoint

**Files:**
- Create: `touchdesigner/maskcombiner/README.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Scripted E2E round-trip**

PowerShell:

```powershell
$mask = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9981/mask
$b64 = [Convert]::ToBase64String($mask.Content)
$body = @{ name = 'e2e_test'; png_base64 = $b64 } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9981/send -ContentType 'application/json' -Body $body
$r
```

Expected: `ok=True`, `out_path=/project1/cont_mask_combiner/e2e_test`, `file` under `assets/sent_masks/`.

- [ ] **Step 2: Verify TD side over the bridge**

- `get_operator_info` on `/project1/cont_mask_combiner/e2e_test` → exists, TOP.
- `execute_script`: `o = op('/project1/cont_mask_combiner/mfi_e2e_test'); s = op('/project1/cont_mask_combiner/in1'); print(o.width, o.height, s.width, s.height)` → matching dims.
- `get_errors` → clean.

- [ ] **Step 3: Clean up the E2E artifacts**

`execute_script` (undo_label `remove e2e test send`):

```python
import os
c = op('/project1/cont_mask_combiner')
mfi = c.op('mfi_e2e_test')
fp = mfi.par.file.eval() if mfi else None
for name in ('e2e_test', 'mfi_e2e_test'):
    o = c.op(name)
    if o: o.destroy()
if fp and os.path.exists(fp):
    os.remove(fp)
print('cleaned')
```

- [ ] **Step 4: README**

```markdown
# Mask Combiner v2 (`cont_mask_combiner`)

Visual replacement for the `cont_region_split` Submask-ID workflow. The container
serves a webapp at http://127.0.0.1:9981/ from `index.html` in this directory.

- `in1` — label field (R = pieceID/255), wired from `/project1/moviefilein3`.
- Click a piece to toggle select (animated stripes); last selected = active (green outline).
- Lasso toggles every piece ≥50% inside the loop.
- Toolbar edits the ACTIVE piece only: Fill Voids, Knife (closed loop removes interior),
  Add Loop (both stroke ends on the piece; enclosed region added), Outset/Inset (±1px).
  Ctrl+Z undoes the last edit.
- Send Mask unions all selected pieces into one white-on-black PNG, saved to
  `touchdesigner/assets/sent_masks/<name>_<ts>.png` (never overwritten), and creates
  `mfi_<name>` → `<name>` out TOP on the container.

Callbacks source of truth: `webserver_callbacks.py` (loaded into the
`webserver_mask_callbacks` textDAT). Tests: `node test_maskops.mjs`,
`python test_callbacks.py`. Spec:
`docs/superpowers/specs/2026-08-07-mask-combiner-webapp-design.md`.
```

- [ ] **Step 5: Final checkpoint + commit**

- Bridge: `save_checkpoint` on `/project1`, name `post-mask-combiner`, description `mask combiner v2 webapp verified end-to-end`.

```powershell
git add touchdesigner/maskcombiner/README.md
git commit -m "docs(maskcombiner): usage README; e2e verified"
```
