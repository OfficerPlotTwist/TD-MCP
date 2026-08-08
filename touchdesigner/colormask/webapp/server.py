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
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import protocol

BRIDGE_URL = "http://127.0.0.1:9980"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
# Trailing separator so a sibling dir sharing STATIC_DIR's prefix (e.g. "static2")
# can't pass the startswith() containment check below.
STATIC_DIR_PREFIX = os.path.join(STATIC_DIR, "")
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript",
                 ".css": "text/css"}
MAX_STENCIL_PIXELS = 1_048_576


def bridge_post(path, payload):
    """POST JSON to the TD bridge. Returns (ok, parsed_json_or_error_str).

    - ok=True: 2xx response with JSON body, or 4xx/5xx response from bridge with JSON body
    - ok=False: connection error (refused, timeout, etc.)
    """
    try:
        req = urllib.request.Request(
            BRIDGE_URL + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return True, json.loads(e.read().decode("utf-8"))
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def bridge_get(path):
    """GET from the TD bridge. Returns (ok, parsed_json_or_error_str).

    - ok=True: 2xx response with JSON body, or 4xx/5xx response from bridge with JSON body
    - ok=False: connection error (refused, timeout, etc.)
    """
    try:
        with urllib.request.urlopen(BRIDGE_URL + path, timeout=30) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return True, json.loads(e.read().decode("utf-8"))
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def process_send(body, post):
    """Validate a /send body and push it to TD. Returns (status, json_obj)."""
    try:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            return 400, {"error": "payload must be a JSON object"}
        rules = protocol.validate_rules(payload.get("rules", []))
        st = payload.get("stencil")
        if st is not None and not isinstance(st, dict):
            return 400, {"error": "stencil must be a JSON object or absent"}
        st = st or {}
        w, h = int(st.get("w", 1)), int(st.get("h", 1))
        if w < 1 or h < 1 or w * h > MAX_STENCIL_PIXELS:
            return 400, {"error": f"invalid stencil dimensions: {w}x{h}"}
        raw = base64.b64decode(st["data"]) if st.get("data") else bytes(w * h)
        if len(raw) != w * h:
            return 400, {"error": f"stencil size mismatch: {len(raw)} != {w*h}"}
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return 400, {"error": str(e)}
    script = protocol.build_send_script(rules, w, h, protocol.encode_stencil(raw))
    ok, result = post("/execute", {"script": script,
                                   "undo_label": "colormask SEND"})
    if not ok:
        return 503, {"error": "TD bridge unreachable", "detail": result}
    # The bridge's /execute reports every *currently present* Error DAT row,
    # even ambient ones unrelated to this script — so a successful SEND can
    # carry stale/unrelated errors. Trust the script's own success marker
    # (always printed by _SEND_TEMPLATE on completion) over that ambient list.
    if "OK rules=" in result.get("output", ""):
        resp = {"ok": True, "rules": len(rules)}
        if result.get("errors"):
            resp["warnings"] = result["errors"]
        return 200, resp
    return 502, {"error": "TD execute failed", "detail": result.get("errors")}


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
    png = base64.b64decode(result["image_b64"])
    # The bridge always writes its own timestamped PNG under save_dir; we've
    # already decoded the bytes we need, so best-effort delete it here rather
    # than letting %TEMP%\colormask_frames grow unboundedly (same machine,
    # so the saved_to path is always local).
    try:
        os.remove(result.get("saved_to"))
    except (OSError, TypeError):
        pass
    return 200, png, None


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
        if not (fspath == STATIC_DIR or fspath.startswith(STATIC_DIR_PREFIX)) \
                or ext not in CONTENT_TYPES:
            return self._json({"error": "not found"}, 404)
        if not os.path.exists(fspath):
            return self._json({"error": "not found"}, 404)
        with open(fspath, "rb") as f:
            return self._bytes(f.read(), CONTENT_TYPES[ext])

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/send":
            return self._json({"error": "not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return self._json({"error": "invalid Content-Length"}, 400)
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
