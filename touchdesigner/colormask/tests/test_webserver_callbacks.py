"""Pure-logic tests for the in-TD webserver callbacks (no TD needed).

Fake op objects stand in for the WebServer DAT, its parent COMP, and the
TOPs/Script TOPs the callbacks touch. Run: python -m pytest tests/ -q
"""
import base64
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import webserver_callbacks as wc


class FakeTop:
    def __init__(self):
        self.saved_png = b'\x89PNG_fake_frame'
        self.cooked = []

    def save(self, path):
        with open(path, 'wb') as f:
            f.write(self.saved_png)

    def cook(self, force=False):
        self.cooked.append(force)


class FakeComp:
    def __init__(self, ops):
        self.ops = ops
        self.stored = {}
        self.cook_order = []
        for name, o in ops.items():
            if isinstance(o, FakeTop):
                o._comp, o._name = self, name

    def op(self, name):
        o = self.ops.get(name)
        if isinstance(o, FakeTop):
            orig = o.cook
            def cook(force=False, _n=name, _o=orig):
                self.cook_order.append(_n)
                _o(force=force)
            o.cook = cook
        return o

    def store(self, key, value):
        self.stored[key] = value


class FakeWS:
    def __init__(self, comp):
        self._comp = comp

    def parent(self):
        return self._comp


def make_ws(**ops):
    defaults = {'null_src': FakeTop(), 'script_stencil': FakeTop(),
                'script_rules': FakeTop()}
    defaults.update(ops)
    return FakeWS(FakeComp(defaults))


def req(method, uri, data=b''):
    return {'method': method, 'uri': uri, 'data': data}


def hit(ws, method, uri, data=b''):
    return wc.onHTTPRequest(ws, req(method, uri, data), {})


def body_json(resp):
    return json.loads(resp['data'])


# ---------- validate_rules ----------

def test_validate_rules_ok():
    rules = [{'type': 'wand', 'color': [0.1, 0.2, 0.3], 'tol': 0.5},
             {'type': 'bycolor', 'color': [1, 0, 0], 'tol': 0}]
    out = wc.validate_rules(rules)
    assert out == [(0, 0.1, 0.2, 0.3, 0.5), (1, 1.0, 0.0, 0.0, 0.0)]


@pytest.mark.parametrize('bad', [
    'not a list',
    [{'type': 'nope', 'color': [0, 0, 0], 'tol': 0}],
    [{'type': 'wand', 'color': [0, 0], 'tol': 0}],
    [{'type': 'wand', 'color': [0, 0, 2], 'tol': 0}],
    [{'type': 'wand', 'color': [0, 0, 0], 'tol': 3}],
    [{'type': 'wand', 'color': [0, 0, 0], 'tol': -0.1}],
    ['not a dict'],
])
def test_validate_rules_rejects(bad):
    with pytest.raises(ValueError):
        wc.validate_rules(bad)


def test_validate_rules_cap():
    ok = [{'type': 'wand', 'color': [0, 0, 0], 'tol': 0}] * wc.MAX_RULES
    assert len(wc.validate_rules(ok)) == wc.MAX_RULES
    with pytest.raises(ValueError):
        wc.validate_rules(ok + ok[:1])


# ---------- static serving ----------

def test_serves_index_at_root():
    resp = hit(make_ws(), 'GET', '/')
    assert resp['statusCode'] == 200
    assert resp['content-type'].startswith('text/html')
    assert resp['Cache-Control'] == 'no-store'
    assert b'app.js' in resp['data']


def test_serves_js_and_css():
    for uri, ctype in (('/app.js', 'text/javascript'),
                       ('/style.css', 'text/css')):
        resp = hit(make_ws(), 'GET', uri)
        assert resp['statusCode'] == 200
        assert resp['content-type'].startswith(ctype)


def test_static_traversal_blocked():
    resp = hit(make_ws(), 'GET', '/../webserver_callbacks.py')
    assert resp['statusCode'] == 404


def test_static_unknown_ext_and_missing_404():
    assert hit(make_ws(), 'GET', '/frame.png')['statusCode'] == 404
    assert hit(make_ws(), 'GET', '/nope.js')['statusCode'] == 404


def test_unknown_endpoint_404():
    assert hit(make_ws(), 'POST', '/nope')['statusCode'] == 404
    assert hit(make_ws(), 'PUT', '/send')['statusCode'] == 404


# ---------- /frame ----------

def test_frame_returns_png_bytes():
    ws = make_ws()
    resp = hit(ws, 'GET', '/frame')
    assert resp['statusCode'] == 200
    assert resp['content-type'] == 'image/png'
    assert resp['data'] == ws.parent().ops['null_src'].saved_png


def test_frame_missing_null_src_500():
    ws = FakeWS(FakeComp({}))
    resp = hit(ws, 'GET', '/frame')
    assert resp['statusCode'] == 500


# ---------- /send ----------

def send_payload(rules=None, stencil=None):
    p = {}
    if rules is not None:
        p['rules'] = rules
    if stencil is not None:
        p['stencil'] = stencil
    return json.dumps(p).encode('utf-8')


def test_send_happy_path_stores_flipped_and_cooks():
    ws = make_ws()
    w, h = 3, 2
    raw = bytes([1, 2, 3, 4, 5, 6])          # row0 (top) = 1,2,3
    rules = [{'type': 'wand', 'color': [0.5, 0.5, 0.5], 'tol': 0.25}]
    stencil = {'w': w, 'h': h, 'data': base64.b64encode(raw).decode()}
    resp = hit(ws, 'POST', '/send', send_payload(rules, stencil))
    assert resp['statusCode'] == 200
    assert body_json(resp) == {'ok': True, 'rules': 1}
    comp = ws.parent()
    st = comp.stored['colormask_stencil']
    assert (st['w'], st['h']) == (w, h)
    # flipud: browser top row must land in the LAST numpy row (TD bottom-up)
    assert st['data'].tolist() == [[4, 5, 6], [1, 2, 3]]
    assert comp.stored['colormask_rules'] == [(0, 0.5, 0.5, 0.5, 0.25)]
    assert comp.cook_order == ['script_stencil', 'script_rules']


def test_send_absent_stencil_data_zero_fills():
    ws = make_ws()
    resp = hit(ws, 'POST', '/send',
               send_payload([], {'w': 2, 'h': 2}))
    assert resp['statusCode'] == 200
    st = ws.parent().stored['colormask_stencil']
    assert st['data'].tolist() == [[0, 0], [0, 0]]


@pytest.mark.parametrize('body,msg', [
    (b'null', 'object'),
    (b'[]', 'object'),
    (b'{"rules": "x"}', 'list'),
    (b'{"rules": [], "stencil": 5}', 'stencil'),
    (b'{"rules": [], "stencil": {"w": -1, "h": 4}}', 'dimensions'),
    (b'{"rules": [], "stencil": {"w": 99999, "h": 99999}}', 'dimensions'),
    (b'{"rules": [], "stencil": {"w": 4, "h": 4, "data": "AAAA"}}', 'mismatch'),
])
def test_send_bad_payloads_400(body, msg):
    ws = make_ws()
    resp = hit(ws, 'POST', '/send', body)
    assert resp['statusCode'] == 400
    assert msg in body_json(resp)['error']
    assert ws.parent().stored == {}          # nothing persisted on failure


def test_send_invalid_json_400():
    resp = hit(make_ws(), 'POST', '/send', b'{not json')
    assert resp['statusCode'] == 400


def test_internal_error_500():
    class Boom:
        def parent(self):
            raise RuntimeError('boom')
    resp = wc.onHTTPRequest(Boom(), req('GET', '/frame'), {})
    assert resp['statusCode'] == 500
    assert body_json(resp)['ok'] is False
