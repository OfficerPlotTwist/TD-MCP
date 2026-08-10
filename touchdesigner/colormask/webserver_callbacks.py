"""Callbacks for cont_colormask/webserver_colormask (port 8903 — kept far from
the MCP bridge's 9980; 8899 is cont_mask_combiner, 8902 was the retired
external server.py).

Serves the colormask webapp from webapp/static and handles /frame and /send
directly inside TD — no bridge hop. Source of truth is this repo file; the
in-TD textDAT (text_webserver_cb) is loaded from it.
Only stdlib at module import time so tests can import it outside TD.
"""

import base64
import json
import os
import tempfile

APP_DIR = r'C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\colormask\webapp\static'
# Trailing separator so a sibling dir sharing APP_DIR's prefix can't pass the
# startswith() containment check below.
APP_DIR_PREFIX = os.path.join(APP_DIR, '')
CONTENT_TYPES = {'.html': 'text/html; charset=utf-8',
                 '.js': 'text/javascript; charset=utf-8',
                 '.css': 'text/css; charset=utf-8'}
MAX_BODY = 32 * 1024 * 1024
MAX_RULES = 32
RULE_TYPES = ('wand', 'bycolor')
MAX_STENCIL_PIXELS = 1_048_576


def validate_rules(rules):
    """Normalize webapp rule dicts to (type_int, r, g, b, tol) tuples.

    type_int: 0 = wand (stencil-gated), 1 = bycolor (frame-wide).
    Colors and tol are normalized floats. Raises ValueError on any problem.
    """
    if not isinstance(rules, list):
        raise ValueError('rules must be a list')
    if len(rules) > MAX_RULES:
        raise ValueError('too many rules: %d > %d' % (len(rules), MAX_RULES))
    out = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            raise ValueError('rule %d: must be an object' % i)
        t = r.get('type')
        if t not in RULE_TYPES:
            raise ValueError('rule %d: bad type %r' % (i, t))
        color = r.get('color')
        if (not isinstance(color, (list, tuple)) or len(color) != 3
                or not all(isinstance(c, (int, float)) and 0.0 <= c <= 1.0
                           for c in color)):
            raise ValueError('rule %d: color must be 3 floats in 0..1' % i)
        tol = r.get('tol')
        if not isinstance(tol, (int, float)) or not 0.0 <= tol <= 2.0:
            raise ValueError('rule %d: tol must be a float in 0..2' % i)
        out.append((1 if t == 'bycolor' else 0,
                    float(color[0]), float(color[1]), float(color[2]),
                    float(tol)))
    return out


def onHTTPRequest(webServerDAT, request, response):
    try:
        return _dispatch(webServerDAT, request, response)
    except Exception as e:
        response['statusCode'] = 500
        response['statusReason'] = 'Internal Server Error'
        response['content-type'] = 'application/json'
        response['data'] = json.dumps({'ok': False, 'error': str(e)})
        return response


def _dispatch(webServerDAT, request, response):
    uri = request['uri'].split('?')[0]
    method = request['method']
    if method == 'GET':
        if uri == '/frame':
            return _serve_frame(webServerDAT, response)
        if uri == '/':
            uri = '/index.html'
        return _serve_static(uri, response)
    if method == 'POST' and uri == '/send':
        return _handle_send(webServerDAT, request, response)
    return _err(response, 404, 'unknown endpoint %s %s' % (method, uri),
                reason='Not Found')


def _serve_static(uri, response):
    ext = os.path.splitext(uri)[1]
    fspath = os.path.normpath(os.path.join(APP_DIR, uri.lstrip('/')))
    if not fspath.startswith(APP_DIR_PREFIX) or ext not in CONTENT_TYPES:
        return _err(response, 404, 'not found', reason='Not Found')
    if not os.path.exists(fspath):
        return _err(response, 404, 'not found', reason='Not Found')
    with open(fspath, 'rb') as f:
        response['data'] = f.read()
    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['content-type'] = CONTENT_TYPES[ext]
    response['Cache-Control'] = 'no-store'
    return response


def _serve_frame(webServerDAT, response):
    src = webServerDAT.parent().op('null_src')
    if src is None:
        return _err(response, 500, 'null_src missing',
                    reason='Internal Server Error')
    tmp = os.path.join(tempfile.gettempdir(), 'colormask_frame.png')
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
        if len(body) > MAX_BODY:
            return _err(response, 400, 'body too large')
        body = body.decode('utf-8')
    if len(body) > MAX_BODY:
        return _err(response, 400, 'body too large')
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            return _err(response, 400, 'payload must be a JSON object')
        rules = validate_rules(payload.get('rules', []))
        st = payload.get('stencil')
        if st is not None and not isinstance(st, dict):
            return _err(response, 400, 'stencil must be a JSON object or absent')
        st = st or {}
        w, h = int(st.get('w', 1)), int(st.get('h', 1))
        if w < 1 or h < 1 or w * h > MAX_STENCIL_PIXELS:
            return _err(response, 400, 'invalid stencil dimensions: %dx%d' % (w, h))
        raw = base64.b64decode(st['data']) if st.get('data') else bytes(w * h)
        if len(raw) != w * h:
            return _err(response, 400,
                        'stencil size mismatch: %d != %d' % (len(raw), w * h))
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return _err(response, 400, str(e))

    import numpy as np
    comp = webServerDAT.parent()
    # Browser stencil rows are top-down; TD numpy arrays are bottom-up.
    arr = np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(h, w)).copy()
    comp.store('colormask_stencil', {'w': w, 'h': h, 'data': arr})
    comp.store('colormask_rules', list(rules))
    comp.op('script_stencil').cook(force=True)
    comp.op('script_rules').cook(force=True)

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['content-type'] = 'application/json'
    response['Cache-Control'] = 'no-store'
    response['data'] = json.dumps({'ok': True, 'rules': len(rules)})
    return response


def _err(response, code, msg, reason='Bad Request'):
    response['statusCode'] = code
    response['statusReason'] = reason
    response['content-type'] = 'application/json'
    response['data'] = json.dumps({'ok': False, 'error': msg})
    return response
