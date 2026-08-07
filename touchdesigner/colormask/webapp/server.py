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
