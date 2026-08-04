# Attention Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `/attention-handoff <youtube-url>` skill: human box-selects param windows and network grabs from a tutorial video in a local browser app; the agent vision-reads the crops, builds a network graph, gets browser approval, and rebuilds the network in TouchDesigner with all non-default params routed through `/project1/master_controls`.

**Architecture:** Five stages — download (yt-dlp) → capture (stdlib Python HTTP server + browser UI) → extract (agent reads crops, pure-Python matching merges them into `graph.json`) → approve (SVG diagram page on the same server) → rebuild (agent executes a generated plan over the TD MCP bridge). All state lives as JSON files in a per-video session dir; the server derives its state from which files exist.

**Tech Stack:** Python 3.9+ stdlib only (http.server, unittest — no pip deps), vanilla JS/CSS (no CDN, no npm), yt-dlp (external CLI, user-installed), TD MCP bridge tools.

**Spec:** `docs/superpowers/specs/2026-08-04-attention-handoff-design.md`

## Global Constraints

- Python: stdlib only, no pip installs. Tests use `unittest`, not pytest.
- Browser code: no external JS/CSS/fonts/CDN — everything served from `tools/static/`.
- Session dir layout: `tutorials/<video-id>/` containing `video.mp4` (gitignored), `crops/*.png`, `captures.json`, `readings.json`, `optypes.json`, `graph.json`, `approved.json`, `captures.done`.
- Non-default params rebuild via master_controls channels named `tut_<videoid>_<opname>_<parname>` (sanitized `[a-z0-9_]`, max 60 chars), referenced as `op('/project1/master_controls')['<chan>']`. Non-numeric values (strings/menu tokens) are set directly and flagged — CHOP channels carry numbers only.
- Rebuild NEVER calls `project.save()` (untitled-project modal freezes the bridge) — `save_checkpoint` only.
- Server binds `127.0.0.1` only.
- Run all commands from the repo root `C:\Users\NICKESCHEN\dev\TD-MCP`. Use PowerShell for git commands in this repo.
- Test command for every Python task: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`

## File Structure

```
.claude/skills/attention-handoff/
  SKILL.md                    — agent workflow (Task 8)
  tools/
    matching.py               — pure matching/dedupe library + graph.json CLI (Tasks 1-2)
    server.py                 — capture/approval HTTP server (Tasks 3-4)
    rebuild_plan.py           — approved.json → rebuild plan JSON (Task 7)
    static/
      capture.html/.js        — capture UI (Task 5)
      approve.html/.js        — approval UI (Task 6)
      optypes.json            — fallback TD op-type list (Task 8)
    tests/
      test_matching.py, test_server.py, test_rebuild_plan.py
tutorials/.gitignore          — ignore video files (Task 8)
```

---

### Task 1: Matching core — `normalize` + `resolve_label`

**Files:**
- Create: `.claude/skills/attention-handoff/tools/matching.py`
- Test: `.claude/skills/attention-handoff/tools/tests/test_matching.py`

**Interfaces:**
- Produces: `normalize(name) -> str` (lowercased, stripped); `resolve_label(label, known_names) -> (resolved_name_or_None, conflict_dict_or_None)`. Conflict dicts have keys `kind`, `detail`, `captureIds`. Task 2 builds on both.

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/attention-handoff/tools/tests/test_matching.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matching import normalize, resolve_label


class TestResolveLabel(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("  Noise1 "), "noise1")

    def test_exact_match_case_insensitive(self):
        self.assertEqual(resolve_label("Noise1", ["noise1", "level1"]),
                         ("noise1", None))

    def test_unique_prefix_match(self):
        self.assertEqual(resolve_label("noi", ["noise1", "level1"]),
                         ("noise1", None))

    def test_ambiguous_prefix_is_conflict(self):
        name, conflict = resolve_label("no", ["noise1", "noise2"])
        self.assertIsNone(name)
        self.assertEqual(conflict["kind"], "ambiguous-name")
        self.assertIn("noise1", conflict["detail"])

    def test_no_match_returns_label_as_new_name(self):
        self.assertEqual(resolve_label("blur1", ["noise1"]), ("blur1", None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'matching'`

- [ ] **Step 3: Write minimal implementation**

Create `.claude/skills/attention-handoff/tools/matching.py`:

```python
"""Merge human captures and agent vision readings into graph.json.

Inputs (session dir):
  captures.json  - written by the capture app:
      [{"id","t","type":"param|network|pair","bbox","file","pairId","role"}]
  readings.json  - written by the agent after vision-reading each crop:
      {"<captureId>": reading}
    reading kinds:
      {"kind":"param","opName":"noise1","opType":"noiseTOP",
       "params":{"period":"4"}}
      {"kind":"network","nodes":[{"label":"noi","opType":"noiseTOP"}],
       "wires":[{"from":"noi","to":"lev","toInlet":0}]}
      {"kind":"opnode","label":"noise1"}      (pair op-node crops)
      {"kind":"unreadable"}
  optypes.json   - optional list of valid TD op types (from live TD)

Output: graph.json (see design spec 2026-08-04-attention-handoff-design.md).
Pure logic in normalize/resolve_label/build_graph; __main__ does file I/O.
"""
import json
import os
import sys


def normalize(name):
    return str(name).strip().lower()


def resolve_label(label, known_names):
    """Resolve a possibly-truncated node label against known op names.

    Returns (resolved_name, conflict). A unique exact or prefix match wins;
    multiple prefix matches yield an ambiguous-name conflict; no match
    returns the label itself as a new op name.
    """
    lab = normalize(label)
    for n in known_names:
        if normalize(n) == lab:
            return n, None
    prefixed = [n for n in known_names if normalize(n).startswith(lab)]
    if len(prefixed) == 1:
        return prefixed[0], None
    if len(prefixed) > 1:
        return None, {"kind": "ambiguous-name",
                      "detail": "label '%s' matches %s" % (label, sorted(prefixed)),
                      "captureIds": []}
    return label, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```powershell
git add .claude/skills/attention-handoff
git commit -m "feat(attention-handoff): matching core - normalize + truncated-label resolution"
```

---

### Task 2: `build_graph` merge logic + graph.json CLI

**Files:**
- Modify: `.claude/skills/attention-handoff/tools/matching.py` (append)
- Test: `.claude/skills/attention-handoff/tools/tests/test_matching.py` (append)

**Interfaces:**
- Consumes: `normalize`, `resolve_label` from Task 1.
- Produces: `build_graph(captures: list, readings: dict) -> dict` returning `{"ops", "wires", "conflicts", "stats"}` per the spec's graph.json shape. CLI: `python matching.py <session_dir>` reads `captures.json` + `readings.json` (+ optional `optypes.json`, copied into the graph as `opTypes`) and writes `graph.json`. Tasks 6-8 rely on this file shape.

- [ ] **Step 1: Write the failing tests**

Append to `test_matching.py`:

```python
from matching import build_graph


def cap(cid, t, ctype="param", pair_id=None, role=None):
    return {"id": cid, "t": t, "type": ctype, "bbox": [0, 0, 10, 10],
            "file": "crops/%s.png" % cid, "pairId": pair_id, "role": role}


class TestBuildGraph(unittest.TestCase):
    def test_param_latest_wins_history_kept(self):
        captures = [cap("c1", 88.2), cap("c2", 214.6)]
        readings = {
            "c1": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
                   "params": {"period": "1"}},
            "c2": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
                   "params": {"period": "4"}},
        }
        g = build_graph(captures, readings)
        self.assertEqual(g["stats"]["opCount"], 1)
        slot = g["ops"][0]["params"]["period"]
        self.assertEqual(slot["value"], "4")
        self.assertEqual(slot["history"], [{"value": "1", "t": 88.2}])
        self.assertIn("param-changed", [c["kind"] for c in g["conflicts"]])

    def test_wire_union_dedupe_across_grabs(self):
        captures = [cap("c1", 10), cap("c2", 20),
                    cap("c3", 30, "network"), cap("c4", 40, "network")]
        readings = {
            "c1": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
                   "params": {}},
            "c2": {"kind": "param", "opName": "level1", "opType": "levelTOP",
                   "params": {}},
            "c3": {"kind": "network",
                   "nodes": [{"label": "noi"}, {"label": "lev"}],
                   "wires": [{"from": "noi", "to": "lev", "toInlet": 0}]},
            "c4": {"kind": "network",
                   "nodes": [{"label": "noise1"}, {"label": "level1"}],
                   "wires": [{"from": "noise1", "to": "level1", "toInlet": 0}]},
        }
        g = build_graph(captures, readings)
        self.assertEqual(g["stats"]["opCount"], 2)
        self.assertEqual(g["stats"]["wireCount"], 1)
        self.assertEqual(sorted(g["wires"][0]["sources"]), ["c3", "c4"])

    def test_pair_override_beats_ambiguous_prefix(self):
        captures = [cap("c1", 10), cap("c2", 20),
                    cap("c3", 30, "pair", "p1", "op"),
                    cap("c4", 31, "pair", "p1", "param"),
                    cap("c5", 40, "network")]
        readings = {
            "c1": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
                   "params": {}},
            "c2": {"kind": "param", "opName": "noise2", "opType": "noiseTOP",
                   "params": {}},
            "c3": {"kind": "opnode", "label": "no"},
            "c4": {"kind": "param", "opName": "noise2", "opType": "noiseTOP",
                   "params": {}},
            "c5": {"kind": "network", "nodes": [{"label": "no"}], "wires": []},
        }
        g = build_graph(captures, readings)
        # 'no' is ambiguous by prefix (noise1/noise2) but the pair pins it
        self.assertEqual(g["stats"]["opCount"], 2)
        self.assertEqual([c for c in g["conflicts"]
                          if c["kind"] == "ambiguous-name"], [])

    def test_unreadable_and_unknown_optype_conflicts(self):
        captures = [cap("c1", 10), cap("c2", 20, "network")]
        readings = {
            "c1": {"kind": "unreadable"},
            "c2": {"kind": "network", "nodes": [{"label": "mystery1"}],
                   "wires": []},
        }
        g = build_graph(captures, readings)
        kinds = [c["kind"] for c in g["conflicts"]]
        self.assertIn("unreadable", kinds)
        self.assertIn("unknown-optype", kinds)

    def test_wire_endpoint_creates_missing_op(self):
        captures = [cap("c1", 10, "network")]
        readings = {
            "c1": {"kind": "network", "nodes": [],
                   "wires": [{"from": "a1", "to": "b1", "toInlet": 2}]},
        }
        g = build_graph(captures, readings)
        self.assertEqual(g["stats"]["opCount"], 2)
        self.assertEqual(g["wires"][0]["toInlet"], 2)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: `ImportError: cannot import name 'build_graph'`

- [ ] **Step 3: Implement `build_graph` and the CLI**

Append to `matching.py`:

```python
def build_graph(captures, readings):
    conflicts = []

    # 1. Pair overrides: normalized node label -> full op name
    pair_label_to_name = {}
    by_pair = {}
    for c in captures:
        if c.get("pairId"):
            by_pair.setdefault(c["pairId"], []).append(c)
    for group in by_pair.values():
        label, name = None, None
        for c in group:
            r = readings.get(c["id"]) or {}
            if r.get("kind") == "opnode":
                label = r.get("label")
            elif r.get("kind") == "param":
                name = r.get("opName")
        if label and name:
            pair_label_to_name[normalize(label)] = name

    # 2. Ops from param readings, ordered by video time (latest wins)
    ops = {}  # normalized name -> op dict

    def ensure_op(name, op_type=None, cap_id=None):
        key = normalize(name)
        if key not in ops:
            ops[key] = {"id": name, "opType": op_type or "",
                        "confidence": 1.0, "params": {}, "sources": []}
        op = ops[key]
        if op_type and not op["opType"]:
            op["opType"] = op_type
        if cap_id and cap_id not in op["sources"]:
            op["sources"].append(cap_id)
        return op

    param_reads = []
    for c in captures:
        r = readings.get(c["id"]) or {}
        if r.get("kind") == "param":
            param_reads.append((c, r))
        elif r.get("kind") == "unreadable":
            conflicts.append({"kind": "unreadable",
                              "detail": "capture %s could not be read" % c["id"],
                              "captureIds": [c["id"]]})
    param_reads.sort(key=lambda cr: cr[0]["t"])
    for c, r in param_reads:
        op = ensure_op(r["opName"], r.get("opType"), c["id"])
        for pname, value in (r.get("params") or {}).items():
            slot = op["params"].get(pname)
            if slot is None:
                op["params"][pname] = {"value": value, "t": c["t"],
                                       "history": []}
            elif slot["value"] != value:
                slot["history"].append({"value": slot["value"], "t": slot["t"]})
                slot["value"], slot["t"] = value, c["t"]
                conflicts.append({
                    "kind": "param-changed",
                    "detail": "%s.%s changed to %r at t=%.1f"
                              % (op["id"], pname, value, c["t"]),
                    "captureIds": [c["id"]]})

    # 3. Network readings: resolve labels, add unmatched ops, union wires
    known = [o["id"] for o in ops.values()]

    def resolve(label, cap_id):
        key = normalize(label)
        if key in pair_label_to_name:
            return pair_label_to_name[key]
        name, conflict = resolve_label(label, known)
        if conflict:
            conflict["captureIds"] = [cap_id]
            conflicts.append(conflict)
            return None
        return name

    wires = {}
    for c in captures:
        r = readings.get(c["id"]) or {}
        if r.get("kind") != "network":
            continue
        for node in r.get("nodes") or []:
            name = resolve(node["label"], c["id"])
            if name:
                ensure_op(name, node.get("opType"), c["id"])
                if name not in known:
                    known.append(name)
        for w in r.get("wires") or []:
            src = resolve(w["from"], c["id"])
            dst = resolve(w["to"], c["id"])
            if not src or not dst:
                continue
            for endpoint in (src, dst):
                ensure_op(endpoint, None, c["id"])
                if endpoint not in known:
                    known.append(endpoint)
            key = (normalize(src), normalize(dst), w.get("toInlet", 0))
            if key not in wires:
                wires[key] = {"from": src, "to": dst,
                              "toInlet": w.get("toInlet", 0), "sources": []}
            if c["id"] not in wires[key]["sources"]:
                wires[key]["sources"].append(c["id"])

    for op in ops.values():
        if not op["opType"]:
            conflicts.append({"kind": "unknown-optype",
                              "detail": "op '%s' has no op type" % op["id"],
                              "captureIds": list(op["sources"])})

    op_list = list(ops.values())
    wire_list = list(wires.values())
    return {"ops": op_list, "wires": wire_list, "conflicts": conflicts,
            "stats": {"opCount": len(op_list), "wireCount": len(wire_list)}}


def main(session_dir):
    def load(name, default):
        path = os.path.join(session_dir, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default

    captures = load("captures.json", [])
    readings = load("readings.json", {})
    graph = build_graph(captures, readings)
    graph["opTypes"] = load("optypes.json", [])
    out = os.path.join(session_dir, "graph.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    print("wrote %s: %d ops, %d wires, %d conflicts" % (
        out, graph["stats"]["opCount"], graph["stats"]["wireCount"],
        len(graph["conflicts"])))


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: 10 tests PASS

- [ ] **Step 5: Commit**

```powershell
git add .claude/skills/attention-handoff
git commit -m "feat(attention-handoff): build_graph merge logic + graph.json CLI"
```

---

### Task 3: Server — session state + JSON endpoints

**Files:**
- Create: `.claude/skills/attention-handoff/tools/server.py`
- Test: `.claude/skills/attention-handoff/tools/tests/test_server.py`

**Interfaces:**
- Produces: `Session(root_dir)` with `.state()` returning `capturing | captured | awaiting_approval | approved` (derived from file existence: `approved.json` → approved, `graph.json` → awaiting_approval, `captures.done` → captured, else capturing). HTTP endpoints: `GET /captures`, `GET /graph`, `GET /readings` (serves `readings.json`, `{}` when absent), `GET /status`, `POST /capture` (JSON with base64 `image` dataURL → writes `crops/<id>.png`, returns the capture record), `POST /delete {"id"}`, `POST /done`, `POST /approved` (body saved verbatim as `approved.json`). Module-level `SESSION` is set by `main()` or by tests. Tasks 4-6 extend/consume this server.

- [ ] **Step 1: Write the failing tests**

Create `.claude/skills/attention-handoff/tools/tests/test_server.py`:

```python
import base64
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server as srv_mod

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        with open(os.path.join(cls.dir, "video.mp4"), "wb") as f:
            f.write(bytes(range(256)) * 40)  # 10240-byte fake video
        srv_mod.SESSION = srv_mod.Session(cls.dir)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv_mod.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def req(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(method, path, body, headers or {})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def test_1_capture_roundtrip(self):
        img = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
        resp, data = self.req("POST", "/capture", json.dumps(
            {"t": 12.5, "type": "param", "bbox": [1, 2, 3, 4],
             "pairId": None, "role": None, "image": img}))
        self.assertEqual(resp.status, 200)
        rec = json.loads(data)
        self.assertEqual(rec["id"], "c001")
        self.assertEqual(rec["file"], "crops/c001.png")
        self.assertTrue(os.path.exists(
            os.path.join(self.dir, "crops", "c001.png")))
        resp, data = self.req("GET", "/captures")
        self.assertEqual(len(json.loads(data)), 1)

    def test_2_delete_removes_record_and_crop(self):
        img = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
        resp, data = self.req("POST", "/capture", json.dumps(
            {"t": 1.0, "type": "network", "bbox": [0, 0, 5, 5],
             "pairId": None, "role": None, "image": img}))
        cid = json.loads(data)["id"]
        self.req("POST", "/delete", json.dumps({"id": cid}))
        resp, data = self.req("GET", "/captures")
        self.assertNotIn(cid, [c["id"] for c in json.loads(data)])
        self.assertFalse(os.path.exists(
            os.path.join(self.dir, "crops", cid + ".png")))

    def test_3_status_flow(self):
        resp, data = self.req("GET", "/status")
        self.assertEqual(json.loads(data)["state"], "capturing")
        self.req("POST", "/done", "{}")
        resp, data = self.req("GET", "/status")
        self.assertEqual(json.loads(data)["state"], "captured")
        self.req("POST", "/approved", json.dumps({"ops": [], "wires": []}))
        resp, data = self.req("GET", "/status")
        self.assertEqual(json.loads(data)["state"], "approved")
        with open(os.path.join(self.dir, "approved.json")) as f:
            self.assertEqual(json.load(f)["ops"], [])

    def test_4_readings_endpoint(self):
        resp, data = self.req("GET", "/readings")
        self.assertEqual(json.loads(data), {})
        with open(os.path.join(self.dir, "readings.json"), "w") as f:
            json.dump({"c001": {"kind": "param", "opName": "noise1",
                                "opType": "noiseTOP",
                                "params": {"period": "4"},
                                "boxes": {"period": [10, 20, 200, 18]}}}, f)
        resp, data = self.req("GET", "/readings")
        self.assertEqual(json.loads(data)["c001"]["opName"], "noise1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Implement the server**

Create `.claude/skills/attention-handoff/tools/server.py`:

```python
"""Attention-handoff capture/approval server. Stdlib only, 127.0.0.1 only.

Usage: python server.py <session_dir> [--port 8765] [--open]

State is derived from files in the session dir:
  approved.json -> approved; graph.json -> awaiting_approval;
  captures.done -> captured; otherwise capturing.
"""
import argparse
import base64
import json
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

SESSION = None

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript",
                 ".css": "text/css", ".json": "application/json",
                 ".png": "image/png"}


class Session:
    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()
        os.makedirs(os.path.join(root, "crops"), exist_ok=True)

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def load_json(self, name, default):
        try:
            with open(self.path(name), "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default

    def save_json(self, name, data):
        tmp = self.path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path(name))

    def state(self):
        if os.path.exists(self.path("approved.json")):
            return "approved"
        if os.path.exists(self.path("graph.json")):
            return "awaiting_approval"
        if os.path.exists(self.path("captures.done")):
            return "captured"
        return "capturing"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, fspath, ctype):
        if not os.path.exists(fspath):
            return self.send_json({"error": "not found"}, 404)
        with open(fspath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.send_file(os.path.join(STATIC_DIR, "capture.html"),
                           "text/html")
        elif path == "/approve":
            self.send_file(os.path.join(STATIC_DIR, "approve.html"),
                           "text/html")
        elif path == "/evidence":
            self.send_file(os.path.join(STATIC_DIR, "evidence.html"),
                           "text/html")
        elif path.startswith("/static/"):
            name = os.path.basename(path)
            ext = os.path.splitext(name)[1]
            self.send_file(os.path.join(STATIC_DIR, name),
                           CONTENT_TYPES.get(ext, "application/octet-stream"))
        elif path.startswith("/crops/"):
            self.send_file(SESSION.path("crops", os.path.basename(path)),
                           "image/png")
        elif path == "/captures":
            self.send_json(SESSION.load_json("captures.json", []))
        elif path == "/graph":
            self.send_json(SESSION.load_json("graph.json", {}))
        elif path == "/readings":
            self.send_json(SESSION.load_json("readings.json", {}))
        elif path == "/status":
            self.send_json({"state": SESSION.state()})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            return self.send_json({"error": "bad json"}, 400)

        if path == "/capture":
            with SESSION.lock:
                caps = SESSION.load_json("captures.json", [])
                nums = [int(c["id"][1:]) for c in caps
                        if re.fullmatch(r"c\d+", c.get("id", ""))]
                cid = "c%03d" % (max(nums) + 1 if nums else 1)
                image = data.get("image") or ""
                b64 = image.split(",", 1)[1] if "," in image else image
                with open(SESSION.path("crops", cid + ".png"), "wb") as f:
                    f.write(base64.b64decode(b64))
                rec = {"id": cid, "t": data.get("t"), "type": data.get("type"),
                       "bbox": data.get("bbox"),
                       "file": "crops/%s.png" % cid,
                       "pairId": data.get("pairId"), "role": data.get("role")}
                caps.append(rec)
                SESSION.save_json("captures.json", caps)
            self.send_json(rec)
        elif path == "/delete":
            with SESSION.lock:
                caps = SESSION.load_json("captures.json", [])
                caps = [c for c in caps if c["id"] != data.get("id")]
                SESSION.save_json("captures.json", caps)
                crop = SESSION.path("crops", "%s.png" % data.get("id"))
                if os.path.exists(crop):
                    os.remove(crop)
            self.send_json({"ok": True})
        elif path == "/done":
            with open(SESSION.path("captures.done"), "w") as f:
                f.write("")
            self.send_json({"ok": True})
        elif path == "/approved":
            SESSION.save_json("approved.json", data)
            self.send_json({"ok": True})
        else:
            self.send_json({"error": "not found"}, 404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    global SESSION
    SESSION = Session(os.path.abspath(args.session_dir))
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("attention-handoff server: http://127.0.0.1:%d  (session: %s)"
          % (args.port, SESSION.root))
    if args.open:
        webbrowser.open("http://127.0.0.1:%d" % args.port)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: 14 tests PASS

- [ ] **Step 5: Commit**

```powershell
git add .claude/skills/attention-handoff
git commit -m "feat(attention-handoff): capture/approval server with file-derived state"
```

---

### Task 4: Server — byte-range video serving

**Files:**
- Modify: `.claude/skills/attention-handoff/tools/server.py`
- Test: `.claude/skills/attention-handoff/tools/tests/test_server.py` (append)

**Interfaces:**
- Produces: `GET /video` serving `video.mp4` (or `.webm`) from the session dir with HTTP Range support — browsers refuse to seek `<video>` without 206 responses.

- [ ] **Step 1: Write the failing tests**

Append to `test_server.py` inside `ServerTest`:

```python
    def test_5_video_full(self):
        resp, data = self.req("GET", "/video")
        self.assertEqual(resp.status, 200)
        self.assertEqual(len(data), 10240)
        self.assertEqual(resp.getheader("Accept-Ranges"), "bytes")

    def test_6_video_range(self):
        resp, data = self.req("GET", "/video",
                              headers={"Range": "bytes=100-199"})
        self.assertEqual(resp.status, 206)
        self.assertEqual(len(data), 100)
        self.assertEqual(resp.getheader("Content-Range"),
                         "bytes 100-199/10240")
        self.assertEqual(data[0], 100)

    def test_7_video_open_ended_range(self):
        resp, data = self.req("GET", "/video",
                              headers={"Range": "bytes=10200-"})
        self.assertEqual(resp.status, 206)
        self.assertEqual(len(data), 40)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: the three new tests FAIL (404 "not found" — no /video route yet)

- [ ] **Step 3: Implement range serving**

In `server.py`, add a route in `do_GET` (before the final `else`):

```python
        elif path == "/video":
            self.send_video()
```

and add this method to `Handler`:

```python
    def send_video(self):
        video_path = None
        for ext in ("mp4", "webm"):
            candidate = SESSION.path("video." + ext)
            if os.path.exists(candidate):
                video_path = candidate
                break
        if not video_path:
            return self.send_json({"error": "no video in session dir"}, 404)
        size = os.path.getsize(video_path)
        ctype = "video/mp4" if video_path.endswith(".mp4") else "video/webm"
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
            else:                                # suffix range: last N bytes
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range",
                             "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        with open(video_path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionAbortedError, BrokenPipeError):
                    return
                remaining -= len(chunk)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: 17 tests PASS

- [ ] **Step 5: Commit**

```powershell
git add .claude/skills/attention-handoff
git commit -m "feat(attention-handoff): byte-range video serving for browser seeking"
```

---

### Task 5: Capture UI

**Files:**
- Create: `.claude/skills/attention-handoff/tools/static/capture.html`
- Create: `.claude/skills/attention-handoff/tools/static/capture.js`

**Interfaces:**
- Consumes: `/video`, `/capture`, `/captures`, `/delete`, `/done`, `/crops/<id>.png` from Tasks 3-4.
- Produces: capture records whose `bbox` is in **native video pixels** `[x, y, w, h]`; pair captures carry `pairId` + `role` (`"op"` then `"param"`). Browser JS — verified manually (Step 2 checklist), no unit tests.

- [ ] **Step 1: Write both files**

`capture.html`:

```html
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Attention Handoff — Capture</title>
<style>
  body { margin: 0; font: 13px system-ui; background: #16161a; color: #ddd;
         display: flex; height: 100vh; }
  #main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  #stage { position: relative; flex: 1; background: #000; overflow: hidden; }
  #vid { width: 100%; height: 100%; object-fit: contain; display: block; }
  #overlay { position: absolute; cursor: crosshair; }
  #bar { padding: 8px; display: flex; gap: 14px; align-items: center;
         background: #222; flex-wrap: wrap; }
  #bar input { width: 40px; background: #333; color: #ddd;
               border: 1px solid #555; }
  #mode { font-weight: bold; color: #8f8; }
  #hint { color: #888; }
  #done { margin-left: auto; background: #2a6; color: #fff; border: 0;
          padding: 6px 14px; cursor: pointer; }
  #side { width: 230px; overflow-y: auto; background: #1d1d22; padding: 8px; }
  .cap { margin-bottom: 8px; border: 1px solid #333; padding: 4px; }
  .cap img { max-width: 100%; image-rendering: pixelated; }
  .cap button { float: right; background: #a33; color: #fff; border: 0;
                cursor: pointer; }
</style>
</head>
<body>
<div id="main">
  <div id="stage">
    <video id="vid" src="/video"></video>
    <canvas id="overlay"></canvas>
  </div>
  <div id="bar">
    <span id="time">0.00s</span>
    <label>fps <input id="fps" value="30"></label>
    <span id="mode">mode: param</span>
    <span id="hint">space play/pause · &larr;/&rarr; &plusmn;5s ·
      , . frame step · 1 param / 2 network / 3 pair ·
      drag box to capture · esc cancels a pending pair</span>
    <button id="done">Done</button>
  </div>
</div>
<div id="side">
  <h3>Captures (<span id="count">0</span>)</h3>
  <div id="list"></div>
</div>
<script src="/static/capture.js"></script>
</body>
</html>
```

`capture.js`:

```js
const vid = document.getElementById('vid');
const stage = document.getElementById('stage');
const overlay = document.getElementById('overlay');
const ctx = overlay.getContext('2d');
let mode = 'param';          // param | network | pair
let pendingPair = null;      // {pairId, opCaptureId} while awaiting param box
let drag = null;

function fps() {
  return parseFloat(document.getElementById('fps').value) || 30;
}

function fitOverlay() {
  const sw = stage.clientWidth, sh = stage.clientHeight;
  const aspect = (vid.videoWidth / vid.videoHeight) || (16 / 9);
  let w = sw, h = sw / aspect;
  if (h > sh) { h = sh; w = sh * aspect; }
  overlay.width = w;
  overlay.height = h;
  overlay.style.width = w + 'px';
  overlay.style.height = h + 'px';
  overlay.style.left = ((sw - w) / 2) + 'px';
  overlay.style.top = ((sh - h) / 2) + 'px';
}
vid.addEventListener('loadedmetadata', fitOverlay);
window.addEventListener('resize', fitOverlay);

setInterval(() => {
  document.getElementById('time').textContent =
    vid.currentTime.toFixed(2) + 's / ' + (vid.duration || 0).toFixed(1) + 's';
}, 200);

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.code === 'Space') {
    e.preventDefault();
    if (vid.paused) vid.play(); else vid.pause();
  } else if (e.key === 'ArrowLeft') vid.currentTime -= 5;
  else if (e.key === 'ArrowRight') vid.currentTime += 5;
  else if (e.key === ',') { vid.pause(); vid.currentTime -= 1 / fps(); }
  else if (e.key === '.') { vid.pause(); vid.currentTime += 1 / fps(); }
  else if (e.key === '1') setMode('param');
  else if (e.key === '2') setMode('network');
  else if (e.key === '3') setMode('pair');
  else if (e.key === 'Escape') cancelPair();
});

function setMode(m) { mode = m; pendingPair = null; updateModeLabel(); }

function updateModeLabel() {
  document.getElementById('mode').textContent =
    'mode: ' + mode + (pendingPair ? ' — now box the PARAM window' :
                       (mode === 'pair' ? ' — box the OP node first' : ''));
}

async function cancelPair() {
  if (!pendingPair) return;
  await fetch('/delete', {
    method: 'POST',
    body: JSON.stringify({id: pendingPair.opCaptureId})
  });
  pendingPair = null;
  updateModeLabel();
  refresh();
}

overlay.addEventListener('mousedown', e => {
  vid.pause();
  drag = {x: e.offsetX, y: e.offsetY};
});
overlay.addEventListener('mousemove', e => {
  if (!drag) return;
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  ctx.strokeStyle = '#0f0';
  ctx.lineWidth = 2;
  ctx.strokeRect(drag.x, drag.y, e.offsetX - drag.x, e.offsetY - drag.y);
});
overlay.addEventListener('mouseup', async e => {
  if (!drag) return;
  const box = normBox(drag.x, drag.y, e.offsetX, e.offsetY);
  drag = null;
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  if (box.w < 8 || box.h < 8) return;
  await capture(box);
});

function normBox(x0, y0, x1, y1) {
  return {x: Math.min(x0, x1), y: Math.min(y0, y1),
          w: Math.abs(x1 - x0), h: Math.abs(y1 - y0)};
}

async function capture(box) {
  const sx = vid.videoWidth / overlay.width;
  const sy = vid.videoHeight / overlay.height;
  const bbox = [Math.round(box.x * sx), Math.round(box.y * sy),
                Math.round(box.w * sx), Math.round(box.h * sy)];
  const full = document.createElement('canvas');
  full.width = vid.videoWidth;
  full.height = vid.videoHeight;
  full.getContext('2d').drawImage(vid, 0, 0);
  const crop = document.createElement('canvas');
  crop.width = bbox[2];
  crop.height = bbox[3];
  crop.getContext('2d').drawImage(full, bbox[0], bbox[1], bbox[2], bbox[3],
                                  0, 0, bbox[2], bbox[3]);
  let type = mode, role = null, pairId = null;
  if (mode === 'pair') {
    if (!pendingPair) { pairId = 'p' + Date.now(); role = 'op'; }
    else { pairId = pendingPair.pairId; role = 'param'; }
  }
  const res = await fetch('/capture', {method: 'POST', body: JSON.stringify({
    t: vid.currentTime, type, bbox, pairId, role,
    image: crop.toDataURL('image/png')})});
  const saved = await res.json();
  if (mode === 'pair') {
    pendingPair = pendingPair ? null : {pairId, opCaptureId: saved.id};
  }
  updateModeLabel();
  refresh();
}

async function refresh() {
  const caps = await (await fetch('/captures')).json();
  document.getElementById('count').textContent = caps.length;
  const list = document.getElementById('list');
  list.innerHTML = '';
  for (const c of caps.slice().reverse()) {
    const div = document.createElement('div');
    div.className = 'cap';
    div.innerHTML = '<img src="/crops/' + c.id + '.png"><div>' + c.id + ' ' +
      c.type + (c.role ? '/' + c.role : '') + ' @' + c.t.toFixed(1) +
      's <button>x</button></div>';
    div.querySelector('button').onclick = async () => {
      await fetch('/delete', {method: 'POST',
                              body: JSON.stringify({id: c.id})});
      refresh();
    };
    list.appendChild(div);
  }
}

document.getElementById('done').onclick = async () => {
  await fetch('/done', {method: 'POST', body: '{}'});
  document.getElementById('done').textContent = 'Done ✓ (agent notified)';
};

refresh();
```

- [ ] **Step 2: Manual verification**

Get any short mp4 (e.g. copy an existing local video, or `yt-dlp -f "b[ext=mp4]" -o "C:\Users\immer\AppData\Local\Temp\claude\...\scratchpad\smoke\video.mp4" <any short url>`), place it as `<scratch>/smoke/video.mp4`, then:

Run: `python .claude/skills/attention-handoff/tools/server.py <scratch>/smoke --open`

Checklist (ask the user to confirm, or verify server-side effects yourself):
- [ ] Video loads and plays; space toggles, arrows seek, `,`/`.` step one frame while paused
- [ ] Dragging a box in mode 1 adds a `param` capture to the sidebar with a correct thumbnail (crop matches the boxed region — this validates letterbox coordinate mapping)
- [ ] Mode 3: first box posts `pair/op`, label switches to "now box the PARAM window", second box posts `pair/param` with the same `pairId` (check `captures.json`)
- [ ] Esc after the first pair box deletes the op capture
- [ ] Sidebar delete removes record + crop file; Done creates `captures.done`

- [ ] **Step 3: Commit**

```powershell
git add .claude/skills/attention-handoff
git commit -m "feat(attention-handoff): capture UI - scrub, box-select, pair mode"
```

---

### Task 6: Approval UI + param-evidence page

**Files:**
- Create: `.claude/skills/attention-handoff/tools/static/approve.html`
- Create: `.claude/skills/attention-handoff/tools/static/approve.js`
- Create: `.claude/skills/attention-handoff/tools/static/evidence.html`
- Create: `.claude/skills/attention-handoff/tools/static/evidence.js`

**Interfaces:**
- Consumes: `GET /graph` (graph.json incl. `opTypes` list), `GET /captures`, `GET /readings`, `POST /approved` from Task 3.
- Produces: `approved.json` in the graph.json shape with recomputed `stats`. Edits supported: rename op (wires follow), change opType (datalist), delete op (+its wires), add wire (click source then target, prompt for inlet), delete wire (click it), edit param values, dismiss conflicts. `/evidence` page: every param-window crop with mask overlays (from the reading's `boxes`, crop-pixel coords) and the extracted value per non-default param.

- [ ] **Step 1: Write both files**

`approve.html`:

```html
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Attention Handoff — Approve</title>
<style>
  body { margin: 0; font: 13px system-ui; background: #16161a; color: #ddd; }
  header { padding: 10px; background: #222; display: flex; gap: 16px;
           align-items: center; }
  #counts { font-weight: bold; }
  #banner { color: #fc6; }
  #approve { margin-left: auto; background: #2a6; color: #fff; border: 0;
             padding: 8px 18px; cursor: pointer; }
  #wrap { display: flex; }
  #diagram { flex: 1; overflow: auto; background: #101014; min-height: 60vh; }
  #panel { width: 360px; padding: 10px; overflow-y: auto; max-height: 90vh; }
  svg rect { fill: #26262e; stroke: #555; }
  svg .sel rect { stroke: #6cf; stroke-width: 2; }
  svg .conflict rect { stroke: #f80; stroke-width: 2; }
  svg text { fill: #ddd; font: 12px monospace; pointer-events: none; }
  svg .typ { fill: #888; font-size: 10px; }
  svg .wire { fill: none; stroke: #6a6; stroke-width: 2; cursor: pointer; }
  svg g.node { cursor: pointer; }
  table { border-collapse: collapse; width: 100%; }
  td, th { border: 1px solid #333; padding: 3px; }
  tr.changed { background: #3a2f1a; }
  .cf { border: 1px solid #f80; padding: 4px; margin: 4px 0; }
  input, button { background: #333; color: #ddd; border: 1px solid #555; }
</style>
</head>
<body>
<header>
  <span id="counts"></span>
  <button id="addwire">add wire</button>
  <a href="/evidence" style="color:#6cf">param evidence</a>
  <span id="banner"></span>
  <button id="approve">Approve — rebuild in TD</button>
</header>
<div id="wrap">
  <div id="diagram"></div>
  <div id="panel">
    <h3>Inspector</h3><div id="inspector"><em>click a node</em></div>
    <h3>Conflicts</h3><div id="conflicts"></div>
    <h3>Parameters</h3><div id="params"></div>
  </div>
</div>
<datalist id="optypes"></datalist>
<script src="/static/approve.js"></script>
</body>
</html>
```

`approve.js`:

```js
let graph = null;
let selected = null;    // op id
let wireMode = null;    // null | 'pick-src' | {from: opId}

const NW = 150, NH = 46, GX = 210, GY = 70;

async function load() {
  graph = await (await fetch('/graph')).json();
  graph.ops = graph.ops || [];
  graph.wires = graph.wires || [];
  graph.conflicts = graph.conflicts || [];
  const dl = document.getElementById('optypes');
  for (const t of graph.opTypes || []) {
    const o = document.createElement('option');
    o.value = t;
    dl.appendChild(o);
  }
  render();
}

function depths() {
  const d = {}, incoming = {};
  for (const o of graph.ops) { d[o.id] = 0; incoming[o.id] = []; }
  for (const w of graph.wires) {
    if (incoming[w.to] !== undefined && d[w.from] !== undefined) {
      incoming[w.to].push(w.from);
    }
  }
  for (let i = 0; i < graph.ops.length; i++) {   // relaxation, cycle-safe
    let changed = false;
    for (const o of graph.ops) {
      for (const src of incoming[o.id]) {
        if (d[src] + 1 > d[o.id]) { d[o.id] = d[src] + 1; changed = true; }
      }
    }
    if (!changed) break;
  }
  return d;
}

function layout() {
  const d = depths(), rows = {}, pos = {};
  for (const o of graph.ops) {
    const col = d[o.id];
    rows[col] = rows[col] || 0;
    pos[o.id] = {x: 30 + col * GX, y: 30 + rows[col] * GY};
    rows[col]++;
  }
  return pos;
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/"/g, '&quot;');
}

function hasConflict(opId) {
  return graph.conflicts.some(c => (c.detail || '').includes(opId));
}

function banner(msg) { document.getElementById('banner').textContent = msg; }

function render() {
  document.getElementById('counts').textContent =
    graph.ops.length + ' ops · ' + graph.wires.length + ' wires';
  renderSvg();
  renderInspector();
  renderConflicts();
  renderParams();
}

function renderSvg() {
  const pos = layout();
  const xs = Object.values(pos).map(p => p.x);
  const ys = Object.values(pos).map(p => p.y);
  const w = (xs.length ? Math.max(...xs) : 0) + NW + 40;
  const h = (ys.length ? Math.max(...ys) : 0) + NH + 40;
  let s = '<svg width="' + w + '" height="' + h +
          '" xmlns="http://www.w3.org/2000/svg">';
  graph.wires.forEach((wire, i) => {
    const a = pos[wire.from], b = pos[wire.to];
    if (!a || !b) return;
    const x1 = a.x + NW, y1 = a.y + NH / 2, x2 = b.x, y2 = b.y + NH / 2;
    s += '<path class="wire" data-wire="' + i + '" d="M' + x1 + ',' + y1 +
         ' C' + (x1 + 60) + ',' + y1 + ' ' + (x2 - 60) + ',' + y2 +
         ' ' + x2 + ',' + y2 + '"/>';
  });
  for (const o of graph.ops) {
    const p = pos[o.id];
    const cls = 'node' + (o.id === selected ? ' sel' : '') +
                (hasConflict(o.id) ? ' conflict' : '');
    s += '<g class="' + cls + '" data-op="' + esc(o.id) + '">' +
         '<rect x="' + p.x + '" y="' + p.y + '" width="' + NW +
         '" height="' + NH + '" rx="6"/>' +
         '<text x="' + (p.x + 8) + '" y="' + (p.y + 19) + '">' +
         esc(o.id) + '</text>' +
         '<text x="' + (p.x + 8) + '" y="' + (p.y + 37) + '" class="typ">' +
         esc(o.opType || '?') + '</text></g>';
  }
  s += '</svg>';
  const holder = document.getElementById('diagram');
  holder.innerHTML = s;
  holder.querySelectorAll('g.node').forEach(g => {
    g.onclick = () => clickNode(g.dataset.op);
  });
  holder.querySelectorAll('path.wire').forEach(p => {
    p.onclick = () => {
      if (confirm('Delete this wire?')) {
        graph.wires.splice(+p.dataset.wire, 1);
        render();
      }
    };
  });
}

function clickNode(id) {
  if (wireMode === 'pick-src') {
    wireMode = {from: id};
    banner('now click the target op');
    return;
  }
  if (wireMode && wireMode.from) {
    const inlet = parseInt(prompt('Target inlet index?', '0') || '0', 10);
    graph.wires.push({from: wireMode.from, to: id, toInlet: inlet,
                      sources: ['manual']});
    wireMode = null;
    banner('');
    render();
    return;
  }
  selected = id;
  render();
}

function renderInspector() {
  const el = document.getElementById('inspector');
  const op = graph.ops.find(o => o.id === selected);
  if (!op) { el.innerHTML = '<em>click a node</em>'; return; }
  el.innerHTML = '<b>' + esc(op.id) + '</b><br>' +
    'name <input id="i-name" value="' + esc(op.id) + '"><br>' +
    'type <input id="i-type" list="optypes" value="' + esc(op.opType) +
    '"><br><button id="i-del">delete op</button>';
  document.getElementById('i-name').onchange = e => {
    const old = op.id, next = e.target.value.trim();
    if (!next) return;
    op.id = next;
    for (const w of graph.wires) {
      if (w.from === old) w.from = next;
      if (w.to === old) w.to = next;
    }
    selected = next;
    render();
  };
  document.getElementById('i-type').onchange = e => {
    op.opType = e.target.value.trim();
    render();
  };
  document.getElementById('i-del').onclick = () => {
    graph.ops = graph.ops.filter(o => o !== op);
    graph.wires = graph.wires.filter(w => w.from !== op.id && w.to !== op.id);
    selected = null;
    render();
  };
}

function renderConflicts() {
  const el = document.getElementById('conflicts');
  if (!graph.conflicts.length) {
    el.innerHTML = '<em>no conflicts</em>';
    return;
  }
  el.innerHTML = graph.conflicts.map((c, i) =>
    '<div class="cf">[' + esc(c.kind) + '] ' + esc(c.detail) +
    ' <button data-i="' + i + '">resolved</button></div>').join('');
  el.querySelectorAll('button').forEach(b => {
    b.onclick = () => { graph.conflicts.splice(+b.dataset.i, 1); render(); };
  });
}

function renderParams() {
  const el = document.getElementById('params');
  let h = '<table><tr><th>op</th><th>param</th><th>value</th><th></th></tr>';
  for (const o of graph.ops) {
    for (const [p, slot] of Object.entries(o.params || {})) {
      const hist = (slot.history || [])
        .map(x => x.value + ' @' + x.t.toFixed(1) + 's').join(', ');
      h += '<tr class="' + (hist ? 'changed' : '') + '"><td>' + esc(o.id) +
           '</td><td>' + esc(p) + '</td><td><input data-op="' + esc(o.id) +
           '" data-par="' + esc(p) + '" value="' + esc(slot.value) +
           '"></td><td title="' + esc(hist) + '">' +
           (hist ? 'hist' : '') + '</td></tr>';
    }
  }
  el.innerHTML = h + '</table>';
  el.querySelectorAll('input').forEach(inp => {
    inp.onchange = e => {
      const o = graph.ops.find(x => x.id === inp.dataset.op);
      if (o) o.params[inp.dataset.par].value = e.target.value;
    };
  });
}

document.getElementById('addwire').onclick = () => {
  wireMode = 'pick-src';
  banner('click the source op');
};

document.getElementById('approve').onclick = async () => {
  graph.stats = {opCount: graph.ops.length, wireCount: graph.wires.length};
  await fetch('/approved', {method: 'POST', body: JSON.stringify(graph)});
  banner('Approved — agent is rebuilding.');
};

load();
```

`evidence.html`:

```html
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Attention Handoff — Param Evidence</title>
<style>
  body { margin: 0; font: 13px system-ui; background: #16161a; color: #ddd; }
  header { padding: 10px; background: #222; display: flex; gap: 16px;
           align-items: center; }
  header a { color: #6cf; }
  #items { padding: 10px; }
  .item { border: 1px solid #333; margin-bottom: 16px; padding: 8px; }
  .item h4 { margin: 0 0 6px 0; }
  .item small { color: #888; }
  .shot { position: relative; display: inline-block; max-width: 100%; }
  .shot img { max-width: 100%; display: block; image-rendering: pixelated; }
  .mask { position: absolute; border: 2px solid #f6c;
          background: rgba(255, 102, 204, 0.15); }
  table { border-collapse: collapse; margin-top: 6px; }
  td, th { border: 1px solid #333; padding: 3px 8px; }
</style>
</head>
<body>
<header>
  <a href="/approve">&larr; back to approve</a>
  <b>Param evidence</b>
  <span>every param-window crop, masked where a value was read</span>
</header>
<div id="items"></div>
<script src="/static/evidence.js"></script>
</body>
</html>
```

`evidence.js`:

```js
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
}

async function load() {
  const caps = await (await fetch('/captures')).json();
  const readings = await (await fetch('/readings')).json();
  const holder = document.getElementById('items');
  let shown = 0;
  for (const c of caps) {
    const r = readings[c.id];
    if (!r || r.kind !== 'param') continue;
    shown++;
    const boxes = r.boxes || {};
    let rows = '';
    for (const [p, v] of Object.entries(r.params || {})) {
      rows += '<tr><td>' + esc(p) + '</td><td>' + esc(v) + '</td><td>' +
              (boxes[p] ? 'masked' : '—') + '</td></tr>';
    }
    const item = document.createElement('div');
    item.className = 'item';
    item.innerHTML = '<h4>' + esc(r.opName) + ' <small>' +
      esc(r.opType || '?') + ' — ' + c.id + ' @' + c.t.toFixed(1) +
      's</small></h4><div class="shot"><img src="/crops/' + c.id +
      '.png"></div><table><tr><th>param</th><th>OCR value</th><th>mask</th>' +
      '</tr>' + rows + '</table>';
    holder.appendChild(item);
    const img = item.querySelector('img');
    img.onload = () => {
      const shot = item.querySelector('.shot');
      const sx = img.clientWidth / img.naturalWidth;
      const sy = img.clientHeight / img.naturalHeight;
      for (const [p, b] of Object.entries(boxes)) {
        const m = document.createElement('div');
        m.className = 'mask';
        m.style.left = (b[0] * sx) + 'px';
        m.style.top = (b[1] * sy) + 'px';
        m.style.width = (b[2] * sx) + 'px';
        m.style.height = (b[3] * sy) + 'px';
        m.title = p + ' = ' + r.params[p];
        shot.appendChild(m);
      }
    };
  }
  if (!shown) {
    holder.innerHTML = '<em>no param-window readings yet</em>';
  }
}

load();
```

- [ ] **Step 2: Manual verification with a fixture**

Write this fixture as `<scratch>/smoke/graph.json`:

```json
{ "ops": [
    {"id": "noise1", "opType": "noiseTOP", "confidence": 1.0,
     "params": {"period": {"value": "4", "t": 214.6,
                "history": [{"value": "1", "t": 88.2}]}},
     "sources": ["c001"]},
    {"id": "level1", "opType": "levelTOP", "confidence": 1.0,
     "params": {}, "sources": ["c002"]},
    {"id": "out1", "opType": "", "confidence": 1.0,
     "params": {}, "sources": ["c003"]}],
  "wires": [
    {"from": "noise1", "to": "level1", "toInlet": 0, "sources": ["c003"]},
    {"from": "level1", "to": "out1", "toInlet": 0, "sources": ["c003"]}],
  "conflicts": [
    {"kind": "unknown-optype", "detail": "op 'out1' has no op type",
     "captureIds": ["c003"]}],
  "stats": {"opCount": 3, "wireCount": 2},
  "opTypes": ["noiseTOP", "levelTOP", "outTOP", "nullTOP"] }
```

Also write `<scratch>/smoke/readings.json` (reuse a crop PNG made during Task 5 verification as `crops/c001.png`, or capture one fresh):

```json
{ "c001": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
           "params": {"period": "4"},
           "boxes": {"period": [10, 20, 200, 18]}} }
```

and make sure `captures.json` contains a matching `c001` record of type `param`.

Run the Task 5 server against `<scratch>/smoke`, open `http://127.0.0.1:8765/approve`, verify:
- [ ] Header shows "3 ops · 2 wires"; three nodes in depth columns, two curved wires; `out1` outlined orange (conflict)
- [ ] Click `out1` → inspector; set type to `outTOP` via datalist; dismiss the conflict → orange outline clears
- [ ] Rename `noise1` to `noise_main` → wire follows; param table row still edits
- [ ] `add wire` → click two nodes → wire appears; click a wire → confirm deletes it
- [ ] `period` row is highlighted (history) with tooltip "1 @88.2s"; edit value to `5`
- [ ] Approve → `approved.json` exists with `stats.opCount` matching the edited network, and `GET /status` returns `approved`
- [ ] `param evidence` link → `/evidence` lists the `c001` crop under "noise1 noiseTOP" with a pink mask rectangle at the `boxes` position (scaled with the image), a table row `period | 4 | masked`, and a hover tooltip `period = 4` on the mask

- [ ] **Step 3: Commit**

```powershell
git add .claude/skills/attention-handoff
git commit -m "feat(attention-handoff): approval UI, network diagram + param evidence page"
```

---

### Task 7: `rebuild_plan.py`

**Files:**
- Create: `.claude/skills/attention-handoff/tools/rebuild_plan.py`
- Test: `.claude/skills/attention-handoff/tools/tests/test_rebuild_plan.py`

**Interfaces:**
- Consumes: `approved.json` (graph.json shape).
- Produces: `python rebuild_plan.py <session_dir>` prints plan JSON: `{container, bus, opTypes, channels: [{name, value}], creates: [{name, opType, nodeX, nodeY}], channelParams: [{op, par, expr}], directParams: [{op, par, value, note}], wires: [{from, to, toInlet}]}`. This script NEVER touches TD — the agent executes the plan (Task 8). `--dry-run` is accepted and identical to the default (print only).

- [ ] **Step 1: Write the failing tests**

Create `.claude/skills/attention-handoff/tools/tests/test_rebuild_plan.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rebuild_plan import sanitize, is_numeric, channel_name, build_plan


class TestHelpers(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(sanitize("Noise 1!"), "noise_1")
        self.assertEqual(sanitize("dQw4w9WgXcQ"), "dqw4w9wgxcq")

    def test_is_numeric(self):
        self.assertTrue(is_numeric("4.5"))
        self.assertTrue(is_numeric(3))
        self.assertTrue(is_numeric(True))
        self.assertTrue(is_numeric(" 0.5 "))
        self.assertFalse(is_numeric("sparse"))
        self.assertFalse(is_numeric("op('ramp1')"))

    def test_channel_name_prefix_and_cap(self):
        taken = set()
        name = channel_name("x" * 80, "op", "par", taken)
        self.assertTrue(name.startswith("tut_"))
        self.assertLessEqual(len(name), 60)

    def test_channel_collision_gets_suffix(self):
        taken = set()
        a = channel_name("vid", "noise1", "period", taken)
        b = channel_name("vid", "noise1", "period", taken)
        self.assertEqual(a, "tut_vid_noise1_period")
        self.assertNotEqual(a, b)
        self.assertTrue(b.endswith("_2"))


class TestBuildPlan(unittest.TestCase):
    def test_numeric_vs_string_split(self):
        graph = {"ops": [{"id": "noise1", "opType": "noiseTOP",
                          "params": {"period": {"value": "4"},
                                     "type": {"value": "sparse"}}}],
                 "wires": []}
        plan = build_plan(graph, "abc123")
        self.assertEqual(plan["container"], "tutorial_abc123")
        self.assertEqual(plan["bus"], "/project1/master_controls")
        self.assertEqual(len(plan["channels"]), 1)
        self.assertEqual(plan["channels"][0]["value"], 4.0)
        self.assertEqual(plan["channelParams"][0]["expr"],
                         "op('/project1/master_controls')"
                         "['tut_abc123_noise1_period']")
        self.assertEqual(len(plan["directParams"]), 1)
        self.assertEqual(plan["directParams"][0]["value"], "sparse")

    def test_layout_follows_wire_depth(self):
        graph = {"ops": [{"id": "b", "opType": "levelTOP", "params": {}},
                         {"id": "a", "opType": "noiseTOP", "params": {}}],
                 "wires": [{"from": "a", "to": "b", "toInlet": 0}]}
        plan = build_plan(graph, "v")
        xs = {c["name"]: c["nodeX"] for c in plan["creates"]}
        self.assertLess(xs["a"], xs["b"])
        self.assertEqual(plan["wires"],
                         [{"from": "a", "to": "b", "toInlet": 0}])
        self.assertEqual(plan["opTypes"], ["levelTOP", "noiseTOP"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: `ModuleNotFoundError: No module named 'rebuild_plan'`

- [ ] **Step 3: Implement**

Create `.claude/skills/attention-handoff/tools/rebuild_plan.py`:

```python
"""Turn approved.json into an ordered rebuild plan for the agent.

Prints plan JSON: container name, master_controls channels, op creates
(with left-to-right layout), channel-referenced params, direct-set params
(non-numeric - CHOP channels carry numbers only), and wires.

This script never touches TD. The agent executes the plan over the MCP
bridge; --dry-run is accepted and identical to the default (print only).

Usage: python rebuild_plan.py <session_dir> [--dry-run]
"""
import json
import os
import re
import sys

CHAN_MAX = 60
BUS = "/project1/master_controls"


def sanitize(text):
    return re.sub(r"[^a-z0-9_]", "_", str(text).lower()).strip("_")


def is_numeric(value):
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value).strip())
        return True
    except ValueError:
        return False


def channel_name(video_id, op_name, par_name, taken):
    base = "tut_%s_%s_%s" % (sanitize(video_id), sanitize(op_name),
                             sanitize(par_name))
    name = base[:CHAN_MAX]
    n = 2
    while name in taken:
        suffix = "_%d" % n
        name = base[:CHAN_MAX - len(suffix)] + suffix
        n += 1
    taken.add(name)
    return name


def compute_depths(ops, wires):
    depth = {o["id"]: 0 for o in ops}
    incoming = {o["id"]: [] for o in ops}
    for w in wires:
        if w["to"] in incoming and w["from"] in depth:
            incoming[w["to"]].append(w["from"])
    for _ in range(len(ops)):
        changed = False
        for o in ops:
            for src in incoming[o["id"]]:
                if depth[src] + 1 > depth[o["id"]]:
                    depth[o["id"]] = depth[src] + 1
                    changed = True
        if not changed:
            break
    return depth


def build_plan(graph, video_id):
    ops, wires = graph["ops"], graph["wires"]
    depth = compute_depths(ops, wires)
    rows = {}
    creates = []
    for o in sorted(ops, key=lambda o: (depth[o["id"]], o["id"])):
        col = depth[o["id"]]
        row = rows.get(col, 0)
        rows[col] = row + 1
        creates.append({"name": o["id"], "opType": o["opType"],
                        "nodeX": col * 200, "nodeY": -row * 160})
    taken = set()
    channels, chan_params, direct_params = [], [], []
    for o in ops:
        for pname, slot in (o.get("params") or {}).items():
            value = slot["value"]
            if is_numeric(value):
                chan = channel_name(video_id, o["id"], pname, taken)
                channels.append({"name": chan,
                                 "value": float(str(value).strip())
                                 if not isinstance(value, bool)
                                 else float(value)})
                chan_params.append({"op": o["id"], "par": pname,
                                    "expr": "op('%s')['%s']" % (BUS, chan)})
            else:
                direct_params.append({
                    "op": o["id"], "par": pname, "value": value,
                    "note": "non-numeric; set directly "
                            "(CHOP channels are numbers)"})
    return {"container": "tutorial_%s" % sanitize(video_id),
            "bus": BUS,
            "opTypes": sorted({o["opType"] for o in ops if o["opType"]}),
            "channels": channels,
            "creates": creates,
            "channelParams": chan_params,
            "directParams": direct_params,
            "wires": [{"from": w["from"], "to": w["to"],
                       "toInlet": w.get("toInlet", 0)} for w in wires]}


def main():
    session_dir = sys.argv[1]
    with open(os.path.join(session_dir, "approved.json"), "r",
              encoding="utf-8") as f:
        graph = json.load(f)
    video_id = os.path.basename(os.path.normpath(session_dir))
    print(json.dumps(build_plan(graph, video_id), indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v`
Expected: 23 tests PASS

- [ ] **Step 5: Commit**

```powershell
git add .claude/skills/attention-handoff
git commit -m "feat(attention-handoff): rebuild plan generator with master_controls channels"
```

---

### Task 8: SKILL.md, op-type fallback list, tutorials/.gitignore

**Files:**
- Create: `.claude/skills/attention-handoff/SKILL.md`
- Create: `.claude/skills/attention-handoff/tools/static/optypes.json`
- Create: `tutorials/.gitignore`

**Interfaces:**
- Consumes: every prior task — SKILL.md is the orchestration script the agent follows at `/attention-handoff` time.

- [ ] **Step 1: Write `tutorials/.gitignore`**

```
video.*
*/video.*
```

- [ ] **Step 2: Write `optypes.json`** (fallback when the TD bridge is down at extract time)

```json
["addSOP","analyzeTOP","audiodeviceinCHOP","audiodeviceoutCHOP",
 "audiofileinCHOP","baseCOMP","blurTOP","boxSOP","buttonCOMP","cacheTOP",
 "cameraCOMP","chopexecuteDAT","choptoDAT","choptoTOP","circleSOP",
 "circleTOP","compositeTOP","constantCHOP","constantMAT","constantTOP",
 "containerCOMP","crossTOP","datexecuteDAT","displaceTOP","edgeTOP",
 "evaluateDAT","executeDAT","expressionCHOP","feedbackCHOP","feedbackTOP",
 "filterCHOP","fitCHOP","flipTOP","geometryCOMP","glslTOP","glslmultiTOP",
 "gridSOP","hsvadjustTOP","infoCHOP","infoDAT","keyboardinCHOP","lagCHOP",
 "levelTOP","lfoCHOP","lightCOMP","limitCHOP","lineSOP","logicCHOP",
 "lookupCHOP","lookupTOP","luminanceTOP","mathCHOP","mergeCHOP","mergeDAT",
 "mergeSOP","monochromeTOP","moviefileinTOP","moviefileoutTOP","noiseCHOP",
 "noiseSOP","noiseTOP","nullCHOP","nullCOMP","nullDAT","nullSOP","nullTOP",
 "opexecuteDAT","oscinCHOP","oscinDAT","oscoutCHOP","oscoutDAT","outCHOP",
 "outSOP","outTOP","overTOP","panelCHOP","parameterCHOP","parameterexecuteDAT",
 "patternCHOP","phongMAT","pointfileinTOP","polyreduceSOP","rampTOP",
 "rectangleTOP","renderTOP","renderpassTOP","reorderTOP","resampleCHOP",
 "resolutionTOP","rgbkeyTOP","scriptCHOP","scriptDAT","scriptSOP","scriptTOP",
 "selectCHOP","selectCOMP","selectDAT","selectTOP","shuffleCHOP",
 "slopeCHOP","sphereSOP","speedCHOP","spliceCHOP","springCHOP","switchCHOP",
 "switchTOP","tableDAT","textDAT","textTOP","threshold","thresholdTOP",
 "timelineCHOP","timerCHOP","toptoCHOP","transformSOP","transformTOP",
 "triggerCHOP","tubeSOP","videodeviceinTOP","videodeviceoutTOP","webserverDAT",
 "windowCOMP"]
```

- [ ] **Step 3: Write `SKILL.md`**

````markdown
---
name: attention-handoff
description: HITL TouchDesigner tutorial scraping — given a tutorial video URL, the human box-selects param windows and network grabs in a local browser app; the agent vision-reads the crops, builds a network graph for browser approval, then rebuilds the network in TD via the MCP bridge with all non-default params routed through /project1/master_controls.
---

# Attention Handoff

Spec: `docs/superpowers/specs/2026-08-04-attention-handoff-design.md`.
Session dir: `tutorials/<video-id>/` (video-id = YouTube ID, or a slug you
pick for non-YouTube URLs; the dir basename becomes the channel-name prefix
and container suffix).

## Stage 1 — Download

```
yt-dlp -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" \
  --merge-output-format mp4 -o "tutorials/<video-id>/video.mp4" <url>
```

If yt-dlp is missing or fails: STOP and give the user this exact command to
run themselves. Do not scrape the streaming page.

## Stage 2 — Capture (human)

Start the server in the background and tell the user the capture flow
(modes 1/2/3, frame-step keys, Done button):

```
python .claude/skills/attention-handoff/tools/server.py tutorials/<video-id> --open
```

Poll `GET http://127.0.0.1:8765/status` (curl or urllib via Bash) every
~30 s until `state` is `captured`. Do not proceed before then.

## Stage 3 — Extract (agent)

1. If the TD bridge is up, query valid op types and write
   `tutorials/<video-id>/optypes.json`:
   `execute_script`: `import td; print(sorted(n for n in dir(td) if not n.startswith('_') and n[0].islower() and n.endswith(('TOP','CHOP','SOP','DAT','COMP','MAT','POP'))))`
   If the bridge is down, copy `tools/static/optypes.json` there instead.
2. Read `captures.json`, then Read every crop PNG under `crops/` and build
   `readings.json` — `{captureId: reading}` with these reading kinds:
   - param-window crop → `{"kind":"param","opName":"<title-bar op name>",
     "opType":"<type from dialog>","params":{"<par>":"<value>"},
     "boxes":{"<par>":[x,y,w,h]}}`
     Record ONLY params visibly set to non-default values (bold/edited in
     the dialog). Values as strings exactly as displayed. `boxes` gives the
     crop-pixel bounding box of each param row you read — the `/evidence`
     page renders these as masks so the human can audit every read.
   - network crop → `{"kind":"network","nodes":[{"label":"<bottom title
     text, possibly truncated>","opType":"<type if visually identifiable>"}],
     "wires":[{"from":"<label>","to":"<label>","toInlet":0}]}`
   - pair op-node crop → `{"kind":"opnode","label":"<node label>"}`
   - anything illegible → `{"kind":"unreadable"}` — never guess.
3. Run `python .claude/skills/attention-handoff/tools/matching.py
   tutorials/<video-id>` → writes `graph.json`.
4. Tell the user to open `http://127.0.0.1:8765/approve` (network diagram +
   op count; the `param evidence` link shows every param crop with masks and
   the extracted values for auditing), then poll `/status` until `approved`.

## Stage 4 — Rebuild (agent, TD MCP bridge)

Run `python .claude/skills/attention-handoff/tools/rebuild_plan.py
tutorials/<video-id>` to get the plan. If the user asked for a dry run,
show the plan and stop. Otherwise:

1. `save_checkpoint` on `/project1`. NEVER `project.save()` (untitled
   projects pop a modal that freezes the bridge).
2. Validate `plan.opTypes` via `execute_script`
   (`hasattr(td, t) for each`). Unknown types → STOP, report, ask the user
   to fix at `/approve` and re-approve.
3. Create the container: `create_operator` `containerCOMP` named
   `plan.container` in `/project1`.
4. Bus channels: inspect `/project1/master_controls` FIRST and follow its
   existing structure (per AGENTS.md). Constant CHOPs cap at 40 channels —
   if adding `plan.channels` would overflow, create a new Constant CHOP
   inside master_controls (named `tut_<video-id>`) and merge it into the
   bus output the same way existing sources are merged. Set each channel
   to its plan value.
5. Create ops per `plan.creates` inside the container with the given
   `nodeX`/`nodeY` (these are network coords for MY new ops only — never
   move user ops; layout.json pinning does not apply inside the new
   container).
6. `plan.channelParams`: set each `par.expr` to the plan expr and mode to
   EXPRESSION. Verify each with `get_par_value`.
7. `plan.directParams`: set values directly (menu tokens/strings). Verify.
8. Wire per `plan.wires` with `connect_operators` (respect `toInlet`).
9. `get_errors` on the container. Report: ops created/failed, channels
   added, params set/rejected (with reasons), wires made. Failures are
   reported, never silently skipped.

## Notes

- Server is 127.0.0.1-only; default port 8765 (`--port` to change).
- All non-numeric param values bypass the bus (CHOP channels are numbers);
  they are listed in `plan.directParams` with a note.
- Session artifacts except the video are committable; `tutorials/.gitignore`
  excludes video files.
````

- [ ] **Step 4: End-to-end smoke test (no TD needed)**

1. Reuse `<scratch>/smoke` as a fake session: keep `video.mp4`, delete any earlier `captures.done`/`approved.json`/`graph.json`.
2. Start the server; make 2 param captures + 1 network capture on any frames; click Done.
3. Hand-write `readings.json` naming two ops and one wire (per the SKILL.md formats), run `python .claude/skills/attention-handoff/tools/matching.py <scratch>/smoke` — verify `graph.json` has 2 ops, 1 wire.
4. Open `/approve`, edit something, Approve — verify `approved.json`.
5. Run `python .claude/skills/attention-handoff/tools/rebuild_plan.py <scratch>/smoke` — verify plan JSON has container, channels with `tut_smoke_` prefix, creates with increasing `nodeX` along the wire, and the wire.
6. Run the full unit suite one final time: `python -m unittest discover -s .claude/skills/attention-handoff/tools/tests -v` — all PASS.

- [ ] **Step 5: Commit**

```powershell
git add .claude/skills/attention-handoff tutorials/.gitignore
git commit -m "feat(attention-handoff): SKILL.md workflow, op-type fallback, tutorials gitignore"
```

---

## Self-Review Notes

- Spec coverage: download (T8 SKILL.md), capture app incl. pair mode + pass/Esc degrade (T5), data model (T2/T3), matching rules 1-5 (T1/T2), approval UI with SVG diagram/op count/conflicts/editing (T6), rebuild with checkpoint-first, pre-flight opType validation, master_controls routing, layout, get_errors report (T7/T8), error handling (unreadable→conflict T2; yt-dlp stop T8; checkpoint restore T8), testing (unit suites T1-T4/T7, no-TD manual checks T5/T6, dry-run T7/T8). Spec's "pass and accept only param window if necessary" maps to: Esc cancels the pending pair's op box, or the human just uses mode 1 — noted in SKILL.md capture-flow explanation and T5 checklist.
- Type consistency: graph.json shape identical across matching.py output, approve.js consumption, approved.json, rebuild_plan.py input. Capture record fields identical across server.py, capture.js, matching.py.
