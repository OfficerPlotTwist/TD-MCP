# Color Mask Selection Webapp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A browser app (magic wand + select-by-color) that builds a live color mask served by a new `/project1/cont_colormask` container in the running TouchDesigner project.

**Architecture:** Connectivity is computed in the browser at gesture time (flood fill on a frame snapshot); TD applies `stencil ∩ live color test` per frame in one GLSL shader. Rules and the stencil travel to TD as container storage via the MCP bridge (`POST /execute` on port 9980); two Script TOPs re-emit them as data textures. A small stdlib Python server hosts the static page and proxies to the bridge.

**Tech Stack:** Python 3 stdlib (`http.server`, `zlib`, `urllib`), pytest, vanilla JS (canvas), Node's built-in `node --test` for the flood-fill module, TD GLSL TOPs + Script TOPs via the MCP bridge.

**Spec:** `docs/superpowers/specs/2026-08-07-color-mask-selection-webapp-design.md`

## Global Constraints

- Live TD session, unsaved-project gotcha: **never call `project.save()`** (untitled project pops a modal that hangs the bridge). Use the MCP `save_checkpoint` tool for restore points.
- **Never touch `/project1/MCP_Server`** or its server-control buttons.
- All mask-path TOPs use **nearest filtering**: set `inputfiltertype = 'nearest'` and `filtertype = 'nearest'` wherever those pars exist (guard with `hasattr`).
- `MAX_RULES = 32` (webapp refuses the 33rd gesture; validator rejects >32).
- Webapp server port **8902**; TD bridge at **`http://127.0.0.1:9980`**.
- Container storage keys: `colormask_rules`, `colormask_stencil`. Rules stored as tuples `(type_int, r, g, b, tol)` with `type_int` 0=wand, 1=bycolor; colors/tol are floats in normalized 0..1 space.
- Rule texture alpha encoding: `a = tol + 10.0*type_int`; sentinel pixel `a = -1.0` means "no rules".
- Color distance = Euclidean distance of normalized RGB (identical formula in JS and GLSL).
- Orientation: browser stencil is top-down; TD `copyNumpyArray` row 0 = bottom → the SEND script applies `np.flipud`.
- `execute_script` scoping gotcha: no closures/recursion in scripts sent to TD; keep them flat.
- Network layout: only ops pinned in `touchdesigner/layout.json` are managed; never move user ops. New ops get pinned in Task 7.
- Git: run git through **PowerShell**, not Bash. Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File Structure

```
touchdesigner/colormask/
  README.md                     # Task 7
  shaders/
    rules.frag                  # Task 5 (checked-in copy of the TD shader text)
    viz.frag                    # Task 5
  webapp/
    protocol.py                 # Task 1 — pure logic: validation, stencil codec, TD script builder
    server.py                   # Task 2 — HTTP endpoints + bridge client (imports protocol)
    static/
      index.html                # Task 4
      style.css                 # Task 4
      floodfill.js              # Task 3 — pure selection math (browser + node)
      app.js                    # Task 4 — UI state, gestures, SEND
  tests/
    test_protocol.py            # Task 1
    test_server.py              # Task 2
    floodfill.test.js           # Task 3
    integration_td.py           # Task 6 — manual script, needs live TD bridge
```

---

### Task 1: `protocol.py` — rule validation, stencil codec, SEND script builder

**Files:**
- Create: `touchdesigner/colormask/webapp/protocol.py`
- Test: `touchdesigner/colormask/tests/test_protocol.py`

**Interfaces:**
- Produces: `MAX_RULES: int = 32`; `validate_rules(rules: list[dict]) -> list[tuple]` (raises `ValueError`); `encode_stencil(raw: bytes) -> str`; `decode_stencil(b64: str) -> bytes`; `build_send_script(rules: list[tuple], w: int, h: int, stencil_b64: str) -> str`. Task 2 consumes all of these.

- [ ] **Step 1: Write the failing tests**

`touchdesigner/colormask/tests/test_protocol.py`:

```python
import base64
import os
import sys
import zlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webapp"))
import protocol


def test_validate_rules_ok():
    rules = [
        {"type": "wand", "color": [1.0, 0.0, 0.25], "tol": 0.1},
        {"type": "bycolor", "color": [0, 0.5, 1], "tol": 0.3},
    ]
    out = protocol.validate_rules(rules)
    assert out == [(0, 1.0, 0.0, 0.25, 0.1), (1, 0.0, 0.5, 1.0, 0.3)]


def test_validate_rules_empty_ok():
    assert protocol.validate_rules([]) == []


@pytest.mark.parametrize("bad", [
    "not a list",
    [{"type": "lasso", "color": [0, 0, 0], "tol": 0.1}],
    [{"type": "wand", "color": [0, 0], "tol": 0.1}],
    [{"type": "wand", "color": [0, 0, 2.0], "tol": 0.1}],
    [{"type": "wand", "color": [0, 0, 0], "tol": -0.1}],
    [{"type": "wand", "color": [0, 0, 0], "tol": 3.0}],
])
def test_validate_rules_rejects(bad):
    with pytest.raises(ValueError):
        protocol.validate_rules(bad)


def test_validate_rules_cap():
    rules = [{"type": "wand", "color": [0, 0, 0], "tol": 0.1}] * 33
    with pytest.raises(ValueError):
        protocol.validate_rules(rules)


def test_stencil_roundtrip():
    raw = bytes(range(256)) * 16          # 4096 bytes, all values
    b64 = protocol.encode_stencil(raw)
    assert protocol.decode_stencil(b64) == raw
    # it really is zlib+base64, not passthrough
    assert zlib.decompress(base64.b64decode(b64)) == raw


def test_build_send_script_contents():
    rules = protocol.validate_rules(
        [{"type": "bycolor", "color": [1, 0, 0], "tol": 0.2}])
    b64 = protocol.encode_stencil(bytes(64 * 64))
    script = protocol.build_send_script(rules, 64, 64, b64)
    assert "colormask_rules" in script
    assert "colormask_stencil" in script
    assert "(1, 1.0, 0.0, 0.0, 0.2)" in script
    assert "np.flipud" in script
    assert "script_stencil').cook(force=True)" in script
    assert "script_rules').cook(force=True)" in script
    assert b64 in script


def test_build_send_script_empty_rules():
    script = protocol.build_send_script([], 1, 1, protocol.encode_stencil(b"\x00"))
    assert "colormask_rules', [])" in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest touchdesigner/colormask/tests/test_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'protocol'`

- [ ] **Step 3: Write the implementation**

`touchdesigner/colormask/webapp/protocol.py`:

```python
"""Pure logic for the colormask webapp: rule validation, stencil codec,
and the TD-side SEND script builder. No I/O, no TD imports — testable anywhere."""
import base64
import zlib

MAX_RULES = 32
RULE_TYPES = ("wand", "bycolor")

CONTAINER = "/project1/cont_colormask"


def validate_rules(rules):
    """Normalize webapp rule dicts to (type_int, r, g, b, tol) tuples.

    type_int: 0 = wand (stencil-gated), 1 = bycolor (frame-wide).
    Colors and tol are normalized floats. Raises ValueError on any problem.
    """
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    if len(rules) > MAX_RULES:
        raise ValueError(f"too many rules: {len(rules)} > {MAX_RULES}")
    out = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            raise ValueError(f"rule {i}: must be an object")
        t = r.get("type")
        if t not in RULE_TYPES:
            raise ValueError(f"rule {i}: bad type {t!r}")
        color = r.get("color")
        if (not isinstance(color, (list, tuple)) or len(color) != 3
                or not all(isinstance(c, (int, float)) and 0.0 <= c <= 1.0
                           for c in color)):
            raise ValueError(f"rule {i}: color must be 3 floats in 0..1")
        tol = r.get("tol")
        if not isinstance(tol, (int, float)) or not 0.0 <= tol <= 2.0:
            raise ValueError(f"rule {i}: tol must be a float in 0..2")
        out.append((1 if t == "bycolor" else 0,
                    float(color[0]), float(color[1]), float(color[2]),
                    float(tol)))
    return out


def encode_stencil(raw):
    """bytes -> base64(zlib(bytes)) str, for embedding in the SEND script."""
    return base64.b64encode(zlib.compress(raw)).decode("ascii")


def decode_stencil(b64):
    """Inverse of encode_stencil (used by tests and debugging)."""
    return zlib.decompress(base64.b64decode(b64))


_SEND_TEMPLATE = """\
import base64, zlib
import numpy as np
c = op('{container}')
w, h = {w}, {h}
raw = zlib.decompress(base64.b64decode('{b64}'))
arr = np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(h, w)).copy()
c.store('colormask_stencil', {{'w': w, 'h': h, 'data': arr}})
c.store('colormask_rules', {rules!r})
op('{container}/script_stencil').cook(force=True)
op('{container}/script_rules').cook(force=True)
print('OK rules={n} stencil=%dx%d' % (w, h))
"""


def build_send_script(rules, w, h, stencil_b64):
    """Build the flat TD-side script that atomically stores stencil + rules
    then force-cooks the two Script TOPs. `rules` is validate_rules() output."""
    return _SEND_TEMPLATE.format(container=CONTAINER, w=w, h=h,
                                 b64=stencil_b64, rules=list(rules),
                                 n=len(rules))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest touchdesigner/colormask/tests/test_protocol.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

PowerShell:
```powershell
git add touchdesigner/colormask/webapp/protocol.py touchdesigner/colormask/tests/test_protocol.py
git commit -m @'
feat(colormask): protocol module - rule validation, stencil codec, SEND script builder

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 2: `server.py` — HTTP endpoints + bridge client

**Files:**
- Create: `touchdesigner/colormask/webapp/server.py`
- Test: `touchdesigner/colormask/tests/test_server.py`

**Interfaces:**
- Consumes: `protocol.validate_rules`, `protocol.encode_stencil`, `protocol.build_send_script`, `protocol.CONTAINER` (Task 1).
- Produces: `process_send(body: bytes, bridge_post) -> (int, dict)`; `process_frame(bridge_get) -> (int, bytes|None, dict|None)`; `bridge_post(path: str, payload: dict) -> (bool, dict|str)`; `bridge_get(path: str) -> (bool, dict|str)`; `main()` serving on 127.0.0.1:8902. Task 4's JS calls `GET /`, `GET /frame`, `POST /send`. Task 6 reuses `bridge_post`.

- [ ] **Step 1: Write the failing tests**

`touchdesigner/colormask/tests/test_server.py`:

```python
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webapp"))
import protocol
import server


def _body(rules, w=2, h=2, data=None):
    if data is None:
        data = bytes(w * h)
    return json.dumps({
        "rules": rules,
        "stencil": {"w": w, "h": h,
                    "data": base64.b64encode(data).decode("ascii")},
    }).encode("utf-8")


def test_send_ok_posts_execute():
    calls = []

    def fake_post(path, payload):
        calls.append((path, payload))
        return True, {"output": "OK rules=1 stencil=2x2", "errors": []}

    rules = [{"type": "bycolor", "color": [1, 0, 0], "tol": 0.2}]
    code, obj = server.process_send(_body(rules), fake_post)
    assert code == 200 and obj["ok"] is True and obj["rules"] == 1
    assert calls[0][0] == "/execute"
    assert "colormask_rules" in calls[0][1]["script"]
    assert calls[0][1]["undo_label"] == "colormask SEND"


def test_send_empty_rules_is_reset():
    def fake_post(path, payload):
        return True, {"output": "", "errors": []}
    code, obj = server.process_send(_body([]), fake_post)
    assert code == 200 and obj["rules"] == 0


def test_send_bad_json_400():
    code, obj = server.process_send(b"{nope", lambda p, d: (True, {}))
    assert code == 400


def test_send_bad_rule_400():
    rules = [{"type": "lasso", "color": [0, 0, 0], "tol": 0.1}]
    code, obj = server.process_send(_body(rules), lambda p, d: (True, {}))
    assert code == 400


def test_send_stencil_size_mismatch_400():
    body = _body([], w=4, h=4, data=bytes(3))
    code, obj = server.process_send(body, lambda p, d: (True, {}))
    assert code == 400


def test_send_bridge_down_503():
    code, obj = server.process_send(_body([]), lambda p, d: (False, "refused"))
    assert code == 503


def test_send_td_error_502():
    def fake_post(path, payload):
        return True, {"output": "", "errors": ["NameError: nope"]}
    code, obj = server.process_send(_body([]), fake_post)
    assert code == 502


def test_frame_ok():
    png = b"\x89PNG fake"
    def fake_get(path):
        assert path.startswith("/screenshot?path=")
        return True, {"image_b64": base64.b64encode(png).decode("ascii")}
    code, body, err = server.process_frame(fake_get)
    assert code == 200 and body == png and err is None


def test_frame_bridge_down_503():
    code, body, err = server.process_frame(lambda p: (False, "refused"))
    assert code == 503 and body is None


def test_frame_td_error_502():
    code, body, err = server.process_frame(lambda p: (True, {"error": "no such op"}))
    assert code == 502 and body is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest touchdesigner/colormask/tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Write the implementation**

`touchdesigner/colormask/webapp/server.py`:

```python
"""Colormask webapp server. Stdlib only, 127.0.0.1 only.

Usage: python server.py [--port 8902] [--open]

Serves the static app and proxies to the TD MCP bridge on :9980:
  GET  /       -> static/index.html (no-store)
  GET  /frame  -> PNG snapshot of /project1/cont_colormask/null_src
  POST /send   -> {rules, stencil} -> one atomic /execute against TD
"""
import argparse
import base64
import json
import os
import tempfile
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import protocol

BRIDGE_URL = "http://127.0.0.1:9980"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript",
                 ".css": "text/css"}


def bridge_post(path, payload):
    """POST JSON to the TD bridge. Returns (ok, parsed_json_or_error_str)."""
    try:
        req = urllib.request.Request(
            BRIDGE_URL + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return False, str(e)


def bridge_get(path):
    """GET from the TD bridge. Returns (ok, parsed_json_or_error_str)."""
    try:
        with urllib.request.urlopen(BRIDGE_URL + path, timeout=30) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return False, str(e)


def process_send(body, post):
    """Validate a /send body and push it to TD. Returns (status, json_obj)."""
    try:
        payload = json.loads(body.decode("utf-8"))
        rules = protocol.validate_rules(payload.get("rules", []))
        st = payload.get("stencil") or {}
        w, h = int(st.get("w", 1)), int(st.get("h", 1))
        raw = base64.b64decode(st["data"]) if st.get("data") else bytes(w * h)
        if len(raw) != w * h:
            return 400, {"error": f"stencil size mismatch: {len(raw)} != {w*h}"}
    except (ValueError, KeyError, TypeError) as e:
        return 400, {"error": str(e)}
    script = protocol.build_send_script(rules, w, h, protocol.encode_stencil(raw))
    ok, result = post("/execute", {"script": script,
                                   "undo_label": "colormask SEND"})
    if not ok:
        return 503, {"error": "TD bridge unreachable", "detail": result}
    if result.get("errors"):
        return 502, {"error": "TD execute failed", "detail": result["errors"]}
    return 200, {"ok": True, "rules": len(rules)}


def process_frame(get):
    """Snapshot null_src via the bridge. Returns (status, png_bytes, err_obj)."""
    save_dir = os.path.join(tempfile.gettempdir(), "colormask_frames")
    q = ("/screenshot?path="
         + urllib.parse.quote(protocol.CONTAINER + "/null_src", safe="")
         + "&save_dir=" + urllib.parse.quote(save_dir.replace("\\", "/"), safe=""))
    ok, result = get(q)
    if not ok:
        return 503, None, {"error": "TD bridge unreachable", "detail": result}
    if not isinstance(result, dict) or "image_b64" not in result:
        detail = result.get("error") if isinstance(result, dict) else result
        return 502, None, {"error": "screenshot failed", "detail": detail}
    return 200, base64.b64decode(result["image_b64"]), None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        if path == "/frame":
            code, png, err = process_frame(bridge_get)
            if code == 200:
                return self._bytes(png, "image/png")
            return self._json(err, code)
        ext = os.path.splitext(path)[1]
        fspath = os.path.normpath(os.path.join(STATIC_DIR, path.lstrip("/")))
        if not fspath.startswith(STATIC_DIR) or ext not in CONTENT_TYPES:
            return self._json({"error": "not found"}, 404)
        if not os.path.exists(fspath):
            return self._json({"error": "not found"}, 404)
        with open(fspath, "rb") as f:
            return self._bytes(f.read(), CONTENT_TYPES[ext])

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/send":
            return self._json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length", 0))
        code, obj = process_send(self.rfile.read(length), bridge_post)
        return self._json(obj, code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8902)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"colormask webapp: {url}")
    if args.open:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest touchdesigner/colormask/tests/test_server.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

PowerShell:
```powershell
git add touchdesigner/colormask/webapp/server.py touchdesigner/colormask/tests/test_server.py
git commit -m @'
feat(colormask): webapp server - static hosting, /frame snapshot, /send bridge proxy

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 3: `floodfill.js` — selection math (browser + node)

**Files:**
- Create: `touchdesigner/colormask/webapp/static/floodfill.js`
- Test: `touchdesigner/colormask/tests/floodfill.test.js`

**Interfaces:**
- Produces (global in browser, `module.exports` in node): `colorDist(r1,g1,b1,r2,g2,b2) -> float` (normalized Euclidean, 0..√3); `floodFill(data, w, h, sx, sy, tol) -> Uint8Array` (0/255 mask, 4-connectivity from seed); `byColorMask(data, w, h, seed, tol) -> Uint8Array` (`seed` = `[r,g,b]` 0..255, frame-wide test). `data` is RGBA `Uint8ClampedArray` (an `ImageData.data`). Task 4 consumes all three.
- The distance formula must match `shaders/rules.frag` (Task 5): `sqrt(dr²+dg²+db²)` on 0..1 channels.

- [ ] **Step 1: Write the failing tests**

`touchdesigner/colormask/tests/floodfill.test.js`:

```js
const test = require("node:test");
const assert = require("node:assert");
const { colorDist, floodFill, byColorMask } =
  require("../webapp/static/floodfill.js");

// 4x2 image: left 2x2 red block, right 2x2 blue block
//   R R B B
//   R R B B
function img() {
  const w = 4, h = 2;
  const d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      if (x < 2) { d[i] = 255; d[i + 2] = 0; }
      else { d[i] = 0; d[i + 2] = 255; }
      d[i + 1] = 0; d[i + 3] = 255;
    }
  }
  return { d, w, h };
}

test("colorDist normalized euclidean", () => {
  assert.strictEqual(colorDist(255, 0, 0, 255, 0, 0), 0);
  assert.ok(Math.abs(colorDist(255, 0, 0, 0, 0, 0) - 1.0) < 1e-9);
  assert.ok(Math.abs(colorDist(255, 255, 255, 0, 0, 0) - Math.sqrt(3)) < 1e-9);
});

test("floodFill selects connected same-color region only", () => {
  const { d, w, h } = img();
  const m = floodFill(d, w, h, 0, 0, 0.1);
  assert.deepStrictEqual(Array.from(m),
    [255, 255, 0, 0,
     255, 255, 0, 0]);
});

test("floodFill with huge tol takes everything connected", () => {
  const { d, w, h } = img();
  const m = floodFill(d, w, h, 0, 0, 2.0);
  assert.ok(Array.from(m).every(v => v === 255));
});

test("byColorMask selects disconnected matches", () => {
  const w = 4, h = 1;                      // R B R B
  const d = new Uint8ClampedArray(w * h * 4);
  for (let x = 0; x < w; x++) {
    const i = x * 4;
    if (x % 2 === 0) d[i] = 255; else d[i + 2] = 255;
    d[i + 3] = 255;
  }
  const m = byColorMask(d, w, h, [255, 0, 0], 0.1);
  assert.deepStrictEqual(Array.from(m), [255, 0, 255, 0]);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test touchdesigner/colormask/tests/floodfill.test.js`
Expected: FAIL with `Cannot find module '.../floodfill.js'`

- [ ] **Step 3: Write the implementation**

`touchdesigner/colormask/webapp/static/floodfill.js`:

```js
// Selection math shared by the browser app and node tests.
// colorDist MUST stay identical to distance() in shaders/rules.frag
// (Euclidean distance of normalized 0..1 RGB channels).
"use strict";

function colorDist(r1, g1, b1, r2, g2, b2) {
  const dr = (r1 - r2) / 255, dg = (g1 - g2) / 255, db = (b1 - b2) / 255;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

// data: RGBA Uint8ClampedArray. Returns Uint8Array (0/255), 4-connectivity
// flood from (sx, sy) over pixels within tol of the seed pixel's color.
function floodFill(data, w, h, sx, sy, tol) {
  const mask = new Uint8Array(w * h);
  if (sx < 0 || sy < 0 || sx >= w || sy >= h) return mask;
  const si = (sy * w + sx) * 4;
  const sr = data[si], sg = data[si + 1], sb = data[si + 2];
  const stack = [sy * w + sx];
  mask[sy * w + sx] = 255;
  while (stack.length) {
    const p = stack.pop();
    const x = p % w, y = (p - x) / w;
    const neighbors = [];
    if (x > 0) neighbors.push(p - 1);
    if (x < w - 1) neighbors.push(p + 1);
    if (y > 0) neighbors.push(p - w);
    if (y < h - 1) neighbors.push(p + w);
    for (const q of neighbors) {
      if (mask[q]) continue;
      const i = q * 4;
      if (colorDist(data[i], data[i + 1], data[i + 2], sr, sg, sb) <= tol) {
        mask[q] = 255;
        stack.push(q);
      }
    }
  }
  return mask;
}

// Frame-wide color test (the "select by color" tool): every pixel within
// tol of seed [r,g,b], disconnected regions included.
function byColorMask(data, w, h, seed, tol) {
  const mask = new Uint8Array(w * h);
  const [sr, sg, sb] = seed;
  for (let p = 0; p < w * h; p++) {
    const i = p * 4;
    if (colorDist(data[i], data[i + 1], data[i + 2], sr, sg, sb) <= tol) {
      mask[p] = 255;
    }
  }
  return mask;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { colorDist, floodFill, byColorMask };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test touchdesigner/colormask/tests/floodfill.test.js`
Expected: all PASS

- [ ] **Step 5: Commit**

PowerShell:
```powershell
git add touchdesigner/colormask/webapp/static/floodfill.js touchdesigner/colormask/tests/floodfill.test.js
git commit -m @'
feat(colormask): flood fill + by-color selection math, node-tested

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 4: Static UI — `index.html`, `style.css`, `app.js`

**Files:**
- Create: `touchdesigner/colormask/webapp/static/index.html`
- Create: `touchdesigner/colormask/webapp/static/style.css`
- Create: `touchdesigner/colormask/webapp/static/app.js`

**Interfaces:**
- Consumes: `floodFill`, `byColorMask` (Task 3, loaded as a plain script → globals); `GET /frame`, `POST /send` (Task 2).
- Produces: the complete user-facing app. SEND payload shape (must match Task 2's `process_send`): `{"rules": [{"type": "wand"|"bycolor", "color": [r,g,b] floats 0..1, "tol": float}], "stencil": {"w": int, "h": int, "data": base64 of raw uint8 bytes}}`.

Behavior being implemented (from spec): wand = mousedown samples seed → drag distance grows tol → live re-flood preview → release commits gesture; by-color = same gesture, frame-wide test; magenta overlay; chips list; Ctrl+Z pops newest gesture; SEND posts and clears; refresh button + `R` key; red banner on failure; refuse 33rd gesture. Flood buffer capped at 512 px max dimension.

- [ ] **Step 1: Write `index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TD Color Mask</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div id="toolbar">
  <button id="tool-wand" class="tool active">Wand</button>
  <button id="tool-bycolor" class="tool">By Color</button>
  <button id="refresh">Refresh (R)</button>
  <span id="status"></span>
</div>
<div id="banner" class="hidden"></div>
<div id="stage">
  <canvas id="view"></canvas>
  <canvas id="overlay"></canvas>
</div>
<div id="chips"></div>
<button id="send">SEND</button>
<script src="/floodfill.js"></script>
<script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `style.css`**

```css
* { box-sizing: border-box; margin: 0; }
body { background: #16161a; color: #e8e8ea; font: 14px/1.4 system-ui, sans-serif;
       height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
#toolbar { display: flex; gap: 8px; align-items: center; padding: 8px 12px;
           background: #202027; }
#toolbar button { background: #2d2d38; color: #e8e8ea; border: 1px solid #44445a;
                  border-radius: 4px; padding: 6px 14px; cursor: pointer; }
#toolbar button.tool.active { background: #4a4ad6; border-color: #6a6aff; }
#status { margin-left: auto; color: #9a9aa5; }
#banner { background: #7a1f2b; color: #ffd9de; padding: 8px 12px; }
#banner.hidden { display: none; }
#stage { position: relative; flex: 1; min-height: 0; display: flex;
         align-items: center; justify-content: center; }
#stage canvas { position: absolute; image-rendering: pixelated; }
#overlay { pointer-events: none; }
#view { cursor: crosshair; }
#chips { display: flex; gap: 6px; flex-wrap: wrap; padding: 8px 12px;
         min-height: 40px; background: #202027; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
        background: #2d2d38; border: 1px solid #44445a; border-radius: 12px;
        font-size: 12px; }
.chip .swatch { width: 14px; height: 14px; border-radius: 3px;
                border: 1px solid #0008; }
#send { position: fixed; right: 20px; bottom: 60px; padding: 14px 34px;
        font-size: 18px; font-weight: 700; background: #1fa860; color: #fff;
        border: none; border-radius: 8px; cursor: pointer;
        box-shadow: 0 4px 16px #0008; }
#send:disabled { background: #3a3a44; cursor: default; }
```

- [ ] **Step 3: Write `app.js`**

```js
// Colormask webapp UI. State lives here; selection math is in floodfill.js.
"use strict";

const TOL_PER_PIXEL = 1 / 300;   // drag-distance -> tolerance (tuning constant)
const MAX_TOL = 1.2;
const FLOOD_MAX_DIM = 512;       // flood buffer cap
const MAX_RULES = 32;            // must match protocol.MAX_RULES

const view = document.getElementById("view");
const overlay = document.getElementById("overlay");
const stage = document.getElementById("stage");
const banner = document.getElementById("banner");
const statusEl = document.getElementById("status");
const chipsEl = document.getElementById("chips");
const sendBtn = document.getElementById("send");

// Working state
let frameImg = null;         // full-res Image of the latest snapshot
let flood = null;            // {w, h, data} downscaled RGBA buffer
let gestures = [];           // {type, color:[r,g,b] 0..255, tol, region: Uint8Array|null}
let tool = "wand";
let drag = null;             // {sx, sy, seed:[r,g,b], startX, startY, preview}

function showBanner(msg) { banner.textContent = msg; banner.classList.remove("hidden"); }
function hideBanner() { banner.classList.add("hidden"); }
function setStatus(msg) { statusEl.textContent = msg; }

async function fetchFrame() {
  setStatus("fetching frame…");
  try {
    const resp = await fetch("/frame");
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || ("HTTP " + resp.status));
    }
    const blob = await resp.blob();
    const img = new Image();
    await new Promise((res, rej) => {
      img.onload = res; img.onerror = rej;
      img.src = URL.createObjectURL(blob);
    });
    frameImg = img;
    buildFloodBuffer();
    layout();
    redrawOverlay();
    hideBanner();
    setStatus(img.width + "×" + img.height);
  } catch (e) {
    showBanner("Frame fetch failed: " + e.message + " — is TD + the bridge up?");
    setStatus("");
  }
}

function buildFloodBuffer() {
  const scale = Math.min(1, FLOOD_MAX_DIM / Math.max(frameImg.width, frameImg.height));
  const w = Math.max(1, Math.round(frameImg.width * scale));
  const h = Math.max(1, Math.round(frameImg.height * scale));
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(frameImg, 0, 0, w, h);
  flood = { w, h, data: ctx.getImageData(0, 0, w, h).data };
}

function layout() {
  const scale = Math.min(stage.clientWidth / frameImg.width,
                         stage.clientHeight / frameImg.height);
  const dw = Math.round(frameImg.width * scale);
  const dh = Math.round(frameImg.height * scale);
  for (const c of [view, overlay]) {
    c.width = dw; c.height = dh;
    c.style.width = dw + "px"; c.style.height = dh + "px";
  }
  const ctx = view.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(frameImg, 0, 0, dw, dh);
}

// display coords -> flood buffer coords
function toFlood(ev) {
  const r = view.getBoundingClientRect();
  const x = Math.floor((ev.clientX - r.left) / r.width * flood.w);
  const y = Math.floor((ev.clientY - r.top) / r.height * flood.h);
  return [Math.max(0, Math.min(flood.w - 1, x)),
          Math.max(0, Math.min(flood.h - 1, y))];
}

function combinedMask(extra) {
  const m = new Uint8Array(flood.w * flood.h);
  const parts = gestures.map(g => g.region || liveMask(g)).concat(extra ? [extra] : []);
  for (const part of parts) {
    for (let i = 0; i < m.length; i++) if (part[i]) m[i] = 255;
  }
  return m;
}

// by-color gestures have no stored region; preview them live on this frame
function liveMask(g) {
  return byColorMask(flood.data, flood.w, flood.h, g.color, g.tol);
}

function redrawOverlay(previewMask) {
  const m = combinedMask(previewMask || null);
  const c = document.createElement("canvas");
  c.width = flood.w; c.height = flood.h;
  const ctx = c.getContext("2d");
  const id = ctx.createImageData(flood.w, flood.h);
  for (let i = 0; i < m.length; i++) {
    if (m[i]) {
      id.data[i * 4] = 255; id.data[i * 4 + 2] = 255; id.data[i * 4 + 3] = 140;
    }
  }
  ctx.putImageData(id, 0, 0);
  const octx = overlay.getContext("2d");
  octx.imageSmoothingEnabled = false;
  octx.clearRect(0, 0, overlay.width, overlay.height);
  octx.drawImage(c, 0, 0, overlay.width, overlay.height);
}

function renderChips() {
  chipsEl.innerHTML = "";
  gestures.forEach(g => {
    const chip = document.createElement("span");
    chip.className = "chip";
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = `rgb(${g.color[0]},${g.color[1]},${g.color[2]})`;
    chip.append(sw, `${g.type} tol ${g.tol.toFixed(2)}`);
    chipsEl.appendChild(chip);
  });
  sendBtn.disabled = false;
}

view.addEventListener("mousedown", ev => {
  if (!flood) return;
  if (gestures.length >= MAX_RULES) {
    showBanner(`Rule cap reached (${MAX_RULES}) — SEND or Ctrl+Z first.`);
    return;
  }
  const [sx, sy] = toFlood(ev);
  const i = (sy * flood.w + sx) * 4;
  drag = { sx, sy, seed: [flood.data[i], flood.data[i + 1], flood.data[i + 2]],
           startX: ev.clientX, startY: ev.clientY, preview: null, tol: 0 };
  updateDrag(ev);
});

window.addEventListener("mousemove", ev => { if (drag) updateDrag(ev); });

function updateDrag(ev) {
  const dist = Math.hypot(ev.clientX - drag.startX, ev.clientY - drag.startY);
  drag.tol = Math.min(MAX_TOL, dist * TOL_PER_PIXEL);
  drag.preview = tool === "wand"
    ? floodFill(flood.data, flood.w, flood.h, drag.sx, drag.sy, drag.tol)
    : byColorMask(flood.data, flood.w, flood.h, drag.seed, drag.tol);
  setStatus(`${tool} tol ${drag.tol.toFixed(2)}`);
  redrawOverlay(drag.preview);
}

window.addEventListener("mouseup", () => {
  if (!drag) return;
  gestures.push({ type: tool, color: drag.seed, tol: drag.tol,
                  region: tool === "wand" ? drag.preview : null });
  drag = null;
  renderChips();
  redrawOverlay();
});

window.addEventListener("keydown", ev => {
  if (ev.key === "z" && (ev.ctrlKey || ev.metaKey)) {
    ev.preventDefault();
    gestures.pop();
    renderChips();
    redrawOverlay();
  } else if (ev.key === "r" || ev.key === "R") {
    fetchFrame();
  }
});

document.getElementById("tool-wand").addEventListener("click", () => setTool("wand"));
document.getElementById("tool-bycolor").addEventListener("click", () => setTool("bycolor"));
function setTool(t) {
  tool = t;
  document.getElementById("tool-wand").classList.toggle("active", t === "wand");
  document.getElementById("tool-bycolor").classList.toggle("active", t === "bycolor");
}

document.getElementById("refresh").addEventListener("click", fetchFrame);

sendBtn.addEventListener("click", async () => {
  if (!flood) return;
  // combined stencil = union of wand regions only (by-color rules are frame-wide)
  const stencil = new Uint8Array(flood.w * flood.h);
  for (const g of gestures) {
    if (g.region) for (let i = 0; i < stencil.length; i++) {
      if (g.region[i]) stencil[i] = 255;
    }
  }
  const payload = {
    rules: gestures.map(g => ({
      type: g.type,
      color: g.color.map(c => Math.round(c / 255 * 10000) / 10000),
      tol: Math.round(g.tol * 10000) / 10000,
    })),
    stencil: { w: flood.w, h: flood.h,
               data: btoa(String.fromCharCode(...stencil)) },
  };
  sendBtn.disabled = true;
  setStatus("sending…");
  try {
    const resp = await fetch("/send", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const obj = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(obj.error || ("HTTP " + resp.status));
    gestures = [];
    renderChips();
    redrawOverlay();
    hideBanner();
    setStatus(`sent ${obj.rules} rule(s) — mask is live in TD`);
  } catch (e) {
    showBanner("SEND failed: " + e.message);
    setStatus("");
  } finally {
    sendBtn.disabled = false;
  }
});

window.addEventListener("resize", () => { if (frameImg) { layout(); redrawOverlay(); } });

fetchFrame();
```

Note: `btoa(String.fromCharCode(...stencil))` can hit argument limits on very large arrays; the flood buffer is capped at 512×512 = 262 144 bytes which exceeds safe spread limits in some browsers. Build the binary string in chunks instead — use this exact replacement in the payload construction:

```js
let bin = "";
for (let i = 0; i < stencil.length; i += 0x8000) {
  bin += String.fromCharCode.apply(null, stencil.subarray(i, i + 0x8000));
}
// then:  data: btoa(bin)
```

- [ ] **Step 4: Smoke test without TD**

Run: `python touchdesigner/colormask/webapp/server.py --port 8902` (background), then:
- `curl -s http://127.0.0.1:8902/ | findstr "TD Color Mask"` → serves the page
- `curl -s http://127.0.0.1:8902/app.js -o NUL -w "%{http_code}"` → `200`
- `curl -s http://127.0.0.1:8902/frame -w "\n%{http_code}"` → JSON error + `503` if the bridge is down, or PNG + `200` if TD is up (both acceptable here)

Expected: page + assets serve with 200; /frame degrades cleanly. Stop the server.

- [ ] **Step 5: Commit**

PowerShell:
```powershell
git add touchdesigner/colormask/webapp/static/index.html touchdesigner/colormask/webapp/static/style.css touchdesigner/colormask/webapp/static/app.js
git commit -m @'
feat(colormask): browser UI - wand drag-grows-tolerance, by-color, chips, Ctrl+Z, SEND

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 5: Build `/project1/cont_colormask` in the live TD project

**Files:**
- Create: `touchdesigner/colormask/shaders/rules.frag`
- Create: `touchdesigner/colormask/shaders/viz.frag`
- TD (via MCP bridge): new container `/project1/cont_colormask` and children.

**Interfaces:**
- Consumes: storage keys + rule tuple format from Task 1 (`colormask_rules` = list of `(type_int, r, g, b, tol)`, `colormask_stencil` = `{'w', 'h', 'data': np.uint8 (h,w) bottom-up}`).
- Produces: ops `in1`, `null_src`, `script_rules` (+`text_rules_cb`), `script_stencil` (+`text_stencil_cb`), `text_rules_frag`, `glsl_rules`, `text_viz_frag`, `glsl_viz`, `out_mask`, `out_viz`. Task 6 reads `out_mask`; the webapp snapshots `null_src`.

**Use the MCP touchdesigner tools** (`execute_script`, `get_operator_info`, `get_errors`, `save_checkpoint`). One script per step; keep scripts flat (no closures).

- [ ] **Step 1: Checkpoint `/project1`**

MCP tool: `save_checkpoint` on `/project1` (label like `pre-colormask`). Do NOT `project.save()` (untitled-project modal hangs the bridge).

- [ ] **Step 2: Write the shader files (repo copies)**

`touchdesigner/colormask/shaders/rules.frag`:

```glsl
// Combined color-mask rules. Inputs:
//   0 = source frame, 1 = stencil (R, bottom-up like all TOPs), 2 = rule texture (Nx1)
// Rule texel: rgb = reference color, a = tol + 10*type (type 1 = bycolor), a < 0 = no rules.
// distance() here MUST match colorDist() in webapp/static/floodfill.js.
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    vec3 src = texture(sTD2DInputs[0], uv).rgb;
    float stencil = texture(sTD2DInputs[1], uv).r;
    int n = textureSize(sTD2DInputs[2], 0).x;
    float m = 0.0;
    for (int i = 0; i < n; i++) {
        vec4 rule = texelFetch(sTD2DInputs[2], ivec2(i, 0), 0);
        if (rule.a < 0.0) continue;
        bool bycolor = rule.a >= 10.0;
        float tol = bycolor ? rule.a - 10.0 : rule.a;
        if (distance(src, rule.rgb) <= tol && (bycolor || stencil > 0.5)) {
            m = 1.0;
        }
    }
    fragColor = vec4(m, m, m, 1.0);
}
```

`touchdesigner/colormask/shaders/viz.frag`:

```glsl
// Source tinted magenta where the mask is on. Inputs: 0 = source, 1 = mask.
out vec4 fragColor;
void main() {
    vec3 src = texture(sTD2DInputs[0], vUV.st).rgb;
    float m = texture(sTD2DInputs[1], vUV.st).r;
    fragColor = vec4(mix(src, vec3(1.0, 0.0, 1.0), 0.6 * m), 1.0);
}
```

- [ ] **Step 3: Create the container and TOP chain**

`execute_script` (undo_label `colormask build 1/3`):

```python
root = op('/project1')
c = root.create(containerCOMP, 'cont_colormask')
c.nodeX, c.nodeY = 1900, -300
i = c.create(inTOP, 'in1');        i.nodeX, i.nodeY = 0, 0
ns = c.create(nullTOP, 'null_src'); ns.nodeX, ns.nodeY = 220, 0
sr = c.create(scriptTOP, 'script_rules');   sr.nodeX, sr.nodeY = 220, -400
ss = c.create(scriptTOP, 'script_stencil'); ss.nodeX, ss.nodeY = 220, -200
tr = c.create(textDAT, 'text_rules_frag');  tr.nodeX, tr.nodeY = 440, 200
gr = c.create(glslTOP, 'glsl_rules');       gr.nodeX, gr.nodeY = 440, 0
tv = c.create(textDAT, 'text_viz_frag');    tv.nodeX, tv.nodeY = 660, 200
gv = c.create(glslTOP, 'glsl_viz');         gv.nodeX, gv.nodeY = 660, -200
om = c.create(outTOP, 'out_mask');          om.nodeX, om.nodeY = 660, 0
ov = c.create(outTOP, 'out_viz');           ov.nodeX, ov.nodeY = 880, -200
ns.inputConnectors[0].connect(i)
gr.inputConnectors[0].connect(ns)
gr.inputConnectors[1].connect(ss)
gr.inputConnectors[2].connect(sr)
om.inputConnectors[0].connect(gr)
gv.inputConnectors[0].connect(ns)
gv.inputConnectors[1].connect(gr)
ov.inputConnectors[0].connect(gv)
for o in (i, ns, sr, ss, gr, gv, om, ov):
    for pname in ('inputfiltertype', 'filtertype'):
        if hasattr(o.par, pname):
            setattr(o.par, pname, 'nearest')
print('created', [x.name for x in c.children])
```

- [ ] **Step 4: Script TOP callbacks + shader DATs**

`execute_script` (undo_label `colormask build 2/3`) — note callback DATs are plain text DATs assigned via the Script TOPs' `callbacks` par; `op` paths inside callbacks resolve relative to the script op, and `parent()` is the container:

```python
c = op('/project1/cont_colormask')
cb_r = c.create(textDAT, 'text_rules_cb'); cb_r.nodeX, cb_r.nodeY = 0, -400
cb_s = c.create(textDAT, 'text_stencil_cb'); cb_s.nodeX, cb_s.nodeY = 0, -200
cb_r.text = '''import numpy as np

def onSetupParameters(scriptOp):
    return

def onPulse(par):
    return

def onCook(scriptOp):
    rules = parent().fetch('colormask_rules', [])
    n = max(1, len(rules))
    arr = np.zeros((1, n, 4), dtype=np.float32)
    if not rules:
        arr[0, 0, 3] = -1.0
    else:
        for i in range(len(rules)):
            t, r, g, b, tol = rules[i]
            arr[0, i, 0] = r
            arr[0, i, 1] = g
            arr[0, i, 2] = b
            arr[0, i, 3] = tol + (10.0 if t == 1 else 0.0)
    scriptOp.copyNumpyArray(arr)
    return
'''
cb_s.text = '''import numpy as np

def onSetupParameters(scriptOp):
    return

def onPulse(par):
    return

def onCook(scriptOp):
    st = parent().fetch('colormask_stencil', None)
    if st is None:
        arr = np.zeros((1, 1, 4), dtype=np.float32)
        arr[..., 3] = 1.0
    else:
        arr = np.zeros((st['h'], st['w'], 4), dtype=np.float32)
        arr[..., 0] = st['data'].astype(np.float32) / 255.0
        arr[..., 3] = 1.0
    scriptOp.copyNumpyArray(arr)
    return
'''
op('/project1/cont_colormask/script_rules').par.callbacks = 'text_rules_cb'
op('/project1/cont_colormask/script_stencil').par.callbacks = 'text_stencil_cb'
print('callbacks wired')
```

Then load the two shaders — because the shader text contains quotes, write it via the repo files. `execute_script` (undo_label `colormask build 3/3`), substituting `<REPO>` with the absolute repo path:

```python
c = op('/project1/cont_colormask')
with open(r'<REPO>\touchdesigner\colormask\shaders\rules.frag') as f:
    op('/project1/cont_colormask/text_rules_frag').text = f.read()
with open(r'<REPO>\touchdesigner\colormask\shaders\viz.frag') as f:
    op('/project1/cont_colormask/text_viz_frag').text = f.read()
op('/project1/cont_colormask/glsl_rules').par.pixeldat = 'text_rules_frag'
op('/project1/cont_colormask/glsl_viz').par.pixeldat = 'text_viz_frag'
print('shaders loaded')
```

- [ ] **Step 5: Verify structurally**

- MCP `get_operator_info` on `/project1/cont_colormask` — expect the 12 children from steps 3–4.
- MCP `get_errors` — expect no new errors from `cont_colormask` (GLSL compile errors would show here; a Script TOP warning before first cook is acceptable).
- `execute_script`: force-cook both script TOPs once (they emit their empty-state textures) and print resolutions:

```python
sr = op('/project1/cont_colormask/script_rules')
ss = op('/project1/cont_colormask/script_stencil')
sr.cook(force=True)
ss.cook(force=True)
gm = op('/project1/cont_colormask/glsl_rules')
print('rules', sr.width, sr.height, 'stencil', ss.width, ss.height, 'mask', gm.width, gm.height)
```

Expected: `rules 1 1 stencil 1 1` and a mask resolution (glsl output follows input 0; with `in1` unwired it may be the default 256×256 — fine).

- [ ] **Step 6: Checkpoint + commit shader files**

MCP `save_checkpoint` on `/project1` (label `colormask-built`).

PowerShell:
```powershell
git add touchdesigner/colormask/shaders/rules.frag touchdesigner/colormask/shaders/viz.frag
git commit -m @'
feat(colormask): TD container built - rules/viz shaders, script TOP data textures

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 6: End-to-end integration test against live TD

**Files:**
- Create: `touchdesigner/colormask/tests/integration_td.py`

**Interfaces:**
- Consumes: `protocol.build_send_script`/`validate_rules`/`encode_stencil` (Task 1), `server.bridge_post` (Task 2), the container (Task 5).
- Produces: a manually-run script (`python touchdesigner/colormask/tests/integration_td.py`) asserting GLSL == JS semantics. NOT collected by pytest (no `test_` prefix on file functions; guarded by `__main__`).

This is the ground truth that the browser preview and the live TD mask agree: red constant source, by-color hit, by-color miss, wand + top-half stencil (verifies the `flipud` orientation).

- [ ] **Step 1: Write the script**

`touchdesigner/colormask/tests/integration_td.py`:

```python
"""Integration check against the LIVE TD bridge. Run manually:

    python touchdesigner/colormask/tests/integration_td.py

Requires: TD running with the MCP bridge on :9980 and /project1/cont_colormask
built (plan Task 5). Creates a temporary 64x64 red constant wired into in1,
sends rules through the real SEND path, reads out_mask back, then cleans up.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webapp"))
import protocol
import server

W = H = 64


def run(script, label):
    ok, result = server.bridge_post("/execute", {"script": script,
                                                 "undo_label": label})
    if not ok:
        raise SystemExit(f"bridge unreachable: {result}")
    if result.get("errors"):
        raise SystemExit(f"TD error in {label!r}: {result['errors']}")
    return result.get("output", "")


def send(rules_dicts, stencil_raw, w=W, h=H):
    rules = protocol.validate_rules(rules_dicts)
    script = protocol.build_send_script(rules, w, h,
                                        protocol.encode_stencil(stencil_raw))
    return run(script, "colormask integration send")


def read_mask_quadrant_means():
    out = run("""
import numpy as np
a = op('/project1/cont_colormask/out_mask').numpyArray(delayed=False)
r = a[..., 0]
h2 = r.shape[0] // 2
print(float(r[h2:, :].mean()), float(r[:h2, :].mean()))
""", "colormask integration read")
    top_mean, bottom_mean = (float(x) for x in out.split())
    # numpyArray row 0 = bottom of frame, so a[h2:] is the TOP half
    return top_mean, bottom_mean


def main():
    # setup: red constant wired into in1
    run("""
root = op('/project1')
t = root.create(constantTOP, 'constant_cmtest')
t.nodeX, t.nodeY = 1900, -450
t.par.resolutionw = %d
t.par.resolutionh = %d
t.par.colorr, t.par.colorg, t.par.colorb = 1.0, 0.0, 0.0
op('/project1/cont_colormask').inputConnectors[0].connect(t)
print('setup ok')
""" % (W, H), "colormask integration setup")

    try:
        # 1: by-color red -> everything selected
        send([{"type": "bycolor", "color": [1, 0, 0], "tol": 0.1}], bytes(W * H))
        top, bottom = read_mask_quadrant_means()
        assert top == 1.0 and bottom == 1.0, f"bycolor red: {top}, {bottom}"

        # 2: by-color blue -> nothing selected
        send([{"type": "bycolor", "color": [0, 0, 1], "tol": 0.1}], bytes(W * H))
        top, bottom = read_mask_quadrant_means()
        assert top == 0.0 and bottom == 0.0, f"bycolor blue: {top}, {bottom}"

        # 3: wand red + stencil covering the TOP half in browser coords
        #    (browser row 0 = top; rows 0..H//2-1 set)
        stencil = bytearray(W * H)
        for y in range(H // 2):
            for x in range(W):
                stencil[y * W + x] = 255
        send([{"type": "wand", "color": [1, 0, 0], "tol": 0.1}], bytes(stencil))
        top, bottom = read_mask_quadrant_means()
        assert top == 1.0 and bottom == 0.0, \
            f"wand stencil orientation: top={top} bottom={bottom}"

        # 4: empty SEND clears to black
        send([], bytes(1), 1, 1)
        top, bottom = read_mask_quadrant_means()
        assert top == 0.0 and bottom == 0.0, f"clear: {top}, {bottom}"
    finally:
        run("""
t = op('/project1/constant_cmtest')
if t is not None:
    t.destroy()
print('cleanup ok')
""", "colormask integration cleanup")

    print("ALL INTEGRATION CHECKS PASSED")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against live TD**

Run: `python touchdesigner/colormask/tests/integration_td.py`
Expected: `ALL INTEGRATION CHECKS PASSED`

If assertion 3 fails with top/bottom swapped, the `flipud` in `protocol._SEND_TEMPLATE` and the comment in `read_mask_quadrant_means` disagree with this TD build's row order — fix the template, not the test.

- [ ] **Step 3: Verify no TD errors, then checkpoint**

MCP `get_errors` → no new errors. MCP `save_checkpoint` on `/project1` (label `colormask-verified`).

- [ ] **Step 4: Commit**

PowerShell:
```powershell
git add touchdesigner/colormask/tests/integration_td.py
git commit -m @'
test(colormask): live-TD integration check - bycolor, wand stencil orientation, clear

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 7: README, layout pinning, final verification

**Files:**
- Create: `touchdesigner/colormask/README.md`
- Modify: `touchdesigner/layout.json` (add `/project1` entry + new container section)
- Modify: `touchdesigner/LAYOUT.md` (mention the new container, matching its existing style)

**Interfaces:**
- Consumes: everything above.
- Produces: docs + pinned layout; the layout hooks (`reorganize.mjs` / `check-wires.mjs`) start managing the new ops.

- [ ] **Step 1: Pin layout**

In `touchdesigner/layout.json`, add to `"/project1"` → `"ops"`:

```json
"cont_colormask": [1900, -300]
```

and add a new top-level section (positions match Task 5's build script):

```json
"/project1/cont_colormask": {
  "parkDocked": true,
  "ops": {
    "in1": [0, 0],
    "null_src": [220, 0],
    "text_stencil_cb": [0, -200],
    "script_stencil": [220, -200],
    "text_rules_cb": [0, -400],
    "script_rules": [220, -400],
    "text_rules_frag": [440, 200],
    "glsl_rules": [440, 0],
    "text_viz_frag": [660, 200],
    "glsl_viz": [660, -200],
    "out_mask": [660, 0],
    "out_viz": [880, -200]
  }
}
```

Read `touchdesigner/LAYOUT.md` and append a short section for `cont_colormask` following the document's existing conventions.

- [ ] **Step 2: Write `touchdesigner/colormask/README.md`**

Follow the style of `touchdesigner/blobtrack/README.md` (tables for inputs/outputs/internals). Must cover: purpose; how to run the webapp (`python touchdesigner/colormask/webapp/server.py --open`); wiring `in1`; the two tools and gestures (drag grows tolerance, Ctrl+Z, SEND); the stencil + live-color-test semantics and the anchored-wand-region limitation; op table; storage keys + rule texture encoding (`a = tol + 10*type`, sentinel `-1`); the flipud orientation note; test commands (`python -m pytest touchdesigner/colormask/tests -v`, `node --test touchdesigner/colormask/tests/floodfill.test.js`, `python touchdesigner/colormask/tests/integration_td.py`); cross-reference to the spec. State the union-stencil semantics: all wand regions share one stencil; a wand rule's color test applies across the union, which only widens the mask where another selected region contains matching colors.

- [ ] **Step 3: Full test sweep**

Run all three:
- `python -m pytest touchdesigner/colormask/tests -v` → all pass
- `node --test touchdesigner/colormask/tests/floodfill.test.js` → all pass
- `python touchdesigner/colormask/tests/integration_td.py` → `ALL INTEGRATION CHECKS PASSED`

- [ ] **Step 4: Manual UI pass (user-facing)**

Start `python touchdesigner/colormask/webapp/server.py --open`, wire a real source into `in1` (or leave the test constant during the check), and ask the user to try: wand drag on a color block, by-color on a repeated color, Ctrl+Z, SEND, then eyeball `out_viz` in TD. Panels can't be screenshotted through the bridge — verification of the mask itself is the numeric integration test; the feel of the gesture is the user's call (tuning knob: `TOL_PER_PIXEL` in `app.js`).

- [ ] **Step 5: Commit**

PowerShell:
```powershell
git add touchdesigner/colormask/README.md touchdesigner/layout.json touchdesigner/LAYOUT.md
git commit -m @'
docs(colormask): README, pin cont_colormask layout

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```
