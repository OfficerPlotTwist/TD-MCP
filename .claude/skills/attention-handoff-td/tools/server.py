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

    def load_seq(self):
        try:
            with open(self.path("capture.seq"), "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def save_seq(self, num):
        tmp = self.path("capture.seq.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(num))
        os.replace(tmp, self.path("capture.seq"))


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
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

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
        if code == 206 and start > end:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
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
        elif path == "/video":
            self.send_video()
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        origin = self.headers.get("Origin")
        if origin and origin != "http://127.0.0.1:%d" % self.server.server_address[1]:
            return self.send_json({"error": "forbidden origin"}, 403)
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
                seq = SESSION.load_seq()
                next_num = max(seq, max(nums) if nums else 0) + 1
                cid = "c%03d" % next_num
                SESSION.save_seq(next_num)
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
        elif path == "/retag":
            new_type = data.get("type")
            if new_type not in ("param", "network", "network-whole"):
                return self.send_json({"error": "invalid type"}, 400)
            rec = None
            with SESSION.lock:
                caps = SESSION.load_json("captures.json", [])
                for c in caps:
                    if c["id"] == data.get("id"):
                        rec = c
                        break
                if rec is not None:
                    rec["type"] = new_type
                    rec["pairId"] = None
                    rec["role"] = None
                    SESSION.save_json("captures.json", caps)
            if rec is None:
                return self.send_json({"error": "unknown id"}, 404)
            self.send_json(rec)
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
