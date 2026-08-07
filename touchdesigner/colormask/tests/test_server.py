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
