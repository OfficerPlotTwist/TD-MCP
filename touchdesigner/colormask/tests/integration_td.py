"""Integration check against the LIVE TD session. Run manually:

    python touchdesigner/colormask/tests/integration_td.py

Requires: TD running with the MCP bridge on :9980 (setup/readback only) and
/project1/cont_colormask built with its in-TD web server on :8903 (the real
SEND path — same endpoint the webapp posts to). Creates a temporary 64x64 red
constant wired into in1, sends rules through POST /send, reads out_mask back,
then cleans up.
"""
import base64
import json
import urllib.request

BRIDGE_URL = "http://127.0.0.1:9980"
APP_URL = "http://127.0.0.1:8903"

W = H = 64


def run(script, label):
    req = urllib.request.Request(
        BRIDGE_URL + "/execute",
        data=json.dumps({"script": script, "undo_label": label}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("errors"):
        raise SystemExit(f"TD error in {label!r}: {result['errors']}")
    return result.get("output", "")


def send(rules_dicts, stencil_raw, w=W, h=H):
    payload = {"rules": rules_dicts,
               "stencil": {"w": w, "h": h,
                           "data": base64.b64encode(stencil_raw).decode()}}
    req = urllib.request.Request(
        APP_URL + "/send", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if not result.get("ok"):
        raise SystemExit(f"/send failed: {result}")
    return result


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
